"""Le demarrage a froid proposait les memes domaines pour toujours.

Mesure du 16/09/2026, avec un modele qui rend des domaines DIFFERENTS a
chaque appel :

    tour 1 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
    tour 2 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
    tour 3 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
    appels reellement passes au modele : 1 sur 3 tours

Ce n'etait donc pas le modele qui se repetait : c'etait le cache. La cle du
cache est un hachage de l'invite, et l'invite du demarrage a froid ne variait
jamais — ni sujet, ni historique, rien que le nombre demande.

« idees.explorer » avait recu cette correction en septembre : on lui injecte
ce que l'atelier contient deja, ce qui fait d'une pierre deux coups — le
modele cesse de reproposer ce qui existe, et l'invite change des que l'atelier
change. Le demarrage a froid, qui est pourtant le premier ecran de tout le
monde, ne l'avait jamais eue.

Aucun test ici ne sort sur le reseau, et aucun ne mesure de marche : le
sondage est remplace.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("niches-variees")


from usine import production  # noqa: E402
from usine.core import file, llm, marche, store  # noqa: E402


def _modele_qui_varie(compteur):
    """Rend des domaines differents a chaque appel. Si l'usine se repete,
    c'est elle — pas lui."""

    def modele(messages, role):
        invite = messages[-1]["content"]
        if '"pourquoi_maintenant"' in invite:
            compteur["appels"] += 1
            compteur["invites"].append(invite)
            lot = compteur["appels"]
            return json.dumps({"domaines": [
                {"domaine": "domaine {}-{}".format(lot, i),
                 "acheteur": "quelqu'un", "pourquoi_maintenant": "maintenant"}
                for i in range(1, 4)]})
        return "{}"

    return modele


def _sans_sonder():
    """Le sondage de marche ne doit pas peser ici : on mesure la VARIETE."""
    vrai = marche.sonder
    # La MEME forme que le vrai rapport, « date » comprise : un bouchon
    # incomplet faisait planter « idees.explorer » sur une KeyError, donc rien
    # n'entrait en file, donc le test croyait mesurer un cache fige alors
    # qu'il mesurait son propre harnais.
    marche.sonder = lambda sujet, **_k: {
        "sujet": sujet, "date": "2026-09-16", "sources": {},
        "sources_disponibles": [], "sources_indisponibles": [],
        "lecture": {"demande": "", "fiabilite": "", "verdict": "",
                    "signaux": []}}
    return vrai


def _repartir_a_neuf():
    """Un atelier vide et un cache vide, pour CHAQUE test.

    Les deux se partagent autrement d'un test a l'autre, et c'est
    precisement ce que ce module mesure : une invite deja vue rend sa reponse
    depuis le cache sans consulter le modele. Sans cette remise a zero, le
    second test de la classe n'exercait rien — le piege que le depot signale,
    retombe dans le test qui le documente.
    """
    store.cache_vider()
    file.vider(tout=True)


class LeDemarrageAFroidNeSeRepetePlus(unittest.TestCase):

    def setUp(self):
        _repartir_a_neuf()
        self.compteur = {"appels": 0, "invites": []}
        self.vrai_sonder = _sans_sonder()
        llm.definir_simulateur(_modele_qui_varie(self.compteur))

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder

    def test_trois_tours_font_trois_appels_quand_l_atelier_bouge(self):
        """Le defaut mesure : trois tours, un seul appel, trois fois la meme
        liste. Le cache rendait sa reponse sans meme consulter le modele."""
        vus = []
        for _ in range(3):
            rapport = production.domaines_de_depart(
                journal=lambda m: None, nombre=3)
            vus.append([p["domaine"] for p in rapport["retenus"]])
            file.ajouter(rapport["retenus"][0]["domaine"], "ebook")
        self.assertEqual(self.compteur["appels"], 3, (
            "{} appel(s) pour trois tours : le cache repond a la place du "
            "modele".format(self.compteur["appels"])))
        self.assertNotEqual(vus[0], vus[1])
        self.assertNotEqual(vus[1], vus[2])

    def test_l_invite_porte_ce_que_l_atelier_connait_deja(self):
        """C'est le MECANISME : sans ce texte dans l'invite, la cle de cache
        est identique et rien d'autre ne peut la faire varier."""
        production.domaines_de_depart(journal=lambda m: None, nombre=3)
        file.ajouter("la reliure japonaise", "ebook")
        production.domaines_de_depart(journal=lambda m: None, nombre=3)
        self.assertNotIn("reliure japonaise", self.compteur["invites"][0])
        self.assertIn("reliure japonaise", self.compteur["invites"][1], (
            "l'invite ne dit pas au modele ce qui existe deja : elle ne peut "
            "donc pas changer, et le cache la fige"))

    def test_un_atelier_vide_n_ajoute_pas_de_liste_vide(self):
        """Le garde-fou qui crie a tort : sur une installation neuve il n'y a
        rien a lister, et l'invite ne doit pas porter une rubrique vide."""
        production.domaines_de_depart(journal=lambda m: None, nombre=3)
        self.assertNotIn("L'atelier connait deja", self.compteur["invites"][0])


class DeuxAppuisSurUneInstallationNeuve(unittest.TestCase):
    """Le cas reel : on appuie deux fois sur « Trouver des niches » sans avoir
    rien produit entre les deux."""

    def setUp(self):
        _repartir_a_neuf()
        self.compteur = {"appels": 0, "invites": []}
        self.vrai_sonder = _sans_sonder()

        def modele(messages, role):
            invite = messages[-1]["content"]
            if '"pourquoi_maintenant"' in invite:
                self.compteur["appels"] += 1
                lot = self.compteur["appels"]
                return json.dumps({"domaines": [
                    {"domaine": "domaine {}-{}".format(lot, i),
                     "acheteur": "x", "pourquoi_maintenant": "y"}
                    for i in range(1, 4)]})
            return json.dumps({"idees": [
                {"titre": "idee {}".format(self.compteur["appels"]),
                 "type": "ebook", "pourquoi": "x"}]})

        llm.definir_simulateur(modele)

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder

    def test_le_second_appui_part_d_une_autre_graine(self):
        graines = []
        for _ in range(2):
            rapport = production.prospecter(
                nombre=3, journal=lambda m: None, avec_veille=False)
            graines.append(rapport.get("graine"))
        self.assertNotEqual(graines[0], graines[1], (
            "deux appuis de suite repartent de la meme graine « {} »".format(
                graines[0])))


if __name__ == "__main__":
    unittest.main()
