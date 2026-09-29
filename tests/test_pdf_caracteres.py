"""Ce que le PDF ne sait pas ecrire, et pourquoi il doit le dire.

Le moteur PDF est ecrit a la main — c'est la contrainte fondatrice du depot :
Termux ne sait pas compiler de roue native, donc pas de reportlab. Il n'embarque
aucune police et utilise les quatorze polices standard du format, en WinAnsi.

Mesure du 14/09/2026, en passant les caracteres directement dans les deux
moteurs :

    PDF  — remplaces par « ? » : cyrillique, arabe, japonais, grec, emoji
    PDF  — conserves           : « » — et tous les accents francais
    EPUB — perdus              : aucun

Un livre intitule « la cuisine japonaise <deux ideogrammes> » sortait donc
avec « ?? » sur sa couverture et sa page de titre, **livre marque « pret »** —
alors que l'EPUB du meme produit etait parfait, et que rien ne disait lequel
des deux fichiers croire.

C'est la plainte d'origine — « des caracteres bugges qui s'introduisent dans
des produits generes » — sur un chemin qui n'avait pas ete regarde : celui du
clavier vers le PDF, et non celui du modele vers le texte.
"""

from __future__ import annotations

import html
import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, store  # noqa: E402
from usine.render import pdf  # noqa: E402
from usine.render.epub import construire_epub  # noqa: E402


def setUpModule():
    atelier.isoler("pdf-caracteres")


FRANCAIS = ("L'elevage bio : « cout reel », marge — a 12 % pres, ca depend "
            "de l'oeuf et du coeur de metier. Voila ce qu'il faut savoir…")
NON_LATIN = "alphabet алфавит, 和食, مرحبا, α, et ① en tete"


class LeFrancaisPasseEntier(unittest.TestCase):
    """Le premier sens du controle : ne pas crier a tort.

    Un depot entierement francais dont le controle signalerait les accents
    serait ignore des le deuxieme produit."""

    def test_aucun_caractere_francais_n_est_signale(self):
        self.assertEqual(pdf.caracteres_absents(FRANCAIS), [])

    def test_le_francais_sort_intact_du_moteur(self):
        rendu = pdf._echapper(FRANCAIS).decode("cp1252")
        for morceau in ("elevage", "« cout reel »", "l'oeuf", "12 %"):
            with self.subTest(morceau=morceau):
                self.assertIn(morceau, rendu)
        self.assertNotIn("?", rendu)

    def test_les_signes_que_winansi_porte_sont_dessines_tels_quels(self):
        """Tiret cadratin, points de suspension, apostrophe et guillemets
        courbes, puce, signe de multiplication : WinAnsi les a tous. Ils
        etaient remplaces par « - », « ... », « ' » pour rien — les tirets
        de dialogue d'un roman s'imprimaient en traits d'union."""
        texte = "— Tu viens ? dit-elle… l’été, “ok” • 3×4 ± 1"
        self.assertEqual(pdf._echapper(texte).decode("cp1252"), texte)

    def test_ce_que_winansi_n_a_pas_garde_un_equivalent(self):
        """Ce que les modeles ecrivent en francais : l'espace fine insecable
        sortait en « ? », le signe moins disparaissait — « −5 °C » devenait
        « 5 °C »."""
        rendu = pdf._echapper(
            "\u22125 °C, 20\u202f€, a\u2009b, x\u2011y, a → b").decode("cp1252")
        self.assertEqual(rendu, "-5 °C, 20 €, a b, x-y, a -> b")


class LaMesureCompteCeQuiEstDessine(unittest.TestCase):
    """Une ligne se coupe sur la largeur MESUREE ; elle s'imprime a la
    largeur DESSINEE. Tout ecart deborde sur la marge de droite.

    Avant, « « », « — » ou « œ » empruntaient la largeur d'un autre signe :
    un guillemet francais etait compte 36 % trop etroit en Helvetica, « œ »
    41 %. Les valeurs de reference sont celles des fichiers AFM d'Adobe."""

    def test_les_largeurs_des_fichiers_afm(self):
        from usine.render.metriques import largeur_texte

        for texte, police, attendu in (("«", "Helvetica", 556),
                                       ("»", "Times-Roman", 500),
                                       ("—", "Times-Roman", 1000),
                                       ("—", "Times-Italic", 889),
                                       ("œ", "Helvetica", 944),
                                       ("’", "Times-Roman", 333),
                                       ("…", "Helvetica-Bold", 1000)):
            with self.subTest(texte=texte, police=police):
                self.assertEqual(largeur_texte(texte, police, 1000), attendu)

    def test_chaque_signe_de_winansi_a_sa_largeur(self):
        from usine.render.metriques import POLICES

        signes = []
        for octet in range(0x80, 0x100):
            try:
                signes.append(bytes([octet]).decode("cp1252"))
            except UnicodeDecodeError:
                continue
        for police, table in POLICES.items():
            with self.subTest(police=police):
                self.assertEqual([s for s in signes if s not in table], [])

    def test_un_signe_remplace_se_mesure_comme_son_remplacant(self):
        from usine.render.metriques import largeur_texte

        for source, dessine in (("→", "->"), ("\u2212", "-"), ("\u202f", " ")):
            with self.subTest(source=source):
                self.assertEqual(largeur_texte(source, "Helvetica", 10),
                                 largeur_texte(dessine, "Helvetica", 10))


class LeTitreDuFichier(unittest.TestCase):
    """Le titre que la visionneuse affiche dans sa barre, et la liseuse
    dans sa bibliotheque."""

    def _titre(self, titre: str) -> bytes:
        doc = pdf.DocumentPDF(titre_document=titre, auteur="a")
        doc.paragraphe("x")
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "t.pdf"
            doc.enregistrer(chemin)
            brut = chemin.read_bytes()
        return brut.split(b"/Title ", 1)[1].split(b" /", 1)[0]

    def test_un_tiret_cadratin_ne_devient_plus_un_point_d_interrogation(self):
        """Encode en latin-1, qui n'a pas « — » : « Quiz ? la paie »."""
        brut = self._titre("Quiz — la paie (été)")
        self.assertTrue(brut.startswith(b"<FEFF"), brut)
        self.assertEqual(bytes.fromhex(brut[5:-1].decode()).decode("utf-16-be"),
                         "Quiz — la paie (été)")

    def test_un_titre_ascii_reste_litteral_et_echappe(self):
        self.assertEqual(self._titre("Guide (2026)"), rb"(Guide \(2026\))")


class UnSymboleSEffaceUneLettreSeSignale(unittest.TestCase):
    """Deux traitements, parce que ce sont deux pertes differentes."""

    def test_un_emoji_disparait_sans_laisser_de_point_d_interrogation(self):
        """Dans un titre de couverture, « ? » se lit comme un defaut du
        fichier ; une absence se lit comme un choix. Et un emoji ne porte
        aucune information textuelle."""
        rendu = pdf._echapper("Le bien-etre 🌿 au travail").decode("cp1252")
        self.assertNotIn("?", rendu)
        self.assertIn("Le bien-etre au travail", rendu)

    def test_un_emoji_n_est_donc_pas_signale(self):
        """Signaler ce qu'on a retire proprement ferait crier le controle sur
        n'importe quel titre un peu decore."""
        self.assertEqual(pdf.caracteres_absents("Le bien-etre 🌿"), [])

    def test_une_lettre_non_latine_est_signalee(self):
        """L'effacer en silence serait pire qu'un mot illisible : personne ne
        saurait qu'il manque quelque chose."""
        perdus = pdf.caracteres_absents(NON_LATIN)
        for lettre in ("а", "和", "م", "α"):
            with self.subTest(lettre=lettre):
                self.assertIn(lettre, perdus)

    def test_une_lettre_non_latine_reste_visible_en_point_d_interrogation(self):
        """On ne la retire PAS : un « ? » se remarque, une absence non."""
        rendu = pdf._echapper("le mot 和食 ici").decode("cp1252")
        self.assertIn("??", rendu)

    def test_une_fleche_ne_declenche_rien(self):
        """Elle a un equivalent ASCII, donc rien n'est perdu."""
        self.assertEqual(pdf.caracteres_absents("de A → B"), [])
        self.assertIn("->", pdf._echapper("de A → B").decode("cp1252"))


class L_EpubLuiGardeTout(unittest.TestCase):
    """La comparaison est le coeur du sujet : le meme produit livre deux
    fichiers, et un seul est ampute. Sans cette mesure, on ne saurait pas
    lequel des deux croire."""

    def test_l_epub_conserve_ce_que_le_pdf_perd(self):
        essai = FRANCAIS + " " + NON_LATIN
        speciaux = sorted({c for c in essai if ord(c) > 127})
        with tempfile.TemporaryDirectory() as tmp:
            chemin = construire_epub(
                Path(tmp) / "essai.epub", titre=essai, auteur="Test",
                chapitres=[(essai, "<p>" + html.escape(essai) + "</p>")])
            with zipfile.ZipFile(chemin) as archive:
                brut = " ".join(
                    archive.read(nom).decode("utf-8", "replace")
                    for nom in archive.namelist()
                    if nom.endswith((".xhtml", ".html", ".opf", ".ncx")))
        contenu = html.unescape(brut)
        perdus = [c for c in speciaux if c not in contenu]
        self.assertEqual(perdus, [],
                         "l'EPUB perd aussi des caracteres : le sujet n'est "
                         "plus une limite du PDF mais un defaut general")


class LaChaineLeDitSurLaFicheDuProduit(unittest.TestCase):

    def _fabriquer(self, sujet):
        atelier.isoler("pdf-car-" + str(abs(hash(sujet)))[:8])
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["ebook", sujet, "--chapitres", "2",
                               "--sans-image", "-q", "rapide"])
        finally:
            llm.definir_simulateur(None)
        produit = store.lister_produits(2)[0]
        return (produit.get("meta") or {}), sortie.getvalue()

    def test_un_titre_non_latin_est_signale_sur_la_fiche(self):
        """Le titre, pas seulement le corps : une premiere version ne lisait
        que le texte du livre, et le cas qui a ouvert le sujet passait
        inapercu parce que les ideogrammes etaient dans le titre."""
        meta, journal = self._fabriquer("la cuisine japonaise 和食 pour tous")
        self.assertIn("和", meta.get("pdf_caracteres_absents") or [])
        self.assertIn("Le PDF ne sait pas écrire", journal)

    def test_un_produit_sans_pdf_n_est_pas_inspecte(self):
        """Signaler ce que « le PDF » ne sait pas ecrire a propos d'un produit
        qui n'en livre aucun serait un message sur un fichier inexistant.
        « usine idees » ne livre que du CSV, du JSON et du HTML.
        """
        from usine.pipelines.base import _ce_que_le_pdf_ne_sait_pas_ecrire

        class _Ctx:
            sujet = "la cuisine japonaise 和食"
            auteur = ""

            @staticmethod
            def journal(_message):
                raise AssertionError("rien ne doit etre dit sans PDF livre")

        sans_pdf = [Path("idees.csv"), Path("idees.json")]
        self.assertEqual(
            _ce_que_le_pdf_ne_sait_pas_ecrire(_Ctx(), sans_pdf, "和食"), {})

    def test_un_sujet_francais_ne_declenche_rien(self):
        meta, journal = self._fabriquer("la comptabilite des tres petites "
                                        "entreprises et l'oeuf de Paques")
        self.assertFalse(meta.get("pdf_caracteres_absents"))
        self.assertNotIn("Le PDF ne sait pas écrire", journal)


if __name__ == "__main__":
    unittest.main()
