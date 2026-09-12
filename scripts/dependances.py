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


def principal() -> int:
    noms = getattr(sys, "stdlib_module_names", None)
    if noms is None:                   # Python < 3.10
        print("Python {}.{} ne connait pas la liste de sa bibliotheque "
              "standard : verification impossible.".format(*sys.version_info[:2]))
        return 0
    standard = set(noms)
    etrangers = []
    for fichier in sorted(RACINE.rglob("*.py")):
        if "__pycache__" in fichier.parts or "atelier" in fichier.parts:
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
