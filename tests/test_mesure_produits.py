"""Ce que l'usine sait de ce qu'elle vient de fabriquer.

Mesure du 14/09/2026, en produisant un exemplaire de chaque type : seuls
l'ebook et le roman recevaient une note et un rapport. Les sept autres
sortaient sans rien — pas meme un nombre de mots.

Ce n'est pas une coquetterie de tableau de bord. Trois choses en dependaient :

  * `usine bilan` annoncait « 0 mots produits » apres quatre vraies
    fabrications ;
  * `usine conseils` calculait des conseils « tires de vos donnees » sur ces
    zeros, et concluait « aucun ecart significatif » — ce qui est vrai de
    n'importe quel ensemble vide ;
  * `graine_de_depart()` classe par chiffre d'affaires PUIS par note : sans
    note, ces sept types ne pouvaient jamais servir de point de depart a la
    prospection.

## Pourquoi tous les produits ne sont pas notes

Le controle deterministe mesure de la PROSE. Applique a autre chose, il rend
un chiffre qui n'a pas de sens, et un chiffre sans sens est pire que pas de
chiffre parce qu'on le croit. Deux garde-fous, chacun issu d'une mesure :

**Le type.** Trente-et-un posts sociaux de deux lignes obtenaient 9,98/10 ; un
outil logiciel 9,83, note en fait sur sa notice et non sur son code. Le
catalogue dit desormais quels types sont de la prose.

**La longueur des sections.** Le meme texte, coupe de plus en plus fin :

    mots/section :  60   80  100  120  140  200  300  400
    note         : 10.0 10.0 8.69 8.56 7.56 7.19 6.93  6.5

Sous cent mots, la note vaut 10 quoi que dise le texte : elle mesure le
decoupage, pas l'ecriture.
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
from usine.core import controle, llm, store  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402
from usine.pipelines.base import _decouper  # noqa: E402


def setUpModule():
    atelier.isoler("mesure-produits")


def _fabriquer(commande, extra=None):
    atelier.isoler("mesure-" + commande)
    llm.definir_simulateur(simulateur)
    from usine import cli

    sortie = io.StringIO()
    try:
        with redirect_stdout(sortie), redirect_stderr(sortie):
            cli.principal([commande, "la gestion du temps en {}".format(commande),
                           "--sans-image", "-q", "standard"] + (extra or []))
    finally:
        llm.definir_simulateur(None)
    produits = store.lister_produits(3)
    return (produits[0].get("meta") or {}) if produits else {}


class ChaqueProduitDitCombienIlPese(unittest.TestCase):
    """Le decompte vaut pour tous : c'est un decompte, pas un verdict."""

    TEXTUELS = ["ebook", "formation", "prompts", "outils", "social",
                "modeles", "logiciel", "nouvelle"]

    def test_tous_les_produits_textuels_comptent_leurs_mots(self):
        for commande in self.TEXTUELS:
            with self.subTest(chaine=commande):
                meta = _fabriquer(commande)
                self.assertGreater(
                    int(meta.get("mots") or 0), 0,
                    "« {} » ne sait pas combien de mots il a produit : "
                    "« usine bilan » affichera 0".format(commande))

    def test_un_produit_sans_texte_suivi_compte_zero_sans_mentir(self):
        """Un cahier a remplir ne livre que des PDF. Zero est alors un fait,
        et il ne doit surtout pas s'accompagner d'une note."""
        meta = _fabriquer("impression")
        self.assertEqual(int(meta.get("mots") or 0), 0)
        self.assertIsNone(meta.get("note"))


class UneNoteSansSensEstPireQuePasDeNote(unittest.TestCase):

    def test_la_note_depend_fortement_du_decoupage(self):
        """La mesure qui a fixe le seuil. Sans ce cas, le seuil de cent mots
        serait un chiffre sans source — et ce depot en refuse un dans un
        produit comme dans son propre code.
        """
        base = ("La facturation d'un independant obeit a des regles simples, "
                "mais leur application demande de la constance. Chaque "
                "prestation donne lieu a une facture numerotee, sans rupture "
                "dans la serie. Une mention manquante suffit a rendre la "
                "facture contestable, et le client peut alors en retarder le "
                "reglement sans faute de sa part. ")
        mots = (base * 20).split()

        def note_a(taille):
            sections = [("s{}".format(i + 1),
                         " ".join(mots[i * taille:(i + 1) * taille]))
                        for i in range(len(mots) // taille)][:8]
            return controle.controler_ensemble(sections)["note_moyenne"]

        courtes, longues = note_a(60), note_a(300)
        self.assertGreaterEqual(
            courtes, 9.5,
            "sous cent mots la note ne sature plus : le seuil est a revoir")
        self.assertLess(
            longues, courtes - 1.5,
            "la note ne distingue plus rien entre sections courtes et "
            "longues : le seuil ne protege plus de rien")

    def test_des_sections_trop_courtes_ne_sont_pas_notees(self):
        """Une boite a outils de vingt-cinq mots par fiche obtenait 9,91/10,
        et ce chiffre serait parti se comparer a un ebook note 4,33."""
        meta = _fabriquer("outils")
        if meta.get("note") is not None:
            self.assertGreaterEqual(
                int(meta.get("mots_par_section") or 0), 100,
                "une note rendue sur des sections de moins de cent mots")
        else:
            self.assertTrue(meta.get("note_non_mesuree"),
                            "pas de note et aucune raison dite : une case "
                            "vide se lit comme un oubli")

    def test_un_type_qui_n_est_pas_de_la_prose_n_est_pas_note(self):
        for commande in ("prompts", "social", "logiciel"):
            with self.subTest(chaine=commande):
                meta = _fabriquer(commande)
                self.assertIsNone(
                    meta.get("note"),
                    "« {} » recoit une note de prose".format(commande))
                self.assertIn("prose", meta.get("note_non_mesuree") or "")

    def test_un_type_de_prose_assez_fourni_est_note(self):
        """L'autre sens : un garde-fou qui ne laisse jamais rien passer ne
        protege de rien, il supprime la mesure."""
        meta = _fabriquer("formation")
        self.assertIsNotNone(
            meta.get("note"),
            "plus aucun type ne recoit de note : le seuil a tout emporte")
        self.assertGreaterEqual(int(meta.get("mots_par_section") or 0), 100)

    def test_le_catalogue_dit_lesquels_sont_de_la_prose(self):
        """Lu la ou c'est declare, pas recopie : une liste de plus vieillirait."""
        prose = {t.cle: t.prose for t in catalogue.tous()}
        for cle in ("ebook", "nouvelle", "roman", "formation"):
            with self.subTest(type=cle):
                self.assertTrue(prose[cle])
        for cle in ("prompts", "social", "logiciel", "impression"):
            with self.subTest(type=cle):
                self.assertFalse(prose[cle])


class LeBilanDitSurQuoiIlRepose(unittest.TestCase):
    """Une moyenne affichee sous « 4 production(s) » se lit comme la moyenne
    des quatre. Quand une seule est mesurable, c'est un chiffre juste qui
    raconte quelque chose de faux."""

    def test_le_bilan_compte_les_produits_reellement_notes(self):
        from usine.core import apprentissage

        atelier.isoler("mesure-bilan")
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                for commande in ("formation", "prompts", "social"):
                    cli.principal([commande, "la gestion du temps {}".format(commande),
                                   "--sans-image", "-q", "standard"])
        finally:
            llm.definir_simulateur(None)

        donnees = apprentissage.bilan()
        self.assertEqual(donnees["reussites"], 3)
        self.assertLess(donnees["productions_notees"], donnees["reussites"],
                        "tout est note : le test ne mesure plus rien")
        self.assertGreater(donnees["productions_notees"], 0)

    def test_le_bilan_le_dit_a_l_ecran(self):
        from usine.core import apprentissage

        atelier.isoler("mesure-bilan-ecran")
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                for commande in ("formation", "prompts"):
                    cli.principal([commande, "le devis {}".format(commande),
                                   "--sans-image", "-q", "standard"])
            affiche = io.StringIO()
            with redirect_stdout(affiche), redirect_stderr(affiche):
                cli.principal(["bilan"])
        finally:
            llm.definir_simulateur(None)
        texte = affiche.getvalue()
        self.assertIn("Note moyenne", texte)
        self.assertIn("sur 1 produit(s) sur 2", texte,
                      "la moyenne ne dit pas sur combien elle repose")


class LeDecoupageSuitLaChaine(unittest.TestCase):
    """Couper trop fin ne rend pas une note imprecise : il la rend inventee."""

    def test_les_sous_titres_ne_coupent_pas_une_section(self):
        """Un module de formation porte « ## Objectif » et « ## Notions » a
        l'interieur. Couper la donnait des sections de trente-quatre mots pour
        un module qui en fait cent quarante — donc 10/10 par construction.
        """
        texte = ("# Le manuel\n\n"
                 "## Module 1 — cadrer\n\n"
                 "### Objectif\n\nSavoir cadrer une mission.\n\n"
                 "### Notions\n\nLe perimetre, le livrable, la date.\n\n"
                 "## Module 2 — chiffrer\n\n"
                 "### Objectif\n\nPoser un prix qui tient.\n\n"
                 "### Notions\n\nLe cout de revient, la marge.\n")
        sections = _decouper(texte)
        self.assertEqual([titre for titre, _ in sections],
                         ["Module 1 — cadrer", "Module 2 — chiffrer"])

    def test_un_texte_sans_entete_compte_pour_une_section(self):
        sections = _decouper("Un texte suivi, sans aucun titre.")
        self.assertEqual(len(sections), 1)

    def test_un_texte_vide_ne_donne_aucune_section(self):
        self.assertEqual(_decouper("   \n\n  "), [])


if __name__ == "__main__":
    unittest.main()
