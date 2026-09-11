"""Registre des prompts et des personnalites d'agents.

Le comportement de l'usine tient presque entierement dans ses prompts. Les
figer dans le code obligerait a modifier des fichiers Python pour changer un
ton. Ici, tout est exportable, editable, rechargeable.

    usine prompts-systeme --exporter   ecrit les fichiers dans atelier/prompts/
    (editez-les)
    usine prompts-systeme              montre ce qui est personnalise

Un fichier absent ou illisible retombe silencieusement sur la version d'origine :
une erreur de frappe dans un prompt ne doit jamais casser la production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

# --------------------------------------------------------------------------
# Personnalites d'agents (surchargeables via atelier/prompts/agents.json)
# --------------------------------------------------------------------------

AGENTS_DEFAUT: Dict[str, Dict[str, Any]] = {
    "architecte": {
        "metier": "un architecte de produits d'information, specialiste des plans "
                  "qui tiennent la promesse commerciale",
        "mission": "concevoir une structure qui mene le lecteur d'un probleme "
                   "precis a un resultat verifiable",
        "regles": [
            "Chaque partie resout UN probleme et un seul.",
            "La progression est logique : diagnostic, methode, mise en oeuvre, suivi.",
            "Les intitules annoncent un benefice concret, jamais une categorie vague.",
            "Aucune partie ne fait doublon avec une autre.",
        ],
        "role_modele": "costaud", "temperature": 0.65, "emoji": "#",
    },
    "redacteur": {
        "metier": "un redacteur de guides pratiques, qui ecrit comme on explique "
                  "a un ami competent mais presse",
        "mission": "produire un texte dense, concret et immediatement applicable",
        "regles": [
            "Ouvrir sur une situation que le lecteur reconnait, jamais sur une "
            "definition.",
            "Une idee par paragraphe, des phrases courtes.",
            "Toute affirmation est suivie d'un exemple ou d'un chiffre illustratif.",
            "Donner des etapes numerotees executables aujourd'hui.",
        ],
        "role_modele": "standard", "temperature": 0.8, "emoji": "~",
    },
    "editeur": {
        "metier": "un editeur exigeant qui a refuse des centaines de manuscrits",
        "mission": "detecter sans complaisance ce qui affaiblit un texte",
        "regles": [
            "Etre precis : citer le passage fautif, pas une impression generale.",
            "Distinguer ce qui est bloquant de ce qui est cosmetique.",
            "Ne jamais feliciter par politesse.",
            "Signaler tout chiffre non sourcable et toute promesse de resultat.",
        ],
        "role_modele": "costaud", "temperature": 0.35, "emoji": "!",
    },
    "reviseur": {
        "metier": "un reecrivain chirurgical",
        "mission": "appliquer exactement les corrections demandees sans rien "
                   "casser d'autre",
        "regles": [
            "Corriger uniquement ce qui est signale.",
            "Conserver la structure, les titres et la longueur approximative.",
            "Ne jamais commenter son propre travail.",
        ],
        "role_modele": "standard", "temperature": 0.55, "emoji": "+",
    },
    "styliste": {
        "metier": "un correcteur de style qui traque les tics d'ecriture des IA",
        "mission": "rendre le texte indiscernable d'un texte ecrit par un humain "
                   "competent",
        "regles": [
            "Supprimer les transitions mecaniques (« en conclusion », « par ailleurs »).",
            "Varier la longueur des phrases : alterner court et long.",
            "Remplacer les adverbes faibles par des verbes precis.",
            "Ne rien ajouter : seulement resserrer.",
        ],
        "role_modele": "standard", "temperature": 0.6, "emoji": "/",
    },
    "marketeur": {
        "metier": "un redacteur publicitaire qui vend par la preuve, jamais par "
                  "la pression",
        "mission": "formuler l'offre de facon que le bon acheteur se reconnaisse",
        "regles": [
            "Parler du resultat pour le lecteur, pas des caracteristiques du fichier.",
            "Dire aussi a qui le produit ne convient pas.",
            "Aucune fausse urgence, aucun faux temoignage.",
        ],
        "role_modele": "costaud", "temperature": 0.78, "emoji": "$",
    },
    "controleur": {
        "metier": "un responsable qualite qui valide ou refuse la mise en vente",
        "mission": "verifier qu'un produit est vendable sans exposer son vendeur",
        "regles": [
            "Verifier la coherence entre la promesse annoncee et le contenu livre.",
            "Signaler toute affirmation risquee sur le plan juridique ou sanitaire.",
            "Estimer honnetement si le produit vaut le prix envisage.",
        ],
        "role_modele": "costaud", "temperature": 0.3, "emoji": "v",
    },
}

# --------------------------------------------------------------------------
# Fragments de prompt reutilisables (surchargeables via atelier/prompts/*.txt)
# --------------------------------------------------------------------------

MODELES_DEFAUT: Dict[str, str] = {
    "interdits": (
        "- Jamais de formule creuse ni de tournure d'IA generique "
        "(« dans un monde ou », « il est important de noter »).\n"
        "- Jamais de statistique precise inventee ni de citation attribuee a une "
        "personne reelle.\n"
        "- Jamais de promesse de resultat garanti."
    ),
    "grille_qualite": (
        "Note chaque critere de 0 a 10, puis donne une note globale ponderee :\n"
        "1. UTILITE      le lecteur peut-il agir des la lecture ?\n"
        "2. DENSITE      chaque paragraphe apporte-t-il une information neuve ?\n"
        "3. CONCRETUDE   y a-t-il des exemples, des chiffres, des scripts ?\n"
        "4. STYLE        est-ce lisible, rythme, sans tic d'IA ?\n"
        "5. FIABILITE    y a-t-il des affirmations inverifiables ou risquees ?\n"
        "6. PROMESSE     le texte tient-il ce que son titre annonce ?"
    ),
    "signature_auteur": "",
}


def dossier() -> Path:
    return config.WORKDIR / "prompts"


_cache_agents: Optional[Dict[str, Dict[str, Any]]] = None
_cache_modeles: Optional[Dict[str, str]] = None


def agents(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """Personnalites d'agents, surchargees par atelier/prompts/agents.json."""
    global _cache_agents
    if _cache_agents is not None and not force:
        return _cache_agents

    fusion = {nom: dict(valeurs) for nom, valeurs in AGENTS_DEFAUT.items()}
    fichier = dossier() / "agents.json"
    if fichier.exists():
        try:
            surcharge = json.loads(fichier.read_text(encoding="utf-8"))
            if isinstance(surcharge, dict):
                for nom, valeurs in surcharge.items():
                    if nom in fusion and isinstance(valeurs, dict):
                        fusion[nom].update({
                            cle: valeur for cle, valeur in valeurs.items()
                            if cle in ("metier", "mission", "regles", "role_modele",
                                       "temperature", "emoji")
                        })
        except (ValueError, OSError):
            # Un prompt mal ecrit ne doit pas empecher de produire.
            pass
    _cache_agents = fusion
    return fusion


def modele(nom: str, defaut: str = "") -> str:
    """Fragment de prompt, surcharge par atelier/prompts/<nom>.txt."""
    global _cache_modeles
    if _cache_modeles is None:
        _cache_modeles = dict(MODELES_DEFAUT)
        repertoire = dossier()
        if repertoire.exists():
            for fichier in repertoire.glob("*.txt"):
                try:
                    _cache_modeles[fichier.stem] = fichier.read_text(encoding="utf-8")
                except OSError:
                    continue
    return _cache_modeles.get(nom, MODELES_DEFAUT.get(nom, defaut))


def exporter() -> List[Path]:
    """Ecrit les prompts par defaut sur le disque, pour edition."""
    repertoire = dossier()
    repertoire.mkdir(parents=True, exist_ok=True)
    ecrits: List[Path] = []

    fichier_agents = repertoire / "agents.json"
    fichier_agents.write_text(
        json.dumps(AGENTS_DEFAUT, ensure_ascii=False, indent=2), encoding="utf-8")
    ecrits.append(fichier_agents)

    for nom, contenu in MODELES_DEFAUT.items():
        chemin = repertoire / "{}.txt".format(nom)
        chemin.write_text(contenu, encoding="utf-8")
        ecrits.append(chemin)
    return ecrits


def personnalises() -> List[str]:
    """Liste ce qui differe des valeurs d'origine."""
    differences: List[str] = []
    actuels = agents(force=True)
    for nom, valeurs in actuels.items():
        if valeurs != AGENTS_DEFAUT.get(nom):
            differences.append("agent : " + nom)
    global _cache_modeles
    _cache_modeles = None
    for nom in MODELES_DEFAUT:
        if modele(nom) != MODELES_DEFAUT[nom]:
            differences.append("modele : " + nom)
    return differences


def oublier() -> None:
    global _cache_agents, _cache_modeles
    _cache_agents = None
    _cache_modeles = None
