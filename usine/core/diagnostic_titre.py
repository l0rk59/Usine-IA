"""Diagnostic local d'un titre commercial, sans appel IA.

Ce module ne predit PAS un taux de clic — personne ne sait le faire a partir
du texte seul. Il releve des proprietes objectives et verifiables : longueur,
presence d'un chiffre, audience nommee, mots creux. A vous de decider ce qui
compte pour votre marche.

Il repond aussi a une question que les outils d'A/B testing oublient : vos
variantes sont-elles assez differentes pour que le test ait un sens ? Comparer
cinq reformulations du meme titre ne mesure rien.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# Mots qui promettent sans prouver. Ils ne sont pas interdits : ils sont
# signales, parce qu'ils usent la credibilite quand ils s'accumulent.
CREUX = [
    "ultime", "revolutionnaire", "incroyable", "secret", "magique", "miracle",
    "explosif", "redoutable", "imparable", "infaillible", "surpuissant",
    "definitif", "absolu", "parfait", "extraordinaire", "exceptionnel",
    "inedit", "exclusif", "indispensable", "incontournable",
]

# Marqueurs d'un lecteur nomme : un titre qui dit a qui il parle se selectionne.
AUDIENCES = [
    "freelance", "independant", "entrepreneur", "debutant", "artisan",
    "consultant", "createur", "salarie", "etudiant", "parent", "retraite",
    "developpeur", "designer", "commercial", "manager", "dirigeant",
    "coach", "formateur", "photographe", "redacteur", "traducteur",
]

DELAI = re.compile(
    r"\b(en|sous)\s+\d+\s*(jours?|semaines?|mois|heures?|minutes?)\b"
    r"|\b\d+\s*(jours?|semaines?|mois)\s+(pour|afin)\b", re.IGNORECASE)
NOMBRE = re.compile(r"\b\d+\b")
_MOT = re.compile(r"\b[\wàâäéèêëîïôöùûüÿçœæ'-]+\b", re.IGNORECASE | re.UNICODE)


def _sans_accent(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte or "").encode(
        "ascii", "ignore").decode("ascii").lower()


@dataclass
class Diagnostic:
    titre: str
    mesures: Dict[str, Any] = field(default_factory=dict)
    atouts: List[str] = field(default_factory=list)
    reserves: List[str] = field(default_factory=list)

    def resume(self) -> str:
        morceaux = []
        if self.atouts:
            morceaux.append("+ " + " · ".join(self.atouts))
        if self.reserves:
            morceaux.append("- " + " · ".join(self.reserves))
        return " | ".join(morceaux) or "rien à signaler"


def diagnostiquer(titre: str) -> Diagnostic:
    """Proprietes objectives d'un titre. Aucune prediction, que des faits."""
    propre = (titre or "").strip()
    normalise = _sans_accent(propre)
    mots = _MOT.findall(propre)
    diagnostic = Diagnostic(titre=propre)

    creux_trouves = [m for m in CREUX if re.search(r"\b" + m, normalise)]
    audience = [a for a in AUDIENCES if a in normalise]
    a_nombre = bool(NOMBRE.search(propre))
    a_delai = bool(DELAI.search(propre))

    diagnostic.mesures = {
        "caracteres": len(propre),
        "mots": len(mots),
        "mots_longs": sum(1 for m in mots if len(m) >= 12),
        "chiffre": a_nombre,
        "delai": a_delai,
        "audience_nommee": audience,
        "mots_creux": creux_trouves,
        "majuscules_excessives": sum(1 for c in propre if c.isupper()) > len(propre) * 0.3
                                  and len(propre) > 12,
        "ponctuation_forte": propre.count("!") + propre.count("?"),
    }

    if a_nombre:
        diagnostic.atouts.append("contient un chiffre")
    if a_delai:
        diagnostic.atouts.append("annonce un délai")
    if audience:
        diagnostic.atouts.append("nomme son lecteur ({})".format(audience[0]))
    if 4 <= len(mots) <= 12:
        diagnostic.atouts.append("longueur lisible ({} mots)".format(len(mots)))

    if len(propre) > 70:
        diagnostic.reserves.append(
            "{} caracteres : tronque sur la plupart des fiches".format(len(propre)))
    if len(mots) < 3:
        diagnostic.reserves.append("très court : peu de prise pour la recherche")
    if creux_trouves:
        diagnostic.reserves.append(
            "mot(s) creux : {}".format(", ".join(creux_trouves[:3])))
    if diagnostic.mesures["majuscules_excessives"]:
        diagnostic.reserves.append("trop de majuscules")
    if diagnostic.mesures["ponctuation_forte"] >= 2:
        diagnostic.reserves.append("ponctuation appuyee")
    if diagnostic.mesures["mots_longs"] >= 3:
        diagnostic.reserves.append("beaucoup de mots longs")
    return diagnostic


# --------------------------------------------------------------------------
# Distinction entre variantes
# --------------------------------------------------------------------------


def similarite(a: str, b: str) -> float:
    """Recouvrement du vocabulaire entre deux titres, de 0 a 1.

    Les mots-outils sont ignores : deux titres qui ne partagent que « le » et
    « pour » ne se ressemblent pas vraiment.
    """
    outils = {"le", "la", "les", "un", "une", "des", "de", "du", "pour", "en",
              "et", "a", "au", "aux", "sur", "dans", "avec", "sans", "vos",
              "votre", "ses", "son", "qui", "que", "ce", "cette"}
    extraire = lambda t: {  # noqa: E731
        m for m in _MOT.findall(_sans_accent(t)) if m not in outils and len(m) > 2}
    ensemble_a, ensemble_b = extraire(a), extraire(b)
    if not ensemble_a or not ensemble_b:
        return 0.0
    return len(ensemble_a & ensemble_b) / len(ensemble_a | ensemble_b)


def distinguer(titres: List[str], seuil: float = 0.55) -> Dict[str, Any]:
    """Verifie que les variantes sont assez differentes pour etre testables.

    C'est le controle que les outils d'A/B testing omettent : si vos cinq
    titres disent la meme chose autrement, le test ne peut rien reveler, et
    les mois d'attente seront perdus.
    """
    paires: List[Tuple[int, int, float]] = []
    for i in range(len(titres)):
        for j in range(i + 1, len(titres)):
            paires.append((i, j, similarite(titres[i], titres[j])))
    trop_proches = [p for p in paires if p[2] >= seuil]
    moyenne = sum(p[2] for p in paires) / len(paires) if paires else 0.0
    return {
        "similarite_moyenne": round(moyenne, 3),
        "paires_trop_proches": [
            {"a": i, "b": j, "similarite": round(s, 3)} for i, j, s in trop_proches
        ],
        "testable": not trop_proches,
        "message": (
            "Variantes suffisamment distinctes." if not trop_proches else
            "{} paire(s) de variantes se ressemblent trop (recouvrement >= {:.0%}) : "
            "le test ne pourra rien reveler. Reformulez-les sur des angles "
            "vraiment differents.".format(len(trop_proches), seuil)
        ),
    }
