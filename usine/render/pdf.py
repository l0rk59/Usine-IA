"""Generateur PDF ecrit entierement en Python standard.

Suffisant pour un ebook vendable : couverture, sommaire, titres, paragraphes,
listes, citations, encadres, pieds de page numerotes et images JPEG.
Aucune compilation requise : installable sur Termux en une seconde.
"""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import List, Optional, Tuple

from .metriques import largeur_texte

A4 = (595.28, 841.89)
LETTRE = (612.0, 792.0)

POLICES_PDF = {
    "Helvetica": "F1",
    "Helvetica-Bold": "F2",
    "Helvetica-Oblique": "F3",
    "Times-Roman": "F4",
    "Times-Bold": "F5",
    "Times-Italic": "F6",
}


def _echapper(texte: str) -> bytes:
    """Encode en WinAnsi et protege les caracteres speciaux PDF."""
    remplacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " ",
        "•": "-", "→": "->", "≥": ">=", "≤": "<=", "×": "x",
    }
    for source, cible in remplacements.items():
        texte = texte.replace(source, cible)
    brut = texte.encode("cp1252", "replace")
    return brut.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def dimensions_jpeg(brut: bytes) -> Optional[Tuple[int, int, int]]:
    """(largeur, hauteur, composantes) d'un JPEG, ou None si illisible."""
    if brut[:2] != b"\xff\xd8":
        return None
    i = 2
    taille = len(brut)
    while i < taille - 9:
        if brut[i] != 0xFF:
            i += 1
            continue
        marqueur = brut[i + 1]
        if marqueur in (0xD8, 0xD9) or 0xD0 <= marqueur <= 0xD7:
            i += 2
            continue
        longueur = int.from_bytes(brut[i + 2 : i + 4], "big")
        if marqueur in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            hauteur = int.from_bytes(brut[i + 5 : i + 7], "big")
            largeur = int.from_bytes(brut[i + 7 : i + 9], "big")
            composantes = brut[i + 9]
            return largeur, hauteur, composantes
        i += 2 + longueur
    return None


class DocumentPDF:
    """Construction sequentielle d'un PDF, page apres page."""

    def __init__(
        self,
        format_page: Tuple[float, float] = A4,
        marge: float = 62.0,
        police_corps: str = "Times-Roman",
        police_titre: str = "Helvetica-Bold",
        titre_courant: str = "",
    ):
        self.largeur, self.hauteur = format_page
        self.marge = marge
        self.police_corps = police_corps
        self.police_titre = police_titre
        self.titre_courant = titre_courant

        self._pages: List[Tuple[List[str], bool]] = []
        self._flux: List[str] = []
        self._images: List[Tuple[str, bytes, int, int, int]] = []
        self._y = self.hauteur - marge
        self._numeroter = True
        self._page_ouverte = False
        self.sommaire: List[Tuple[str, int, int]] = []  # (titre, niveau, page)

    # -- geometrie -------------------------------------------------------
    @property
    def largeur_utile(self) -> float:
        return self.largeur - 2 * self.marge

    @property
    def page_courante(self) -> int:
        return len(self._pages) + 1

    def _ouvrir_page(self) -> None:
        if self._page_ouverte:
            return
        self._flux = []
        self._y = self.hauteur - self.marge
        self._page_ouverte = True

    def nouvelle_page(self, numeroter: bool = True) -> None:
        self._fermer_page()
        self._numeroter = numeroter
        self._ouvrir_page()

    def _fermer_page(self) -> None:
        if not self._page_ouverte:
            return
        # Les habillages (numero, titre courant) sont ajoutes a l'enregistrement :
        # les pages peuvent encore etre reordonnees d'ici la (insertion du sommaire).
        self._pages.append((self._flux, self._numeroter))
        self._page_ouverte = False
        self._numeroter = True

    def _place(self, hauteur_bloc: float) -> None:
        """Passe a la page suivante si le bloc ne tient pas."""
        if self._y - hauteur_bloc < self.marge + 26:
            self.nouvelle_page()

    def _habillage(self, numero: int) -> List[str]:
        operations: List[str] = []
        libelle_numero = str(numero)
        x = (self.largeur - largeur_texte(libelle_numero, "Helvetica", 9)) / 2
        operations.append(
            "BT /F1 9 Tf 0.45 0.45 0.45 rg 1 0 0 1 {:.2f} {:.2f} Tm ({}) Tj ET".format(
                x, self.marge - 24, libelle_numero
            )
        )
        if self.titre_courant:
            libelle = self.titre_courant[:70]
            lx = (self.largeur - largeur_texte(libelle, "Helvetica", 8)) / 2
            operations.append(
                "BT /F1 8 Tf 0.6 0.6 0.6 rg 1 0 0 1 {:.2f} {:.2f} Tm ({}) Tj ET".format(
                    lx, self.hauteur - self.marge + 22,
                    _echapper(libelle).decode("latin-1"),
                )
            )
        return operations

    # -- primitives de dessin -------------------------------------------
    def _texte(
        self,
        contenu: str,
        x: float,
        y: float,
        police: str,
        taille: float,
        couleur: Tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        self._ouvrir_page()
        self._flux.append(
            "BT /{ref} {t:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm"
            " ({s}) Tj ET".format(
                ref=POLICES_PDF.get(police, "F1"),
                t=taille,
                r=couleur[0], g=couleur[1], b=couleur[2],
                x=x, y=y,
                s=_echapper(contenu).decode("latin-1"),
            )
        )

    def rectangle(
        self,
        x: float,
        y: float,
        largeur: float,
        hauteur: float,
        couleur: Tuple[float, float, float],
        plein: bool = True,
        epaisseur: float = 1.0,
    ) -> None:
        self._ouvrir_page()
        r, v, b = couleur
        if plein:
            self._flux.append(
                "{:.3f} {:.3f} {:.3f} rg {:.2f} {:.2f} {:.2f} {:.2f} re f".format(
                    r, v, b, x, y, largeur, hauteur
                )
            )
        else:
            self._flux.append(
                "{:.3f} {:.3f} {:.3f} RG {:.2f} w {:.2f} {:.2f} {:.2f} {:.2f} re S".format(
                    r, v, b, epaisseur, x, y, largeur, hauteur
                )
            )

    def couper(self, texte: str, police: str, taille: float, largeur: float) -> List[str]:
        """Coupe un paragraphe en lignes tenant dans `largeur` points."""
        lignes: List[str] = []
        for bloc in texte.split("\n"):
            courante = ""
            for mot in bloc.split():
                essai = mot if not courante else courante + " " + mot
                if largeur_texte(essai, police, taille) <= largeur:
                    courante = essai
                    continue
                if courante:
                    lignes.append(courante)
                # Mot plus long que la ligne : on le coupe brutalement
                while largeur_texte(mot, police, taille) > largeur and len(mot) > 1:
                    coupe = len(mot)
                    while coupe > 1 and largeur_texte(mot[:coupe], police, taille) > largeur:
                        coupe -= 1
                    lignes.append(mot[:coupe])
                    mot = mot[coupe:]
                courante = mot
            lignes.append(courante)
        return lignes

    # -- blocs de haut niveau -------------------------------------------
    def paragraphe(
        self,
        texte: str,
        taille: float = 11.0,
        police: Optional[str] = None,
        interligne: float = 1.45,
        espace_apres: float = 9.0,
        retrait: float = 0.0,
        couleur: Tuple[float, float, float] = (0.12, 0.12, 0.14),
        justifier: bool = False,
    ) -> None:
        if not texte.strip():
            return
        police = police or self.police_corps
        self._ouvrir_page()
        largeur = self.largeur_utile - retrait
        lignes = self.couper(texte.strip(), police, taille, largeur)
        pas = taille * interligne
        for index, ligne in enumerate(lignes):
            self._place(pas)
            derniere = index == len(lignes) - 1
            if justifier and not derniere and len(ligne.split()) > 1:
                self._ligne_justifiee(ligne, self.marge + retrait, self._y, police,
                                      taille, largeur, couleur)
            else:
                self._texte(ligne, self.marge + retrait, self._y, police, taille, couleur)
            self._y -= pas
        self._y -= espace_apres

    def _ligne_justifiee(
        self,
        ligne: str,
        x: float,
        y: float,
        police: str,
        taille: float,
        largeur: float,
        couleur: Tuple[float, float, float],
    ) -> None:
        mots = ligne.split()
        naturelle = largeur_texte(ligne, police, taille)
        supplement = (largeur - naturelle) / max(len(mots) - 1, 1)
        if supplement > taille * 0.6:  # evite les lignes trop aerees
            self._texte(ligne, x, y, police, taille, couleur)
            return
        curseur = x
        for i, mot in enumerate(mots):
            self._texte(mot, curseur, y, police, taille, couleur)
            curseur += largeur_texte(mot, police, taille)
            if i < len(mots) - 1:
                curseur += largeur_texte(" ", police, taille) + supplement

    def titre(self, texte: str, niveau: int = 1, sommaire: bool = True) -> None:
        tailles = {1: 24.0, 2: 16.0, 3: 13.0}
        taille = tailles.get(niveau, 12.0)
        if niveau == 1:
            self.nouvelle_page()
            self._y -= 36
        else:
            self._place(taille * 3)
            self._y -= 10
        if sommaire:
            self.sommaire.append((texte, niveau, self.page_courante))
        lignes = self.couper(texte, self.police_titre, taille, self.largeur_utile)
        for ligne in lignes:
            self._place(taille * 1.35)
            self._texte(ligne, self.marge, self._y, self.police_titre, taille,
                        (0.06, 0.09, 0.16))
            self._y -= taille * 1.3
        if niveau == 1:
            self._y -= 4
            self.rectangle(self.marge, self._y, 78, 3, (0.15, 0.5, 0.85))
            self._y -= 22
        else:
            self._y -= 8

    def liste(self, elements: List[str], taille: float = 11.0, puce: str = "-") -> None:
        police = self.police_corps
        for element in elements:
            if not str(element).strip():
                continue
            lignes = self.couper(str(element).strip(), police, taille, self.largeur_utile - 20)
            pas = taille * 1.42
            for index, ligne in enumerate(lignes):
                self._place(pas)
                if index == 0:
                    self._texte(puce, self.marge + 2, self._y, self.police_titre, taille,
                                (0.15, 0.5, 0.85))
                self._texte(ligne, self.marge + 20, self._y, police, taille, (0.12, 0.12, 0.14))
                self._y -= pas
            self._y -= 3
        self._y -= 7

    def citation(self, texte: str, taille: float = 11.0) -> None:
        police = "Times-Italic" if self.police_corps.startswith("Times") else "Helvetica-Oblique"
        lignes = self.couper(texte.strip(), police, taille, self.largeur_utile - 34)
        pas = taille * 1.45
        self._place(pas * len(lignes) + 12)
        haut = self._y + taille
        for ligne in lignes:
            self._place(pas)
            self._texte(ligne, self.marge + 26, self._y, police, taille, (0.25, 0.25, 0.3))
            self._y -= pas
        self.rectangle(self.marge + 6, self._y + pas - 4, 3, haut - self._y - pas + 4,
                       (0.15, 0.5, 0.85))
        self._y -= 10

    def encadre(self, titre_bloc: str, texte: str, taille: float = 10.5) -> None:
        lignes = self.couper(texte.strip(), self.police_corps, taille, self.largeur_utile - 40)
        hauteur = 34 + len(lignes) * taille * 1.42
        self._place(hauteur + 10)
        haut = self._y + 8
        self.rectangle(self.marge, haut - hauteur, self.largeur_utile, hauteur,
                       (0.95, 0.965, 1.0))
        self.rectangle(self.marge, haut - hauteur, 4, hauteur, (0.15, 0.5, 0.85))
        self._y = haut - 22
        self._texte(titre_bloc, self.marge + 18, self._y, self.police_titre, taille + 0.5,
                    (0.08, 0.32, 0.6))
        self._y -= taille * 1.7
        for ligne in lignes:
            self._texte(ligne, self.marge + 18, self._y, self.police_corps, taille,
                        (0.15, 0.17, 0.2))
            self._y -= taille * 1.42
        self._y -= 16

    def separateur(self) -> None:
        self._place(24)
        self._y -= 8
        self.rectangle(self.marge + self.largeur_utile / 2 - 28, self._y, 56, 1,
                       (0.75, 0.78, 0.82))
        self._y -= 16

    def espace(self, points: float) -> None:
        self._y -= points

    def lignes_a_remplir(self, nombre: int = 8, ecart: float = 24.0) -> None:
        """Lignes vierges : cahiers d'exercices, plannings, modeles a completer."""
        for _ in range(nombre):
            self._place(ecart)
            self._y -= ecart * 0.72
            self.rectangle(self.marge, self._y, self.largeur_utile, 0.6,
                           (0.82, 0.85, 0.9))
            self._y -= ecart * 0.28

    def cases_a_cocher(self, elements: List[str], taille: float = 11.0) -> None:
        """Liste avec cases a cocher : checklists imprimables."""
        for element in elements:
            texte = str(element).strip()
            if not texte:
                continue
            lignes = self.couper(texte, self.police_corps, taille, self.largeur_utile - 30)
            pas = taille * 1.45
            self._place(pas * len(lignes) + 6)
            self.rectangle(self.marge + 1, self._y - 1, 10.5, 10.5,
                           (0.35, 0.42, 0.55), plein=False, epaisseur=0.9)
            for index, ligne in enumerate(lignes):
                self._place(pas)
                self._texte(ligne, self.marge + 22, self._y, self.police_corps, taille,
                            (0.12, 0.12, 0.14))
                self._y -= pas
            self._y -= 4
        self._y -= 8

    def tableau(
        self,
        entetes: List[str],
        lignes: List[List[str]],
        taille: float = 9.5,
        lignes_vides: int = 0,
    ) -> None:
        """Tableau a colonnes egales, avec en-tete colore et lignes a remplir."""
        colonnes = max(len(entetes), 1)
        largeur_col = self.largeur_utile / colonnes
        hauteur_ligne = taille * 2.1

        def dessiner_entete() -> None:
            self._place(hauteur_ligne * 2)
            self.rectangle(self.marge, self._y - hauteur_ligne + taille,
                           self.largeur_utile, hauteur_ligne, (0.09, 0.36, 0.72))
            for index, entete in enumerate(entetes):
                libelle = self._tronquer(str(entete), self.police_titre, taille,
                                         largeur_col - 10)
                self._texte(libelle, self.marge + index * largeur_col + 5, self._y,
                            self.police_titre, taille, (1, 1, 1))
            self._y -= hauteur_ligne

        dessiner_entete()
        toutes = [[str(c) for c in ligne] for ligne in lignes]
        toutes += [[""] * colonnes for _ in range(max(0, lignes_vides))]
        for numero, ligne in enumerate(toutes):
            if self._y - hauteur_ligne < self.marge + 26:
                self.nouvelle_page()
                dessiner_entete()
            if numero % 2 == 1:
                self.rectangle(self.marge, self._y - hauteur_ligne + taille,
                               self.largeur_utile, hauteur_ligne, (0.96, 0.97, 0.99))
            for index in range(colonnes):
                cellule = ligne[index] if index < len(ligne) else ""
                if cellule:
                    self._texte(
                        self._tronquer(cellule, self.police_corps, taille,
                                       largeur_col - 10),
                        self.marge + index * largeur_col + 5, self._y,
                        self.police_corps, taille, (0.12, 0.12, 0.14),
                    )
                self.rectangle(self.marge + index * largeur_col,
                               self._y - hauteur_ligne + taille, 0.5, hauteur_ligne,
                               (0.85, 0.88, 0.92))
            self.rectangle(self.marge, self._y - hauteur_ligne + taille,
                           self.largeur_utile, 0.5, (0.85, 0.88, 0.92))
            self._y -= hauteur_ligne
        self.rectangle(self.marge + self.largeur_utile - 0.5,
                       self._y + taille, 0.5, 0, (0.85, 0.88, 0.92))
        self._y -= 14

    def _tronquer(self, texte: str, police: str, taille: float,
                  largeur: float) -> str:
        if largeur_texte(texte, police, taille) <= largeur:
            return texte
        coupe = len(texte)
        while coupe > 1 and largeur_texte(texte[:coupe] + "...", police,
                                          taille) > largeur:
            coupe -= 1
        return texte[:coupe] + "..."

    def grille(self, colonnes: int = 7, rangees: int = 5, hauteur: float = 0,
               titres: Optional[List[str]] = None) -> None:
        """Grille vierge : planning hebdomadaire, calendrier, tableau de suivi."""
        hauteur = hauteur or min(72.0, (self._y - self.marge - 40) / max(rangees, 1))
        largeur_col = self.largeur_utile / max(colonnes, 1)
        total = hauteur * rangees + (18 if titres else 0)
        self._place(total + 12)
        if titres:
            for index in range(colonnes):
                libelle = titres[index] if index < len(titres) else ""
                if libelle:
                    largeur = largeur_texte(libelle, self.police_titre, 9)
                    self._texte(libelle,
                                self.marge + index * largeur_col
                                + (largeur_col - largeur) / 2,
                                self._y, self.police_titre, 9, (0.25, 0.3, 0.4))
            self._y -= 16
        haut = self._y + 8
        bas = haut - hauteur * rangees
        for index in range(colonnes + 1):
            self.rectangle(self.marge + index * largeur_col, bas, 0.6,
                           hauteur * rangees, (0.8, 0.84, 0.9))
        for rangee in range(rangees + 1):
            self.rectangle(self.marge, bas + rangee * hauteur, self.largeur_utile,
                           0.6, (0.8, 0.84, 0.9))
        self._y = bas - 16

    def points(self, espacement: float = 16.0, hauteur: float = 0) -> None:
        """Fond pointille : pages de notes libres, bullet journal."""
        hauteur = hauteur or (self._y - self.marge - 20)
        if hauteur < espacement:
            return
        haut = self._y
        y = haut
        while y > haut - hauteur:
            x = self.marge
            while x < self.marge + self.largeur_utile:
                self.rectangle(x, y, 1.1, 1.1, (0.74, 0.78, 0.84))
                x += espacement
            y -= espacement
        self._y = haut - hauteur - 10

    # -- pages speciales -------------------------------------------------
    def page_couverture(
        self,
        titre_livre: str,
        sous_titre: str = "",
        auteur: str = "",
        image_jpeg: Optional[bytes] = None,
        accent: Tuple[float, float, float] = (0.09, 0.36, 0.72),
    ) -> None:
        self.nouvelle_page(numeroter=False)
        self.rectangle(0, 0, self.largeur, self.hauteur, (0.05, 0.07, 0.12))
        self.rectangle(0, self.hauteur - 14, self.largeur, 14, accent)

        haut_texte = self.hauteur - 210
        if image_jpeg:
            infos = dimensions_jpeg(image_jpeg)
            if infos:
                nom = self._ajouter_image(image_jpeg, infos)
                cote = self.largeur * 0.52
                ratio = infos[1] / max(infos[0], 1)
                self._flux.append(
                    "q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{n} Do Q".format(
                        w=cote, h=cote * ratio,
                        x=(self.largeur - cote) / 2,
                        y=self.hauteur - 190 - cote * ratio,
                        n=nom,
                    )
                )
                haut_texte = self.hauteur - 210 - cote * ratio

        self._y = haut_texte
        for ligne in self.couper(titre_livre, "Helvetica-Bold", 30, self.largeur_utile - 40)[:5]:
            largeur = largeur_texte(ligne, "Helvetica-Bold", 30)
            self._texte(ligne, (self.largeur - largeur) / 2, self._y, "Helvetica-Bold", 30,
                        (1, 1, 1))
            self._y -= 38
        if sous_titre:
            self._y -= 14
            for ligne in self.couper(sous_titre, "Helvetica", 14, self.largeur_utile - 80)[:3]:
                largeur = largeur_texte(ligne, "Helvetica", 14)
                self._texte(ligne, (self.largeur - largeur) / 2, self._y, "Helvetica", 14,
                            (0.62, 0.78, 0.95))
                self._y -= 21
        if auteur:
            largeur = largeur_texte(auteur, "Helvetica", 13)
            self._texte(auteur, (self.largeur - largeur) / 2, self.marge + 46, "Helvetica", 13,
                        (0.8, 0.84, 0.9))
        self.rectangle(0, 0, self.largeur, 10, accent)

    def inserer_sommaire(self, intitule: str = "Sommaire", apres: int = 1) -> None:
        """Construit le sommaire et le place juste apres la couverture.

        Deux passes : la premiere mesure le nombre de pages qu'il occupe, la
        seconde decale les numeros en consequence. Sans cela le sommaire
        renverrait a des pages fausses des qu'il depasse une page.
        """
        self._fermer_page()
        depart = len(self._pages)
        self._rendre_sommaire(intitule, 0)
        nb_pages_sommaire = len(self._pages) - depart
        del self._pages[depart:]

        self._rendre_sommaire(intitule, nb_pages_sommaire)
        pages = self._pages[depart:]
        del self._pages[depart:]
        position = max(0, min(apres, len(self._pages)))
        self._pages[position:position] = pages

    def _rendre_sommaire(self, intitule: str, decalage: int) -> None:
        self.nouvelle_page()
        self._y -= 26
        self._texte(intitule, self.marge, self._y, self.police_titre, 24, (0.06, 0.09, 0.16))
        self._y -= 12
        self.rectangle(self.marge, self._y, 78, 3, (0.15, 0.5, 0.85))
        self._y -= 34
        for texte, niveau, page in self.sommaire:
            if niveau > 2:
                continue
            self._place(20)
            police = self.police_titre if niveau == 1 else self.police_corps
            taille = 11.5 if niveau == 1 else 10.5
            retrait = 0 if niveau == 1 else 18
            libelle = texte if len(texte) < 66 else texte[:63] + "..."
            self._texte(libelle, self.marge + retrait, self._y, police, taille,
                        (0.12, 0.12, 0.14))
            numero = str(page + decalage)
            self._texte(numero,
                        self.largeur - self.marge - largeur_texte(numero, police, taille),
                        self._y, police, taille, (0.35, 0.38, 0.45))
            self._y -= 19 if niveau == 1 else 17
        self._fermer_page()

    # -- images ----------------------------------------------------------
    def _ajouter_image(self, brut: bytes, infos: Tuple[int, int, int]) -> str:
        nom = "Im{}".format(len(self._images) + 1)
        self._images.append((nom, brut, infos[0], infos[1], infos[2]))
        return nom

    # -- ecriture du fichier --------------------------------------------
    def enregistrer(self, chemin: Path) -> Path:
        self._fermer_page()
        if not self._pages:
            self.nouvelle_page()
            self._fermer_page()

        objets: List[bytes] = []

        def ajouter(corps: bytes) -> int:
            objets.append(corps)
            return len(objets)  # les numeros d'objet commencent a 1

        nb_pages = len(self._pages)
        # Reservation : 1 catalogue, 2 pages, puis pages et contenus
        num_catalogue = ajouter(b"")
        num_pages = ajouter(b"")

        polices: List[int] = []
        for nom_police, _ref in sorted(POLICES_PDF.items(), key=lambda kv: kv[1]):
            polices.append(
                ajouter(
                    "<< /Type /Font /Subtype /Type1 /BaseFont /{} /Encoding /WinAnsiEncoding >>"
                    .format(nom_police).encode("latin-1")
                )
            )

        images_num: List[Tuple[str, int]] = []
        for nom, brut, larg, haut, comp in self._images:
            espace = "/DeviceRGB" if comp == 3 else ("/DeviceGray" if comp == 1 else "/DeviceCMYK")
            entete = (
                "<< /Type /XObject /Subtype /Image /Width {} /Height {} /ColorSpace {} "
                "/BitsPerComponent 8 /Filter /DCTDecode /Length {} >>\nstream\n"
            ).format(larg, haut, espace, len(brut)).encode("latin-1")
            images_num.append((nom, ajouter(entete + brut + b"\nendstream")))

        refs_pages: List[int] = []
        for index_page, (operations, numeroter) in enumerate(self._pages):
            flux = list(operations)
            if numeroter and index_page > 0:
                flux.extend(self._habillage(index_page + 1))
            contenu = "\n".join(flux).encode("latin-1", "replace")
            comprime = zlib.compress(contenu, 6)
            num_contenu = ajouter(
                "<< /Length {} /Filter /FlateDecode >>\nstream\n".format(len(comprime))
                .encode("latin-1")
                + comprime
                + b"\nendstream"
            )
            ressources_polices = " ".join(
                "/{} {} 0 R".format(ref, polices[i])
                for i, (_, ref) in enumerate(sorted(POLICES_PDF.items(), key=lambda kv: kv[1]))
            )
            ressources_images = " ".join(
                "/{} {} 0 R".format(nom, num) for nom, num in images_num
            )
            xobjets = " /XObject << {} >>".format(ressources_images) if images_num else ""
            page = (
                "<< /Type /Page /Parent {parent} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] "
                "/Resources << /Font << {f} >>{x} >> /Contents {c} 0 R >>"
            ).format(parent=num_pages, w=self.largeur, h=self.hauteur,
                     f=ressources_polices, x=xobjets, c=num_contenu)
            refs_pages.append(ajouter(page.encode("latin-1")))

        objets[num_pages - 1] = (
            "<< /Type /Pages /Count {} /Kids [{}] >>".format(
                nb_pages, " ".join("{} 0 R".format(n) for n in refs_pages)
            ).encode("latin-1")
        )
        objets[num_catalogue - 1] = (
            "<< /Type /Catalog /Pages {} 0 R >>".format(num_pages).encode("latin-1")
        )

        sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        decalages: List[int] = []
        for index, corps in enumerate(objets, start=1):
            decalages.append(len(sortie))
            sortie += "{} 0 obj\n".format(index).encode("latin-1")
            sortie += corps
            sortie += b"\nendobj\n"

        debut_xref = len(sortie)
        sortie += "xref\n0 {}\n".format(len(objets) + 1).encode("latin-1")
        sortie += b"0000000000 65535 f \n"
        for decalage in decalages:
            sortie += "{:010d} 00000 n \n".format(decalage).encode("latin-1")
        sortie += (
            "trailer\n<< /Size {} /Root {} 0 R >>\nstartxref\n{}\n%%EOF\n".format(
                len(objets) + 1, num_catalogue, debut_xref
            ).encode("latin-1")
        )

        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(bytes(sortie))
        return chemin
