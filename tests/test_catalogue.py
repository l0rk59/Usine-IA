"""Tests du catalogue et de l'assemblage commun.

Le test central est « test_chaque_type_produit_ses_fichiers » : il execute
CHAQUE type de produit declare, de bout en bout. Sans lui, une chaine peut
rester cassee alors que toute la suite passe au vert — c'est exactement ce qui
est arrive pendant ce refactor, une erreur d'import dans la formation n'ayant
ete vue qu'a la comparaison manuelle des sorties.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import llm, reglages  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402
from usine.render import livraison  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("catalogue")


class TestCatalogue(unittest.TestCase):
    def test_chaque_type_a_une_chaine(self):
        for type_produit in catalogue.tous():
            self.assertIsNotNone(
                catalogue.obtenir(type_produit.cle).fabriquer,
                "type « {} » sans chaine de fabrication".format(type_produit.cle))

    def test_cles_uniques(self):
        cles = [t.cle for t in catalogue.TYPES]
        self.assertEqual(len(cles), len(set(cles)))

    def test_champs_renseignes(self):
        for type_produit in catalogue.TYPES:
            self.assertTrue(type_produit.nom)
            self.assertTrue(type_produit.resume)
            self.assertTrue(type_produit.detail)
            self.assertTrue(type_produit.formats)
            self.assertEqual(len(type_produit.minutes), 2)
            self.assertLessEqual(type_produit.minutes[0], type_produit.minutes[1])

    def test_mots_cles_sans_accent(self):
        """Un mot-cle accentue ne correspondrait jamais au texte normalise."""
        for type_produit in catalogue.TYPES:
            for mot in type_produit.mots_cles:
                self.assertTrue(all(ord(c) < 128 for c in mot),
                                "{} : {!r}".format(type_produit.cle, mot))

    def test_normalisation_des_synonymes(self):
        """Un modele ecrit « planner » ou « Notion », pas nos cles internes."""
        for propose, attendu in (
            ("impression", "impression"), ("planner", "impression"),
            ("Notion", "modeles"), ("template", "modeles"),
            ("e-book", "ebook"), ("MASTERCLASS", "formation"),
            ("checklist", "outils"), ("agenda imprimable", "impression"),
        ):
            self.assertEqual(catalogue.normaliser(propose), attendu,
                             "{!r} mal normalise".format(propose))

    def test_normalisation_retombe_sur_le_defaut(self):
        self.assertEqual(catalogue.normaliser("quelque chose d'inconnu"), "ebook")
        self.assertEqual(catalogue.normaliser(""), "ebook")

    def test_les_filtres_sont_coherents(self):
        en_file = set(catalogue.cles(en_file=True))
        vendables = set(catalogue.cles(vendables=True))
        tous = set(catalogue.cles())
        self.assertTrue(en_file <= tous)
        self.assertTrue(vendables <= tous)
        self.assertNotIn("idees", en_file, "une etude de niche n'est pas un produit")

    def test_source_unique_partagee(self):
        """Les sept endroits qui listaient les types doivent lire le catalogue."""
        from usine import menu, production
        from usine.web import serveur

        reference = set(catalogue.cles(en_file=True))
        self.assertEqual(set(production.types_disponibles()), reference)
        self.assertEqual(
            {p["cle"] for p in menu.produits_offerts(en_file=True)}, reference)
        self.assertEqual(
            {t["cle"] for t in serveur._catalogue()}, set(catalogue.cles(fabricables=True)))

    def test_execution_par_le_catalogue(self):
        llm.definir_simulateur(simulateur)
        try:
            contexte = Contexte(sujet="un sujet", hors_ligne=True, sans_image=True,
                                journal=lambda message: None)
            resultat = catalogue.executer("prompts", contexte, {"nombre": 4})
            self.assertIn("produit_id", resultat)
        finally:
            llm.definir_simulateur(None)

    def test_type_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            catalogue.executer("inexistant", None, {})


class TestToutesLesChaines(unittest.TestCase):
    """Execute chaque type declare, de bout en bout."""

    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)
        reglages.ecrire({"images": False, "qualite": "rapide", "auteur": "Tests"})

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def test_chaque_type_produit_ses_fichiers(self):
        for type_produit in catalogue.tous(fabricables=True, vendables=True):
            with self.subTest(type=type_produit.cle):
                contexte = Contexte(
                    sujet="sujet de test", audience="testeurs", taille="mini",
                    hors_ligne=True, sans_image=True, journal=lambda message: None)
                options = {"nombre": 3} if type_produit.quantite else {}
                resultat = catalogue.executer(type_produit.cle, contexte, options)

                dossier = Path(resultat["dossier"])
                self.assertTrue(dossier.exists())
                fichiers = [f for f in dossier.rglob("*") if f.is_file()]
                self.assertTrue(fichiers, "aucun fichier produit")

                # Chaque format annonce au catalogue doit exister sur le disque.
                extensions = {f.suffix.lstrip(".") for f in fichiers}
                for format_attendu in type_produit.formats:
                    self.assertIn(
                        format_attendu, extensions,
                        "{} annonce « {} » mais ne le produit pas".format(
                            type_produit.cle, format_attendu))

                # Aucun fichier vide : un PDF de 0 octet passerait inapercu.
                for fichier in fichiers:
                    self.assertGreater(fichier.stat().st_size, 0,
                                       "fichier vide : {}".format(fichier.name))

    def test_les_etudes_de_niche_aussi(self):
        contexte = Contexte(sujet="une niche", hors_ligne=True, sans_image=True,
                            journal=lambda message: None)
        resultat = catalogue.executer("idees", contexte,
                                      {"nombre": 4, "avec_marche": False})
        self.assertTrue(resultat["idees"])


class TestAssemblage(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.contexte = Contexte(sujet="x", auteur="Auteur", hors_ligne=True,
                                 sans_image=True, journal=lambda message: None)
        self.contexte.dossier = self.dossier

    def test_formats_demandes_et_pas_davantage(self):
        produit = livraison.Produit(
            type="essai", titre="Un titre",
            blocs=[livraison.Bloc("Section", "Du texte.")],
            formats=("md", "html"))
        fichiers = livraison.livrer(self.contexte, produit)
        extensions = {f.suffix for f in fichiers}
        self.assertEqual(extensions, {".md", ".html"})

    def test_un_bloc_sans_texte_ne_laisse_pas_de_titre_vide(self):
        """Un bloc a mise en page PDF seule ne doit pas apparaitre en markdown."""
        produit = livraison.Produit(
            type="essai", titre="Un titre",
            blocs=[
                livraison.Bloc("Page PDF", rendu_pdf=lambda doc: doc.paragraphe("x")),
                livraison.Bloc("Vraie section", "Du contenu."),
            ],
            formats=("md", "pdf"))
        livraison.livrer(self.contexte, produit)
        markdown = (self.dossier / "essai.md").read_text(encoding="utf-8")
        self.assertNotIn("# Page PDF", markdown)
        self.assertIn("# Vraie section", markdown)

    def test_le_pdf_contient_bien_les_deux_blocs(self):
        produit = livraison.Produit(
            type="essai", titre="Un titre",
            blocs=[
                livraison.Bloc("Page PDF", rendu_pdf=lambda doc: doc.paragraphe("marqueur")),
                livraison.Bloc("Vraie section", "Du contenu."),
            ],
            formats=("pdf",))
        fichiers = livraison.livrer(self.contexte, produit)
        octets = fichiers[0].read_bytes()
        self.assertGreater(len(octets), 500)
        self.assertTrue(octets.startswith(b"%PDF"))

    def test_tableaux_exportes_en_csv(self):
        produit = livraison.Produit(
            type="essai", titre="T",
            tableaux=[livraison.Tableau("suivi", ["A", "B"], [["1", "2"]]),
                      livraison.Tableau("bases", ["C"], [["3"]],
                                        dossier="a-importer", bom=True)],
            formats=())
        livraison.livrer(self.contexte, produit)
        self.assertTrue((self.dossier / "suivi.csv").exists())
        cible = self.dossier / "a-importer" / "bases.csv"
        self.assertTrue(cible.exists())
        self.assertTrue(cible.read_bytes().startswith(b"\xef\xbb\xbf"),
                        "le BOM est requis par Notion et Excel")

    def test_document_supplementaire_part_du_nom_de_base(self):
        """Le cahier ne doit pas heriter du suffixe du document principal."""
        from usine.render.pdf import DocumentPDF

        def cahier(octets):
            doc = DocumentPDF()
            doc.titre("Cahier", 1)
            return doc

        produit = livraison.Produit(
            type="essai", titre="Ma formation", nom_fichier="ma-formation",
            suffixe_pdf="-manuel", formats=("pdf",),
            blocs=[livraison.Bloc("S", "texte")],
            documents=[("cahier-exercices", cahier)])
        noms = {f.name for f in livraison.livrer(self.contexte, produit)}
        self.assertIn("ma-formation-manuel.pdf", noms)
        self.assertIn("ma-formation-cahier-exercices.pdf", noms)


if __name__ == "__main__":
    unittest.main(verbosity=2)
