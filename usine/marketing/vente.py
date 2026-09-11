"""Kit de vente : fiche produit, page de vente, sequence de lancement.

Genere a partir d'un produit deja fabrique. C'est la moitie du travail qui
transforme un fichier en revenu.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..core import llm
from ..render import document as D
from ..render.page import ecrire_page
from ..pipelines.base import Contexte, nettoyer_titre

ROLE = (
    "un redacteur publicitaire specialise dans les produits digitaux, "
    "qui vend par la clarte et la preuve, jamais par la pression"
)

PLATEFORMES = {
    "gumroad": "Gumroad (description en markdown, 150-300 mots, titre court, "
               "puces de benefices, section 'ce que vous recevez')",
    "etsy": "Etsy (titre de 140 caracteres riche en mots-cles, 13 tags de 20 caracteres "
            "maximum, description structuree avec livraison numerique instantanee)",
    "payhip": "Payhip (description courte, puces, garantie)",
    "site": "site personnel (page de vente longue, structure classique)",
}


def fiche_produit(ctx: Contexte, titre: str, description_produit: str,
                  plateforme: str = "gumroad") -> Dict[str, Any]:
    """Titres alternatifs, description, mots-cles, prix conseille."""
    invite = (
        "PRODUIT : {titre}\nCONTENU : {contenu}\nAUDIENCE : {audience}\n"
        "PLATEFORME : {plateforme}\n\n"
        "Prepare la fiche de vente. Le prix doit etre coherent avec un produit digital "
        "auto-edite et exprime en euros.\n\n"
        "Schema JSON exact :\n"
        '{{"titres": ["5 variantes de titre de vente"], '
        '"accroche": "une phrase de moins de 140 caracteres", '
        '"description": "description de vente complete en markdown", '
        '"benefices": ["5 a 7 benefices concrets"], '
        '"contenu_livre": ["ce que l\'acheteur recoit, fichier par fichier"], '
        '"pour_qui": ["3 profils"], "pas_pour_qui": ["2 profils"], '
        '"objections": [{{"objection": "...", "reponse": "..."}}], '
        '"mots_cles": ["12 mots-cles de recherche"], '
        '"prix_conseille": {{"bas": 9, "cible": 19, "haut": 39, '
        '"justification": "..."}}, '
        '"garantie": "formulation de la garantie"}}'
    ).format(titre=titre, contenu=description_produit[:2500],
             audience=ctx.audience, plateforme=PLATEFORMES.get(plateforme, plateforme))
    fiche = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                             temperature=0.75, max_tokens=3500)
    if not isinstance(fiche, dict):
        raise ValueError("Fiche produit invalide")
    fiche["titres"] = [nettoyer_titre(str(t)) for t in (fiche.get("titres") or [titre])]
    return fiche


def sequence_lancement(ctx: Contexte, titre: str, fiche: Dict[str, Any]) -> List[Dict[str, str]]:
    """5 e-mails de lancement, du teasing a la cloture."""
    invite = (
        "PRODUIT : {titre}\nACCROCHE : {accroche}\n"
        "BENEFICES : {benefices}\nAUDIENCE : {audience}\n\n"
        "Redige une sequence de lancement en 5 e-mails : (1) le probleme, "
        "(2) l'histoire et la methode, (3) l'annonce du produit, "
        "(4) les objections levees, (5) derniere occasion. "
        "120 a 200 mots par e-mail, un seul appel a l'action par e-mail, "
        "aucune fausse urgence ni faux compte a rebours.\n\n"
        "Schema JSON exact :\n"
        '{{"emails": [{{"jour": 1, "objet": "...", "preheader": "...", '
        '"corps": "...", "cta": "..."}}]}}'
    ).format(titre=titre, accroche=fiche.get("accroche", ""),
             benefices=" ; ".join(str(b) for b in fiche.get("benefices", [])[:6]),
             audience=ctx.audience)
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="standard",
                               temperature=0.78, max_tokens=4096)
    emails = donnees.get("emails") if isinstance(donnees, dict) else donnees
    return [
        {
            "jour": str(e.get("jour", i + 1)),
            "objet": str(e.get("objet") or "").strip(),
            "preheader": str(e.get("preheader") or "").strip(),
            "corps": str(e.get("corps") or "").strip(),
            "cta": str(e.get("cta") or "").strip(),
        }
        for i, e in enumerate(emails or [])
        if isinstance(e, dict) and e.get("corps")
    ]


def page_de_vente(titre: str, fiche: Dict[str, Any], prix: str = "",
                  couverture: str = "") -> str:
    """Fragment HTML de page de vente, insere dans le gabarit standard."""
    def liste(elements: List[Any]) -> str:
        return "<ul>{}</ul>".format(
            "".join("<li>{}</li>".format(D.inline_html(str(e))) for e in elements or [])
        )

    prix_affiche = prix or "{} EUR".format(
        (fiche.get("prix_conseille") or {}).get("cible", 19)
    )
    morceaux: List[str] = []
    if couverture:
        morceaux.append('<p><img src="{}" alt="Couverture"/></p>'.format(couverture))
    morceaux.append("<h2>Ce que ce produit change pour vous</h2>")
    morceaux.append(liste(fiche.get("benefices")))
    if fiche.get("description"):
        morceaux.append(D.vers_html(D.analyser(str(fiche["description"])), niveau_depart=2))
    if fiche.get("contenu_livre"):
        morceaux.append("<h2>Ce que vous recevez</h2>")
        morceaux.append(liste(fiche["contenu_livre"]))
    if fiche.get("pour_qui"):
        morceaux.append("<h2>Pour qui c'est fait</h2>")
        morceaux.append(liste(fiche["pour_qui"]))
    if fiche.get("pas_pour_qui"):
        morceaux.append("<h2>Pour qui ce n'est pas fait</h2>")
        morceaux.append(liste(fiche["pas_pour_qui"]))
    if fiche.get("objections"):
        morceaux.append("<h2>Vos questions</h2>")
        for objection in fiche["objections"]:
            if isinstance(objection, dict):
                morceaux.append(
                    "<h3>{}</h3><p>{}</p>".format(
                        D.inline_html(str(objection.get("objection", ""))),
                        D.inline_html(str(objection.get("reponse", ""))),
                    )
                )
    morceaux.append(
        '<aside class="encadre"><p class="encadre-titre">Prix</p>'
        "<p><strong>{}</strong> — acces immediat apres paiement, "
        "telechargement direct.</p>{}</aside>".format(
            D.inline_html(prix_affiche),
            "<p>{}</p>".format(D.inline_html(str(fiche.get("garantie", ""))))
            if fiche.get("garantie") else "",
        )
    )
    morceaux.append(
        '<p><a href="#acheter"><strong>Obtenir « {} »</strong></a></p>'.format(
            D.inline_html(titre)
        )
    )
    return "\n".join(morceaux)


def produire_kit(ctx: Contexte, titre: str, description_produit: str,
                 dossier: Path, plateforme: str = "gumroad",
                 couverture: str = "") -> Dict[str, Any]:
    """Genere le kit de vente complet dans `dossier/marketing`."""
    cible = dossier / "marketing"
    cible.mkdir(parents=True, exist_ok=True)
    fichiers: List[Path] = []

    ctx.journal("  fiche produit ({})...".format(plateforme))
    fiche = fiche_produit(ctx, titre, description_produit, plateforme)
    (cible / "fiche-produit.json").write_text(
        json.dumps(fiche, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fichiers.append(cible / "fiche-produit.json")

    # Fiche lisible, a copier-coller dans la boutique
    lignes = [
        "# Fiche de vente — {}\n".format(titre),
        "## Titres a tester\n",
        "\n".join("- " + t for t in fiche.get("titres", [])),
        "\n## Accroche\n",
        str(fiche.get("accroche", "")),
        "\n## Description ({})\n".format(plateforme),
        str(fiche.get("description", "")),
        "\n## Benefices\n",
        "\n".join("- " + str(b) for b in fiche.get("benefices", [])),
        "\n## Ce que l'acheteur recoit\n",
        "\n".join("- " + str(c) for c in fiche.get("contenu_livre", [])),
        "\n## Mots-cles / tags\n",
        ", ".join(str(m) for m in fiche.get("mots_cles", [])),
        "\n## Prix conseille\n",
        json.dumps(fiche.get("prix_conseille", {}), ensure_ascii=False, indent=2),
    ]
    chemin_fiche = cible / "fiche-produit.md"
    chemin_fiche.write_text("\n".join(lignes), encoding="utf-8")
    fichiers.append(chemin_fiche)

    ctx.journal("  page de vente...")
    prix = ctx.prix or ""
    chemin_page = cible / "page-de-vente.html"
    ecrire_page(
        chemin_page,
        fiche.get("titres", [titre])[0],
        page_de_vente(titre, fiche, prix, couverture),
        sous_titre=str(fiche.get("accroche", "")),
        meta=ctx.marque or ctx.auteur,
    )
    fichiers.append(chemin_page)

    ctx.journal("  sequence de lancement...")
    try:
        emails = sequence_lancement(ctx, titre, fiche)
    except Exception as exc:
        ctx.journal("  sequence indisponible : {}".format(exc))
        emails = []
    if emails:
        lignes_email = ["# Sequence de lancement — {}\n".format(titre)]
        for email in emails:
            lignes_email.append("\n## Jour {} — {}\n".format(email["jour"], email["objet"]))
            if email["preheader"]:
                lignes_email.append("*Preheader : {}*\n".format(email["preheader"]))
            lignes_email.append(email["corps"])
            if email["cta"]:
                lignes_email.append("\n**CTA :** {}\n".format(email["cta"]))
        chemin_emails = cible / "sequence-lancement.md"
        chemin_emails.write_text("\n".join(lignes_email), encoding="utf-8")
        fichiers.append(chemin_emails)

    return {
        "fiche": fiche,
        "emails": len(emails),
        "fichiers": [f.name for f in fichiers],
        "dossier": str(cible),
    }
