"""Tests de la verification du code genere et de la chaine logicielle.

L'enjeu : ne jamais livrer du code casse, et ne jamais executer du code
dangereux. Ces tests verifient surtout ce que l'usine REFUSE de faire.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

os.environ["USINE_HOME"] = tempfile.mkdtemp(prefix="usine-logi-")

from usine.core import llm, reglages  # noqa: E402
from usine.core import verification as V  # noqa: E402
from usine.pipelines import catalogue, logiciel  # noqa: E402
from usine.pipelines.base import Contexte, identifiant  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


class TestPython(unittest.TestCase):
    def test_syntaxe_cassee_detectee(self):
        rapport = V.analyser_python("def f(:\n  return 1")
        self.assertFalse(rapport.valide)
        self.assertFalse(rapport.executable)
        self.assertIn("syntaxe", rapport.casse[0].message)

    def test_la_ligne_fautive_est_indiquee(self):
        rapport = V.analyser_python("a = 1\nb = 2\ndef f(:\n    pass")
        self.assertEqual(rapport.casse[0].ligne, 3)

    def test_code_dangereux_refuse_l_execution(self):
        """Chacun de ces codes a une syntaxe valide et ne doit PAS tourner."""
        for description, code in (
            ("effacement", "import os\nos.system('rm -rf ~')"),
            ("shutil", "import shutil\nshutil.rmtree('/')"),
            ("eval", "eval(input())"),
            ("exec", "exec('x=1')"),
            ("socket", "import socket\ns = socket.socket()"),
            ("subprocess", "import subprocess\nsubprocess.run(['ls'])"),
            ("ecriture absolue", "open('/etc/passwd', 'w').write('x')"),
            ("ecriture remontante", "open('../../secret', 'w')"),
            ("ctypes", "import ctypes"),
            ("pickle", "import pickle"),
        ):
            with self.subTest(cas=description):
                rapport = V.analyser_python(code)
                self.assertTrue(rapport.valide, "la syntaxe doit rester valide")
                self.assertFalse(rapport.executable,
                                 "{} ne doit jamais etre execute".format(description))

    def test_code_sain_autorise(self):
        code = ("import argparse\n\n\ndef principal():\n"
                "    p = argparse.ArgumentParser()\n    p.parse_args()\n")
        rapport = V.analyser_python(code)
        self.assertTrue(rapport.valide)
        self.assertTrue(rapport.executable)
        self.assertEqual(rapport.soucis, [])

    def test_saisie_interactive_signalee_sans_bloquer(self):
        rapport = V.analyser_python("nom = input('nom ? ')\nprint(nom)")
        self.assertTrue(rapport.executable, "une saisie n'est pas un danger")
        self.assertTrue(any(s.gravite == "avertissement" for s in rapport.soucis))


class TestExecution(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())

    def test_script_sain_est_execute(self):
        code = "import sys\nprint('bonjour')\nsys.exit(0)\n"
        chemin = self.dossier / "ok.py"
        chemin.write_text(code, encoding="utf-8")
        execution = V.executer_python(chemin, rapport=V.analyser_python(code))
        self.assertTrue(execution.reussi)
        self.assertIn("bonjour", execution.sortie)

    def test_code_dangereux_n_est_jamais_lance(self):
        code = "import os\nos.system('echo COMPROMIS')"
        chemin = self.dossier / "mauvais.py"
        chemin.write_text(code, encoding="utf-8")
        execution = V.executer_python(chemin, rapport=V.analyser_python(code))
        self.assertFalse(execution.lance)
        self.assertIn("analyse statique", execution.refus)
        self.assertNotIn("COMPROMIS", execution.sortie)

    def test_boucle_infinie_interrompue(self):
        code = "while True:\n    pass\n"
        chemin = self.dossier / "boucle.py"
        chemin.write_text(code, encoding="utf-8")
        execution = V.executer_python(chemin, rapport=V.analyser_python(code),
                                      secondes=3)
        self.assertFalse(execution.reussi)
        self.assertIn("depassement", execution.erreur)

    def test_code_retour_non_nul_signale(self):
        code = "import sys\nsys.exit(2)\n"
        chemin = self.dossier / "echec.py"
        chemin.write_text(code, encoding="utf-8")
        execution = V.executer_python(chemin, rapport=V.analyser_python(code))
        self.assertTrue(execution.lance)
        self.assertEqual(execution.code_retour, 2)
        self.assertFalse(execution.reussi)


class TestAutresLangages(unittest.TestCase):
    def test_javascript_casse(self):
        rapport = V.analyser_js("function f( { return 1 }")
        self.assertFalse(rapport.valide)

    def test_javascript_sain(self):
        self.assertTrue(V.analyser_js("const a = 1;\nconsole.log(a);").valide)

    def test_message_node_utile(self):
        """La derniere ligne de node est sa banniere : elle n'aide pas a corriger."""
        rapport = V.analyser_js("const x = ;")
        self.assertNotIn("Node.js v", rapport.casse[0].message)
        self.assertIn("Error", rapport.casse[0].message)

    def test_controle_structurel_sans_node(self):
        """Termux n'a pas node : le repli doit quand meme voir un desequilibre."""
        rapport = V.Rapport(fichier="x.js", langage="javascript")
        V._controle_structurel("function f() { if (a) { return 1; }", rapport)
        self.assertFalse(rapport.valide)

    def test_controle_structurel_ignore_les_chaines(self):
        rapport = V.Rapport(fichier="x.js", langage="javascript")
        V._controle_structurel('const a = "un ( non ferme";', rapport)
        self.assertTrue(rapport.valide, "une parenthese dans une chaine n'est pas "
                                        "un desequilibre")

    def test_manifeste_v2_refuse(self):
        rapport = V.analyser_manifeste(json.dumps(
            {"manifest_version": 2, "name": "X", "version": "1.0"}))
        self.assertFalse(rapport.valide)

    def test_manifeste_permissions_larges_signalees(self):
        rapport = V.analyser_manifeste(json.dumps(
            {"manifest_version": 3, "name": "X", "version": "1.0.0",
             "permissions": ["tabs"], "host_permissions": ["<all_urls>"]}))
        self.assertTrue(rapport.valide)
        self.assertEqual(
            sum(1 for s in rapport.soucis if s.gravite == "avertissement"), 2)

    def test_html_balise_non_fermee(self):
        rapport = V.analyser_html("<html><body><div><p>x</body></html>")
        self.assertFalse(rapport.valide)

    def test_html_dependance_externe_signalee(self):
        rapport = V.analyser_html(
            '<html><head><script src="https://cdn.x/y.js"></script></head>'
            "<body></body></html>")
        self.assertTrue(any("hors ligne" in s.message for s in rapport.soucis))

    def test_script_inline_casse_invalide_le_html(self):
        rapport = V.analyser_html("<html><body><script>function f( {</script>"
                                  "</body></html>")
        self.assertFalse(rapport.valide)

    def test_aiguillage_par_extension(self):
        self.assertEqual(V.analyser_fichier("a.py", "x = 1").langage, "python")
        self.assertEqual(V.analyser_fichier("a.js", "const a=1;").langage,
                         "javascript")
        self.assertEqual(V.analyser_fichier("manifest.json", "{}").fichier,
                         "manifest.json")
        inconnu = V.analyser_fichier("a.zzz", "n'importe quoi")
        self.assertTrue(inconnu.valide)
        self.assertIn("aucune verification", inconnu.verifie_par)


class TestChaineLogicielle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)
        reglages.ecrire({"images": False, "qualite": "rapide", "auteur": "Tests"})

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def _produire(self, cible: str):
        contexte = Contexte(sujet="compter les mots", audience="auteurs",
                            hors_ligne=True, sans_image=True,
                            journal=lambda message: None)
        return logiciel.produire(contexte, cible=cible)

    def test_outil_en_ligne_de_commande(self):
        resultat = self._produire("cli")
        self.assertTrue(resultat["code_valide"])
        self.assertTrue(resultat["demarre"], "le script doit reellement demarrer")
        source = Path(resultat["dossier"]) / "source"
        self.assertTrue((source / "outil.py").exists())
        self.assertTrue((source / "test_outil.py").exists())

    def test_application_web_autonome(self):
        resultat = self._produire("web")
        self.assertTrue(resultat["code_valide"])
        page = (Path(resultat["dossier"]) / "source" / "index.html").read_text(
            encoding="utf-8")
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_extension_chrome(self):
        resultat = self._produire("extension")
        self.assertTrue(resultat["code_valide"])
        manifeste = json.loads(
            (Path(resultat["dossier"]) / "source" / "manifest.json").read_text(
                encoding="utf-8"))
        self.assertEqual(manifeste["manifest_version"], 3)

    def test_chaque_produit_a_son_dossier(self):
        """Deux produits crees dans la meme seconde ne doivent pas se melanger."""
        premier = self._produire("cli")
        second = self._produire("web")
        self.assertNotEqual(premier["dossier"], second["dossier"])
        sources = {f.name for f in (Path(second["dossier"]) / "source").iterdir()}
        self.assertEqual(sources, {"index.html"},
                         "les fichiers du produit precedent ont fuite")

    def test_identifiants_distincts_dans_la_meme_seconde(self):
        self.assertNotEqual(identifiant("ebook", "meme titre"),
                            identifiant("ebook", "meme titre"))

    def test_le_rapport_de_verification_est_livre(self):
        resultat = self._produire("cli")
        rapport = json.loads(
            (Path(resultat["dossier"]) / "verification.json").read_text(
                encoding="utf-8"))
        self.assertIn("verification", rapport)
        self.assertTrue(rapport["verification"]["tout_valide"])
        self.assertTrue(rapport["essais"]["essais"])

    def test_la_documentation_annonce_ce_qui_a_ete_verifie(self):
        resultat = self._produire("cli")
        doc = (Path(resultat["dossier"]) / "notice.md").read_text(encoding="utf-8")
        self.assertIn("Verification du code", doc)
        self.assertIn("execution reelle", doc)

    def test_cible_inconnue_retombe_sur_le_cli(self):
        self.assertEqual(self._produire("inexistant")["cible"], "cli")

    def test_inscrit_au_catalogue(self):
        type_produit = catalogue.obtenir("logiciel")
        self.assertIsNotNone(type_produit)
        self.assertIsNotNone(type_produit.fabriquer)
        self.assertIn("logiciel", catalogue.cles(en_file=True))


class TestReparation(unittest.TestCase):
    def test_les_instructions_de_correction_sont_exploitables(self):
        rapport = V.analyser_python("def f(:\n  pass")
        instructions = rapport.instructions_correction()
        self.assertIn("CASSE", instructions)
        self.assertIn("ligne 1", instructions)

    def test_synthese_multi_fichiers(self):
        rapports = [
            V.analyser_python("x = 1", "bon.py"),
            V.analyser_python("def f(:", "casse.py"),
            V.analyser_python("import os\nos.system('x')", "risque.py"),
        ]
        synthese = V.synthese(rapports)
        self.assertEqual(synthese["fichiers"], 3)
        self.assertEqual(synthese["valides"], 2)
        self.assertEqual(synthese["casses"], ["casse.py"])
        self.assertEqual(synthese["a_relire"], ["risque.py"])
        self.assertFalse(synthese["tout_valide"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
