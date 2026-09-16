"""Un roman demande, une niche pratique choisie.

Journal reel du 16/09/2026, type « roman », aucun sujet donne :

    Exploration autour de ce qui a le mieux marche : « Cannabis »...
    Toutes les pistes recouvrent un produit deja fait.
    8 domaines proposes — mesure sur les sources publiques...
      garde « cours video montage video » ...
      garde « ebook strategie marketing TikTok » ...
    Premiere niche, choisie par l'usine : « cours video montage video ».
    L'usine decide 9 reglage(s) : genre, sous_genre, tropes, ambiance...
    Titre retenu : « L'Ame du Montage »

Un roman sur un cours de montage video, dont les neuf reglages de genre ont
ensuite ete devines a partir de cette niche-la.

« fiction.explorer_promesses » existait depuis septembre, et son docstring
annoncait le defaut mot pour mot : « on obtenait donc des fictions habillees
en produits pratiques ». Mais rien ne l'appelait depuis ce chemin. Seuls le
bouton « Trouver des idees de fiction » et « usine prospecter --fiction » y
menaient ; le chemin le plus court — choisir un type, appuyer sur Lancer —
posait la question des niches a un roman.

Une fonction sans appelant ne protege personne. Celle-ci en avait deux, et
aucun sur le chemin qu'on emprunte vraiment.

Aucun test ici ne sort sur le reseau : le sondage de marche est remplace.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("fiction-pas-niche")


from usine import production  # noqa: E402
from usine.core import file, llm, marche, store  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402

PROMESSE = {
    "titre": "Le dernier train de Roubaix", "type": "roman",
    "genre": "drame social", "sous_genre": "huis clos",
    "tropes": "retrouvailles, secret de famille", "ambiance": "melancolique",
    "point_de_vue": "troisieme personne", "temps": "passe",
    "chaleur": "aucune", "fin": "amere",
    "structure": "trois actes",
    "lecteur": "qui aime les fins qui ne consolent pas",
}


class _Modele:
    """Repond aux deux questions, et note laquelle on lui a posee."""

    def __init__(self, avec_promesse=True):
        self.questions = []
        self.avec_promesse = avec_promesse
        self.promesse = PROMESSE

    def __call__(self, messages, role):
        invite = messages[-1]["content"]
        if '"pourquoi_maintenant"' in invite:
            self.questions.append("niche")
            return json.dumps({"domaines": [
                {"domaine": "cours video montage video", "acheteur": "x",
                 "pourquoi_maintenant": "y"}]})
        if '"lecteur"' in invite:
            self.questions.append("fiction")
            return json.dumps(
                {"promesses": [self.promesse] if self.avec_promesse else []})
        self.questions.append("autre")
        return json.dumps({"idees": []})


def _sans_marche():
    vrai = marche.sonder
    marche.sonder = lambda sujet, **_k: {
        "sujet": sujet, "date": "2026-09-16", "sources": {},
        "sources_disponibles": [], "sources_indisponibles": [],
        "lecture": {"demande": "", "fiabilite": "", "verdict": "", "signaux": []}}
    return vrai


class UnRomanNeSeCherchePasCommeUnGuide(unittest.TestCase):

    def setUp(self):
        store.cache_vider()
        file.vider(tout=True)
        self.vrai_sonder = _sans_marche()
        self.modele = _Modele()
        llm.definir_simulateur(self.modele)

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder

    def test_la_question_posee_est_celle_du_lecteur(self):
        choix = production.choisir_une_niche(journal=lambda m: None,
                                             type_produit="roman")
        self.assertEqual(self.modele.questions[0], "fiction", (
            "premiere question posee : {} — l'usine cherche un acheteur pour "
            "un roman".format(self.modele.questions))) 
        self.assertEqual(choix["sujet"], PROMESSE["titre"])
        self.assertEqual(choix["source"], "fiction")

    def test_les_neuf_reglages_voyagent_avec_la_promesse(self):
        """Le journal montrait « L'usine decide 9 reglage(s) » APRES avoir
        choisi une niche pratique : neuf reglages devines sur un malentendu.
        Ils arrivent maintenant avec le sujet, et lui sont accordes."""
        choix = production.choisir_une_niche(journal=lambda m: None,
                                             type_produit="roman")
        options = choix.get("options") or {}
        for cle in ("genre", "sous_genre", "tropes", "ambiance",
                    "point_de_vue", "temps", "chaleur", "fin", "structure"):
            with self.subTest(reglage=cle):
                self.assertEqual(options.get(cle), PROMESSE[cle])
        self.assertEqual(options.get("audience"), PROMESSE["lecteur"])

    def test_une_promesse_concue_pour_un_autre_type_est_refusee(self):
        """Le type demande est une contrainte, pas une preference. Une
        promesse d'album jeunesse ne fait pas un roman — le depot avait deja
        paye cette lecon sur les niches, ou « 30 posts LinkedIn » devenait un
        ebook intitule « 30 posts LinkedIn »."""
        self.modele.promesse = dict(PROMESSE, type="conte",
                                    titre="L'ourson qui ne dormait pas")
        choix = production.choisir_une_niche(journal=lambda m: None,
                                             type_produit="roman")
        self.assertNotEqual(choix["sujet"], "L'ourson qui ne dormait pas", (
            "une promesse ecrite pour un conte a ete retenue pour un roman"))
        self.assertNotEqual(choix.get("source"), "fiction")

    def test_un_guide_garde_la_question_du_marche(self):
        """Le garde-fou qui crie a tort : poser la question du lecteur a un
        ebook pratique serait l'erreur symetrique, et aussi couteuse."""
        production.choisir_une_niche(journal=lambda m: None,
                                     type_produit="ebook")
        self.assertNotIn("fiction", self.modele.questions, (
            "un ebook pratique s'est vu poser la question du lecteur"))

    def test_toute_la_famille_fiction_est_concernee(self):
        """Pas seulement le roman. Le CATALOGUE est la source : un type de
        fiction ajoute demain en herite sans qu'on ait a y penser, ce qui est
        exactement ce qu'une liste ecrite a la main ne fait pas."""
        fictions = [t.cle for t in catalogue.tous() if t.famille == "fiction"]
        self.assertGreaterEqual(len(fictions), 6)
        for cle in fictions:
            with self.subTest(type=cle):
                store.cache_vider()
                file.vider(tout=True)
                modele = _Modele()
                modele.promesse = dict(PROMESSE, type=cle,
                                       titre="Promesse pour " + cle)
                llm.definir_simulateur(modele)
                choix = production.choisir_une_niche(
                    journal=lambda m: None, type_produit=cle)
                self.assertEqual(modele.questions[0], "fiction")
                self.assertEqual(choix["sujet"], "Promesse pour " + cle)


class LeJournalDitCeQuiClasse(unittest.TestCase):
    """« Exploration autour de ce qui a le mieux marche : « Cannabis » » —
    dit a quelqu'un qui n'a jamais rien vendu, et dont « Cannabis » etait un
    essai. Le classement retombe sur la note QUALITE quand il n'y a pas de
    vente, et la note est une mesure de l'usine, pas du marche.

    Ce n'est pas le classement qui est faux, c'est la phrase.
    """

    def setUp(self):
        store.cache_vider()
        file.vider(tout=True)
        self.vrai_sonder = _sans_marche()
        self.vrai_meilleures = production.apprentissage.meilleures_niches
        self.modele = _Modele()
        llm.definir_simulateur(self.modele)

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder
        production.apprentissage.meilleures_niches = self.vrai_meilleures

    def _journal_pour(self, brut):
        production.apprentissage.meilleures_niches = lambda n=1: [
            {"sujet": "Cannabis", "note": 9.1, "brut": brut, "productions": 1}]
        lignes = []
        production.choisir_une_niche(journal=lignes.append,
                                     type_produit="ebook")
        return " ".join(lignes)

    def test_sans_vente_le_journal_ne_parle_pas_de_marche(self):
        texte = self._journal_pour(0.0)
        self.assertIn("mieux NOTE", texte)
        self.assertIn("pas une mesure du marche", texte)
        self.assertNotIn("le mieux marche", texte, (
            "une note de l'usine est annoncee comme un resultat de vente"))

    def test_avec_une_vente_le_journal_le_dit_et_chiffre(self):
        """Le pendant : sans lui, se taire TOUJOURS sur les ventes passerait
        le test precedent sans rien distinguer."""
        texte = self._journal_pour(42.5)
        self.assertIn("le mieux marche", texte)
        self.assertIn("42.5", texte)


class QuandAucunePromesseNeVient(unittest.TestCase):
    """Le repli doit exister : une fiction sans promesse neuve vaut mieux
    qu'une fabrication refusee."""

    def setUp(self):
        store.cache_vider()
        file.vider(tout=True)
        self.vrai_sonder = _sans_marche()
        self.modele = _Modele(avec_promesse=False)
        llm.definir_simulateur(self.modele)

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder

    def test_l_usine_cherche_autrement_au_lieu_d_abandonner(self):
        choix = production.choisir_une_niche(journal=lambda m: None,
                                             type_produit="roman")
        self.assertIn("fiction", self.modele.questions)
        self.assertTrue(choix["sujet"], (
            "aucune promesse et aucun repli : la fabrication est refusee"))


class LaFileDAttentePasseAvant(unittest.TestCase):
    """Une promesse qui attend deja vaut mieux qu'une neuve — et elle ne doit
    pas couter un appel de modele."""

    def setUp(self):
        store.cache_vider()
        file.vider(tout=True)
        self.vrai_sonder = _sans_marche()
        self.modele = _Modele()
        llm.definir_simulateur(self.modele)

    def tearDown(self):
        llm.definir_simulateur(None)
        marche.sonder = self.vrai_sonder

    def test_rien_n_est_demande_au_modele(self):
        file.ajouter("Une promesse qui attendait", "roman")
        choix = production.choisir_une_niche(journal=lambda m: None,
                                             type_produit="roman")
        self.assertEqual(choix["sujet"], "Une promesse qui attendait")
        self.assertEqual(self.modele.questions, [], (
            "la file a ete doublee par un appel de modele : {}".format(
                self.modele.questions)))


if __name__ == "__main__":
    unittest.main()
