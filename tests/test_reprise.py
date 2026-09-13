"""Reprendre une fabrication interrompue, et effacer un produit.

Le defaut repare ici tenait en une ligne de code : le pipeline n'attrapait que
« BudgetEpuise ». « PlusDeFournisseur » — quota atteint partout, reseau coupe,
cles refusees — remontait jusqu'a la CLI et emportait la fabrication entiere.
Mesure du 13/09/2026 : reseau coupe au sixieme appel d'un ebook de huit
chapitres, il restait sur le disque UN fichier, « plan.json ». Le plan,
l'avant-propos et le premier chapitre — relu, controle, corrige — avaient ete
produits, payes, puis perdus.

Le cache des reponses n'y suffisait pas : une section passe par plusieurs
appels enchaines, et chaque passe forge une invite qui depend de la
precedente. Ce qu'il faut garder n'est donc pas l'appel, c'est la section
finie. D'ou le carnet.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine import cli  # noqa: E402
from usine.core import config, llm, store  # noqa: E402
from usine.pipelines import carnet  # noqa: E402


def setUpModule():
    atelier.isoler("reprise")


def _muet(argv):
    """Lance la CLI sans rien ecrire a l'ecran, et rend (code, texte)."""
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


def _coupe_apres(combien):
    """Simulateur qui cesse de repondre apres « combien » appels."""
    compteur = {"n": 0}

    def simuler(invite, role="standard", **kw):
        compteur["n"] += 1
        if compteur["n"] > combien:
            raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
        return simulateur(invite, role=role, **kw)

    return simuler, compteur


class CoupureEtReprise(unittest.TestCase):

    def setUp(self):
        atelier.isoler("reprise-{}".format(self.id().rsplit(".", 1)[-1]))

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_une_coupure_ne_perd_plus_le_travail_paye(self):
        llm.definir_simulateur(_coupe_apres(8)[0])
        code, _ = _muet(["ebook", "la facturation", "--chapitres", "6"])
        self.assertEqual(code, 0, "la fabrication doit aller au bout")
        produit = store.lister_produits()[0]
        dossier = Path(produit["dossier"])
        # Le carnet porte ce qui a ete ecrit avant la coupure. Sans lui, il ne
        # restait que « plan.json ».
        self.assertGreaterEqual(carnet.compte(dossier), 2)
        self.assertTrue(carnet.plan(dossier))
        self.assertTrue(carnet.commande(dossier))

    def test_le_produit_coupe_se_declare_inacheve(self):
        """« pret » veut dire vendable, et celui-la ne l'est pas.

        Il etait pourtant marque pret comme les autres, et se presentait au
        catalogue et a « usine livrer » sans rien signaler.
        """
        llm.definir_simulateur(_coupe_apres(8)[0])
        _muet(["ebook", "la facturation", "--chapitres", "6"])
        produit = store.lister_produits()[0]
        self.assertEqual(produit["statut"], "en_cours")
        manquants = (produit.get("meta") or {}).get("manquants") or []
        self.assertTrue(manquants)
        self.assertIn("conclusion", manquants)

    def test_la_reprise_ne_refait_que_ce_qui_manque(self):
        """La mesure qui justifie la commande.

        Une relance ordinaire repayerait les sections deja ecrites : leurs
        invites de relecture dependent du texte precedent et ratent le cache.
        """
        llm.definir_simulateur(_coupe_apres(8)[0])
        _muet(["ebook", "la facturation", "--chapitres", "6"])
        avant = store.lister_produits()[0]
        deja = carnet.compte(Path(avant["dossier"]))

        payes = {"n": 0}

        def compter(invite, role="standard", **kw):
            payes["n"] += 1
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(compter)
        code, journal = _muet(["reprendre"])
        self.assertEqual(code, 0)
        # Ce que dit le journal est la seule preuve que les sections deja
        # ecrites ont ete RELUES et non refaites. Compter les appels ne suffit
        # pas : le simulateur est deterministe, donc une section refaite
        # retombe sur le cache et ne se voit pas au compteur. Ce ne sera pas
        # le cas d'un vrai modele — d'ou la mesure sur le journal.
        self.assertGreaterEqual(journal.count("repris du carnet"), deja)

        apres = store.lister_produits()
        self.assertEqual(len(apres), 1, "la reprise ne doit pas creer un second produit")
        self.assertEqual(apres[0]["id"], avant["id"], "meme dossier, meme produit")
        self.assertEqual(apres[0]["statut"], "pret")
        self.assertFalse((apres[0].get("meta") or {}).get("manquants"))
        self.assertGreater(carnet.compte(Path(apres[0]["dossier"])), deja)
        self.assertGreater(payes["n"], 0,
                           "sans quoi le test ne distinguerait pas reprise et cache")

        # Combien couterait la MEME fabrication d'un seul trait, cache vide ?
        # Sans cette comparaison, une reprise qui refait tout passerait le
        # test : elle finit le produit, elle aussi.
        atelier.isoler("reprise-temoin")
        try:
            dun_trait = {"n": 0}

            def temoin(invite, role="standard", **kw):
                dun_trait["n"] += 1
                return simulateur(invite, role=role, **kw)

            llm.definir_simulateur(temoin)
            _muet(["ebook", "la facturation", "--chapitres", "6"])
        finally:
            atelier.isoler("reprise-test_la_reprise_ne_refait_que_ce_qui_manque")
        self.assertLess(payes["n"], dun_trait["n"],
                        "la reprise doit couter moins qu'une fabrication entiere")

    def test_la_reprise_garde_le_plan_d_origine(self):
        """Un plan reconstruit differe, et les chapitres deja ecrits se
        retrouveraient ranges sous des titres qui ne sont plus les leurs.

        Le modele n'est pas deterministe ; le simulateur l'est. On verifie
        donc que le plan est RELU du carnet, pas qu'il se trouve identique.
        """
        llm.definir_simulateur(_coupe_apres(8)[0])
        _muet(["ebook", "la facturation", "--chapitres", "6"])
        produit = store.lister_produits()[0]
        dossier = Path(produit["dossier"])
        plan = carnet.plan(dossier)
        plan["titre"] = "Titre marque pour la reprise"
        carnet.noter_plan(dossier, plan)

        llm.definir_simulateur(simulateur)
        _, texte = _muet(["reprendre"])
        self.assertIn("Titre marque pour la reprise", texte)

    def test_reprendre_sans_produit_inacheve_le_dit(self):
        code, texte = _muet(["reprendre"])
        self.assertEqual(code, 1)
        self.assertIn("Aucun produit inacheve", texte)


class Carnet(unittest.TestCase):

    def setUp(self):
        self.dossier = config.PRODUITS_DIR / "carnet-essai"
        self.dossier.mkdir(parents=True, exist_ok=True)

    def test_une_section_notee_se_relit(self):
        carnet.noter_section(self.dossier, "chapitre-1", "Un titre", "Un corps.")
        self.assertEqual(carnet.section(self.dossier, "chapitre-1"),
                         ("Un titre", "Un corps."))

    def test_un_carnet_illisible_est_traite_comme_absent(self):
        """Refaire le travail coute cher ; assembler un produit a partir de
        morceaux qu'on n'a pas su relire coute bien plus."""
        carnet.chemin(self.dossier).write_text("{ceci n'est pas du json",
                                               encoding="utf-8")
        self.assertEqual(carnet.compte(self.dossier), 0)
        self.assertIsNone(carnet.section(self.dossier, "chapitre-1"))

    def test_une_section_vide_ne_compte_pas_comme_ecrite(self):
        """Sinon la reprise la saute et le produit garde un trou."""
        carnet.noter_section(self.dossier, "chapitre-2", "Titre", "   ")
        self.assertIsNone(carnet.section(self.dossier, "chapitre-2"))

    def test_l_ecriture_passe_par_un_fichier_temporaire(self):
        """Le processus meurt sans preavis sur un telephone.

        Ecrire par-dessus le carnet expose a mourir au milieu : le carnet
        devient illisible et la reprise repart de zero — exactement ce qu'il
        devait empecher. On verifie qu'aucun fichier temporaire ne survit,
        donc que le remplacement a bien eu lieu d'un bloc.
        """
        carnet.noter_section(self.dossier, "chapitre-3", "T", "C")
        restes = list(self.dossier.glob("*.tmp"))
        self.assertEqual(restes, [])


class Suppression(unittest.TestCase):

    def setUp(self):
        atelier.isoler("reprise-suppression")
        llm.definir_simulateur(simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _un_produit(self):
        _muet(["ebook", "un sujet a effacer", "--chapitres", "3"])
        return store.lister_produits()[0]

    def test_effacer_retire_la_fiche_et_le_dossier(self):
        produit = self._un_produit()
        dossier = Path(produit["dossier"])
        self.assertTrue(dossier.exists())
        code, _ = _muet(["supprimer", produit["id"], "--oui"])
        self.assertEqual(code, 0)
        self.assertFalse(dossier.exists())
        self.assertIsNone(store.lire_produit(produit["id"]))

    def test_l_empreinte_part_avec_le_produit(self):
        """Sinon un nouveau produit sur le meme sujet est refuse comme le
        doublon de quelque chose qui n'existe plus."""
        produit = self._un_produit()
        store.enregistrer_empreinte(produit["id"], "ebook", produit["titre"],
                                    produit["sujet"], "signature", "plan", 100)
        _muet(["supprimer", produit["id"], "--oui"])
        restantes = [e for e in store.lister_empreintes()
                     if e["produit_id"] == produit["id"]]
        self.assertEqual(restantes, [])

    def test_une_fiche_qui_pointe_hors_de_l_atelier_n_efface_rien(self):
        """Garde-fou : le chemin vient de la base, et la base se modifie.

        Sans lui, une fiche dont le dossier a ete change a la main ferait
        effacer n'importe quel dossier de l'appareil.
        """
        produit = self._un_produit()
        dehors = Path(config.WORKDIR) / "hors-atelier"
        dehors.mkdir(parents=True, exist_ok=True)
        (dehors / "temoin.txt").write_text("a garder", encoding="utf-8")
        store.maj_produit(produit["id"], dossier=str(dehors))
        code, texte = _muet(["supprimer", produit["id"], "--oui"])
        self.assertEqual(code, 1)
        self.assertIn("hors de l'atelier", texte)
        self.assertTrue((dehors / "temoin.txt").exists())
        self.assertIsNotNone(store.lire_produit(produit["id"]),
                             "rien efface, donc la fiche reste")

    def test_une_fin_d_identifiant_suffit_a_designer_un_produit(self):
        """Taper quarante caracteres sur un clavier de telephone est le genre
        de detail qui fait abandonner une fonction."""
        produit = self._un_produit()
        code, _ = _muet(["supprimer", produit["id"][-8:], "--oui"])
        self.assertEqual(code, 0)
        self.assertIsNone(store.lire_produit(produit["id"]))


if __name__ == "__main__":
    unittest.main()
