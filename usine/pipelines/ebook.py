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
from ..core import controle as ctrl
from ..core import evenements, securite
from ..render import document as D
from ..render import libelles, livraison
from . import carnet
from .base import (PLUS_RIEN_A_DEMANDER, Contexte, elaguer_markdown,
                   jetons_pour, nettoyer_titre, preparer, terminer)

ROLE = "un auteur de guides pratiques qui se vendent, editeur exigeant"

# Les formes d'un guide. Mesure du 26/09/2026 : il n'en existait qu'une,
# ecrite en dur dans l'invite de chaque chapitre — « au moins une liste
# numerotee d'etapes applicables aujourd'hui », un exemple chiffre, et une
# conclusion en « plan des 30 prochains jours ». Un manuel qu'on consulte sur
# le droit des baux, un recueil de cas de negociation et un programme de
# remise en forme sur quatre semaines sortaient avec la meme charpente et la
# meme derniere page. Rien n'echouait : un reglage par defaut n'est pas
# neutre, il est juste invisible.
#
# Chaque forme dit trois choses au modele, aux trois endroits ou la
# charpente se decide : le plan, le chapitre, l'avant-propos et la fin.
FORMES: Dict[str, Dict[str, str]] = {
    "methode": {
        "nom": "Méthode pas à pas",
        "plan": "Les chapitres forment une progression : chacun suppose le "
                "precedent acquis et fait franchir une etape vers la promesse.",
        "chapitre": "- Commence par un paragraphe d'accroche : une situation "
                    "concrete que le lecteur reconnait.\n"
                    "- Inclus au moins une liste numerotee d'etapes "
                    "applicables aujourd'hui.\n"
                    "- Inclus un exemple chiffre realiste (presente comme un "
                    "exemple, pas comme une statistique officielle).",
        "lecture": "comment le lire : dans l'ordre, un chapitre apres "
                   "l'autre, en appliquant chacun avant de passer au suivant",
        "conclusion": "une synthese des principes cles, puis un plan d'action "
                      "concret semaine par semaine sur 4 semaines, sous forme "
                      "de liste",
    },
    "reference": {
        "nom": "Manuel de référence",
        "plan": "Chaque chapitre se lit SEUL, dans n'importe quel ordre : "
                "c'est un ouvrage qu'on ouvre au moment ou la question se "
                "pose. Le titre de chapitre nomme la question ou la notion "
                "traitee, pour qu'on la retrouve au sommaire.",
        "chapitre": "- Ouvre par la reponse courte, en deux phrases, puis "
                    "developpe.\n"
                    "- Inclus un tableau markdown ou une liste qui resume les "
                    "cas, les seuils ou les options.\n"
                    "- Signale l'erreur la plus frequente dans une ligne qui "
                    "commence exactement par « **Attention :** ».\n"
                    "- Ne suppose pas que le lecteur a lu les autres "
                    "chapitres : renvoie-y par leur titre quand c'est utile.",
        "lecture": "comment le consulter : dans le desordre, au moment ou la "
                   "question se pose, en partant du sommaire",
        "conclusion": "un aide-memoire : les regles, les seuils et les "
                      "reperes a garder sous la main, chapitre par chapitre, "
                      "sous forme de liste — pas de plan d'action",
    },
    "programme": {
        "nom": "Programme par étapes datées",
        "plan": "Chaque chapitre est une etape datee d'un programme "
                "(« Semaine 1 », « Jour 3 »...) : le titre dit la periode ET "
                "ce qu'on y accomplit. La charge de travail monte "
                "progressivement, et le programme tient dans la duree "
                "annoncee par la promesse.",
        "chapitre": "- Ouvre par ce que le lecteur aura accompli a la fin de "
                    "l'etape, et le temps a y consacrer.\n"
                    "- Donne les actions de l'etape en liste numerotee, dans "
                    "l'ordre ou les faire.\n"
                    "- Termine par un point de controle : comment savoir que "
                    "l'etape est reussie avant de passer a la suivante.",
        "lecture": "comment suivre le programme : le rythme, le temps a "
                   "prevoir chaque semaine, et quoi faire si l'on prend du "
                   "retard",
        "conclusion": "le bilan du programme : ce qui est acquis, comment le "
                      "maintenir, et quoi reprendre si une etape a ete sautee",
    },
    "cas": {
        "nom": "Études de cas",
        "plan": "Chaque chapitre part d'une situation concrete differente — "
                "un profil, un contexte, un probleme — et en tire une lecon "
                "applicable. Les cas couvrent des situations variees du "
                "lecteur vise, du plus courant au plus delicat.",
        "chapitre": "- Ouvre par le cas, raconte avec precision : qui, quelle "
                    "situation, quel enjeu. Presente-le comme un exemple "
                    "compose, jamais comme un temoignage reel.\n"
                    "- Analyse ce qui a marche ou echoue, et pourquoi.\n"
                    "- Degage la lecon sous forme d'une methode que le "
                    "lecteur applique a SA situation.",
        "lecture": "comment lire les cas : reperer d'abord celui qui "
                   "ressemble a sa propre situation, puis lire les autres",
        "conclusion": "ce que les cas ont en commun : les principes qui "
                      "reviennent d'un chapitre a l'autre, puis comment "
                      "reconnaitre lequel s'applique a sa propre situation",
    },
    "questions": {
        "nom": "Questions et réponses",
        "plan": "Chaque chapitre repond a UNE question que le lecteur vise "
                "se pose reellement, formulee comme il la formulerait. Le "
                "titre du chapitre EST la question. Elles vont des plus "
                "frequentes aux plus pointues.",
        "chapitre": "- Ouvre par la reponse directe, en une ou deux phrases, "
                    "sans preambule.\n"
                    "- Puis les nuances : dans quels cas la reponse change, "
                    "et pourquoi.\n"
                    "- Termine par ce qu'il faut faire concretement, en liste.",
        "lecture": "comment le parcourir : aller directement a sa question, "
                   "le sommaire les liste toutes",
        "conclusion": "les questions qu'on ne se pose pas encore mais qu'on "
                      "se posera, et comment y repondre avec ce que le livre "
                      "a donne",
    },
}
for _cle, _fiche in FORMES.items():
    _fiche["cle"] = _cle

# Ce que l'ebook faisait avant qu'on puisse choisir : c'est la forme d'un
# livre dont personne n'a decide la forme, et la fabrication le dit.
FORME_PAR_DEFAUT = "methode"

# Le niveau decide de ce qu'on explique et de ce qu'on saute. L'audience le
# suggere, sans le dire : « des freelances » ne dit pas s'ils debutent.
NIVEAUX: Dict[str, str] = {
    "debutant": "Le lecteur part de zero : chaque terme du domaine est "
                "explique a sa premiere apparition, aucune etape n'est "
                "sautee, et chaque notion est suivie d'un exemple.",
    "intermediaire": "Le lecteur connait les bases et les mots du domaine : "
                     "ne les redefinis pas. Concentre-toi sur la methode, les "
                     "arbitrages et les erreurs courantes.",
    "avance": "Le lecteur pratique deja : aucun rappel des bases. Traite les "
              "cas limites, les arbitrages, et ce que les guides pour "
              "debutants simplifient a tort.",
}

# L'exercice va dans un encadre que le rendu sait reconnaitre (« Exercice »
# figure dans « document._ENCADRE ») : il ressort mis en valeur dans le PDF,
# l'EPUB et la page HTML, au lieu d'un paragraphe de plus.
EXERCICE = ("- Avant la ligne « A retenir », ajoute une ligne qui commence "
            "exactement par « **Exercice :** » : une tache de moins de vingt "
            "minutes que le lecteur fait sur SA situation, et ce qu'il doit "
            "avoir obtenu a la fin.")


def forme_de(ctx: Contexte, forme: str = "") -> Dict[str, str]:
    """La forme retenue, et le journal dit quand personne ne l'a choisie."""
    if forme in FORMES:
        return FORMES[forme]
    ctx.journal("  forme : {} (personne ne l'a choisie)".format(
        FORMES[FORME_PAR_DEFAUT]["nom"]))
    return FORMES[FORME_PAR_DEFAUT]


def _consignes_de_lecteur(niveau: str) -> str:
    return ("NIVEAU DU LECTEUR : " + NIVEAUX[niveau] + "\n") if niveau in NIVEAUX else ""


def construire_plan(ctx: Contexte, forme: Dict[str, str] = FORMES[FORME_PAR_DEFAUT],
                    niveau: str = "") -> Dict[str, Any]:
    """Titre commercial + structure detaillee, en JSON."""
    invite = (
        "Concois le plan d'un ebook pratique et vendable sur ce sujet :\n"
        "SUJET : {sujet}\n"
        "LECTEUR : {audience}\n"
        "{niveau}"
        "LONGUEUR : {n} chapitres.\n"
        "FORME DU LIVRE : {forme} — {charpente} Cette forme prime sur la "
        "progression habituelle.\n\n"
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
    ).format(sujet=ctx.sujet, audience=ctx.audience, n=ctx.nb_chapitres,
             niveau=_consignes_de_lecteur(niveau), forme=forme["nom"],
             charpente=forme["plan"])

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
    ctx: Contexte, plan: Dict[str, Any], index: int, chapitre: Dict[str, Any],
    forme: Dict[str, str] = FORMES[FORME_PAR_DEFAUT], niveau: str = "",
    exercices: bool = False,
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
        "AUTRES CHAPITRES (ne les traite pas, evite les redites) : {autres}\n"
        "{niveau}"
        "FORME DU LIVRE : {forme}. Ce qu'elle demande prime sur tes "
        "habitudes de redaction.\n\n"
        "Consignes de redaction :\n"
        "- Environ {mots} mots.\n"
        "- Pas de repetition du titre en ouverture.\n"
        "- Structure avec des sous-titres markdown de niveau 2 (##) et 3 (###).\n"
        "{charpente}\n"
        "{exercice}"
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
        niveau=_consignes_de_lecteur(niveau),
        forme=forme["nom"],
        charpente=forme["chapitre"],
        exercice=(EXERCICE + "\n") if exercices else "",
    )
    reponse = equipe.REDACTEUR.travailler(
        ctx, invite, max_tokens=jetons_pour(ctx.mots_par_chapitre)
    )
    texte = elaguer_markdown(reponse.texte)
    # Le modele reintroduit parfois un titre h1 : on le retire pour eviter le doublon.
    lignes = texte.split("\n")
    if lignes and lignes[0].startswith("# "):
        lignes.pop(0)
    return "\n".join(lignes).strip(), reponse.fournisseur


def rediger_annexe(ctx: Contexte, plan: Dict[str, Any], genre: str,
                   forme: Dict[str, str] = FORMES[FORME_PAR_DEFAUT]) -> Tuple[str, str]:
    """Avant-propos ou conclusion. Renvoie (titre, markdown)."""
    sommaire = "\n".join("- " + c["titre"] for c in plan["chapitres"])
    if genre == "introduction":
        titre = libelles.libelle(ctx.langue_iso, "ebook_avant_propos")
        consigne = (
            "Redige l'avant-propos (450 mots environ) : le probleme que vit le lecteur, "
            "pourquoi les solutions habituelles echouent, ce que ce livre change, "
            "et {lecture}. Termine par une invitation a s'y mettre."
        ).format(lecture=forme["lecture"])
    else:
        # Le titre suit la forme : « votre plan des 30 prochains jours » en
        # tete d'un aide-memoire annoncait une page qui n'existe pas. Chaque
        # libelle est lu en toutes lettres : un nom compose a la volee
        # echapperait au test qui repere le texte que plus rien ne lit.
        t = libelles.textes(ctx.langue_iso)
        titre = {"methode": t["ebook_conclusion"],
                 "reference": t["ebook_conclusion_reference"],
                 "programme": t["ebook_conclusion_programme"],
                 "cas": t["ebook_conclusion_cas"],
                 "questions": t["ebook_conclusion_questions"]}[forme["cle"]]
        consigne = (
            "Redige la conclusion (450 mots environ) : {contenu}. Termine sur "
            "une phrase sobre, sans promesse de resultat garanti."
        ).format(contenu=forme["conclusion"])
    invite = (
        "Ebook : « {livre} »\nFORME : {forme}\nPROMESSE : {promesse}\n"
        "SOMMAIRE :\n{sommaire}\n\n{consigne}\n"
        "Markdown uniquement, sous-titres de niveau 2 (##) autorises, "
        "pas de titre de niveau 1."
    ).format(
        livre=plan["titre"],
        forme=forme["nom"],
        promesse=plan.get("promesse", ""),
        sommaire=sommaire,
        consigne=consigne,
    )
    reponse = equipe.REDACTEUR.travailler(ctx, invite, max_tokens=1800)
    return titre, elaguer_markdown(reponse.texte)


def produire(ctx: Contexte, relecture_ensemble: bool = False, forme: str = "",
             niveau: str = "", exercices: str = "") -> Dict[str, Any]:
    """Produit l'ebook complet et renvoie un resume des fichiers generes.

    « relecture_ensemble » ajoute UNE lecture du livre entier a la recherche
    des contradictions entre chapitres. Un appel de modele par produit, sur
    un long texte : c'est pourquoi elle se demande.

    « forme », « niveau » et « exercices » arrivent vides quand personne ne
    les a choisis ET que l'usine n'a pas pu les decider (voir
    « brief.decider_les_reglages ») : la forme retombe alors sur la methode
    pas a pas, et le journal le dit.
    """
    charpente = forme_de(ctx, forme)
    avec_exercices = str(exercices).strip().lower() == "avec"
    ctx.journal("Étape 1/5 — construction du plan...")
    # Une reprise DOIT repartir du meme plan. Un plan reconstruit differe —
    # le modele n'est pas deterministe — et les chapitres deja ecrits se
    # retrouveraient ranges sous des titres qui ne sont plus les leurs.
    repris = carnet.plan(ctx.dossier) if ctx.dossier and ctx.dossier.name else None
    plan = repris or construire_plan(ctx, charpente, niveau)
    titre = plan["titre"]
    sous_titre = plan.get("sous_titre", "")
    dossier = preparer(ctx, "ebook", titre)
    if repris:
        ctx.journal("  Reprise : plan et {} section(s) déjà au carnet."
                    .format(carnet.compte(dossier)))
    ctx.etape("plan", "ok", "{} chapitres".format(len(plan["chapitres"])))
    ctx.journal('  Titre retenu : « {} »'.format(titre))
    (dossier / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    carnet.noter_plan(dossier, plan)

    total = len(plan["chapitres"])
    sections: List[Tuple[str, str]] = []
    qualite: Dict[str, List[Critique]] = {}
    local: Dict[str, List[ctrl.Controle]] = {}

    alertes = securite.analyser_sujet(ctx.sujet)
    for domaine, avertissement in alertes:
        ctx.journal("  [!] domaine sensible « {} » : {}".format(domaine, avertissement))
        evenements.publier("alerte", domaine=domaine, detail=avertissement)

    budget_epuise = False

    manquants: List[str] = []

    ctx.journal("Étape 2/5 — avant-propos...")
    deja = carnet.section(dossier, "introduction")
    if deja:
        sections.append(deja)
        ctx.journal("  déjà écrit — repris du carnet")
    else:
        try:
            titre_intro, corps_intro = rediger_annexe(ctx, plan, "introduction",
                                                      charpente)
            sections.append((titre_intro, corps_intro))
            carnet.noter_section(dossier, "introduction", titre_intro, corps_intro)
            ctx.etape("introduction")
        except PLUS_RIEN_A_DEMANDER as exc:
            budget_epuise = True
            manquants.append("avant-propos")
            ctx.journal("  {} — avant-propos ignore".format(exc))
            ctx.etape("introduction", "echec", str(exc))

    ctx.journal("Étape 3/5 — rédaction des {} chapitres...".format(total))
    passes = ctx.nb_passes
    if passes:
        ctx.journal("  qualité « {} » : {} relecture(s) éditoriale(s) par chapitre"
                    .format(ctx.qualite, passes))
    for index, chapitre in enumerate(plan["chapitres"]):
        ctx.journal("  [{}/{}] {}".format(index + 1, total, chapitre["titre"]))
        evenements.publier("section", etape="redaction", index=index + 1,
                           total=total, titre=chapitre["titre"])
        repere = "chapitre-{}".format(index + 1)
        fait = carnet.section(dossier, repere)
        if fait:
            sections.append(fait)
            ctx.journal("     déjà écrit — repris du carnet")
            ctx.etape(repere, "ok", fait[0])
            continue
        if budget_epuise:
            # Inutile de tenter les chapitres suivants : chaque appel serait
            # refuse. On les remplace par leur plan et on va a l'export. Le
            # carnet ne les recoit PAS : un repli n'est pas un chapitre, et
            # une reprise doit encore les ecrire.
            sections.append((chapitre["titre"], _repli(chapitre)))
            manquants.append(repere)
            ctx.etape(repere, "echec", "plus rien a demander")
            continue
        try:
            corps, auteur = rediger_chapitre(ctx, plan, index, chapitre,
                                             charpente, niveau, avec_exercices)
        except PLUS_RIEN_A_DEMANDER as exc:
            budget_epuise = True
            manquants.append(repere)
            ctx.journal("     {} — chapitres restants réduits à leur plan".format(exc))
            ctx.etape(repere, "echec", str(exc))
            sections.append((chapitre["titre"], _repli(chapitre)))
            continue
        except Exception as exc:
            # Ce chapitre-ci est remplace par son plan, mais la fabrication
            # continue : une panne passagere sur un chapitre ne doit pas
            # emporter le livre. Il faut en revanche le traiter comme les
            # deux cas au-dessus — sinon le repli descendait jusqu'au carnet
            # et s'y inscrivait comme un chapitre ecrit, marque « ok » en
            # sortie de boucle. Le livre se livrait « pret », et « usine
            # reprendre » ne refaisait jamais ce chapitre-la : le plan
            # partait chez l'acheteur a sa place, definitivement.
            ctx.journal("     échec : {} — chapitre à refaire".format(exc))
            manquants.append(repere)
            ctx.etape(repere, "echec", str(exc))
            sections.append((chapitre["titre"], _repli(chapitre)))
            continue
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
                ctx.journal("     contrôle : " + controles[-1].resume())
            except PLUS_RIEN_A_DEMANDER as exc:
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
                    # Passe de style finale, reservee au niveau exigeant : le
                    # STYLISTE resserre ce que l'editeur a valide. C'est le
                    # dernier agent de la chaine, et le plus discret.
                    if passes >= 2:
                        corps = equipe.polir(ctx, corps, auteur)
                        ctx.journal("     style : resserre par le styliste")
                except PLUS_RIEN_A_DEMANDER as exc:
                    budget_epuise = True
                    ctx.journal("     {} — relecture interrompue".format(exc))
        sections.append((chapitre["titre"], corps))
        # Au carnet MAINTENANT, pas a la fin de la boucle : le seul moment ou
        # l'on est sur de pouvoir ecrire, c'est celui-ci.
        carnet.noter_section(dossier, repere, chapitre["titre"], corps)
        ctx.etape(repere, "ok", chapitre["titre"])

    ctx.journal("Étape 4/5 — conclusion...")
    finie = carnet.section(dossier, "conclusion")
    if finie:
        sections.append(finie)
        ctx.journal("  déjà écrite — reprise du carnet")
    elif budget_epuise:
        manquants.append("conclusion")
        ctx.journal("  ignorée : plus rien à demander")
        ctx.etape("conclusion", "echec", "plus rien a demander")
    else:
        try:
            titre_fin, corps_fin = rediger_annexe(ctx, plan, "conclusion",
                                                  charpente)
            sections.append((titre_fin, corps_fin))
            carnet.noter_section(dossier, "conclusion", titre_fin, corps_fin)
            ctx.etape("conclusion")
        except PLUS_RIEN_A_DEMANDER as exc:
            budget_epuise = True
            manquants.append("conclusion")
            ctx.journal("  {} — conclusion ignorée".format(exc))
            ctx.etape("conclusion", "echec", str(exc))

    ensemble = {}
    if relecture_ensemble and not budget_epuise:
        ctx.journal("Relecture d'ensemble : contradictions entre chapitres...")
        try:
            ensemble = equipe.relire_l_ensemble(
                ctx, sections, plan.get("promesse", ""))
        except PLUS_RIEN_A_DEMANDER as exc:
            budget_epuise = True
            ctx.journal("  {} — relecture d'ensemble ignorée".format(exc))
        except Exception as exc:
            ctx.journal("  relecture d'ensemble indisponible : {}".format(exc))
        if ensemble.get("disponible"):
            ctx.journal("  " + ensemble["resume"])
            for souci in ensemble["incoherences"][:4]:
                ctx.journal("    [{}] {}".format(souci["gravite"],
                                                 souci["probleme"][:90]))
        # Une mesure, pas un chapitre : un livre dont la relecture d'ensemble
        # n'a pas pu tourner reste un livre entier. Le marquer inacheve
        # enverrait « usine reprendre » refaire un livre complet pour une
        # mesure manquante.
        ctx.etape("ensemble", "ok" if ensemble.get("disponible") else "echec",
                  ensemble.get("resume", ""), essentiel=False)

    # Le lecteur : la seule voix qui ne juge pas le metier. Tout le reste de
    # l'usine juge le TEXTE ; personne ne demandait s'il est comprehensible
    # pour celui a qui on le vend. Un chapitre techniquement excellent et
    # incomprehensible pour son audience est un chapitre rate, et rien ne le
    # signalait.
    lecture = {}
    if relecture_ensemble and not budget_epuise:
        ctx.journal("Lecture par l'audience : ce qui n'est pas compris...")
        try:
            lecture = equipe.lire_comme_l_audience(
                ctx, sections, plan.get("promesse", ""))
        except PLUS_RIEN_A_DEMANDER as exc:
            budget_epuise = True
            ctx.journal("  {} — lecture par l'audience ignorée".format(exc))
        except Exception as exc:
            ctx.journal("  lecture par l'audience indisponible : {}".format(exc))
        if lecture.get("disponible"):
            ctx.journal("  " + lecture["resume"])
            for decrochage in lecture["decrochages"][:3]:
                ctx.journal("    « {} » — {}".format(
                    str(decrochage.get("passage", ""))[:60],
                    str(decrochage.get("pourquoi", ""))[:80]))
            if lecture["mots_non_expliques"]:
                ctx.journal("    jamais expliques : "
                            + ", ".join(lecture["mots_non_expliques"][:6]))
        ctx.etape("lecteur", "ok" if lecture.get("disponible") else "echec",
                  lecture.get("resume", ""), essentiel=False)

    ctx.journal("Étape 5/5 — mise en forme et export...")
    fichiers = exporter(ctx, plan, sections)

    rapport = equipe.rapport_qualite(qualite) if qualite else {}
    if ensemble:
        rapport["ensemble"] = ensemble
    if lecture:
        rapport["lecteur"] = lecture
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
            ctx.journal("  contrôle local : {} -> {} / 10".format(
                bloc["note_moyenne_initiale"], bloc["note_moyenne_finale"]))
        ctx.journal("  note finale mesurée : {} / 10".format(
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
        "manquants": manquants,
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
    """Confie le livre a l'assemblage commun.

    Un ebook est le cas le plus simple : des sections en prose, aucune mise en
    page particuliere. Tout — couverture, markdown, PDF, EPUB, HTML, texte —
    est le comportement par defaut de usine/render/livraison.py.
    """
    produit = livraison.Produit(
        type="ebook",
        titre=plan["titre"],
        sous_titre=plan.get("sous_titre", ""),
        promesse=plan.get("promesse", ""),
        blocs=livraison.blocs_depuis_sections(sections),
        formats=("md", "pdf", "epub", "html", "txt"),
        police_corps="Times-Roman",
        style_couverture="modern editorial book cover, {}".format(ctx.sujet),
        langue=ctx.langue_iso,
        libelle_sections=libelles.libelle(ctx.langue_iso, "unite_chapitres"),
    )
    return livraison.livrer(ctx, produit)
