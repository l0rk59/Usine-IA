"""Deux chaines se nomment par un chiffre, et le chiffre etait faux.

Mesure du 15/09/2026, en fabriquant un pack de prompts et en COMPTANT ce
qu'il contient :

    titre annonce   « 7 prompts pour l'ecriture de fiches produit »
    pack livre      12 prompts

Le titre etait fixe a la ligne qui suit le plan, a partir du nombre DEMANDE,
avant qu'un seul prompt ne soit redige. Rien ne le comparait ensuite a ce qui
sortait. Le nombre sur la couverture est pourtant la seule chose qu'un
acheteur verifie d'un coup d'oeil.

Et la cause du douze : la redaction publiait tout ce que le modele rendait,
y compris des prompts que le plan n'avait jamais demandes. Sur la mesure du
jour, quatre des six « prompts » d'une categorie etaient des morceaux de la
CONSIGNE promus au rang de produit vendu :

    ## titre' : l'intitule, reformule pour etre vendeur et clair.

Le plan est le contrat. On coupe sur le NOMBRE planifie et non sur les
intitules : la consigne demande justement de reformuler le titre, donc
comparer les libelles ecarterait les bonnes reformulations avec les mauvaises.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("compte-annonce")


from usine.core import llm, store  # noqa: E402
from usine.pipelines import base, catalogue  # noqa: E402
from tests import simulateur  # noqa: E402


def _fabriquer(cle, sujet, options, modele=None):
    llm.definir_simulateur(modele or simulateur.simulateur)
    try:
        ctx = base.Contexte(sujet=sujet, sans_image=True, journal=lambda m: None)
        resume = catalogue.executer(cle, ctx, options)
    finally:
        llm.definir_simulateur(None)
    return Path(resume["dossier"]), resume


def _etapes(produit_id):
    return {str(p.get("nom")): str(p.get("statut"))
            for p in store.etapes_produit(produit_id)}


def _plan_fixe(categories, par_categorie, muets=0):
    """Un modele qui planifie ce qu'on lui dit, puis redige autre chose.

    « muets » : des entrees rendues SANS champ « prompt ». C'est la seule
    facon d'obtenir moins de prompts ecrits que planifies — le plafond, lui,
    ne peut qu'egaler le plan. Sans ce cas, la correction du titre APRES
    redaction n'etait atteinte par aucun test : une campagne de mutation a
    montre qu'on pouvait la retirer entierement sans rien casser.
    """

    def modele(messages, role):
        invite = messages[-1]["content"]
        if '"categories"' in invite and '"intention"' in invite:
            return json.dumps({"categories": [
                {"nom": "Categorie {}".format(rang),
                 "intention": "un resultat",
                 "prompts": ["intitule {}-{}".format(rang, n)
                             for n in range(1, 3)]}
                for rang in range(1, categories + 1)]})
        if '"astuce"' in invite:
            rendus = [{"titre": "Prompt {}".format(n), "quand": "au demarrage",
                       "prompt": "Tu es un consultant. [CONTEXTE]",
                       "astuce": "un exemple"}
                      for n in range(1, par_categorie + 1)]
            for element in rendus[:muets]:
                element.pop("prompt")
            return json.dumps({"prompts": rendus})
        return simulateur.simulateur(messages, role)

    return modele


class LaCouvertureAnnonceCeQueLePackContient(unittest.TestCase):

    def test_le_titre_compte_les_prompts_ecrits_et_non_ceux_demandes(self):
        dossier, resume = _fabriquer(
            "prompts", "la redaction d'annonces immobilieres", {"nombre": 50})
        annonce = int(re.match(r"(\d+) prompts", resume["titre"]).group(1))
        self.assertEqual(annonce, resume["prompts"], (
            "la couverture annonce {} prompts, le pack en contient {}"
            .format(annonce, resume["prompts"])))

    def test_le_markdown_livre_porte_le_meme_compte(self):
        """Le titre corrige doit atteindre les FICHIERS, pas seulement le
        resume : le markdown, le PDF et la page HTML sont ecrits par
        « _exporter », qui recoit le titre en parametre."""
        dossier, resume = _fabriquer(
            "prompts", "la gestion d'un gite rural", {"nombre": 50})
        markdown = next(dossier.glob("prompts.md")).read_text(encoding="utf-8")
        annonce = int(re.match(r"# (\d+) prompts", markdown).group(1))
        prompts = markdown.count("\n```\n")  # ouverture + fermeture par prompt
        self.assertEqual(annonce, prompts // 2, (
            "le markdown s'intitule « {} prompts » et en contient {}"
            .format(annonce, prompts // 2)))

    def test_le_tableau_de_bord_lit_le_titre_corrige(self):
        """Le titre part en base a la creation du dossier, donc AVANT la
        redaction. Sans la remise a jour, la couverture disait une chose et la
        liste des produits une autre."""
        dossier, resume = _fabriquer(
            "prompts", "l'entretien d'un velo electrique", {"nombre": 50})
        ligne = store.lire_produit(resume["produit_id"])
        self.assertEqual(ligne["titre"], resume["titre"])

    def test_un_pack_court_est_signale_sans_etre_declare_troue(self):
        """Le pack EST complet : chaque prompt planifie est redige. C'est la
        commande qui n'est pas honoree. « anomalie » dit exactement cela —
        « en_cours » aurait fait croire a une reprise possible."""
        dossier, resume = _fabriquer(
            "prompts", "la location de materiel de chantier", {"nombre": 50})
        etapes = _etapes(resume["produit_id"])
        self.assertEqual(etapes.get("plan"), "anomalie")
        self.assertEqual(store.lire_produit(resume["produit_id"])["statut"],
                         "pret")


class LaRedactionNePublieQueCeQueLePlanADemande(unittest.TestCase):

    def test_les_prompts_hors_plan_ne_sont_pas_vendus(self):
        """Six prompts rendus pour deux planifies : les quatre en trop, sur la
        mesure d'origine, etaient des fragments de la consigne."""
        dossier, resume = _fabriquer(
            "prompts", "la vente de miel en direct", {"nombre": 4},
            modele=_plan_fixe(categories=2, par_categorie=6))
        self.assertEqual(resume["prompts"], 4, (
            "{} prompts vendus pour 4 planifies".format(resume["prompts"])))

    def test_un_modele_obeissant_ne_declenche_aucune_anomalie(self):
        """Le garde-fou qui crie a tort finit ignore : quand le plan honore la
        commande et que la redaction suit, les deux etapes sont « ok »."""
        dossier, resume = _fabriquer(
            "prompts", "la taille des arbres fruitiers", {"nombre": 4},
            modele=_plan_fixe(categories=2, par_categorie=2))
        etapes = _etapes(resume["produit_id"])
        self.assertEqual(etapes.get("plan"), "ok")
        self.assertNotEqual(etapes.get("redaction"), "anomalie")
        self.assertEqual(resume["prompts"], 4)

    def test_un_plan_plus_genereux_que_la_commande_ne_crie_pas(self):
        """Six prompts planifies pour quatre demandes : l'acheteur n'est pas
        lese. On signale le MANQUE, pas l'ecart."""
        dossier, resume = _fabriquer(
            "prompts", "la fabrication de savon a froid", {"nombre": 4},
            modele=_plan_fixe(categories=3, par_categorie=2))
        self.assertEqual(_etapes(resume["produit_id"]).get("plan"), "ok")
        self.assertEqual(resume["prompts"], 6)
        self.assertTrue(resume["titre"].startswith("6 prompts"))


class QuandLaRedactionRendMoinsQueLePlan(unittest.TestCase):
    """Le plafond ne peut que couper : pour ecrire MOINS que le plan, il faut
    que le modele rende des entrees sans prompt. Elles sont ecartees depuis
    toujours — mais le titre, lui, restait celui du plan.

    Ce cas n'existait dans aucun test : la campagne de mutation a montre qu'on
    pouvait supprimer la correction du titre d'apres redaction, la remise a
    jour de la base ET le passage du titre corrige aux fichiers sans qu'un
    seul test bronche. Trois corrections que rien ne gardait.
    """

    def _quatre_planifies_deux_ecrits(self, sujet):
        return _fabriquer("prompts", sujet, {"nombre": 4},
                          modele=_plan_fixe(categories=2, par_categorie=2,
                                            muets=1))

    def test_le_titre_tombe_au_nombre_reellement_ecrit(self):
        _, resume = self._quatre_planifies_deux_ecrits("le brassage amateur")
        self.assertEqual(resume["prompts"], 2)
        self.assertTrue(resume["titre"].startswith("2 prompts"), (
            "titre « {} » pour deux prompts ecrits".format(resume["titre"])))

    def test_le_markdown_livre_porte_le_titre_corrige(self):
        dossier, resume = self._quatre_planifies_deux_ecrits(
            "la culture des champignons")
        markdown = (dossier / "prompts.md").read_text(encoding="utf-8")
        self.assertTrue(markdown.startswith("# 2 prompts"), (
            "le markdown s'ouvre sur « {} »".format(
                markdown.splitlines()[0])))

    def test_la_base_porte_le_titre_corrige(self):
        _, resume = self._quatre_planifies_deux_ecrits("le tressage d'osier")
        ligne = store.lire_produit(resume["produit_id"])
        self.assertEqual(ligne["titre"], resume["titre"])
        self.assertTrue(ligne["titre"].startswith("2 prompts"))

    def test_la_perte_est_signalee(self):
        _, resume = self._quatre_planifies_deux_ecrits("la reliure a la main")
        self.assertEqual(_etapes(resume["produit_id"]).get("redaction"),
                         "anomalie")


class UnCalendrierEditorialSeNommeDeMeme(unittest.TestCase):
    """Meme defaut, meme forme : « 30 posts LinkedIn — … » venait du nombre
    demande. Les deux seules chaines du depot qui se nomment par un chiffre —
    partout ailleurs le titre vient d'un « len(...) » deja mesure."""

    def _calendrier_court(self, combien):
        def modele(messages, role):
            invite = messages[-1]["content"]
            if '"accroche"' in invite and '"jour"' in invite:
                return json.dumps({"publications": [
                    {"jour": n, "angle": "angle {}".format(n),
                     "sujet": "sujet {}".format(n),
                     "objectif": "engagement",
                     "accroche": "une accroche"}
                    for n in range(1, combien + 1)]})
            return simulateur.simulateur(messages, role)
        return modele

    def test_le_titre_compte_les_posts_du_calendrier(self):
        dossier, resume = _fabriquer(
            "social", "la reparation de smartphones", {"nombre": 30},
            modele=self._calendrier_court(6))
        annonce = int(re.match(r"(\d+) posts", resume["titre"]).group(1))
        self.assertEqual(annonce, resume["posts"], (
            "le titre annonce {} posts, le pack en contient {}"
            .format(annonce, resume["posts"])))
        self.assertEqual(annonce, 6)

    def test_un_calendrier_court_est_signale(self):
        dossier, resume = _fabriquer(
            "social", "la garde d'animaux a domicile", {"nombre": 30},
            modele=self._calendrier_court(5))
        self.assertEqual(_etapes(resume["produit_id"]).get("calendrier"),
                         "anomalie")


if __name__ == "__main__":
    unittest.main()
