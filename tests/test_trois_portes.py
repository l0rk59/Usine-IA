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
    travail = "t-{}".format(len(serveur.TRAVAUX) + 1)
    serveur.TRAVAUX[travail] = {"statut": "en_cours", "journal": [],
                                "type": type_produit, "sujet": ""}
    try:
        serveur._lancer(travail, type_produit, dict(options))
        return dict(serveur.TRAVAUX[travail])
    finally:
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
        carnet.retenir_commande(["usine", "demarrer"])
        llm.definir_simulateur(Espion(coupe_apres=9))
        _par_la_file("la comptabilite des artisans", "ebook", {"chapitres": 6})
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
