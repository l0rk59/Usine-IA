"""L'usine produit depuis ZERO : elle decide, on ne remplit rien.

C'est sa raison d'etre — des appels d'API, un sujet, et un produit. Pas un
formulaire de dix menus qu'un humain remplit.

Mesure du 15/09/2026, avant correction. Le brief automatique decidait TROIS
choses : audience, ton, taille. Tout le reste tombait sur une valeur en dur,
et en silence :

    social      reseau      toujours « linkedin »
    emails      intention   toujours « bienvenue »
    quiz        niveau      toujours « intermediaire »
    logiciel    cible       toujours « cli »
    conte       tranche     toujours « 6-8 ans »

Cinq de ces champs n'offraient meme pas d'option vide : on ne POUVAIT pas
dire « que l'usine decide ». Et pour la fiction, aucun des neuf reglages de
promesse n'etait decide — le modele ecrivait sans contrat de genre.

Un reglage par defaut n'est pas neutre, il est juste invisible.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("depuis-zero")


from usine.core import llm  # noqa: E402
from usine.pipelines import base, brief, catalogue, fiction  # noqa: E402
from tests import simulateur  # noqa: E402


class AucunChoixNEstImpose(unittest.TestCase):

    def test_tout_champ_de_choix_offre_de_laisser_l_usine_decider(self):
        forces = [(t.cle, c.nom) for t in catalogue.TYPES
                  for c in (t.champs or ())
                  if c.genre == "choix" and "" not in (c.choix or ())]
        self.assertEqual(forces, [], (
            "Ces champs imposent une valeur : on ne peut pas dire « que "
            "l'usine decide ». {}".format(forces)))

    def test_aucun_champ_faconnant_le_produit_n_a_de_valeur_en_dur(self):
        en_dur = [(t.cle, c.nom, c.defaut) for t in catalogue.TYPES
                  for c in (t.champs or ())
                  if c.genre == "choix" and c.defaut not in ("", None)]
        self.assertEqual(en_dur, [], en_dur)


class LUsineDecideCeQuiFaconneLeProduit(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _decider(self, cle, sujet, options=None):
        self.lignes = []
        contexte = base.Contexte(sujet=sujet, sans_image=True,
                                 journal=self.lignes.append)
        return brief.decider_les_reglages(
            contexte, catalogue.obtenir(cle), options or {})

    def test_un_pack_de_posts_ne_part_plus_toujours_sur_linkedin(self):
        decides = self._decider("social", "la facturation des independants")
        self.assertIn("reseau", decides)
        self.assertIn(decides["reseau"], ("x", "linkedin", "instagram",
                                          "tiktok"))

    def test_le_niveau_d_un_quiz_est_decide_d_apres_le_sujet(self):
        self.assertIn("niveau", self._decider("quiz", "le droit du travail"))

    def test_la_fiction_recoit_un_contrat_de_genre_complet(self):
        decides = self._decider("nouvelle", "un phare et sa releve")
        for reglage in ("genre", "ambiance", "point_de_vue", "temps", "fin",
                        "structure"):
            self.assertIn(reglage, decides, reglage)

    def test_une_valeur_choisie_par_l_utilisateur_n_est_jamais_touchee(self):
        decides = self._decider("quiz", "le droit du travail",
                                {"niveau": "avance"})
        self.assertNotIn("niveau", decides)

    def test_la_decision_se_lit_dans_le_journal(self):
        """Une decision qu'on ne retrouve pas ne vaut pas mieux qu'un defaut
        invisible : c'est la meme opacite, avec une etape en plus."""
        self._decider("quiz", "le droit du travail")
        journal = "\n".join(self.lignes)
        self.assertIn("L'usine décide", journal)
        self.assertIn("niveau", journal)

    def test_une_valeur_hors_liste_est_ecartee_et_non_corrigee(self):
        """Accepter « thriller psychologique » la ou le champ attend
        « thriller » ferait entrer dans la fiche une valeur que rien d'autre
        ne sait relire."""
        def hors_liste(messages, role):
            if "Ces reglages n'ont pas ete choisis" in messages[-1]["content"]:
                return '{"niveau": "tres tres avance", "nombre": 12}'
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(hors_liste)
        decides = self._decider("quiz", "la retraite progressive")
        self.assertNotIn("niveau", decides)
        self.assertEqual(decides.get("nombre"), 12)

    def test_un_modele_muet_laisse_les_reglages_vides_et_le_dit(self):
        """Un reglage a moitie devine serait pire que pas de reglage : on
        croirait que le sujet a ete lu."""
        def muet(messages, role):
            raise RuntimeError("aucun fournisseur")

        llm.definir_simulateur(muet)
        self.assertEqual(self._decider("quiz", "la rupture conventionnelle"),
                         {})
        self.assertIn("n'a pas pu décider", "\n".join(self.lignes))


class CeQueLUsineNeDecidePas(unittest.TestCase):
    """Elle decide le PRODUIT, pas ce que l'utilisateur veut depenser."""

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _decider(self, cle, sujet):
        contexte = base.Contexte(sujet=sujet, sans_image=True,
                                 journal=lambda m: None)
        return brief.decider_les_reglages(contexte, catalogue.obtenir(cle), {})

    def test_une_nouvelle_isolee_ne_recoit_pas_de_nom_de_serie(self):
        # Un champ « serie » vide est un recit isole. La premiere version
        # faisait inventer un nom de serie a chaque nouvelle.
        self.assertNotIn("serie", self._decider("nouvelle", "un phare"))

    def test_l_usine_ne_decide_pas_de_sauter_une_etape(self):
        # Une case « ne pas mesurer le marche » decochee veut dire « fais-le ».
        decides = self._decider("idees", "la facturation")
        for case in ("sans_marche", "sans_veille"):
            self.assertNotIn(case, decides, case)

    def test_l_usine_ne_decide_pas_de_depenser_des_images(self):
        self.assertNotIn("visuels", self._decider("social", "la facturation"))

    def test_l_usine_ne_decide_pas_la_marge_de_l_imprimeur(self):
        # La marge depend de l'imprimeur, pas du sujet.
        self.assertNotIn("reliure", self._decider("impression", "un planning"))


class LaDecisionArriveJusquALaChaine(unittest.TestCase):
    """Decider et ne pas transmettre serait la pire des deux situations."""

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_la_promesse_de_fiction_decidee_parvient_a_la_chaine(self):
        contexte = base.Contexte(sujet="un phare et sa releve",
                                 sans_image=True, journal=lambda m: None)
        contexte.chapitres = 3
        try:
            catalogue.executer("nouvelle", contexte, {})
        except Exception:
            pass          # ce qu'on mesure est la promesse, pas le produit
        promesse = fiction.promesse_du_contexte(contexte)
        self.assertTrue(promesse, (
            "l'usine a decide un genre, une ambiance et une fin — et la "
            "chaine ecrit sans les voir"))
        self.assertTrue(promesse.get("genre"))

    def test_la_decision_est_rangee_dans_la_fiche_du_produit(self):
        """Une decision qu'on ne retrouve plus six mois apres n'aide pas a
        comprendre le resultat."""
        contexte = base.Contexte(sujet="le droit du travail", sans_image=True,
                                 journal=lambda m: None)
        try:
            catalogue.executer("quiz", contexte, {})
        except Exception:
            pass
        self.assertTrue(contexte.meta.get("reglages_decides"))


if __name__ == "__main__":
    unittest.main()
