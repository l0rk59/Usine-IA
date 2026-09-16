"""La source Wikipedia rendait la frequentation d'un article sans rapport.

Mesure du 16/09/2026, sur six noms de niches francaises realistes. Wikipedia
ne repondait que sur UN — « le tricot » — et repondait faux :

    « le tricot »                      -> « Le Tricheur a l'as de carreau »
                                          2 218 vues/mois (un tableau de
                                          Georges de La Tour)
    « la facturation des independants » -> « DKV Euro Service »
                                          145 vues/mois (cartes carburant)

Deux defauts empiles, et le second se cachait derriere le premier.

1. « opensearch » compare des PREFIXES de titres. Interroge avec « le
   tricot », il rend « Le Tricheur... » et jamais « Tricot » : l'article
   defini francais rend la bonne page inatteignable. On l'interroge donc avec
   le nom nu.

2. Quand aucun titre n'a de rapport avec le sujet, l'ancien code departageait
   les candidats a la FREQUENTATION — c'est-a-dire qu'il elisait le plus
   consulte des articles sans rapport. Le nombre avait l'air d'une mesure. On
   ne lui attribue plus rien, et on le dit.

Ce que la recherche plein texte apporte en repli, mesure le meme jour :

    le tricot                             2 209 articles
    la facturation des independants          232
    la meditation pour debutants             183
    le potager en bac sur balcon              21
    la reparation de theremines a vapeur       0
    le pliage de serviettes pour chats         0

Elle separe le reel de l'invente. Le compte est rendu, jamais interprete :
six points de releve ne font pas un seuil.

Aucun test ici ne sort sur le reseau : les reponses des deux API sont figees.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("wikipedia-niche")


from usine.core import marche  # noqa: E402


class _Faux:
    """Repond aux URL de Wikipedia sans toucher au reseau."""

    def __init__(self, titres=(), plein_texte=(), hits=0, vues=None):
        self.titres = list(titres)
        self.plein_texte = list(plein_texte)
        self.hits = hits
        self.vues = vues or {}
        self.appels = []

    def __call__(self, url, timeout=20):
        self.appels.append(url)
        if "action=opensearch" in url:
            return ["", self.titres, [], []]
        if "list=search" in url:
            return {"query": {
                "search": [{"title": t} for t in self.plein_texte],
                "searchinfo": {"totalhits": self.hits}}}
        if "pageviews" in url:
            article = url.split("/monthly/")[0].split("/")[-1]
            mesures = self.vues.get(article.replace("_", " "))
            if mesures is None:
                raise marche.HttpErreur(404, "pas de donnees")
            return {"items": [{"views": v} for v in mesures]}
        raise AssertionError("URL inattendue : " + url)


def _avec(faux):
    vrai = marche._json
    marche._json = faux
    return vrai


class LArticleDefiniNeCacheePlusLaBonnePage(unittest.TestCase):

    def test_le_nom_nu_est_ce_qu_on_demande_a_wikipedia(self):
        faux = _Faux(titres=["Tricot"], vues={"Tricot": [900] * 12})
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("le tricot")
        finally:
            marche._json = vrai
        self.assertIn("search=tricot", faux.appels[0], (
            "Wikipedia est interroge avec « le tricot » : l'article « Tricot » "
            "est alors inatteignable, opensearch comparant des prefixes"))
        self.assertEqual(source.donnees["article"], "Tricot")

    def test_la_requete_garde_les_accents(self):
        """Demander « meditation » a fr.wikipedia rendait un homonyme a 10
        vues par mois, quand « Méditation » en fait plusieurs milliers. Les
        accents servent a COMPARER deux titres, pas a interroger l'API — les
        confondre fabrique un chiffre qui a l'air d'une mesure."""
        import urllib.parse

        faux = _Faux(titres=["Méditation"], vues={"Méditation": [5000] * 12})
        vrai = _avec(faux)
        try:
            marche.wikipedia_interet("la méditation")
        finally:
            marche._json = vrai
        self.assertIn(urllib.parse.quote("méditation"), faux.appels[0], (
            "l'accent est tombe avant la requete : « {} »".format(
                faux.appels[0])))

    def test_le_normalisateur_compare_sans_accent(self):
        """Le pendant : « Méditation » et « meditation » doivent se
        reconnaitre, sinon la page trouvee serait ecartee par le classement."""
        self.assertEqual(marche._nu("la Méditation"), "meditation")
        self.assertEqual(marche._sans_article("les Épices"), "Épices")
        # Avec une majuscule : c'est la casse, et non l'accent, qui empechait
        # de reconnaitre l'article.
        self.assertEqual(marche._sans_article("Les Épices"), "Épices")

    def test_le_normalisateur_retire_les_articles_empiles(self):
        self.assertEqual(marche._nu("d'une niche"), "niche")
        self.assertEqual(marche._nu("Le Tricot"), "tricot")
        self.assertEqual(marche._nu("Tricot"), "tricot")


class UneFrequentationSansRapportNEstPasUneMesure(unittest.TestCase):

    def test_le_plus_consulte_des_hors_sujet_n_est_pas_elu(self):
        """Le defaut mesure : « le tricot » -> un tableau de La Tour, 2 218
        vues/mois. Le classement se rabattait sur les vues quand aucun titre
        ne correspondait."""
        faux = _Faux(titres=["Le Tricheur a l'as de carreau", "Le Tricycle"],
                     vues={"Le Tricheur a l'as de carreau": [2218] * 12,
                           "Le Tricycle": [40] * 12})
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("le tricot")
        finally:
            marche._json = vrai
        self.assertEqual(source.donnees.get("article"), "", (
            "« {} » a ete elu pour un sujet qui n'a rien a voir".format(
                source.donnees.get("article"))))
        self.assertNotIn("vues_mensuelles_moyennes", source.donnees)
        self.assertEqual(source.donnees.get("frequentation"), "non attribuee")

    def test_un_titre_qui_correspond_garde_sa_frequentation(self):
        """Le pendant : sans lui, refuser TOUJOURS d'attribuer passerait le
        test precedent sans rien mesurer."""
        faux = _Faux(titres=["Meditation", "Meditation bouddhique"],
                     vues={"Meditation": [5000] * 12,
                           "Meditation bouddhique": [90] * 12})
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("la meditation")
        finally:
            marche._json = vrai
        self.assertEqual(source.donnees["article"], "Meditation")
        self.assertEqual(source.donnees["vues_mensuelles_moyennes"], 5000)
        self.assertTrue(source.donnees["significatif"])


class LeRepliPleinTexteTrouveLesNomsDeNiches(unittest.TestCase):

    def test_un_nom_de_niche_passe_par_la_recherche_plein_texte(self):
        faux = _Faux(titres=[], plein_texte=["Jardinage en carres"], hits=21,
                     vues={"Jardinage en carres": [300] * 12})
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("le potager en bac sur balcon")
        finally:
            marche._json = vrai
        self.assertTrue(source.disponible, (
            "la source abandonnait des qu'aucun TITRE ne correspondait"))
        self.assertEqual(source.donnees["articles_fr"], 21)
        self.assertTrue(any("list=search" in u for u in faux.appels))

    def test_la_phrase_entiere_sert_au_plein_texte(self):
        """Le nom nu sert aux titres, la phrase aux mots : c'est elle qui
        trouve « Jardinage en carres » a partir de « potager en bac »."""
        faux = _Faux(titres=[], plein_texte=["Jardinage en carres"], hits=21)
        vrai = _avec(faux)
        try:
            marche.wikipedia_interet("le potager en bac sur balcon")
        finally:
            marche._json = vrai
        recherche = next(u for u in faux.appels if "list=search" in u)
        # L'ARTICLE DE TETE est la seule difference entre la phrase et le nom
        # nu : verifier la presence de « potager » et « balcon » passait dans
        # les deux cas, et une campagne de mutation l'a montre. On verifie
        # donc ce qui distingue reellement les deux requetes.
        self.assertIn("le%20potager", recherche, (
            "le plein texte est interroge avec le nom nu : « {} »".format(
                recherche)))

    def test_un_sujet_invente_ne_rend_aucun_article(self):
        faux = _Faux(titres=[], plein_texte=[], hits=0)
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("la reparation de theremines a vapeur")
        finally:
            marche._json = vrai
        self.assertFalse(source.disponible)
        self.assertEqual(source.erreur, "aucun article correspondant")

    def test_le_compte_survit_a_l_absence_de_vues(self):
        """Un titre correspond, l'API des vues ne rend rien : la source
        rendait « indisponible » et le rapport comptait 3/4 sources pour une
        mesure qu'on avait pourtant."""
        faux = _Faux(titres=[], plein_texte=["Facturation"], hits=232, vues={})
        vrai = _avec(faux)
        try:
            source = marche.wikipedia_interet("la facturation des independants")
        finally:
            marche._json = vrai
        self.assertTrue(source.disponible)
        self.assertEqual(source.donnees["articles_fr"], 232)


class CeQueLeRapportEnDit(unittest.TestCase):

    def test_le_rapport_dit_qu_il_n_a_pas_attribue(self):
        lecture = marche.interpreter({"sources": {"wikipedia": {
            "disponible": True, "articles_fr": 232,
            "frequentation": "non attribuee"}},
            "sources_disponibles": ["wikipedia"]})
        texte = " ".join(lecture.get("signaux") or []) + (lecture.get("verdict") or "")
        self.assertIn("232", texte)
        self.assertIn("attribuer", texte)
        self.assertNotIn("vues/mois", texte)


if __name__ == "__main__":
    unittest.main()
