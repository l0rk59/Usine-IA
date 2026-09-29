"""Tests du controle qualite deterministe, du marche et de l'apprentissage.

Le controle et l'apprentissage ne touchent pas au reseau. Les tests de marche
n'appellent rien non plus : la couche HTTP est remplacee par des reponses
figees, pour que la suite reste utilisable hors ligne et reproductible.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import apprentissage, marche  # noqa: E402
from usine.core import controle as ctrl  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402

TEXTE_IA = """Dans un monde où la productivité est reine, il est important de noter
que nous allons explorer ensemble les clés du succès. En conclusion, gardons à
l'esprit que la productivité joue un rôle crucial. Il est essentiel de comprendre
que la productivité est incontournable de nos jours.
"""

TEXTE_PROPRE = """Julie facture 320 euros la journee. Elle remplit onze jours par mois.

## Le vrai probleme

Son tarif n'est pas en cause. Ce qui manque, c'est un systeme d'acquisition qui
tourne sans elle et qui remplit son agenda meme pendant les semaines de mission.
Prenons un exemple : a douze jours factures a 450 euros, le chiffre d'affaires
mensuel atteindrait 5 400 euros.

## Trois etapes

1. Lister les trois derniers clients.
2. Calculer le taux journalier reel, charges comprises.
3. Supprimer l'offre la moins rentable.

Cela prend une heure.
"""


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("controle")


class TestMesures(unittest.TestCase):
    def test_repetition_detecte_les_blocs_repetes(self):
        repete = ["le", "chat", "dort", "sur", "le", "tapis"] * 6
        unique = "un texte entierement different a chaque mot employe ici".split()
        self.assertGreater(ctrl.repetition_ngrammes(repete, 4), 0.5)
        self.assertEqual(ctrl.repetition_ngrammes(unique, 4), 0.0)

    def test_repetition_ignore_un_texte_trop_court(self):
        self.assertEqual(ctrl.repetition_ngrammes(["a", "b"], 4), 0.0)

    def test_diversite_lexicale_normalisee_par_fenetre(self):
        """Deux textes de longueurs differentes doivent rester comparables."""
        varie = ["mot{}".format(i) for i in range(1200)]
        pauvre = ["toujours", "le", "meme"] * 400
        self.assertGreater(ctrl.diversite_lexicale(varie), 0.9)
        self.assertLess(ctrl.diversite_lexicale(pauvre), 0.05)

    def test_rythme(self):
        uniforme = " ".join(["Une phrase de six mots juste ici." for _ in range(8)])
        moyenne, ecart = ctrl.rythme(ctrl.phrases(uniforme))
        self.assertEqual(ecart, 0.0)
        self.assertGreater(moyenne, 0)

    def test_chiffres_sans_source(self):
        self.assertTrue(ctrl.chiffres_sans_source("87% des freelances echouent."))
        self.assertFalse(ctrl.chiffres_sans_source(
            "Par exemple, 87% des freelances de cet echantillon fictif."))
        self.assertFalse(ctrl.chiffres_sans_source(
            "Selon une etude citee, 40% des projets derapent."))

    def test_chiffres_sources_en_anglais(self):
        """Le modele ecrit dans la langue du produit. Seuls les marqueurs
        francais etaient reconnus : quatre chiffres anglais correctement
        introduits sur quatre etaient declares inventes."""
        for phrase in (
                "According to a 2023 Gallup survey, 67% of remote workers "
                "report better focus.",
                "For example, a shop that converts 3% of visitors doubles "
                "revenue at 6%.",
                "A 2022 McKinsey report found that teams ship 30% faster.",
                "Imagine a freelancer who raises prices by 20% this year."):
            with self.subTest(phrase=phrase[:30]):
                self.assertFalse(ctrl.chiffres_sans_source(phrase))
        # Et un chiffre anglais sans rien reste signale.
        self.assertTrue(ctrl.chiffres_sans_source(
            "Most freelancers lose 40% of their revenue to late payments."))

    def test_continuite(self):
        a = "la prospection commerciale demande une methode reguliere et mesurable"
        proche = "la methode de prospection reguliere se mesure chaque semaine"
        loin = "la photographie argentique utilise des pellicules sensibles"
        self.assertGreater(ctrl.continuite(proche, [a]), ctrl.continuite(loin, [a]))
        self.assertEqual(ctrl.continuite(loin, []), 1.0)

    def test_phrases_ignore_titres_et_listes(self):
        texte = "# Titre\n\nUne phrase. Une autre phrase.\n\n- un point\n- deux"
        self.assertEqual(len(ctrl.phrases(texte)), 2)


class TestControle(unittest.TestCase):
    def test_texte_genere_est_lourdement_sanctionne(self):
        rapport = ctrl.controler(TEXTE_IA, mots_cibles=60)
        self.assertLess(rapport.note, 5.0)
        self.assertTrue(rapport.bloquantes)
        self.assertFalse(rapport.acceptable)
        self.assertIn("tics", [a.genre for a in rapport.anomalies])

    def test_texte_propre_passe(self):
        rapport = ctrl.controler(TEXTE_PROPRE, mots_cibles=100)
        self.assertGreaterEqual(rapport.note, 8.0)
        self.assertTrue(rapport.acceptable)

    def test_promesse_de_resultat_est_bloquante(self):
        rapport = ctrl.controler(
            TEXTE_PROPRE + "\n\nAvec cette methode, les resultats sont garantis.",
            mots_cibles=100)
        genres = [a.genre for a in rapport.anomalies]
        self.assertIn("promesse", genres)
        self.assertTrue(any(a.gravite == "bloquant" for a in rapport.anomalies))

    def test_les_consignes_sont_exploitables(self):
        rapport = ctrl.controler(TEXTE_IA, mots_cibles=60)
        consignes = rapport.consignes()
        self.assertTrue(consignes)
        self.assertEqual(len(consignes), len(set(consignes)), "consignes en double")
        for consigne in consignes:
            self.assertGreater(len(consigne), 25)

    def test_note_bornee(self):
        vide = ctrl.controler("", mots_cibles=1000)
        self.assertGreaterEqual(vide.note, 0.0)
        self.assertLessEqual(ctrl.controler(TEXTE_PROPRE).note, 10.0)

    def test_ensemble_suit_la_continuite(self):
        resultat = ctrl.controler_ensemble(
            [("Chapitre 1", TEXTE_PROPRE), ("Chapitre 2", TEXTE_PROPRE)],
            mots_cibles=100)
        self.assertEqual(len(resultat["sections"]), 2)
        self.assertIsNotNone(resultat["note_moyenne"])
        self.assertIn("continuite", resultat["sections"][1]["mesures"])

    def test_deux_executions_donnent_le_meme_resultat(self):
        """Un controle deterministe doit etre reproductible."""
        a = ctrl.controler(TEXTE_IA, mots_cibles=60)
        b = ctrl.controler(TEXTE_IA, mots_cibles=60)
        self.assertEqual(a.note, b.note)
        self.assertEqual(a.mesures, b.mesures)


class TestMarqueursDeTravail(unittest.TestCase):
    """Une consigne a l'auteur laissee dans le livre : « [Inserer un exemple
    concret ici] ». Comparee le 23/09/2026, la chaine ebook-factory verifie
    TODO et LOREM avant de livrer ; notre controle ne le faisait pas."""

    def _marqueurs(self, texte):
        return [a for a in ctrl.controler(texte * 3, exiger_structure=False)
                .anomalies if a.genre == "marqueur"]

    def test_une_consigne_a_l_auteur_est_bloquante(self):
        for texte in ("Voici un cas. [Insérer un exemple concret ici] La suite.",
                      "Lorem ipsum dolor sit amet, la suite du chapitre.",
                      "Le tarif moyen est de [TODO : chiffre] euros.",
                      "Une idée forte (à développer : trois exemples).",
                      "Le nombre exact reste [TBD] pour l'instant."):
            with self.subTest(texte=texte):
                trouves = self._marqueurs(texte)
                self.assertEqual(len(trouves), 1)
                self.assertEqual(trouves[0].gravite, "bloquant")
                self.assertTrue(trouves[0].consigne)

    def test_ce_qui_parle_au_lecteur_n_est_pas_un_marqueur(self):
        """Le pendant, et c'est lui qui garde l'etroitesse du vocabulaire :
        un exercice, une variable de modele, une indication de lecture a voix
        haute, une liste de taches, un renvoi."""
        for texte in ("Votre objectif pour ce mois : [à compléter].",
                      "Remplacez [VOTRE PRODUIT] par ce que vous vendez.",
                      "[PAUSE] Respirez. [INSISTER] C'est le point clé.",
                      "Ouvrez votre todo list chaque matin, avant le café.",
                      "Le mot lorem vient d'une coupure de Cicéron.",
                      "Nous y reviendrons (voir le chapitre 3)."):
            with self.subTest(texte=texte):
                self.assertEqual(self._marqueurs(texte), [])


class TestMarche(unittest.TestCase):
    """Sources figees : aucun appel reseau, resultat reproductible."""

    def setUp(self):
        self.origine = marche.requete

    def tearDown(self):
        marche.requete = self.origine

    def _brancher(self, reponses):
        def faux(url, methode="GET", entetes=None, donnees=None, timeout=20):
            for fragment, charge in reponses.items():
                if fragment in url:
                    return 200, json.dumps(charge).encode("utf-8")
            raise HttpErreur(404, "non simule")

        marche.requete = faux

    def test_hacker_news(self):
        self._brancher({"hn.algolia.com": {
            "nbHits": 4200,
            "hits": [{"title": "Un titre", "points": 300, "num_comments": 120},
                     {"title": "Un autre", "points": 100, "num_comments": 20}],
        }})
        source = marche.hacker_news("freelance")
        self.assertTrue(source.disponible)
        self.assertEqual(source.donnees["discussions_totales"], 4200)
        self.assertEqual(source.donnees["titres_forts"][0]["points"], 300)

    def test_une_source_muette_ne_casse_rien(self):
        self._brancher({})  # tout echoue
        rapport = marche.sonder("n'importe quoi")
        self.assertEqual(rapport["sources_disponibles"], [])
        self.assertEqual(len(rapport["sources_indisponibles"]), len(marche.SOURCES))
        self.assertIn("Impossible de qualifier", rapport["lecture"]["verdict"])

    def test_wikipedia_prefere_le_titre_exact(self):
        """« Freelance » ne doit pas renvoyer « Freelance (2023 film) »."""
        self._brancher({
            "opensearch": ["freelance",
                           ["Freelance (2023 film)", "Freelancer"], ["", ""], ["", ""]],
            "Freelance_(2023_film)": {"items": [{"views": 900000} for _ in range(12)]},
            "Freelancer": {"items": [{"views": 5000} for _ in range(12)]},
        })
        source = marche.wikipedia_interet("freelance", "en")
        self.assertTrue(source.disponible)
        self.assertEqual(source.donnees["article"], "Freelancer",
                         "la page homonyme ne doit pas etre retenue")

    def test_frequentation_faible_marquee_non_significative(self):
        self._brancher({
            "opensearch": ["sujet", ["Sujet"], [""], [""]],
            "Sujet": {"items": [{"views": 12} for _ in range(12)]},
        })
        source = marche.wikipedia_interet("sujet", "fr")
        self.assertFalse(source.donnees["significatif"])
        lecture = marche.interpreter(
            {"sujet": "sujet", "sources": {"wikipedia": {"disponible": True,
                                                         **source.donnees}},
             "sources_disponibles": ["wikipedia"]})
        self.assertTrue(any("trop peu pour conclure" in s for s in lecture["signaux"]))

    def test_requete_francaise_signalee(self):
        lecture = marche.interpreter({
            "sujet": "la prospection pour les freelances",
            "sources": {"hacker_news": {"disponible": True, "discussions_totales": 3}},
            "sources_disponibles": ["hacker_news"],
        })
        self.assertTrue(lecture["requete_francophone"])
        self.assertIn("anglophones", lecture["verdict"])

    def test_resume_pour_ia_reste_borne(self):
        rapport = {
            "sujet": "x", "date": "2026-01-01",
            "sources": {"hacker_news": {"disponible": True, "titres_forts": [
                {"titre": "T" * 200, "points": 10, "commentaires": 2}] * 10}},
            "sources_disponibles": ["hacker_news"],
        }
        rapport["lecture"] = marche.interpreter(rapport)
        self.assertLessEqual(len(marche.resume_pour_ia(rapport, limite=500)), 500)


class TestApprentissage(unittest.TestCase):
    def setUp(self):
        apprentissage._assurer()
        from usine.core import store

        with store.cursor() as cur:
            cur.execute("DELETE FROM productions")

    def test_bilan_vide(self):
        self.assertEqual(apprentissage.bilan()["productions"], 0)
        conseils = apprentissage.conseils()
        self.assertEqual(conseils[0]["sujet"], "demarrage")

    def test_bilan_agrege(self):
        for i in range(6):
            apprentissage.enregistrer(
                "p{}".format(i), "ebook", ton="punchy" if i % 2 else "pro",
                note=9.0 if i % 2 else 6.0, note_avant=5.0, mots=1000, appels=10,
                defauts=["repetition de blocs : 30%"])
        donnees = apprentissage.bilan()
        self.assertEqual(donnees["productions"], 6)
        self.assertEqual(donnees["note_moyenne"], 7.5)
        self.assertEqual(donnees["mots_totaux"], 6000)
        meilleur = donnees["par_ton"][0]
        self.assertEqual(meilleur["valeur"], "punchy")

    def test_conseil_appuye_sur_les_donnees(self):
        for i in range(8):
            apprentissage.enregistrer(
                "q{}".format(i), "ebook", ton="punchy" if i % 2 else "pro",
                note=9.0 if i % 2 else 6.0, note_avant=5.0, appels=10)
        conseils = apprentissage.conseils()
        sujets = [c["sujet"] for c in conseils]
        self.assertIn("ton", sujets)
        for conseil in conseils:
            self.assertTrue(conseil["appui"], "tout conseil doit citer son appui")

    def test_echantillon_trop_faible_est_annonce(self):
        apprentissage.enregistrer("r1", "ebook", ton="pro", note=8.0)
        self.assertEqual(apprentissage.conseils()[0]["sujet"], "echantillon")

    def test_les_groupes_trop_petits_sont_ecartes(self):
        """Une seule production avec un ton donne ne fait pas une tendance."""
        apprentissage.enregistrer("s1", "ebook", ton="unique", note=10.0)
        for i in range(3):
            apprentissage.enregistrer("s{}".format(i + 2), "ebook", ton="pro", note=6.0)
        tons = [g["valeur"] for g in apprentissage.bilan()["par_ton"]]
        self.assertNotIn("unique", tons)
        self.assertIn("pro", tons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
