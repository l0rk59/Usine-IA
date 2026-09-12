"""Page HTML autonome, lisible sur telephone et imprimable en PDF depuis le navigateur."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

GABARIT = """<!doctype html>
<html lang="{langue}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{titre}</title>
<style>
:root {{ --fond:#ffffff; --encre:#16181d; --doux:#5b6472; --accent:#2563eb;
         --bordure:#e2e8f0; --encadre:#f1f6fe; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fond:#0f1218; --encre:#e8eaee; --doux:#9aa3b2; --accent:#60a5fa;
           --bordure:#262c38; --encadre:#151c28; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--fond); color:var(--encre);
        font:16px/1.68 Georgia,'Times New Roman',serif; }}
.enveloppe {{ max-width: 46rem; margin: 0 auto; padding: 2.2rem 1.15rem 5rem; }}
header.hero {{ padding: 2.4rem 0 1.6rem; border-bottom: 1px solid var(--bordure);
               margin-bottom: 2.2rem; }}
h1,h2,h3 {{ font-family: -apple-system,'Helvetica Neue',Helvetica,Arial,sans-serif;
            line-height:1.25; }}
h1 {{ font-size: clamp(1.7rem, 5.2vw, 2.35rem); margin:.2em 0 .3em; }}
h2 {{ font-size: clamp(1.22rem, 3.8vw, 1.5rem); margin:2.2em 0 .5em; }}
h3 {{ font-size: 1.08rem; margin:1.7em 0 .4em; color:var(--doux); }}
h2:after {{ content:''; display:block; width:52px; height:3px; background:var(--accent);
            margin-top:.45em; border-radius:2px; }}
p {{ margin:0 0 1em; }}
ul,ol {{ padding-left:1.3rem; margin:.7em 0 1.3em; }}
li {{ margin-bottom:.45em; }}
blockquote {{ margin:1.5em 0; padding:.3em 0 .3em 1.1rem;
              border-left:3px solid var(--accent); font-style:italic; color:var(--doux); }}
aside.encadre {{ background:var(--encadre); border-left:4px solid var(--accent);
                 padding:1rem 1.15rem; margin:1.7em 0; border-radius:0 8px 8px 0; }}
aside.encadre .encadre-titre {{ font-family:Helvetica,Arial,sans-serif; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em; font-size:.78rem;
    color:var(--accent); margin:0 0 .45em; }}
hr {{ border:0; height:1px; background:var(--bordure); width:40%; margin:2.4em auto; }}
pre {{ background:var(--encadre); padding:.9rem; border-radius:8px; overflow-x:auto;
       font-size:.85rem; }}
code {{ font-family:ui-monospace,'Courier New',monospace; font-size:.9em; }}
img {{ max-width:100%; height:auto; border-radius:10px; }}
.sous-titre {{ color:var(--doux); font-size:1.08rem; font-style:italic; margin:0; }}
.meta {{ color:var(--doux); font-size:.85rem; font-family:Helvetica,Arial,sans-serif;
         margin-top:1.1rem; }}
table {{ width:100%; border-collapse:collapse; margin:1.3em 0; font-size:.92rem; }}
th,td {{ border:1px solid var(--bordure); padding:.55em .7em; text-align:left; }}
@media print {{
  body {{ background:#fff; color:#000; font-size:11pt; }}
  .enveloppe {{ max-width:none; padding:0; }}
  h2 {{ page-break-after:avoid; }}
  aside.encadre, blockquote {{ page-break-inside:avoid; }}
}}
{style}
</style>
</head>
<body>
<div class="enveloppe">
<header class="hero">
<h1>{titre}</h1>
{sous_titre}
{meta}
</header>
{couverture}
{corps}
</div>
{script}
</body>
</html>
"""


def ecrire_page(
    chemin: Path,
    titre: str,
    corps_html: str,
    sous_titre: str = "",
    meta: str = "",
    langue: str = "fr",
    couverture: Optional[str] = None,
    style: str = "",
    script: str = "",
) -> Path:
    """Page autonome. « style » entre dans l'en-tete, « script » en fin de corps.

    Les deux existent pour le quiz auto-corrige : une page qui se corrige
    seule a besoin de ses propres regles et de son script. Les placer ici
    plutot que dans le corps garde le HTML conforme — une balise « style »
    dans le corps ne l'est pas.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        GABARIT.format(
            langue=langue,
            titre=html.escape(titre),
            sous_titre='<p class="sous-titre">{}</p>'.format(html.escape(sous_titre))
            if sous_titre else "",
            meta='<p class="meta">{}</p>'.format(html.escape(meta)) if meta else "",
            couverture='<p><img src="{}" alt="Couverture"/></p>'.format(html.escape(couverture))
            if couverture else "",
            corps=corps_html,
            style=style,
            script="<script>{}</script>".format(script) if script else "",
        ),
        encoding="utf-8",
    )
    return chemin
