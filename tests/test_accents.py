"""Ce que l'acheteur et l'utilisateur lisent est ecrit en francais accentue.

Mesure du 26/09/2026. Le mobilier francais des produits — licence, page de
copyright, LISEZ-MOI, mode d'emploi du quiz, « Precedemment » du feuilleton,
noms des mois — sortait sans un accent : « Tous droits reserves », « Premiere
edition : septembre 2026 », « Ce produit a ete elabore ». C'est la premiere
page qu'ouvre l'acheteur, et elle se lisait comme une saisie au clavier
anglais. Rien ne le signalait : les tests cherchaient justement ces chaines
sans accent, donc confirmaient le defaut.

Meme constat sur ce que lit le VENDEUR : les reglages affichaient leur
identifiant de code (« signature_ia », « budget_appels_jour »), les agents
aussi (« lecteur_de_fiction au travail »), et les noms des types de produits
se lisaient « Etude de niche », « Memo / antiseche ».

Le detecteur ne cherche PAS « un mot qui devrait porter un accent » : il
n'a pas de dictionnaire, et « marche », « a », « ou », « illustre » existent
avec et sans. Il cherche une liste FERMEE de mots qui n'existent pas en
francais sans leur accent. Il rate donc beaucoup de defauts, et n'en invente
aucun — un garde-fou qui crie a tort finit ignore.
"""

from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Iterator, List, Tuple
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import cli, menu  # noqa: E402
from usine.agents import equipe  # noqa: E402
from usine.core import reglages  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402
from usine.render import libelles  # noqa: E402


def setUpModule():
    atelier.isoler("accents")


# Des mots qui n'existent pas sans leur accent. Pas « marche » (le verbe),
# pas « illustre » (l'adjectif), pas « a » : ceux-la sont justes aussi sans.
IMPOSSIBLES = frozenset("""
    deja tres apres etre ete donnees systeme probleme problemes methode
    methodes etape etapes francais reponse reponses reglage reglages etude
    idee idees resultat resultats qualite activite verifie verifiee verifier
    verification controle numero generer genere elabore precedemment bareme
    prerequis priorites categorie apercu decembre fevrier acces immediat
    telechargement debut recit recits scenes reseau reseaux sequence
    antiseche bibliotheque equipe premiere reserve reserves heros
    melancolique epique drole inquietante amere enquete episodique
    litterature troisieme limitee alternes fermee reconfortante
""".split())

_MOT = re.compile(r"[A-Za-zÀ-ÿ]+")
_CHAMP = re.compile(r"\{[^{}]*\}")


def fautes(texte: str) -> List[str]:
    """Les mots de la liste fermee presents dans un texte.

    Les champs a remplir (« {numero} ») sont des noms de code et restent
    hors de la mesure.
    """
    return [m for m in _MOT.findall(_CHAMP.sub("", texte or ""))
            if m.lower() in IMPOSSIBLES]


def _chaines(valeur: Any) -> Iterator[str]:
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, (list, tuple)):
        for element in valeur:
            yield from _chaines(element)
    elif isinstance(valeur, dict):
        for element in valeur.values():
            yield from _chaines(element)


def _textes_du_catalogue() -> Iterator[Tuple[str, str]]:
    for type_produit in catalogue.TYPES:
        for attribut in ("nom", "resume", "detail"):
            yield type_produit.cle + "." + attribut, getattr(type_produit, attribut)
        if type_produit.quantite:
            yield type_produit.cle + ".quantite", type_produit.quantite[1]
        for champ in type_produit.champs:
            yield type_produit.cle + "." + champ.nom, champ.libelle + " " + champ.aide
            for valeur, etiquette in champ.etiquettes:
                yield type_produit.cle + "." + champ.nom + "=" + valeur, etiquette


class LeDetecteurSaitVoir(unittest.TestCase):
    """Un detecteur qu'on n'a pas vu sonner ne garde rien."""

    def test_il_reconnait_le_defaut_mesure(self):
        self.assertEqual(fautes("Tous droits reserves. Premiere edition"),
                         ["reserves", "Premiere"])
        self.assertEqual(fautes("Corriger mes reponses"), ["reponses"])

    def test_il_ne_crie_pas_sur_les_mots_justes_sans_accent(self):
        self.assertEqual(fautes("ce qui a le mieux marche, un auteur illustre, "
                                "ou la suite"), [])
        self.assertEqual(fautes("Module {numero} — {titre}"), [])


class LeMobilierDesProduits(unittest.TestCase):
    """Ce que l'acheteur lit autour du contenu, dans les dix-huit types."""

    def test_aucun_mot_francais_sans_son_accent(self):
        for cle, valeur in libelles.FR.items():
            if cle.startswith("fichier_"):
                continue  # des noms de fichiers : ASCII, et c'est voulu
            for texte in _chaines(valeur):
                with self.subTest(cle=cle):
                    self.assertEqual(fautes(texte), [], texte[:120])

    def test_les_mois_de_la_page_de_copyright(self):
        self.assertIn("février", libelles.FR["mois"])
        self.assertIn("août", libelles.FR["mois"])
        self.assertIn("décembre", libelles.FR["mois"])


class CeQueLeVendeurLit(unittest.TestCase):

    def test_les_types_de_produits(self):
        for ou, texte in _textes_du_catalogue():
            with self.subTest(ou=ou):
                self.assertEqual(fautes(texte), [], texte[:120])

    def test_les_reglages_leurs_groupes_et_les_peaux(self):
        textes = (list(reglages.DESCRIPTIONS.values())
                  + list(reglages.ETIQUETTES.values())
                  + [g["titre"] + " " + g["aide"] for g in reglages.GROUPES]
                  + [t["description"] for t in reglages.THEMES])
        for texte in textes:
            with self.subTest(texte=texte[:40]):
                self.assertEqual(fautes(texte), [], texte)


class DesMotsPasDesIdentifiants(unittest.TestCase):
    """Un nom de code en face d'un champ se lit comme un fichier de
    configuration. Chaque reglage et chaque agent a un nom a montrer."""

    def tearDown(self):
        reglages.reinitialiser()

    def test_chaque_reglage_a_une_etiquette(self):
        for nom in reglages.DEFAUTS:
            with self.subTest(reglage=nom):
                etiquette = reglages.ETIQUETTES.get(nom, "")
                self.assertTrue(etiquette.strip())
                self.assertNotIn("_", etiquette)

    def test_chaque_valeur_de_liste_a_une_etiquette(self):
        """« melancolique », « voyage du heros » s'affichaient tels quels dans
        les listes. Seules les tranches d'age (« 3-5 ans ») se lisent deja."""
        for type_produit in catalogue.TYPES:
            for champ in type_produit.champs:
                if champ.genre != "choix":
                    continue
                noms = dict(champ.etiquettes)
                for valeur in champ.choix:
                    if not valeur or valeur[0].isdigit():
                        continue
                    with self.subTest(type=type_produit.cle, champ=champ.nom,
                                      valeur=valeur):
                        self.assertIn(valeur, noms)
                        self.assertNotIn("_", noms[valeur])

    def test_chaque_agent_a_une_etiquette(self):
        for nom in equipe.EQUIPE:
            with self.subTest(agent=nom):
                etiquette = equipe.ETIQUETTES.get(nom, "")
                self.assertTrue(etiquette.strip())
                self.assertNotIn("_", etiquette)

    def test_le_tableau_de_bord_recoit_les_etiquettes(self):
        from usine.web import serveur

        etat = serveur._etat()
        for groupe in etat["groupes_reglages"]:
            for reglage in groupe["reglages"]:
                with self.subTest(reglage=reglage["nom"]):
                    self.assertEqual(reglage["etiquette"],
                                     reglages.ETIQUETTES[reglage["nom"]])
        for agent in etat["agents"]:
            with self.subTest(agent=agent["nom"]):
                self.assertEqual(agent["etiquette"],
                                 equipe.ETIQUETTES[agent["nom"]])

    def test_la_page_affiche_l_etiquette_et_garde_le_nom_pour_la_cle(self):
        """Le serveur peut envoyer l'etiquette : si la page affiche encore
        le nom, rien n'a change a l'ecran."""
        source = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        debut = source.index("function champReglage(")
        corps = source[debut:source.index("\n}\n", debut)]
        self.assertIn("reglage.etiquette", corps)
        puces = source[source.index("$('agents').innerHTML"):]
        puces = puces[:puces.index("join('')")]
        self.assertIn("a.etiquette", puces)
        self.assertIn('data-agent="${echapper(a.nom)}"', puces)

    def test_le_menu_termux_montre_les_etiquettes(self):
        sortie = io.StringIO()
        with redirect_stdout(sortie), mock.patch("builtins.input",
                                                 lambda invite="": "0"):
            menu.menu_reglages()
        ecran = sortie.getvalue()
        self.assertIn("Signature IA dans la licence", ecran)
        self.assertNotIn("signature_ia", ecran)

    def test_la_ligne_de_commande_montre_l_etiquette_et_le_nom(self):
        """Le nom reste : c'est lui qu'on tape dans « --definir »."""
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(io.StringIO()):
            cli.principal(["reglages"])
        ecran = sortie.getvalue()
        self.assertIn("Signature IA dans la licence", ecran)
        self.assertIn("(signature_ia)", ecran)


if __name__ == "__main__":
    unittest.main()
