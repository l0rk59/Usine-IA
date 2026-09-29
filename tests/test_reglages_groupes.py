"""Trente reglages, dont dix-huit que le tableau de bord ne montrait pas.

Mesure du 13/09/2026 : sur vingt-six reglages declares, le tableau de bord en
exposait huit. Les dix-huit autres — le contact imprime dans la notice de
l'acheteur, la marque, la devise, les budgets qui arretent l'usine continue —
n'existaient que dans un fichier JSON que personne n'ouvre.

Et sur les vingt-six, deux ne servaient a rien : « plateforme » et « devise »
etaient affiches dans les trois interfaces, enregistres sur disque, et lus par
personne — leurs valeurs par defaut etaient ecrites en dur dans la CLI. Qui
vend en francs suisses reglait sa devise et voyait « EUR » a chaque import.
Le garde-fou cense attraper exactement cela ne les voyait pas : il cherchait
le nom du reglage n'importe ou dans le code, et « devise » apparait dans
n'importe quelle ligne qui parle de ventes.
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
from usine import cli
from usine.pipelines import apres  # noqa: E402
from usine.core import reglages  # noqa: E402


def setUpModule():
    atelier.isoler("reglages-groupes")


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class LesGroupes(unittest.TestCase):

    def tearDown(self):
        reglages.reinitialiser()

    def test_aucun_reglage_n_est_hors_groupe(self):
        """Un reglage hors groupe est INVISIBLE partout ou l'on affiche par
        groupe : sauvegarde, lu par le code, et impossible a changer."""
        self.assertEqual(reglages.non_groupes(), [])

    def test_aucun_reglage_n_est_dans_deux_groupes(self):
        """Il apparaitrait deux fois dans le menu, avec deux numeros."""
        vus = [nom for groupe in reglages.GROUPES for nom in groupe["reglages"]]
        self.assertEqual(len(vus), len(set(vus)))

    def test_chaque_reglage_a_une_description(self):
        """Un reglage sans description est un champ de saisie muet : on ne
        sait ni ce qu'il fait, ni ce qu'on a le droit d'y mettre."""
        for nom in reglages.DEFAUTS:
            with self.subTest(reglage=nom):
                self.assertTrue(reglages.DESCRIPTIONS.get(nom, "").strip())

    def test_l_ordre_affiche_suit_les_groupes(self):
        """L'ordre donne son numero a chaque reglage dans le menu.

        Le laisser suivre l'ordre de declaration pendant que le menu affiche
        par groupe ferait pointer chaque numero sur un autre reglage :
        l'utilisateur croirait changer le ton et changerait la devise.
        """
        attendu = [nom for groupe in reglages.GROUPES
                   for nom in groupe["reglages"]]
        self.assertEqual([l["nom"] for l in reglages.lignes_affichables()],
                         attendu)


class LesReglagesQuiNePilotaientRien(unittest.TestCase):

    def tearDown(self):
        reglages.reinitialiser()

    def test_la_plateforme_reglee_devient_le_defaut(self):
        reglages.ecrire({"plateforme": "etsy"})
        parseur = cli.construire_parseur()
        args = parseur.parse_args(["ebook", "un sujet"])
        self.assertEqual(args.plateforme, "etsy")

    def test_la_devise_reglee_devient_le_defaut(self):
        """Qui vend en francs suisses voyait « EUR » a chaque import."""
        reglages.ecrire({"devise": "CHF"})
        parseur = cli.construire_parseur()
        args = parseur.parse_args(["ventes", "--ajouter", "un produit"])
        self.assertEqual(args.devise, "CHF")


class LeReglageDecideEtLOptionTranche(unittest.TestCase):
    """Le confort ne doit pas devenir un piege.

    Sans forme negative, un reglage active ne pourrait plus jamais etre
    annule pour un seul produit.
    """

    def tearDown(self):
        reglages.reinitialiser()

    def _args(self, *options):
        parseur = cli.construire_parseur()
        return parseur.parse_args(["ebook", "un sujet"] + list(options))

    def _decide(self, options, cle, reglage):
        """La decision complete : ce que la ligne de commande veut, puis ce
        que le reglage dit quand elle ne veut rien.

        Elle se lit en deux temps depuis que le tableau de bord doit rendre le
        MEME verdict : « cli._tranche » ne connait que les options, et
        « apres.veut » applique le reglage. Le troisieme etat — None, « je ne
        me prononce pas » — est ce qui permet aux deux de coexister ; l'ecraser
        par False rendrait le reglage inapplicable.
        """
        return apres.veut(cli._tranche(self._args(*options), cle), reglage)

    def test_sans_reglage_ni_option_on_ne_fait_rien(self):
        self.assertFalse(self._decide((), "marketing", "marketing_auto"))

    def test_le_reglage_seul_suffit(self):
        reglages.ecrire({"marketing_auto": True})
        self.assertTrue(self._decide((), "marketing", "marketing_auto"))

    def test_l_option_negative_l_emporte_sur_le_reglage(self):
        reglages.ecrire({"marketing_auto": True})
        self.assertFalse(self._decide(("--sans-marketing",), "marketing",
                                      "marketing_auto"))

    def test_l_option_positive_suffit_sans_reglage(self):
        self.assertTrue(self._decide(("--marketing",), "marketing",
                                     "marketing_auto"))

    def test_l_archive_suit_la_meme_regle(self):
        reglages.ecrire({"archive_auto": True})
        self.assertTrue(self._decide((), "zip", "archive_auto"))
        self.assertFalse(self._decide(("--sans-zip",), "zip", "archive_auto"))


class LeTableauDeBordLesMontreTous(unittest.TestCase):

    def test_tous_sauf_les_secrets(self):
        """Le mot de passe du tableau de bord ne se change pas depuis la page
        qu'il garde : on pourrait s'y enfermer, ou en sortir."""
        from usine.web import serveur

        etat = serveur._etat()
        exposes = set(etat["reglages"])
        self.assertEqual(exposes, set(reglages.DEFAUTS) - reglages.HORS_WEB)
        self.assertIn("jeton_web", reglages.HORS_WEB)
        self.assertNotIn("jeton_web", exposes)

    def test_la_page_recoit_de_quoi_les_ranger(self):
        """Sans la structure, la page retomberait sur une liste a plat — ce
        qu'on vient justement de corriger dans le menu Termux."""
        from usine.web import serveur

        groupes = serveur._etat()["groupes_reglages"]
        self.assertEqual([g["cle"] for g in groupes],
                         [g["cle"] for g in reglages.GROUPES])
        for groupe in groupes:
            for reglage in groupe["reglages"]:
                with self.subTest(reglage=reglage["nom"]):
                    self.assertIn(reglage["genre"],
                                  ("booleen", "entier", "texte"))
                    self.assertTrue(reglage["description"])

    def test_une_valeur_refusee_revient_corrigee(self):
        """La page redessine avec ce que le SERVEUR a retenu.

        « qualite: rapidos » ne veut rien dire et vaut « standard » : afficher
        ce qu'on a tape ferait croire a un reglage qui n'existe pas.
        """
        valeurs = reglages.ecrire({"qualite": "rapidos"})
        self.assertEqual(valeurs["qualite"], "standard")


if __name__ == "__main__":
    unittest.main()
