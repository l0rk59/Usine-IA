"""L'equipe d'agents et la boucle qualite.

Sept roles, et surtout un mecanisme : ecrire, faire relire par un AUTRE modele,
corriger. La recherche sur les boucles de reflexion est constante sur deux
points, appliques ici :

  - un modele qui se relit lui-meme renforce ses propres erreurs (« degeneration
    de la pensee ») : le relecteur doit donc etre un fournisseur different ;
  - le gain s'epuise apres deux ou trois passes : la boucle est bornee.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..core import controle as ctrl
from ..core import evenements, prompts
from .base import Agent, Critique

# --------------------------------------------------------------------------
# Les roles
# --------------------------------------------------------------------------

def _agent(nom: str) -> Agent:
    """Construit un agent depuis le registre de prompts.

    Les personnalites viennent de usine/core/prompts.py et peuvent etre
    remplacees par atelier/prompts/agents.json sans toucher au code.
    """
    fiche = prompts.agents().get(nom, {})
    return Agent(
        nom=nom,
        metier=str(fiche.get("metier", nom)),
        mission=str(fiche.get("mission", "")),
        regles=[str(r) for r in fiche.get("regles", [])],
        role_modele=str(fiche.get("role_modele", "standard")),
        temperature=float(fiche.get("temperature", 0.75)),
        emoji=str(fiche.get("emoji", "*")),
    )


ARCHITECTE = _agent("architecte")
REDACTEUR = _agent("redacteur")
EDITEUR = _agent("editeur")
REVISEUR = _agent("reviseur")
STYLISTE = _agent("styliste")
MARKETEUR = _agent("marketeur")
CONTROLEUR = _agent("controleur")

EQUIPE: Dict[str, Agent] = {
    a.nom: a for a in (ARCHITECTE, REDACTEUR, EDITEUR, REVISEUR, STYLISTE,
                       MARKETEUR, CONTROLEUR)
}


# --------------------------------------------------------------------------
# La boucle qualite
# --------------------------------------------------------------------------


def _plafond_reecriture(texte: str, marge: int) -> int:
    """Jetons a demander pour RENDRE un texte de cette taille, corrige.

    Une reecriture doit pouvoir rendre au moins autant que ce qu'elle recoit.
    L'ancien plafond fige a 4096 coupait toute reecriture d'un texte de plus
    de huit mille caracteres — soit un chapitre long — et le garde-fou
    « texte tronque » d'en face rejetait alors la correction : une boucle qui
    corrigeait sans jamais rien appliquer.
    """
    from ..pipelines.base import JETONS_MAX

    return max(512, min(JETONS_MAX, len(texte) // 2 + marge))

def grille() -> str:
    return prompts.modele("grille_qualite")


def critiquer(
    contexte: Any,
    texte: str,
    intitule: str,
    promesse: str = "",
    fournisseur_auteur: str = "",
) -> Critique:
    """Fait relire un texte par l'editeur, en evitant le modele qui l'a ecrit."""
    invite = (
        "TEXTE A EVALUER (intitule : « {intitule} »)\n"
        "PROMESSE ANNONCEE : {promesse}\n"
        "PUBLIC : {audience}\n\n"
        "--- DEBUT DU TEXTE ---\n{texte}\n--- FIN DU TEXTE ---\n\n"
        "{grille}\n\n"
        "Schema JSON exact :\n"
        '{{"note": 7.5, "points_forts": ["..."], '
        '"problemes": [{{"passage": "citation exacte du passage fautif", '
        '"probleme": "ce qui ne va pas", "gravite": "bloquant|majeur|mineur", '
        '"correction": "l\'instruction precise de correction"}}], '
        '"verdict": "une phrase"}}\n'
        "Liste au maximum 6 problemes, les plus importants d'abord. "
        "S'il n'y a rien a corriger, renvoie une liste vide."
    ).format(
        intitule=intitule,
        promesse=promesse or "non precisee",
        audience=getattr(contexte, "audience", "un public francophone"),
        texte=texte[:14000],
        grille=grille(),
    )
    relecteur = ""
    try:
        donnees, relecteur = EDITEUR.travailler_json(
            contexte, invite, max_tokens=2600,
            eviter=[fournisseur_auteur] if fournisseur_auteur else None,
            avec_fournisseur=True,
        )
    except Exception as exc:
        evenements.publier("qualite", etat="critique_indisponible", detail=str(exc))
        return Critique(note=7.5, verdict="relecture indisponible")

    if not isinstance(donnees, dict):
        return Critique(note=7.5, verdict="relecture illisible",
                        fournisseur_auteur=fournisseur_auteur,
                        fournisseur_relecteur=relecteur)

    try:
        note = float(donnees.get("note") or 7.0)
    except (TypeError, ValueError):
        note = 7.0
    problemes = [
        {
            "passage": str(p.get("passage") or "")[:300],
            "probleme": str(p.get("probleme") or ""),
            "gravite": str(p.get("gravite") or "mineur"),
            "correction": str(p.get("correction") or ""),
        }
        for p in (donnees.get("problemes") or [])
        if isinstance(p, dict) and p.get("correction")
    ]
    return Critique(
        fournisseur_auteur=fournisseur_auteur,
        fournisseur_relecteur=relecteur,
        note=max(0.0, min(10.0, note)),
        problemes=problemes[:6],
        points_forts=[str(x) for x in (donnees.get("points_forts") or [])][:5],
        verdict=str(donnees.get("verdict") or ""),
    )


def reviser(contexte: Any, texte: str, critique: Critique, intitule: str) -> str:
    """Applique les corrections de la critique, sans toucher au reste."""
    if not critique.problemes:
        return texte
    corrections = "\n".join(
        "{}. [{}] {}\n   Passage vise : « {} »\n   A faire : {}".format(
            i, p["gravite"], p["probleme"], p["passage"][:160], p["correction"]
        )
        for i, p in enumerate(critique.problemes, 1)
    )
    invite = (
        "Voici un texte et la liste des corrections demandees par l'editeur.\n"
        "INTITULE : {intitule}\n\n"
        "--- TEXTE ACTUEL ---\n{texte}\n--- FIN ---\n\n"
        "--- CORRECTIONS A APPLIQUER ---\n{corrections}\n--- FIN ---\n\n"
        "Renvoie le texte COMPLET corrige, en markdown, sans titre de niveau 1, "
        "sans commentaire, sans preambule. Conserve la structure et la longueur."
    ).format(intitule=intitule, texte=texte[:14000], corrections=corrections)
    reponse = REVISEUR.travailler(
        contexte, invite, max_tokens=_plafond_reecriture(texte, 1200))
    from ..pipelines.base import elaguer_markdown

    corrige = elaguer_markdown(reponse.texte)
    # Un reviseur qui renvoie un texte deux fois plus court a tronque : on garde
    # l'original plutot que de livrer un chapitre ampute.
    if len(corrige) < len(texte) * 0.55:
        evenements.publier("qualite", etat="revision_rejetee",
                           detail="texte tronque par le reviseur")
        return texte
    return corrige


def corriger_defauts(
    contexte: Any,
    texte: str,
    rapport: "ctrl.Controle",
    intitule: str,
) -> str:
    """Applique les corrections issues du controle local, en un seul appel.

    Les defauts mesurables (tics, promesses, chiffres sans source, rythme)
    n'ont pas besoin d'un relecteur IA pour etre DETECTES : ils sont trouves en
    Python, gratuitement. Le modele ne sert qu'a reecrire, avec des consignes
    deja precises — ce qui coute un appel au lieu de deux.
    """
    consignes = rapport.consignes()
    if not consignes:
        return texte
    numerotees = "\n".join("{}. {}".format(i, c) for i, c in enumerate(consignes, 1))
    extraits = [a.extrait for a in rapport.anomalies if a.extrait][:3]
    citations = ("\nPassages concernes :\n"
                 + "\n".join("- « {} »".format(e) for e in extraits)) if extraits else ""
    invite = (
        "Un controle automatique a releve des defauts precis dans ce texte.\n"
        "INTITULE : {intitule}\n\n"
        "--- TEXTE ---\n{texte}\n--- FIN ---\n\n"
        "CORRECTIONS A APPLIQUER :\n{consignes}{citations}\n\n"
        "Renvoie le texte COMPLET corrige, en markdown, sans titre de niveau 1, "
        "sans commentaire. Conserve la structure et la longueur."
    ).format(intitule=intitule, texte=texte[:14000], consignes=numerotees,
             citations=citations)

    reponse = REVISEUR.travailler(
        contexte, invite, max_tokens=_plafond_reecriture(texte, 1200))
    from ..pipelines.base import elaguer_markdown

    corrige = elaguer_markdown(reponse.texte)
    if len(corrige) < len(texte) * 0.55:
        evenements.publier("qualite", etat="revision_rejetee",
                           detail="texte tronque lors de la correction automatique")
        return texte
    return corrige


def controler_et_corriger(
    contexte: Any,
    texte: str,
    intitule: str,
    mots_cibles: int = 0,
    precedents: Optional[List[str]] = None,
    tentatives: int = 2,
    exiger_structure: bool = True,
) -> Tuple[str, List["ctrl.Controle"]]:
    """Boucle locale : mesurer, corriger, remesurer. Un appel IA par tour.

    Renvoie le texte et l'historique des controles, pour que le rapport montre
    la progression reelle plutot qu'une affirmation.

    « exiger_structure » existe pour la fiction : une scene de nouvelle n'a ni
    sous-titre ni liste numerotee, et lui reprocher leur absence la ferait
    reecrire dans le sens contraire de ce qu'elle doit etre.
    """
    # Le controle deterministe EST le travail du controleur : on allume
    # sa pastille pour que l'interface le montre a l'oeuvre, meme si
    # aucun appel IA n'est fait ici.
    evenements.publier("agent", agent=CONTROLEUR.nom,
                       etat="debut", emoji=CONTROLEUR.emoji)
    historique: List[ctrl.Controle] = []
    courant = texte
    for tour in range(max(1, tentatives)):
        rapport = ctrl.controler(courant, mots_cibles, precedents or [],
                                 exiger_structure=exiger_structure)
        historique.append(rapport)
        evenements.publier("controle", intitule=intitule, note=rapport.note,
                           anomalies=len(rapport.anomalies),
                           bloquantes=len(rapport.bloquantes), tour=tour + 1)
        if rapport.acceptable or tour == tentatives - 1:
            break
        courant = corriger_defauts(contexte, courant, rapport, intitule)
    evenements.publier("agent", agent=CONTROLEUR.nom, etat="fin",
                       emoji=CONTROLEUR.emoji)
    return courant, historique


def affiner(
    contexte: Any,
    texte: str,
    intitule: str,
    promesse: str = "",
    fournisseur_auteur: str = "",
    passes: int = 1,
) -> Tuple[str, List[Critique]]:
    """Boucle ecrire → critiquer → corriger, bornee a `passes` iterations.

    Renvoie le texte final et l'historique des critiques, pour que le rapport
    qualite montre l'evolution reelle plutot qu'une affirmation.
    """
    historique: List[Critique] = []
    courant = texte
    for passe in range(max(0, passes)):
        critique = critiquer(contexte, courant, intitule, promesse, fournisseur_auteur)
        historique.append(critique)
        evenements.publier("qualite", etat="critique", intitule=intitule,
                           note=critique.note, passe=passe + 1,
                           problemes=len(critique.problemes))
        if critique.acceptable and not critique.bloquants:
            break
        if not critique.problemes:
            break
        courant = reviser(contexte, courant, critique, intitule)
        evenements.publier("qualite", etat="revision", intitule=intitule,
                           passe=passe + 1)
    return courant, historique


def polir(contexte: Any, texte: str, fournisseur_auteur: str = "") -> str:
    """Passe de style : retire les tics d'IA sans rien ajouter."""
    invite = (
        "Resserre ce texte sans en changer le sens ni la structure.\n"
        "Supprime les transitions mecaniques, les redondances et les adverbes "
        "faibles. Varie la longueur des phrases.\n\n"
        "--- TEXTE ---\n{texte}\n--- FIN ---\n\n"
        "Renvoie uniquement le texte resserre, en markdown."
    ).format(texte=texte[:12000])
    try:
        reponse = STYLISTE.travailler(
            contexte, invite, max_tokens=_plafond_reecriture(texte, 900),
            eviter=[fournisseur_auteur] if fournisseur_auteur else None,
        )
    except Exception:
        return texte
    from ..pipelines.base import elaguer_markdown

    poli = elaguer_markdown(reponse.texte)
    return poli if len(poli) > len(texte) * 0.6 else texte


def relire_l_ensemble(contexte: Any, sections: List[Tuple[str, str]],
                      promesse: str = "",
                      fournisseur_auteur: str = "") -> Dict[str, Any]:
    """Une seule lecture du produit ENTIER, a la recherche des incoherences.

    Ce n'est pas la resurrection de « equipe.controler() », retire lors d'un
    audit precedent. Celle-la rendait un VERDICT — une note avant-vente, que
    le controle deterministe donne gratuitement et mieux. Celle-ci cherche
    ce qu'aucun outil local ne peut voir : ce qui se contredit d'une section
    a l'autre.

    Chaque agent travaille section par section ; personne ne lit le produit
    en entier. Une promesse faite dans l'avant-propos et jamais tenue, deux
    chapitres qui donnent des conseils opposes, un terme defini deux fois
    differemment : aucun de ces defauts n'est visible depuis une section
    seule, et aucun ne se mesure en Python.

    C'est un appel de modele par produit, sur un long texte : la chaine le
    demande, il ne s'impose pas.
    """
    if len(sections) < 2:
        return {}
    corps = "\n\n".join(
        "### {}\n{}".format(titre, texte[:2500]) for titre, texte in sections)
    invite = (
        "Voici un produit complet, section par section. Tu le lis d'un bout a "
        "l'autre pour trouver ce qui SE CONTREDIT — rien d'autre.\n\n"
        "PROMESSE ANNONCEE : {promesse}\n\n"
        "--- DEBUT ---\n{corps}\n--- FIN ---\n\n"
        "Cherche uniquement :\n"
        "- une promesse faite quelque part et jamais tenue ailleurs ;\n"
        "- deux passages qui se contredisent ou donnent des conseils opposes ;\n"
        "- un terme ou un chiffre defini deux fois differemment ;\n"
        "- une section qui repete ce qu'une autre a deja dit.\n\n"
        "Ne juge NI le style NI la qualite : d'autres s'en chargent. "
        "S'il n'y a aucune incoherence, renvoie une liste vide — c'est une "
        "reponse parfaitement acceptable.\n\n"
        "Schema JSON exact :\n"
        '{{"incoherences": [{{"sections": ["titre A", "titre B"], '
        '"probleme": "ce qui se contredit", '
        '"gravite": "bloquant|majeur|mineur"}}]}}'
    ).format(promesse=promesse or "non precisee", corps=corps[:30000])

    try:
        donnees, relecteur = EDITEUR.travailler_json(
            contexte, invite, max_tokens=1800,
            eviter=[fournisseur_auteur] if fournisseur_auteur else None,
            avec_fournisseur=True)
    except Exception as exc:
        evenements.publier("qualite", etat="ensemble_indisponible", detail=str(exc))
        return {"disponible": False, "raison": str(exc)}

    brutes = donnees.get("incoherences") if isinstance(donnees, dict) else None
    incoherences = []
    titres = {titre for titre, _ in sections}
    for element in brutes or []:
        if not isinstance(element, dict) or not element.get("probleme"):
            continue
        citees = [str(t) for t in (element.get("sections") or [])
                  if str(t) in titres]
        incoherences.append({
            "sections": citees,
            "probleme": str(element["probleme"])[:400],
            "gravite": str(element.get("gravite") or "mineur").lower(),
        })
    graves = [i for i in incoherences if i["gravite"] in ("bloquant", "majeur")]
    return {
        "disponible": True,
        "relecteur": relecteur,
        "incoherences": incoherences,
        "majeures": len(graves),
        "resume": ("aucune incoherence d'ensemble" if not incoherences else
                   "{} incoherence(s) entre sections, dont {} majeure(s)".format(
                       len(incoherences), len(graves))),
    }


def rapport_qualite(historiques: Dict[str, List[Critique]]) -> Dict[str, Any]:
    """Synthese chiffree des relectures, ecrite dans le dossier du produit."""
    lignes = []
    notes_avant: List[float] = []
    notes_apres: List[float] = []
    for intitule, critiques in historiques.items():
        if not critiques:
            continue
        notes_avant.append(critiques[0].note)
        notes_apres.append(critiques[-1].note)
        lignes.append({
            "section": intitule,
            "note_initiale": critiques[0].note,
            "note_finale": critiques[-1].note,
            "passes": len(critiques),
            "problemes_corriges": sum(len(c.problemes) for c in critiques[:-1]),
            "restants": [p["probleme"] for p in critiques[-1].problemes],
        })
    moyenne = lambda v: round(sum(v) / len(v), 2) if v else None  # noqa: E731
    toutes = [c for suite in historiques.values() for c in suite]
    croisees = [c for c in toutes if c.croisee]
    return {
        "sections": lignes,
        "note_moyenne_initiale": moyenne(notes_avant),
        "note_moyenne_finale": moyenne(notes_apres),
        # Mesure, pas promesse : quand un seul fournisseur est configure, la
        # relecture a lieu sur le modele qui a ecrit — c'est un repli assume,
        # et le rapport doit le montrer plutot que de laisser croire.
        "relecture_croisee": {
            "relectures": len(toutes),
            "sur_un_autre_modele": len(croisees),
            "part": (round(len(croisees) / len(toutes), 2) if toutes else None),
        },
    }
