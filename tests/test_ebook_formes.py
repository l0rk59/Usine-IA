"""Un guide a une forme, et elle se choisit.

Mesure du 26/09/2026 : l'ebook, type phare de l'usine, n'avait aucun reglage
propre — contre neuf pour un roman. Sa charpente etait ecrite en dur dans
l'invite de chaque chapitre : « au moins une liste numerotee d'etapes
applicables aujourd'hui », un exemple chiffre, et une conclusion intitulee
« votre plan des 30 prochains jours ». Un manuel de reference, un recueil de
cas et un programme sur quatre semaines sortaient avec la meme charpente et
la meme derniere page.

Ces tests suivent chaque reglage jusqu'a l'invite qui part au modele : un
reglage qui s'affiche et n'y arrive pas est un mensonge fait a
l'utilisateur.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests import simulateur as sim  # noqa: E402
from usine.core import llm  # noqa: E402
from usine.pipelines import catalogue, ebook  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402
from usine.render import document as D  # noqa: E402
from usine.render import libelles  # noqa: E402

INVITES: List[str] = []


def _espion(messages, role):
    INVITES.append(messages[-1]["content"])
    return sim.simulateur(messages, role)


def setUpModule():
    atelier.isoler("ebook-formes")
    llm.definir_simulateur(_espion)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet: str, journal=None) -> Contexte:
    # Un sujet ET une audience par cas. Le simulateur rend le meme titre a
    # tous les plans, donc l'avant-propos de deux livres differents part
    # avec la meme invite : seule l'audience, portee par la consigne systeme,
    # les distingue. Sans elle, le second livre lisait le cache du premier
    # et l'espion ne voyait rien passer.
    return Contexte(sujet=sujet, audience="des lecteurs de " + sujet,
                    chapitres=2, mots_section=300,
                    qualite="rapide", sans_image=True,
                    journal=journal or (lambda _m: None))


def _fabriquer(sujet: str, options, journal=None):
    INVITES.clear()
    ctx = _contexte(sujet, journal)
    resume = catalogue.executer("ebook", ctx, dict(options))
    return ctx, resume


def _invite(debut: str) -> str:
    trouvees = [i for i in INVITES if i.startswith(debut)]
    if not trouvees:
        raise AssertionError("aucune invite ne commence par « {} »".format(debut))
    return trouvees[0]


class ChaqueFormeChangeLaCharpente(unittest.TestCase):

    def test_la_forme_arrive_au_plan_aux_chapitres_et_a_la_fin(self):
        for cle, fiche in ebook.FORMES.items():
            with self.subTest(forme=cle):
                ctx, resume = _fabriquer(
                    "la gestion des stocks d'un atelier ({})".format(cle),
                    {"forme": cle, "niveau": "avance", "exercices": "sans"})
                self.assertIn(fiche["plan"], _invite("Concois le plan"))
                chapitre = _invite("Redige le chapitre 1")
                self.assertIn(fiche["chapitre"], chapitre)
                self.assertIn(ebook.NIVEAUX["avance"], chapitre)
                self.assertNotIn("**Exercice :**", chapitre)
                self.assertIn(fiche["lecture"], "\n".join(INVITES))
                self.assertIn(fiche["conclusion"], "\n".join(INVITES))

    def test_la_derniere_page_porte_le_titre_de_sa_forme(self):
        """« Votre plan des 30 prochains jours » en tete d'un aide-memoire
        annoncait une page qui n'existe pas."""
        titres = set()
        for cle in ebook.FORMES:
            with self.subTest(forme=cle):
                ctx, resume = _fabriquer(
                    "l'entretien d'un velo de ville ({})".format(cle),
                    {"forme": cle})
                texte = (Path(resume["dossier"]) / "livre.md").read_text(
                    encoding="utf-8")
                entetes = [l for l in texte.splitlines() if l.startswith("# ")]
                titres.add(entetes[-1])
        self.assertEqual(len(titres), len(ebook.FORMES),
                         "deux formes finissent sur le meme titre")
        self.assertIn("# " + libelles.FR["ebook_conclusion_reference"], titres)

    def test_les_exercices_arrivent_dans_chaque_chapitre(self):
        _fabriquer("la taille des arbres fruitiers", {"forme": "methode",
                                                      "exercices": "avec"})
        chapitres = [i for i in INVITES if i.startswith("Redige le chapitre")]
        self.assertEqual(len(chapitres), 2)
        for invite in chapitres:
            self.assertIn("**Exercice :**", invite)

    def test_l_exercice_ressort_en_encadre(self):
        """La promesse faite dans l'aide du champ : mis en valeur dans le PDF
        et l'EPUB. Elle tient parce que le rendu reconnait la ligne."""
        blocs = D.analyser("Un paragraphe.\n\n**Exercice :** notez vos trois "
                           "derniers devis et leur delai de paiement.")
        encadres = [b for b in blocs if getattr(b, "titre", "") == "Exercice"]
        self.assertEqual(len(encadres), 1)


class QuandPersonneNeChoisit(unittest.TestCase):

    def test_l_usine_decide_la_forme_d_apres_le_sujet(self):
        ctx, resume = _fabriquer("la negociation d'un premier salaire", {})
        decides = ctx.meta.get("reglages_decides", {})
        for nom in ("forme", "niveau", "exercices"):
            self.assertIn(nom, decides)
        self.assertIn(ebook.FORMES[decides["forme"]]["plan"],
                      _invite("Concois le plan"))

    def test_le_modele_sait_ce_que_chaque_forme_fabrique(self):
        """« cas » ou « reference » ne se choisissent pas sans savoir ce
        qu'ils fabriquent : l'invite montre l'etiquette a cote de la cle."""
        _fabriquer("la location d'un premier appartement", {})
        decision = _invite("Tu prepares la fabrication")
        self.assertIn("cas (Études de cas)", decision)
        self.assertIn("reference (Manuel de référence)", decision)

    def test_une_etiquette_rendue_par_le_modele_est_lue(self):
        """L'invite montrant les deux, le modele rend parfois l'etiquette.
        L'ecarter perdrait une decision juste ; la lire ne devine rien."""
        from usine.pipelines import brief

        fiche = catalogue.obtenir("ebook")
        for reponse, attendu in (('{"forme": "Études de cas"}', "cas"),
                                 ('{"forme": "cas (Études de cas)"}', "cas"),
                                 ('{"forme": "roman noir"}', None)):
            with self.subTest(reponse=reponse):
                with mock.patch.object(brief.llm, "generer_json",
                                       lambda *a, _r=reponse, **k:
                                       __import__("json").loads(_r)):
                    decides = brief.decider_les_reglages(
                        _contexte("un sujet"), fiche,
                        {"niveau": "avance", "exercices": "sans"})
                self.assertEqual(decides.get("forme"), attendu)

    def test_la_forme_par_defaut_se_dit(self):
        """Si le modele n'a pas pu decider, l'ebook retombe sur la methode pas
        a pas — et le journal le dit, au lieu d'une forme que personne n'a
        choisie et que rien ne signale."""
        lignes: List[str] = []
        INVITES.clear()
        ebook.produire(_contexte("le compostage en appartement",
                                 journal=lignes.append))
        self.assertTrue(any("personne ne l'a choisie" in l for l in lignes),
                        lignes[:5])
        self.assertIn(ebook.FORMES["methode"]["plan"], _invite("Concois le plan"))


class LesTroisPortesLesProposent(unittest.TestCase):

    def test_la_ligne_de_commande(self):
        from usine import cli

        args = cli.construire_parseur().parse_args(
            ["ebook", "un sujet", "--forme", "cas", "--niveau", "debutant",
             "--exercices", "avec"])
        self.assertEqual((args.forme, args.niveau, args.exercices),
                         ("cas", "debutant", "avec"))

    def test_le_menu_montre_les_etiquettes_et_rend_les_cles(self):
        from usine import menu

        sortie = io.StringIO()
        reponses = iter(["3", "2", "2", "n"])
        with redirect_stdout(sortie), mock.patch(
                "builtins.input", lambda invite="": next(reponses, "")):
            options = menu._options_du_type("ebook")
        self.assertEqual(options, {"forme": "reference", "niveau": "debutant",
                                   "exercices": "avec"})
        self.assertIn("Manuel de référence", sortie.getvalue())
        from usine import cli

        with redirect_stderr(io.StringIO()):
            cli.construire_parseur().parse_args(
                ["ebook"] + menu._ARGUMENTS["forme"]("reference")
                + menu._ARGUMENTS["exercices"]("avec"))

    def test_la_liste_deroulante_affiche_l_etiquette(self):
        """Le serveur envoie l'etiquette ; si la page affiche encore la cle,
        on lit « reference » et une ligne vide la ou l'usine decide."""
        source = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        debut = source.index("function champDuType(")
        corps = source[debut:source.index("\n}\n", debut)]
        self.assertIn("champ.etiquettes", corps)
        self.assertIn("${echapper(lisible(valeur))}</option>", corps)
        self.assertIn("champ.decide_par_l_usine", corps)

    def test_le_tableau_de_bord_recoit_les_etiquettes(self):
        from usine.web import serveur

        fiche = next(t for t in serveur._etat()["types"] if t["cle"] == "ebook")
        champs = {c["nom"]: c for c in fiche["champs"]}
        self.assertEqual(set(champs), {"forme", "niveau", "exercices"})
        self.assertEqual(champs["forme"]["etiquettes"]["cas"], "Études de cas")
        self.assertTrue(champs["forme"]["decide_par_l_usine"])


if __name__ == "__main__":
    unittest.main()
