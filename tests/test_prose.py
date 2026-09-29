"""La phrase, que la charpente ne regardait pas.

Trois controles de fiction existaient : « faits » tient le registre de ce qui
a ete affirme, « voix » rattache les repliques a qui les prononce,
« nouvelle.controler_continuite » lit la charpente. Tous trois regardent la
STRUCTURE.

Aucun ne regardait la phrase. Or c'est la que se voit, d'une ligne, qu'un
texte a ete genere : le mot filtre qui met une conscience entre la scene et
le lecteur, l'emotion nommee au lieu d'etre montree, le meme adverbe onze
fois, l'incise qui cherche un synonyme de « dit » a chaque replique.

Ce que ce module verifie surtout : que le controle NE CRIE PAS A TORT. Un
personnage a le droit de dire « je suis triste », un narrateur a le droit
d'ecrire « un moment plus tard », et aucun des deux ne doit compter.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("prose")


from usine.core import llm  # noqa: E402
from usine.pipelines import base, prose  # noqa: E402
from tests import simulateur  # noqa: E402


class LeReleveNePortePasSurLesRepliques(unittest.TestCase):
    """Le point ou un controle de prose devient un garde-fou qui crie a tort."""

    def test_un_personnage_a_le_droit_de_dire_qu_il_est_triste(self):
        texte = ("La porte claqua.\n\n"
                 "— Je suis triste, dit Camille.\n\n"
                 "Elle sortit.")
        self.assertEqual(prose.emotions_nommees(texte), [])

    def test_un_personnage_a_le_droit_de_dire_tu_vois_bien_que(self):
        texte = "— Tu vois bien que j'ai raison, dit Hakim."
        self.assertEqual(prose.mots_filtres(texte), [])

    def test_les_guillemets_francais_comptent_aussi_comme_du_dialogue(self):
        texte = "Il hesita. « Elle etait triste », pensa-t-il."
        self.assertEqual(prose.emotions_nommees(texte), [])

    def test_la_narration_autour_du_dialogue_reste_mesuree(self):
        texte = ("Il etait furieux.\n\n"
                 "— Je pars, dit Camille.\n\n"
                 "Elle vit que la lampe brulait encore.")
        self.assertEqual(len(prose.emotions_nommees(texte)), 1)
        self.assertEqual(len(prose.mots_filtres(texte)), 1)


class LeMotFiltreExigeSaConstruction(unittest.TestCase):
    """« Que » n'est pas une commodite d'ecriture : c'est ce qui rend sur."""

    def test_le_verbe_suivi_de_que_est_releve(self):
        for phrase in ("Elle vit que la porte etait ouverte.",
                       "Il sentit que le sol tremblait.",
                       "Elle se rendit compte qu'il mentait.",
                       "Il s'apercut que la cle manquait."):
            self.assertEqual(len(prose.mots_filtres(phrase)), 1, phrase)

    def test_le_meme_verbe_sans_que_n_est_pas_releve(self):
        # « Elle sentit le froid » EST un mot filtre. Ce module le RATE, et
        # c'est le choix du depot : rater un defaut plutot que d'en inventer.
        self.assertEqual(prose.mots_filtres("Elle sentit le froid."), [])

    def test_vivre_n_est_pas_voir(self):
        # « Il vit a Rouen » : le meme mot que le passe simple de « voir ».
        # Sans l'exigence du « que », ce detecteur signalerait chaque
        # personnage qui habite quelque part.
        self.assertEqual(prose.mots_filtres("Il vit a Rouen depuis dix ans."),
                         [])

    def test_la_phrase_entiere_est_rendue_pas_le_verbe_seul(self):
        # Un compte sans son extrait ne se verifie pas : il faut pouvoir lire
        # ce qui a ete compte pour savoir si le compte a raison.
        releve = prose.mots_filtres("Elle vit que la porte etait ouverte.")
        self.assertEqual(releve, ["Elle vit que la porte etait ouverte."])


class LEmotionNommeeNEstPasTouteQualification(unittest.TestCase):

    def test_un_etat_emotionnel_est_releve(self):
        self.assertEqual(len(prose.emotions_nommees("Il etait furieux.")), 1)
        self.assertEqual(
            len(prose.emotions_nommees("Elle se sentit tres coupable.")), 1)

    def test_une_qualite_qui_n_est_pas_une_emotion_ne_l_est_pas(self):
        # « Il etait grand » n'est pas un defaut d'ecriture. Relever tout
        # « etait + adjectif » ferait crier le controle a chaque description.
        for phrase in ("Il etait grand.", "Elle etait medecin.",
                       "La porte etait ouverte.", "Il etait tard."):
            self.assertEqual(prose.emotions_nommees(phrase), [], phrase)


class LesMotsEnMentSontRenduSansEtreClasses(unittest.TestCase):
    """Le refus de classer est la decision, pas un manque."""

    def test_les_noms_et_les_adverbes_sont_comptes_ensemble(self):
        # « Gouvernement » est un nom et sort compte comme « doucement ».
        # C'est assume : les separer demanderait un dictionnaire.
        comptes = prose.mots_en_ment("Le gouvernement recula. Doucement.")
        self.assertEqual(comptes, {"gouvernement": 1, "doucement": 1})

    def test_les_noms_les_plus_courts_sont_ecartes_par_la_longueur(self):
        # Quatre lettres avant « -ment ». « Moment » et « ciment »
        # reviendraient sinon en tete de chaque releve de roman.
        self.assertEqual(prose.mots_en_ment("Un moment, un ciment."), {})

    def test_seul_ce_qui_se_repete_est_rapporte(self):
        texte = " ".join(["Doucement."] * prose.REPETITIONS_MONTREES
                         + ["Vivement."])
        mesure = prose.mesurer_la_prose([("S1", texte)])
        self.assertIn("doucement", mesure["mots_en_ment_repetes"])
        self.assertNotIn("vivement", mesure["mots_en_ment_repetes"])

    def test_un_mot_trop_court_n_est_pas_un_mot_en_ment(self):
        # « ment » et « dement » ne sont pas la construction cherchee.
        self.assertEqual(prose.mots_en_ment("Il ment."), {})


class LesIncisesSontComptees(unittest.TestCase):

    TEXTE = ("— Je viens, dit Camille.\n"
             "— Jamais, s'exclama Hakim.\n"
             "— Peut-etre, murmura Lucie.\n"
             "Il murmura quelque chose en refermant la porte.\n")

    def test_la_part_de_dit_est_rendue(self):
        mesure = prose.incises(self.TEXTE)
        self.assertEqual(mesure["incises"], 3)
        self.assertEqual(mesure["avec_dit"], 1)
        self.assertAlmostEqual(mesure["part_de_dit"], 0.333, places=2)

    def test_les_verbes_evites_sont_nommes(self):
        self.assertEqual(set(prose.incises(self.TEXTE)["autres_verbes"]),
                         {"s'exclama", "murmura"})

    def test_un_verbe_de_parole_hors_replique_n_est_pas_une_incise(self):
        # La derniere ligne du texte porte « murmura » en pleine narration.
        # La compter gonflerait le releve d'un verbe qui n'introduit rien.
        self.assertEqual(prose.incises(self.TEXTE)["incises"], 3)


class LaPartDeDialogueSeSitueSansSeJuger(unittest.TestCase):
    """L'ecart mesure entre Woolf et Christie interdit tout verdict."""

    def test_un_texte_sans_replique_rend_zero(self):
        self.assertEqual(prose.part_de_dialogue("Il pleuvait sur la lande."),
                         0.0)

    def test_un_texte_tout_en_repliques_rend_presque_un(self):
        self.assertGreater(
            prose.part_de_dialogue("— Viens.\n— Non.\n— Viens."), 0.8)

    def test_la_phrase_situe_et_ne_juge_pas(self):
        for part in (0.03, 0.30, 0.50, 0.79):
            phrase = prose.situer_le_dialogue(part)
            self.assertIn("%", phrase)
            # Aucun mot de verdict : la phrase place le texte parmi des
            # romans reellement mesures, elle ne dit pas s'il a raison.
            for verdict in ("trop", "pas assez", "insuffisant", "excessif"):
                self.assertNotIn(verdict, phrase.lower())

    def test_les_reperes_cites_portent_leur_source(self):
        self.assertIn("Liberman", prose.SOURCES["dialogue"])
        self.assertIn("Blatt", prose.SOURCES["adverbes"])


class LesQuatreChainesDeProseLaMesurent(unittest.TestCase):
    """Un module que personne n'appelle ne protege personne."""

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _contexte(self, sujet):
        ctx = base.Contexte(sujet=sujet, sans_image=True, hors_ligne=True,
                            journal=lambda m: None)
        return ctx

    def test_le_recueil_mesure_la_prose_de_ses_recits(self):
        from usine.pipelines import recueil

        ctx = self._contexte("des gares de nuit")
        ctx.chapitres = 3
        resume = recueil.produire(ctx, recits=3)
        self.assertIn("part_de_dialogue", resume["prose"])
        self.assertGreater(resume["prose"]["mots"], 0)

    def test_le_feuilleton_mesure_la_prose_de_ses_episodes(self):
        from usine.pipelines import feuilleton

        ctx = self._contexte("un hotel hors saison")
        resume = feuilleton.produire(ctx, episodes=3)
        self.assertIn("part_de_dialogue", resume["prose"])

    def test_le_livre_jeu_mesure_la_prose_de_ses_sections(self):
        from usine.pipelines import interactive

        ctx = self._contexte("une mine noyee")
        ctx.chapitres, ctx.mots_section = 12, 150
        resume = interactive.produire(ctx)
        self.assertIn("part_de_dialogue", resume["prose"])

    def test_la_mesure_de_prose_n_est_pas_un_verdict_de_la_chaine(self):
        """Elle est rangee a part de « lectures ».

        Les fondre ensemble faisait passer pour alerte un produit sain : un
        feuilleton correct sortait « en alerte » parce que le mot
        « exactement » revenait neuf fois. C'est un fait sur le texte, pas un
        defaut de la saison.
        """
        from usine.pipelines import feuilleton

        ctx = self._contexte("un phare et sa releve")
        resume = feuilleton.produire(ctx, episodes=3)
        self.assertIn("lectures_prose", resume)
        for ligne in resume["lectures"]:
            self.assertNotIn("-ment", ligne)


if __name__ == "__main__":
    unittest.main()
