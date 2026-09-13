"""Ce que l'usine decide quand on ne lui dit rien, et comment elle le montre.

Taper un sujet et rien d'autre etait possible, mais trompeur : les reglages
« par defaut » s'appliquaient — ton « pro », douze chapitres, « un public
francophone motive » — quel que soit le sujet. Un guide de fiscalite pour
experts-comptables et un carnet de recettes pour debutants sortaient donc avec
la meme voix, la meme longueur et la meme audience imaginaire. Ce n'etait pas
un defaut visible : le produit s'ecrivait, se notait, se vendait mal.

Un reglage par defaut n'est pas neutre. Il est juste invisible.

Ce module demande donc au modele ce que le sujet appelle : a qui l'on parle,
sur quel ton, en combien de sections, et dans quelle niche. Trois regles le
gouvernent :

1. **Ce que l'utilisateur a choisi n'est jamais touche.** Le brief ne remplit
   que les cases laissees vides. « --ton punchy » gagne toujours.
2. **Le brief se montre.** Une decision prise en silence ne se corrige pas :
   l'usine ecrit ce qu'elle a choisi et sous quel nom le redemander autrement.
3. **Il doit pouvoir echouer.** Un seul appel, court, et si le modele ne
   repond pas on garde les valeurs par defaut. Personne n'attend cinq minutes
   pour se voir proposer un ton.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core import llm
from .base import (CHAPITRES_MAX, CHAPITRES_MIN, MOTS_MAX, MOTS_MIN, TAILLES,
                   TONS)

# Le mot qui veut dire « decide pour moi ». Il vaut mieux qu'une case vide :
# une case vide se confond avec un reglage oublie, alors que « auto » est un
# choix — celui de ne pas choisir.
AUTO = "auto"

# Ce qu'on demande au modele, et rien de plus : un brief court coute un appel
# court, et c'est le tout premier de la fabrication.
_INVITE = """Tu prepares la fabrication d'un {genre} sur ce sujet :

{sujet}

Decide ce qui convient VRAIMENT a ce sujet-la, pas ce qui conviendrait a
n'importe quoi. Reponds en JSON strict :

{{
  "audience": "a qui s'adresse ce produit, en une ligne precise (metier,
               niveau, situation) — surtout pas « un public motive »",
  "ton": "un des raccourcis ({tons}) OU une description libre de la voix",
  "sections": <nombre entier de sections entre {mini} et {maxi}>,
  "mots_par_section": <entier entre {mots_mini} et {mots_maxi}>,
  "niche": "le positionnement en trois a six mots",
  "promesse": "ce que le lecteur sait faire apres, en une phrase",
  "pourquoi": "en une phrase : pourquoi ce ton et cette longueur pour CE sujet"
}}

Un sujet technique et etroit merite peu de sections denses ; un sujet large et
debutant en merite davantage, plus courtes. Choisis en consequence."""


def _borner(valeur: Any, mini: int, maxi: int, defaut: int) -> int:
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return max(mini, min(maxi, nombre))


def demander(sujet: str, genre: str = "produit",
             journal: Optional[Any] = None) -> Dict[str, Any]:
    """Rend le brief du modele, ou {} s'il n'a pas pu etre obtenu.

    Rendre {} plutot que des valeurs inventees : l'appelant sait alors qu'il
    garde ses defauts, et il le dit. Un brief a moitie devine serait pire que
    pas de brief — on croirait que le sujet a ete lu.
    """
    invite = _INVITE.format(
        genre=genre, sujet=sujet.strip()[:400],
        tons=", ".join(sorted(TONS)),
        mini=CHAPITRES_MIN, maxi=CHAPITRES_MAX,
        mots_mini=MOTS_MIN, mots_maxi=MOTS_MAX)
    try:
        brut = llm.generer_json(
            invite,
            systeme="Tu es un directeur editorial. Tu reponds en JSON strict, "
                    "en francais, sans commentaire autour.",
            # « raisonnement » : c'est un arbitrage, pas une redaction. Chez un
            # fournisseur qui n'a rien de tel, le role retombe sur standard.
            role="raisonnement",
            temperature=0.4,
            max_tokens=600,
        )
    except Exception as exc:          # pas de fournisseur, JSON illisible...
        if journal:
            journal("  brief automatique indisponible ({}) — reglages par "
                    "defaut conserves".format(type(exc).__name__))
        return {}
    if not isinstance(brut, dict):
        return {}

    sections = _borner(brut.get("sections"), CHAPITRES_MIN, CHAPITRES_MAX,
                       TAILLES["standard"][0])
    mots = _borner(brut.get("mots_par_section"), MOTS_MIN, MOTS_MAX,
                   TAILLES["standard"][1])
    return {
        "audience": str(brut.get("audience") or "").strip()[:300],
        "ton": str(brut.get("ton") or "").strip()[:300],
        "sections": sections,
        "mots_par_section": mots,
        "niche": str(brut.get("niche") or "").strip()[:120],
        "promesse": str(brut.get("promesse") or "").strip()[:300],
        "pourquoi": str(brut.get("pourquoi") or "").strip()[:300],
    }


def a_decider(ctx: Any) -> List[str]:
    """Les champs que l'utilisateur a laisses a l'usine.

    Un champ vaut « auto » soit parce qu'il a ete demande ainsi, soit parce
    que le reglage par defaut le dit. Les deux veulent dire la meme chose, et
    c'est bien le point : ne pas choisir est un choix, et il se voit.
    """
    manquants = []
    if not (ctx.audience or "").strip() or (ctx.audience or "").strip() == AUTO:
        manquants.append("audience")
    if not (ctx.ton or "").strip() or (ctx.ton or "").strip() == AUTO:
        manquants.append("ton")
    if (not (ctx.taille or "").strip() or (ctx.taille or "").strip() == AUTO) \
            and not ctx.chapitres:
        manquants.append("taille")
    return manquants


def appliquer(ctx: Any, genre: str = "produit") -> Dict[str, Any]:
    """Complete le contexte avec ce que le modele propose, et le dit.

    Rend le brief applique (vide si rien n'a ete demande ou obtenu), pour que
    la chaine puisse le ranger dans la fiche du produit : une decision qu'on
    ne retrouve plus six mois apres n'aide pas a comprendre le resultat.
    """
    manquants = a_decider(ctx)
    if not manquants:
        return {}
    ctx.journal("Brief automatique : {} a decider...".format(
        ", ".join(manquants)))
    brief = demander(ctx.sujet, genre, journal=ctx.journal)
    if not brief:
        return {}

    applique: Dict[str, Any] = {}
    if "audience" in manquants and brief["audience"]:
        ctx.audience = brief["audience"]
        applique["audience"] = brief["audience"]
    if "ton" in manquants and brief["ton"]:
        ctx.ton = brief["ton"]
        applique["ton"] = brief["ton"]
    if "taille" in manquants:
        ctx.chapitres = brief["sections"]
        ctx.mots_section = brief["mots_par_section"]
        applique["sections"] = brief["sections"]
        applique["mots_par_section"] = brief["mots_par_section"]
    for cle in ("niche", "promesse", "pourquoi"):
        if brief.get(cle):
            applique[cle] = brief[cle]

    # Le brief se montre, et il se redemande autrement. Sans ces lignes, une
    # decision prise en silence ne se corrige pas.
    if applique.get("niche"):
        ctx.journal("  niche : {}".format(applique["niche"]))
    if applique.get("audience"):
        ctx.journal("  audience : {}".format(applique["audience"]))
    if applique.get("ton"):
        ctx.journal("  ton : {}".format(applique["ton"]))
    if applique.get("sections"):
        ctx.journal("  volume : {} sections de ~{} mots".format(
            applique["sections"], applique["mots_par_section"]))
    if applique.get("pourquoi"):
        ctx.journal("  pourquoi : {}".format(applique["pourquoi"]))
    ctx.journal("  (imposez le votre avec --ton, --audience, --chapitres)")
    return applique
