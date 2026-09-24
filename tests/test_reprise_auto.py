"""L'usine continue finit seule un produit coupe par les quotas.

Journal reel du 16/09/2026, roman de dix-huit scenes : les quotas s'epuisent a
la huitieme, dix scenes restent a ecrire, et l'usine continue marquait la
niche « faite » avant de s'arreter. Le produit attendait sur le disque qu'on
pense a appuyer sur « Reprendre ».

Ce module mesure le contraire : la niche repart en tete de file, l'usine
attend que le routeur voie un fournisseur rouvrir, puis finit CE produit — pas
un autre. Et il garde les deux limites : le plafond que l'utilisateur s'est
fixe arrete l'usine comme avant, et une section qui echoue toujours, alors que
les fournisseurs repondent, finit par etre abandonnee.

AUCUN test de ce module ne sort sur le reseau, ni ne dort vraiment.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


def setUpModule():
    atelier.isoler("reprise-auto")


from usine import production  # noqa: E402
from usine.core import cles as pool_cles  # noqa: E402
from usine.core import config, file, llm, reglages, store, telephone  # noqa: E402

BASE = dict(images=False, qualite="rapide", pause_entre_produits=0,
            budget_appels_jour=0, budget_appels_produit=0,
            budget_produits_jour=0, budget_minutes_produit=0,
            notifications=False, verrou_veille=False, batterie_minimum=0)


class Fournisseurs:
    """Le simulateur, qui se tait apres N appels jusqu'a ce qu'on le rouvre."""

    def __init__(self, coupe_apres=None, toujours_en_echec=""):
        self.appels = 0
        self.coupe_apres = coupe_apres
        self.ouverts = True
        self.toujours_en_echec = toujours_en_echec

    def __call__(self, messages, role):
        self.appels += 1
        invite = messages[-1]["content"]
        if self.toujours_en_echec and self.toujours_en_echec in invite:
            raise ValueError("reponse illisible, a chaque fois")
        if self.coupe_apres is not None and self.appels > self.coupe_apres:
            self.ouverts = False
        if not self.ouverts:
            raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
        return simulateur(messages, role)


class Moteur(production.UsineContinue):
    """L'usine continue, dont le sommeil est mesure au lieu d'etre dormi.

    Dormir rouvre les fournisseurs : c'est ce qui se passe dans la realite
    pendant l'attente, et c'est ce qu'on veut voir l'usine exploiter.
    """

    def __init__(self, fournisseurs, **kwargs):
        super().__init__(journal=self.noter, pause=0, **kwargs)
        self.lignes = []
        self.sommeils = []
        self.fournisseurs = fournisseurs

    def noter(self, message):
        self.lignes.append(message)

    def _fabriquer(self, entree):
        # Un garde-fou de banc d'essai : une boucle qui ne renonce jamais doit
        # faire ECHOUER le test, pas le figer jusqu'au delai de la campagne.
        self.essais = getattr(self, "essais", 0) + 1
        if self.essais > 12:
            self.arret_demande = True
            return False
        return super()._fabriquer(entree)

    def _dormir(self, secondes):
        self.sommeils.append(secondes)
        self.fournisseurs.ouverts = True
        self.fournisseurs.coupe_apres = None
        return True


class _Cas(unittest.TestCase):

    def setUp(self):
        atelier.isoler("reprise-auto-{}".format(self.id().rsplit(".", 1)[-1]))
        reglages.ecrire(dict(BASE))
        self._ouverture = llm.prochaine_ouverture
        # Le routeur est interroge sans reseau : on lui fait dire ce qu'il
        # dirait si le premier fournisseur rouvrait dans cinq minutes.
        llm.prochaine_ouverture = lambda role="standard": 300.0

    def tearDown(self):
        llm.prochaine_ouverture = self._ouverture
        llm.definir_simulateur(None)


class UnProduitCoupeEstFiniSeul(_Cas):

    def test_la_niche_attend_puis_finit_le_meme_produit(self):
        fournisseurs = Fournisseurs(coupe_apres=9)
        llm.definir_simulateur(fournisseurs)
        file.ajouter("la facturation des independants", "ebook",
                     options={"chapitres": 6})
        moteur = Moteur(fournisseurs)
        moteur.tourner()

        produits = store.lister_produits()
        self.assertEqual(len(produits), 1, "un seul produit : le meme, fini")
        self.assertEqual(produits[0]["statut"], "pret")
        self.assertEqual(file.compter()["fait"], 1)
        self.assertEqual(len(moteur.faits), 1)
        # Une attente, reglee sur ce que dit le routeur — pas un arret.
        self.assertEqual(moteur.sommeils, [300])
        self.assertTrue(any("reprise automatique" in l for l in moteur.lignes))
        self.assertTrue(any("depuis son carnet" in l for l in moteur.lignes))

    def test_l_attente_respecte_un_plancher(self):
        """« 0 » du routeur n'est pas une promesse : il ne voit pas un reseau
        coupe. Reprendre a la seconde meme bruler la reprise pour rien."""
        llm.prochaine_ouverture = lambda role="standard": 0.0
        fournisseurs = Fournisseurs(coupe_apres=9)
        llm.definir_simulateur(fournisseurs)
        file.ajouter("la note de frais", "ebook", options={"chapitres": 6})
        moteur = Moteur(fournisseurs)
        moteur.tourner()
        self.assertEqual(moteur.sommeils, [production.PALIERS_D_ATTENTE[0]])
        self.assertEqual(store.lister_produits()[0]["statut"], "pret")

    def test_sans_aucun_fournisseur_possible_l_usine_le_dit_et_s_arrete(self):
        llm.prochaine_ouverture = lambda role="standard": None
        fournisseurs = Fournisseurs(coupe_apres=9)
        llm.definir_simulateur(fournisseurs)
        file.ajouter("le devis des artisans", "ebook", options={"chapitres": 6})
        moteur = Moteur(fournisseurs)
        moteur.tourner()
        self.assertEqual(moteur.sommeils, [])
        self.assertIn("aucun fournisseur", moteur.motif_fin)
        # La niche attend en tete de file : la prochaine session la finira.
        entree = file.prochain()
        self.assertEqual(entree["options"]["reprendre_id"],
                         store.lister_produits()[0]["id"])

    def test_le_verrou_de_veille_est_relache_pendant_l_attente(self):
        """Une attente de quota peut durer jusqu'a minuit UTC. Garder le
        telephone eveille pour ne rien calculer videait la batterie."""
        reglages.ecrire(dict(BASE, verrou_veille=True))
        appels = []
        vrai = telephone.verrou_veille
        telephone.verrou_veille = lambda actif: appels.append(actif) or True
        try:
            fournisseurs = Fournisseurs(coupe_apres=9)
            llm.definir_simulateur(fournisseurs)
            file.ajouter("la paie des associations", "ebook",
                         options={"chapitres": 6})
            Moteur(fournisseurs).tourner()
        finally:
            telephone.verrou_veille = vrai
        # pris au debut, relache pour attendre, repris, relache a la fin
        self.assertEqual(appels, [True, False, True, False])


class LeBoutonGenererNeLaissePasDeTrou(_Cas):
    """Le bouton « Generer » fabrique hors de la boucle. Coupe par les
    quotas, son produit attendait qu'on revienne appuyer sur « Reprendre »."""

    def test_le_produit_coupe_est_confie_a_la_boucle_et_fini(self):
        from usine.web import serveur

        fournisseurs = Fournisseurs(coupe_apres=9)
        llm.definir_simulateur(fournisseurs)
        sommeils = []

        def dormir(moteur, secondes):
            sommeils.append(secondes)
            fournisseurs.ouverts, fournisseurs.coupe_apres = True, None
            return True

        vrai_dormir = production.UsineContinue._dormir
        vraie_boucle = serveur._lancer_la_boucle
        fils = []
        production.UsineContinue._dormir = dormir
        serveur._lancer_la_boucle = lambda **kw: fils.append(vraie_boucle(**kw)) or fils[-1]
        # Une autre niche attend dans la file : personne n'a demande de la
        # fabriquer maintenant, la boucle ne doit finir QUE le produit coupe.
        file.ajouter("une autre niche", "ebook", options={"chapitres": 6})
        serveur.TRAVAUX["g1"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer("g1", "ebook", {"sujet": "le devis des artisans",
                                           "chapitres": 6})
            for fil in fils:
                fil.join(60)
            journal = " ".join(str(l) for l in serveur.TRAVAUX["g1"]["journal"])
        finally:
            production.UsineContinue._dormir = vrai_dormir
            serveur._lancer_la_boucle = vraie_boucle
            serveur.TRAVAUX.pop("g1", None)

        self.assertEqual(len(fils), 1, "la boucle doit etre lancee, une fois")
        self.assertIn("rien a faire", journal)
        produits = store.lister_produits()
        self.assertEqual(len(produits), 1)
        self.assertEqual(produits[0]["statut"], "pret")
        self.assertEqual(sommeils, [300])
        self.assertEqual(file.compter()["en_attente"], 1,
                         "l'autre niche attend toujours qu'on la demande")

    def test_un_produit_complet_ne_derange_pas_la_boucle(self):
        from usine.web import serveur

        llm.definir_simulateur(Fournisseurs())
        vraie_boucle = serveur._lancer_la_boucle
        lances = []
        serveur._lancer_la_boucle = lambda **kw: lances.append(kw)
        serveur.TRAVAUX["g2"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer("g2", "ebook", {"sujet": "la paie des associations",
                                           "chapitres": 6})
        finally:
            serveur._lancer_la_boucle = vraie_boucle
            serveur.TRAVAUX.pop("g2", None)
        self.assertEqual(lances, [])
        self.assertEqual(file.compter()["total"], 0)


    def test_un_trou_qui_n_est_pas_un_quota_reste_a_la_main(self):
        """Une section illisible a chaque essai : attendre ne la reparera
        pas, et la confier a la boucle la ferait tourner pour rien."""
        from usine.web import serveur

        llm.definir_simulateur(Fournisseurs(
            toujours_en_echec="Redige le chapitre 2 sur"))
        vraie_boucle = serveur._lancer_la_boucle
        lances = []
        serveur._lancer_la_boucle = lambda **kw: lances.append(kw)
        serveur.TRAVAUX["g3"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer("g3", "ebook", {"sujet": "la note de frais",
                                           "chapitres": 6})
        finally:
            serveur._lancer_la_boucle = vraie_boucle
            serveur.TRAVAUX.pop("g3", None)
        self.assertEqual(store.lister_produits()[0]["statut"], "en_cours")
        self.assertEqual(lances, [])
        self.assertEqual(file.compter()["total"], 0)


class LesDeuxLimites(_Cas):

    def test_le_plafond_de_l_utilisateur_arrete_sans_attendre(self):
        """Son plafond, c'est a lui de le lever — pas a l'usine d'attendre
        qu'il disparaisse. Le premier essai de cette correction attendait
        soixante secondes sur un plafond « appels par produit »."""
        reglages.ecrire(dict(BASE, budget_appels_produit=5))
        fournisseurs = Fournisseurs()
        llm.definir_simulateur(fournisseurs)
        file.ajouter("sujet tronque", "ebook", options={"taille": "mini"})
        moteur = Moteur(fournisseurs)
        moteur.tourner()
        self.assertEqual(moteur.sommeils, [])
        self.assertEqual(moteur.motif_fin, "budget epuise pendant la fabrication")

    def test_une_section_qui_echoue_toujours_finit_abandonnee(self):
        fournisseurs = Fournisseurs(toujours_en_echec="Redige le chapitre 2 sur")
        llm.definir_simulateur(fournisseurs)
        file.ajouter("la tresorerie des artisans", "ebook",
                     options={"chapitres": 6})
        moteur = Moteur(fournisseurs)
        moteur.tourner()
        self.assertEqual(moteur.sommeils, [], "rien ne s'epuisait : rien a attendre")
        self.assertEqual(file.compter()["echec"], 1)
        self.assertEqual(store.lister_produits()[0]["statut"], "en_cours")
        self.assertTrue(any("reessayer a la main" in l for l in moteur.lignes))


class UneSeuleRepriseParProduit(_Cas):
    """La boucle finit un produit confie par le bouton « Generer » ; si l'on
    appuie aussi sur « Reprendre », deux reprises ecrivaient le meme carnet
    en meme temps, et l'une mourait sur « carnet.json.tmp »."""

    def _produit_coupe(self, sujet):
        from usine.web import serveur

        llm.definir_simulateur(Fournisseurs(coupe_apres=9))
        vraie_boucle = serveur._lancer_la_boucle
        serveur._lancer_la_boucle = lambda **_kw: None
        serveur.TRAVAUX["v"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer("v", "ebook", {"sujet": sujet, "chapitres": 6})
        finally:
            serveur._lancer_la_boucle = vraie_boucle
            serveur.TRAVAUX.pop("v", None)
        return store.lister_produits()[0]

    def test_une_seconde_reprise_est_refusee_pendant_la_premiere(self):
        from usine.core import verrou
        from usine.pipelines import reprise

        produit = self._produit_coupe("la note de frais des artisans")
        llm.definir_simulateur(Fournisseurs())
        garde = Path(produit["dossier"]) / ".reprise.pid"
        self.assertTrue(verrou.prendre(garde))    # la premiere, en cours
        try:
            with self.assertRaises(reprise.DejaEnReprise):
                reprise.reprendre(produit["id"], journal=lambda _m: None)
        finally:
            garde.unlink(missing_ok=True)
        reprise.reprendre(produit["id"], journal=lambda _m: None)
        self.assertEqual(store.lire_produit(produit["id"])["statut"], "pret")
        self.assertFalse(garde.exists(), "le verrou est rendu apres la reprise")

    def test_la_boucle_laisse_faire_qui_finit_deja(self):
        """Compter « deja en reprise » comme un echec ferait abandonner une
        niche dont le produit est justement en train d'aboutir."""
        from usine.core import verrou

        produit = self._produit_coupe("le budget des artisans")
        production.confier_a_la_boucle("ebook", produit["sujet"], produit["id"], 1)
        garde = Path(produit["dossier"]) / ".reprise.pid"
        self.assertTrue(verrou.prendre(garde))
        fournisseurs = Fournisseurs()
        llm.definir_simulateur(fournisseurs)
        try:
            moteur = Moteur(fournisseurs)
            moteur.tourner()
        finally:
            garde.unlink(missing_ok=True)
        self.assertEqual(file.compter()["echec"], 0)
        self.assertEqual(file.compter()["fait"], 1)
        self.assertTrue(any("la boucle le laisse faire" in l for l in moteur.lignes))

    def test_deux_ecrivains_du_meme_carnet_ne_se_tuent_pas(self):
        """La seconde ceinture : deux fils qui ecrivent le carnet ensemble."""
        import tempfile
        import threading

        from usine.pipelines import carnet

        dossier = Path(tempfile.mkdtemp())
        erreurs = []

        def ecrire(n):
            for i in range(60):
                try:
                    carnet.noter_section(dossier, "s{}-{}".format(n, i),
                                         "titre", "corps " * 50)
                except Exception as exc:          # noqa: BLE001
                    erreurs.append(repr(exc))

        fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(6)]
        for fil in fils:
            fil.start()
        for fil in fils:
            fil.join()
        self.assertEqual(erreurs, [])


class LAttenteSeVoit(_Cas):
    """Une attente de quota peut durer jusqu'a minuit UTC. Elle s'affichait
    « En cours », comme une fabrication : on croyait l'usine bloquee, et on
    l'arretait au moment ou elle allait finir."""

    def test_le_statut_dit_l_attente_et_l_heure_de_reprise(self):
        import io
        from contextlib import redirect_stdout

        from usine import cli

        production._poser_verrou()
        self.addCleanup(production._lever_verrou)
        fin = time.time() + 3 * 3600
        production.ecrire_etat({
            "pid": os.getpid(), "demarre_le": time.time(), "duree": 5,
            "faits": [], "nombre_faits": 0, "motif_fin": "",
            "courant": {"id": 1, "sujet": "Echos d'acier", "type": "roman",
                        "depuis": time.time(), "attente_jusqu_a": fin}})
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            cli.principal(["usine", "statut"])
        texte = sortie.getvalue()
        self.assertIn("En attente des fournisseurs", texte)
        self.assertIn(time.strftime("%H:%M", time.localtime(fin)), texte)
        self.assertNotIn("En cours", texte)

    def test_le_tableau_de_bord_le_dit_aussi(self):
        """Verifie dans un vrai navigateur le 24/09/2026 ; ici, on garde que
        le script lit bien la cle que la boucle publie."""
        script = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        self.assertIn("courant.attente_jusqu_a", script)
        source = (RACINE / "usine" / "production.py").read_text(encoding="utf-8")
        self.assertIn('"attente_jusqu_a": fin', source)


class LeProgresSeCompteEnSections(unittest.TestCase):
    """« sans_progres » decide quand renoncer : il ne doit monter que quand
    une reprise n'a rien ecrit de plus."""

    def setUp(self):
        atelier.isoler("reprise-auto-progres")
        file.vider(tout=True)

    def test_une_reprise_qui_avance_remet_le_compte_a_zero(self):
        file.ajouter("un sujet", "ebook")
        entree = file.prochain()
        self.assertEqual(file.a_finir(entree["id"], "p", 5)["sans_progres"], 0)
        self.assertEqual(file.a_finir(entree["id"], "p", 3)["sans_progres"], 0)
        self.assertEqual(file.a_finir(entree["id"], "p", 3)["sans_progres"], 1)
        self.assertEqual(file.a_finir(entree["id"], "p", 3)["sans_progres"], 2)
        self.assertEqual(file.a_finir(entree["id"], "p", 1)["sans_progres"], 0)


class CeQueLeRouteurSaitDuRetour(unittest.TestCase):
    """« prochaine_ouverture » relit les repos et les quotas ; elle ne devine rien."""

    def setUp(self):
        atelier.isoler("reprise-auto-routeur")
        self._ordre, self._quota = config.provider_order, llm._quota_ok
        config.provider_order = lambda: ["groq"]
        os.environ["GROQ_API_KEY"] = "gsk_" + "R" * 40
        pool_cles.oublier()
        llm._REPOS.clear()

    def tearDown(self):
        config.provider_order, llm._quota_ok = self._ordre, self._quota
        os.environ.pop("GROQ_API_KEY", None)
        pool_cles.oublier()
        llm._REPOS.clear()

    def test_un_fournisseur_ouvert_repond_maintenant(self):
        self.assertEqual(llm.prochaine_ouverture(), 0.0)

    def test_un_repos_dit_jusqu_a_quand(self):
        llm._REPOS["groq"] = time.time() + 600
        self.assertAlmostEqual(llm.prochaine_ouverture(), 600, delta=5)

    def test_un_quota_du_jour_repart_a_minuit_utc(self):
        llm._quota_ok = lambda p, role="standard", cle_id="": False
        attente = llm.prochaine_ouverture()
        minuit = (int(time.time() // 86400) + 1) * 86400
        self.assertAlmostEqual(attente, minuit - time.time(), delta=5)

    def test_sans_cle_ni_serveur_local_rien_ne_rouvrira(self):
        os.environ.pop("GROQ_API_KEY", None)
        pool_cles.oublier()
        self.assertIsNone(llm.prochaine_ouverture())


if __name__ == "__main__":
    unittest.main()
