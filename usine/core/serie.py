"""La bible de serie : ce qu'un tome transmet au suivant.

L'usine fabriquait des produits isolés. Une nouvelle ecrite hier et une
nouvelle ecrite aujourd'hui ne se connaissaient pas, meme si l'auteur voulait
la meme heroine dans le meme village. Deux consequences, l'une commerciale et
l'autre litteraire, et c'est la premiere qui compte le plus :

  - **Le tome 2 se vend au lecteur du tome 1.** C'est le seul levier de vente
    qu'une fabrique de fiction possede vraiment, et l'usine ne l'exploitait
    pas du tout.
  - Un tome qui contredit le precedent perd ce lecteur pour de bon. Les yeux
    de l'heroine, son age, le nom du village : le registre des faits sait deja
    reperer ces contradictions DANS un texte. Il suffisait de lui donner deux
    textes.

Ce module tient donc l'etat d'une serie — le monde, la distribution, les faits
acquis, ce qui s'est passe — et le rend a la chaine de fiction pour le tome
suivant.

CE QU'IL NE FAIT PAS. Il n'appelle aucun modele. La bible d'un tome est
enrichie par la chaine, pas resumee par une IA : un resume de resume derive a
chaque generation, et au tome 4 le village a change de nom sans que personne
ne l'ait decide. Ce qui entre ici vient du texte produit ou de la bible du
tome, jamais d'une interpretation.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional

from . import store

# Un resume de tome plus long que cela ne tient plus dans l'invite du tome
# suivant a cote de tout le reste. Mesure : la memoire d'une scene fait
# 90 mots (voir pipelines/memoire.py), et un tome en vaut quelques-unes.
MOTS_RESUME_TOME = 220

# Au-dela, la distribution accumulee ne sert plus le tome suivant : elle
# l'ecrase. Les personnages sont gardes dans l'ordre d'apparition, donc les
# premiers — ceux que le lecteur connait — restent.
PERSONNAGES_MAX = 12


def normaliser(nom: str) -> str:
    """Cle stable d'une serie. « Les Ombres » et « les ombres » sont la meme.

    Sans cela, une faute de casse ou un accent oublie creerait une seconde
    serie vide, et le tome 2 repartirait de zero sans rien dire.
    """
    decompose = unicodedata.normalize("NFD", (nom or "").strip().lower())
    sans_accent = "".join(c for c in decompose
                          if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sans_accent).strip("-")


def _vide(nom: str) -> Dict[str, Any]:
    return {"nom": nom.strip(), "cadre": {}, "personnages": [],
            "faits": {}, "tomes": []}


def lire(nom: str) -> Optional[Dict[str, Any]]:
    """La bible accumulee d'une serie, ou None si elle n'existe pas encore.

    None veut dire « premier tome », pas « erreur » : l'appelant doit pouvoir
    lancer une serie sans la declarer d'abord.
    """
    cle = normaliser(nom)
    if not cle:
        return None
    with store.cursor() as cur:
        cur.execute("SELECT bible FROM series WHERE nom=?", (cle,))
        ligne = cur.fetchone()
    if not ligne:
        return None
    try:
        return json.loads(ligne["bible"])
    except (ValueError, TypeError):
        # Une bible illisible ne doit pas empecher d'ecrire le tome suivant :
        # mieux vaut un tome sans memoire qu'une chaine qui refuse de tourner.
        return None


def ecrire(nom: str, bible: Dict[str, Any]) -> None:
    cle = normaliser(nom)
    if not cle:
        return
    maintenant = time.time()
    with store.cursor() as cur:
        cur.execute(
            "INSERT INTO series(nom, bible, cree_le, maj_le) VALUES (?,?,?,?)"
            " ON CONFLICT(nom) DO UPDATE SET bible=excluded.bible,"
            " maj_le=excluded.maj_le",
            (cle, json.dumps(bible, ensure_ascii=False), maintenant, maintenant))


def lister() -> List[Dict[str, Any]]:
    """Toutes les series, avec leur nombre de tomes — pour la CLI et le menu."""
    series: List[Dict[str, Any]] = []
    with store.cursor() as cur:
        cur.execute("SELECT nom, bible, maj_le FROM series ORDER BY maj_le DESC")
        for ligne in cur.fetchall():
            try:
                bible = json.loads(ligne["bible"])
            except (ValueError, TypeError):
                continue
            series.append({
                "cle": ligne["nom"],
                "nom": bible.get("nom") or ligne["nom"],
                "tomes": len(bible.get("tomes") or []),
                "personnages": len(bible.get("personnages") or []),
                "maj_le": ligne["maj_le"],
            })
    return series


def prochain_rang(nom: str) -> int:
    """Numero du tome qu'on s'apprete a ecrire. Le premier porte le 1."""
    bible = lire(nom)
    return len(bible.get("tomes") or []) + 1 if bible else 1


# --------------------------------------------------------------------------
# Ce que le tome suivant recoit
# --------------------------------------------------------------------------


def _abreger(texte: str, mots: int) -> str:
    morceaux = (texte or "").split()
    if len(morceaux) <= mots:
        return " ".join(morceaux)
    return " ".join(morceaux[:mots]) + "..."


def rappel(nom: str) -> str:
    """Ce que le lecteur sait deja, en clair, pour l'invite du tome suivant.

    Rendu vide quand la serie n'existe pas : le premier tome n'a rien a
    rappeler, et une consigne vide vaut mieux qu'une consigne qui parle d'un
    passe inexistant.
    """
    bible = lire(nom)
    if not bible or not bible.get("tomes"):
        return ""
    lignes = ["CETTE HISTOIRE APPARTIENT A LA SERIE « {} ».".format(
        bible.get("nom") or nom)]

    cadre = bible.get("cadre") or {}
    if cadre.get("lieu") or cadre.get("epoque"):
        lignes.append("CADRE ETABLI : {} — {}".format(
            cadre.get("lieu") or "non precise",
            cadre.get("epoque") or "non precisee"))
    if cadre.get("regles"):
        lignes.append("REGLES DU MONDE, DEJA POSEES : "
                      + " ; ".join(cadre["regles"]))

    if bible.get("personnages"):
        lignes.append("PERSONNAGES QUE LE LECTEUR CONNAIT :")
        for personnage in bible["personnages"][:PERSONNAGES_MAX]:
            detail = "  - {} ({})".format(personnage.get("nom", ""),
                                          personnage.get("role", "secondaire"))
            faits = bible.get("faits", {}).get(personnage.get("nom", ""))
            if faits:
                # Ces faits sont ceux qu'un tome precedent a AFFIRMES. Les
                # rappeler au modele coute trois lignes et evite la
                # contradiction que le lecteur, lui, remarquera.
                detail += " — " + ", ".join(
                    "{} : {}".format(attribut, valeur)
                    for attribut, valeur in sorted(faits.items()))
            lignes.append(detail)

    lignes.append("TOMES PRECEDENTS :")
    for tome in bible["tomes"]:
        lignes.append("  {}. « {} » — {}".format(
            tome.get("rang", "?"), tome.get("titre", ""),
            tome.get("resume", "") or "resume indisponible"))
    lignes.append(
        "Ecris la SUITE : ne reexplique pas ce que le lecteur a deja lu, "
        "ne contredis aucun fait ci-dessus, et n'oublie pas qu'un tome doit "
        "se tenir seul pour qui commence par lui.")
    return "\n".join(lignes)


# --------------------------------------------------------------------------
# Ce que le tome laisse derriere lui
# --------------------------------------------------------------------------


def _fusionner_personnages(anciens: List[Dict[str, str]],
                           nouveaux: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Distribution cumulee, dans l'ordre d'apparition.

    Un personnage deja connu garde la fiche du tome ou il est apparu : c'est
    celle que le lecteur a lue. Un tome ulterieur qui le redecrit autrement ne
    doit pas reecrire le passe — au mieux il precise, au pire il derive.
    """
    connus = {p.get("nom", "") for p in anciens}
    fusion = list(anciens)
    for personnage in nouveaux:
        if personnage.get("nom") and personnage["nom"] not in connus:
            fusion.append(dict(personnage))
            connus.add(personnage["nom"])
    return fusion


def _fusionner_faits(acquis: Dict[str, Dict[str, str]],
                     releves: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Faits canoniques de la serie. Le PREMIER tome qui affirme a raison.

    C'est le point de toute la mecanique : un fait acquis ne se reecrit pas.
    Si le tome 3 donne des yeux bleus a une heroine que le tome 1 a faite aux
    yeux verts, ce n'est pas la serie qui a change d'avis, c'est le tome 3 qui
    se trompe — et « contradictions() » le dira.
    """
    fusion = {nom: dict(attributs) for nom, attributs in acquis.items()}
    for personnage, attributs in releves.items():
        fiche = fusion.setdefault(personnage, {})
        for attribut, valeur in attributs.items():
            fiche.setdefault(attribut, valeur)
    return fusion


def contradictions(nom: str,
                   releves: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """Faits du tome courant qui contredisent ceux d'un tome precedent.

    « releves » est ce que « pipelines/faits.py » a lu dans le texte, reduit a
    une valeur par personnage et par attribut.

    Rien n'est signale quand la serie est neuve : il n'y a pas encore de canon
    a contredire. Et rien n'est signale pour un attribut que la serie ne
    connait pas — c'est le tome courant qui l'etablit.
    """
    bible = lire(nom)
    if not bible:
        return []
    acquis = bible.get("faits") or {}
    trouvees: List[Dict[str, str]] = []
    for personnage in sorted(releves):
        connu = acquis.get(personnage)
        if not connu:
            continue
        for attribut, valeur in sorted(releves[personnage].items()):
            ancienne = connu.get(attribut)
            if ancienne is None or str(ancienne) == str(valeur):
                continue
            trouvees.append({
                "genre": "fait_contredit_la_serie",
                "gravite": "majeur",
                "detail": "« {} » : {} vaut « {} » dans la serie, « {} » ici"
                          .format(personnage, attribut, ancienne, valeur),
            })
    return trouvees


def enregistrer_tome(nom: str, bible_du_tome: Dict[str, Any],
                     titre: str, resume: str, produit_id: str = "",
                     faits: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
    """Range un tome dans sa serie et rend son rang.

    Appele une fois le tome produit, avec ce que la chaine a sous la main :
    aucun appel de modele, aucune interpretation.
    """
    cle = normaliser(nom)
    if not cle:
        return 0
    bible = lire(nom) or _vide(nom)

    # Le cadre du premier tome fait loi. Celui d'un tome ulterieur ne
    # complete que ce qui manquait : reecrire le lieu au tome 3 deplacerait
    # retroactivement une histoire que le lecteur a deja lue.
    cadre = dict(bible.get("cadre") or {})
    for champ, valeur in (bible_du_tome.get("cadre") or {}).items():
        if valeur and not cadre.get(champ):
            cadre[champ] = valeur
    regles = list(cadre.get("regles") or [])
    for regle in (bible_du_tome.get("cadre") or {}).get("regles") or []:
        if regle not in regles:
            regles.append(regle)
    cadre["regles"] = regles[:8]
    bible["cadre"] = cadre

    bible["personnages"] = _fusionner_personnages(
        bible.get("personnages") or [],
        bible_du_tome.get("personnages") or [])[:PERSONNAGES_MAX]
    bible["faits"] = _fusionner_faits(bible.get("faits") or {}, faits or {})

    rang = len(bible.get("tomes") or []) + 1
    bible.setdefault("tomes", []).append({
        "rang": rang,
        "titre": titre,
        "resume": _abreger(resume, MOTS_RESUME_TOME),
        "produit_id": produit_id,
    })
    ecrire(nom, bible)

    if produit_id:
        store.maj_produit(produit_id, serie=cle, rang=rang)
    return rang


# --------------------------------------------------------------------------
# Ce que le lecteur trouve a la derniere page
# --------------------------------------------------------------------------

TITRE_PAGE_DE_SUITE = "La suite"


def page_de_suite(nom: str, rang: int) -> str:
    """La page de fin d'un tome : les autres tomes de la serie.

    C'est ici que la serie devient une vente et pas seulement une continuite.
    Un lecteur qui vient de finir un tome est, a cet instant precis, le plus
    disponible qu'il sera jamais pour en acheter un autre — et la derniere
    page est le seul endroit ou on le tient encore.

    Rendue vide quand il n'y a aucun autre tome : une page « la suite » qui
    n'annonce rien decoit, et une deception a la derniere page est ce qu'on
    peut faire de pire a un lecteur qui vous a lu jusqu'au bout.

    Aucune promesse sur un tome a venir. Ce qui est annonce existe.
    """
    bible = lire(nom)
    if not bible:
        return ""
    autres = [t for t in (bible.get("tomes") or []) if t.get("rang") != rang]
    if not autres:
        return ""

    titre_serie = bible.get("nom") or nom
    lignes = []
    avant = [t for t in autres if (t.get("rang") or 0) < rang]
    apres = [t for t in autres if (t.get("rang") or 0) > rang]

    if rang and avant:
        lignes.append(
            "Vous venez de lire le tome {} de la serie **{}**. Chaque tome se "
            "lit seul, mais ils se repondent.".format(rang, titre_serie))
    else:
        lignes.append("Ce recit appartient a la serie **{}**.".format(titre_serie))
    lignes.append("")

    if avant:
        lignes.append("### Ce qui precede")
        lignes.append("")
        for tome in avant:
            lignes.append("**Tome {} — {}**".format(tome.get("rang"),
                                                    tome.get("titre", "")))
            if tome.get("resume"):
                lignes.append("")
                lignes.append(_abreger(tome["resume"], 45))
            lignes.append("")
    if apres:
        lignes.append("### La suite")
        lignes.append("")
        for tome in apres:
            lignes.append("**Tome {} — {}**".format(tome.get("rang"),
                                                    tome.get("titre", "")))
            if tome.get("resume"):
                lignes.append("")
                lignes.append(_abreger(tome["resume"], 45))
            lignes.append("")

    lignes.append(
        "Si cette histoire vous a plu, le meilleur service que vous puissiez "
        "rendre a son auteur tient en deux lignes d'avis la ou vous l'avez "
        "achetee. C'est ce qui decide si quelqu'un d'autre la trouvera.")
    return "\n".join(lignes).strip()


def tomes_a_rafraichir(nom: str) -> List[Dict[str, Any]]:
    """Tomes dont la page de fin ne connait pas encore les tomes suivants.

    Un tome fabrique quand il etait le dernier porte une page de fin qui
    n'annonce rien de ce qui est venu apres. C'est precisement le lecteur le
    plus precieux — celui du tome 1 — qui ne voit rien.
    """
    bible = lire(nom)
    if not bible:
        return []
    tomes = bible.get("tomes") or []
    dernier = max((t.get("rang") or 0) for t in tomes) if tomes else 0
    return [t for t in tomes if (t.get("rang") or 0) < dernier
            and t.get("produit_id")]


def tomes_du_produit(produit_id: str) -> Optional[Dict[str, Any]]:
    """Serie et rang d'un produit, ou None s'il n'appartient a aucune serie."""
    produit = store.lire_produit(produit_id)
    if not produit or not produit.get("serie"):
        return None
    return {"serie": produit["serie"], "rang": produit.get("rang") or 0}
