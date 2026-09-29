"""Largeurs des polices PDF standard (unites 1/1000 em, d'apres les fichiers AFM).

Necessaire pour couper les lignes au bon endroit sans dependance externe.
"""

from __future__ import annotations

from typing import Dict

_ASCII = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
)


def _table(valeurs: str) -> Dict[str, int]:
    nombres = [int(v) for v in valeurs.split()]
    assert len(nombres) == len(_ASCII), (len(nombres), len(_ASCII))
    return dict(zip(_ASCII, nombres))


HELVETICA = _table(
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 1015 "
    "667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 "
    "278 278 278 469 556 333 "
    "556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722 500 500 500 "
    "334 260 334 584"
)

HELVETICA_GRAS = _table(
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 975 "
    "722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 667 778 722 667 611 722 667 944 667 667 611 "
    "333 278 333 584 556 333 "
    "556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 611 611 389 556 333 611 556 778 556 556 500 "
    "389 280 389 584"
)

TIMES = _table(
    "250 333 408 500 500 833 778 180 333 333 500 564 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 278 278 564 564 564 444 921 "
    "722 667 667 722 611 556 722 722 333 389 722 611 889 722 722 556 722 667 556 611 722 722 944 722 722 611 "
    "333 278 333 469 500 333 "
    "444 500 444 500 444 333 500 500 278 278 500 278 778 500 500 500 500 333 389 278 500 500 722 500 500 444 "
    "480 200 480 541"
)

TIMES_GRAS = _table(
    "250 333 555 500 500 1000 833 278 333 333 500 570 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 333 333 570 570 570 500 930 "
    "722 667 722 722 667 611 778 778 389 500 778 667 944 722 778 611 778 722 556 667 722 722 1000 722 722 667 "
    "333 278 333 581 500 333 "
    "500 556 444 556 444 333 500 556 278 333 556 278 833 556 500 556 556 444 389 333 556 500 722 500 500 444 "
    "394 220 394 520"
)

TIMES_ITALIQUE = _table(
    "250 333 420 500 500 833 778 214 333 333 500 675 250 333 250 278 "
    "500 500 500 500 500 500 500 500 500 500 333 333 675 675 675 500 920 "
    "611 611 667 722 611 611 722 722 333 444 667 556 833 667 722 611 722 611 500 556 722 611 833 611 556 556 "
    "389 278 389 422 500 333 "
    "500 500 444 500 444 278 500 500 278 278 444 278 722 500 500 500 500 389 389 278 500 444 667 444 444 389 "
    "400 275 400 541"
)

# Les 128 signes superieurs de WinAnsi (cp1252, octets 0x80 a 0xFF), dans
# l'ordre des octets, 0 pour les cinq positions vides. D'apres les memes
# fichiers AFM d'Adobe (copie livree avec matplotlib, lue le 27/09/2026 ;
# les tables ASCII ci-dessus y concordent a l'unite pres).
#
# Avant, « « », « — » ou « œ » empruntaient la largeur d'un autre signe : un
# guillemet francais etait mesure 36 % plus etroit qu'il ne s'imprime en
# Helvetica, « œ » 41 %. Une ligne justifiee qui en contenait depassait la
# marge de droite d'autant — sur du francais, c'est presque chaque page.
def _etendue(valeurs: str) -> Dict[str, int]:
    nombres = [int(v) for v in valeurs.split()]
    assert len(nombres) == 128, len(nombres)
    return {bytes([0x80 + rang]).decode("cp1252"): largeur
            for rang, largeur in enumerate(nombres) if largeur}


HELVETICA.update(_etendue(
    "556 0 222 556 333 1000 556 556 333 1000 667 333 1000 0 611 0 "
    "0 222 222 333 333 350 556 1000 333 1000 500 333 944 0 500 667 "
    "278 333 556 556 556 556 260 556 333 737 370 556 584 333 737 333 "
    "400 584 333 333 333 556 537 278 333 333 365 556 834 834 834 611 "
    "667 667 667 667 667 667 1000 722 667 667 667 667 278 278 278 278 "
    "722 722 778 778 778 778 778 584 778 722 722 722 722 667 667 611 "
    "556 556 556 556 556 556 889 500 556 556 556 556 278 278 278 278 "
    "556 556 556 556 556 556 556 584 611 556 556 556 556 500 556 500"))

HELVETICA_GRAS.update(_etendue(
    "556 0 278 556 500 1000 556 556 333 1000 667 333 1000 0 611 0 "
    "0 278 278 500 500 350 556 1000 333 1000 556 333 944 0 500 667 "
    "278 333 556 556 556 556 280 556 333 737 370 556 584 333 737 333 "
    "400 584 333 333 333 611 556 278 333 333 365 556 834 834 834 611 "
    "722 722 722 722 722 722 1000 722 667 667 667 667 278 278 278 278 "
    "722 722 778 778 778 778 778 584 778 722 722 722 722 667 667 611 "
    "556 556 556 556 556 556 889 556 556 556 556 556 278 278 278 278 "
    "611 611 611 611 611 611 611 584 611 611 611 611 611 556 611 556"))

TIMES.update(_etendue(
    "500 0 333 500 444 1000 500 500 333 1000 556 333 889 0 611 0 "
    "0 333 333 444 444 350 500 1000 333 980 389 333 722 0 444 722 "
    "250 333 500 500 500 500 200 500 333 760 276 500 564 333 760 333 "
    "400 564 300 300 333 500 453 250 333 300 310 500 750 750 750 444 "
    "722 722 722 722 722 722 889 667 611 611 611 611 333 333 333 333 "
    "722 722 722 722 722 722 722 564 722 722 722 722 722 722 556 500 "
    "444 444 444 444 444 444 667 444 444 444 444 444 278 278 278 278 "
    "500 500 500 500 500 500 500 564 500 500 500 500 500 500 500 500"))

TIMES_GRAS.update(_etendue(
    "500 0 333 500 500 1000 500 500 333 1000 556 333 1000 0 667 0 "
    "0 333 333 500 500 350 500 1000 333 1000 389 333 722 0 444 722 "
    "250 333 500 500 500 500 220 500 333 747 300 500 570 333 747 333 "
    "400 570 300 300 333 556 540 250 333 300 330 500 750 750 750 500 "
    "722 722 722 722 722 722 1000 722 667 667 667 667 389 389 389 389 "
    "722 722 778 778 778 778 778 570 778 722 722 722 722 722 611 556 "
    "500 500 500 500 500 500 722 444 444 444 444 444 278 278 278 278 "
    "500 556 500 500 500 500 500 570 500 556 556 556 556 500 556 500"))

TIMES_ITALIQUE.update(_etendue(
    "500 0 333 500 556 889 500 500 333 1000 500 333 944 0 556 0 "
    "0 333 333 556 556 350 500 889 333 980 389 333 667 0 389 556 "
    "250 389 500 500 500 500 275 500 333 760 276 500 675 333 760 333 "
    "400 675 300 300 333 500 523 250 333 300 310 500 750 750 750 500 "
    "611 611 611 611 611 611 889 667 611 611 611 611 333 333 333 333 "
    "722 667 722 722 722 722 722 675 722 722 722 722 722 556 611 500 "
    "500 500 500 500 500 500 667 444 444 444 444 444 278 278 278 278 "
    "500 500 500 500 500 500 500 675 500 500 500 500 500 444 500 444"))

POLICES = {
    "Helvetica": HELVETICA,
    "Helvetica-Bold": HELVETICA_GRAS,
    "Helvetica-Oblique": HELVETICA,
    "Times-Roman": TIMES,
    "Times-Bold": TIMES_GRAS,
    "Times-Italic": TIMES_ITALIQUE,
}

# Ce que WinAnsi n'a pas, et que le PDF dessine a la place — plutot qu'un
# « ? ». La table vit ICI parce que la mesure doit compter ce qui sera
# dessine : « → » s'imprime « -> », deux signes, pas un.
#
# Elle ne contient que ce que WinAnsi n'a VRAIMENT pas. Elle remplacait
# aussi « — », « – », « ’ », « “ », « … », « • », « × » : des signes que les
# polices standard portent, degrades pour rien — les tirets de dialogue d'un
# roman s'imprimaient en traits d'union. Et elle ignorait ce que les modeles
# ecrivent en francais : l'espace fine insecable (U+202F, avant « ; ! ? »
# et dans les guillemets) sortait en « ? », et le signe moins (U+2212)
# disparaissait — « −5 °C » s'imprimait « 5 °C ».
REMPLACEMENTS = {
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2007": " ",
    "\u2002": " ", "\u2003": " ", "\u200a": " ",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-",
    "\u2015": "\u2014",
    "→": "->", "←": "<-", "≥": ">=", "≤": "<=", "≠": "!=", "∞": "infini",
    "≈": "~", "⇒": "=>", "№": "no",
}


def largeur_texte(texte: str, police: str, taille: float) -> float:
    """Largeur d'une chaine en points typographiques."""
    table = POLICES.get(police, HELVETICA)
    total = 0
    defaut = table.get("n", 500)
    for caractere in texte:
        for dessine in REMPLACEMENTS.get(caractere, caractere):
            total += table.get(dessine, defaut)
    return total * taille / 1000.0
