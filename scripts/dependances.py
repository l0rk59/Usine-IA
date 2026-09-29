#!/usr/bin/env python3
"""Verifie que l'usine n'importe rien hors de la bibliotheque standard.

C'est la contrainte fondatrice du projet : Termux ne sait pas compiler de
roue native, et une dependance ajoutee par megarde ne se voit qu'au moment
ou quelqu'un installe sur un telephone neuf — c'est-a-dire trop tard.

On lit les imports dans l'arbre syntaxique plutot que d'executer le code :
un module qui plante a l'import passerait autrement inapercu.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _locaux() -> set:
    """Les modules du depot lui-meme, deduits de l'arborescence.

    Les enumerer a la main se serait perime au premier fichier ajoute — et
    un module local pris pour une dependance ferait echouer l'integration
    continue sans raison.
    """
    noms = set()
    for entree in RACINE.iterdir():
        if entree.is_dir() and (entree / "__init__.py").exists():
            noms.add(entree.name)
        elif entree.is_dir() and entree.name in ("tests", "scripts"):
            noms.add(entree.name)
            noms.update(f.stem for f in entree.glob("*.py"))
        elif entree.suffix == ".py":
            noms.add(entree.stem)
    return noms


LOCAUX = _locaux()


def modules_importes(fichier: Path):
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), str(fichier))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                yield alias.name.split(".")[0], noeud.lineno
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level:            # import relatif : forcement local
                continue
            if noeud.module:
                yield noeud.module.split(".")[0], noeud.lineno


def bibliotheque_standard() -> set:
    """Les modules que l'interpreteur livre lui-meme.

    Python 3.10 en tient la liste (« sys.stdlib_module_names »). Avant, on
    la deduit du dossier ou il range sa bibliotheque, sans descendre dans
    « site-packages » : c'est la que pip installe, donc la que serait une
    dependance.

    Mesure du 23/09/2026 : sans cette deduction, Python 3.9 rendait
    « verification impossible » et le code 0 — un succes. Le job 3.9 de la
    CI, qui garde les telephones jamais mis a jour, ne verifiait rien et
    restait vert. Un test l'a vu le 15/09 ; la CI etait deja rouge pour une
    autre raison (« scripts/fuites.py » raconte laquelle), et personne n'a
    lu le second echec sous le premier.

    La deduction manque les modules propres a Windows et ceux que
    l'installation n'a pas (tkinter, souvent) : les importer serait de toute
    facon une dependance pour un telephone.
    """
    noms = getattr(sys, "stdlib_module_names", None)
    if noms is not None:
        return set(noms)
    import sysconfig

    standard = set(sys.builtin_module_names)
    racine = Path(sysconfig.get_paths()["stdlib"])
    for dossier in (racine, racine / "lib-dynload"):
        if not dossier.is_dir():
            continue
        for entree in dossier.iterdir():
            if entree.suffix == ".py":
                standard.add(entree.stem)
            elif entree.is_dir() and (entree / "__init__.py").exists():
                standard.add(entree.name)
            elif entree.suffix in (".so", ".pyd"):
                standard.add(entree.name.split(".")[0])
    return standard


def principal() -> int:
    standard = bibliotheque_standard()
    etrangers = []
    for fichier in sorted(RACINE.rglob("*.py")):
        if "__pycache__" in fichier.parts or "atelier" in fichier.parts:
            continue
        # Projet independant (upscaler GPU, NumPy assume), avec sa propre
        # integration continue : la contrainte Termux ne le concerne pas.
        if fichier.relative_to(RACINE).parts[0] == "super-resolution":
            continue
        for nom, ligne in modules_importes(fichier):
            if nom in standard or nom in LOCAUX:
                continue
            etrangers.append("{}:{} importe « {} »".format(
                fichier.relative_to(RACINE), ligne, nom))

    if etrangers:
        print("Dependances hors bibliotheque standard :")
        for ligne in etrangers:
            print("  " + ligne)
        print("\nL'usine doit s'installer sur un Termux nu, sans pip.")
        return 1
    print("Aucune dependance hors bibliotheque standard.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
