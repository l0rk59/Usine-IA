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

from ..core import reglages, store
from . import apres, brief, catalogue, reprise
from .base import Contexte


def _entier(valeur: Any) -> int:
    """Un champ de formulaire vide vaut zero, pas une erreur."""
    try:
        return max(0, int(valeur or 0))
    except (TypeError, ValueError):
        return 0


def contexte(sujet: str, options: Dict[str, Any],
             journal: Callable[[str], None]) -> Contexte:
    """Les options d'abord, les reglages ensuite.

    Mesure du 24/09/2026 : la langue et la marque n'etaient pas lues. Reglee
    sur « anglais », l'usine ecrivait en francais depuis le tableau de bord
    et la boucle — zero invite sur sept demandait l'anglais, l'EPUB se
    declarait « fr » — et la marque n'apparaissait dans aucun fichier. La
    ligne de commande, elle, les lisait. Un test compare maintenant les deux
    constructeurs de contexte champ par champ, derive de la structure.
    """
    profil = reglages.charger()
    return Contexte(
        sujet=sujet,
        audience=options.get("audience") or profil["audience"],
        langue=options.get("langue") or profil["langue"],
        marque=options.get("marque") or profil["marque"],
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


def contexte_existant(produit_id: str, journal: Callable[[str], None],
                      **repli: Any) -> Contexte:
    """Le contexte d'un produit deja fabrique, pour agir dessus.

    Kit de vente, test A/B : ces actions reconstruisaient un contexte a partir
    des reglages, qui valent « auto ». Mesure du 23/09/2026 : chaque invite
    du kit de vente et du test A/B portait « TON : auto » — le produit avait
    pourtant une voix, decidee a sa fabrication et gardee depuis au carnet.

    Le carnet fait donc foi. « repli » sert aux produits d'avant lui et a un
    test A/B sur un titre libre ; le brief comble alors ce qui manque, sans
    rien redemander quand le carnet a deja repondu.
    """
    ctx = reprise.contexte_garde(produit_id, journal=journal) if produit_id else None
    if ctx is None:
        # Un produit d'avant le carnet a quand meme sa fiche, et sa langue y
        # est inscrite depuis toujours. Aucun appelant ne la passait en
        # repli : le kit de vente d'un livre anglais repartait dans la langue
        # par defaut du contexte — page de vente, extrait, mentions en
        # francais autour d'un texte anglais.
        fiche = store.lire_produit(produit_id) if produit_id else None
        if fiche and fiche.get("langue") and "langue" not in repli:
            repli["langue"] = fiche["langue"]
        ctx = Contexte(journal=journal, **repli)
    brief.appliquer(ctx, "produit")
    return ctx
