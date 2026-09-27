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
    debutant debutants intermediaire reperes achete reveiller
    cle cles livree livrees pret prets echec echecs exigee defaut etat etats
    generee generees heros verifiee antiseche
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


class LesMessagesDuCode(unittest.TestCase):
    """Le journal, la console et les notifications : ce qui defile sous les
    yeux de l'utilisateur pendant chaque fabrication (« Etape 1/5 »,
    « Termine. », « deja ecrit — repris du carnet »).

    Lu dans l'arbre syntaxique : seul le PREMIER argument des fonctions qui
    affichent compte, et pas ce qui sert de cle (« rapport["probleme"] ») ni
    un nom de fichier (« verification.json »). Les commandes a taper
    (« usine reglages ») restent sans accent : c'est ce qu'on tape.
    """

    AFFICHENT = frozenset({"journal", "ok", "alerte", "erreur",
                           "titre_console", "dire", "notifier", "entete"})

    def test_aucun_message_affiche_sans_ses_accents(self):
        import ast

        trouves = []
        for fichier in sorted((RACINE / "usine").rglob("*.py")):
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            for appel in ast.walk(arbre):
                if not (isinstance(appel, ast.Call) and appel.args):
                    continue
                nom = getattr(appel.func, "attr", getattr(appel.func, "id", ""))
                if nom not in self.AFFICHENT:
                    continue
                # Une cle (« rapport["probleme"] ») ou ce qu'on passe a
                # « .format() » et « .get() » n'est pas le message.
                cles = {id(c) for n in ast.walk(appel.args[0])
                        if isinstance(n, ast.Subscript)
                        for c in ast.walk(n.slice)}
                cles |= {id(c) for n in ast.walk(appel.args[0])
                         if isinstance(n, ast.Call)
                         for a in n.args for c in ast.walk(a)}
                for noeud in ast.walk(appel.args[0]):
                    if (isinstance(noeud, ast.Constant)
                            and isinstance(noeud.value, str)
                            and id(noeud) not in cles):
                        texte = re.sub(r"«\s*usine[^»]*»|\busine \w+|"
                                       r"[\w-]+\.(?:json|md|csv|py|txt)\b",
                                       "", noeud.value)
                        for mot in fautes(texte):
                            trouves.append("{}:{} {}".format(
                                fichier.relative_to(RACINE), noeud.lineno, mot))
        self.assertEqual(trouves, [])


class LeMenuDuTelephone(unittest.TestCase):
    """La vraie porte d'entree de l'usine : chaque ecran se lit sans faute
    d'accent sur la liste fermee."""

    def test_les_ecrans_des_sections(self):
        frappes = iter(["1", "0", "3", "0", "4", "0", "5", "0", "6", "0", "0"])
        sortie = io.StringIO()
        with redirect_stdout(sortie), mock.patch(
                "builtins.input", lambda invite="": next(frappes, "0")):
            menu.menu_principal(lambda arguments: 0)
        ecran = sortie.getvalue()
        self.assertIn("Réglages", ecran)
        self.assertEqual(fautes(ecran), [])


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
        # Le vocabulaire de Python n'a rien a faire en face d'une case.
        self.assertNotIn("True", ecran)
        self.assertNotIn("False", ecran)
        self.assertRegex(ecran, r"Signature IA dans la licence\s+.*oui")

    def test_la_ligne_de_commande_montre_l_etiquette_et_le_nom(self):
        """Le nom reste : c'est lui qu'on tape dans « --definir »."""
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(io.StringIO()):
            cli.principal(["reglages"])
        ecran = sortie.getvalue()
        self.assertIn("Signature IA dans la licence", ecran)
        self.assertIn("(signature_ia)", ecran)


class LeCatalogueEntierEnFrancais(unittest.TestCase):
    """Ce que l'acheteur francais ouvre, fichier par fichier.

    Les tests ci-dessus lisent le CODE : les libelles, les messages. Ils
    ne voyaient pas les valeurs que les chaines affichent a travers une
    table vide en francais — mesure du 27/09/2026 : « niveau debutant » sur
    la couverture d'un quiz, « etapes » et « reperes » dans le tableur d'un
    memo. Ici, tout le catalogue est fabrique en francais par un modele qui
    n'ecrit que « zz… », et chaque fichier livre est relu : ce qui reste de
    francais vient de l'usine.

    Meme liste fermee que plus haut, donc memes limites : un mot absent de
    la liste passe, et c'est voulu.
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_langue_livree import (_fabriquer, _texte_visible,
                                              fichiers_livres, simulateur_neutre)
        from usine.core import llm

        atelier.isoler("accents-catalogue")
        reglages.ecrire(dict(images=False, qualite="rapide", langue="francais",
                             auteur="Zz", archive_auto=True,
                             marketing_auto=True))
        llm.definir_simulateur(simulateur_neutre())
        cls.lus = {}
        cls.trouves = {}
        cls.formulaires = {}
        try:
            for rang, fiche in enumerate(catalogue.tous(fabricables=True)):
                # « idees » ne livre rien a un acheteur : c'est une liste de
                # niches pour le vendeur, sans dossier de produit.
                if fiche.cle == "idees":
                    continue
                ctx, _dits = _fabriquer(fiche.cle, "zz zz {}".format(rang))
                lus = list(fichiers_livres(ctx.dossier))
                cls.lus[fiche.cle] = len(lus)
                cls.trouves[fiche.cle] = sorted({
                    "{} : {}".format(nom, mot)
                    for nom, brut in lus
                    for mot in fautes(_texte_visible(nom, brut))})
                # « 29 repère(s) en 6 bloc(s) » : la notation d'un formulaire
                # sur la couverture d'un produit (voir « libelles.accorder »).
                cls.formulaires[fiche.cle] = sorted({
                    "{} : {}".format(nom, ligne.strip()[:70])
                    for nom, brut in lus
                    for ligne in _texte_visible(nom, brut).splitlines()
                    if "(s)" in ligne})
        finally:
            llm.definir_simulateur(None)

    def test_chaque_type_a_ete_lu(self):
        for cle in catalogue.cles(fabricables=True):
            if cle == "idees":
                continue
            with self.subTest(type=cle):
                self.assertGreaterEqual(self.lus.get(cle, 0), 3)

    def test_aucun_mot_sans_son_accent_chez_l_acheteur(self):
        for cle, trouves in self.trouves.items():
            with self.subTest(type=cle):
                self.assertEqual(trouves, [])

    def test_aucun_pluriel_de_formulaire_chez_l_acheteur(self):
        for cle, trouves in self.formulaires.items():
            with self.subTest(type=cle):
                self.assertEqual(trouves, [])


class CeQueLaConsoleAffiche(unittest.TestCase):
    """Ce que les commandes affichent VRAIMENT, relu ligne a ligne.

    Le test des messages ci-dessus lit huit noms de fonctions dans le code.
    Il ne voyait ni « print », ni l'aide des options, ni les lignes que le
    docteur compose en morceaux. Une vraie fabrication du 27/09/2026 a donc
    affiche « sans cle », « la notice livree », « 0 livre(s), 0 echec(s) »,
    « Reseau : disponible », et l'aide entiere de la ligne de commande sans
    un accent — alors que ce test-la passait.

    Ce qu'on tape reste tel quel : les commandes (« usine cles »), les
    options (« --qualite ») et les listes de valeurs (« {rapide,exigeant} »)
    sont retirees de la ligne avant la lecture.
    """

    # L'aide d'argparse aligne le nom de chaque commande en tete de ligne
    # (« cles    obtenir des clés ») ; les reglages montrent la cle a taper
    # entre parentheses, et les exemples l'ecrivent « qualite=exigeant ».
    TAPE = re.compile(r"«\s*usine[^»]*»|\busine(?:\s+[a-z][\w-]*)+|--?[a-z][\w-]*"
                      r"|\{[^{}]*\}|https?://\S+|[\w./-]+\.(?:json|md|csv|py|txt|env)\b"
                      r"|[A-Z][A-Z0-9_]{3,}|^\s{2,}[a-z][\w-]*(?=\s{2,})"
                      r"|\([a-z_]+\)|\b\w+=\S*")

    @classmethod
    def setUpClass(cls):
        from tests.simulateur import simulateur
        from usine.core import llm

        atelier.isoler("accents-console")
        llm.definir_simulateur(simulateur)
        cls.sorties = {}
        parseur = cli.construire_parseur()
        sous = [a for a in parseur._actions if getattr(a, "choices", None)][0]
        commandes = [["memo", "le compost", "-n", "4", "--sans-image"],
                     ["docteur"], ["cles"], ["liste"], ["reglages"],
                     ["usine", "statut"], ["file"], ["bilan"], ["specs"],
                     ["--help"]]
        # L'aide de chaque commande : c'est la que l'on apprend les options.
        commandes += [[nom, "--help"] for nom in sorted(sous.choices)]
        from usine.core import diagnostic

        vrai = diagnostic.etat_installation

        def sans_reseau(**_options):
            # Le docteur sonde Pollinations et les IA locales : dans un test,
            # ces deux controles sortiraient sur le reseau.
            return vrai(avec_reseau=False, avec_locaux=False)

        try:
            with mock.patch.object(diagnostic, "etat_installation", sans_reseau):
                for argv in commandes:
                    sortie = io.StringIO()
                    with redirect_stdout(sortie), redirect_stderr(sortie):
                        try:
                            cli.principal(argv)
                        except SystemExit:
                            pass
                    cls.sorties[" ".join(argv)] = sortie.getvalue()
        finally:
            llm.definir_simulateur(None)

    def test_le_test_a_lu_quelque_chose(self):
        self.assertGreater(len(self.sorties), 20)
        self.assertIn("Fournisseurs", self.sorties["docteur"])

    def test_pas_de_titre_de_section_sans_rien_dessous(self):
        """« == Kit de vente » s'affichait des qu'on ne passait pas
        « --sans-marketing », meme quand le reglage ne demandait aucun kit :
        un titre, puis rien (vraie fabrication du 27/09/2026)."""
        self.assertFalse(reglages.lire("marketing_auto", False))
        self.assertNotIn("Kit de vente",
                         self.sorties["memo le compost -n 4 --sans-image"])

    def test_aucun_mot_sans_son_accent_a_l_ecran(self):
        trouves = []
        for commande, texte in self.sorties.items():
            for ligne in texte.splitlines():
                for mot in fautes(self.TAPE.sub(" ", ligne)):
                    trouves.append("{} : {} — {}".format(commande, mot,
                                                          ligne.strip()[:80]))
        self.assertEqual(trouves, [], "\n".join(trouves[:60]))


class LesPlurielsSAccordent(unittest.TestCase):
    """« 29 repère(s) en 6 bloc(s) » : la notation d'un formulaire, sur la
    couverture d'un produit. Voir « libelles.accorder »."""

    def test_chaque_s_suit_le_nombre_qui_le_precede(self):
        self.assertEqual(libelles.accorder("29 repère(s) en 1 bloc(s)"),
                         "29 repères en 1 bloc")
        self.assertEqual(libelles.accorder("1 double(s)-page(s)"), "1 double-page")
        self.assertEqual(libelles.accorder("un message tous les 3 jour(s)"),
                         "un message tous les 3 jours")

    def test_zero_au_singulier_en_francais_au_pluriel_en_anglais(self):
        self.assertEqual(libelles.accorder("0 question(s)", "fr"), "0 question")
        self.assertEqual(libelles.accorder("0 question(s)", "en"), "0 questions")
        self.assertEqual(libelles.accorder("1 question(s)", "en"), "1 question")

    def test_sans_nombre_la_notation_reste(self):
        """Mieux vaut la notation qu'un accord invente."""
        self.assertEqual(libelles.accorder("section(s)"), "section(s)")

    def test_la_page_du_quiz_accorde_son_score(self):
        import shutil
        import subprocess

        from usine.render import quiz

        if not shutil.which("node"):
            self.skipTest("node absent : le script ne peut pas etre execute")
        debut = quiz.SCRIPT.index("function accorder")
        fin = quiz.SCRIPT.index("function corriger")
        programme = (
            "var textes = {zero_pluriel: false};\n" + quiz.SCRIPT[debut:fin]
            + "console.log([accorder(' bonne(s) réponse(s) sur ', 1),"
              " accorder(' bonne(s) réponse(s) sur ', 3),"
              " accorder(' bonne(s) réponse(s) sur ', 0)].join('|'));")
        sortie = subprocess.run(["node", "-e", programme], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(sortie.stdout.rstrip("\n"),
                         " bonne réponse sur | bonnes réponses sur | bonne réponse sur ",
                         sortie.stderr)


if __name__ == "__main__":
    unittest.main()
