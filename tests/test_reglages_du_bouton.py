"""Quatre reglages coches dans le tableau de bord ne faisaient rien.

Mesure du 15/09/2026, par le chemin REEL du bouton (« serveur._lancer »), les
quatre actives dans les reglages :

    relecture_ensemble   l'agent LECTEUR a parle 0 fois
    marketing_auto       aucun kit de vente
    archive_auto         aucune archive ZIP
    extrait_offert       aucun extrait offert

Le travail existait — « cli._apres_production » le faisait depuis toujours —
mais il vivait dans la ligne de commande, derriere des arguments argparse. Le
tableau de bord s'arretait a « catalogue.executer ».

Un reglage affiche, sauvegarde et jamais lu est un mensonge fait a
l'utilisateur. Le depot avait deja trouve ce defaut une fois, sur
« plateforme » et « devise ». Il etait revenu sur le chemin du TELEPHONE,
c'est-a-dire l'usage normal de cette usine.

Ces tests passent par le serveur et regardent le PRODUIT, pas le code : c'est
la seule facon de voir qu'un reglage a servi.
"""

from __future__ import annotations

import collections
import sys
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("reglages-bouton")


from usine.agents import base as agents_base, equipe  # noqa: E402
from usine.core import llm, reglages  # noqa: E402
from usine.pipelines import apres  # noqa: E402
from usine.web import serveur  # noqa: E402
from tests import simulateur  # noqa: E402


def _fabriquer(sujet, **actifs):
    """Fabrique par le chemin du bouton, et rend (resume, appels par agent)."""
    reglages.ecrire(actifs)
    reglages.charger(force=True)
    compte = collections.Counter()
    vrai = agents_base.Agent.travailler_json

    def pister(self, *a, **k):
        compte[self.nom] += 1
        return vrai(self, *a, **k)

    agents_base.Agent.travailler_json = pister
    llm.definir_simulateur(simulateur.simulateur)
    travail = "t-" + sujet[:12]
    # La MEME fiche que celle posee par le serveur, et retiree ensuite.
    # « TRAVAUX » est partage par tout le processus : une fiche incomplete
    # laissee derriere soi faisait tomber « _etat() » dans un autre module de
    # test, sur une cle « debut » absente. Un harnais de test qui abime l'etat
    # d'autrui fait perdre plus de temps qu'il n'en fait gagner.
    serveur.TRAVAUX[travail] = {
        "id": travail, "type": "ebook", "sujet": sujet[:300],
        "statut": "en_cours", "debut": time.time(), "journal": [],
        "resultat": None, "erreur": "",
    }
    try:
        serveur._lancer(travail, "ebook", {"sujet": sujet})
        etat = dict(serveur.TRAVAUX[travail])
    finally:
        agents_base.Agent.travailler_json = vrai
        llm.definir_simulateur(None)
        reglages.reinitialiser()
        serveur.TRAVAUX.pop(travail, None)
    assert etat["statut"] == "termine", etat.get("erreur")
    return etat["resultat"], compte


class CeQueLeBoutonApplique(unittest.TestCase):
    """Chaque test porte sur un SUJET different : deux cas qui partagent une
    invite partagent une entree de cache, et le second n'exerce rien."""

    def test_la_relecture_d_ensemble_fait_parler_le_lecteur(self):
        """L'agent qui lit le produit comme l'acheteur. Il ne s'allume que sur
        ce reglage — et ce reglage n'atteignait pas la chaine."""
        _, compte = _fabriquer("la comptabilite des artisans",
                               relecture_ensemble=True)
        self.assertGreaterEqual(compte[equipe.LECTEUR.nom], 1, (
            "le LECTEUR n'a pas parle : « relecture_ensemble » n'arrive pas "
            "jusqu'a la chaine"))

    def test_sans_le_reglage_le_lecteur_se_tait(self):
        """Le pendant du precedent : sans lui, le test ci-dessus ne mesurerait
        rien — un agent qui parle toujours passerait pour bien cable."""
        _, compte = _fabriquer("la taille des rosiers",
                               relecture_ensemble=False)
        self.assertEqual(compte[equipe.LECTEUR.nom], 0)

    def test_le_kit_de_vente_est_produit(self):
        resume, _ = _fabriquer("la location saisonniere", marketing_auto=True)
        self.assertTrue(resume.get("marketing"), (
            "aucun kit de vente alors que « marketing_auto » est actif"))
        fiches = [f for f in resume["marketing"] if "fiche-produit" in str(f)]
        self.assertTrue(fiches, "le kit ne contient pas de fiche produit")

    def test_l_extrait_offert_compte_les_chapitres_demandes(self):
        resume, _ = _fabriquer("le brassage de la biere",
                               marketing_auto=True, extrait_offert=2)
        extrait = resume.get("extrait") or {}
        self.assertEqual(extrait.get("chapitres_offerts"), 2, (
            "extrait_offert=2 n'a pas ete lu : {}".format(extrait)))

    def test_l_archive_est_ecrite(self):
        resume, _ = _fabriquer("l'entretien d'une piscine", archive_auto=True)
        archive = resume.get("archive")
        self.assertTrue(archive, "aucune archive alors que « archive_auto » "
                                 "est actif")
        self.assertTrue(Path(archive).exists())
        self.assertTrue(str(archive).endswith(".zip"))

    def test_rien_n_est_produit_quand_rien_n_est_demande(self):
        """Le garde-fou qui crie a tort : une usine qui empaquette toujours
        aurait fait passer les quatre tests ci-dessus sans rien cabler."""
        resume, compte = _fabriquer("la culture du safran")
        self.assertIsNone(resume.get("archive"))
        self.assertFalse(resume.get("marketing"))
        self.assertEqual(compte[equipe.LECTEUR.nom], 0)


class LeMemeVerdictDesDeuxCotes(unittest.TestCase):
    """La ligne de commande et le bouton doivent decider pareil.

    Ils decidaient pareil sur le papier et pas dans les faits : le code du
    verdict n'existait que d'un cote. Il vit maintenant dans « apres.veut »,
    que les deux appellent — c'est ce qui les empeche de rediverger.
    """

    def tearDown(self):
        reglages.reinitialiser()

    def test_le_reglage_decide_quand_personne_ne_tranche(self):
        reglages.ecrire({"archive_auto": True})
        self.assertTrue(apres.veut(None, "archive_auto"))

    def test_un_refus_explicite_l_emporte_sur_le_reglage(self):
        reglages.ecrire({"archive_auto": True})
        self.assertFalse(apres.veut(False, "archive_auto"))

    def test_une_demande_explicite_suffit_sans_reglage(self):
        self.assertTrue(apres.veut(True, "archive_auto"))


if __name__ == "__main__":
    unittest.main()
