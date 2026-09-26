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


def _rapport(sujet, discussions=None, ouvrages=None):
    """Un rapport de sondage a la forme que « interpreter » attend vraiment."""
    sources = {}
    disponibles = []
    if discussions is not None:
        sources["hacker_news"] = {"disponible": True,
                                  "discussions_totales": discussions}
        disponibles.append("hacker_news")
    if ouvrages is not None:
        sources["open_library"] = {"disponible": True,
                                   "ouvrages_totaux": ouvrages,
                                   "recents_dans_echantillon": 1,
                                   "echantillon": 10}
        disponibles.append("open_library")
    return {"sujet": sujet, "date": "2026-09-15", "sources": sources,
            "sources_disponibles": disponibles, "sources_indisponibles": []}


class UneSourceAnglophoneNePeutPasRefuterUneNiche(unittest.TestCase):
    """Le defaut etait dans « interpreter », et rien ne le testait.

    Les tests de selection injectaient « demande » directement dans la
    lecture, donc ils n'exercaient jamais le calcul qui la produit. Une
    campagne de mutation l'a montre le 15/09/2026 : remettre « demande =
    faible » dans Hacker News ne faisait echouer aucun test.

    Releve du meme jour, sur l'API de recherche de Hacker News :

        machine learning 18539, kubernetes 11481, photography 5203,
        startup funding 4642, python programming 3078, meditation 2290,
        personal finance 1819, gardening 566, meal planning 196,
        freelance invoicing 126, facturation freelance 0, potager balcon 0

    L'echelle suit la LARGEUR du mot-cle et sa presence dans un forum
    anglophone de developpeurs. Elle ne suit pas la demande d'un marche.
    """

    def test_sous_le_seuil_la_demande_n_est_pas_mesuree_et_non_faible(self):
        for total in (0, 1, 126, 196, 400):
            with self.subTest(discussions=total):
                lecture = marche.interpreter(_rapport("potager balcon", total))
                self.assertIsNone(
                    lecture["demande"],
                    "{} discussions ont produit un verdict que la mesure ne "
                    "porte pas".format(total))

    def test_au_dessus_du_seuil_la_source_confirme(self):
        self.assertEqual(
            marche.interpreter(_rapport("photography", 5203))["demande"],
            "forte")
        self.assertEqual(
            marche.interpreter(_rapport("gardening", 566))["demande"],
            "moyenne")

    def test_les_seuils_restent_a_l_echelle_relevee(self):
        # « gardening » (566) est moyen, « meal planning » (196) n'est pas
        # mesurable : entre les deux se trouve le seuil. Le descendre
        # promouvrait n'importe quel mot-cle au rang de marche confirme.
        self.assertGreater(marche.DISCUSSIONS_MOYENNE, 196)
        self.assertLess(marche.DISCUSSIONS_MOYENNE, 566)
        self.assertGreater(marche.DISCUSSIONS_FORTE, 2290)
        self.assertLess(marche.DISCUSSIONS_FORTE, 4642)

    def test_le_verdict_dit_que_le_sujet_n_est_ni_valide_ni_invalide(self):
        lecture = marche.interpreter(_rapport("facturation freelance", 0))
        self.assertIn("non mesure", lecture["verdict"])
        # Et il ne doit surtout pas suggerer que la niche est mauvaise.
        self.assertNotIn("trop etroite", lecture["verdict"])

    def test_une_requete_francaise_est_nommee_comme_telle(self):
        # Le detecteur cherche un mot-outil francais. « facturation
        # freelance » n'en contient aucun et passe donc pour anglophone —
        # c'est une limite connue, et elle ne decide plus de rien depuis que
        # la mesure ne peut plus ecarter une piste.
        lecture = marche.interpreter(_rapport("le potager en bac sur balcon", 0))
        self.assertTrue(lecture["requete_francophone"])
        self.assertIn("anglophones", lecture["verdict"])


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

    def test_un_domaine_que_les_sources_ne_savent_pas_juger_survit(self):
        """Ce test disait l'inverse, et il avait tort.

        Il exigeait qu'un domaine sans demande mesuree soit ECARTE — au nom
        d'une idee juste : ce qui sort d'un modele n'est pas une mesure. Mais
        le filtre ne mesurait rien. Releve du 15/09/2026 sur Hacker News, la
        seule source qui alimentait ce verdict :

            machine learning 18539, photography 5203, gardening 566,
            meal planning 196, freelance invoicing 126,
            facturation freelance 0, potager balcon 0

        L'echelle suit la largeur du mot-cle et sa presence dans un forum
        anglophone de developpeurs. Un nom de niche fait plusieurs mots par
        nature ; une niche francophone rend zero. « Faible » tombait donc sur
        toutes les pistes que le prospecteur propose, et la recherche de niche
        ne pouvait pas aboutir : huit domaines mesures, huit ecartes, « aucune
        niche trouvee ».

        Ce qui est garde ici : une source anglophone generaliste peut
        CONFIRMER un interet, jamais prouver son absence.
        """
        from usine import production

        marche.sonder = _sondage_simule({
            "la facturation des independants": None,
            "le potager en bac sur balcon": None,
            "la reprise de course a pied apres 40 ans": "forte"})
        retenus = production.domaines_de_depart()["retenus"]
        noms = [d["domaine"] for d in retenus]
        self.assertEqual(len(noms), 3, "une piste non mesuree a ete perdue")
        # Confirmee d'abord, non mesurees ensuite : elles ferment la marche,
        # elles ne sont pas une recommandation.
        self.assertEqual(noms[0], "la reprise de course a pied apres 40 ans")
        self.assertEqual(retenus[0]["demande"], "forte")
        for piste in retenus[1:]:
            self.assertEqual(piste["demande"], "")

    def test_le_journal_dit_la_raison_et_non_la_fiabilite(self):
        """Il affichait « ecarte ... — 3/4 sources ».

        La fiabilite a la place de la raison : on cherchait une panne de
        source la ou il n'y en avait pas. Trois sources sur quatre
        repondaient, et le rejet ne venait pas de la quatrieme.
        """
        from usine import production

        marche.sonder = _sondage_simule({
            "la facturation des independants": None,
            "le potager en bac sur balcon": "forte",
            "la reprise de course a pied apres 40 ans": "moyenne"})
        lignes = []
        production.domaines_de_depart(journal=lignes.append)
        journal = "\n".join(lignes)
        self.assertNotIn("écarté", journal)
        self.assertIn("demande non mesurée", journal)

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
