"""File de production : les niches en attente de fabrication.

Persistee en base plutot qu'en memoire, pour une raison precise : sur Android,
le systeme tue les processus en arriere-plan sans preavis. Une file en memoire
disparaitrait avec le processus ; ici, relancer l'usine reprend exactement ou
elle s'etait arretee.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from . import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS file_production (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sujet TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'ebook',
    options TEXT NOT NULL DEFAULT '{}',
    priorite INTEGER NOT NULL DEFAULT 5,
    statut TEXT NOT NULL DEFAULT 'en_attente',
    tentatives INTEGER NOT NULL DEFAULT 0,
    max_tentatives INTEGER NOT NULL DEFAULT 2,
    produit_id TEXT,
    erreur TEXT,
    source TEXT NOT NULL DEFAULT 'manuel',
    ajoute_le REAL NOT NULL,
    maj_le REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_file_statut ON file_production(statut, priorite, id);
"""

STATUTS = ("en_attente", "en_cours", "fait", "echec", "annule")

# Les tables de ce module se creent au premier usage, et le drapeau qui dit
# « c'est fait » retombe quand la base change. Le mecanisme etait recopie ici,
# dans « experience » et dans « apprentissage » — a l'octet pres.
_assurer = store.tables_a_la_demande(SCHEMA)


def ajouter(
    sujet: str,
    type_produit: str = "ebook",
    options: Optional[Dict[str, Any]] = None,
    priorite: int = 5,
    source: str = "manuel",
    max_tentatives: int = 2,
) -> Optional[int]:
    """Ajoute une niche. Renvoie None si elle est deja en attente.

    Le doublon est ecarte sur le couple (sujet, type) : relancer la meme
    commande deux fois ne doit pas produire deux fois le meme livre.
    """
    _assurer()
    sujet = (sujet or "").strip()
    if not sujet:
        return None
    with store.cursor() as cur:
        cur.execute(
            "SELECT id FROM file_production WHERE sujet=? AND type=?"
            " AND statut IN ('en_attente','en_cours')",
            (sujet, type_produit),
        )
        if cur.fetchone():
            return None
        maintenant = time.time()
        cur.execute(
            "INSERT INTO file_production(sujet, type, options, priorite, statut,"
            " max_tentatives, source, ajoute_le, maj_le)"
            " VALUES (?,?,?,?,'en_attente',?,?,?,?)",
            (sujet, type_produit, json.dumps(options or {}, ensure_ascii=False),
             priorite, max_tentatives, source, maintenant, maintenant),
        )
        return int(cur.lastrowid)


def prochain() -> Optional[Dict[str, Any]]:
    """Reserve la prochaine niche et la marque « en cours ».

    La lecture et la reservation sont faites dans une transaction immediate :
    deux usines lancees par erreur ne peuvent pas prendre la meme entree.
    """
    _assurer()
    conn = store.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "SELECT * FROM file_production WHERE statut='en_attente'"
            " ORDER BY priorite ASC, id ASC LIMIT 1")
        ligne = cur.fetchone()
        if ligne is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE file_production SET statut='en_cours', tentatives=tentatives+1,"
            " maj_le=? WHERE id=?",
            (time.time(), ligne["id"]),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    entree = dict(ligne)
    entree["options"] = json.loads(entree.get("options") or "{}")
    entree["tentatives"] += 1
    return entree


def terminer(identifiant: int, produit_id: str = "") -> None:
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "UPDATE file_production SET statut='fait', produit_id=?, erreur='',"
            " maj_le=? WHERE id=?",
            (produit_id, time.time(), identifiant),
        )


def echouer(identifiant: int, erreur: str = "") -> str:
    """Marque un echec. Renvoie le nouveau statut : « en_attente » ou « echec ».

    Une niche est remise en file tant qu'il reste des tentatives : un echec
    reseau ne doit pas la condamner definitivement.
    """
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT tentatives, max_tentatives FROM file_production"
                    " WHERE id=?", (identifiant,))
        ligne = cur.fetchone()
        if ligne is None:
            return "inconnu"
        rejouable = ligne["tentatives"] < ligne["max_tentatives"]
        statut = "en_attente" if rejouable else "echec"
        cur.execute(
            "UPDATE file_production SET statut=?, erreur=?, maj_le=? WHERE id=?",
            (statut, (erreur or "")[:400], time.time(), identifiant),
        )
        return statut


def reporter(identifiant: int, erreur: str, produit_id: str = "") -> None:
    """Remet une niche en attente SANS lui compter l'essai qu'elle vient de faire.

    Pour un seul cas : les fournisseurs se sont tus avant que le produit
    sorte. Ce n'est pas la niche qui a echoue — la suivante echouerait de la
    meme facon. « echouer » comptait pourtant l'essai, et deux essais font un
    echec definitif. Voir « UsineContinue._silence » pour la mesure.

    Si le produit a eu le temps d'exister, c'est lui que la niche reprendra :
    en fabriquer un second laisserait le premier inacheve sur le disque, sans
    rien pour le finir.
    """
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT options FROM file_production WHERE id=?",
                    (identifiant,))
        ligne = cur.fetchone()
        options = json.loads((ligne["options"] if ligne else "") or "{}")
        if produit_id:
            options["reprendre_id"] = produit_id
        cur.execute(
            "UPDATE file_production SET statut='en_attente',"
            " tentatives=MAX(0, tentatives - 1), erreur=?, options=?,"
            " produit_id=COALESCE(NULLIF(?, ''), produit_id), maj_le=?"
            " WHERE id=?",
            ((erreur or "")[:400], json.dumps(options, ensure_ascii=False),
             produit_id, time.time(), identifiant),
        )


def a_finir(identifiant: int, produit_id: str, manquants: int) -> Dict[str, Any]:
    """Remet en tete de file une niche dont le produit est reste inacheve.

    Avant, la niche etait marquee « fait » : le produit coupe par les quotas
    restait inacheve sur le disque, et rien ne le reprenait jamais — il
    fallait penser a appuyer sur « Reprendre ». La niche repart donc en
    tete, avec de quoi reprendre CE produit plutot qu'en fabriquer un autre.

    Rend les options ecrites : « sans_progres » compte les reprises qui n'ont
    pas fait baisser le nombre de sections manquantes. C'est l'appelant qui
    decide quand renoncer — un quota epuise n'est pas un echec de la niche.
    """
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT options FROM file_production WHERE id=?",
                    (identifiant,))
        ligne = cur.fetchone()
        options = json.loads((ligne["options"] if ligne else "") or "{}")
        avant = options.get("manquants")
        # « 0 » avant : le produit a ete coupe avant sa premiere section, il
        # n'y avait rien a compter. Le prendre pour une mesure ferait croire
        # a la premiere vraie reprise qu'elle n'a rien fait avancer.
        progres = not avant or manquants < int(avant)
        options["reprendre_id"] = produit_id
        options["manquants"] = manquants
        options["sans_progres"] = (0 if progres
                                   else int(options.get("sans_progres") or 0) + 1)
        cur.execute(
            "UPDATE file_production SET statut='en_attente', priorite=0,"
            " tentatives=0, options=?, produit_id=?, maj_le=? WHERE id=?",
            (json.dumps(options, ensure_ascii=False), produit_id, time.time(),
             identifiant),
        )
    return options


def abandonner(identifiant: int, erreur: str) -> None:
    """Sort une niche de la file pour de bon, quel que soit son compte d'essais."""
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "UPDATE file_production SET statut='echec', erreur=?, maj_le=?"
            " WHERE id=?", ((erreur or "")[:400], time.time(), identifiant))


def liberer_orphelins() -> int:
    """Remet en attente les entrees laissees « en cours » par un arret brutal.

    A appeler au demarrage de l'usine : c'est ce qui rend une coupure Android
    sans consequence.
    """
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM file_production WHERE statut='en_cours'")
        nombre = int(cur.fetchone()[0])
        if nombre:
            cur.execute(
                "UPDATE file_production SET statut='en_attente', maj_le=?"
                " WHERE statut='en_cours'", (time.time(),))
        return nombre


def lister(statut: str = "", limite: int = 50) -> List[Dict[str, Any]]:
    _assurer()
    with store.cursor() as cur:
        if statut:
            cur.execute(
                "SELECT * FROM file_production WHERE statut=?"
                " ORDER BY priorite ASC, id ASC LIMIT ?", (statut, limite))
        else:
            cur.execute(
                "SELECT * FROM file_production"
                " ORDER BY CASE statut WHEN 'en_cours' THEN 0 WHEN 'en_attente'"
                " THEN 1 ELSE 2 END, priorite ASC, id ASC LIMIT ?", (limite,))
        entrees = []
        for ligne in cur.fetchall():
            entree = dict(ligne)
            entree["options"] = json.loads(entree.get("options") or "{}")
            entrees.append(entree)
        return entrees


def compter() -> Dict[str, int]:
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT statut, COUNT(*) AS n FROM file_production"
                    " GROUP BY statut")
        compte = {statut: 0 for statut in STATUTS}
        for ligne in cur.fetchall():
            compte[ligne["statut"]] = int(ligne["n"])
        compte["total"] = sum(compte[s] for s in STATUTS)
        return compte


def retirer(identifiant: int) -> bool:
    _assurer()
    with store.cursor() as cur:
        cur.execute("UPDATE file_production SET statut='annule', maj_le=?"
                    " WHERE id=? AND statut IN ('en_attente','en_cours')",
                    (time.time(), identifiant))
        return cur.rowcount > 0


def rejouer(identifiant: int = 0) -> int:
    """Remet en file une entree en echec, ou toutes si aucun identifiant."""
    _assurer()
    with store.cursor() as cur:
        if identifiant:
            cur.execute(
                "UPDATE file_production SET statut='en_attente', tentatives=0,"
                " erreur='', maj_le=? WHERE id=? AND statut IN ('echec','annule')",
                (time.time(), identifiant))
        else:
            cur.execute(
                "UPDATE file_production SET statut='en_attente', tentatives=0,"
                " erreur='', maj_le=? WHERE statut='echec'", (time.time(),))
        return cur.rowcount


def vider(tout: bool = False) -> int:
    """Supprime les entrees terminees, ou toute la file si `tout`."""
    _assurer()
    with store.cursor() as cur:
        if tout:
            cur.execute("DELETE FROM file_production")
        else:
            cur.execute("DELETE FROM file_production"
                        " WHERE statut IN ('fait','annule')")
        return cur.rowcount
