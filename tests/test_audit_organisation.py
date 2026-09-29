"""Ce que l'audit du 15/09/2026 a mesure, transforme en garde-fous.

Un audit qui trouve un defaut et le corrige laisse le depot propre un jour.
Un audit qui laisse un detecteur laisse le depot propre. Ces controles-la
lisent la STRUCTURE — arbre syntaxique, analyseur d'arguments reel — parce
qu'un garde-fou satisfait par un nom ne garde rien.

Trois d'entre eux sont nes d'un defaut reel :

  la copie de corps         trois modules recopiaient mot pour mot le meme
                            couple assurer/oublier, et le serveur cinq fois
                            la meme fermeture de journal ;
  la parite CLI/navigateur  la recherche de promesses de lecture n'existait
                            qu'en ligne de commande, donc pas pour qui pilote
                            l'usine depuis son telephone ;
  le titre fantome          une nouvelle annoncant trois scenes en rendait
                            six au sommaire.
"""

from __future__ import annotations

import ast
import collections
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("audit_organisation")


SOURCES = sorted(p for p in (RACINE / "usine").rglob("*.py"))


def _arbre(chemin: Path) -> ast.Module:
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


class AucunCorpsDeFonctionN_EstEcritDeuxFois(unittest.TestCase):
    """Un NOM partage ne prouve rien : « produire » est un protocole, chaque
    chaine a le sien. Ce qui coute, c'est la COPIE — le meme code a deux
    endroits diverge, et le jour ou l'on corrige l'un on oublie l'autre.
    """

    # Ce que le detecteur ignore, et pourquoi :
    # deux corps de moins de deux instructions se ressemblent par hasard
    # (« return x », « pass »), et les signaler noierait les vraies copies.
    INSTRUCTIONS_MINIMUM = 2

    def _copies(self):
        corps = collections.defaultdict(list)
        for chemin in SOURCES:
            for noeud in ast.walk(_arbre(chemin)):
                if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                utile = [n for n in noeud.body
                         if not (isinstance(n, ast.Expr)
                                 and isinstance(n.value, ast.Constant)
                                 and isinstance(n.value.value, str))]
                if len(utile) < self.INSTRUCTIONS_MINIMUM:
                    continue
                # La STRUCTURE, pas le texte : deux copies qui different par
                # un commentaire ou un nom de variable locale restent deux
                # copies.
                cle = ast.dump(ast.Module(body=utile, type_ignores=[]))
                corps[cle].append("{}:{} {}".format(
                    chemin.relative_to(RACINE), noeud.lineno, noeud.name))
        return {c: lieux for c, lieux in corps.items() if len(lieux) > 1}

    def test_aucune_fonction_n_est_recopiee(self):
        copies = self._copies()
        self.assertEqual(
            copies, {},
            "Ces corps sont identiques a plusieurs endroits :\n" + "\n".join(
                "  " + " / ".join(lieux) for lieux in copies.values()))

    def test_le_detecteur_voit_vraiment_une_copie(self):
        """Un detecteur qu'on n'a pas vu accuser n'accuse rien. Celui-ci a
        ete ecrit apres la correction : on lui montre le defaut."""
        source = ("def un(a, b):\n    total = a + b\n    return total * 2\n\n"
                  "def deux(a, b):\n    total = a + b\n    return total * 2\n")
        faux = RACINE / "usine" / "_temoin_copie.py"
        faux.write_text(source, encoding="utf-8")
        try:
            global SOURCES
            avant = SOURCES
            SOURCES = avant + [faux]
            try:
                self.assertTrue(self._copies())
            finally:
                SOURCES = avant
        finally:
            faux.unlink()


class CeQuiSeFaitEnLigneDeCommandeSeFaitAuNavigateur(unittest.TestCase):
    """Cette usine tourne sur un telephone. Une capacite qui n'existe qu'en
    CLI n'existe pas pour la plupart des sessions.

    Defaut constate : la recherche de promesses de lecture, ecrite, cablee a
    la CLI et documentee, restait introuvable depuis le navigateur.
    """

    # Les gestes de MAINTENEUR, et la raison de chacun. Ils ecrivent des
    # fichiers qu'on edite ensuite dans un editeur de texte, ou qu'on pousse
    # sur le depot : un bouton de telephone n'y changerait rien.
    HORS_NAVIGATEUR = {
        "specs": "ecrit SPECS-APPAREIL.md a la racine du depot, pour le pousser",
        "prompts-systeme": "exporte des fichiers a editer dans un editeur",
        "maj": "met a jour le depot lui-meme ; le serveur tourne dessus",
        "web": "c'est la commande qui LANCE le navigateur",
        "menu": "c'est l'autre interface",
        "cles": "saisie de cles API : jamais par le reseau, meme local",
    }

    def _commandes(self):
        from usine import cli

        parseur = cli.construire_parseur()
        sous = [a for a in parseur._actions
                if hasattr(a, "choices") and a.choices]
        return sorted(sous[0].choices) if sous else []

    def _absentes(self, commandes, serveur, script, exceptions):
        """La detection elle-meme, appelee PAR le test et PAR son temoin.

        La premiere version la reecrivait dans le temoin. Les deux passaient,
        et neutraliser celle du test ne faisait echouer personne : un
        detecteur vert ne se garde pas lui-meme, et un temoin qui refait le
        calcul ne garde que sa propre copie.
        """
        from usine.pipelines import catalogue

        # Les types de produits passent tous par « /api/fabriquer » : les
        # exiger un par un dans le script accuserait a tort.
        fabricables = set(catalogue.cles(fabricables=True))
        absentes = []
        for commande in commandes:
            if commande in fabricables or commande in exceptions:
                continue
            formes = (commande, commande.replace("-", "_"))
            if not any(f in serveur or f in script for f in formes):
                absentes.append(commande)
        return absentes

    def _sources_du_navigateur(self):
        return ((RACINE / "usine" / "web" / "serveur.py").read_text(
                    encoding="utf-8"),
                (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
                    encoding="utf-8"))

    def test_chaque_commande_est_atteignable_depuis_le_navigateur(self):
        serveur, script = self._sources_du_navigateur()
        absentes = self._absentes(self._commandes(), serveur, script,
                                  self.HORS_NAVIGATEUR)
        self.assertEqual(absentes, [], "\n".join([
            "Ces commandes n'existent qu'en ligne de commande :",
            ", ".join(absentes),
            "Soit elles gagnent un chemin dans le tableau de bord, soit "
            "elles rejoignent HORS_NAVIGATEUR avec la raison."]))

    def test_le_detecteur_de_parite_accuse_vraiment(self):
        serveur, script = self._sources_du_navigateur()
        self.assertEqual(
            self._absentes(["commande-qui-n-existe-nulle-part"],
                           serveur, script, {}),
            ["commande-qui-n-existe-nulle-part"])

    def _perimees(self, exceptions, commandes):
        """Une exception qui designe une commande disparue est un mensonge
        tranquille : elle laisse croire qu'on a examine le cas."""
        return sorted(set(exceptions) - set(commandes))

    def test_la_liste_des_exceptions_ne_pourrit_pas(self):
        self.assertEqual(
            self._perimees(self.HORS_NAVIGATEUR, self._commandes()), [])

    def test_le_detecteur_d_exception_perimee_accuse_vraiment(self):
        self.assertEqual(
            self._perimees({"commande-retiree": "raison sans objet"},
                           self._commandes()),
            ["commande-retiree"])

    def test_chaque_exception_porte_sa_raison(self):
        for commande, raison in self.HORS_NAVIGATEUR.items():
            self.assertTrue(len(raison) > 20, commande)


class AucunBoutonN_EstMort(unittest.TestCase):
    """Un bouton sans ecouteur se clique, rien ne se passe, et l'utilisateur
    conclut que la fonction est cassee."""

    def test_chaque_bouton_du_gabarit_est_branche(self):
        html = (RACINE / "usine" / "web" / "statique" / "tableau.html"
                ).read_text(encoding="utf-8")
        script = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        self.assertEqual(self._morts(html, script), [])

    def _morts(self, html, script):
        return [b for b in sorted(set(re.findall(
            r'<button[^>]*id="([a-zA-Z0-9_-]+)"', html)))
            if "'{}'".format(b) not in script]

    def test_le_detecteur_de_bouton_mort_accuse_vraiment(self):
        """Ecrit apres la correction, il ne pouvait pas etre vu echouer sur
        un vrai bouton mort. On lui en montre un."""
        script = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        faux = '<button id="bouton-sans-ecouteur">Cliquer</button>'
        self.assertEqual(self._morts(faux, script), ["bouton-sans-ecouteur"])


class AucunTitreFantomeDansUneFiction(unittest.TestCase):
    """Le titre d'une scene est ajoute par la chaine. Un titre laisse dans le
    corps en fabrique un second, qui entre au sommaire du PDF et dans la
    navigation de l'EPUB.

    Mesure du 15/09/2026 : avec un modele qui place « ## Le principe de
    base » au milieu de chaque scene, une nouvelle annoncant trois scenes
    rendait SIX entrees.
    """

    def test_les_chaines_de_fiction_retirent_tous_les_titres(self):
        """Structurel : on cherche l'APPEL, pas le nom. Une chaine qui
        definirait « sans_titres » sans l'appeler passerait un test qui lit
        le fichier."""
        from usine.pipelines import fiction

        attendues = {"nouvelle": "rediger_scene",
                     "interactive": "_rediger_section",
                     "feuilleton": "_ecrire_recap"}
        for module, fonction in attendues.items():
            chemin = RACINE / "usine" / "pipelines" / "{}.py".format(module)
            arbre = _arbre(chemin)
            cible = next((n for n in ast.walk(arbre)
                          if isinstance(n, ast.FunctionDef)
                          and n.name == fonction), None)
            self.assertIsNotNone(cible, "{}.{}".format(module, fonction))
            appels = [n for n in ast.walk(cible)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name)
                      and n.func.id == "sans_titres"]
            self.assertTrue(appels, "{}.{} ne nettoie pas les titres".format(
                module, fonction))
        # Et la fonction n'existe qu'a un seul endroit.
        self.assertTrue(callable(fiction.est_fiction))

    def test_le_nettoyage_garde_le_texte(self):
        from usine.pipelines.base import sans_titres

        propre = sans_titres("Elle poussa la porte.\n\n## Un titre\n\n"
                             "Le vent entra.")
        self.assertNotIn("#", propre)
        self.assertIn("Elle poussa la porte.", propre)
        self.assertIn("Le vent entra.", propre)
