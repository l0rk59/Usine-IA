"""Mise en page d'un cahier de mots meles : grilles, listes, solutions.

La grille arrive toute faite (« pipelines/mots_meles.py ») ; ici, on ne
decide que de la taille des choses. Deux contraintes, venues de l'usage :

- **la grille prend toute la place que la liste lui laisse**. Une case se
  dimensionne sur la largeur ET sur la hauteur restante, puis se plafonne :
  une grille de douze cases etiree sur toute la page ressemble a une page
  pour enfants, meme au niveau « difficile » ;
- **les solutions se lisent en noir sur fond pale**. Surlignees en couleurs
  pastel, elles restent lisibles imprimees en niveaux de gris, ce que font
  la plupart des imprimantes a domicile. Les lettres qui ne servent a aucun
  mot passent en gris clair, pour que le mot saute aux yeux.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List

from .metriques import largeur_texte
from .pdf import DocumentPDF

POLICE = "Helvetica-Bold"
POLICE_LISTE = "Helvetica"
ENCRE = (0.08, 0.09, 0.12)
GRIS_CLAIR = (0.70, 0.72, 0.76)
GRIS_TRAIT = (0.45, 0.48, 0.55)
SURLIGNEURS = ((1.0, 0.84, 0.45), (0.62, 0.85, 0.96), (0.72, 0.92, 0.66),
               (0.98, 0.72, 0.78))
# Le plafond d'une case, en points. Au-dela, une petite grille devient une
# page pour enfants ; les gros caracteres ont le leur, plus haut.
CASE_MAX = {False: 30.0, True: 36.0}
# La lettre par rapport a sa case : assez d'air pour que deux lettres
# voisines ne se touchent pas, assez de corps pour lire sans lunettes.
PROPORTION = {False: 0.55, True: 0.64}
TAILLE_LISTE = {False: 10.5, True: 13.5}
COLONNES_LISTE = {False: 3, True: 2}
PAR_PAGE_SOLUTIONS = 4


def _y(doc: DocumentPDF) -> float:
    """Le curseur de la page, lu par la seule voie publique."""
    return doc.marge + 26 + doc.hauteur_restante


def _lettre(doc: DocumentPDF, lettre: str, cx: float, cy: float,
            police: str, taille: float, couleur) -> None:
    """Une capitale centree sur un point : 0,36 corps sous le centre, soit
    la moitie de la hauteur des capitales d'Helvetica."""
    doc.texte_a(lettre, cx - largeur_texte(lettre, police, taille) / 2,
                cy - taille * 0.36, police, taille, couleur)


def page_de_grille(grille: Dict[str, Any], t: Dict[str, Any],
                   gros: bool) -> Callable[[DocumentPDF], None]:
    """La page d'une grille, sous son titre : la grille, puis sa liste."""

    def dessiner(doc: DocumentPDF) -> None:
        lettres = grille["lettres"]
        n = len(lettres)
        mots = [m["affichage"] for m in grille["mots"]]
        colonnes = COLONNES_LISTE[gros]
        corps = TAILLE_LISTE[gros]
        rangs = math.ceil(len(mots) / colonnes)
        hauteur_liste = 30 + rangs * corps * 1.7
        case = min(doc.largeur_utile / n,
                   (doc.hauteur_restante - hauteur_liste - 20) / n,
                   CASE_MAX[gros])
        cote = n * case
        x0 = doc.marge_gauche + (doc.largeur_utile - cote) / 2
        haut = _y(doc) - 6
        doc.rectangle(x0 - 5, haut - cote - 5, cote + 10, cote + 10,
                      GRIS_TRAIT, plein=False, epaisseur=1.1)
        taille = case * PROPORTION[gros]
        for ligne, rangee in enumerate(lettres):
            for colonne, lettre in enumerate(rangee):
                _lettre(doc, lettre, x0 + (colonne + 0.5) * case,
                        haut - (ligne + 0.5) * case, POLICE, taille, ENCRE)
        doc.espace(cote + 30)

        y = _y(doc)
        doc.texte_a(t["meles_a_trouver"], doc.marge_gauche, y, POLICE,
                    corps, ENCRE)
        y -= corps * 2
        largeur_col = doc.largeur_utile / colonnes
        for rang, mot in enumerate(mots):
            colonne, ligne = rang // rangs, rang % rangs
            x = doc.marge_gauche + colonne * largeur_col
            yl = y - ligne * corps * 1.7
            # Une case a cocher : le joueur raye ce qu'il a trouve.
            doc.rectangle(x, yl - 1, corps * 0.75, corps * 0.75, GRIS_TRAIT,
                          plein=False, epaisseur=0.7)
            place = largeur_col - corps * 1.6
            taille_mot = corps
            while (largeur_texte(mot, POLICE_LISTE, taille_mot) > place
                   and taille_mot > corps * 0.7):
                taille_mot -= 0.5
            doc.texte_a(mot, x + corps * 1.2, yl, POLICE_LISTE, taille_mot, ENCRE)
        doc.espace(hauteur_liste)

    return dessiner


def _solution(doc: DocumentPDF, grille: Dict[str, Any], libelle: str,
              x0: float, haut: float, case: float) -> None:
    n = len(grille["lettres"])
    corps = min(9.0, case * 0.9)
    doc.texte_a(libelle, x0, haut, POLICE, corps, ENCRE)
    haut -= corps + 6
    dans_un_mot = set()
    for rang, mot in enumerate(grille["mots"]):
        ligne, colonne, dl, dc = mot["position"]
        fin = len(mot["forme"]) - 1
        for i in range(fin + 1):
            dans_un_mot.add((ligne + dl * i, colonne + dc * i))
        doc.trait(x0 + (colonne + 0.5) * case, haut - (ligne + 0.5) * case,
                  x0 + (colonne + dc * fin + 0.5) * case,
                  haut - (ligne + dl * fin + 0.5) * case,
                  SURLIGNEURS[rang % len(SURLIGNEURS)], epaisseur=case * 0.8,
                  arrondi=True)
    doc.rectangle(x0, haut - n * case, n * case, n * case, GRIS_CLAIR,
                  plein=False, epaisseur=0.6)
    taille = case * 0.58
    for ligne, rangee in enumerate(grille["lettres"]):
        for colonne, lettre in enumerate(rangee):
            utile = (ligne, colonne) in dans_un_mot
            _lettre(doc, lettre, x0 + (colonne + 0.5) * case,
                    haut - (ligne + 0.5) * case,
                    POLICE if utile else POLICE_LISTE, taille,
                    ENCRE if utile else GRIS_CLAIR)


def pages_de_solutions(grilles: List[Dict[str, Any]],
                       t: Dict[str, Any]) -> Callable[[DocumentPDF], None]:
    """Quatre solutions par page, deux par rangee, dans l'ordre des grilles."""

    def dessiner(doc: DocumentPDF) -> None:
        for debut in range(0, len(grilles), PAR_PAGE_SOLUTIONS):
            if debut:
                doc.nouvelle_page()
                doc.espace(10)
            haut = _y(doc)
            hauteur = doc.hauteur_restante
            demi_l = (doc.largeur_utile - 24) / 2
            demi_h = (hauteur - 20) / 2
            for rang, grille in enumerate(grilles[debut:debut + PAR_PAGE_SOLUTIONS]):
                n = len(grille["lettres"])
                case = min(demi_l / n, (demi_h - 24) / n)
                colonne, rangee = rang % 2, rang // 2
                _solution(doc, grille,
                          t["meles_solution"].format(numero=debut + rang + 1),
                          doc.marge_gauche + colonne * (demi_l + 24),
                          haut - rangee * (demi_h + 20), case)
            doc.espace(hauteur)

    return dessiner


def markdown_grille(grille: Dict[str, Any], t: Dict[str, Any]) -> str:
    """La grille en texte, pour le markdown et la page : une lettre par
    colonne, espacees, dans un bloc a chasse fixe."""
    lignes = ["```text"] + [" ".join(rangee) for rangee in grille["lettres"]] + ["```"]
    lignes.append("")
    lignes.append(t["deux_points"].format(
        libelle="**{}**".format(t["meles_a_trouver"]),
        texte=" · ".join(m["affichage"] for m in grille["mots"])))
    return "\n".join(lignes)


def markdown_solutions(grilles: List[Dict[str, Any]], t: Dict[str, Any]) -> str:
    """Chaque solution en texte : les lettres des mots, un point ailleurs."""
    morceaux = []
    for numero, grille in enumerate(grilles, 1):
        n = len(grille["lettres"])
        vue = [["·"] * n for _ in range(n)]
        for mot in grille["mots"]:
            ligne, colonne, dl, dc = mot["position"]
            for i, lettre in enumerate(mot["forme"]):
                vue[ligne + dl * i][colonne + dc * i] = lettre
        morceaux.append("**{}**".format(t["meles_solution"].format(numero=numero)))
        morceaux.append("\n".join(["```text"] + [" ".join(r) for r in vue] + ["```"]))
    return "\n\n".join(morceaux)
