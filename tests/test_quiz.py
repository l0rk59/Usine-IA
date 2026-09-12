"""Le quiz auto-corrige : une page qui se corrige seule, hors ligne.

Ce qui est verifie ici tient en trois points. La page doit etre UTILISABLE
(vrais boutons radio etiquetes, questions groupees, verdicts annonces au
lecteur d'ecran), son script doit etre VALIDE — il ne sert a rien qu'une page
se corrige mal — et les donnees du modele doivent etre FILTREES : une reponse
hors des bornes afficherait « la bonne reponse etait undefined » a un
acheteur.

Le comportement du script dans un vrai navigateur a ete verifie a la main
(Chromium : bonne reponse marquee juste, mauvaise corrigee avec l'explication,
questions sans reponse comptees). La suite, elle, doit tourner sur une
installation Python nue : elle verifie la structure et la syntaxe, pas le
rendu.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, verification  # noqa: E402
from usine.render import quiz  # noqa: E402

QUESTIONS = [
    {"module": "Module 1 — le diagnostic",
     "question": "Par quoi commencer ?",
     "propositions": ["Tout lister", "Poser l'objectif", "Demander"],
     "reponse": 1, "explication": "L'objectif decide du reste."},
    {"module": "Module 1 — le diagnostic",
     "question": "Combien de temps y consacrer ?",
     "propositions": ["Dix minutes", "Une journee"],
     "reponse": 0, "explication": "Dix minutes suffisent a trancher."},
    {"module": "Module 2 — la mise en oeuvre",
     "question": "Que faire du reste ?",
     "propositions": ["Le jeter", "L'archiver", "Le deleguer"],
     "reponse": 2, "explication": "Deleguer garde la matiere disponible."},
]


def setUpModule():
    atelier.isoler("quiz")
    llm.definir_simulateur(simulateur)


def tearDownModule():
    llm.definir_simulateur(None)


def _ecrire(questions=None) -> str:
    chemin = Path(tempfile.mkdtemp(prefix="usine-quiz-")) / "quiz.html"
    quiz.ecrire(chemin, "Ma formation", questions or QUESTIONS,
                promesse="Savoir trancher vite.")
    return chemin.read_text(encoding="utf-8")


class TestStructure(unittest.TestCase):
    def setUp(self):
        self.page = _ecrire()

    def test_une_question_par_groupe_de_champs(self):
        """« fieldset » + « legend » : le lecteur d'ecran annonce la question
        avant de lire les propositions. Une suite de radios sans groupe
        laisserait l'utilisateur deviner a quoi il repond."""
        self.assertEqual(self.page.count('<fieldset class="question">'), 3)
        self.assertEqual(self.page.count("<legend>"), 3)

    def test_chaque_proposition_est_un_bouton_radio_etiquete(self):
        radios = re.findall(r'<input type="radio" id="(q\d+-\d+)"', self.page)
        self.assertEqual(len(radios), 8)
        for identifiant in radios:
            self.assertIn('for="{}"'.format(identifiant), self.page,
                          "proposition sans etiquette cliquable")

    def test_les_propositions_d_une_question_partagent_leur_nom(self):
        """Sinon on pourrait cocher deux reponses a la meme question."""
        for index, attendu in enumerate((3, 2, 3)):
            self.assertEqual(
                self.page.count('name="q{}"'.format(index)), attendu)

    def test_les_verdicts_sont_annonces(self):
        self.assertEqual(self.page.count('aria-live="polite"'), 4,
                         "un par question, plus le score")

    def test_les_modules_ordonnent_la_page(self):
        self.assertIn("<h2>Module 1 — le diagnostic</h2>", self.page)
        self.assertIn("<h2>Module 2 — la mise en oeuvre</h2>", self.page)
        self.assertEqual(self.page.count("<h2>"), 2,
                         "un titre par module, pas un par question")

    def test_la_page_est_autonome(self):
        """Elle s'ouvre depuis un dossier, sans reseau ni bibliotheque."""
        self.assertNotIn("http://", self.page)
        self.assertNotIn("<script src", self.page)
        for distant in ("cdn", "googleapis", "unpkg"):
            self.assertNotIn(distant, self.page.lower())

    def test_le_bouton_disparait_a_l_impression(self):
        self.assertIn("@media print", quiz.STYLE)


class TestDonneesEmbarquees(unittest.TestCase):
    def test_les_reponses_sont_lisibles_par_le_script(self):
        page = _ecrire()
        brut = re.search(
            r'<script type="application/json" id="reponses">(.*?)</script>',
            page, re.DOTALL)
        self.assertIsNotNone(brut)
        donnees = json.loads(brut.group(1).replace("<\\/", "</"))
        self.assertEqual(len(donnees), 3)
        self.assertEqual(donnees[0]["reponse"], 1)

    def test_une_question_ne_peut_pas_fermer_le_script(self):
        """Un « </script> » dans un intitule couperait la page en deux."""
        piege = [{"module": "", "question": "Que fait </script> ici ?",
                  "propositions": ["Rien", "Il casse la page"],
                  "reponse": 1, "explication": "</script> ferme la balise."}]
        page = _ecrire(piege)
        # Une seule balise de script ouvrante pour les donnees, une pour le
        # comportement : la charge ne doit pas en fabriquer une troisieme.
        self.assertEqual(page.count("</script>"), 2)
        self.assertIn("<\\/script>", page)

    def test_le_html_d_une_question_est_echappe(self):
        piege = [{"module": "", "question": "<b>gras</b> ?",
                  "propositions": ["<i>oui</i>", "non"],
                  "reponse": 0, "explication": "x"}]
        page = _ecrire(piege)
        self.assertIn("&lt;b&gt;gras&lt;/b&gt;", page)
        self.assertNotIn("<b>gras</b>", page)


class TestScript(unittest.TestCase):
    def test_le_script_est_syntaxiquement_valide(self):
        """Une page qui se corrige mal ne vaut pas mieux qu'aucune page."""
        rapport = verification.analyser_js(quiz.SCRIPT, "quiz.js")
        self.assertTrue(rapport.valide, [s.message for s in rapport.soucis])

    def test_il_ne_sort_jamais_du_navigateur(self):
        """« Rien n'est envoye » est ecrit dans la page : ce doit etre vrai."""
        for interdit in ("fetch(", "XMLHttpRequest", "navigator.sendBeacon",
                         "WebSocket", "localStorage"):
            self.assertNotIn(interdit, quiz.SCRIPT)


class TestFiltrageDesQuestions(unittest.TestCase):
    """Ce que le modele renvoie n'est pas affichable tel quel."""

    compteur = itertools.count()

    def _quiz(self, brut):
        from usine.pipelines import formation
        from usine.pipelines.base import Contexte

        # Un titre different a chaque appel : les reponses du modele sont
        # mises en cache par empreinte de l'invite, et deux cas de test qui
        # posent la meme question recevraient la meme reponse — le second
        # testerait alors le cache, pas le filtre.
        programme = {"titre": "T{}".format(next(self.compteur)), "promesse": "P",
                     "modules": [{"titre": "Module 1", "objectif": "o",
                                  "notions": ["n"], "livrable": "", "exercice": ""}]}
        llm.definir_simulateur(lambda messages, role: json.dumps(brut))
        try:
            contexte = Contexte(sujet="x", journal=lambda message: None)
            return formation._quiz(contexte, programme)
        finally:
            llm.definir_simulateur(simulateur)

    def test_une_reponse_hors_des_bornes_est_ecartee(self):
        """Sinon la page annonce « la bonne reponse etait undefined »."""
        retenues = self._quiz({"quiz": [
            {"module": "Module 1", "question": "q", "propositions": ["a", "b"],
             "reponse": 7, "explication": "e"},
            {"module": "Module 1", "question": "q2", "propositions": ["a", "b"],
             "reponse": -1, "explication": "e"},
            {"module": "Module 1", "question": "bonne", "propositions": ["a", "b"],
             "reponse": 1, "explication": "e"},
        ]})
        self.assertEqual([q["question"] for q in retenues], ["bonne"])

    def test_une_question_a_une_seule_proposition_est_ecartee(self):
        retenues = self._quiz({"quiz": [
            {"module": "Module 1", "question": "q", "propositions": ["seule"],
             "reponse": 0, "explication": "e"}]})
        self.assertEqual(retenues, [])

    def test_une_question_sans_intitule_est_ecartee(self):
        retenues = self._quiz({"quiz": [
            {"module": "Module 1", "question": "   ",
             "propositions": ["a", "b"], "reponse": 0, "explication": "e"}]})
        self.assertEqual(retenues, [])

    def test_un_module_invente_est_efface_plutot_que_retenu(self):
        """Le programme fait foi : un titre inconnu ferait un intertitre orphelin."""
        retenues = self._quiz({"quiz": [
            {"module": "Module fantome", "question": "q",
             "propositions": ["a", "b"], "reponse": 0, "explication": "e"}]})
        self.assertEqual(retenues[0]["module"], "")

    def test_une_reponse_illisible_ne_leve_pas(self):
        retenues = self._quiz({"quiz": [
            {"module": "Module 1", "question": "q", "propositions": ["a", "b"],
             "reponse": "la deuxieme", "explication": "e"}]})
        self.assertEqual(retenues, [])

    def test_un_json_sans_quiz_rend_une_liste_vide(self):
        self.assertEqual(self._quiz({"autre": []}), [])


class TestDansLaChaine(unittest.TestCase):
    def test_la_formation_livre_son_quiz(self):
        from usine.pipelines import formation
        from usine.pipelines.base import Contexte

        contexte = Contexte(sujet="le copywriting", hors_ligne=True,
                            sans_image=True, journal=lambda message: None)
        resume = formation.produire(contexte, modules=2)
        self.assertEqual(resume["questions"], 4)
        self.assertIn("quiz.html", resume["fichiers"])
        page = (Path(resume["dossier"]) / "quiz.html").read_text(encoding="utf-8")
        self.assertEqual(page.count('<fieldset class="question">'), 4)

    def test_sans_question_aucun_fichier_n_est_ecrit(self):
        """Un quiz vide serait une page avec un bouton et rien a corriger."""
        from usine.pipelines import formation
        from usine.pipelines.base import Contexte

        original = formation._quiz
        formation._quiz = lambda *a, **k: []
        try:
            contexte = Contexte(sujet="x", hors_ligne=True, sans_image=True,
                                journal=lambda message: None)
            resume = formation.produire(contexte, modules=2)
        finally:
            formation._quiz = original
        self.assertEqual(resume["questions"], 0)
        self.assertNotIn("quiz.html", resume["fichiers"])


if __name__ == "__main__":
    unittest.main()
