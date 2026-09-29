"""Le catalogue des fournisseurs, confronte a ce qu'ils servent vraiment.

Releve du 23/09/2026, croise sur trois sources :

  - GitHub Models a FERME (HTTP 410). Journal d'un utilisateur le 15/09 puis
    le 16/09 ; releve externe du 11/09 ; message du depot lui-meme, qui
    conseillait deja de le retirer. Il etait pourtant interroge a chaque
    bascule, sur chaque scene.
  - Cerebras n'est PLUS GRATUIT : essai de 5 $ avec carte, et une cle sans
    credit repond 402. Il etait annonce « tres rapide, quota genereux ».
  - Cloudflare Workers AI est gratuit SANS carte — 10 000 neurones par jour,
    environ trente appels a gpt-oss-120b — et il manquait.

Et un defaut que le retrait a lui-meme provoque : l'ordre de bascule par
defaut gardait le nom « github », et « active_providers » levait KeyError. Plus
aucune fabrication ne demarrait. Retirer un fournisseur ferme ne doit jamais
couter la production entiere.
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
    atelier.isoler("fournisseurs-a-jour")


from usine.core import config, store  # noqa: E402


class RetirerUnFournisseurNeFaitPasTomberLUsine(unittest.TestCase):

    def test_un_nom_de_l_ordre_qui_n_est_plus_declare_est_ignore(self):
        config.DEFAULT_ORDER.insert(0, "fournisseur-disparu")
        try:
            ordre = config.provider_order()
            actifs = config.active_providers(include_unavailable=True)
        finally:
            config.DEFAULT_ORDER.remove("fournisseur-disparu")
        self.assertNotIn("fournisseur-disparu", ordre)
        self.assertTrue(actifs, "plus aucun fournisseur : l'usine ne demarre pas")

    def test_chaque_nom_de_l_ordre_par_defaut_est_declare(self):
        """Le filtre protege l'utilisateur ; ce test protege la liste. Sans
        lui, un nom mort pourrait y rester indefiniment sans que rien ne le
        signale — ignore en silence, c'est-a-dire oublie."""
        inconnus = [n for n in config.DEFAULT_ORDER
                    if n not in config.PROVIDERS_BY_NAME]
        self.assertEqual(inconnus, [], (
            "l'ordre par defaut cite des fournisseurs qui n'existent plus : {}"
            .format(inconnus)))


class CloudflareDemandeSesDeuxValeurs(unittest.TestCase):
    """L'identifiant de compte est DANS l'URL. Avec la cle seule, chaque appel
    serait parti vers une adresse fausse, et le routeur l'aurait mis au repos
    comme une panne au lieu de dire qu'il manque un reglage."""

    def setUp(self):
        self.avant = {k: os.environ.get(k) for k in
                      ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")}

    def tearDown(self):
        for cle, valeur in self.avant.items():
            if valeur is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = valeur

    def test_la_cle_seule_ne_suffit_pas(self):
        os.environ["CLOUDFLARE_API_TOKEN"] = "jeton-de-test"
        os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
        cloudflare = config.PROVIDERS_BY_NAME["cloudflare"]
        self.assertFalse(cloudflare.available(), (
            "Cloudflare se dit disponible sans identifiant de compte"))

    def test_les_deux_valeurs_le_rendent_disponible(self):
        """Le pendant : sans lui, refuser toujours passerait le test
        precedent."""
        os.environ["CLOUDFLARE_API_TOKEN"] = "jeton-de-test"
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = "compte-de-test"
        self.assertTrue(config.PROVIDERS_BY_NAME["cloudflare"].available())

    def test_les_modeles_sont_ceux_releves_sur_la_documentation(self):
        modeles = config.PROVIDERS_BY_NAME["cloudflare"].models
        self.assertEqual(modeles["standard"], "@cf/openai/gpt-oss-120b")
        self.assertEqual(modeles["rapide"], "@cf/openai/gpt-oss-20b")

    def test_les_deux_variables_sont_dans_le_modele_de_env(self):
        modele = (RACINE / ".env.exemple").read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_API_TOKEN=", modele)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID=", modele)


class CeQuiNEstPlusGratuitNeSeDitPlusGratuit(unittest.TestCase):

    def test_cerebras_annonce_la_carte(self):
        cerebras = config.PROVIDERS_BY_NAME["cerebras"]
        texte = (cerebras.notes + " " + cerebras.signup).lower()
        self.assertIn("payant", texte)
        self.assertIn("carte", texte)

    def test_cerebras_passe_apres_les_gratuits(self):
        """Une cle creditee coute : elle ne doit servir qu'une fois les
        paliers gratuits epuises."""
        ordre = config.provider_order()
        for gratuit in ("groq", "gemini", "cloudflare"):
            with self.subTest(gratuit=gratuit):
                self.assertLess(ordre.index(gratuit), ordre.index("cerebras"))

    def test_le_service_ferme_n_est_plus_au_catalogue(self):
        self.assertNotIn("github", config.PROVIDERS_BY_NAME)
        self.assertNotIn("GITHUB_MODELS_TOKEN", (
            RACINE / ".env.exemple").read_text(encoding="utf-8"))


class LeJourDuFournisseurEstEnTempsUniversel(unittest.TestCase):
    """« All limits reset daily at 00:00 UTC » (Cloudflare). Compte en heure
    locale, le quota de l'usine repartait a zero deux heures avant celui du
    service, pour quelqu'un en France l'ete."""

    def test_le_jour_est_celui_du_temps_universel(self):
        """Le fuseau est FORCE a Paris. Dans un conteneur regle sur UTC,
        heure locale et temps universel coincident, et le test passerait avec
        ou sans la correction — un test qui ne distingue rien ne garde rien."""
        avant = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Paris"
        time.tzset()
        try:
            # 22 h 30 UTC le 22 septembre = 0 h 30 le 23 a Paris (UTC+2).
            instant = 1790116200.0
            self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(instant)),
                             "2026-09-23", "le test ne se place pas ou il croit")
            self.assertEqual(store._jour(instant), "2026-09-22", (
                "le jour du fournisseur suit l'heure de Paris : le quota "
                "repart a zero deux heures avant le service"))
        finally:
            if avant is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = avant
            time.tzset()

    def test_le_budget_de_l_utilisateur_reste_local(self):
        """L'autre journee : celle que l'utilisateur se fixe. Elle ne doit
        pas bouger — c'est son jour a lui, pas celui du service."""
        source = (RACINE / "usine/core/budget.py").read_text(encoding="utf-8")
        self.assertNotIn("gmtime", source)
        self.assertNotIn("_jour(", source)


if __name__ == "__main__":
    unittest.main()
