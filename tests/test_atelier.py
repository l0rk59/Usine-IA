"""L'outillage de test lui-meme : un atelier par module, et rien qui deborde.

Ces tests ne verifient pas l'usine, ils verifient la cloison entre les
suites. C'est le genre de chose qu'on ne regarde jamais — jusqu'au jour ou
un test passe seul et echoue dans la suite, ou l'inverse, et ou la piste
n'existe plus.
"""

from __future__ import annotations

import ast
import io
import re
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
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


class TestCompatibilite(unittest.TestCase):
    """L'integration continue annonce Python 3.9 : encore faut-il que ce
    soit vrai.

    Un telephone qu'on ne met pas a jour garde longtemps sa version. Une
    syntaxe trop recente ne se verrait qu'a l'installation, chez quelqu'un
    d'autre, sans moyen de corriger sur place.
    """

    PLANCHER = (3, 9)

    def test_toute_la_source_se_lit_en_python_du_plancher(self):
        fautives = []
        for fichier in sorted(RACINE.rglob("*.py")):
            if "__pycache__" in fichier.parts or "atelier" in fichier.parts:
                continue
            try:
                ast.parse(fichier.read_text(encoding="utf-8"), str(fichier),
                          feature_version=self.PLANCHER)
            except SyntaxError as exc:
                fautives.append("{}:{} {}".format(
                    fichier.relative_to(RACINE), exc.lineno, exc.msg))
        self.assertEqual(fautives, [], "syntaxe posterieure a Python {}.{}"
                         .format(*self.PLANCHER))

    def test_le_plancher_annonce_est_celui_de_l_integration_continue(self):
        """Les deux se contrediraient sans que rien ne le signale."""
        atelier_ci = RACINE / ".github" / "workflows" / "tests.yml"
        self.assertTrue(atelier_ci.exists(), "workflow d'integration absent")
        declare = re.findall(r'"(\d+)\.(\d+)"',
                             atelier_ci.read_text(encoding="utf-8"))
        versions = sorted((int(a), int(b)) for a, b in declare)
        self.assertIn(self.PLANCHER, versions,
                      "la CI ne teste pas la version plancher")
        self.assertEqual(versions[0], self.PLANCHER,
                         "la CI descend plus bas que ce que ce test verifie")


class TestDependances(unittest.TestCase):
    """Zero dependance : c'est la contrainte fondatrice, pas une preference.

    Termux ne sait pas compiler de roue native. Un import ajoute par
    megarde ne se voit qu'a l'installation sur un telephone neuf.
    """

    def test_le_verificateur_ne_trouve_rien(self):
        sys.path.insert(0, str(RACINE / "scripts"))
        import dependances

        self.assertEqual(dependances.principal(), 0)

    def test_le_verificateur_verrait_une_dependance_ajoutee(self):
        sys.path.insert(0, str(RACINE / "scripts"))
        import dependances

        intrus = RACINE / "usine" / "_essai_dependance.py"
        intrus.write_text("import requests\n", encoding="utf-8")
        self.addCleanup(intrus.unlink, True)
        with redirect_stdout(io.StringIO()) as dit:
            code = dependances.principal()
        self.assertEqual(code, 1)
        self.assertIn("requests", dit.getvalue())

    def test_sans_la_liste_officielle_la_verification_a_lieu_quand_meme(self):
        """Python 3.9 n'a pas « sys.stdlib_module_names ». Le verificateur
        rendait alors 0 sans rien lire, et le job 3.9 de la CI etait vert
        pour cette seule raison. On retire la liste ici pour exercer la
        deduction sur n'importe quelle version."""
        sys.path.insert(0, str(RACINE / "scripts"))
        import dependances

        officielle = getattr(sys, "stdlib_module_names", None)
        if officielle is not None:
            del sys.stdlib_module_names
            self.addCleanup(setattr, sys, "stdlib_module_names", officielle)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dependances.principal(), 0)
        intrus = RACINE / "usine" / "_essai_dependance_39.py"
        intrus.write_text("import requests\n", encoding="utf-8")
        self.addCleanup(intrus.unlink, True)
        with redirect_stdout(io.StringIO()) as dit:
            code = dependances.principal()
        self.assertEqual(code, 1)
        self.assertIn("requests", dit.getvalue())


class TestFuites(unittest.TestCase):
    """Aucune cle d'API dans le depot — et aucune alerte sur ce qui n'en est
    pas une. Le controle precedent cherchait « gsk_ » seul et fut rouge
    quatorze lignes durant, sans une seule cle : il ne gardait plus rien."""

    def setUp(self):
        sys.path.insert(0, str(RACINE / "scripts"))
        import fuites

        self.fuites = fuites

    def test_le_depot_ne_contient_aucune_cle(self):
        with redirect_stdout(io.StringIO()) as dit:
            code = self.fuites.principal()
        self.assertEqual(code, 0, dit.getvalue())

    def test_une_cle_ajoutee_serait_vue_sans_etre_recopiee(self):
        import tempfile

        cle = "gsk_" + "Zq7" * 18
        dossier = Path(tempfile.mkdtemp())
        fichier = dossier / "notes.md"
        fichier.write_text("rappel\nGROQ_API_KEY={}\n".format(cle), encoding="utf-8")
        trouvees = self.fuites.fuites([fichier])
        self.assertEqual(len(trouvees), 1)
        self.assertTrue(trouvees[0].endswith(":2"))
        self.assertNotIn(cle, " ".join(trouvees))

    def test_un_prefixe_seul_n_est_pas_une_cle(self):
        """Ce que l'ancien controle signalait : documentation, aide, cles
        factices courtes. Aucune n'est un secret."""
        import tempfile

        dossier = Path(tempfile.mkdtemp())
        fichier = dossier / "aide.md"
        fichier.write_text("GROQ_API_KEY=gsk_...\naffichage `gsk_ab***xyz`\n"
                           "GROQ_API_KEY=gsk_secrete\n", encoding="utf-8")
        self.assertEqual(self.fuites.fuites([fichier]), [])

    def test_sans_liste_de_fichiers_rien_n_est_declare_propre(self):
        """Sans git, rendre 0 annoncerait « aucune fuite » sans avoir lu un
        seul fichier — le defaut que « dependances.py » avait sous 3.9."""
        def sans_git():
            raise OSError("git introuvable")

        vrai = self.fuites.fichiers_suivis
        self.fuites.fichiers_suivis = sans_git
        self.addCleanup(setattr, self.fuites, "fichiers_suivis", vrai)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.fuites.principal(), 2)

    def test_un_env_suivi_est_signale(self):
        import tempfile

        fichier = Path(tempfile.mkdtemp()) / ".env"
        fichier.write_text("GROQ_API_KEY=\n", encoding="utf-8")
        self.assertEqual(len(self.fuites.fuites([fichier])), 1)


class TestDrapeauxDeSchema(unittest.TestCase):
    """Les « tables deja creees » ne valent que pour la base ouverte."""

    def test_fermer_la_base_fait_tomber_les_drapeaux(self):
        """Mesure le COMPORTEMENT, pas le drapeau.

        La premiere version lisait « module._pret ». Elle est tombee le jour
        ou les trois modules ont cesse de recopier le meme couple
        assurer/oublier pour partager celui de « store » — alors que rien
        n'avait change pour l'utilisateur. Un test qui garde un detail
        d'implementation interdit de ranger le code sans le reecrire.

        Ce qui doit rester vrai : apres « close() », chaque module refait ses
        tables au lieu de croire qu'elles sont la.
        """
        modules = (file_prod, experience, apprentissage)
        for module in modules:
            module._assurer()
        executions = []
        vrai_connect = store.connect

        def compter():
            executions.append(1)
            return vrai_connect()

        # Sans remise a zero, « _assurer » ne rouvrirait rien : il croirait
        # ses tables deja creees.
        store.close()
        store.connect = compter
        try:
            for module in modules:
                module._assurer()
        finally:
            store.connect = vrai_connect
        self.assertEqual(len(executions), len(modules),
                         "un module croit encore ses tables la")

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


class TestEchelleDeMigrations(unittest.TestCase):
    """Une base d'hier doit arriver au schema d'aujourd'hui.

    C'est le seul endroit du depot ou une erreur detruit des donnees que
    personne ne peut reconstituer : l'historique de production vit sur le
    telephone de l'utilisateur, et nulle part ailleurs. Le defaut ne se voit
    pas chez qui developpe — sa base est toujours neuve, donc elle saute les
    paliers — mais des semaines plus tard, chez quelqu'un d'autre, sous la
    forme d'un « no such column » en pleine fabrication.

    Ces tests partent donc d'une base VRAIMENT ancienne : les tables telles
    qu'elles existaient au palier 1, et « PRAGMA user_version = 1 ».
    """

    def _base_v1(self) -> None:
        """Recree une base au palier 1 : sans empreintes, sans ventes."""
        store.close()
        if config.DB_PATH.exists():
            config.DB_PATH.unlink()
        config.ensure_dirs()
        conn = sqlite3.connect(str(config.DB_PATH), isolation_level=None)
        conn.executescript(
            """
            CREATE TABLE produits (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, titre TEXT,
                sujet TEXT, statut TEXT, dossier TEXT, cree_le REAL);
            CREATE TABLE appels (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fournisseur TEXT NOT NULL,
                modele TEXT, ts REAL NOT NULL, jour TEXT NOT NULL,
                ok INTEGER NOT NULL DEFAULT 1, tokens INTEGER DEFAULT 0,
                latence REAL DEFAULT 0, erreur TEXT, cle_id TEXT DEFAULT '');
            """
        )
        conn.execute(
            "INSERT INTO produits VALUES ('vieux','ebook','Un titre','sujet',"
            "'termine','/nulle/part', 1.0)")
        conn.execute("PRAGMA user_version = 1")
        conn.close()

    def _tables(self):
        with store.cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return {ligne[0] for ligne in cur.fetchall()}

    def test_une_base_du_palier_1_monte_au_palier_courant(self):
        self._base_v1()
        with store.cursor() as cur:
            version = cur.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, store.VERSION_SCHEMA)

    def _base_v3_sans_les_colonnes(self) -> None:
        """Une base au palier 3 : « variantes » existe, sans debut ni fin.

        C'est le seul cas qui distingue vraiment l'echelle du reste. Les
        paliers 2 et 3 ne font que creer des tables, et « CREATE TABLE IF NOT
        EXISTS » du schema les recree de toute facon : un test qui verifie
        leur presence passe meme si l'echelle ne tourne pas. Une COLONNE
        ajoutee a une table existante, elle, ne peut venir que d'un ALTER —
        donc de l'echelle.
        """
        store.close()
        if config.DB_PATH.exists():
            config.DB_PATH.unlink()
        config.ensure_dirs()
        conn = sqlite3.connect(str(config.DB_PATH), isolation_level=None)
        conn.executescript(
            """
            CREATE TABLE produits (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, titre TEXT,
                sujet TEXT, statut TEXT, dossier TEXT, cree_le REAL);
            CREATE TABLE variantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id INTEGER NOT NULL, etiquette TEXT NOT NULL,
                contenu TEXT NOT NULL, fichier TEXT,
                meta TEXT NOT NULL DEFAULT '{}', cree_le REAL NOT NULL);
            """
        )
        conn.execute("PRAGMA user_version = 3")
        conn.close()

    def _colonnes(self, table: str):
        with store.cursor() as cur:
            return {ligne[1] for ligne in cur.execute(
                "PRAGMA table_info({})".format(table))}

    def test_une_colonne_ajoutee_par_un_palier_apparait(self):
        """Le cas qui distingue l'echelle du schema.

        « CREATE TABLE IF NOT EXISTS » ne touche pas une table deja creee :
        sans l'echelle, ces deux colonnes n'existeraient jamais chez qui a
        deja lance une experience — et la premiere requete leverait
        « no such column: debut », des semaines apres la mise a jour.
        """
        self._base_v3_sans_les_colonnes()
        colonnes = self._colonnes("variantes")
        self.assertIn("debut", colonnes)
        self.assertIn("fin", colonnes)

    def test_les_tables_nees_apres_le_palier_1_apparaissent(self):
        """Celles-la viennent du schema, pas de l'echelle — mais leur absence
        se verrait tout de suite, donc le constat vaut quand meme."""
        self._base_v1()
        tables = self._tables()
        self.assertIn("empreintes", tables)   # palier 2
        self.assertIn("ventes", tables)       # palier 3

    def test_les_donnees_d_avant_survivent(self):
        """Une migration qui recree proprement en perdant tout n'en est pas
        une : l'historique de ventes et les produits sont irremplacables."""
        self._base_v1()
        produit = store.lire_produit("vieux")
        self.assertIsNotNone(produit)
        self.assertEqual(produit["titre"], "Un titre")

    def test_les_donnees_survivent_a_une_colonne_ajoutee(self):
        """Un ALTER ne doit pas se transformer en recreation de table."""
        self._base_v3_sans_les_colonnes()
        with store.cursor() as cur:
            cur.execute(
                "INSERT INTO variantes(experience_id, etiquette, contenu,"
                " cree_le) VALUES (1,'A','du texte', 1.0)")
            cur.execute("SELECT etiquette, debut FROM variantes")
            ligne = cur.fetchone()
        self.assertEqual(ligne[0], "A")
        self.assertIsNone(ligne[1])

    def test_un_index_sur_une_colonne_migree_est_pose_dans_les_deux_cas(self):
        """L'index qui a du sortir de SCHEMA doit exister quand meme.

        Il portait sur « produits(serie, rang) », des colonnes que l'echelle
        ajoute. Dans SCHEMA, il s'executait AVANT la migration et levait
        « no such column » : l'usine ne demarrait plus chez quiconque avait
        deja produit. Le deplacer apres « _migrer » repare cela — a condition
        qu'il soit encore pose, sur une base ancienne comme sur une neuve.
        """
        for preparer in (self._base_v1, self._base_v3_sans_les_colonnes):
            preparer()
            with self.subTest(depart=preparer.__name__):
                with store.cursor() as cur:
                    cur.execute("SELECT name FROM sqlite_master"
                                " WHERE type='index' AND name=?",
                                ("idx_produits_serie",))
                    self.assertIsNotNone(cur.fetchone())

    def test_une_base_neuve_saute_les_paliers_sans_les_rejouer(self):
        """Une base creee ce matin a deja toutes ses tables : lui faire
        rejouer l'echelle n'ajouterait rien et masquerait une erreur de
        palier derriere un « IF NOT EXISTS »."""
        store.close()
        if config.DB_PATH.exists():
            config.DB_PATH.unlink()
        with store.cursor() as cur:
            version = cur.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, store.VERSION_SCHEMA)
        self.assertIn("ventes", self._tables())

    def test_chaque_palier_declare_a_un_numero_atteignable(self):
        """Un palier numerote au-dela de VERSION_SCHEMA ne s'execute jamais :
        la migration est ecrite, commitee, et ne tourne chez personne."""
        for palier in store.MIGRATIONS:
            self.assertLessEqual(
                palier, store.VERSION_SCHEMA,
                "le palier {} ne sera jamais joue : VERSION_SCHEMA vaut {}"
                .format(palier, store.VERSION_SCHEMA))
