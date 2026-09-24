"""Qui parle, et combien.

La bible donne une voix a chaque personnage, cette voix part dans l'invite de
chaque scene, et rien ne verifiait qu'elle avait ete tenue : une consigne
emise, jamais relue.

Ces tests verifient surtout ce que le module REFUSE de faire — attribuer une
replique qu'il ne sait pas attribuer, et juger ce qu'il n'a pas mesure.
"""

from __future__ import annotations

import sys
import unicodedata
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.pipelines import voix  # noqa: E402


def setUpModule():
    atelier.isoler("voix")


NOMS = ["Camille", "Lucie"]


def _extraire(texte):
    return [(r["personnage"], r["texte"])
            for r in voix.repliques([("Scene 1", texte)], NOMS)]


class TestExtractionDesRepliques(unittest.TestCase):
    def test_le_tiret_cadratin(self):
        self.assertEqual(_extraire("— Tu es en retard, dit Camille."),
                         [("Camille", "Tu es en retard")])

    def test_les_guillemets_francais(self):
        self.assertEqual(_extraire("« Ce n'est pas grave », murmura Camille."),
                         [("Camille", "Ce n'est pas grave")])

    def test_l_incise_sans_virgule(self):
        """« — Vraiment ? demanda Lucie. » : le point d'interrogation ferme la
        replique, il n'y a pas de virgule ou remonter."""
        self.assertEqual(_extraire("— Vraiment ? demanda Lucie."),
                         [("Lucie", "Vraiment ?")])

    def test_l_incise_qui_precede(self):
        self.assertEqual(_extraire('Camille annonca : « Je pars. »'),
                         [("Camille", "Je pars.")])

    def test_un_verbe_de_parole_dans_la_replique(self):
        """« Il m'a dit oui » contient un verbe de parole qui n'est pas
        l'incise : c'est le DERNIER qui ouvre l'incise."""
        self.assertEqual(_extraire("— Il m'a dit oui, murmura Lucie."),
                         [("Lucie", "Il m'a dit oui")])

    def test_l_accent_ne_decale_pas_la_coupe(self):
        """La coupe se fait a une POSITION : un texte accentue doit garder
        les siennes."""
        self.assertEqual(_extraire("— Élise était là, répondit Camille."),
                         [("Camille", "Élise était là")])

    def test_un_accent_decompose_ne_decale_pas_la_coupe(self):
        """Le meme mot s'ecrit de deux facons en Unicode : « é » en un
        caractere, ou « e » suivi d'un accent combinant. Les modeles
        produisent les deux. Chercher la coupe dans une version raccourcie du
        texte la placerait alors quelques caracteres trop loin, et l'incise
        emporterait la fin de la replique.
        """
        aigu, grave = "\u0301", "\u0300"
        # Sans virgule : la coupe tombe alors sur le verbe lui-meme, et c'est
        # la que le decalage se voit. Avec une virgule, la recherche retombe
        # par chance sur la bonne — l'erreur reste, invisible.
        ligne = "— E{a}lise e{a}tait la{g} ? re{a}pondit Camille.".format(
            a=aigu, g=grave)
        trouvees = _extraire(ligne)
        self.assertEqual(len(trouvees), 1)
        self.assertEqual(trouvees[0][0], "Camille")
        # Egalite exacte : trois accents avant le verbe decalent la coupe de
        # trois caracteres, et la replique perdrait sa fin en silence.
        attendu = unicodedata.normalize(
            "NFC", "E{a}lise e{a}tait la{g} ?".format(a=aigu, g=grave))
        self.assertEqual(trouvees[0][1], attendu)

    def test_une_action_apres_une_replique_n_est_pas_une_incise(self):
        """« Non. » Camille recula. — Camille a peut-etre parle, et peut-etre
        reagi a ce qu'un autre vient de dire. Rien ne le dit."""
        self.assertEqual(_extraire('« Non. » Camille recula.'), [])

    def test_une_replique_sans_incise_n_est_pas_attribuee(self):
        """Deviner qui parle serait pire que de perdre la replique."""
        self.assertEqual(_extraire("— Elle a dit non."), [])

    def test_une_incise_a_deux_noms_n_attribue_rien(self):
        self.assertEqual(
            _extraire("— Assez, dit Camille en regardant Lucie."), [])

    def test_un_nom_sans_verbe_de_parole_n_attribue_rien(self):
        """« Camille recula » n'est pas une incise : elle ne dit pas qui
        parle, elle dit ce que fait quelqu'un."""
        self.assertEqual(_extraire("— Non. Camille recula."), [])

    def test_de_la_narration_seule_ne_donne_rien(self):
        self.assertEqual(_extraire("Camille haussa les epaules."), [])


class TestProfil(unittest.TestCase):
    def test_les_mesures_d_une_facon_de_parler(self):
        mesures = voix.profil(["Oui.", "Je ne sais pas encore, vraiment ?",
                               "Non !", "Peut-etre."])
        self.assertEqual(mesures["repliques"], 4)
        self.assertEqual(mesures["questions"], 0.25)
        self.assertEqual(mesures["exclamations"], 0.25)
        self.assertGreater(mesures["mots_moyens"], 1)

    def test_un_personnage_muet_n_a_pas_de_profil(self):
        self.assertEqual(voix.profil([]), {"repliques": 0})


class LesGuillemetsAnglais(unittest.TestCase):
    """“ ” : ceux d'un livre anglais, et ceux qu'un modele pose parfois dans
    un texte francais. Ces repliques passaient pour de la narration."""

    def test_une_replique_francaise_entre_guillemets_anglais(self):
        self.assertEqual(_extraire("“Ce n'est rien”, murmura Camille."),
                         [("Camille", "Ce n'est rien")])

    def test_la_part_de_dialogue_les_compte(self):
        from usine.pipelines import prose

        texte = "“I know,” said Mara. The rain kept on. “Stay here.”"
        self.assertGreater(prose.part_de_dialogue(texte), 0.3)


class HorsDuFrancais(unittest.TestCase):
    """La liste des verbes de parole est francaise. Dans un livre anglais,
    « fit » ou « admit » s'y lisent pour des verbes : UNE replique rattachee
    ainsi, et tous les autres personnages etaient declares muets."""

    PERSONNAGES = [{"nom": "Mara", "role": "protagoniste"},
                   {"nom": "Tom", "role": "secondaire"}]
    TEXTE = ('"Stay," said Mara, fit to burst.\n'
             '"I heard you," Tom answered.\n'
             'Tom looked away.\n')

    def test_rien_n_est_affirme(self):
        rapport = voix.controler([("Scene 1", self.TEXTE)], self.PERSONNAGES,
                                 langue="en")
        self.assertEqual(rapport["anomalies"], [])
        self.assertIn("francais", rapport["resume"])

    def test_la_chaine_transmet_la_langue_du_livre(self):
        from unittest import mock

        from tests.simulateur import simulateur
        from usine.core import llm
        from usine.pipelines import nouvelle
        from usine.pipelines.base import Contexte

        llm.definir_simulateur(simulateur)
        try:
            with mock.patch.object(voix, "controler",
                                   wraps=voix.controler) as espion:
                nouvelle.produire(Contexte(
                    sujet="the lighthouse keeper", langue="anglais",
                    sans_image=True, hors_ligne=True, qualite="rapide",
                    journal=lambda _m: None))
        finally:
            llm.definir_simulateur(None)
        self.assertTrue(espion.called)
        self.assertEqual(espion.call_args.kwargs.get("langue"), "en")

    def test_le_defaut_qu_on_evite_existe_bien(self):
        """Le meme texte lu comme du francais : Tom, qui parle, est declare
        muet. C'est ce que le parametre de langue empeche."""
        rapport = voix.controler([("Scene 1", self.TEXTE)], self.PERSONNAGES)
        self.assertTrue([a for a in rapport["anomalies"]
                         if a["genre"] == "personnage_muet"
                         and "Tom" in a["detail"]])


class TestControle(unittest.TestCase):
    PERSONNAGES = [{"nom": "Camille", "role": "protagoniste"},
                   {"nom": "Lucie", "role": "secondaire"}]

    def _controler(self, texte):
        return voix.controler([("Scene 1", texte)], self.PERSONNAGES)

    def test_un_personnage_present_qui_ne_parle_jamais(self):
        rapport = self._controler(
            "— Bonjour, dit Camille.\n"
            "— Encore, dit Camille.\n"
            "Lucie ne repondit pas.\n")
        muets = [a for a in rapport["anomalies"]
                 if a["genre"] == "personnage_muet"]
        self.assertEqual(len(muets), 1)
        self.assertIn("Lucie", muets[0]["detail"])
        self.assertEqual(muets[0]["gravite"], "mineur")

    def test_un_protagoniste_muet_est_plus_grave(self):
        rapport = self._controler(
            "— Bonjour, dit Lucie.\n"
            "— Encore, dit Lucie.\n"
            "Camille regarda ailleurs.\n")
        muets = [a for a in rapport["anomalies"]
                 if a["genre"] == "personnage_muet"]
        self.assertEqual(muets[0]["gravite"], "majeur")

    def test_un_personnage_absent_du_texte_n_est_pas_dit_muet(self):
        """Son absence est deja signalee par le controle de continuite ;
        la repeter sous un autre nom ferait deux alertes pour un defaut."""
        rapport = self._controler("— Bonjour, dit Camille.\n"
                                  "— Encore, dit Camille.\n")
        self.assertEqual([a for a in rapport["anomalies"]
                          if "Lucie" in a["detail"]], [])

    def test_un_recit_sans_dialogue_n_accuse_personne(self):
        """Une nouvelle entierement narrative est un choix, pas un defaut."""
        rapport = self._controler("Camille marchait. Lucie la suivait.")
        self.assertEqual(rapport["anomalies"], [])
        self.assertEqual(rapport["resume"], "aucun dialogue attribue")

    def test_la_parole_confisquee(self):
        texte = "".join("— Replique {}, dit Camille.\n".format(i)
                        for i in range(9))
        texte += "— Un mot, dit Lucie.\n"
        rapport = self._controler(texte)
        confisquee = [a for a in rapport["anomalies"]
                      if a["genre"] == "parole_confisquee"]
        self.assertEqual(len(confisquee), 1)
        self.assertIn("Camille", confisquee[0]["detail"])
        self.assertIn("90 %", confisquee[0]["detail"])

    def test_un_dialogue_equilibre_ne_dit_rien(self):
        texte = "".join("— Oui, dit Camille.\n— Non, dit Lucie.\n"
                        for _ in range(4))
        self.assertEqual(self._controler(texte)["anomalies"], [])

    def test_trop_peu_de_repliques_pour_comparer(self):
        """Trois repliques ne font pas une voix : le module dit sur combien
        de personnages la comparaison aurait un sens."""
        rapport = self._controler("— Oui, dit Camille.\n— Non, dit Lucie.\n")
        self.assertEqual(rapport["comparables"], [])

    def test_aucun_verdict_sur_la_ressemblance_des_voix(self):
        """Le declarer demanderait un seuil qui n'a pas ete mesure.

        Les profils sont rendus, et c'est un humain qui les regarde. Ce test
        existe pour que personne n'ajoute ce verdict sans la mesure.
        """
        texte = "".join("— Oui, dit Camille.\n— Oui, dit Lucie.\n"
                        for _ in range(5))
        rapport = self._controler(texte)
        self.assertEqual(rapport["anomalies"], [])
        self.assertEqual(sorted(rapport["comparables"]), ["Camille", "Lucie"])
        self.assertEqual(rapport["profils"]["Camille"]["mots_moyens"],
                         rapport["profils"]["Lucie"]["mots_moyens"])


class TestBrancheDansLaChaine(unittest.TestCase):
    def test_le_controle_de_continuite_remonte_les_muets(self):
        from usine.pipelines import nouvelle

        bible = {
            "titre": "Essai", "genre": "", "premisse": "", "enjeu": "",
            "fin_visee": "", "cadre": {"lieu": "", "epoque": "", "regles": []},
            "personnages": [
                {"nom": "Camille", "role": "protagoniste", "desir": "",
                 "defaut": "", "voix": ""},
                {"nom": "Lucie", "role": "secondaire", "desir": "",
                 "defaut": "", "voix": ""},
            ],
        }
        grille = {"scenes": [], "fils": [], "arcs": [], "intrigues": []}
        scenes = [("Scene 1", "— Bonjour, dit Camille.\nLucie se tut."),
                  ("Scene 2", "— Encore, dit Camille.\nLucie sortit.")]
        rapport = nouvelle.controler_continuite(bible, grille, scenes,
                                                ["a", "b"])
        muets = [a for a in rapport["anomalies"]
                 if a["genre"] == "personnage_muet"]
        self.assertEqual(len(muets), 1)
        self.assertEqual(rapport["parole"]["repliques"], 2)


if __name__ == "__main__":
    unittest.main()
