"""La marge de reliure : ce que la pliure d'un livre broche avale.

Un cahier imprime a la demande et relie perd quelques millimetres du cote
interieur : le texte y disparait dans la pliure. La correction consiste a
decaler le contenu vers l'exterieur — a GAUCHE sur une page impaire, a DROITE
sur une paire, puisque le cote interieur change de bord a chaque page.

Le test qui compte le plus est le premier : a reliure nulle, tout ce que
l'usine produisait doit sortir a l'identique, octet pour octet. Une
refactorisation du moteur PDF qui deplacerait d'un point le texte de tous les
produits serait invisible en relecture et evidente a l'impression.
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.render.pdf import A4, DocumentPDF  # noqa: E402


def setUpModule():
    atelier.isoler("reliure")


def _document(**kwargs) -> bytes:
    """Un PDF qui exerce toutes les primitives de mise en page."""
    doc = DocumentPDF(titre_courant="Essai", titre_document="Essai",
                      auteur="Zoe", sujet="s", **kwargs)
    doc.page_couverture("Un titre", "Un sous-titre", "Zoe")
    doc.titre("Premier chapitre", 1)
    doc.paragraphe("Un paragraphe assez long pour occuper plusieurs lignes et "
                   "donc exercer la justification du moteur de rendu.",
                   justifier=True)
    doc.liste(["un element", "un autre element", "un troisieme"])
    doc.encadre("Un encadre", "Du texte dans un encadre.")
    doc.tableau(["Colonne A", "Colonne B"], [["a1", "b1"], ["a2", "b2"]])
    doc.titre("Second chapitre", 2)
    doc.lignes_a_remplir(5)
    doc.grille(3, 2)
    doc.inserer_sommaire(apres=1)
    chemin = Path(tempfile.mkdtemp(prefix="usine-reliure-")) / "essai.pdf"
    doc.enregistrer(chemin)
    return chemin.read_bytes()


def _empreinte(octets: bytes) -> str:
    """Empreinte du PDF, horodatage et identifiant exclus.

    Ces trois champs changent a chaque execution par construction : les
    inclure ferait echouer le test pour la seule raison que le temps passe.
    """
    for motif in (rb"/CreationDate \([^)]*\)", rb"/ModDate \([^)]*\)",
                  rb"/ID \[[^\]]*\]"):
        octets = re.sub(motif, b"", octets)
    return hashlib.sha256(octets).hexdigest()


class TestAucuneRegression(unittest.TestCase):
    def test_sans_reliure_le_pdf_est_inchange(self):
        """Deux rendus successifs sans reliure doivent etre identiques.

        C'est le verrou de la refactorisation : le moteur a vu trente-trois
        de ses abscisses remplacees, et rien ne devait bouger pour autant.
        """
        self.assertEqual(_empreinte(_document()), _empreinte(_document()))

    def test_la_reliure_nulle_est_le_defaut(self):
        self.assertEqual(DocumentPDF().reliure, 0.0)
        self.assertEqual(DocumentPDF().marge_gauche, DocumentPDF().marge)

    def test_une_reliure_negative_est_ramenee_a_zero(self):
        """Elle ferait sortir le contenu de la page par la gauche."""
        self.assertEqual(DocumentPDF(reliure=-40).reliure, 0.0)

    def test_une_reliure_change_reellement_le_rendu(self):
        """Sinon le reste de ces tests ne prouverait rien."""
        self.assertNotEqual(_empreinte(_document()),
                            _empreinte(_document(reliure=28)))


class TestGeometrie(unittest.TestCase):
    def setUp(self):
        self.doc = DocumentPDF(marge=60, reliure=30)

    def _avancer_jusqu_a(self, page: int) -> None:
        while self.doc.page_courante < page:
            self.doc.paragraphe("x")
            self.doc.nouvelle_page()

    def test_la_page_impaire_porte_la_reliure_a_gauche(self):
        self._avancer_jusqu_a(1)
        self.assertEqual(self.doc.marge_gauche, 90)
        self.assertAlmostEqual(self.doc.bord_droit, self.doc.largeur - 60, 2)

    def test_la_page_paire_la_porte_a_droite(self):
        """Le cote interieur change de bord a chaque page."""
        self._avancer_jusqu_a(2)
        self.assertEqual(self.doc.marge_gauche, 60)
        self.assertAlmostEqual(self.doc.bord_droit, self.doc.largeur - 90, 2)

    def test_elle_alterne_sur_toute_la_longueur(self):
        attendus = []
        for page in range(1, 7):
            self._avancer_jusqu_a(page)
            attendus.append(self.doc.marge_gauche)
        self.assertEqual(attendus, [90, 60, 90, 60, 90, 60])

    def test_la_largeur_utile_est_la_meme_des_deux_cotes(self):
        """Une colonne de texte qui change de largeur page apres page se voit."""
        self._avancer_jusqu_a(1)
        impaire = self.doc.largeur_utile
        self._avancer_jusqu_a(2)
        self.assertEqual(self.doc.largeur_utile, impaire)

    def test_la_reliure_se_prend_sur_la_largeur_utile(self):
        """Elle s'ajoute a la marge, elle ne pousse pas le texte hors page."""
        nu = DocumentPDF(marge=60)
        self.assertAlmostEqual(self.doc.largeur_utile, nu.largeur_utile - 30, 2)

    def test_le_contenu_ne_sort_jamais_de_la_page(self):
        for page in range(1, 5):
            self._avancer_jusqu_a(page)
            self.assertGreaterEqual(self.doc.marge_gauche, 0)
            self.assertLessEqual(self.doc.bord_droit, self.doc.largeur)


def _texte_du_pdf(chemin: Path) -> str:
    """Le texte d'un PDF, flux decompresses.

    Chercher une chaine dans les octets bruts ne trouve jamais rien : les
    flux de contenu sont compresses par Flate.
    """
    brut = chemin.read_bytes()
    morceaux = []
    for flux in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", brut, re.DOTALL):
        try:
            morceaux.append(zlib.decompress(flux).decode("latin-1"))
        except zlib.error:
            morceaux.append(flux.decode("latin-1", "replace"))
    return "\n".join(morceaux)


class TestChaineImpression(unittest.TestCase):
    def _cahier(self, reliure: float):
        from tests.simulateur import simulateur
        from usine.core import llm, reglages
        from usine.pipelines import impression
        from usine.pipelines.base import Contexte

        llm.definir_simulateur(simulateur)
        reglages.ecrire({"images": False, "qualite": "rapide"})
        try:
            contexte = Contexte(sujet="la planification", hors_ligne=True,
                                sans_image=True, journal=lambda message: None)
            return impression.produire(contexte, pages=4, reliure=reliure)
        finally:
            llm.definir_simulateur(None)

    def test_les_deux_formats_sortent_avec_la_reliure(self):
        resume = self._cahier(12)
        dossier = Path(resume["dossier"])
        pdfs = sorted(f.name for f in dossier.glob("*.pdf"))
        self.assertEqual(len(pdfs), 2, pdfs)
        for chemin in dossier.glob("*.pdf"):
            self.assertTrue(chemin.read_bytes().startswith(b"%PDF"))
            self.assertGreater(chemin.stat().st_size, 1000)

    def test_les_millimetres_deviennent_des_points(self):
        from usine.pipelines import impression

        self.assertAlmostEqual(impression.POINTS_PAR_MM, 2.8346, 3)
        self.assertAlmostEqual(10 * impression.POINTS_PAR_MM, 28.35, 2)

    def test_sans_reliure_le_cahier_n_en_parle_pas(self):
        """Le mode d'emploi ne doit pas expliquer une mise en page absente."""
        resume = self._cahier(0)
        pdf = next(Path(resume["dossier"]).glob("*-A4.pdf"))
        self.assertNotIn("Impression à la demande", _texte_du_pdf(pdf))

    def test_avec_reliure_le_cahier_l_explique(self):
        resume = self._cahier(12)
        pdf = next(Path(resume["dossier"]).glob("*-A4.pdf"))
        self.assertIn("Impression à la demande", _texte_du_pdf(pdf))

    def test_l_option_est_declaree_au_catalogue(self):
        from usine.pipelines import catalogue

        self.assertIn("reliure", catalogue.obtenir("impression").options)


if __name__ == "__main__":
    unittest.main()
