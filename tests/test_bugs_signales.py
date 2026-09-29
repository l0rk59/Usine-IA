"""Deux defauts signales par l'utilisateur le 14/09/2026.

Ils n'ont rien de spectaculaire, et c'est exactement pour cela qu'ils ont
dure : dans les deux cas l'usine faisait quelque chose de raisonnable, le
disait, et continuait quand meme.

**« Je ne vois pas opencode dans mon .env. »** « install.sh » ne cree « .env »
que s'il n'existe pas, et « usine maj » ne le touche jamais — a raison, il
contient les cles. Donc tout fournisseur ajoute APRES la premiere installation
n'apparait jamais chez quelqu'un qui a deja installe. Il ouvre « nano .env »,
ne voit pas la variable, et en conclut que l'integration n'existe pas.

**« La recherche de niche ne fonctionne pas. »** Sans fournisseur joignable,
l'usine annoncait « aucune niche a proposer »... puis CONTINUAIT avec un sujet
vide : sondage de marche pour «  », veille pour «  », quatre appels reseau, et
une mort une minute plus tard sur un message sans rapport.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, maj  # noqa: E402


def setUpModule():
    atelier.isoler("bugs-signales")


class LeEnvSeCompleteSansJamaisSeReecrire(unittest.TestCase):

    def _atelier(self, contenu):
        import tempfile

        dossier = Path(tempfile.mkdtemp())
        (dossier / ".env").write_text(contenu, encoding="utf-8")
        return dossier

    def test_un_fournisseur_ajoute_apres_l_installation_est_ajoute(self):
        dossier = self._atelier("GROQ_API_KEY=gsk_secrete\n")
        manquantes = maj.variables_manquantes(dossier)
        self.assertIn("OPENCODE_API_KEY", manquantes,
                      "le .env ancien ne manque de rien : le test ne mesure "
                      "plus le defaut")
        ajoutees = maj.completer_env(dossier)
        self.assertEqual(sorted(ajoutees), sorted(manquantes))
        self.assertIn("OPENCODE_API_KEY",
                      (dossier / ".env").read_text(encoding="utf-8"))

    def test_une_cle_deja_collee_n_est_jamais_touchee(self):
        """Le fichier contient des cles. Un outil qui les reecrit est un outil
        qu'on n'ose plus lancer."""
        dossier = self._atelier("GROQ_API_KEY=gsk_a_ne_pas_perdre\n"
                                "NVIDIA_API_KEY=nvapi_aussi\n")
        maj.completer_env(dossier)
        apres = (dossier / ".env").read_text(encoding="utf-8")
        self.assertIn("GROQ_API_KEY=gsk_a_ne_pas_perdre", apres)
        self.assertIn("NVIDIA_API_KEY=nvapi_aussi", apres)

    def test_completer_deux_fois_n_ajoute_rien_la_seconde(self):
        """« usine maj » tourne a chaque mise a jour : sans cela le fichier
        grossirait d'un bloc identique a chaque fois."""
        dossier = self._atelier("GROQ_API_KEY=gsk_secrete\n")
        premier = maj.completer_env(dossier)
        self.assertTrue(premier)
        self.assertEqual(maj.completer_env(dossier), [])

    def test_une_variable_commentee_compte_comme_vue(self):
        """L'utilisateur l'a lue et a choisi de ne pas s'en servir. La lui
        remettre a chaque mise a jour serait du harcelement."""
        dossier = self._atelier("GROQ_API_KEY=gsk\n# OPENCODE_API_KEY=\n")
        self.assertNotIn("OPENCODE_API_KEY", maj.variables_manquantes(dossier))

    def test_chaque_fournisseur_distant_est_couvert(self):
        """C'est le catalogue qui fait foi, pas « .env.exemple » : le modele
        lui-meme pourrait avoir du retard."""
        dossier = self._atelier("")
        attendues = {p.api_key_env for p in config.PROVIDERS
                     if p.api_key_env and not p.local}
        self.assertEqual(set(maj.variables_manquantes(dossier)), attendues)


class LaMiseAJourCompleteVraimentLeEnv(unittest.TestCase):
    """La fonction peut etre juste et n'etre appelee par personne.

    Une premiere version des controles ci-dessus appelait « completer_env »
    directement : ils passaient tous, et retirer l'appel de « usine maj »
    ne changeait rien. Un test qui court-circuite le chemin reel ne garde que
    la fonction, pas la fonctionnalite.
    """

    def test_usine_maj_complete_le_env(self):
        import tempfile

        from usine import cli
        from usine.core import maj as module_maj

        dossier = Path(tempfile.mkdtemp())
        (dossier / ".env").write_text("GROQ_API_KEY=gsk_secrete\n",
                                      encoding="utf-8")
        vrais = (module_maj.racine, module_maj.est_un_clone,
                 module_maj.git_disponible, module_maj.par_git,
                 module_maj.verifier, module_maj.modifications_locales)
        module_maj.racine = lambda: dossier
        module_maj.est_un_clone = lambda *a, **k: True
        module_maj.git_disponible = lambda: True
        module_maj.modifications_locales = lambda *a, **k: []
        module_maj.par_git = lambda *a, **k: {
            "ok": True, "change": True, "avant": "aaa", "apres": "bbb",
            "journal": "", "branche": "main"}
        module_maj.verifier = lambda *a, **k: {"ok": True, "version": "1.0.0"}
        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                code = cli.principal(["maj"])
        finally:
            (module_maj.racine, module_maj.est_un_clone,
             module_maj.git_disponible, module_maj.par_git,
             module_maj.verifier, module_maj.modifications_locales) = vrais

        self.assertEqual(code, 0)
        apres = (dossier / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENCODE_API_KEY", apres,
                      "« usine maj » n'ajoute pas les fournisseurs apparus "
                      "depuis l'installation")
        self.assertIn("GROQ_API_KEY=gsk_secrete", apres)
        self.assertIn("OPENCODE_API_KEY", sortie.getvalue(),
                      "l'ajout est fait mais rien ne le dit a l'ecran")


class SansNicheLaCommandeSArrete(unittest.TestCase):

    def test_un_sujet_introuvable_leve_plutot_que_de_rendre_le_vide(self):
        """Rendre "" laissait la chaine partir sur un sujet vide. Quatorze
        appels a « contexte_depuis » auraient chacun du y penser ; une
        exception les arrete tous d'un coup."""
        from usine import cli
        from usine.pipelines import catalogue

        args = cli.construire_parseur().parse_args(["ebook"])

        def rien_du_tout(journal=None, type_produit="ebook"):
            if journal:
                journal("rien a proposer")
            return {"sujet": "", "type": type_produit, "source": ""}

        from usine import production

        vrai = production.choisir_une_niche
        production.choisir_une_niche = rien_du_tout
        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                with self.assertRaises(cli.SujetIntrouvable):
                    cli.contexte_depuis(args)
        finally:
            production.choisir_une_niche = vrai
        self.assertTrue(catalogue.tous())

    def test_la_commande_rend_un_code_d_erreur_et_dit_quoi_faire(self):
        from usine import cli
        from usine import production

        def rien_du_tout(journal=None, type_produit="ebook"):
            return {"sujet": "", "type": type_produit, "source": ""}

        vrai = production.choisir_une_niche
        production.choisir_une_niche = rien_du_tout
        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                code = cli.principal(["ebook", "--sans-image", "-q", "rapide"])
        finally:
            production.choisir_une_niche = vrai
        texte = sortie.getvalue()
        self.assertEqual(code, 3)
        self.assertIn("devait choisir une niche", texte)
        self.assertIn("votre sujet", texte,
                      "l'usine ne dit pas comment s'en sortir")

    def test_elle_ne_sonde_aucun_marche_pour_un_sujet_vide(self):
        """Le symptome que l'utilisateur a vu : quatre appels reseau APRES
        avoir annonce qu'elle s'arretait."""
        from usine import cli, production
        from usine.core import marche

        sondages = []

        def sonder_espion(sujet, **_kw):
            sondages.append(sujet)
            return {"sujet": sujet, "date": "", "sources": {},
                    "sources_disponibles": [], "sources_indisponibles": [],
                    "lecture": {}}

        def rien_du_tout(journal=None, type_produit="ebook"):
            return {"sujet": "", "type": type_produit, "source": ""}

        vrais = production.choisir_une_niche, marche.sonder
        production.choisir_une_niche = rien_du_tout
        marche.sonder = sonder_espion
        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["idees"])
        finally:
            production.choisir_une_niche, marche.sonder = vrais
        self.assertEqual(sondages, [],
                         "l'usine sonde encore un marche pour un sujet vide")


if __name__ == "__main__":
    unittest.main()
