"""Le type de produit, quand c'est l'usine qui le choisit.

Onze commandes de fabrication demandent un type : « usine ebook »,
« usine social ». Choisir le type suppose deja de savoir ce qui se vend dans
une niche qu'on n'a pas encore cherchee — c'est l'ordre inverse de celui dans
lequel la question se pose. Deux defauts en decoulaient.

**Un sujet concu pour un type servait a en fabriquer un autre.** « usine
ebook » sans sujet reprenait la premiere entree de la file, quelle qu'elle
soit. Mesure du 14/09/2026 : sur quatre demandes de types differents, trois
repartaient avec un sujet concu pour un autre — un ebook intitule « 30 posts
LinkedIn pour freelances ». Rien n'echouait : le produit sortait, complet,
et seul son titre disait que quelque chose n'allait pas.

**Le type que l'usine venait de calculer etait jete.** « choisir_une_niche »
rend { sujet, type } ; les deux appelants — la ligne de commande et le
serveur — ne gardaient que le sujet. La chaine « idees » donne pourtant un
type a chaque piste qu'elle trouve, et ce type n'etait suivi nulle part,
faute d'un endroit ou il aurait change quelque chose.

D'ou « auto » : le mode ou l'usine choisit AUSSI le type, et ou l'appelant
doit le suivre. C'est le seul mode ou le type rendu peut differer du type
demande ; partout ailleurs, le type demande est une contrainte.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("type_choisi")


from usine import production  # noqa: E402
from usine.core import file as file_prod  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402


class NicheAccordeeAuType(unittest.TestCase):

    def setUp(self):
        file_prod.vider(tout=True)
        # Le demarrage a froid mesure de vrais domaines sur des sources
        # publiques. Aucun test ne sort sur le reseau — et sans ce garde, ces
        # neuf tests mettaient cinquante-cinq secondes a echouer d'attente.
        froid = mock.patch.object(
            production, "domaines_de_depart",
            return_value={"retenus": [{"domaine": "la productivite"}],
                          "mesures": [], "mesure": True})
        froid.start()
        self.addCleanup(froid.stop)
        graine = mock.patch.object(production, "graine_de_depart",
                                   return_value="")
        graine.start()
        self.addCleanup(graine.stop)

    def test_une_niche_d_un_autre_type_n_est_pas_reprise(self):
        """Le defaut mesure : trois demandes sur quatre partaient de travers."""
        file_prod.ajouter("30 posts LinkedIn pour freelances", "social")
        choix = production.choisir_une_niche(type_produit="ebook")
        self.assertNotEqual(
            choix["sujet"], "30 posts LinkedIn pour freelances",
            "un sujet concu pour « social » ne doit pas devenir un ebook")

    def test_la_niche_du_bon_type_est_reprise(self):
        file_prod.ajouter("30 posts LinkedIn pour freelances", "social")
        choix = production.choisir_une_niche(type_produit="social")
        self.assertEqual(choix["sujet"], "30 posts LinkedIn pour freelances")
        self.assertEqual(choix["type"], "social")

    def test_la_file_est_fouillee_au_dela_de_la_premiere_entree(self):
        """Une seule entree etait lue : la bonne pouvait etre la deuxieme.

        C'est la forme discrete du meme defaut. Filtrer par type sans
        regarder plus loin que la premiere entree aurait rendu « aucune
        niche » alors qu'il y en avait une, juste derriere.
        """
        file_prod.ajouter("30 posts LinkedIn pour freelances", "social")
        file_prod.ajouter("Pack de 50 prompts pour redacteurs", "prompts")
        choix = production.choisir_une_niche(type_produit="prompts")
        self.assertEqual(choix["sujet"], "Pack de 50 prompts pour redacteurs")

    def test_en_mode_auto_le_type_vient_de_la_niche(self):
        file_prod.ajouter("30 posts LinkedIn pour freelances", "social")
        choix = production.choisir_une_niche(type_produit=production.AUTO)
        self.assertEqual(choix["sujet"], "30 posts LinkedIn pour freelances")
        self.assertEqual(choix["type"], "social",
                         "en mode auto, le type de la niche fait foi")

    def test_le_type_rendu_est_toujours_fabricable(self):
        """Meme sans rien en file, et meme en mode auto.

        Un type vide ou « auto » remonterait jusqu'a « catalogue.executer »,
        qui leve. Le mode ou l'usine decide ne doit pas pouvoir rendre un
        type que l'usine ne sait pas fabriquer.
        """
        for demande in ("ebook", "social", production.AUTO, ""):
            choix = production.choisir_une_niche(type_produit=demande)
            self.assertIsNotNone(
                catalogue.obtenir(choix["type"]),
                "type non fabricable rendu pour « {} » : {!r}".format(
                    demande, choix["type"]))


class LeTypeSurvitAuxAppelants(unittest.TestCase):
    """Ce que la ligne de commande et le serveur font du type calcule."""

    def test_la_commande_auto_existe_et_suit_le_type(self):
        from usine import cli

        source = (RACINE / "usine" / "cli.py").read_text(encoding="utf-8")
        self.assertTrue(hasattr(cli, "cmd_auto"))
        # Elle doit POSER le type retenu, pas seulement le lire : c'est
        # exactement ce que les deux appelants ne faisaient pas.
        debut = source.index("def cmd_auto(")
        fin = source.index("\ndef ", debut + 10)
        corps = source[debut:fin]
        self.assertIn("args._type = fiche.cle", corps)
        self.assertIn("catalogue.executer(fiche.cle", corps)

    def test_le_serveur_suit_le_type_rendu_par_la_niche(self):
        source = (RACINE / "usine" / "web" / "serveur.py").read_text(
            encoding="utf-8")
        debut = source.index("def _lancer(")
        fin = source.index("\ndef ", debut + 10)
        corps = source[debut:fin]
        self.assertIn('type_produit = choix.get("type")', corps,
                      "le serveur jette encore le type qu'il vient de calculer")

    def test_le_tableau_de_bord_propose_de_laisser_decider(self):
        from usine.web import serveur

        offerts = serveur._types_offerts()
        self.assertEqual(offerts[0]["cle"], production.AUTO,
                         "le choix « l'usine decide » doit venir en tete")
        # Et il ne porte aucun champ : les reglages d'un type ne peuvent pas
        # etre demandes avant que le type soit connu.
        self.assertEqual(offerts[0]["champs"], [])
        # Les onze autres restent proposes tels quels.
        self.assertEqual([t["cle"] for t in offerts[1:]],
                         [t.cle for t in catalogue.tous(fabricables=True)])

    def test_le_choix_auto_n_est_pas_un_type_fabricable(self):
        """Sinon il apparaitrait dans la CLI, le menu et la file."""
        self.assertIsNone(catalogue.obtenir(production.AUTO))
        self.assertNotIn(production.AUTO, catalogue.cles(fabricables=True))


if __name__ == "__main__":
    unittest.main()
