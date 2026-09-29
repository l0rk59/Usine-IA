"""Le telephone comme machine : notifications, batterie, verrou de veille.

Aucun de ces tests n'a de telephone sous la main, et c'est le sujet : le pont
`termux-api` doit etre invisible quand il est absent, et exact quand il est
la. Les deux moities sont testees — l'absence en laissant `shutil.which`
repondre la verite (aucune machine d'integration continue n'a `termux-*`), la
presence en simulant les binaires.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import telephone  # noqa: E402


def setUpModule():
    atelier.isoler("telephone")


class FauxBinaires:
    """Simule les commandes termux-*, et retient ce qui leur a ete demande.

    On remplace `subprocess.run` plutot que `telephone._executer` : c'est la
    construction de la ligne de commande qui merite d'etre gardee — c'est la
    qu'un chemin mal echappe casse silencieusement.
    """

    def __init__(self, sorties: Optional[Dict[str, Any]] = None,
                 presents: Optional[List[str]] = None):
        self.sorties = sorties or {}
        self.presents = presents
        self.appels: List[List[str]] = []

    def which(self, nom: str) -> Optional[str]:
        if self.presents is not None and nom not in self.presents:
            return None
        return "/data/data/com.termux/files/usr/bin/" + nom

    def run(self, commande, **kwargs):  # noqa: ANN001
        self.appels.append(list(commande))
        nom = Path(commande[0]).name
        valeur = self.sorties.get(nom, "")
        if isinstance(valeur, Exception):
            raise valeur
        if isinstance(valeur, int):
            return subprocess.CompletedProcess(commande, valeur, "", "")
        return subprocess.CompletedProcess(commande, 0, valeur, "")

    def commande(self, nom: str) -> List[str]:
        for appel in self.appels:
            if Path(appel[0]).name == nom:
                return appel
        return []


def brancher(faux: FauxBinaires):
    """Installe le faux telephone pour la duree d'un bloc « with »."""
    return mock.patch.multiple(telephone, shutil=mock.Mock(which=faux.which),
                               subprocess=mock.Mock(run=faux.run,
                                                    SubprocessError=subprocess.SubprocessError))


# --------------------------------------------------------------------------
# Sans termux-api : tout doit se taire
# --------------------------------------------------------------------------


class TestAbsenceTotale(unittest.TestCase):
    """La machine qui fait tourner ces tests n'a pas termux-api. C'est le cas
    normal du projet — un PC, une machine d'integration continue — et rien ne
    doit lever, ni bloquer, ni ecrire."""

    def test_api_absente(self):
        self.assertFalse(telephone.api_disponible())

    def test_batterie_inconnue_vaut_none_pas_zero(self):
        # None veut dire « je ne sais pas ». Zero voudrait dire « a plat » et
        # arreterait l'usine sur une machine qui n'a meme pas de batterie.
        self.assertIsNone(telephone.batterie())

    def test_aucun_arret_sans_mesure(self):
        self.assertEqual(telephone.batterie_trop_faible(50), "")

    def test_notification_silencieuse(self):
        self.assertFalse(telephone.notifier("titre", "contenu"))

    def test_verrou_sans_effet(self):
        self.assertFalse(telephone.verrou_veille(True))
        with telephone.veille_maintenue() as pris:
            self.assertFalse(pris)

    def test_etat_complet_et_serialisable(self):
        etat = telephone.etat()
        self.assertEqual(set(etat), {"termux", "api", "batterie"})
        json.dumps(etat)  # le tableau de bord le renvoie tel quel


# --------------------------------------------------------------------------
# Batterie
# --------------------------------------------------------------------------


class TestBatterie(unittest.TestCase):
    def lire(self, charge: Dict[str, Any]):
        faux = FauxBinaires({"termux-battery-status": json.dumps(charge)})
        with brancher(faux):
            return telephone.batterie()

    def test_lecture_simple(self):
        etat = self.lire({"percentage": 64, "status": "DISCHARGING",
                          "plugged": "UNPLUGGED", "health": "GOOD"})
        self.assertEqual(etat["niveau"], 64)
        self.assertFalse(etat["en_charge"])
        self.assertEqual(etat["sante"], "GOOD")

    def test_en_charge_par_le_statut(self):
        self.assertTrue(self.lire({"percentage": 30, "status": "CHARGING",
                                   "plugged": "UNPLUGGED"})["en_charge"])

    def test_batterie_pleine_compte_comme_en_charge(self):
        # Un telephone branche a 100 % annonce FULL, jamais CHARGING : sans
        # ce cas, l'usine s'arreterait sur secteur, prise en main.
        self.assertTrue(self.lire({"percentage": 100, "status": "FULL",
                                   "plugged": "PLUGGED_AC"})["en_charge"])

    def test_en_charge_par_la_prise_seule(self):
        self.assertTrue(self.lire({"percentage": 12, "status": "NOT_CHARGING",
                                   "plugged": "PLUGGED_USB"})["en_charge"])

    def test_sortie_illisible(self):
        for sortie in ("", "pas du json", "[]", "null",
                       '{"status": "CHARGING"}', '{"percentage": "beaucoup"}'):
            faux = FauxBinaires({"termux-battery-status": sortie})
            with brancher(faux):
                self.assertIsNone(telephone.batterie(), sortie)

    def test_niveau_aberrant_ramene_dans_les_bornes(self):
        self.assertEqual(self.lire({"percentage": 140})["niveau"], 100)
        self.assertEqual(self.lire({"percentage": -3})["niveau"], 0)

    def test_commande_qui_echoue(self):
        faux = FauxBinaires({"termux-battery-status": 1})
        with brancher(faux):
            self.assertIsNone(telephone.batterie())

    def test_commande_qui_ne_rend_jamais_la_main(self):
        # termux-api installe SANS l'application Termux:API : la commande
        # attend indefiniment. Sans le delai, l'usine se figerait avant son
        # premier produit — une panne qui ne dit rien.
        faux = FauxBinaires({"termux-battery-status":
                             subprocess.TimeoutExpired("termux-battery-status", 8)})
        with brancher(faux):
            self.assertIsNone(telephone.batterie())


class TestPlancherBatterie(unittest.TestCase):
    def motif(self, charge: Dict[str, Any], plancher: int = 20) -> str:
        faux = FauxBinaires({"termux-battery-status": json.dumps(charge)})
        with brancher(faux):
            return telephone.batterie_trop_faible(plancher)

    def test_sous_le_plancher(self):
        motif = self.motif({"percentage": 8, "status": "DISCHARGING"})
        self.assertIn("8 %", motif)
        self.assertIn("20 %", motif)

    def test_pile_sur_le_plancher_arrete(self):
        # « minimum 20 » doit inclure 20 : un produit de plus descendrait
        # forcement dessous.
        self.assertNotEqual(self.motif({"percentage": 20,
                                        "status": "DISCHARGING"}), "")

    def test_au_dessus_continue(self):
        self.assertEqual(self.motif({"percentage": 21,
                                     "status": "DISCHARGING"}), "")

    def test_en_charge_continue_meme_a_plat(self):
        self.assertEqual(self.motif({"percentage": 3, "status": "CHARGING"}), "")

    def test_plancher_zero_coupe_le_garde_fou(self):
        self.assertEqual(self.motif({"percentage": 1, "status": "DISCHARGING"},
                                    plancher=0), "")

    def test_plancher_zero_ne_lit_meme_pas_la_batterie(self):
        faux = FauxBinaires({"termux-battery-status": '{"percentage": 1}'})
        with brancher(faux):
            telephone.batterie_trop_faible(0)
        self.assertEqual(faux.appels, [])


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


class TestNotifications(unittest.TestCase):
    def test_ligne_de_commande(self):
        faux = FauxBinaires()
        with brancher(faux):
            self.assertTrue(telephone.notifier("Produit pret", "un titre"))
        commande = faux.commande("termux-notification")
        self.assertIn("--title", commande)
        self.assertEqual(commande[commande.index("--title") + 1], "Produit pret")
        self.assertEqual(commande[commande.index("--content") + 1], "un titre")

    def test_meme_identifiant_pour_remplacer(self):
        # Dix produits doivent laisser UNE ligne dans le volet, pas dix.
        faux = FauxBinaires()
        with brancher(faux):
            telephone.notifier("un")
            telephone.notifier("deux")
        identifiants = {a[a.index("--id") + 1] for a in faux.appels}
        self.assertEqual(len(identifiants), 1)

    def test_urgence(self):
        faux = FauxBinaires()
        with brancher(faux):
            telephone.notifier("batterie", urgente=True)
        commande = faux.commande("termux-notification")
        self.assertEqual(commande[commande.index("--priority") + 1], "high")

    def test_chemin_echappe_dans_l_action(self):
        # termux-notification passe l'action a un shell. Un titre de produit
        # contient des espaces et des apostrophes ; non echappe, il casse la
        # commande — ou pire, en execute une autre.
        chemin = Path("/tmp/l'ebook de julie/livre; rm -rf .pdf")
        faux = FauxBinaires()
        with brancher(faux):
            telephone.notifier("pret", ouvrir=chemin)
        commande = faux.commande("termux-notification")
        action = commande[commande.index("--action") + 1]
        # Le chemin entier doit tenir dans UN seul argument shell : ni le
        # point-virgule ni les espaces ne sortent des guillemets.
        self.assertEqual(shlex.split(action), ["termux-open", str(chemin)])

    def test_titre_vide_refuse(self):
        faux = FauxBinaires()
        with brancher(faux):
            self.assertFalse(telephone.notifier(""))
        self.assertEqual(faux.appels, [])


# --------------------------------------------------------------------------
# Verrou de veille
# --------------------------------------------------------------------------


class TestVerrouVeille(unittest.TestCase):
    def test_pris_puis_relache(self):
        faux = FauxBinaires()
        with brancher(faux):
            with telephone.veille_maintenue() as pris:
                self.assertTrue(pris)
                self.assertTrue(faux.commande("termux-wake-lock"))
                self.assertFalse(faux.commande("termux-wake-unlock"))
        self.assertTrue(faux.commande("termux-wake-unlock"))

    def test_relache_meme_en_cas_d_erreur(self):
        faux = FauxBinaires()
        with brancher(faux):
            with self.assertRaises(ValueError):
                with telephone.veille_maintenue():
                    raise ValueError("fabrication interrompue")
        self.assertTrue(faux.commande("termux-wake-unlock"))

    def test_ne_relache_pas_un_verrou_qu_on_n_a_pas_pris(self):
        # Relacher la veille posee par QUELQU'UN D'AUTRE serait pire que de
        # ne rien faire : sa fabrication s'endormirait.
        faux = FauxBinaires(presents=[])
        with brancher(faux):
            with telephone.veille_maintenue() as pris:
                self.assertFalse(pris)
        self.assertEqual(faux.appels, [])

    def test_desactive_ne_prend_rien(self):
        faux = FauxBinaires()
        with brancher(faux):
            with telephone.veille_maintenue(actif=False) as pris:
                self.assertFalse(pris)
        self.assertEqual(faux.appels, [])


if __name__ == "__main__":
    unittest.main()
