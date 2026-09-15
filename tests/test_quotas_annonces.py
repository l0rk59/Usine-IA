"""Les quotas ecrits, confrontes a ceux que le service annonce.

« config.py » le dit de lui-meme : fournisseurs, modeles, quotas — donnees
recopiees, donc perissables. Les modeles savent desormais se verifier ; les
quotas, non. Ils sont recopies d'une page de documentation, et rien ne les
avait jamais confrontes a quoi que ce soit.

Or la plupart des services les annoncent dans les en-tetes de CHAQUE reponse.
Un appel minimal par fournisseur suffit — pas un par modele, puisque ces
limites valent pour le compte.

Ce que ce module garde, c'est surtout ce que l'audit doit REFUSER de dire :
deviner une fenetre qu'il ne connait pas, et prendre un silence pour un
accord.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("quotas_annonces")


from usine.core import config, diagnostic  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402


class LireLaFenetreDansLaRemiseAZero(unittest.TestCase):
    """Une limite de mille ne veut rien dire sans sa fenetre.

    Aucun en-tete ne dit « par jour » : c'est le temps de remise a zero qui
    le dit. Comparer un chiffre a « rpm » plutot qu'a « rpd » se trompe d'un
    facteur mille quatre cent quarante.
    """

    def test_les_formes_connues_se_lisent(self):
        for brut, attendu in (("7.2s", 7.2), ("60", 60.0), ("2m", 120.0),
                              ("1m30s", 90.0), ("23h14m56s", 83696.0),
                              ("500ms", 0.5)):
            self.assertAlmostEqual(diagnostic._secondes(brut), attendu, places=2,
                                   msg=brut)

    def test_ce_qui_ne_se_lit_pas_rend_rien(self):
        for brut in ("", "bientot", None):
            self.assertIsNone(diagnostic._secondes(brut))

    def test_la_minute_et_le_jour_se_distinguent(self):
        self.assertEqual(diagnostic._fenetre(7.2), "minute")
        self.assertEqual(diagnostic._fenetre(60.0), "minute")
        self.assertEqual(diagnostic._fenetre(83696.0), "jour")

    def test_l_entre_deux_ne_se_tranche_pas(self):
        """Quinze minutes n'est ni une minute ni un jour.

        Trancher au hasard donnerait un « different » ou un « accorde » tire
        a pile ou face, sur un chiffre que personne n'irait reverifier. Un
        quota compare a la mauvaise fenetre est pire qu'un quota non verifie.
        """
        self.assertEqual(diagnostic._fenetre(900.0), "")
        self.assertEqual(diagnostic._fenetre(None), "")


class LesTroisVerdicts(unittest.TestCase):

    def _auditer(self, entetes, fournisseur="mistral"):
        p = config.PROVIDERS_BY_NAME[fournisseur]

        def essai(prov, modele, timeout=30, entetes_vus=None):
            if entetes_vus is not None:
                entetes_vus.update(entetes)
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            return diagnostic.auditer_quotas()["lignes"][0]

    def test_un_chiffre_conforme_est_accorde(self):
        p = config.PROVIDERS_BY_NAME["mistral"]
        ligne = self._auditer({
            "x-ratelimit-limit-requests": str(p.quota("standard").rpd),
            "x-ratelimit-reset-requests": "20h",
        })
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["verdict"], "accorde")
        self.assertEqual(requetes["fenetre"], "jour")

    def test_un_chiffre_different_est_signale(self):
        """C'est le service qui a raison : c'est lui qui applique."""
        ligne = self._auditer({
            "x-ratelimit-limit-requests": "7",
            "x-ratelimit-reset-requests": "30s",
        })
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["verdict"], "different")
        self.assertEqual(requetes["annonce"], 7)

    def test_un_silence_n_est_pas_un_accord(self):
        """« Non publie » veut dire « on ne sait pas ».

        Le confondre avec « conforme » ferait passer un quota jamais verifie
        pour un quota verifie — la meme fausse assurance que ce depot
        supprime partout ailleurs.
        """
        ligne = self._auditer({})
        for mesure in ligne["mesures"]:
            self.assertEqual(mesure["verdict"], "non publie")
            self.assertNotIn("annonce", mesure)

    def test_une_fenetre_illisible_ne_devient_pas_un_verdict(self):
        ligne = self._auditer({"x-ratelimit-limit-requests": "1000"})
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["verdict"], "fenetre inconnue")

    def test_ce_qu_on_ne_sait_pas_lire_est_rendu_tel_quel(self):
        """Ce qu'on ne comprend pas aujourd'hui se lit a l'oeil, et se code
        demain. Le jeter garantirait de ne jamais l'apprendre."""
        ligne = self._auditer({"x-ratelimit-limit-audio-seconds": "3600"})
        self.assertIn("x-ratelimit-limit-audio-seconds", ligne["inconnus"])

    def test_les_jetons_se_mesurent_aussi(self):
        p = config.PROVIDERS_BY_NAME["mistral"]
        ligne = self._auditer({
            "x-ratelimit-limit-tokens": str(p.quota("standard").tpm or 1),
            "x-ratelimit-reset-tokens": "45s",
        })
        jetons = next(m for m in ligne["mesures"] if m["genre"] == "jetons")
        self.assertEqual(jetons["fenetre"], "minute")
        self.assertIn(jetons["verdict"], ("accorde", "different"))


class UnRefusPorteLesEntetes(unittest.TestCase):
    """Un 429 porte justement les en-tetes les plus interessants.

    Les jeter au motif que l'appel a echoue reviendrait a ne jamais pouvoir
    verifier un quota au moment precis ou il est atteint.
    """

    def test_un_429_livre_quand_meme_ses_chiffres(self):
        p = config.PROVIDERS_BY_NAME["mistral"]

        def essai(prov, modele, timeout=30, entetes_vus=None):
            raise HttpErreur(429, "Too Many Requests", entetes={
                "x-ratelimit-limit-requests": "500",
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "12h",
            })

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["annonce"], 500)
        self.assertEqual(requetes["reste"], 0)
        self.assertEqual(requetes["consomme_service"], 500)


if __name__ == "__main__":
    unittest.main()
