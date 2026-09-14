"""Modeles prets a l'emploi : Notion, tableur, Airtable.

D'apres les classements 2026 des places de marche, c'est le produit digital le
plus vendu apres l'ebook : l'acheteur veut un systeme deja construit, pas un
cours sur la maniere de le construire.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..core import evenements, images
from ..render import document as D
from ..render import tableur
from ..render import livraison
from ..render.page import ecrire_page
from .base import Contexte, nettoyer_titre, preparer, slug, terminer


def _systeme(ctx: Contexte, nombre: int) -> Dict[str, Any]:
    invite = (
        "Concois un systeme de {n} bases liees, pret a importer dans Notion ou "
        "dans un tableur, sur le theme : {sujet}\n"
        "UTILISATEUR : {audience}\n\n"
        "Chaque base a des colonnes typees et un role precis dans le systeme. "
        "Prevois les relations entre bases (une colonne qui pointe vers une autre "
        "base) et au moins trois vues utiles par base.\n\n"
        "Types de colonne autorises : texte, texte_long, nombre, selection, "
        "multi_selection, date, case_a_cocher, url, email, relation, formule.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "nom commercial du systeme", "promesse": "...", '
        '"bases": [{{"nom": "...", "role": "a quoi elle sert", '
        '"colonnes": [{{"nom": "...", "type": "...", '
        '"options": ["si selection"], "description": "..."}}], '
        '"vues": [{{"nom": "...", "filtre": "...", "tri": "..."}}], '
        '"exemples": [["valeur1", "valeur2"]]}}], '
        '"mise_en_route": ["etape 1", "etape 2"]}}'
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience)
    systeme = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=4096)
    if not isinstance(systeme, dict) or not systeme.get("bases"):
        raise ValueError("Systeme de modeles invalide")
    systeme["titre"] = nettoyer_titre(str(systeme.get("titre") or ctx.sujet))
    bases = []
    for base in systeme["bases"][:nombre]:
        if not isinstance(base, dict) or not base.get("colonnes"):
            continue
        colonnes = []
        for colonne in base["colonnes"]:
            if isinstance(colonne, str):
                colonne = {"nom": colonne, "type": "texte"}
            colonnes.append({
                "nom": str(colonne.get("nom") or "Colonne"),
                "type": str(colonne.get("type") or "texte"),
                "options": [str(o) for o in (colonne.get("options") or [])],
                "description": str(colonne.get("description") or ""),
            })
        bases.append({
            "nom": nettoyer_titre(str(base.get("nom") or "Base")),
            "role": str(base.get("role") or ""),
            "colonnes": colonnes,
            "vues": [v for v in (base.get("vues") or []) if isinstance(v, dict)],
            "exemples": [list(map(str, e)) for e in (base.get("exemples") or [])
                         if isinstance(e, (list, tuple))],
        })
    if not bases:
        raise ValueError("Aucune base exploitable")
    systeme["bases"] = bases
    return systeme


def produire(ctx: Contexte, nombre: int = 4) -> Dict[str, Any]:
    ctx.journal("Etape 1/3 — conception du systeme ({} bases)...".format(nombre))
    systeme = _systeme(ctx, nombre)
    titre = systeme["titre"]
    dossier = preparer(ctx, "modeles", titre)
    ctx.etape("systeme", "ok", "{} bases".format(len(systeme["bases"])))
    ctx.journal('  Systeme : « {} »'.format(titre))
    evenements.publier("section", etape="modeles", titre=titre,
                       total=len(systeme["bases"]))

    ctx.journal("Etape 2/3 — guide d'installation...")
    perdu = ""
    try:
        guide = equipe.REDACTEUR.travailler(ctx, (
            "Systeme : « {titre} »\nBASES : {bases}\n\n"
            "Redige le guide d'installation et d'utilisation (700 mots environ) :\n"
            "## Installation dans Notion\n(import du CSV, creation des relations)\n"
            "## Installation dans un tableur\n"
            "## Le rituel hebdomadaire\n(comment s'en servir chaque semaine)\n"
            "## Personnalisation\n\nMarkdown, pas de titre de niveau 1."
        ).format(titre=titre, bases=" ; ".join(b["nom"] for b in systeme["bases"])),
            max_tokens=2200).texte
    except Exception as exc:
        perdu = str(exc)
        ctx.journal("  guide indisponible : {}".format(exc))
        # Le guide est remplace par la liste des etapes de mise en route :
        # quelques puces la ou l'acheteur attend un mode d'emploi. Sans le
        # dire, le produit se presentait « pret » avec ce trou dedans.
        guide = "## Mise en route\n\n" + "\n".join(
            "1. " + str(e) for e in systeme.get("mise_en_route", []))
    # « ctx.etape("guide") » tout court valait « ok » — meme apres l'echec,
    # puisque l'appel est hors du « except ». Le meme defaut se cachait dans
    # la formation : noter le resultat APRES coup, sans regarder ce qui vient
    # de se passer, revient a ne rien noter.
    ctx.etape("guide", "echec" if perdu else "ok", perdu)

    ctx.journal("Etape 3/3 — export...")
    fichiers = _exporter(ctx, systeme, guide)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "bases": len(systeme["bases"]),
        "colonnes": sum(len(b["colonnes"]) for b in systeme["bases"]),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"bases": len(systeme["bases"])})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _exporter(ctx: Contexte, systeme: Dict[str, Any], guide: str) -> List[Path]:
    dossier = ctx.dossier
    titre = systeme["titre"]
    fichiers: List[Path] = []
    (dossier / "systeme.json").write_text(
        json.dumps(systeme, ensure_ascii=False, indent=2), encoding="utf-8")

    # Un CSV par base : c'est le format qu'importent Notion, Airtable et Sheets.
    dossier_csv = dossier / "a-importer"
    dossier_csv.mkdir(exist_ok=True)
    for index, base in enumerate(systeme["bases"], 1):
        chemin = dossier_csv / "{:02d}-{}.csv".format(index, slug(base["nom"], 40))
        with chemin.open("w", encoding="utf-8-sig", newline="") as flux:
            auteur = csv.writer(flux)
            auteur.writerow(tableur.ligne(c["nom"] for c in base["colonnes"]))
            for exemple in base["exemples"][:8]:
                ligne = list(exemple)[: len(base["colonnes"])]
                ligne += [""] * (len(base["colonnes"]) - len(ligne))
                auteur.writerow(tableur.ligne(ligne))
        fichiers.append(chemin)

    # Markdown : colle directement dans une page Notion.
    lignes = ["# {}\n".format(titre), "*{}*\n".format(systeme.get("promesse", "")),
              "\n" + guide + "\n"]
    for base in systeme["bases"]:
        lignes.append("\n# {}\n".format(base["nom"]))
        lignes.append("*{}*\n".format(base["role"]))
        lignes.append("\n| Colonne | Type | Role |")
        lignes.append("| --- | --- | --- |")
        for colonne in base["colonnes"]:
            options = (" (" + ", ".join(colonne["options"]) + ")"
                       if colonne["options"] else "")
            lignes.append("| {} | {}{} | {} |".format(
                colonne["nom"], colonne["type"], options, colonne["description"]))
        if base["vues"]:
            lignes.append("\n**Vues a creer :**\n")
            for vue in base["vues"]:
                lignes.append("- **{}** — filtre : {} — tri : {}".format(
                    vue.get("nom", ""), vue.get("filtre", "aucun"),
                    vue.get("tri", "aucun")))
    chemin_md = dossier / "modeles.md"
    chemin_md.write_text("\n".join(lignes), encoding="utf-8")
    fichiers.append(chemin_md)

    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, titre, systeme.get("promesse", ""), ctx.auteur,
            style="dashboard template cover, clean interface, organized grid",
            en_ligne=not ctx.hors_ligne)
        fichiers.append(couverture)

    doc = livraison.document(ctx, titre, systeme.get("promesse", ""),
                             couverture, police_corps="Helvetica")
    doc.titre("Guide d'installation", 1)
    D.vers_pdf(D.analyser(guide), doc, sauter_h1=True)
    for base in systeme["bases"]:
        doc.titre(base["nom"], 1)
        if base["role"]:
            doc.citation(base["role"])
        doc.titre("Structure", 2)
        doc.tableau(
            ["Colonne", "Type", "Role"],
            [[c["nom"], c["type"] + (" (" + ", ".join(c["options"]) + ")"
                                     if c["options"] else ""), c["description"]]
             for c in base["colonnes"]],
        )
        if base["vues"]:
            doc.titre("Vues a creer", 2)
            doc.liste(["{} — filtre : {} — tri : {}".format(
                v.get("nom", ""), v.get("filtre", "aucun"), v.get("tri", "aucun"))
                for v in base["vues"]])
    doc.inserer_sommaire(apres=1)
    chemin_pdf = dossier / "{}.pdf".format(slug(titre, 46))
    doc.enregistrer(chemin_pdf)
    fichiers.append(chemin_pdf)

    corps = [D.vers_html(D.analyser(guide), niveau_depart=2)]
    for base in systeme["bases"]:
        corps.append("<h2>{}</h2><p><em>{}</em></p>".format(base["nom"], base["role"]))
        corps.append("<table><tr><th>Colonne</th><th>Type</th><th>Role</th></tr>"
                     + "".join("<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                         c["nom"], c["type"], c["description"])
                         for c in base["colonnes"]) + "</table>")
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), systeme.get("promesse", ""),
                ctx.auteur, langue=ctx.langue_iso,
                couverture=couverture.name if couverture else None)
    fichiers.append(chemin_html)
    return fichiers
