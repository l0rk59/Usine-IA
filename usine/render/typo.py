"""Une fonte capitale geometrique, ecrite en polygones.

Pourquoi ecrire une fonte plutot que d'en embarquer une : pour dessiner un
titre sur une image, il faut les CONTOURS des lettres. Les metriques AFM que
le moteur PDF utilise ne donnent que des largeurs — le PDF delegue le dessin
au lecteur. Une couverture PNG, elle, n'a personne a qui deleguer.

Les trois issues possibles etaient : embarquer un fichier TrueType et ecrire
son analyseur (un binaire dans un depot qui n'en a aucun), dependre d'une
fonte du systeme (Termux n'en garantit aucune), ou dessiner les lettres.
C'est la troisieme, cohérente avec un moteur PDF et un moteur WebGL deja
ecrits a la main.

CAPITALES UNIQUEMENT, et c'est un choix, pas une limite subie : un titre de
couverture se compose en capitales, un sous-titre en petites capitales
espacees. Dessiner soixante bas-de-casse pour ne jamais les utiliser aurait
double le travail sans rien ajouter a la page.

Systeme de coordonnees : cadratin de 1000, capitale de 700, y vers le HAUT,
origine sur la ligne de pied. Les accents montent jusqu'a 920, la cedille
descend a -170.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Tuple

Point = Tuple[float, float]
Contour = List[Point]
Glyphe = Tuple[float, List[Contour]]

CADRATIN = 1000.0
CAPITALE = 700.0
EPAISSEUR = 112.0
HAUT_ACCENT = 920.0
BAS_CEDILLE = -170.0


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def _aire(contour: Sequence[Point]) -> float:
    total = 0.0
    for i in range(len(contour)):
        x0, y0 = contour[i]
        x1, y1 = contour[(i + 1) % len(contour)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def _direct(contour: Contour) -> Contour:
    """Force le sens trigonometrique.

    Le remplissage compte les enroulements (regle « nonzero ») : deux formes
    de meme sens fusionnent, deux formes de sens opposes se percent. Toutes
    les formes pleines passent donc par ici, et seuls les anneaux — qui
    portent leur trou dans leur propre contour — y echappent.
    """
    return contour if _aire(contour) > 0 else contour[::-1]


def _barre(x: float, y: float, largeur: float, hauteur: float) -> Contour:
    return _direct([(x, y), (x + largeur, y), (x + largeur, y + hauteur),
                    (x, y + hauteur)])


def _poly(*points: Point) -> Contour:
    return _direct(list(points))


def _oblique(xa: float, ya: float, xb: float, yb: float,
             epaisseur: float = EPAISSEUR, coupe: str = "auto") -> Contour:
    """Trait incline, de meme graisse perpendiculaire qu'une barre droite.

    Decaler les extremites de epaisseur/2 a l'horizontale donnerait un trait
    d'autant plus maigre qu'il est couche : a 45 degres il perdrait 30 % de
    sa graisse et le Z paraitrait plus clair que le E. La coupe se fait donc
    du cote le plus court, et le decalage compense l'inclinaison.
    """
    dx, dy = xb - xa, yb - ya
    longueur = math.hypot(dx, dy) or 1.0
    demi = epaisseur / 2.0
    horizontale = abs(dy) >= abs(dx) if coupe == "auto" else coupe == "horizontale"
    if horizontale:                  # extremites coupees a l'horizontale
        ecart = demi * longueur / (abs(dy) or 1.0)
        return _direct([(xa - ecart, ya), (xa + ecart, ya),
                        (xb + ecart, yb), (xb - ecart, yb)])
    ecart = demi * longueur / (abs(dx) or 1.0)   # trait couche : verticales
    return _direct([(xa, ya - ecart), (xa, ya + ecart),
                    (xb, yb + ecart), (xb, yb - ecart)])


def _bol(x: float, y: float, largeur: float, hauteur: float,
         epaisseur: float = EPAISSEUR, rayon: float = 0.0) -> List[Contour]:
    """Panse en forme de D, ouverte a gauche : le ventre du B, D, P et R.

    Une demi-ellipse donnerait un contrepoinçon en amande, pointu aux deux
    bouts — le defaut le plus visible d'une fonte geometrique bâclee. Un
    montant droit ferme par deux quarts de cercle donne la forme attendue.
    """
    rayon = min(rayon or hauteur / 2.0, hauteur / 2.0, largeur)
    droit = x + largeur - rayon
    formes = [
        _barre(x, y + hauteur - epaisseur, max(0.0, droit - x), epaisseur),
        _barre(x, y, max(0.0, droit - x), epaisseur),
        _anneau(droit, y + hauteur - rayon, rayon, rayon, epaisseur, 0, 90),
        _anneau(droit, y + rayon, rayon, rayon, epaisseur, -90, 0),
    ]
    if hauteur - 2 * rayon > 0.5:
        formes.append(_barre(x + largeur - epaisseur, y + rayon, epaisseur,
                             hauteur - 2 * rayon))
    return formes


def _anneau(cx: float, cy: float, rx: float, ry: float,
            epaisseur: float = EPAISSEUR, a0: float = 0.0, a1: float = 360.0,
            pas: float = 6.0) -> Contour:
    """Arc epais. Un seul contour : bord exterieur, puis bord interieur a
    l'envers — le trou est donc porte par la forme elle-meme."""
    segments = max(4, int(math.ceil(abs(a1 - a0) / pas)))
    dehors: Contour = []
    dedans: Contour = []
    for i in range(segments + 1):
        angle = math.radians(a0 + (a1 - a0) * i / segments)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        dehors.append((cx + rx * cos_a, cy + ry * sin_a))
        dedans.append((cx + (rx - epaisseur) * cos_a,
                       cy + (ry - epaisseur) * sin_a))
    return dehors + dedans[::-1]


def _decaler(contours: Sequence[Contour], dx: float = 0.0,
             dy: float = 0.0) -> List[Contour]:
    return [[(x + dx, y + dy) for x, y in c] for c in contours]


def _disque(cx: float, cy: float, rayon: float) -> Contour:
    return _anneau(cx, cy, rayon, rayon, rayon, 0.0, 360.0, pas=12.0)


# --------------------------------------------------------------------------
# Le dessin des lettres
# --------------------------------------------------------------------------

H = CAPITALE
E = EPAISSEUR


def _table() -> Dict[str, Glyphe]:
    g: Dict[str, Glyphe] = {}

    g[" "] = (300.0, [])

    g["A"] = (660.0, [
        _poly((0, 0), (E, 0), (290 + E / 2, H), (290 - E / 2, H)),
        _poly((580 - E, 0), (580, 0), (290 + E / 2, H), (290 - E / 2, H)),
        _barre(92, 165, 396, 100),
    ])
    g["B"] = (640.0, [
        _barre(0, 0, E, H),
        _barre(0, H - E, 170, E), _barre(0, 294, 250, E), _barre(0, 0, 170, E),
    ] + _bol(150, 350, 340, 350, E, 172) + _bol(150, 0, 370, 350, E, 172) + [
    ])
    g["C"] = (660.0, [_anneau(290, 350, 290, 350, E, 42, 318)])
    g["D"] = (680.0, [
        _barre(0, 0, E, H),
        _barre(0, H - E, 170, E), _barre(0, 0, 170, E),
    ] + _bol(150, 0, 430, H, E, 250))
    g["E"] = (600.0, [
        _barre(0, 0, E, H), _barre(0, H - E, 480, E),
        _barre(0, 294, 430, E), _barre(0, 0, 480, E),
    ])
    g["F"] = (580.0, [
        _barre(0, 0, E, H), _barre(0, H - E, 470, E), _barre(0, 294, 420, E),
    ])
    g["G"] = (700.0, [
        _anneau(290, 350, 290, 350, E, 28, 332),
        _barre(468, 186, E, 220), _barre(318, 294, 262, E),
    ])
    g["H"] = (660.0, [
        _barre(0, 0, E, H), _barre(448, 0, E, H), _barre(0, 294, 560, E),
    ])
    # Comme toutes les autres : le dessin part de x = 0, l'approche est a
    # droite. Centrer le I dans sa chasse lui donnait une approche gauche de
    # 79 unites, et « FREELANCING » se lisait « FREELANC ING ».
    g["I"] = (212.0, [_barre(0, 0, E, H)])
    g["J"] = (580.0, [
        _barre(360, 200, E, 500),
        _anneau(236, 200, 236, 200, E, 180, 360),
    ])
    g["K"] = (640.0, [
        _barre(0, 0, E, H),
        _oblique(98, 318, 498, H, coupe="horizontale"),
        _oblique(102, 372, 516, 0, coupe="horizontale"),
    ])
    g["L"] = (560.0, [_barre(0, 0, E, H), _barre(0, 0, 460, E)])
    g["M"] = (800.0, [
        _barre(0, 0, E, H), _barre(578, 0, E, H),
        _oblique(66, H, 345, 190, coupe="horizontale"),
        _oblique(624, H, 345, 190, coupe="horizontale"),
    ])
    g["N"] = (680.0, [
        _barre(0, 0, E, H), _barre(458, 0, E, H),
        _oblique(70, H, 500, 0, coupe="horizontale"),
    ])
    g["O"] = (700.0, [_anneau(300, 350, 300, 350, E)])
    g["P"] = (630.0, [
        _barre(0, 0, E, H),
        _barre(0, H - E, 170, E), _barre(0, 350, 250, E),
    ] + _bol(150, 350, 360, 350, E, 172))
    g["Q"] = (700.0, [
        _anneau(300, 350, 300, 350, E),
        _oblique(400, 150, 570, -70, 104),
    ])
    g["R"] = (660.0, [
        _barre(0, 0, E, H),
        _barre(0, H - E, 170, E), _barre(0, 350, 250, E),
        _oblique(296, 372, 556, 0),
    ] + _bol(150, 350, 360, 350, E, 172))
    g["S"] = (620.0, [
        _anneau(270, 525, 270, 175, E, 4, 268),
        _anneau(270, 175, 270, 175, E, -178, 90),
    ])
    g["T"] = (620.0, [_barre(0, H - E, 540, E), _barre(214, 0, E, H - E)])
    g["U"] = (670.0, [
        _barre(0, 200, E, 500), _barre(458, 200, E, 500),
        _anneau(285, 200, 285, 200, E, 180, 360),
    ])
    g["V"] = (660.0, [
        _poly((0, H), (E, H), (290 + E / 2, 0), (290 - E / 2, 0)),
        _poly((580 - E, H), (580, H), (290 + E / 2, 0), (290 - E / 2, 0)),
    ])
    g["W"] = (930.0, [
        _oblique(62, H, 250, 0, coupe="horizontale"),
        _oblique(420, H, 250, 0, coupe="horizontale"),
        _oblique(420, H, 594, 0, coupe="horizontale"),
        _oblique(782, H, 594, 0, coupe="horizontale"),
    ])
    g["X"] = (650.0, [_oblique(68, H, 492, 0, coupe="horizontale"),
                      _oblique(492, H, 68, 0, coupe="horizontale")])
    g["Y"] = (630.0, [
        _oblique(68, H, 280, 358, coupe="horizontale"),
        _oblique(492, H, 280, 358, coupe="horizontale"),
        _barre(224, 0, E, 380),
    ])
    g["Z"] = (620.0, [
        _barre(0, H - E, 520, E), _oblique(446, H - E, 80, E),
        _barre(0, 0, 520, E),
    ])

    g["0"] = (650.0, [_anneau(280, 350, 280, 350, E)])
    g["1"] = (400.0, [
        _barre(150, 0, E, H),
        _poly((20, 556), (160, 640), (160, H), (20, 616)),
    ])
    g["2"] = (640.0, [
        _anneau(270, 455, 260, 245, E, -32, 188),
        _oblique(443, 355, 118, E), _barre(0, 0, 540, E),
    ])
    g["3"] = (630.0, [
        _anneau(262, 525, 250, 175, E, -100, 168),
        _anneau(262, 175, 250, 175, E, -168, 100),
    ])
    g["4"] = (650.0, [
        _oblique(340, H, 70, 250), _barre(0, 250, 520, E), _barre(340, 0, E, H),
    ])
    g["5"] = (620.0, [
        _barre(0, H - E, 470, E), _barre(0, 330, E, 370),
        _anneau(250, 230, 290, 230, E, -110, 105),
        _barre(0, 330, 240, E),
    ])
    g["6"] = (650.0, [
        _anneau(280, 220, 280, 220, E),
        _anneau(300, 200, 300, 500, E, 100, 172),
    ])
    g["7"] = (610.0, [_barre(0, H - E, 540, E), _oblique(474, H - E, 170, 0)])
    g["8"] = (650.0, [
        _anneau(270, 520, 270, 180, E), _anneau(270, 180, 270, 180, E),
    ])
    g["9"] = (650.0, [
        _anneau(280, 480, 280, 220, E),
        _anneau(260, 500, 300, 500, E, -80, -8),
    ])

    g["."] = (300.0, [_disque(150, 60, 62)])
    g[","] = (300.0, [_disque(150, 60, 62),
                      _poly((88, 20), (200, 40), (140, -160), (70, -150))])
    g[":"] = (300.0, [_disque(150, 60, 62), _disque(150, 420, 62)])
    g[";"] = (300.0, [_disque(150, 420, 62), _disque(150, 60, 62),
                      _poly((88, 20), (200, 40), (140, -160), (70, -150))])
    g["'"] = (240.0, [_poly((60, 480), (170, 480), (140, H), (60, H))])
    g["-"] = (460.0, [_barre(60, 294, 340, E)])
    g["—"] = (760.0, [_barre(40, 294, 680, E)])
    g["_"] = (600.0, [_barre(20, -110, 560, E)])
    g["!"] = (300.0, [_barre(94, 200, E, 500), _disque(150, 60, 62)])
    g["?"] = (580.0, [
        _anneau(270, 495, 250, 205, E, -35, 200),
        _barre(214, 200, E, 130), _disque(270, 60, 62),
    ])
    g["("] = (380.0, [_anneau(350, 350, 340, 460, E, 145, 215)])
    g[")"] = (380.0, [_anneau(30, 350, 340, 460, E, -35, 35)])
    g["/"] = (560.0, [_oblique(70, -40, 430, H + 40)])
    g["+"] = (600.0, [_barre(60, 294, 460, E), _barre(234, 120, E, 460)])
    g["«"] = (560.0, [
        _oblique(240, 480, 90, 350, 96), _oblique(90, 350, 240, 220, 96),
        _oblique(460, 480, 310, 350, 96), _oblique(310, 350, 460, 220, 96),
    ])
    g["»"] = (560.0, [
        _oblique(90, 480, 240, 350, 96), _oblique(240, 350, 90, 220, 96),
        _oblique(310, 480, 460, 350, 96), _oblique(460, 350, 310, 220, 96),
    ])
    g["%"] = (760.0, [
        _anneau(160, 540, 160, 160, 84), _anneau(560, 160, 160, 160, 84),
        _oblique(140, 0, 580, H, 92),
    ])
    g["&"] = (740.0, [
        _anneau(248, 520, 186, 166, 100, -58, 248),
        _anneau(250, 212, 250, 212, E, 132, 380),
        _oblique(178, 366, 66, 356),
        _oblique(346, 396, 652, 44),
    ])
    g["°"] = (380.0, [_anneau(190, 570, 130, 130, 72)])
    g["€"] = (660.0, [
        _anneau(310, 350, 290, 350, E, 40, 320),
        _barre(0, 250, 420, 92), _barre(0, 400, 420, 92),
    ])
    return g


TABLE: Dict[str, Glyphe] = _table()


# --------------------------------------------------------------------------
# Accents : composes, pas redessines
# --------------------------------------------------------------------------

_AIGU = [_oblique(-70, 745, 70, 900, 100)]
_GRAVE = [_oblique(70, 745, -70, 900, 100)]
# Les deux jambages visent le MEME sommet : les decaler de quelques unites
# les faisait se croiser, et l'accent circonflexe prenait l'air d'un tilde.
_CIRCONFLEXE = [_oblique(-112, 742, 0, 898, 94), _oblique(112, 742, 0, 898, 94)]
_TREMA = [_disque(-92, 822, 62), _disque(92, 822, 62)]
_CEDILLE = [_barre(-40, -54, 80, 114),
            _poly((-40, -30), (40, -14), (-26, -206), (-100, -156))]

_COMPOSES = {
    "À": ("A", _GRAVE), "Â": ("A", _CIRCONFLEXE),
    "Ä": ("A", _TREMA),
    "É": ("E", _AIGU), "È": ("E", _GRAVE),
    "Ê": ("E", _CIRCONFLEXE), "Ë": ("E", _TREMA),
    "Î": ("I", _CIRCONFLEXE), "Ï": ("I", _TREMA),
    "Ì": ("I", _GRAVE), "Í": ("I", _AIGU),
    "Ô": ("O", _CIRCONFLEXE), "Ö": ("O", _TREMA),
    "Ò": ("O", _GRAVE), "Ó": ("O", _AIGU),
    "Ù": ("U", _GRAVE), "Û": ("U", _CIRCONFLEXE),
    "Ü": ("U", _TREMA), "Ú": ("U", _AIGU),
    "Ç": ("C", _CEDILLE),
    "Ñ": ("N", _CIRCONFLEXE),
}

# Ce que la fonte ne dessine pas, mais qu'un titre peut contenir.
_EQUIVALENTS = {
    "Œ": "OE", "Æ": "AE", "ß": "SS",
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "−": "-", " ": " ", " ": " ",
    "…": "...", "×": "X", "*": "", "#": "", "|": "/",
    '"': "'", "[": "(", "]": ")", "{": "(", "}": ")",
    "$": "€", "£": "€", "=": "-", "~": "-",
    "<": "«", ">": "»", "@": "A", "\\": "/", "`": "'",
}


def _glyphe(caractere: str) -> Glyphe:
    if caractere in TABLE:
        return TABLE[caractere]
    compose = _COMPOSES.get(caractere)
    if compose is None:
        return TABLE[" "]
    base, accent = compose
    largeur, formes = TABLE[base]
    # L'accent se centre sur le DESSIN de la lettre, pas sur sa chasse : le I
    # occupe le milieu de sa chasse, le L le tiers gauche. Centrer sur la
    # chasse posait l'accent du I a quarante-cinq unites de son montant.
    gauche, _, droite, _ = cadre(formes)
    return (largeur, list(formes)
            + _decaler(accent, dx=(gauche + droite) / 2.0))


def normaliser(texte: str) -> str:
    """Met en capitales et remplace ce que la fonte ne sait pas dessiner.

    Un caractere inconnu est retire plutot que remplace par un rectangle : sur
    une couverture, une lettre manquante se remarque moins qu'un carre noir.
    """
    sortie = []
    for caractere in (texte or ""):
        remplacement = _EQUIVALENTS.get(caractere)
        if remplacement is not None:
            caractere = remplacement
        for lettre in caractere.upper():
            if lettre in TABLE or lettre in _COMPOSES:
                sortie.append(lettre)
            elif lettre.isspace():
                sortie.append(" ")
    return "".join(sortie)


def chasse(texte: str, interlettre: float = 0.0) -> float:
    """Largeur du texte, en unites de cadratin."""
    total = 0.0
    for caractere in texte:
        total += _glyphe(caractere)[0] + interlettre
    return max(0.0, total - interlettre) if texte else 0.0


def contours(texte: str, interlettre: float = 0.0) -> List[Contour]:
    """Contours du texte, ligne de pied en y=0, premier glyphe en x=0."""
    formes: List[Contour] = []
    curseur = 0.0
    for caractere in texte:
        largeur_glyphe, dessin = _glyphe(caractere)
        if dessin:
            formes.extend(_decaler(dessin, dx=curseur))
        curseur += largeur_glyphe + interlettre
    return formes


def couper(texte: str, largeur_max: float,
           interlettre: float = 0.0) -> List[str]:
    """Repartit un texte deja normalise en lignes tenant dans la largeur.

    La largeur est en unites de cadratin, comme tout le reste : le module ne
    connait ni pixels ni points, c'est l'appelant qui met a l'echelle.

    Il n'y a pas de nombre maximal de lignes ici. Une version precedente
    fusionnait les lignes excedentaires dans la derniere, qui devenait alors
    plus large que la limite demandee — la fonction rendait un resultat qui
    violait sa propre promesse, et l'appelant devait s'en mefier. Le nombre
    de lignes est une decision de mise en page, pas de cesure.

    Seule exception a la promesse, et elle est explicite : un mot seul plus
    large que la limite reste entier. Il n'y a pas de cesure — couper
    « PRESTATIONS » en deux sur une couverture serait pire que de reduire le
    corps, et c'est ce que fait l'appelant.
    """
    mots = texte.split()
    if not mots:
        return []
    lignes: List[str] = []
    courante = ""
    for mot in mots:
        essai = (courante + " " + mot).strip()
        if courante and chasse(essai, interlettre) > largeur_max:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    if courante:
        lignes.append(courante)
    return lignes


def cadre(formes: Iterable[Contour]) -> Tuple[float, float, float, float]:
    """(x_min, y_min, x_max, y_max) d'un ensemble de contours."""
    points = [p for contour in formes for p in contour]
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))
