"""Memoire de production : l'usine apprend de ce qu'elle a deja fabrique.

Chaque produit laisse une trace mesuree — note du controle local, defauts
restants, duree, fournisseurs utilises, nombre d'appels. Au bout de quelques
produits, cela repond a des questions qu'aucun modele ne peut trancher :
quel ton donne les meilleures notes chez vous, quel type de produit vous coute
le moins d'appels, quel sujet a echoue et pourquoi.

Rien n'est devine : tout vient de la base locale.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from . import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS productions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id TEXT NOT NULL,
    type TEXT NOT NULL,
    sujet TEXT,
    audience TEXT,
    ton TEXT,
    taille TEXT,
    qualite TEXT,
    note REAL,
    note_avant REAL,
    mots INTEGER,
    sections INTEGER,
    duree REAL,
    appels INTEGER,
    fournisseurs TEXT,
    defauts TEXT,
    reussi INTEGER NOT NULL DEFAULT 1,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_productions_type ON productions(type);
CREATE INDEX IF NOT EXISTS idx_productions_ts ON productions(ts);
"""

_pret = False


def _assurer() -> None:
    global _pret
    if not _pret:
        store.connect().executescript(SCHEMA)
        _pret = True


def enregistrer(
    produit_id: str,
    type_produit: str,
    sujet: str = "",
    audience: str = "",
    ton: str = "",
    taille: str = "",
    qualite: str = "",
    note: Optional[float] = None,
    note_avant: Optional[float] = None,
    mots: int = 0,
    sections: int = 0,
    duree: float = 0.0,
    appels: int = 0,
    fournisseurs: Optional[List[str]] = None,
    defauts: Optional[List[str]] = None,
    reussi: bool = True,
) -> None:
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "INSERT INTO productions(produit_id, type, sujet, audience, ton, taille,"
            " qualite, note, note_avant, mots, sections, duree, appels, fournisseurs,"
            " defauts, reussi, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (produit_id, type_produit, sujet, audience, ton, taille, qualite, note,
             note_avant, mots, sections, duree, appels,
             json.dumps(fournisseurs or [], ensure_ascii=False),
             json.dumps((defauts or [])[:20], ensure_ascii=False),
             1 if reussi else 0, time.time()),
        )


def historique(limite: int = 100) -> List[Dict[str, Any]]:
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT * FROM productions ORDER BY ts DESC LIMIT ?", (limite,))
        return [dict(row) for row in cur.fetchall()]


def _racine(defaut: str) -> str:
    """Ramene un defaut a sa categorie, chiffres exclus.

    « 167 mots pour 700 attendus » et « 142 mots pour 700 attendus » sont le
    meme probleme : sans cette normalisation, chaque chapitre creerait sa
    propre categorie et aucun defaut ne semblerait recurrent.
    """
    import re

    texte = defaut.split(":")[0].split("(")[0]
    # Ne consomme jamais l'espace qui suit : « 167 mots » doit devenir
    # « N mots », pas « Nmots ».
    texte = re.sub(r"\d+(?:[.,]\d+)?%?", "N", texte)
    return " ".join(texte.split())[:60] or "defaut"


def _moyenne(valeurs: List[float]) -> Optional[float]:
    propres = [v for v in valeurs if v is not None]
    return round(sum(propres) / len(propres), 2) if propres else None


def _grouper(colonne: str, minimum: int = 2) -> List[Dict[str, Any]]:
    """Note moyenne par valeur d'un reglage, pour les groupes assez fournis."""
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "SELECT {col} AS valeur, COUNT(*) AS n, AVG(note) AS note,"
            " AVG(appels) AS appels, AVG(duree) AS duree"
            " FROM productions WHERE reussi=1 AND note IS NOT NULL AND {col} != ''"
            " GROUP BY {col} HAVING COUNT(*) >= ? ORDER BY AVG(note) DESC".format(
                col=colonne),
            (minimum,),
        )
        return [
            {"valeur": r["valeur"], "productions": r["n"],
             "note_moyenne": round(r["note"], 2),
             "appels_moyens": round(r["appels"] or 0, 1),
             "duree_moyenne": round(r["duree"] or 0, 1)}
            for r in cur.fetchall()
        ]


def bilan() -> Dict[str, Any]:
    """Synthese de tout ce que l'usine a produit."""
    _assurer()
    lignes = historique(500)
    if not lignes:
        return {"productions": 0, "message": "Aucune production enregistree."}

    reussies = [l for l in lignes if l["reussi"]]
    notes = [l["note"] for l in reussies if l["note"] is not None]
    progression = [
        l["note"] - l["note_avant"] for l in reussies
        if l["note"] is not None and l["note_avant"] is not None
    ]

    # Defauts les plus frequents, tous produits confondus.
    compte: Dict[str, int] = {}
    for ligne in reussies:
        for defaut in json.loads(ligne["defauts"] or "[]"):
            compte[_racine(str(defaut))] = compte.get(_racine(str(defaut)), 0) + 1

    return {
        "productions": len(lignes),
        "reussites": len(reussies),
        "echecs": len(lignes) - len(reussies),
        "note_moyenne": _moyenne(notes),
        "note_meilleure": max(notes) if notes else None,
        "note_pire": min(notes) if notes else None,
        "gain_moyen_relecture": _moyenne(progression),
        "mots_totaux": sum(l["mots"] or 0 for l in reussies),
        "appels_totaux": sum(l["appels"] or 0 for l in reussies),
        "par_type": _grouper("type"),
        "par_ton": _grouper("ton"),
        "par_taille": _grouper("taille"),
        "par_qualite": _grouper("qualite"),
        "defauts_frequents": sorted(
            ({"defaut": d, "occurrences": n} for d, n in compte.items()),
            key=lambda x: -x["occurrences"])[:8],
    }


def conseils() -> List[Dict[str, str]]:
    """Recommandations deduites de l'historique, jamais inventees.

    Chaque conseil cite le nombre de productions sur lequel il s'appuie : sous
    trois productions, on le dit au lieu de presenter une moyenne comme une loi.
    """
    donnees = bilan()
    if donnees["productions"] == 0:
        return [{"sujet": "demarrage",
                 "conseil": "Fabriquez un premier produit : l'usine n'a encore "
                            "aucune mesure sur laquelle s'appuyer.",
                 "appui": "0 production"}]

    recommandations: List[Dict[str, str]] = []

    if donnees["productions"] < 3:
        recommandations.append({
            "sujet": "echantillon",
            "conseil": "Trop peu de productions pour degager une tendance fiable. "
                       "Les indications ci-dessous sont indicatives.",
            "appui": "{} production(s)".format(donnees["productions"]),
        })

    for critere, libelle in (("par_ton", "ton"), ("par_taille", "volume"),
                             ("par_qualite", "niveau de qualite")):
        groupes = donnees[critere]
        if len(groupes) >= 2:
            meilleur, pire = groupes[0], groupes[-1]
            ecart = meilleur["note_moyenne"] - pire["note_moyenne"]
            if ecart >= 0.5:
                recommandations.append({
                    "sujet": libelle,
                    "conseil": "Le {} « {} » donne {} /10 contre {} pour « {} ». "
                               "Privilegiez-le.".format(
                                   libelle, meilleur["valeur"],
                                   meilleur["note_moyenne"], pire["note_moyenne"],
                                   pire["valeur"]),
                    "appui": "{} vs {} productions".format(
                        meilleur["productions"], pire["productions"]),
                })

    gain = donnees["gain_moyen_relecture"]
    if gain is not None:
        if gain < 0.3:
            recommandations.append({
                "sujet": "relecture",
                "conseil": "La relecture ne fait gagner que {} point en moyenne. "
                           "Passez en qualite « rapide » pour economiser vos "
                           "quotas.".format(round(gain, 2)),
                "appui": "{} productions relues".format(donnees["reussites"]),
            })
        elif gain >= 1.0:
            recommandations.append({
                "sujet": "relecture",
                "conseil": "La relecture fait gagner {} points en moyenne : le "
                           "niveau « exigeant » vaut son cout ici.".format(
                               round(gain, 2)),
                "appui": "{} productions relues".format(donnees["reussites"]),
            })

    if donnees["defauts_frequents"]:
        principal = donnees["defauts_frequents"][0]
        if principal["occurrences"] >= 3:
            recommandations.append({
                "sujet": "defaut recurrent",
                "conseil": "« {} » revient {} fois. Ajoutez une regle a l'agent "
                           "redacteur : usine prompts-systeme --exporter".format(
                               principal["defaut"], principal["occurrences"]),
                "appui": "{} occurrences".format(principal["occurrences"]),
            })

    types = donnees["par_type"]
    if len(types) >= 2:
        economique = min(types, key=lambda t: t["appels_moyens"] or 999)
        if economique["appels_moyens"]:
            recommandations.append({
                "sujet": "cout",
                "conseil": "« {} » est votre produit le moins gourmand : {} appels "
                           "en moyenne, note {} /10.".format(
                               economique["valeur"], economique["appels_moyens"],
                               economique["note_moyenne"]),
                "appui": "{} productions".format(economique["productions"]),
            })

    if not recommandations:
        recommandations.append({
            "sujet": "stable",
            "conseil": "Aucun ecart significatif entre vos reglages. Continuez, "
                       "et variez un parametre a la fois pour pouvoir comparer.",
            "appui": "{} productions".format(donnees["productions"]),
        })
    return recommandations
