"""Quand on ne dit pas quoi produire.

Trois mesures ont ouvert ce sujet, le 14/09/2026.

**L'usine ne savait pas demarrer.** « prospecter » cherche des niches
VOISINES d'une graine, et la graine vient de ce qui a deja rapporte. Sur une
installation neuve il n'y a rien : pas de graine, donc pas de prospection.
L'usine repondait « ajoutez-en une a la main », poliment, sans echouer. La
seule fonction qui lui permet de choisir seule etait inatteignable depuis le
seul etat ou tout le monde commence.

**Le sujet etait obligatoire.** « _options_communes » le declarait en
positionnel pour les dix chaines : la seule facon de ne pas dicter la niche
etait de ne pas produire.

**Le refus etait muet.** Le tableau de bord, devant un sujet vide, faisait
« focus() » sur le champ et s'arretait la — aucun message, aucune erreur. On
recliquait sur le bouton en croyant qu'il ne marchait pas.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import file, llm, marche  # noqa: E402


def setUpModule():
    atelier.isoler("niche-choisie")


def _sondage_simule(demande_par_sujet=None):
    """Un sondage de marche qui ne sort pas sur le reseau.

    Le rapport passe par le VRAI « interpreter » : une lecture fabriquee a la
    main aurait des cles que le code de production n'attend pas, et le test
    aurait valide une forme inexistante.
    """
    vrai = marche.interpreter
    demandes = demande_par_sujet or {}

    def sonder(sujet, **_kw):
        rapport = {"sujet": sujet, "date": "2026-09-14", "sources": {},
                   "sources_disponibles": ["reddit"], "sources_indisponibles": []}
        rapport["lecture"] = vrai(rapport)
        if sujet in demandes:
            rapport["lecture"]["demande"] = demandes[sujet]
        return rapport

    return sonder


class UneInstallationNeuveSaitDemarrer(unittest.TestCase):
    """Le cas de TOUT LE MONDE le premier jour."""

    def setUp(self):
        atelier.isoler("niche-" + self.id().rsplit(".", 1)[-1])
        llm.definir_simulateur(simulateur)
        self._vrai_sonder = marche.sonder
        marche.sonder = _sondage_simule()

    def tearDown(self):
        marche.sonder = self._vrai_sonder
        llm.definir_simulateur(None)

    def test_sans_historique_l_usine_propose_quand_meme(self):
        from usine import production

        self.assertEqual(production.graine_de_depart(), "",
                         "l'atelier n'est pas vide : le test ne mesure rien")
        trouve = production.domaines_de_depart()
        self.assertTrue(trouve["retenus"],
                        "atelier vide : l'usine ne sait toujours pas commencer")

    def test_la_prospection_part_de_rien_et_remplit_la_file(self):
        from usine import production

        resultat = production.prospecter(nombre=4, avec_veille=False)
        self.assertTrue(resultat["froid"],
                        "la graine ne vient pas d'un demarrage a froid")
        self.assertGreater(resultat["ajoutees"], 0)
        self.assertGreater(file.compter()["en_attente"], 0)

    def test_un_domaine_sans_demande_mesuree_est_ecarte(self):
        """Proposer ne suffit pas : ce qui sort d'un modele n'est pas une
        mesure. Sans ce filtre, l'usine fabriquerait la premiere chose qui
        lui passe par la tete et la presenterait comme un choix motive."""
        from usine import production

        marche.sonder = _sondage_simule({
            "la facturation des independants": "faible",
            "le potager en bac sur balcon": "faible",
            "la reprise de course a pied apres 40 ans": "forte"})
        retenus = [d["domaine"] for d in production.domaines_de_depart()["retenus"]]
        self.assertEqual(retenus, ["la reprise de course a pied apres 40 ans"])

    def test_le_plus_demande_passe_devant(self):
        from usine import production

        marche.sonder = _sondage_simule({
            "la facturation des independants": "moyenne",
            "le potager en bac sur balcon": "forte",
            "la reprise de course a pied apres 40 ans": "moyenne"})
        retenus = production.domaines_de_depart()["retenus"]
        self.assertEqual(retenus[0]["domaine"], "le potager en bac sur balcon")

    def test_une_panne_reseau_n_empeche_pas_de_demarrer(self):
        from usine import production

        def sonder_casse(_sujet, **_kw):
            raise OSError("reseau coupe")

        marche.sonder = sonder_casse
        trouve = production.domaines_de_depart()
        self.assertFalse(trouve["mesure"])
        self.assertTrue(trouve["retenus"], "une panne reseau ne doit pas "
                                           "empecher de demarrer")

    def test_des_sources_muettes_ne_font_pas_une_mesure(self):
        """Le cas le plus sournois : les sources REPONDENT, mais aucune ne
        dit rien d'exploitable. Tous les signaux ont l'air normaux — pas
        d'exception, pas d'erreur — et le rapport semble complet.

        La premiere version du test coupait le reseau brutalement, ce qui
        passe par la branche « except » et ne touchait jamais la ligne qui
        decide. Elle etait donc verte alors que « mesure » pouvait valoir
        True en permanence.
        """
        from usine import production

        vrai = marche.interpreter

        def sonder_muet(sujet, **_kw):
            rapport = {"sujet": sujet, "date": "2026-09-14", "sources": {},
                       "sources_disponibles": [], "sources_indisponibles":
                       ["reddit", "google", "hn", "wikipedia"]}
            rapport["lecture"] = vrai(rapport)
            return rapport

        marche.sonder = sonder_muet
        trouve = production.domaines_de_depart()
        self.assertFalse(trouve["mesure"],
                         "aucune source disponible, et l'usine annonce "
                         "pourtant un classement mesure")
        self.assertTrue(trouve["retenus"])


class LeSujetEstFacultatif(unittest.TestCase):

    def setUp(self):
        atelier.isoler("niche-sujet-" + self.id().rsplit(".", 1)[-1])
        llm.definir_simulateur(simulateur)
        self._vrai_sonder = marche.sonder
        marche.sonder = _sondage_simule()

    def tearDown(self):
        marche.sonder = self._vrai_sonder
        llm.definir_simulateur(None)

    def test_les_dix_chaines_acceptent_d_etre_lancees_sans_sujet(self):
        """Mesure sur l'analyseur d'arguments, pas sur le texte de l'aide :
        un positionnel obligatoire leve SystemExit, et c'est la seule chose
        qui compte pour quelqu'un qui tape « usine ebook » tout court."""
        from usine import cli
        from usine.pipelines import catalogue

        analyseur = cli.construire_parseur()
        for cle in catalogue.cles():
            with self.subTest(chaine=cle):
                try:
                    args = analyseur.parse_args([cle])
                except SystemExit:
                    self.fail("« usine {} » sans sujet est refuse".format(cle))
                self.assertEqual(getattr(args, "sujet", ""), "")

    def test_la_ligne_de_commande_relie_vraiment_les_deux(self):
        """Les deux pieces peuvent marcher chacune de son cote sans que rien
        ne les branche : l'analyseur accepte un sujet vide, « choisir_une_
        niche » sait choisir, et « contexte_depuis » ne les appelle pas. La
        chaine fabriquerait alors un produit sur le sujet « », sans erreur.
        """
        from usine import cli

        args = cli.construire_parseur().parse_args(["ebook"])
        self.assertEqual(args.sujet, "")
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            contexte = cli.contexte_depuis(args)
        self.assertTrue(contexte.sujet,
                        "la chaine part avec un sujet vide : « usine ebook » "
                        "tout court ne choisit rien")

    def test_un_sujet_vide_fait_choisir_l_usine(self):
        from usine import production

        choix = production.choisir_une_niche()
        self.assertTrue(choix["sujet"])
        self.assertEqual(choix["source"], "froid")

    def test_une_niche_qui_attend_en_file_passe_avant(self):
        """Inventer une onzieme niche pendant que dix patientent gaspille un
        appel et fabrique un doublon."""
        from usine import production

        file.ajouter("la comptabilite des associations", "ebook")
        choix = production.choisir_une_niche()
        self.assertEqual(choix["sujet"], "la comptabilite des associations")
        self.assertEqual(choix["source"], "file")

    def test_regarder_la_file_ne_prend_pas_l_entree(self):
        """« prochain() » marque l'entree en cours : une commande unique qui
        la consomme la volerait a l'usine continue, qui la refabriquerait."""
        from usine import production

        file.ajouter("la comptabilite des associations", "ebook")
        production.choisir_une_niche()
        self.assertEqual(file.compter()["en_attente"], 1)
        self.assertEqual(file.compter()["en_cours"], 0)


class LeTableauDeBordNeRefusePlusEnSilence(unittest.TestCase):

    def test_plus_aucun_bouton_ne_refuse_sans_rien_dire(self):
        """Un « focus() » suivi d'un « return » ne dit rien a personne : le
        bouton semble mort. Pire depuis que les onglets sont separes — le
        champ vise peut vivre dans une section cachee, et le curseur y va
        sans que rien ne bouge a l'ecran.
        """
        source = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        muets = [ligne.strip() for ligne in source.splitlines()
                 if ".focus(); return;" in ligne]
        self.assertEqual(muets, [], "ces refus sont muets : " + " | ".join(muets))

    def test_la_page_annonce_que_le_sujet_est_facultatif(self):
        page = (RACINE / "usine" / "web" / "statique" / "tableau.html").read_text(
            encoding="utf-8")
        self.assertIn("facultatif", page)

    def test_le_serveur_accepte_de_fabriquer_sans_sujet(self):
        """Sur la FABRICATION seulement. Mettre une ligne en file exige
        toujours un sujet, et c'est juste : une entree de file sans sujet ne
        serait rien de lisible dans la liste d'attente.
        """
        import inspect

        from usine.web import serveur

        corps = inspect.getsource(serveur.Gestionnaire._fabriquer)
        self.assertNotIn("sujet manquant", corps,
                         "le tableau de bord refuse encore de chercher")

    def test_le_fil_de_fabrication_choisit_pour_de_bon(self):
        """On fait tourner le fil et on regarde le sujet qu'il retient.

        Chercher « choisir_une_niche » dans le source ne prouvait rien : un
        import renomme — « from ..production import prospecter as
        choisir_une_niche » — laissait le nom en place et le test vert, alors
        que la fabrication partait sur autre chose. C'est la regle du depot :
        un garde-fou satisfait par une homonymie ne garde rien.
        """
        from usine.core import llm, marche
        from usine.pipelines import catalogue
        from usine.web import serveur

        atelier.isoler("niche-fil-web")
        llm.definir_simulateur(simulateur)
        vrai_sonder, vrai_executer = marche.sonder, catalogue.executer
        marche.sonder = _sondage_simule()
        vus = {}

        def executer_faux(_type, contexte, _options):
            vus["sujet"] = contexte.sujet
            return {"titre": "x", "fichiers": []}

        catalogue.executer = executer_faux
        serveur.TRAVAUX["essai"] = {
            "id": "essai", "type": "ebook", "sujet": "(l'usine choisit)",
            "statut": "en_cours", "debut": 0.0, "journal": [],
            "resultat": None, "erreur": "",
        }
        try:
            serveur._lancer("essai", "ebook", {"sujet": ""})
        finally:
            marche.sonder, catalogue.executer = vrai_sonder, vrai_executer
            llm.definir_simulateur(None)

        self.assertTrue(vus.get("sujet"),
                        "le tableau de bord fabrique sur un sujet vide")
        self.assertEqual(serveur.TRAVAUX["essai"]["sujet"], vus["sujet"],
                         "la niche choisie n'apparait pas dans le suivi : "
                         "on voit « (l'usine choisit) » jusqu'a la fin")
        serveur.TRAVAUX.pop("essai", None)

    def test_le_menu_termux_ne_l_exige_plus(self):
        from usine import menu

        source = (RACINE / "usine" / "menu.py").read_text(encoding="utf-8")
        self.assertNotIn('demander("Sujet du produit", obligatoire=True)', source)
        self.assertTrue(hasattr(menu, "menu_fabriquer")
                        or hasattr(menu, "demander"))


if __name__ == "__main__":
    unittest.main()
