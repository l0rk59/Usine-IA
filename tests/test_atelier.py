"""L'outillage de test lui-meme : un atelier par module, et rien qui deborde.

Ces tests ne verifient pas l'usine, ils verifient la cloison entre les
suites. C'est le genre de chose qu'on ne regarde jamais — jusqu'au jour ou
un test passe seul et echoue dans la suite, ou l'inverse, et ou la piste
n'existe plus.
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import apprentissage, config, experience, store  # noqa: E402
from usine.core import file as file_prod  # noqa: E402

DOSSIER = Path(__file__).resolve().parent


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("atelier")


def _isolements() -> dict:
    """Nom d'atelier declare par chaque module de test, lu dans sa source.

    On lit le code plutot que d'importer : un module de test importe ici
    poserait son propre atelier au passage, ce qui est exactement ce qu'on
    cherche a mesurer.
    """
    trouves = {}
    for source in sorted(DOSSIER.glob("test_*.py")):
        arbre = ast.parse(source.read_text(encoding="utf-8"))
        noms = []
        for noeud in arbre.body:
            if not isinstance(noeud, ast.FunctionDef):
                continue
            if noeud.name != "setUpModule":
                continue
            for appel in ast.walk(noeud):
                if (isinstance(appel, ast.Call)
                        and isinstance(appel.func, ast.Attribute)
                        and appel.func.attr == "isoler"
                        and appel.args
                        and isinstance(appel.args[0], ast.Constant)):
                    noms.append(appel.args[0].value)
        trouves[source.name] = noms
    return trouves


class TestCloisonnement(unittest.TestCase):

    def test_chaque_module_de_test_pose_son_atelier(self):
        """Sans setUpModule, un module herite de l'atelier du precedent.

        Il travaille alors dans une base qu'il n'a pas remplie, ce qui ne
        se voit pas tant que personne ne compte.
        """
        for nom, isolements in sorted(_isolements().items()):
            with self.subTest(module=nom):
                self.assertEqual(
                    len(isolements), 1,
                    "{} doit declarer exactement un "
                    "setUpModule appelant atelier.isoler()".format(nom))

    def test_aucun_module_ne_partage_le_nom_d_un_autre(self):
        """Deux modules du meme nom retomberaient dans le meme dossier."""
        noms = [n for liste in _isolements().values() for n in liste]
        doublons = sorted({n for n in noms if noms.count(n) > 1})
        self.assertEqual(doublons, [], "ateliers partages : {}".format(doublons))

    def test_plus_aucun_module_ne_pose_usine_home_a_l_import(self):
        """La pose a l'import ne marchait que pour le premier module charge.

        `config` resout ses chemins une seule fois, et unittest importe tous
        les modules avant d'en executer un. Laisser cette ligne quelque part
        redonnerait l'illusion d'un isolement qui n'a pas lieu.
        """
        pose = re.compile(r"os\.environ[.\[].{0,20}USINE_HOME")
        for source in sorted(DOSSIER.glob("test_*.py")):
            texte = source.read_text(encoding="utf-8")
            with self.subTest(module=source.name):
                self.assertIsNone(
                    pose.search(texte),
                    "{} pose encore USINE_HOME lui-meme : c'est "
                    "atelier.isoler() qui s'en charge".format(source.name))

    def test_isoler_deplace_vraiment_l_usine(self):
        ici = config.WORKDIR
        ailleurs = atelier.isoler("atelier-temoin")
        try:
            self.assertNotEqual(ailleurs, ici)
            self.assertEqual(config.WORKDIR, ailleurs)
            self.assertEqual(config.DB_PATH, ailleurs / "usine.db")
            self.assertEqual(config.PRODUITS_DIR, ailleurs / "produits")
            # Et la base ouverte est bien celle du nouveau dossier.
            chemin = store.connect().execute(
                "PRAGMA database_list").fetchone()[2]
            self.assertEqual(Path(chemin).parent, ailleurs)
        finally:
            atelier.isoler("atelier")
        self.assertEqual(config.WORKDIR, ici)


class TestDrapeauxDeSchema(unittest.TestCase):
    """Les « tables deja creees » ne valent que pour la base ouverte."""

    def test_fermer_la_base_fait_tomber_les_drapeaux(self):
        file_prod._assurer()
        experience._assurer()
        apprentissage._assurer()
        self.assertTrue(file_prod._pret)
        self.assertTrue(experience._pret)
        self.assertTrue(apprentissage._pret)

        store.close()

        self.assertFalse(file_prod._pret, "la file croit encore ses tables la")
        self.assertFalse(experience._pret)
        self.assertFalse(apprentissage._pret)

    def test_les_tables_renaissent_dans_une_base_neuve(self):
        """Le vrai risque : une base changee sous les pieds du processus."""
        file_prod.ajouter("un sujet quelconque", "ebook")
        precedent = config.WORKDIR
        neuf = atelier.isoler("atelier-neuf")
        try:
            self.assertNotEqual(neuf, precedent)
            # Sans la remise a zero, ceci leve « no such table ».
            self.assertEqual(file_prod.lister(), [])
            self.assertEqual(apprentissage.historique(5), [])
            self.assertEqual(experience.lister(5), [])
        finally:
            atelier.isoler("atelier")


if __name__ == "__main__":
    unittest.main()
