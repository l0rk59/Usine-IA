"""Pack de contenu reseaux sociaux : calendrier editorial, posts et visuels."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..core import images
from ..render import document as D
from ..render import livraison, tableur
from ..render.page import ecrire_page
from .base import (Contexte, nettoyer_titre, preparer, renommer, slug,
                   terminer)


SOURCES = {
    "RESEAUX": (
        "Consignes d'ecriture BATIES sur « LIMITES », donc relevees le "
        "15/09/2026 comme elles. Elles n'ont pas de source propre : elles en "
        "heritent. Les recopier a cote ferait deux chiffres pour la meme "
        "chose, et c'est celui de l'invite qui ferait ecrire des posts "
        "tronques."),
    "LIMITES": (
        "Limites de caracteres relevees le 15/09/2026 sur les recensements "
        "publics par plateforme. Donnee perissable : le plafond des legendes "
        "TikTok est passe de 2 200 a 4 000 caracteres en 2024, et rien dans "
        "l'usine ne l'aurait su."),
}

# Ce qu'une plateforme accepte, et ce qu'elle MONTRE avant de replier.
#
# Le second chiffre est celui qui compte, et il manquait. Un post LinkedIn
# peut faire trois mille caracteres — mais seuls les deux cent dix premiers
# s'affichent avant « voir plus ». Ecrire une accroche de trois lignes revient
# donc a ecrire pour personne : ce qui decide qu'on clique tient dans deux
# cent dix signes.
#
# La premiere version de ce module n'avait aucun de ces chiffres. Elle
# donnait « 120-220 mots » pour LinkedIn et « 240 caracteres » pour X, deux
# valeurs sans source — et la seconde laissait quarante caracteres inutilises
# par message sur un plafond reel de deux cent quatre-vingts.
LIMITES = {
    "linkedin": {"maximum": 3000, "avant_repli": 210},
    "instagram": {"maximum": 2200, "avant_repli": 125},
    "x": {"maximum": 280, "avant_repli": 280},
    "tiktok": {"maximum": 4000, "avant_repli": 120},
}

# Une adresse compte pour vingt-trois caracteres chez X, quelle que soit sa
# longueur. Un fil qui colle un lien dans chaque message perd donc vingt-trois
# signes par message sans que personne ne les voie partir.
CARACTERES_PAR_LIEN_X = 23

_GABARITS = {
    "linkedin": "LinkedIn (ton professionnel, paragraphes d'une ligne, pas de "
                "hashtags excessifs. Plafond {linkedin_max} caracteres, mais "
                "seuls les {linkedin_repli} premiers s'affichent avant « voir "
                "plus » : tout ce qui doit faire cliquer tient la)",
    "instagram": "Instagram (ton direct, emojis avec parcimonie, appel a "
                 "commenter, 5 a 8 hashtags pertinents. Plafond "
                 "{instagram_max} caracteres, repli apres "
                 "{instagram_repli})",
    "x": "X/Twitter (fil de 4 a 7 messages de {x_max} caracteres maximum "
         "chacun, separes par une ligne '---'. Une adresse compte pour "
         "{lien_x} caracteres quelle que soit sa longueur)",
    "tiktok": "TikTok (script video de 30 a 45 secondes : accroche 3 "
              "secondes, 3 points, conclusion + appel a l'action. La legende "
              "accepte {tiktok_max} caracteres, repli apres "
              "{tiktok_repli})",
}

# Les consignes sont BATIES sur les limites, jamais recopiees a cote : deux
# endroits pour le meme chiffre divergent, et c'est celui de l'invite qui
# ferait ecrire des posts tronques.
RESEAUX = {
    cle: texte.format(
        linkedin_max=LIMITES["linkedin"]["maximum"],
        linkedin_repli=LIMITES["linkedin"]["avant_repli"],
        instagram_max=LIMITES["instagram"]["maximum"],
        instagram_repli=LIMITES["instagram"]["avant_repli"],
        x_max=LIMITES["x"]["maximum"],
        tiktok_max=LIMITES["tiktok"]["maximum"],
        tiktok_repli=LIMITES["tiktok"]["avant_repli"],
        lien_x=CARACTERES_PAR_LIEN_X)
    for cle, texte in _GABARITS.items()
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
    donnees = equipe.ANIMATEUR.travailler_json(
        ctx, invite, role_modele="costaud",
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
    donnees = equipe.ANIMATEUR.travailler_json(
        ctx, invite, role_modele="standard",
                               temperature=0.85, max_tokens=4096)
    posts = donnees.get("posts") if isinstance(donnees, dict) else donnees
    resultat = []
    for post in posts or []:
        if not isinstance(post, dict) or not post.get("texte"):
            continue
        resultat.append(
            {
                "jour": str(post.get("jour") or ""),
                # Un reseau social n'interprete pas le markdown : un
                # « **mot** » du modele partait tel quel, etoiles comprises, dans
                # le post que le client copie sur LinkedIn.
                "texte": D.nettoyer_inline(str(post["texte"])),
                "hashtags": str(post.get("hashtags") or "").strip(),
                "visuel": D.nettoyer_inline(str(post.get("visuel") or "")),
            }
        )
    return resultat


def _titre(ctx: Contexte, combien: int, reseau: str) -> str:
    """Le titre annonce le nombre de posts REELLEMENT rediges.

    Il annoncait le nombre demande, arrete avant la redaction — le meme defaut
    que le pack de prompts, et pour la meme raison : c'est la seule des deux
    chaines qui se nomme par un chiffre. Un lot qui echoue est rattrape par
    ses accroches, mais un post rendu sans texte disparait sans que le titre
    bouge.
    """
    return "{} posts {} — {}".format(combien, reseau.capitalize(), ctx.sujet)


def produire(ctx: Contexte, nombre: int = 30, reseau: str = "linkedin",
             visuels: int = 0) -> Dict[str, Any]:
    reseau = reseau.lower()
    ctx.journal("Etape 1/4 — calendrier editorial ({} posts, {})...".format(nombre, reseau))
    calendrier = _calendrier(ctx, nombre, reseau)
    titre = _titre(ctx, len(calendrier), reseau)
    dossier = preparer(ctx, "social", titre)
    ctx.etape("calendrier",
              "anomalie" if len(calendrier) < nombre else "ok",
              "{} publications sur {} demandees".format(
                  len(calendrier), nombre))

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
    ctx.etape("redaction",
              "anomalie" if len(posts) < len(calendrier) else "ok",
              "{} posts pour {} au calendrier".format(
                  len(posts), len(calendrier)))

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
    if len(posts) != len(calendrier):
        titre = renommer(ctx, _titre(ctx, len(posts), reseau))
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
        auteur.writerow(tableur.ligne(
            ["Jour", "Angle", "Objectif", "Texte", "Hashtags",
             "Idee de visuel"]))
        index_calendrier = {str(p["jour"]): p for p in calendrier}
        for post in posts:
            reference = index_calendrier.get(post["jour"], {})
            auteur.writerow(tableur.ligne([
                post["jour"], reference.get("angle", ""),
                reference.get("objectif", ""),
                post["texte"], post["hashtags"], post["visuel"],
            ]))
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
    # Pas de sommaire. Mesure du 15/09/2026 : le PDF faisait quatre pages,
    # dont une entiere de sommaire — un quart du document pour lister « Mode
    # d'emploi » et quatre jours numerotes, qu'on trouve en tournant la page.
    # Un sommaire vaut sa page dans un livre, pas dans un calendrier.
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
            corps.append("<p><code>{}</code></p>".format(
                D.inline_html(post["hashtags"])))
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), "Pack de contenu " + reseau,
                ctx.auteur, langue=ctx.langue_iso)
    fichiers.append(chemin_html)
    return fichiers
