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
