"""Le texte fixe d'un produit est dans la langue du produit.

Mesure du 24/09/2026, langue reglee sur « anglais », dix-sept types fabriques
avec un simulateur dont chaque mot est remplace par « zz… » : tout mot qui
reste dans les fichiers livres a donc ete ecrit par l'usine elle-meme. Les
dix-sept livraient un contenu anglais habille en francais — licence,
LISEZ-MOI, page de copyright, sommaire, « Chapitre », « Precedemment »,
« rendez-vous au », jusqu'aux colonnes du tableur et au script du quiz.

Rien n'echouait : le modele ecrivait bien en anglais, les fichiers etaient
bien la, et chaque test lisait des chaines francaises parce que c'est la
langue par defaut. Le defaut n'existait que dans la langue que personne ne
testait.

Ce module fabrique donc le catalogue ENTIER — tire de « catalogue.tous », pas
d'une liste recopiee — en anglais, et lit chaque fichier que l'acheteur
recoit. Il est volontairement grossier : il cherche des mots francais qui ne
sont pas aussi des mots anglais, des lettres accentuees, l'espace avant les
deux-points et les guillemets francais. Un libelle oublie tombe presque
toujours sur l'un des quatre.
"""

from __future__ import annotations

import itertools
import json
import re
import string
import sys
import unittest
import zipfile
import zlib
from pathlib import Path
from string import Formatter
from typing import Dict, Iterator, List, Tuple

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, reglages, store  # noqa: E402
from usine.core import serie as module_serie  # noqa: E402
from usine.core import verification  # noqa: E402
from usine.pipelines import (catalogue, emails, impression,  # noqa: E402
                             logiciel, nouvelle, porte, quiz)
from usine.pipelines.base import Contexte  # noqa: E402
from usine.packaging import livraison as empaquetage  # noqa: E402
from usine.render import libelles  # noqa: E402


def setUpModule():
    atelier.isoler("langue-livree")


# --------------------------------------------------------------------------
# Un modele qui n'ecrit aucune langue
# --------------------------------------------------------------------------

_MOT = re.compile(r"[^\W\d_]{2,}", re.U)
# Les valeurs que les chaines lisent comme des enumerations : les neutraliser
# ferait ecarter la reponse, et le type ne serait plus fabrique du tout.
_GARDE = {"type", "fin", "issue", "vers", "numero", "choix", "format", "genre",
          "categorie", "niveau", "reseau", "reponse", "index", "lettre", "canal",
          "jour", "disposition"}


def _neutre_texte(texte: str, compteur: Iterator[int]) -> str:
    """Chaque mot devient « zz » suivi d'un suffixe UNIQUE.

    Unique, parce qu'un quiz dont les quatre propositions valent « zz » est
    ecarte comme insoluble — et le type sortirait du test sans le dire. Les
    guillemets et l'espace avant la ponctuation du simulateur, qui ecrit en
    francais, sont retires aussi : ce qui en reste vient de l'usine.
    """
    def suffixe(_m):
        n, lettres = next(compteur), ""
        while True:
            n, reste = divmod(n, 26)
            lettres += string.ascii_lowercase[reste]
            if not n:
                return "zz" + lettres
    texte = _MOT.sub(suffixe, texte)
    texte = re.sub(r"[   ]+([:;!?»])", r"\1", texte)
    return texte.replace("«", '"').replace("»", '"')


def simulateur_neutre():
    compteur = itertools.count()

    def neutre(valeur, cle=""):
        if isinstance(valeur, dict):
            return {k: (v if k in _GARDE else neutre(v, k))
                    for k, v in valeur.items()}
        if isinstance(valeur, list):
            return [neutre(v, cle) for v in valeur]
        if isinstance(valeur, str):
            return _neutre_texte(valeur, compteur)
        return valeur

    def repondre(messages, role):
        rendu = simulateur(messages, role)
        try:
            return json.dumps(neutre(json.loads(rendu)), ensure_ascii=False)
        except ValueError:
            return neutre(rendu)

    return repondre


# --------------------------------------------------------------------------
# Ce qui trahit un mobilier francais
# --------------------------------------------------------------------------

# Des mots francais qui ne sont PAS des mots anglais. « page », « question »,
# « illustration », « module » ou « suite » s'ecrivent pareil dans les deux
# langues : les compter ferait crier le test a tort sur un produit juste.
MOTS_FRANCAIS = frozenset("""
    les des une est pour vous votre vos avec sans dans qui que cette ces aux
    sont leur leurs tous toutes elle nous mais donc chaque
    chapitre chapitres sommaire precedemment reponse reponses corrige bareme
    consignes prerequis cahier exercices droits reserves objectif livrable
    astuce ouvrage elabore etape etapes jour jours fiche fiches modele
    modeles recit nouvelles lecteur lecture suivre rendez allez tournez
    lisez utilisation avertissement edite premiere mois unitaires erreur
    syntaxe appelle importe acces systeme reseau dossier travail fichier
    fichiers analyse statique execute verifie resultat
    debutant intermediaire avance texte nombre selection cocher formule suivi
    matrice bienvenue vente fidelisation relance liste tableau reperes arbre
    syntaxique controle structurel indisponible lancement manuel extrait
""".split())
_ACCENTS = re.compile(r"[éèêëàâùûüçôîïœÉÈÊÀÇ]")

# Ce qui s'adresse au VENDEUR reste en francais, par decision : c'est la
# langue de celui qui fabrique. Voir « render/libelles.py ».
FICHIERS_DU_VENDEUR = {"fiche-produit.md", "sequence-lancement.md"}
_LISIBLES = (".md", ".txt", ".html", ".csv", ".xhtml")


def _texte_visible(nom: str, brut: str) -> str:
    if nom.endswith((".html", ".xhtml")):
        brut = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", brut)
        # Les balises de mise en forme disparaissent sans espace : sinon
        # « <strong>Tip</strong>: » devient « Tip : » et le test accuse une
        # typographie que le lecteur ne voit pas.
        brut = re.sub(r"</?(strong|em|b|i|a|span|code|small)\b[^>]*>", "", brut)
        brut = re.sub(r"<[^>]+>", " ", brut)
        brut = (brut.replace("&nbsp;", " ").replace("&#160;", " ")
                .replace("&laquo;", "«").replace("&raquo;", "»"))
    # Les noms de fichiers cites entre accents graves : « lire.html » ou
    # « nouvelle.md » sont des noms, pas du texte, et ils ne changent pas.
    # Seulement les NOMS : « `tests unitaires` » passait par la et sortait
    # tel quel dans la notice anglaise d'un outil.
    return re.sub(r"`[^`\s]*[./][^`\s]*`", " ", brut)


def residus(nom: str, brut: str) -> List[str]:
    """Les lignes d'un fichier qui portent du francais ecrit par l'usine."""
    trouves = []
    for ligne in _texte_visible(nom, brut).splitlines():
        mots = {m.lower() for m in _MOT.findall(ligne)}
        raisons = sorted(mots & MOTS_FRANCAIS)
        if _ACCENTS.search(ligne):
            raisons.append("accent")
        if re.search(r"\w[   ]+[:;!?](\s|$)", ligne):
            raisons.append("espace avant la ponctuation")
        if "«" in ligne or "»" in ligne:
            raisons.append("guillemets francais")
        if raisons:
            trouves.append("{} : {} — {}".format(
                nom, re.sub(r"\s+", " ", ligne.strip())[:90], ", ".join(raisons)))
    return trouves


def texte_pdf(chemin: Path) -> str:
    """Les chaines de texte d'un PDF de l'usine, flux par flux.

    Plusieurs blocs n'existent QUE dans le PDF — consignes et bareme du quiz,
    fiches imprimables, cahier d'exercices : les lire en markdown ne dit rien
    d'eux. Les flux d'image sont sautes : chercher des chaines dans les
    octets d'une couverture est long et ne trouve que du bruit.
    """
    brut = chemin.read_bytes()
    morceaux = []
    for bloc in re.finditer(rb"stream\r?\n(.*?)endstream", brut, re.S):
        if b"/Image" in brut[max(0, bloc.start() - 400):bloc.start()]:
            continue
        flux = bloc.group(1)
        try:
            flux = zlib.decompress(flux)
        except zlib.error:
            pass
        morceaux += [m.decode("latin-1") for m in
                     re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", flux)]
    return "\n".join(morceaux)


def fichiers_livres(dossier: Path) -> Iterator[Tuple[str, str]]:
    """Tout ce que l'acheteur peut ouvrir : le dossier, le PDF, l'EPUB,
    l'archive."""
    for chemin in sorted(dossier.rglob("*")):
        if not chemin.is_file() or chemin.name in FICHIERS_DU_VENDEUR:
            continue
        if chemin.suffix in _LISIBLES:
            yield chemin.name, chemin.read_text(encoding="utf-8", errors="replace")
        elif chemin.suffix == ".pdf":
            yield chemin.name, texte_pdf(chemin)
        elif chemin.suffix == ".epub":
            with zipfile.ZipFile(chemin) as epub:
                for membre in epub.namelist():
                    if membre.endswith(".xhtml"):
                        yield ("{}:{}".format(chemin.name, membre.rsplit("/", 1)[-1]),
                               epub.read(membre).decode("utf-8", "replace"))
    for archive in sorted(dossier.parent.glob("*.zip")):
        with zipfile.ZipFile(archive) as contenu:
            for membre in contenu.namelist():
                nom = membre.rsplit("/", 1)[-1]
                if nom.endswith((".md", ".txt")) and nom not in FICHIERS_DU_VENDEUR:
                    yield ("{}:{}".format(archive.name, nom),
                           contenu.read(membre).decode("utf-8", "replace"))


def _fabriquer(cle: str, sujet: str) -> Tuple[Contexte, List[str]]:
    dits: List[str] = []
    store.cache_vider()
    ctx = porte.contexte(sujet, {}, dits.append)
    porte.fabriquer(cle, ctx, {}, dits.append)
    return ctx, dits


# --------------------------------------------------------------------------
# Les deux tables
# --------------------------------------------------------------------------


def _champs(gabarit: str) -> set:
    return {nom for _, nom, _, _ in Formatter().parse(gabarit) if nom is not None}


class LesDeuxLanguesDisentLaMemeChose(unittest.TestCase):
    """Une cle absente d'une langue leve une KeyError a la livraison — dans
    la langue que personne ne teste. Un champ oublie d'un cote imprime
    « {titre} » tel quel chez l'acheteur, ou leve a la mise en forme."""

    def test_les_memes_cles(self):
        self.assertEqual(sorted(libelles.FR), sorted(libelles.EN))

    def test_les_memes_champs_a_remplir(self):
        for cle, francais in libelles.FR.items():
            anglais = libelles.EN[cle]
            with self.subTest(cle=cle):
                self.assertIs(type(francais), type(anglais))
                if isinstance(francais, str):
                    self.assertEqual(_champs(francais), _champs(anglais))
                elif isinstance(francais, tuple):
                    self.assertEqual(len(francais), len(anglais))
                elif isinstance(francais, dict) and francais:
                    # Un dictionnaire rempli des deux cotes est une table de
                    # textes (le script du quiz) : memes cles. Vide en
                    # francais, c'est une table d'affichage — l'identite.
                    self.assertEqual(sorted(francais), sorted(anglais))

    def test_les_tables_d_affichage_couvrent_leurs_valeurs(self):
        """Une valeur ajoutee a l'enumeration sans entree ici s'afficherait
        en francais dans un produit anglais, sans rien casser."""
        enumerations = {
            "quiz_niveaux": quiz.NIVEAUX,
            "impression_dispositions": impression.DISPOSITIONS,
            "emails_objectifs": emails.OBJECTIFS,
            "memo_genres": ("liste", "etapes", "tableau", "reperes"),
        }
        for cle, valeurs in enumerations.items():
            with self.subTest(cle=cle):
                self.assertEqual(libelles.FR[cle], {},
                                 "le francais affiche la valeur telle quelle")
                self.assertEqual(sorted(libelles.EN[cle]), sorted(valeurs))

    def test_chaque_libelle_est_lu(self):
        """Un libelle que rien ne lit est du texte mort, qu'on traduira et
        tiendra a jour pour personne.

        Lu dans l'arbre syntaxique, pas cherche comme un mot : « sommaire »
        ou « licence » apparaissent partout dans le code, et une recherche
        textuelle serait satisfaite par n'importe quelle homonymie. Compte
        comme lecture : « t["cle"] », « libelles.FR["cle"] »,
        « libelles.textes(...)["cle"] » et « libelle(code, "cle") »."""
        import ast

        def est_une_table(noeud) -> bool:
            if isinstance(noeud, ast.Name):
                return noeud.id == "t"
            if isinstance(noeud, ast.Attribute):
                return (noeud.attr in ("FR", "EN")
                        and isinstance(noeud.value, ast.Name)
                        and noeud.value.id == "libelles")
            return (isinstance(noeud, ast.Call)
                    and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr == "textes")

        lus = set()
        for fichier in (RACINE / "usine").rglob("*.py"):
            if fichier.name == "libelles.py":
                continue
            for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
                if isinstance(noeud, ast.Subscript) and est_une_table(noeud.value):
                    cle = noeud.slice
                    # Python 3.8 enveloppe l'indice dans « ast.Index ».
                    cle = getattr(cle, "value", cle) if not isinstance(
                        cle, ast.Constant) else cle
                    if isinstance(cle, ast.Constant):
                        lus.add(cle.value)
                elif isinstance(noeud, ast.Call):
                    fonction = noeud.func
                    nom = (fonction.attr if isinstance(fonction, ast.Attribute)
                           else getattr(fonction, "id", ""))
                    if (nom == "libelle" and len(noeud.args) >= 2
                            and isinstance(noeud.args[1], ast.Constant)):
                        lus.add(noeud.args[1].value)
        self.assertEqual(sorted(set(libelles.FR) - lus), [])

    def test_une_langue_non_tenue_recoit_l_anglais(self):
        for code in ("es", "de", "it", "pt", "nl"):
            with self.subTest(code=code):
                self.assertIs(libelles.textes(code), libelles.EN)
        self.assertIs(libelles.textes("fr"), libelles.FR)


# --------------------------------------------------------------------------
# Le catalogue entier, en anglais
# --------------------------------------------------------------------------


class LeCatalogueEntierEnAnglais(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        atelier.isoler("langue-livree-catalogue")
        reglages.ecrire(dict(images=False, qualite="rapide", langue="anglais",
                             auteur="Zz", archive_auto=True,
                             marketing_auto=True))
        llm.definir_simulateur(simulateur_neutre())
        cls.types = [f.cle for f in catalogue.tous(fabricables=True)
                     # « idees » ne livre rien a un acheteur : c'est une liste
                     # de niches pour le vendeur.
                     if f.cle != "idees"]
        cls.trouves: Dict[str, List[str]] = {}
        cls.lus: Dict[str, int] = {}
        cls.journaux: Dict[str, List[str]] = {}
        cls.archives: Dict[str, List[str]] = {}
        cls.extraits: Dict[str, List[str]] = {}
        try:
            for rang, cle in enumerate(cls.types):
                ctx, dits = _fabriquer(cle, "zz zz {}".format(rang))
                cls.journaux[cle] = dits
                lus = list(fichiers_livres(ctx.dossier))
                cls.lus[cle] = len(lus)
                cls.trouves[cle] = [r for nom, brut in lus
                                    for r in residus(nom, brut)]
                cls.archives[cle] = [
                    nom.rsplit("/", 1)[-1]
                    for archive in ctx.dossier.parent.glob("*.zip")
                    for nom in zipfile.ZipFile(archive).namelist()]
                # L'extrait gratuit n'entre pas dans l'archive — le kit de
                # vente reste a l'atelier — mais c'est l'acheteur qui l'ouvre.
                cls.extraits[cle] = [
                    f.name for f in (ctx.dossier / "marketing" / "extrait").rglob("*")
                    if f.is_file()]
                for archive in ctx.dossier.parent.glob("*.zip"):
                    archive.unlink()
        finally:
            llm.definir_simulateur(None)

    def test_chaque_type_a_ete_lu(self):
        """Le test ne vaut que s'il a lu quelque chose : un type qui ne
        livrerait plus rien passerait « sans residu »."""
        for cle in self.types:
            with self.subTest(type=cle):
                self.assertGreaterEqual(self.lus.get(cle, 0), 3)

    def test_aucun_texte_fixe_francais_chez_l_acheteur(self):
        for cle in self.types:
            with self.subTest(type=cle):
                self.assertEqual(self.trouves.get(cle), [],
                                 "\n".join(self.trouves.get(cle) or []))

    def test_l_archive_porte_une_notice_et_une_licence_anglaises(self):
        for cle in self.types:
            with self.subTest(type=cle):
                noms = self.archives.get(cle) or []
                self.assertIn("README.md", noms)
                self.assertIn("LICENSE.txt", noms)
                self.assertNotIn("LISEZ-MOI.md", noms)
                self.assertNotIn("LICENCE.txt", noms)

    def test_les_noms_ajoutes_au_titre_sont_anglais(self):
        """« -cahier-exercices.pdf », « -manuel.pdf », « tableau-03-… » : les
        noms que l'usine compose autour du titre suivent la langue.

        Les noms FIXES d'un type — « livre.md », « nouvelle.md », « lire.html »
        — ne changent pas, par decision : l'usine les relit (reprise, extrait,
        rafraichissement de serie) et la notice les cite. Ils sont tires ici
        du code qui les nomme, pas recopies."""
        from usine.render.livraison import _nom_markdown

        fixes = {"lire"} | {mot for cle in self.types
                            for mot in re.split(r"[-_]", _nom_markdown(cle))}
        for cle in self.types:
            with self.subTest(type=cle):
                noms = (self.archives.get(cle) or []) + self.extraits.get(cle, [])
                mots = {mot.lower() for nom in noms
                        for mot in re.split(r"[-_.]", nom)
                        if mot and not mot.lower().startswith("zz")}
                self.assertEqual(sorted((mots - fixes) & MOTS_FRANCAIS), [])

    def test_l_anglais_ne_declenche_pas_d_avertissement(self):
        for cle in self.types:
            with self.subTest(type=cle):
                self.assertFalse([d for d in self.journaux[cle]
                                  if "texte fixe" in d])


# --------------------------------------------------------------------------
# Le diagnostic d'un outil logiciel
# --------------------------------------------------------------------------


class LeRefusDExecuterSeDitDansLaLangue(unittest.TestCase):
    """La notice d'un outil dit pourquoi un script n'a pas ete lance. Le
    motif venait de la verification, en francais : « non execute : static
    analysis: erreur de syntaxe : invalid syntax » dans un produit anglais.

    Un script par motif de refus. Un motif ajoute a la verification sans
    entree dans « logiciel_soucis » sortirait en francais : ce test le voit,
    parce qu'il exige que CHAQUE refus porte un motif connu."""

    SCRIPTS = {
        "syntaxe": "def f(:\n    pass\n",
        "import": "import socket\n",
        "appel": "eval('1')\n",
        "ecriture": "open('/tmp/x', 'w').write('x')\n",
    }

    def _essai(self, code: str):
        import tempfile

        with tempfile.TemporaryDirectory() as bac:
            chemin = Path(bac) / "outil.py"
            chemin.write_text(code, encoding="utf-8")
            rapport = verification.analyser_python(code, "outil.py")
            execution = verification.executer_python(chemin, ["--help"], rapport)
        return {"quoi": "outil.py --help", "refus": execution.refus,
                "motif": execution.motif, "valeur": execution.valeur}

    def test_chaque_motif_se_traduit(self):
        anglais = libelles.textes("en")
        for motif, code in self.SCRIPTS.items():
            with self.subTest(motif=motif):
                essai = self._essai(code)
                self.assertTrue(essai["refus"], "le script devait etre refuse")
                self.assertEqual(essai["motif"], motif)
                lisible = logiciel._refus_lisible(essai, anglais)
                self.assertEqual(residus("notice.md", lisible), [], lisible)

    def test_le_francais_ne_change_pas(self):
        francais = libelles.textes("fr")
        for code in self.SCRIPTS.values():
            essai = self._essai(code)
            with self.subTest(refus=essai["refus"]):
                self.assertEqual(logiciel._refus_lisible(essai, francais),
                                 essai["refus"])


# --------------------------------------------------------------------------
# L'archive
# --------------------------------------------------------------------------


class LArchiveNeLivreQuUneNotice(unittest.TestCase):
    """Le nom de la notice suit la langue. Deux cas que le catalogue ne voit
    pas, parce qu'il fabrique des dossiers neufs."""

    def _dossier(self, nom: str) -> Path:
        from usine.core import config

        dossier = config.PRODUITS_DIR / nom
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "livre.md").write_text("# Zz\n", encoding="utf-8")
        return dossier

    def _contenu(self, archive: Path) -> List[str]:
        with zipfile.ZipFile(archive) as contenu:
            return [n.rsplit("/", 1)[-1] for n in contenu.namelist()]

    def test_une_ancienne_notice_francaise_ne_part_pas(self):
        """Un produit anglais empaquete avant que le nom suive la langue
        garde un « LISEZ-MOI.md » dans son dossier. L'acheteur recevrait deux
        modes d'emploi, dont un perime."""
        # Les deux modes : la liste que la chaine a declaree, et le filet des
        # appels qui ne l'ont pas — c'est dans ce second mode que l'ancienne
        # notice passait, rien ne l'ecartant.
        for livres in (["livre.md"], None):
            with self.subTest(livres=livres):
                dossier = self._dossier("ancienne-notice")
                (dossier / "LISEZ-MOI.md").write_text("perime", encoding="utf-8")
                (dossier / "LICENCE.txt").write_text("perime", encoding="utf-8")
                archive = empaquetage.empaqueter(
                    dossier, "ancienne-notice", "Zz", "Zz", livres=livres,
                    langue="en")
                noms = self._contenu(archive)
                self.assertIn("livre.md", noms)
                self.assertIn("README.md", noms)
                self.assertIn("LICENSE.txt", noms)
                self.assertNotIn("LISEZ-MOI.md", noms)
                self.assertNotIn("LICENCE.txt", noms)

    def test_la_notice_ne_se_cite_pas_elle_meme(self):
        """Au second empaquetage, la notice et la licence du premier sont
        dans le dossier : la liste des fichiers ne doit pas les annoncer."""
        dossier = self._dossier("deux-fois")
        for _ in range(2):
            empaquetage.empaqueter(dossier, "deux-fois", "Zz", "Zz",
                                   livres=["livre.md"], langue="en")
        notice = (dossier / "README.md").read_text(encoding="utf-8")
        self.assertIn("`livre.md`", notice)
        self.assertNotIn("`README.md`", notice)
        self.assertNotIn("`LICENSE.txt`", notice)


# --------------------------------------------------------------------------
# Les autres langues du reglage
# --------------------------------------------------------------------------


class UneLangueSansMobilier(unittest.TestCase):
    """Espagnol, allemand, italien, portugais, neerlandais : le modele ecrit
    dans la langue, le mobilier est anglais — et la fabrication le dit, parce
    qu'un livre espagnol au mobilier anglais ne se voit qu'en ouvrant le
    fichier livre."""

    @classmethod
    def setUpClass(cls):
        atelier.isoler("langue-livree-espagnol")
        reglages.ecrire(dict(images=False, qualite="rapide", langue="espagnol",
                             auteur="Zz", archive_auto=True))
        llm.definir_simulateur(simulateur_neutre())
        try:
            cls.ctx, cls.dits = _fabriquer("memo", "zz zz espagnol")
        finally:
            llm.definir_simulateur(None)

    def test_la_fabrication_le_dit(self):
        dits = [d for d in self.dits if "texte fixe" in d]
        self.assertEqual(len(dits), 1, self.dits)
        self.assertIn("espagnol", dits[0])
        self.assertIn("anglais", dits[0])

    def test_le_mobilier_est_anglais(self):
        lus = list(fichiers_livres(self.ctx.dossier))
        self.assertGreaterEqual(len(lus), 3)
        self.assertEqual([r for nom, brut in lus for r in residus(nom, brut)], [])
        licence = (self.ctx.dossier / "LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("All rights reserved", licence)

    def test_une_langue_inconnue_est_dite_aussi(self):
        from usine.pipelines.base import avertir_habillage

        dits: List[str] = []
        avertir_habillage(Contexte(sujet="x", langue="japonais",
                                   journal=dits.append))
        self.assertEqual(len(dits), 1)
        self.assertIn("inconnue", dits[0])


# --------------------------------------------------------------------------
# La page de fin d'un tome de serie
# --------------------------------------------------------------------------


class LaSerieGardeSaLangue(unittest.TestCase):
    """La page « La suite » est refaite des mois apres la fabrication, par
    « usine serie rafraichir ». Le contexte de ce rafraichissement etait
    construit sans langue : un tome anglais repartait en francais."""

    @classmethod
    def setUpClass(cls):
        atelier.isoler("langue-livree-serie")
        llm.definir_simulateur(simulateur)
        try:
            with store.cursor() as cur:
                cur.execute("DELETE FROM series")
            cls.t1 = nouvelle.produire(
                Contexte(sujet="the depot that closes", langue="anglais",
                         sans_image=True, hors_ligne=True, qualite="rapide",
                         journal=lambda _m: None), serie="Rails")
            cls.t2 = nouvelle.produire(
                Contexte(sujet="ten years later", langue="anglais",
                         sans_image=True, hors_ligne=True, qualite="rapide",
                         journal=lambda _m: None), serie="Rails")
        finally:
            llm.definir_simulateur(None)
        cls.fin_fr = libelles.libelle("fr", "serie_page")
        cls.fin_en = libelles.libelle("en", "serie_page")

    def _markdown(self, resume) -> str:
        from usine.marketing.extrait import _markdown_du_produit

        return _markdown_du_produit(Path(resume["dossier"]),
                                    "nouvelle").read_text(encoding="utf-8")

    def test_la_page_de_fin_est_dans_la_langue_du_tome(self):
        page = module_serie.page_de_suite("Rails", 2, "en")
        self.assertIn("volume 2", page)
        self.assertNotIn("tome", page.lower())
        self.assertIn("\n# " + self.fin_en, self._markdown(self.t2))

    def test_le_rafraichissement_garde_l_anglais(self):
        nouvelle.rafraichir_serie("Rails", journal=lambda _m: None)
        markdown = self._markdown(self.t1)
        self.assertEqual(markdown.count("\n# " + self.fin_en), 1)
        self.assertNotIn("\n# " + self.fin_fr, markdown)
        epub = next(Path(self.t1["dossier"]).glob("*.epub"))
        with zipfile.ZipFile(epub) as contenu:
            droits = [contenu.read(n).decode("utf-8") for n in contenu.namelist()
                      if n.endswith("droits.xhtml")]
        self.assertTrue(droits)
        self.assertIn("All rights reserved", droits[0])

    def test_une_ancienne_page_francaise_est_remplacee_pas_empilee(self):
        """Un tome anglais fabrique avant ce changement finit sur « La
        suite ». Ne chercher que le titre anglais la laisserait en double."""
        from usine.marketing.extrait import _markdown_du_produit

        source = _markdown_du_produit(Path(self.t1["dossier"]), "nouvelle")
        texte = self._markdown(self.t1).split("\n# " + self.fin_en)[0]
        source.write_text(texte.rstrip() + "\n\n# " + self.fin_fr
                          + "\n\nAncienne page.\n", encoding="utf-8")
        nouvelle.rafraichir_serie("Rails", journal=lambda _m: None)
        markdown = self._markdown(self.t1)
        self.assertNotIn("Ancienne page.", markdown)
        self.assertEqual(markdown.count("\n# " + self.fin_en), 1)

    def test_une_scene_intitulee_comme_la_page_n_est_pas_retiree(self):
        """Seule la DERNIERE section est la page de fin : une scene que le
        modele aurait intitulee ainsi fait partie du recit."""
        from usine.marketing.extrait import _markdown_du_produit

        source = _markdown_du_produit(Path(self.t1["dossier"]), "nouvelle")
        entete, _, reste = self._markdown(self.t1).partition("\n# ")
        source.write_text(entete + "\n# " + self.fin_en
                          + "\n\nUne scene du recit.\n\n# " + reste,
                          encoding="utf-8")
        nouvelle.rafraichir_serie("Rails", journal=lambda _m: None)
        self.assertIn("Une scene du recit.", self._markdown(self.t1))


if __name__ == "__main__":
    unittest.main()
