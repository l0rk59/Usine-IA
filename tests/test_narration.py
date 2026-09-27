"""Le script de narration : ce qui se dit, et combien de temps ca prend.

Le module ne redige pas — c'est le travail du modele. Il fait ce qui se
CALCULE : la duree, le nettoyage de ce qui ne se prononce pas, la mise en
page. Ce sont donc ces trois choses qui sont testees, plus le fait que la
narration reste une OPTION : elle coute un appel par module, et doubler le
prix d'une formation sans le demander serait une mauvaise surprise.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, reglages  # noqa: E402
from usine.render import narration as N  # noqa: E402


def setUpModule():
    atelier.isoler("narration")
    llm.definir_simulateur(simulateur)
    reglages.ecrire({"images": False, "qualite": "rapide"})


def tearDownModule():
    llm.definir_simulateur(None)


class TestNettoyage(unittest.TestCase):
    """Lu par une voix, « ## Le contenu » donne « diese diese le contenu »."""

    def test_les_titres_disparaissent(self):
        self.assertEqual(N.nettoyer("## Le contenu\n\nDu texte."),
                         "Le contenu\n\nDu texte.")

    def test_les_puces_et_la_numerotation_disparaissent(self):
        propre = N.nettoyer("- premier\n- second\n\n1. faire\n2. refaire")
        self.assertNotIn("-", propre)
        self.assertNotIn("1.", propre)
        self.assertIn("premier", propre)
        self.assertIn("refaire", propre)

    def test_l_emphase_et_le_code_disparaissent(self):
        self.assertEqual(N.nettoyer("un point **important** et `du code`"),
                         "un point important et du code")

    def test_un_lien_garde_son_texte_et_perd_son_adresse(self):
        self.assertEqual(N.nettoyer("voir [le guide](https://exemple.fr/x)"),
                         "voir le guide")

    def test_les_indications_de_jeu_sont_conservees(self):
        """Elles sont pour la personne qui lit, pas pour le micro."""
        propre = N.nettoyer("Une phrase. [PAUSE] Une autre. [INSISTER] La fin.")
        self.assertIn("[PAUSE]", propre)
        self.assertIn("[INSISTER]", propre)

    def test_les_lignes_vides_en_trop_sont_resserrees(self):
        self.assertEqual(N.nettoyer("un\n\n\n\n\ndeux"), "un\n\ndeux")


class TestDuree(unittest.TestCase):
    def test_les_indications_de_jeu_ne_sont_pas_prononcees(self):
        """Les compter gonflerait la duree annoncee au monteur."""
        self.assertEqual(N.compter_mots("un deux trois"), 3)
        self.assertEqual(N.compter_mots("un [PAUSE] deux [INSISTER] trois"), 3)

    def test_la_duree_suit_le_debit_de_reference(self):
        mesure = N.duree(N.MOTS_PAR_MINUTE * 4)
        self.assertEqual(mesure["minutes"], 4.0)

    def test_la_fourchette_encadre_l_estimation(self):
        """Un chiffre unique donnerait une precision qu'une voix n'a pas."""
        mesure = N.duree(1500)
        self.assertLess(mesure["minimum"], mesure["minutes"])
        self.assertGreater(mesure["maximum"], mesure["minutes"])

    def test_un_script_vide_ne_divise_pas_par_zero(self):
        self.assertEqual(N.duree(0)["minutes"], 0.0)
        self.assertEqual(N.minutes_lisibles(N.duree(0)), "vide")


class TestAssemblage(unittest.TestCase):
    def setUp(self):
        self.document, self.mesures = N.assembler("Ma formation", [
            ("Module 1 — les bases", "## Titre\n\n- un\n- deux\n\nDu texte dit."),
            ("Module 2 — la suite", "Encore du texte, plus long que le premier "
                                    "module afin de peser davantage."),
        ])

    def test_chaque_module_porte_sa_duree(self):
        self.assertEqual(self.document.count("## Module"), 2)
        self.assertEqual(len(self.mesures["modules"]), 2)
        for module in self.mesures["modules"]:
            self.assertGreater(module["mots"], 0)

    def test_le_total_est_la_somme_des_modules(self):
        self.assertEqual(self.mesures["mots"],
                         sum(m["mots"] for m in self.mesures["modules"]))
        self.assertIn("2 modules", self.document)

    def test_le_document_ne_contient_plus_de_balisage_a_dire(self):
        """Les seuls titres restants sont ceux de la mise en page du script."""
        corps = self.document.split("## Module 1")[1]
        for ligne in corps.splitlines():
            self.assertFalse(ligne.startswith(("- ", "* ", "> ")), ligne)


class TestDansLaChaine(unittest.TestCase):
    def _formation(self, **kwargs):
        from usine.pipelines import formation
        from usine.pipelines.base import Contexte

        contexte = Contexte(sujet="le copywriting", hors_ligne=True,
                            sans_image=True, journal=lambda message: None)
        return formation.produire(contexte, modules=2, **kwargs)

    def test_sans_l_option_rien_n_est_produit(self):
        """Elle double le cout d'une formation : elle ne s'impose pas."""
        resume = self._formation()
        self.assertNotIn("narration.md", resume["fichiers"])
        self.assertIsNone(resume["narration"])

    def test_avec_l_option_le_script_est_livre_et_mesure(self):
        resume = self._formation(narration=True)
        self.assertIn("narration.md", resume["fichiers"])
        self.assertEqual(len(resume["narration"]["modules"]), 2)
        self.assertGreater(resume["narration"]["minutes"], 0)
        document = (Path(resume["dossier"]) / "narration.md").read_text(
            encoding="utf-8")
        self.assertIn("Script de narration", document)
        self.assertIn("[PAUSE]", document)

    def test_un_echec_de_narration_n_emporte_pas_la_formation(self):
        from usine.pipelines import formation

        original = formation._narration

        def tomber(*args, **kwargs):
            raise RuntimeError("le modele n'a pas repondu")

        formation._narration = tomber
        try:
            resume = self._formation(narration=True)
        finally:
            formation._narration = original
        self.assertNotIn("narration.md", resume["fichiers"])
        self.assertIn("formation.md", resume["fichiers"],
                      "le reste de la formation doit sortir quand meme")

    def test_l_option_est_declaree_au_catalogue(self):
        """Le menu et le tableau de bord la lisent de la, pas d'une copie."""
        from usine.pipelines import catalogue

        self.assertIn("narration", catalogue.obtenir("formation").options)


if __name__ == "__main__":
    unittest.main()
