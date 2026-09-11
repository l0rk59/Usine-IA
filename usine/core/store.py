"""Persistance SQLite : quotas, cache des reponses IA, catalogue produits.

Une seule base (atelier/usine.db), mode WAL, safe pour Termux.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

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
"""

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
            conn.executescript(SCHEMA)
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


def lire_produit(produit_id: str) -> Optional[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM produits WHERE id=?", (produit_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def lister_produits(limite: int = 50) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM produits ORDER BY cree_le DESC LIMIT ?", (limite,))
        return [dict(row) for row in cur.fetchall()]


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
