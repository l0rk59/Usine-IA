"""Le menu doit lancer la commande qu'il annonce.

Un sous-menu est une table de correspondance entre un numero tape au clavier
et une branche de code. Rien ne la verifie a l'execution : inserer une entree
au milieu decale toutes les suivantes, et le menu se met a lancer
tranquillement la mauvaise commande. C'est exactement le defaut trouve dans
« _rythme_ab », ou un decalage d'indice faisait annoncer « variante B » pour
ce que le tableau juste au-dessus appelait C.

Ces tests pilotent donc le menu par son entree standard, comme un doigt sur
un ecran de telephone, et regardent ce qui en sort.
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
from usine import menu  # noqa: E402
from usine.core import experience  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("menu")


def _un_test(titre: str, contenus: List[str]) -> int:
    """Un test A/B avec ses variantes, sans passer par l'IA."""
    identifiant = experience.creer(titre, "titre")
    for contenu in contenus:
        experience.ajouter_variante(identifiant, contenu)
    return identifiant


def piloter(fonction, frappes: List[str]):
    """Deroule un sous-menu avec des frappes ecrites d'avance.

    Renvoie la liste des commandes que le menu a voulu lancer. La derniere
    frappe doit ramener au menu precedent, sinon la boucle ne rend pas la
    main — et un test qui ne rend pas la main est un test qui pend.
    """
    lancees: List[List[str]] = []

    def executer(arguments):
        lancees.append(list(arguments))
        return 0

    entrees = iter(frappes)

    def faux_input(invite=""):
        try:
            return next(entrees)
        except StopIteration:
            raise AssertionError(
                "le menu demande plus que les {} frappes prevues "
                "(invite : {!r})".format(len(frappes), invite))

    with redirect_stdout(io.StringIO()):
        with mock.patch("builtins.input", faux_input):
            fonction(executer)
    return lancees


class TestSousMenuAB(unittest.TestCase):
    """Chaque entree du sous-menu A/B, verifiee par ce qu'elle lance."""

    def setUp(self):
        self.test_id = _un_test("La prospection pour freelances",
                                ["Trouver des clients sans se vendre",
                                 "Quinze minutes par jour suffisent"])

    def test_rythme_lance_bien_ab_rythme(self):
        lancees = piloter(menu.menu_ab,
                          ["5", str(self.test_id), "", "0"])
        self.assertEqual(lancees, [["ab", "rythme", str(self.test_id)]])

    def test_verdict_lance_bien_ab_verdict(self):
        lancees = piloter(menu.menu_ab,
                          ["6", str(self.test_id), "", "0"])
        self.assertEqual(lancees, [["ab", "verdict", str(self.test_id)]])

    def test_chaque_entree_atteint_une_branche(self):
        """Aucun numero affiche ne doit tomber dans le vide.

        Une entree ajoutee a la liste sans branche correspondante ne provoque
        rien du tout : le menu se reaffiche, et l'utilisateur croit que
        l'usine a fait quelque chose.
        """
        for numero in (3, 4, 5, 6):
            with self.subTest(entree=numero):
                # « zzz » n'est un numero de test pour personne : chaque
                # branche doit le refuser et revenir, sans rien lancer.
                lancees = piloter(menu.menu_ab, [str(numero), "zzz", "0"])
                self.assertEqual(
                    lancees, [],
                    "l'entree {} a lance {}".format(numero, lancees))
        for numero in (1, 2):
            with self.subTest(entree=numero):
                # Les deux premieres passent par « ab creer ». Refuser de
                # partir d'un produit, puis donner un titre et un nombre.
                lancees = piloter(menu.menu_ab,
                                  [str(numero), "Un titre", "3", "", "0"])
                self.assertEqual(len(lancees), 1)
                self.assertEqual(lancees[0][:2], ["ab", "creer"])
                attendu = "titre" if numero == 1 else "couverture"
                self.assertIn(attendu, lancees[0])


class TestDatationDesVariantes(unittest.TestCase):
    """« Dater les variantes » ecrit reellement la periode en base."""

    def setUp(self):
        self.test_id = _un_test("Le systeme du freelance",
                                ["Facturer sans se justifier",
                                 "La semaine de quatre jours"])
        self.lot = experience.variantes(self.test_id)

    def test_les_dates_saisies_arrivent_en_base(self):
        frappes = [
            "4", str(self.test_id),
            "2026-01-01", "2026-02-15",   # variante A
            "2026-02-16", "",             # variante B : toujours en ligne
            "",                           # Appuyez sur Entree
            "0",
        ]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertEqual(apres[0]["debut"], "2026-01-01")
        self.assertEqual(apres[0]["fin"], "2026-02-15")
        self.assertEqual(apres[1]["debut"], "2026-02-16")
        self.assertIsNone(apres[1]["fin"])

    def test_une_variante_laissee_vide_reste_sans_periode(self):
        frappes = ["4", str(self.test_id), "", "", "", "0"]
        piloter(menu.menu_ab, frappes)
        for variante in experience.variantes(self.test_id):
            self.assertIsNone(variante["debut"])

    def test_une_date_illisible_est_refusee_sans_casser_le_menu(self):
        frappes = [
            "4", str(self.test_id),
            "le 3 janvier", "",           # variante A : format refuse
            "2026-03-01", "",             # variante B : acceptee
            "", "0",
        ]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertIsNone(apres[0]["debut"])
        self.assertEqual(apres[1]["debut"], "2026-03-01")

    def test_une_fin_avant_le_debut_est_refusee(self):
        frappes = [
            "4", str(self.test_id),
            "2026-05-01", "2026-04-01",   # variante A : fin avant debut
            "",                           # variante B : passee
            "", "0",
        ]
        piloter(menu.menu_ab, frappes)
        self.assertIsNone(experience.variantes(self.test_id)[0]["debut"])

    def test_la_periode_deja_posee_est_proposee_par_defaut(self):
        """Repasser sur une variante datee sans rien taper ne l'efface pas."""
        experience.fixer_periode(self.lot[0]["id"], "2026-01-10", "2026-01-20")
        frappes = ["4", str(self.test_id), "", "", "", "", "0"]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertEqual(apres[0]["debut"], "2026-01-10")
        self.assertEqual(apres[0]["fin"], "2026-01-20")


if __name__ == "__main__":
    unittest.main()
