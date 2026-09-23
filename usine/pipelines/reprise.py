"""Finir un produit interrompu, quelle que soit la porte par laquelle il est entre.

Trois portes fabriquent : la ligne de commande, le tableau de bord et l'usine
continue. La reprise ne savait rejouer que la premiere, parce qu'elle rejouait
une LIGNE DE COMMANDE — et les deux autres n'en ont pas. Voir
« carnet.noter_fabrication » pour la mesure.

Ce module n'a qu'une regle : ce qui a ete decide a la premiere fabrication
fait foi. Le sujet, le public, le ton, le volume, la promesse de lecture, les
reglages du type sont relus du carnet ; rien n'est redemande au modele. Un
reglage redecide a la reprise donnerait a la seconde moitie du livre une autre
voix que la premiere, et le lecteur, lui, le verrait.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core import config, store, verrou
from . import apres, carnet, catalogue
from .base import Contexte, depuis_instantane


class DejaEnReprise(RuntimeError):
    """Un autre fil ou un autre processus finit deja ce produit."""


def dossier_de(produit_id: str) -> Path:
    produit = store.lire_produit(produit_id) or {}
    return Path(produit.get("dossier") or config.PRODUITS_DIR / produit_id)


def contexte_garde(produit_id: str,
                   journal: Callable[[str], None] = print) -> Optional[Contexte]:
    """Le contexte de la premiere fabrication, pret a reprendre — ou None.

    None pour un produit fabrique avant que le carnet ne garde son contexte :
    l'appelant retombe alors sur l'ancienne voie, les arguments de la commande.
    """
    dossier = dossier_de(produit_id)
    photo = carnet.contexte_garde(dossier)
    if photo is None:
        return None
    ctx = depuis_instantane(photo, journal=journal)
    ctx.produit_id = produit_id
    ctx.dossier = dossier
    return ctx


def par_le_catalogue(produit_id: str) -> bool:
    """Ce produit se reprend-il sans ligne de commande ?"""
    dossier = dossier_de(produit_id)
    return (carnet.relance(dossier) is not None
            and carnet.contexte_garde(dossier) is not None)


def reprendre(produit_id: str,
              journal: Callable[[str], None] = print) -> Dict[str, Any]:
    """Refait les sections manquantes, par le catalogue, et rend le resume.

    Le kit de vente et l'archive suivent, comme apres une premiere
    fabrication : un produit fini en deux fois doit sortir avec les memes
    pieces qu'un produit fini d'un trait.
    """
    dossier = dossier_de(produit_id)
    recette = carnet.relance(dossier)
    ctx = contexte_garde(produit_id, journal=journal)
    if recette is None or ctx is None:
        raise ValueError("ce produit n'a pas garde de quoi etre repris sans "
                         "sa ligne de commande")
    options: Dict[str, Any] = dict(recette.get("options") or {})
    type_produit = str(recette["type"])
    # Une reprise a la fois par produit. Vu le 23/09/2026, dans la suite de
    # tests : la boucle a qui le tableau de bord confie un produit coupe, et
    # une reprise manuelle lancee entre-temps, ecrivaient le meme carnet en
    # meme temps. L'un deplacait « carnet.json.tmp » sous les pieds de
    # l'autre, qui mourait sur « No such file ».
    garde = Path(dossier) / ".reprise.pid"
    if not verrou.prendre(garde):
        raise DejaEnReprise("ce produit est deja en train d'etre fini "
                            "(processus {})".format(verrou.detenteur(garde)))
    try:
        resultat = catalogue.executer(type_produit, ctx, options)
        return apres.apres_production(
            ctx, resultat, str(resultat.get("promesse") or ctx.sujet),
            type_produit=type_produit,
            kit=options.get("marketing"), archive=options.get("zip"),
            journal=journal)
    finally:
        garde.unlink(missing_ok=True)
