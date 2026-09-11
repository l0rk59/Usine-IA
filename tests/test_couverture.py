"""La couverture : fonte, rendu, contraste, et le format reellement livrable.

Le test qui compte ici est celui du contraste. La version precedente
choisissait la couleur du sous-titre dans la palette, sans jamais la
comparer au fond : sur le fond prune, le sous-titre etait rose sur rose. Le
defaut a survecu a toute la suite parce qu'aucun test ne REGARDAIT l'image.
Ceux-ci la rendent, puis en lisent les pixels.
"""

from __future__ import annotations

import struct
import unittest
import zlib
from pathlib import Path

from usine.render import couverture, raster, typo

TITRE = "La prospection pour freelances"
SOUS_TITRE = "Trouver des clients sans se vendre"
AUTEUR = "Marie Dupont"


class TestFonte(unittest.TestCase):

    def test_chaque_glyphe_a_des_contours_utilisables(self):
        for caractere, (chasse, formes) in typo.TABLE.items():
            self.assertGreater(chasse, 0, "chasse nulle pour {!r}".format(caractere))
            if caractere == " ":
                continue
            self.assertTrue(formes, "aucun contour pour {!r}".format(caractere))
            for contour in formes:
                self.assertGreaterEqual(
                    len(contour), 3,
                    "contour degenere dans {!r}".format(caractere))

    def test_aucun_glyphe_ne_deborde_de_sa_chasse(self):
        """Un glyphe plus large que sa chasse chevaucherait son voisin."""
        for caractere in typo.TABLE:
            chasse, formes = typo.TABLE[caractere]
            if not formes:
                continue
            gauche, _, droite, _ = typo.cadre(formes)
            self.assertGreaterEqual(gauche, -1.0, caractere)
            self.assertLessEqual(droite, chasse + 1.0,
                                 "{!r} deborde de sa chasse".format(caractere))

    def test_les_capitales_atteignent_la_hauteur_annoncee(self):
        """Une lettre plus courte que les autres se verrait immediatement."""
        for lettre in "ABDEFHIKLMNPRTUVWXYZ":
            _, formes = typo.TABLE[lettre]
            _, bas, _, haut = typo.cadre(formes)
            self.assertAlmostEqual(haut, typo.CAPITALE, delta=6.0, msg=lettre)
            self.assertAlmostEqual(bas, 0.0, delta=6.0, msg=lettre)

    def test_les_rondes_depassent_legerement(self):
        """O, C, S debordent volontairement : sinon elles paraissent petites."""
        for lettre in "OCSGQ":
            _, formes = typo.TABLE[lettre]
            _, _, _, haut = typo.cadre(formes)
            self.assertGreaterEqual(haut, typo.CAPITALE - 2.0, lettre)

    def test_les_accents_francais_sont_composes(self):
        for accentuee, base in (("É", "E"), ("À", "A"), ("Ç", "C"),
                                ("Ô", "O"), ("Û", "U"), ("Ê", "E")):
            self.assertEqual(typo.normaliser(accentuee), accentuee)
            self.assertGreater(len(typo.contours(accentuee)),
                               len(typo.contours(base)),
                               "{} n'a pas recu son accent".format(accentuee))

    def test_normaliser_retire_ce_qui_ne_se_dessine_pas(self):
        self.assertEqual(typo.normaliser("Œuf & cie"), "OEUF & CIE")
        self.assertEqual(typo.normaliser("l’ete"), "L'ETE")
        # Un caractere inconnu disparait au lieu de laisser un rectangle noir.
        self.assertEqual(typo.normaliser("a中b"), "AB")
        self.assertEqual(typo.normaliser(""), "")

    def test_la_chasse_annoncee_correspond_au_dessin(self):
        texte = typo.normaliser("METHODE")
        gauche, _, droite, _ = typo.cadre(typo.contours(texte))
        self.assertLessEqual(droite, typo.chasse(texte) + 1.0)
        self.assertGreater(droite, typo.chasse(texte) * 0.85)

    def test_couper_respecte_la_largeur_demandee(self):
        texte = typo.normaliser(
            "Methode complete pour vendre ses prestations sans se trahir")
        lignes = typo.couper(texte, 6000)
        self.assertGreater(len(lignes), 1)
        for ligne in lignes:
            if len(ligne.split()) > 1:
                self.assertLessEqual(typo.chasse(ligne), 6000)
        self.assertEqual(" ".join(lignes), texte, "aucun mot ne doit se perdre")

    def test_un_mot_plus_large_que_la_ligne_reste_entier(self):
        """La cesure n'existe pas ici : c'est le corps qui doit ceder."""
        lignes = typo.couper(typo.normaliser("anticonstitutionnellement"), 900)
        self.assertEqual(lignes, ["ANTICONSTITUTIONNELLEMENT"])


class TestRaster(unittest.TestCase):

    def test_un_carre_se_remplit_la_ou_il_faut(self):
        toile = raster.Toile(20, 20, (255, 255, 255))
        toile.remplir([[(5, 5), (15, 5), (15, 15), (5, 15)]], (0, 0, 0))
        self.assertEqual(self._pixel(toile, 10, 10), (0, 0, 0))
        self.assertEqual(self._pixel(toile, 2, 2), (255, 255, 255))
        self.assertEqual(self._pixel(toile, 17, 10), (255, 255, 255))

    def test_deux_formes_qui_se_chevauchent_fusionnent(self):
        """Regle nonzero : c'est ce qui tient la jonction du K et le sommet du A."""
        toile = raster.Toile(30, 30, (255, 255, 255))
        toile.remplir([[(2, 2), (20, 2), (20, 20), (2, 20)],
                       [(10, 10), (28, 10), (28, 28), (10, 28)]], (0, 0, 0))
        self.assertEqual(self._pixel(toile, 15, 15), (0, 0, 0),
                         "la zone commune doit rester pleine, pas se percer")

    def test_un_anneau_laisse_son_trou(self):
        toile = raster.Toile(60, 60, (255, 255, 255))
        exterieur = [(5, 5), (55, 5), (55, 55), (5, 55)]
        interieur = [(20, 20), (20, 40), (40, 40), (40, 20)]  # sens oppose
        toile.remplir([exterieur, interieur], (0, 0, 0))
        self.assertEqual(self._pixel(toile, 10, 30), (0, 0, 0))
        self.assertEqual(self._pixel(toile, 30, 30), (255, 255, 255),
                         "le contrepoinçon du O doit rester vide")

    def test_le_degrade_va_bien_d_une_couleur_a_l_autre(self):
        toile = raster.Toile(10, 100)
        toile.degrade_vertical((0, 0, 0), (255, 255, 255))
        self.assertEqual(self._pixel(toile, 5, 0), (0, 0, 0))
        self.assertEqual(self._pixel(toile, 5, 99), (255, 255, 255))
        milieu = self._pixel(toile, 5, 50)[0]
        self.assertTrue(120 < milieu < 136, milieu)

    def test_le_png_produit_est_lisible(self):
        toile = raster.Toile(17, 9, (10, 20, 30))
        octets = toile.png()
        self.assertTrue(octets.startswith(b"\x89PNG\r\n\x1a\n"))
        largeur, hauteur, profondeur, couleur = struct.unpack(
            ">IIBB", octets[16:26])
        self.assertEqual((largeur, hauteur, profondeur, couleur), (17, 9, 8, 2))
        self.assertEqual(self._idat(octets),
                         b"".join(b"\x00" + bytes((10, 20, 30)) * 17
                                  for _ in range(9)))

    def test_le_png_se_termine_par_iend(self):
        self.assertTrue(raster.Toile(4, 4).png().endswith(b"IEND\xae\x42\x60\x82"))

    @staticmethod
    def _idat(png: bytes) -> bytes:
        position = 8
        morceaux = b""
        while position < len(png):
            taille = struct.unpack(">I", png[position:position + 4])[0]
            genre = png[position + 4:position + 8]
            if genre == b"IDAT":
                morceaux += png[position + 8:position + 8 + taille]
            position += 12 + taille
        return zlib.decompress(morceaux)

    @staticmethod
    def _pixel(toile, x, y):
        i = y * toile.pas + x * 3
        return tuple(toile.pixels[i:i + 3])


class TestContraste(unittest.TestCase):
    """Le texte doit etre lisible sur ce qui se trouve REELLEMENT derriere."""

    SEUIL = 4.5   # WCAG AA pour du texte normal

    def test_le_calcul_de_contraste_est_juste(self):
        self.assertAlmostEqual(couverture.contraste((0, 0, 0), (255, 255, 255)),
                               21.0, delta=0.01)
        self.assertAlmostEqual(couverture.contraste((7, 7, 7), (7, 7, 7)),
                               1.0, delta=0.001)

    def test_chaque_palette_et_chaque_modele_restent_lisibles(self):
        manques = []
        for index_palette, palette in enumerate(couverture.PALETTES):
            for index_modele, modele in enumerate(couverture.MODELES):
                dessin = couverture.composer(
                    TITRE, SOUS_TITRE, AUTEUR, "Atelier Nord",
                    largeur=300, hauteur=450,
                    palette=index_palette, modele=index_modele)
                for role, mesure in self._mesurer(dessin).items():
                    if mesure < self.SEUIL:
                        manques.append("{}/{} — {} : {:.2f}:1".format(
                            palette.nom, modele, role, mesure))
        self.assertFalse(manques, "contraste insuffisant :\n  "
                                  + "\n  ".join(manques))

    def _mesurer(self, dessin):
        """Contraste par role, mesure sur les pixels rendus.

        On rend deux fois — avec et sans le texte — et on retient les pixels
        que le texte a REELLEMENT changes. On compare alors l'encre posee a
        ce qu'elle recouvre. C'est la seule mesure qui tienne compte d'un
        bloc d'accent ou d'un triangle glisse derriere le titre : le degrade
        seul ne le dirait pas.
        """
        avec = couverture.toile(dessin)
        sans = couverture.toile(dessin.sans_texte())
        resultats = {}
        for couche in dessin.couches:
            if not couche.role:
                continue
            mesure = self._contraste_couche(couche, avec, sans)
            if mesure is not None:
                resultats[couche.role] = min(
                    mesure, resultats.get(couche.role, 99.0))
        return resultats

    @staticmethod
    def _contraste_couche(couche, avec, sans):
        """Encre choisie contre fond reellement rencontre.

        Le fond vient du rendu SANS texte : c'est lui qu'il faut decouvrir,
        parce qu'un bloc d'accent ou un cercle a 30 % ne se devine pas depuis
        la palette. L'encre, elle, est prise telle que la mise en page l'a
        decidee — pas telle que l'anticrenelage la restitue. Mesurer les
        pixels de bord reviendrait a sanctionner l'adoucissement des contours,
        qui est la pour lisser les lettres, pas pour les eclaircir.
        """
        points = [p for contour in couche.formes for p in contour]
        x0 = max(0, int(min(p[0] for p in points)))
        x1 = min(avec.largeur, int(max(p[0] for p in points)) + 1)
        y0 = max(0, int(min(p[1] for p in points)))
        y1 = min(avec.hauteur, int(max(p[1] for p in points)) + 1)
        pire = None
        for y in range(y0, y1):
            base = y * avec.pas
            for x in range(x0, x1):
                i = base + x * 3
                if avec.pixels[i:i + 3] == sans.pixels[i:i + 3]:
                    continue          # le texte n'est pas passe par la
                fond = tuple(sans.pixels[i:i + 3])
                encre = raster.melanger(fond, couche.couleur, couche.opacite)
                mesure = couverture.contraste(encre, fond)
                pire = mesure if pire is None else min(pire, mesure)
        return pire


class TestComposition(unittest.TestCase):

    def test_rien_n_est_dessine_hors_de_la_page(self):
        cas = [
            TITRE,
            "Nego",
            "Methode complete pour vendre ses prestations sans jamais se "
            "trahir ni brader son travail de freelance",
            "ANTICONSTITUTIONNELLEMENT",
            "Éléments de méthode — l'édition 2026",
        ]
        for titre in cas:
            for index in range(len(couverture.MODELES)):
                dessin = couverture.composer(
                    titre, SOUS_TITRE, AUTEUR, "Atelier",
                    largeur=300, hauteur=450, palette=index, modele=index)
                for couche in dessin.couches:
                    if not couche.role:
                        continue   # les decors debordent expres
                    for contour in couche.formes:
                        for x, y in contour:
                            self.assertTrue(
                                -2 <= x <= 302 and -2 <= y <= 452,
                                "{} deborde en {} : ({:.0f}, {:.0f})".format(
                                    couche.role, titre[:22], x, y))

    def test_le_titre_est_reellement_dessine(self):
        dessin = couverture.composer(TITRE, SOUS_TITRE, AUTEUR,
                                     largeur=300, hauteur=450)
        roles = [c.role for c in dessin.couches]
        self.assertIn("titre", roles)
        self.assertIn("sous-titre", roles)
        self.assertIn("auteur", roles)

    def test_un_titre_court_occupe_plus_de_place_qu_un_titre_long(self):
        def hauteur_du_titre(titre):
            dessin = couverture.composer(titre, "", "", largeur=300,
                                         hauteur=450, palette=0, modele=0)
            couche = [c for c in dessin.couches if c.role == "titre"][0]
            ys = [p[1] for contour in couche.formes for p in contour]
            return max(ys) - min(ys)

        self.assertGreater(hauteur_du_titre("Nego"),
                           hauteur_du_titre("Methode complete pour vendre "
                                            "ses prestations sans se trahir"))

    def test_la_meme_entree_donne_la_meme_couverture(self):
        """Regenerer un produit ne doit pas changer sa fiche de vente."""
        premier = couverture.png(couverture.composer(
            TITRE, SOUS_TITRE, AUTEUR, largeur=200, hauteur=300))
        second = couverture.png(couverture.composer(
            TITRE, SOUS_TITRE, AUTEUR, largeur=200, hauteur=300))
        self.assertEqual(premier, second)

    def test_deux_titres_donnent_deux_couvertures(self):
        styles = set()
        for titre in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"):
            dessin = couverture.composer(titre, largeur=80, hauteur=120)
            styles.add((dessin.haut, dessin.bas, len(dessin.couches)))
        self.assertGreater(len(styles), 2,
                           "toutes les couvertures se ressemblent")

    def test_le_svg_est_du_xml_bien_forme(self):
        import xml.etree.ElementTree as ET

        source = couverture.svg(couverture.composer(
            TITRE, SOUS_TITRE, AUTEUR, "Atelier", largeur=200, hauteur=300))
        racine = ET.fromstring(source)
        self.assertTrue(racine.tag.endswith("svg"))
        self.assertEqual(racine.get("width"), "200")

    def test_png_et_svg_decrivent_la_meme_chose(self):
        dessin = couverture.composer(TITRE, SOUS_TITRE, AUTEUR,
                                     largeur=200, hauteur=300)
        source = couverture.svg(dessin)
        chemins = source.count("<path")
        self.assertEqual(chemins, len(dessin.couches))
        self.assertTrue(couverture.png(dessin).startswith(b"\x89PNG"))


class TestIntegration(unittest.TestCase):

    def test_la_couverture_par_defaut_ne_passe_pas_par_le_reseau(self):
        """Le defaut doit etre vendable, donc local, donc sans filigrane.

        C'est le defaut corrige : l'usine appelait Pollinations pour chaque
        couverture, et Pollinations appose « pollinations.ai » sur toute
        image produite sans jeton. Chaque produit sortait avec une couverture
        invendable, dans un module qui documentait par ailleurs pourquoi elle
        l'etait.
        """
        import tempfile

        from usine.core import images

        appels = []

        def interdit(*args, **kwargs):
            appels.append(args)
            raise AssertionError("le reseau ne doit pas etre sollicite")

        origine = images.image_pollinations
        images.image_pollinations = interdit
        try:
            dossier = Path(tempfile.mkdtemp())
            chemin = images.generer_couverture(
                dossier, TITRE, SOUS_TITRE, AUTEUR, en_ligne=True)
        finally:
            images.image_pollinations = origine

        self.assertEqual(appels, [])
        self.assertEqual(chemin.suffix, ".png")
        self.assertTrue(chemin.read_bytes().startswith(b"\x89PNG"))
        self.assertTrue(chemin.with_suffix(".svg").exists(),
                        "le SVG accompagne le PNG, pour qui veut retoucher")

    def test_le_pdf_recoit_les_pixels_exacts_de_la_couverture(self):
        """Aller-retour complet : composition, flux PDF, decompression."""
        import tempfile
        import zlib as z

        from usine.render.pdf import DocumentPDF

        dessin = couverture.composer(TITRE, SOUS_TITRE, AUTEUR,
                                     largeur=120, hauteur=170)
        surface = couverture.toile(dessin)
        document = DocumentPDF()
        document.page_couverture_image(surface.rvb(), surface.largeur,
                                       surface.hauteur)
        document.titre("Un chapitre")
        chemin = document.enregistrer(
            Path(tempfile.mkdtemp()) / "essai.pdf")
        brut = chemin.read_bytes()

        marque = b"/Filter /FlateDecode /Length "
        position = brut.index(b"/Subtype /Image")
        debut = brut.index(marque, position) + len(marque)
        longueur = int(brut[debut:brut.index(b" >>", debut)])
        flux = brut.index(b"stream\n", debut) + 7
        self.assertEqual(z.decompress(brut[flux:flux + longueur]),
                         surface.rvb(),
                         "les pixels du PDF doivent etre ceux de la couverture")
        self.assertIn(b"/Width 120", brut)
        self.assertIn(b"/ColorSpace /DeviceRGB", brut)


if __name__ == "__main__":
    unittest.main()
