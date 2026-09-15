"""Une illustration produite doit arriver dans le produit livre.

Le defaut que ce module garde. La chaine « conte » generait jusqu'a quatorze
illustrations, les enregistrait sur le disque, et n'en livrait aucune : le
markdown « ![](images/page-01.png) » n'etait reconnu par aucun rendu. Il
tombait dans « paragraphe » et sortait imprime tel quel — point
d'exclamation, crochets et parentheses compris — dans le PDF, le HTML,
l'EPUB et le texte brut.

Rien n'echouait. Le markdown etait correct, l'EPUB etait conforme, le PDF
s'ouvrait, et aucune mesure de qualite ne regarde les images. Le defaut ne se
voyait qu'en OUVRANT le livre — ce que personne n'avait fait.
"""

from __future__ import annotations

import re
import sys
import unittest
import zipfile
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


DOSSIER = Path()


def setUpModule():
    global DOSSIER
    DOSSIER = atelier.isoler("illustrations")


from usine.core import llm  # noqa: E402
from usine.render import document as D, pdf as moteur_pdf  # noqa: E402
from usine.render.epub import construire_epub  # noqa: E402
from usine.render.epub_conformite import verifier_epub  # noqa: E402
from tests import simulateur  # noqa: E402


def jpeg_minimal(largeur: int = 64, hauteur: int = 48) -> bytes:
    """Un flux JPEG reduit a ce que le depot en lit.

    Ce qu'il prouve : que le chemin d'incorporation reconnait un JPEG, en
    lit ses dimensions et l'ecrit dans le fichier. Ce qu'il NE prouve PAS :
    qu'un lecteur saurait l'afficher — il n'y a ni table de Huffman ni
    donnee d'image. C'est dit ici plutot que decouvert plus tard : un
    fichier d'essai qu'on croit complet fait passer pour verifie un chemin
    qui ne l'est pas.

    Le construire plutot que le livrer en binaire : le depot n'a aucune
    donnee compilee, et une image d'essai dont personne ne peut relire la
    provenance est exactement le genre de fichier qu'on n'ose plus toucher.
    """
    sof0 = (b"\xff\xc0\x00\x11\x08"
            + hauteur.to_bytes(2, "big") + largeur.to_bytes(2, "big")
            + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01")
    return b"\xff\xd8" + sof0 + b"\xff\xd9"


def flux_du_pdf(chemin: Path) -> str:
    """Le contenu d'un PDF, flux decompresses.

    Chercher une chaine dans les octets bruts ne trouve jamais rien : les
    flux de contenu sont compresses par Flate.
    """
    morceaux = []
    for flux in re.findall(rb"stream\r?\n(.*?)\r?\nendstream",
                           chemin.read_bytes(), re.DOTALL):
        try:
            morceaux.append(zlib.decompress(flux).decode("latin-1"))
        except zlib.error:
            morceaux.append(flux.decode("latin-1", "replace"))
    return "\n".join(morceaux)


class LeModeleDeDocumentReconnaitUneImage(unittest.TestCase):
    """Le point exact ou le defaut entrait : « analyser » ne voyait rien."""

    MD = "Le petit ours dort.\n\n![un ourson roule en boule](images/page-01.jpg)"

    def test_une_image_seule_sur_sa_ligne_devient_un_bloc_image(self):
        blocs = D.analyser(self.MD)
        types = [b.type for b in blocs]
        self.assertEqual(types, ["p", "image"])
        self.assertEqual(blocs[1].url, "images/page-01.jpg")
        self.assertEqual(blocs[1].texte, "un ourson roule en boule")

    def test_un_lien_ordinaire_ne_devient_pas_une_image(self):
        # Le detecteur lit le point d'exclamation. Sans lui, « [voir](a.html) »
        # deviendrait une image — un garde-fou qui se trompe finit ignore.
        blocs = D.analyser("[voir la carte](carte.html)")
        self.assertEqual([b.type for b in blocs], ["p"])

    def test_le_texte_brut_annonce_l_illustration_au_lieu_du_chemin(self):
        sortie = D.vers_texte(D.analyser(self.MD))
        self.assertIn("[Illustration : un ourson roule en boule]", sortie)
        self.assertNotIn("images/page-01.jpg", sortie)

    def test_le_html_porte_une_balise_image_et_son_texte_de_remplacement(self):
        sortie = D.vers_html(D.analyser(self.MD))
        self.assertIn('<img src="images/page-01.jpg"', sortie)
        self.assertIn('alt="un ourson roule en boule"', sortie)
        self.assertNotIn("![", sortie)

    def test_le_pdf_n_imprime_jamais_le_chemin_du_fichier(self):
        doc = moteur_pdf.DocumentPDF()
        D.vers_pdf(D.analyser(self.MD), doc)
        chemin = DOSSIER / "chemin.pdf"
        doc.enregistrer(chemin)
        contenu = flux_du_pdf(chemin)
        self.assertIn("Le petit ours dort.", contenu)
        self.assertNotIn("images/page-01.jpg", contenu)
        self.assertIn("un ourson roule en boule", contenu)


class LeMoteurPdfPlaceUneImageOuDitQuIlNAPasPu(unittest.TestCase):
    """Le faux n'est pas un detail : c'est ce qui laisse sortir le livre."""

    def test_un_jpeg_entre_dans_le_document(self):
        doc = moteur_pdf.DocumentPDF()
        doc.paragraphe("avant")
        self.assertTrue(doc.image(jpeg_minimal()))
        chemin = DOSSIER / "avec-image.pdf"
        doc.enregistrer(chemin)
        brut = chemin.read_bytes()
        self.assertIn(b"/Subtype /Image", brut)
        self.assertIn(b"/Filter /DCTDecode", brut)
        # L'operateur de dessin, sans lequel l'image serait dans le fichier
        # sans etre sur la page.
        self.assertIn("/Im1 Do", flux_du_pdf(chemin))

    def test_les_dimensions_declarees_sont_celles_du_jpeg(self):
        doc = moteur_pdf.DocumentPDF()
        doc.image(jpeg_minimal(90, 30))
        chemin = DOSSIER / "dimensions.pdf"
        doc.enregistrer(chemin)
        brut = chemin.read_bytes().decode("latin-1", "replace")
        self.assertIn("/Width 90 /Height 30", brut)

    def test_un_png_est_refuse_sans_exception(self):
        # Le moteur n'a pas de decodeur PNG. Il doit le dire a l'appelant,
        # pas lever : l'appelant ecrit sa note d'illustration et le livre sort.
        doc = moteur_pdf.DocumentPDF()
        self.assertFalse(doc.image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64))
        self.assertFalse(doc.image(b""))

    def test_une_image_haute_est_ramenee_dans_la_page(self):
        doc = moteur_pdf.DocumentPDF()
        doc.image(jpeg_minimal(100, 10000))
        chemin = DOSSIER / "haute.pdf"
        doc.enregistrer(chemin)
        # « cm » porte l'echelle : largeur, 0, 0, hauteur. La hauteur dessinee
        # doit tenir sous la hauteur de page, sinon l'image deborde en
        # silence — le PDF s'ouvre quand meme.
        echelles = re.findall(r"q ([\d.]+) 0 0 ([\d.]+) ", flux_du_pdf(chemin))
        self.assertTrue(echelles)
        self.assertLess(float(echelles[0][1]), doc.hauteur)


class LesIllustrationsEntrentDansLEpub(unittest.TestCase):
    """Un EPUB est une archive fermee : une image absente ne s'affiche pas."""

    def _construire(self, ressources):
        chemin = DOSSIER / "album.epub"
        construire_epub(
            chemin, "Album", "Usine-IA",
            [("Page 1", '<p><img src="images/p1.jpg" alt="un ours"/></p>')],
            ressources=ressources)
        return chemin

    def test_la_ressource_est_dans_le_conteneur_et_dans_le_manifeste(self):
        chemin = self._construire([("images/p1.jpg", jpeg_minimal())])
        with zipfile.ZipFile(chemin) as archive:
            self.assertIn("OEBPS/images/p1.jpg", archive.namelist())
            opf = next(n for n in archive.namelist() if n.endswith(".opf"))
            manifeste = archive.read(opf).decode("utf-8")
        self.assertIn('href="images/p1.jpg" media-type="image/jpeg"', manifeste)
        self.assertTrue(verifier_epub(chemin).conforme)

    def test_le_type_declare_suit_l_extension(self):
        chemin = self._construire([("images/p1.jpg", jpeg_minimal()),
                                   ("images/p2.png", b"\x89PNG\r\n\x1a\n"),
                                   ("images/p3.webp", b"RIFF0000WEBP")])
        with zipfile.ZipFile(chemin) as archive:
            opf = next(n for n in archive.namelist() if n.endswith(".opf"))
            manifeste = archive.read(opf).decode("utf-8")
        for nom, mime in (("p1.jpg", "image/jpeg"), ("p2.png", "image/png"),
                          ("p3.webp", "image/webp")):
            self.assertIn('href="images/{}" media-type="{}"'.format(nom, mime),
                          manifeste)


class UnAlbumNEstPasUnGuide(unittest.TestCase):
    """La mise en page vue en ouvrant le PDF, pas celle du markdown."""

    @classmethod
    def setUpClass(cls):
        from usine.pipelines import base, conte
        llm.definir_simulateur(simulateur.simulateur)
        try:
            contexte = base.Contexte(sujet="un ourson qui perd son doudou",
                                     sans_image=True, journal=lambda m: None)
            cls.resume = conte.produire(contexte, pages=6, tranche="3-5 ans")
        finally:
            llm.definir_simulateur(None)
        cls.dossier = Path(cls.resume["dossier"])
        cls.pdf = next(f for f in cls.dossier.glob("*.pdf"))

    def test_une_page_de_pdf_par_double_page_et_rien_de_plus(self):
        # Couverture + six doubles-pages. Sept, pas huit : le sommaire d'un
        # album — « Page 1 »... « Page 6 » — ne renseigne personne, et une
        # page « Sommaire » vide sortait tant que personne ne regardait.
        pages = len(re.findall(rb"/Type\s*/Page[^s]", self.pdf.read_bytes()))
        self.assertEqual(pages, self.resume["pages"] + 1)

    def test_aucun_titre_de_chapitre_au_dessus_du_recit(self):
        contenu = flux_du_pdf(self.pdf)
        self.assertNotIn("Sommaire", contenu)
        # « Page 1 » reste le titre du chapitre dans le markdown, le HTML et
        # l'EPUB, qui en ont besoin pour naviguer. Dans le PDF il sortait en
        # vingt-quatre points au-dessus d'une seule phrase.
        self.assertNotIn("(Page 1)", contenu)
        self.assertIn("Page 1", (self.dossier / "conte.md").read_text(
            encoding="utf-8"))

    def test_la_note_d_illustration_ne_se_lit_pas_comme_le_recit(self):
        contenu = flux_du_pdf(self.pdf)
        self.assertIn("Illustration a dessiner", contenu)

    def test_le_recit_est_compose_plus_gros_que_le_corps_d_un_guide(self):
        # Un album se lit a voix haute, l'enfant regardant la page. Onze
        # points, c'est un guide.
        from usine.pipelines import conte
        tailles = {float(t) for t in
                   re.findall(r"/F\d+ ([\d.]+) Tf", flux_du_pdf(self.pdf))}
        self.assertIn(conte.CORPS, tailles)
        self.assertGreater(conte.CORPS, 14.0)


class LesIllustrationsDUnConteArriventDansLeLivre(unittest.TestCase):
    """Le bout de la chaine : de « generer_visuel » jusqu'au fichier livre.

    C'est le seul endroit qui mesure ce qui manquait vraiment. Les autres
    classes gardent chacune un maillon ; celle-ci verifie que les maillons
    sont attaches. Le defaut d'origine ne tenait a aucun maillon casse — ils
    marchaient tous — mais a ce que rien ne les reliait.
    """

    @classmethod
    def setUpClass(cls):
        from usine.core import images
        from usine.pipelines import base, conte

        rendu = {}

        def visuel(dossier, nom, invite, largeur=1024, hauteur=1024,
                   en_ligne=True):
            # Le reseau ne doit jamais etre touche par un test. On rend un
            # JPEG d'essai a la place de Pollinations, par le meme chemin.
            dossier.mkdir(parents=True, exist_ok=True)
            chemin = dossier / "{}.jpg".format(nom)
            chemin.write_bytes(jpeg_minimal(120, 90))
            rendu[nom] = chemin
            return chemin

        vrai = images.generer_visuel
        conte.images.generer_visuel = visuel
        llm.definir_simulateur(simulateur.simulateur)
        try:
            contexte = base.Contexte(sujet="un renard qui compte les etoiles",
                                     journal=lambda m: None)
            contexte.sans_image = False
            contexte.hors_ligne = False
            cls.resume = conte.produire(contexte, pages=6, tranche="6-8 ans")
        finally:
            conte.images.generer_visuel = vrai
            llm.definir_simulateur(None)
        cls.dossier = Path(cls.resume["dossier"])

    def test_chaque_double_page_a_recu_son_illustration(self):
        self.assertEqual(self.resume["illustrations"], self.resume["pages"])
        self.assertEqual(len(list((self.dossier / "images").glob("*.jpg"))),
                         self.resume["pages"])

    def test_le_pdf_porte_autant_d_images_que_de_doubles_pages(self):
        pdf = next(self.dossier.glob("*.pdf"))
        brut = pdf.read_bytes()
        # Les illustrations, pas la couverture : celle-ci entre en pixels
        # bruts sous « FlateDecode », les illustrations en JPEG.
        self.assertEqual(brut.count(b"/Filter /DCTDecode"),
                         self.resume["pages"])
        dessins = flux_du_pdf(pdf).count(" Do Q")
        self.assertGreaterEqual(dessins, self.resume["pages"])

    def test_l_epub_embarque_les_fichiers_qu_il_cite(self):
        chemin = next(self.dossier.glob("*.epub"))
        with zipfile.ZipFile(chemin) as archive:
            noms = set(archive.namelist())
            opf = next(n for n in noms if n.endswith(".opf"))
            manifeste = archive.read(opf).decode("utf-8")
            cites = set()
            for nom in noms:
                if nom.endswith(".xhtml"):
                    cites.update(re.findall(
                        r'<img src="([^"]+)"', archive.read(nom).decode()))
        for cite in cites:
            self.assertIn("OEBPS/" + cite, noms, cite)
            self.assertIn('href="{}"'.format(cite), manifeste, cite)
        self.assertEqual(len([c for c in cites if c.startswith("images/")]),
                         self.resume["pages"])
        self.assertTrue(verifier_epub(chemin).conforme)

    def test_le_html_pointe_sur_des_fichiers_qui_existent(self):
        page = (self.dossier / "lire.html").read_text(encoding="utf-8")
        sources = re.findall(r'<img src="([^"]+)"', page)
        self.assertTrue(sources)
        for source in sources:
            self.assertTrue((self.dossier / source).is_file(), source)


if __name__ == "__main__":
    unittest.main()
