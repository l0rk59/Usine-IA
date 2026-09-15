"""Conte jeunesse : des doubles-pages, pas des chapitres.

Pourquoi une chaine a part. Un album se compose en DOUBLES-PAGES : deux ou
trois phrases par page, une image par page, et un nombre de pages qui est un
multiple contraint par la reliure. Faire passer cela par la chaine de fiction
donnerait un roman court avec des titres de scenes — c'est-a-dire tout ce
qu'un album n'est pas.

Ce que cette chaine ajoute, et qui n'existe nulle part ailleurs : elle
verifie que le texte produit correspond a la TRANCHE D'AGE demandee.

Et elle le fait sans inventer de seuil. Le plafond de mots par phrase n'est
pas une verite sur la lecture enfantine : c'est ce que l'usine a DEMANDE au
modele, ecrit ici, modifiable, et le controle mesure si la reponse s'y tient.
Comparer une sortie a la consigne qui l'a produite est verifiable ; affirmer
« une phrase de plus de douze mots est trop longue pour un enfant de cinq
ans » demanderait une etude qu'on n'a pas.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

from ..agents import equipe
from ..core import images
from ..render import livraison
from . import fiction
from .base import (Contexte, nettoyer_titre, preparer,
                   sans_titres, terminer)

# Tranche d'age -> (pages par defaut, mots par page, mots par phrase demandes).
# Les deux premiers chiffres suivent les longueurs d'album relevees dans
# « fiction.MOTS_ATTENDUS ». Le troisieme est une CONSIGNE, pas une mesure :
# c'est ce qu'on demande au modele, et le controle verifie qu'il s'y tient.
TRANCHES: Dict[str, Dict[str, int]] = {
    "3-5 ans": {"pages": 12, "mots_page": 35, "mots_phrase": 10},
    "6-8 ans": {"pages": 16, "mots_page": 70, "mots_phrase": 14},
    "9-12 ans": {"pages": 20, "mots_page": 140, "mots_phrase": 20},
}
TRANCHE_DEFAUT = "6-8 ans"
PAGES_MIN, PAGES_MAX = 6, 40


def reglages_de_tranche(tranche: str) -> Dict[str, int]:
    return TRANCHES.get(tranche) or TRANCHES[TRANCHE_DEFAUT]


def _pages(ctx: Contexte, tranche: str, pages: int) -> Dict[str, Any]:
    regle = reglages_de_tranche(tranche)
    invite = (
        "Ecris un conte pour enfants de {tranche}, en {n} doubles-pages.\n"
        "SUJET : {sujet}\n{promesse}\n"
        "Un album n'est pas un roman court. Chaque double-page porte UN "
        "moment, et l'image raconte ce que le texte ne dit pas.\n\n"
        "Contraintes, et elles comptent plus que le style :\n"
        "- environ {mots} mots par double-page ;\n"
        "- des phrases de {phrase} mots au maximum ;\n"
        "- un vocabulaire que l'enfant connait, sauf un ou deux mots neufs "
        "que le contexte explique ;\n"
        "- la derniere page referme l'histoire, sans morale ecrite en "
        "toutes lettres.\n\n"
        "Pour chaque double-page, donne aussi l'ILLUSTRATION : ce qu'on "
        "voit, en une phrase, sans texte dans l'image.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "...", "heros": "qui c\'est, en trois mots", '
        '"pages": [{{"numero": 1, "texte": "...", '
        '"illustration": "ce qu\'on voit"}}]}}'
    ).format(tranche=tranche, n=pages, sujet=ctx.sujet,
             mots=regle["mots_page"], phrase=regle["mots_phrase"],
             promesse=fiction.consignes(ctx))
    donnees = equipe.REDACTEUR.travailler_json(
        ctx, invite, role_modele="creatif", temperature=0.85, max_tokens=4000)
    if not isinstance(donnees, dict):
        raise ValueError("Conte illisible")
    propres = []
    for rang, brut in enumerate(donnees.get("pages") or [], 1):
        if not isinstance(brut, dict):
            continue
        texte = sans_titres(str(brut.get("texte") or ""))
        if not texte:
            continue
        propres.append({
            "numero": rang,
            "texte": texte,
            "illustration": str(brut.get("illustration") or "").strip(),
        })
    if not propres:
        raise ValueError("Aucune page exploitable")
    return {"titre": nettoyer_titre(str(donnees.get("titre") or ctx.sujet)),
            "heros": str(donnees.get("heros") or "").strip(),
            "pages": propres[:pages]}


def phrases(texte: str) -> List[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texte or "")
            if p.strip()]


def mesurer_l_age(pages: Sequence[Dict[str, Any]],
                  tranche: str) -> Dict[str, Any]:
    """Le texte produit tient-il la consigne de la tranche d'age ?

    Compare une sortie a la CONSIGNE qui l'a produite — pas a une verite sur
    la lecture enfantine. C'est ce qui rend cette mesure honnete : le plafond
    est ecrit dans « TRANCHES », il se modifie, et le controle ne pretend rien
    savoir de plus que « on a demande dix mots par phrase, en voici vingt ».
    """
    regle = reglages_de_tranche(tranche)
    plafond = regle["mots_phrase"]
    toutes = [p for page in pages for p in phrases(page.get("texte", ""))]
    longueurs = [len(p.split()) for p in toutes]
    trop_longues = [(page["numero"], len(p.split()))
                    for page in pages
                    for p in phrases(page.get("texte", ""))
                    if len(p.split()) > plafond]
    mots_par_page = [len((page.get("texte") or "").split()) for page in pages]
    return {
        "tranche": tranche,
        "plafond_demande": plafond,
        "phrases": len(toutes),
        "mots_par_phrase": (round(sum(longueurs) / len(longueurs), 1)
                            if longueurs else 0),
        "phrase_la_plus_longue": max(longueurs) if longueurs else 0,
        "phrases_trop_longues": trop_longues,
        "mots_par_page": (round(sum(mots_par_page) / len(mots_par_page), 1)
                          if mots_par_page else 0),
        "mots_page_demandes": regle["mots_page"],
        "pages_sans_illustration": [p["numero"] for p in pages
                                    if not p.get("illustration")],
    }


def lire_l_age(mesure: Dict[str, Any]) -> List[str]:
    """Ce que la mesure permet de dire, sans rien affirmer de plus."""
    lectures = []
    trop = mesure["phrases_trop_longues"]
    if trop:
        pages = sorted({numero for numero, _mots in trop})
        lectures.append(
            "{} phrase(s) depassent les {} mots demandes pour {} "
            "(jusqu'a {} mots), pages {}.".format(
                len(trop), mesure["plafond_demande"], mesure["tranche"],
                max(mots for _n, mots in trop),
                ", ".join(str(p) for p in pages[:8])))
    sans = mesure["pages_sans_illustration"]
    if sans:
        lectures.append(
            "Pages sans note d'illustration : {}. Dans un album, l'image "
            "porte la moitie du recit.".format(
                ", ".join(str(p) for p in sans[:8])))
    return lectures


def produire(ctx: Contexte, pages: int = 0,
             tranche: str = TRANCHE_DEFAUT) -> Dict[str, Any]:
    """Un conte en doubles-pages, avec ses illustrations quand c'est possible."""
    if tranche not in TRANCHES:
        tranche = TRANCHE_DEFAUT
    regle = reglages_de_tranche(tranche)
    demande = int(pages or ctx.chapitres or regle["pages"])
    demande = max(PAGES_MIN, min(demande, PAGES_MAX))

    ctx.journal("Etape 1/3 — le conte, {} doubles-pages pour {}...".format(
        demande, tranche))
    conte = _pages(ctx, tranche, demande)
    titre = conte["titre"]
    dossier = preparer(ctx, "conte", titre)
    mesure = mesurer_l_age(conte["pages"], tranche)
    lectures = lire_l_age(mesure)
    ctx.journal("  {} mots par phrase en moyenne (demande : {} au maximum), "
                "{} mots par page.".format(
                    mesure["mots_par_phrase"], mesure["plafond_demande"],
                    mesure["mots_par_page"]))
    for lecture in lectures:
        ctx.journal("  [!] " + lecture)
    ctx.etape("texte", "partiel" if lectures else "ok",
              "{} pages, {} phrases".format(len(conte["pages"]),
                                            mesure["phrases"]))

    ctx.journal("Etape 2/3 — illustrations...")
    illustrees = 0
    for page in conte["pages"]:
        if not page["illustration"] or ctx.sans_image:
            continue
        # Une illustration qui ne vient pas ne fait pas echouer le conte : la
        # note reste dans le livre, et l'acheteur peut la faire dessiner. Un
        # album sans images se vend mal ; un album qui n'existe pas ne se vend
        # pas du tout.
        chemin = images.generer_visuel(
            dossier / "images", "page-{:02d}".format(page["numero"]),
            "illustration d'album jeunesse, {}, sans aucun texte, {}".format(
                tranche, page["illustration"]),
            largeur=1024, hauteur=1024, en_ligne=not ctx.hors_ligne)
        if chemin is not None:
            page["image"] = chemin.name
            illustrees += 1
    ctx.journal("  {} image(s) sur {}".format(illustrees, len(conte["pages"])))
    ctx.etape("illustrations",
              "ok" if illustrees == len(conte["pages"]) else "partiel",
              "{} image(s)".format(illustrees))

    ctx.journal("Etape 3/3 — export...")
    blocs = []
    for page in conte["pages"]:
        corps = [page["texte"]]
        if page.get("image"):
            corps.append("![]({})".format("images/" + page["image"]))
        elif page["illustration"]:
            corps.append("*Illustration : {}*".format(page["illustration"]))
        blocs.append(livraison.Bloc(
            titre="Page {}".format(page["numero"]),
            corps="\n\n".join(corps)))
    produit = livraison.Produit(
        type="conte", titre=titre,
        sous_titre="{} doubles-pages — {}".format(len(conte["pages"]), tranche),
        promesse=conte["heros"],
        blocs=blocs,
        donnees={"conte": conte, "lisibilite": mesure},
        nom_donnees="conte",
        formats=("md", "pdf", "html", "epub", "txt"),
        libelle_sections="double(s)-page(s)",
    )
    fichiers = livraison.livrer(ctx, produit)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "pages": len(conte["pages"]),
        "tranche": tranche,
        "illustrations": illustrees,
        "lisibilite": mesure,
        "lectures": lectures,
        "mots": sum(len(p["texte"].split()) for p in conte["pages"]),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"pages": len(conte["pages"]), "tranche": tranche})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume
