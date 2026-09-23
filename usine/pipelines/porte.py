"""Fabriquer sans ligne de commande : le tableau de bord et l'usine continue.

Ces deux portes recoivent la meme chose — un type, un sujet, un dictionnaire
d'options — et fabriquaient chacune a sa facon. Mesure du 23/09/2026, memes
reglages actives des deux cotes :

    reglage                 tableau de bord    usine continue
    relecture_ensemble            1                  0
    archive_auto                  1                  0
    marketing_auto                1                  0

Trois reglages decrits « a chaque produit » ne s'appliquaient pas dans la
boucle, c'est-a-dire precisement la ou l'on fabrique sans surveiller. Et la
boucle ignorait aussi les chapitres, les mots et l'auteur passes en options.

Rien de ce qui suit n'est nouveau : c'est ce que faisait le tableau de bord,
sorti de son fichier pour que la boucle fasse pareil. La ligne de commande
garde son propre chemin, parce qu'elle a des arguments a lire ; elle passe par
« brief.completer » et « apres.apres_production », comme ici.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..core import reglages
from . import apres, brief, catalogue
from .base import Contexte


def _entier(valeur: Any) -> int:
    """Un champ de formulaire vide vaut zero, pas une erreur."""
    try:
        return max(0, int(valeur or 0))
    except (TypeError, ValueError):
        return 0


def contexte(sujet: str, options: Dict[str, Any],
             journal: Callable[[str], None]) -> Contexte:
    """Les options d'abord, les reglages ensuite."""
    profil = reglages.charger()
    return Contexte(
        sujet=sujet,
        audience=options.get("audience") or profil["audience"],
        ton=options.get("ton") or profil["ton"],
        taille=options.get("taille") or profil["taille"],
        qualite=options.get("qualite") or profil["qualite"],
        chapitres=_entier(options.get("chapitres")),
        mots_section=_entier(options.get("mots")),
        auteur=options.get("auteur") or profil["auteur"],
        sans_image=bool(options.get("sans_image")) or not profil["images"],
        journal=journal,
    )


def fabriquer(type_produit: str, ctx: Contexte, options: Dict[str, Any],
              journal: Callable[[str], None]) -> Dict[str, Any]:
    """Brief, fabrication, puis kit de vente et archive selon les reglages."""
    profil = reglages.charger()
    # Les reglages de fabrication que la chaine prend en OPTION. Le tableau
    # de bord les affichait, les enregistrait, et ne les passait pas : coche,
    # « relecture_ensemble » ne faisait rien, et l'agent LECTEUR — celui qui
    # lit le produit comme l'acheteur — n'a jamais parle une seule fois quand
    # on fabrique depuis le telephone.
    for cle in ("relecture_ensemble",):
        if options.get(cle) is None and profil.get(cle):
            options[cle] = profil[cle]
    # La meme preparation que la ligne de commande. Sans elle, le bouton
    # « Generer » et la boucle envoyaient « TON : auto » et « PUBLIC : auto »
    # dans chacune des invites.
    brief.completer(ctx, type_produit, options)
    resultat = catalogue.executer(type_produit, ctx, options)
    return apres.apres_production(
        ctx, resultat, str(resultat.get("promesse") or ctx.sujet),
        type_produit=type_produit,
        kit=options.get("marketing"), archive=options.get("zip"),
        journal=journal)
