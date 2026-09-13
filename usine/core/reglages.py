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
    # « auto » : l'usine decide en lisant le sujet. Un reglage par defaut
    # n'est pas neutre, il est juste invisible — « pro / standard / un public
    # francophone motive » donnait la meme voix, la meme longueur et la meme
    # audience imaginaire a un guide de fiscalite et a un carnet de recettes.
    # Ces trois-la restent modifiables : y mettre une valeur la rend
    # definitive, et le brief ne la touche plus.
    "ton": "auto",
    "taille": "auto",
    "audience": "auto",
    "plateforme": "gumroad",
    "devise": "EUR",
    # Ce qu'on demandait en option a CHAQUE commande, faute de pouvoir le
    # declarer une fois. Un vendeur qui empaquette toujours ses produits
    # retapait « --zip » cent fois ; celui qui ne le fait jamais n'avait pas
    # a le voir.
    "marketing_auto": False,      # produire le kit de vente sans le demander
    "archive_auto": False,        # ecrire l'archive ZIP livrable
    "relecture_ensemble": False,  # une lecture du produit entier, en plus
    "extrait_offert": 0,          # chapitres offerts en edition gratuite
    "images": True,
    "couverture": "atelier",       # atelier (composee localement) | ia
    "qualite": "standard",        # rapide | standard | exigeant
    "theme": "nuit",              # nuit | jour
    "effets_3d": True,
    "jeton_web": "",              # protege le tableau de bord si renseigne
    "signature_ia": True,         # mentionne l'usage de l'IA dans la licence
    # --- budget de production continue (0 = pas de limite) ---
    "budget_appels_jour": 250,
    "budget_appels_produit": 80,
    "budget_produits_jour": 3,
    "budget_minutes_produit": 45,
    # 0 : pas de plafond en jetons. Plusieurs paliers gratuits comptent ainsi
    # plutot qu'en requetes — Cerebras et Gemini, notamment.
    "budget_jetons_jour": 0,
    "pause_entre_produits": 60,   # secondes, laisse les quotas par minute respirer
    # --- le telephone comme machine (termux-api, tout est facultatif) ---
    "notifications": True,        # notification Android quand un produit sort
    "batterie_minimum": 20,       # % sous lequel l'usine continue s'arrete (0 = jamais)
    "verrou_veille": True,        # empeche Android d'endormir une fabrication
}

DESCRIPTIONS: Dict[str, str] = {
    "auteur": "Nom affiche comme auteur sur vos produits",
    "marque": "Nom de votre marque ou de votre boutique",
    "contact": "Adresse e-mail de support, inscrite dans la notice",
    "site": "Adresse de votre site ou de votre boutique",
    "langue": "Langue de redaction",
    "ton": "Ton par defaut : auto (l'usine lit le sujet), expert, amical, "
           "pro, punchy, pedagogue, ou une description libre",
    "taille": "Volume par defaut : auto, mini, court, standard, long",
    "audience": "Audience par defaut : auto (deduite du sujet), ou une "
                "description precise (metier, niveau, situation)",
    "plateforme": "Plateforme de vente visee : gumroad, etsy, payhip, site",
    "couverture": "Couverture : atelier (composee ici, gratuite) ou ia (generee)",
    "marketing_auto": "Produire le kit de vente a chaque produit, sans le demander",
    "archive_auto": "Ecrire l'archive ZIP livrable a chaque produit",
    "relecture_ensemble": "Relire le produit ENTIER a la recherche des "
                          "contradictions (un appel de plus par produit)",
    "extrait_offert": "Chapitres offerts dans une edition gratuite (0 = aucune)",
    "devise": "Devise des prix conseilles",
    "images": "Generer les couvertures et visuels (oui/non)",
    "qualite": "rapide (1 passe) | standard (relecture) | exigeant (2 relectures)",
    "theme": "Theme du tableau de bord : nuit ou jour",
    "effets_3d": "Animations 3D du tableau de bord (desactivez sur vieux telephone)",
    "jeton_web": "Mot de passe du tableau de bord (vide = acces local libre)",
    "signature_ia": "Mentionner l'assistance IA dans la licence livree",
    "budget_appels_jour": "Appels IA maximum par jour en mode usine (0 = illimite)",
    "budget_appels_produit": "Appels IA maximum pour un seul produit",
    "budget_produits_jour": "Produits maximum fabriques par jour "
                            "(produire n'est pas publier : voir docs/VENDRE.md)",
    "budget_minutes_produit": "Duree maximum d'un produit, en minutes",
    "budget_jetons_jour": "Jetons IA maximum par jour, tous fournisseurs "
                          "confondus (0 = illimite)",
    "pause_entre_produits": "Pause entre deux produits, en secondes",
    "notifications": "Notification Android quand un produit est pret "
                     "(demande termux-api)",
    "batterie_minimum": "Niveau de batterie sous lequel l'usine continue "
                        "s'arrete, en % (0 = jamais)",
    "verrou_veille": "Empecher Android d'endormir le telephone pendant une "
                     "fabrication",
}

# Les peaux du tableau de bord. Declarees ici, et nulle part ailleurs : la
# CLI, le menu et la page les lisent toutes les trois. Une liste recopiee dans
# le CSS et une autre dans le menu finiraient par ne plus proposer les memes.
#
# « nuit » et « jour » sont les deux peaux d'origine. Les quatre autres ne
# changent pas que les couleurs — c'est le point : une peau qui ne change que
# la teinte ne sert qu'a soi-meme, alors qu'un ecran de telephone au soleil,
# un vieil appareil qui rame et un lecteur d'ecran demandent trois interfaces
# differentes.
THEMES: List[Dict[str, Any]] = [
    {"cle": "nuit", "nom": "Nuit",
     "description": "Cyberpunk sombre : neon sur noir, grille en fuite.",
     "anime": True, "police": "sans"},
    {"cle": "jour", "nom": "Jour",
     "description": "Le meme, en clair. Lisible dehors.",
     "anime": True, "police": "sans"},
    {"cle": "papier", "nom": "Papier",
     "description": "Atelier d'edition : serif sur creme, aucune animation, "
                    "tout au calme. Pour travailler longtemps.",
     "anime": False, "police": "serif"},
    {"cle": "console", "nom": "Console",
     "description": "Terminal : tout en chasse fixe, dense, sans arrondi. "
                    "La meme peau que Termux.",
     "anime": False, "police": "mono"},
    {"cle": "ambre", "nom": "Ambre",
     "description": "Ecran monochrome ambre, comme un terminal de 1981.",
     "anime": True, "police": "mono"},
    {"cle": "contraste", "nom": "Contraste",
     "description": "Noir et blanc francs, texte plus grand, aucune "
                    "animation. Pour voir de loin ou voir mal.",
     "anime": False, "police": "sans"},
]

THEMES_PAR_CLE: Dict[str, Dict[str, Any]] = {t["cle"]: t for t in THEMES}


def theme(cle: str = "") -> Dict[str, Any]:
    """La fiche d'un theme, ou celle de « nuit » si le nom est inconnu.

    Un theme inconnu ne doit pas rendre la page illisible : un reglage
    recopie a la main, ou une peau retiree entre deux versions, se rattrape
    ici plutot que de laisser une page sans couleurs.
    """
    return THEMES_PAR_CLE.get(cle or lire("theme", "nuit"), THEMES_PAR_CLE["nuit"])


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
    # Un theme tape a la main qui n'existe pas laissait la page sans
    # couleurs : le navigateur ne trouve aucune regle et affiche du noir sur
    # du noir. Liste fermee, donc, et le champ devient une liste deroulante.
    "theme": tuple(t["cle"] for t in THEMES),
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


# Les reglages, ranges par ce qu'ils decident. Vingt-six reglages a plat
# etaient illisibles partout — et surtout dans le tableau de bord, qui n'en
# montrait que huit : les dix-huit autres n'existaient que dans un fichier
# JSON que personne n'ouvre. Le critere de regroupement est la QUESTION a
# laquelle le reglage repond, pas le module qui le lit.
GROUPES: List[Dict[str, Any]] = [
    {"cle": "identite", "titre": "Qui vend",
     "aide": "Ce qui apparait sur vos produits et dans la notice de l'acheteur.",
     "reglages": ["auteur", "marque", "contact", "site", "signature_ia"]},
    {"cle": "fabrication", "titre": "Comment l'usine ecrit",
     "aide": "« auto » laisse l'usine decider en lisant le sujet.",
     "reglages": ["langue", "ton", "taille", "audience", "qualite",
                  "relecture_ensemble", "images", "couverture"]},
    {"cle": "vente", "titre": "Ce qui part avec le produit",
     "aide": "Produit a chaque fabrication, sans avoir a le demander.",
     "reglages": ["plateforme", "devise", "marketing_auto", "archive_auto",
                  "extrait_offert"]},
    {"cle": "budget", "titre": "Ce que l'usine a le droit de depenser",
     "aide": "Zero veut dire : pas de plafond. Ces limites arretent l'usine "
             "continue, pas une fabrication lancee a la main.",
     "reglages": ["budget_appels_jour", "budget_appels_produit",
                  "budget_produits_jour", "budget_minutes_produit",
                  "budget_jetons_jour", "pause_entre_produits"]},
    {"cle": "telephone", "titre": "Le telephone",
     "aide": "Tout est facultatif et demande termux-api.",
     "reglages": ["notifications", "batterie_minimum", "verrou_veille"]},
    {"cle": "interface", "titre": "L'affichage",
     "aide": "Le tableau de bord et le menu.",
     "reglages": ["theme", "effets_3d", "jeton_web"]},
]

# Ce qui ne se change PAS depuis le navigateur. « jeton_web » est le mot de
# passe qui protege ce navigateur-la : le laisser modifier depuis la page
# qu'il garde permettrait de s'y enfermer, ou d'en sortir.
HORS_WEB = frozenset({"jeton_web"})


def non_groupes() -> List[str]:
    """Les reglages qu'aucun groupe ne montre.

    Un reglage hors groupe est INVISIBLE dans les interfaces qui affichent
    par groupe — c'est-a-dire un reglage sauvegarde, lu par le code, et que
    personne ne peut changer. Un test garde ce point.
    """
    places = {nom for groupe in GROUPES for nom in groupe["reglages"]}
    return [nom for nom in DEFAUTS if nom not in places]


def lignes_affichables() -> List[Dict[str, str]]:
    """Les reglages a montrer, DANS L'ORDRE DES GROUPES.

    L'ordre compte : c'est lui qui donne leur numero dans le menu. Le laisser
    suivre l'ordre de declaration pendant que le menu affichait par groupe
    ferait pointer chaque numero sur un autre reglage — l'utilisateur croirait
    changer le ton et changerait la devise.
    """
    valeurs = charger()
    lignes = []
    for groupe in GROUPES:
        for nom in groupe["reglages"]:
            lignes.append({
                "nom": nom,
                "groupe": groupe["cle"],
                "titre_groupe": groupe["titre"],
                "aide_groupe": groupe["aide"],
                "valeur": "(non defini)" if valeurs.get(nom) in ("", None)
                          else str(valeurs.get(nom)),
                "description": DESCRIPTIONS.get(nom, ""),
            })
    return lignes
