"""Generateur EPUB 3 (avec repli EPUB 2 via toc.ncx) en Python standard.

Un EPUB est une archive ZIP avec une structure imposee : zipfile suffit.
"""

from __future__ import annotations

import html
import uuid
import time
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import libelles

STYLE = """\
@page { margin: 1.1em; }
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.62;
       margin: 0 6%; color: #16181d; hyphens: auto; text-align: justify; }
h1 { font-family: Helvetica, Arial, sans-serif; font-size: 1.75em; line-height: 1.22;
     margin: 1.6em 0 0.2em; color: #0f172a; page-break-before: always; text-align: left; }
h1.premier { page-break-before: avoid; }
h1:after { content: ''; display: block; width: 68px; height: 3px;
           background: #2563eb; margin-top: .5em; }
h2 { font-family: Helvetica, Arial, sans-serif; font-size: 1.22em; margin: 1.7em 0 .35em;
     color: #1e293b; text-align: left; }
h3 { font-family: Helvetica, Arial, sans-serif; font-size: 1.05em; margin: 1.3em 0 .3em;
     color: #334155; text-align: left; }
p { margin: 0 0 .85em; text-indent: 0; }
ul, ol { margin: .6em 0 1.1em 1.3em; text-align: left; }
li { margin-bottom: .42em; }
blockquote { margin: 1.3em 0; padding: .2em 0 .2em 1.1em; border-left: 3px solid #2563eb;
             font-style: italic; color: #3f4653; }
aside.encadre { background: #f1f6fe; border-left: 4px solid #2563eb; padding: .9em 1.1em;
                margin: 1.4em 0; text-align: left; }
aside.encadre .encadre-titre { font-family: Helvetica, Arial, sans-serif; font-weight: bold;
                               color: #1d4ed8; margin: 0 0 .4em; font-size: .95em;
                               text-transform: uppercase; letter-spacing: .04em; }
hr { border: 0; height: 1px; background: #cbd5e1; width: 38%; margin: 2em auto; }
pre { background: #f4f5f7; padding: .8em; overflow-x: auto; font-size: .85em;
      font-family: 'Courier New', monospace; text-align: left; }
code { font-family: 'Courier New', monospace; font-size: .9em; }
.page-titre { text-align: center; margin-top: 22%; page-break-after: always; }
.page-titre h1 { page-break-before: avoid; font-size: 2.1em; border: 0; }
.page-titre h1:after { margin: .6em auto 0; }
.page-titre .sous-titre { font-size: 1.15em; color: #475569; font-style: italic; }
.page-titre .auteur { margin-top: 3.2em; color: #64748b; letter-spacing: .06em; }
img.couverture { max-width: 100%; height: auto; display: block; margin: 0 auto; }
.droits { font-size: .88em; color: #3f4653; text-align: left; margin-top: 12%;
          page-break-after: always; }
.droits p { margin: 0 0 .7em; }
.droits .oeuvre { font-weight: bold; color: #16181d; }
.droits .identifiant { font-size: .82em; color: #64748b; word-wrap: break-word; }
.dedicace { text-align: center; margin-top: 32%; font-style: italic;
            color: #3f4653; page-break-after: always; }
"""

GABARIT_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" \
xml:lang="{langue}" lang="{langue}">
<head><meta charset="utf-8"/><title>{titre}</title>
<link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>
{corps}
</body>
</html>
"""


def _xml(texte: str) -> str:
    return html.escape(texte, quote=True)


# --------------------------------------------------------------------------
# Accessibilite
# --------------------------------------------------------------------------

def metadonnees_accessibilite(avec_image: bool, langue: str = "fr") -> str:
    """Metadonnees EPUB Accessibility 1.1, exigees pour vendre dans l'Union.

    Elles ne sont pas decoratives : depuis le 28 juin 2025, l'European
    Accessibility Act s'applique aux livres numeriques, et un distributeur
    europeen refuse desormais un fichier qui n'en porte aucune.

    Ce qui est declare ici doit etre VRAI. Chaque affirmation correspond a
    une propriete du document reellement produit : l'ordre de lecture vient
    du fichier de navigation, la hierarchie des titres du modele de document,
    le contraste est verifie par un test sur la feuille de style livree.
    """
    modes = ["textual"]
    traits = ["tableOfContents", "structuralNavigation", "readingOrder",
              "displayTransformability", "unlocked"]
    if avec_image:
        modes.append("visual")
        traits.append("alternativeText")
    morceaux = ['<meta property="schema:accessMode">{}</meta>'.format(m)
                for m in modes]
    # Le texte seul suffit : rien d'essentiel n'est porte par l'image.
    morceaux.append(
        '<meta property="schema:accessModeSufficient">textual</meta>')
    morceaux += ['<meta property="schema:accessibilityFeature">{}</meta>'.format(t)
                 for t in traits]
    morceaux.append('<meta property="schema:accessibilityHazard">none</meta>')
    morceaux.append(
        '<meta property="schema:accessibilitySummary">{}</meta>'.format(
            _xml(libelles.libelle(langue, "resume_accessibilite"))))
    morceaux.append(
        '<meta property="dcterms:conformsTo">'
        "EPUB Accessibility 1.1 - WCAG 2.1 Level AA</meta>")
    morceaux.append('<meta property="a11y:certifiedBy">Usine-IA</meta>')
    return "".join(morceaux)


def page_droits(titre: str, auteur: str, editeur: str, identifiant: str,
                horodatage: str, mentions: Sequence[str] = (),
                langue: str = "fr") -> str:
    """Page de copyright — ce qui manque le plus visiblement a un livre fait maison.

    Amazon KDP attend un appareil liminaire dans cet ordre : page de titre,
    page de copyright, dedicace eventuelle, table des matieres. Un livre sans
    page de copyright se repere au premier coup d'oeil, et c'est la premiere
    chose qu'un lecteur habitue regarde apres le titre.

    Elle suit la langue du livre, comme « Sommaire » : elle etait en
    francais pour tout livre, y compris ecrit en anglais — la page que
    l'acheteur regarde juste apres le titre. Voir « render/libelles.py ».
    """
    t = libelles.textes(langue)
    annee = horodatage[:4]
    try:
        mois = t["mois"][int(horodatage[5:7]) - 1]
    except (ValueError, IndexError):
        mois = ""
    lignes = ['<p class="oeuvre">{}</p>'.format(_xml(titre))]
    lignes.append("<p>&#169; {} {}</p>".format(annee, _xml(auteur or "Usine-IA")))
    lignes.append("<p>{}</p>".format(_xml(t["droits_reserves"])))
    if editeur and editeur != auteur:
        lignes.append("<p>{}</p>".format(
            _xml(t["edite_par"].format(editeur=editeur))))
    lignes.append("<p>{}</p>".format(_xml(t["premiere_edition"].format(
        date="{} {}".format(mois, annee) if mois else annee))))
    for mention in mentions:
        if mention:
            lignes.append("<p>{}</p>".format(_xml(mention)))
    lignes.append('<p class="identifiant">{}</p>'.format(_xml(
        t["identifiant_publication"].format(identifiant=identifiant))))
    return '<div class="droits">{}</div>'.format("".join(lignes))


def _type_image(nom: str) -> str:
    """Type mime d'apres l'extension.

    Deduit du NOM, pas des octets : c'est ce que le manifeste declare, et un
    manifeste qui ment sur le type fait rejeter le livre par le distributeur
    avant meme qu'un lecteur l'ouvre. Les quatre formats connus sont ceux
    qu'EPUB 3 accepte comme images de base ; tout le reste passe pour du PNG,
    ce qui est faux mais visible — le controle de conformite le dira.
    """
    bas = nom.lower()
    if bas.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if bas.endswith(".svg"):
        return "image/svg+xml"
    if bas.endswith(".gif"):
        return "image/gif"
    if bas.endswith(".webp"):
        return "image/webp"
    return "image/png"


def construire_epub(
    chemin: Path,
    titre: str,
    auteur: str,
    chapitres: Sequence[Tuple[str, str]],
    langue: str = "fr",
    sous_titre: str = "",
    description: str = "",
    couverture: Optional[Tuple[str, bytes]] = None,
    editeur: str = "",
    mentions: Sequence[str] = (),
    dedicace: str = "",
    ressources: Sequence[Tuple[str, bytes]] = (),
) -> Path:
    """Assemble un EPUB.

    chapitres : suite de (titre, fragment HTML deja rendu).
    couverture : (nom de fichier, octets) — JPEG ou PNG.
    ressources : (chemin dans le livre, octets) — images citees par les
                 chapitres. Un EPUB est une archive FERMEE : une image
                 referencee mais absente du conteneur ne s'affiche pas chez
                 le lecteur, et le distributeur refuse le fichier.
    mentions   : lignes ajoutees a la page de copyright (mention d'assistance
                 IA, contact, numero d'edition...).
    dedicace   : texte de la page de dedicace, omise si vide.

    L'ordre des pages liminaires est celui qu'attend Amazon KDP : couverture,
    page de titre, page de copyright, dedicace, table des matieres, puis le
    texte. Ce n'est pas un detail de presentation — c'est a cet ordre qu'un
    lecteur reconnait un livre edite d'un fichier bricole.
    """
    identifiant = "urn:uuid:{}".format(uuid.uuid4())
    # Horodatage reel. Il etait fige a « 2026-01-01T00:00:00Z » pour tous les
    # livres : deux ouvrages differents portaient la meme date de derniere
    # modification, ce qu'une chaine de distribution utilise pour decider
    # quelle version remplacer.
    horodatage = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    chemin.parent.mkdir(parents=True, exist_ok=True)

    fichiers: List[Tuple[str, str, str]] = []  # (id, nom, type mime)

    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        # Le mimetype doit etre la premiere entree et rester non compresse.
        z.writestr(
            zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr("OEBPS/style.css", STYLE)

        nom_couverture = ""
        if couverture:
            nom_couverture, octets = couverture
            z.writestr("OEBPS/" + nom_couverture, octets)
            mime = _type_image(nom_couverture)
            fichiers.append(("cover-image", nom_couverture, mime))
            z.writestr(
                "OEBPS/couverture.xhtml",
                GABARIT_XHTML.format(
                    langue=langue,
                    titre=_xml(titre),
                    corps='<div class="page-titre"><img class="couverture" src="{}" '
                          'alt="{}"/></div>'.format(_xml(nom_couverture), _xml(titre)),
                ),
            )
            fichiers.append(("couverture", "couverture.xhtml", "application/xhtml+xml"))

        # Page de titre
        page_titre = ['<div class="page-titre"><h1>{}</h1>'.format(_xml(titre))]
        if sous_titre:
            page_titre.append('<p class="sous-titre">{}</p>'.format(_xml(sous_titre)))
        if auteur:
            page_titre.append('<p class="auteur">{}</p>'.format(_xml(auteur)))
        page_titre.append("</div>")
        z.writestr(
            "OEBPS/titre.xhtml",
            GABARIT_XHTML.format(langue=langue, titre=_xml(titre), corps="".join(page_titre)),
        )
        fichiers.append(("titre", "titre.xhtml", "application/xhtml+xml"))

        # Page de copyright : attendue par les plateformes, et absente de
        # tout livre fait maison. Elle porte l'identifiant unique de la
        # publication, qui n'apparaissait jusqu'ici que dans les metadonnees.
        z.writestr(
            "OEBPS/droits.xhtml",
            GABARIT_XHTML.format(
                langue=langue, titre=_xml(titre),
                corps=page_droits(titre, auteur, editeur, identifiant,
                                  horodatage, mentions, langue)),
        )
        fichiers.append(("droits", "droits.xhtml", "application/xhtml+xml"))

        if dedicace:
            z.writestr(
                "OEBPS/dedicace.xhtml",
                GABARIT_XHTML.format(
                    langue=langue, titre=_xml(titre),
                    corps='<div class="dedicace">{}</div>'.format(
                        _xml(dedicace))),
            )
            fichiers.append(("dedicace", "dedicace.xhtml",
                             "application/xhtml+xml"))

        for rang, (nom_ressource, octets) in enumerate(ressources, 1):
            if not octets:
                continue
            z.writestr("OEBPS/" + nom_ressource, octets)
            fichiers.append(("res{:03d}".format(rang), nom_ressource,
                             _type_image(nom_ressource)))

        entrees_nav: List[Tuple[str, str]] = []
        for index, (titre_chapitre, corps_html) in enumerate(chapitres, 1):
            nom = "ch{:03d}.xhtml".format(index)
            classe = ' class="premier"' if index == 1 else ""
            corps = "<h1{}>{}</h1>\n{}".format(classe, _xml(titre_chapitre), corps_html)
            z.writestr(
                "OEBPS/" + nom,
                GABARIT_XHTML.format(
                    langue=langue, titre=_xml(titre_chapitre), corps=corps
                ),
            )
            fichiers.append(("ch{:03d}".format(index), nom, "application/xhtml+xml"))
            entrees_nav.append((nom, titre_chapitre))

        # nav.xhtml (EPUB 3)
        liens = "".join(
            '<li><a href="{}">{}</a></li>'.format(_xml(n), _xml(t)) for n, t in entrees_nav
        )
        z.writestr(
            "OEBPS/nav.xhtml",
            GABARIT_XHTML.format(
                langue=langue,
                titre=_xml(libelles.libelle(langue, "sommaire")),
                corps='<nav epub:type="toc" id="toc"><h1 class="premier">{}</h1>'
                      "<ol>{}</ol></nav>".format(
                          _xml(libelles.libelle(langue, "sommaire")), liens),
            ),
        )

        # toc.ncx (compatibilite liseuses EPUB 2)
        points = "".join(
            '<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{t}</text></navLabel>'
            '<content src="{n}"/></navPoint>'.format(i=i, t=_xml(t), n=_xml(n))
            for i, (n, t) in enumerate(entrees_nav, 1)
        )
        z.writestr(
            "OEBPS/toc.ncx",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            '<head><meta name="dtb:uid" content="{id}"/></head>'
            '<docTitle><text>{t}</text></docTitle>'
            "<navMap>{p}</navMap></ncx>".format(id=identifiant, t=_xml(titre), p=points),
        )

        # content.opf
        manifeste = [
            '<item id="style" href="style.css" media-type="text/css"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        ]
        for ident, nom, mime in fichiers:
            extra = ' properties="cover-image"' if ident == "cover-image" else ""
            manifeste.append(
                '<item id="{}" href="{}" media-type="{}"{}/>'.format(ident, nom, mime, extra)
            )
        colonne = []
        if nom_couverture:
            colonne.append('<itemref idref="couverture"/>')
        colonne.append('<itemref idref="titre"/>')
        colonne.append('<itemref idref="droits"/>')
        if dedicace:
            colonne.append('<itemref idref="dedicace"/>')
        colonne.append('<itemref idref="nav"/>')
        colonne.extend(
            '<itemref idref="{}"/>'.format(ident)
            for ident, _, mime in fichiers
            if mime == "application/xhtml+xml" and ident.startswith("ch")
        )
        meta_couverture = (
            '<meta name="cover" content="cover-image"/>' if nom_couverture else ""
        )
        z.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="pub-id" xml:lang="{langue}" '
            'prefix="a11y: http://www.idpf.org/epub/vocab/package/a11y/#">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="pub-id">{id}</dc:identifier>'
            "<dc:title>{titre}</dc:title>"
            "<dc:creator>{auteur}</dc:creator>"
            "<dc:language>{langue}</dc:language>"
            "<dc:description>{desc}</dc:description>"
            "<dc:publisher>{editeur}</dc:publisher>"
            "<dc:date>{horodatage}</dc:date>"
            "<dc:rights>(c) {annee} {auteur}</dc:rights>"
            '<meta property="dcterms:modified">{horodatage}</meta>'
            "{acces}{metacouv}</metadata>"
            "<manifest>{manifeste}</manifest>"
            '<spine toc="ncx">{colonne}</spine></package>'.format(
                id=identifiant,
                titre=_xml(titre),
                auteur=_xml(auteur or "Usine-IA"),
                langue=langue,
                desc=_xml(description[:600]),
                editeur=_xml(editeur or auteur or "Usine-IA"),
                horodatage=horodatage,
                annee=horodatage[:4],
                acces=metadonnees_accessibilite(bool(couverture), langue),
                metacouv=meta_couverture,
                manifeste="".join(manifeste),
                colonne="".join(colonne),
            ),
        )
    return chemin
