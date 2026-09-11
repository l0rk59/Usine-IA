"""Profil et reglages persistants.

Evite de retaper --auteur, --marque, --ton a chaque commande. Stocke dans
atelier/reglages.json, modifiable a la main, par la CLI ou par le menu.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import config

DEFAUTS: Dict[str, Any] = {
    "auteur": "Usine-IA",
    "marque": "",
    "contact": "",
    "site": "",
    "langue": "francais",
    "ton": "pro",
    "taille": "standard",
    "audience": "un public francophone motive",
    "plateforme": "gumroad",
    "devise": "EUR",
    "images": True,
    "couverture": "atelier",       # atelier (composee localement) | ia
    "qualite": "standard",        # rapide | standard | exigeant
    "relectures": 1,              # passages de revision par l'agent editeur
    "theme": "nuit",              # nuit | jour
    "effets_3d": True,
    "jeton_web": "",              # protege le tableau de bord si renseigne
    "signature_ia": True,         # mentionne l'usage de l'IA dans la licence
    # --- budget de production continue (0 = pas de limite) ---
    "budget_appels_jour": 250,
    "budget_appels_produit": 80,
    "budget_produits_jour": 3,
    "budget_minutes_produit": 45,
    "pause_entre_produits": 60,   # secondes, laisse les quotas par minute respirer
}

DESCRIPTIONS: Dict[str, str] = {
    "auteur": "Nom affiche comme auteur sur vos produits",
    "marque": "Nom de votre marque ou de votre boutique",
    "contact": "Adresse e-mail de support, inscrite dans la notice",
    "site": "Adresse de votre site ou de votre boutique",
    "langue": "Langue de redaction",
    "ton": "Ton par defaut : expert, amical, pro, punchy, pedagogue",
    "taille": "Volume par defaut : mini, court, standard, long",
    "audience": "Audience par defaut",
    "plateforme": "Plateforme de vente visee : gumroad, etsy, payhip, site",
    "devise": "Devise des prix conseilles",
    "images": "Generer les couvertures et visuels (oui/non)",
    "qualite": "rapide (1 passe) | standard (relecture) | exigeant (2 relectures)",
    "relectures": "Nombre de passages de revision par l'agent editeur",
    "theme": "Theme du tableau de bord : nuit ou jour",
    "effets_3d": "Animations 3D du tableau de bord (desactivez sur vieux telephone)",
    "jeton_web": "Mot de passe du tableau de bord (vide = acces local libre)",
    "signature_ia": "Mentionner l'assistance IA dans la licence livree",
    "budget_appels_jour": "Appels IA maximum par jour en mode usine (0 = illimite)",
    "budget_appels_produit": "Appels IA maximum pour un seul produit",
    "budget_produits_jour": "Produits maximum fabriques par jour "
                            "(produire n'est pas publier : voir docs/VENDRE.md)",
    "budget_minutes_produit": "Duree maximum d'un produit, en minutes",
    "pause_entre_produits": "Pause entre deux produits, en secondes",
}

QUALITES = {
    "rapide": {"relectures": 0, "role_plan": "standard"},
    "standard": {"relectures": 1, "role_plan": "costaud"},
    "exigeant": {"relectures": 2, "role_plan": "costaud"},
}


def chemin() -> Path:
    return config.WORKDIR / "reglages.json"


_cache: Dict[str, Any] = {}


def charger(force: bool = False) -> Dict[str, Any]:
    global _cache
    if _cache and not force:
        return _cache
    valeurs = dict(DEFAUTS)
    fichier = chemin()
    if fichier.exists():
        try:
            enregistres = json.loads(fichier.read_text(encoding="utf-8"))
            if isinstance(enregistres, dict):
                valeurs.update({k: v for k, v in enregistres.items() if k in DEFAUTS})
        except (ValueError, OSError):
            pass  # fichier corrompu : on repart des defauts sans bloquer l'usine
    _cache = valeurs
    return valeurs


def lire(nom: str, defaut: Any = None) -> Any:
    return charger().get(nom, DEFAUTS.get(nom, defaut))


def ecrire(modifications: Dict[str, Any]) -> Dict[str, Any]:
    valeurs = charger()
    for nom, valeur in modifications.items():
        if nom not in DEFAUTS:
            continue
        valeurs[nom] = _convertir(nom, valeur)
    config.ensure_dirs()
    chemin().write_text(json.dumps(valeurs, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return valeurs


# Le ton et le volume acceptent du sur-mesure : « comme un vieux menuisier a
# son apprenti » et « 15 » sont des valeurs valides, que les chaines savent
# lire. La qualite, elle, est une liste fermee — « rapidos » ne veut rien dire
# pour personne et vaut silencieusement « standard » partout.
FERMES: Dict[str, Tuple[str, ...]] = {
    "qualite": tuple(QUALITES),
}


def _convertir(nom: str, valeur: Any) -> Any:
    modele = DEFAUTS[nom]
    if nom in FERMES:
        propre = str(valeur).strip().lower()
        return propre if propre in FERMES[nom] else modele
    if isinstance(modele, bool):
        if isinstance(valeur, bool):
            return valeur
        return str(valeur).strip().lower() in ("1", "oui", "true", "yes", "on", "o")
    if isinstance(modele, int) and not isinstance(modele, bool):
        try:
            return int(valeur)
        except (TypeError, ValueError):
            return modele
    return str(valeur).strip()


def reinitialiser() -> Dict[str, Any]:
    global _cache
    _cache = {}
    if chemin().exists():
        chemin().unlink()
    return charger(force=True)


def relectures_pour(qualite: str) -> int:
    return QUALITES.get(qualite, QUALITES["standard"])["relectures"]


def lignes_affichables() -> List[Dict[str, str]]:
    valeurs = charger()
    return [
        {
            "nom": nom,
            "valeur": "(non defini)" if valeurs.get(nom) in ("", None)
                      else str(valeurs.get(nom)),
            "description": DESCRIPTIONS.get(nom, ""),
        }
        for nom in DEFAUTS
    ]
