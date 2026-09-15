"""Un conte jeunesse se compose en doubles-pages, pas en chapitres.

Ce que cette chaine ajoute : elle verifie que le texte produit correspond a
la TRANCHE D'AGE demandee — et elle le fait sans inventer de seuil.

Le plafond de mots par phrase n'est pas une verite sur la lecture enfantine.
C'est ce que l'usine a DEMANDE au modele, ecrit dans « TRANCHES »,
modifiable, et le controle mesure si la reponse s'y tient. Comparer une
sortie a la consigne qui l'a produite est verifiable ; affirmer « une phrase
de plus de douze mots est trop longue pour un enfant de cinq ans »
demanderait une etude qu'on n'a pas.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("conte")


from usine.core import llm, store  # noqa: E402
from usine.pipelines import base, conte  # noqa: E402
from tests import simulateur  # noqa: E402


class LeTexteEstCompareALaConsigneQuiLAProduit(unittest.TestCase):

    def test_une_phrase_trop_longue_pour_la_tranche_est_signalee(self):
        pages = [{"numero": 1, "texte": "Le petit ours dort.",
                  "illustration": "un ours"},
                 {"numero": 2, "illustration": "la foret",
                  "texte": "Ce matin-la, le petit ours ouvrit les yeux et vit "
                           "que toute la foret avait change de couleur."}]
        mesure = conte.mesurer_l_age(pages, "3-5 ans")
        lectures = conte.lire_l_age(mesure)
        # Huit mots : le repere « comprise a pres de cent pour cent ». La
        # premiere version disait dix, un chiffre que personne n'avait mesure.
        self.assertTrue(any("depassent les 8 mots" in l for l in lectures),
                        lectures)

    def test_la_meme_phrase_passe_pour_une_tranche_plus_agee(self):
        """Le controle ne juge pas la phrase : il la compare a ce qu'on a
        demande. Changer la demande change le verdict, et c'est voulu."""
        pages = [{"numero": 1, "illustration": "x",
                  "texte": "Le petit ours ouvrit les yeux et vit la foret."}]
        self.assertEqual(conte.lire_l_age(
            conte.mesurer_l_age(pages, "9-12 ans")), [])

    def test_le_plafond_rendu_est_celui_de_la_tranche(self):
        for tranche, regle in conte.TRANCHES.items():
            mesure = conte.mesurer_l_age(
                [{"numero": 1, "texte": "Il dort.", "illustration": "x"}],
                tranche)
            self.assertEqual(mesure["plafond_demande"], regle["mots_phrase"])

    def test_une_tranche_inconnue_retombe_sur_le_defaut(self):
        """Plutot que de lever : un reglage inconnu ne doit pas empecher de
        fabriquer, il doit ramener a ce qui est raisonnable."""
        self.assertEqual(conte.reglages_de_tranche("42 ans"),
                         conte.TRANCHES[conte.TRANCHE_DEFAUT])

    def test_un_texte_conforme_ne_declenche_rien(self):
        pages = [{"numero": 1, "texte": "Le petit ours dort.",
                  "illustration": "un ourson"},
                 {"numero": 2, "texte": "Dehors, la neige tombe.",
                  "illustration": "des flocons"}]
        self.assertEqual(conte.lire_l_age(conte.mesurer_l_age(pages, "3-5 ans")),
                         [])

    def test_une_page_sans_illustration_est_signalee(self):
        """Dans un album, l'image porte la moitie du recit."""
        pages = [{"numero": 1, "texte": "Il dort.", "illustration": ""}]
        lectures = conte.lire_l_age(conte.mesurer_l_age(pages, "3-5 ans"))
        self.assertTrue(any("sans note d'illustration" in l for l in lectures))

    def test_la_mesure_compte_les_phrases_et_non_les_pages(self):
        pages = [{"numero": 1, "illustration": "x",
                  "texte": "Il dort. Il reve. Il se leve."}]
        self.assertEqual(conte.mesurer_l_age(pages, "3-5 ans")["phrases"], 3)

    def test_la_phrase_la_plus_longue_est_rendue(self):
        """Une moyenne cache une phrase de trente mots au milieu de vingt
        phrases de trois."""
        pages = [{"numero": 1, "illustration": "x",
                  "texte": "Il dort. " + "mot " * 30 + "."}]
        mesure = conte.mesurer_l_age(pages, "3-5 ans")
        self.assertGreaterEqual(mesure["phrase_la_plus_longue"], 30)


class LaChaineCompleteViaLeSimulateur(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)
        store.cache_vider()

    def tearDown(self):
        llm.definir_simulateur(None)

    def _produire(self, pages, tranche="3-5 ans", sujet="un ourson"):
        ctx = base.Contexte(sujet=sujet, sans_image=True, journal=lambda m: None)
        ctx.chapitres = pages
        return conte.produire(ctx, tranche=tranche)

    def test_un_album_sort_conforme_a_sa_tranche(self):
        resume = self._produire(6)
        self.assertEqual(resume["pages"], 6)
        self.assertEqual(resume["tranche"], "3-5 ans")
        self.assertEqual(resume["lectures"], [])
        self.assertLessEqual(resume["lisibilite"]["phrase_la_plus_longue"],
                             resume["lisibilite"]["plafond_demande"])

    def test_la_mesure_de_lisibilite_est_livree_avec_l_album(self):
        import json

        resume = self._produire(6, sujet="un renard")
        donnees = json.loads((Path(resume["dossier"]) / "conte.json")
                             .read_text(encoding="utf-8"))
        self.assertIn("lisibilite", donnees)
        self.assertEqual(donnees["lisibilite"]["tranche"], "3-5 ans")

    def test_sans_image_les_notes_d_illustration_restent(self):
        """Un album sans images se vend mal ; un album dont l'acheteur ne
        sait pas quoi faire dessiner ne se vend pas du tout."""
        resume = self._produire(6, sujet="une chouette")
        texte = (Path(resume["dossier"]) / "conte.md").read_text(
            encoding="utf-8")
        self.assertIn("Illustration :", texte)

    def test_le_nombre_de_pages_demande_fait_foi(self):
        self.assertEqual(self._produire(8, sujet="un blaireau")["pages"], 8)


class UnModeleTropGenereuxEstRameneALaDemande(unittest.TestCase):
    """Le simulateur rend exactement ce qu'on lui demande : le plafond ne
    s'executait jamais, et une mutation qui le retirait ne faisait echouer
    aucun test."""

    def tearDown(self):
        llm.definir_simulateur(None)
        store.cache_vider()

    def test_vingt_pages_rendues_pour_six_demandees(self):
        import json as _json

        def trop(messages, role):
            invite = messages[-1]["content"]
            if '"illustration"' in invite and '"pages"' in invite:
                return _json.dumps({
                    "titre": "Album trop long", "heros": "un ourson",
                    "pages": [{"numero": rang, "texte": "Il dort.",
                               "illustration": "un ourson"}
                              for rang in range(1, 21)]})
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(trop)
        ctx = base.Contexte(sujet="un album trop long", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres = 6
        self.assertEqual(conte.produire(ctx, tranche="3-5 ans")["pages"], 6)
