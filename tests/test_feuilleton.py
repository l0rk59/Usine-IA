"""Un feuilleton, ce n'est pas un roman decoupe.

Couper un roman en morceaux donne un roman vendu en tranches. Ce qui
distingue le format, c'est que chaque episode doit tenir deux promesses que
le roman n'a pas a tenir : se lire sans avoir relu le precedent, et donner
envie du suivant.

Les deux se verifient sans appeler un modele, et c'est ce que ce module
garde.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("feuilleton")


from usine.core import llm, store  # noqa: E402
from usine.pipelines import base, feuilleton  # noqa: E402
from tests import simulateur  # noqa: E402


class UnEpisodeQuiNOuvreRienNAppellePasLeSuivant(unittest.TestCase):

    def test_les_episodes_sans_suspens_sont_nommes(self):
        episodes = [{"suspens": "qui a vu ?"}, {"suspens": ""},
                    {"suspens": "x"}, {"suspens": ""}]
        self.assertEqual(feuilleton.episodes_sans_suspens(episodes), [2])

    def test_le_dernier_episode_est_exclu_par_construction(self):
        """Il referme l'arc. Lui reclamer un suspens serait lui reclamer une
        saison de plus — et le garde-fou signalerait a tort a chaque fois."""
        self.assertEqual(
            feuilleton.episodes_sans_suspens(
                [{"suspens": "a"}, {"suspens": "b"}, {"suspens": ""}]), [])

    def test_une_saison_entiere_suspendue_ne_declenche_rien(self):
        self.assertEqual(feuilleton.episodes_sans_suspens(
            [{"suspens": "a"}, {"suspens": "b"}, {"suspens": ""}]), [])

    def test_un_seul_episode_n_a_rien_a_ouvrir(self):
        self.assertEqual(feuilleton.episodes_sans_suspens([{"suspens": ""}]), [])


class LeRappelDoitRappelerQuelqueChose(unittest.TestCase):

    CAST = ["Camille Renard", "Hakim Oussaid"]

    def _mesurer(self, episodes):
        return feuilleton.mesurer_les_recaps(episodes, self.CAST)

    def test_le_premier_episode_n_a_rien_a_rappeler(self):
        """L'inclure ferait signaler a tort a chaque saison."""
        mesures = self._mesurer([{"recap": "", "texte": "x " * 100}])
        self.assertEqual(mesures, [])

    def test_un_rappel_qui_ne_nomme_personne_est_signale(self):
        mesures = self._mesurer([
            {"recap": "", "texte": "x " * 100},
            {"recap": "Il s'etait passe des choses.", "texte": "y " * 100}])
        lectures = feuilleton.lire_les_recaps(mesures)
        self.assertTrue(any("ne nomme personne" in l for l in lectures))

    def test_un_rappel_qui_nomme_la_distribution_ne_l_est_pas(self):
        mesures = self._mesurer([
            {"recap": "", "texte": "x " * 100},
            {"recap": "Camille Renard avait pousse la porte.",
             "texte": "y " * 100}])
        self.assertEqual(feuilleton.lire_les_recaps(mesures), [])

    def test_un_rappel_plus_long_qu_un_quart_est_signale(self):
        """Ce n'est plus un rappel : c'est un resume qui prend la place du
        recit."""
        mesures = self._mesurer([
            {"recap": "", "texte": "x " * 100},
            {"recap": "Camille Renard " * 30, "texte": "y " * 100}])
        lectures = feuilleton.lire_les_recaps(mesures)
        self.assertTrue(any("quart" in l for l in lectures))

    def test_un_episode_sans_rappel_du_tout_est_signale(self):
        mesures = self._mesurer([
            {"recap": "", "texte": "x " * 100},
            {"recap": "", "texte": "y " * 100}])
        lectures = feuilleton.lire_les_recaps(mesures)
        self.assertTrue(any("pas de « Precedemment »" in l for l in lectures))

    def test_la_part_se_compte_sur_l_episode_et_non_sur_un_absolu(self):
        """Cinquante mots de rappel sont longs devant deux cents mots
        d'episode, et courts devant deux mille."""
        court = self._mesurer([{"recap": "", "texte": "x " * 100},
                               {"recap": "a " * 50, "texte": "y " * 100}])
        long = self._mesurer([{"recap": "", "texte": "x " * 100},
                              {"recap": "a " * 50, "texte": "y " * 2000}])
        self.assertGreater(court[0]["part"], long[0]["part"])


class LaChaineCompleteViaLeSimulateur(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)
        store.cache_vider()

    def tearDown(self):
        llm.definir_simulateur(None)

    def _produire(self, episodes, sujet="un depot de trains"):
        ctx = base.Contexte(sujet=sujet, sans_image=True, journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = episodes, 140
        return feuilleton.produire(ctx)

    def test_une_saison_sort_sans_alerte_quand_tout_va_bien(self):
        resume = self._produire(3)
        self.assertEqual(resume["episodes"], 3)
        self.assertEqual(resume["episodes_sans_suspens"], [])
        self.assertEqual(resume["lectures"], [])

    def test_chaque_episode_sauf_le_premier_porte_son_rappel(self):
        import json

        resume = self._produire(3, sujet="un port de nuit")
        donnees = json.loads((Path(resume["dossier"]) / "saison.json")
                             .read_text(encoding="utf-8"))
        episodes = donnees["episodes"]
        self.assertFalse(episodes[0]["recap"])
        for episode in episodes[1:]:
            self.assertTrue(episode["recap"].strip(), episode["titre"])

    def test_le_rappel_ne_fabrique_pas_de_section_fantome(self):
        """Le numero d'episode est un titre dans le document rendu. Mesure du
        15/09/2026 : le rappel de l'episode 2 portait « ## Le principe de
        base », qui serait apparu au sommaire entre deux episodes."""
        resume = self._produire(3, sujet="une gare de triage")
        texte = (Path(resume["dossier"]) / "feuilleton.md").read_text(
            encoding="utf-8")
        for ligne in texte.split("\n"):
            if ligne.startswith("## "):
                self.assertTrue(ligne[3:].strip().startswith(("Épisode", "Episode"))
                                or ligne[3:].strip() in ("La saison",),
                                ligne)

    def test_le_nombre_demande_fait_foi(self):
        self.assertEqual(self._produire(4, sujet="un tunnel")["episodes"], 4)


class LesCasQueLeSimulateurNeProduitJamais(unittest.TestCase):
    """Un simulateur cooperatif ne fabrique ni titre parasite ni exces.

    Une campagne de mutation l'a montre : supprimer le nettoyage des titres
    et le plafond du nombre d'episodes ne faisait echouer aucun test. Ces
    chemins ne s'executaient jamais. On fabrique donc les situations a la
    main.
    """

    def tearDown(self):
        llm.definir_simulateur(None)
        store.cache_vider()

    def test_un_titre_dans_le_rappel_ne_ressort_pas_dans_le_livre(self):
        def avec_titre(messages, role):
            invite = messages[-1]["content"]
            if "precedemment" in invite.lower() and "rappel" in invite.lower():
                return ("## Le principe de base\n\nCamille Renard avait "
                        "pousse la porte du depot.")
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(avec_titre)
        ctx = base.Contexte(sujet="un depot a titres", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 140
        resume = feuilleton.produire(ctx)
        texte = (Path(resume["dossier"]) / "feuilleton.md").read_text(
            encoding="utf-8")
        self.assertNotIn("Le principe de base", texte)
        self.assertIn("Camille Renard avait pousse la porte", texte)

    def test_un_modele_trop_genereux_est_ramene_a_la_demande(self):
        import json as _json

        def trop(messages, role):
            invite = messages[-1]["content"]
            if '"suspens"' in invite and '"episodes"' in invite:
                return _json.dumps({
                    "titre": "Saison trop longue", "promesse": "p",
                    "episodes": [
                        {"titre": "Jour {}".format(rang), "question": "q",
                         "evenement": "e",
                         "suspens": "" if rang == 9 else "et apres ?"}
                        for rang in range(1, 10)]})
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(trop)
        ctx = base.Contexte(sujet="un depot trop genereux", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 140
        self.assertEqual(feuilleton.produire(ctx)["episodes"], 3)
