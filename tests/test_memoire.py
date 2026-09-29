"""Ou la memoire d'une fiction lache, mesure plutot que suppose.

La chaine « nouvelle » porte un resume roulant de quatre-vingt-dix mots. La
question du roman est : jusqu'a combien de scenes tient-il ? On peut y
repondre par un raisonnement, et c'est ce que fait le module ; ces tests le
verifient sur la vraie boucle.

## Le compresseur de la mesure

Le redacteur employe ici est un modele IDEAL, et c'est volontaire. Il ne
paraphrase pas, ne se trompe pas, n'oublie rien par distraction : il garde
autant de faits que la taille du resume le permet, et jette les plus anciens
— ce que fait tout resume de taille fixe. Ce qu'on mesure est donc la limite
de CAPACITE, pas le talent d'un modele. Un vrai modele fera moins bien ; il
ne fera jamais mieux.

Si la memoire plate perd des faits meme avec ce compresseur-la, elle en perd
en vrai, et augmenter la qualite du modele n'y changera rien.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Callable, List

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.pipelines import memoire as M  # noqa: E402

MOTS_RESUME = 90


def setUpModule():
    """Ces tests n'ecrivent rien, mais la regle du depot est uniforme : un
    module qui n'isole pas son atelier herite de celui du precedent."""
    atelier.isoler("memoire")

# Une clause d'etat par fait. Sept mots — la mesure du module — plus le jeton.
CLAUSE = "l'evenement {} a eu lieu, toujours vrai"
JETON = re.compile(r"FAIT-\d+")


def redacteur_ideal(mots_resume: int = MOTS_RESUME) -> Callable[[str, str, str], str]:
    """Le meilleur resumeur possible sous contrainte de taille.

    Il retient les faits les plus RECENTS : c'est ce que fait un resume d'etat,
    qui doit dire ou en est l'histoire maintenant. Les plus anciens sortent
    quand la place manque, et c'est exactement le phenomene mesure.
    """
    plafond = M.capacite(mots_resume)

    def redacteur(etat: str, ajout: str, intitule: str = "") -> str:  # noqa: ARG001
        faits = list(dict.fromkeys(JETON.findall("{} {}".format(etat, ajout))))
        return " ".join(CLAUSE.format(fait) for fait in faits[-plafond:])

    return redacteur


def _scene(numero: int) -> str:
    """Le texte d'une scene, portant un fait qu'on saura reconnaitre."""
    return ("Camille entre. Elle apprend quelque chose de precis : "
            "FAIT-{:03d}. Elle ressort sans rien dire.".format(numero))


def executer(memoire, nb_scenes: int) -> List[str]:
    """Deroule une histoire de N scenes et renvoie les faits encore en memoire."""
    redacteur = redacteur_ideal()
    for index in range(nb_scenes):
        memoire.apres_scene(redacteur, _scene(index + 1),
                            "Scene {}".format(index + 1), index, nb_scenes)
    return JETON.findall(memoire.pour_invite())


class TestCapaciteAnnoncee(unittest.TestCase):
    def test_le_calcul_est_explicite(self):
        self.assertEqual(M.capacite(90), 12)
        self.assertEqual(M.capacite(90, mots_par_evenement=15), 6)

    def test_une_taille_absurde_ne_divise_pas_par_zero(self):
        self.assertEqual(M.capacite(90, mots_par_evenement=0), 0)
        self.assertEqual(M.capacite(3), 1)


class TestMemoirePlate(unittest.TestCase):
    """Le comportement d'origine : un etat, reecrit a chaque scene."""

    def test_une_nouvelle_tient_entierement(self):
        faits = executer(M.MemoirePlate(), 8)
        self.assertEqual(len(faits), 8, "une nouvelle de huit scenes tient")
        self.assertIn("FAIT-001", faits, "la premiere scene doit survivre")

    def test_elle_tient_exactement_jusqu_a_sa_capacite(self):
        plafond = M.capacite(MOTS_RESUME)
        faits = executer(M.MemoirePlate(), plafond)
        self.assertEqual(len(faits), plafond)
        self.assertIn("FAIT-001", faits)

    def test_une_scene_de_plus_et_la_premiere_disparait(self):
        """La bascule est nette, et elle ne depend pas du modele."""
        plafond = M.capacite(MOTS_RESUME)
        faits = executer(M.MemoirePlate(), plafond + 1)
        self.assertNotIn("FAIT-001", faits,
                         "le premier fait doit avoir ete chasse")
        self.assertIn("FAIT-{:03d}".format(plafond + 1), faits,
                      "le dernier fait doit y etre")

    def test_a_l_echelle_d_un_roman_elle_perd_la_moitie(self):
        """Vingt-quatre scenes : la premiere moitie du livre a disparu."""
        faits = executer(M.MemoirePlate(), 24)
        self.assertEqual(len(faits), 12)
        for numero in range(1, 13):
            self.assertNotIn("FAIT-{:03d}".format(numero), faits)

    def test_elle_ne_grandit_jamais(self):
        """C'est un tampon, pas un journal : sa taille est bornee."""
        memoire = M.MemoirePlate()
        executer(memoire, 40)
        self.assertLessEqual(len(memoire.pour_invite().split()), MOTS_RESUME + 12)


class TestMemoireHierarchique(unittest.TestCase):
    """Ce qui ne se reecrit pas ne se degrade pas."""

    def test_rien_ne_se_perd_a_l_echelle_d_un_roman(self):
        faits = executer(M.MemoireHierarchique(scenes_par_partie=6), 24)
        self.assertEqual(len(faits), 24)
        self.assertIn("FAIT-001", faits,
                      "la premiere scene doit encore etre la a la vingt-quatrieme")

    def test_elle_tient_aussi_a_quarante_scenes(self):
        faits = executer(M.MemoireHierarchique(scenes_par_partie=6), 40)
        self.assertEqual(len(faits), 40)
        self.assertIn("FAIT-001", faits)

    def test_un_resume_de_partie_close_n_est_plus_jamais_reecrit(self):
        """C'est l'unique propriete sur laquelle tout repose."""
        memoire = M.MemoireHierarchique(scenes_par_partie=4)
        redacteur = redacteur_ideal()
        for index in range(4):
            memoire.apres_scene(redacteur, _scene(index + 1), "", index, 20)
        self.assertEqual(len(memoire.closes), 1)
        fige = memoire.closes[0]

        for index in range(4, 20):
            memoire.apres_scene(redacteur, _scene(index + 1), "", index, 20)
        self.assertEqual(memoire.closes[0], fige,
                         "la premiere partie a ete modifiee apres sa fermeture")

    def test_la_partie_en_cours_repart_a_zero_a_chaque_fermeture(self):
        memoire = M.MemoireHierarchique(scenes_par_partie=3)
        redacteur = redacteur_ideal()
        for index in range(3):
            memoire.apres_scene(redacteur, _scene(index + 1), "", index, 12)
        self.assertEqual(memoire.courante, "")
        memoire.apres_scene(redacteur, _scene(4), "", 3, 12)
        self.assertIn("FAIT-004", memoire.courante)
        self.assertNotIn("FAIT-001", memoire.courante,
                         "la partie close ne doit plus peser sur la courante")

    def test_la_derniere_scene_ne_ferme_pas_de_partie(self):
        """Figer une partie que plus aucune scene ne lira coute un appel pour rien."""
        memoire = M.MemoireHierarchique(scenes_par_partie=3)
        appels = []

        def compter(etat, ajout, intitule=""):
            appels.append(intitule)
            return redacteur_ideal()(etat, ajout, intitule)

        for index in range(6):
            memoire.apres_scene(compter, _scene(index + 1),
                                "Scene {}".format(index + 1), index, 6)
        # 6 scenes, parties de 3 : la 3e ferme, la 6e est la derniere du livre.
        self.assertEqual(len(memoire.closes), 1)
        self.assertEqual(len(appels), 6 + 1, "un seul appel de fermeture")
        self.assertIn("Partie 1", appels,
                      "la fermeture doit s'annoncer comme telle au redacteur")

    def test_le_cout_reste_lineaire(self):
        """Un appel par scene, plus un par partie fermee. Pas davantage."""
        memoire = M.MemoireHierarchique(scenes_par_partie=6)
        appels = []
        redacteur = redacteur_ideal()
        for index in range(24):
            memoire.apres_scene(
                lambda etat, ajout, intitule="": (
                    appels.append(1), redacteur(etat, ajout, intitule))[1],
                _scene(index + 1), "", index, 24)
        self.assertEqual(len(appels), 24 + 3,
                         "24 scenes + 3 fermetures (la 24e ne ferme rien)")


class TestEtatCourant(unittest.TestCase):
    """Ce que le controle de continuite doit lire, et surtout pas lire.

    Le controle compare deux etats successifs pour reperer une scene qui n'a
    rien fait avancer. Si on lui donnait l'historique complet d'une memoire
    hierarchique, deux etats voisins partageraient toutes leurs parties
    closes : leur recouvrement serait quasi total, et CHAQUE scene serait
    signalee comme inutile. Le piege est d'autant plus serieux qu'il se
    declencherait seulement sur les longs textes.
    """

    def test_la_memoire_plate_rend_son_etat(self):
        memoire = M.MemoirePlate()
        executer(memoire, 4)
        self.assertEqual(memoire.etat_courant(), memoire.etat)

    def test_la_hierarchique_ne_rend_que_la_partie_en_cours(self):
        memoire = M.MemoireHierarchique(scenes_par_partie=6)
        executer(memoire, 20)
        courant = memoire.etat_courant()
        self.assertNotIn("FAIT-001", courant,
                         "une partie close ne doit pas peser sur la comparaison")
        self.assertIn("FAIT-020", courant)

    def test_deux_etats_successifs_restent_comparables(self):
        """Deux scenes qui avancent ne doivent pas se ressembler."""
        from usine.pipelines.nouvelle import _proximite

        memoire = M.MemoireHierarchique(scenes_par_partie=6)
        redacteur = redacteur_ideal()
        etats = []
        for index in range(20):
            memoire.apres_scene(redacteur, _scene(index + 1), "", index, 20)
            etats.append(memoire.etat_courant())
        # Les etats vides (juste apres une fermeture) ne se comparent pas.
        paires = [(a, b) for a, b in zip(etats, etats[1:]) if a and b]
        self.assertTrue(paires)
        for avant, apres in paires:
            self.assertLessEqual(
                _proximite(avant, apres), 0.92,
                "deux etats successifs trop proches : chaque scene serait "
                "signalee comme ne faisant rien avancer")


class TestChoixDeLaMemoire(unittest.TestCase):
    """La hierarchie ne s'active que quand la memoire plate ne suffit plus."""

    def test_une_nouvelle_garde_la_memoire_la_moins_chere(self):
        for nombre in (2, 6, 8, 12):
            self.assertIsInstance(M.choisir(nombre, MOTS_RESUME), M.MemoirePlate,
                                  "{} scenes".format(nombre))

    def test_au_dela_de_la_capacite_la_hierarchie_prend_le_relais(self):
        for nombre in (13, 18, 24, 60):
            self.assertIsInstance(M.choisir(nombre, MOTS_RESUME),
                                  M.MemoireHierarchique, "{} scenes".format(nombre))

    def test_les_parties_tiennent_dans_la_capacite(self):
        """Une partie plus longue que la capacite reproduirait le defaut."""
        choisie = M.choisir(24, MOTS_RESUME)
        self.assertLessEqual(choisie.scenes_par_partie, M.capacite(MOTS_RESUME))
        self.assertGreaterEqual(choisie.scenes_par_partie, 2)


class TestComparaison(unittest.TestCase):
    """Le tableau chiffre qui figure dans docs/FICTION.md."""

    def test_les_chiffres_publies_sont_ceux_que_le_code_produit(self):
        attendu = {6: (6, 6), 12: (12, 12), 18: (12, 18), 24: (12, 24),
                   40: (12, 40)}
        for scenes, (plate, hierarchique) in attendu.items():
            self.assertEqual(len(executer(M.MemoirePlate(), scenes)), plate,
                             "memoire plate a {} scenes".format(scenes))
            self.assertEqual(
                len(executer(M.MemoireHierarchique(scenes_par_partie=6), scenes)),
                hierarchique, "memoire hierarchique a {} scenes".format(scenes))


if __name__ == "__main__":
    unittest.main()
