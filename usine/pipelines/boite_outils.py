"""Boite a outils : checklists, modeles et plannings imprimables.

Produit digital a forte valeur percue et faible cout de production.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..core import images, llm
from ..render import document as D
from ..render.page import ecrire_page
from ..render.pdf import DocumentPDF
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

ROLE = "un consultant operationnel qui transforme des methodes en outils utilisables"


def _sommaire(ctx: Contexte, nombre: int) -> Dict[str, Any]:
    invite = (
        "Concois une boite a outils de {n} documents pratiques sur : {sujet}\n"
        "UTILISATEUR : {audience}\n\n"
        "Chaque outil est soit une checklist, soit un modele a completer, soit un "
        "tableau de suivi. Il doit s'utiliser en moins de 20 minutes et produire une "
        "decision ou un document.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "titre commercial de la boite a outils", '
        '"promesse": "...", '
        '"outils": [{{"nom": "...", "type": "checklist|modele|tableau", '
        '"quand": "dans quelle situation l\'utiliser", '
        '"resultat": "ce que l\'utilisateur obtient"}}]}}'
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience)
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                               temperature=0.68, max_tokens=2600)
    if not isinstance(donnees, dict) or not donnees.get("outils"):
        raise ValueError("Sommaire de boite a outils invalide")
    donnees["titre"] = nettoyer_titre(str(donnees.get("titre") or ctx.sujet))
    outils = []
    for outil in donnees["outils"][:nombre]:
        if isinstance(outil, str):
            outil = {"nom": outil}
        type_outil = str(outil.get("type") or "checklist").lower()
        if type_outil not in ("checklist", "modele", "tableau"):
            type_outil = "checklist"
        outils.append(
            {
                "nom": nettoyer_titre(str(outil.get("nom") or "Outil")),
                "type": type_outil,
                "quand": str(outil.get("quand") or "").strip(),
                "resultat": str(outil.get("resultat") or "").strip(),
            }
        )
    donnees["outils"] = outils
    return donnees


def _remplir(ctx: Contexte, boite: Dict[str, Any], outil: Dict[str, Any]) -> Dict[str, Any]:
    if outil["type"] == "tableau":
        consigne = (
            "Definis un tableau de suivi : 4 a 6 colonnes et 3 lignes d'exemple remplies.\n"
            'Schema JSON : {"intro": "...", "colonnes": ["..."], '
            '"exemples": [["...", "..."]], "conseils": ["...", "..."]}'
        )
    elif outil["type"] == "modele":
        consigne = (
            "Redige un modele a completer avec des variables entre crochets, decoupe en "
            "sections.\n"
            'Schema JSON : {"intro": "...", "sections": [{"titre": "...", '
            '"contenu": "le texte du modele avec des [VARIABLES]"}], '
            '"conseils": ["...", "..."]}'
        )
    else:
        consigne = (
            "Redige une checklist de 10 a 16 points verifiables, ordonnes, formules a "
            "l'imperatif et commencant par un verbe d'action.\n"
            'Schema JSON : {"intro": "...", "points": ["...", "..."], '
            '"conseils": ["...", "..."]}'
        )
    invite = (
        "Boite a outils : « {boite} »\nOUTIL : {nom} (type : {type})\n"
        "QUAND L'UTILISER : {quand}\nRESULTAT ATTENDU : {resultat}\n"
        "CONTEXTE : {sujet} — pour {audience}\n\n{consigne}"
    ).format(
        boite=boite["titre"], nom=outil["nom"], type=outil["type"],
        quand=outil["quand"], resultat=outil["resultat"],
        sujet=ctx.sujet, audience=ctx.audience, consigne=consigne,
    )
    contenu = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="standard",
                               temperature=0.7, max_tokens=3000)
    return contenu if isinstance(contenu, dict) else {"intro": "", "points": []}


def produire(ctx: Contexte, nombre: int = 10) -> Dict[str, Any]:
    ctx.journal("Etape 1/3 — sommaire de la boite a outils ({} outils)...".format(nombre))
    boite = _sommaire(ctx, nombre)
    titre = boite["titre"]
    dossier = preparer(ctx, "boite-outils", titre)
    ctx.etape("sommaire", "ok", "{} outils".format(len(boite["outils"])))
    ctx.journal('  Boite : « {} »'.format(titre))

    ctx.journal("Etape 2/3 — redaction des outils...")
    for index, outil in enumerate(boite["outils"], 1):
        ctx.journal("  [{}/{}] {} ({})".format(index, len(boite["outils"]),
                                               outil["nom"], outil["type"]))
        try:
            outil["contenu"] = _remplir(ctx, boite, outil)
            ctx.etape("outil-{}".format(index), "ok", outil["nom"])
        except Exception as exc:
            ctx.journal("     echec : {}".format(exc))
            ctx.etape("outil-{}".format(index), "echec", str(exc))
            outil["contenu"] = {"intro": outil["resultat"], "points": []}

    ctx.journal("Etape 3/3 — export...")
    fichiers = _exporter(ctx, boite)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "outils": len(boite["outils"]),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"outils": len(boite["outils"])})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _markdown_outil(outil: Dict[str, Any]) -> str:
    contenu = outil.get("contenu") or {}
    morceaux = []
    if contenu.get("intro"):
        morceaux.append(str(contenu["intro"]))
    if contenu.get("points"):
        morceaux.append("\n".join("- [ ] " + str(p) for p in contenu["points"]))
    for section in contenu.get("sections") or []:
        if isinstance(section, dict):
            morceaux.append("### {}\n\n{}".format(
                section.get("titre", ""), section.get("contenu", "")
            ))
    if contenu.get("colonnes"):
        colonnes = [str(c) for c in contenu["colonnes"]]
        lignes = ["| " + " | ".join(colonnes) + " |",
                  "| " + " | ".join("---" for _ in colonnes) + " |"]
        for exemple in contenu.get("exemples") or []:
            cellules = [str(c) for c in exemple][: len(colonnes)]
            cellules += [""] * (len(colonnes) - len(cellules))
            lignes.append("| " + " | ".join(cellules) + " |")
        morceaux.append("\n".join(lignes))
    if contenu.get("conseils"):
        morceaux.append("**Astuce :** " + " ".join(str(c) for c in contenu["conseils"]))
    return "\n\n".join(morceaux)


def _exporter(ctx: Contexte, boite: Dict[str, Any]) -> List[Path]:
    dossier = ctx.dossier
    titre = boite["titre"]
    fichiers: List[Path] = []

    (dossier / "boite.json").write_text(
        json.dumps(boite, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lignes = ["# {}\n".format(titre), "*{}*\n".format(boite.get("promesse", ""))]
    for outil in boite["outils"]:
        lignes.append("\n# {}\n".format(outil["nom"]))
        if outil["quand"]:
            lignes.append("*Quand : {}*\n".format(outil["quand"]))
        lignes.append(_markdown_outil(outil))
    chemin_md = dossier / "boite-outils.md"
    chemin_md.write_text("\n".join(lignes), encoding="utf-8")
    fichiers.append(chemin_md)

    # Un CSV par tableau de suivi : directement exploitable dans un tableur
    for index, outil in enumerate(boite["outils"], 1):
        contenu = outil.get("contenu") or {}
        if outil["type"] != "tableau" or not contenu.get("colonnes"):
            continue
        chemin = dossier / "tableau-{:02d}-{}.csv".format(index, slug(outil["nom"], 30))
        with chemin.open("w", encoding="utf-8", newline="") as flux:
            auteur = csv.writer(flux)
            auteur.writerow([str(c) for c in contenu["colonnes"]])
            for exemple in contenu.get("exemples") or []:
                auteur.writerow([str(c) for c in exemple])
        fichiers.append(chemin)

    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, titre, boite.get("promesse", ""), ctx.auteur,
            style="toolkit cover, blueprint style, organized grid",
            en_ligne=not ctx.hors_ligne,
        )
        fichiers.append(couverture)

    doc = DocumentPDF(titre_courant=titre, police_corps="Helvetica")
    octets = couverture.read_bytes() if (
        couverture and couverture.suffix.lower() in (".jpg", ".jpeg")
    ) else None
    doc.page_couverture(titre, boite.get("promesse", ""), ctx.auteur, image_jpeg=octets)
    doc.titre("Comment utiliser cette boite a outils", 1)
    doc.paragraphe(
        "Ces documents sont faits pour etre imprimes ou remplis a l'ecran. Choisissez "
        "l'outil correspondant a votre situation du moment : chacun produit un resultat "
        "en une seule session de travail.",
        justifier=True,
    )
    for outil in boite["outils"]:
        doc.titre(outil["nom"], 1)
        if outil["quand"]:
            doc.citation("Quand l'utiliser : " + outil["quand"])
        contenu = outil.get("contenu") or {}
        if contenu.get("intro"):
            doc.paragraphe(str(contenu["intro"]), justifier=True)
        if contenu.get("points"):
            doc.titre("A verifier", 2)
            doc.cases_a_cocher([str(p) for p in contenu["points"]])
        for section in contenu.get("sections") or []:
            if isinstance(section, dict):
                doc.titre(str(section.get("titre", "")), 2)
                doc.paragraphe(str(section.get("contenu", "")), justifier=True)
        if contenu.get("colonnes"):
            doc.titre("Colonnes du tableau", 2)
            doc.liste([str(c) for c in contenu["colonnes"]])
            doc.titre("A completer", 2)
            doc.lignes_a_remplir(10)
        if contenu.get("conseils"):
            doc.encadre("Astuce", " ".join(str(c) for c in contenu["conseils"]))
    doc.inserer_sommaire(apres=1)
    chemin_pdf = dossier / "{}.pdf".format(slug(titre, 46))
    doc.enregistrer(chemin_pdf)
    fichiers.append(chemin_pdf)

    corps = []
    for outil in boite["outils"]:
        corps.append("<h2>{}</h2>".format(outil["nom"]))
        corps.append(D.vers_html(D.analyser(_markdown_outil(outil)), niveau_depart=3))
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), boite.get("promesse", ""), ctx.auteur,
                couverture=couverture.name if couverture else None)
    fichiers.append(chemin_html)
    return fichiers
