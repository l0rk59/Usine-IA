"""Ce qui suit la fabrication : kit de vente, extrait offert, archive.

POURQUOI CE MODULE EXISTE. Ces trois etapes vivaient dans « cli.py », dans une
fonction qui prenait les arguments d'argparse. Le tableau de bord, lui,
s'arretait a « catalogue.executer » — donc quatre reglages affiches et
enregistres par le tableau de bord n'avaient aucun effet quand on fabriquait
DEPUIS le tableau de bord.

Mesure du 15/09/2026, par le chemin du bouton, les quatre coches :

    relecture_ensemble   le LECTEUR a parle 0 fois
    marketing_auto       aucun kit de vente
    archive_auto         aucune archive ZIP
    extrait_offert       aucun extrait

Un reglage affiche, sauvegarde et jamais lu est un mensonge fait a
l'utilisateur — le depot avait deja trouve ce defaut une fois, sur
« plateforme » et « devise ». Il etait revenu, sur le chemin du TELEPHONE,
c'est-a-dire l'usage normal.

La correction n'est pas de recopier le code dans le serveur : deux copies
divergent, et c'est ainsi que la premiere avait vieilli. Elle est de poser le
travail ici et de le faire appeler par les deux.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core import reglages, store
from ..marketing import vente
from ..packaging import livraison


def veut(option: Optional[bool], cle_reglage: str) -> bool:
    """Le reglage decide, l'appelant tranche — dans les deux sens.

    « None » veut dire « je ne me prononce pas » : on applique alors ce qui a
    ete declare une fois pour toutes. Sans ce troisieme etat, un reglage actif
    ne pourrait plus jamais etre annule pour un seul produit, ou bien il ne
    pourrait jamais s'appliquer du tout — selon le sens du defaut choisi.
    """
    if option is None:
        return bool(reglages.lire(cle_reglage, False))
    return bool(option)


def pas_encore_vendable(fiche: Dict[str, Any]) -> str:
    """Pourquoi ce produit ne doit pas encore etre empaquete ni vendu — ou "".

    Inacheve, il contient des sections reduites a leur plan. Mesure du
    24/09/2026 : l'archive destinee a l'acheteur livrait un chapitre perdu
    sous la forme « Point A, Point B, Point C », dans le PDF, l'EPUB et le
    Markdown, et une page de vente promettait le livre entier. Le produit
    etait marque inacheve ; le paquet pret a mettre en ligne ne le disait
    nulle part. Les cinq chemins qui vendent ou empaquettent passent ici.
    """
    if (fiche or {}).get("statut") != "en_cours":
        return ""
    manquants = ((fiche.get("meta") or {}).get("manquants")) or []
    return ("produit inacheve{} — finissez-le d'abord : usine reprendre {}"
            .format(" ({} section(s) manquent)".format(len(manquants))
                    if manquants else "", fiche.get("id", "")))


def apres_production(
    ctx: Any,
    resume: Dict[str, Any],
    description: str,
    type_produit: str,
    *,
    kit: Optional[bool] = None,
    archive: Optional[bool] = None,
    plateforme: str = "",
    extrait: int = 0,
    contact: str = "",
    journal: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Kit de vente et archive, selon les reglages. Enrichit `resume`.

    Aucune de ces deux etapes ne doit pouvoir emporter un produit deja ecrit :
    elles sont un supplement, pas le produit. Une exception est donc dite et
    avalee — le livre existe sur le disque, il serait absurde de le perdre
    parce que sa fiche de vente n'a pas pu etre calculee.
    """
    dire = journal if callable(journal) else (lambda _m: None)
    dossier = Path(resume["dossier"])

    # Pas pour un produit inacheve (voir « pas_encore_vendable »). La
    # reprise refait les deux une fois le produit fini : c'est elle qui passe
    # ici ensuite.
    fiche = store.lire_produit(str(resume.get("produit_id") or "")) or {}
    if pas_encore_vendable(fiche) and (
            veut(kit, "marketing_auto") or veut(archive, "archive_auto")):
        manquants = (fiche.get("meta") or {}).get("manquants") or []
        dire("Kit de vente et archive : pas pour un produit inachevé{}. Ils "
             "seront faits quand il sera fini.".format(
                 " ({} section(s) manquent)".format(len(manquants))
                 if manquants else ""))
        return resume

    if veut(kit, "marketing_auto"):
        try:
            produit = vente.produire_kit(
                ctx, resume["titre"], description, dossier,
                plateforme=plateforme or str(reglages.lire("plateforme", "gumroad")),
                couverture=next(
                    (n for n in resume.get("fichiers", [])
                     if n.startswith("couverture")), ""),
                type_produit=type_produit,
                chapitres_offerts=(extrait
                                   or int(reglages.lire("extrait_offert", 0) or 0)),
            )
            resume["marketing"] = produit["fichiers"]
            if produit.get("extrait"):
                resume["extrait"] = produit["extrait"]
            prix = (produit["fiche"].get("prix_conseille") or {}).get("cible")
            dire("Kit de vente prêt ({} fichiers){}".format(
                len(produit["fichiers"]),
                " — prix conseille {} EUR".format(prix) if prix else ""))
        except Exception as exc:
            dire("Kit de vente non généré : {}".format(exc))

    if veut(archive, "archive_auto"):
        from .base import slug

        try:
            chemin = livraison.empaqueter(
                dossier, slug(resume["titre"], 46), resume["titre"], ctx.auteur,
                promesse=description[:200],
                contact=contact or str(reglages.lire("contact", "") or ""),
                # Ce que la chaine a declare livrer, et rien d'autre.
                livres=resume.get("fichiers"),
                langue=getattr(ctx, "langue_iso", "fr"),
            )
            resume["archive"] = str(chemin)
            dire("Archive : {} ({} Ko)".format(
                chemin.name, chemin.stat().st_size // 1024))
        except Exception as exc:
            dire("Archive non écrite : {}".format(exc))
    return resume
