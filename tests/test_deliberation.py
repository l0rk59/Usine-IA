"""Les sept agents ne se parlaient pas.

L'editeur critiquait, le reviseur appliquait. Sept agents, et aucune
conversation : une file d'attente ou chacun corrige le precedent sans jamais
lui repondre.

Le defaut que cela produit est precis. Une critique d'editeur peut etre
FAUSSE, et certaines le sont d'une facon couteuse : « ajoute un chiffre pour
appuyer cette affirmation » fait inventer une statistique, « developpe ce
passage » fait ajouter du remplissage a un texte volontairement dense,
« donne un exemple concret » fait fabriquer un temoignage. Le reviseur
appliquait tout, faute de mandat pour discuter — et le controle qualite
deterministe signalait ensuite un chiffre sans source que personne n'avait
demande.

La deliberation ajoute les deux tours qui manquaient : l'auteur repond aux
points qu'il juge errones, le controleur tranche point par point, et seules
les corrections retenues sont appliquees.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine import cli  # noqa: E402
from usine.agents import equipe  # noqa: E402
from usine.agents.base import Critique  # noqa: E402
from usine.core import llm  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402


def setUpModule():
    atelier.isoler("deliberation")


def _critique(nb=2):
    return Critique(
        note=6.0,
        problemes=[
            {"passage": "p{}".format(i), "probleme": "probleme {}".format(i),
             "gravite": "majeur", "correction": "correction {}".format(i)}
            for i in range(1, nb + 1)],
        verdict="a retravailler")


class QuandElleALieu(unittest.TestCase):

    def test_seul_le_niveau_exigeant_delibere(self):
        """Deux appels de plus par section, sur un quota gratuit, se paient
        immediatement : a douze chapitres, c'est vingt-quatre appels.

        Le niveau de qualite est deja l'endroit ou l'utilisateur declare ce
        qu'il accepte de depenser ; un second reglage pour dire la meme chose
        serait un reglage de trop.
        """
        for qualite, attendu in (("rapide", False), ("standard", False),
                                 ("exigeant", True)):
            with self.subTest(qualite=qualite):
                ctx = Contexte(sujet="x", qualite=qualite)
                self.assertEqual(equipe.deliberation_active(ctx), attendu)


class LEchange(unittest.TestCase):

    def setUp(self):
        atelier.isoler("deliberation-echange")
        llm.definir_simulateur(simulateur)
        self.ctx = Contexte(sujet="la vente", qualite="exigeant",
                            journal=lambda _m: None)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_l_auteur_conteste_et_la_correction_est_ecartee(self):
        reduite, rendu = equipe.deliberer(
            self.ctx, "Un texte dense.", _critique(2), "Chapitre 1")
        self.assertEqual(len(rendu), 1)
        self.assertFalse(rendu[0]["retenue"])
        # La critique appliquee ensuite ne porte plus que le point non conteste.
        self.assertEqual(len(reduite.problemes), 1)
        self.assertEqual(reduite.problemes[0]["probleme"], "probleme 2")

    def test_sans_objection_la_critique_passe_intacte(self):
        """La deliberation est un supplement, jamais un filtre systematique."""
        vrai = equipe.contester
        equipe.contester = lambda *a, **k: []
        try:
            critique = _critique(3)
            reduite, rendu = equipe.deliberer(self.ctx, "texte", critique, "C1")
        finally:
            equipe.contester = vrai
        self.assertEqual(rendu, [])
        self.assertIs(reduite, critique)

    def test_une_objection_sur_un_point_inexistant_est_ignoree(self):
        """Le numero vient du modele : rien ne garantit qu'il existe.

        Sans ce controle, un numero fantaisiste ferait sauter un point au
        hasard — ou lever une erreur en pleine fabrication.
        """
        critique = _critique(2)
        decisions = equipe.arbitrer(
            self.ctx, critique,
            [{"numero": 99, "raison": "point qui n'existe pas"}], "C1")
        self.assertNotIn(99, decisions)

    def test_sans_arbitrage_la_correction_est_appliquee(self):
        """Le choix conservateur, et il se justifie.

        Sans arbitrage on retombe exactement sur le comportement d'avant,
        alors qu'ecarter par defaut ferait de chaque panne d'arbitrage une
        relecture silencieusement annulee.
        """
        vrai = equipe.arbitrer
        equipe.arbitrer = lambda *a, **k: {}
        try:
            critique = _critique(2)
            reduite, rendu = equipe.deliberer(self.ctx, "texte", critique, "C1")
        finally:
            equipe.arbitrer = vrai
        self.assertEqual(len(reduite.problemes), 2, "rien ne doit etre ecarte")
        self.assertTrue(rendu and rendu[0]["retenue"])

    def test_une_panne_de_modele_ne_casse_pas_la_relecture(self):
        # Atelier neuf : sinon le cache repond a la place du modele tombe, et
        # le test verifie le cache au lieu de verifier la panne.
        atelier.isoler("deliberation-panne")

        def tombe(*_a, **_kw):
            raise llm.PlusDeFournisseur("plus rien")

        llm.definir_simulateur(tombe)
        critique = _critique(2)
        reduite, rendu = equipe.deliberer(self.ctx, "texte", critique, "C1")
        self.assertIs(reduite, critique)
        self.assertEqual(rendu, [])

    def test_le_nombre_de_contestations_est_borne(self):
        """Au-dela, ce n'est plus une contestation, c'est un refus de relecture.

        Le simulateur ordinaire ne conteste qu'un point : il ne peut donc pas
        exercer la borne. On en pose un qui conteste TOUT, ce qui est
        exactement le cas que la borne existe pour contenir.
        """
        import json as _json

        atelier.isoler("deliberation-borne")

        def conteste_tout(invite, role="standard", **kw):
            texte = (invite[-1]["content"] if isinstance(invite, list)
                     else str(invite))
            if '"objections"' in texte:
                return _json.dumps({"objections": [
                    {"numero": i, "raison": "je conteste le point {}".format(i)}
                    for i in range(1, 7)]}, ensure_ascii=False)
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(conteste_tout)
        objections = equipe.contester(self.ctx, "texte", _critique(6), "C1")
        self.assertEqual(len(objections), equipe.CONTESTATIONS_MAX)


class DansUneVraieFabrication(unittest.TestCase):
    """Le module peut etre juste et n'etre appele nulle part."""

    def setUp(self):
        atelier.isoler("deliberation-fabrication")
        self.vus = []

        def espion(invite, role="standard", **kw):
            texte = (invite[-1]["content"] if isinstance(invite, list)
                     else str(invite))
            if '"objections"' in texte:
                self.vus.append("contestation")
            if '"decisions"' in texte:
                self.vus.append("arbitrage")
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(espion)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _fabriquer(self, *options):
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(sortie):
            cli.principal(["ebook", "la vente en ligne", "--chapitres", "2",
                           "--sans-image"] + list(options))
        return sortie.getvalue()

    def test_en_exigeant_les_agents_echangent(self):
        texte = self._fabriquer("--qualite", "exigeant")
        self.assertIn("contestation", self.vus)
        self.assertIn("arbitrage", self.vus)
        self.assertIn("deliberation", texte)

    def test_en_standard_ils_n_echangent_pas(self):
        """L'autre branche. Sans elle, un « toujours delibérer » passerait."""
        self._fabriquer()
        self.assertEqual(self.vus, [])


if __name__ == "__main__":
    unittest.main()
