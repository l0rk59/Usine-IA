"""Recherche d'idees de produits : que fabriquer, pour qui, a quel prix."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..core import config, llm
from ..render import document as D
from ..render.page import ecrire_page
from .base import Contexte, nettoyer_titre

ROLE = (
    "un analyste de marche des produits digitaux, lucide sur ce qui se vend "
    "reellement et sur la saturation des niches"
)


def explorer(ctx: Contexte, nombre: int = 12) -> List[Dict[str, Any]]:
    invite = (
        "NICHE : {niche}\nAUDIENCE VISEE : {audience}\n\n"
        "Propose {n} idees de produits digitaux realisables par une seule personne, "
        "sans stock ni equipe, livrables en fichiers telechargeables "
        "(ebook, pack de prompts, mini-formation, boite a outils, pack de contenu).\n\n"
        "Sois honnete : signale la concurrence quand elle est forte, et evite les "
        "idees qui exigent une expertise certifiee (medical, juridique, financier "
        "reglemente).\n\n"
        "Schema JSON exact :\n"
        '{{"idees": [{{"titre": "...", "type": "ebook|prompts|formation|outils|social", '
        '"probleme": "le probleme precis resolu", "acheteur": "qui paie et pourquoi", '
        '"promesse": "...", "prix_eur": 19, "difficulte": "facile|moyenne|elevee", '
        '"concurrence": "faible|moyenne|forte", '
        '"angle_differenciant": "...", "premier_canal": "ou trouver les 10 premiers '
        'acheteurs"}}]}}'
    ).format(niche=ctx.sujet, audience=ctx.audience, n=nombre)
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                               temperature=0.85, max_tokens=4096)
    idees = donnees.get("idees") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for idee in idees or []:
        if not isinstance(idee, dict) or not idee.get("titre"):
            continue
        type_produit = str(idee.get("type") or "ebook").lower().strip()
        if type_produit not in ("ebook", "prompts", "formation", "outils", "social"):
            type_produit = "ebook"
        propres.append(
            {
                "titre": nettoyer_titre(str(idee["titre"])),
                "type": type_produit,
                "probleme": str(idee.get("probleme") or "").strip(),
                "acheteur": str(idee.get("acheteur") or "").strip(),
                "promesse": str(idee.get("promesse") or "").strip(),
                "prix_eur": idee.get("prix_eur") or 19,
                "difficulte": str(idee.get("difficulte") or "moyenne").strip(),
                "concurrence": str(idee.get("concurrence") or "moyenne").strip(),
                "angle_differenciant": str(idee.get("angle_differenciant") or "").strip(),
                "premier_canal": str(idee.get("premier_canal") or "").strip(),
            }
        )
    if not propres:
        raise ValueError("Aucune idee exploitable")
    return propres


def produire(ctx: Contexte, nombre: int = 12) -> Dict[str, Any]:
    ctx.journal("Exploration de la niche « {} »...".format(ctx.sujet))
    idees = explorer(ctx, nombre)

    config.ensure_dirs()
    from .base import slug

    dossier = config.PRODUITS_DIR / "idees-{}".format(slug(ctx.sujet, 40))
    dossier.mkdir(parents=True, exist_ok=True)

    (dossier / "idees.json").write_text(
        json.dumps({"niche": ctx.sujet, "idees": idees}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    chemin_csv = dossier / "idees.csv"
    with chemin_csv.open("w", encoding="utf-8", newline="") as flux:
        auteur = csv.DictWriter(flux, fieldnames=list(idees[0].keys()))
        auteur.writeheader()
        auteur.writerows(idees)

    lignes = ["# Idees de produits — {}\n".format(ctx.sujet)]
    for index, idee in enumerate(idees, 1):
        lignes.append("\n## {}. {}\n".format(index, idee["titre"]))
        lignes.append("- **Type :** {} | **Prix cible :** {} EUR | "
                      "**Difficulte :** {} | **Concurrence :** {}".format(
                          idee["type"], idee["prix_eur"],
                          idee["difficulte"], idee["concurrence"]))
        lignes.append("- **Probleme :** {}".format(idee["probleme"]))
        lignes.append("- **Acheteur :** {}".format(idee["acheteur"]))
        lignes.append("- **Promesse :** {}".format(idee["promesse"]))
        lignes.append("- **Angle :** {}".format(idee["angle_differenciant"]))
        lignes.append("- **Premier canal :** {}".format(idee["premier_canal"]))
        lignes.append("\n```\nusine {} \"{}\"\n```".format(idee["type"], idee["titre"]))
    markdown = "\n".join(lignes)
    (dossier / "idees.md").write_text(markdown, encoding="utf-8")
    ecrire_page(dossier / "idees.html", "Idees de produits — {}".format(ctx.sujet),
                D.vers_html(D.analyser(markdown), niveau_depart=1),
                sous_titre="{} pistes evaluees".format(len(idees)), meta=ctx.auteur)

    return {"niche": ctx.sujet, "idees": idees, "dossier": str(dossier)}
