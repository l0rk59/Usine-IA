"""Imprimables : plannings, suivis, cahiers d'exercices, fiches a completer.

Produit a tres forte marge sur les places de marche : un PDF prevu pour etre
imprime, avec des pages a completer a la main. Deux formats sont livres (A4 et
Lettre US) parce que le marche anglophone imprime en Lettre.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..core import evenements, images
from ..render import document as D
from ..render import libelles, livraison
from ..render.page import ecrire_page
from ..render.pdf import A4, LETTRE, DocumentPDF
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

DISPOSITIONS = {
    "checklist": "une liste de points a cocher",
    "planning": "une grille de planification hebdomadaire",
    "suivi": "un tableau de suivi a remplir",
    "questions": "des questions ouvertes avec des lignes de reponse",
    "notes": "une page de notes pointillee",
    "matrice": "une matrice a quatre quadrants",
}


def _cahier(ctx: Contexte, pages: int) -> Dict[str, Any]:
    invite = (
        "Concois un cahier imprimable de {n} fiches sur : {sujet}\n"
        "UTILISATEUR : {audience}\n\n"
        "Chaque fiche tient sur une page et se remplit a la main en moins de "
        "20 minutes. Varie les dispositions. Dispositions disponibles :\n{dispos}\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "titre commercial du cahier", "promesse": "...", '
        '"sous_titre": "...", '
        '"fiches": [{{"titre": "...", "disposition": "checklist|planning|suivi|'
        'questions|notes|matrice", "consigne": "2 phrases expliquant quoi faire", '
        '"elements": ["les points a cocher, les questions, ou les libelles"], '
        '"colonnes": ["si disposition suivi"], '
        '"quadrants": ["si disposition matrice, exactement 4"]}}]}}'
    ).format(n=pages, sujet=ctx.sujet, audience=ctx.audience,
             dispos="\n".join("- {} : {}".format(k, v)
                              for k, v in DISPOSITIONS.items()))
    cahier = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=4096)
    if not isinstance(cahier, dict) or not cahier.get("fiches"):
        raise ValueError("Cahier imprimable invalide")
    cahier["titre"] = nettoyer_titre(str(cahier.get("titre") or ctx.sujet))
    fiches = []
    for fiche in cahier["fiches"][:pages]:
        if isinstance(fiche, str):
            fiche = {"titre": fiche}
        disposition = str(fiche.get("disposition") or "checklist").lower()
        if disposition not in DISPOSITIONS:
            disposition = "checklist"
        fiches.append({
            "titre": nettoyer_titre(str(fiche.get("titre") or "Fiche")),
            "disposition": disposition,
            "consigne": str(fiche.get("consigne") or ""),
            "elements": [str(e) for e in (fiche.get("elements") or []) if str(e).strip()],
            "colonnes": [str(c) for c in (fiche.get("colonnes") or [])],
            "quadrants": [str(q) for q in (fiche.get("quadrants") or [])],
        })
    cahier["fiches"] = fiches
    return cahier


def _dessiner_fiche(doc: DocumentPDF, fiche: Dict[str, Any],
                    t: Dict[str, Any]) -> None:
    """Une fiche par page, adaptee a sa disposition."""
    doc.titre(fiche["titre"], 1)
    if fiche["consigne"]:
        doc.encadre(t["impression_comment_remplir"], fiche["consigne"])

    disposition = fiche["disposition"]
    if disposition == "checklist":
        doc.cases_a_cocher(fiche["elements"] or ["", "", "", "", "", ""])
        doc.titre(t["impression_notes"], 2)
        doc.lignes_a_remplir(4)
    elif disposition == "planning":
        jours = list(t["impression_jours"])
        if fiche["elements"]:
            doc.titre(t["impression_priorites"], 2)
            doc.cases_a_cocher(fiche["elements"][:4])
        doc.titre(t["impression_semaine"], 2)
        doc.grille(7, 4, titres=jours)
    elif disposition == "suivi":
        colonnes = fiche["colonnes"] or list(t["impression_suivi_colonnes"])
        doc.tableau(colonnes, [], lignes_vides=14)
    elif disposition == "questions":
        for question in (fiche["elements"] or [t["impression_question"]])[:6]:
            doc.titre(question, 3)
            doc.lignes_a_remplir(3)
    elif disposition == "matrice":
        quadrants = (fiche["quadrants"] + ["", "", "", ""])[:4]
        doc.titre(" | ".join(q for q in quadrants[:2] if q), 3)
        doc.grille(2, 2, hauteur=190)
        doc.titre(" | ".join(q for q in quadrants[2:] if q), 3)
    else:  # notes
        doc.points()


# Valeur de depart quand on demande une reliure sans preciser laquelle. Ce
# n'est PAS une recommandation d'imprimeur : chaque service d'impression a la
# demande publie la sienne, souvent fonction du nombre de pages, et c'est
# celle-la qui fait foi. Dix millimetres tiennent pour un cahier mince.
RELIURE_MM = 10.0

# 1 mm = 72/25.4 points PostScript.
POINTS_PAR_MM = 72.0 / 25.4


def produire(ctx: Contexte, pages: int = 12,
             reliure: float = 0.0) -> Dict[str, Any]:
    """« reliure » est une marge interieure en MILLIMETRES, 0 pour aucune."""
    reliure_mm = RELIURE_MM if reliure and reliure < 0 else float(reliure or 0)
    reliure_points = round(reliure_mm * POINTS_PAR_MM, 2)
    ctx.journal("Étape 1/3 — conception du cahier ({} fiches)...".format(pages))
    if reliure_points:
        ctx.journal("  marge de reliure : {:.0f} mm, alternee".format(reliure_mm))
    cahier = _cahier(ctx, pages)
    titre = cahier["titre"]
    dossier = preparer(ctx, "impression", titre)
    ctx.etape("cahier", "ok", "{} fiches".format(len(cahier["fiches"])))
    ctx.journal('  Cahier : « {} »'.format(titre))
    evenements.publier("section", etape="impression", titre=titre,
                       total=len(cahier["fiches"]))

    ctx.journal("Étape 2/3 — couverture...")
    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, titre, cahier.get("sous_titre", ""), ctx.auteur,
            style="printable planner cover, minimal stationery, soft paper texture",
            en_ligne=not ctx.hors_ligne)

    ctx.journal("Étape 3/3 — génération des deux formats...")
    fichiers: List[Path] = []
    t = libelles.textes(ctx.langue_iso)
    if couverture:
        fichiers.append(couverture)
    for nom_format, format_page in (("A4", A4), ("Lettre-US", LETTRE)):
        doc = livraison.document(ctx, titre, cahier.get("sous_titre", ""),
                                 couverture, format_page=format_page,
                                 marge=54, police_corps="Helvetica",
                                 reliure=reliure_points)
        doc.titre(t["impression_mode_emploi_titre"], 1)
        doc.paragraphe(t["impression_mode_emploi"], justifier=True)
        if reliure_points:
            doc.encadre(t["impression_a_la_demande_titre"],
                        t["impression_a_la_demande"].format(
                            mm="{:.0f}".format(reliure_mm)))
        if cahier.get("promesse"):
            doc.encadre(t["impression_apporte"], str(cahier["promesse"]))
        for fiche in cahier["fiches"]:
            _dessiner_fiche(doc, fiche, t)
        doc.inserer_sommaire(t["sommaire"], apres=1)
        chemin = dossier / "{}-{}.pdf".format(slug(titre, 40), nom_format)
        doc.enregistrer(chemin)
        fichiers.append(chemin)
        ctx.journal("  format {} : {} pages".format(nom_format, len(doc._pages)))

    (dossier / "cahier.json").write_text(
        json.dumps(cahier, ensure_ascii=False, indent=2), encoding="utf-8")

    # Le texte du modele entrait dans la page SANS echappement : un « a < b »
    # dans une consigne cassait la page, une balise y aurait ete interpretee
    # chez l'acheteur, et un « **mot** » restait en clair (balayage du
    # 24/09/2026). « inline_html » echappe et rend le gras, comme ailleurs.
    corps = ["<h2>{}</h2><p>{}</p><p><em>{}</em></p>".format(
        D.inline_html(f["titre"]), D.inline_html(f["consigne"]),
        D.inline_html(t["deux_points"].format(
            libelle=t["impression_disposition"],
            texte=t["impression_dispositions"].get(f["disposition"],
                                                   f["disposition"]))))
        for f in cahier["fiches"]]
    chemin_html = dossier / "lire.html"
    ecrire_page(chemin_html, titre, "\n".join(corps), cahier.get("sous_titre", ""),
                ctx.auteur, langue=ctx.langue_iso,
                couverture=couverture.name if couverture else None)
    fichiers.append(chemin_html)

    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "fiches": len(cahier["fiches"]),
        "formats": ["A4", "Lettre-US"],
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"fiches": len(cahier["fiches"])})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume
