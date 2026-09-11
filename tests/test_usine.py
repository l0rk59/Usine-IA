"""Suite de tests de l'Usine-IA.

Aucun appel reseau : le routeur IA est remplace par un simulateur.
Lancement :  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# Le dossier de travail doit etre isole AVANT le premier import de config.
_TEMPORAIRE = tempfile.mkdtemp(prefix="usine-tests-")
os.environ["USINE_HOME"] = _TEMPORAIRE

from usine.core import config, llm, store  # noqa: E402
from usine.pipelines import base, ebook  # noqa: E402
from usine.render import document as D  # noqa: E402
from usine.render.epub import construire_epub  # noqa: E402
from usine.render.metriques import largeur_texte  # noqa: E402
from usine.render.pdf import DocumentPDF, dimensions_jpeg  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


class TestConfiguration(unittest.TestCase):
    def test_tous_les_fournisseurs_ont_un_modele(self):
        for fournisseur in config.PROVIDERS:
            for role in ("rapide", "standard", "costaud"):
                self.assertTrue(fournisseur.model_for(role),
                                "modele manquant : {}/{}".format(fournisseur.name, role))

    def test_les_url_sont_https_sauf_en_local(self):
        for fournisseur in config.PROVIDERS:
            if fournisseur.local:
                continue
            self.assertTrue(fournisseur.base_url.startswith("https://"),
                            "URL non chiffree : " + fournisseur.name)

    def test_les_fournisseurs_locaux_passent_en_dernier(self):
        os.environ["USINE_PROVIDERS"] = "ollama,groq,pollinations"
        try:
            noms = [p.name for p in config.active_providers()]
        finally:
            os.environ.pop("USINE_PROVIDERS", None)
        self.assertEqual(noms[-1], "ollama",
                         "l'IA locale doit rester le dernier recours")

    def test_lecture_env(self):
        chemin = Path(_TEMPORAIRE) / "essai.env"
        chemin.write_text(
            '# commentaire\nexport CLE_A="valeur a"\nCLE_B=valeur-b\nVIDE=\n',
            encoding="utf-8",
        )
        lues = config.load_env(chemin, override=True)
        self.assertEqual(lues["CLE_A"], "valeur a")
        self.assertEqual(lues["CLE_B"], "valeur-b")
        self.assertEqual(lues["VIDE"], "")


class TestRouteurIA(unittest.TestCase):
    def test_extraction_json_dans_un_bloc_markdown(self):
        self.assertEqual(llm.extraire_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_extraction_json_avec_bavardage(self):
        self.assertEqual(
            llm.extraire_json('Bien sur ! Voici : {"a": [1, 2]} Bonne lecture.'),
            {"a": [1, 2]},
        )

    def test_extraction_json_avec_virgule_finale(self):
        self.assertEqual(llm.extraire_json('{"a": 1, "b": 2,}'), {"a": 1, "b": 2})

    def test_json_introuvable_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            llm.extraire_json("aucune structure ici")

    def test_le_cache_evite_un_second_appel(self):
        appels = []

        def compteur(messages, role):
            appels.append(1)
            return "reponse"

        llm.definir_simulateur(compteur)
        try:
            invite = "question unique pour le test du cache"
            self.assertEqual(llm.generer(invite).texte, "reponse")
            deuxieme = llm.generer(invite)
            self.assertEqual(deuxieme.texte, "reponse")
            self.assertTrue(deuxieme.depuis_cache)
            self.assertEqual(len(appels), 1, "le cache n'a pas ete utilise")
        finally:
            llm.definir_simulateur(simulateur)


class TestModeleDocument(unittest.TestCase):
    def setUp(self):
        self.blocs = D.analyser(
            "# Titre\n\nUn **paragraphe**.\n\n## Section\n\n- a\n- b\n\n"
            "1. un\n2. deux\n\n> citation\n\n**A retenir :** l'essentiel.\n\n---\n\n"
            "```\ncode\n```\n"
        )

    def test_types_de_blocs(self):
        self.assertEqual(
            [b.type for b in self.blocs],
            ["h1", "p", "h2", "ul", "ol", "quote", "callout", "hr", "code"],
        )

    def test_html_echappe_le_contenu_hostile(self):
        html = D.vers_html(D.analyser("Un <script>alert(1)</script> injecte"))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_conserve_le_balisage_inline(self):
        html = D.vers_html(D.analyser("du **gras** et un [lien](https://exemple.fr)"))
        self.assertIn("<strong>gras</strong>", html)
        self.assertIn('href="https://exemple.fr"', html)

    def test_texte_brut_retire_le_balisage(self):
        texte = D.vers_texte(D.analyser("du **gras** ici"))
        self.assertNotIn("**", texte)
        self.assertIn("gras", texte)


class TestNettoyage(unittest.TestCase):
    def test_slug_sans_accent_ni_espace(self):
        self.assertEqual(base.slug("Été à Paris — édition 2026"),
                         "ete-a-paris-edition-2026")

    def test_slug_ne_rend_jamais_une_chaine_vide(self):
        self.assertTrue(base.slug("!!!???"))

    def test_nettoyer_titre(self):
        self.assertEqual(base.nettoyer_titre("## Chapitre 3 : **Vendre**"), "Vendre")
        self.assertEqual(base.nettoyer_titre('"Un titre"'), "Un titre")

    def test_elaguer_preambule_et_clotures(self):
        self.assertEqual(
            base.elaguer_markdown("Voici le texte :\n\n```markdown\n# T\n\nx\n```"),
            "# T\n\nx",
        )


class TestPDF(unittest.TestCase):
    def _construire(self) -> bytes:
        doc = DocumentPDF(titre_courant="Test")
        doc.page_couverture("Un titre", "un sous-titre", "un auteur")
        for numero in range(1, 6):
            doc.titre("Chapitre {}".format(numero), 1)
            doc.paragraphe("Accentué : éàçùî. " * 40, justifier=True)
            doc.titre("Sous-partie", 2)
            doc.liste(["point un", "point deux"])
            doc.cases_a_cocher(["a cocher"])
            doc.citation("une citation")
            doc.encadre("A retenir", "un encadre")
            doc.lignes_a_remplir(3)
        doc.inserer_sommaire(apres=1)
        chemin = Path(_TEMPORAIRE) / "test.pdf"
        doc.enregistrer(chemin)
        return chemin.read_bytes()

    def test_structure_valide(self):
        brut = self._construire()
        self.assertTrue(brut.startswith(b"%PDF-1.4"))
        self.assertTrue(brut.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Type /Catalog", brut)
        self.assertIn(b"/Type /Pages", brut)

    def test_table_xref_coherente(self):
        """Chaque decalage de la xref doit pointer sur le bon objet."""
        brut = self._construire()
        debut = int(brut[brut.rfind(b"startxref") + 9 : brut.rfind(b"%%EOF")].strip())
        self.assertEqual(brut[debut : debut + 4], b"xref")
        lignes = brut[debut:].split(b"\n")
        nombre = int(lignes[1].split()[1])
        for numero in range(1, nombre):
            decalage = int(lignes[2 + numero].split()[0])
            attendu = "{} 0 obj".format(numero).encode("latin-1")
            self.assertEqual(brut[decalage : decalage + len(attendu)], attendu,
                             "objet {} mal reference dans la xref".format(numero))

    def test_sommaire_place_en_deuxieme_page(self):
        doc = DocumentPDF()
        doc.page_couverture("T", "s", "a")
        doc.titre("Premier chapitre", 1)
        doc.paragraphe("corps")
        doc.inserer_sommaire(apres=1)
        doc._fermer_page()
        contenu = "\n".join(doc._pages[1][0])
        self.assertIn("Sommaire", contenu)

    def test_coupe_les_mots_plus_longs_que_la_ligne(self):
        doc = DocumentPDF()
        lignes = doc.couper("a" * 400, "Helvetica", 12, 200)
        self.assertGreater(len(lignes), 1)
        for ligne in lignes:
            self.assertLessEqual(largeur_texte(ligne, "Helvetica", 12), 200.5)

    def test_lecture_des_dimensions_jpeg(self):
        """Le SOF0 place la hauteur AVANT la largeur : verifions l'ordre."""
        entete_jfif = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        sof0 = (
            b"\xff\xc0"
            + (17).to_bytes(2, "big")      # longueur du segment
            + b"\x08"                      # precision
            + (7).to_bytes(2, "big")       # hauteur
            + (13).to_bytes(2, "big")      # largeur
            + b"\x03"                      # composantes (RGB)
            + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        )
        jpeg = b"\xff\xd8" + entete_jfif + sof0 + b"\xff\xd9"
        self.assertEqual(dimensions_jpeg(jpeg), (13, 7, 3))

    def test_refuse_les_donnees_non_jpeg(self):
        self.assertIsNone(dimensions_jpeg(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40))


class TestEPUB(unittest.TestCase):
    def setUp(self):
        self.chemin = Path(_TEMPORAIRE) / "test.epub"
        construire_epub(
            self.chemin, "Un livre", "Un auteur",
            [("Chapitre {}".format(i), "<p>Contenu accentué : éàç</p>") for i in range(1, 4)],
            sous_titre="Sous-titre", description="Description",
        )

    def test_mimetype_premier_et_non_compresse(self):
        with zipfile.ZipFile(self.chemin) as z:
            premier = z.infolist()[0]
            self.assertEqual(premier.filename, "mimetype")
            self.assertEqual(premier.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(z.read("mimetype"), b"application/epub+zip")

    def test_archive_saine(self):
        with zipfile.ZipFile(self.chemin) as z:
            self.assertIsNone(z.testzip())

    def test_tout_le_xml_est_bien_forme(self):
        with zipfile.ZipFile(self.chemin) as z:
            for nom in z.namelist():
                if nom.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                    ET.fromstring(z.read(nom))  # leve si mal forme

    def test_chapitres_references_dans_le_spine(self):
        with zipfile.ZipFile(self.chemin) as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
        for numero in range(1, 4):
            self.assertIn('idref="ch{:03d}"'.format(numero), opf)


class TestChaineComplete(unittest.TestCase):
    """Fabrication d'un ebook de bout en bout, sans reseau."""

    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)
        contexte = base.Contexte(
            sujet="un sujet de test", audience="des testeurs",
            taille="mini", hors_ligne=True, sans_image=True, auteur="Tests",
            journal=lambda message: None,
        )
        cls.resume = ebook.produire(contexte)
        cls.dossier = Path(cls.resume["dossier"])

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def test_tous_les_formats_sont_produits(self):
        noms = {f.name for f in self.dossier.iterdir()}
        self.assertIn("livre.md", noms)
        self.assertIn("livre.txt", noms)
        self.assertIn("lire.html", noms)
        self.assertTrue(any(n.endswith(".pdf") for n in noms))
        self.assertTrue(any(n.endswith(".epub") for n in noms))

    def test_le_produit_est_enregistre_au_catalogue(self):
        produit = store.lire_produit(self.resume["produit_id"])
        self.assertIsNotNone(produit)
        self.assertEqual(produit["statut"], "pret")

    def test_les_etapes_sont_journalisees(self):
        etapes = store.etapes_produit(self.resume["produit_id"])
        noms = {e["nom"] for e in etapes}
        self.assertIn("plan", noms)
        self.assertIn("introduction", noms)
        self.assertIn("conclusion", noms)

    def test_le_contenu_a_du_volume(self):
        self.assertGreater(self.resume["mots"], 200)
        self.assertEqual(self.resume["chapitres"], 6)

    def test_empaquetage(self):
        from usine.packaging import livraison

        # Le kit de vente du vendeur ne doit jamais entrer dans l'archive client.
        (self.dossier / "marketing").mkdir(exist_ok=True)
        (self.dossier / "marketing" / "page-de-vente.html").write_text(
            "prix plancher", encoding="utf-8"
        )
        archive = livraison.empaqueter(self.dossier, "test-livrable",
                                       self.resume["titre"], "Tests")
        self.assertTrue(archive.exists())
        with zipfile.ZipFile(archive) as z:
            noms = z.namelist()
            self.assertIsNone(z.testzip())
            self.assertTrue(any(n.endswith("LISEZ-MOI.md") for n in noms))
            self.assertTrue(any(n.endswith("LICENCE.txt") for n in noms))
            self.assertFalse(any(n.endswith("plan.json") for n in noms),
                             "les fichiers de travail ne doivent pas etre livres")
            self.assertFalse(any("marketing" in n for n in noms),
                             "le kit de vente ne doit pas etre livre a l'acheteur")


class TestServeurWeb(unittest.TestCase):
    """Tests HTTP reels : le serveur est demarre sur un port libre."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        from usine.web import serveur

        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.port = cls.serveur.server_address[1]
        cls.fil = threading.Thread(target=cls.serveur.serve_forever, daemon=True)
        cls.fil.start()
        cls.base = "http://127.0.0.1:{}".format(cls.port)

        # Un fichier legitime, et un fichier secret hors de l'atelier.
        config.PRODUITS_DIR.mkdir(parents=True, exist_ok=True)
        (config.PRODUITS_DIR / "demo").mkdir(exist_ok=True)
        (config.PRODUITS_DIR / "demo" / "lire.html").write_text("<p>ok</p>",
                                                                encoding="utf-8")
        (config.WORKDIR / "secret.txt").write_text("NE DOIT PAS FUIR", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def _appeler(self, chemin: str):
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(self.base + chemin, timeout=10) as reponse:
                return reponse.status, reponse.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_page_d_accueil(self):
        statut, corps = self._appeler("/")
        self.assertEqual(statut, 200)
        self.assertIn(b"Usine-IA", corps)

    def test_api_etat(self):
        import json

        statut, corps = self._appeler("/api/etat")
        self.assertEqual(statut, 200)
        donnees = json.loads(corps)
        self.assertIn("fournisseurs", donnees)
        self.assertTrue(donnees["fournisseurs"])

    def test_fichier_legitime_servi(self):
        statut, corps = self._appeler("/fichier/demo/lire.html")
        self.assertEqual(statut, 200)
        self.assertIn(b"ok", corps)

    def test_traversee_de_chemin_refusee(self):
        """Aucune de ces formes ne doit sortir du dossier des produits."""
        for tentative in (
            "/fichier/%2e%2e/secret.txt",
            "/fichier/demo/%2e%2e/%2e%2e/secret.txt",
            "/fichier/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "/fichier/demo/../../secret.txt",
        ):
            statut, corps = self._appeler(tentative)
            self.assertIn(statut, (400, 403, 404),
                          "chemin accepte a tort : " + tentative)
            self.assertNotIn(b"NE DOIT PAS FUIR", corps,
                             "fuite de fichier via : " + tentative)

    def test_fabrication_refusee_sans_sujet(self):
        import json
        import urllib.error
        import urllib.request

        requete = urllib.request.Request(
            self.base + "/api/fabriquer",
            data=json.dumps({"type": "ebook"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as contexte:
            urllib.request.urlopen(requete, timeout=10)
        self.assertEqual(contexte.exception.code, 400)

    def test_type_de_produit_inconnu_refuse(self):
        import json
        import urllib.error
        import urllib.request

        requete = urllib.request.Request(
            self.base + "/api/fabriquer",
            data=json.dumps({"type": "malveillant", "sujet": "x"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as contexte:
            urllib.request.urlopen(requete, timeout=10)
        self.assertEqual(contexte.exception.code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPersonnalisation(unittest.TestCase):
    """Le type, le ton et le volume doivent se regler a volonte.

    Cinq tons fermes et quatre volumes imposaient les memes reglages a tout
    un catalogue — ce qui est exactement ce qui fait que les produits se
    ressemblent.
    """

    def test_un_ton_libre_est_accepte_tel_quel(self):
        from usine.pipelines.base import resoudre_ton

        libre = "comme un vieux menuisier qui explique a son apprenti"
        self.assertEqual(resoudre_ton(libre), libre)

    def test_les_tons_predefinis_restent_des_raccourcis(self):
        from usine.pipelines.base import TONS, resoudre_ton

        self.assertEqual(resoudre_ton("punchy"), TONS["punchy"])
        self.assertEqual(resoudre_ton("PUNCHY"), TONS["punchy"])
        self.assertEqual(resoudre_ton(""), TONS["pro"])

    def test_le_ton_libre_atteint_l_invite(self):
        from usine.pipelines.base import Contexte

        contexte = Contexte(sujet="x", ton="sec et factuel, sans adjectif")
        self.assertIn("sec et factuel, sans adjectif",
                      contexte.systeme("un redacteur"))

    def test_un_nombre_de_sections_se_demande_directement(self):
        from usine.pipelines.base import resoudre_taille

        self.assertEqual(resoudre_taille("", chapitres=15)[0], 15)
        self.assertEqual(resoudre_taille("15")[0], 15)
        self.assertEqual(resoudre_taille("standard", 24, 1500), (24, 1500))

    def test_les_raccourcis_de_volume_restent_valables(self):
        from usine.pipelines.base import TAILLES, resoudre_taille

        for nom, attendu in TAILLES.items():
            self.assertEqual(resoudre_taille(nom), attendu)

    def test_les_valeurs_absurdes_sont_bornees_pas_refusees(self):
        """Un quota gratuit ne tient pas neuf cents chapitres."""
        from usine.pipelines.base import (CHAPITRES_MAX, CHAPITRES_MIN,
                                          MOTS_MAX, MOTS_MIN, resoudre_taille)

        self.assertEqual(resoudre_taille("", 900, 99999),
                         (CHAPITRES_MAX, MOTS_MAX))
        self.assertEqual(resoudre_taille("", 1, 10), (CHAPITRES_MIN, MOTS_MIN))

    def test_le_contexte_suit_le_sur_mesure(self):
        from usine.pipelines.base import Contexte

        contexte = Contexte(sujet="x", taille="mini", chapitres=20, mots_section=900)
        self.assertEqual(contexte.nb_chapitres, 20)
        self.assertEqual(contexte.mots_par_chapitre, 900)

    def test_la_ligne_de_commande_accepte_un_ton_libre(self):
        """argparse refusait tout ton hors des cinq choix."""
        from usine import cli

        parseur = cli.construire_parseur()
        args = parseur.parse_args(
            ["ebook", "un sujet", "-t", "comme un menuisier", "-T", "15",
             "--chapitres", "7"])
        self.assertEqual(args.ton, "comme un menuisier")
        self.assertEqual(args.chapitres, 7)
