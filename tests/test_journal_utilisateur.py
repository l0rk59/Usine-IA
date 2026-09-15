"""Trois defauts lus dans le journal d'une vraie fabrication.

Le 15/09/2026, une nouvelle de cinq scenes est sortie avec UNE scene ecrite
sur cinq et une note de 4,33. Le journal de cette fabrication disait tout ce
qu'il fallait, a condition de le lire dans le bon ordre — et les trois causes
etaient a deux etapes de l'endroit ou le defaut se voyait.

C'est la raison d'etre de ce module : garder ces trois-la, nommees par ce que
le journal montrait.
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
    atelier.isoler("journal_utilisateur")


from usine.core import config, llm, modeles  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402


class UneSubstitutionNeSeGardePasSurUnMensonge(unittest.TestCase):
    """« writer/palmyra-creative-122b » etait dans le catalogue de NVIDIA.

    Le journal disait « le modele n'existe plus chez nvidia » et l'usine est
    passee a « meta/muse-glimmer-30b ». Or le catalogue public de NVIDIA,
    relu le lendemain, servait bien ce modele — parmi 81. Le 404 disait donc
    autre chose : un palier qui n'y donne pas droit, une panne d'un instant,
    un routage interne.

    La substitution, elle, etait RETENUE — ecrite en base, valable pour
    toutes les sessions suivantes. Ce modele existe exactement pour ecrire de
    la fiction : toutes les nouvelles suivantes auraient ete ecrites par un
    modele plus petit, definitivement, sans que rien ne le dise.
    """

    CATALOGUE = ["writer/palmyra-creative-122b", "meta/muse-glimmer-30b",
                 "nvidia/nemotron-3-super-120b-a12b"]

    def setUp(self):
        modeles.oublier()
        self.vrai = modeles.interroger
        modeles.interroger = lambda f, timeout=10: list(self.CATALOGUE)
        self.addCleanup(lambda: setattr(modeles, "interroger", self.vrai))

    def test_un_modele_encore_liste_ne_fige_pas_la_substitution(self):
        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        refuse = "writer/palmyra-creative-122b"
        remplacant = modeles.substituer(fournisseur, "creatif", refuse)
        self.assertTrue(remplacant, "la fabrication en cours doit aboutir")
        self.assertNotEqual(remplacant, refuse)
        # Rien en base : la session suivante redemandera le modele configure.
        modeles.oublier_la_session()
        self.assertEqual(modeles.modele_effectif(fournisseur, "creatif"),
                         fournisseur.model_for("creatif"))

    def test_un_modele_vraiment_disparu_reste_remplace(self):
        """L'autre moitie : quand le catalogue ne le sert plus, la
        substitution doit survivre au redemarrage, sinon chaque lancement
        refait le meme 404 et la meme interrogation."""
        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        # Un catalogue qui ne sert PLUS le modele configure : sans cela,
        # « choisir » le reprenait, le remplacant valait le modele de depart,
        # et le cas ne distinguait plus rien.
        modeles.interroger = lambda f, timeout=10: [
            "meta/muse-glimmer-30b", "nvidia/nemotron-3-super-120b-a12b"]
        remplacant = modeles.substituer(fournisseur, "creatif",
                                        "writer/modele-retire-l-an-dernier")
        self.assertTrue(remplacant)
        # Sans cette ligne, le test passait des DEUX cotes de la mutation :
        # le remplacant choisi se trouvait etre le modele deja configure, et
        # l'egalite d'apres tenait sans qu'aucune substitution ne soit gardee.
        self.assertNotEqual(remplacant, fournisseur.model_for("creatif"),
                            "ce cas ne prouve rien si le remplacant est "
                            "deja le modele configure")
        modeles.oublier_la_session()
        self.assertEqual(modeles.modele_effectif(fournisseur, "creatif"),
                         remplacant)


class UnServiceRetireSeNommeAinsi(unittest.TestCase):
    """GitHub Models rendait « HTTP 410 : Gone ».

    Le corps disait « github_models_retirement_brownout » : le service est en
    cours de retrait. Le message brut donnait a chercher une cle ou un
    identifiant de modele, alors qu'il n'y avait rien a corriger.
    """

    def test_un_410_distant_dit_que_le_service_ferme(self):
        github = config.PROVIDERS_BY_NAME["github"]
        texte = llm._expliquer(github, HttpErreur(
            410, "Gone",
            corps='{"error":{"code":"github_models_retirement_brownout"}}'))
        self.assertIn("retire par son editeur", texte)
        self.assertIn("ni votre cle", texte)

    def test_un_410_sans_explication_suffit(self):
        """Tous les services retires ne le disent pas dans leur corps.

        Le premier cas de ce module portait « retirement » dans le corps, ce
        qui rattrapait la lecture du code : retirer la branche du 410 ne
        changeait rien, et la mutation l'a montre. Un « Gone » nu est la
        forme minimale, et c'est elle qu'il faut garder.
        """
        self.assertTrue(llm._service_ferme(HttpErreur(410, "Gone")))

    def test_un_service_retire_n_est_pas_un_modele_inconnu(self):
        """Les deux demandent des gestes opposes : corriger un identifiant,
        ou cesser de compter sur le service."""
        exc = HttpErreur(410, "Gone", corps="retirement brownout")
        self.assertTrue(llm._service_ferme(exc))
        self.assertFalse(llm._modele_inconnu(exc))

    def test_une_panne_ordinaire_n_est_pas_un_retrait(self):
        """Sinon l'usine dirait « ce service ferme » a chaque 503."""
        for statut in (500, 502, 503, 429, 404):
            self.assertFalse(
                llm._service_ferme(HttpErreur(statut, "panne")),
                "un {} ne doit pas passer pour un retrait".format(statut))


class UneGrilleCoupeeEstRedemandee(unittest.TestCase):
    """Cinq scenes, 2250 jetons accordes, reponse coupee.

    Le JSON tronque se relit en partie, donc rien n'echouait : la grille
    perdait ses derniers beats, et le controle de continuite signalait deux
    etapes plus loin « aucune scene ne livre le beat resolution ». La cause
    etait loin de l'endroit ou le defaut se voyait.
    """

    def test_le_plancher_couvre_le_cas_qui_a_echoue(self):
        from usine.pipelines import nouvelle

        source = (RACINE / "usine" / "pipelines" / "nouvelle.py").read_text(
            encoding="utf-8")
        self.assertIn("2600 + total * 150", source,
                      "le plancher est revenu sous le cas mesure")
        # Cinq scenes : 3350 jetons, la ou 2250 avait ete coupe.
        self.assertGreater(2600 + 5 * 150, 2250)
        self.assertTrue(hasattr(nouvelle, "_grille_ou_retente"))

    def test_une_grille_coupee_est_redemandee_plus_grande(self):
        """Un chiffre choisi a la main finit toujours par etre trop petit
        pour un cas qu'on n'avait pas vu. Le routeur MESURE deja la coupe."""
        from usine.pipelines import nouvelle

        class FauxContexte:
            def __init__(self):
                self.meta = {}
                self.lignes = []

            def journal(self, message):
                self.lignes.append(message)

        ctx = FauxContexte()
        budgets = []

        def repondre(_contexte, _invite, max_tokens=0, **_reste):
            budgets.append(max_tokens)
            if len(budgets) == 1:
                # Le routeur note la coupe comme il le fait en vrai.
                ctx.meta.setdefault("tronquees", []).append({"agent": "architecte"})
                return {"scenes": [{"titre": "coupee"}]}
            return {"scenes": [{"titre": "a"}, {"titre": "b"}], "beats": [1]}

        with mock.patch.object(nouvelle.equipe.ARCHITECTE, "travailler_json",
                               side_effect=repondre):
            grille = nouvelle._grille_ou_retente(ctx, "invite", 2250)
        self.assertEqual(budgets, [2250, 4500], "la relance doit doubler")
        self.assertEqual(len(grille["scenes"]), 2, "la seconde grille gagne")
        self.assertTrue(any("redemande" in l for l in ctx.lignes),
                        "la relance doit se dire dans le journal")

    def test_une_grille_entiere_ne_coute_pas_un_second_appel(self):
        from usine.pipelines import nouvelle

        class FauxContexte:
            meta = {}

            def journal(self, message):
                pass

        appels = []

        def repondre(_contexte, _invite, max_tokens=0, **_reste):
            appels.append(max_tokens)
            return {"scenes": [{"titre": "a"}]}

        with mock.patch.object(nouvelle.equipe.ARCHITECTE, "travailler_json",
                               side_effect=repondre):
            nouvelle._grille_ou_retente(FauxContexte(), "invite", 3350)
        self.assertEqual(appels, [3350], "un seul appel quand rien n'est coupe")


if __name__ == "__main__":
    unittest.main()
