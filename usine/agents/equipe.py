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
    try:
        donnees = EDITEUR.travailler_json(
            contexte, invite, max_tokens=2600,
            eviter=[fournisseur_auteur] if fournisseur_auteur else None,
        )
    except Exception as exc:
        evenements.publier("qualite", etat="critique_indisponible", detail=str(exc))
        return Critique(note=7.5, verdict="relecture indisponible")

    if not isinstance(donnees, dict):
        return Critique(note=7.5, verdict="relecture illisible")

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
    reponse = REVISEUR.travailler(contexte, invite,
                                  max_tokens=min(4096, len(texte) // 2 + 1200))
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
        contexte, invite, max_tokens=min(4096, len(texte) // 2 + 1200))
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
) -> Tuple[str, List["ctrl.Controle"]]:
    """Boucle locale : mesurer, corriger, remesurer. Un appel IA par tour.

    Renvoie le texte et l'historique des controles, pour que le rapport montre
    la progression reelle plutot qu'une affirmation.
    """
    historique: List[ctrl.Controle] = []
    courant = texte
    for tour in range(max(1, tentatives)):
        rapport = ctrl.controler(courant, mots_cibles, precedents or [])
        historique.append(rapport)
        evenements.publier("controle", intitule=intitule, note=rapport.note,
                           anomalies=len(rapport.anomalies),
                           bloquantes=len(rapport.bloquantes), tour=tour + 1)
        if rapport.acceptable or tour == tentatives - 1:
            break
        courant = corriger_defauts(contexte, courant, rapport, intitule)
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
            contexte, invite, max_tokens=min(4096, len(texte) // 2 + 900),
            eviter=[fournisseur_auteur] if fournisseur_auteur else None,
        )
    except Exception:
        return texte
    from ..pipelines.base import elaguer_markdown

    poli = elaguer_markdown(reponse.texte)
    return poli if len(poli) > len(texte) * 0.6 else texte


def controler(contexte: Any, titre: str, promesse: str, extrait: str,
              prix: str = "") -> Dict[str, Any]:
    """Verdict final avant mise en vente."""
    invite = (
        "PRODUIT : {titre}\nPROMESSE : {promesse}\n"
        "PRIX ENVISAGE : {prix}\nPUBLIC : {audience}\n\n"
        "EXTRAIT DU CONTENU :\n{extrait}\n\n"
        "Rends un verdict de mise en vente.\n\n"
        "Schema JSON exact :\n"
        '{{"pret": true, "note_globale": 8.0, '
        '"coherence_promesse": "la promesse est-elle tenue ?", '
        '"risques": [{{"type": "juridique|sanitaire|commercial", '
        '"detail": "...", "action": "..."}}], '
        '"prix_juste": "sous-evalue|correct|sur-evalue", '
        '"a_corriger_avant_vente": ["..."], "verdict": "une phrase"}}'
    ).format(titre=titre, promesse=promesse, prix=prix or "non defini",
             audience=getattr(contexte, "audience", "un public francophone"),
             extrait=extrait[:9000])
    try:
        rapport = CONTROLEUR.travailler_json(contexte, invite, max_tokens=2000)
    except Exception as exc:
        return {"pret": True, "note_globale": None, "verdict": "controle indisponible",
                "erreur": str(exc), "risques": [], "a_corriger_avant_vente": []}
    if not isinstance(rapport, dict):
        return {"pret": True, "verdict": "controle illisible", "risques": [],
                "a_corriger_avant_vente": []}
    rapport.setdefault("risques", [])
    rapport.setdefault("a_corriger_avant_vente", [])
    return rapport


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
    return {
        "sections": lignes,
        "note_moyenne_initiale": moyenne(notes_avant),
        "note_moyenne_finale": moyenne(notes_apres),
    }
