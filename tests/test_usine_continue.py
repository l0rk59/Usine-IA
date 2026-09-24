"""Tests de la file de production, du budget et de l'usine continue.

Aucun appel reseau : le routeur IA est remplace par un simulateur.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import production  # noqa: E402
from usine.core import budget, config, file, llm, reglages, store  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402

BASE = dict(images=False, qualite="rapide", pause_entre_produits=0,
            budget_appels_jour=0, budget_appels_produit=0,
            budget_produits_jour=0, budget_minutes_produit=0,
            # Le pont telephone est simule test par test : par defaut, la
            # suite tourne comme sur une machine sans Termux.
            notifications=False, verrou_veille=False, batterie_minimum=0)


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("usine-continue")


def _remettre_a_zero():
    file.vider(tout=True)
    store.cache_vider()
    with store.cursor() as cur:
        cur.execute("DELETE FROM appels")
    reglages.ecrire(dict(BASE))
    for nom in ("usine.pid", "usine.stop", "usine-etat.json"):
        (config.WORKDIR / nom).unlink(missing_ok=True)


class TestFile(unittest.TestCase):
    def setUp(self):
        _remettre_a_zero()

    def test_priorite_avant_ordre_d_ajout(self):
        file.ajouter("tardif", "ebook", priorite=9)
        file.ajouter("urgent", "ebook", priorite=1)
        self.assertEqual(file.prochain()["sujet"], "urgent")

    def test_doublon_refuse_tant_qu_il_est_en_file(self):
        self.assertIsNotNone(file.ajouter("meme sujet", "ebook"))
        self.assertIsNone(file.ajouter("meme sujet", "ebook"))
        # Un autre type de produit sur le meme sujet reste legitime.
        self.assertIsNotNone(file.ajouter("meme sujet", "prompts"))

    def test_un_sujet_livre_peut_etre_relance(self):
        identifiant = file.ajouter("sujet", "ebook")
        entree = file.prochain()
        file.terminer(entree["id"], "produit-1")
        self.assertIsNotNone(file.ajouter("sujet", "ebook"),
                             "un sujet deja livre doit pouvoir etre refait")
        self.assertNotEqual(identifiant, None)

    def test_reprise_puis_condamnation(self):
        file.ajouter("fragile", "ebook", max_tentatives=2)
        entree = file.prochain()
        self.assertEqual(file.echouer(entree["id"], "reseau"), "en_attente")
        entree = file.prochain()
        self.assertEqual(file.echouer(entree["id"], "reseau"), "echec")
        self.assertEqual(file.compter()["echec"], 1)

    def test_rejouer_remet_les_echecs_en_file(self):
        file.ajouter("casse", "ebook", max_tentatives=1)
        entree = file.prochain()
        file.echouer(entree["id"], "erreur")
        self.assertEqual(file.rejouer(), 1)
        self.assertEqual(file.compter()["en_attente"], 1)

    def test_orphelins_liberes_au_demarrage(self):
        """Android tue le processus : l'entree en cours doit revenir en file."""
        file.ajouter("interrompu", "ebook")
        file.prochain()
        self.assertEqual(file.compter()["en_cours"], 1)
        self.assertEqual(file.liberer_orphelins(), 1)
        self.assertEqual(file.compter()["en_attente"], 1)

    def test_retirer_et_vider(self):
        identifiant = file.ajouter("a retirer", "ebook")
        self.assertTrue(file.retirer(identifiant))
        self.assertFalse(file.retirer(identifiant), "deux retraits ne font pas deux")
        self.assertEqual(file.compter()["annule"], 1)
        self.assertEqual(file.vider(), 1)


class TestBudget(unittest.TestCase):
    def setUp(self):
        _remettre_a_zero()
        budget.brancher(None)

    def tearDown(self):
        budget.brancher(None)

    def test_sans_plafond_rien_n_est_refuse(self):
        compteur = budget.Compteur(budget.Plafonds())
        compteur.demarrer_produit()
        for _ in range(50):
            store.enregistrer_appel("faux", "m", True)
            compteur.verifier_appel()  # ne doit pas lever

    def test_plafond_par_produit(self):
        compteur = budget.Compteur(budget.Plafonds(appels_produit=3))
        compteur.demarrer_produit()
        for _ in range(3):
            compteur.verifier_appel()
            store.enregistrer_appel("faux", "m", True)
        with self.assertRaises(budget.BudgetEpuise) as contexte:
            compteur.verifier_appel()
        self.assertEqual(contexte.exception.plafond, "appels par produit")

    def test_refus_de_demarrer_un_produit_infinissable(self):
        """Entamer un produit qu'on ne peut pas finir gaspille le reste."""
        compteur = budget.Compteur(
            budget.Plafonds(appels_jour=10, appels_produit=30))
        for _ in range(8):
            store.enregistrer_appel("faux", "m", True)
        motif = compteur.peut_demarrer_produit()
        self.assertIsNotNone(motif)
        self.assertIn("trop peu", motif)

    def test_plafond_de_produits_par_jour(self):
        compteur = budget.Compteur(budget.Plafonds(produits_jour=2))
        for _ in range(2):
            compteur.demarrer_produit()
            compteur.terminer_produit(reussi=True)
        self.assertIn("2 produit(s) par jour", compteur.peut_demarrer_produit() or "")

    def test_la_garde_est_consultee_par_le_routeur(self):
        compteur = budget.Compteur(budget.Plafonds(appels_jour=1))
        store.enregistrer_appel("faux", "m", True)
        budget.brancher(compteur)
        llm.definir_simulateur(lambda messages, role: "texte")
        try:
            with self.assertRaises(budget.BudgetEpuise):
                llm.generer("une invite inedite pour ce test", cache=False)
        finally:
            llm.definir_simulateur(None)

    def test_la_garde_ne_vaut_que_pour_son_fil(self):
        """Le tableau de bord fait tourner la boucle dans un fil. Un produit
        lance pendant ce temps par « Generer » se faisait couper par le
        plafond de la boucle — lui qui n'en a aucun."""
        import threading

        compteur = budget.Compteur(budget.Plafonds(appels_jour=1))
        store.enregistrer_appel("faux", "m", True)
        budget.brancher(compteur)
        llm.definir_simulateur(lambda messages, role: "texte")
        ailleurs = []

        def autre_fil():
            try:
                llm.generer("une invite d'un autre fil", cache=False)
                ailleurs.append("servi")
            except budget.BudgetEpuise:
                ailleurs.append("refuse")

        try:
            fil = threading.Thread(target=autre_fil)
            fil.start()
            fil.join(10)
            with self.assertRaises(budget.BudgetEpuise):
                llm.generer("une invite du fil de la boucle", cache=False)
        finally:
            llm.definir_simulateur(None)
        self.assertEqual(ailleurs, ["servi"])
        self.assertIn("appels par jour", compteur.refus)

    def test_le_plafond_par_produit_ne_compte_que_ce_produit(self):
        """Les appels d'un autre fil arrivent aussi en base. Relus comme
        ceux du produit, ils le coupaient avant son plafond : deux ebooks de
        dix appels, plafond a douze, sortaient inacheves tous les deux."""
        compteur = budget.Compteur(budget.Plafonds(appels_produit=2))
        compteur.demarrer_produit()
        compteur.verifier_appel()
        for _ in range(5):
            store.enregistrer_appel("un autre fil", "m", True)
        compteur.verifier_appel()
        with self.assertRaises(budget.BudgetEpuise):
            compteur.verifier_appel()

    def test_un_nouveau_produit_repart_de_zero(self):
        compteur = budget.Compteur(budget.Plafonds(appels_produit=2))
        compteur.demarrer_produit()
        compteur.verifier_appel()
        compteur.verifier_appel()
        compteur.terminer_produit()
        compteur.demarrer_produit()
        compteur.verifier_appel()     # ne doit pas lever

    def test_une_reponse_en_cache_ne_consomme_pas_de_budget(self):
        """Le cache est verifie avant le budget : relire ne coute rien."""
        compteur = budget.Compteur(budget.Plafonds(appels_jour=1))
        llm.definir_simulateur(lambda messages, role: "reponse mise en cache")
        try:
            invite = "invite mise en cache pour le test du budget"
            llm.generer(invite)                      # 1er appel : compte
            budget.brancher(compteur)
            reponse = llm.generer(invite)            # 2e : servi par le cache
            self.assertTrue(reponse.depuis_cache)
        finally:
            llm.definir_simulateur(None)


class LeCoutDUnProduitNeCompteQueLui(unittest.TestCase):
    """Deux ebooks fabriques en meme temps — le tableau de bord et la boucle —
    inscrivaient dix-huit appels chacun pour neuf chacun en realite : le
    produit comptait tout ce que la base avait recu pendant sa fabrication.
    « usine conseils » en tirait le type le plus economique."""

    def test_les_appels_d_un_autre_fil_ne_lui_sont_pas_imputes(self):
        from usine.pipelines import porte

        atelier.isoler("cout-par-produit")
        reglages.ecrire(dict(images=False, qualite="rapide"))
        propres = []

        def modele(messages, role):
            propres.append(1)
            if len(propres) == 1:
                # Ce qu'un autre fil fabrique pendant ce temps arrive aussi
                # en base.
                for _ in range(5):
                    store.enregistrer_appel("un autre fil", "m", True)
            return simulateur(messages, role)

        # Le fil de la boucle fabrique produit apres produit : ce qu'il a
        # fait AVANT celui-ci ne lui est pas impute non plus.
        llm.definir_simulateur(lambda messages, role: "un produit d'avant")
        for rang in range(4):
            llm.generer("un produit d'avant {}".format(rang), cache=False)
        llm.definir_simulateur(modele)
        try:
            ctx = porte.contexte("la paie des saisonniers", {}, lambda _m: None)
            porte.fabriquer("memo", ctx, {}, lambda _m: None)
        finally:
            llm.definir_simulateur(None)
        with store.cursor() as cur:
            cur.execute("SELECT appels, fournisseurs FROM productions"
                        " WHERE produit_id=?", (ctx.produit_id,))
            ligne = cur.fetchone()
        self.assertEqual(ligne["appels"], len(propres))
        self.assertNotIn("un autre fil", ligne["fournisseurs"])

    def test_chaque_fil_tient_son_propre_compte(self):
        import threading

        llm.definir_simulateur(lambda messages, role: "texte")
        comptes = {}
        # Les deux fils posent leur marque, travaillent, puis comptent — et
        # chacun attend l'autre entre deux etapes : le chevauchement est
        # garanti, pas laisse au hasard de l'ordonnanceur.
        ensemble = threading.Barrier(2)

        def travailler(nom, combien):
            marque = llm.marque_du_fil()
            ensemble.wait(5)
            for rang in range(combien):
                llm.generer("{} {}".format(nom, rang), cache=False)
            ensemble.wait(5)
            comptes[nom] = llm.appels_du_fil_depuis(marque)[0]

        try:
            fils = [threading.Thread(target=travailler, args=(n, c))
                    for n, c in (("a", 2), ("b", 3))]
            for fil in fils:
                fil.start()
            for fil in fils:
                fil.join(10)
        finally:
            llm.definir_simulateur(None)
        self.assertEqual(comptes, {"a": 2, "b": 3})


class LesMemoiresDUnServeurQuiDure(unittest.TestCase):
    """Ce qui tourne des jours sur un telephone ne doit pas grandir sans fin."""

    def test_le_journal_des_appels_du_fil_reste_borne_et_juste(self):
        limite = llm.JOURNAL_DU_FIL_MAX
        llm.JOURNAL_DU_FIL_MAX = 10
        llm.definir_simulateur(lambda messages, role: "texte")
        try:
            for rang in range(37):
                llm.generer("un appel d'avant {}".format(rang), cache=False)
            marque = llm.marque_du_fil()
            for rang in range(4):
                llm.generer("un appel du produit {}".format(rang), cache=False)
            self.assertEqual(llm.appels_du_fil_depuis(marque)[0], 4)
            self.assertLessEqual(len(llm._fil.appels), 10)
        finally:
            llm.JOURNAL_DU_FIL_MAX = limite
            llm.definir_simulateur(None)

    def test_les_travaux_termines_ne_s_accumulent_pas(self):
        from usine.web import serveur

        sauve = dict(serveur.TRAVAUX)
        serveur.TRAVAUX.clear()
        try:
            for rang in range(45):
                serveur.TRAVAUX["fini-{}".format(rang)] = {
                    "id": "fini-{}".format(rang), "statut": "termine",
                    "debut": float(rang), "journal": ["..."] * 50}
            serveur.TRAVAUX["en-cours"] = {"id": "en-cours", "statut": "en_cours",
                                           "debut": 0.0, "journal": []}
            serveur._ranger_travaux()
            finis = [t for t in serveur.TRAVAUX.values() if t["statut"] != "en_cours"]
            self.assertEqual(len(finis), serveur.TRAVAUX_TERMINES_GARDES)
            self.assertIn("en-cours", serveur.TRAVAUX,
                          "un travail en cours ne s'oublie jamais")
            self.assertIn("fini-44", serveur.TRAVAUX, "les plus recents restent")
            self.assertNotIn("fini-0", serveur.TRAVAUX)
        finally:
            serveur.TRAVAUX.clear()
            serveur.TRAVAUX.update(sauve)


class TestUsineContinue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def setUp(self):
        _remettre_a_zero()

    def _moteur(self, **kwargs):
        return production.UsineContinue(journal=lambda m: None, pause=0, **kwargs)

    def test_la_file_est_consommee(self):
        for i in range(3):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 3)
        self.assertEqual(file.compter()["en_attente"], 0)
        self.assertEqual(file.compter()["fait"], 3)
        self.assertEqual(moteur.motif_fin, "file vide")

    def test_maximum_respecte_et_file_preservee(self):
        for i in range(4):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur(maximum=2)
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 2)
        self.assertEqual(file.compter()["en_attente"], 2)

    def test_budget_journalier_empeche_de_demarrer(self):
        reglages.ecrire(dict(BASE, budget_appels_jour=4))
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 0)
        self.assertIn("trop peu", moteur.motif_fin)
        self.assertEqual(file.compter()["en_attente"], 1,
                         "la niche doit rester en file")

    def test_budget_epuise_en_cours_exporte_quand_meme(self):
        """Promesse tenue : un plafond atteint ne detruit pas le travail fait."""
        reglages.ecrire(dict(BASE, budget_appels_produit=5))
        file.ajouter("sujet tronque", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1, "le produit doit etre livre")
        dossier = Path(moteur.faits[0]["dossier"])
        fichiers = [f.name for f in dossier.iterdir() if f.is_file()]
        self.assertTrue(any(f.endswith(".pdf") for f in fichiers))
        self.assertTrue(any(f.endswith(".epub") for f in fichiers))
        self.assertIn("livre.md", fichiers)
        self.assertGreater((dossier / "livre.md").stat().st_size, 500)
        self.assertIn("budget epuise", moteur.motif_fin)

    def test_type_inconnu_ne_bloque_pas_la_file(self):
        file.ajouter("mauvais type", "inexistant")
        file.ajouter("bon sujet", "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1)

    def test_arret_entre_deux_produits(self):
        """Le drapeau d'arret est lu entre deux produits, pas au milieu d'un."""
        for i in range(4):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        moteur = self._moteur()
        original = moteur._fabriquer

        def fabriquer_puis_demander(entree):
            resultat = original(entree)
            (config.WORKDIR / "usine.stop").write_text("stop", encoding="utf-8")
            return resultat

        moteur._fabriquer = fabriquer_puis_demander
        moteur.tourner()
        self.assertEqual(len(moteur.faits), 1)
        self.assertEqual(file.compter()["en_attente"], 3,
                         "les niches non traitees doivent rester en file")

    def test_verrou_empeche_deux_usines(self):
        production._poser_verrou()
        try:
            self.assertEqual(production.verrou_actif(), os.getpid())
            self.assertEqual(self._moteur().tourner(), 1)
        finally:
            production._lever_verrou()

    def test_verrou_orphelin_est_nettoye(self):
        """Un processus tue laisse un verrou qui ment : il doit etre ignore."""
        (config.WORKDIR / "usine.pid").write_text("999999", encoding="utf-8")
        self.assertIsNone(production.verrou_actif())
        self.assertFalse((config.WORKDIR / "usine.pid").exists())

    def test_etat_lisible_depuis_un_autre_processus(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        self._moteur().tourner()
        etat = production.statut()
        self.assertFalse(etat["en_marche"])
        self.assertEqual(etat["session"]["nombre_faits"], 1)
        self.assertIn("budget", etat)

    def test_ecriture_d_etat_atomique(self):
        """Aucun lecteur ne doit pouvoir tomber sur un fichier a moitie ecrit."""
        production.ecrire_etat({"a": 1})
        self.assertEqual(production.lire_etat()["a"], 1)
        self.assertFalse(
            production.chemin_etat().with_suffix(".json.tmp").exists(),
            "le fichier temporaire doit avoir ete renomme")

    def test_etat_illisible_ne_casse_rien(self):
        production.chemin_etat().write_text("{ pas du json", encoding="utf-8")
        self.assertEqual(production.lire_etat(), {})


class FauxTelephone:
    """Un telephone qui note ce qu'on lui demande, sans Termux sous la main."""

    def __init__(self, motifs=None):
        self.motifs = list(motifs or [])
        self.planchers = []
        self.notifications = []
        self.verrous = []

    def batterie_trop_faible(self, plancher):
        self.planchers.append(plancher)
        return self.motifs.pop(0) if self.motifs else ""

    def notifier(self, titre, contenu="", ouvrir=None, urgente=False):
        self.notifications.append({"titre": titre, "contenu": contenu,
                                   "ouvrir": ouvrir, "urgente": urgente})
        return True

    def verrou_veille(self, actif):
        self.verrous.append(actif)
        return True


class TestTelephonePendantLaProduction(unittest.TestCase):
    """L'usine tourne des heures sur un telephone : elle doit le menager.

    Ces trois comportements ne se voient que dans la boucle : le module
    « core.telephone » se teste a part, ici on verifie qu'il est APPELE, au
    bon moment, et avec les reglages de l'utilisateur.
    """

    @classmethod
    def setUpClass(cls):
        llm.definir_simulateur(simulateur)

    @classmethod
    def tearDownClass(cls):
        llm.definir_simulateur(None)

    def setUp(self):
        _remettre_a_zero()

    def _tourner(self, faux, **profil):
        if profil:
            reglages.ecrire(dict(BASE, **profil))
        moteur = production.UsineContinue(journal=lambda m: None, pause=0)
        with mock.patch.object(production, "telephone", faux):
            moteur.tourner()
        return moteur

    # -- batterie ---------------------------------------------------------
    def test_batterie_faible_arrete_avant_le_premier_produit(self):
        for i in range(2):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        faux = FauxTelephone(motifs=["batterie a 9 % (plancher 20 %)"])
        moteur = self._tourner(faux, batterie_minimum=20)
        self.assertEqual(len(moteur.faits), 0)
        self.assertIn("batterie", moteur.motif_fin)
        self.assertEqual(file.compter()["en_attente"], 2,
                         "les niches doivent rester en file, intactes")

    def test_batterie_relue_entre_chaque_produit(self):
        """Elle se vide PENDANT la session : une seule lecture ne suffit pas."""
        for i in range(3):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        faux = FauxTelephone(motifs=["", "batterie a 11 % (plancher 20 %)"])
        moteur = self._tourner(faux, batterie_minimum=20)
        self.assertEqual(len(moteur.faits), 1,
                         "le produit en cours va au bout, le suivant ne demarre pas")
        self.assertEqual(file.compter()["en_attente"], 2)

    def test_le_plancher_regle_est_celui_transmis(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, batterie_minimum=35)
        self.assertEqual(faux.planchers[0], 35)

    def test_plancher_zero_laisse_tourner(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone(motifs=["batterie a 2 %"])
        # Le garde-fou coupe est transmis tel quel : c'est « core.telephone »
        # qui refuse alors de lire la batterie, pas la boucle.
        moteur = self._tourner(faux, batterie_minimum=0)
        self.assertEqual(faux.planchers[0], 0)
        self.assertEqual(len(moteur.faits), 0)  # le faux repond quand meme

    # -- notifications -----------------------------------------------------
    def test_une_notification_par_produit_et_une_en_fin_de_session(self):
        for i in range(2):
            file.ajouter("sujet {}".format(i), "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        moteur = self._tourner(faux, notifications=True)
        self.assertEqual(len(moteur.faits), 2)
        self.assertEqual(len(faux.notifications), 3)
        self.assertIn("Produit 1", faux.notifications[0]["titre"])
        self.assertIn("Produit 2", faux.notifications[1]["titre"])
        self.assertIn("2 produit(s)", faux.notifications[-1]["titre"])

    def test_la_notification_ouvre_le_pdf_du_produit(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, notifications=True)
        ouvrir = faux.notifications[0]["ouvrir"]
        self.assertIsNotNone(ouvrir)
        self.assertEqual(ouvrir.suffix, ".pdf")
        self.assertTrue(ouvrir.exists())

    def test_la_notification_vise_le_document_principal(self):
        """Une annexe ne doit pas passer devant le livre.

        « guide-annexe.pdf » trie AVANT « guide.pdf » — le tiret trie avant
        le point. Lister le dossier designerait donc l'annexe. L'ordre du
        resume de fabrication, lui, met le document principal en tete.
        """
        dossier = config.WORKDIR / "produit-annexe"
        dossier.mkdir(exist_ok=True)
        for nom in ("guide.pdf", "guide-annexe.pdf", "guide.epub"):
            (dossier / nom).write_bytes(b"%PDF-1.4")
        moteur = production.UsineContinue(journal=lambda m: None, pause=0)
        vise = moteur._fichier_a_montrer(
            {"dossier": str(dossier),
             "fichiers": ["guide.pdf", "guide-annexe.pdf", "guide.epub"]})
        self.assertEqual(vise.name, "guide.pdf")

    def test_sans_pdf_la_notification_se_rabat_proprement(self):
        dossier = config.WORKDIR / "produit-sans-pdf"
        dossier.mkdir(exist_ok=True)
        (dossier / "livre.epub").write_bytes(b"PK")
        moteur = production.UsineContinue(journal=lambda m: None, pause=0)
        self.assertEqual(
            moteur._fichier_a_montrer({"dossier": str(dossier),
                                       "fichiers": ["livre.epub"]}).name,
            "livre.epub")
        # Un nom annonce mais absent du disque ne doit pas donner un chemin
        # mort a la notification : on retombe sur le dossier.
        self.assertEqual(
            moteur._fichier_a_montrer({"dossier": str(dossier),
                                       "fichiers": ["disparu.pdf"]}), dossier)
        self.assertIsNone(moteur._fichier_a_montrer({"fichiers": ["x.pdf"]}))

    def test_seule_la_batterie_donne_une_notification_prioritaire(self):
        """« file vide » n'est pas une urgence ; un telephone a plat, si."""
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, notifications=True)
        self.assertFalse(faux.notifications[-1]["urgente"])

        _remettre_a_zero()
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone(motifs=["batterie a 5 %"])
        self._tourner(faux, notifications=True, batterie_minimum=20)
        self.assertTrue(faux.notifications[-1]["urgente"])

    def test_reglage_a_non_coupe_toutes_les_notifications(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, notifications=False)
        self.assertEqual(faux.notifications, [])

    # -- verrou de veille --------------------------------------------------
    def test_verrou_de_veille_pris_puis_relache(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, verrou_veille=True)
        self.assertEqual(faux.verrous, [True, False],
                         "pris au demarrage, relache a la fin — jamais oublie")

    def test_verrou_relache_meme_apres_une_interruption(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        reglages.ecrire(dict(BASE, verrou_veille=True))
        faux = FauxTelephone()
        moteur = production.UsineContinue(journal=lambda m: None, pause=0)
        moteur._fabriquer = mock.Mock(side_effect=KeyboardInterrupt)
        with mock.patch.object(production, "telephone", faux):
            self.assertEqual(moteur.tourner(), 130)
        self.assertEqual(faux.verrous, [True, False],
                         "un Ctrl+C ne doit pas laisser le telephone eveille")

    def test_verrou_non_demande_n_est_pas_pris(self):
        file.ajouter("sujet", "ebook", options={"taille": "mini"})
        faux = FauxTelephone()
        self._tourner(faux, verrou_veille=False)
        self.assertEqual(faux.verrous, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestVerrouAtomique(unittest.TestCase):
    """Deux usines ne doivent jamais tourner ensemble.

    Le verrou etait pris en deux temps — verifier qu'il est libre, puis
    l'ecrire — avec un intervalle entre les deux. Deux « usine usine
    demarrer » lancees dans la meme seconde le voyaient toutes deux libre, et
    la seconde ecrasait le PID de la premiere : « arreter » n'en arretait donc
    qu'une, pendant que l'autre continuait a consommer le budget et a tirer
    sur la meme file.
    """

    def setUp(self):
        production._lever_verrou()

    def tearDown(self):
        production._lever_verrou()

    def test_la_seconde_prise_echoue(self):
        self.assertTrue(production._poser_verrou())
        self.assertFalse(production._poser_verrou())

    def test_le_verrou_se_reprend_apres_liberation(self):
        self.assertTrue(production._poser_verrou())
        production._lever_verrou()
        self.assertTrue(production._poser_verrou())

    def test_le_pid_de_la_premiere_n_est_pas_ecrase(self):
        """Le vrai degat : « arreter » visait le mauvais processus."""
        production._poser_verrou()
        pid = production.chemin_verrou().read_text(encoding="utf-8").strip()
        production._poser_verrou()
        self.assertEqual(
            production.chemin_verrou().read_text(encoding="utf-8").strip(), pid)

    def test_un_verrou_orphelin_est_repris(self):
        """Android tue les processus sans preavis : un verrou qui ment ne
        doit pas interdire toute production jusqu'au prochain redemarrage."""
        production.chemin_verrou().write_text("999999", encoding="utf-8")
        self.assertTrue(production._poser_verrou())

    def test_un_verrou_illisible_est_repris(self):
        production.chemin_verrou().write_text("ce n'est pas un pid",
                                              encoding="utf-8")
        self.assertTrue(production._poser_verrou())

    def test_l_usine_refuse_de_demarrer_si_le_verrou_est_pris(self):
        production._poser_verrou()
        dits = []
        code = production.UsineContinue(journal=dits.append).tourner()
        self.assertEqual(code, 1)
        self.assertTrue(any("tourne deja" in d for d in dits))
