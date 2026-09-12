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
import itertools
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
from usine.core import experience, reglages, store, ventes  # noqa: E402
from usine.core import file as file_prod  # noqa: E402


def setUpModule():
    """Un atelier a nous, rempli une fois pour toutes.

    Les sous-menus changent de branche selon ce que l'atelier contient :
    « Partir d'un produit existant ? » n'est posee que s'il y a des
    produits. Remplir depuis un test et pas depuis un autre ferait
    dependre chaque suite de l'ordre d'execution — ce qu'on vient
    justement de supprimer entre les modules.
    """
    atelier.isoler("menu")
    _atelier_rempli()


def _un_test(titre: str, contenus: List[str]) -> int:
    """Un test A/B avec ses variantes, sans passer par l'IA."""
    identifiant = experience.creer(titre, "titre")
    for contenu in contenus:
        experience.ajouter_variante(identifiant, contenu)
    return identifiant


def deroule(fonction, frappes: List[str], ensuite: str = "0",
            limite: int = 80):
    """Comme `piloter`, mais tolerant : les frappes epuisees, on repond
    toujours la meme chose.

    « 0 » ressort de n'importe quel sous-menu en boucle. Pour un ecran qui
    se deroule une fois — « Fabriquer un produit » — c'est la chaine vide
    qu'il faut : elle accepte chaque valeur par defaut jusqu'au bout.

    Sert a promener le menu partout sans avoir a compter chaque question.
    Le garde-fou est la limite : un menu qui ne rend pas la main est un
    menu qui bloque un telephone.
    """
    lancees: List[List[str]] = []
    restantes = list(frappes)
    posees = itertools.count(1)

    def faux_input(invite=""):
        if next(posees) > limite:
            raise AssertionError("le menu ne rend pas la main")
        return restantes.pop(0) if restantes else ensuite

    with redirect_stdout(io.StringIO()):
        with mock.patch("builtins.input", faux_input):
            if fonction in _SANS_EXECUTER:
                fonction()
            else:
                fonction(lambda args: lancees.append(list(args)) or 0)
    return lancees


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
                lancees = piloter(
                    menu.menu_ab,
                    [str(numero), "n", "Un titre", "3", "", "0"])
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




_SANS_EXECUTER = (menu.menu_reglages, menu.menu_cles)

_SOUS_MENUS = (
    ("menu_fabriquer", menu.menu_fabriquer),
    ("menu_usine", menu.menu_usine),
    ("menu_ab", menu.menu_ab),
    ("menu_produits", menu.menu_produits),
    ("menu_ventes", menu.menu_ventes),
    ("menu_reglages", menu.menu_reglages),
    ("menu_cles", menu.menu_cles),
)


def _atelier_rempli():
    """De quoi faire changer les branches qui dependent des donnees."""
    store.creer_produit("menu-p1", "ebook", "Le systeme du freelance",
                        sujet="freelance", dossier="/tmp/menu-p1")
    store.creer_produit("menu-p2", "prompts", "80 prompts pour freelances",
                        sujet="prompts", dossier="/tmp/menu-p2")
    file_prod.ajouter("une niche en attente", "ebook")
    ventes.enregistrer({"date": "2026-08-01",
                        "reference": "Le systeme du freelance",
                        "unites": 2, "brut": 58.0, "net": 50.0,
                        "devise": "EUR", "remboursement": 0,
                        "plateforme": "gumroad", "empreinte": "menu-v1"},
                       produit_id="menu-p1")


class TestMenuPrincipal(unittest.TestCase):
    """Chaque entree du menu principal lance la commande qu'elle annonce.

    Le menu principal est la plus longue table numero -> branche du projet.
    Y inserer une entree decale toutes les suivantes en silence : c'est
    exactement ce qui vient d'arriver en ajoutant « Mesurer un marche » et
    « Ce que l'usine a appris » au milieu.
    """

    # Les entrees qui ouvrent un sous-menu ne lancent rien : elles sont
    # absentes de cette table, et le test verifie alors qu'aucune commande
    # ne part.
    ATTENDU = {
        6: "doublons", 7: "veille", 8: "recon", 9: "marche", 10: "bilan",
        11: "sauvegarde", 14: "prompts-systeme", 15: "cache",
        16: "web", 17: "docteur",
    }
    # 12 = Cles, 13 = Reglages : les seuls sous-menus qui ne lancent rien seuls.
    SOUS_MENUS = (1, 2, 4, 12, 13)

    def _lancer(self, numero):
        frappes = [str(numero), "un sujet quelconque", "1", "", "0", "0", "0"]
        return deroule(menu.menu_principal, frappes)

    def test_chaque_entree_lance_ce_qu_elle_annonce(self):
        for numero, commande in sorted(self.ATTENDU.items()):
            with self.subTest(entree=numero, commande=commande):
                lancees = self._lancer(numero)
                self.assertTrue(lancees, "l'entree {} ne lance rien".format(numero))
                self.assertEqual(lancees[0][0], commande)

    def test_les_entrees_de_sous_menu_ne_lancent_rien_toutes_seules(self):
        for numero in self.SOUS_MENUS:
            with self.subTest(entree=numero):
                self.assertEqual(self._lancer(numero), [])

    def test_aucune_entree_affichee_ne_tombe_dans_le_vide(self):
        """Une entree sans branche ne provoque rien : l'utilisateur croit
        que l'usine a fait quelque chose."""
        couvertes = set(self.ATTENDU) | set(self.SOUS_MENUS)
        couvertes.add(3)                      # Tests A/B, couvert plus haut
        couvertes.add(5)                      # Ventes, sous-menu avec commande
        affichees = set(range(1, _entrees_du_menu() + 1))
        self.assertEqual(affichees - couvertes, set(),
                         "entrees sans branche verifiee")


def _entrees_du_menu():
    """Combien d'entrees le menu principal affiche, lues dans sa source."""
    source = (Path(menu.__file__)).read_text(encoding="utf-8")
    bloc = source.split('choisir("Menu principal", [')[1].split("], defaut=")[0]
    return bloc.count('("')


class TestAucunSousMenuNeLeve(unittest.TestCase):
    """Une trace Python en plein ecran de telephone n'est pas une reponse.

    Le menu n'avait aucun test : c'est du code de presentation, celui qu'on
    juge trop simple pour se tromper. Il l'etait assez pour rendre
    « Fabriquer un produit » inaccessible des qu'un ton sur mesure etait
    enregistre.
    """

    def _suites(self):
        yield []
        yield ["zzz"]
        yield ["99"]
        yield ["-1"]
        for numero in range(1, 13):
            yield [str(numero)]
            yield [str(numero), "zzz", "zzz"]
            yield [str(numero), "1", "1", "1"]

    def test_atelier_rempli(self):
        for nom, fonction in _SOUS_MENUS:
            for frappes in self._suites():
                with self.subTest(sous_menu=nom, frappes=frappes):
                    deroule(fonction, frappes)


class TestReglagesSurMesure(unittest.TestCase):
    """Un reglage hors liste ne doit rien casser, et ne pas etre perdu."""

    def tearDown(self):
        reglages.reinitialiser()

    def _fabriquer(self):
        lancees = deroule(menu.menu_fabriquer,
                          ["1", "un sujet", "des freelances", "o"],
                          ensuite="")
        self.assertTrue(lancees, "aucune commande lancee")
        return lancees[0]

    def test_un_ton_sur_mesure_n_empeche_pas_de_fabriquer(self):
        """Le defaut : « tons.index(valeurs["ton"]) » levait ValueError.

        Le menu propose la saisie libre du ton — et refusait ensuite de
        s'ouvrir tant que ce ton etait enregistre comme defaut.
        """
        libre = "comme un vieux menuisier a son apprenti"
        reglages.ecrire({"ton": libre})
        commande = self._fabriquer()
        self.assertIn("-t", commande)
        self.assertEqual(commande[commande.index("-t") + 1], libre)

    def test_un_volume_sur_mesure_devient_un_nombre_de_sections(self):
        reglages.ecrire({"taille": "15"})
        commande = self._fabriquer()
        self.assertIn("--chapitres", commande)
        self.assertEqual(commande[commande.index("--chapitres") + 1], "15")
        self.assertNotIn("-T", commande)

    def test_une_qualite_inventee_n_est_pas_enregistree(self):
        """« rapidos » vaut « standard » partout : autant le dire tout de suite."""
        reglages.ecrire({"qualite": "rapidos"})
        self.assertEqual(reglages.lire("qualite"), "standard")
        commande = self._fabriquer()
        self.assertEqual(commande[commande.index("--qualite") + 1], "standard")

    def test_les_trois_qualites_connues_restent_acceptees(self):
        for qualite in ("rapide", "standard", "exigeant"):
            with self.subTest(qualite=qualite):
                reglages.ecrire({"qualite": qualite})
                self.assertEqual(reglages.lire("qualite"), qualite)


class TestReglageParListe(unittest.TestCase):
    """Le menu des reglages propose les raccourcis au lieu du clavier."""

    def tearDown(self):
        reglages.reinitialiser()

    def _rang_de(self, nom):
        return [l["nom"] for l in reglages.lignes_affichables()].index(nom) + 1

    def test_choisir_un_ton_dans_la_liste(self):
        deroule(menu.menu_reglages, [str(self._rang_de("ton")), "1"])
        self.assertEqual(reglages.lire("ton"), sorted(menu.TONS)[0])

    def test_saisir_un_ton_libre(self):
        libre = "comme un guide de haute montagne"
        entree_libre = str(len(menu.TONS) + 1)
        deroule(menu.menu_reglages,
                [str(self._rang_de("ton")), entree_libre, libre])
        self.assertEqual(reglages.lire("ton"), libre)

    def test_une_qualite_ne_peut_plus_etre_tapee(self):
        """La liste fermee ne laisse aucun moyen d'ecrire n'importe quoi."""
        deroule(menu.menu_reglages, [str(self._rang_de("qualite")), "1"])
        self.assertEqual(reglages.lire("qualite"), "rapide")


if __name__ == "__main__":
    unittest.main()
