"""Le message qu'on lit quand aucun fournisseur n'a repondu.

Mesure du 24/09/2026, huit fournisseurs actifs, chacun en panne a sa facon. Le
message gardait les DIX DERNIERES lignes d'une liste qui en avait onze — une
par essai. Groq, le premier essaye, avait disparu ; trois fournisseurs
apparaissaient deux fois ; « cerebras : en repos » ne disait ni jusqu'a quand
ni pourquoi ; une cle refusee se lisait « HTTP 401 : Unauthorized » ; les
fournisseurs sans cle n'etaient nommes nulle part.

AUCUN test de ce module ne sort sur le reseau : chaque panne est injectee.
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


def setUpModule():
    atelier.isoler("message-fournisseurs")


from usine.core import cles as pool_cles  # noqa: E402
from usine.core import config, http, llm  # noqa: E402

CLES = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY"}


class _Cas(unittest.TestCase):

    def setUp(self):
        atelier.isoler("message-fournisseurs-{}".format(
            self.id().rsplit(".", 1)[-1]))
        self._ordre, self._appel = config.provider_order, llm._appel
        self._patienter, self._quota = llm._patienter, llm._quota_ok
        llm._patienter = lambda secondes: None
        for variable in CLES.values():
            os.environ[variable] = "cle-de-test-" + "q" * 40
        pool_cles.oublier()
        llm._REPOS.clear()

    def tearDown(self):
        config.provider_order, llm._appel = self._ordre, self._appel
        llm._patienter, llm._quota_ok = self._patienter, self._quota
        for variable in CLES.values():
            os.environ.pop(variable, None)
        pool_cles.oublier()
        llm._REPOS.clear()

    def _message(self, ordre, pannes, tentatives=2):
        config.provider_order = lambda: list(ordre)

        def appel(p, *a, **k):
            raise pannes[p.name]

        llm._appel = appel
        with self.assertRaises(llm.PlusDeFournisseur) as echec:
            llm.generer("une question", cache=False,
                        tentatives_par_fournisseur=tentatives)
        return str(echec.exception)


class ChaqueFournisseurUneFois(_Cas):

    def test_le_premier_essaye_n_est_plus_coupe(self):
        """Le defaut mesure : une ligne par essai, les dix dernieres gardees.
        Trois fournisseurs a six essais font dix-huit lignes — assez pour que
        le premier tombe hors du message, comme groq le 24/09/2026."""
        message = self._message(
            ["groq", "gemini", "mistral"],
            {"groq": http.HttpErreur(500, "erreur a"),
             "gemini": http.HttpErreur(500, "erreur b"),
             "mistral": http.HttpErreur(500, "erreur c")}, tentatives=6)
        for nom in ("groq", "gemini", "mistral"):
            self.assertIn("- {} :".format(nom), message)

    def test_deux_essais_font_une_ligne(self):
        message = self._message(["mistral"],
                                {"mistral": http.HttpErreur(503, "indisponible")})
        self.assertEqual(message.count("- mistral :"), 1)
        self.assertIn("(2 essais)", message)
        # Et l'explication une seule fois dans la ligne, pas recopiee par essai.
        self.assertEqual(message.count("indisponible"), 1)

    def test_une_cle_refusee_dit_quelle_variable_verifier(self):
        message = self._message(["gemini"],
                                {"gemini": http.HttpErreur(401, "Unauthorized")})
        self.assertIn("cle refusee", message)
        self.assertIn("GEMINI_API_KEY", message)

    def test_un_repos_dit_jusqu_a_quand_et_pourquoi(self):
        llm._reposer("groq", 600, "limite de debit")
        message = self._message(["groq", "mistral"],
                                {"mistral": http.HttpErreur(500, "erreur")})
        self.assertIn("Pas essayes", message)
        self.assertIn("groq : au repos jusqu'a {} (limite de debit)".format(
            time.strftime("%H:%M", time.localtime(llm._REPOS["groq"]))), message)

    def test_un_quota_du_jour_dit_quand_il_repart(self):
        llm._quota_ok = lambda p, role="standard", cle_id="": p.name != "groq"
        message = self._message(["groq", "mistral"],
                                {"mistral": http.HttpErreur(500, "erreur")})
        self.assertIn("groq : quota du jour atteint — il repart a", message)
        self.assertIn("(minuit UTC)", message)

    def test_les_fournisseurs_sans_cle_sont_nommes(self):
        os.environ.pop("MISTRAL_API_KEY", None)
        pool_cles.oublier()
        message = self._message(["groq", "mistral"],
                                {"groq": http.HttpErreur(500, "erreur")})
        self.assertIn("Sans cle : mistral", message)
        self.assertNotIn("- mistral :", message)

    def test_aucune_cle_n_apparait_dans_le_message(self):
        """L'ancien message affichait la cle masquee de chaque essai ; ce
        n'est pas elle qu'on cherche quand plus rien ne repond."""
        message = self._message(["gemini"],
                                {"gemini": http.HttpErreur(500, "erreur")})
        self.assertNotIn("cle-de", message)
        self.assertNotIn("***", message)


class LePremierRetour(_Cas):

    def test_tous_au_repos_le_premier_retour_est_annonce(self):
        message = self._message(
            ["groq", "gemini"],
            {"groq": http.HttpErreur(429, "Too Many Requests",
                                     entetes={"Retry-After": "300"}),
             "gemini": http.HttpErreur(429, "Too Many Requests",
                                       entetes={"Retry-After": "900"})})
        premier = min(c.repos_jusqu_a for nom in ("groq", "gemini")
                      for c in pool_cles.pool(nom, CLES[nom]).cles)
        self.assertIn("Le premier devrait rouvrir vers {}.".format(
            time.strftime("%H:%M", time.localtime(premier))), message)

    def test_une_panne_passagere_n_annonce_pas_d_heure(self):
        """Un 503 laisse le fournisseur ouvert : annoncer une heure de retour
        serait l'inventer."""
        message = self._message(
            ["groq", "mistral"],
            {"groq": http.HttpErreur(429, "Too Many Requests"),
             "mistral": http.HttpErreur(503, "indisponible")})
        self.assertNotIn("devrait rouvrir", message)


if __name__ == "__main__":
    unittest.main()
