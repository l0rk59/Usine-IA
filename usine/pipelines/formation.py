"""Mini-formation : modules pedagogiques, cahier d'exercices et sequence e-mail."""

from __future__ import annotations


import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..agents import equipe
from ..core import images
from ..render import libelles, livraison, narration, quiz
from ..render.pdf import DocumentPDF
from .base import (Contexte, elaguer_markdown, jetons_pour, nettoyer_titre,
                   preparer, slug, terminer)


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
    programme = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="costaud",
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
    reponse = equipe.FORMATEUR.travailler(
        ctx, invite, role_modele="standard",
                          temperature=0.75,
                          max_tokens=jetons_pour(ctx.mots_par_chapitre))
    texte = elaguer_markdown(reponse.texte)
    lignes = texte.split("\n")
    if lignes and lignes[0].startswith("# "):
        lignes.pop(0)
    return "\n".join(lignes).strip()


def _quiz(ctx: Contexte, programme: Dict[str, Any],
          par_module: int = 2) -> List[Dict[str, Any]]:
    """Questions a choix unique, deux par module, en un seul appel.

    Un seul appel plutot qu'un par module : le modele voit alors toute la
    progression et evite de poser deux fois la meme question sous deux
    formes. Sur une formation de huit modules, c'est sept appels economises.
    """
    modules = "\n".join(
        "- {} — objectif : {} ; notions : {}".format(
            module["titre"], module["objectif"],
            ", ".join(module["notions"]) or "libres")
        for module in programme["modules"])
    invite = (
        "Redige le quiz d'auto-evaluation de cette mini-formation.\n"
        "FORMATION : {titre}\n"
        "PROMESSE : {promesse}\n"
        "MODULES :\n{modules}\n\n"
        "{n} question(s) par module, dans l'ordre des modules.\n"
        "Contraintes :\n"
        "- Chaque question porte sur ce que l'apprenant doit SAVOIR FAIRE, "
        "pas sur une definition a reciter.\n"
        "- Trois ou quatre propositions, dont UNE SEULE est juste.\n"
        "- Les mauvaises propositions sont plausibles : ce sont les erreurs "
        "que fait vraiment un debutant, pas des absurdites.\n"
        "- « reponse » est l'INDICE de la bonne proposition, a partir de 0.\n"
        "- L'explication dit pourquoi la bonne reponse est bonne, en une ou "
        "deux phrases.\n\n"
        "Schema JSON exact :\n"
        '{{"quiz": [{{"module": "titre du module", "question": "...", '
        '"propositions": ["...", "...", "..."], "reponse": 0, '
        '"explication": "..."}}]}}'
    ).format(titre=programme["titre"], promesse=programme.get("promesse", ""),
             modules=modules, n=par_module)

    brut = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="costaud",
                            temperature=0.5, max_tokens=3200)
    questions = brut.get("quiz") if isinstance(brut, dict) else None
    if not isinstance(questions, list):
        return []

    titres = [module["titre"] for module in programme["modules"]]
    propres: List[Dict[str, Any]] = []
    for element in questions:
        if not isinstance(element, dict):
            continue
        propositions = [str(p).strip() for p in element.get("propositions") or []
                        if str(p).strip()]
        # Une question a une seule proposition n'en est pas une, et une
        # reponse hors des bornes designerait une proposition inexistante :
        # le quiz afficherait alors « la bonne reponse etait undefined ».
        if len(propositions) < 2:
            continue
        try:
            reponse = int(element.get("reponse", 0))
        except (TypeError, ValueError):
            continue
        if not 0 <= reponse < len(propositions):
            continue
        intitule = str(element.get("question") or "").strip()
        if not intitule:
            continue
        module = str(element.get("module") or "").strip()
        propres.append({
            "module": module if module in titres else "",
            "question": intitule,
            "propositions": propositions,
            "reponse": reponse,
            "explication": str(element.get("explication") or "").strip(),
        })
    return propres


def _narration(ctx: Contexte, programme: Dict[str, Any],
               contenus: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Reecrit chaque module pour qu'il se DISE, pas qu'il se lise.

    Un appel par module, contrairement au quiz : convertir huit modules en
    une fois depasserait le budget de jetons d'une reponse, et une narration
    tronquee au module six ne vaut rien. C'est pourquoi elle est en option —
    elle double le cout d'une formation, et l'utilisateur doit le decider.
    """
    scripts: List[Tuple[str, str]] = []
    for index, (nom, corps) in enumerate(contenus):
        module = programme["modules"][index] if index < len(
            programme["modules"]) else {}
        invite = (
            "Reecris ce module de formation en SCRIPT DE NARRATION, destine a "
            "etre lu a voix haute devant un micro.\n\n"
            "FORMATION : {formation}\n"
            "MODULE {num}/{total} : {titre}\n"
            "OBJECTIF : {objectif}\n\n"
            "--- TEXTE ECRIT ---\n{corps}\n--- FIN ---\n\n"
            "Ce qui change a l'oral :\n"
            "- Aucun sous-titre, aucune puce, aucune numerotation : ce qui "
            "etait une liste devient une enumeration parlee "
            "(« Premier point : ... Deuxieme : ... »).\n"
            "- Des phrases COURTES. On ne relit pas une phrase entendue.\n"
            "- Aucune reference visuelle : ni « ci-dessus », ni « le schema "
            "suivant », ni « comme on l'a vu plus haut ».\n"
            "- Commence par une accroche de deux phrases qui donne envie "
            "d'ecouter la suite, et termine par une transition vers le "
            "module suivant.\n"
            "- Place « [PAUSE] » aux respirations, et « [INSISTER] » devant "
            "ce qui doit etre appuye. Rien d'autre entre crochets.\n"
            "- Garde les exemples chiffres : ce sont eux qui tiennent "
            "l'attention.\n\n"
            "Reponds uniquement par le texte a dire."
        ).format(formation=programme["titre"], num=index + 1,
                 total=len(contenus), titre=module.get("titre", nom),
                 objectif=module.get("objectif", ""), corps=corps[:9000])
        reponse = equipe.FORMATEUR.travailler(
        ctx, invite, role_modele="standard",
                              temperature=0.7,
                              max_tokens=jetons_pour(ctx.mots_par_chapitre))
        scripts.append((nom, elaguer_markdown(reponse.texte)))
        ctx.journal("  [{}/{}] {}".format(index + 1, len(contenus), nom))
    return scripts


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
    donnees = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="standard",
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


def produire(ctx: Contexte, modules: int = 0,
             narration: bool = False) -> Dict[str, Any]:
    modules = modules or max(5, min(ctx.nb_chapitres, 10))
    ctx.journal("Etape 1/5 — programme pedagogique ({} modules)...".format(modules))
    programme = _programme(ctx, modules)
    titre = programme["titre"]
    dossier = preparer(ctx, "formation", titre)
    ctx.etape("programme", "ok", "{} modules".format(len(programme["modules"])))
    ctx.journal('  Formation : « {} »'.format(titre))

    ctx.journal("Etape 2/5 — redaction des modules...")
    contenus: List[Tuple[str, str]] = []
    for index, module in enumerate(programme["modules"]):
        ctx.journal("  [{}/{}] {}".format(index + 1, len(programme["modules"]),
                                          module["titre"]))
        perdu = ""
        try:
            corps = _rediger_module(ctx, programme, index, module)
        except Exception as exc:
            perdu = str(exc)
            ctx.journal("     echec : {}".format(exc))
            # Le module est remplace par son PLAN : quelques puces la ou
            # l'acheteur attend une lecon. C'est un trou, pas un module.
            corps = libelles.libelle(
                ctx.langue_iso, "module_plan", objectif=module["objectif"],
                notions="\n".join("- " + n for n in module["notions"]))
        contenus.append((libelles.libelle(ctx.langue_iso, "module_titre",
                                          numero=index + 1, titre=module["titre"]),
                         corps))
        # Un seul appel, et apres coup. La version d'avant notait « echec »
        # dans la branche d'erreur puis « ok » deux lignes plus bas, hors du
        # « else » : le dernier statut ecrasait le premier, et le module
        # remplace par son plan passait pour un module ecrit.
        ctx.etape("module-{}".format(index + 1),
                  "echec" if perdu else "ok", perdu)

    ctx.journal("Etape 3/5 — quiz d'auto-evaluation...")
    try:
        questions = _quiz(ctx, programme)
    except Exception as exc:
        # Le quiz est un plus : son echec ne doit pas emporter la formation.
        ctx.journal("  quiz indisponible : {}".format(exc))
        questions = []
    ctx.etape("quiz", "ok" if questions else "echec",
              "{} question(s)".format(len(questions)), essentiel=False)

    scripts: List[Tuple[str, str]] = []
    if narration:
        ctx.journal("Etape 4/6 — script de narration (un appel par module)...")
        try:
            scripts = _narration(ctx, programme, contenus)
        except Exception as exc:
            ctx.journal("  narration indisponible : {}".format(exc))
            scripts = []
        ctx.etape("narration", "ok" if scripts else "echec",
                  "{} script(s)".format(len(scripts)), essentiel=False)

    ctx.journal("Etape {} — sequence e-mail de livraison...".format(
        "5/6" if narration else "4/5"))
    try:
        emails = _sequence_email(ctx, programme)
    except Exception as exc:
        ctx.journal("  sequence e-mail indisponible : {}".format(exc))
        emails = []
    ctx.etape("emails", "ok" if emails else "echec",
              "{} e-mails".format(len(emails)), essentiel=False)

    ctx.journal("Etape {} — export...".format("6/6" if narration else "5/5"))
    fichiers = _exporter(ctx, programme, contenus, emails, questions, scripts)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "modules": len(contenus),
        "emails": len(emails),
        "questions": len(questions),
        "narration": ctx.meta.get("narration"),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"modules": len(contenus), "emails": len(emails),
                             "questions": len(questions)})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resume


def _exporter(ctx: Contexte, programme: Dict[str, Any], contenus: List[Tuple[str, str]],
              emails: List[Dict[str, str]],
              questions: Optional[List[Dict[str, Any]]] = None,
              scripts: Optional[List[Tuple[str, str]]] = None) -> List[Path]:
    """Confie la formation a l'assemblage commun.

    Deux specificites : un cahier d'exercices qui est un second document PDF,
    et la sequence e-mail, un markdown a part. Le reste est standard.
    """
    titre = programme["titre"]
    prerequis = str(programme.get("prerequis") or "")
    t = libelles.textes(ctx.langue_iso)

    def avant_propos(doc) -> None:
        doc.paragraphe(programme.get("promesse", ""), justifier=True)
        if prerequis:
            doc.encadre(t["formation_prerequis"], prerequis)
        doc.paragraphe(t["formation_methode"], justifier=True)

    blocs = [livraison.Bloc(titre=t["formation_avant"], rendu_pdf=avant_propos)]
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
        suffixe_pdf=t["fichier_manuel"],
        libelle_sections=t["unite_modules"],
        documents=[(t["fichier_cahier"], _cahier(ctx, programme, titre))],
    )
    fichiers = livraison.livrer(ctx, produit)

    if questions:
        # Page autonome : l'apprenant l'ouvre depuis le dossier, hors ligne,
        # et la correction se fait dans son navigateur. Rien n'est envoye.
        fichiers.append(quiz.ecrire(
            ctx.dossier / "quiz.html", titre, questions,
            promesse=programme.get("promesse", ""), langue=ctx.langue_iso))

    if scripts:
        document, mesures = narration.assembler(titre, scripts)
        chemin = ctx.dossier / "narration.md"
        chemin.write_text(document, encoding="utf-8")
        fichiers.append(chemin)
        ctx.meta["narration"] = mesures
        ctx.journal("  narration : {} mots — {}".format(
            mesures["mots"], narration.minutes_lisibles(mesures)))

    if emails:
        lignes = ["# {}\n".format(t["sequence_titre"].format(titre=titre))]
        for email in emails:
            lignes.append("\n## {}\n".format(t["sequence_jour"].format(
                jour=email["jour"], objet=email["objet"])))
            lignes.append(email["corps"])
            if email["action"]:
                lignes.append("\n{}\n".format(t["deux_points"].format(
                    libelle="**{}**".format(t["sequence_action"]),
                    texte=email["action"])))
        chemin = ctx.dossier / "sequence-emails.md"
        chemin.write_text("\n".join(lignes), encoding="utf-8")
        fichiers.append(chemin)
    return fichiers


def _cahier(ctx: Contexte, programme: Dict[str, Any], titre: str):
    """Construit le cahier d'exercices, second document du produit."""

    t = libelles.textes(ctx.langue_iso)

    def construire(_couverture):
        # Le cahier compose la sienne plutot que de reprendre celle du manuel :
        # c'est un document distinct, que l'acheteur ouvre separement.
        doc = DocumentPDF(titre_courant=t["cahier_titre_courant"].format(titre=titre),
                          police_corps="Helvetica", langue=ctx.langue_iso)
        if ctx.sans_image:
            doc.page_couverture(t["cahier_titre"], titre, ctx.auteur)
        else:
            doc.page_couverture_image(*images.couverture_pleine_page(
                t["cahier_titre"], titre, ctx.auteur,
                getattr(ctx, "marque", "") or ""))
        for index, module in enumerate(programme["modules"], 1):
            doc.titre(t["module_titre"].format(numero=index, titre=module["titre"]), 1)
            if module["objectif"]:
                doc.paragraphe(t["deux_points"].format(
                    libelle=t["cahier_objectif"], texte=module["objectif"]),
                    taille=10.5)
            if module["livrable"]:
                doc.encadre(t["cahier_livrable"], module["livrable"])
            if module["exercice"]:
                doc.titre(t["cahier_consigne"], 2)
                doc.paragraphe(module["exercice"], justifier=True)
            doc.titre(t["cahier_notes"], 2)
            doc.lignes_a_remplir(9)
        return doc

    return construire
