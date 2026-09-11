"""Ecriture de CSV destines a etre ouverts dans un tableur.

Un CSV produit par l'usine n'est pas un fichier de travail : c'est un
LIVRABLE. Les modeles Notion, le calendrier editorial, les tableaux de la
boite a outils partent tels quels chez l'acheteur, qui les ouvre dans Excel,
LibreOffice ou Google Sheets.

Or ces trois logiciels interpretent comme une FORMULE toute cellule qui
commence par « = », « + », « - » ou « @ ». Deux consequences, l'une genante
et l'autre grave :

  QUALITE   une cellule legitime comme « -50 % de temps passe » devient
            « #NAME? » a l'ouverture. L'acheteur voit une erreur dans un
            fichier qu'il a paye.
  SECURITE  le contenu vient d'un modele de langage, nourri entre autres de
            titres Hacker News et de questions Stack Exchange recuperes sur
            internet. Une cellule commencant par « =HYPERLINK(... » ou
            « =cmd|... » s'execute a l'ouverture, sur la machine de
            l'acheteur. C'est l'injection de formule, CWE-1236.

La parade est d'un caractere : un apostrophe en tete marque la cellule comme
du texte. Il est INVISIBLE dans Excel, LibreOffice et Google Sheets — la
cellule s'affiche « -50 % de temps passe », donc la fidelite s'ameliore au
lieu de se degrader. Il reste visible dans un editeur de texte brut : c'est
le prix, et il est assume.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Sequence

# Caracteres qui declenchent l'evaluation d'une formule. La tabulation et le
# retour chariot sont inclus : un tableur les ignore en tete, puis lit le
# caractere suivant — « \t=1+1 » s'execute donc aussi.
AMORCES = ("=", "+", "-", "@", "\t", "\r")


def cellule(valeur: Any) -> str:
    """Rend une valeur inoffensive pour un tableur."""
    texte = "" if valeur is None else str(valeur)
    if texte.startswith(AMORCES):
        return "'" + texte
    return texte


def ligne(valeurs: Iterable[Any]) -> list:
    return [cellule(v) for v in valeurs]


def ecrire(chemin: Path, entetes: Sequence[Any],
           lignes: Iterable[Sequence[Any]]) -> Path:
    """Ecrit un CSV livrable, en-tetes comprises."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="") as flux:
        auteur = csv.writer(flux)
        auteur.writerow(ligne(entetes))
        for valeurs in lignes:
            auteur.writerow(ligne(valeurs))
    return chemin


def ecrire_dictionnaires(chemin: Path, colonnes: Sequence[str],
                         entrees: Iterable[dict]) -> Path:
    """Meme chose a partir de dictionnaires, colonnes imposees."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="") as flux:
        auteur = csv.DictWriter(flux, fieldnames=list(colonnes))
        auteur.writeheader()
        for entree in entrees:
            auteur.writerow({c: cellule(entree.get(c, "")) for c in colonnes})
    return chemin
