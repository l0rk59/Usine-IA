"""Generateur EPUB 3 (avec repli EPUB 2 via toc.ncx) en Python standard.

Un EPUB est une archive ZIP avec une structure imposee : zipfile suffit.
"""

from __future__ import annotations

import html
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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


def construire_epub(
    chemin: Path,
    titre: str,
    auteur: str,
    chapitres: Sequence[Tuple[str, str]],
    langue: str = "fr",
    sous_titre: str = "",
    description: str = "",
    couverture: Optional[Tuple[str, bytes]] = None,
) -> Path:
    """Assemble un EPUB.

    chapitres : suite de (titre, fragment HTML deja rendu).
    couverture : (nom de fichier, octets) — JPEG ou PNG.
    """
    identifiant = "urn:uuid:{}".format(uuid.uuid4())
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
            mime = "image/jpeg" if nom_couverture.lower().endswith(("jpg", "jpeg")) else (
                "image/svg+xml" if nom_couverture.lower().endswith("svg") else "image/png"
            )
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
                titre="Sommaire",
                corps='<nav epub:type="toc" id="toc"><h1 class="premier">Sommaire</h1>'
                      "<ol>{}</ol></nav>".format(liens),
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
            'unique-identifier="pub-id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="pub-id">{id}</dc:identifier>'
            "<dc:title>{titre}</dc:title>"
            "<dc:creator>{auteur}</dc:creator>"
            "<dc:language>{langue}</dc:language>"
            "<dc:description>{desc}</dc:description>"
            '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>'
            "{metacouv}</metadata>"
            "<manifest>{manifeste}</manifest>"
            '<spine toc="ncx">{colonne}</spine></package>'.format(
                id=identifiant,
                titre=_xml(titre),
                auteur=_xml(auteur or "Usine-IA"),
                langue=langue,
                desc=_xml(description[:600]),
                metacouv=meta_couverture,
                manifeste="".join(manifeste),
                colonne="".join(colonne),
            ),
        )
    return chemin
