"""Le scout de niches : ce que les gens disent, et ce qu'on n'invente pas.

Les quatre sources de marche mesurent des VOLUMES : elles disent si une
niche existe. Elles ne disent pas ce qui y fait mal, ni avec quels mots.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import veille  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402

FLUX_SUBS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Meal Prep Sunday</title>
<link href="https://www.reddit.com/r/MealPrepSunday/"/></entry>
<entry><title>Eat Cheap And Healthy</title>
<link href="https://www.reddit.com/r/EatCheapAndHealthy/"/></entry>
</feed>"""

FLUX_POSTS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>How do I plan meals for a whole week?</title>
<link href="https://www.reddit.com/r/MealPrepSunday/comments/a/"/>
<updated>2026-08-01T10:00:00+00:00</updated></entry>
<entry><title>My weekly batch cooking setup &amp; containers</title>
<link href="https://www.reddit.com/r/MealPrepSunday/comments/b/"/>
<updated>2026-08-02T10:00:00+00:00</updated></entry>
<entry><title>Struggling with portion sizes for meals</title>
<link href="https://www.reddit.com/r/MealPrepSunday/comments/c/"/>
<updated>2026-08-03T10:00:00+00:00</updated></entry>
</feed>"""


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("veille")


class FauxReseau:
    """Remplace requete() : renvoie ce qu'on lui dit, selon le chemin."""

    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []

    def __call__(self, url, methode="GET", entetes=None, donnees=None,
                 timeout=15):
        self.appels.append(url)
        for marqueur, reponse in self.reponses.items():
            if marqueur in url:
                if isinstance(reponse, Exception):
                    raise reponse
                return (200, reponse.encode("utf-8"))
        return (404, b"")


class Reseau:
    def __init__(self, reponses):
        self.faux = FauxReseau(reponses)

    def __enter__(self):
        self._ancien = veille.requete
        self._ancienne_pause = veille.time.sleep
        veille.requete = self.faux
        veille.time.sleep = lambda _s: None      # pas d'attente en test
        return self.faux

    def __exit__(self, *args):
        veille.requete = self._ancien
        veille.time.sleep = self._ancienne_pause


class TestLecture(unittest.TestCase):

    def test_les_communautes_sont_extraites_du_flux(self):
        with Reseau({"subreddits/search": FLUX_SUBS}):
            trouvees, probleme = veille.communautes("meal planning")
        self.assertEqual(probleme, "")
        self.assertEqual([c["nom"] for c in trouvees],
                         ["MealPrepSunday", "EatCheapAndHealthy"])

    def test_les_titres_sont_decodes(self):
        with Reseau({"/r/MealPrepSunday/top": FLUX_POSTS}):
            lot, probleme = veille.discussions("MealPrepSunday")
        self.assertEqual(probleme, "")
        self.assertEqual(len(lot), 3)
        self.assertIn("batch cooking setup & containers", lot[1].titre)
        self.assertEqual(lot[0].communaute, "MealPrepSunday")
        self.assertEqual(lot[0].date, "2026-08-01")

    def test_les_formulations_de_probleme_sont_repereees(self):
        with Reseau({"/r/MealPrepSunday/top": FLUX_POSTS}):
            lot, _ = veille.discussions("MealPrepSunday")
        douleurs = [d.titre for d in lot if d.douleur]
        self.assertEqual(len(douleurs), 2)
        self.assertIn("How do I plan meals for a whole week?", douleurs)


class TestIndisponibilite(unittest.TestCase):
    """« Aucune discussion » et « on n'a pas pu regarder » ne se confondent pas."""

    def test_un_429_est_rapporte_pas_pris_pour_un_vide(self):
        with Reseau({"reddit.com": HttpErreur(429, "Too Many Requests")}):
            rapport = veille.scouter("une niche", pause=0)
        self.assertFalse(rapport.utilisable)
        self.assertIn("429", rapport.indisponible)
        self.assertEqual(rapport.discussions, [])

    def test_un_429_donne_lieu_a_un_seul_reessai(self):
        """Insister prolonge le blocage au lieu de le lever."""
        with Reseau({"reddit.com": HttpErreur(429, "x")}) as faux:
            veille.communautes("x")
        self.assertEqual(len(faux.appels), 2)

    def test_une_panne_reseau_est_rapportee(self):
        with Reseau({"reddit.com": OSError("nom de domaine introuvable")}):
            rapport = veille.scouter("une niche", pause=0)
        self.assertIn("injoignable", rapport.indisponible)

    def test_une_niche_sans_communaute_le_dit_sans_conclure(self):
        vide = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>'
        with Reseau({"subreddits/search": vide}):
            rapport = veille.scouter("une niche tres francaise", pause=0)
        self.assertFalse(rapport.utilisable)
        self.assertIn("anglophone", rapport.indisponible)

    def test_une_communaute_muette_n_empeche_pas_les_autres(self):
        with Reseau({"subreddits/search": FLUX_SUBS,
                     "/r/MealPrepSunday/top": HttpErreur(429, "x"),
                     "/r/EatCheapAndHealthy/top": FLUX_POSTS}):
            rapport = veille.scouter("meal planning", pause=0)
        self.assertTrue(rapport.utilisable)
        self.assertEqual(len(rapport.discussions), 3)


class TestVocabulaire(unittest.TestCase):

    def test_les_mots_vides_ne_ressortent_pas(self):
        lot = [veille.Discussion("All of them are now only for you", "")
               for _ in range(5)]
        self.assertEqual(veille.vocabulaire(lot), [])

    def test_un_mot_vu_une_seule_fois_ne_compte_pas(self):
        lot = [veille.Discussion("congelateur unique", ""),
               veille.Discussion("congelateur pratique", "")]
        mots = dict(veille.vocabulaire(lot))
        self.assertEqual(mots.get("congelateur"), 2)
        self.assertNotIn("unique", mots)

    def test_un_mot_repete_dans_un_titre_ne_compte_qu_une_fois(self):
        lot = [veille.Discussion("meal meal meal meal", ""),
               veille.Discussion("meal prep", "")]
        self.assertEqual(dict(veille.vocabulaire(lot)).get("meal"), 2)


class TestResume(unittest.TestCase):

    def test_le_resume_ne_cache_pas_les_discussions_derriere_le_filtre(self):
        """Une seule douleur reperee masquait toutes les autres discussions."""
        rapport = veille.Veille(niche="x", discussions=[
            veille.Discussion("How do I do this", ""),
            veille.Discussion("Mon installation du dimanche", ""),
            veille.Discussion("Les boites qui s'empilent", ""),
        ])
        resume = veille.resume_pour_ia(rapport)
        self.assertIn("How do I do this", resume)
        self.assertIn("Mon installation du dimanche", resume)
        self.assertIn("Les boites qui s'empilent", resume)

    def test_les_douleurs_passent_en_premier(self):
        rapport = veille.Veille(niche="x", discussions=[
            veille.Discussion("Une photo de mon frigo", ""),
            veille.Discussion("Help, I am struggling with this", ""),
        ])
        lignes = veille.resume_pour_ia(rapport).splitlines()
        self.assertIn("struggling", lignes[1])

    def test_sans_donnees_le_resume_est_vide(self):
        """Mieux vaut ne rien dire au modele que lui dire « rien trouve »."""
        self.assertEqual(veille.resume_pour_ia(veille.Veille(niche="x")), "")
        self.assertEqual(
            veille.resume_pour_ia(veille.Veille(niche="x",
                                                indisponible="429")), "")

    def test_le_resume_annonce_sa_propre_limite(self):
        rapport = veille.Veille(niche="x", discussions=[
            veille.Discussion("Un titre", "")])
        self.assertIn("non representative", veille.resume_pour_ia(rapport))


if __name__ == "__main__":
    unittest.main()
