"""La prose elle-meme : ce que la charpente ne regarde pas.

Ce que les controles de fiction existants savent deja faire. « faits.py »
tient le registre de ce qui a ete affirme, « voix.py » rattache les repliques
a qui les prononce, « nouvelle.controler_continuite » lit la charpente —
personnages, promesses, beats. Tous regardent la STRUCTURE.

Aucun ne regarde la phrase. Or c'est la que se voit, d'une ligne, qu'un texte
a ete genere : le mot filtre qui met une conscience entre la scene et le
lecteur, l'emotion nommee au lieu d'etre montree, le meme adverbe onze fois,
l'incise qui cherche un synonyme de « dit » a chaque replique.

CE QUE CE MODULE AFFIRME. Rien qui demande un seuil non mesure. Il compte, il
nomme, et il rend les listes — l'humain regarde. Les deux seules lectures
qu'il ecrit sont des FAITS : « voici les six mots filtres, avec leur
phrase », « voici les adverbes repetes ». Pas « votre prose est trop
filtree ».

Pourquoi ce refus. Les reperes chiffres qui existent sont anglais et ne se
transposent pas. Ben Blatt a compte les adverbes en « -ly » de cinquante et un
romans de Stephen King : cent un pour dix mille mots, contre quatre-vingts
chez Hemingway (« Nabokov's Favorite Word Is Mauve », releve le 15/09/2026).
En francais, le suffixe « -ment » porte aussi des NOMS tres courants —
moment, sentiment, gouvernement, batiment — et aucun detecteur ne les separe
des adverbes sans dictionnaire. Annoncer « 140 adverbes pour dix mille mots,
c'est trop » serait donc un chiffre faux compare a un seuil etranger.

Ce qui est rendu a la place : les mots en « -ment » les plus repetes. Un
humain voit d'un coup d'oeil lesquels sont des adverbes, et « doucement »
onze fois se lit sans qu'aucun seuil soit necessaire.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Sequence, Tuple

from .voix import VERBES_DE_PAROLE

SOURCES = {
    "adverbes": (
        "Ben Blatt, « Nabokov's Favorite Word Is Mauve » — adverbes en "
        "« -ly » pour dix mille mots : 101 chez Stephen King (51 romans), 80 "
        "chez Hemingway (10 romans). Releve le 15/09/2026. Repere ANGLAIS : "
        "il n'est pas transpose ici, il situe l'ordre de grandeur."),
    "dialogue": (
        "Part de dialogue mesuree par Mark Liberman (Language Log, "
        "« Proportion of dialogue in novels »), methode : part des caracteres "
        "compris entre guillemets. Releve le 15/09/2026. Virginia Woolf, "
        "« To the Lighthouse » : 3,3 %. Conan Doyle, « Sherlock Holmes » : "
        "47,0 %. Fitzgerald, « Gatsby » : 51,3 %. Agatha Christie : de 49,2 % "
        "en 1920 a 79,4 % en 1972. L'ecart est la donnee : il n'y a pas de "
        "bonne part de dialogue, et c'est pourquoi ce module n'en juge pas."),
    "VERBES_FILTRES": (
        "Ce n'est pas une donnee de marche : une liste fermee de formes "
        "verbales "
        "francaises, choisie pour ce qu'elle permet de detecter SUREMENT "
        "— voir le commentaire qui la precede. Elle ne decrit aucun marche "
        "et ne perime pas."),
    "EMOTIONS": (
        "Ce n'est pas une donnee de marche : une liste fermee d'etats "
        "emotionnels "
        "francais. Elle est volontairement courte — « grand » ou « medecin » "
        "n'y sont pas, parce que relever tout « etait + adjectif » ferait "
        "crier le controle a chaque description."),
    "incises": (
        "Guide editorial releve le 15/09/2026 : 90 a 95 % des incises "
        "devraient employer « dit ». C'est une RECOMMANDATION d'editeur, pas "
        "une mesure sur un corpus — elle est citee, elle ne sert pas de "
        "verdict."),
}

# --------------------------------------------------------------------------
# Ce qui n'est pas de la narration
# --------------------------------------------------------------------------

_GUILLEMETS = re.compile(r"[«\"]\s*.+?\s*[»\"]", re.DOTALL)
_LIGNE_DE_REPLIQUE = re.compile(r"^\s*[—–-]\s+.*$", re.MULTILINE)


def sans_dialogue(texte: str) -> str:
    """Le texte prive de ses repliques.

    Tous les releves de ce module portent sur la NARRATION. Un personnage a
    parfaitement le droit de dire « je suis triste » ou « tu vois bien que
    j'ai raison » : c'est sa voix, et la compter comme un defaut de prose
    ferait crier le controle exactement la ou il n'y a rien.
    """
    return _LIGNE_DE_REPLIQUE.sub(" ", _GUILLEMETS.sub(" ", texte or ""))


def part_de_dialogue(texte: str) -> float:
    """Part des caracteres qui sont du dialogue, entre 0 et 1.

    Meme methode que le releve cite dans « SOURCES » : on compte les
    caracteres, pas les repliques. Une replique de trois mots et un monologue
    de trois cents ne pesent pas pareil dans la lecture.
    """
    entier = len((texte or "").strip())
    if not entier:
        return 0.0
    reste = len(sans_dialogue(texte).strip())
    return round(max(0.0, entier - reste) / entier, 3)


# --------------------------------------------------------------------------
# 1. Les mots filtres
# --------------------------------------------------------------------------

# Le verbe de perception suivi de « que ». La construction compte autant que
# le verbe : « il vit que la porte etait ouverte » interpose une conscience
# la ou « la porte etait ouverte » met le lecteur dans la piece.
#
# Exiger le « que » n'est pas une commodite d'ecriture, c'est ce qui rend le
# detecteur sur. « Il vit » seul est ambigu — vivre ou voir — et « elle
# sentit le froid » est un mot filtre que ce module RATE volontairement.
# Rater un defaut est le choix de ce depot : un controle qui signale a tort
# finit ignore, ce qui est pire que se taire.
VERBES_FILTRES = (
    "vit", "voyait", "voit", "virent", "voyaient",
    "entendit", "entendait", "entend", "entendirent",
    "sentit", "sentait", "sent", "sentirent",
    "remarqua", "remarquait", "remarque",
    "apercut", "apercevait", "apercurent",
    "constata", "constatait", "constate",
    "observa", "observait", "observe",
    "comprit", "comprenait", "comprend", "comprirent",
    "sut", "savait", "sait", "surent",
    "devina", "devinait", "devine",
    "realisa", "realisait", "realise",
    "songea", "songeait",
)
_FILTRE = re.compile(
    r"\b(?:se rendit compte|se rendait compte|s'apercut|s'apercevait|"
    + "|".join(VERBES_FILTRES) + r")\s+qu[e']", re.IGNORECASE)


def _sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte)
                   if unicodedata.category(c) != "Mn")


_PHRASE = re.compile(r"[^.!?…]*[.!?…]+|[^.!?…]+$", re.UNICODE)


def mots_filtres(texte: str) -> List[str]:
    """Les phrases de narration qui interposent une conscience. Sans verdict."""
    trouvees = []
    for phrase in _PHRASE.findall(sans_dialogue(texte)):
        nu = phrase.strip()
        if nu and _FILTRE.search(_sans_accent(nu)):
            trouvees.append(" ".join(nu.split())[:160])
    return trouvees


# --------------------------------------------------------------------------
# 2. L'emotion nommee au lieu d'etre montree
# --------------------------------------------------------------------------

# Liste fermee d'ETATS, pas d'adjectifs en general. « Il etait grand » n'est
# pas un defaut ; « il etait triste » en est un, parce que l'emotion est la
# seule chose qu'un lecteur veut deduire lui-meme.
EMOTIONS = (
    "triste", "heureux", "heureuse", "furieux", "furieuse", "en colere",
    "inquiet", "inquiete", "anxieux", "anxieuse", "terrifie", "terrifiee",
    "effraye", "effrayee", "surpris", "surprise", "decu", "decue",
    "soulage", "soulagee", "epuise", "epuisee", "nerveux", "nerveuse",
    "jaloux", "jalouse", "honteux", "honteuse", "coupable", "fier", "fiere",
    "amoureux", "amoureuse", "content", "contente", "malheureux",
    "malheureuse", "bouleverse", "bouleversee", "terrorise", "terrorisee",
    "excite", "excitee", "desespere", "desesperee", "perplexe",
)
_ETAT = re.compile(
    r"\b(?:etait|etaient|est|sont|se sentait|se sentit|se sentirent|"
    r"se sent|paraissait|parut|semblait|sembla|avait l'air)\s+"
    r"(?:tres |si |tellement |plutot |assez |vraiment )?(?:"
    + "|".join(re.escape(e) for e in EMOTIONS) + r")\b", re.IGNORECASE)


def emotions_nommees(texte: str) -> List[str]:
    """Les endroits ou l'emotion est dite plutot que montree. Sans verdict."""
    trouvees = []
    for phrase in _PHRASE.findall(sans_dialogue(texte)):
        nu = phrase.strip()
        if nu and _ETAT.search(_sans_accent(nu)):
            trouvees.append(" ".join(nu.split())[:160])
    return trouvees


# --------------------------------------------------------------------------
# 3. Les mots en -ment
# --------------------------------------------------------------------------

# Quatre lettres au minimum AVANT « -ment ». Ce n'est pas un reglage de
# confort : c'est ce qui ecarte les noms les plus courts — moment, ciment,
# ment, dement — qui, eux, reviendraient en tete de chaque releve. Le cout
# est une poignee d'adverbes rares construits sur un adjectif de trois
# lettres (« dument », « crument »), que ce module rate. Rater plutot
# qu'inventer.
_EN_MENT = re.compile(r"\b[^\W\d_]{4,}ment\b", re.UNICODE)


def mots_en_ment(texte: str) -> Dict[str, int]:
    """Les mots en « -ment » et leur nombre. Adverbes et noms confondus.

    Confondus VOLONTAIREMENT. « Changement » et « lentement » se ressemblent
    trop en francais pour qu'un detecteur les separe sans dictionnaire, et un
    dictionnaire ne tient pas dans ce depot. Une liste d'exceptions ecrite a
    la main serait incomplete par construction : elle rendrait un chiffre
    faux qui aurait l'air juste.

    Seule la longueur ecarte quelque chose, et seulement les noms les plus
    courts : voir « _EN_MENT ». « Gouvernement », « sentiment », « document »
    restent comptes comme des adverbes.

    Ce qui sort d'ici est donc une liste de mots avec leur compte. Un humain
    voit en une seconde que « moment » est un nom et que « doucement » onze
    fois est un tic — ce qu'aucun seuil n'aurait dit a sa place.
    """
    comptes: Dict[str, int] = {}
    for mot in _EN_MENT.findall(sans_dialogue(texte)):
        cle = mot.lower()
        comptes[cle] = comptes.get(cle, 0) + 1
    return comptes


# --------------------------------------------------------------------------
# 4. Les incises
# --------------------------------------------------------------------------

_DIRE = ("dit", "dis", "disait", "disaient", "dirent", "redit")
_AUTRES_VERBES = tuple(v for v in VERBES_DE_PAROLE if v not in _DIRE)
_INCISE_DIRE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _DIRE) + r")\b", re.IGNORECASE)
_INCISE_AUTRE = re.compile(
    r"\b(?:" + "|".join(re.escape(_sans_accent(v)) for v in _AUTRES_VERBES)
    + r")\b", re.IGNORECASE)


def incises(texte: str) -> Dict[str, Any]:
    """Comment les repliques sont introduites : « dit », ou autre chose.

    Le releve porte sur les LIGNES DE REPLIQUE, pas sur la narration : un
    « il murmura » au milieu d'un paragraphe descriptif n'est pas une incise.
    """
    dire, autres = 0, {}
    for ligne in _LIGNE_DE_REPLIQUE.findall(texte or ""):
        nu = _sans_accent(ligne)
        if _INCISE_DIRE.search(nu):
            dire += 1
            continue
        trouve = _INCISE_AUTRE.search(nu)
        if trouve:
            mot = trouve.group(0).lower()
            autres[mot] = autres.get(mot, 0) + 1
    total = dire + sum(autres.values())
    return {
        "incises": total,
        "avec_dit": dire,
        "part_de_dit": round(dire / total, 3) if total else 0.0,
        "autres_verbes": dict(sorted(autres.items(),
                                     key=lambda kv: -kv[1])[:10]),
    }


# --------------------------------------------------------------------------
# La mesure d'ensemble, et sa lecture
# --------------------------------------------------------------------------

_MOT = re.compile(r"[^\W\d_]+", re.UNICODE)

# A partir de combien d'occurrences un mot en « -ment » est RAPPORTE. Ce n'est
# pas un seuil de qualite : c'est le point ou une liste devient lisible. En
# dessous de trois, la liste d'un roman fait deux cents lignes et personne ne
# la lit.
REPETITIONS_MONTREES = 3


def mesurer_la_prose(sections: Sequence[Tuple[str, str]]) -> Dict[str, Any]:
    """Les cinq releves, pour l'ensemble et section par section."""
    entier = "\n\n".join(corps for _titre, corps in sections)
    mots = len(_MOT.findall(entier))
    repetes = {mot: n for mot, n in mots_en_ment(entier).items()
               if n >= REPETITIONS_MONTREES}
    par_section = []
    for titre, corps in sections:
        filtres = mots_filtres(corps)
        emotions = emotions_nommees(corps)
        if filtres or emotions:
            par_section.append({"titre": titre,
                                "mots_filtres": len(filtres),
                                "emotions_nommees": len(emotions)})
    return {
        "mots": mots,
        "mots_filtres": mots_filtres(entier),
        "emotions_nommees": emotions_nommees(entier),
        "mots_en_ment_repetes": dict(sorted(repetes.items(),
                                            key=lambda kv: -kv[1])),
        "mots_en_ment_pour_dix_mille": (
            round(sum(mots_en_ment(entier).values()) * 10000 / mots, 1)
            if mots else 0.0),
        "part_de_dialogue": part_de_dialogue(entier),
        "incises": incises(entier),
        "sections_concernees": par_section,
    }


def lire_la_prose(mesure: Dict[str, Any]) -> List[str]:
    """Ce que la mesure permet de dire, et rien de plus.

    Aucune de ces lignes n'est un verdict : chacune est un compte, suivi de
    ce qui a ete compte. C'est ce qui permet a un humain de trancher en
    quelques secondes — et ce qui evite d'ecrire « votre prose est trop
    filtree » a partir d'un seuil que personne n'a mesure.
    """
    lectures = []
    filtres = mesure["mots_filtres"]
    if filtres:
        lectures.append(
            "{} phrase(s) mettent une conscience entre la scene et le "
            "lecteur. La premiere : « {} »".format(len(filtres), filtres[0]))
    emotions = mesure["emotions_nommees"]
    if emotions:
        lectures.append(
            "{} emotion(s) nommees au lieu d'etre montrees. La premiere : "
            "« {} »".format(len(emotions), emotions[0]))
    repetes = mesure["mots_en_ment_repetes"]
    if repetes:
        lectures.append(
            "Mots en « -ment » repetes : {}. (Noms et adverbes confondus : "
            "le depot ne les separe pas.)".format(
                ", ".join("{} x{}".format(m, n)
                          for m, n in list(repetes.items())[:8])))
    autres = mesure["incises"]["autres_verbes"]
    if autres:
        lectures.append(
            "{} incise(s) sur {} evitent « dit » : {}.".format(
                mesure["incises"]["incises"] - mesure["incises"]["avec_dit"],
                mesure["incises"]["incises"],
                ", ".join("{} x{}".format(v, n)
                          for v, n in list(autres.items())[:6])))
    return lectures


def situer_le_dialogue(part: float) -> str:
    """Place la part de dialogue parmi des romans REELLEMENT mesures.

    Pas de verdict : l'ecart entre 3,3 % chez Woolf et 79,4 % chez Christie
    est precisement ce qui interdit d'en rendre un. La phrase situe, elle ne
    juge pas.
    """
    pourcent = round(part * 100, 1)
    if part < 0.10:
        repere = "sous « To the Lighthouse » (3,3 %) et loin de « Sherlock Holmes » (47,0 %)"
    elif part < 0.35:
        repere = "entre « To the Lighthouse » (3,3 %) et « Sherlock Holmes » (47,0 %)"
    elif part < 0.55:
        repere = "autour de « Sherlock Holmes » (47,0 %) et « Gatsby » (51,3 %)"
    else:
        repere = "au-dessus de « Gatsby » (51,3 %), vers Christie tardive (79,4 %)"
    return "Dialogue : {} % du texte — {}.".format(pourcent, repere)
