"""Pack de prompts : produit digital rapide a fabriquer et facile a vendre."""

from __future__ import annotations


import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import document as D
from ..render import libelles, livraison
from .base import (Contexte, nettoyer_titre, preparer, renommer, slug,
                   terminer)


# Les deux familles d'outils qu'un pack peut viser. Mesure du 26/09/2026 :
# le pack ne savait ecrire que pour un assistant de texte — « assigner un
# role, preciser le format de sortie » — alors que les packs de prompts
# d'IMAGE forment un rayon a part sur les places de marche. Un prompt
# d'image n'a ni role ni format de sortie : il decrit un sujet, un style, une
# lumiere, un cadrage. Ecrit comme un prompt de texte, il ne produit rien
# d'utilisable, et l'acheteur ne le decouvre qu'en l'essayant.
CIBLES: Dict[str, Dict[str, str]] = {
    "texte": {
        "nom": "Assistants de texte (ChatGPT, Claude, Mistral…)",
        "categories": "(par exemple : strategie, creation, analyse, vente, "
                      "automatisation), chacune orientee vers un resultat de "
                      "travail concret",
        "prompt": "le prompt complet, pret a coller dans une IA. Il doit "
                  "assigner un role, donner le contexte, preciser le format "
                  "de sortie attendu, et contenir des variables entre "
                  "crochets comme [VOTRE PRODUIT] ou [AUDIENCE]. 150 a 260 "
                  "mots.",
        "couverture": "abstract tech pattern, prompt library",
    },
    "image": {
        "nom": "Générateurs d'images (Midjourney, Stable Diffusion…)",
        "categories": "(par exemple : portraits, produits, decors, "
                      "illustrations, textures), chacune orientee vers un "
                      "type d'image que l'acheteur veut obtenir",
        "prompt": "le prompt complet, pret a coller dans un generateur "
                  "d'images, ecrit EN ANGLAIS : ces outils le comprennent "
                  "mieux. Il decrit dans cet ordre le sujet, le style ou la "
                  "technique, la lumiere, le cadrage, la palette ; il "
                  "contient des variables entre crochets comme [SUBJECT] ou "
                  "[COLOR] ; il se termine par le format d'image, par "
                  "exemple « --ar 3:2 ». 40 a 90 mots, sans phrase "
                  "d'introduction, sans role ni consigne de format.",
        "couverture": "moodboard grid of generated images, art prompts",
    },
}
CIBLE_PAR_DEFAUT = "texte"


def _cible(ctx: Contexte, cible: str) -> Dict[str, str]:
    """La cible retenue, et le journal dit quand personne ne l'a choisie."""
    if cible in CIBLES:
        return dict(CIBLES[cible], cle=cible)
    ctx.journal("  outil vise : {} (personne ne l'a choisi)".format(
        CIBLES[CIBLE_PAR_DEFAUT]["nom"]))
    return dict(CIBLES[CIBLE_PAR_DEFAUT], cle=CIBLE_PAR_DEFAUT)


def _categories(ctx: Contexte, nombre: int,
                cible: Dict[str, str]) -> List[Dict[str, Any]]:
    invite = (
        "Organise un pack de {n} prompts professionnels sur le theme : {sujet}\n"
        "UTILISATEUR : {audience}\n"
        "OUTIL VISE : {outil}\n\n"
        "Repartis les prompts en 5 a 7 categories utiles {categories}.\n\n"
        "Schema JSON exact :\n"
        '{{"categories": [{{"nom": "...", "intention": "...", '
        '"prompts": ["intitule court du prompt 1", "intitule court du prompt 2"]}}]}}\n'
        "Au total exactement {n} intitules repartis entre les categories."
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience,
             outil=cible["nom"], categories=cible["categories"])
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
                "nom": nettoyer_titre(str(categorie.get("nom") or libelles.libelle(
                    ctx.langue_iso, "prompts_categorie"))),
                "intention": str(categorie.get("intention") or "").strip(),
                "prompts": [str(p).strip() for p in intitules if str(p).strip()],
            }
        )
    if not propres:
        raise ValueError("Aucune categorie de prompts exploitable")
    return propres


def _rediger_lot(ctx: Contexte, categorie: Dict[str, Any],
                 cible: Dict[str, str]) -> List[Dict[str, str]]:
    """Redige les prompts complets d'une categorie, en un seul appel."""
    invite = (
        "Theme du pack : {sujet}\nUtilisateur : {audience}\n"
        "OUTIL VISE : {outil}\n"
        "CATEGORIE : {nom} — {intention}\n"
        "Redige la version complete de chacun de ces prompts :\n{liste}\n\n"
        "Pour chaque prompt :\n"
        "- 'titre' : l'intitule, reformule pour etre vendeur et clair.\n"
        "- 'quand' : en une phrase, dans quelle situation l'utiliser.\n"
        "- 'prompt' : {consigne}\n"
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
        outil=cible["nom"],
        consigne=cible["prompt"],
    )
    donnees = equipe.BIBLIOTHECAIRE.travailler_json(
        ctx, invite, role_modele="standard",
                               temperature=0.72, max_tokens=4096)
    elements = donnees.get("prompts") if isinstance(donnees, dict) else donnees
    resultat: List[Dict[str, str]] = []
    # Le plan est le contrat : on a demande la version complete de CES
    # intitules-la, pas d'autres. Un modele qui en rend davantage rend autre
    # chose — mesure du 15/09/2026 : deux intitules planifies, six prompts
    # rendus, dont quatre etaient des morceaux de la consigne elle-meme
    # (« 'titre' : l'intitule, reformule pour etre vendeur et clair. ») promus
    # au rang de prompt vendu.
    #
    # On coupe sur le NOMBRE et non sur les intitules : la consigne demande
    # justement de reformuler le titre, donc comparer les libelles ecarterait
    # les bonnes reformulations en meme temps que les mauvaises — le garde-fou
    # qui crie a tort.
    plafond = len(categorie["prompts"])
    for element in elements or []:
        if len(resultat) >= plafond:
            break
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


def _titre(ctx: Contexte, combien: int) -> str:
    """Le titre annonce ce que le pack CONTIENT.

    Il annoncait le nombre demande, fixe avant la redaction. Mesure du
    15/09/2026 : couverture « 7 prompts », pack de douze. L'acheteur compte —
    c'est meme la seule chose qu'il puisse verifier d'un coup d'oeil.
    """
    return libelles.libelle(ctx.langue_iso, "prompts_titre", nombre=combien,
                            sujet=ctx.sujet.lower())


def produire(ctx: Contexte, nombre: int = 50, cible: str = "") -> Dict[str, Any]:
    visee = _cible(ctx, cible)
    ctx.journal("Étape 1/3 — plan du pack ({} prompts)...".format(nombre))
    categories = _categories(ctx, nombre, visee)
    planifies = sum(len(c["prompts"]) for c in categories)
    titre = _titre(ctx, planifies)
    dossier = preparer(ctx, "prompts", titre)
    # « anomalie » et non « echec » : le pack sera complet — chaque prompt
    # planifie sera redige — mais l'acheteur en a commande cinquante. Sans
    # cette ligne la difference ne vivait que dans le defilement du terminal,
    # c'est-a-dire nulle part sur un telephone.
    #
    # On signale le MANQUE, pas l'ecart : un plan qui rend cinquante-deux
    # prompts pour cinquante n'a lese personne, et un garde-fou qui crie a
    # tort finit ignore. Aucun seuil : les deux nombres sont rendus, un humain
    # juge si quatre prompts sur cinquante valent d'etre vendus.
    ctx.etape("plan",
              "anomalie" if planifies < nombre else "ok",
              "{} categories, {} prompts sur {} demandes".format(
                  len(categories), planifies, nombre))

    ctx.journal("Étape 2/3 — rédaction des prompts...")
    for index, categorie in enumerate(categories, 1):
        ctx.journal("  [{}/{}] {}".format(index, len(categories), categorie["nom"]))
        perdu = ""
        try:
            categorie["details"] = _rediger_lot(ctx, categorie, visee)
        except Exception as exc:
            perdu = str(exc)
            ctx.journal("     échec : {}".format(exc))
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

    ctx.journal("Étape 3/3 — export...")
    total = sum(len(c.get("details", [])) for c in categories)
    if total != planifies:
        titre = renommer(ctx, _titre(ctx, total))
        # Une categorie perdue est rattrapee par ses intitules, donc le compte
        # tient. S'il ne tient pas, c'est que le modele a rendu des entrees
        # sans prompt : le pack est plus court que son plan.
        ctx.etape("redaction", "anomalie" if total < planifies else "ok",
                  "{} prompts ecrits pour {} planifies".format(total, planifies))
    fichiers = _exporter(ctx, titre, categories, visee)
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


def _exporter(ctx: Contexte, titre: str, categories: List[Dict[str, Any]],
              cible: Dict[str, str] = CIBLES[CIBLE_PAR_DEFAUT]) -> List[Path]:
    """Prepare le produit et le confie a l'assemblage commun.

    Seules la mise en page PDF et la structure HTML sont propres aux prompts :
    le reste — couverture, markdown, CSV, JSON, sommaire — est identique a tous
    les autres types et vit dans usine/render/livraison.py.
    """
    t = libelles.textes(ctx.langue_iso)
    sous_titre = t["prompts_sous_titre"]
    # Le mode d'emploi d'un pack d'images ne parle pas de « coller le texte
    # dans Claude ou ChatGPT » : ce serait la premiere page du produit, et
    # elle se tromperait d'outil.
    image = cible.get("cle") == "image"
    explication = t["prompts_mode_emploi_image"] if image else t["prompts_mode_emploi"]
    conseil = t["prompts_conseil_image"] if image else t["prompts_conseil"]

    def mode_emploi(doc) -> None:
        doc.paragraphe(explication, justifier=True)
        doc.encadre(t["prompts_conseil_titre"], conseil)

    # Sans « corps », ce bloc n'existe que dans le PDF : la page HTML livree
    # s'ouvrait sur la premiere categorie, sans mode d'emploi. Le defaut est
    # muet — un bloc vide ne rend rien et ne se plaint pas.
    blocs = [livraison.Bloc(
        titre=t["prompts_mode_emploi_titre"],
        corps="{}\n\n**{}** — {}".format(
            explication, t["prompts_conseil_titre"],
            conseil[:1].lower() + conseil[1:]),
        rendu_pdf=mode_emploi)]
    for categorie in categories:
        blocs.append(livraison.Bloc(
            titre=categorie["nom"],
            corps=_markdown_categorie(categorie, t),
            rendu_pdf=_mise_en_page(categorie, t),
            rendu_html=_html_categorie(categorie, t),
        ))

    produit = livraison.Produit(
        type="prompts", titre=titre, sous_titre=sous_titre,
        promesse=sous_titre, blocs=blocs,
        tableaux=[livraison.Tableau(
            nom="prompts",
            colonnes=list(t["prompts_colonnes"]),
            lignes=[[categorie["nom"], detail["titre"], detail["quand"],
                     detail["prompt"], detail["astuce"]]
                    for categorie in categories
                    for detail in categorie.get("details", [])])],
        donnees={"titre": titre, "categories": categories},
        nom_donnees="prompts",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture=cible["couverture"],
        nom_fichier=slug(titre, 48),
    )
    return livraison.livrer(ctx, produit)


def _markdown_categorie(categorie: Dict[str, Any], t: Dict[str, Any]) -> str:
    lignes = []
    if categorie["intention"]:
        lignes.append("*{}*\n".format(categorie["intention"]))
    for detail in categorie.get("details", []):
        lignes.append("\n## {}\n".format(detail["titre"]))
        if detail["quand"]:
            lignes.append(t["deux_points"].format(
                libelle="**{}**".format(t["prompts_quand"]),
                texte=detail["quand"]) + "\n")
        lignes.append("```\n{}\n```\n".format(detail["prompt"]))
        if detail["astuce"]:
            lignes.append(t["deux_points"].format(
                libelle="**{}**".format(t["prompts_astuce"]),
                texte=detail["astuce"]) + "\n")
    return "\n".join(lignes)


def _mise_en_page(categorie: Dict[str, Any], t: Dict[str, Any]):
    """Rendu PDF d'une categorie : chaque prompt dans son encadre."""

    def rendre(doc) -> None:
        if categorie["intention"]:
            doc.citation(categorie["intention"])
        for detail in categorie.get("details", []):
            doc.titre(detail["titre"], 2)
            if detail["quand"]:
                doc.paragraphe(t["deux_points"].format(
                    libelle=t["prompts_quand"], texte=detail["quand"]), taille=10,
                               police="Helvetica-Oblique")
            doc.encadre("Prompt", detail["prompt"])
            if detail["astuce"]:
                doc.paragraphe(t["deux_points"].format(
                    libelle=t["prompts_astuce"], texte=detail["astuce"]), taille=10,
                               police="Helvetica-Oblique")

    return rendre


def _html_categorie(categorie: Dict[str, Any], t: Dict[str, Any]) -> str:
    # Le texte du modele entrait ici sans echappement. Mesure du 24/09/2026 :
    # un gabarit du genre « <VOTRE NOM> » etait avale comme une balise
    # inconnue, donc invisible pour l'acheteur. « inline_html » echappe, et
    # rend le gras au passage.
    corps = []
    for detail in categorie.get("details", []):
        corps.append("<h3>{}</h3>".format(D.inline_html(detail["titre"])))
        if detail["quand"]:
            corps.append("<p><em>{}</em></p>".format(D.inline_html(detail["quand"])))
        corps.append(D.vers_html(D.analyser("```\n{}\n```".format(detail["prompt"]))))
        if detail["astuce"]:
            corps.append(
                '<aside class="encadre"><p class="encadre-titre">{}</p>'
                "<p>{}</p></aside>".format(D.inline_html(t["prompts_astuce"]),
                                           D.inline_html(detail["astuce"])))
    return "\n".join(corps)
