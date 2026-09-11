"""Pack de prompts : produit digital rapide a fabriquer et facile a vendre."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..core import images, llm
from ..render import document as D
from ..render.page import ecrire_page
from ..render.pdf import DocumentPDF
from .base import Contexte, nettoyer_titre, preparer, terminer

ROLE = "un ingenieur prompt qui concoit des bibliotheques de prompts professionnelles"


def _categories(ctx: Contexte, nombre: int) -> List[Dict[str, Any]]:
    invite = (
        "Organise un pack de {n} prompts professionnels sur le theme : {sujet}\n"
        "UTILISATEUR : {audience}\n\n"
        "Repartis les prompts en 5 a 7 categories utiles (par exemple : strategie, "
        "creation, analyse, vente, automatisation), chacune orientee vers un resultat "
        "de travail concret.\n\n"
        "Schema JSON exact :\n"
        '{{"categories": [{{"nom": "...", "intention": "...", '
        '"prompts": ["intitule court du prompt 1", "intitule court du prompt 2"]}}]}}\n'
        "Au total exactement {n} intitules repartis entre les categories."
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience)
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                               temperature=0.7, max_tokens=2600)
    categories = donnees.get("categories") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for categorie in categories or []:
        intitules = categorie.get("prompts") or []
        if not intitules:
            continue
        propres.append(
            {
                "nom": nettoyer_titre(str(categorie.get("nom") or "Categorie")),
                "intention": str(categorie.get("intention") or "").strip(),
                "prompts": [str(p).strip() for p in intitules if str(p).strip()],
            }
        )
    if not propres:
        raise ValueError("Aucune categorie de prompts exploitable")
    return propres


def _rediger_lot(ctx: Contexte, categorie: Dict[str, Any]) -> List[Dict[str, str]]:
    """Redige les prompts complets d'une categorie, en un seul appel."""
    invite = (
        "Theme du pack : {sujet}\nUtilisateur : {audience}\n"
        "CATEGORIE : {nom} — {intention}\n"
        "Redige la version complete de chacun de ces prompts :\n{liste}\n\n"
        "Pour chaque prompt :\n"
        "- 'titre' : l'intitule, reformule pour etre vendeur et clair.\n"
        "- 'quand' : en une phrase, dans quelle situation l'utiliser.\n"
        "- 'prompt' : le prompt complet, pret a coller dans une IA. Il doit assigner un "
        "role, donner le contexte, preciser le format de sortie attendu, et contenir "
        "des variables entre crochets comme [VOTRE PRODUIT] ou [AUDIENCE]. "
        "150 a 260 mots.\n"
        "- 'astuce' : une phrase pour ameliorer le resultat.\n\n"
        "Schema JSON exact :\n"
        '{{"prompts": [{{"titre": "...", "quand": "...", "prompt": "...", '
        '"astuce": "..."}}]}}'
    ).format(
        sujet=ctx.sujet,
        audience=ctx.audience,
        nom=categorie["nom"],
        intention=categorie["intention"],
        liste="\n".join("- " + p for p in categorie["prompts"]),
    )
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="standard",
                               temperature=0.72, max_tokens=4096)
    elements = donnees.get("prompts") if isinstance(donnees, dict) else donnees
    resultat: List[Dict[str, str]] = []
    for element in elements or []:
        if not isinstance(element, dict) or not element.get("prompt"):
            continue
        resultat.append(
            {
                "titre": nettoyer_titre(str(element.get("titre") or "Prompt")),
                "quand": str(element.get("quand") or "").strip(),
                "prompt": str(element.get("prompt")).strip(),
                "astuce": str(element.get("astuce") or "").strip(),
            }
        )
    return resultat


def produire(ctx: Contexte, nombre: int = 50) -> Dict[str, Any]:
    ctx.journal("Etape 1/3 — plan du pack ({} prompts)...".format(nombre))
    categories = _categories(ctx, nombre)
    titre = "{} prompts pour {}".format(nombre, ctx.sujet.lower())
    dossier = preparer(ctx, "prompts", titre)
    ctx.etape("plan", "ok", "{} categories".format(len(categories)))

    ctx.journal("Etape 2/3 — redaction des prompts...")
    for index, categorie in enumerate(categories, 1):
        ctx.journal("  [{}/{}] {}".format(index, len(categories), categorie["nom"]))
        try:
            categorie["details"] = _rediger_lot(ctx, categorie)
        except Exception as exc:
            ctx.journal("     echec : {}".format(exc))
            ctx.etape("categorie-{}".format(index), "echec", str(exc))
            categorie["details"] = [
                {"titre": p, "quand": "", "prompt": p, "astuce": ""}
                for p in categorie["prompts"]
            ]
        ctx.etape("categorie-{}".format(index), "ok", categorie["nom"])

    ctx.journal("Etape 3/3 — export...")
    fichiers = _exporter(ctx, titre, categories)
    total = sum(len(c.get("details", [])) for c in categories)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "prompts": total,
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"prompts": total})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _exporter(ctx: Contexte, titre: str, categories: List[Dict[str, Any]]) -> List[Path]:
    dossier = ctx.dossier
    fichiers: List[Path] = []

    # Markdown
    lignes = ["# {}\n".format(titre), "_Pack de prompts — {}_\n".format(ctx.auteur)]
    for categorie in categories:
        lignes.append("\n# {}\n".format(categorie["nom"]))
        if categorie["intention"]:
            lignes.append("*{}*\n".format(categorie["intention"]))
        for detail in categorie.get("details", []):
            lignes.append("\n## {}\n".format(detail["titre"]))
            if detail["quand"]:
                lignes.append("**Quand l'utiliser :** {}\n".format(detail["quand"]))
            lignes.append("```\n{}\n```\n".format(detail["prompt"]))
            if detail["astuce"]:
                lignes.append("**Astuce :** {}\n".format(detail["astuce"]))
    chemin_md = dossier / "prompts.md"
    chemin_md.write_text("\n".join(lignes), encoding="utf-8")
    fichiers.append(chemin_md)

    # CSV : import direct dans Notion, Airtable ou un tableur
    chemin_csv = dossier / "prompts.csv"
    with chemin_csv.open("w", encoding="utf-8", newline="") as flux:
        auteur = csv.writer(flux)
        auteur.writerow(["Categorie", "Titre", "Quand l'utiliser", "Prompt", "Astuce"])
        for categorie in categories:
            for detail in categorie.get("details", []):
                auteur.writerow([categorie["nom"], detail["titre"], detail["quand"],
                                 detail["prompt"], detail["astuce"]])
    fichiers.append(chemin_csv)

    # JSON : reutilisable dans une application
    chemin_json = dossier / "prompts.json"
    chemin_json.write_text(
        json.dumps({"titre": titre, "categories": categories}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fichiers.append(chemin_json)

    # Couverture
    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, titre, "Pret a copier-coller", ctx.auteur,
            style="abstract tech pattern, prompt library",
            en_ligne=not ctx.hors_ligne,
        )
        fichiers.append(couverture)

    # PDF
    doc = DocumentPDF(titre_courant=titre, police_corps="Helvetica")
    octets = couverture.read_bytes() if (
        couverture and couverture.suffix.lower() in (".jpg", ".jpeg")
    ) else None
    doc.page_couverture(titre, "Pret a copier-coller", ctx.auteur, image_jpeg=octets)
    doc.titre("Comment utiliser ce pack", 1)
    doc.paragraphe(
        "Chaque prompt est autonome. Remplacez les variables entre crochets par vos "
        "informations, puis collez le texte dans l'IA de votre choix (Claude, ChatGPT, "
        "Gemini, Mistral ou un modele local). Les prompts sont classes par intention : "
        "commencez par la categorie qui correspond a votre tache du jour.",
        justifier=True,
    )
    doc.encadre(
        "Conseil",
        "Gardez le contexte d'une conversation a l'autre : plus l'IA connait votre "
        "activite, meilleurs sont les resultats. Collez d'abord un descriptif de votre "
        "activite, puis enchainez les prompts du pack.",
    )
    for categorie in categories:
        doc.titre(categorie["nom"], 1)
        if categorie["intention"]:
            doc.citation(categorie["intention"])
        for detail in categorie.get("details", []):
            doc.titre(detail["titre"], 2)
            if detail["quand"]:
                doc.paragraphe("Quand l'utiliser : " + detail["quand"], taille=10,
                               police="Helvetica-Oblique")
            doc.encadre("Prompt", detail["prompt"])
            if detail["astuce"]:
                doc.paragraphe("Astuce : " + detail["astuce"], taille=10,
                               police="Helvetica-Oblique")
    doc.inserer_sommaire(apres=1)
    from .base import slug

    chemin_pdf = dossier / "{}.pdf".format(slug(titre, 48))
    doc.enregistrer(chemin_pdf)
    fichiers.append(chemin_pdf)

    # HTML
    corps = []
    for categorie in categories:
        corps.append("<h2>{}</h2>".format(categorie["nom"]))
        for detail in categorie.get("details", []):
            corps.append("<h3>{}</h3>".format(detail["titre"]))
            if detail["quand"]:
                corps.append("<p><em>{}</em></p>".format(detail["quand"]))
            corps.append(D.vers_html(D.analyser("```\n{}\n```".format(detail["prompt"]))))
            if detail["astuce"]:
                corps.append(
                    '<aside class="encadre"><p class="encadre-titre">Astuce</p>'
                    "<p>{}</p></aside>".format(detail["astuce"])
                )
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), "Pack de prompts", ctx.auteur,
                couverture=couverture.name if couverture else None)
    fichiers.append(chemin_html)
    return fichiers
