"""Recueil de nouvelles : sept histoires qui ne doivent pas etre la meme.

Pourquoi une chaine a part. Fabriquer sept nouvelles et les agrafer ne fait
pas un recueil : cela fait sept nouvelles dans le meme fichier. Ce qui fait la
valeur d'un recueil, c'est qu'il se lise d'un bout a l'autre — donc que les
textes se REPONDENT sans se repeter, et que l'ordre soit voulu.

Et c'est precisement la ou la fiction generee est la plus faible. Les etudes
publiques sur les textes de modeles le disent toutes de la meme facon :
personnages archetypaux, tensions desamorcees, resolutions trop nettes. Sur
une nouvelle isolee, cela passe. Sur sept d'affilee, cela se voit — le lecteur
reconnait la meme histoire a la troisieme, et repose le livre.

D'ou le controle qui donne son interet a cette chaine, et qui n'existe nulle
part ailleurs dans l'usine : mesurer que les sept recits ne sont PAS le meme.
Il se fait en deux temps, et le premier est le moins cher :

  AVANT d'ecrire   les premisses proposees se ressemblent-elles ? Deux
                   premisses jumelles coutent deux recits a decouvrir ;
  APRES avoir ecrit les protagonistes, les fins et les longueurs se
                   distinguent-ils vraiment ?

Les deux sont deterministes : ils comparent des chaines et comptent des mots.
Aucun n'appelle un modele, et aucun ne juge la qualite d'un texte — ils
mesurent un ECART, ce qui est verifiable, la ou « ce recit est banal » ne
l'est pas.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..agents import equipe
from ..core import empreinte
from ..render import libelles, livraison
from . import carnet
from . import fiction
from . import memoire as M
from . import prose
from .base import (PLUS_RIEN_A_DEMANDER, Contexte, Redaction, nettoyer_titre,
                   preparer, terminer)

RECITS = 7
RECITS_MIN, RECITS_MAX = 3, 15
# Quatre scenes : la longueur d'une nouvelle de revue. En dessous, le recit
# n'a pas la place d'un retournement ; au-dessus, ce n'est plus un recueil,
# c'est un roman decoupe.
SCENES_PAR_RECIT = 4
# Au-dela de cette proportion de mots porteurs partages, deux premisses sont
# la meme histoire dite deux fois, et on redemande le fil.
#
# Le seuil est celui des niches, et il est VOLONTAIREMENT haut. Mesure du
# 15/09/2026 : « une libraire herite du phare de son pere et y trouve une
# lettre » contre « une libraire recoit le phare de son pere et decouvre une
# lettre » donne 0,67 — deux fois la meme histoire, et ce controle la laisse
# passer.
#
# C'est assume, et c'est la regle du depot : rater un defaut plutot qu'en
# inventer un. Un recueil ou deux textes se repondent volontairement — deux
# versions d'un meme evenement, un diptyque — est un procede, pas une faute,
# et un controle qui le refuserait finirait ignore.
#
# Ce qui compense : la proximite maximale est RENDUE dans tous les cas, avec
# son chiffre. Le 0,67 se voit, et c'est un humain qui tranche.
SEUIL_JUMELLES = empreinte.SEUIL_SUJET


def _fil(ctx: Contexte, nombre: int) -> Dict[str, Any]:
    """Le fil du recueil, et les premisses qui doivent differer."""
    invite = (
        "Concois un RECUEIL de {n} nouvelles autour de : {sujet}\n"
        "LECTEUR : {audience}\n{promesse}\n"
        "Un recueil n'est pas {n} nouvelles agrafees. Les textes se "
        "repondent : un fil les traverse, et l'ordre est voulu.\n\n"
        "Le piege a eviter, et c'est le seul qui compte : ecrire {n} fois la "
        "meme histoire avec d'autres noms. Chaque premisse doit differer des "
        "autres par au moins deux choses parmi : qui la vit, ce qui est en "
        "jeu, l'epoque, le registre, et la facon dont elle finit.\n\n"
        "Varie aussi les FINS : un recueil ou tout se resout bien se lit "
        "comme un catalogue. Il en faut d'amères, d'ouvertes, de "
        "suspendues.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "le titre du recueil", '
        '"fil": "ce qui traverse les textes, une phrase", '
        '"recits": [{{"titre": "...", "premisse": "deux phrases", '
        '"qui": "le personnage central, en trois mots", "registre": "...", '
        '"fin": "heureuse|amere|ouverte|ironique|tragique", '
        '"place": "pourquoi ce texte est a cette place dans le recueil"}}]}}'
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience,
             promesse=fiction.consignes(ctx))
    donnees = equipe.SCENARISTE.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.85, max_tokens=3000)
    if not isinstance(donnees, dict):
        raise ValueError("Fil du recueil illisible")
    recits = []
    for brut in donnees.get("recits") or []:
        if not isinstance(brut, dict) or not str(brut.get("titre") or "").strip():
            continue
        recits.append({
            "titre": nettoyer_titre(str(brut["titre"])),
            "premisse": str(brut.get("premisse") or "").strip(),
            "qui": str(brut.get("qui") or "").strip(),
            "registre": str(brut.get("registre") or "").strip(),
            "fin": str(brut.get("fin") or "").strip().lower(),
            "place": str(brut.get("place") or "").strip(),
        })
    if not recits:
        raise ValueError("Aucun recit exploitable dans le fil")
    # Ce qui a ete demande fait foi. Un modele qui rend douze premisses quand
    # on en demande trois ferait fabriquer douze recits, donc quatre fois le
    # temps et le quota annonces — et l'utilisateur ne l'apprendrait qu'a la
    # fin. Mesure du 15/09/2026 : la premiere version livrait sept recits
    # pour trois demandes, sans un mot.
    return {"titre": nettoyer_titre(str(donnees.get("titre") or ctx.sujet)),
            "fil": str(donnees.get("fil") or "").strip(),
            "recits": recits[:nombre]}


def premisses_jumelles(recits: Sequence[Dict[str, Any]],
                       seuil: float = SEUIL_JUMELLES) -> List[Tuple[int, int, float]]:
    """Les couples de recits qui racontent la meme chose.

    Compare les PREMISSES, pas les titres : deux titres peuvent differer
    entierement et couvrir la meme histoire, et c'est le cas le plus frequent
    — un modele varie le vocabulaire bien avant de varier le fond.

    Se fait avant d'ecrire. Une premisse jumelle detectee ici coute un appel
    a corriger ; detectee a la lecture, elle coute le recueil.
    """
    doubles = []
    for gauche in range(len(recits)):
        for droite in range(gauche + 1, len(recits)):
            score = empreinte.ressemblance_sujet(
                _texte_compare(recits[gauche]), _texte_compare(recits[droite]))
            if score >= seuil:
                doubles.append((gauche, droite, round(score, 2)))
    return doubles


def _texte_compare(recit: Dict[str, Any]) -> str:
    return "{} {}".format(recit.get("premisse", ""), recit.get("qui", ""))


def proximite_maximale(recits: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Le couple de recits le plus proche, et de combien. Toujours rendu.

    C'est le pendant du seuil haut : ce qui passe sous la barre reste
    visible. Sans cette mesure, un recueil dont deux textes se ressemblent a
    0,67 sortirait en annoncant « aucune premisse jumelle », ce qui est vrai
    au sens du controle et trompeur au sens de l'auteur.
    """
    meilleur = {"couple": (), "score": 0.0}
    for gauche in range(len(recits)):
        for droite in range(gauche + 1, len(recits)):
            score = empreinte.ressemblance_sujet(
                _texte_compare(recits[gauche]), _texte_compare(recits[droite]))
            if score > meilleur["score"]:
                meilleur = {"couple": (gauche, droite), "score": round(score, 2),
                            "titres": (recits[gauche].get("titre", ""),
                                       recits[droite].get("titre", ""))}
    return meilleur


def mesurer_la_variete(recits: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Ce qui distingue les recits les uns des autres, en chiffres.

    Rend une MESURE, pas un verdict. Un recueil de sept textes qui finissent
    tous bien peut etre un choix — un recueil de Noel, un recueil pour
    enfants. L'usine n'a pas de quoi trancher, et un « trop uniforme » affirme
    sur un seuil non mesure serait exactement le verdict fabrique que ce depot
    refuse.

    Elle repond a trois questions qu'on peut compter : combien de
    protagonistes differents, combien de formes de fin differentes, et de
    combien les longueurs s'ecartent.
    """
    protagonistes = [r.get("protagoniste", "") or r.get("qui", "")
                     for r in recits]
    fins = [(r.get("fin") or "").lower() for r in recits if r.get("fin")]
    mots = [int(r.get("mots") or 0) for r in recits]
    distincts = len({p.strip().lower() for p in protagonistes if p.strip()})
    ecart = 0
    if len(mots) > 1 and max(mots):
        ecart = round((max(mots) - min(mots)) / max(mots), 2)
    return {
        "recits": len(recits),
        "protagonistes_distincts": distincts,
        "fins_distinctes": len(set(fins)),
        "fins": sorted(set(fins)),
        "ecart_de_longueur": ecart,
    }


def lire_la_variete(mesure: Dict[str, Any]) -> List[str]:
    """Ce que la mesure permet de dire SANS inventer de seuil.

    Une seule chose est affirmee, parce qu'une seule est certaine : deux
    recits qui portent le meme protagoniste, ou sept qui finissent de la meme
    facon, sont un fait, pas une appreciation. Tout le reste est rendu en
    chiffres et laisse a l'auteur.
    """
    lectures = []
    total = mesure["recits"]
    if total > 1 and mesure["protagonistes_distincts"] < total:
        lectures.append(
            "{} recits pour {} protagoniste(s) distinct(s) : deux textes au "
            "moins portent le meme personnage.".format(
                total, mesure["protagonistes_distincts"]))
    if total > 2 and mesure["fins_distinctes"] == 1:
        lectures.append(
            "Les {} recits finissent tous de la meme facon ({}). C'est "
            "peut-etre voulu ; lu d'affilee, cela s'entend.".format(
                total, (mesure["fins"] or ["?"])[0]))
    return lectures


def _plan_garde(dossier: Any,
                rang: int) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """La bible et la grille d'un recit, si le carnet les a deja.

    Une reprise qui les reconstruirait donnerait un autre protagoniste aux
    scenes deja ecrites.
    """
    garde = ((carnet.plan(dossier) or {}).get("par_recit") or {}).get(str(rang))
    if isinstance(garde, dict) and garde.get("bible") and garde.get("grille"):
        return garde["bible"], garde["grille"]
    return None


def _nouveau_plan(local: Contexte, dossier: Any,
                  rang: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """La bible et la grille d'un recit, demandees puis gardees au carnet."""
    from .nouvelle import construire_bible, construire_grille

    bible = construire_bible(local)
    grille = construire_grille(local, bible)
    plan = carnet.plan(dossier) or {}
    plan.setdefault("par_recit", {})[str(rang)] = {"bible": bible, "grille": grille}
    carnet.noter_plan(dossier, plan)
    return bible, grille


def _ecrire_un_recit(ctx: Contexte, fiche: Dict[str, Any], scenes: int,
                     redaction: Redaction, rang: int) -> Optional[Dict[str, Any]]:
    """Un recit du recueil, ecrit avec les primitives de la fiction — ou None
    s'il n'a pas pu commencer.

    Bible, grille et scenes viennent de « nouvelle ». Ce n'est pas de la
    paresse : le depot a deja tranche que deux chaines de fiction
    divergeraient, et la continuite d'un recit court se tient exactement
    comme celle d'une nouvelle. Ce que le recueil ajoute est AUTOUR des
    recits, pas dedans.
    """
    from .nouvelle import (memoriser, protagoniste, repli_de_scene,
                           rediger_scene)

    # Un contexte propre au recit : c'est son sujet, pas celui du recueil,
    # qui doit nourrir la bible. Passer le sujet du recueil donnerait sept
    # bibles identiques — donc sept fois la meme histoire, ce que toute cette
    # chaine existe pour eviter.
    local = replace(ctx, sujet=fiche["premisse"] or fiche["titre"],
                    chapitres=scenes, journal=lambda _m: None)
    local.meta = ctx.meta
    repere = "recit-{}".format(rang)
    # Le carnet d'abord, le silence des fournisseurs ensuite. Dans l'autre
    # ordre, un recit ecrit en entier a une premiere fabrication etait
    # compte manquant des qu'un recit plus tot tombait sur un quota vide, et
    # sortait du fichier jusqu'a la reprise suivante.
    plan = _plan_garde(redaction.dossier, rang)
    if plan is None and redaction.budget_epuise:
        redaction.manque(repere, "plus rien a demander")
        return None
    try:
        bible, grille = plan or _nouveau_plan(local, redaction.dossier, rang)
    except PLUS_RIEN_A_DEMANDER as exc:
        redaction.budget_epuise, redaction.cause = True, exc
        ctx.journal("    {} : {}".format(repere, exc))
        redaction.manque(repere, str(exc))
        return None
    except Exception as exc:
        ctx.journal("    recit abandonne : {}".format(exc))
        redaction.manque(repere, str(exc))
        return None
    # Le « ok » efface, a la reprise, l'echec d'une premiere fabrication
    # coupee avant la bible de ce recit : le dernier statut gagne.
    ctx.etape(repere, "ok", fiche["titre"])
    prevues = grille["scenes"][:scenes]
    memoire = M.choisir(len(prevues), 90)
    morceaux: List[str] = []
    ecrites = 0
    for index, scene in enumerate(prevues):
        corps = redaction.ecrire(
            "{}-scene-{}".format(repere, index + 1), scene["titre"],
            lambda: rediger_scene(
                local, bible, grille, index, scene, memoire.pour_invite(),
                morceaux[-1][-320:] if morceaux else "")[0])
        if index < len(prevues) - 1:
            # Le resume roulant, comme dans « nouvelle » : c'est lui qui fait
            # qu'une scene sait ce que la precedente a change. La derniere
            # scene n'en a pas besoin — personne ne la lira apres.
            memoriser(memoire, redaction, local, scene, corps, index,
                      len(prevues))
        if corps is None:
            # Une scene perdue ne doit pas emporter le recueil : sa fiche
            # tient la place, et elle est notee en echec — le recueil reste
            # inacheve jusqu'a ce qu'une reprise l'ecrive.
            corps = repli_de_scene(scene)
        else:
            ecrites += 1
        morceaux.append(corps)
    texte = "\n\n".join(morceaux)
    return {
        **fiche,
        "protagoniste": protagoniste(bible) if bible.get("personnages") else "",
        "bible": bible,
        "texte": texte,
        "mots": len(texte.split()),
        "scenes_ecrites": ecrites,
        "scenes_prevues": len(prevues),
    }


def produire(ctx: Contexte, recits: int = 0) -> Dict[str, Any]:
    """Un recueil dont les textes ne sont pas le meme texte sept fois."""
    demande = int(recits or ctx.chapitres or RECITS)
    demande = max(RECITS_MIN, min(demande, RECITS_MAX))

    ctx.journal("Etape 1/4 — le fil du recueil et ses {} premisses..."
                .format(demande))
    # Une reprise repart du fil du carnet : un fil redemande changerait les
    # premisses sous les recits deja ecrits.
    repris = carnet.plan(ctx.dossier) if ctx.dossier and ctx.dossier.name else None
    fil = (repris or {}).get("fil") or _fil(ctx, demande)
    jumelles = premisses_jumelles(fil["recits"])
    if jumelles and not repris:
        # Une seule reprise, et elle NOMME les couples : redemander « varie
        # davantage » ne change rien, dire « les recits 2 et 5 racontent la
        # meme chose » change ce point-la.
        couples = ", ".join(
            "« {} » et « {} »".format(fil["recits"][g]["titre"],
                                      fil["recits"][d]["titre"])
            for g, d, _score in jumelles)
        ctx.journal("  {} couple(s) de premisses jumelles : {}".format(
            len(jumelles), couples))
        ancien = ctx.sujet
        try:
            ctx.sujet = ("{}\n\nATTENTION : ces couples racontaient la meme "
                         "histoire, refais-les entierement differents : {}"
                         .format(ancien, couples))
            fil = _fil(ctx, demande)
        finally:
            ctx.sujet = ancien
        jumelles = premisses_jumelles(fil["recits"])

    titre = fil["titre"]
    dossier = preparer(ctx, "recueil", titre)
    if repris:
        ctx.journal("  Reprise : fil et {} section(s) deja au carnet."
                    .format(carnet.compte(dossier)))
    else:
        carnet.noter_plan(dossier, {"fil": fil, "chapitres": fil["recits"]})
    proximite = proximite_maximale(fil["recits"])
    ctx.etape("fil", "partiel" if jumelles else "ok",
              "{} recits, proximite max {}".format(
                  len(fil["recits"]), proximite.get("score", 0)))

    ctx.journal("Etape 2/4 — redaction des {} recits...".format(
        len(fil["recits"])))
    ecrits: List[Dict[str, Any]] = []
    redaction = Redaction(ctx, dossier)
    for rang, fiche in enumerate(fil["recits"], 1):
        ctx.journal("  [{}/{}] « {} »".format(rang, len(fil["recits"]),
                                              fiche["titre"]))
        recit = _ecrire_un_recit(ctx, fiche, SCENES_PAR_RECIT, redaction, rang)
        if recit is not None:
            ecrits.append(recit)
    if not ecrits:
        # Rien d'ecrit parce que les fournisseurs se sont tus : c'est leur
        # silence qui remonte, pour que la boucle attende qu'ils rouvrent au
        # lieu de compter une panne. Le fil est au carnet, la reprise le
        # relira.
        if redaction.cause is not None:
            raise redaction.cause
        raise ValueError("Aucun recit n'a pu etre ecrit")
    ctx.etape("recits", "partiel" if redaction.manquants else "ok",
              "{} recit(s) sur {}".format(len(ecrits), len(fil["recits"])))

    ctx.journal("Etape 3/4 — mesure de la variete...")
    mesure = mesurer_la_variete(ecrits)
    mesure["proximite_maximale"] = proximite
    lectures = lire_la_variete(mesure)
    ctx.journal("  {} protagoniste(s) distinct(s), {} forme(s) de fin, "
                "proximite max {}".format(
                    mesure["protagonistes_distincts"],
                    mesure["fins_distinctes"], proximite.get("score", 0)))
    for lecture in lectures:
        ctx.journal("  [!] " + lecture)
    ctx.etape("variete", "ok",
              "{} protagonistes, {} fins".format(
                  mesure["protagonistes_distincts"], mesure["fins_distinctes"]))

    # La variete mesure la DISTANCE entre les recits ; la prose mesure la
    # phrase. Sept nouvelles peuvent etre parfaitement variees et toutes
    # ecrites de la meme main molle.
    style = prose.mesurer_la_prose([(r["titre"], r["texte"]) for r in ecrits])
    lectures_prose = prose.lire_la_prose(style)
    ctx.journal("  " + prose.situer_le_dialogue(style["part_de_dialogue"]))
    for lecture in lectures_prose:
        ctx.journal("  [prose] " + lecture)

    ctx.journal("Etape 4/4 — export...")
    t = libelles.textes(ctx.langue_iso)
    blocs = [livraison.Bloc(
        titre=t["recueil_fil"], corps=fil["fil"] or t["recueil_fil_defaut"])]
    blocs += [livraison.Bloc(titre=r["titre"], corps=r["texte"]) for r in ecrits]
    produit = livraison.Produit(
        type="recueil", titre=titre,
        sous_titre=t["recueil_sous_titre"].format(nombre=len(ecrits)),
        promesse=fil["fil"],
        blocs=blocs,
        donnees={"fil": fil["fil"], "recits": [
            {k: v for k, v in r.items() if k != "bible"} for r in ecrits],
            "variete": mesure, "prose": style},
        nom_donnees="recueil",
        formats=("md", "pdf", "html", "epub", "txt"),
        libelle_sections=t["unite_nouvelles"],
    )
    fichiers = livraison.livrer(ctx, produit)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "recits": len(ecrits),
        "mots": sum(r["mots"] for r in ecrits),
        "variete": mesure,
        "prose": style,
        # A part, et non fondues dans « lectures ». « lectures » porte les
        # VERDICTS de la chaine — un recueil dont deux nouvelles se
        # ressemblent trop. Les lignes de prose ne sont pas des verdicts :
        # elles comptent et elles nomment. Les melanger ferait passer un
        # produit sain pour un produit alerte.
        "lectures_prose": lectures_prose,
        "lectures": lectures,
        "premisses_jumelles": jumelles,
        "fichiers": [f.name for f in fichiers],
        "budget_epuise": redaction.budget_epuise,
    }
    terminer(ctx, fichiers, {"recits": len(ecrits)})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume
