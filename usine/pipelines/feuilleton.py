"""Feuilleton : des episodes qu'on attend, pas un roman decoupe.

Pourquoi une chaine a part. Couper un roman en morceaux ne fait pas un
feuilleton : cela fait un roman vendu en tranches. Ce qui distingue le
format, c'est que chaque episode doit tenir DEUX promesses que le roman n'a
pas a tenir :

  il se lit sans avoir relu le precedent — d'ou un « Precedemment » qui est
  du TEXTE POUR LE LECTEUR, pas la memoire interne de la chaine ;
  il donne envie du suivant — d'ou une fin suspendue, voulue, ecrite comme
  telle, et non le hasard de l'endroit ou l'on a coupe.

Les deux se verifient sans appeler un modele, et c'est ce que cette chaine
ajoute :

  un episode sans suspens declare      le lecteur n'a aucune raison de revenir ;
  un recap qui ne nomme personne       il ne rappelle rien, il meuble ;
  un recap plus long qu'un quart de
  l'episode                            ce n'est plus un rappel, c'est un
                                       resume qui prend la place du recit.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

from ..agents import equipe
from ..render import livraison
from . import fiction
from . import memoire as M
from . import prose
from .base import (Contexte, elaguer_markdown, nettoyer_titre,
                   preparer, sans_titres, terminer)

EPISODES = 8
EPISODES_MIN, EPISODES_MAX = 3, 30
SCENES_PAR_EPISODE = 3
# Au-dela de cette part de l'episode, le rappel n'en est plus un. Ce n'est pas
# un chiffre trouve dans une etude : c'est la definition d'un rappel, et le
# controle le dit tel quel plutot que de le maquiller en mesure.
PART_MAXIMALE_DU_RECAP = 0.25


def _arc(ctx: Contexte, nombre: int) -> Dict[str, Any]:
    """L'arc de la saison : ce que chaque episode promet et ou il coupe."""
    invite = (
        "Concois l'arc d'un FEUILLETON en {n} episodes sur : {sujet}\n"
        "LECTEUR : {audience}\n{promesse}\n"
        "Un feuilleton n'est pas un roman decoupe. Chaque episode a sa "
        "propre question, posee au debut et refermee a la fin — et il en "
        "ouvre une autre juste avant de s'arreter.\n\n"
        "Le dernier episode est le SEUL qui referme l'arc entier : lui seul "
        "n'a pas de suspens final.\n\n"
        "Schema JSON exact :\n"
        '{{"titre": "le titre de la saison", '
        '"promesse": "ce que la saison promet, une phrase", '
        '"episodes": [{{"titre": "...", "question": "la question de cet '
        'episode", "evenement": "ce qui s\'y passe vraiment", '
        '"suspens": "la question ouverte a la derniere ligne, vide pour le '
        'dernier episode"}}]}}'
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience,
             promesse=fiction.consignes(ctx))
    donnees = equipe.SCENARISTE.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.75, max_tokens=3000)
    if not isinstance(donnees, dict):
        raise ValueError("Arc de saison illisible")
    episodes = []
    for brut in donnees.get("episodes") or []:
        if not isinstance(brut, dict) or not str(brut.get("titre") or "").strip():
            continue
        episodes.append({
            "titre": nettoyer_titre(str(brut["titre"])),
            "question": str(brut.get("question") or "").strip(),
            "evenement": str(brut.get("evenement") or "").strip(),
            "suspens": str(brut.get("suspens") or "").strip(),
        })
    if not episodes:
        raise ValueError("Aucun episode exploitable dans l'arc")
    return {"titre": nettoyer_titre(str(donnees.get("titre") or ctx.sujet)),
            "promesse": str(donnees.get("promesse") or "").strip(),
            # Ce qui est demande fait foi : un modele qui rend douze episodes
            # pour huit ferait fabriquer douze fois le temps annonce.
            "episodes": episodes[:nombre]}


def episodes_sans_suspens(episodes: Sequence[Dict[str, Any]]) -> List[int]:
    """Les episodes qui s'arretent sans rien ouvrir, sauf le dernier.

    Le dernier est exclu par construction, pas par tolerance : il referme
    l'arc, et lui reclamer un suspens serait reclamer une saison de plus.
    """
    return [rang for rang, episode in enumerate(episodes[:-1], 1)
            if not (episode.get("suspens") or "").strip()]


def _phrases(texte: str) -> List[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texte or "")
            if p.strip()]


def mesurer_les_recaps(episodes: Sequence[Dict[str, Any]],
                       distribution: Sequence[str]) -> List[Dict[str, Any]]:
    """Ce que chaque « Precedemment » fait vraiment, en chiffres.

    Deux faits verifiables, et rien d'autre : nomme-t-il quelqu'un de la
    distribution, et quelle part de l'episode occupe-t-il. Ni l'un ni l'autre
    ne juge la qualite du rappel — « ce recap est mauvais » n'est pas
    mesurable, « ce recap ne nomme personne » l'est.

    Le premier episode n'a rien a rappeler : il est exclu, sinon le controle
    signalerait a tort a chaque saison.
    """
    noms = [n for n in distribution if n]
    mesures = []
    for rang, episode in enumerate(episodes, 1):
        if rang == 1:
            continue
        recap = (episode.get("recap") or "").strip()
        corps = (episode.get("texte") or "").strip()
        mots_recap = len(recap.split())
        mots_corps = len(corps.split()) or 1
        mesures.append({
            "episode": rang,
            "mots": mots_recap,
            "part": round(mots_recap / mots_corps, 2),
            "nomme": sorted({n for n in noms if n.lower() in recap.lower()}),
        })
    return mesures


def lire_les_recaps(mesures: Sequence[Dict[str, Any]]) -> List[str]:
    """Ce que les mesures permettent de dire, et rien de plus."""
    lectures = []
    muets = [m["episode"] for m in mesures if not m["nomme"] and m["mots"]]
    if muets:
        lectures.append(
            "Le rappel des episodes {} ne nomme personne de la "
            "distribution : il ne rappelle rien, il meuble.".format(
                ", ".join(str(e) for e in muets)))
    absents = [m["episode"] for m in mesures if not m["mots"]]
    if absents:
        lectures.append(
            "Les episodes {} n'ont pas de « Precedemment » : ils se lisent "
            "mal seuls, et c'est la promesse du format.".format(
                ", ".join(str(e) for e in absents)))
    longs = [m["episode"] for m in mesures
             if m["part"] > PART_MAXIMALE_DU_RECAP]
    if longs:
        lectures.append(
            "Le rappel des episodes {} depasse le quart de l'episode : ce "
            "n'est plus un rappel, c'est un resume qui prend la place du "
            "recit.".format(", ".join(str(e) for e in longs)))
    return lectures


def _ecrire_recap(ctx: Contexte, precedent: Dict[str, Any],
                  distribution: Sequence[str]) -> str:
    """Le « Precedemment », ecrit POUR LE LECTEUR.

    Ce n'est pas le resume roulant de la chaine : celui-la sert au modele a
    ne pas se contredire, il est ecrit en notes et personne ne doit le lire.
    Confondre les deux livrait au lecteur une fiche technique — « Camille :
    veut sauver la ligne ; obstacle : Hakim » — au lieu d'un rappel.
    """
    invite = (
        "Ecris le « Precedemment » d'un episode de feuilleton.\n\n"
        "CE QUI S'EST PASSE DANS L'EPISODE PRECEDENT :\n{texte}\n\n"
        "DISTRIBUTION : {noms}\n\n"
        "Consignes :\n"
        "- Quarante a quatre-vingts mots. C'est un rappel, pas un resume.\n"
        "- Nomme les personnages : c'est ce que le lecteur a oublie.\n"
        "- Termine sur la question restee ouverte : {suspens}\n"
        "- Ecris-le comme une voix qui parle au lecteur, pas comme une "
        "fiche.\n"
        "- Reponds uniquement par le texte du rappel."
    ).format(texte=(precedent.get("texte") or "")[-1800:],
             noms=", ".join(distribution) or "libre",
             suspens=precedent.get("suspens") or "libre")
    reponse = equipe.ROMANCIER.travailler(ctx, invite, max_tokens=400)
    # Un titre dans le rappel fabrique une section fantome au sommaire, au
    # milieu des episodes numerotes. Mesure du 15/09/2026 : le rappel de
    # l'episode 2 portait « ## Le principe de base ».
    return sans_titres(elaguer_markdown(reponse.texte))


def produire(ctx: Contexte, episodes: int = 0) -> Dict[str, Any]:
    """Un feuilleton : chaque episode se lit seul et appelle le suivant."""
    from .nouvelle import (construire_bible, construire_grille, redacteur_pour,
                           rediger_scene)

    demande = int(episodes or ctx.chapitres or EPISODES)
    demande = max(EPISODES_MIN, min(demande, EPISODES_MAX))
    mots = ctx.mots_section or 700

    ctx.journal("Etape 1/4 — la bible : distribution, cadre, enjeu...")
    bible = construire_bible(ctx)
    distribution = [p.get("nom", "") for p in bible.get("personnages", [])]
    ctx.etape("bible", "ok", "{} personnage(s)".format(len(distribution)))

    ctx.journal("Etape 2/4 — l'arc de la saison, {} episodes...".format(demande))
    arc = _arc(ctx, demande)
    titre = arc["titre"]
    dossier = preparer(ctx, "feuilleton", titre)
    sans_suspens = episodes_sans_suspens(arc["episodes"])
    if sans_suspens:
        ctx.journal("  [!] episodes sans suspens declare : {} — le lecteur "
                    "n'a aucune raison de revenir.".format(
                        ", ".join(str(e) for e in sans_suspens)))
    ctx.etape("arc", "partiel" if sans_suspens else "ok",
              "{} episodes".format(len(arc["episodes"])))

    ctx.journal("Etape 3/4 — redaction des episodes...")
    grille = construire_grille(ctx, bible)
    prevues = grille["scenes"]
    memoire = M.choisir(len(arc["episodes"]) * SCENES_PAR_EPISODE, 90)
    ecrits: List[Dict[str, Any]] = []
    for rang, episode in enumerate(arc["episodes"], 1):
        ctx.journal("  [{}/{}] « {} »".format(rang, len(arc["episodes"]),
                                              episode["titre"]))
        recap = ""
        if ecrits:
            try:
                recap = _ecrire_recap(ctx, ecrits[-1], distribution)
            except Exception as exc:
                ctx.journal("    rappel indisponible : {}".format(exc))
        morceaux: List[str] = []
        for pas in range(SCENES_PAR_EPISODE):
            index = ((rang - 1) * SCENES_PAR_EPISODE + pas) % len(prevues)
            scene = dict(prevues[index])
            # L'episode impose sa question et son suspens a ses scenes : sans
            # cela, on redigerait les scenes d'un roman et l'on appellerait
            # « episode » un paquet de trois.
            scene["objectif"] = episode["question"] or scene.get("objectif", "")
            if pas == SCENES_PAR_EPISODE - 1 and episode["suspens"]:
                scene["pivot"] = episode["suspens"]
            try:
                corps, _auteur = rediger_scene(
                    ctx, bible, grille, index, scene, memoire.pour_invite(),
                    morceaux[-1][-320:] if morceaux else "")
            except Exception as exc:
                ctx.journal("    scene indisponible : {}".format(exc))
                continue
            morceaux.append(corps)
            try:
                memoire.apres_scene(redacteur_pour(ctx, scene), corps,
                                    scene["titre"], index, len(prevues))
            except Exception:
                pass
        ecrits.append({**episode, "rang": rang, "recap": recap,
                       "texte": "\n\n".join(morceaux),
                       "mots": len(" ".join(morceaux).split())})
    ctx.etape("episodes", "ok", "{} episode(s)".format(len(ecrits)))

    ctx.journal("Etape 4/4 — mesure des rappels, puis export...")
    mesures = mesurer_les_recaps(ecrits, distribution)
    lectures = lire_les_recaps(mesures)
    for lecture in lectures:
        ctx.journal("  [!] " + lecture)

    # Le recap mesure ce qui se repete d'un episode a l'autre ; la prose
    # mesure la phrase. Un feuilleton dont chaque episode rappelle
    # correctement le precedent peut rester ecrit de la meme main molle.
    style = prose.mesurer_la_prose(
        [(e["titre"], e["texte"]) for e in ecrits])
    lectures_prose = prose.lire_la_prose(style)
    ctx.journal("  " + prose.situer_le_dialogue(style["part_de_dialogue"]))
    for lecture in lectures_prose:
        ctx.journal("  [prose] " + lecture)

    blocs = [livraison.Bloc(
        titre="La saison", corps=arc["promesse"] or "Une saison en {} "
        "episodes.".format(len(ecrits)))]
    for episode in ecrits:
        corps = []
        if episode["recap"]:
            corps.append("**Precedemment.** " + episode["recap"])
        corps.append(episode["texte"])
        if episode["suspens"]:
            corps.append("*A suivre.*")
        blocs.append(livraison.Bloc(
            titre="Episode {} — {}".format(episode["rang"], episode["titre"]),
            corps="\n\n".join(corps)))
    produit = livraison.Produit(
        type="feuilleton", titre=titre,
        sous_titre="{} episodes".format(len(ecrits)),
        promesse=arc["promesse"],
        blocs=blocs,
        donnees={"bible": bible, "arc": arc, "episodes": ecrits,
                 "recaps": mesures, "prose": style},
        nom_donnees="saison",
        formats=("md", "pdf", "html", "epub", "txt"),
        libelle_sections="episode(s)",
    )
    fichiers = livraison.livrer(ctx, produit)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "episodes": len(ecrits),
        "mots": sum(e["mots"] for e in ecrits),
        "episodes_sans_suspens": sans_suspens,
        "recaps": mesures,
        "prose": style,
        # A part, et non fondues dans « lectures » : celles-ci portent les
        # verdicts de la chaine, les lignes de prose ne sont que des comptes.
        "lectures_prose": lectures_prose,
        "lectures": lectures,
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"episodes": len(ecrits)})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume
