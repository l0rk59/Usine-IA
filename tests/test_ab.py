"""Tests de l'A/B testing : statistiques, diagnostic, refus de conclure.

L'enjeu de ces tests n'est pas que l'outil trouve un gagnant, mais qu'il
REFUSE d'en trouver un quand les donnees ne le permettent pas.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

os.environ["USINE_HOME"] = tempfile.mkdtemp(prefix="usine-ab-")

from usine.core import diagnostic_titre as dt  # noqa: E402
from usine.core import experience as ex  # noqa: E402


class TestStatistiques(unittest.TestCase):
    """La formule exacte et le tirage aleatoire doivent concorder."""

    def test_formule_exacte_et_tirage_concordent(self):
        for succes_a, essais_a, succes_b, essais_b in (
            (5, 100, 10, 100), (50, 1000, 60, 1000), (2, 20, 3, 20),
            (0, 50, 5, 50), (100, 1000, 100, 1000), (1, 5, 4, 5),
        ):
            exact = ex.probabilite_superieure(succes_a, essais_a, succes_b, essais_b)
            comparaison = ex.comparer([(succes_a, essais_a), (succes_b, essais_b)],
                                      tirages=60000)
            tirage = comparaison["variantes"][1]["probabilite_meilleure"]
            self.assertLess(
                abs(exact - tirage), 0.012,
                "divergence sur {}/{} vs {}/{} : {:.4f} vs {:.4f}".format(
                    succes_a, essais_a, succes_b, essais_b, exact, tirage))

    def test_donnees_identiques_donnent_une_chance_sur_deux(self):
        self.assertAlmostEqual(
            ex.probabilite_superieure(10, 100, 10, 100), 0.5, places=6)

    def test_sans_donnees_aucune_preference(self):
        self.assertAlmostEqual(ex.probabilite_superieure(0, 0, 0, 0), 0.5, places=6)

    def test_ecart_massif_reconnu(self):
        self.assertGreater(ex.probabilite_superieure(1, 200, 40, 200), 0.999)

    def test_resultat_reproductible(self):
        """Un verdict qui changerait d'un appel a l'autre serait indefendable."""
        premier = ex.comparer([(12, 300), (18, 300)])
        second = ex.comparer([(12, 300), (18, 300)])
        self.assertEqual(premier["variantes"][1]["probabilite_meilleure"],
                         second["variantes"][1]["probabilite_meilleure"])

    def test_les_probabilites_somment_a_un(self):
        comparaison = ex.comparer([(10, 200), (14, 200), (8, 200), (12, 200)])
        total = sum(v["probabilite_meilleure"] for v in comparaison["variantes"])
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_intervalle_credible_encadre_le_taux(self):
        comparaison = ex.comparer([(50, 1000)])
        variante = comparaison["variantes"][0]
        self.assertLess(variante["bas"], 0.05)
        self.assertGreater(variante["haut"], 0.05)

    def test_la_perte_esperee_du_meilleur_est_la_plus_faible(self):
        comparaison = ex.comparer([(30, 1000), (90, 1000), (40, 1000)])
        pertes = [v["perte_esperee"] for v in comparaison["variantes"]]
        self.assertEqual(pertes.index(min(pertes)), 1)


class TestRefusDeConclure(unittest.TestCase):
    """Le coeur du sujet : ne pas designer de gagnant sans preuve."""

    def test_petit_echantillon_malgre_un_ecart_apparent_enorme(self):
        """8/100 contre 12/100 : +50 % apparent, et pourtant rien a conclure."""
        verdict = ex.verdict(ex.comparer([(8, 100), (12, 100)]))
        self.assertEqual(verdict["etat"], "insuffisant")
        self.assertIn("bruit", verdict["message"])

    def test_cinq_variantes_identiques_ne_produisent_pas_de_gagnant(self):
        """Comparer cinq variantes deux a deux inventerait un gagnant."""
        comparaison = ex.comparer([(20, 400)] * 5)
        for variante in comparaison["variantes"]:
            self.assertLess(variante["probabilite_meilleure"], 0.35)
        self.assertEqual(ex.verdict(comparaison)["etat"], "indecis")

    def test_gros_echantillon_avec_ecart_reel(self):
        verdict = ex.verdict(ex.comparer([(50, 1000), (100, 1000)]))
        self.assertEqual(verdict["etat"], "gagnant")
        self.assertEqual(verdict["gagnante"], 1)
        self.assertGreaterEqual(verdict["certitude"], ex.CERTITUDE_GAGNANT)

    def test_tendance_declaree_sans_etre_un_gagnant(self):
        """5,0 % contre 6,5 % sur 1000 vues : P = 0,93, sous le seuil de 0,95."""
        verdict = ex.verdict(ex.comparer([(50, 1000), (65, 1000)]))
        self.assertEqual(verdict["etat"], "tendance")
        self.assertLess(verdict["certitude"], ex.CERTITUDE_GAGNANT)
        self.assertGreaterEqual(verdict["certitude"], ex.CERTITUDE_TENDANCE)
        self.assertIn("besoin_par_variante", verdict)

    def test_un_ecart_franc_sur_gros_volume_est_bien_declare(self):
        """A l'inverse, 5,0 % contre 7,1 % sur 1200 vues doit conclure."""
        verdict = ex.verdict(ex.comparer([(60, 1200), (85, 1200)]))
        self.assertEqual(verdict["etat"], "gagnant")
        self.assertEqual(verdict["gagnante"], 1)

    def test_sans_observation(self):
        verdict = ex.verdict(ex.comparer([(0, 0), (0, 0)]))
        self.assertEqual(verdict["etat"], "sans_donnees")

    def test_l_echelle_annoncee_est_realiste(self):
        """A 5 % de conversion, il faut des milliers de vues, pas des dizaines."""
        self.assertGreater(ex.observations_necessaires(0.05), 5000)
        self.assertGreater(ex.observations_necessaires(0.01), 30000)


class TestPersistance(unittest.TestCase):
    def setUp(self):
        for exp in ex.lister(100):
            ex.supprimer(exp["id"])

    def test_cycle_complet(self):
        identifiant = ex.creer("Mon produit", sujet="titre", objectif="ventes")
        premiere = ex.ajouter_variante(identifiant, "Titre A", meta={"angle": "benefice"})
        seconde = ex.ajouter_variante(identifiant, "Titre B")
        self.assertEqual([v["etiquette"] for v in ex.variantes(identifiant)],
                         ["A", "B"])
        ex.observer(premiere, vues=100, actions=5)
        ex.observer(premiere, vues=50, actions=3)   # les releves s'additionnent
        ex.observer(seconde, vues=150, actions=12)
        lot = ex.variantes(identifiant)
        self.assertEqual(lot[0]["total_vues"], 150)
        self.assertEqual(lot[0]["total_actions"], 8)
        self.assertEqual(lot[0]["releves"], 2)
        analyse = ex.analyser(identifiant)
        self.assertIn("verdict", analyse)
        self.assertEqual(len(analyse["variantes"]), 2)

    def test_saisie_incoherente_refusee(self):
        identifiant = ex.creer("Produit", sujet="titre")
        variante = ex.ajouter_variante(identifiant, "A")
        with self.assertRaises(ValueError):
            ex.observer(variante, vues=10, actions=20)   # plus d'achats que de vues
        with self.assertRaises(ValueError):
            ex.observer(variante, vues=-5)

    def test_sujet_et_objectif_valides(self):
        with self.assertRaises(ValueError):
            ex.creer("Produit", sujet="inexistant")
        with self.assertRaises(ValueError):
            ex.creer("Produit", objectif="inexistant")

    def test_suppression_nettoie_tout(self):
        identifiant = ex.creer("A supprimer", sujet="titre")
        variante = ex.ajouter_variante(identifiant, "A")
        ex.observer(variante, vues=10, actions=1)
        self.assertTrue(ex.supprimer(identifiant))
        self.assertIsNone(ex.lire(identifiant))
        self.assertEqual(ex.variantes(identifiant), [])


class TestDiagnosticTitre(unittest.TestCase):
    def test_signaux_reconnus(self):
        diagnostic = dt.diagnostiquer(
            "Freelance : 7 etapes pour doubler vos revenus en 90 jours")
        self.assertTrue(diagnostic.mesures["chiffre"])
        self.assertTrue(diagnostic.mesures["delai"])
        self.assertIn("freelance", diagnostic.mesures["audience_nommee"])

    def test_mots_creux_signales(self):
        diagnostic = dt.diagnostiquer("La methode ultime et revolutionnaire")
        self.assertTrue(diagnostic.mesures["mots_creux"])
        self.assertTrue(any("creux" in r for r in diagnostic.reserves))

    def test_titre_trop_long_signale(self):
        diagnostic = dt.diagnostiquer("mot " * 30)
        self.assertTrue(any("caracteres" in r for r in diagnostic.reserves))

    def test_accents_indifferents(self):
        avec = dt.diagnostiquer("La méthode ultime")
        sans = dt.diagnostiquer("La methode ultime")
        self.assertEqual(avec.mesures["mots_creux"], sans.mesures["mots_creux"])

    def test_variantes_trop_proches_detectees(self):
        """Un test entre reformulations ne peut rien reveler : il faut le dire."""
        resultat = dt.distinguer([
            "Le guide du freelance rentable",
            "Le guide du freelance qui devient rentable",
            "Guide : devenir un freelance rentable",
        ])
        self.assertFalse(resultat["testable"])
        self.assertTrue(resultat["paires_trop_proches"])

    def test_variantes_distinctes_acceptees(self):
        resultat = dt.distinguer([
            "Facturer mieux en travaillant moins",
            "Pourquoi votre agenda se vide apres chaque mission",
            "Sept canaux pour remplir un planning vide",
        ])
        self.assertTrue(resultat["testable"])
        self.assertLess(resultat["similarite_moyenne"], 0.3)

    def test_les_mots_outils_ne_creent_pas_de_fausse_ressemblance(self):
        proche = dt.similarite("Le guide pour les freelances de la vente",
                               "Le manuel pour les artisans de la photo")
        self.assertLess(proche, 0.2)


class TestRythmeDeVente(unittest.TestCase):
    """Comparer des variantes sans connaitre les vues.

    Le modele beta-binomial exige des vues, qu'aucune place de marche ne met
    dans son export : il faut aller les relever a l'ecran. Ce qu'un vendeur
    possede sans effort, c'est le nombre de ventes et la duree pendant
    laquelle chaque variante etait en ligne. Ce n'est pas un probleme
    binomial — il n'y a pas d'essais, il y a un comptage sur une duree.
    """

    def test_la_formule_exacte_et_le_tirage_concordent(self):
        """Meme garde-fou que pour le beta-binomial : deux chemins, un resultat."""
        for ka, ta, kb, tb in ((7, 14, 4, 12), (0, 14, 0, 14), (3, 10, 3, 10),
                               (20, 30, 5, 30), (1, 7, 9, 7), (48, 30, 12, 30)):
            exact = ex.probabilite_rythme_superieur(ka, ta, kb, tb)
            tirage = ex.comparer_rythmes(
                [(ka, ta), (kb, tb)])["variantes"][0]["probabilite_meilleure"]
            self.assertAlmostEqual(
                exact, tirage, delta=0.02,
                msg="{}/{}j vs {}/{}j : {:.4f} contre {:.4f}".format(
                    ka, ta, kb, tb, exact, tirage))

    def test_trois_variantes_identiques_ne_donnent_pas_de_gagnant(self):
        """Assez de ventes pour conclure, et pourtant rien a conclure."""
        comparaison = ex.comparer_rythmes([(20, 20), (20, 20), (20, 20)])
        for resultat in comparaison["variantes"]:
            self.assertAlmostEqual(resultat["probabilite_meilleure"], 1 / 3,
                                   delta=0.06)
        self.assertEqual(
            ex.verdict_rythme(comparaison)["etat"], "indecis")

    def test_la_duree_ne_tient_pas_lieu_de_preuve(self):
        """Cent jours sans vente ne renseignent sur rien."""
        comparaison = ex.comparer_rythmes([(1, 100), (0, 100)])
        conclusion = ex.verdict_rythme(comparaison)
        self.assertEqual(conclusion["etat"], "insuffisant")
        self.assertIn("du bruit", conclusion["message"])

    def test_un_ecart_franc_et_nourri_conclut(self):
        conclusion = ex.verdict_rythme(
            ex.comparer_rythmes([(48, 30), (12, 30)]))
        self.assertEqual(conclusion["etat"], "gagnant")
        self.assertEqual(conclusion["gagnante"], 0)

    def test_une_periode_plus_longue_ne_suffit_pas_a_gagner(self):
        """Le piege du modele : 20 ventes en 60 jours valent moins que 15 en 20."""
        comparaison = ex.comparer_rythmes([(20, 60), (15, 20)])
        self.assertGreater(comparaison["variantes"][1]["probabilite_meilleure"],
                           comparaison["variantes"][0]["probabilite_meilleure"])

    def test_le_verdict_nomme_la_variante_du_tableau(self):
        """Une variante ecartee decalait toutes les lettres suivantes.

        Avec A sans periode, B faible et C forte, le verdict annoncait
        « variante B gagnante » pour ce que le tableau juste au-dessus
        appelait C : la position dans la liste filtree n'est pas la lettre.
        """
        comparaison = ex.comparer_rythmes(
            [(0, 0.0), (5, 30.0), (60, 30.0)], etiquettes=["A", "B", "C"])
        self.assertEqual([r["etiquette"] for r in comparaison["variantes"]],
                         ["B", "C"])
        self.assertIn("Variante C", ex.verdict_rythme(comparaison)["message"])

    def test_une_variante_sans_duree_ne_gagne_pas(self):
        """Une duree nulle est une absence de mesure, pas une petite duree.

        Ramenee a 1e-6, elle donnait un rythme immense et la victoire quasi
        certaine a la variante qui n'avait rien mesure.
        """
        comparaison = ex.comparer_rythmes([(0, 0.0), (5, 30.0)])
        self.assertEqual(len(comparaison["variantes"]), 1)
        self.assertEqual(comparaison["variantes"][0]["ventes"], 5)

    def test_sans_aucune_duree_il_n_y_a_pas_de_comparaison(self):
        comparaison = ex.comparer_rythmes([(3, 0.0), (5, 0.0)])
        self.assertEqual(comparaison["variantes"], [])
        self.assertEqual(ex.verdict_rythme(comparaison)["etat"], "vide")

    def test_le_resultat_ne_change_pas_d_un_appel_a_l_autre(self):
        premier = ex.comparer_rythmes([(7, 14), (4, 12)])
        second = ex.comparer_rythmes([(7, 14), (4, 12)])
        self.assertEqual(premier, second)


class TestVentesReelles(unittest.TestCase):
    """Les chiffres viennent des ventes, plus de la saisie."""

    def setUp(self):
        from usine.core import store, ventes

        with store.cursor() as cur:
            cur.execute("DELETE FROM ventes")
        store.creer_produit("prod-ab", "ebook", "Le systeme", sujet="s",
                            dossier="/tmp")
        self.experience_id = ex.creer("Le systeme", sujet="titre",
                                              produit_id="prod-ab")
        self.a = ex.ajouter_variante(self.experience_id, "Titre A")
        self.b = ex.ajouter_variante(self.experience_id, "Titre B")
        self.ventes = ventes

    def _vendre(self, jour, nombre, rembourse=0):
        for index in range(nombre):
            self.ventes.enregistrer({
                "date": jour, "reference": "x", "unites": 1, "brut": 29.0,
                "net": None, "devise": "EUR", "remboursement": rembourse,
                "plateforme": "gumroad",
                "empreinte": "{}-{}-{}".format(jour, index, rembourse),
            }, produit_id="prod-ab")

    def test_chaque_variante_recoit_les_ventes_de_sa_periode(self):
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        ex.fixer_periode(self.b, "2026-07-15", "2026-07-28")
        self._vendre("2026-07-05", 3)
        self._vendre("2026-07-20", 8)
        mesures = ex.mesures_reelles(self.experience_id)
        self.assertEqual([m["ventes"] for m in mesures["variantes"]], [3, 8])
        self.assertEqual([m["jours"] for m in mesures["variantes"]], [14.0, 14.0])

    def test_une_vente_hors_periode_n_est_attribuee_a_personne(self):
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        self._vendre("2026-06-20", 5)
        mesures = ex.mesures_reelles(self.experience_id)
        self.assertEqual(mesures["variantes"][0]["ventes"], 0)

    def test_les_remboursements_ne_comptent_pas(self):
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        self._vendre("2026-07-05", 4)
        self._vendre("2026-07-06", 2, rembourse=1)
        self.assertEqual(
            ex.mesures_reelles(self.experience_id)["variantes"][0]["ventes"],
            4)

    def test_une_variante_sans_periode_est_signalee_pas_comptee_a_zero(self):
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        self._vendre("2026-07-05", 3)
        mesures = ex.mesures_reelles(self.experience_id)
        self.assertEqual(mesures["variantes"][1]["periode"], "")
        self.assertEqual(mesures["variantes"][1]["jours"], 0.0)

    def test_un_test_sans_produit_le_dit_au_lieu_de_deviner(self):
        orphelin = ex.creer("Sans produit", sujet="titre")
        ex.ajouter_variante(orphelin, "A")
        mesures = ex.mesures_reelles(orphelin)
        self.assertIn("sans produit", mesures["probleme"])
        self.assertEqual(mesures["variantes"], [])

    def test_une_journee_unique_compte_pour_un_jour(self):
        """Bornes comprises : sinon une periode d'un jour vaudrait zero."""
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-01")
        self._vendre("2026-07-01", 2)
        mesure = ex.mesures_reelles(self.experience_id)["variantes"][0]
        self.assertEqual((mesure["ventes"], mesure["jours"]), (2, 1.0))

    def test_une_periode_sans_date_de_debut_est_refusee(self):
        """« usine ab periode 7 » sans --du effacait la periode existante
        et annoncait une reussite."""
        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        with self.assertRaises(ValueError):
            ex.fixer_periode(self.a, "")
        mesure = ex.mesures_reelles(self.experience_id)["variantes"][0]
        self.assertTrue(mesure["periode"], "la periode ne doit pas etre effacee")

    def test_reporter_deux_fois_ne_compte_pas_les_ventes_deux_fois(self):
        """« observer » tient un journal ADDITIF ; les ventes sont un CUMUL.

        Reporter le cumul a chaque releve comptait chaque vente autant de
        fois qu'on relevait les vues — et pouvait faire depasser le nombre
        de vues, donc lever une erreur de saisie sur une saisie correcte.
        """
        from usine import cli

        ex.fixer_periode(self.a, "2026-07-01", "2026-07-14")
        self._vendre("2026-07-05", 7)
        for _ in range(3):
            ajout = cli._actions_reelles(self.a)
            ex.observer(self.a, vues=300, actions=ajout or 0)
        variante = ex.variantes(self.experience_id)[0]
        self.assertEqual(variante["total_actions"], 7)
        self.assertEqual(variante["total_vues"], 900)

    def test_une_date_malformee_est_refusee(self):
        with self.assertRaises(ValueError):
            ex.fixer_periode(self.a, "01/07/2026")
        with self.assertRaises(ValueError):
            ex.fixer_periode(self.a, "2026-07-14", "2026-07-01")


class TestGenerationVariantes(unittest.TestCase):
    """Chaine complete avec le simulateur, sans reseau."""

    @classmethod
    def setUpClass(cls):
        from usine.core import llm
        from tests.simulateur import simulateur

        llm.definir_simulateur(simulateur)
        cls.llm = llm

    @classmethod
    def tearDownClass(cls):
        cls.llm.definir_simulateur(None)

    def test_preparation_d_un_test_de_titres(self):
        from usine.pipelines import variantes
        from usine.pipelines.base import Contexte

        dossier = Path(tempfile.mkdtemp())
        contexte = Contexte(sujet="la prospection", audience="freelances",
                            hors_ligne=True, sans_image=True,
                            journal=lambda message: None)
        resultat = variantes.preparer_test(
            contexte, "Le systeme du freelance rentable", dossier,
            sujet="titre", nombre=5)
        self.assertEqual(len(resultat["variantes"]), 5)
        self.assertTrue(Path(resultat["planche"]).exists())
        for variante in resultat["variantes"]:
            self.assertTrue(variante["titre"])
            self.assertIn("diagnostic", variante)

    def test_preparation_de_couvertures_hors_ligne(self):
        from usine.pipelines import variantes
        from usine.pipelines.base import Contexte

        dossier = Path(tempfile.mkdtemp())
        contexte = Contexte(sujet="la prospection", hors_ligne=True,
                            sans_image=True, journal=lambda message: None)
        resultat = variantes.preparer_test(
            contexte, "Un titre", dossier, sujet="couverture", nombre=4)
        self.assertEqual(len(resultat["variantes"]), 4)
        fichiers = {v["fichier"] for v in resultat["variantes"]}
        self.assertEqual(len(fichiers), 4, "chaque couverture doit etre distincte")
        octets = [(dossier / f).read_bytes() for f in fichiers]
        self.assertEqual(len({o for o in octets}), 4,
                         "quatre fichiers identiques ne testeraient rien")
        for contenu in octets:
            self.assertTrue(contenu.startswith(b"\x89PNG"),
                            "une couverture testee doit etre livrable telle "
                            "quelle : les places de marche refusent le SVG")

    def test_la_planche_est_du_html_bien_forme(self):
        import html.parser

        from usine.pipelines import variantes
        from usine.pipelines.base import Contexte

        dossier = Path(tempfile.mkdtemp())
        contexte = Contexte(sujet="x", hors_ligne=True, sans_image=True,
                            journal=lambda message: None)
        resultat = variantes.preparer_test(contexte, "Un titre", dossier,
                                           sujet="titre", nombre=3)
        texte = Path(resultat["planche"]).read_text(encoding="utf-8")

        class Verificateur(html.parser.HTMLParser):
            vides = ("br", "img", "hr", "meta", "link", "input")

            def __init__(self):
                super().__init__()
                self.pile = []
                self.souci = []

            def handle_starttag(self, balise, attributs):
                if balise not in self.vides:
                    self.pile.append(balise)

            def handle_endtag(self, balise):
                if balise in self.vides:
                    return
                if not self.pile or self.pile[-1] != balise:
                    self.souci.append(balise)
                else:
                    self.pile.pop()

        verificateur = Verificateur()
        verificateur.feed(texte)
        self.assertEqual(verificateur.pile, [], "balises non refermees")
        self.assertEqual(verificateur.souci, [], "fermetures incoherentes")

    def test_le_contenu_des_variantes_est_echappe(self):
        from usine.pipelines import variantes

        identifiant = ex.creer("Produit", sujet="titre")
        ex.ajouter_variante(identifiant, "<script>alert(1)</script>")
        dossier = Path(tempfile.mkdtemp())
        chemin = variantes.planche(identifiant, dossier)
        texte = chemin.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", texte)
        self.assertIn("&lt;script&gt;", texte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
