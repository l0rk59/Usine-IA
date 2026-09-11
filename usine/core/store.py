"""Persistance SQLite : quotas, cache des reponses IA, catalogue produits.

Une seule base (atelier/usine.db), mode WAL, safe pour Termux.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

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
VERSION_SCHEMA = 4

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
}


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


def connect() -> sqlite3.Connection:
    global _schema_pret
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
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
            _schema_pret = True
    _local.conn = conn
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
    """Ferme la connexion du thread courant."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


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


def compteur_jour_cle(fournisseur: str, cle_id: str) -> int:
    """Appels du jour imputes a une cle precise du pool."""
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND cle_id=? AND jour=?",
            (fournisseur, cle_id, _jour()),
        )
        return int(cur.fetchone()[0])


def compteur_minute_cle(fournisseur: str, cle_id: str) -> int:
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND cle_id=? AND ts > ?",
            (fournisseur, cle_id, time.time() - 60),
        )
        return int(cur.fetchone()[0])


def journal_cle(fournisseur: str, cle_id: str, raison: str, repos: float) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO cles_journal(fournisseur, cle_id, raison, repos, ts)"
            " VALUES (?,?,?,?,?)",
            (fournisseur, cle_id, raison[:200], repos, time.time()),
        )


def compteur_minute(fournisseur: str) -> int:
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND ts > ?",
            (fournisseur, time.time() - 60),
        )
        return int(cur.fetchone()[0])


def compteur_jour(fournisseur: str) -> int:
    with cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM appels WHERE fournisseur=? AND jour=?",
            (fournisseur, _jour()),
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
