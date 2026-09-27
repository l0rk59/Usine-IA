"""Cahier de mots meles : le modele choisit les mots, le code fait les grilles.

Un rayon entier des places de marche d'impression a la demande, et le seul
produit de l'usine ou le modele n'ecrit presque rien : une liste de mots par
theme. Tout le reste — placer, remplir, verifier, dessiner, resoudre — est
du calcul, donc deterministe et gratuit. Ce qu'un modele ferait mal ici, il
ne le fait pas : une grille « ecrite » par un modele contient des mots
introuvables, et l'acheteur le decouvre en cherchant.

Trois defauts qu'un cahier de mots meles ne pardonne pas, et que ce module
empeche au lieu de les esperer absents :

  1. **un mot de la liste absent de la grille** : il n'est liste QUE s'il a
     ete place. Un mot que la grille refuse sort de la liste, et c'est
     compte ;
  2. **un mot present deux fois** : le remplissage au hasard recree parfois
     un mot court (« RAT ») ailleurs dans la grille. Le joueur en trouve un,
     coche, et la solution lui en montre un autre. Chaque grille est relue
     apres remplissage, et refaite tant qu'un mot y figure deux fois ;
  3. **un mot contenu dans un autre** (« RAT » et « RATEAU ») : le second
     contient toujours le premier, le defaut 2 est alors inevitable. Le plus
     court est ecarte avant de placer quoi que ce soit.
"""

from __future__ import annotations

import json
import random
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..agents import equipe
from ..render import libelles, livraison
from ..render import mots_meles as rendu
from ..render.pdf import LETTRE
from .base import Contexte, Redaction, nettoyer_titre, preparer, renommer, slug, terminer

LOT = 8
NOMBRE_MIN, NOMBRE_MAX = 4, 100
MOTS_MIN = 6          # en dessous, une page de grille ne se vend pas
DIFFICULTE_PAR_DEFAUT = "moyen"
CARACTERES_PAR_DEFAUT = "standard"

# Les directions de lecture, en (pas de ligne, pas de colonne). « moyen »
# ajoute les diagonales qui se lisent de gauche a droite ; seul « difficile »
# fait lire a l'envers — c'est ce qui rend une grille vraiment dure.
_EST, _SUD, _SUD_EST, _NORD_EST = (0, 1), (1, 0), (1, 1), (-1, 1)
DIFFICULTES: Dict[str, Dict[str, Any]] = {
    "facile": {"taille": 12, "gros": 11, "mots": 12,
               "directions": (_EST, _SUD)},
    "moyen": {"taille": 15, "gros": 13, "mots": 15,
              "directions": (_EST, _SUD, _SUD_EST, _NORD_EST)},
    "difficile": {"taille": 18, "gros": 14, "mots": 18,
                  "directions": (_EST, _SUD, _SUD_EST, _NORD_EST,
                                 (0, -1), (-1, 0), (-1, -1), (1, -1))},
}
CARACTERES = ("standard", "gros")
_ESSAIS_REMPLISSAGE = 40


def lettres(mot: str) -> str:
    """La forme d'un mot dans la grille : majuscules, sans accent, sans
    espace ni tiret. Rend « » si le mot garde autre chose que A a Z."""
    mot = (str(mot).replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae")
           .replace("Æ", "AE").replace("ß", "ss"))
    sans = "".join(c for c in unicodedata.normalize("NFKD", mot)
                   if not unicodedata.combining(c))
    sans = "".join(c for c in sans if c not in " -'’.").upper()
    return sans if sans.isascii() and sans.isalpha() else ""


def preparer_mots(bruts: List[Any], taille: int, combien: int
                  ) -> Tuple[List[Tuple[str, str]], int]:
    """(affichage, lettres) des mots retenus, et combien ont ete ecartes.

    Ecartes : ce qui ne s'ecrit pas en lettres, ce qui est trop court ou
    trop long pour la grille, les doublons, et le plus court de deux mots
    dont l'un contient l'autre.
    """
    retenus: List[Tuple[str, str]] = []
    vus = set()
    ecartes = 0
    for brut in bruts or []:
        affichage = " ".join(str(brut or "").split())
        forme = lettres(affichage)
        if not (3 <= len(forme) <= taille) or forme in vus:
            ecartes += 1
            continue
        vus.add(forme)
        retenus.append((affichage.upper(), forme))
    contenus = {f for _, f in retenus
                if any(f != g and f in g for _, g in retenus)}
    ecartes += len(contenus)
    retenus = [(a, f) for a, f in retenus if f not in contenus]
    ecartes += max(0, len(retenus) - combien)
    return retenus[:combien], ecartes


def _lignes(grille: List[List[str]]) -> List[str]:
    """Toutes les lignes droites de la grille, dans les quatre sens de
    lecture « a l'endroit ». Les quatre autres sont leurs envers."""
    n = len(grille)
    lignes = ["".join(rangee) for rangee in grille]
    lignes += ["".join(grille[l][c] for l in range(n)) for c in range(n)]
    for d in range(-n + 1, n):
        lignes.append("".join(grille[l][l - d] for l in range(n) if 0 <= l - d < n))
        lignes.append("".join(grille[l][d + n - 1 - l] for l in range(n)
                              if 0 <= d + n - 1 - l < n))
    return lignes


def occurrences(grille: List[List[str]], forme: str) -> int:
    """Combien de fois un mot se lit dans la grille, toutes directions.

    Un palindrome (« RADAR ») se lit deux fois au meme endroit, dans un
    sens et dans l'autre : il n'est compte qu'a l'endroit.
    """
    total = 0
    for ligne in _lignes(grille):
        for sens in ((ligne,) if forme == forme[::-1] else (ligne, ligne[::-1])):
            debut = sens.find(forme)
            while debut != -1:
                total += 1
                debut = sens.find(forme, debut + 1)
    return total


def _essayer(grille, forme, ligne, colonne, dl, dc) -> Optional[int]:
    """Le nombre de lettres partagees si le mot tient la, None sinon."""
    n = len(grille)
    fin_l, fin_c = ligne + dl * (len(forme) - 1), colonne + dc * (len(forme) - 1)
    if not (0 <= fin_l < n and 0 <= fin_c < n):
        return None
    partagees = 0
    for rang, lettre in enumerate(forme):
        case = grille[ligne + dl * rang][colonne + dc * rang]
        if case is None:
            continue
        if case != lettre:
            return None
        partagees += 1
    # Un mot pose entierement sur un autre ne se voit pas.
    return None if partagees == len(forme) else partagees


def placer(formes: List[str], taille: int,
           directions: Tuple[Tuple[int, int], ...], alea: random.Random
           ) -> Tuple[List[List[Optional[str]]], Dict[str, Tuple[int, int, int, int]]]:
    """Pose les mots, du plus long au plus court. Rend la grille (cases
    vides a None) et, pour chaque mot place, (ligne, colonne, dl, dc)."""
    grille: List[List[Optional[str]]] = [[None] * taille for _ in range(taille)]
    places: Dict[str, Tuple[int, int, int, int]] = {}
    for forme in sorted(formes, key=len, reverse=True):
        candidats = []
        for dl, dc in directions:
            for ligne in range(taille):
                for colonne in range(taille):
                    partage = _essayer(grille, forme, ligne, colonne, dl, dc)
                    if partage is not None:
                        candidats.append((partage, ligne, colonne, dl, dc))
        if not candidats:
            continue
        # Un croisement de temps en temps rend la grille plus dense et plus
        # juste ; toujours croiser la rendrait previsible.
        croisants = [c for c in candidats if c[0]]
        pool = croisants if croisants and alea.random() < 0.6 else candidats
        _, ligne, colonne, dl, dc = alea.choice(pool)
        for rang, lettre in enumerate(forme):
            grille[ligne + dl * rang][colonne + dc * rang] = lettre
        places[forme] = (ligne, colonne, dl, dc)
    return grille, places


def remplir(grille: List[List[Optional[str]]], formes: List[str],
            alea: random.Random) -> Optional[List[List[str]]]:
    """Comble les cases vides avec les lettres des mots eux-memes — une
    lettre rare au milieu du bruit se reperait d'un coup d'oeil — et refait
    le remplissage tant qu'un mot se lit deux fois. None si rien n'y fait."""
    reservoir = "".join(formes) or "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for _essai in range(_ESSAIS_REMPLISSAGE):
        pleine = [[case if case is not None else alea.choice(reservoir)
                   for case in rangee] for rangee in grille]
        if all(occurrences(pleine, f) == 1 for f in formes):
            return pleine
    return None


def fabriquer_grille(mots: List[Tuple[str, str]], difficulte: str,
                     caracteres: str, graine: str) -> Optional[Dict[str, Any]]:
    """Une grille complete et verifiee, ou None si trop peu de mots tiennent.

    La graine vient du sujet et du theme : la meme liste redonne la meme
    grille, et une reprise ne change pas un cahier deja relu.
    """
    fiche = DIFFICULTES[difficulte]
    taille = fiche["gros"] if caracteres == "gros" else fiche["taille"]
    alea = random.Random(graine)
    formes = [f for _, f in mots if len(f) <= taille]
    for _essai in range(4):
        brute, places = placer(formes, taille, fiche["directions"], alea)
        retenues = [f for f in formes if f in places]
        pleine = remplir(brute, retenues, alea)
        if pleine is not None and len(retenues) >= MOTS_MIN:
            affichage = {f: a for a, f in mots}
            return {"lettres": ["".join(r) for r in pleine],
                    "mots": [{"affichage": affichage[f], "forme": f,
                              "position": list(places[f])}
                             for f in sorted(retenues, key=affichage.get)],
                    "perdus": len(formes) - len(retenues)
                              + (len(mots) - len(formes))}
    return None


# --------------------------------------------------------------------------
# La chaine
# --------------------------------------------------------------------------


def _rediger_lot(ctx: Contexte, combien: int, par_grille: int, taille: int,
                 deja: List[str]) -> List[Dict[str, Any]]:
    invite = (
        "Prepare {n} grilles de mots meles sur le theme general : {sujet}\n"
        "PUBLIC : {audience}\n{deja}\n"
        "Pour chaque grille :\n"
        "- 'theme' : un sous-theme precis du theme general, deux a cinq "
        "mots. Deux grilles n'ont jamais le meme sous-theme.\n"
        "- 'mots' : {m} mots, ou expressions tres courtes, qui appartiennent "
        "a ce sous-theme et que le public connait. Chacun fait de 3 a {l} "
        "lettres, espaces et tirets non comptes. Ni chiffre, ni sigle. "
        "Aucun mot n'est contenu dans un autre de la meme grille (pas « rat » "
        "avec « rateau »).\n"
        "Ecris les mots avec leurs accents, dans la langue du produit.\n\n"
        "Schema JSON exact :\n"
        '{{"grilles": [{{"theme": "...", "mots": ["...", "..."]}}]}}'
    ).format(n=combien, sujet=ctx.sujet, audience=ctx.audience, m=par_grille,
             l=taille, deja=("SOUS-THEMES DEJA PRIS, n'y reviens pas : "
                             + " | ".join(deja[-60:]) if deja else ""))
    donnees = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="standard", temperature=0.7,
        max_tokens=60 * par_grille * combien + 400)
    brutes = donnees.get("grilles") if isinstance(donnees, dict) else donnees
    return [{"theme": nettoyer_titre(str(b.get("theme") or "")),
             "mots": [str(m) for m in (b.get("mots") or []) if str(m).strip()]}
            for b in (brutes or []) if isinstance(b, dict)
            and str(b.get("theme") or "").strip()]


def _choix(ctx: Contexte, valeur: str, possibles, defaut: str, nom: str) -> str:
    if valeur in possibles:
        return valeur
    ctx.journal("  {} : {} (personne ne l'a choisi)".format(nom, defaut))
    return defaut


def produire(ctx: Contexte, nombre: int = 30, difficulte: str = "",
             caracteres: str = "") -> Dict[str, Any]:
    nombre = max(NOMBRE_MIN, min(int(nombre or 30), NOMBRE_MAX))
    difficulte = _choix(ctx, difficulte, DIFFICULTES, DIFFICULTE_PAR_DEFAUT,
                        "difficulté")
    caracteres = _choix(ctx, caracteres, CARACTERES, CARACTERES_PAR_DEFAUT,
                        "caractères")
    fiche = DIFFICULTES[difficulte]
    taille = fiche["gros"] if caracteres == "gros" else fiche["taille"]
    par_grille = fiche["mots"] if caracteres == "standard" else fiche["mots"] - 3
    t = libelles.textes(ctx.langue_iso)
    titre = t["meles_titre"].format(nombre=nombre, sujet=ctx.sujet)
    dossier = preparer(ctx, "mots-meles", titre)

    lots = (nombre + LOT - 1) // LOT
    ctx.journal("Étape 1/2 — {} listes de mots, en {} lot(s)...".format(
        nombre, lots))
    redaction = Redaction(ctx, dossier)
    grilles: List[Dict[str, Any]] = []
    themes_vus = set()
    ecartes = perdus = 0
    for rang in range(1, lots + 1):
        combien = min(LOT, nombre - (rang - 1) * LOT)
        deja = [g["theme"] for g in grilles]
        texte = redaction.ecrire(
            "lot-{}".format(rang), "{} grille(s)".format(combien),
            lambda: json.dumps(_rediger_lot(ctx, combien, par_grille, taille,
                                            deja), ensure_ascii=False))
        if texte is None:
            continue
        for liste in json.loads(texte):
            if len(grilles) >= nombre:
                break
            cle = liste["theme"].lower()
            if cle in themes_vus:
                ecartes += 1
                continue
            mots, rejetes = preparer_mots(liste["mots"], taille, par_grille)
            perdus += rejetes
            grille = fabriquer_grille(mots, difficulte, caracteres,
                                      "{}|{}".format(ctx.sujet, liste["theme"]))
            if grille is None:
                ecartes += 1
                continue
            themes_vus.add(cle)
            perdus += grille.pop("perdus")
            grille["theme"] = liste["theme"]
            grilles.append(grille)
        ctx.journal("  lot {}/{} : {} grille(s) au total".format(
            rang, lots, len(grilles)))
    if not grilles:
        if redaction.cause is not None:
            raise redaction.cause
        raise ValueError("Aucune grille exploitable")
    if ecartes:
        ctx.journal("  {} liste(s) écartée(s) : thème répété, ou trop peu de "
                    "mots utilisables.".format(ecartes))
    if perdus:
        ctx.journal("  {} mot(s) écarté(s) : doublon, trop long pour la "
                    "grille, contenu dans un autre, ou impossible à "
                    "placer.".format(perdus))
    # Un cahier de vingt-six grilles vendu pour trente est un cahier troue,
    # et c'est a l'etape de le porter, pas au journal seul.
    if not redaction.manquants:
        ctx.etape("grilles", "anomalie" if len(grilles) < nombre else "ok",
                  "{} grille(s) sur {} demandées".format(len(grilles), nombre))
    if len(grilles) != nombre:
        titre = renommer(ctx, t["meles_titre"].format(nombre=len(grilles),
                                                      sujet=ctx.sujet))

    ctx.journal("Étape 2/2 — mise en page, A4 et Lettre US...")
    fichiers = _exporter(ctx, titre, grilles, difficulte, caracteres, t)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "grilles": len(grilles),
        "mots": sum(len(g["mots"]) for g in grilles),
        "difficulte": difficulte,
        "caracteres": caracteres,
        "fichiers": [f.name for f in fichiers],
        "budget_epuise": redaction.budget_epuise,
    }
    terminer(ctx, fichiers, {"grilles": len(grilles), "difficulte": difficulte,
                             "caracteres": caracteres,
                             "manquants": redaction.manquants})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _exporter(ctx: Contexte, titre: str, grilles: List[Dict[str, Any]],
              difficulte: str, caracteres: str, t: Dict[str, Any]) -> List[Path]:
    gros = caracteres == "gros"
    niveau = t["meles_niveaux"][difficulte]
    sous_titre = (t["meles_sous_titre_gros"] if gros
                  else t["meles_sous_titre"]).format(niveau=niveau)
    regle = t["meles_regle"].format(directions=t["meles_directions"][difficulte])
    blocs = [livraison.Bloc(titre=t["meles_regle_titre"], corps=regle)]
    for numero, grille in enumerate(grilles, 1):
        blocs.append(livraison.Bloc(
            titre=t["meles_grille"].format(numero=numero, theme=grille["theme"]),
            corps=rendu.markdown_grille(grille, t),
            rendu_pdf=rendu.page_de_grille(grille, t, gros),
            sommaire=False))
    blocs.append(livraison.Bloc(
        titre=t["meles_solutions"], corps=rendu.markdown_solutions(grilles, t),
        rendu_pdf=rendu.pages_de_solutions(grilles, t), sommaire=False))

    produit = livraison.Produit(
        type="mots-meles", titre=titre, sous_titre=sous_titre,
        promesse=t["meles_promesse"], blocs=blocs,
        donnees={"titre": titre, "difficulte": difficulte,
                 "caracteres": caracteres, "grilles": grilles},
        nom_donnees="grilles",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica", marge=54.0,
        style_couverture="word search puzzle book cover, letters grid, playful",
        nom_fichier=slug(titre, 44),
        sommaire=False,
        suffixe_pdf="-A4",
        libelle_sections=t["unite_sections"],
    )
    # Le marche anglophone imprime en Lettre US : la meme composition, sur
    # l'autre format de page. Composee par le meme code que l'A4, pas copiee.
    produit.documents.append((t["fichier_lettre_us"], lambda couverture:
                              livraison.composer_pdf(
                                  livraison.au_format(produit, LETTRE), ctx,
                                  couverture)))
    return livraison.livrer(ctx, produit)
