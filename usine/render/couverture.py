"""Composition d'une couverture : une mise en page, deux sorties.

La couverture est d'abord decrite en geometrie — des contours et des
couleurs, en pixels — puis emise deux fois : en PNG pour les places de
marche, qui n'acceptent pas le SVG, et en SVG pour qui veut la retoucher.
Les deux sortent de la meme description, donc la vignette de la fiche de
vente et le fichier source montrent exactement la meme chose.

Le contraste n'est pas decrete, il est calcule. La version precedente
choisissait la couleur du sous-titre dans la palette : sur le fond prune,
le sous-titre etait rose sur rose, illisible sans que rien ne le signale.
Ici la couleur d'encre est retenue par son rapport de contraste avec le
fond mesure a l'endroit ou le texte se pose, et un test refuse toute
combinaison sous 4,5:1 — le seuil WCAG AA.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from . import raster, typo

Couleur = Tuple[int, int, int]
Contour = List[Tuple[float, float]]

BLANC: Couleur = (250, 250, 248)
NOIR: Couleur = (18, 18, 22)


@dataclass
class Palette:
    nom: str
    haut: Couleur
    bas: Couleur
    accent: Couleur


def _h(code: str) -> Couleur:
    return raster.couleur_hex(code)


PALETTES: List[Palette] = [
    Palette("nuit", _h("#0b1020"), _h("#1e2a4a"), _h("#f4b942")),
    Palette("encre", _h("#101418"), _h("#2c333c"), _h("#e8503a")),
    Palette("foret", _h("#07241e"), _h("#164a3c"), _h("#e9d8a6")),
    Palette("prune", _h("#260c2a"), _h("#511b48"), _h("#f2a0c4")),
    Palette("acier", _h("#0e2032"), _h("#274a68"), _h("#7fd1d1")),
    Palette("safran", _h("#33170a"), _h("#6b2f0c"), _h("#f2c14e")),
    Palette("argile", _h("#f6f0e7"), _h("#ded0bc"), _h("#b4462f")),
    Palette("menthe", _h("#f3f8f6"), _h("#d3e6df"), _h("#0f5c49")),
]

MODELES = ("bandeau", "centre", "diagonale", "arcs", "bloc")


# --------------------------------------------------------------------------
# Contraste
# --------------------------------------------------------------------------

def _canal(valeur: int) -> float:
    v = valeur / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(couleur: Couleur) -> float:
    r, v, b = couleur
    return 0.2126 * _canal(r) + 0.7152 * _canal(v) + 0.0722 * _canal(b)


def contraste(a: Couleur, b: Couleur) -> float:
    """Rapport de contraste WCAG : 1 (identique) a 21 (noir sur blanc)."""
    la, lb = luminance(a), luminance(b)
    clair, sombre = max(la, lb), min(la, lb)
    return (clair + 0.05) / (sombre + 0.05)


def encre_sur(fond: Couleur) -> Couleur:
    """L'encre la plus lisible sur ce fond, mesuree et non supposee."""
    return BLANC if contraste(BLANC, fond) >= contraste(NOIR, fond) else NOIR


# Seuil interne plus exigeant que le seuil teste (4,5:1) : un decor pose
# entre le fond et le texte — un cercle a 30 %, un degrade — deplace le
# contraste de quelques dixiemes. La marge absorbe ce jeu.
SEUIL = 5.2


def encre_lisible(fonds: Sequence[Couleur], souhaitee: Optional[Couleur] = None,
                  opacite: float = 1.0, seuil: float = SEUIL
                  ) -> Tuple[Couleur, float]:
    """Encre lisible sur TOUS les fonds possibles a cet endroit.

    Une couleur d'accent posee sans verification est la faute d'origine :
    le vermillon sur fond creme donne 3,3:1, le rose sur fond prune 1,4:1.
    Le texte etait la, il n'etait pas lisible, et rien ne le signalait.

    « Tous les fonds » compte, parce qu'un decor passe derriere le texte : un
    cercle d'accent a 55 % change ce que le titre recouvre, et raisonner sur
    le seul degrade revient a ignorer ce qu'on vient soi-meme de dessiner.
    """
    candidats: List[Tuple[Couleur, float]] = []
    if souhaitee is not None:
        candidats += [(souhaitee, opacite), (souhaitee, 1.0)]
    candidats += [(BLANC, 1.0), (NOIR, 1.0)]
    meilleur, score = candidats[-1], -1.0
    for couleur, alpha in candidats:
        pire = min(contraste(raster.melanger(fond, couleur, alpha), fond)
                   for fond in fonds)
        if pire >= seuil:
            return (couleur, alpha)
        if pire > score:
            meilleur, score = (couleur, alpha), pire
    return meilleur


# --------------------------------------------------------------------------
# Description d'une couverture
# --------------------------------------------------------------------------

@dataclass
class Couche:
    formes: List[Contour]
    couleur: Couleur
    opacite: float = 1.0
    # « titre », « sous-titre », « auteur », « marque » ou "" pour un decor.
    # Le role permet de rendre la couverture SANS son texte et de mesurer le
    # contraste reel sur les pixels obtenus, fond compose compris — un bloc
    # d'accent derriere le titre ne se devine pas depuis le degrade seul.
    role: str = ""


@dataclass
class Dessin:
    largeur: int
    hauteur: int
    haut: Couleur
    bas: Couleur
    couches: List[Couche] = field(default_factory=list)

    def poser(self, formes: Sequence[Contour], couleur: Couleur,
              opacite: float = 1.0, role: str = "") -> None:
        if formes:
            self.couches.append(
                Couche([list(f) for f in formes], couleur, opacite, role))

    def sans_texte(self) -> "Dessin":
        """Le meme dessin, decor seul. Sert a mesurer ce qu'il y a derriere."""
        return Dessin(self.largeur, self.hauteur, self.haut, self.bas,
                      [c for c in self.couches if not c.role])

    def fond_a(self, y: float) -> Couleur:
        """Couleur du degrade a cette hauteur."""
        t = max(0.0, min(1.0, y / max(1.0, self.hauteur - 1.0)))
        return raster.melanger(self.haut, self.bas, t)

    def fonds_possibles(self, y0: float, y1: float) -> List[Couleur]:
        """Tout ce qu'un texte pose entre ces deux hauteurs peut recouvrir.

        Le degrade, plus chaque decor deja dessine qui traverse la bande.
        C'est volontairement pessimiste : mieux vaut une encre trop sure
        qu'un titre qui disparait sur le seul modele ou un cercle passe
        derriere lui.
        """
        if y1 < y0:
            y0, y1 = y1, y0
        base = [self.fond_a(y0), self.fond_a(y1), self.fond_a((y0 + y1) / 2)]
        fonds = list(base)
        for couche in self.couches:
            if couche.role or couche.opacite <= 0.04:
                continue
            hauteurs = [p[1] for forme in couche.formes for p in forme]
            if not hauteurs or max(hauteurs) < y0 or min(hauteurs) > y1:
                continue
            fonds.extend(raster.melanger(fond, couche.couleur, couche.opacite)
                         for fond in base)
        return fonds

    def rectangle(self, x: float, y: float, largeur: float, hauteur: float,
                  couleur: Couleur, opacite: float = 1.0) -> None:
        self.poser([[(x, y), (x + largeur, y), (x + largeur, y + hauteur),
                     (x, y + hauteur)]], couleur, opacite)


def _echelle(contours_texte: Sequence[Contour], echelle: float,
             x: float, ligne_de_pied: float) -> List[Contour]:
    """Passe des unites de cadratin aux pixels, en retournant l'axe y."""
    return [[(x + px * echelle, ligne_de_pied - py * echelle) for px, py in c]
            for c in contours_texte]


def texte(dessin: Dessin, chaine: str, x: float, ligne_de_pied: float,
          capitale: float, couleur: Couleur, interlettre: float = 0.0,
          ancrage: str = "gauche", opacite: float = 1.0,
          role: str = "titre") -> float:
    """Pose une ligne de texte. Renvoie sa largeur en pixels."""
    chaine = typo.normaliser(chaine)
    if not chaine:
        return 0.0
    echelle = capitale / typo.CAPITALE
    largeur = typo.chasse(chaine, interlettre) * echelle
    if ancrage == "centre":
        x -= largeur / 2.0
    elif ancrage == "droite":
        x -= largeur
    dessin.poser(_echelle(typo.contours(chaine, interlettre), echelle, x,
                          ligne_de_pied), couleur, opacite, role)
    return largeur


def ajuster(chaine: str, largeur_px: float, capitale_max: float,
            lignes_max: int = 4, interlettre: float = 0.0,
            capitale_min: float = 0.0) -> Tuple[List[str], float]:
    """Plus grand corps auquel le titre tient dans la largeur donnee.

    Cherche du plus grand au plus petit plutot que l'inverse : un titre court
    doit occuper la couverture, un titre long doit rester lisible, et les deux
    sortent de la meme regle.
    """
    chaine = typo.normaliser(chaine)
    if not chaine:
        return ([], capitale_max)
    # Le plancher est PROPORTIONNEL au corps demande, pas exprime en pixels :
    # une couverture de vignette et une couverture pleine doivent se composer
    # pareil. Un plancher absolu de 18 px laissait le titre deborder de la
    # page des qu'on rendait petit — le texte existait, il n'etait plus sur
    # l'image.
    plancher = capitale_min or capitale_max * 0.18
    capitale = capitale_max
    while capitale > plancher:
        echelle = capitale / typo.CAPITALE
        lignes = typo.couper(chaine, largeur_px / echelle, interlettre)
        if len(lignes) <= lignes_max and all(
                typo.chasse(l, interlettre) * echelle <= largeur_px
                for l in lignes):
            return (lignes, capitale)
        capitale -= max(1.0, capitale_max / 40.0)
    return (typo.couper(chaine, largeur_px / (plancher / typo.CAPITALE),
                        interlettre), plancher)


# --------------------------------------------------------------------------
# Formes d'appui
# --------------------------------------------------------------------------

def _cercle(cx: float, cy: float, rayon: float, epaisseur: float = 0.0,
            a0: float = 0.0, a1: float = 360.0) -> Contour:
    import math
    epaisseur = epaisseur or rayon
    segments = max(8, int(abs(a1 - a0) / 4.0))
    dehors, dedans = [], []
    for i in range(segments + 1):
        angle = math.radians(a0 + (a1 - a0) * i / segments)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        dehors.append((cx + rayon * cos_a, cy + rayon * sin_a))
        dedans.append((cx + (rayon - epaisseur) * cos_a,
                       cy + (rayon - epaisseur) * sin_a))
    return dehors + dedans[::-1]


def _triangle(a, b, c) -> Contour:
    return [a, b, c]


# --------------------------------------------------------------------------
# Les cinq mises en page
# --------------------------------------------------------------------------

def _surtitre(dessin: Dessin, marque: str, x: float, y: float,
              ancrage: str = "gauche", fond: Optional[Couleur] = None) -> None:
    if not marque:
        return
    corps = dessin.hauteur * 0.0115
    fonds = ([fond] if fond is not None
             else dessin.fonds_possibles(y - corps, y))
    # Opaque, et pas par gout : ces petites capitales espacees ont des fûts
    # d'environ un pixel et demi. L'anticrenelage ne les couvre jamais
    # entierement, si bien qu'une opacite de 0,85 devient 0,72 a l'ecran et
    # fait passer le contraste sous le seuil. La transparence coute ici plus
    # qu'elle ne rapporte.
    couleur, _ = encre_lisible(fonds)
    texte(dessin, marque, x, y, corps, couleur,
          interlettre=260, ancrage=ancrage, role="marque")


def _pied(dessin: Dessin, auteur: str, x: float, ancrage: str = "gauche",
          y: float = 0.0, fond: Optional[Couleur] = None) -> None:
    if not auteur:
        return
    y = y or dessin.hauteur * 0.925
    corps = dessin.hauteur * 0.0135
    fonds = ([fond] if fond is not None
             else dessin.fonds_possibles(y - corps, y))
    couleur, _ = encre_lisible(fonds)
    texte(dessin, auteur, x, y, corps, couleur,
          interlettre=200, ancrage=ancrage, role="auteur")


def _bloc_titre(dessin: Dessin, titre: str, sous_titre: str, x: float,
                sommet: float, largeur: float, hauteur_dispo: float,
                accent: Couleur, ancrage: str = "gauche",
                capitale_max: float = 0.0) -> float:
    """Titre puis sous-titre, garantis a l'interieur du cadre donne.

    Le corps est reduit jusqu'a ce que l'ENSEMBLE tienne — titre et
    sous-titre ensemble, en largeur comme en hauteur. Ajuster le seul titre
    laissait le sous-titre deborder sous le bord de la page : le texte etait
    la, mais il n'etait pas sur l'image.
    """
    # Plafond volontairement haut : un titre de quatre lettres doit occuper
    # la couverture, un titre de douze mots doit rester lisible. C'est la
    # reduction qui arbitre, pas une taille fixe choisie pour le cas moyen.
    capitale = capitale_max or dessin.hauteur * 0.105
    plancher = dessin.hauteur * 0.012
    petit_min = dessin.hauteur * 0.0105
    while True:
        lignes, capitale = ajuster(titre, largeur, capitale, lignes_max=4,
                                   capitale_min=plancher)
        petit = max(petit_min, min(dessin.hauteur * 0.0165, capitale * 0.30))
        lignes_sous = typo.couper(typo.normaliser(sous_titre),
                                  largeur / (petit / typo.CAPITALE), 130)[:3] \
            if sous_titre else []
        total = len(lignes) * capitale * 1.24
        if lignes_sous:
            total += capitale * 0.34 + len(lignes_sous) * petit * 1.85
        if total <= hauteur_dispo or capitale <= plancher:
            break
        capitale -= max(1.0, dessin.hauteur / 400.0)

    # Dernier garde-fou : si meme au plancher l'ensemble ne rentre pas, le
    # sous-titre saute. Un sous-titre imprime sous le bord de la page n'est
    # pas un sous-titre, c'est un defaut invisible au moment ou on le cree.
    if lignes_sous and (len(lignes) * capitale * 1.24 + capitale * 0.34
                        + len(lignes_sous) * petit * 1.85) > hauteur_dispo:
        place = hauteur_dispo - len(lignes) * capitale * 1.24 - capitale * 0.34
        lignes_sous = lignes_sous[:max(0, int(place / (petit * 1.85)))]

    y = sommet + capitale
    for ligne in lignes:
        encre, _ = encre_lisible(dessin.fonds_possibles(y - capitale, y))
        texte(dessin, ligne, x, y, capitale, encre, ancrage=ancrage,
              role="titre")
        y += capitale * 1.24
    if lignes_sous:
        y += capitale * 0.34
        for ligne in lignes_sous:
            couleur, opacite = encre_lisible(
                dessin.fonds_possibles(y - petit, y), accent)
            texte(dessin, ligne, x, y, petit, couleur, interlettre=130,
                  ancrage=ancrage, opacite=opacite, role="sous-titre")
            y += petit * 1.85
    return y


def _modele_bandeau(d: Dessin, p: Palette, titre, sous_titre, auteur,
                    marque) -> None:
    marge = d.largeur * 0.088
    d.poser([_cercle(d.largeur * 0.88, d.hauteur * 0.17, d.largeur * 0.42,
                     d.largeur * 0.012)], p.accent, 0.30)
    _surtitre(d, marque, marge, d.hauteur * 0.085)
    d.rectangle(marge, d.hauteur * 0.355, d.largeur * 0.17,
                max(4.0, d.hauteur * 0.006), p.accent)
    _bloc_titre(d, titre, sous_titre, marge, d.hauteur * 0.40,
                d.largeur - 2 * marge, d.hauteur * 0.46, p.accent)
    _pied(d, auteur, marge)


def _modele_centre(d: Dessin, p: Palette, titre, sous_titre, auteur,
                   marque) -> None:
    marge = d.largeur * 0.11
    milieu = d.largeur / 2.0
    d.poser([_cercle(milieu, d.hauteur * 0.44, d.largeur * 0.36,
                     d.largeur * 0.010)], p.accent, 0.30)
    _surtitre(d, marque, milieu, d.hauteur * 0.095, ancrage="centre")
    d.rectangle(milieu - d.largeur * 0.06, d.hauteur * 0.275,
                d.largeur * 0.12, max(3.0, d.hauteur * 0.0042), p.accent)
    bas = _bloc_titre(d, titre, sous_titre, milieu, d.hauteur * 0.315,
                      d.largeur - 2 * marge, d.hauteur * 0.50, p.accent,
                      ancrage="centre")
    d.rectangle(milieu - d.largeur * 0.06, bas + d.hauteur * 0.012,
                d.largeur * 0.12, max(3.0, d.hauteur * 0.0042), p.accent)
    _pied(d, auteur, milieu, ancrage="centre")


def _modele_diagonale(d: Dessin, p: Palette, titre, sous_titre, auteur,
                      marque) -> None:
    marge = d.largeur * 0.088
    d.poser([_triangle((d.largeur, 0), (d.largeur, d.hauteur * 0.52),
                       (d.largeur * 0.18, 0))], p.accent, 0.90)
    d.poser([_triangle((d.largeur, d.hauteur * 0.54),
                       (d.largeur, d.hauteur * 0.60),
                       (d.largeur * 0.46, d.hauteur * 0.335))], p.accent, 0.45)
    _bloc_titre(d, titre, sous_titre, marge, d.hauteur * 0.585,
                d.largeur - 2 * marge, d.hauteur * 0.25, p.accent,
                capitale_max=d.hauteur * 0.066)
    _surtitre(d, marque, marge, d.hauteur * 0.545)
    _pied(d, auteur, marge)


def _modele_arcs(d: Dessin, p: Palette, titre, sous_titre, auteur,
                 marque) -> None:
    marge = d.largeur * 0.088
    # Ces cercles passent derriere le sous-titre et la signature. Au-dela
    # d'environ 30 % d'opacite, un accent clair sur fond sombre fait tomber
    # le contraste du texte sous le seuil — et aucune encre ne rattrape un
    # fond qui change sous les lettres. L'ornement cede le pas.
    cx, cy = d.largeur * 0.84, d.hauteur * 0.84
    for i, rayon in enumerate((0.46, 0.35, 0.24, 0.13)):
        d.poser([_cercle(cx, cy, d.largeur * rayon, d.largeur * 0.014)],
                p.accent, 0.30 - i * 0.05)
    d.poser([_cercle(cx, cy, d.largeur * 0.055)], p.accent, 0.30)
    _surtitre(d, marque, marge, d.hauteur * 0.085)
    _bloc_titre(d, titre, sous_titre, marge, d.hauteur * 0.155,
                d.largeur - 2 * marge, d.hauteur * 0.44, p.accent)
    _pied(d, auteur, marge)


def _modele_bloc(d: Dessin, p: Palette, titre, sous_titre, auteur,
                 marque) -> None:
    marge = d.largeur * 0.088
    hauteur_bloc = d.hauteur * 0.30
    d.rectangle(0, 0, d.largeur, hauteur_bloc, p.accent)
    sur_accent = encre_sur(p.accent)
    _surtitre(d, marque or "atelier", marge, hauteur_bloc * 0.32,
              fond=p.accent)
    d.rectangle(marge, hauteur_bloc * 0.50, d.largeur * 0.22,
                max(4.0, d.hauteur * 0.006), sur_accent)
    _pied(d, auteur, marge, y=hauteur_bloc * 0.86, fond=p.accent)
    _bloc_titre(d, titre, sous_titre, marge, hauteur_bloc + d.hauteur * 0.07,
                d.largeur - 2 * marge, d.hauteur * 0.40, p.accent)


_MISES_EN_PAGE = {
    "bandeau": _modele_bandeau, "centre": _modele_centre,
    "diagonale": _modele_diagonale, "arcs": _modele_arcs, "bloc": _modele_bloc,
}


# --------------------------------------------------------------------------
# Entree du module
# --------------------------------------------------------------------------

def _empreinte(graine: str) -> int:
    return int(hashlib.sha256(graine.encode("utf-8")).hexdigest()[:8], 16)


def composer(titre: str, sous_titre: str = "", auteur: str = "",
             marque: str = "", largeur: int = 1200, hauteur: int = 1800,
             palette: Optional[int] = None,
             modele: Optional[int] = None) -> Dessin:
    """Construit la couverture. Le choix de style est fonction du titre.

    Deux appels avec le meme titre donnent la meme couverture : c'est ce qui
    permet de regenerer un produit sans que sa fiche de vente change.
    """
    graine = _empreinte(titre or "usine")
    choix_p = PALETTES[palette % len(PALETTES)] if palette is not None \
        else PALETTES[graine % len(PALETTES)]
    nom_modele = MODELES[modele % len(MODELES)] if modele is not None \
        else MODELES[(graine // 8) % len(MODELES)]
    dessin = Dessin(int(largeur), int(hauteur), choix_p.haut, choix_p.bas)
    _MISES_EN_PAGE[nom_modele](dessin, choix_p, titre, sous_titre, auteur,
                               marque)
    return dessin


def toile(dessin: Dessin, compression: int = 6) -> raster.Toile:
    surface = raster.Toile(dessin.largeur, dessin.hauteur, dessin.haut)
    surface.degrade_vertical(dessin.haut, dessin.bas)
    for couche in dessin.couches:
        surface.remplir(couche.formes, couche.couleur, couche.opacite)
    return surface


def png(dessin: Dessin, compression: int = 6) -> bytes:
    return toile(dessin).png(compression)


def _rvb(couleur: Couleur) -> str:
    return "#{:02x}{:02x}{:02x}".format(*couleur)


def svg(dessin: Dessin) -> str:
    morceaux = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}">'.format(w=dessin.largeur, h=dessin.hauteur),
        '<defs><linearGradient id="f" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="{}"/><stop offset="1" stop-color="{}"/>'
        '</linearGradient></defs>'.format(_rvb(dessin.haut), _rvb(dessin.bas)),
        '<rect width="{}" height="{}" fill="url(#f)"/>'.format(
            dessin.largeur, dessin.hauteur),
    ]
    for couche in dessin.couches:
        formes, couleur, opacite = couche.formes, couche.couleur, couche.opacite
        chemin = []
        for contour in formes:
            if len(contour) < 3:
                continue
            chemin.append("M" + " L".join(
                "{:.1f} {:.1f}".format(x, y) for x, y in contour) + " Z")
        if not chemin:
            continue
        morceaux.append(
            '<path d="{}" fill="{}" fill-rule="nonzero"{}/>'.format(
                " ".join(chemin), _rvb(couleur),
                ' fill-opacity="{:.2f}"'.format(opacite) if opacite < 1 else ""))
    morceaux.append("</svg>")
    return "".join(morceaux)
