"""La prospection doit rendre autre chose que la fois d'avant.

Defaut mesure le 15/09/2026, sur un vrai telephone : « 8 piste(s) explorees,
0 mise(s) en file », a chaque lancement, indefiniment.

La cause n'etait ni le dedoublonnage ni le modele. Le cache des reponses est
indexe sur l'invite ; l'invite ne dependait que de la graine ; la graine ne
changeait pas. Trois prospections de suite ne faisaient donc qu'UN appel au
modele et rendaient trois fois la meme liste — deja mise en file au premier
tour, donc rejetee aux suivants.

C'est le piege que « CLAUDE.md » nomme pour les tests (« deux cas qui
partagent une invite partagent une entree de cache »), applique ici a la
production elle-meme.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


_SANS_RESEAU = None


def setUpModule():
    """Aucun test ne sort sur le reseau — y compris celui-ci.

    « prospecter » appelle « idees.produire(avec_marche=True) », qui interroge
    quatre services publics (Hacker News, Wikipedia, Stack Exchange, Open
    Library). Ce module les appelait donc pour de vrai, et cela s'est vu de
    la pire facon : le test qui compare deux invites a echoue dans la suite
    complete parce que la mesure de marche disait « 3/4 sources » au premier
    passage et « 4/4 » au second. Un service lent, et le test devenait faux
    sur un defaut qui n'existait pas.

    Un test qui depend du reseau ne mesure pas ce qu'il croit mesurer : il
    mesure aussi la meteo du jour chez quatre inconnus.
    """
    global _SANS_RESEAU
    atelier.isoler("prospection_neuve")
    _SANS_RESEAU = mock.patch.object(
        marche, "sonder",
        side_effect=OSError("reseau coupe : aucun test ne sort d'ici"))
    _SANS_RESEAU.start()


def tearDownModule():
    if _SANS_RESEAU is not None:
        _SANS_RESEAU.stop()


from usine import production  # noqa: E402
from usine.core import file, llm, marche, store  # noqa: E402
from usine.pipelines import idees  # noqa: E402


def _lot(prefixe, combien=8):
    return json.dumps({"idees": [
        {"titre": "{} {}".format(prefixe, i), "type": "ebook",
         "probleme": "p", "acheteur": "a", "promesse": "pr", "prix_eur": 19,
         "difficulte": "facile", "concurrence": "faible",
         "angle_differenciant": "x", "premier_canal": "y"}
        for i in range(1, combien + 1)]})


class DeuxProspectionsNeSontPasUnSeulAppel(unittest.TestCase):

    def tearDown(self):
        llm.definir_simulateur(None)
        file.vider(tout=True)

    def test_trois_prospections_font_trois_appels(self):
        """Le coeur du defaut : elles n'en faisaient qu'un."""
        appels = []

        def simulateur(messages, role):
            appels.append(messages)
            return _lot("Piste tour {}".format(len(appels)))

        llm.definir_simulateur(simulateur)
        for _ in range(3):
            production.prospecter(nombre=8, graine="jardinage urbain",
                                  journal=lambda m: None, avec_veille=False)
        self.assertEqual(len(appels), 3,
                         "le cache a reservi la premiere exploration")

    def test_deux_appels_meme_quand_l_atelier_n_a_PAS_change(self):
        """Le cas que l'autre moitie de la correction ne couvre pas.

        Injecter dans l'invite ce qui existe deja suffit a faire changer la
        cle de cache — tant que l'atelier change. Quand il ne change pas
        (toutes les pistes recouvrent un produit fabrique, donc aucune n'est
        retenue), l'invite est identique au mot pres, et seul le refus
        explicite du cache fait repartir l'exploration.

        Sans ce cas, une campagne de mutation a montre que retirer le refus
        du cache ne faisait echouer aucun test : les deux moities de la
        correction se recouvraient, et l'une cachait la perte de l'autre.
        """
        store.enregistrer_empreinte("p9", "ebook", "Deja fait",
                                    "Piste bloquee 1", "sig", "plan", 900)
        appels = []

        def simulateur(messages, role):
            appels.append(messages)
            return _lot("Piste bloquee", combien=1)

        llm.definir_simulateur(simulateur)
        premier = production.prospecter(nombre=1, graine="jardinage urbain",
                                        journal=lambda m: None,
                                        avec_veille=False)
        second = production.prospecter(nombre=1, graine="jardinage urbain",
                                       journal=lambda m: None,
                                       avec_veille=False)
        self.assertEqual(premier["ajoutees"], 0)
        self.assertEqual(second["ajoutees"], 0)
        self.assertEqual(appels[0][-1]["content"], appels[1][-1]["content"],
                         "l'atelier n'a pas change : l'invite doit etre la "
                         "meme, sinon ce test ne mesure pas le cache")
        self.assertEqual(len(appels), 2,
                         "a invite identique, le cache a reservi la premiere "
                         "exploration")

    def test_une_seconde_prospection_met_des_niches_en_file(self):
        """Ce que l'utilisateur voyait : jamais rien de neuf."""
        appels = []

        def simulateur(messages, role):
            appels.append(messages)
            return _lot("Piste tour {}".format(len(appels)))

        llm.definir_simulateur(simulateur)
        premier = production.prospecter(nombre=8, graine="jardinage urbain",
                                        journal=lambda m: None,
                                        avec_veille=False)
        second = production.prospecter(nombre=8, graine="jardinage urbain",
                                       journal=lambda m: None,
                                       avec_veille=False)
        self.assertEqual(premier["ajoutees"], 8)
        self.assertEqual(second["ajoutees"], 8)


class LeModeleSaitCeQuiExisteDeja(unittest.TestCase):
    """Le filtrage d'apres coup ne suffit pas : il jette huit propositions sur
    huit sans jamais apprendre au modele pourquoi."""

    def tearDown(self):
        llm.definir_simulateur(None)
        file.vider(tout=True)

    def test_l_invite_porte_ce_qui_est_deja_en_file(self):
        file.ajouter("Composter sans jardin", "ebook", priorite=5)
        vues = []

        def simulateur(messages, role):
            vues.append(messages[-1]["content"])
            return _lot("Neuf")

        llm.definir_simulateur(simulateur)
        production.prospecter(nombre=8, graine="jardinage urbain",
                              journal=lambda m: None, avec_veille=False)
        self.assertIn("Composter sans jardin", vues[0])
        # La liste seule ne dit rien : sans consigne, un modele peut tres
        # bien la lire comme des exemples a imiter.
        self.assertIn("ne propose rien qui recouvre", vues[0])

    def test_l_invite_porte_ce_qui_est_deja_fabrique(self):
        store.enregistrer_empreinte("p1", "ebook", "Titre du produit",
                                    "Arroser pendant les vacances",
                                    "sig", "plan", 1200)
        self.assertIn("Arroser pendant les vacances", idees.deja_connu())

    def test_l_invite_change_quand_l_atelier_change(self):
        """C'est ce qui rend la cle de cache differente sans la truquer : la
        QUESTION a change, parce que l'atelier a change."""
        avant = idees.deja_connu()
        file.ajouter("Une niche toute neuve", "ebook", priorite=5)
        self.assertNotEqual(avant, idees.deja_connu())


class DejaEnFileNEstPasDejaFabrique(unittest.TestCase):
    """Deux refus differents, et les confondre envoie sur une fausse piste.

    Le rapport disait « toutes recouvrent un produit deja fabrique » alors
    que l'atelier etait vide : les pistes etaient simplement celles du tour
    d'avant, encore en attente. On cherchait un defaut de dedoublonnage la ou
    il n'y en avait pas.
    """

    def tearDown(self):
        llm.definir_simulateur(None)
        file.vider(tout=True)

    def test_une_piste_deja_en_file_est_comptee_a_part(self):
        llm.definir_simulateur(lambda messages, role: _lot("Repetee"))
        premier = production.prospecter(nombre=8, graine="jardinage",
                                        journal=lambda m: None,
                                        avec_veille=False)
        second = production.prospecter(nombre=8, graine="jardinage",
                                       journal=lambda m: None,
                                       avec_veille=False)
        self.assertEqual(premier["ajoutees"], 8)
        self.assertEqual(second["ajoutees"], 0)
        self.assertEqual(second["en_file"], 8)
        self.assertEqual(second["ecartees"], [],
                         "aucune ne recouvre un produit fabrique")


class LExplorationRefuseLeCache(unittest.TestCase):
    """Garde-fou de structure, pas de nom.

    Chercher « cache=False » quelque part dans le fichier serait satisfait
    par un commentaire. Ce qu'on veut savoir : l'appel au modele qui explore
    porte-t-il bien cet argument ?
    """

    def test_l_appel_d_exploration_passe_cache_faux(self):
        arbre = ast.parse((RACINE / "usine" / "pipelines" / "idees.py")
                          .read_text(encoding="utf-8"))
        fonction = next(n for n in ast.walk(arbre)
                        if isinstance(n, ast.FunctionDef)
                        and n.name == "explorer")
        appels = [n for n in ast.walk(fonction)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "travailler_json"]
        self.assertEqual(len(appels), 1)
        refus = [m for m in appels[0].keywords
                 if m.arg == "cache" and isinstance(m.value, ast.Constant)
                 and m.value.value is False]
        self.assertTrue(refus, "l'exploration lit encore le cache")

    def test_le_refus_traverse_les_deux_couches(self):
        """L'agent et le routeur doivent tous deux savoir le transmettre.
        Un « cache » accepte puis ignore serait un reglage orphelin."""
        import inspect
        from usine.agents import base as agents_base
        self.assertIn(
            "cache", inspect.signature(agents_base.Agent.travailler_json).parameters)
        self.assertIn("cache", inspect.signature(llm.generer_json).parameters)
        appels = []
        llm.definir_simulateur(lambda m, r: '{"ok": 1}')
        try:
            with mock.patch.object(llm.store, "cache_set",
                                   side_effect=lambda *a, **k: appels.append(a)):
                llm.generer_json("une invite unique pour ce test", cache=False)
            self.assertEqual(appels, [], "la reponse a quand meme ete mise "
                                         "en cache")
        finally:
            llm.definir_simulateur(None)
