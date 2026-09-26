"""Accessibilite et metadonnees des fichiers livres.

Depuis le 28 juin 2025, l'European Accessibility Act s'applique aux livres
numeriques vendus dans l'Union. Un EPUB sans metadonnees d'accessibilite est
refuse par une partie des distributeurs europeens — et ce qu'elles annoncent
engage le vendeur, donc doit etre vrai.

Ces tests verifient les deux moities : que les metadonnees sont la, et que
ce qu'elles affirment correspond au document reellement produit.
"""

from __future__ import annotations

import re
import tempfile
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.pipelines.base import code_langue
from usine.render import epub, lisibilite, page, quiz
from usine.render.couverture import contraste
from usine.render.pdf import DocumentPDF
from usine.render.raster import couleur_hex

CHAPITRES = [("Premier chapitre", "<p>Du texte de premier chapitre.</p>"),
             ("Second chapitre", "<p>Du texte de second chapitre.</p>")]


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("acces")


def _construire(**extra):
    chemin = Path(tempfile.mkdtemp()) / "essai.epub"
    epub.construire_epub(chemin, "Un titre", "Claire Fontaine", CHAPITRES,
                         description="Une promesse claire.", **extra)
    return chemin


def _opf(chemin: Path) -> str:
    return zipfile.ZipFile(chemin).read("OEBPS/content.opf").decode("utf-8")


class TestMetadonneesEpub(unittest.TestCase):

    def test_les_metadonnees_d_accessibilite_sont_presentes(self):
        opf = _opf(_construire())
        for propriete in ("schema:accessMode", "schema:accessModeSufficient",
                          "schema:accessibilityFeature",
                          "schema:accessibilityHazard",
                          "schema:accessibilitySummary",
                          "dcterms:conformsTo"):
            self.assertIn('property="{}"'.format(propriete), opf, propriete)

    def test_la_conformite_annoncee_est_nommee_precisement(self):
        self.assertIn("EPUB Accessibility 1.1 - WCAG 2.1 Level AA",
                      _opf(_construire()))

    def test_le_texte_suffit_a_lire_le_livre(self):
        """accessModeSufficient=textual : rien d'essentiel n'est dans l'image."""
        self.assertIn(
            '<meta property="schema:accessModeSufficient">textual</meta>',
            _opf(_construire()))

    def test_l_image_ajoute_son_mode_et_son_texte_de_remplacement(self):
        """Ce qui est declare doit dependre de ce qui est reellement livre."""
        avec = _opf(_construire(couverture=("couverture.png", b"\x89PNG" + b"0" * 40)))
        sans = _opf(_construire())
        self.assertIn('<meta property="schema:accessMode">visual</meta>', avec)
        self.assertIn("alternativeText", avec)
        self.assertNotIn('<meta property="schema:accessMode">visual</meta>', sans)
        self.assertNotIn("alternativeText", sans)

    def test_l_opf_reste_du_xml_bien_forme(self):
        racine = ET.fromstring(_opf(_construire()))
        self.assertTrue(racine.tag.endswith("package"))
        self.assertEqual(
            racine.get("{http://www.w3.org/XML/1998/namespace}lang"), "fr")

    def test_le_prefixe_a11y_est_declare(self):
        """« a11y: » n'est pas un prefixe reserve : sans declaration, l'OPF est invalide."""
        opf = _opf(_construire())
        self.assertIn("a11y: http://www.idpf.org/epub/vocab/package/a11y/#", opf)
        self.assertIn('property="a11y:certifiedBy"', opf)

    def test_la_date_de_modification_est_reelle(self):
        """Elle etait figee : deux livres differents portaient la meme."""
        premier = _opf(_construire())
        modifie = re.search(r'"dcterms:modified">([^<]+)<', premier).group(1)
        self.assertRegex(modifie, r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertNotEqual(modifie, "2026-01-01T00:00:00Z")

    def test_l_editeur_et_les_droits_accompagnent_le_fichier(self):
        opf = _opf(_construire(editeur="Atelier Nord"))
        self.assertIn("<dc:publisher>Atelier Nord</dc:publisher>", opf)
        self.assertIn("<dc:rights>", opf)


class TestMetadonneesPdf(unittest.TestCase):

    def _pdf(self, **extra) -> bytes:
        document = DocumentPDF(titre_courant="Courant", **extra)
        document.titre("Un chapitre")
        document.paragraphe("Du texte.")
        chemin = document.enregistrer(Path(tempfile.mkdtemp()) / "essai.pdf")
        return chemin.read_bytes()

    def test_le_fichier_porte_son_titre_et_son_auteur(self):
        """Sans /Info, le PDF s'affiche « Untitled » dans tous les lecteurs."""
        brut = self._pdf(titre_document="Le systeme du freelance",
                         auteur="Claire Fontaine", sujet="Prospection")
        self.assertIn(b"/Title (Le systeme du freelance)", brut)
        self.assertIn(b"/Author (Claire Fontaine)", brut)
        self.assertIn(b"/Subject (Prospection)", brut)
        self.assertIn(b"/Producer (", brut)

    def test_le_trailer_pointe_vers_le_dictionnaire_info(self):
        """Un /Info non reference par le trailer n'est lu par personne."""
        brut = self._pdf(titre_document="T", auteur="A")
        trailer = re.search(rb"trailer\n<< (.+?) >>", brut, re.S).group(1)
        numero = re.search(rb"/Info (\d+) 0 R", trailer)
        self.assertIsNotNone(numero, "le trailer doit citer /Info")
        objet = re.search(
            numero.group(1) + rb" 0 obj\n<< (.+?) >>", brut, re.S)
        self.assertIn(b"/Title", objet.group(1))

    def test_la_langue_est_declaree(self):
        """Sans /Lang, un lecteur d'ecran devine — et il devine l'anglais."""
        self.assertIn(b"/Lang (en)", self._pdf(langue="en"))
        self.assertIn(b"/DisplayDocTitle true", self._pdf())

    def test_un_titre_avec_parentheses_ne_casse_pas_le_fichier(self):
        """Une parenthese non echappee ferme la chaine PDF en avance."""
        brut = self._pdf(titre_document="Le guide (complet) du \\ freelance")
        self.assertIn(rb"/Title (Le guide \(complet\) du \\ freelance)", brut)
        self.assertTrue(brut.rstrip().endswith(b"%%EOF"))

    def test_les_decalages_xref_restent_justes(self):
        """L'objet /Info s'ajoute a la table : elle doit suivre."""
        brut = self._pdf(titre_document="T")
        position = brut.index(b"xref\n")
        declare = int(re.search(rb"startxref\n(\d+)", brut).group(1))
        self.assertEqual(declare, position)
        entrees = re.findall(rb"^(\d{10}) 00000 n $", brut[position:], re.M)
        for entree in entrees:
            debut = int(entree)
            self.assertRegex(brut[debut:debut + 12], rb"^\d+ 0 obj\n")


class TestLangue(unittest.TestCase):

    def test_les_noms_courants_donnent_le_bon_code(self):
        for nom, attendu in (("francais", "fr"), ("Français", "fr"),
                             ("anglais", "en"), ("english", "en"),
                             ("espagnol", "es"), ("Allemand", "de")):
            self.assertEqual(code_langue(nom), attendu, nom)

    def test_une_langue_inconnue_retombe_sur_le_defaut(self):
        self.assertEqual(code_langue("klingon"), "fr")
        self.assertEqual(code_langue(""), "fr")

    def test_les_trois_formats_annoncent_la_meme_langue(self):
        """Seule la chaine ebook convertissait : les huit autres livraient « fr »."""
        from usine.pipelines.base import Contexte

        contexte = Contexte(sujet="x", langue="anglais")
        self.assertEqual(contexte.langue_iso, "en")

        chemin = _construire()
        self.assertIn("<dc:language>fr</dc:language>", _opf(chemin))
        anglais = Path(tempfile.mkdtemp()) / "en.epub"
        epub.construire_epub(anglais, "T", "A", CHAPITRES, langue="en")
        self.assertIn("<dc:language>en</dc:language>", _opf(anglais))

        html = page.ecrire_page(Path(tempfile.mkdtemp()) / "p.html", "T",
                                "<p>x</p>", langue="en")
        self.assertIn('<html lang="en">', html.read_text(encoding="utf-8"))


class TestContrasteDesDocuments(unittest.TestCase):
    """Ce que la declaration de conformite affirme doit rester vrai."""

    def test_chaque_couple_declare_atteint_son_seuil(self):
        self.assertEqual(lisibilite.verifier(), [])

    def test_aucune_couleur_des_feuilles_de_style_n_echappe_au_tableau(self):
        """Le verrou : une teinte ajoutee doit etre classee, pas oubliee.

        Sans lui, la feuille de style aurait derive de la declaration au
        premier changement, et l'usine aurait continue d'affirmer une
        conformite qu'elle n'avait plus.
        """
        declarees = lisibilite.couleurs_declarees()
        for nom, feuille in (("epub", epub.STYLE), ("html", page.GABARIT),
                             ("quiz", quiz.STYLE)):
            trouvees = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", feuille)}
            inconnues = trouvees - declarees
            self.assertFalse(
                inconnues,
                "{} : teintes absentes de render/lisibilite.py : {}".format(
                    nom, ", ".join(sorted(inconnues))))

    def test_le_calcul_est_bien_celui_de_wcag(self):
        self.assertAlmostEqual(
            contraste(couleur_hex("#000000"), couleur_hex("#ffffff")), 21.0,
            delta=0.01)


if __name__ == "__main__":
    unittest.main()


class TestNoticeDeContact(unittest.TestCase):
    """La notice ne promet pas ce qu'elle ne peut pas tenir.

    Le repli valait « votre adresse e-mail », et il partait tel quel chez
    l'acheteur : « Ecrivez a votre adresse e-mail ». Un rappel destine au
    VENDEUR, imprime dans le document VENDU.

    Pire que ridicule : la section accessibilite promettait d'envoyer une
    version adaptee a une adresse qui n'existe pas — et c'est precisement la
    promesse que la reglementation europeenne attend de voir tenue.
    """

    def _notice(self, contact):
        import tempfile

        from usine.packaging.livraison import ecrire_notice

        with tempfile.TemporaryDirectory() as brut:
            dossier = Path(brut)
            (dossier / "livre.pdf").write_bytes(b"%PDF-1.4\n")
            return ecrire_notice(dossier, "Un titre", "une promesse",
                                 "Une autrice", contact).read_text(
                                     encoding="utf-8")

    def test_sans_adresse_aucune_promesse_n_est_faite(self):
        texte = self._notice("")
        self.assertNotIn("Écrivez à", texte)
        self.assertNotIn("une version adaptée", texte)

    def test_aucun_texte_de_rappel_ne_part_chez_l_acheteur(self):
        """Le defaut exact : le repli etait une consigne au vendeur."""
        self.assertNotIn("votre adresse e-mail", self._notice(""))

    def test_avec_adresse_les_deux_passages_reviennent(self):
        texte = self._notice("contact@exemple.fr")
        self.assertIn("une version adaptée", texte)
        self.assertIn("## Une question ?", texte)
        self.assertEqual(texte.count("contact@exemple.fr"), 2)

    def test_la_notice_reste_lisible_sans_adresse(self):
        """Retirer deux passages ne doit pas laisser un trou de trois lignes
        vides avant la signature."""
        texte = self._notice("")
        self.assertNotIn("\n\n\n", texte)
        self.assertIn("sont incluses dans le fichier.\n\n---", texte)

    def test_le_defaut_de_la_fonction_n_invente_rien_non_plus(self):
        """Un appelant qui omet l'argument ne doit pas retrouver le repli.

        Les autres cas passent « contact » explicitement : c'est justement
        ce qui laissait le defaut de la signature hors de portee.
        """
        import tempfile

        from usine.packaging.livraison import ecrire_notice

        with tempfile.TemporaryDirectory() as brut:
            dossier = Path(brut)
            (dossier / "livre.pdf").write_bytes(b"%PDF-1.4\n")
            texte = ecrire_notice(dossier, "Un titre", "", "Une autrice"
                                  ).read_text(encoding="utf-8")
        self.assertNotIn("votre adresse e-mail", texte)
        self.assertNotIn("Écrivez à", texte)

    def test_la_ligne_de_commande_ne_fabrique_pas_d_adresse(self):
        """Le bout en bout : c'est « usine ebook --zip » qui ecrit la notice,
        et c'est la que le repli etait pose."""
        import tempfile

        from tests.simulateur import simulateur
        from usine.cli import principal
        from usine.core import llm

        llm.definir_simulateur(simulateur)
        try:
            with tempfile.TemporaryDirectory() as brut:
                dossier = Path(brut)
                (dossier / "livre.pdf").write_bytes(b"%PDF-1.4\n")
                from usine.packaging import livraison

                archive = livraison.empaqueter(
                    dossier, "un-titre", "Un titre", "Une autrice",
                    promesse="une promesse")
                self.assertTrue(archive.exists())
                notice = (dossier / "LISEZ-MOI.md").read_text(encoding="utf-8")
            self.assertNotIn("votre adresse e-mail", notice)
            source = (RACINE / "usine" / "cli.py").read_text(encoding="utf-8")
            self.assertNotIn('"votre adresse e-mail"', source)
        finally:
            llm.definir_simulateur(None)
        self.assertTrue(callable(principal))

    def test_le_vendeur_est_prevenu_quand_il_n_a_pas_donne_d_adresse(self):
        """C'est lui qui decide de tenir la promesse ou non — mais il doit
        savoir qu'elle n'est pas ecrite."""
        source = (RACINE / "usine" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("Aucune adresse de contact", source)
