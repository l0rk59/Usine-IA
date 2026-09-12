"""Le routeur IA : ce qu'il compte, ce qu'il attend, ce qu'il retient.

Cinq defauts sont corriges ici, et chacun se voyait mal parce qu'aucun ne
provoque d'erreur — ils font juste perdre quelque chose en silence : une fin
de chapitre, un quota, une attente, un repos, une entree de cache.

Rien ici ne sort sur le reseau : le client HTTP est remplace.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import cles as pool_cles  # noqa: E402
from usine.core import config, llm, store  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402


def setUpModule():
    atelier.isoler("routeur")


def _reponse(texte="du texte", finish="stop", tokens=42):
    return {"choices": [{"message": {"content": texte}, "finish_reason": finish}],
            "usage": {"total_tokens": tokens}}


def _vider_appels():
    with store.cursor() as cur:
        cur.execute("DELETE FROM appels")
        cur.execute("DELETE FROM cles_journal")
    store.cache_vider()
    llm._REPOS.clear()
    llm._REPOS_CHARGE = False
    pool_cles.oublier()


class TestTroncature(unittest.TestCase):
    """« finish_reason » n'etait pas lu : un chapitre coupe au milieu d'une
    phrase passait pour un chapitre termine, partout en aval."""

    def setUp(self):
        _vider_appels()

    def _generer(self, finish):
        with mock.patch.object(llm, "post_json", return_value=_reponse(finish=finish)):
            with mock.patch.object(config, "active_providers",
                                   return_value=[config.PROVIDERS_BY_NAME["groq"]]):
                return llm.generer("invite", cache=False)

    def test_une_reponse_complete_n_est_pas_dite_tronquee(self):
        self.assertFalse(self._generer("stop").tronquee)

    def test_une_reponse_coupee_au_plafond_est_signalee(self):
        self.assertTrue(self._generer("length").tronquee)
        self.assertTrue(self._generer("max_tokens").tronquee)

    def test_une_reponse_tronquee_n_entre_pas_au_cache(self):
        """La resservir indefiniment fixerait la coupure pour toujours."""
        with mock.patch.object(llm, "post_json", return_value=_reponse(finish="length")):
            with mock.patch.object(config, "active_providers",
                                   return_value=[config.PROVIDERS_BY_NAME["groq"]]):
                llm.generer("invite unique", cache=True)
                deuxieme = llm.generer("invite unique", cache=True)
        self.assertFalse(deuxieme.depuis_cache)

    def test_le_plafond_demande_est_ramene_a_ce_que_le_fournisseur_emet(self):
        vus = {}

        def espion(url, charge, entetes, timeout=0):
            vus.update(charge)
            return _reponse()

        with mock.patch.object(llm, "post_json", side_effect=espion):
            with mock.patch.object(config, "active_providers",
                                   return_value=[config.PROVIDERS_BY_NAME["ollama"]]):
                llm.generer("invite", max_tokens=60000, cache=False)
        self.assertEqual(vus["max_tokens"],
                         config.PROVIDERS_BY_NAME["ollama"].max_sortie)


class TestComptabiliteDuQuota(unittest.TestCase):
    """Un fournisseur ne doit pas payer pour une panne dont il n'est pas la cause."""

    def setUp(self):
        _vider_appels()

    def test_une_coupure_reseau_ne_consomme_pas_le_quota(self):
        store.enregistrer_appel("groq", "m", False, erreur="HTTP 0 : reseau indisponible")
        store.enregistrer_appel("groq", "m", False, erreur="HTTP 500 : erreur serveur")
        self.assertEqual(store.compteur_jour("groq"), 0)

    def test_un_succes_et_un_429_le_consomment(self):
        """Le 429 a bien ete traite par le service : il compte chez lui."""
        store.enregistrer_appel("groq", "m", True)
        store.enregistrer_appel("groq", "m", False, erreur="HTTP 429 : trop de requetes")
        self.assertEqual(store.compteur_jour("groq"), 2)

    def test_le_debit_par_minute_compte_tout(self):
        """Une requete refusee a bien ete envoyee : elle pese sur le debit."""
        store.enregistrer_appel("groq", "m", False, erreur="HTTP 500 : erreur")
        self.assertEqual(store.compteur_minute("groq"), 1)

    def test_la_meme_regle_vaut_par_cle(self):
        store.enregistrer_appel("groq", "m", False, erreur="HTTP 0 : reseau", cle_id="abc")
        store.enregistrer_appel("groq", "m", True, cle_id="abc")
        self.assertEqual(store.compteur_jour_cle("groq", "abc"), 1)


class TestRetryAfter(unittest.TestCase):
    """Le service dit combien de temps attendre ; l'ignorer coutait des minutes."""

    def test_un_nombre_de_secondes(self):
        self.assertEqual(HttpErreur(429, "x", entetes={"Retry-After": "45"}).patienter(), 45.0)

    def test_l_entete_est_insensible_a_la_casse(self):
        self.assertEqual(HttpErreur(429, "x", entetes={"retry-after": "12"}).patienter(), 12.0)

    def test_une_date_http(self):
        futur = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 120))
        attente = HttpErreur(429, "x", entetes={"Retry-After": futur}).patienter()
        self.assertGreater(attente, 60)
        self.assertLessEqual(attente, 130)

    def test_un_service_muet_ou_absurde_rend_zero(self):
        self.assertEqual(HttpErreur(429, "x").patienter(), 0.0)
        self.assertEqual(HttpErreur(429, "x", entetes={"Retry-After": "bientot"}).patienter(), 0.0)

    def test_une_attente_demesuree_est_bornee(self):
        """Une heure suffit : au-dela, mieux vaut changer de fournisseur."""
        self.assertEqual(
            HttpErreur(429, "x", entetes={"Retry-After": "999999"}).patienter(), 3600.0)

    def test_une_date_passee_ne_rend_pas_un_negatif(self):
        passe = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() - 600))
        self.assertEqual(HttpErreur(429, "x", entetes={"Retry-After": passe}).patienter(), 0.0)


class TestRetryAfterDansLeRouteur(unittest.TestCase):
    """Lire l'en-tete ne sert a rien si le routeur ne s'en sert pas."""

    def setUp(self):
        _vider_appels()

    def _refuser(self, entetes):
        """Fait repondre 429 a un fournisseur sans cle, et rend son repos."""
        erreur = HttpErreur(429, "trop de requetes", entetes=entetes)
        avant = time.time()
        with mock.patch.object(llm, "post_json", side_effect=erreur):
            with mock.patch.object(config, "active_providers",
                                   return_value=[config.PROVIDERS_BY_NAME["pollinations"]]):
                with mock.patch.object(llm.time, "sleep", lambda _s: None):
                    with self.assertRaises(llm.PlusDeFournisseur):
                        llm.generer("invite", cache=False)
        return llm._REPOS.get("pollinations", 0) - avant

    def test_le_delai_demande_est_respecte(self):
        """Le service demande dix minutes : on ne revient pas dans 90 s."""
        self.assertGreater(self._refuser({"Retry-After": "600"}), 550)

    def test_un_service_muet_garde_le_repli(self):
        repos = self._refuser({})
        self.assertGreater(repos, 60)
        self.assertLess(repos, 120)

    def test_un_delai_court_n_est_pas_arrondi_vers_le_haut(self):
        """Attendre 90 s quand le service en demande 5 gaspille la session."""
        self.assertLess(self._refuser({"Retry-After": "5"}), 30)


class TestReposPersiste(unittest.TestCase):
    """Android tue le processus : le repos doit vivre en base, pas en memoire."""

    def setUp(self):
        _vider_appels()

    def test_le_repos_d_un_fournisseur_survit_au_processus(self):
        llm._reposer("groq", 600, "limite de debit")
        # Un nouveau processus : les dictionnaires sont vides.
        llm._REPOS.clear()
        llm._REPOS_CHARGE = False
        self.assertFalse(llm._quota_ok(config.PROVIDERS_BY_NAME["groq"]))

    def test_un_repos_expire_ne_bloque_plus(self):
        store.journal_cle("groq", "", "vieux repos", 1)
        with store.cursor() as cur:
            cur.execute("UPDATE cles_journal SET ts = ?", (time.time() - 3600,))
        llm._REPOS.clear()
        llm._REPOS_CHARGE = False
        self.assertTrue(llm._quota_ok(config.PROVIDERS_BY_NAME["groq"]))

    def test_le_repos_d_une_cle_survit_aussi(self):
        import os

        os.environ["CLE_DE_TEST"] = "valeur-secrete-de-test"
        pool_cles.oublier()
        lot = pool_cles.pool("essai", "CLE_DE_TEST")
        lot.mettre_au_repos(lot.cles[0], 900, "limite de debit")
        pool_cles.oublier()          # le processus repart de zero
        recharge = pool_cles.pool("essai", "CLE_DE_TEST")
        self.assertFalse(recharge.cles[0].disponible())
        self.assertEqual(recharge.disponibles(), [])
        del os.environ["CLE_DE_TEST"]


class TestCleDeCache(unittest.TestCase):
    """Deux appels qui ne different que par leur plafond ne sont pas le meme."""

    def test_le_plafond_de_jetons_entre_dans_la_cle(self):
        messages = [{"role": "user", "content": "identique"}]
        self.assertNotEqual(llm._cle_cache(messages, "standard", 0.7, 500),
                            llm._cle_cache(messages, "standard", 0.7, 4000))

    def test_le_mode_json_aussi(self):
        messages = [{"role": "user", "content": "identique"}]
        self.assertNotEqual(llm._cle_cache(messages, "standard", 0.7, 500, False),
                            llm._cle_cache(messages, "standard", 0.7, 500, True))

    def test_deux_appels_identiques_partagent_leur_entree(self):
        messages = [{"role": "user", "content": "identique"}]
        self.assertEqual(llm._cle_cache(messages, "standard", 0.7, 500),
                         llm._cle_cache(messages, "standard", 0.7, 500))


class TestBudgetEnJetons(unittest.TestCase):
    """Plusieurs paliers gratuits comptent en jetons, pas en requetes."""

    def setUp(self):
        _vider_appels()
        from usine.core import reglages

        reglages.ecrire({"budget_jetons_jour": 1000, "budget_appels_jour": 0,
                         "budget_appels_produit": 0, "budget_produits_jour": 0,
                         "budget_minutes_produit": 0})

    def tearDown(self):
        from usine.core import reglages

        reglages.ecrire({"budget_jetons_jour": 0})

    def test_sous_le_plafond_on_produit(self):
        from usine.core import budget

        store.enregistrer_appel("groq", "m", True, tokens=600)
        self.assertIsNone(budget.Compteur().peut_demarrer_produit())

    def test_au_dela_on_s_arrete(self):
        from usine.core import budget

        store.enregistrer_appel("groq", "m", True, tokens=1200)
        compteur = budget.Compteur()
        self.assertIn("jetons", compteur.peut_demarrer_produit())
        with self.assertRaises(budget.BudgetEpuise):
            compteur.verifier_appel()

    def test_les_jetons_d_un_appel_echoue_ne_comptent_pas(self):
        from usine.core import budget

        store.enregistrer_appel("groq", "m", False, tokens=5000, erreur="HTTP 500")
        self.assertIsNone(budget.Compteur().peut_demarrer_produit())

    def test_le_plafond_apparait_dans_l_etat(self):
        from usine.core import budget

        etat = budget.Compteur().etat()
        self.assertEqual(etat["jetons_jour_max"], 1000)
        self.assertIn("jetons_jour", etat)


class TestRoleLongContexte(unittest.TestCase):
    def test_chaque_fournisseur_repond_au_role_long(self):
        """« model_for » retombe sur standard : declarer le role ne casse rien."""
        for fournisseur in config.PROVIDERS:
            self.assertTrue(fournisseur.model_for("long"), fournisseur.name)

    def test_gemini_le_declare_explicitement(self):
        gemini = config.PROVIDERS_BY_NAME["gemini"]
        self.assertIn("long", gemini.models)

    def test_chaque_fournisseur_annonce_ce_qu_il_sait_emettre(self):
        for fournisseur in config.PROVIDERS:
            self.assertGreaterEqual(fournisseur.max_sortie, 1024, fournisseur.name)


if __name__ == "__main__":
    unittest.main()
