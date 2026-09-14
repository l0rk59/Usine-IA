"""Pack de prompts : produit digital rapide a fabriquer et facile a vendre."""

from __future__ import annotations


import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import document as D
from ..render import livraison
from .base import Contexte, nettoyer_titre, preparer, slug, terminer


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
    donnees = equipe.BIBLIOTHECAIRE.travailler_json(
        ctx, invite, role_modele="costaud",
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
    donnees = equipe.BIBLIOTHECAIRE.travailler_json(
        ctx, invite, role_modele="standard",
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
        perdu = ""
        try:
            categorie["details"] = _rediger_lot(ctx, categorie)
        except Exception as exc:
            perdu = str(exc)
            ctx.journal("     echec : {}".format(exc))
            # Les prompts sont remplaces par leur seul intitule : une liste de
            # titres la ou l'acheteur paie des prompts rediges.
            categorie["details"] = [
                {"titre": p, "quand": "", "prompt": p, "astuce": ""}
                for p in categorie["prompts"]
            ]
        # Un seul appel, apres coup, qui REGARDE ce qui vient de se passer.
        # La version d'avant notait « echec » dans la branche d'erreur puis
        # « ok » hors du « except » : le second ecrasait le premier, et un
        # pack entierement remplace par ses intitules se livrait « pret ».
        ctx.etape("categorie-{}".format(index),
                  "echec" if perdu else "ok",
                  perdu or categorie["nom"])

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
    """Prepare le produit et le confie a l'assemblage commun.

    Seules la mise en page PDF et la structure HTML sont propres aux prompts :
    le reste — couverture, markdown, CSV, JSON, sommaire — est identique a tous
    les autres types et vit dans usine/render/livraison.py.
    """
    sous_titre = "Pret a copier-coller"

    def mode_emploi(doc) -> None:
        doc.paragraphe(
            "Chaque prompt est autonome. Remplacez les variables entre crochets par vos "
            "informations, puis collez le texte dans l'IA de votre choix (Claude, ChatGPT, "
            "Gemini, Mistral ou un modele local). Les prompts sont classes par intention : "
            "commencez par la categorie qui correspond a votre tache du jour.",
            justifier=True)
        doc.encadre(
            "Conseil",
            "Gardez le contexte d'une conversation a l'autre : plus l'IA connait votre "
            "activite, meilleurs sont les resultats. Collez d'abord un descriptif de votre "
            "activite, puis enchainez les prompts du pack.")

    # Sans « corps », ce bloc n'existe que dans le PDF : la page HTML livree
    # s'ouvrait sur la premiere categorie, sans mode d'emploi. Le defaut est
    # muet — un bloc vide ne rend rien et ne se plaint pas.
    blocs = [livraison.Bloc(
        titre="Comment utiliser ce pack",
        corps="Chaque prompt est autonome. Remplacez les variables entre "
              "crochets par vos informations, puis collez le texte dans "
              "l'IA de votre choix (Claude, ChatGPT, Gemini, Mistral ou un "
              "modele local). Les prompts sont classes par intention : "
              "commencez par la categorie qui correspond a votre tache du "
              "jour.\n\n"
              "**Conseil** — gardez le contexte d'une conversation a "
              "l'autre : plus l'IA connait votre activite, meilleurs sont "
              "les resultats. Collez d'abord un descriptif de votre "
              "activite, puis enchainez les prompts du pack.",
        rendu_pdf=mode_emploi)]
    for categorie in categories:
        blocs.append(livraison.Bloc(
            titre=categorie["nom"],
            corps=_markdown_categorie(categorie),
            rendu_pdf=_mise_en_page(categorie),
            rendu_html=_html_categorie(categorie),
        ))

    produit = livraison.Produit(
        type="prompts", titre=titre, sous_titre=sous_titre,
        promesse=sous_titre, blocs=blocs,
        tableaux=[livraison.Tableau(
            nom="prompts",
            colonnes=["Categorie", "Titre", "Quand l'utiliser", "Prompt", "Astuce"],
            lignes=[[categorie["nom"], detail["titre"], detail["quand"],
                     detail["prompt"], detail["astuce"]]
                    for categorie in categories
                    for detail in categorie.get("details", [])])],
        donnees={"titre": titre, "categories": categories},
        nom_donnees="prompts",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture="abstract tech pattern, prompt library",
        nom_fichier=slug(titre, 48),
    )
    return livraison.livrer(ctx, produit)


def _markdown_categorie(categorie: Dict[str, Any]) -> str:
    lignes = []
    if categorie["intention"]:
        lignes.append("*{}*\n".format(categorie["intention"]))
    for detail in categorie.get("details", []):
        lignes.append("\n## {}\n".format(detail["titre"]))
        if detail["quand"]:
            lignes.append("**Quand l'utiliser :** {}\n".format(detail["quand"]))
        lignes.append("```\n{}\n```\n".format(detail["prompt"]))
        if detail["astuce"]:
            lignes.append("**Astuce :** {}\n".format(detail["astuce"]))
    return "\n".join(lignes)


def _mise_en_page(categorie: Dict[str, Any]):
    """Rendu PDF d'une categorie : chaque prompt dans son encadre."""

    def rendre(doc) -> None:
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

    return rendre


def _html_categorie(categorie: Dict[str, Any]) -> str:
    corps = []
    for detail in categorie.get("details", []):
        corps.append("<h3>{}</h3>".format(detail["titre"]))
        if detail["quand"]:
            corps.append("<p><em>{}</em></p>".format(detail["quand"]))
        corps.append(D.vers_html(D.analyser("```\n{}\n```".format(detail["prompt"]))))
        if detail["astuce"]:
            corps.append(
                '<aside class="encadre"><p class="encadre-titre">Astuce</p>'
                "<p>{}</p></aside>".format(detail["astuce"]))
    return "\n".join(corps)
