"""Trois portes fabriquent : la ligne de commande, le tableau de bord, l'usine continue.

Mesure du 23/09/2026. Seule la premiere preparait le contexte. Depuis les deux
autres — le bouton « Generer » et la boucle, c'est-a-dire l'usage reel sur un
telephone — quinze invites sur quinze portaient « TON : auto » et
« PUBLIC : auto », et un reglage de fiction choisi dans le formulaire
n'atteignait qu'une invite sur vingt-huit, jamais celles qui ecrivent.

Et la reprise ne savait rejouer que la ligne de commande. Un produit de
l'usine continue gardait « usine demarrer » dans son carnet ; « usine
reprendre » mourait sur « unrecognized arguments ».

AUCUN test de ce module ne sort sur le reseau.
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


def setUpModule():
    atelier.isoler("trois-portes")


from usine import cli, production  # noqa: E402
from usine.core import file, llm, reglages, store  # noqa: E402
from usine.pipelines import carnet  # noqa: E402
from usine.web import serveur  # noqa: E402

BASE = dict(images=False, qualite="rapide", pause_entre_produits=0,
            notifications=False, verrou_veille=False, batterie_minimum=0)
# Ce que le simulateur decide au brief. Le retrouver dans une invite prouve
# que la decision a voyage ; ne jamais y trouver « auto » prouve qu'aucune
# case n'est partie vide.
PUBLIC_DU_BRIEF = "Freelance en portage qui facture moins de 40 k par an"


class Espion:
    """Le simulateur, qui garde chaque invite et peut se taire apres N appels."""

    def __init__(self, coupe_apres=None):
        self.invites = []
        self.coupe_apres = coupe_apres

    def __call__(self, messages, role):
        self.invites.append("\n".join(m["content"] for m in messages))
        if self.coupe_apres is not None and len(self.invites) > self.coupe_apres:
            raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
        return simulateur(messages, role)

    def avec(self, texte):
        return sum(texte in invite for invite in self.invites)

    def auto(self):
        """Invites ou « auto » est donne comme valeur d'un reglage."""
        import re

        motif = re.compile(r"(?im)^[^\n]*:\s*auto\s*$")
        return sum(bool(motif.search(invite)) for invite in self.invites)


def _atelier_du_cas(cas):
    atelier.isoler("trois-portes-{}".format(cas.id().rsplit(".", 1)[-1]))
    reglages.ecrire(dict(BASE))


def _par_le_tableau(type_produit, options):
    """Le bouton « Generer ». La boucle a qui il confie un produit coupe
    n'est PAS lancee ici : ces tests reprennent a la main, et une boucle
    reelle dans un fil reprendrait le meme produit en meme temps (voir
    « test_reprise_auto » pour ce relais)."""
    travail = "t-{}".format(len(serveur.TRAVAUX) + 1)
    serveur.TRAVAUX[travail] = {"statut": "en_cours", "journal": [],
                                "type": type_produit, "sujet": ""}
    vraie_boucle = serveur._lancer_la_boucle
    serveur._lancer_la_boucle = lambda **_kw: None
    try:
        serveur._lancer(travail, type_produit, dict(options))
        return dict(serveur.TRAVAUX[travail])
    finally:
        serveur._lancer_la_boucle = vraie_boucle
        serveur.TRAVAUX.pop(travail, None)


def _par_la_file(sujet, type_produit, options=None):
    file.ajouter(sujet, type_produit, options=options or {})
    production.UsineContinue(journal=lambda _m: None, pause=0).tourner()


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class AucunePorteNEnvoieAuto(unittest.TestCase):

    def setUp(self):
        _atelier_du_cas(self)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_le_tableau_de_bord_passe_par_le_brief(self):
        espion = Espion()
        llm.definir_simulateur(espion)
        _par_le_tableau("ebook", {"sujet": "la facturation des independants"})
        self.assertEqual(espion.auto(), 0)
        self.assertGreater(espion.avec(PUBLIC_DU_BRIEF), 3)

    def test_l_usine_continue_passe_par_le_brief(self):
        espion = Espion()
        llm.definir_simulateur(espion)
        _par_la_file("la comptabilite des artisans", "ebook")
        self.assertEqual(espion.auto(), 0)
        self.assertGreater(espion.avec(PUBLIC_DU_BRIEF), 3)

    def test_la_ligne_de_commande_aussi(self):
        """Le temoin : la porte qui marchait doit continuer de marcher."""
        espion = Espion()
        llm.definir_simulateur(espion)
        _muet(["ebook", "la paie des associations"])
        self.assertEqual(espion.auto(), 0)
        self.assertGreater(espion.avec(PUBLIC_DU_BRIEF), 3)

    def test_un_reglage_de_fiction_du_formulaire_atteint_l_ecriture(self):
        espion = Espion()
        llm.definir_simulateur(espion)
        _par_le_tableau("nouvelle", {"sujet": "un phare en Bretagne",
                                     "ambiance": "brume et sel"})
        # Avant : une seule invite, celle qui decide des AUTRES reglages.
        self.assertGreater(espion.avec("brume et sel"), 3)


class LesActionsSurUnProduitGardentSaVoix(unittest.TestCase):
    """Kit de vente et test A/B reconstruisaient un contexte depuis les
    reglages, qui valent « auto » : chacune de leurs invites portait
    « TON : auto ». Le produit avait pourtant une voix, gardee au carnet."""

    def setUp(self):
        _atelier_du_cas(self)
        llm.definir_simulateur(Espion())
        _par_le_tableau("ebook", {"sujet": "la facturation des independants",
                                  "chapitres": 3})
        self.produit = store.lister_produits()[0]
        self.espion = Espion()
        llm.definir_simulateur(self.espion)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _verifier(self):
        self.assertGreater(len(self.espion.invites), 0)
        self.assertEqual(self.espion.auto(), 0)
        self.assertGreater(self.espion.avec(PUBLIC_DU_BRIEF), 0)
        # Rien n'est redemande : le carnet a deja repondu.
        self.assertEqual(self.espion.avec('"mots_par_section"'), 0)

    def test_le_kit_de_vente_du_tableau_de_bord(self):
        serveur.TRAVAUX["k"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer_marketing("k", self.produit["id"], "9")
        finally:
            serveur.TRAVAUX.pop("k", None)
        self._verifier()

    def test_le_kit_de_vente_de_la_ligne_de_commande(self):
        code, texte = _muet(["marketing", self.produit["id"]])
        self.assertEqual(code, 0, texte[-300:])
        self._verifier()

    def test_le_test_a_b_d_un_produit(self):
        serveur.TRAVAUX["ab"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer_ab("ab", {"produit": self.produit["id"],
                                      "sur": "titre", "nombre": 3})
        finally:
            serveur.TRAVAUX.pop("ab", None)
        self._verifier()

    def test_un_test_a_b_sur_titre_libre_passe_par_le_brief(self):
        serveur.TRAVAUX["ab2"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer_ab("ab2", {"titre": "Le guide du freelance serein",
                                       "sur": "titre", "nombre": 3})
        finally:
            serveur.TRAVAUX.pop("ab2", None)
        self.assertEqual(self.espion.auto(), 0)


class LaLigneDeCommandeLaisseDeciderLUsine(unittest.TestCase):
    """Mesure du 24/09/2026 : dix-sept types sur dix-sept, zero reglage de
    type decide en ligne de commande — et donc depuis le menu Termux, qui
    passe par elle. Chaque commande appelait sa chaine directement, avec
    « linkedin », « bienvenue », « intermediaire » en dur."""

    DECISION = "n'ont pas ete choisis"

    def setUp(self):
        _atelier_du_cas(self)
        self.espion = Espion()
        llm.definir_simulateur(self.espion)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_chaque_type_fait_decider_ses_reglages(self):
        # Un echantillon qui couvre les formes differentes : fiction longue,
        # album, liste, sequence, questionnaire, et le type dont l'analyseur
        # etait ecrit a la main.
        for i, cle in enumerate(("roman", "conte", "social", "emails", "quiz",
                                 "idees")):
            with self.subTest(type=cle):
                self.espion.invites.clear()
                code, texte = _muet([cle, "la trésorerie des artisans {}".format(i)])
                self.assertEqual(code, 0, texte[-300:])
                self.assertEqual(self.espion.avec(self.DECISION), 1)

    def test_ce_qui_est_tape_n_est_pas_redecide(self):
        _muet(["social", "le compost en appartement", "-n", "5",
               "--reseau", "instagram"])
        self.assertEqual(self.espion.avec(self.DECISION), 0)

    def test_aucun_reglage_decide_n_a_de_valeur_par_defaut(self):
        """La structure : un « 50 » par defaut ne se distingue pas d'un
        « -n 50 » tape. Tout champ que l'usine decide doit valoir None tant
        qu'on ne l'a pas donne, pour chaque type, y compris ceux dont
        l'analyseur serait un jour reecrit a la main."""
        import argparse

        from usine.pipelines import catalogue

        for fiche in catalogue.tous(fabricables=True):
            decides = [c for c in fiche.champs
                       if c.decide_par_l_usine and c.genre != "booleen"]
            if not decides:
                continue
            with self.subTest(type=fiche.cle):
                args = cli.construire_parseur().parse_args([fiche.cle])
                self.assertIsInstance(args, argparse.Namespace)
                for champ in decides:
                    self.assertIsNone(getattr(args, champ.nom, None), champ.nom)

    def test_le_menu_laisse_decider_quand_on_appuie_sur_entree(self):
        """Entree choisissait « linkedin », « bienvenue », « intermediaire »,
        la tranche d'age par defaut et la premiere forme d'outil."""
        from unittest import mock

        from usine import menu

        for cle in ("social", "logiciel", "emails", "quiz", "conte"):
            with self.subTest(type=cle):
                with redirect_stdout(io.StringIO()), \
                        mock.patch("builtins.input", lambda invite="": ""):
                    self.assertEqual(menu._options_du_type(cle), {})


class LaBoucleLitLesMemesOptionsQueLeBouton(unittest.TestCase):
    """La boucle construisait son contexte a part, et ignorait les chapitres,
    les mots et l'auteur passes en options."""

    def setUp(self):
        _atelier_du_cas(self)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_les_chapitres_et_l_auteur_de_la_file_sont_tenus(self):
        llm.definir_simulateur(Espion())
        _par_la_file("le budget des familles", "ebook",
                     {"chapitres": 4, "auteur": "Camille Delmas"})
        produit = store.lister_produits()[0]
        plan = carnet.plan(Path(produit["dossier"]))
        self.assertEqual(len(plan["chapitres"]), 4)
        self.assertEqual(carnet.contexte_garde(Path(produit["dossier"]))["auteur"],
                         "Camille Delmas")


class LaRepriseMarcheQuelleQueSoitLaPorte(unittest.TestCase):

    def setUp(self):
        _atelier_du_cas(self)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _coupe(self):
        produit = store.lister_produits()[0]
        self.assertEqual(produit["statut"], "en_cours",
                         "la coupure doit laisser un produit inacheve")
        return produit

    def _reprendre_et_verifier(self, produit):
        espion = Espion()
        llm.definir_simulateur(espion)
        code, texte = _muet(["reprendre", produit["id"]])
        self.assertEqual(code, 0, texte[-400:])
        apres = store.lister_produits()
        self.assertEqual(len(apres), 1, "la reprise ne doit pas creer un second produit")
        self.assertEqual(apres[0]["id"], produit["id"])
        self.assertEqual(apres[0]["statut"], "pret")
        return espion

    def test_un_produit_du_tableau_de_bord_se_reprend(self):
        # Ce que le processus du tableau de bord a vu en demarrant : « web ».
        carnet.retenir_commande(["web"])
        llm.definir_simulateur(Espion(coupe_apres=9))
        _par_le_tableau("ebook", {"sujet": "la facturation des independants",
                                  "chapitres": 6})
        produit = self._coupe()
        self.assertEqual(carnet.commande(Path(produit["dossier"])), [],
                         "la commande du serveur n'est pas celle du produit")
        self._reprendre_et_verifier(produit)

    def test_un_produit_de_l_usine_continue_se_reprend(self):
        """A la main, cette fois. L'usine continue attendrait que les
        fournisseurs reviennent et finirait seule (« test_reprise_auto ») ;
        on lui fait dire qu'aucun ne reviendra, pour qu'elle s'arrete et
        laisse le produit a « usine reprendre »."""
        carnet.retenir_commande(["usine", "demarrer"])
        llm.definir_simulateur(Espion(coupe_apres=9))
        vraie = llm.prochaine_ouverture
        llm.prochaine_ouverture = lambda role="standard": None
        try:
            _par_la_file("la comptabilite des artisans", "ebook", {"chapitres": 6})
        finally:
            llm.prochaine_ouverture = vraie
        self._reprendre_et_verifier(self._coupe())

    def test_la_reprise_garde_la_voix_decidee_au_brief(self):
        """Les chapitres repris partaient « auto » : la reprise reconstruisait
        le contexte depuis les arguments, et le brief n'y figurait pas."""
        llm.definir_simulateur(Espion(coupe_apres=9))
        _muet(["ebook", "la paie des associations", "--chapitres", "6"])
        espion = self._reprendre_et_verifier(self._coupe())
        self.assertEqual(espion.auto(), 0)
        self.assertGreater(espion.avec(PUBLIC_DU_BRIEF), 0)
        # Rien n'est redemande : une decision prise une fois fait foi.
        self.assertEqual(espion.avec('"mots_par_section"'), 0)

    def test_la_promesse_de_lecture_survit_a_la_reprise(self):
        """Une nouvelle coupee a mi-chemin : les scenes reprises doivent
        porter l'ambiance choisie, pas en inventer une autre."""
        llm.definir_simulateur(Espion(coupe_apres=12))
        _par_le_tableau("nouvelle", {"sujet": "un phare en Bretagne",
                                     "ambiance": "brume et sel"})
        espion = self._reprendre_et_verifier(self._coupe())
        self.assertGreater(espion.avec("brume et sel"), 0)

    def test_le_tableau_de_bord_reprend_sans_ligne_de_commande(self):
        carnet.retenir_commande(["web"])
        llm.definir_simulateur(Espion(coupe_apres=9))
        _par_le_tableau("ebook", {"sujet": "le devis des artisans",
                                  "chapitres": 6})
        produit = self._coupe()
        llm.definir_simulateur(Espion())
        serveur.TRAVAUX["r1"] = {"statut": "en_cours", "journal": []}
        try:
            serveur._lancer_reprise("r1", produit["id"])
            travail = dict(serveur.TRAVAUX["r1"])
        finally:
            serveur.TRAVAUX.pop("r1", None)
        self.assertEqual(travail["statut"], "termine")
        self.assertEqual(store.lire_produit(produit["id"])["statut"], "pret")

    def test_une_commande_perimee_ne_fige_pas_le_tableau_de_bord(self):
        """Un produit d'avant cette version garde « web » pour commande.
        argparse sort par « SystemExit », qu'un « except Exception » laisse
        passer : le travail restait « en cours » pour toujours."""
        llm.definir_simulateur(Espion(coupe_apres=9))
        _muet(["ebook", "la note de frais", "--chapitres", "6"])
        produit = self._coupe()
        dossier = Path(produit["dossier"])
        ancien = carnet.lire(dossier)
        ancien.pop("contexte", None)
        ancien.pop("relance", None)
        ancien["commande"] = ["web"]
        carnet._ecrire(dossier, ancien)
        serveur.TRAVAUX["r2"] = {"statut": "en_cours", "journal": []}
        try:
            with redirect_stderr(io.StringIO()):
                serveur._lancer_reprise("r2", produit["id"])
            travail = dict(serveur.TRAVAUX["r2"])
        finally:
            serveur.TRAVAUX.pop("r2", None)
        self.assertEqual(travail["statut"], "echec")


if __name__ == "__main__":
    unittest.main()
