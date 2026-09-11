"""Tests de la file de production, du budget et de l'usine continue.

Aucun appel reseau : le routeur IA est remplace par un simulateur.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import production  # noqa: E402
from usine.core import budget, config, file, llm, reglages, store  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402

BASE = dict(images=False, qualite="rapide", pause_entre_produits=0,
            budget_appels_jour=0, budget_appels_produit=0,
            budget_produits_jour=0, budget_minutes_produit=0)


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("usine-continue")


def _remettre_a_zero():
    file.vider(tout=True)
    store.cache_vider()
    with store.cursor() as cur:
        cur.execute("DELETE FROM appels")
    reglages.ecrire(dict(BASE))
    for nom in ("usine.pid", "usine.stop", "usine-etat.json"):
        (config.WORKDIR / nom).unlink(missing_ok=True)


class TestFile(unittest.TestCase):
    def setUp(self):
        _remettre_a_zero()

    def test_priorite_avant_ordre_d_ajout(self):
        file.ajouter("tardif", "ebook", priorite=9)
        file.ajouter("urgent", "ebook", priorite=1)
        self.assertEqual(file.prochain()["sujet"], "urgent")

    def test_doublon_refuse_tant_qu_il_est_en_file(self):
        self.assertIsNotNone(file.ajouter("meme sujet", "ebook"))
        self.assertIsNone(file.ajouter("meme sujet", "ebook"))
        # Un autre type de produit sur le meme sujet reste legitime.
        self.assertIsNotNone(file.ajouter("meme sujet", "prompts"))

    def test_un_sujet_livre_peut_etre_relance(self):
        identifiant = file.ajouter("sujet", "ebook")
        entree = file.prochain()
        file.terminer(entree["id"], "produit-1")
        self.assertIsNotNone(file.ajouter("sujet", "ebook"),
                             "un sujet deja livre doit pouvoir etre refait")
        self.assertNotEqual(identifiant, None)

    def test_reprise_puis_condamnation(self):
        file.ajouter("fragile", "ebook", max_tentatives=2)
        entree = file.prochain()
        self.assertEqual(file.echouer(entree["id"], "reseau"), "en_attente")
        entree = file.prochain()
        self.assertEqual(file.echouer(entree["id"], "reseau"), "echec")
        self.assertEqual(file.compter()["echec"], 1)

    def test_rejouer_remet_les_echecs_en_file(self):
        file.ajouter("casse", "ebook", max_tentatives=1)
        entree = file.prochain()
        file.echouer(entree["id"], "erreur")
        self.assertEqual(file.rejouer(), 1)
        self.assertEqual(file.compter()["en_attente"], 1)

    def test_orphelins_liberes_au_demarrage(self):
        """Android tue le processus : l'entree en cours doit revenir en file."""
        file.ajouter("interrompu", "ebook")
        file.prochain()
        self.assertEqual(file.compter()["en_cours"], 1)
        self.assertEqual(file.liberer_orphelins(), 1)
        self.assertEqual(file.compter()["en_attente"], 1)

    def test_retirer_et_vider(self):
        identifiant = file.ajouter("a retirer", "ebook")
        self.assertTrue(file.retirer(identifiant))
        self.assertFalse(file.retirer(identifiant), "deux retraits ne font pas deux")
        self.assertEqual(file.compter()["annule"], 1)
        self.assertEqual(file.vider(), 1)


class TestBudget(unittest.TestCase):
    def setUp(self):
        _remettre_a_zero()
        budget.brancher(None)

    def tearDown(self):
        budget.brancher(None)

    def test_sans_plafond_rien_n_est_refuse(self):
        compteur = budget.Compteur(budget.Plafonds())
        compteur.demarrer_produit()
        for _ in range(50):
            store.enregistrer_appel("faux", "m", True)
            compteur.verifier_appel()  # ne doit pas lever

    def test_plafond_par_produit(self):
        compteur = budget.Compteur(budget.Plafonds(appels_produit=3))
        compteur.demarrer_produit()
        for _ in range(3):
            compteur.verifier_appel()
            store.enregistrer_appel("faux", "m", True)
        with self.assertRaises(budget.BudgetEpuise) as contexte:
            compteur.verifier_appel()
        self.assertEqual(contexte.exception.plafond, "appels par produit")

    def test_refus_de_demarrer_un_produit_infinissable(self):
        """Entamer un produit qu'on ne peut pas finir gaspille le reste."""
        compteur = budget.Compteur(
            budget.Plafonds(appels_jour=10, appels_produit=30))
        for _ in range(8):
            store.enregistrer_appel("faux", "m", True)
        motif = compteur.peut_demarrer_produit()
        self.assertIsNotNone(motif)
        self.assertIn("trop peu", motif)

    def test_plafond_de_produits_par_jour(self):
        compteur = budget.Compteur(budget.Plafonds(produits_jour=2))
        for _ in range(2):
            compteur.demarrer_produit()
            compteur.terminer_produit(reussi=True)
        self.assertIn("2 produit(s) par jour", compteur.peut_demarrer_produit() or "")

    def test_la_garde_est_consultee_par_le_routeur(self):
        compteur = budget.Compteur(budget.Plafonds(appels_jour=1))
        store.enregistrer_appel("faux", "m", True)
        budget.brancher(compteur)
        llm.definir_simulateur(lambda messages, role: "texte")
        try:
            with self.assertRaises(budget.BudgetEpuise):
                llm.generer("une invite inedite pour ce test", cache=False)
        finally:
            llm.definir_simulateur(None)

    def test_une_reponse_en_cache_ne_consomme_pas_de_budget(self):
        """Le cache est verifie avant le budget : relire ne coute rien."""
        compteur = budget.Compteur(budget.Plafonds(appels_jour=1))
        llm.definir_simulateur(lambda messages, role: "reponse mise en cache")
        try:
            invite = "invite mise en cache pour le test du budget"
            llm.generer(invite)                      # 1er appel : compte
            budget.brancher(compteur)
            reponse = llm.generer(invite)            # 2e : servi par le cache
            self.assertTrue(reponse.depuis_cache)
        finally:
            llm.definir_simulateur(None)


class TestUsineContinue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def setUp(self):
        _remettre_a_zero()

    def _moteur(self, **kwargs):
        return production.UsineContinue(journal=lambda m: None, pause=0, **kwargs)

    def test_la_file_est_consommee(self):
        for i in range(3):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 3)
        self.assertEqual(file.compter()["en_attente"], 0)
        self.assertEqual(file.compter()["fait"], 3)
        self.assertEqual(moteur.motif_fin, "file vide")

    def test_maximum_respecte_et_file_preservee(self):
        for i in range(4):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur(maximum=2)
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 2)
        self.assertEqual(file.compter()["en_attente"], 2)

    def test_budget_journalier_empeche_de_demarrer(self):
        reglages.ecrire(dict(BASE, budget_appels_jour=4))
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 0)
        self.assertIn("trop peu", moteur.motif_fin)
        self.assertEqual(file.compter()["en_attente"], 1,
                         "la niche doit rester en file")

    def test_budget_epuise_en_cours_exporte_quand_meme(self):
        """Promesse tenue : un plafond atteint ne detruit pas le travail fait."""
        reglages.ecrire(dict(BASE, budget_appels_produit=5))
        file.ajouter("sujet tronque", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1, "le produit doit etre livre")
        dossier = Path(moteur.faits[0]["dossier"])
        fichiers = [f.name for f in dossier.iterdir() if f.is_file()]
        self.assertTrue(any(f.endswith(".pdf") for f in fichiers))
        self.assertTrue(any(f.endswith(".epub") for f in fichiers))
        self.assertIn("livre.md", fichiers)
        self.assertGreater((dossier / "livre.md").stat().st_size, 500)
        self.assertIn("budget epuise", moteur.motif_fin)

    def test_type_inconnu_ne_bloque_pas_la_file(self):
        file.ajouter("mauvais type", "inexistant")
        file.ajouter("bon sujet", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1)

    def test_arret_entre_deux_produits(self):
        """Le drapeau d'arret est lu entre deux produits, pas au milieu d'un."""
        for i in range(4):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        original = moteur._fabriquer

        def fabriquer_puis_demander(entree):
            resultat = original(entree)
            (config.WORKDIR / "usine.stop").write_text("stop", encoding="utf-8")
            return resultat

        moteur._fabriquer = fabriquer_puis_demander
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1)
        self.assertEqual(file.compter()["en_attente"], 3,
                         "les niches non traitees doivent rester en file")

    def test_verrou_empeche_deux_usines(self):
        production._poser_verrou()
        try:
            self.assertEqual(production.verrou_actif(), os.getpid())
            self.assertEqual(self._moteur().tourner(), 1)
        finally:
            production._lever_verrou()

    def test_verrou_orphelin_est_nettoye(self):
        """Un processus tue laisse un verrou qui ment : il doit etre ignore."""
        (config.WORKDIR / "usine.pid").write_text("999999", encoding="utf-8")
        self.assertIsNone(production.verrou_actif())
        self.assertFalse((config.WORKDIR / "usine.pid").exists())

    def test_etat_lisible_depuis_un_autre_processus(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        self._moteur().tourner()
        etat = production.statut()
        self.assertFalse(etat["en_marche"])
        self.assertEqual(etat["session"]["nombre_faits"], 1)
        self.assertIn("budget", etat)

    def test_ecriture_d_etat_atomique(self):
        """Aucun lecteur ne doit pouvoir tomber sur un fichier a moitie ecrit."""
        production.ecrire_etat({"a": 1})
        self.assertEqual(production.lire_etat()["a"], 1)
        self.assertFalse(
            production.chemin_etat().with_suffix(".json.tmp").exists(),
            "le fichier temporaire doit avoir ete renomme")

    def test_etat_illisible_ne_casse_rien(self):
        production.chemin_etat().write_text("{ pas du json", encoding="utf-8")
        self.assertEqual(production.lire_etat(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
