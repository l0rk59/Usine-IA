"""Les branchements que cet audit a rétablis restent branchés.

Trois choses étaient déclarées mais reliées à rien : deux agents (styliste,
contrôleur) qui n'entraient jamais en action, et le réglage « signature_ia »
que la licence ignorait. Ces tests échouent si l'une redevient orpheline.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import evenements, llm, reglages  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("connexions")
    llm.definir_simulateur(simulateur)


class TestAgentsRelies(unittest.TestCase):
    """Un agent affiché dans l'équipe doit réellement travailler.

    Les deux étaient déclarés, montrés dans l'interface et la scène 3D, mais
    aucune chaîne ne les appelait : leur pastille ne s'allumait jamais.
    """

    def _agents_allumes(self, qualite):
        from usine.pipelines import ebook
        from usine.pipelines.base import Contexte

        vus = set()
        origine = evenements.publier

        def espion(type_, **kw):
            if type_ == "agent" and kw.get("etat") == "debut":
                vus.add(kw.get("agent"))
            return origine(type_, **kw)

        evenements.publier = espion
        try:
            ctx = Contexte(sujet="la prospection pour freelances",
                           audience="freelances", qualite=qualite,
                           chapitres=2, mots_section=300, sans_image=True,
                           journal=lambda m: None)
            ebook.produire(ctx)
        finally:
            evenements.publier = origine
        return vus

    def test_le_controleur_s_allume_meme_en_qualite_rapide(self):
        """Le contrôle déterministe EST le travail du contrôleur."""
        self.assertIn("controleur", self._agents_allumes("rapide"))

    def test_le_styliste_s_allume_en_qualite_exigeante(self):
        """La passe de style finale n'existe qu'au niveau exigeant."""
        vus = self._agents_allumes("exigeant")
        self.assertIn("styliste", vus)
        self.assertIn("editeur", vus)     # la relecture éditoriale aussi

    def test_le_styliste_ne_tourne_pas_en_qualite_rapide(self):
        """Rapide = aucune relecture : le styliste doit rester au repos."""
        self.assertNotIn("styliste", self._agents_allumes("rapide"))

    def test_plus_aucun_agent_declare_n_est_orphelin(self):
        """Chaque agent de l'équipe doit être invocable par du code réel.

        On lit le code plutôt que de tout exécuter : un agent dont le nom
        n'apparaît qu'à sa déclaration est un agent mort.
        """
        from usine.agents import equipe

        sources = "\n".join(
            f.read_text(encoding="utf-8")
            for f in (RACINE / "usine").rglob("*.py"))
        for nom, agent in equipe.EQUIPE.items():
            variable = nom.upper()
            # Nombre d'occurrences de la CONSTANTE agent (ARCHITECTE, ...) :
            # au moins une hors de sa définition dans equipe.py.
            occurrences = sources.count(variable)
            with self.subTest(agent=nom):
                self.assertGreater(
                    occurrences, 2,
                    "l'agent {} n'est presque jamais reference".format(nom))


class TestAucuneFonctionSansAppelant(unittest.TestCase):
    """« Une fonction que personne n'appelle ne protege personne. »

    La regle est dans CLAUDE.md, et rien ne la verifiait. La mesure en a
    trouve six : deux doublons d'utilitaires existants, un compteur rendu
    inutile par un refactor, trois restes d'une fonctionnalite abandonnee.
    Aucun test n'a casse en les retirant — ce qui est precisement la preuve
    qu'elles ne protegeaient personne.

    L'exemption est possible, mais elle se NOMME ici. Un ensemble vide est le
    bon etat par defaut : une fonction qu'on garde « au cas ou » est une
    fonction qu'on ne supprimera jamais, parce que le « cas » n'arrive pas et
    que personne n'osera decider.
    """

    # Vide, et c'est voulu. Ajouter un nom ici demande d'ecrire pourquoi.
    TOLEREES = frozenset()

    @staticmethod
    def _noms_lies(fonction):
        """Noms que la fonction fabrique elle-meme : parametres, variables, imports.

        Ce sont ceux qu'il ne faut PAS compter comme des appels : ils parlent
        d'autre chose que de la fonction de module qui porte le meme nom.
        """
        import ast

        noms = set()
        args = fonction.args
        for groupe in (args.posonlyargs, args.args, args.kwonlyargs):
            noms.update(a.arg for a in groupe)
        if args.vararg:
            noms.add(args.vararg.arg)
        if args.kwarg:
            noms.add(args.kwarg.arg)
        for noeud in ast.walk(fonction):
            if isinstance(noeud, ast.Name) and isinstance(noeud.ctx,
                                                          (ast.Store, ast.Del)):
                noms.add(noeud.id)
            elif isinstance(noeud, (ast.Import, ast.ImportFrom)):
                for alias in noeud.names:
                    noms.add((alias.asname or alias.name).split(".")[0])
        return noms

    @classmethod
    def _references(cls, fichiers):
        """Tout ce qui ressemble a « quelqu'un se sert de ce nom-la ».

        La premiere version de ce detecteur cherchait le nom dans le TEXTE du
        depot. Elle a laisse passer « http.en_ligne », qui n'avait aucun
        appelant : le mot apparaissait ailleurs comme nom de parametre
        (« en_ligne=not ctx.hors_ligne »), et cela suffisait a le declarer
        employe. Un garde-fou satisfait par une homonymie ne garde rien.

        On lit donc l'arbre : un appel, un attribut, un nom charge hors de sa
        propre portee. Les chaines de caracteres comptent aussi — une fonction
        atteinte par « getattr(module, "nom") » a un appelant bien reel, et
        l'accuser serait crier a tort.
        """
        import ast

        vues = set()
        for fichier in fichiers:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            lies = {}
            for noeud in ast.walk(arbre):
                if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    locaux = cls._noms_lies(noeud)
                    for sous in ast.walk(noeud):
                        lies.setdefault(id(sous), set()).update(locaux)
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Attribute):
                    vues.add(noeud.attr)
                elif isinstance(noeud, ast.Name) and isinstance(noeud.ctx, ast.Load):
                    if noeud.id not in lies.get(id(noeud), set()):
                        vues.add(noeud.id)
                elif isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                    vues.update(noeud.value.split())
                elif isinstance(noeud, (ast.Import, ast.ImportFrom)):
                    for alias in noeud.names:
                        vues.add(alias.name.split(".")[-1])
        return vues

    @classmethod
    def orphelines(cls, racine):
        import ast

        fichiers = sorted(racine.glob("usine/**/*.py"))
        vues = cls._references(fichiers + sorted(racine.glob("tests/*.py"))
                               + sorted(racine.glob("scripts/*.py")))
        # Le tableau de bord appelle des fonctions Python par leur nom, depuis
        # du JavaScript et des gabarits : les ignorer en ferait des orphelines.
        for fichier in sorted(racine.glob("usine/web/statique/*.js")):
            vues.update(fichier.read_text(encoding="utf-8")
                        .replace("(", " ").replace(".", " ").split())
        seules = []
        for fichier in fichiers:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            for noeud in arbre.body:
                if not isinstance(noeud, ast.FunctionDef):
                    continue
                if noeud.name.startswith("_") or noeud.name == "main":
                    continue
                if noeud.name not in vues:
                    seules.append("{}:{}".format(
                        fichier.relative_to(racine), noeud.name))
        return seules

    def test_aucune_fonction_publique_n_est_sans_emploi(self):
        restantes = [o for o in self.orphelines(RACINE)
                     if o.rsplit(":", 1)[-1] not in self.TOLEREES]
        self.assertEqual(restantes, [])

    # Les deux suivants portent sur le DETECTEUR lui-meme. Sans eux, le
    # controle ci-dessus pourrait passer parce qu'il ne trouve jamais rien,
    # et non parce qu'il n'y a rien a trouver — la difference ne se voit pas
    # depuis un depot en bon etat.
    @staticmethod
    def _depot(racine, contenu):
        (racine / "usine").mkdir(parents=True, exist_ok=True)
        (racine / "usine" / "module.py").write_text(contenu, encoding="utf-8")
        return racine

    def test_le_detecteur_trouve_une_fonction_sans_appelant(self):
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = self._depot(pathlib.Path(brut),
                                 "def seule():\n    return 1\n")
            self.assertEqual(self.orphelines(racine), ["usine/module.py:seule"])

    def test_le_detecteur_laisse_tranquille_une_fonction_appelee(self):
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = self._depot(
                pathlib.Path(brut),
                "def utile():\n    return 1\n\n\ndef autre():\n"
                "    return utile()\n")
            # « autre » n'est pas appelee non plus : seule « utile » l'est.
            self.assertEqual(self.orphelines(racine), ["usine/module.py:autre"])

    def test_le_detecteur_ignore_les_fonctions_privees(self):
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = self._depot(pathlib.Path(brut),
                                 "def _interne():\n    return 1\n")
            self.assertEqual(self.orphelines(racine), [])

    def test_un_parametre_homonyme_ne_compte_pas_pour_un_appel(self):
        """Le defaut exact qui a laisse « http.en_ligne » sans appelant.

        Le detecteur lisait le texte du depot. « en_ligne » y apparaissait
        souvent — comme nom de parametre, jamais comme appel — et cela
        suffisait a le declarer employe.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = self._depot(
                pathlib.Path(brut),
                "def en_ligne():\n    return True\n\n\n"
                "def dessiner(en_ligne=False):\n"
                "    return 1 if en_ligne else 0\n")
            # L'ordre est celui des definitions dans le fichier.
            self.assertEqual(self.orphelines(racine),
                             ["usine/module.py:en_ligne",
                              "usine/module.py:dessiner"])

    def test_une_fonction_atteinte_par_son_nom_en_chaine_n_est_pas_accusee(self):
        """L'autre direction : ne pas inventer un defaut.

        Un nom passe a getattr est un appelant bien reel. Le detecteur doit
        rater ce cas plutot que de le signaler.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = self._depot(
                pathlib.Path(brut),
                "def repondre():\n    return 1\n\n\n"
                "def routeur(mod):\n"
                "    return getattr(mod, \"repondre\")()\n")
            self.assertEqual(self.orphelines(racine), ["usine/module.py:routeur"])


class TestAucunImportInutile(unittest.TestCase):
    """Un import declare et jamais employe est du poids mort.

    Peu de chose sur un serveur, davantage sur un telephone : chaque import
    est un fichier ouvert, lu et compile au demarrage. Dix-sept trainaient,
    dont trois nes d'un refactor de la veille — c'est la qu'ils apparaissent,
    et personne ne les voit jamais si rien ne les cherche.
    """

    @staticmethod
    def inutiles(racine):
        import ast
        import re

        trouves = []
        for fichier in (sorted(racine.glob("usine/**/*.py"))
                        + sorted(racine.glob("tests/*.py"))
                        + sorted(racine.glob("scripts/*.py"))):
            texte = fichier.read_text(encoding="utf-8")
            lignes = texte.splitlines()
            for noeud in ast.walk(ast.parse(texte)):
                if not isinstance(noeud, (ast.Import, ast.ImportFrom)):
                    continue
                # Le corps SANS la ligne d'import : sinon l'import se
                # justifierait lui-meme.
                corps = "\n".join(l for i, l in enumerate(lignes, 1)
                                  if i != noeud.lineno)
                for alias in noeud.names:
                    if alias.name == "annotations":
                        continue
                    nom = alias.asname or alias.name.split(".")[0]
                    if not re.search(r"\b" + re.escape(nom) + r"\b", corps):
                        trouves.append("{}:{} {}".format(
                            fichier.relative_to(racine), noeud.lineno, nom))
        return trouves

    def test_aucun_import_ne_traine(self):
        self.assertEqual(self.inutiles(RACINE), [])

    def test_le_detecteur_voit_un_import_inutile(self):
        import tempfile

        with tempfile.TemporaryDirectory() as brut:
            racine = pathlib.Path(brut)
            (racine / "usine").mkdir()
            (racine / "usine" / "m.py").write_text(
                "import json\nimport re\n\n\ndef f():\n    return re\n",
                encoding="utf-8")
            self.assertEqual(self.inutiles(racine), ["usine/m.py:1 json"])


class TestEvenementsEtRoutesConsommes(unittest.TestCase):
    """Publier sans destinataire, servir sans appelant : deux orphelins.

    Les deux se ressemblent et coutent la meme chose. L'evenement
    « tronquee » etait publie a chaque reponse coupee au plafond de jetons —
    « le defaut le plus couteux du routeur », disait le commentaire qui
    l'avait introduit — et aucune interface ne l'affichait. La route
    « /api/reglages » etait servie et appelee par personne : le tableau de
    bord montrait les reglages sans pouvoir les changer.
    """

    @staticmethod
    def _page():
        return ((RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
            + (RACINE / "usine" / "web" / "statique" / "tableau.html").read_text(
                encoding="utf-8"))

    def test_chaque_evenement_publie_a_une_branche_dans_la_page(self):
        import re

        code = "\n".join(f.read_text(encoding="utf-8")
                         for f in (RACINE / "usine").rglob("*.py"))
        publies = sorted(set(re.findall(r'evenements\.publier\(\s*"(\w+)"', code)))
        self.assertTrue(publies)
        page = self._page()
        for genre in publies:
            with self.subTest(evenement=genre):
                self.assertIn(
                    "'{}'".format(genre), page,
                    "l'evenement « {} » est publie et affiche nulle part"
                    .format(genre))

    @classmethod
    def _routes_appelees(cls):
        """URLs que la page DEMANDE vraiment, pas celles qu'elle mentionne.

        Une premiere version cherchait la route n'importe ou dans le fichier,
        et se satisfaisait du commentaire qui expliquait justement qu'elle
        n'etait appelee par personne. Seuls comptent les appels : « fetch »
        et « EventSource ».
        """
        import re

        return set(re.findall(
            r"(?:fetch|EventSource)\(\s*[`'\"]([^`'\"?]+)", cls._page()))

    def test_chaque_route_servie_est_appelee_par_la_page(self):
        import re

        serveur = (RACINE / "usine" / "web" / "serveur.py").read_text(
            encoding="utf-8")
        routes = sorted(set(re.findall(
            r'chemin (?:==|\.startswith\()\s*"(/api/[\w/-]*)"', serveur)))
        self.assertTrue(routes)
        appelees = self._routes_appelees()
        self.assertTrue(appelees)
        for route in routes:
            # Une route a segment variable — « /api/ab/<numero> » — est
            # appelee par son prefixe, concatene au numero cote page.
            trouvee = any(appelee.startswith(route) or route.startswith(appelee)
                          for appelee in appelees)
            with self.subTest(route=route):
                self.assertTrue(
                    trouvee,
                    "« {} » est servie et appelee par personne".format(route))


class TestDocumentationAtteignable(unittest.TestCase):
    """Une note que rien ne reference est une note que personne ne lit.

    C'est le defaut de l'orphelin applique a la documentation : le fichier
    existe, il est juste, il est a jour — et le seul moyen de le trouver est
    de lister le dossier. Deux notes etaient dans ce cas, dont celle qui
    explique comment sauvegarder un atelier.

    Etre reference depuis le CODE suffit : le journal de production renvoie a
    « docs/VENDRE.md » au moment ou la question se pose, ce qui vaut mieux
    qu'un lien dans un sommaire.
    """

    # Ce qui peut renvoyer vers une note.
    MOTIFS = ("*.md", "docs/*.md", ".claude/skills/*/SKILL.md",
              "usine/*.py", "usine/*/*.py", "usine/web/statique/*")

    @classmethod
    def orphelines(cls, racine):
        """Notes de `racine/docs` que rien d'autre ne mentionne.

        Une note est lue fichier par fichier et non en un seul bloc, pour
        pouvoir l'ecarter d'elle-meme : une note qui cite son propre nom se
        vouche toute seule, et le garde-fou devient muet.
        """
        notes = sorted((racine / "docs").glob("*.md"))
        sources = [f for motif in cls.MOTIFS for f in sorted(racine.glob(motif))
                   if f.is_file()]
        orphelines = []
        for note in notes:
            texte = "\n".join(
                f.read_text(encoding="utf-8", errors="replace")
                for f in sources if f != note)
            if note.name not in texte:
                orphelines.append(note.name)
        return orphelines

    def test_chaque_note_est_atteignable(self):
        self.assertTrue(sorted((RACINE / "docs").glob("*.md")))
        # Pas de corpus dans le message : un echec doit tenir en une ligne,
        # sinon personne ne le lit.
        self.assertEqual(self.orphelines(RACINE), [])

    def test_une_note_qui_se_cite_elle_meme_reste_orpheline(self):
        """Sinon il suffirait qu'une note prononce son propre nom pour que le
        garde-fou la declare atteignable — et il ne garderait plus rien."""
        import tempfile

        with tempfile.TemporaryDirectory() as racine:
            chemin = pathlib.Path(racine)
            (chemin / "docs").mkdir()
            (chemin / "docs" / "SEULE.md").write_text(
                "Voir SEULE.md pour le detail.", encoding="utf-8")
            (chemin / "README.md").write_text("rien ici", encoding="utf-8")
            self.assertEqual(self.orphelines(chemin), ["SEULE.md"])

    def test_une_note_reliee_depuis_le_readme_passe(self):
        import tempfile

        with tempfile.TemporaryDirectory() as racine:
            chemin = pathlib.Path(racine)
            (chemin / "docs").mkdir()
            (chemin / "docs" / "SEULE.md").write_text("du contenu", encoding="utf-8")
            (chemin / "README.md").write_text("voir docs/SEULE.md", encoding="utf-8")
            self.assertEqual(self.orphelines(chemin), [])


class TestOptionsDuCatalogueAtteignables(unittest.TestCase):
    """Une option declaree doit etre proposee quelque part.

    Le catalogue declare des leviers par type de produit : relire le livre
    entier, produire le script de narration, poser une marge de reliure,
    choisir un reseau, ranger un recit dans une serie. Ils n'existaient que
    dans la ligne de commande — c'est-a-dire, en pratique, pour personne : la
    vraie porte d'entree de cette usine est le menu, sur un telephone.

    C'est le defaut du reglage orphelin deplace d'un cran. Le reglage
    orphelin etait affiche et jamais lu ; l'option inaccessible est lue et
    jamais proposee. Dans les deux cas l'utilisateur croit disposer d'un
    levier qu'il n'a pas.

    Exemption possible, mais nommee : « executer » desactive la verification
    du programme genere. C'est un levier de mise au point, pas un choix de
    fabrication, et le proposer dans un menu n'aiderait personne.
    """

    CLI_SEULEMENT = set()
    NON_PROPOSEES = {"executer"}

    def _options_declarees(self):
        from usine.pipelines import catalogue

        return {(t.cle, nom) for t in catalogue.TYPES for nom in t.options}

    def _repondre(self, fonction, reponses):
        """Pilote le menu par son entree standard, comme un doigt sur un
        ecran : c'est le seul moyen de verifier qu'une question est POSEE."""
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        entrees = iter(list(reponses))
        with redirect_stdout(io.StringIO()):
            with mock.patch("builtins.input",
                            lambda invite="": next(entrees, "")):
                return fonction()

    def test_chaque_option_declaree_est_demandee_a_l_utilisateur(self):
        """Lire le source ne suffit pas : le nom peut y figurer sans qu'aucune
        question ne soit posee. On fait donc repondre le menu."""
        from usine import menu

        # Une reponse qui accepte le defaut partout, sauf la ou il faut une
        # valeur non nulle pour que l'option existe.
        attendus = {
            "ebook": (["o"], "relecture_ensemble"),
            "formation": (["o"], "narration"),
            "impression": (["5"], "reliure"),
            # « 2 » : l'entree 1 est « l'usine decide », qui ne fixe rien.
            "social": (["2"], "reseau"),
            "logiciel": (["2"], "cible"),
            "idees": (["n"], "avec_marche"),
            "nouvelle": (["Les rails"], "serie"),
        }
        for cle, (reponses, option) in sorted(attendus.items()):
            with self.subTest(type=cle):
                valeurs = self._repondre(
                    lambda: menu._options_du_type(cle), reponses)
                self.assertIn(option, valeurs,
                              "le menu ne demande pas « {} » pour « {} »"
                              .format(option, cle))

    def test_aucune_option_du_catalogue_n_est_oubliee(self):
        """Le garde-fou structurel : une option ajoutee au catalogue demain
        doit apparaitre ici, sinon elle n'existera que dans la CLI."""
        from usine import menu

        couvertes = set()
        # Les types viennent du CATALOGUE, pas d'une liste recopiee ici. La
        # premiere version en tenait une : trois types ajoutes plus tard —
        # sequence e-mail, memo, quiz — n'auraient pas ete interroges, et
        # leurs options auraient ete declarees « couvertes » sans que le menu
        # ne pose la moindre question. Un garde-fou dont la liste est a jour
        # a la main garde jusqu'au jour ou on l'oublie.
        from usine.pipelines import catalogue as _catalogue

        for cle in _catalogue.cles(fabricables=True):
            # Les jeux a DEUX reponses ne sont pas decoratifs : un type qui
            # pose deux questions — le quiz demande son niveau, puis s'il
            # faut un bareme — ne peut pas atteindre la seconde avec une
            # reponse unique. Le garde-fou declarait alors « sans_bareme »
            # couverte alors que le menu ne la proposait nulle part.
            for reponses in (["o"], ["n"], ["1"], ["5"], ["x"],
                             ["n", "n"], ["1", "n"], ["o", "n"],
                             ["1", "5"], ["2", "o"]):
                couvertes |= set(self._repondre(
                    lambda: menu._options_du_type(cle), reponses))
        for cle, nom in sorted(self._options_declarees()):
            if nom in self.NON_PROPOSEES:
                continue
            with self.subTest(type=cle, option=nom):
                self.assertIn(nom, couvertes)

    def test_la_file_de_production_recoit_les_memes_options(self):
        """La file rejoue plus tard, sans personne devant l'ecran. Si elle ne
        stocke pas ce que le menu a demande, l'utilisateur a repondu pour
        rien — et la difference ne se voit qu'au produit livre."""
        source = (RACINE / "usine" / "menu.py").read_text(encoding="utf-8")
        avant_file = source.split("file_prod.ajouter")[0]
        self.assertIn("options.update(_options_du_type(", avant_file)

    def test_la_fabrication_directe_passe_les_options_a_la_commande(self):
        source = (RACINE / "usine" / "menu.py").read_text(encoding="utf-8")
        self.assertIn("arguments += _arguments_du_type(", source)

    def test_la_traduction_en_arguments_respecte_les_inversions(self):
        """La CLI expose « --sans-marche », le catalogue declare
        « avec_marche ». Une correspondance recopiee finit par diverger."""
        from usine import menu

        self.assertEqual(menu._ARGUMENTS["avec_marche"](False), ["--sans-marche"])
        self.assertEqual(menu._ARGUMENTS["avec_marche"](True), [])
        self.assertEqual(menu._ARGUMENTS["serie"]("Les rails"),
                         ["--serie", "Les rails"])
        self.assertEqual(menu._ARGUMENTS["narration"](True), ["--narration"])

    def test_les_arguments_traduits_sont_acceptes_par_la_cli(self):
        """Un argument invente serait refuse au lancement, apres avoir fait
        repondre l'utilisateur a toutes les questions."""
        from usine import cli, menu

        parseur = cli.construire_parseur()
        connus = set()
        for action in parseur._subparsers._group_actions[0].choices.values():
            connus.update(o for a in action._actions for o in a.option_strings)
        for nom, traduire in menu._ARGUMENTS.items():
            produits = traduire("x") + traduire(True) + traduire(False)
            for argument in produits:
                if argument.startswith("--"):
                    with self.subTest(option=nom, argument=argument):
                        self.assertIn(argument, connus)


class TestReglagesTousBranches(unittest.TestCase):
    """Un reglage propose a l'utilisateur doit piloter quelque chose.

    L'audit en avait trouve trois qui ne pilotaient rien — theme, effets_3d,
    signature_ia : affiches dans les trois interfaces, modifiables,
    enregistres sur disque, et lus par personne. Le defaut ne se voit pas,
    il s'accumule, et il trahit l'utilisateur en silence : il croit avoir
    regle quelque chose.

    Ce test relit le code source. Un reglage dont le nom n'apparait nulle
    part ailleurs que dans sa propre declaration n'est branche a rien. Il a
    immediatement trouve un quatrieme orphelin, « relectures », que l'audit
    avait manque : « qualite » decide seule du nombre de passes, et le
    reglage a donc ete retire plutot que branche — le brancher aurait
    silencieusement ramene a 1 les deux relectures du mode exigeant chez
    tous ceux qui avaient deja enregistre leurs reglages.
    """

    # Ce que le nom d'un reglage peut traverser avant d'agir.
    EXTENSIONS = (".py", ".js", ".html")

    # Les mots qui font d'une ligne une LECTURE de reglage. Chercher le nom
    # n'importe ou dans un fichier ne suffisait pas : « couverture » apparait
    # comme classe CSS dans le moteur EPUB et comme sujet de test A/B, ce qui
    # suffisait a le declarer branche. Il ne l'etait pas — reglage affiche,
    # enregistre, lu par personne.
    #
    # Deux autres dormaient derriere la meme homonymie : « plateforme » et
    # « devise », dont les valeurs par defaut etaient ecrites en dur dans la
    # CLI. Qui vend en francs suisses reglait sa devise et voyait « EUR » a
    # chaque import.
    #
    # « veut( » est arrive le 15/09/2026, quand le kit de vente et l'archive
    # ont quitte la ligne de commande pour un point commun que le tableau de
    # bord appelle aussi. Le detecteur a immediatement signale « marketing_auto »
    # et « archive_auto » comme orphelins : la cle etait la, sur une ligne
    # qu'il ne savait pas lire. Il avait raison de se plaindre — une liste de
    # verbes est une liste, elle ne devine pas. C'est le prix d'un detecteur
    # qui lit la STRUCTURE plutot qu'un nom « quelque part dans le code ».
    VERBES = ("lire(", "profil", "reglages", "charger()", "DEFAUTS",
              "veut(")

    @classmethod
    def orphelins(cls, lignes, noms):
        """Ceux dont aucune ligne DE LECTURE ne cite le nom.

        Le detecteur est separe de sa source pour pouvoir etre eprouve sur des
        lignes choisies : sinon il pourrait passer parce qu'il ne trouve
        jamais rien, et non parce qu'il n'y a rien a trouver.
        """
        import re

        utiles = [ligne for ligne in lignes
                  if any(verbe in ligne for verbe in cls.VERBES)]
        manquants = []
        for nom in noms:
            cite = any(
                '"{}"'.format(nom) in ligne or "'{}'".format(nom) in ligne
                or re.search(r"\breglages\.{}\b".format(nom), ligne)
                for ligne in utiles)
            if not cite:
                manquants.append(nom)
        return manquants

    @classmethod
    def _lignes_du_depot(cls):
        lignes = []
        for chemin in (RACINE / "usine").rglob("*"):
            if chemin.suffix not in cls.EXTENSIONS or chemin.name == "reglages.py":
                continue
            lignes.extend(chemin.read_text(encoding="utf-8").splitlines())
        return lignes

    def test_aucun_reglage_orphelin(self):
        from usine.core import reglages as module_reglages

        self.assertEqual(
            self.orphelins(self._lignes_du_depot(), module_reglages.DEFAUTS),
            [], "reglage(s) affiche(s) mais lu(s) par personne : "
                "les brancher, ou les retirer")

    def test_le_detecteur_voit_un_reglage_seulement_homonyme(self):
        """Le defaut exact qui a laisse passer « plateforme » et « devise ».

        Un nom cite hors de tout contexte de lecture — une classe CSS, un
        sujet de test A/B, une colonne de ventes — ne prouve pas qu'un
        reglage pilote quoi que ce soit.
        """
        lignes = ['if sujet == "couverture":',
                  '<img class="couverture" src="x"/>',
                  'total = ligne["devise"] + ligne["brut"]']
        self.assertEqual(self.orphelins(lignes, ["couverture", "devise"]),
                         ["couverture", "devise"])

    def test_le_detecteur_laisse_tranquille_un_reglage_vraiment_lu(self):
        """L'autre direction : un detecteur qui accuse tout finit ignore."""
        lignes = ['contact = reglages.lire("contact", "")',
                  'if profil.get("images", True):',
                  'const veut = donnees.reglages.effets_3d !== false;']
        self.assertEqual(
            self.orphelins(lignes, ["contact", "images", "effets_3d"]), [])

    def test_chaque_reglage_appartient_a_un_groupe(self):
        """Un reglage hors groupe est INVISIBLE dans les interfaces qui
        affichent par groupe : sauvegarde, lu par le code, et impossible a
        changer."""
        from usine.core import reglages as module_reglages

        self.assertEqual(module_reglages.non_groupes(), [])


class TestSignatureIA(unittest.TestCase):
    """Le réglage « signature_ia » doit décider de la mention dans la licence."""

    def tearDown(self):
        reglages.reinitialiser()

    def _licence(self):
        from usine.packaging import livraison

        dossier = reglages.chemin().parent
        chemin = livraison.ecrire_licence(dossier, "Un produit", "Moi")
        return chemin.read_text(encoding="utf-8")

    def test_activee_la_mention_ia_est_dans_la_licence(self):
        reglages.ecrire({"signature_ia": True})
        self.assertIn("TRANSPARENCE", self._licence())

    def test_desactivee_la_mention_disparait(self):
        reglages.ecrire({"signature_ia": False})
        texte = self._licence()
        self.assertNotIn("TRANSPARENCE", texte)
        # Le reste de la licence tient toujours.
        self.assertIn("LICENCE D'UTILISATION", texte)


if __name__ == "__main__":
    unittest.main()
