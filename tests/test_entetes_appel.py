"""Les en-tetes d'un appel a un fournisseur, construits a un seul endroit.

Le defaut qui a rendu ce module necessaire : OpenCode Go refuse tout appel
sans en-tete « x-opencode-session ». Six modeles, six cents requetes par
jour, un abonnement paye — et pas un seul appel n'aboutissait.

Le code seul n'en disait rien : « HTTP 400 ». C'est le CORPS de la reponse
qui le nommait, et personne ne le lisait.

Ce qui suit garde les deux moities de la correction : l'en-tete part bien,
et il part de PARTOUT. Quatre endroits construisaient ces en-tetes chacun a
sa facon ; n'en corriger qu'un aurait donne le defaut favori de ce depot —
la chose marche a un endroit, echoue ailleurs, et l'ecart ne se voit qu'a
l'usage.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("entetes_appel")


from usine.core import config  # noqa: E402


class LEnTeteDeSessionPart(unittest.TestCase):

    def test_opencode_recoit_son_en_tete_de_session(self):
        p = config.PROVIDERS_BY_NAME["opencode"]
        entetes = config.entetes_appel(p, "sk-quelconque")
        self.assertIn("x-opencode-session", entetes)
        self.assertTrue(entetes["x-opencode-session"])

    def test_un_fournisseur_qui_n_en_demande_pas_n_en_recoit_pas(self):
        """Envoyer un en-tete inconnu a tout le monde, c'est chercher un 400
        chez les huit autres pour en reparer un."""
        p = config.PROVIDERS_BY_NAME["groq"]
        for nom in config.entetes_appel(p, "sk-quelconque"):
            self.assertNotIn("session", nom.lower())

    def test_sans_cle_pas_de_session(self):
        """La session se derive de la cle : sans cle, il n'y a rien a
        deriver, et un identifiant invente ne routerait rien."""
        p = config.PROVIDERS_BY_NAME["opencode"]
        self.assertNotIn("x-opencode-session", config.entetes_appel(p, ""))

    def test_la_session_ne_laisse_pas_remonter_a_la_cle(self):
        """Elle part sur le reseau a chaque appel."""
        cle = "sk-une-cle-tres-secrete-1234567890"
        valeur = config.entetes_appel(
            config.PROVIDERS_BY_NAME["opencode"], cle)["x-opencode-session"]
        self.assertNotIn(cle, valeur)
        self.assertNotIn(cle[3:12], valeur)

    def test_la_session_est_stable_et_propre_a_la_cle(self):
        """Stable, parce qu'une session qui change a chaque appel n'est pas
        une session. Propre a la cle, sinon deux comptes n'en font qu'un."""
        p = config.PROVIDERS_BY_NAME["opencode"]
        a1 = config.entetes_appel(p, "cle-A")["x-opencode-session"]
        a2 = config.entetes_appel(p, "cle-A")["x-opencode-session"]
        b = config.entetes_appel(p, "cle-B")["x-opencode-session"]
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)


class PersonneNeConstruitCesEnTetesDeSonCote(unittest.TestCase):
    """Le garde-fou lit la STRUCTURE, pas un nom.

    Chercher « entetes_appel » quelque part dans le fichier serait satisfait
    par un commentaire. Ce qu'on veut savoir est autre chose : existe-t-il
    encore une fonction qui parle a un fournisseur ET pose son
    « Authorization » elle-meme ? Si oui, elle oubliera l'en-tete suivant.
    """

    def _fautives(self):
        fautives = []
        for chemin in sorted((RACINE / "usine").rglob("*.py")):
            if chemin.name == "config.py":
                continue  # c'est lui, l'endroit unique
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                corps = ast.dump(noeud)
                pose = any(
                    isinstance(c, ast.Assign)
                    and any(isinstance(ci, ast.Subscript)
                            and isinstance(ci.slice, ast.Constant)
                            and ci.slice.value == "Authorization"
                            for ci in c.targets)
                    for c in ast.walk(noeud))
                # « parle a un fournisseur » se lit a l'usage de son URL de
                # base : c'est ce qui distingue un appel de fournisseur d'un
                # appel a un service tiers (le generateur d'images).
                fournisseur = "base_url" in corps
                if pose and fournisseur:
                    fautives.append("{}:{}".format(chemin.name, noeud.name))
        return fautives

    def test_aucune_fonction_ne_pose_son_autorisation_elle_meme(self):
        self.assertEqual(self._fautives(), [], "\n".join([
            "Ces fonctions appellent un fournisseur en construisant leurs "
            "en-tetes a la main.", "Elles oublieront le prochain en-tete "
            "exige, comme les quatre d'avant ont oublie celui d'OpenCode.",
            "Passer par « config.entetes_appel »."]))

    def test_le_detecteur_voit_vraiment_quelque_chose(self):
        """Un detecteur qu'on n'a pas vu accuser n'accuse rien.

        Celui-ci a ete ecrit apres la correction : il ne pouvait donc pas
        etre vu echouer sur le vrai defaut. On le lui montre ici.
        """
        source = ('def interroger(fournisseur):\n'
                  '    entetes = {}\n'
                  '    entetes["Authorization"] = "Bearer x"\n'
                  '    return fournisseur.base_url\n')
        faux = RACINE / "usine" / "_temoin_entetes.py"
        faux.write_text(source, encoding="utf-8")
        try:
            self.assertIn("_temoin_entetes.py:interroger", self._fautives())
        finally:
            faux.unlink()


class LesQuatreAppelantsPassentBienParLa(unittest.TestCase):
    """Le test precedent dit que personne ne le fait a la main. Celui-ci dit
    que quelqu'un le fait tout court — sans quoi plus aucun appel n'est
    authentifie, et les deux tests seraient verts."""

    def test_le_routeur_la_sonde_et_les_deux_catalogues_l_appellent(self):
        attendus = {"llm.py": 2, "diagnostic.py": 1, "modeles.py": 1}
        for nom, compte in attendus.items():
            arbre = ast.parse(
                (RACINE / "usine" / "core" / nom).read_text(encoding="utf-8"))
            appels = [n for n in ast.walk(arbre)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute)
                      and n.func.attr == "entetes_appel"]
            self.assertEqual(len(appels), compte, nom)
