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
from . import tableur
from . import document as D
from .epub import construire_epub
from .epub_conformite import verifier_epub
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
    # Le titre du bloc est ecrit par le moteur, en corps de chapitre. Un album
    # jeunesse n'en veut pas : « Page 1 » en vingt-quatre points au-dessus
    # d'une seule phrase, c'est la mise en page d'un guide appliquee a un
    # album. Quand ce drapeau est baisse, « rendu_pdf » ouvre sa page et
    # compose tout — titre compris s'il en veut un.
    titre_pdf: bool = True


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
    # Marge de reliure, en points. Utile pour l'impression a la demande d'un
    # document broche ; inutile — et genante — pour une impression a domicile.
    reliure: float = 0.0
    style_couverture: str = ""
    nom_fichier: str = ""
    # Suffixe du PDF principal quand le produit en compte plusieurs : le
    # manuel d'une formation s'appelle « ...-manuel », mais son cahier
    # d'exercices part du meme nom de base, pas du nom du manuel.
    suffixe_pdf: str = ""
    # Vide par defaut : la langue vient du contexte de production. Une valeur
    # en dur ici annoncait « fr » dans les metadonnees de TOUS les produits,
    # y compris ceux rediges dans une autre langue.
    langue: str = ""
    # « 8 chapitres » est plus juste que « 8 sections » pour un ebook : chaque
    # type garde son vocabulaire plutot que d'heriter d'un terme generique.
    libelle_sections: str = "section(s)"
    # Un sommaire coute une page pleine. Il la vaut dans un livre, ou l'on
    # cherche le chapitre neuf ; pas dans une fiche qu'on parcourt d'un coup
    # d'oeil. Mesure du 15/09/2026 sur les produits reellement fabriques :
    #
    #     social   4 pages, dont 1 de sommaire — un quart du document
    #     quiz     5 pages, sommaire de trois entrees : Consignes,
    #              Questions, Corrige. On les trouve en tournant la page.
    #     memo     6 pages, alors que ce type se veut « une ou deux pages »
    #
    # C'est la chaine qui declare, parce qu'elle seule sait si son produit est
    # un livre ou une carte. Un seuil en nombre de pages serait un chiffre
    # invente, et il se tromperait sur un ebook court comme sur un memo long.
    sommaire: bool = True
    # Les sections s'ENCHAINENT au lieu d'ouvrir chacune leur page.
    #
    # Un titre de niveau 1 ouvre une page neuve, et c'est juste dans un livre :
    # un chapitre commence en haut d'une page. Ce ne l'est pas dans une
    # documentation qu'on lit a l'ecran. Mesure du 15/09/2026 sur la notice
    # d'un outil logiciel : trois sections, trois pages, et les deux tiers
    # bas de chacune blancs — cinq pages dont trois quasi vides.
    #
    # Ce qui n'est PAS un defaut, et que la meme mesure signale : un episode
    # de feuilleton qui se termine par « A suivre » au milieu de la page. Un
    # chapitre finit ou il finit. La mesure compte le blanc ; elle ne dit pas
    # s'il est de trop.
    sections_enchainees: bool = False
    # Refabriquer un produit deja livre doit lui rendre SA couverture. Celle
    # d'un modele d'images ne se reproduit pas a l'identique : regenerer, ce
    # serait livrer a un acheteur un livre dont la couverture a change depuis
    # qu'il l'a vu. Le drapeau n'est leve que par une refabrication.
    reutiliser_couverture: bool = False
    # Fichiers du dossier produit a embarquer dans l'EPUB, chemins relatifs
    # (« images/page-01.jpg »). Un EPUB est une archive fermee : une image
    # referencee mais absente du conteneur ne s'affiche pas chez le lecteur,
    # et le distributeur refuse le fichier.
    ressources: Tuple[str, ...] = ()
    # Documents supplementaires : cahier d'exercices, second format de page.
    documents: List[Tuple[str, Callable[[Optional[Tuple[str, Any]]],
                                        DocumentPDF]]] = \
        field(default_factory=list)

    def base(self) -> str:
        from ..pipelines.base import slug

        return self.nom_fichier or slug(self.titre, 46)


def _mentions_droits(langue: str = "fr") -> List[str]:
    """Lignes ajoutees a la page de copyright de l'EPUB.

    La mention d'assistance IA suit le meme reglage que celle de la licence
    livree : deux endroits ou l'utilisateur l'attendrait ne doivent pas
    repondre differemment a la meme case a cocher.
    """
    from ..core import reglages
    from . import libelles

    return ([libelles.libelle(langue, "mention_ia_courte")]
            if reglages.lire("signature_ia", True) else [])


def _couverture_existante(dossier: Path) -> Optional[Path]:
    """La couverture deja ecrite dans ce dossier, si elle y est."""
    for extension in (".jpg", ".jpeg", ".png"):
        chemin = dossier / "couverture{}".format(extension)
        if chemin.exists():
            return chemin
    return None


def livrer(ctx: Any, produit: Produit) -> List[Path]:
    """Ecrit tous les fichiers du produit. Renvoie ceux qui ont ete crees."""
    # Le titre et le sous-titre partent partout : couverture, page, PDF, et
    # les metadonnees de l'EPUB que lisent les boutiques. Un sous-titre venu
    # du modele avec son « **gras** » s'y retrouvait en clair (mesure du
    # 24/09/2026 : la page de trois types sur dix-huit). Nettoyes ici, une
    # fois, pour tous les formats.
    produit.titre = D.nettoyer_inline(produit.titre)
    produit.sous_titre = D.nettoyer_inline(produit.sous_titre)
    dossier: Path = ctx.dossier
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: List[Path] = []
    formats = set(produit.formats)
    base = produit.base()
    langue = produit.langue or getattr(ctx, "langue_iso", "fr")

    # --- couverture (avant le PDF, qui peut l'incorporer) -----------------
    couverture = None
    page_couverture = None
    deja_la = _couverture_existante(dossier) if produit.reutiliser_couverture else None
    if deja_la is not None:
        couverture = deja_la
    elif not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, produit.titre, produit.sous_titre, ctx.auteur,
            style=produit.style_couverture or produit.type,
            en_ligne=not ctx.hors_ligne,
            marque=getattr(ctx, "marque", "") or "")
    if couverture is not None:
        fichiers.append(couverture)
        svg = couverture.with_suffix(".svg")
        if svg.exists():
            fichiers.append(svg)
        if couverture.suffix.lower() in (".jpg", ".jpeg"):
            # Illustration IA : le PDF garde sa vignette centree.
            page_couverture = ("jpeg", couverture.read_bytes())
        else:
            # Couverture d'atelier : elle porte deja son titre, donc elle
            # prend la page entiere au lieu d'etre repetee en vignette.
            page_couverture = ("rvb", images.couverture_pleine_page(
                produit.titre, produit.sous_titre, ctx.auteur,
                getattr(ctx, "marque", "") or "",
                largeur=int(produit.format_page[0] * 1.28),
                hauteur=int(produit.format_page[1] * 1.28)))

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
        doc = _document(produit, ctx, page_couverture)
        for rang, (bloc, blocs_analysees) in enumerate(blocs_analyses):
            if bloc.titre_pdf:
                if produit.sections_enchainees:
                    # La premiere ouvre une page — sinon le texte se dessine
                    # par-dessus la couverture. Le memo l'a appris : le PDF
                    # tombait a une page, le compte semblait parfait, et le
                    # contenu etait imprime sur la couverture.
                    if rang == 0:
                        doc.nouvelle_page()
                    doc.titre(bloc.titre, 2, sommaire=bloc.sommaire)
                else:
                    doc.titre(bloc.titre, 1, sommaire=bloc.sommaire)
            if bloc.rendu_pdf is not None:
                bloc.rendu_pdf(doc)
            elif blocs_analysees:
                D.vers_pdf(blocs_analysees, doc, sauter_h1=True)
        # Un sommaire vide ne s'omettait pas : il sortait une page « Sommaire »
        # avec son filet bleu et rien dessous. Personne ne l'avait vu parce
        # qu'aucun produit n'avait, jusqu'au conte, de blocs sans titre PDF.
        if doc.sommaire and produit.sommaire:
            from . import libelles

            doc.inserer_sommaire(libelles.libelle(langue, "sommaire"), apres=1)
        chemin = dossier / "{}{}.pdf".format(base, produit.suffixe_pdf)
        doc.enregistrer(chemin)
        fichiers.append(chemin)

    # --- documents supplementaires ----------------------------------------
    for suffixe, constructeur in produit.documents:
        doc = constructeur(page_couverture)
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
            langue=langue, sous_titre=produit.sous_titre,
            description=produit.promesse, couverture=image,
            editeur=getattr(ctx, "marque", "") or "",
            mentions=_mentions_droits(langue),
            dedicace=getattr(ctx, "dedicace", "") or "",
            ressources=[(nom, (dossier / nom).read_bytes())
                        for nom in produit.ressources
                        if (dossier / nom).is_file()])
        # Un EPUB casse ne se voit pas : l'archive s'ouvre, le fichier part
        # chez le distributeur, et c'est lui qui le refuse. Le controle est
        # instantane et sans reseau — il n'y a aucune raison de le sauter.
        rapport = verifier_epub(chemin)
        ctx.meta["epub"] = rapport.en_donnees()
        if not rapport.conforme:
            ctx.journal("EPUB : {}".format(rapport.resume()))
        fichiers.append(chemin)

    # --- HTML ---------------------------------------------------------------
    if "html" in formats:
        corps = []
        for bloc, blocs_md in blocs_texte:
            corps.append("<h2>{}</h2>".format(D.inline_html(bloc.titre)))
            corps.append(bloc.rendu_html or D.vers_html(blocs_md, niveau_depart=3))
        chemin = dossier / "lire.html"
        ecrire_page(chemin, produit.titre, "\n".join(corps),
                    sous_titre=produit.sous_titre, langue=langue,
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
            auteur.writerow(tableur.ligne(tableau.colonnes))
            for valeurs in tableau.lignes:
                auteur.writerow(tableur.ligne(valeurs))
        fichiers.append(chemin)

    # --- donnees de travail ----------------------------------------------------
    if produit.donnees and produit.nom_donnees:
        chemin = dossier / "{}.json".format(produit.nom_donnees)
        chemin.write_text(json.dumps(produit.donnees, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        fichiers.append(chemin)

    return fichiers


def _document(produit: Produit, ctx: Any,
              couverture: Optional[Tuple[str, Any]]) -> DocumentPDF:
    doc = DocumentPDF(format_page=produit.format_page, marge=produit.marge,
                      reliure=produit.reliure, titre_courant=produit.titre,
                      police_corps=produit.police_corps,
                      titre_document=produit.titre, auteur=ctx.auteur,
                      sujet=produit.sous_titre or produit.promesse,
                      langue=produit.langue or getattr(ctx, "langue_iso", "fr"))
    poser_couverture(doc, produit.titre, produit.sous_titre, ctx.auteur,
                     couverture)
    return doc


def poser_couverture(doc: DocumentPDF, titre: str, sous_titre: str,
                     auteur: str, couverture: Optional[Tuple[str, Any]]) -> None:
    """Premiere page du PDF, selon l'origine de la couverture."""
    if couverture and couverture[0] == "rvb":
        rvb, largeur, hauteur = couverture[1]
        doc.page_couverture_image(rvb, largeur, hauteur)
        return
    doc.page_couverture(titre, sous_titre, auteur,
                        image_jpeg=couverture[1] if couverture else None)


def document(ctx: Any, titre: str, sous_titre: str,
             couverture: Optional[Path] = None, format_page: Tuple[float, float] = A4,
             marge: float = 62.0, police_corps: str = "Times-Roman",
             titre_courant: str = "", reliure: float = 0.0) -> DocumentPDF:
    """Un PDF ouvert sur sa couverture, quelle qu'en soit la provenance.

    Les chaines qui gardent leur propre exportateur passaient toutes par les
    trois memes lignes : lire le fichier s'il est en JPEG, le donner au PDF,
    sinon rien. Le jour ou la couverture est devenue un PNG compose
    localement, ces trois lignes ont cesse d'en incorporer aucune — sans
    bruit, puisque le PDF restait valide. Elles vivent ici desormais.
    """
    doc = DocumentPDF(format_page=format_page, marge=marge, reliure=reliure,
                      police_corps=police_corps,
                      titre_courant=titre_courant or titre,
                      titre_document=titre, auteur=ctx.auteur,
                      sujet=sous_titre, langue=getattr(ctx, "langue_iso", "fr"))
    if couverture is None:
        poser_couverture(doc, titre, sous_titre, ctx.auteur, None)
    elif couverture.suffix.lower() in (".jpg", ".jpeg"):
        poser_couverture(doc, titre, sous_titre, ctx.auteur,
                         ("jpeg", couverture.read_bytes()))
    else:
        poser_couverture(doc, titre, sous_titre, ctx.auteur, ("rvb",
            images.couverture_pleine_page(
                titre, sous_titre, ctx.auteur,
                getattr(ctx, "marque", "") or "",
                largeur=int(format_page[0] * 1.28),
                hauteur=int(format_page[1] * 1.28))))
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
        "logiciel": "notice",
    }.get(type_produit, type_produit)


def bloc_markdown(titre: str, corps: str) -> Bloc:
    return Bloc(titre=titre, corps=corps)


def blocs_depuis_sections(sections: Sequence[Tuple[str, str]]) -> List[Bloc]:
    return [Bloc(titre=titre, corps=corps) for titre, corps in sections]
