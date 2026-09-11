"""Assemblage des fichiers livrables, commun a tous les types de produits.

Chaque chaine de fabrication ecrivait son propre exportateur : couverture,
markdown, PDF avec page de titre et sommaire, HTML, CSV. Six variantes du meme
enchainement, avec les memes oublis a chaque fois.

Ce module fait le travail commun. Ce qui reste propre a un type — la mise en
page d'une fiche a remplir, un second document, un format de page particulier —
passe par des fonctions de rappel plutot que par des drapeaux. Une abstraction
qui se contorsionne pour couvrir tous les cas particuliers coute plus cher que
la duplication qu'elle remplace.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..core import images
from . import document as D
from .epub import construire_epub
from .page import ecrire_page
from .pdf import A4, DocumentPDF


@dataclass
class Bloc:
    """Une section du produit."""

    titre: str
    corps: str = ""                                   # markdown
    # Mise en page specifique : cases a cocher, grille, tableau... Quand elle
    # est fournie, elle remplace le rendu markdown dans le PDF.
    rendu_pdf: Optional[Callable[[DocumentPDF], None]] = None
    rendu_html: str = ""                              # sinon derive du markdown
    sommaire: bool = True


@dataclass
class Tableau:
    """Un tableau exporte en CSV, importable dans un tableur."""

    nom: str
    colonnes: List[str]
    lignes: List[List[str]] = field(default_factory=list)
    dossier: str = ""          # sous-dossier optionnel
    bom: bool = False          # utf-8-sig, requis par Notion et Excel


@dataclass
class Produit:
    """Ce qu'une chaine de fabrication remet a la livraison."""

    type: str
    titre: str
    sous_titre: str = ""
    promesse: str = ""
    blocs: List[Bloc] = field(default_factory=list)
    tableaux: List[Tableau] = field(default_factory=list)
    donnees: Dict[str, Any] = field(default_factory=dict)
    nom_donnees: str = ""                       # fichier JSON de travail
    formats: Tuple[str, ...] = ("md", "pdf", "html")
    police_corps: str = "Times-Roman"
    format_page: Tuple[float, float] = A4
    marge: float = 62.0
    style_couverture: str = ""
    nom_fichier: str = ""
    # Suffixe du PDF principal quand le produit en compte plusieurs : le
    # manuel d'une formation s'appelle « ...-manuel », mais son cahier
    # d'exercices part du meme nom de base, pas du nom du manuel.
    suffixe_pdf: str = ""
    langue: str = "fr"
    # « 8 chapitres » est plus juste que « 8 sections » pour un ebook : chaque
    # type garde son vocabulaire plutot que d'heriter d'un terme generique.
    libelle_sections: str = "section(s)"
    # Documents supplementaires : cahier d'exercices, second format de page.
    documents: List[Tuple[str, Callable[[Optional[bytes]], DocumentPDF]]] = \
        field(default_factory=list)

    def base(self) -> str:
        from ..pipelines.base import slug

        return self.nom_fichier or slug(self.titre, 46)


def livrer(ctx: Any, produit: Produit) -> List[Path]:
    """Ecrit tous les fichiers du produit. Renvoie ceux qui ont ete crees."""
    dossier: Path = ctx.dossier
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: List[Path] = []
    formats = set(produit.formats)
    base = produit.base()

    # --- couverture (avant le PDF, qui peut l'incorporer) -----------------
    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, produit.titre, produit.sous_titre, ctx.auteur,
            style=produit.style_couverture or produit.type,
            en_ligne=not ctx.hors_ligne)
        fichiers.append(couverture)
    octets_jpeg = (couverture.read_bytes()
                   if couverture and couverture.suffix.lower() in (".jpg", ".jpeg")
                   else None)

    blocs_analyses = [(b, D.analyser(b.corps) if b.corps else []) for b in produit.blocs]
    # Un bloc qui n'a qu'une mise en page PDF est PDF par nature : l'inscrire
    # dans le markdown ou le HTML y laisserait un titre sans contenu.
    blocs_texte = [(b, m) for b, m in blocs_analyses if b.corps or b.rendu_html]

    # --- markdown ---------------------------------------------------------
    if "md" in formats:
        morceaux = ["# {}".format(produit.titre)]
        if produit.sous_titre:
            morceaux.append("*{}*".format(produit.sous_titre))
        morceaux.append("\n_{}_\n".format(ctx.auteur))
        for bloc, _ in blocs_texte:
            morceaux.append("\n# {}\n".format(bloc.titre))
            morceaux.append(bloc.corps)
        chemin = dossier / "{}.md".format(_nom_markdown(produit.type))
        chemin.write_text("\n".join(morceaux).strip() + "\n", encoding="utf-8")
        fichiers.append(chemin)

    # --- PDF --------------------------------------------------------------
    if "pdf" in formats:
        doc = _document(produit, ctx, octets_jpeg)
        for bloc, blocs_md in blocs_analyses:
            doc.titre(bloc.titre, 1, sommaire=bloc.sommaire)
            if bloc.rendu_pdf is not None:
                bloc.rendu_pdf(doc)
            elif blocs_md:
                D.vers_pdf(blocs_md, doc, sauter_h1=True)
        doc.inserer_sommaire(apres=1)
        chemin = dossier / "{}{}.pdf".format(base, produit.suffixe_pdf)
        doc.enregistrer(chemin)
        fichiers.append(chemin)

    # --- documents supplementaires ----------------------------------------
    for suffixe, constructeur in produit.documents:
        doc = constructeur(octets_jpeg)
        chemin = dossier / "{}-{}.pdf".format(base, suffixe)
        doc.enregistrer(chemin)
        fichiers.append(chemin)

    # --- EPUB --------------------------------------------------------------
    if "epub" in formats:
        image = (couverture.name, couverture.read_bytes()) if (
            couverture and couverture.suffix.lower() in (".jpg", ".jpeg", ".png")
        ) else None
        chemin = dossier / "{}.epub".format(base)
        construire_epub(
            chemin, produit.titre, ctx.auteur,
            [(bloc.titre, bloc.rendu_html or D.vers_html(blocs_md, niveau_depart=2))
             for bloc, blocs_md in blocs_texte],
            langue=produit.langue, sous_titre=produit.sous_titre,
            description=produit.promesse, couverture=image)
        fichiers.append(chemin)

    # --- HTML ---------------------------------------------------------------
    if "html" in formats:
        corps = []
        for bloc, blocs_md in blocs_texte:
            corps.append("<h2>{}</h2>".format(D.inline_html(bloc.titre)))
            corps.append(bloc.rendu_html or D.vers_html(blocs_md, niveau_depart=3))
        chemin = dossier / "lire.html"
        ecrire_page(chemin, produit.titre, "\n".join(corps),
                    sous_titre=produit.sous_titre,
                    meta="{} — {} {}".format(ctx.auteur, len(blocs_texte),
                                             produit.libelle_sections),
                    couverture=couverture.name if couverture else None)
        fichiers.append(chemin)

    # --- texte brut ----------------------------------------------------------
    if "txt" in formats:
        chemin = dossier / "{}.txt".format(_nom_markdown(produit.type))
        chemin.write_text(
            "\n\n".join(
                "{}\n{}\n\n{}".format(bloc.titre.upper(), "=" * len(bloc.titre),
                                      D.vers_texte(blocs_md))
                for bloc, blocs_md in blocs_texte),
            encoding="utf-8")
        fichiers.append(chemin)

    # --- tableaux CSV ---------------------------------------------------------
    for tableau in produit.tableaux:
        cible = dossier / tableau.dossier if tableau.dossier else dossier
        cible.mkdir(parents=True, exist_ok=True)
        chemin = cible / "{}.csv".format(tableau.nom)
        encodage = "utf-8-sig" if tableau.bom else "utf-8"
        with chemin.open("w", encoding=encodage, newline="") as flux:
            auteur = csv.writer(flux)
            auteur.writerow(tableau.colonnes)
            auteur.writerows(tableau.lignes)
        fichiers.append(chemin)

    # --- donnees de travail ----------------------------------------------------
    if produit.donnees and produit.nom_donnees:
        chemin = dossier / "{}.json".format(produit.nom_donnees)
        chemin.write_text(json.dumps(produit.donnees, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        fichiers.append(chemin)

    return fichiers


def _document(produit: Produit, ctx: Any,
              octets_jpeg: Optional[bytes]) -> DocumentPDF:
    doc = DocumentPDF(format_page=produit.format_page, marge=produit.marge,
                      titre_courant=produit.titre,
                      police_corps=produit.police_corps)
    doc.page_couverture(produit.titre, produit.sous_titre, ctx.auteur,
                        image_jpeg=octets_jpeg)
    return doc


def _nom_markdown(type_produit: str) -> str:
    """Nom historique du fichier markdown, conserve par type."""
    return {
        "ebook": "livre",
        "formation": "formation",
        "prompts": "prompts",
        "outils": "boite-outils",
        "modeles": "modeles",
        "social": "posts",
    }.get(type_produit, type_produit)


def bloc_markdown(titre: str, corps: str) -> Bloc:
    return Bloc(titre=titre, corps=corps)


def blocs_depuis_sections(sections: Sequence[Tuple[str, str]]) -> List[Bloc]:
    return [Bloc(titre=titre, corps=corps) for titre, corps in sections]
