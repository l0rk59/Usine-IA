"""Le registre des faits : ce que le texte affirme, et ce qu'il se contredit.

Le controle de continuite de « nouvelle.py » verifie la CHARPENTE — un
personnage annonce puis oublie, un beat jamais livre, une intrigue
abandonnee. Il ne lit pas ce que les phrases affirment. Une heroine aux yeux
verts au chapitre deux et aux yeux bleus au chapitre neuf traverse donc tous
les controles : la structure est intacte, seul le detail ment.

C'est le defaut de continuite que les lecteurs relevent le plus, et celui qui
se voit le moins a la relecture d'un auteur — a plus forte raison quand le
texte est ecrit scene par scene par un modele dont la memoire est un resume
de quatre-vingt-dix mots.

Aucun appel de modele ici, et c'est deliberer : demander a une IA si elle
s'est contredite revient a lui demander de se relire, ce qu'elle fait mal.
Une contradiction sur une couleur d'yeux est un fait verifiable, et un fait
verifiable se verifie.

CE QUE CE MODULE NE FAIT PAS. Il ne comprend pas le recit. Il ne suit que des
attributs a vocabulaire ferme (yeux, cheveux, age), et seulement quand la
phrase ne nomme qu'un personnage — sinon l'attribution serait devinee. Il rate
donc des contradictions plutot que d'en inventer : un garde-fou qui crie a
tort n'est plus lu. Les attributs qui peuvent legitimement changer (les
cheveux se teignent, blanchissent) sont signales comme a verifier, jamais
comme fautifs.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------
# Les attributs suivis
# --------------------------------------------------------------------------

# Un attribut = un nom commun porteur, un vocabulaire ferme de valeurs, et le
# fait de savoir s'il peut changer en cours de recit. Les valeurs sont ecrites
# sans accent et au masculin singulier : la comparaison passe par _plat().
ATTRIBUTS: Dict[str, Dict[str, Any]] = {
    "yeux": {
        "porteurs": ("yeux", "regard", "prunelles", "iris"),
        "valeurs": {
            "bleu": ("bleu", "bleus", "bleue", "bleues", "azur"),
            "vert": ("vert", "verts", "verte", "vertes", "emeraude"),
            "noir": ("noir", "noirs", "noire", "noires"),
            "marron": ("marron", "brun", "bruns", "brune", "brunes",
                       "noisette", "chocolat"),
            "gris": ("gris", "grise", "grises"),
            "ambre": ("ambre", "ambres", "dore", "dores", "doree", "dorees"),
        },
        # Les yeux ne changent pas. Une divergence est une faute, pas un fait.
        "peut_changer": False,
        "libelle": "la couleur des yeux",
    },
    "cheveux": {
        "porteurs": ("cheveux", "chevelure", "meches", "tignasse"),
        "valeurs": {
            "blond": ("blond", "blonds", "blonde", "blondes"),
            "brun": ("brun", "bruns", "brune", "brunes", "chatain",
                     "chatains", "chataine"),
            "noir": ("noir", "noirs", "noire", "noires", "corbeau"),
            "roux": ("roux", "rousse", "rousses", "auburn"),
            "gris": ("gris", "grise", "grises", "poivre et sel"),
            "blanc": ("blanc", "blancs", "blanche", "blanches"),
        },
        # Une teinture, un choc, vingt ans : les cheveux changent pour de bon.
        "peut_changer": True,
        "libelle": "la couleur des cheveux",
    },
}

# L'age s'ecrit de trois facons dans un recit, et la fiction n'emploie
# presque jamais la premiere : « 32 ans », « trente-deux ans »,
# « la quarantaine ». Ne lire que les chiffres revenait a ne rien lire.
_AGE_CHIFFRE = re.compile(r"\b(\d{1,3})\s+ans\b", re.IGNORECASE)
_DIZAINES = {
    "vingtaine": 20, "trentaine": 30, "quarantaine": 40, "cinquantaine": 50,
    "soixantaine": 60, "septantaine": 70, "octogenaire": 80,
    "nonagenaire": 90, "centenaire": 100,
}
_AGE_DIZAINE = re.compile(
    r"\b(?:la\s+)?(" + "|".join(_DIZAINES) + r")\b", re.IGNORECASE)

# Nombres francais ecrits en lettres, de un a cent vingt. « quatre-vingts » et
# « soixante-dix » se composent : les unites s'ajoutent a la dizaine, sauf
# pour les dizaines de soixante-dix et quatre-vingt-dix ou elles s'ajoutent a
# soixante et quatre-vingts.
_UNITES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
}
_SOCLES = {
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "cent": 100, "cents": 100,
}
# On ne cherche pas le nombre : on cherche « ans », puis on remonte mot a mot.
# Une expression reguliere gourmande avalait le debut de la phrase — « camille
# avait quarante-cinq » — et le lecteur de nombres rejetait le tout.
_AVANT_ANS = re.compile(r"([a-z][a-z\- ]{0,40})\s+ans\b", re.IGNORECASE)


def _valeur_ecrite(expression: str) -> Optional[int]:
    """Valeur brute d'un nombre francais ecrit en lettres, sans borne d'age.

    Separer « ce n'est pas un nombre » de « c'est un nombre, mais pas un
    age » est necessaire : sans cela, « trois cents ans » se repliait sur son
    dernier mot et faisait un centenaire.
    """
    morceaux = [m for m in re.split(r"[- ]+", _plat(expression)) if m and m != "et"]
    if not morceaux or any(m not in _UNITES and m not in _SOCLES
                           for m in morceaux):
        return None
    total = 0
    for morceau in morceaux:
        if morceau in _SOCLES:
            socle = _SOCLES[morceau]
            # « quatre-vingt » : quatre puis vingt se multiplient, ils ne
            # s'ajoutent pas. Idem « deux cents ».
            total = (total * socle) if total and socle >= 20 and total < 10 \
                else total + socle
        else:
            total += _UNITES[morceau]
    return total


def _nombre_ecrit(expression: str) -> Optional[int]:
    """Age ecrit en lettres, ou None. Un personnage a entre 1 et 120 ans."""
    valeur = _valeur_ecrite(expression)
    return valeur if valeur is not None and 1 <= valeur <= 120 else None

# L'attribut doit toucher le porteur : « ses yeux verts », « les yeux d'un
# vert pale ». Au-dela d'une trentaine de caracteres, le lien n'est plus sur.
PORTEE = 40

_PHRASE = re.compile(r"[^.!?…]+[.!?…]*", re.UNICODE)
_MOT = re.compile(r"[^\W\d_]+", re.UNICODE)


def _plat(texte: str) -> str:
    """Minuscules sans accent : « Émeraude » et « emeraude » se comparent."""
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def phrases(texte: str) -> List[str]:
    return [p.strip() for p in _PHRASE.findall(texte) if p.strip()]


# --------------------------------------------------------------------------
# Qui parle cette phrase ?
# --------------------------------------------------------------------------


def _parties(nom: str) -> List[str]:
    """Mots d'un nom qui servent a le reconnaitre, titres ecartes."""
    petits = {"de", "du", "des", "le", "la", "les", "monsieur", "madame",
              "mademoiselle", "docteur", "professeur", "maitre", "pere",
              "mere", "oncle", "tante"}
    mots = [_plat(m) for m in _MOT.findall(nom)]
    retenus = [m for m in mots if len(m) > 2 and m not in petits]
    return retenus or mots


def nommes(phrase: str, noms: Iterable[str]) -> List[str]:
    """Personnages de la distribution nommes dans cette phrase.

    Rend la liste entiere, pas le premier : c'est le NOMBRE qui decide. Une
    phrase qui nomme deux personnages ne permet pas de savoir a qui appartient
    « ses yeux verts », et deviner serait pire que se taire.

    Les homonymes sont le piege de cette reconnaissance, et il est reel : une
    mere et sa fille partagent un nom de famille, donc « Camille Renard » et
    « Lucie Renard » se reconnaissent l'une dans l'autre a chaque page. Le
    depart se fait au NOMBRE de mots retrouves — « Camille Renard » en a deux
    dans « Camille poussa la porte », « Lucie Renard » un seul — et seulement
    quand un candidat devance strictement les autres. A egalite, la phrase
    reste ambigue : elle rend les deux noms, donc elle sera ecartee. C'est le
    meme depart que « nouvelle.personnage_officiel », pour la meme raison.
    """
    plate = _plat(phrase)
    scores: List[Tuple[int, str]] = []
    for nom in noms:
        retrouves = sum(
            1 for partie in _parties(nom)
            if re.search(r"\b" + re.escape(partie) + r"\b", plate))
        if retrouves:
            scores.append((retrouves, nom))
    if not scores:
        return []
    meilleur = max(s for s, _ in scores)
    return [nom for score, nom in scores if score == meilleur]


# --------------------------------------------------------------------------
# Lecture des attributs
# --------------------------------------------------------------------------


def _valeur_proche(plate: str, debut: int, fin: int,
                   valeurs: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    """Valeur d'attribut citee dans le voisinage immediat du porteur."""
    gauche = max(0, debut - PORTEE)
    voisinage = plate[gauche:fin + PORTEE]
    for canonique, formes in valeurs.items():
        for forme in formes:
            if re.search(r"\b" + re.escape(forme) + r"\b", voisinage):
                return canonique
    return None


def lire_attributs(phrase: str) -> Dict[str, str]:
    """Attributs physiques affirmes par une phrase, sous forme canonique."""
    plate = _plat(phrase)
    trouves: Dict[str, str] = {}
    for attribut, regle in ATTRIBUTS.items():
        for porteur in regle["porteurs"]:
            for occurrence in re.finditer(r"\b" + re.escape(porteur) + r"\b",
                                          plate):
                valeur = _valeur_proche(plate, occurrence.start(),
                                        occurrence.end(), regle["valeurs"])
                if valeur:
                    trouves[attribut] = valeur
                    break
            if attribut in trouves:
                break
    age = lire_age(phrase)
    if age is not None:
        trouves["age"] = str(age)
    return trouves


def lire_age(phrase: str) -> Optional[int]:
    """Age affirme par une phrase, en annees.

    « la quarantaine » vaut quarante : ce n'est pas le meme fait que « 42 ans »,
    et c'est pourquoi l'ecart tolere plus bas est d'une dizaine.
    """
    plate = _plat(phrase)
    chiffre = _AGE_CHIFFRE.search(plate)
    if chiffre:
        valeur = int(chiffre.group(1))
        # Au-dela, ce n'est plus un age de personnage : « trois cents ans de
        # solitude », « la maison a 200 ans ».
        if 1 <= valeur <= 120:
            return valeur
    for avant in _AVANT_ANS.finditer(plate):
        mots_avant = [m for m in re.split(r"[- ]+", avant.group(1)) if m]
        # Du plus long au plus court : « quatre-vingt-douze » avant « douze ».
        for debut in range(max(0, len(mots_avant) - 4), len(mots_avant)):
            valeur = _valeur_ecrite(" ".join(mots_avant[debut:]))
            if valeur is None:
                continue  # « avait quarante » n'est pas un nombre : on raccourcit
            # Le plus long nombre qui precede « ans » decide. S'il deborde,
            # ce n'est l'age de personne — se rabattre sur un morceau plus
            # court ferait de « trois cents ans » un centenaire.
            return valeur if 1 <= valeur <= 120 else None
    dizaine = _AGE_DIZAINE.search(plate)
    if dizaine:
        return _DIZAINES[dizaine.group(1)]
    return None


# --------------------------------------------------------------------------
# Le registre
# --------------------------------------------------------------------------


def relever(sections: List[Tuple[str, str]],
            noms: Iterable[str]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Tout ce que le texte affirme, par personnage puis par attribut.

    Chaque affirmation garde sa phrase : une contradiction sans la citation
    des deux passages oblige a relire le livre entier pour la verifier, ce que
    personne ne fait.
    """
    noms = list(noms)
    registre: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for titre, corps in sections:
        for phrase in phrases(corps):
            presents = nommes(phrase, noms)
            if len(presents) != 1:
                continue  # zero : personne a qui rattacher ; deux : on devine
            attributs = lire_attributs(phrase)
            if not attributs:
                continue
            fiche = registre.setdefault(presents[0], {})
            for attribut, valeur in attributs.items():
                fiche.setdefault(attribut, []).append({
                    "valeur": valeur,
                    "section": titre,
                    "extrait": phrase[:200],
                })
    return registre


# Deux ages qui different d'une dizaine peuvent etre le meme fait dit deux
# fois : « la quarantaine » et « quarante-deux ans ». Au-dela, le texte s'est
# contredit.
ECART_AGE = 10


def _libelle(attribut: str) -> str:
    if attribut == "age":
        return "l'age"
    return ATTRIBUTS[attribut]["libelle"]


def _contradiction_age(releves: List[Dict[str, Any]]) -> Optional[Tuple[Dict, Dict]]:
    ages = [(int(r["valeur"]), r) for r in releves]
    plus_jeune = min(ages, key=lambda t: t[0])
    plus_vieux = max(ages, key=lambda t: t[0])
    if plus_vieux[0] - plus_jeune[0] > ECART_AGE:
        return plus_jeune[1], plus_vieux[1]
    return None


def contradictions(registre: Dict[str, Dict[str, List[Dict[str, Any]]]]
                   ) -> List[Dict[str, Any]]:
    """Les faits que le texte affirme de deux facons incompatibles.

    Une seule anomalie par personnage et par attribut : signaler chaque paire
    d'un attribut cite dix fois noierait le constat dans sa propre repetition.
    """
    trouvees: List[Dict[str, Any]] = []
    for personnage in sorted(registre):
        for attribut in sorted(registre[personnage]):
            releves = registre[personnage][attribut]
            if len(releves) < 2:
                continue
            if attribut == "age":
                paire = _contradiction_age(releves)
                if paire is None:
                    continue
                premier, second = paire
                detail = "{} a {} ans puis {} ans".format(
                    personnage, premier["valeur"], second["valeur"])
                peut_changer = False
            else:
                valeurs = {r["valeur"] for r in releves}
                if len(valeurs) < 2:
                    continue
                premier = releves[0]
                second = next(r for r in releves if r["valeur"] != premier["valeur"])
                detail = "{} : {} passe de « {} » a « {} »".format(
                    personnage, _libelle(attribut), premier["valeur"],
                    second["valeur"])
                peut_changer = bool(ATTRIBUTS[attribut]["peut_changer"])
            trouvees.append({
                "genre": "fait_contredit",
                # Ce qui peut legitimement changer se signale sans accuser :
                # une teinture n'est pas une faute de continuite.
                "gravite": "mineur" if peut_changer else "majeur",
                "personnage": personnage,
                "attribut": attribut,
                "detail": detail + (" (peut etre voulu)" if peut_changer else ""),
                "preuves": [
                    {"section": premier["section"], "extrait": premier["extrait"]},
                    {"section": second["section"], "extrait": second["extrait"]},
                ],
            })
    return trouvees


def controler(sections: List[Tuple[str, str]],
              noms: Iterable[str]) -> Dict[str, Any]:
    """Registre et contradictions d'un texte, en une passe."""
    registre = relever(sections, noms)
    trouvees = contradictions(registre)
    return {
        "registre": registre,
        "contradictions": trouvees,
        "faits": sum(len(v) for f in registre.values() for v in f.values()),
        "resume": ("aucune contradiction de fait" if not trouvees else
                   "{} fait(s) contredit(s)".format(len(trouvees))),
    }
