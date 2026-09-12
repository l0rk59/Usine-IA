"""Ce que les agents font vraiment : relecture croisee et lecture d'ensemble.

Deux choses manquaient. La chaine ANNONCE une relecture par un autre modele
sans pouvoir le prouver — et l'ecart existe : quand un seul fournisseur est
configure, « eviter » se desactive pour ne pas perdre la relecture. Et aucun
agent ne lit le produit ENTIER : chacun travaille section par section, si
bien que deux chapitres peuvent se contredire sans que rien ne le voie.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from unittest import mock  # noqa: E402

from usine.agents import base as base_agents  # noqa: E402
from usine.agents import equipe  # noqa: E402
from usine.agents.base import Critique  # noqa: E402
from usine.core import llm, reglages, store  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402


def setUpModule():
    atelier.isoler("agents")
    llm.definir_simulateur(simulateur)
    reglages.ecrire({"images": False, "qualite": "rapide"})


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte():
    return Contexte(sujet="la prospection", hors_ligne=True,
                    journal=lambda message: None)


class TestRelectureCroisee(unittest.TestCase):
    """Mesuree, pas affirmee."""

    def test_deux_modeles_differents_font_une_relecture_croisee(self):
        critique = Critique(note=8.0, fournisseur_auteur="groq",
                            fournisseur_relecteur="mistral")
        self.assertTrue(critique.croisee)

    def test_le_meme_modele_ne_la_fait_pas(self):
        critique = Critique(note=8.0, fournisseur_auteur="groq",
                            fournisseur_relecteur="groq")
        self.assertFalse(critique.croisee)

    def test_un_fournisseur_inconnu_ne_compte_pas_pour_une_croisee(self):
        """Ne rien savoir n'est pas une preuve : c'est l'absence de preuve."""
        self.assertFalse(Critique(note=8.0, fournisseur_relecteur="groq").croisee)
        self.assertFalse(Critique(note=8.0, fournisseur_auteur="groq").croisee)

    def test_la_critique_retient_qui_a_ecrit_et_qui_a_relu(self):
        critique = equipe.critiquer(_contexte(), "Du texte a relire.", "Un titre",
                                    fournisseur_auteur="un-autre-modele")
        self.assertEqual(critique.fournisseur_auteur, "un-autre-modele")
        self.assertEqual(critique.fournisseur_relecteur, "simulateur")
        self.assertTrue(critique.croisee)

    def test_le_rapport_chiffre_la_part_reellement_croisee(self):
        rapport = equipe.rapport_qualite({
            "A": [Critique(note=6.0, fournisseur_auteur="groq",
                           fournisseur_relecteur="mistral")],
            "B": [Critique(note=7.0, fournisseur_auteur="groq",
                           fournisseur_relecteur="groq")],
        })
        mesure = rapport["relecture_croisee"]
        self.assertEqual(mesure["relectures"], 2)
        self.assertEqual(mesure["sur_un_autre_modele"], 1)
        self.assertEqual(mesure["part"], 0.5)

    def test_sans_relecture_la_part_n_est_pas_inventee(self):
        rapport = equipe.rapport_qualite({"A": []})
        self.assertIsNone(rapport["relecture_croisee"]["part"])


class TestRelectureDEnsemble(unittest.TestCase):
    """Ce qu'aucune section ne peut voir depuis sa place."""

    SECTIONS = [("Chapitre un", "Le tarif de depart est de 320 euros."),
                ("Chapitre deux", "Le tarif de depart est de 450 euros."),
                ("Chapitre trois", "Encore du texte sur autre chose.")]

    def test_elle_trouve_une_contradiction_entre_sections(self):
        rapport = equipe.relire_l_ensemble(_contexte(), self.SECTIONS,
                                           promesse="une promesse")
        self.assertTrue(rapport["disponible"])
        self.assertEqual(rapport["majeures"], 1)
        self.assertIn("tarif", rapport["incoherences"][0]["probleme"])

    def test_elle_ecarte_une_section_que_le_modele_invente(self):
        """Citer une section inexistante rendrait le rapport inutilisable.

        Le modele le fait : il renvoie ici une incoherence qui designe « Un
        chapitre qui n'existe pas ». Le probleme est conserve — il peut etre
        vrai — mais la reference fausse ne doit pas l'etre.
        """
        rapport = equipe.relire_l_ensemble(_contexte(), self.SECTIONS)
        reels = [t for t, _ in self.SECTIONS]
        invente = [s for s in rapport["incoherences"]
                   if "absente du produit" in s["probleme"]]
        self.assertTrue(invente, "le cas n'a pas ete exerce")
        self.assertEqual(invente[0]["sections"], [],
                         "la section inventee devait etre retiree")
        for souci in rapport["incoherences"]:
            for titre in souci["sections"]:
                self.assertIn(titre, reels)

    def test_elle_ignore_les_entrees_sans_probleme(self):
        rapport = equipe.relire_l_ensemble(_contexte(), self.SECTIONS)
        self.assertTrue(all(s["probleme"] for s in rapport["incoherences"]))

    def test_un_produit_d_une_seule_section_ne_la_declenche_pas(self):
        """Rien ne peut se contredire tout seul."""
        self.assertEqual(equipe.relire_l_ensemble(_contexte(), [("A", "x")]), {})

    def test_un_echec_du_modele_ne_leve_pas(self):
        def tomber(messages, role):
            raise RuntimeError("le modele n'a pas repondu")

        # Des sections DIFFERENTES de celles des autres tests : les reponses
        # sont mises en cache par empreinte de l'invite, et un texte deja vu
        # serait servi sans que le simulateur en echec soit consulte.
        sections = [("Section inedite un", "du texte jamais soumis"),
                    ("Section inedite deux", "un autre texte inedit")]
        llm.definir_simulateur(tomber)
        try:
            rapport = equipe.relire_l_ensemble(_contexte(), sections)
        finally:
            llm.definir_simulateur(simulateur)
        self.assertFalse(rapport["disponible"])
        self.assertIn("raison", rapport)


class TestDansLaChaine(unittest.TestCase):
    def _ebook(self, **kwargs):
        from usine.pipelines import ebook

        return ebook.produire(Contexte(
            sujet="la prospection", taille="mini", qualite="rapide",
            hors_ligne=True, sans_image=True, journal=lambda message: None),
            **kwargs)

    def test_sans_l_option_aucun_appel_de_plus(self):
        """Un appel de modele par produit ne s'impose pas."""
        import json

        resume = self._ebook()
        rapport = json.loads(
            (Path(resume["dossier"]) / "rapport-qualite.json").read_text(
                encoding="utf-8"))
        self.assertNotIn("ensemble", rapport)

    def test_avec_l_option_le_rapport_porte_la_relecture(self):
        import json

        resume = self._ebook(relecture_ensemble=True)
        rapport = json.loads(
            (Path(resume["dossier"]) / "rapport-qualite.json").read_text(
                encoding="utf-8"))
        self.assertIn("ensemble", rapport)
        self.assertTrue(rapport["ensemble"]["disponible"])

    def test_l_option_est_declaree_au_catalogue(self):
        from usine.pipelines import catalogue

        self.assertIn("relecture_ensemble", catalogue.obtenir("ebook").options)


class TestPlafondDeJetons(unittest.TestCase):
    """Le calcul etait recopie partout, et coupait le sur-mesure en silence."""

    def test_les_paliers_tiennent_dans_le_plafond(self):
        from usine.pipelines.base import JETONS_MAX, jetons_pour, resoudre_taille

        for taille in ("mini", "court", "standard", "long"):
            _, mots = resoudre_taille(taille)
            self.assertLess(jetons_pour(mots), JETONS_MAX, taille)

    def test_le_sur_mesure_le_plus_long_est_desormais_servi(self):
        """Avant : 4096 jetons demandes pour 4000 mots, soit 40 % du texte."""
        from usine.pipelines.base import MOTS_MAX, jetons_pour

        self.assertGreater(jetons_pour(MOTS_MAX), 4096)

    def test_le_plafond_reste_borne(self):
        from usine.pipelines.base import JETONS_MAX, jetons_pour

        self.assertEqual(jetons_pour(100000), JETONS_MAX)
        self.assertGreaterEqual(jetons_pour(1), 512)

    def test_une_reecriture_peut_rendre_ce_qu_elle_recoit(self):
        """L'ancien plafond rejetait la correction d'un chapitre long.

        La correction recoit au plus quatorze mille caracteres — elle tronque
        elle-meme au-dela. C'est donc CETTE taille que le plafond doit
        couvrir, et l'ancien 4096 ne la couvrait pas.
        """
        from usine.pipelines.base import JETONS_MAX

        recu_maximum = "x" * 14000
        plafond = equipe._plafond_reecriture(recu_maximum, 1200)
        self.assertGreater(plafond, 4096, "l'ancien plafond etait insuffisant")
        self.assertGreaterEqual(plafond, len(recu_maximum) // 2)
        self.assertLessEqual(plafond, JETONS_MAX,
                             "jamais plus que ce qu'un fournisseur emet")


if __name__ == "__main__":
    unittest.main()


class TestTroncatureRemontee(unittest.TestCase):
    """Une reponse coupee au plafond de jetons doit se VOIR.

    Le routeur la detecte depuis longtemps et refuse de la mettre en cache,
    pour ne pas figer la coupure. Mais il le savait tout seul : ni le journal,
    ni la fiche du produit, ni le tableau de bord n'en portaient trace. Un
    chapitre tranche au milieu d'une phrase traversait donc toute la
    fabrication en passant pour termine — exactement le defaut que la
    detection etait censee rendre visible.
    """

    def _contexte(self):
        dits = []
        ctx = Contexte(sujet="un sujet", journal=dits.append)
        return ctx, dits

    def _reponse(self, tronquee):
        return llm.Reponse(texte="du texte", fournisseur="groq",
                           modele="openai/gpt-oss-120b", tronquee=tronquee)

    def test_le_journal_le_dit_tout_de_suite(self):
        """Pendant qu'il est encore temps de reduire la longueur demandee."""
        ctx, dits = self._contexte()
        base_agents.signaler_troncature(ctx, "redacteur", self._reponse(True))
        self.assertTrue(any("coupee au plafond" in d for d in dits))
        self.assertTrue(any("redacteur" in d for d in dits))

    def test_le_contexte_accumule_pour_le_rapport(self):
        ctx, _ = self._contexte()
        base_agents.signaler_troncature(ctx, "redacteur", self._reponse(True))
        base_agents.signaler_troncature(ctx, "reviseur", self._reponse(True))
        self.assertEqual(len(ctx.meta["tronquees"]), 2)
        self.assertEqual(ctx.meta["tronquees"][0]["fournisseur"], "groq")

    def test_un_agent_signale_quand_la_reponse_est_coupee(self):
        """Le cablage : c'est « travailler » qui doit appeler le signalement,
        sinon la fonction ne protege personne."""
        ctx, dits = self._contexte()
        with mock.patch.object(llm, "generer", return_value=self._reponse(True)):
            equipe.REDACTEUR.travailler(ctx, "ecris")
        self.assertTrue(any("coupee au plafond" in d for d in dits))
        self.assertEqual(len(ctx.meta.get("tronquees") or []), 1)

    def test_une_reponse_complete_ne_dit_rien(self):
        ctx, dits = self._contexte()
        with mock.patch.object(llm, "generer", return_value=self._reponse(False)):
            equipe.REDACTEUR.travailler(ctx, "ecris")
        self.assertEqual(dits, [])
        self.assertEqual(ctx.meta.get("tronquees"), None)

    def test_un_contexte_sans_journal_ne_fait_pas_echouer(self):
        """Toutes les chaines ne passent pas un Contexte complet."""
        class Minimal:
            pass

        base_agents.signaler_troncature(Minimal(), "agent", self._reponse(True))

    def test_la_fiche_du_produit_porte_le_compte(self):
        """Le rapport du produit livre doit dire combien de sections sont
        concernees : c'est ce qu'on lit apres coup, pas le journal."""
        from usine.pipelines.base import preparer, terminer

        ctx = Contexte(sujet="un sujet coupe", journal=lambda _m: None)
        preparer(ctx, "ebook", "Un titre coupe")
        base_agents.signaler_troncature(ctx, "redacteur", self._reponse(True))
        terminer(ctx, [], {"mots": 100})
        fiche = store.lire_produit(ctx.produit_id)
        self.assertEqual(fiche["meta"]["tronquees"], 1)
        self.assertEqual(fiche["meta"]["tronquees_detail"][0]["agent"],
                         "redacteur")

    def test_sans_troncature_la_fiche_n_en_parle_pas(self):
        from usine.pipelines.base import preparer, terminer

        ctx = Contexte(sujet="un sujet entier", journal=lambda _m: None)
        preparer(ctx, "ebook", "Un titre entier")
        terminer(ctx, [], {"mots": 100})
        fiche = store.lire_produit(ctx.produit_id)
        self.assertNotIn("tronquees", fiche["meta"])
