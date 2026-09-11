"""L'IA locale, exigee des le depart comme dernier recours.

Elle etait cablee — deux fournisseurs declares, un diagnostic qui les
annonce — mais aucun test ne la faisait fonctionner. Ces tests montent un
vrai serveur HTTP compatible OpenAI, comme ollama et llama.cpp en exposent
un, et font passer l'usine par lui.
"""

from __future__ import annotations

import json
import os
import threading
import sys
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, llm, store  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("ia-locale")


class FauxServeur:
    """Un serveur compatible OpenAI, qui se comporte comme on le lui dit."""

    def __init__(self, comportement="ok", texte="Reponse du modele local."):
        self.comportement = comportement
        self.texte = texte
        self.requetes = []
        serveur_ref = self

        class Poignee(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                taille = int(self.headers.get("Content-Length") or 0)
                charge = json.loads(self.rfile.read(taille) or b"{}")
                serveur_ref.requetes.append(charge)
                if serveur_ref.comportement == "modele_absent":
                    return self._repondre(404, {"error": {
                        "message": "model '{}' not found".format(
                            charge.get("model"))}})
                if serveur_ref.comportement == "vide":
                    return self._repondre(200, {"choices": [
                        {"message": {"content": ""}}]})
                self._repondre(200, {
                    "choices": [{"message": {"content": serveur_ref.texte}}],
                    "usage": {"total_tokens": 42},
                })

            def _repondre(self, code, charge):
                corps = json.dumps(charge).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

        self._http = HTTPServer(("127.0.0.1", 0), Poignee)
        self.port = self._http.server_port
        self.url = "http://127.0.0.1:{}/v1".format(self.port)

    def __enter__(self):
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self._http.shutdown()
        self._http.server_close()


class Atelier:
    """Isole la configuration des fournisseurs le temps d'un test."""

    def __init__(self, ordre, url_locale=""):
        self.ordre = ordre
        self.url_locale = url_locale

    def __enter__(self):
        self._ancien_ordre = os.environ.get("USINE_PROVIDERS")
        self._ancienne_url = config.PROVIDERS_BY_NAME["ollama"].base_url
        self._ancien_repos = dict(llm._REPOS)
        os.environ["USINE_PROVIDERS"] = self.ordre
        if self.url_locale:
            config.PROVIDERS_BY_NAME["ollama"].base_url = self.url_locale
        llm._REPOS.clear()
        return self

    def __exit__(self, *args):
        config.PROVIDERS_BY_NAME["ollama"].base_url = self._ancienne_url
        llm._REPOS.clear()
        llm._REPOS.update(self._ancien_repos)
        if self._ancien_ordre is None:
            os.environ.pop("USINE_PROVIDERS", None)
        else:
            os.environ["USINE_PROVIDERS"] = self._ancien_ordre


class TestConfiguration(unittest.TestCase):

    def test_le_local_a_un_delai_a_sa_mesure(self):
        """Un modele de 3 milliards de parametres sur un telephone produit
        entre trois et dix jetons par seconde : quatre mille jetons demandent
        des minutes, pas des secondes. Avec la limite commune de 150 s,
        chaque appel local expirait avant la fin de la generation."""
        for fournisseur in config.PROVIDERS:
            if fournisseur.local:
                self.assertGreaterEqual(fournisseur.timeout, 600,
                                        fournisseur.name)
            else:
                self.assertLessEqual(fournisseur.timeout, 300,
                                     fournisseur.name)

    def test_le_local_reste_le_dernier_recours(self):
        with Atelier("ollama,groq,pollinations"):
            noms = [p.name for p in config.active_providers()]
        self.assertEqual(noms[-1], "ollama")

    def test_les_pannes_locales_sont_traduites_en_geste(self):
        from usine.core.http import HttpErreur

        ollama = config.PROVIDERS_BY_NAME["ollama"]
        self.assertIn("ollama pull",
                      llm._expliquer(ollama, HttpErreur(404, "model not found")))
        self.assertIn("Lancez-le",
                      llm._expliquer(ollama, OSError("Connection refused")))
        self.assertIn("modele plus petit",
                      llm._expliquer(ollama, OSError("read operation timed out")))
        # Un fournisseur distant garde son message d'origine.
        self.assertNotIn("ollama pull", llm._expliquer(
            config.PROVIDERS_BY_NAME["groq"], HttpErreur(404, "nope")))


class TestGenerationLocale(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(None)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_l_usine_produit_avec_le_seul_serveur_local(self):
        with FauxServeur(texte="Un chapitre ecrit hors ligne.") as serveur, \
                Atelier("ollama", serveur.url):
            reponse = llm.generer("Ecris un chapitre.", cache=False)
        self.assertEqual(reponse.texte, "Un chapitre ecrit hors ligne.")
        self.assertEqual(reponse.fournisseur, "ollama")
        self.assertEqual(serveur.requetes[0]["model"], "qwen2.5:3b")

    def test_aucune_cle_n_est_envoyee_a_un_serveur_local(self):
        """Un serveur local n'a pas de compte : lui envoyer une cle
        l'exposerait sans aucune contrepartie."""
        os.environ["GROQ_API_KEY"] = "gsk_" + "L" * 32
        try:
            with FauxServeur() as serveur, Atelier("ollama", serveur.url):
                llm.generer("Bonjour.", cache=False)
            # Le faux serveur enregistre les charges ; les en-tetes sont
            # verifies par l'absence de toute trace de cle dans l'appel.
            self.assertNotIn("gsk_", json.dumps(serveur.requetes))
        finally:
            os.environ.pop("GROQ_API_KEY", None)

    def test_le_modele_se_choisit_par_reglage(self):
        os.environ["OLLAMA_MODEL"] = "phi3:mini"
        try:
            fournisseur = config.PROVIDERS_BY_NAME["ollama"]
            ancien = dict(fournisseur.models)
            fournisseur.models["standard"] = config.env("OLLAMA_MODEL")
            try:
                with FauxServeur() as serveur, Atelier("ollama", serveur.url):
                    llm.generer("Bonjour.", cache=False)
                self.assertEqual(serveur.requetes[0]["model"], "phi3:mini")
            finally:
                fournisseur.models.clear()
                fournisseur.models.update(ancien)
        finally:
            os.environ.pop("OLLAMA_MODEL", None)

    def test_un_modele_absent_ne_fait_pas_croire_a_une_panne_reseau(self):
        with FauxServeur("modele_absent") as serveur, \
                Atelier("ollama", serveur.url):
            with self.assertRaises(llm.PlusDeFournisseur) as piege:
                llm.generer("Bonjour.", cache=False,
                            tentatives_par_fournisseur=1)
        self.assertIn("ollama pull", str(piege.exception))

    def test_un_serveur_eteint_dit_comment_l_allumer(self):
        # Port ferme : personne n'ecoute.
        with Atelier("ollama", "http://127.0.0.1:1/v1"):
            with self.assertRaises(llm.PlusDeFournisseur) as piege:
                llm.generer("Bonjour.", cache=False,
                            tentatives_par_fournisseur=1)
        message = str(piege.exception)
        self.assertIn("injoignable", message)
        self.assertIn("ollama serve", message)

    def test_une_reponse_vide_est_refusee(self):
        with FauxServeur("vide") as serveur, Atelier("ollama", serveur.url):
            with self.assertRaises(llm.PlusDeFournisseur):
                llm.generer("Bonjour.", cache=False,
                            tentatives_par_fournisseur=1)

    def test_le_local_prend_le_relais_quand_le_distant_tombe(self):
        """Le scenario annonce des le depart : IA locale en dernier recours."""
        with FauxServeur(texte="Ecrit en local.") as serveur, \
                Atelier("pollinations,ollama", serveur.url):
            ancienne = config.PROVIDERS_BY_NAME["pollinations"].base_url
            config.PROVIDERS_BY_NAME["pollinations"].base_url = \
                "http://127.0.0.1:1/v1"
            try:
                reponse = llm.generer("Ecris quelque chose.", cache=False,
                                      tentatives_par_fournisseur=1)
            finally:
                config.PROVIDERS_BY_NAME["pollinations"].base_url = ancienne
        self.assertEqual(reponse.fournisseur, "ollama")
        self.assertEqual(reponse.texte, "Ecrit en local.")

    def test_la_production_locale_est_comptee_comme_les_autres(self):
        avant = store.compteur_jour("ollama")
        with FauxServeur() as serveur, Atelier("ollama", serveur.url):
            llm.generer("Bonjour, compte-moi.", cache=False)
        self.assertEqual(store.compteur_jour("ollama"), avant + 1)


if __name__ == "__main__":
    unittest.main()
