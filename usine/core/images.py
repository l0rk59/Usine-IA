"""Generation d'images : couverture, visuels reseaux sociaux.

Source principale : Pollinations (aucune cle API requise).
Repli hors ligne : couverture SVG generee localement, sans dependance.
"""

from __future__ import annotations

import hashlib
import random
import urllib.parse
from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .http import HttpErreur, get_bytes

PALETTES: List[Tuple[str, str, str]] = [
    ("#0f172a", "#38bdf8", "#f8fafc"),
    ("#1e1b4b", "#a78bfa", "#faf5ff"),
    ("#052e16", "#4ade80", "#f0fdf4"),
    ("#450a0a", "#fb923c", "#fff7ed"),
    ("#0c4a6e", "#facc15", "#f8fafc"),
    ("#18181b", "#f472b6", "#fafafa"),
]


def _palette(graine: str) -> Tuple[str, str, str]:
    index = int(hashlib.md5(graine.encode("utf-8")).hexdigest(), 16) % len(PALETTES)
    return PALETTES[index]


def _echapper_xml(texte: str) -> str:
    return (
        texte.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def decouper(texte: str, largeur: int) -> List[str]:
    """Coupe un texte en lignes d'au plus `largeur` caracteres."""
    lignes: List[str] = []
    courante = ""
    for mot in texte.split():
        essai = (courante + " " + mot).strip()
        if len(essai) <= largeur:
            courante = essai
        else:
            if courante:
                lignes.append(courante)
            courante = mot
    if courante:
        lignes.append(courante)
    return lignes


def couverture_svg(
    titre: str,
    sous_titre: str = "",
    auteur: str = "",
    largeur: int = 1200,
    hauteur: int = 1600,
) -> str:
    """Couverture vectorielle autonome : fonctionne toujours, meme hors ligne."""
    fond, accent, encre = _palette(titre)
    lignes = decouper(titre.upper(), 18)[:5]
    taille = 92 if len(lignes) <= 3 else 74
    depart = hauteur // 2 - (len(lignes) - 1) * taille // 2 - 60

    blocs = []
    for i, ligne in enumerate(lignes):
        blocs.append(
            '<text x="{x}" y="{y}" font-family="Georgia,serif" font-size="{t}" '
            'font-weight="bold" fill="{c}" text-anchor="middle">{s}</text>'.format(
                x=largeur // 2, y=depart + i * int(taille * 1.15), t=taille,
                c=encre, s=_echapper_xml(ligne)
            )
        )
    if sous_titre:
        for j, ligne in enumerate(decouper(sous_titre, 42)[:2]):
            blocs.append(
                '<text x="{x}" y="{y}" font-family="Helvetica,Arial,sans-serif" '
                'font-size="38" fill="{c}" text-anchor="middle" opacity="0.9">{s}</text>'.format(
                    x=largeur // 2,
                    y=depart + len(lignes) * int(taille * 1.15) + 70 + j * 52,
                    c=accent,
                    s=_echapper_xml(ligne),
                )
            )
    if auteur:
        blocs.append(
            '<text x="{x}" y="{y}" font-family="Helvetica,Arial,sans-serif" font-size="34" '
            'fill="{c}" text-anchor="middle" opacity="0.75">{s}</text>'.format(
                x=largeur // 2, y=hauteur - 130, c=encre, s=_echapper_xml(auteur)
            )
        )

    rnd = random.Random(titre)
    cercles = "".join(
        '<circle cx="{}" cy="{}" r="{}" fill="{}" opacity="{:.2f}"/>'.format(
            rnd.randint(0, largeur), rnd.randint(0, hauteur),
            rnd.randint(60, 320), accent, rnd.uniform(0.04, 0.13)
        )
        for _ in range(9)
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="{fond}"/>'
        '<stop offset="100%" stop-color="{fond2}"/></linearGradient></defs>'
        '<rect width="{w}" height="{h}" fill="url(#g)"/>{cercles}'
        '<rect x="70" y="70" width="{wi}" height="{hi}" fill="none" '
        'stroke="{accent}" stroke-width="4" opacity="0.55"/>'
        "{blocs}</svg>"
    ).format(
        w=largeur,
        h=hauteur,
        fond=fond,
        fond2=accent + "22",
        cercles=cercles,
        wi=largeur - 140,
        hi=hauteur - 140,
        accent=accent,
        blocs="".join(blocs),
    )


def image_pollinations(
    invite: str,
    largeur: int = 1024,
    hauteur: int = 1024,
    modele: str = "sana",
    graine: Optional[int] = None,
    timeout: int = 180,
) -> bytes:
    """Genere une image via Pollinations (sans cle API). Leve HttpErreur si echec."""
    params = {
        "width": str(largeur),
        "height": str(hauteur),
        "model": modele,
        "nologo": "true",
        "referrer": "usine-ia",
    }
    if graine is None:
        graine = abs(hash(invite)) % 1_000_000
    params["seed"] = str(graine)
    url = "https://image.pollinations.ai/prompt/{}?{}".format(
        urllib.parse.quote(invite[:900], safe=""), urllib.parse.urlencode(params)
    )
    entetes = {}
    jeton = config.env("POLLINATIONS_TOKEN")
    if jeton:
        entetes["Authorization"] = "Bearer {}".format(jeton)
    brut = get_bytes(url, entetes, timeout=timeout)
    if len(brut) < 1024:
        raise HttpErreur(502, "image trop petite, generation probablement refusee")
    return brut


def extension_image(brut: bytes) -> str:
    if brut[:3] == b"\xff\xd8\xff":
        return "jpg"
    if brut[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if brut[:4] == b"RIFF" and brut[8:12] == b"WEBP":
        return "webp"
    return "bin"


def generer_couverture(
    dossier: Path,
    titre: str,
    sous_titre: str = "",
    auteur: str = "",
    style: str = "",
    en_ligne: bool = True,
) -> Path:
    """Ecrit une couverture dans `dossier`. Renvoie le chemin produit.

    Tente Pollinations ; retombe systematiquement sur le SVG local en cas
    d'echec, pour qu'un produit ne soit jamais bloque par le reseau.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    if en_ligne:
        invite = (
            "book cover artwork, {style}, abstract editorial design, bold geometric shapes, "
            "premium minimal poster, theme: {titre}. No text, no letters, no words."
        ).format(style=style or "modern flat vector", titre=titre)
        try:
            brut = image_pollinations(invite, 1024, 1365)
            chemin = dossier / "couverture.{}".format(extension_image(brut))
            chemin.write_bytes(brut)
            return chemin
        except Exception:
            pass  # repli local silencieux : la couverture SVG reste presentable
    chemin = dossier / "couverture.svg"
    chemin.write_text(couverture_svg(titre, sous_titre, auteur), encoding="utf-8")
    return chemin


def generer_visuel(
    dossier: Path,
    nom: str,
    invite: str,
    largeur: int = 1080,
    hauteur: int = 1080,
    en_ligne: bool = True,
) -> Optional[Path]:
    """Visuel carre pour les reseaux sociaux. Renvoie None si indisponible."""
    if not en_ligne:
        return None
    try:
        brut = image_pollinations(invite, largeur, hauteur)
    except Exception:
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "{}.{}".format(nom, extension_image(brut))
    chemin.write_bytes(brut)
    return chemin
