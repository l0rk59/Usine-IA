"""Rendu d'images en Python pur : polygones, degrades, encodage PNG.

Le moteur PDF du projet sait incorporer du JPEG (DCTDecode). Il ne sait pas
en fabriquer, et ecrire un encodeur JPEG — DCT, quantification, Huffman —
pour afficher une couverture serait disproportionne.

Ce module prend l'autre chemin, celui que le format PNG et le format PDF
partagent : des pixels bruts compresses par zlib. PNG les range en lignes
prefixees d'un octet de filtre ; PDF les accepte tels quels sous
« /Filter /FlateDecode ». Le meme tampon sert donc aux deux, et zlib est
dans la bibliotheque standard.

Le remplissage suit la regle « nonzero » : deux formes de meme sens
fusionnent au lieu de se percer. C'est ce qui permet de composer une lettre
a partir de traits qui se chevauchent — la jonction du K, le sommet du A —
sans calculer d'union geometrique.
"""

from __future__ import annotations

import binascii
import struct
import zlib
from typing import List, Optional, Sequence, Tuple

Couleur = Tuple[int, int, int]
Point = Tuple[float, float]
Contour = Sequence[Point]

# Nombre de sous-lignes par pixel. 4 suffit : au-dela, la difference n'est
# plus visible et le temps de rendu grimpe lineairement — ce qui se paie sur
# un telephone, pas sur un poste de travail.
SOUS_LIGNES = 4


def couleur_hex(code: str) -> Couleur:
    code = code.lstrip("#")
    if len(code) == 3:
        code = "".join(c * 2 for c in code)
    return (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))


def melanger(a: Couleur, b: Couleur, t: float) -> Couleur:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t + 0.5),
            int(a[1] + (b[1] - a[1]) * t + 0.5),
            int(a[2] + (b[2] - a[2]) * t + 0.5))


class Toile:
    """Une image RVB 8 bits, en memoire, sans dependance."""

    def __init__(self, largeur: int, hauteur: int,
                 fond: Couleur = (255, 255, 255)) -> None:
        self.largeur = int(largeur)
        self.hauteur = int(hauteur)
        self.pas = self.largeur * 3
        self.pixels = bytearray(bytes(fond) * (self.largeur * self.hauteur))

    # --- fonds ------------------------------------------------------------

    def degrade_vertical(self, haut: Couleur, bas: Couleur,
                         courbe: float = 1.0) -> None:
        """Degrade ligne par ligne : chaque ligne est une couleur unie."""
        for y in range(self.hauteur):
            t = (y / max(1, self.hauteur - 1)) ** courbe
            ligne = bytes(melanger(haut, bas, t)) * self.largeur
            self.pixels[y * self.pas:(y + 1) * self.pas] = ligne

    # --- formes -----------------------------------------------------------

    def remplir(self, formes: Sequence[Contour], couleur: Couleur,
                opacite: float = 1.0) -> None:
        """Remplit des contours, regle nonzero, avec anticrenelage."""
        if opacite <= 0.0:
            return
        aretes = self._aretes(formes)
        if not aretes:
            return
        aretes.sort(key=lambda a: a[0])
        y_debut = max(0, int(min(a[0] for a in aretes)))
        y_fin = min(self.hauteur, int(max(a[1] for a in aretes)) + 1)
        actives: List[List[float]] = []
        suivante = 0
        poids = 1.0 / SOUS_LIGNES
        for y in range(y_debut, y_fin):
            while suivante < len(aretes) and aretes[suivante][0] < y + 1:
                actives.append(aretes[suivante])
                suivante += 1
            if actives:
                actives = [a for a in actives if a[1] > y]
            if not actives:
                continue
            couverture = [0.0] * self.largeur
            bornes = [self.largeur, -1]
            for sous in range(SOUS_LIGNES):
                milieu = y + (sous + 0.5) * poids
                croisements = [(a[2] + (milieu - a[0]) * a[3], a[4])
                               for a in actives if a[0] <= milieu < a[1]]
                if not croisements:
                    continue
                croisements.sort()
                enroulement = 0
                depart = 0.0
                for x, sens in croisements:
                    avant = enroulement
                    enroulement += sens
                    if avant == 0 and enroulement != 0:
                        depart = x
                    elif avant != 0 and enroulement == 0:
                        self._segment(couverture, bornes, depart, x, poids)
            if bornes[1] >= bornes[0]:
                self._ecrire(y, couverture, bornes, couleur, opacite)

    def _aretes(self, formes: Sequence[Contour]) -> List[List[float]]:
        aretes: List[List[float]] = []
        for contour in formes:
            nombre = len(contour)
            if nombre < 3:
                continue
            for i in range(nombre):
                x0, y0 = contour[i]
                x1, y1 = contour[(i + 1) % nombre]
                if y0 == y1:
                    continue
                sens = 1
                if y0 > y1:
                    x0, y0, x1, y1 = x1, y1, x0, y0
                    sens = -1
                aretes.append([y0, y1, x0, (x1 - x0) / (y1 - y0), sens])
        return aretes

    def _segment(self, couverture: List[float], bornes: List[int],
                 x0: float, x1: float, poids: float) -> None:
        """Ajoute la couverture d'un segment horizontal, bords compris."""
        if x1 <= x0:
            return
        x0 = max(0.0, x0)
        x1 = min(float(self.largeur), x1)
        if x1 <= x0:
            return
        premier, dernier = int(x0), int(x1 - 1e-9)
        if premier < bornes[0]:
            bornes[0] = premier
        if dernier > bornes[1]:
            bornes[1] = dernier
        if premier == dernier:
            couverture[premier] += (x1 - x0) * poids
            return
        couverture[premier] += (premier + 1 - x0) * poids
        for x in range(premier + 1, dernier):
            couverture[x] += poids
        couverture[dernier] += (x1 - dernier) * poids

    def _ecrire(self, y: int, couverture: List[float], bornes: List[int],
                couleur: Couleur, opacite: float) -> None:
        pixels = self.pixels
        base = y * self.pas
        rouge, vert, bleu = couleur
        for x in range(max(0, bornes[0]), min(self.largeur, bornes[1] + 1)):
            alpha = couverture[x] * opacite
            if alpha <= 0.002:
                continue
            i = base + x * 3
            if alpha >= 0.998:
                pixels[i] = rouge
                pixels[i + 1] = vert
                pixels[i + 2] = bleu
            else:
                inverse = 1.0 - alpha
                pixels[i] = int(pixels[i] * inverse + rouge * alpha + 0.5)
                pixels[i + 1] = int(pixels[i + 1] * inverse + vert * alpha + 0.5)
                pixels[i + 2] = int(pixels[i + 2] * inverse + bleu * alpha + 0.5)

    # --- sorties ----------------------------------------------------------

    def rvb(self) -> bytes:
        """Pixels bruts, pour « /Filter /FlateDecode » cote PDF."""
        return bytes(self.pixels)

    def png(self, compression: int = 6) -> bytes:
        brut = bytearray()
        for y in range(self.hauteur):
            brut.append(0)  # filtre « aucun » : zlib fait le reste
            brut += self.pixels[y * self.pas:(y + 1) * self.pas]
        return _png(self.largeur, self.hauteur,
                    zlib.compress(bytes(brut), compression))

def _bloc(genre: bytes, donnees: bytes) -> bytes:
    corps = genre + donnees
    return (struct.pack(">I", len(donnees)) + corps
            + struct.pack(">I", binascii.crc32(corps) & 0xFFFFFFFF))


def _png(largeur: int, hauteur: int, donnees: bytes) -> bytes:
    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _bloc(b"IHDR", entete)
            + _bloc(b"IDAT", donnees) + _bloc(b"IEND", b""))
