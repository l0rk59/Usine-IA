"""Persistance SQLite : quotas, cache des reponses IA, catalogue produits.

Une seule base (atelier/usine.db), mode WAL, safe pour Termux.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import (Any, Callable, Dict, Iterator, List, Optional, Sequence,
                    Tuple)

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS appels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fournisseur TEXT NOT NULL,
    modele TEXT,
    ts REAL NOT NULL,
    jour TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 1,
    tokens INTEGER DEFAULT 0,
    latence REAL DEFAULT 0,
    erreur TEXT,
    cle_id TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_appels_f_ts ON appels(fournisseur, ts);
CREATE INDEX IF NOT EXISTS idx_appels_f_jour ON appels(fournisseur, jour);
CREATE INDEX IF NOT EXISTS idx_appels_cle ON appels(fournisseur, cle_id, jour);

CREATE TABLE IF NOT EXISTS cles_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fournisseur TEXT NOT NULL,
    cle_id TEXT NOT NULL,
    raison TEXT,
    repos REAL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cles_journal ON cles_journal(fournisseur, cle_id);

CREATE TABLE IF NOT EXISTS cache (
    cle TEXT PRIMARY KEY,
    contenu TEXT NOT NULL,
    fournisseur TEXT,
    modele TEXT,
    cree_le REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS produits (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    titre TEXT NOT NULL,
    sujet TEXT,
    audience TEXT,
    langue TEXT,
    statut TEXT NOT NULL DEFAULT 'en_cours',
    dossier TEXT,
    meta TEXT,
    serie TEXT,
    rang INTEGER,
    cree_le REAL NOT NULL,
    maj_le REAL NOT NULL
);

-- Une serie : le monde et la distribution qu'un tome transmet au suivant.
-- La bible y est stockee en JSON parce que sa forme suit celle de la fiction
-- et changera avec elle ; la normaliser en colonnes obligerait a une
-- migration a chaque champ ajoute a une bible.
CREATE TABLE IF NOT EXISTS series (
    nom TEXT PRIMARY KEY,
    bible TEXT NOT NULL,
    cree_le REAL NOT NULL,
    maj_le REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS etapes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id TEXT NOT NULL,
    nom TEXT NOT NULL,
    statut TEXT NOT NULL,
    detail TEXT,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_etapes_produit ON etapes(produit_id);

CREATE TABLE IF NOT EXISTS empreintes (
    produit_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    titre TEXT,
    sujet TEXT,
    signature TEXT,
    plan TEXT,
    mots INTEGER,
    cree_le REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_empreintes_type ON empreintes(type);

CREATE TABLE IF NOT EXISTS ventes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id TEXT,
    reference TEXT,
    plateforme TEXT NOT NULL,
    date TEXT NOT NULL,
    unites INTEGER NOT NULL DEFAULT 1,
    brut REAL NOT NULL DEFAULT 0,
    net REAL,
    devise TEXT NOT NULL DEFAULT 'EUR',
    remboursement INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manuel',
    empreinte TEXT UNIQUE,
    cree_le REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ventes_produit ON ventes(produit_id);
CREATE INDEX IF NOT EXISTS idx_ventes_date ON ventes(date);
"""

# Version du schema. « CREATE TABLE IF NOT EXISTS » suffit a creer une base
# neuve, mais reste sans effet sur une base existante : une colonne ajoutee
# plus tard ne serait jamais creee chez qui a deja produit, et l'erreur SQL
# tomberait des semaines apres, sur un telephone, avec tout l'historique
# dedans. Chaque evolution s'inscrit donc ici.
VERSION_SCHEMA = 5

MIGRATIONS = {
    # v1 -> v2 : empreintes des produits, pour detecter les doublons.
    2: ["""CREATE TABLE IF NOT EXISTS empreintes (
             produit_id TEXT PRIMARY KEY, type TEXT NOT NULL, titre TEXT,
             sujet TEXT, signature TEXT, plan TEXT, mots INTEGER,
             cree_le REAL NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_empreintes_type ON empreintes(type)"],
    # v2 -> v3 : les ventes reelles, pour que l'usine sache ce qui rapporte.
    3: ["""CREATE TABLE IF NOT EXISTS ventes (
             id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id TEXT,
             reference TEXT, plateforme TEXT NOT NULL, date TEXT NOT NULL,
             unites INTEGER NOT NULL DEFAULT 1, brut REAL NOT NULL DEFAULT 0,
             net REAL, devise TEXT NOT NULL DEFAULT 'EUR',
             remboursement INTEGER NOT NULL DEFAULT 0,
             source TEXT NOT NULL DEFAULT 'manuel', empreinte TEXT UNIQUE,
             cree_le REAL NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_ventes_produit ON ventes(produit_id)",
        "CREATE INDEX IF NOT EXISTS idx_ventes_date ON ventes(date)"],
    # v3 -> v4 : periode de mise en ligne d'une variante A/B. Les tables
    # d'experience sont creees a la demande par core/experience.py, donc
    # elles peuvent ne pas exister ici : la migration est conditionnelle,
    # d'ou une fonction plutot qu'une suite d'ordres SQL.
    4: [lambda conn: _ajouter_colonnes(
        conn, "variantes", (("debut", "TEXT"), ("fin", "TEXT")))],
    # v4 -> v5 : les series. Un tome doit savoir de quel monde il est le
    # suivant, et « produits » doit pouvoir le dire sans jointure — c'est ce
    # que listent la CLI, le menu et le tableau de bord.
    5: ["""CREATE TABLE IF NOT EXISTS series (
             nom TEXT PRIMARY KEY, bible TEXT NOT NULL,
             cree_le REAL NOT NULL, maj_le REAL NOT NULL)""",
        lambda conn: _ajouter_colonnes(
            conn, "produits", (("serie", "TEXT"), ("rang", "INTEGER")))],
}


# Index portant sur des colonnes que l'echelle de migrations ajoute.
#
# Ils ne peuvent pas vivre dans SCHEMA, et la raison merite d'etre dite :
# SCHEMA s'execute AVANT « _migrer », et « CREATE TABLE IF NOT EXISTS » ne
# touche pas une table deja creee. Sur une base existante, l'index tombait
# donc sur une colonne qui n'existait pas encore, et « connect() » levait
# « no such column: serie » — avant meme d'avoir eu la chance de migrer.
# Autrement dit : l'usine ne demarrait plus du tout chez quiconque avait deja
# produit un seul fichier, tandis qu'elle marchait parfaitement chez qui
# developpe. C'est le defaut de migration type, et il a ete attrape par le
# test qui part d'une base au palier 1.
INDEX_APRES_MIGRATION = """
CREATE INDEX IF NOT EXISTS idx_produits_serie ON produits(serie, rang);
"""


def _ajouter_colonnes(conn: sqlite3.Connection, table: str,
                      colonnes: Sequence[Tuple[str, str]]) -> None:
    """Ajoute des colonnes a une table existante, sans echouer si elle manque.

    « CREATE TABLE IF NOT EXISTS » ne touche pas une table deja creee : une
    colonne ajoutee dans une nouvelle version n'apparaitrait jamais chez qui
    a deja produit. C'est ce que l'echelle de migrations repare, et une
    colonne se rajoute par ALTER, pas par une redefinition du schema.
    """
    presente = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone()[0]
    if not presente:
        return
    existantes = {ligne[1] for ligne in conn.execute(
        "PRAGMA table_info({})".format(table))}
    for nom, genre in colonnes:
        if nom not in existantes:
            conn.execute("ALTER TABLE {} ADD COLUMN {} {}".format(
                table, nom, genre))


def _migrer(conn: sqlite3.Connection, base_neuve: bool) -> None:
    """Amene la base a VERSION_SCHEMA en repassant par les paliers manquants.

    `base_neuve` doit etre mesure AVANT l'execution de SCHEMA : apres, toutes
    les tables existent et une base d'hier ressemble a une base de ce matin.
    Une base neuve saute les paliers — SCHEMA vient de tout creer — la ou une
    base existante sans numero de version est traitee comme une v1, celle
    d'avant l'introduction du versionnage.
    """
    actuelle = conn.execute("PRAGMA user_version").fetchone()[0]
    if actuelle >= VERSION_SCHEMA:
        return
    if base_neuve:
        conn.execute("PRAGMA user_version = {}".format(VERSION_SCHEMA))
        return
    for palier in range(max(actuelle, 1) + 1, VERSION_SCHEMA + 1):
        for ordre in MIGRATIONS.get(palier, []):
            if callable(ordre):
                ordre(conn)
            else:
                conn.execute(ordre)
    conn.execute("PRAGMA user_version = {}".format(VERSION_SCHEMA))

# Une connexion SQLite appartient au thread qui l'a creee. Le tableau de bord
# sert chaque requete dans son propre thread : on garde donc une connexion par
# thread plutot qu'une connexion globale.
_local = threading.local()
_verrou_schema = threading.Lock()
_schema_pret = False

# Une connexion appartient a son thread, et « close() » ne ferme que celle du
# thread qui appelle. Or une restauration DEPLACE le fichier de base : les
# autres threads gardent alors une poignee ouverte sur un fichier qui n'est
# plus la base de personne. Ils continuent de lire l'ancien atelier, et ce
# qu'ils y ecrivent est perdu — sans la moindre erreur. Chaque connexion
# retient donc la generation ou elle est nee, et se refait quand elle a
# change.
_generation = 0

# « _schema_pret » n'est pas le seul drapeau de ce genre. La file, les
# experiences et l'apprentissage creent leurs tables a la demande et
# retiennent « c'est fait » dans un drapeau de module. Ce drapeau ne vaut
# que pour la base ouverte a ce moment-la : quand le fichier change sous
# nos pieds — restauration d'archive, atelier de test — il ment. Chacun
# s'inscrit ici, et close() les fait tomber ensemble.
_oublis: List[Callable[[], None]] = []


def oublier_avec_la_base(rappel: Callable[[], None]) -> None:
    """Enregistre un drapeau a remettre a zero quand la base change."""
    _oublis.append(rappel)


def connect() -> sqlite3.Connection:
    global _schema_pret
    conn = getattr(_local, "conn", None)
    if conn is not None:
        if getattr(_local, "generation", -1) == _generation:
            return conn
        try:
            conn.close()
        except sqlite3.Error:
            pass  # le fichier a pu disparaitre sous la connexion
        _local.conn = None
    config.ensure_dirs()
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass  # /sdcard ne supporte pas toujours WAL
    conn.execute("PRAGMA synchronous=NORMAL")
    with _verrou_schema:
        if not _schema_pret:
            neuve = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                " AND name='produits'").fetchone()[0] == 0
            conn.executescript(SCHEMA)
            _migrer(conn, neuve)
            conn.executescript(INDEX_APRES_MIGRATION)
            _schema_pret = True
    _local.conn = conn
    _local.generation = _generation
    return conn


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    conn = connect()
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def close() -> None:
    """Ferme la connexion du thread courant et oublie l'etat du schema.

    Oublier le schema importe : « _schema_pret » est un drapeau de module
    qui survivait a la fermeture. Apres une restauration de sauvegarde, le
    fichier de base a change sous nos pieds — sans cet oubli, la reconnexion
    sautait la creation des tables ET l'echelle de migrations, et une
    archive plus ancienne revenait avec son schema d'origine.

    Les modules qui se sont inscrits par « oublier_avec_la_base » sont
    remis a zero de la meme facon, et pour la meme raison.

    Les connexions des AUTRES threads ne peuvent pas etre fermees d'ici —
    une connexion SQLite appartient a son thread. On avance la generation :
    chacune se refera d'elle-meme au prochain usage.
    """
    global _schema_pret, _generation
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
    _schema_pret = False
    _generation += 1
    for rappel in _oublis:
        rappel()


def diagnostic_base() -> str:
    """Rend le defaut constate sur le fichier de base, ou "" si elle est saine.

    On MESURE au lieu de deduire. « sqlite3.DatabaseError » couvre aussi bien
    un fichier illisible qu'une colonne mal nommee : conseiller une
    restauration de sauvegarde a qui vient de croiser un defaut de requete
    serait le garde-fou qui crie a tort, et on lui ferait detruire son atelier
    pour rien. Le seul moyen de trancher est de rouvrir le fichier et de le
    faire verifier par SQLite lui-meme.

    Trois formes de casse existent, et elles ne se voient pas au meme moment
    (mesure du 13/09/2026, Python 3.11) :

    - entete detruite ou fichier remplace par du texte : « file is not a
      database », des la premiere lecture ;
    - fichier tronque : « database disk image is malformed », des la premiere
      lecture ;
    - page interieure ecrasee : AUCUNE erreur a l'ouverture. Le defaut ne
      sort que le jour ou l'on lit cette page-la. C'est la forme la plus
      couteuse, et « PRAGMA integrity_check » est ce qui la trouve.

    Un fichier VIDE n'est pas une base cassee : SQLite y ecrit son schema.
    Rien a signaler, donc, et c'est voulu.

    On ouvre une connexion a part, qu'on ferme aussitot : celle du thread
    peut etre justement celle qui vient d'echouer.
    """
    if not config.DB_PATH.exists():
        return ""
    try:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=5)
    except sqlite3.Error as exc:
        return str(exc)
    try:
        lignes = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    # SQLite rend exactement une ligne « ok » quand tout va bien.
    if len(lignes) == 1 and str(lignes[0][0]).lower() == "ok":
        return ""
    return " ; ".join(str(ligne[0]) for ligne in lignes[:3])


# --------------------------------------------------------------------------
# Empreintes : ce que l'usine a deja ecrit
# --------------------------------------------------------------------------


def enregistrer_empreinte(produit_id: str, type_produit: str, titre: str,
                          sujet: str, signature: str, plan: str,
                          mots: int) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO empreintes"
            " (produit_id, type, titre, sujet, signature, plan, mots, cree_le)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (produit_id, type_produit, titre, sujet, signature, plan,
             int(mots or 0), time.time()),
        )


def lister_empreintes(type_produit: str = "", sauf: str = "",
                      limite: int = 400) -> List[Dict[str, Any]]:
    """Les empreintes connues, la plus recente d'abord.

    Le filtre par type est volontaire : un ebook et un cahier imprimable sur
    le meme sujet ne sont pas des doublons, ils sont complementaires.
    """
    requete = "SELECT * FROM empreintes"
    conditions, parametres = [], []
    if type_produit:
        conditions.append("type = ?")
        parametres.append(type_produit)
    if sauf:
        conditions.append("produit_id != ?")
        parametres.append(sauf)
    if conditions:
        requete += " WHERE " + " AND ".join(conditions)
    requete += " ORDER BY cree_le DESC LIMIT ?"
    parametres.append(int(limite))
    with cursor() as cur:
        return [dict(ligne) for ligne in cur.execute(requete, parametres)]


# --------------------------------------------------------------------------
# Journal des appels / quotas
# --------------------------------------------------------------------------


def _jour(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))


def enregistrer_appel(
    fournisseur: str,
    modele: str,
    ok: bool,
    tokens: int = 0,
    latence: float = 0.0,
    erreur: str = "",
    cle_id: str = "",
) -> None:
    now = time.time()
    with cursor() as cur:
        cur.execute(
            "INSERT INTO appels"
            "(fournisseur, modele, ts, jour, ok, tokens, latence, erreur, cle_id)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (fournisseur, modele, now, _jour(now), 1 if ok else 0, tokens, latence,
             erreur[:400], cle_id),
        )


# Un appel compte dans le quota d'un fournisseur s'il l'a REELLEMENT traite :
# une reponse servie, ou un refus pour cause de debit (429), que tous les
# services decomptent. Une coupure reseau ou un 500 ne consomment rien chez
# eux — les compter revenait a s'interdire un fournisseur pour des pannes dont
# il n'est pas responsable, ce qui arrive sans cesse sur un reseau mobile.
_TRAITE = "(ok=1 OR erreur LIKE 'HTTP 429%')"


def compteur_jour_cle(fournisseur: str, cle_id: str, modele: str = "") -> int:
    """Appels du jour imputes a une cle precise du pool.

    « modele » sert aux fournisseurs dont le quota se compte par modele : une
    cle qui a epuise les requetes de gemini-2.5-flash garde entieres celles de
    gemini-2.5-flash-lite, et ne doit pas etre ecartee pour autant.
    """
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND cle_id=? "
            "AND jour=? AND " + _TRAITE + _et_modele(modele),
            (fournisseur, cle_id, _jour()) + ((modele,) if modele else ()),
        )
        return int(cur.fetchone()[0])


def journal_cle(fournisseur: str, cle_id: str, raison: str, repos: float) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO cles_journal(fournisseur, cle_id, raison, repos, ts)"
            " VALUES (?,?,?,?,?)",
            (fournisseur, cle_id, raison[:200], repos, time.time()),
        )


def tokens_intervalle(depuis: float, jusqu_a: Optional[float] = None) -> int:
    """Jetons consommes dans une fenetre, tous fournisseurs confondus.

    Plusieurs paliers gratuits comptent en JETONS, pas en requetes : Cerebras
    et Gemini l'annoncent dans leurs propres notes. Un budget qui ne compte
    que les appels laisse donc passer le plafond qui compte vraiment.
    """
    fin = time.time() if jusqu_a is None else jusqu_a
    with cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM appels"
            " WHERE ts >= ? AND ts <= ? AND ok=1",
            (depuis, fin),
        )
        return int(cur.fetchone()[0])


def repos_actifs() -> Dict[Tuple[str, str], float]:
    """Mises au repos encore valables, par (fournisseur, cle).

    Android tue le processus sans preavis. Sans relecture, un fournisseur qui
    venait de repondre 429 etait resollicite dans la seconde au redemarrage —
    et repondait 429. La donnee etait deja la, dans « cles_journal » ; il ne
    manquait que de la lire.
    """
    maintenant = time.time()
    actifs: Dict[Tuple[str, str], float] = {}
    with cursor() as cur:
        cur.execute(
            "SELECT fournisseur, cle_id, MAX(ts + repos) AS fin FROM cles_journal"
            " WHERE ts + repos > ? GROUP BY fournisseur, cle_id",
            (maintenant,),
        )
        for ligne in cur.fetchall():
            actifs[(ligne["fournisseur"], ligne["cle_id"] or "")] = float(ligne["fin"])
    return actifs


# Certains fournisseurs comptent leur quota par modele plutot que pour tout le
# service (c'est le cas de Google). Passer « modele » restreint le decompte a
# ce modele ; le laisser vide compte tout le fournisseur, comme avant.
def _et_modele(modele: str) -> str:
    return " AND modele=?" if modele else ""


# Les quotas d'un fournisseur s'appliquent a un COMPTE, donc a une cle. Les
# compter pour tout le fournisseur revenait a additionner les consommations de
# cles independantes : deux cles donnaient un seul quota, et le pool — dont
# toute la raison d'etre est de ne jamais s'arreter faute de quota — ne
# multipliait rien du tout.
def _et_cle(cle_id: str) -> str:
    return " AND cle_id=?" if cle_id else ""


def _filtres(modele: str, cle_id: str) -> Tuple[str, Tuple[Any, ...]]:
    """Clause SQL et parametres pour restreindre a un modele et/ou une cle."""
    clause = _et_modele(modele) + _et_cle(cle_id)
    valeurs = tuple(v for v in (modele, cle_id) if v)
    return clause, valeurs


def compteur_minute(fournisseur: str, modele: str = "",
                    cle_id: str = "") -> int:
    clause, valeurs = _filtres(modele, cle_id)
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND ts > ?" + clause,
            (fournisseur, time.time() - 60) + valeurs,
        )
        return int(cur.fetchone()[0])


def compteur_jour(fournisseur: str, modele: str = "",
                  cle_id: str = "") -> int:
    clause, valeurs = _filtres(modele, cle_id)
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND jour=? AND "
            + _TRAITE + clause,
            (fournisseur, _jour()) + valeurs,
        )
        return int(cur.fetchone()[0])


def jetons_minute(fournisseur: str, modele: str = "",
                  cle_id: str = "") -> Tuple[int, float]:
    """Jetons consommes dans la derniere minute, et date du plus ancien.

    Le plafond par minute est une fenetre GLISSANTE : la place ne se libere
    pas a la minute ronde, elle se libere quand le plus vieil appel de la
    fenetre en sort. Rendre cette date permet d'attendre exactement ce qu'il
    faut au lieu d'attendre une minute entiere a chaque fois.
    """
    debut = time.time() - 60
    clause, valeurs = _filtres(modele, cle_id)
    with cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(tokens), 0), COALESCE(MIN(ts), 0) FROM appels"
            " WHERE fournisseur=? AND ts > ? AND ok=1 AND tokens > 0" + clause,
            (fournisseur, debut) + valeurs,
        )
        ligne = cur.fetchone()
        return int(ligne[0]), float(ligne[1])


def jetons_jour(fournisseur: str, modele: str = "", cle_id: str = "") -> int:
    """Jetons consommes aujourd'hui chez un fournisseur."""
    clause, valeurs = _filtres(modele, cle_id)
    with cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM appels"
            " WHERE fournisseur=? AND jour=? AND ok=1" + clause,
            (fournisseur, _jour()) + valeurs,
        )
        return int(cur.fetchone()[0])


def compteur_intervalle(depuis: float, jusqu_a: Optional[float] = None) -> int:
    """Appels effectues dans une fenetre de temps, tous fournisseurs confondus.

    C'est ce qu'il faut pour imputer un cout a UNE production : compter les
    appels du jour attribuerait a un produit tout ce qui a ete fait avant lui.
    """
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE ts >= ? AND ts <= ?",
            (depuis, jusqu_a if jusqu_a is not None else time.time()),
        )
        return int(cur.fetchone()[0])


def fournisseurs_intervalle(depuis: float, jusqu_a: Optional[float] = None) -> List[str]:
    """Fournisseurs ayant effectivement repondu pendant la fenetre."""
    with cursor() as cur:
        cur.execute(
            "SELECT DISTINCT fournisseur FROM appels"
            " WHERE ts >= ? AND ts <= ? AND ok=1",
            (depuis, jusqu_a if jusqu_a is not None else time.time()),
        )
        return [row[0] for row in cur.fetchall()]


def stats_fournisseurs() -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            "SELECT fournisseur,"
            " COUNT(*) AS total,"
            " SUM(ok) AS reussites,"
            " SUM(tokens) AS tokens,"
            " AVG(latence) AS latence"
            " FROM appels WHERE jour=? GROUP BY fournisseur ORDER BY total DESC",
            (_jour(),),
        )
        return [dict(row) for row in cur.fetchall()]


# --------------------------------------------------------------------------
# Cache des reponses IA
# --------------------------------------------------------------------------


def cache_get(cle: str) -> Optional[str]:
    with cursor() as cur:
        cur.execute("SELECT contenu FROM cache WHERE cle=?", (cle,))
        row = cur.fetchone()
        return row["contenu"] if row else None


def cache_set(cle: str, contenu: str, fournisseur: str = "", modele: str = "") -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO cache(cle, contenu, fournisseur, modele, cree_le)"
            " VALUES (?,?,?,?,?)",
            (cle, contenu, fournisseur, modele, time.time()),
        )


def cache_par_prefixe(prefixe: str) -> Dict[str, str]:
    """Les entrees de cache dont la cle commence par « prefixe »."""
    with cursor() as cur:
        cur.execute("SELECT cle, contenu FROM cache WHERE cle LIKE ?",
                    (prefixe + "%",))
        return {row["cle"]: row["contenu"] for row in cur.fetchall()}


def compter_reponses_cachees() -> int:
    """Reponses de modele en cache — sans ce qui n'en est pas.

    La table sert aussi a garder le catalogue des fournisseurs et les
    substitutions de modeles. Les compter comme des reponses faisait annoncer
    un cache non vide a qui n'avait encore rien fabrique.
    """
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cache WHERE cle NOT LIKE ?"
                    " AND cle NOT LIKE ?",
                    ("catalogue-modeles:%", "substitution:%"))
        return int(cur.fetchone()[0])


def cache_oublier_prefixe(prefixe: str) -> int:
    """Efface les entrees de cache dont la cle commence par « prefixe ».

    Le cache sert a deux choses qui n'ont rien a voir : garder les reponses du
    modele, et garder le catalogue des fournisseurs. Oublier le second sans
    jeter le premier evite de faire repayer une fabrication entiere parce
    qu'on a change de cle API.
    """
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cache WHERE cle LIKE ?", (prefixe + "%",))
        n = int(cur.fetchone()[0])
        cur.execute("DELETE FROM cache WHERE cle LIKE ?", (prefixe + "%",))
        return n


def cache_vider() -> int:
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cache")
        n = int(cur.fetchone()[0])
        cur.execute("DELETE FROM cache")
        return n


# --------------------------------------------------------------------------
# Catalogue produits
# --------------------------------------------------------------------------


def creer_produit(
    produit_id: str,
    type_: str,
    titre: str,
    sujet: str = "",
    audience: str = "",
    langue: str = "fr",
    dossier: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    now = time.time()
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO produits"
            "(id, type, titre, sujet, audience, langue, statut, dossier, meta, cree_le, maj_le)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                produit_id,
                type_,
                titre,
                sujet,
                audience,
                langue,
                "en_cours",
                dossier,
                json.dumps(meta or {}, ensure_ascii=False),
                now,
                now,
            ),
        )


def maj_produit(produit_id: str, **champs: Any) -> None:
    if not champs:
        return
    if "meta" in champs and not isinstance(champs["meta"], str):
        champs["meta"] = json.dumps(champs["meta"], ensure_ascii=False)
    champs["maj_le"] = time.time()
    sets = ", ".join("{}=?".format(k) for k in champs)
    with cursor() as cur:
        cur.execute(
            "UPDATE produits SET {} WHERE id=?".format(sets),
            list(champs.values()) + [produit_id],
        )


def _produit(ligne: sqlite3.Row) -> Dict[str, Any]:
    """Fiche produit avec son meta deja decode.

    Il etait rendu en JSON brut, et les six appelants le decodaient chacun
    de leur cote. Le septieme a oublie, s'est protege par un
    « isinstance(meta, dict) » — et sa fonctionnalite est devenue un
    no-op silencieux. Le decodage appartient a la couche qui lit.
    """
    fiche = dict(ligne)
    brut = fiche.get("meta")
    if isinstance(brut, str):
        try:
            charge = json.loads(brut or "{}")
        except ValueError:
            charge = {}
        fiche["meta"] = charge if isinstance(charge, dict) else {}
    elif brut is None:
        fiche["meta"] = {}
    return fiche


def lire_produit(produit_id: str) -> Optional[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM produits WHERE id=?", (produit_id,))
        row = cur.fetchone()
        return _produit(row) if row else None


def supprimer_produit(produit_id: str) -> None:
    """Efface la fiche d'un produit et ce qui y renvoie.

    Les etapes et l'empreinte partent avec. Les laisser derriere faisait deux
    degats invisibles : le journal d'etapes gonflait sans jamais etre lu, et
    l'empreinte d'un produit efface faisait refuser un nouveau produit sur le
    meme sujet comme un doublon de quelque chose qui n'existe plus.
    """
    with cursor() as cur:
        cur.execute("DELETE FROM etapes WHERE produit_id=?", (produit_id,))
        cur.execute("DELETE FROM empreintes WHERE produit_id=?", (produit_id,))
        cur.execute("DELETE FROM produits WHERE id=?", (produit_id,))


def lister_produits(limite: int = 50) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM produits ORDER BY cree_le DESC LIMIT ?", (limite,))
        return [_produit(row) for row in cur.fetchall()]


def journal_etape(produit_id: str, nom: str, statut: str, detail: str = "") -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO etapes(produit_id, nom, statut, detail, ts) VALUES (?,?,?,?,?)",
            (produit_id, nom, statut, detail[:500], time.time()),
        )


def etapes_produit(produit_id: str) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM etapes WHERE produit_id=? ORDER BY id", (produit_id,))
        return [dict(row) for row in cur.fetchall()]
