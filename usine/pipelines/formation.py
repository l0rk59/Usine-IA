"""Mini-formation : modules pedagogiques, cahier d'exercices et sequence e-mail."""

from __future__ import annotations


import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core import images, llm
from ..render import livraison
from ..render.pdf import DocumentPDF
from .base import Contexte, elaguer_markdown, nettoyer_titre, preparer, slug, terminer

ROLE = "un concepteur pedagogique qui cree des formations en ligne actionnables"


def _programme(ctx: Contexte, modules: int) -> Dict[str, Any]:
    invite = (
        "Concois une mini-formation en {n} modules sur : {sujet}\n"
        "APPRENANT : {audience}\n\n"
        "Chaque module produit un livrable concret (pas seulement du savoir). "
        "La progression va du diagnostic a la mise en oeuvre autonome.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "titre commercial de la formation", '
        '"promesse": "ce que l\'apprenant sait faire a la fin", '
        '"prerequis": "...", '
        '"modules": [{{"titre": "...", "objectif": "...", '
        '"livrable": "ce que l\'apprenant produit", '
        '"notions": ["...", "..."], "exercice": "consigne de l\'exercice"}}]}}'
    ).format(n=modules, sujet=ctx.sujet, audience=ctx.audience)
    programme = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                                 temperature=0.65, max_tokens=3000)
    if not isinstance(programme, dict) or not programme.get("modules"):
        raise ValueError("Programme de formation invalide")
    programme["titre"] = nettoyer_titre(str(programme.get("titre") or ctx.sujet))
    propres = []
    for module in programme["modules"][:modules]:
        if isinstance(module, str):
            module = {"titre": module}
        notions = module.get("notions") or []
        propres.append(
            {
                "titre": nettoyer_titre(str(module.get("titre") or "Module")),
                "objectif": str(module.get("objectif") or "").strip(),
                "livrable": str(module.get("livrable") or "").strip(),
                "notions": [str(n).strip() for n in notions if str(n).strip()],
                "exercice": str(module.get("exercice") or "").strip(),
            }
        )
    programme["modules"] = propres
    return programme


def _rediger_module(ctx: Contexte, programme: Dict[str, Any], index: int,
                    module: Dict[str, Any]) -> str:
    invite = (
        "Formation : « {formation} »\nPROMESSE : {promesse}\n"
        "MODULE {num}/{total} : {titre}\nOBJECTIF : {objectif}\n"
        "LIVRABLE ATTENDU : {livrable}\nNOTIONS : {notions}\n\n"
        "Redige le contenu du module (environ {mots} mots) avec cette structure :\n"
        "## Ce que vous allez obtenir\n(2 phrases)\n"
        "## Le contenu\n(sous-sections ### avec explications et exemples concrets)\n"
        "## La methode pas a pas\n(liste numerotee d'etapes applicables)\n"
        "## Les erreurs a eviter\n(liste a puces de 3 erreurs frequentes)\n"
        "## Votre exercice\n(consigne precise et verifiable : {exercice})\n\n"
        "Markdown uniquement, pas de titre de niveau 1."
    ).format(
        formation=programme["titre"],
        promesse=programme.get("promesse", ""),
        num=index + 1,
        total=len(programme["modules"]),
        titre=module["titre"],
        objectif=module["objectif"],
        livrable=module["livrable"],
        notions=" ; ".join(module["notions"]) or "libre",
        mots=ctx.mots_par_chapitre,
        exercice=module["exercice"] or "a definir",
    )
    reponse = llm.generer(invite, systeme=ctx.systeme(ROLE), role="standard",
                          temperature=0.75, max_tokens=min(4096, ctx.mots_par_chapitre * 3))
    texte = elaguer_markdown(reponse.texte)
    lignes = texte.split("\n")
    if lignes and lignes[0].startswith("# "):
        lignes.pop(0)
    return "\n".join(lignes).strip()


def _sequence_email(ctx: Contexte, programme: Dict[str, Any]) -> List[Dict[str, str]]:
    """Sequence de livraison : un e-mail par module + un e-mail de bienvenue."""
    invite = (
        "Formation : « {formation} »\nPROMESSE : {promesse}\n"
        "MODULES :\n{modules}\n\n"
        "Redige la sequence d'e-mails de livraison : un e-mail de bienvenue, puis un "
        "e-mail par module, puis un e-mail de cloture. Chaque e-mail fait 120 a 180 mots, "
        "tutoie ou vouvoie selon le ton demande, et se termine par une action unique.\n\n"
        "Schema JSON exact :\n"
        '{{"emails": [{{"jour": 0, "objet": "...", "corps": "texte de l\'e-mail", '
        '"action": "l\'action unique demandee"}}]}}'
    ).format(
        formation=programme["titre"],
        promesse=programme.get("promesse", ""),
        modules="\n".join("- " + m["titre"] for m in programme["modules"]),
    )
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="standard",
                               temperature=0.7, max_tokens=4096)
    emails = donnees.get("emails") if isinstance(donnees, dict) else donnees
    return [
        {
            "jour": str(e.get("jour", i)),
            "objet": str(e.get("objet") or "").strip(),
            "corps": str(e.get("corps") or "").strip(),
            "action": str(e.get("action") or "").strip(),
        }
        for i, e in enumerate(emails or [])
        if isinstance(e, dict) and e.get("corps")
    ]


def produire(ctx: Contexte, modules: int = 0) -> Dict[str, Any]:
    modules = modules or max(5, min(ctx.nb_chapitres, 10))
    ctx.journal("Etape 1/4 — programme pedagogique ({} modules)...".format(modules))
    programme = _programme(ctx, modules)
    titre = programme["titre"]
    dossier = preparer(ctx, "formation", titre)
    ctx.etape("programme", "ok", "{} modules".format(len(programme["modules"])))
    ctx.journal('  Formation : « {} »'.format(titre))

    ctx.journal("Etape 2/4 — redaction des modules...")
    contenus: List[Tuple[str, str]] = []
    for index, module in enumerate(programme["modules"]):
        ctx.journal("  [{}/{}] {}".format(index + 1, len(programme["modules"]),
                                          module["titre"]))
        try:
            corps = _rediger_module(ctx, programme, index, module)
        except Exception as exc:
            ctx.journal("     echec : {}".format(exc))
            ctx.etape("module-{}".format(index + 1), "echec", str(exc))
            corps = "## Objectif\n\n{}\n\n## Notions\n\n{}".format(
                module["objectif"], "\n".join("- " + n for n in module["notions"])
            )
        contenus.append(("Module {} — {}".format(index + 1, module["titre"]), corps))
        ctx.etape("module-{}".format(index + 1), "ok")

    ctx.journal("Etape 3/4 — sequence e-mail de livraison...")
    try:
        emails = _sequence_email(ctx, programme)
    except Exception as exc:
        ctx.journal("  sequence e-mail indisponible : {}".format(exc))
        emails = []
    ctx.etape("emails", "ok" if emails else "echec", "{} e-mails".format(len(emails)))

    ctx.journal("Etape 4/4 — export...")
    fichiers = _exporter(ctx, programme, contenus, emails)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "modules": len(contenus),
        "emails": len(emails),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"modules": len(contenus), "emails": len(emails)})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _exporter(ctx: Contexte, programme: Dict[str, Any], contenus: List[Tuple[str, str]],
              emails: List[Dict[str, str]]) -> List[Path]:
    """Confie la formation a l'assemblage commun.

    Deux specificites : un cahier d'exercices qui est un second document PDF,
    et la sequence e-mail, un markdown a part. Le reste est standard.
    """
    titre = programme["titre"]
    prerequis = str(programme.get("prerequis") or "")

    def avant_propos(doc) -> None:
        doc.paragraphe(programme.get("promesse", ""), justifier=True)
        if prerequis:
            doc.encadre("Prerequis", prerequis)
        doc.paragraphe(
            "Traitez un module par session de travail. Ne passez au suivant qu'apres "
            "avoir produit le livrable demande : c'est lui qui transforme la lecture "
            "en resultat.", justifier=True)

    blocs = [livraison.Bloc(titre="Avant de commencer", rendu_pdf=avant_propos)]
    blocs += livraison.blocs_depuis_sections(contenus)

    produit = livraison.Produit(
        type="formation", titre=titre,
        sous_titre=programme.get("promesse", ""),
        promesse=programme.get("promesse", ""),
        blocs=blocs,
        donnees=programme, nom_donnees="programme",
        formats=("md", "pdf", "html"),
        style_couverture="online course cover, educational, clean geometric",
        nom_fichier=slug(titre, 40),
        suffixe_pdf="-manuel",
        libelle_sections="modules",
        documents=[("cahier-exercices", _cahier(ctx, programme, titre))],
    )
    fichiers = livraison.livrer(ctx, produit)

    if emails:
        lignes = ["# Sequence e-mail — {}\n".format(titre)]
        for email in emails:
            lignes.append("\n## Jour {} — {}\n".format(email["jour"], email["objet"]))
            lignes.append(email["corps"])
            if email["action"]:
                lignes.append("\n**Action demandee :** {}\n".format(email["action"]))
        chemin = ctx.dossier / "sequence-emails.md"
        chemin.write_text("\n".join(lignes), encoding="utf-8")
        fichiers.append(chemin)
    return fichiers


def _cahier(ctx: Contexte, programme: Dict[str, Any], titre: str):
    """Construit le cahier d'exercices, second document du produit."""

    def construire(octets_jpeg):
        doc = DocumentPDF(titre_courant="{} — cahier d'exercices".format(titre),
                          police_corps="Helvetica")
        doc.page_couverture("Cahier d'exercices", titre, ctx.auteur)
        for index, module in enumerate(programme["modules"], 1):
            doc.titre("Module {} — {}".format(index, module["titre"]), 1)
            if module["objectif"]:
                doc.paragraphe("Objectif : " + module["objectif"], taille=10.5)
            if module["livrable"]:
                doc.encadre("Livrable attendu", module["livrable"])
            if module["exercice"]:
                doc.titre("Consigne", 2)
                doc.paragraphe(module["exercice"], justifier=True)
            doc.titre("Vos notes", 2)
            doc.lignes_a_remplir(9)
        return doc

    return construire
