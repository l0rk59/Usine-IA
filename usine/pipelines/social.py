"""Pack de contenu reseaux sociaux : calendrier editorial, posts et visuels."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..core import images, llm
from ..render import livraison
from ..render.page import ecrire_page
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

ROLE = "un strategiste de contenu qui ecrit des posts qui font reagir, sans clickbait"

RESEAUX = {
    "linkedin": "LinkedIn (ton professionnel, 120-220 mots, paragraphes d'une ligne, "
                "une accroche forte en premiere ligne, pas de hashtags excessifs)",
    "instagram": "Instagram (legende de 60-140 mots, ton direct, emojis avec parcimonie, "
                 "appel a commenter, 5 a 8 hashtags pertinents)",
    "x": "X/Twitter (fil de 4 a 7 messages de 240 caracteres maximum chacun, "
         "separes par une ligne '---')",
    "tiktok": "TikTok (script video de 30 a 45 secondes : accroche 3 secondes, "
              "3 points, conclusion + appel a l'action)",
}


def _calendrier(ctx: Contexte, nombre: int, reseau: str) -> List[Dict[str, Any]]:
    invite = (
        "Construis un calendrier editorial de {n} publications sur : {sujet}\n"
        "AUDIENCE : {audience}\nRESEAU : {reseau}\n\n"
        "Varie les angles : retour d'experience, erreur courante, methode, coulisses, "
        "opinion argumentee, cas chiffre, question ouverte, ressource utile.\n"
        "Aucun doublon d'angle sur deux publications consecutives.\n\n"
        "Schema JSON exact :\n"
        '{{"publications": [{{"jour": 1, "angle": "...", "sujet": "...", '
        '"accroche": "la premiere phrase du post", "objectif": "notoriete|engagement|vente"}}]}}'
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience,
             reseau=RESEAUX.get(reseau, reseau))
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                               temperature=0.8, max_tokens=3500)
    publications = donnees.get("publications") if isinstance(donnees, dict) else donnees
    propres = []
    for index, publication in enumerate(publications or [], 1):
        if not isinstance(publication, dict):
            continue
        propres.append(
            {
                "jour": int(publication.get("jour") or index),
                "angle": str(publication.get("angle") or "").strip(),
                "sujet": nettoyer_titre(str(publication.get("sujet") or "")),
                "accroche": str(publication.get("accroche") or "").strip(),
                "objectif": str(publication.get("objectif") or "engagement").strip(),
            }
        )
    if not propres:
        raise ValueError("Calendrier editorial vide")
    return propres[:nombre]


def _rediger_lot(ctx: Contexte, lot: List[Dict[str, Any]], reseau: str) -> List[Dict[str, str]]:
    descriptions = "\n".join(
        "{}. angle={} | sujet={} | accroche={}".format(
            p["jour"], p["angle"], p["sujet"], p["accroche"]
        )
        for p in lot
    )
    invite = (
        "Sujet general : {sujet}\nAudience : {audience}\n"
        "FORMAT DU RESEAU : {reseau}\n\n"
        "Redige integralement ces publications :\n{liste}\n\n"
        "Respecte scrupuleusement le format du reseau. Pas de formule creuse, "
        "pas de promesse de gain garanti.\n\n"
        "Schema JSON exact :\n"
        '{{"posts": [{{"jour": 1, "texte": "le post complet", '
        '"hashtags": "#un #deux", "visuel": "description en anglais de l\'image a generer"}}]}}'
    ).format(sujet=ctx.sujet, audience=ctx.audience,
             reseau=RESEAUX.get(reseau, reseau), liste=descriptions)
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="standard",
                               temperature=0.85, max_tokens=4096)
    posts = donnees.get("posts") if isinstance(donnees, dict) else donnees
    resultat = []
    for post in posts or []:
        if not isinstance(post, dict) or not post.get("texte"):
            continue
        resultat.append(
            {
                "jour": str(post.get("jour") or ""),
                "texte": str(post["texte"]).strip(),
                "hashtags": str(post.get("hashtags") or "").strip(),
                "visuel": str(post.get("visuel") or "").strip(),
            }
        )
    return resultat


def produire(ctx: Contexte, nombre: int = 30, reseau: str = "linkedin",
             visuels: int = 0) -> Dict[str, Any]:
    reseau = reseau.lower()
    ctx.journal("Etape 1/4 — calendrier editorial ({} posts, {})...".format(nombre, reseau))
    calendrier = _calendrier(ctx, nombre, reseau)
    titre = "{} posts {} — {}".format(nombre, reseau.capitalize(), ctx.sujet)
    dossier = preparer(ctx, "social", titre)
    ctx.etape("calendrier", "ok", "{} publications".format(len(calendrier)))

    ctx.journal("Etape 2/4 — redaction des publications...")
    posts: List[Dict[str, str]] = []
    taille_lot = 5
    lots = [calendrier[i : i + taille_lot] for i in range(0, len(calendrier), taille_lot)]
    for index, lot in enumerate(lots, 1):
        ctx.journal("  lot {}/{} ({} posts)".format(index, len(lots), len(lot)))
        try:
            posts.extend(_rediger_lot(ctx, lot, reseau))
        except Exception as exc:
            ctx.journal("     echec : {}".format(exc))
            ctx.etape("lot-{}".format(index), "echec", str(exc))
            posts.extend(
                {"jour": str(p["jour"]), "texte": p["accroche"], "hashtags": "", "visuel": ""}
                for p in lot
            )
    ctx.etape("redaction", "ok", "{} posts".format(len(posts)))

    ctx.journal("Etape 3/4 — visuels...")
    chemins_visuels: List[Path] = []
    if visuels > 0 and not ctx.sans_image and not ctx.hors_ligne:
        dossier_visuels = dossier / "visuels"
        for index, post in enumerate(posts[:visuels], 1):
            invite_visuel = post["visuel"] or "minimal abstract social media background"
            ctx.journal("  visuel {}/{}".format(index, min(visuels, len(posts))))
            chemin = images.generer_visuel(
                dossier_visuels, "post-{:02d}".format(index),
                "{}, flat vector, bold colors, no text, social media square".format(
                    invite_visuel
                ),
            )
            if chemin:
                chemins_visuels.append(chemin)
    ctx.etape("visuels", "ok", "{} images".format(len(chemins_visuels)))

    ctx.journal("Etape 4/4 — export...")
    fichiers = _exporter(ctx, titre, reseau, calendrier, posts)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "posts": len(posts),
        "visuels": len(chemins_visuels),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"posts": len(posts), "reseau": reseau})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _exporter(ctx: Contexte, titre: str, reseau: str, calendrier: List[Dict[str, Any]],
              posts: List[Dict[str, str]]) -> List[Path]:
    dossier = ctx.dossier
    fichiers: List[Path] = []

    chemin_csv = dossier / "calendrier.csv"
    with chemin_csv.open("w", encoding="utf-8", newline="") as flux:
        auteur = csv.writer(flux)
        auteur.writerow(["Jour", "Angle", "Objectif", "Texte", "Hashtags", "Idee de visuel"])
        index_calendrier = {str(p["jour"]): p for p in calendrier}
        for post in posts:
            reference = index_calendrier.get(post["jour"], {})
            auteur.writerow([
                post["jour"], reference.get("angle", ""), reference.get("objectif", ""),
                post["texte"], post["hashtags"], post["visuel"],
            ])
    fichiers.append(chemin_csv)

    lignes = ["# {}\n".format(titre)]
    for post in posts:
        lignes.append("\n## Jour {}\n".format(post["jour"]))
        lignes.append(post["texte"])
        if post["hashtags"]:
            lignes.append("\n`{}`\n".format(post["hashtags"]))
    chemin_md = dossier / "posts.md"
    chemin_md.write_text("\n".join(lignes), encoding="utf-8")
    fichiers.append(chemin_md)

    chemin_json = dossier / "posts.json"
    chemin_json.write_text(
        json.dumps({"titre": titre, "reseau": reseau, "calendrier": calendrier,
                    "posts": posts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fichiers.append(chemin_json)

    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            ctx.dossier, titre, "Calendrier editorial pret a publier",
            ctx.auteur, marque=getattr(ctx, "marque", "") or "")
        fichiers.append(couverture)
    doc = livraison.document(ctx, titre, "Calendrier editorial pret a publier",
                             couverture, police_corps="Helvetica")
    doc.titre("Mode d'emploi", 1)
    doc.paragraphe(
        "Publiez une piece de contenu par jour ouvre. Adaptez les chiffres et les "
        "exemples a votre realite : un post credible vaut mieux qu'un post parfait. "
        "Le fichier calendrier.csv s'importe directement dans un tableur ou un outil "
        "de programmation.",
        justifier=True,
    )
    for post in posts:
        doc.titre("Jour {}".format(post["jour"]), 2)
        doc.paragraphe(post["texte"], taille=10.5)
        if post["hashtags"]:
            doc.paragraphe(post["hashtags"], taille=9.5, police="Helvetica-Oblique")
        doc.separateur()
    doc.inserer_sommaire(apres=1)
    chemin_pdf = dossier / "{}.pdf".format(slug(titre, 46))
    doc.enregistrer(chemin_pdf)
    fichiers.append(chemin_pdf)

    corps = []
    for post in posts:
        corps.append("<h2>Jour {}</h2>".format(post["jour"]))
        corps.append("<pre>{}</pre>".format(
            post["texte"].replace("&", "&amp;").replace("<", "&lt;")
        ))
        if post["hashtags"]:
            corps.append("<p><code>{}</code></p>".format(post["hashtags"]))
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), "Pack de contenu " + reseau, ctx.auteur)
    fichiers.append(chemin_html)
    return fichiers
