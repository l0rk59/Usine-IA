"""La boite a outils et les modeles avaient une seule forme, choisie pour tous.

Mesure du 26/09/2026 :

- la boite a outils imposait TOUJOURS un melange de checklists, de modeles
  et de tableaux. Un pack de trente checklists, un pack de modeles a
  completer et un classeur de suivi sont trois produits distincts sur une
  place de marche, cherches avec des mots differents ;
- les modeles visaient « Notion ou un tableur » a la fois, et le guide
  livre expliquait les deux a chaque acheteur. Notion relie des bases et
  filtre des vues, un tableur calcule avec des formules : un systeme pense
  pour les deux n'exploite ni l'un ni l'autre.

Chaque reglage est suivi jusqu'a l'invite qui part au modele, et jusqu'a ce
qui est livre.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests import simulateur as sim  # noqa: E402
from usine.core import llm  # noqa: E402
from usine.pipelines import boite_outils, catalogue, modeles  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402

INVITES: List[str] = []


def _espion(messages, role):
    INVITES.append(messages[-1]["content"])
    return sim.simulateur(messages, role)


def setUpModule():
    atelier.isoler("composition-outil")
    llm.definir_simulateur(_espion)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet: str, journal=None) -> Contexte:
    # Une audience par cas : elle entre dans la consigne systeme, donc dans
    # la cle du cache, et deux cas au meme plan simule ne se liront pas.
    return Contexte(sujet=sujet, audience="des lecteurs de " + sujet,
                    sans_image=True, journal=journal or (lambda _m: None))


def _invite(debut: str) -> str:
    return next(i for i in INVITES if i.startswith(debut))


class LaCompositionDeLaBoite(unittest.TestCase):

    def test_chaque_composition_arrive_au_sommaire(self):
        for cle, fiche in boite_outils.COMPOSITIONS.items():
            with self.subTest(composition=cle):
                INVITES.clear()
                catalogue.executer("outils", _contexte("le demenagement " + cle),
                                   {"nombre": 3, "composition": cle})
                self.assertIn(fiche["consigne"],
                              _invite("Concois une boite a outils"))

    def test_un_pack_de_checklists_ne_livre_que_des_checklists(self):
        """Le modele derive parfois vers un tableau : ce qui a ete choisi
        est ce qui est vendu."""
        INVITES.clear()
        resume = catalogue.executer("outils", _contexte("la rentree scolaire"),
                                    {"nombre": 4, "composition": "checklists"})
        import json

        boite = json.loads((Path(resume["dossier"]) / "boite.json").read_text(
            encoding="utf-8"))
        redaction = [i for i in INVITES if i.startswith("Boite a outils")]
        self.assertTrue(redaction)
        for invite in redaction:
            self.assertIn("(type : checklist)", invite)
        self.assertEqual({o["type"] for o in boite["outils"]}, {"checklist"})

    def test_la_composition_par_defaut_se_dit(self):
        lignes: List[str] = []
        boite_outils.produire(_contexte("le compost", journal=lignes.append),
                              nombre=3)
        self.assertTrue(any("personne ne l'a choisie" in l for l in lignes))


class LOutilDesModeles(unittest.TestCase):

    def test_notion_parle_de_relations_et_le_tableur_de_formules(self):
        INVITES.clear()
        catalogue.executer("modeles", _contexte("un suivi de clients notion"),
                           {"nombre": 2, "outil": "notion"})
        conception = _invite("Concois un systeme")
        self.assertIn("RELATIONS", conception)
        self.assertNotIn("formule exacte", conception)
        guide = _invite("Systeme : ")
        self.assertIn("Installation dans Notion", guide)
        self.assertNotIn("Installation dans un tableur", guide)

        INVITES.clear()
        catalogue.executer("modeles", _contexte("un suivi de clients tableur"),
                           {"nombre": 2, "outil": "tableur"})
        conception = _invite("Concois un systeme")
        self.assertIn("formule exacte", conception)
        guide = _invite("Systeme : ")
        self.assertIn("Installation dans un tableur", guide)
        self.assertNotIn("Installation dans Notion", guide)

    def test_l_outil_par_defaut_se_dit(self):
        lignes: List[str] = []
        modeles.produire(_contexte("un budget familial", journal=lignes.append),
                         nombre=2)
        self.assertTrue(any("personne ne l'a choisi" in l for l in lignes))


class LesPortes(unittest.TestCase):

    def test_le_menu_propose_les_deux_reglages(self):
        from usine import menu

        for cle, attendu in (("outils", {"composition": "melange"}),
                             ("modeles", {"outil": "notion"})):
            with self.subTest(type=cle):
                reponses = iter(["2"])
                sortie = io.StringIO()
                with redirect_stdout(sortie), mock.patch(
                        "builtins.input", lambda invite="": next(reponses, "")):
                    self.assertEqual(menu._options_du_type(cle), attendu)

    def test_l_usine_les_decide_quand_personne_ne_les_choisit(self):
        for cle, nom in (("outils", "composition"), ("modeles", "outil")):
            with self.subTest(type=cle):
                ctx = _contexte("un sujet pour " + cle)
                catalogue.executer(cle, ctx, {"nombre": 2})
                self.assertIn(nom, ctx.meta.get("reglages_decides", {}))


if __name__ == "__main__":
    unittest.main()
