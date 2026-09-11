"""Verification du code genere, avant toute livraison.

Livrer un script qui ne demarre pas est pire que ne rien livrer : l'acheteur
demande un remboursement et n'y revient pas. Un modele produit du code
plausible, pas du code correct — la difference se mesure, elle ne se suppose
pas.

Deux niveaux, dans cet ordre :

  1. ANALYSE STATIQUE, toujours. La syntaxe doit passer, et le contenu est
     inspecte a la recherche de constructions dangereuses.
  2. EXECUTION, seulement si l'analyse est propre et si l'appelant la demande.
     Dans un dossier temporaire, avec une limite de temps.

Le second point merite d'etre explicite : ce code vient d'un modele de langage,
pas de vous. Un `os.system("rm -rf ~")` genere par accident dans un exemple
d'illustration effacerait le telephone. L'execution n'a donc lieu que sur du
code dont l'arbre syntaxique ne contient aucun appel systeme, aucun acces
reseau et aucune ecriture hors du dossier de travail.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Ce qui interdit l'execution
# --------------------------------------------------------------------------

# Modules dont la seule presence suspend l'execution automatique.
MODULES_SENSIBLES = {
    "subprocess", "socket", "ctypes", "multiprocessing", "shutil",
    "requests", "urllib", "http", "ftplib", "smtplib", "telnetlib",
    "pty", "pickle", "marshal", "importlib",
}

# Fonctions integrees a ne jamais executer sans relecture humaine.
INTEGREES_INTERDITES = {"eval", "exec", "compile", "__import__", "breakpoint"}

# Appels du module os qui touchent au systeme de fichiers ou aux processus.
OS_INTERDITS = {
    "system", "popen", "remove", "unlink", "rmdir", "removedirs", "rename",
    "replace", "execv", "execve", "execl", "execlp", "spawnv", "fork", "kill",
    "chmod", "chown", "truncate",
}


@dataclass
class Souci:
    gravite: str          # casse | dangereux | avertissement
    message: str
    ligne: int = 0
    extrait: str = ""


@dataclass
class Rapport:
    fichier: str
    langage: str
    valide: bool = True
    soucis: List[Souci] = field(default_factory=list)
    executable: bool = True        # sur du plan de la surete, pas du succes
    verifie_par: str = ""          # ce qui a reellement ete controle

    @property
    def casse(self) -> List[Souci]:
        return [s for s in self.soucis if s.gravite == "casse"]

    @property
    def dangers(self) -> List[Souci]:
        return [s for s in self.soucis if s.gravite == "dangereux"]

    def resume(self) -> str:
        if self.casse:
            return "{} : NE COMPILE PAS — {}".format(
                self.fichier, self.casse[0].message)
        if self.dangers:
            return "{} : syntaxe correcte, {} construction(s) a relire".format(
                self.fichier, len(self.dangers))
        if self.soucis:
            return "{} : correct, {} remarque(s)".format(
                self.fichier, len(self.soucis))
        return "{} : correct ({})".format(self.fichier, self.verifie_par)

    def instructions_correction(self) -> str:
        """Message a renvoyer au modele pour qu'il corrige."""
        lignes = []
        for souci in self.casse + self.dangers:
            emplacement = " (ligne {})".format(souci.ligne) if souci.ligne else ""
            lignes.append("- {}{} : {}".format(
                souci.gravite.upper(), emplacement, souci.message))
            if souci.extrait:
                lignes.append("  " + souci.extrait[:120])
        return "\n".join(lignes)


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------


def analyser_python(code: str, nom: str = "script.py") -> Rapport:
    """Syntaxe, puis inspection de l'arbre a la recherche de dangers."""
    rapport = Rapport(fichier=nom, langage="python",
                      verifie_par="syntaxe + arbre syntaxique")
    try:
        arbre = ast.parse(code, filename=nom)
    except SyntaxError as exc:
        rapport.valide = False
        rapport.executable = False
        rapport.soucis.append(Souci(
            "casse", "erreur de syntaxe : {}".format(exc.msg),
            ligne=exc.lineno or 0, extrait=(exc.text or "").strip()))
        return rapport

    for noeud in ast.walk(arbre):
        ligne = getattr(noeud, "lineno", 0)

        if isinstance(noeud, (ast.Import, ast.ImportFrom)):
            noms = ([a.name for a in noeud.names] if isinstance(noeud, ast.Import)
                    else [noeud.module or ""])
            for nom_module in noms:
                racine = (nom_module or "").split(".")[0]
                if racine in MODULES_SENSIBLES:
                    rapport.soucis.append(Souci(
                        "dangereux",
                        "importe « {} » : acces systeme ou reseau".format(racine),
                        ligne=ligne))

        if isinstance(noeud, ast.Call):
            cible = _nom_appel(noeud.func)
            if cible in INTEGREES_INTERDITES:
                rapport.soucis.append(Souci(
                    "dangereux", "appelle « {}() »".format(cible), ligne=ligne))
            elif cible.startswith("os.") and cible.split(".", 1)[1] in OS_INTERDITS:
                rapport.soucis.append(Souci(
                    "dangereux", "appelle « {}() »".format(cible), ligne=ligne))
            elif cible == "open":
                mode = _mode_ouverture(noeud)
                if mode and any(c in mode for c in "wax+"):
                    chemin = _premier_texte(noeud)
                    if chemin and (chemin.startswith("/") or chemin.startswith("~")
                                   or ".." in chemin):
                        rapport.soucis.append(Souci(
                            "dangereux",
                            "ecrit hors du dossier de travail : {}".format(chemin),
                            ligne=ligne))
            elif cible == "input":
                rapport.soucis.append(Souci(
                    "avertissement",
                    "attend une saisie : le script se bloquera si on l'automatise",
                    ligne=ligne))

    if rapport.dangers:
        rapport.executable = False
    return rapport


def _nom_appel(noeud: ast.AST) -> str:
    if isinstance(noeud, ast.Name):
        return noeud.id
    if isinstance(noeud, ast.Attribute):
        base = _nom_appel(noeud.value)
        return "{}.{}".format(base, noeud.attr) if base else noeud.attr
    return ""


def _mode_ouverture(appel: ast.Call) -> str:
    if len(appel.args) > 1 and isinstance(appel.args[1], ast.Constant):
        return str(appel.args[1].value)
    for mot in appel.keywords:
        if mot.arg == "mode" and isinstance(mot.value, ast.Constant):
            return str(mot.value.value)
    return ""


def _premier_texte(appel: ast.Call) -> str:
    if appel.args and isinstance(appel.args[0], ast.Constant):
        return str(appel.args[0].value)
    return ""


# --------------------------------------------------------------------------
# JavaScript
# --------------------------------------------------------------------------

_JS_DANGERS = [
    (r"\beval\s*\(", "appelle eval()"),
    (r"\bnew\s+Function\s*\(", "construit une fonction depuis du texte"),
    (r"require\s*\(\s*['\"]child_process", "lance des processus"),
    (r"require\s*\(\s*['\"]fs['\"]", "acces au systeme de fichiers"),
    (r"\bdocument\.write\s*\(", "document.write() : a eviter"),
    (r"\binnerHTML\s*=", "innerHTML : risque d'injection si la valeur vient "
                         "de l'utilisateur"),
]


def node_disponible() -> bool:
    return shutil.which("node") is not None


def analyser_js(code: str, nom: str = "script.js") -> Rapport:
    """Syntaxe par node si disponible, sinon controle structurel annonce comme tel."""
    rapport = Rapport(fichier=nom, langage="javascript")

    if node_disponible():
        rapport.verifie_par = "node --check"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as fichier:
            fichier.write(code)
            chemin = fichier.name
        try:
            resultat = subprocess.run(["node", "--check", chemin],
                                      capture_output=True, text=True, timeout=20)
            if resultat.returncode != 0:
                rapport.valide = False
                rapport.executable = False
                rapport.soucis.append(Souci(
                    "casse", "erreur de syntaxe : {}".format(
                        _message_node(resultat.stderr or "")),
                    extrait=(resultat.stderr or "").strip()[:300]))
        except (subprocess.TimeoutExpired, OSError) as exc:
            rapport.verifie_par = "controle structurel (node indisponible)"
            _controle_structurel(code, rapport)
        finally:
            os.unlink(chemin)
    else:
        # Termux n'a pas node par defaut. On verifie ce qu'on peut, et on le dit.
        rapport.verifie_par = "controle structurel (node absent)"
        _controle_structurel(code, rapport)

    for motif, message in _JS_DANGERS:
        for occurrence in re.finditer(motif, code):
            ligne = code[: occurrence.start()].count("\n") + 1
            rapport.soucis.append(Souci("dangereux", message, ligne=ligne))
    return rapport


def _message_node(stderr: str) -> str:
    """Extrait la ligne utile de la sortie de node.

    Sa derniere ligne est sa banniere de version : la renvoyer au modele pour
    qu'il corrige ne lui apprendrait rien.
    """
    lignes = [l.strip() for l in stderr.strip().split("\n") if l.strip()]
    for ligne in lignes:
        if "Error:" in ligne:
            return ligne
    for ligne in lignes:
        if not ligne.startswith("Node.js v") and not ligne.startswith("at "):
            return ligne
    return "node a refuse le fichier"


def _controle_structurel(code: str, rapport: Rapport) -> None:
    """Equilibre des delimiteurs, hors chaines et commentaires."""
    nettoye = re.sub(r"//[^\n]*", "", code)
    nettoye = re.sub(r"/\*.*?\*/", "", nettoye, flags=re.DOTALL)
    nettoye = re.sub(r"'(?:\\.|[^'\\])*'", "''", nettoye)
    nettoye = re.sub(r'"(?:\\.|[^"\\])*"', '""', nettoye)
    nettoye = re.sub(r"`(?:\\.|[^`\\])*`", "``", nettoye)
    pile: List[str] = []
    paires = {")": "(", "]": "[", "}": "{"}
    for caractere in nettoye:
        if caractere in "([{":
            pile.append(caractere)
        elif caractere in paires:
            if not pile or pile[-1] != paires[caractere]:
                rapport.valide = False
                rapport.executable = False
                rapport.soucis.append(Souci(
                    "casse", "delimiteur « {} » mal ferme".format(caractere)))
                return
            pile.pop()
    if pile:
        rapport.valide = False
        rapport.executable = False
        rapport.soucis.append(Souci(
            "casse", "{} delimiteur(s) jamais fermes : {}".format(
                len(pile), "".join(pile[-5:]))))


# --------------------------------------------------------------------------
# JSON, HTML, manifeste d'extension
# --------------------------------------------------------------------------


def analyser_json(texte: str, nom: str = "data.json",
                  cles_requises: Sequence[str] = ()) -> Rapport:
    rapport = Rapport(fichier=nom, langage="json", verifie_par="json.loads")
    try:
        donnees = json.loads(texte)
    except ValueError as exc:
        rapport.valide = False
        rapport.executable = False
        rapport.soucis.append(Souci("casse", "JSON invalide : {}".format(exc)))
        return rapport
    if cles_requises and isinstance(donnees, dict):
        for cle in cles_requises:
            if cle not in donnees:
                rapport.valide = False
                rapport.soucis.append(Souci(
                    "casse", "cle obligatoire absente : « {} »".format(cle)))
    return rapport


PERMISSIONS_LARGES = {"<all_urls>", "tabs", "webRequest", "cookies", "history",
                      "downloads", "management", "debugger", "proxy"}


def analyser_manifeste(texte: str, nom: str = "manifest.json") -> Rapport:
    """Manifeste d'extension Chrome : structure et etendue des permissions."""
    rapport = analyser_json(texte, nom,
                            cles_requises=("manifest_version", "name", "version"))
    if not rapport.valide:
        return rapport
    donnees = json.loads(texte)
    rapport.verifie_par = "json.loads + schema Chrome MV3"

    if donnees.get("manifest_version") != 3:
        rapport.soucis.append(Souci(
            "casse", "manifest_version doit valoir 3 : les versions 2 ne sont "
                     "plus acceptees sur le Chrome Web Store"))
        rapport.valide = False

    if not re.match(r"^\d+(\.\d+){0,3}$", str(donnees.get("version", ""))):
        rapport.soucis.append(Souci(
            "casse", "« version » doit etre une suite de nombres, ex : 1.0.0"))
        rapport.valide = False

    permissions = set(donnees.get("permissions") or []) | set(
        donnees.get("host_permissions") or [])
    for permission in sorted(permissions & PERMISSIONS_LARGES):
        rapport.soucis.append(Souci(
            "avertissement",
            "permission « {} » : large, elle rallonge la revue du Web Store et "
            "inquiete l'utilisateur".format(permission)))
    return rapport


def analyser_html(texte: str, nom: str = "index.html") -> Rapport:
    """Bonne formation des balises et dependances externes."""
    import html.parser

    rapport = Rapport(fichier=nom, langage="html",
                      verifie_par="analyseur HTML + dependances")

    class Verificateur(html.parser.HTMLParser):
        vides = {"br", "img", "hr", "meta", "link", "input", "source", "area",
                 "base", "col", "embed", "param", "track", "wbr"}

        def __init__(self):
            super().__init__()
            self.pile: List[Tuple[str, int]] = []
            self.erreurs: List[Souci] = []

        def handle_starttag(self, balise, attributs):
            if balise not in self.vides:
                self.pile.append((balise, self.getpos()[0]))

        def handle_endtag(self, balise):
            if balise in self.vides:
                return
            if not self.pile:
                self.erreurs.append(Souci(
                    "casse", "</{}> sans ouverture".format(balise),
                    ligne=self.getpos()[0]))
            elif self.pile[-1][0] != balise:
                self.erreurs.append(Souci(
                    "casse", "</{}> alors que <{}> est ouvert".format(
                        balise, self.pile[-1][0]), ligne=self.getpos()[0]))
            else:
                self.pile.pop()

    verificateur = Verificateur()
    try:
        verificateur.feed(texte)
    except Exception as exc:
        rapport.valide = False
        rapport.soucis.append(Souci("casse", "HTML illisible : {}".format(exc)))
        return rapport

    rapport.soucis.extend(verificateur.erreurs)
    for balise, ligne in verificateur.pile:
        rapport.soucis.append(Souci(
            "casse", "<{}> jamais referme".format(balise), ligne=ligne))
    if rapport.casse:
        rapport.valide = False

    # Une dependance externe rend le produit inutilisable hors ligne, et casse
    # le jour ou le service distant disparait.
    for occurrence in re.finditer(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)',
                                  texte):
        rapport.soucis.append(Souci(
            "avertissement",
            "depend de {} : le produit ne fonctionnera plus hors ligne".format(
                occurrence.group(1)[:60]),
            ligne=texte[: occurrence.start()].count("\n") + 1))

    for bloc in re.findall(r"<script[^>]*>(.*?)</script>", texte, re.DOTALL):
        sous_rapport = analyser_js(bloc, nom + " (script inline)")
        rapport.soucis.extend(sous_rapport.soucis)
        if not sous_rapport.valide:
            rapport.valide = False
    return rapport


# --------------------------------------------------------------------------
# Execution encadree
# --------------------------------------------------------------------------


@dataclass
class Execution:
    lance: bool = False
    code_retour: Optional[int] = None
    sortie: str = ""
    erreur: str = ""
    refus: str = ""

    @property
    def reussi(self) -> bool:
        return self.lance and self.code_retour == 0


def executer_python(
    chemin: Path,
    arguments: Sequence[str] = (),
    rapport: Optional[Rapport] = None,
    secondes: int = 15,
) -> Execution:
    """Lance un script genere, uniquement si l'analyse statique l'autorise.

    Le refus n'est pas un echec du produit : c'est la garantie qu'on ne lance
    pas sur votre telephone un code qu'aucun humain n'a lu.
    """
    if rapport is not None and not rapport.executable:
        raison = (rapport.casse or rapport.dangers)[0].message
        return Execution(refus="analyse statique : {}".format(raison))

    environnement = dict(os.environ)
    # Un script genere n'a aucune raison d'atteindre le reseau pendant la
    # verification, ni d'ecrire ailleurs que dans son dossier.
    environnement.pop("HTTP_PROXY", None)
    environnement.pop("HTTPS_PROXY", None)
    environnement["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        resultat = subprocess.run(
            [sys.executable, str(chemin), *arguments],
            capture_output=True, text=True, timeout=secondes,
            cwd=str(chemin.parent), env=environnement,
        )
    except subprocess.TimeoutExpired:
        return Execution(lance=True, code_retour=None,
                         erreur="depassement de {} s : boucle infinie probable"
                                .format(secondes))
    except OSError as exc:
        return Execution(refus="lancement impossible : {}".format(exc))

    return Execution(lance=True, code_retour=resultat.returncode,
                     sortie=(resultat.stdout or "")[:4000],
                     erreur=(resultat.stderr or "")[:4000])


# --------------------------------------------------------------------------
# Aiguillage
# --------------------------------------------------------------------------

_ANALYSEURS = {
    ".py": analyser_python,
    ".js": analyser_js,
    ".mjs": analyser_js,
    ".json": analyser_json,
    ".html": analyser_html,
    ".htm": analyser_html,
}


def analyser_fichier(chemin: str, contenu: str) -> Rapport:
    """Choisit l'analyseur d'apres l'extension. Le manifeste est un cas a part."""
    nom = Path(chemin).name
    if nom == "manifest.json":
        return analyser_manifeste(contenu, nom)
    analyseur = _ANALYSEURS.get(Path(chemin).suffix.lower())
    if analyseur is None:
        return Rapport(fichier=nom, langage="texte",
                       verifie_par="aucune verification pour ce format")
    return analyseur(contenu, nom)


def synthese(rapports: Sequence[Rapport]) -> Dict[str, Any]:
    return {
        "fichiers": len(rapports),
        "valides": sum(1 for r in rapports if r.valide),
        "casses": [r.fichier for r in rapports if not r.valide],
        "a_relire": [r.fichier for r in rapports if r.dangers],
        "avertissements": sum(
            1 for r in rapports for s in r.soucis if s.gravite == "avertissement"),
        "tout_valide": all(r.valide for r in rapports),
        "detail": [
            {"fichier": r.fichier, "langage": r.langage, "valide": r.valide,
             "verifie_par": r.verifie_par,
             "soucis": [{"gravite": s.gravite, "message": s.message,
                         "ligne": s.ligne} for s in r.soucis]}
            for r in rapports
        ],
    }
