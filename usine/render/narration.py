"""Script de narration : le texte d'un module, dit a voix haute.

Une mini-formation se vend mieux en video, et la video demande un texte qui
se DIT. Ce n'est pas le meme objet qu'un texte qui se lit : a l'oral, une
liste a puces n'existe pas, un sous-titre ne s'entend pas, et « comme vous
pouvez le voir ci-dessus » ne veut plus rien dire.

Ce module ne redige pas — c'est le travail du modele. Il fait ce qui se
calcule : la duree, le nettoyage de ce qui ne se prononce pas, et la mise en
page du script. La duree surtout, parce qu'elle decide du montage et qu'une
estimation au jugé se paie au tournage.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .libelles import accorder

# Debit de reference d'une narration pedagogique posee. La fourchette usuelle
# d'un francais parle clairement va de 140 a 160 mots par minute ; on prend le
# milieu, et on annonce une fourchette plutot qu'un chiffre unique.
MOTS_PAR_MINUTE = 150
DEBIT_LENT, DEBIT_RAPIDE = 130, 170

# Ce qu'on ne prononce pas : balisage markdown, puces, numerotation de liste.
_TITRE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_PUCE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMERO = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_EMPHASE = re.compile(r"(\*\*|__|\*|_|`)")
_CITATION = re.compile(r"^\s*>\s?", re.MULTILINE)
_LIEN = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# Les indications de jeu, conservees telles quelles : elles sont pour la
# personne qui lit, pas pour le micro.
CUES = ("[PAUSE]", "[RESPIRER]", "[INSISTER]", "[SOURIRE]", "[RALENTIR]")


def nettoyer(texte: str) -> str:
    """Retire ce qui ne se prononce pas, garde les indications de jeu.

    Le modele laisse presque toujours un peu de balisage : un « ## » en tete
    de section, des puces, du gras. Lu tel quel par une voix de synthese, cela
    donne « diese diese le contenu ». Corrige ici plutot que redemande au
    modele : c'est gratuit et sur.
    """
    propre = _LIEN.sub(r"\1", texte)
    propre = _TITRE.sub("", propre)
    propre = _CITATION.sub("", propre)
    propre = _PUCE.sub("", propre)
    propre = _NUMERO.sub("", propre)
    propre = _EMPHASE.sub("", propre)
    # Trois lignes vides de suite ne s'entendent pas plus que deux.
    propre = re.sub(r"\n{3,}", "\n\n", propre)
    return propre.strip()


def compter_mots(texte: str) -> int:
    """Mots reellement prononces : les indications de jeu n'en sont pas."""
    sans_cues = texte
    for cue in CUES:
        sans_cues = sans_cues.replace(cue, " ")
    sans_cues = re.sub(r"\[[^\]]{0,40}\]", " ", sans_cues)
    return len([m for m in re.split(r"\s+", sans_cues) if m.strip()])


def duree(mots: int) -> Dict[str, float]:
    """Duree de lecture, en minutes, avec sa fourchette.

    Un chiffre unique donnerait une precision que le debit d'une voix humaine
    n'a pas. La fourchette dit ce qu'elle est : un cadrage de montage.
    """
    if mots <= 0:
        return {"minutes": 0.0, "minimum": 0.0, "maximum": 0.0, "mots": 0}
    return {
        "mots": mots,
        "minutes": round(mots / MOTS_PAR_MINUTE, 1),
        "minimum": round(mots / DEBIT_RAPIDE, 1),
        "maximum": round(mots / DEBIT_LENT, 1),
    }


def minutes_lisibles(mesure: Dict[str, float]) -> str:
    if not mesure["mots"]:
        return "vide"
    return "{} min (entre {} et {})".format(
        mesure["minutes"], mesure["minimum"], mesure["maximum"])


def assembler(titre: str, scripts: List[Tuple[str, str]]) -> Tuple[str, Dict]:
    """Le document complet, et la mesure de l'ensemble.

    Renvoie (markdown, mesures) — les mesures servent au journal et a la
    fiche du produit, pas seulement au document.
    """
    lignes = ["# Script de narration — {}".format(titre), ""]
    mesures = {"modules": [], "mots": 0}
    for nom, texte in scripts:
        propre = nettoyer(texte)
        mesure = duree(compter_mots(propre))
        mesures["modules"].append({"module": nom, **mesure})
        mesures["mots"] += mesure["mots"]
        lignes.append("## {}".format(nom))
        lignes.append("")
        lignes.append("*{} mots — {}*".format(mesure["mots"],
                                              minutes_lisibles(mesure)))
        lignes.append("")
        lignes.append(propre)
        lignes.append("")
    total = duree(mesures["mots"])
    mesures.update({k: v for k, v in total.items() if k != "mots"})
    lignes.insert(1, "")
    lignes.insert(
        2, accorder("*{} module(s), {} mots au total — {} de narration.*".format(
            len(scripts), mesures["mots"], minutes_lisibles(total))))
    return "\n".join(lignes).strip() + "\n", mesures
