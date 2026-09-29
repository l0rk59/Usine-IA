"""Le registre des faits : ce que le texte affirme, et ce qu'il se contredit.

Le controle de continuite lit la charpente ; celui-ci lit les phrases. Une
heroine aux yeux verts scene deux et aux yeux bleus scene neuf ne casse
aucune structure — et c'est l'erreur de continuite que les lecteurs relevent
le plus.

Ces tests verifient autant ce que le module RATE que ce qu'il trouve : un
garde-fou qui crie a tort n'est plus lu, donc l'attribution devinee est
interdite.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.pipelines import faits  # noqa: E402


def setUpModule():
    atelier.isoler("faits")


class TestNombresEcrits(unittest.TestCase):
    """La fiction ecrit « quarante-deux ans », pas « 42 ans ». Ne lire que les
    chiffres revenait a ne rien lire."""

    def test_les_formes_courantes(self):
        for texte, attendu in (("deux", 2), ("seize", 16), ("trente-deux", 32),
                               ("quarante", 40), ("soixante-dix", 70),
                               ("soixante-quinze", 75), ("quatre-vingts", 80),
                               ("quatre-vingt-deux", 82),
                               ("quatre-vingt-douze", 92), ("cent", 100),
                               ("cent dix", 110)):
            self.assertEqual(faits._nombre_ecrit(texte), attendu, texte)

    def test_la_forme_avec_et(self):
        self.assertEqual(faits._nombre_ecrit("vingt et un"), 21)
        self.assertEqual(faits._nombre_ecrit("soixante et onze"), 71)

    def test_ce_qui_n_est_pas_un_age_est_refuse(self):
        for texte in ("trois cents", "mille", "bonjour", "", "cinq cents"):
            self.assertIsNone(faits._nombre_ecrit(texte), texte)


class TestLectureDeLAge(unittest.TestCase):
    def test_les_trois_ecritures(self):
        self.assertEqual(faits.lire_age("Camille, quarante-cinq ans, se tut."), 45)
        self.assertEqual(faits.lire_age("Il avait 32 ans."), 32)
        self.assertEqual(faits.lire_age("Elle approchait de la quarantaine."), 40)

    def test_un_nombre_d_annees_qui_n_est_pas_un_age(self):
        """« Trois cents ans de solitude » n'est l'age de personne."""
        self.assertIsNone(faits.lire_age("Trois cents ans de solitude."))
        self.assertIsNone(faits.lire_age("La maison a 200 ans."))

    def test_une_phrase_sans_age(self):
        self.assertIsNone(faits.lire_age("Il pleuvait sur le port."))


class TestAttribution(unittest.TestCase):
    """A qui appartiennent « ses yeux verts » ? La reponse n'est sure que
    quand la phrase ne nomme qu'un personnage."""

    def test_un_seul_personnage_nomme(self):
        self.assertEqual(faits.nommes("Camille sourit.", ["Camille", "Lucie"]),
                         ["Camille"])

    def test_deux_personnages_nommes(self):
        trouves = faits.nommes("Camille regarda Lucie.", ["Camille", "Lucie"])
        self.assertEqual(len(trouves), 2)

    def test_le_nom_de_famille_suffit(self):
        """La bible dit « Madame Rivet », le texte ecrit « Rivet »."""
        self.assertEqual(faits.nommes("Rivet entra.", ["Madame Rivet"]),
                         ["Madame Rivet"])

    def test_un_titre_seul_ne_suffit_pas(self):
        self.assertEqual(faits.nommes("Madame attendait.", ["Madame Rivet"]), [])


class TestLectureDesAttributs(unittest.TestCase):
    def test_la_couleur_des_yeux(self):
        self.assertEqual(faits.lire_attributs("ses yeux verts")["yeux"], "vert")
        self.assertEqual(
            faits.lire_attributs("les yeux d'un bleu delave")["yeux"], "bleu")
        self.assertEqual(faits.lire_attributs("son regard noisette")["yeux"],
                         "marron")

    def test_l_accent_ne_change_rien(self):
        self.assertEqual(faits.lire_attributs("ses yeux émeraude")["yeux"], "vert")

    def test_la_couleur_des_cheveux(self):
        self.assertEqual(faits.lire_attributs("sa chevelure rousse")["cheveux"],
                         "roux")

    def test_une_couleur_trop_loin_du_porteur_n_est_pas_rattachee(self):
        """« vert » a quatre-vingts caracteres des yeux ne les qualifie pas."""
        phrase = ("Ses yeux" + " parcoururent la piece encombree de meubles "
                  "et de caisses empilees jusqu'au plafond" + ", puis le "
                  "rideau vert")
        self.assertNotIn("yeux", faits.lire_attributs(phrase))

    def test_une_phrase_sans_attribut(self):
        self.assertEqual(faits.lire_attributs("Il pleuvait."), {})


class TestContradictions(unittest.TestCase):
    NOMS = ["Camille Renard", "Lucie Renard"]

    def _controler(self, sections):
        return faits.controler(sections, self.NOMS)

    def test_deux_couleurs_d_yeux_sont_une_contradiction(self):
        rapport = self._controler([
            ("Scene 1", "Camille leva ses yeux verts."),
            ("Scene 9", "Les yeux bleus de Camille ne cillaient plus."),
        ])
        self.assertEqual(len(rapport["contradictions"]), 1)
        trouvee = rapport["contradictions"][0]
        self.assertEqual(trouvee["gravite"], "majeur")
        self.assertEqual(trouvee["attribut"], "yeux")
        self.assertIn("vert", trouvee["detail"])
        self.assertIn("bleu", trouvee["detail"])

    def test_la_contradiction_cite_les_deux_passages(self):
        """Sans les citations, verifier demande de relire le livre entier."""
        rapport = self._controler([
            ("Scene 1", "Camille leva ses yeux verts."),
            ("Scene 9", "Les yeux bleus de Camille ne cillaient plus."),
        ])
        preuves = rapport["contradictions"][0]["preuves"]
        self.assertEqual(len(preuves), 2)
        self.assertEqual(preuves[0]["section"], "Scene 1")
        self.assertIn("yeux verts", preuves[0]["extrait"])
        self.assertEqual(preuves[1]["section"], "Scene 9")
        self.assertIn("yeux bleus", preuves[1]["extrait"])

    def test_la_meme_couleur_repetee_n_est_pas_une_contradiction(self):
        rapport = self._controler([
            ("Scene 1", "Camille leva ses yeux verts."),
            ("Scene 4", "Camille, les yeux verts brillants, se tut."),
        ])
        self.assertEqual(rapport["contradictions"], [])

    def test_une_teinture_est_signalee_sans_accuser(self):
        """Les cheveux changent pour de bon ; les yeux, non."""
        rapport = self._controler([
            ("Scene 1", "Camille secoua ses cheveux blonds."),
            ("Scene 6", "Camille avait les cheveux noirs, desormais."),
        ])
        self.assertEqual(len(rapport["contradictions"]), 1)
        self.assertEqual(rapport["contradictions"][0]["gravite"], "mineur")
        self.assertIn("peut etre voulu", rapport["contradictions"][0]["detail"])

    def test_deux_ages_eloignes_se_contredisent(self):
        rapport = self._controler([
            ("Scene 1", "Camille, trente ans, poussa la porte."),
            ("Scene 7", "Camille avait quarante-cinq ans et le savait."),
        ])
        genres = [c["attribut"] for c in rapport["contradictions"]]
        self.assertIn("age", genres)

    def test_la_quarantaine_et_quarante_deux_ans_sont_le_meme_fait(self):
        """« La quarantaine » n'est pas un chiffre : l'ecart tolere est d'une
        dizaine, sinon chaque approximation deviendrait une faute."""
        rapport = self._controler([
            ("Scene 1", "Camille approchait de la quarantaine."),
            ("Scene 7", "Camille avait quarante-deux ans."),
        ])
        self.assertEqual(rapport["contradictions"], [])

    def test_une_phrase_a_deux_personnages_n_attribue_rien(self):
        """Deviner a qui appartiennent « ses yeux verts » serait pire que se
        taire : on rate une contradiction plutot que d'en inventer une."""
        rapport = self._controler([
            ("Scene 1", "Camille Renard regarda Lucie Renard, les yeux verts."),
            ("Scene 9", "Camille Renard baissa ses yeux bleus."),
        ])
        self.assertEqual(rapport["contradictions"], [])
        self.assertEqual(rapport["faits"], 1)

    def test_deux_personnages_gardent_chacun_leurs_faits(self):
        rapport = faits.controler([
            ("Scene 1", "Camille Renard avait les yeux verts."),
            ("Scene 2", "Lucie Renard avait les yeux bleus."),
        ], ["Camille Renard", "Lucie Renard"])
        self.assertEqual(rapport["contradictions"], [])
        self.assertEqual(set(rapport["registre"]),
                         {"Camille Renard", "Lucie Renard"})

    def test_un_seul_constat_par_personnage_et_par_attribut(self):
        """Signaler chaque paire d'un attribut cite dix fois noierait le
        constat dans sa propre repetition."""
        sections = [("Scene {}".format(i),
                     "Camille avait les yeux {}.".format(
                         "verts" if i % 2 else "bleus"))
                    for i in range(1, 9)]
        rapport = self._controler(sections)
        self.assertEqual(len(rapport["contradictions"]), 1)

    def test_un_texte_sans_fait_ne_dit_rien(self):
        rapport = self._controler([("Scene 1", "Il pleuvait sur le port.")])
        self.assertEqual(rapport["faits"], 0)
        self.assertEqual(rapport["resume"], "aucune contradiction de fait")


class TestBrancheDansLaChaine(unittest.TestCase):
    """Du code sans appelant ne protege personne."""

    def test_le_controle_de_continuite_remonte_les_contradictions(self):
        from usine.pipelines import nouvelle

        bible = {
            "titre": "Essai", "genre": "drame", "premisse": "",
            "enjeu": "", "fin_visee": "",
            "cadre": {"lieu": "", "epoque": "", "regles": []},
            "personnages": [{"nom": "Camille", "role": "protagoniste",
                             "desir": "", "defaut": "", "voix": ""}],
        }
        grille = {"scenes": [], "fils": [], "arcs": [], "intrigues": []}
        scenes = [("Scene 1", "Camille leva ses yeux verts."),
                  ("Scene 2", "Camille baissa ses yeux bleus.")]
        rapport = nouvelle.controler_continuite(bible, grille, scenes,
                                                ["a", "b"])
        contradictions = [a for a in rapport["anomalies"]
                          if a["genre"] == "fait_contredit"]
        self.assertEqual(len(contradictions), 1)
        self.assertEqual(len(contradictions[0]["preuves"]), 2)
        self.assertEqual(rapport["faits_releves"], 2)


if __name__ == "__main__":
    unittest.main()
