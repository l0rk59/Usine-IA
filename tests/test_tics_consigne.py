"""Le detecteur de tics et la consigne des agents disent la meme chose.

Mesure du 23/09/2026 : le controle deterministe connait vingt-neuf tics
(« plongeons dans », « force est de constater », « joue un role cle »...). La
consigne envoyee aux agents en citait DEUX. Les vingt-sept autres n'etaient
appris qu'apres coup, au prix d'une passe de correction par section — un
appel de modele entier pour retirer une tournure qu'on aurait pu interdire en
une ligne. Les deux listes etaient tenues a la main, separement.

La liste va maintenant aux trois agents dont le texte passe par le
detecteur : le redacteur et le romancier qui l'ecrivent, le reviseur qui le
corrige. Pas aux autres : quatre cents jetons de plus par appel ne se
rembourseraient pas sur un agent qui rend un titre ou un plan.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("tics-consigne")


from usine.agents import equipe  # noqa: E402
from usine.core import controle  # noqa: E402


class _Contexte:
    langue = "francais"
    description_ton = "sobre"
    audience = "des lecteurs"


class LaConsigneCiteCeQueLeControleRetire(unittest.TestCase):

    def test_chaque_tic_detecte_est_annonce_aux_agents_qui_ecrivent(self):
        systeme = equipe.ROMANCIER.systeme(_Contexte())
        manquants = [t for t in controle.tics_lisibles() if t not in systeme]
        self.assertEqual(manquants, [], (
            "le controle retire ces tournures sans que l'agent en ait ete "
            "prevenu : {}".format(manquants[:5])))

    def test_les_trois_agents_suivis_la_recoivent(self):
        for agent in (equipe.REDACTEUR, equipe.ROMANCIER, equipe.REVISEUR):
            with self.subTest(agent=agent.nom):
                self.assertIn("plongeons dans", agent.systeme(_Contexte()))

    def test_un_agent_qui_n_ecrit_pas_de_prose_ne_paie_pas_la_liste(self):
        """Le cout est reel — pres de quatre cents jetons par appel. Un
        architecte qui rend un plan JSON n'ecrit pas « plongeons dans »."""
        for agent in (equipe.ARCHITECTE, equipe.PROSPECTEUR,
                      equipe.BIBLIOTHECAIRE):
            with self.subTest(agent=agent.nom):
                self.assertNotIn("plongeons dans", agent.systeme(_Contexte()))


class LaListeResteLisibleQuandOnAjouteUnTic(unittest.TestCase):
    """Le jour ou quelqu'un ajoute un motif au detecteur, il part aussi dans
    la consigne. Il doit y arriver en francais, pas en syntaxe de motif."""

    def test_aucune_syntaxe_de_motif_ne_passe(self):
        for rendu, motif in zip(controle.tics_lisibles(), controle.TICS):
            with self.subTest(motif=motif):
                self.assertTrue(rendu, "motif rendu vide")
                self.assertIsNone(re.search(r"[()\[\]{}|\\?*+^$]", rendu), (
                    "« {} » est parti tel quel dans la consigne".format(rendu)))

    def test_le_groupe_facultatif_est_garde(self):
        """« il (ne )?faut pas oublier » : un modele a qui l'on interdit « il
        faut pas oublier » a appris une faute, pas une tournure."""
        self.assertIn("il ne faut pas oublier que", controle.tics_lisibles())

    def test_autant_de_rendus_que_de_motifs(self):
        self.assertEqual(len(controle.tics_lisibles()), len(controle.TICS))


if __name__ == "__main__":
    unittest.main()
