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


# ==========================================================================
# Ce que les fournisseurs autorisent vraiment
# ==========================================================================

# Retires du palier gratuit de leur fournisseur. L'usine les a demandes
# pendant des semaines apres leur retrait : chaque appel repondait 404, le
# routeur mettait le fournisseur au repos et passait au suivant — le
# comportement prevu pour une panne passagere, appliquee a une panne
# definitive. Les noms restent ici pour que la regression soit impossible.
MODELES_RETIRES = {
    "groq": ("llama-3.1-8b-instant", "llama-3.3-70b-versatile"),
    "cerebras": ("llama3.1-8b", "llama-3.3-70b"),
    # Mesures sur un compte reel, 15/09/2026 : 404 sur chacun, deux fois a un
    # jour d'intervalle. « writer/palmyra-creative-122b » figure pourtant au
    # catalogue public de NVIDIA — liste ne veut pas dire appelable.
    "gemini": ("gemini-2.5-flash", "gemini-2.5-flash-lite"),
    "nvidia": ("writer/palmyra-creative-122b",
               "mistralai/codestral-22b-instruct-v0.1",
               "nvidia/nemotron-nano-3-30b-a3b"),
}


class TestCatalogueDesModeles(unittest.TestCase):
    def test_aucun_modele_retire_n_est_encore_configure(self):
        for nom, retires in MODELES_RETIRES.items():
            configures = set(config.PROVIDERS_BY_NAME[nom].models.values())
            for mort in retires:
                self.assertNotIn(mort, configures,
                                 "{} demande encore {}".format(nom, mort))

    def test_chaque_fournisseur_declare_les_trois_roles(self):
        for p in config.PROVIDERS:
            for role in ("rapide", "standard", "costaud"):
                self.assertTrue(p.model_for(role), "{}/{}".format(p.name, role))


class TestQuotaParModele(unittest.TestCase):
    """Google compte par modele. Un seul couple rpm/rpd pour tout le
    fournisseur interdisait flash-lite — mille requetes par jour — des que
    flash avait epuise ses deux cent cinquante."""

    def setUp(self):
        _vider_appels()
        self.gemini = config.PROVIDERS_BY_NAME["gemini"]

    def _saturer(self, modele, nombre):
        maintenant = time.time()
        with store.cursor() as cur:
            cur.executemany(
                "INSERT INTO appels(fournisseur, modele, ts, jour, ok, tokens)"
                " VALUES ('gemini',?,?,?,1,10)",
                [(modele, maintenant, store._jour())] * nombre)

    def test_les_deux_modeles_ont_des_plafonds_differents(self):
        self.assertNotEqual(self.gemini.quota("standard").rpd,
                            self.gemini.quota("rapide").rpd)

    def test_epuiser_flash_ferme_flash(self):
        # Le nom du modele se LIT dans la configuration : le recopier ici en
        # faisait la meme donnee perissable a un deuxieme endroit, et ces deux
        # cas ont casse le jour ou Google a retire ses « 2.5 ». Ce qui est
        # teste, c'est le comptage PAR MODELE, pas un identifiant precis.
        self._saturer(self.gemini.model_for("standard"),
                      self.gemini.quota("standard").rpd)
        self.assertFalse(llm._quota_ok(self.gemini, "standard"))

    def test_epuiser_le_modele_le_plus_genereux_n_en_ferme_pas_un_autre(self):
        """Le cas qui distingue vraiment les deux comptages.

        flash-lite a droit a mille requetes par jour, flash a deux cent
        cinquante. En comptant pour tout le fournisseur, les mille requetes de
        flash-lite fermaient flash quatre fois plus tot que son propre quota —
        et le role « costaud », qui passe par flash, devenait indisponible
        pour une raison qui ne le concernait pas.
        """
        self._saturer(self.gemini.model_for("rapide"),
                      self.gemini.quota("rapide").rpd)
        self.assertFalse(llm._quota_ok(self.gemini, "rapide"))
        self.assertTrue(llm._quota_ok(self.gemini, "standard"))

    def test_un_quota_de_fournisseur_compte_tous_les_modeles(self):
        mistral = config.PROVIDERS_BY_NAME["mistral"]
        self.assertEqual(mistral.quota("rapide").portee, "fournisseur")
        for _ in range(mistral.quota("standard").rpd):
            store.enregistrer_appel("mistral", "mistral-small-latest", True, 10)
        # Le quota vaut pour le service entier : changer de role n'en ouvre pas
        # un second.
        self.assertFalse(llm._quota_ok(mistral, "costaud"))


class TestBudgetEnJetonsParFournisseur(unittest.TestCase):
    """Groq annonce trente requetes par minute et huit mille jetons. C'est le
    second chiffre qui decide : une demande de chapitre ne tient pas dedans."""

    def setUp(self):
        _vider_appels()
        self.groq = config.PROVIDERS_BY_NAME["groq"]

    def test_le_cout_estime_compte_l_entree_et_la_sortie(self):
        """Exprime par la constante, pas par un nombre fige : un test qui
        recopie une valeur derivee casse a chaque reetalonnage et n'apprend
        rien sur ce qui est vrai."""
        caracteres = 3500
        messages = [{"role": "user", "content": "a" * caracteres}]
        cout = llm._cout_estime(messages, 2000, self.groq)
        attendu = 2000 + caracteres / llm.CARACTERES_PAR_JETON
        self.assertGreater(cout, attendu * 0.95)
        self.assertLess(cout, attendu * 1.10)

    def test_les_deux_estimateurs_de_jetons_s_accordent(self):
        """Ils convertissent tous deux du francais en jetons, et ils ne
        peuvent pas avoir raison ensemble.

        Ils ont diverge d'un facteur 1,63 : celui qui fixe le plafond de
        sortie comptait 2,6 jetons par mot, celui qui pese une demande avant
        de l'envoyer 3,5 caracteres par jeton. La contradiction tenait dans
        deux modules differents, ou personne ne pouvait la voir.
        """
        from usine.pipelines.base import jetons_pour

        mots = 1000
        par_le_plafond = jetons_pour(mots, marge=0)
        texte = "a" * int(mots * llm.CARACTERES_PAR_MOT)
        par_le_cout = llm._cout_estime([{"role": "user", "content": texte}],
                                       0, self.groq) - self.groq.max_sortie
        self.assertAlmostEqual(par_le_plafond, par_le_cout,
                               delta=par_le_plafond * 0.05)

    def test_une_demande_plus_grosse_que_la_minute_ecarte_le_fournisseur(self):
        messages = [{"role": "user", "content": "a" * 12000}]
        cout = llm._cout_estime(messages, 8192, self.groq)
        self.assertGreater(cout, self.groq.quota("standard").tpm)
        self.assertIsNone(llm._attente(self.groq, "standard", cout))

    def test_une_demande_courte_passe(self):
        self.assertEqual(llm._attente(self.groq, "standard", 1200), 0.0)

    def test_le_routeur_passe_au_suivant_sans_appeler(self):
        """Le point de la mesure : ne pas aller chercher un 429 a la main."""
        mistral = config.PROVIDERS_BY_NAME["mistral"]
        appels = []

        def espion(url, charge, entetes, timeout=0):
            appels.append(url)
            return _reponse()

        with mock.patch.object(llm, "post_json", side_effect=espion):
            with mock.patch.object(config, "active_providers",
                                   return_value=[self.groq, mistral]):
                rep = llm.generer("z" * 12000, max_tokens=8192, cache=False)
        self.assertEqual(rep.fournisseur, "mistral")
        self.assertEqual(len(appels), 1)
        self.assertNotIn("groq", appels[0])

    def test_le_plafond_journalier_en_jetons_ferme_le_fournisseur(self):
        self.assertTrue(llm._quota_ok(self.groq, "standard"))
        store.enregistrer_appel("groq", "openai/gpt-oss-120b", True,
                                self.groq.quota("standard").tpd, 1.0)
        self.assertFalse(llm._quota_ok(self.groq, "standard"))

    def test_l_attente_suit_la_fenetre_glissante(self):
        """La place se libere quand le plus vieil appel sort de la minute,
        pas a la minute ronde."""
        q = self.groq.quota("standard")
        with store.cursor() as cur:
            cur.execute(
                "INSERT INTO appels(fournisseur, modele, ts, jour, ok, tokens)"
                " VALUES (?,?,?,?,1,?)",
                ("groq", "openai/gpt-oss-120b", time.time() - 45,
                 store._jour(), q.tpm - 100))
        attente = llm._attente(self.groq, "standard", 1000)
        self.assertIsNotNone(attente)
        self.assertGreater(attente, 10.0)
        self.assertLess(attente, 20.0)

    def test_un_fournisseur_sans_plafond_publie_n_est_jamais_freine(self):
        mistral = config.PROVIDERS_BY_NAME["mistral"]
        self.assertEqual(mistral.quota("standard").tpm, 0)
        self.assertEqual(llm._attente(mistral, "standard", 500000), 0.0)


class TestModeleDisparu(unittest.TestCase):
    """Un 404 distant a une seule cause, et le message brut ne la disait pas."""

    def setUp(self):
        _vider_appels()

    def test_le_message_nomme_le_modele_et_le_remede(self):
        groq = config.PROVIDERS_BY_NAME["groq"]
        texte = llm._expliquer(groq, HttpErreur(404, "Not Found"),
                               "openai/gpt-oss-120b")
        self.assertIn("openai/gpt-oss-120b", texte)
        self.assertIn("n'existe plus", texte)
        self.assertIn("usine docteur --modeles", texte)

    def test_le_routeur_remonte_cette_explication(self):
        groq = config.PROVIDERS_BY_NAME["groq"]
        with mock.patch.object(llm, "post_json",
                               side_effect=HttpErreur(404, "Not Found")):
            with mock.patch.object(config, "active_providers",
                                   return_value=[groq]):
                with self.assertRaises(llm.PlusDeFournisseur) as capture:
                    llm.generer("court", cache=False)
        self.assertIn("n'existe plus", str(capture.exception))

    def test_un_404_local_garde_son_message_d_installation(self):
        ollama = config.PROVIDERS_BY_NAME["ollama"]
        texte = llm._expliquer(ollama, HttpErreur(404, "Not Found"))
        self.assertIn("ollama pull", texte)


class TestQuotaParCle(unittest.TestCase):
    """Le pool de cles doit multiplier le quota, ce qui est toute sa raison
    d'etre : « ne jamais s'arreter pour cause de quota ».

    Il ne multipliait rien. Les plafonds d'un fournisseur s'appliquent a un
    COMPTE, donc a une cle, et le routeur les comptait pour tout le
    fournisseur : il additionnait les consommations de cles independantes.
    Mille appels sur la premiere cle de Groq suffisaient a declarer le
    fournisseur epuise, la seconde n'ayant servi a rien.
    """

    def setUp(self):
        _vider_appels()
        self.groq = config.PROVIDERS_BY_NAME["groq"]

    def _consommer(self, cle_id, nombre, tokens=10):
        maintenant = time.time()
        with store.cursor() as cur:
            cur.executemany(
                "INSERT INTO appels(fournisseur, modele, ts, jour, ok, tokens,"
                " cle_id) VALUES ('groq','openai/gpt-oss-120b',?,?,1,?,?)",
                [(maintenant, store._jour(), tokens, cle_id)] * nombre)

    def test_epuiser_une_cle_n_epuise_pas_l_autre(self):
        self._consommer("cle-A", self.groq.quota("standard").rpd)
        self.assertFalse(llm._quota_ok(self.groq, "standard", "cle-A"))
        self.assertTrue(llm._quota_ok(self.groq, "standard", "cle-B"))

    def test_le_plafond_en_jetons_se_compte_aussi_par_cle(self):
        q = self.groq.quota("standard")
        self._consommer("cle-A", 1, tokens=q.tpd)
        self.assertFalse(llm._quota_ok(self.groq, "standard", "cle-A"))
        self.assertTrue(llm._quota_ok(self.groq, "standard", "cle-B"))

    def test_le_debit_par_minute_aussi(self):
        """Sinon deux cles se freinent l'une l'autre : le pool ralentit la
        production au lieu de l'accelerer."""
        q = self.groq.quota("standard")
        self._consommer("cle-A", q.rpm)
        self.assertGreater(llm._attente(self.groq, "standard", 100, "cle-A"), 0)
        self.assertEqual(llm._attente(self.groq, "standard", 100, "cle-B"), 0.0)

    def test_le_repos_du_fournisseur_vaut_pour_toutes_les_cles(self):
        """Un modele retire ou un service en panne ne regarde aucune cle en
        particulier : la ce sont bien toutes qui doivent s'arreter."""
        llm._reposer("groq", 600, "modele inconnu")
        self.assertFalse(llm._quota_ok(self.groq, "standard", "cle-A"))
        self.assertFalse(llm._quota_ok(self.groq, "standard", "cle-B"))

    def test_une_cle_saturee_en_JETONS_est_sautee_pas_le_fournisseur(self):
        """Le pool ecarte deja une cle qui a epuise ses REQUETES. Il ignore
        tout des jetons — et c'est le plafond qui tombe en premier chez Groq,
        deux cent mille jetons valant environ un livre. Une cle a bout de
        jetons mais pas de requetes doit donc etre sautee ici, et la suivante
        essayee : abandonner le fournisseur entier gaspillerait la seconde.
        """
        lot = pool_cles.Pool("groq", [
            pool_cles.Cle(valeur="cle-premiere", fournisseur="groq", rang=0),
            pool_cles.Cle(valeur="cle-seconde", fournisseur="groq", rang=1),
        ])
        premiere, seconde = lot.cles
        # Peu d'appels, beaucoup de jetons : sous le plafond de requetes,
        # au-dessus de celui de jetons. La seconde cle en a fait davantage,
        # pour que le pool — qui classe la moins sollicitee en tete — propose
        # bien la premiere d'abord : sinon la seconde repondrait sans que le
        # saut ait lieu, et ce test ne prouverait rien.
        self._consommer(premiere.id, 1, tokens=self.groq.quota("standard").tpd)
        self._consommer(seconde.id, 3, tokens=1)

        with mock.patch.object(pool_cles, "pool", return_value=lot):
            with mock.patch.object(llm, "post_json", return_value=_reponse()):
                with mock.patch.object(config, "active_providers",
                                       return_value=[self.groq]):
                    rep = llm.generer("court", cache=False)
        self.assertEqual(rep.cle, seconde.affichage)

    def test_le_routeur_bascule_sur_la_seconde_cle(self):
        """Le bout en bout : la premiere cle est saturee, l'appel doit partir
        quand meme, et avec l'autre cle."""
        lot = pool_cles.Pool("groq", [
            pool_cles.Cle(valeur="cle-premiere", fournisseur="groq", rang=0),
            pool_cles.Cle(valeur="cle-seconde", fournisseur="groq", rang=1),
        ])
        premiere, seconde = lot.cles
        self._consommer(premiere.id, self.groq.quota("standard").rpd)

        with mock.patch.object(pool_cles, "pool", return_value=lot):
            with mock.patch.object(llm, "post_json", return_value=_reponse()):
                with mock.patch.object(config, "active_providers",
                                       return_value=[self.groq]):
                    rep = llm.generer("court", cache=False)
        self.assertEqual(rep.fournisseur, "groq")
        self.assertEqual(rep.cle, seconde.affichage)


class TestJsonEtRotationDeFournisseur(unittest.TestCase):
    """Un fournisseur qui ne sait pas tenir un format ne doit pas couter
    trois appels puis la production entiere.

    « generer_json » reessayait trois fois avec la meme liste d'exclusions,
    donc chez le meme fournisseur : un modele qui repond en prose a une
    consigne « JSON uniquement » recommence, et la chaine mourait sur son
    premier appel — la construction du plan.
    """

    def setUp(self):
        _vider_appels()

    def _providers(self):
        return [config.PROVIDERS_BY_NAME["groq"],
                config.PROVIDERS_BY_NAME["mistral"]]

    def test_le_second_essai_change_de_fournisseur(self):
        vus = []

        def bavard(url, charge, entetes, timeout=0):
            vus.append(url)
            # Le premier fournisseur repond en prose, le second en JSON.
            if "groq" in url:
                return _reponse("Bonjour, je suis un modele.")
            return _reponse('{"ok": true}')

        with mock.patch.object(llm, "post_json", side_effect=bavard):
            with mock.patch.object(config, "active_providers",
                                   return_value=self._providers()):
                obtenu = llm.generer_json("donne du json")
        self.assertEqual(obtenu, {"ok": True})
        self.assertIn("groq", vus[0])
        self.assertIn("mistral", vus[1])

    def test_un_fournisseur_ecarte_ne_revient_pas(self):
        """Sinon l'essai suivant retombe dessus et brule un appel de plus."""
        vus = []

        def muet(url, charge, entetes, timeout=0):
            vus.append(url)
            return _reponse("toujours de la prose")

        with mock.patch.object(llm, "post_json", side_effect=muet):
            with mock.patch.object(config, "active_providers",
                                   return_value=self._providers()):
                with self.assertRaises(ValueError):
                    llm.generer_json("donne du json")
        # Ce qui compte : aucun fournisseur n'est resollicite tant qu'il en
        # reste un qui n'a pas essaye. Au troisieme essai les deux ont
        # echoue, et « generer » refuse d'ecarter tout le monde — mieux vaut
        # un nouvel essai chez le premier, a temperature plus haute, que pas
        # d'essai du tout.
        self.assertEqual(len(vus), 3)
        self.assertNotEqual(vus[0], vus[1])

    def test_le_message_dit_quoi_faire(self):
        """« JSON introuvable » n'apprend rien a qui produit depuis un
        telephone."""
        with mock.patch.object(llm, "post_json",
                               return_value=_reponse("de la prose")):
            with mock.patch.object(config, "active_providers",
                                   return_value=self._providers()):
                with self.assertRaises(ValueError) as capture:
                    llm.generer_json("donne du json")
        message = str(capture.exception)
        self.assertIn("modele trop petit", message)
        self.assertIn("groq", message)

    def test_une_reponse_json_du_premier_coup_ne_change_rien(self):
        with mock.patch.object(llm, "post_json",
                               return_value=_reponse('{"ok": 1}')):
            with mock.patch.object(config, "active_providers",
                                   return_value=self._providers()):
                self.assertEqual(llm.generer_json("donne du json"), {"ok": 1})
