"""Chaine de production d'un ebook vendable.

Enchainement : plan -> chapitres -> avant-propos/conclusion -> mise en forme
PDF + EPUB + HTML + Markdown + TXT, couverture comprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..agents import equipe
from ..agents.base import Critique
from ..core import budget
from ..core import controle as ctrl
from ..core import evenements, images, llm, securite
from ..render import document as D
from ..render.epub import construire_epub
from ..render.page import ecrire_page
from ..render.pdf import DocumentPDF
from .base import Contexte, elaguer_markdown, nettoyer_titre, preparer, terminer

ROLE = "un auteur de guides pratiques qui se vendent, editeur exigeant"


def construire_plan(ctx: Contexte) -> Dict[str, Any]:
    """Titre commercial + structure detaillee, en JSON."""
    invite = (
        "Concois le plan d'un ebook pratique et vendable sur ce sujet :\n"
        "SUJET : {sujet}\n"
        "LECTEUR : {audience}\n"
        "LONGUEUR : {n} chapitres.\n\n"
        "Contraintes :\n"
        "- Le titre doit etre commercial et specifique (pas de titre generique).\n"
        "- Chaque chapitre resout UN probleme precis et progresse vers la promesse.\n"
        "- Les titres de chapitres sont des benefices concrets, pas des categories.\n"
        "- 'points' liste 4 a 6 idees a couvrir dans le chapitre, en style telegraphique.\n\n"
        "Schema JSON exact attendu :\n"
        '{{"titre": "...", "sous_titre": "...", "promesse": "une phrase : ce que le '
        'lecteur sait faire a la fin", "lecteur_ideal": "...", '
        '"chapitres": [{{"titre": "...", "objectif": "...", '
        '"points": ["...", "..."]}}]}}'
    ).format(sujet=ctx.sujet, audience=ctx.audience, n=ctx.nb_chapitres)

    plan = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=3000)

    if not isinstance(plan, dict) or not plan.get("chapitres"):
        raise ValueError("Plan invalide renvoye par le modele")
    plan["titre"] = nettoyer_titre(str(plan.get("titre") or ctx.sujet))
    plan["sous_titre"] = str(plan.get("sous_titre") or "").strip().strip('"')
    chapitres: List[Dict[str, Any]] = []
    for brut in plan["chapitres"]:
        if isinstance(brut, str):
            brut = {"titre": brut, "objectif": "", "points": []}
        titre = nettoyer_titre(str(brut.get("titre") or "Chapitre"))
        points = brut.get("points") or []
        if isinstance(points, str):
            points = [points]
        chapitres.append(
            {
                "titre": titre,
                "objectif": str(brut.get("objectif") or "").strip(),
                "points": [str(p).strip() for p in points if str(p).strip()],
            }
        )
    plan["chapitres"] = chapitres[: ctx.nb_chapitres]
    return plan


def rediger_chapitre(
    ctx: Contexte, plan: Dict[str, Any], index: int, chapitre: Dict[str, Any]
) -> Tuple[str, str]:
    """Redige un chapitre. Renvoie (markdown, fournisseur utilise)."""
    autres = " | ".join(
        c["titre"] for j, c in enumerate(plan["chapitres"]) if j != index
    )
    invite = (
        "Redige le chapitre {num} sur {total} de l'ebook « {livre} ».\n"
        "PROMESSE DU LIVRE : {promesse}\n"
        "TITRE DU CHAPITRE : {titre}\n"
        "OBJECTIF : {objectif}\n"
        "POINTS A COUVRIR : {points}\n"
        "AUTRES CHAPITRES (ne les traite pas, evite les redites) : {autres}\n\n"
        "Consignes de redaction :\n"
        "- Environ {mots} mots.\n"
        "- Commence directement par un paragraphe d'accroche : une situation concrete "
        "que le lecteur reconnait. Pas de repetition du titre.\n"
        "- Structure avec des sous-titres markdown de niveau 2 (##) et 3 (###).\n"
        "- Inclus au moins une liste numerotee d'etapes applicables aujourd'hui.\n"
        "- Inclus un exemple chiffre realiste (presente comme un exemple, pas comme "
        "une statistique officielle).\n"
        "- Termine par une ligne exactement au format : "
        "**A retenir :** suivi de deux phrases maximum.\n"
        "- N'ecris PAS de titre de niveau 1 (#), il est ajoute automatiquement.\n"
        "- Reponds uniquement en markdown, sans commentaire d'introduction."
    ).format(
        num=index + 1,
        total=len(plan["chapitres"]),
        livre=plan["titre"],
        promesse=plan.get("promesse", ""),
        titre=chapitre["titre"],
        objectif=chapitre.get("objectif", ""),
        points=" ; ".join(chapitre.get("points", [])) or "libre",
        autres=autres or "aucun",
        mots=ctx.mots_par_chapitre,
    )
    reponse = equipe.REDACTEUR.travailler(
        ctx, invite, max_tokens=min(4096, int(ctx.mots_par_chapitre * 2.6))
    )
    texte = elaguer_markdown(reponse.texte)
    # Le modele reintroduit parfois un titre h1 : on le retire pour eviter le doublon.
    lignes = texte.split("\n")
    if lignes and lignes[0].startswith("# "):
        lignes.pop(0)
    return "\n".join(lignes).strip(), reponse.fournisseur


def rediger_annexe(ctx: Contexte, plan: Dict[str, Any], genre: str) -> Tuple[str, str]:
    """Avant-propos ou conclusion. Renvoie (titre, markdown)."""
    sommaire = "\n".join("- " + c["titre"] for c in plan["chapitres"])
    if genre == "introduction":
        titre = "Avant-propos : pourquoi ce livre"
        consigne = (
            "Redige l'avant-propos (450 mots environ) : le probleme que vit le lecteur, "
            "pourquoi les solutions habituelles echouent, ce que ce livre change, "
            "et comment le lire (parcours conseille). Termine par une invitation a "
            "commencer par le chapitre 1."
        )
    else:
        titre = "Et maintenant : votre plan des 30 prochains jours"
        consigne = (
            "Redige la conclusion (450 mots environ) : une synthese des principes cles, "
            "puis un plan d'action concret semaine par semaine sur 4 semaines, "
            "sous forme de liste. Termine sur une phrase de motivation sobre, "
            "sans promesse de resultat garanti."
        )
    invite = (
        "Ebook : « {livre} »\nPROMESSE : {promesse}\nSOMMAIRE :\n{sommaire}\n\n{consigne}\n"
        "Markdown uniquement, sous-titres de niveau 2 (##) autorises, "
        "pas de titre de niveau 1."
    ).format(
        livre=plan["titre"],
        promesse=plan.get("promesse", ""),
        sommaire=sommaire,
        consigne=consigne,
    )
    reponse = equipe.REDACTEUR.travailler(ctx, invite, max_tokens=1800)
    return titre, elaguer_markdown(reponse.texte)


def produire(ctx: Contexte) -> Dict[str, Any]:
    """Produit l'ebook complet et renvoie un resume des fichiers generes."""
    ctx.journal("Etape 1/5 — construction du plan...")
    plan = construire_plan(ctx)
    titre = plan["titre"]
    sous_titre = plan.get("sous_titre", "")
    dossier = preparer(ctx, "ebook", titre)
    ctx.etape("plan", "ok", "{} chapitres".format(len(plan["chapitres"])))
    ctx.journal('  Titre retenu : « {} »'.format(titre))
    (dossier / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = len(plan["chapitres"])
    sections: List[Tuple[str, str]] = []
    qualite: Dict[str, List[Critique]] = {}
    local: Dict[str, List[ctrl.Controle]] = {}

    alertes = securite.analyser_sujet(ctx.sujet)
    for domaine, avertissement in alertes:
        ctx.journal("  [!] domaine sensible « {} » : {}".format(domaine, avertissement))
        evenements.publier("alerte", domaine=domaine, detail=avertissement)

    budget_epuise = False

    ctx.journal("Etape 2/5 — avant-propos...")
    try:
        titre_intro, corps_intro = rediger_annexe(ctx, plan, "introduction")
        sections.append((titre_intro, corps_intro))
        ctx.etape("introduction")
    except budget.BudgetEpuise as exc:
        budget_epuise = True
        ctx.journal("  {} — avant-propos ignore".format(exc))
        ctx.etape("introduction", "echec", str(exc))

    ctx.journal("Etape 3/5 — redaction des {} chapitres...".format(total))
    passes = ctx.nb_passes
    if passes:
        ctx.journal("  qualite « {} » : {} relecture(s) editoriale(s) par chapitre"
                    .format(ctx.qualite, passes))
    for index, chapitre in enumerate(plan["chapitres"]):
        ctx.journal("  [{}/{}] {}".format(index + 1, total, chapitre["titre"]))
        evenements.publier("section", etape="redaction", index=index + 1,
                           total=total, titre=chapitre["titre"])
        if budget_epuise:
            # Inutile de tenter les chapitres suivants : chaque appel serait
            # refuse. On les remplace par leur plan et on va a l'export.
            sections.append((chapitre["titre"], _repli(chapitre)))
            ctx.etape("chapitre-{}".format(index + 1), "echec", "budget epuise")
            continue
        try:
            corps, auteur = rediger_chapitre(ctx, plan, index, chapitre)
        except budget.BudgetEpuise as exc:
            budget_epuise = True
            ctx.journal("     {} — chapitres restants reduits a leur plan".format(exc))
            ctx.etape("chapitre-{}".format(index + 1), "echec", str(exc))
            sections.append((chapitre["titre"], _repli(chapitre)))
            continue
        except Exception as exc:
            ctx.journal("     echec : {} — chapitre conserve en resume".format(exc))
            ctx.etape("chapitre-{}".format(index + 1), "echec", str(exc))
            corps, auteur = _repli(chapitre), ""
        else:
            # 1. Controle local : gratuit, instantane, reproductible. Les defauts
            #    mesurables sont corriges ici, sans consulter de relecteur IA.
            try:
                corps, controles = equipe.controler_et_corriger(
                    ctx, corps, chapitre["titre"], ctx.mots_par_chapitre,
                    precedents=[c for _, c in sections],
                    tentatives=2 if passes else 1,
                )
                local[chapitre["titre"]] = controles
                ctx.journal("     controle : " + controles[-1].resume())
            except budget.BudgetEpuise as exc:
                budget_epuise = True
                ctx.journal("     {} — corrections interrompues".format(exc))

            # 2. Relecture IA : uniquement ce qui demande un jugement — la
            #    pertinence, la progression, la tenue de la promesse.
            if passes and not budget_epuise:
                try:
                    corps, critiques = equipe.affiner(
                        ctx, corps, chapitre["titre"], plan.get("promesse", ""),
                        auteur, passes=passes,
                    )
                    qualite[chapitre["titre"]] = critiques
                    if critiques:
                        ctx.journal("     relecture : " + critiques[-1].resume())
                except budget.BudgetEpuise as exc:
                    budget_epuise = True
                    ctx.journal("     {} — relecture interrompue".format(exc))
        sections.append((chapitre["titre"], corps))
        ctx.etape("chapitre-{}".format(index + 1), "ok", chapitre["titre"])

    ctx.journal("Etape 4/5 — conclusion...")
    if budget_epuise:
        ctx.journal("  ignoree : budget epuise")
        ctx.etape("conclusion", "echec", "budget epuise")
    else:
        try:
            titre_fin, corps_fin = rediger_annexe(ctx, plan, "conclusion")
            sections.append((titre_fin, corps_fin))
            ctx.etape("conclusion")
        except budget.BudgetEpuise as exc:
            budget_epuise = True
            ctx.journal("  {} — conclusion ignoree".format(exc))
            ctx.etape("conclusion", "echec", str(exc))

    ctx.journal("Etape 5/5 — mise en forme et export...")
    fichiers = exporter(ctx, plan, sections)

    rapport = equipe.rapport_qualite(qualite) if qualite else {}
    if local:
        rapport["controle_local"] = {
            "sections": [
                {"section": titre, "note_initiale": suite[0].note,
                 "note_finale": suite[-1].note,
                 "defauts_restants": [a.detail for a in suite[-1].anomalies]}
                for titre, suite in local.items()
            ],
            "note_moyenne_initiale": round(
                sum(s[0].note for s in local.values()) / len(local), 2),
            "note_moyenne_finale": round(
                sum(s[-1].note for s in local.values()) / len(local), 2),
        }
    # Mesure finale sur le texte reellement exporte, pas sur un etat intermediaire.
    rapport["mesure_finale"] = ctrl.controler_ensemble(sections, ctx.mots_par_chapitre)
    if rapport:
        (dossier / "rapport-qualite.json").write_text(
            json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
        if rapport.get("note_moyenne_finale") is not None:
            ctx.journal("  relecture IA : {} -> {} / 10".format(
                rapport["note_moyenne_initiale"], rapport["note_moyenne_finale"]))
        if rapport.get("controle_local"):
            bloc = rapport["controle_local"]
            ctx.journal("  controle local : {} -> {} / 10".format(
                bloc["note_moyenne_initiale"], bloc["note_moyenne_finale"]))
        ctx.journal("  note finale mesuree : {} / 10".format(
            rapport["mesure_finale"]["note_moyenne"]))
    if alertes:
        (dossier / "AVERTISSEMENT.txt").write_text(
            securite.CLAUSE_RENFORCEE + "\n\nDomaines detectes : "
            + ", ".join(d for d, _ in alertes) + "\n",
            encoding="utf-8",
        )

    mots = sum(D.compter_mots(corps) for _, corps in sections)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "sous_titre": sous_titre,
        "dossier": str(dossier),
        "chapitres": total,
        "mots": mots,
        "fichiers": [f.name for f in fichiers],
        "qualite": rapport or None,
        "budget_epuise": budget_epuise,
        "note": (rapport.get("mesure_finale") or {}).get("note_moyenne"),
        "alertes": [d for d, _ in alertes],
    }
    evenements.publier("produit", etat="termine", titre=titre, mots=mots,
                       dossier=str(dossier))
    mesure = rapport.get("mesure_finale") or {}
    defauts = []
    for section in mesure.get("sections", []):
        defauts.extend(a["detail"] for a in section.get("anomalies", []))
    terminer(ctx, fichiers, {
        "mots": mots, "chapitres": total, "promesse": plan.get("promesse"),
        "note": mesure.get("note_moyenne"),
        "note_avant": (rapport.get("controle_local") or {}).get(
            "note_moyenne_initiale"),
        "defauts": defauts,
    })
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _repli(chapitre: Dict[str, Any]) -> str:
    """Contenu de secours d'un chapitre non redige : son plan detaille.

    Livrer un chapitre reduit a son plan vaut mieux que perdre tout le livre
    parce qu'un plafond est tombe au dixieme chapitre.
    """
    return "## {}\n\n{}\n\n{}".format(
        chapitre.get("objectif") or "Points cles",
        chapitre.get("objectif", ""),
        "\n".join("- " + p for p in chapitre.get("points", [])),
    )


def exporter(
    ctx: Contexte, plan: Dict[str, Any], sections: List[Tuple[str, str]]
) -> List[Path]:
    """Ecrit tous les formats de sortie dans le dossier du produit."""
    dossier = ctx.dossier
    titre = plan["titre"]
    sous_titre = plan.get("sous_titre", "")
    fichiers: List[Path] = []

    # --- Markdown maitre ------------------------------------------------
    morceaux = ["# {}".format(titre)]
    if sous_titre:
        morceaux.append("*{}*".format(sous_titre))
    morceaux.append("\n_{}_\n".format(ctx.auteur))
    for titre_section, corps in sections:
        morceaux.append("\n# {}\n".format(titre_section))
        morceaux.append(corps)
    markdown = "\n".join(morceaux).strip() + "\n"
    chemin_md = dossier / "livre.md"
    chemin_md.write_text(markdown, encoding="utf-8")
    fichiers.append(chemin_md)

    blocs_par_section = [(t, D.analyser(c)) for t, c in sections]

    # --- Couverture -----------------------------------------------------
    couverture = None
    if not ctx.sans_image:
        couverture = images.generer_couverture(
            dossier, titre, sous_titre, ctx.auteur,
            style="modern editorial book cover, {}".format(ctx.sujet),
            en_ligne=not ctx.hors_ligne,
        )
        fichiers.append(couverture)

    # --- PDF ------------------------------------------------------------
    doc = DocumentPDF(titre_courant=titre)
    octets_jpeg = None
    if couverture and couverture.suffix.lower() in (".jpg", ".jpeg"):
        octets_jpeg = couverture.read_bytes()
    doc.page_couverture(titre, sous_titre, ctx.auteur, image_jpeg=octets_jpeg)
    for titre_section, blocs in blocs_par_section:
        doc.titre(titre_section, 1)
        D.vers_pdf(blocs, doc, sauter_h1=True)
    doc.inserer_sommaire(apres=1)
    chemin_pdf = dossier / "{}.pdf".format(_nom_fichier(titre))
    doc.enregistrer(chemin_pdf)
    fichiers.append(chemin_pdf)

    # --- EPUB -----------------------------------------------------------
    image_epub = None
    if couverture and couverture.suffix.lower() in (".jpg", ".jpeg", ".png"):
        image_epub = (couverture.name, couverture.read_bytes())
    chapitres_html = [
        (titre_section, D.vers_html(blocs, niveau_depart=2))
        for titre_section, blocs in blocs_par_section
    ]
    chemin_epub = dossier / "{}.epub".format(_nom_fichier(titre))
    construire_epub(
        chemin_epub,
        titre,
        ctx.auteur,
        chapitres_html,
        langue="fr" if ctx.langue.lower().startswith("fran") else "en",
        sous_titre=sous_titre,
        description=plan.get("promesse", ""),
        couverture=image_epub,
    )
    fichiers.append(chemin_epub)

    # --- HTML autonome (lisible sur telephone, imprimable) --------------
    corps_html = []
    for titre_section, blocs in blocs_par_section:
        corps_html.append("<h2>{}</h2>".format(titre_section))
        corps_html.append(D.vers_html(blocs, niveau_depart=3))
    chemin_html = dossier / "lire.html"
    ecrire_page(
        chemin_html,
        titre,
        "\n".join(corps_html),
        sous_titre=sous_titre,
        meta="{} — {} chapitres".format(ctx.auteur, len(sections)),
        couverture=couverture.name if couverture else None,
    )
    fichiers.append(chemin_html)

    # --- Texte brut -----------------------------------------------------
    chemin_txt = dossier / "livre.txt"
    chemin_txt.write_text(
        "\n\n".join(
            "{}\n{}\n\n{}".format(t.upper(), "=" * len(t), D.vers_texte(b))
            for t, b in blocs_par_section
        ),
        encoding="utf-8",
    )
    fichiers.append(chemin_txt)
    return fichiers


def _nom_fichier(titre: str) -> str:
    from .base import slug

    return slug(titre, 48)
