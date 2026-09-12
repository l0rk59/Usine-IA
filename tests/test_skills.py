"""Les skills du depot doivent dire la verite sur le code.

Une skill se lit comme une consigne : elle nomme des fichiers, des fonctions
et des commandes, et celui qui la suit les prend pour argent comptant. Le jour
ou une fonction est renommee, la skill continue de la citer — sans erreur,
sans avertissement, jusqu'a ce que quelqu'un tape la commande et perde une
heure a comprendre pourquoi elle ne marche pas.

C'est le meme defaut que le depot traque ailleurs : une consigne emise,
jamais relue. Ces tests la relisent.

Ils ne jugent pas le contenu — seulement ce qui est verifiable
mecaniquement : la forme de l'entete, l'existence des chemins cites, et
l'existence des fonctions citees. Un garde-fou qui pretendrait juger la
qualite d'une skill crierait a tort, et finirait ignore.
"""

from __future__ import annotations

import builtins
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402

SKILLS = RACINE / ".claude" / "skills"

# Le harnais tronque la description au-dela de cette longueur : une skill plus
# bavarde perd la fin de sa regle d'aiguillage, sans le dire.
DESCRIPTION_MAX = 1536

# Au-dela, le corps est charge en entier a chaque declenchement pour rien.
CORPS_MAX = 500


def setUpModule():
    atelier.isoler("skills")


def _skills():
    return sorted(d for d in SKILLS.iterdir() if (d / "SKILL.md").exists())


def _entete(fichier: Path):
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    if not lignes or lignes[0] != "---":
        return None, lignes
    fin = lignes.index("---", 1)
    entete = {}
    for ligne in lignes[1:fin]:
        cle, _, valeur = ligne.partition(":")
        if _:
            entete[cle.strip()] = valeur.strip()
    return entete, lignes[fin + 1:]


class TestEntete(unittest.TestCase):
    def test_il_y_a_des_skills(self):
        """Sans ce controle, tous les autres passeraient sur une liste vide."""
        self.assertTrue(_skills())

    def test_chaque_entete_est_lisible(self):
        for skill in _skills():
            with self.subTest(skill=skill.name):
                entete, _ = _entete(skill / "SKILL.md")
                # Le « --- » doit etre la premiere ligne du fichier, sinon le
                # harnais lit tout le fichier comme du contenu et la skill ne
                # se declenche jamais.
                self.assertIsNotNone(entete, "entete absent ou mal placee")
                self.assertEqual(entete.get("name"), skill.name)
                self.assertTrue(entete.get("description"))

    def test_la_description_tient_dans_la_limite(self):
        for skill in _skills():
            entete, _ = _entete(skill / "SKILL.md")
            with self.subTest(skill=skill.name):
                self.assertLessEqual(len(entete["description"]), DESCRIPTION_MAX)

    def test_le_corps_reste_court(self):
        for skill in _skills():
            _, corps = _entete(skill / "SKILL.md")
            with self.subTest(skill=skill.name):
                self.assertLess(len(corps), CORPS_MAX)


class TestCeQueLesSkillsCitent(unittest.TestCase):
    """Une skill qui cite un chemin ou une fonction disparue est un piege."""

    CHEMIN = re.compile(
        r"`((?:usine|tests|scripts|docs|\.claude)/[\w/.-]+\.(?:py|md|json))`")
    COMMANDE = re.compile(r"python3 ((?:tests|scripts|\.claude)/[\w/.-]+\.py)")
    # Un identifiant suivi de parentheses dans une skill est un appel : il doit
    # correspondre a une fonction reelle. Le dernier segment suffit —
    # « store.connect() » et « connect() » designent la meme definition.
    APPEL = re.compile(r"`(?:[\w.]+\.)?(\w+)\(\)`")

    @classmethod
    def setUpClass(cls):
        cls.sources = "\n".join(
            f.read_text(encoding="utf-8")
            for f in list((RACINE / "usine").rglob("*.py"))
            + list((RACINE / "tests").glob("*.py"))
            + list((RACINE / "scripts").glob("*.py")))
        cls.textes = {s.name: (s / "SKILL.md").read_text(encoding="utf-8")
                      for s in _skills()}

    def test_les_chemins_cites_existent(self):
        for nom, texte in self.textes.items():
            for chemin in set(self.CHEMIN.findall(texte)):
                with self.subTest(skill=nom, chemin=chemin):
                    self.assertTrue((RACINE / chemin).exists())

    def test_les_commandes_citees_existent(self):
        for nom, texte in self.textes.items():
            for chemin in set(self.COMMANDE.findall(texte)):
                with self.subTest(skill=nom, commande=chemin):
                    self.assertTrue((RACINE / chemin).exists())

    def test_les_fonctions_citees_existent(self):
        connus = dir(builtins)
        for nom, texte in self.textes.items():
            for appel in set(self.APPEL.findall(texte)):
                if appel in connus:
                    continue
                with self.subTest(skill=nom, fonction=appel):
                    self.assertIn(
                        "def {}(".format(appel), self.sources,
                        "« {}() » est cite par la skill {} et n'existe pas"
                        .format(appel, nom))


class TestOutilsLivresAvecLesSkills(unittest.TestCase):
    """Un script livre dans une skill doit au moins se lancer."""

    def test_chaque_script_se_compile(self):
        import py_compile

        scripts = list(SKILLS.rglob("scripts/*.py"))
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=script.name):
                py_compile.compile(str(script), doraise=True)

    def test_la_campagne_d_exemple_est_jouable(self):
        """Les motifs de l'exemple doivent encore se trouver dans le code.

        Une campagne de mutation dont les motifs ont vieilli ne signale rien :
        elle rend « motif absent » pour tout, ce qui ressemble a un succes
        quand on lit vite.
        """
        import json

        exemple = SKILLS / "mutation" / "exemple.json"
        campagne = json.loads(exemple.read_text(encoding="utf-8"))
        self.assertTrue(campagne)
        for mutation in campagne:
            cible = RACINE / mutation["fichier"]
            with self.subTest(mutation=mutation["titre"]):
                self.assertTrue(cible.exists())
                contenu = cible.read_text(encoding="utf-8")
                self.assertEqual(
                    contenu.count(mutation["avant"]), 1,
                    "le motif doit apparaitre exactement une fois")


if __name__ == "__main__":
    unittest.main()
