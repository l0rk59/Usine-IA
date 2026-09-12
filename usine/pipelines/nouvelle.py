"""Chaine de production d'une nouvelle : la fiction, qui demande une memoire.

Pourquoi une chaine a part, et pas une option de l'ebook. La chaine « ebook »
redige chaque chapitre INDEPENDAMMENT : il ne recoit que la liste des titres
des autres, pour eviter les redites. Pour un guide pratique, c'est une
qualite — les chapitres sont modulaires, fabricables dans n'importe quel
ordre, et un chapitre rate n'entraine pas les autres.

Pour une histoire, c'est redhibitoire. Une fiction a besoin de savoir qui est
present, ce que le lecteur sait deja, ou en est l'arc, et ce qui a ete promis
a la scene 3 et doit etre paye a la scene 11. Trois pieces que l'ebook n'a
pas, et qui sont tout ce que cette chaine ajoute :

  1. UNE BIBLE, ecrite avant la premiere scene : personnages (nom, desir,
     defaut, voix), lieu, epoque, regles du monde, enjeu. Elle est passee a
     chaque scene et ne change plus. C'est la source de verite.
  2. UN RESUME ROULANT : chaque scene recoit ce qui s'est passe jusque-la, en
     quelques lignes, et le met a jour en sortant. C'est la memoire que la
     chaine ebook n'a pas, et elle coute un appel court par scene — le prix
     de la continuite.
  3. UNE GRILLE DE BEATS plutot qu'un plan de chapitres. Un « beat » est un
     tournant de l'histoire ; une scene est une unite de manuscrit. On
     planifie en beats, puis on ecrit les scenes qui les livrent.

S'y ajoute un controle de continuite DETERMINISTE, gratuit et instantane, qui
relit la bible contre le texte produit : un personnage annonce et jamais
apparu, une scene ou personne de la distribution n'est present, un resume qui
n'avance plus. Ce sont les defauts propres a la fiction generee, et aucun
d'eux ne demande un appel de modele pour etre vu.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..agents import equipe
from ..core import budget
from ..core import controle as ctrl
from ..core import evenements, llm, securite
from ..render import document as D
from ..render import livraison
from .base import Contexte, elaguer_markdown, nettoyer_titre, preparer, terminer

ROLE = ("un auteur de fiction courte publie en revue, qui tient la continuite "
        "et montre plutot que de raconter")

# Longueur du resume roulant. Assez pour porter l'etat de l'histoire, assez
# court pour tenir dans chaque invite sans manger le budget de la scene.
MOTS_RESUME = 90

# Armature d'une nouvelle. Ce ne sont pas des chapitres : plusieurs scenes
# peuvent livrer un meme beat, et une scene peut en livrer deux.
BEATS = (
    ("situation", "l'ordinaire du personnage, et ce qui lui manque"),
    ("declencheur", "l'evenement qui rend le retour en arriere impossible"),
    ("engagement", "le personnage choisit d'agir, et paie ce choix"),
    ("complication", "ce qui marchait ne marche plus ; l'enjeu monte"),
    ("crise", "le pire moment : le personnage perd ce a quoi il tenait"),
    ("climax", "la confrontation, et la decision qui la tranche"),
    ("resolution", "le nouvel ordinaire, different du premier"),
)

# Les trois beats dont une histoire ne peut pas se passer. Les autres
# peuvent fusionner ou sauter — une nouvelle de six scenes ne peut pas
# livrer sept tournants separement, et le lui reprocher serait faux.
# Mais un recit sans declencheur, sans climax ou sans fin n'est pas un recit.
BEATS_ESSENTIELS = ("declencheur", "climax", "resolution")


# Reperes de longueur du marche. Les paliers de taille de l'usine (mini,
# court, standard, long) sont penses pour des guides : ils ne disent rien a
# qui ecrit de la fiction. Plutot que d'imposer une longueur, la chaine
# annonce a quel format correspond ce qu'on lui demande.
FORMATS_FICTION = (
    (1000, "texte tres court"),
    (10000, "nouvelle"),
    (17000, "novelette"),
    (40000, "novella"),
)


def format_fiction(mots: int) -> str:
    """Nom du format correspondant a un nombre de mots."""
    for plafond, nom in FORMATS_FICTION:
        if mots < plafond:
            return nom
    return "roman"


# --------------------------------------------------------------------------
# 1. La bible
# --------------------------------------------------------------------------


def construire_bible(ctx: Contexte) -> Dict[str, Any]:
    """Tout ce qui ne changera plus : distribution, cadre, enjeu.

    Elle est ecrite en un seul appel, AVANT la premiere ligne de texte, parce
    qu'un personnage dont le desir se decide au fil de l'eau n'a pas de desir.
    """
    invite = (
        "Concois la bible d'une nouvelle (fiction courte) a partir de cette "
        "idee :\n"
        "IDEE : {sujet}\n"
        "LECTEUR : {audience}\n\n"
        "Contraintes :\n"
        "- Le titre est evocateur, pas explicatif.\n"
        "- 2 a 4 personnages, pas plus : une nouvelle n'a pas la place d'une "
        "distribution de roman.\n"
        "- Chaque personnage a un DESIR (ce qu'il veut, concretement) et un "
        "DEFAUT qui l'empeche de l'obtenir. Les deux doivent s'opposer.\n"
        "- La « voix » decrit comment il parle en une formule : registre, "
        "tic de langage, ce qu'il ne dit jamais.\n"
        "- L'enjeu dit ce que le protagoniste PERD s'il echoue. Pas une "
        "abstraction : une chose precise.\n\n"
        "Schema JSON exact attendu :\n"
        '{{"titre": "...", "genre": "...", "premisse": "une phrase", '
        '"cadre": {{"lieu": "...", "epoque": "...", '
        '"regles": ["ce qui est vrai dans ce monde et ne changera pas"]}}, '
        '"personnages": [{{"nom": "...", "role": "protagoniste", '
        '"desir": "...", "defaut": "...", "voix": "..."}}], '
        '"enjeu": "...", "fin_visee": "..."}}'
    ).format(sujet=ctx.sujet, audience=ctx.audience)

    bible = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=2200)
    if not isinstance(bible, dict) or not bible.get("personnages"):
        raise ValueError("Bible invalide renvoyee par le modele")

    bible["titre"] = nettoyer_titre(str(bible.get("titre") or ctx.sujet))
    bible["genre"] = str(bible.get("genre") or "").strip()
    bible["premisse"] = str(bible.get("premisse") or "").strip()
    bible["enjeu"] = str(bible.get("enjeu") or "").strip()
    bible["fin_visee"] = str(bible.get("fin_visee") or "").strip()

    cadre = bible.get("cadre")
    if not isinstance(cadre, dict):
        cadre = {}
    regles = cadre.get("regles") or []
    if isinstance(regles, str):
        regles = [regles]
    bible["cadre"] = {
        "lieu": str(cadre.get("lieu") or "").strip(),
        "epoque": str(cadre.get("epoque") or "").strip(),
        "regles": [str(r).strip() for r in regles if str(r).strip()][:6],
    }

    personnages: List[Dict[str, str]] = []
    for brut in bible["personnages"]:
        if isinstance(brut, str):
            brut = {"nom": brut}
        nom = nettoyer_titre(str(brut.get("nom") or "")).strip()
        if not nom:
            continue
        personnages.append({
            "nom": nom,
            "role": str(brut.get("role") or "secondaire").strip().lower(),
            "desir": str(brut.get("desir") or "").strip(),
            "defaut": str(brut.get("defaut") or "").strip(),
            "voix": str(brut.get("voix") or "").strip(),
        })
    if not personnages:
        raise ValueError("Bible sans personnage exploitable")
    # Une nouvelle tient sur peu de monde : au-dela, la continuite se perd et
    # le lecteur aussi.
    bible["personnages"] = personnages[:5]
    return bible


def protagoniste(bible: Dict[str, Any]) -> str:
    for personnage in bible["personnages"]:
        if personnage["role"].startswith("protagon"):
            return personnage["nom"]
    return bible["personnages"][0]["nom"]


def resumer_bible(bible: Dict[str, Any]) -> str:
    """La bible en quelques lignes, telle qu'elle entre dans chaque invite."""
    cadre = bible["cadre"]
    lignes = [
        "TITRE : {}".format(bible["titre"]),
        "GENRE : {}".format(bible.get("genre") or "non precise"),
        "PREMISSE : {}".format(bible.get("premisse") or ""),
        "CADRE : {} — {}".format(cadre.get("lieu") or "non precise",
                                 cadre.get("epoque") or "non precisee"),
    ]
    if cadre.get("regles"):
        lignes.append("REGLES DU MONDE : " + " ; ".join(cadre["regles"]))
    lignes.append("ENJEU : {}".format(bible.get("enjeu") or ""))
    lignes.append("DISTRIBUTION :")
    for personnage in bible["personnages"]:
        lignes.append(
            "  - {nom} ({role}) — veut : {desir} ; defaut : {defaut} ; "
            "voix : {voix}".format(**personnage))
    return "\n".join(lignes)


# --------------------------------------------------------------------------
# 2. La grille de beats
# --------------------------------------------------------------------------


def construire_grille(ctx: Contexte, bible: Dict[str, Any]) -> Dict[str, Any]:
    """Les tournants d'abord, les scenes qui les livrent ensuite."""
    armature = "\n".join("- {} : {}".format(nom, role) for nom, role in BEATS)
    invite = (
        "Construis la grille d'une nouvelle a partir de cette bible.\n\n"
        "{bible}\n\n"
        "FIN VISEE : {fin}\n\n"
        "Travaille en deux temps.\n"
        "1. Les BEATS : les tournants de l'histoire, dans cet ordre :\n"
        "{armature}\n"
        "   Pour chacun, dis l'EVENEMENT precis qui le realise dans CETTE "
        "histoire — pas sa definition generale.\n"
        "2. Les SCENES : {n} scenes qui livrent ces beats, dans l'ordre de "
        "lecture. Plusieurs scenes peuvent servir le meme beat.\n"
        "   Chaque scene a un lieu, les personnages presents, ce que le "
        "personnage de point de vue VEUT dans cette scene, l'OBSTACLE qui s'y "
        "oppose, et le PIVOT : ce qui a change a la fin de la scene et qui "
        "n'etait pas vrai au debut. Une scene sans pivot est une scene morte.\n"
        "   Le titre d'une scene est evocateur et court, jamais « Scene 1 ».\n\n"
        "Schema JSON exact attendu :\n"
        '{{"beats": [{{"nom": "situation", "evenement": "..."}}], '
        '"scenes": [{{"titre": "...", "beat": "situation", "lieu": "...", '
        '"personnages": ["..."], "point_de_vue": "...", "objectif": "...", '
        '"obstacle": "...", "pivot": "..."}}]}}'
    ).format(bible=resumer_bible(bible), fin=bible.get("fin_visee") or "libre",
             armature=armature, n=ctx.nb_chapitres)

    grille = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=3200)
    if not isinstance(grille, dict) or not grille.get("scenes"):
        raise ValueError("Grille de scenes invalide renvoyee par le modele")

    noms = [p["nom"] for p in bible["personnages"]]
    beats_connus = {nom for nom, _ in BEATS}
    scenes: List[Dict[str, Any]] = []
    for brut in grille["scenes"]:
        if isinstance(brut, str):
            brut = {"titre": brut}
        presents = brut.get("personnages") or []
        if isinstance(presents, str):
            presents = [presents]
        # Un personnage invente ici contournerait la bible, qui est la source
        # de verite : on ne garde que la distribution declaree.
        presents = [str(p).strip() for p in presents
                    if _reconnu(str(p), noms)]
        beat = str(brut.get("beat") or "").strip().lower()
        scenes.append({
            "titre": nettoyer_titre(str(brut.get("titre") or "Scene")),
            "beat": beat if beat in beats_connus else "",
            "lieu": str(brut.get("lieu") or "").strip(),
            "personnages": presents or [protagoniste(bible)],
            "point_de_vue": (str(brut.get("point_de_vue") or "").strip()
                             or (presents[0] if presents else protagoniste(bible))),
            "objectif": str(brut.get("objectif") or "").strip(),
            "obstacle": str(brut.get("obstacle") or "").strip(),
            "pivot": str(brut.get("pivot") or "").strip(),
        })
    grille["scenes"] = scenes[: ctx.nb_chapitres]

    beats = []
    for brut in grille.get("beats") or []:
        if not isinstance(brut, dict):
            continue
        beats.append({"nom": str(brut.get("nom") or "").strip().lower(),
                      "evenement": str(brut.get("evenement") or "").strip()})
    grille["beats"] = beats
    return grille


def _normaliser(texte: str) -> str:
    sans_accent = unicodedata.normalize("NFKD", texte)
    return sans_accent.encode("ascii", "ignore").decode("ascii").lower()


def _reconnu(nom: str, connus: List[str]) -> bool:
    """Un nom de la bible, meme cite par un seul de ses mots.

    La comparaison se fait mot a mot, jamais par sous-chaine : « Alex » ne
    doit pas reconnaitre « Alexandra », qui serait un autre personnage.
    """
    mots_cible = set(_normaliser(nom).split())
    if not mots_cible:
        return False
    for connu in connus:
        mots_connus = set(_normaliser(connu).split())
        if mots_cible & mots_connus:
            return True
    return False


# --------------------------------------------------------------------------
# 3. La memoire : resume roulant
# --------------------------------------------------------------------------


def mettre_a_jour_resume(ctx: Contexte, memoire: str, scene: Dict[str, Any],
                         texte: str) -> str:
    """Reecrit l'etat de l'histoire apres une scene. C'est LA memoire.

    Un appel court par scene. C'est le surcout de cette chaine par rapport a
    l'ebook, et c'est ce qu'on achete : sans lui, la scene 9 ne sait pas que
    le personnage a quitte la ville a la scene 4.
    """
    invite = (
        "Voici l'etat d'une nouvelle en cours, puis la scene qui vient d'etre "
        "ecrite.\n\n"
        "ETAT JUSQU'ICI :\n{memoire}\n\n"
        "SCENE « {titre} » :\n{texte}\n\n"
        "Reecris l'ETAT COMPLET a jour, en {mots} mots maximum, au present, "
        "purement factuel : qui est ou, ce qui a change, ce qui reste en "
        "suspens et qui devra etre paye plus tard. Pas de jugement, pas de "
        "style, pas de titre. Uniquement le texte de l'etat."
    ).format(memoire=memoire or "(rien encore : l'histoire commence)",
             titre=scene["titre"], texte=texte[:6000], mots=MOTS_RESUME)

    reponse = equipe.REDACTEUR.travailler(ctx, invite, max_tokens=320)
    propre = elaguer_markdown(reponse.texte).strip()
    # Un resume vide ou aberrant ferait perdre la memoire pour toutes les
    # scenes suivantes : mieux vaut garder le precedent, augmente du pivot.
    if len(propre) < 40:
        return _memoire_de_secours(memoire, scene)
    return propre


def _memoire_de_secours(memoire: str, scene: Dict[str, Any]) -> str:
    """Memoire deterministe, quand le modele ne repond pas ou que le budget tombe.

    Elle vaut moins qu'un vrai resume, mais elle porte l'essentiel : le pivot
    annonce par la grille. Perdre la memoire entierement ferait repartir les
    scenes suivantes de zero, ce qui est exactement le defaut que cette chaine
    existe pour corriger.
    """
    pivot = scene.get("pivot") or scene.get("objectif") or ""
    ajout = "Apres « {} » : {}".format(scene["titre"], pivot).strip(" :")
    if not memoire:
        return ajout
    return "{}\n{}".format(memoire, ajout)


# --------------------------------------------------------------------------
# 4. Les scenes
# --------------------------------------------------------------------------


def rediger_scene(ctx: Contexte, bible: Dict[str, Any], grille: Dict[str, Any],
                  index: int, scene: Dict[str, Any], memoire: str,
                  fin_precedente: str = "") -> Tuple[str, str]:
    """Redige une scene. Renvoie (markdown, fournisseur utilise)."""
    total = len(grille["scenes"])
    beat = next((b for b in grille.get("beats", [])
                 if b["nom"] == scene["beat"]), None)
    reste = [s["titre"] for s in grille["scenes"][index + 1:]][:3]

    invite = (
        "Ecris la scene {num} sur {total} d'une nouvelle.\n\n"
        "--- BIBLE (source de verite, ne la contredis jamais) ---\n{bible}\n\n"
        "--- CE QUI S'EST PASSE JUSQU'ICI ---\n{memoire}\n\n"
        "--- LA SCENE A ECRIRE ---\n"
        "TITRE : {titre}\n"
        "BEAT : {beat}\n"
        "LIEU : {lieu}\n"
        "PRESENTS : {presents}\n"
        "POINT DE VUE : {pdv}\n"
        "CE QUE {pdv} VEUT ICI : {objectif}\n"
        "OBSTACLE : {obstacle}\n"
        "PIVOT (vrai a la fin, faux au debut) : {pivot}\n"
        "{fin_precedente}"
        "SCENES SUIVANTES (ne les ecris pas, laisse-leur la place) : {reste}\n\n"
        "Consignes :\n"
        "- Environ {mots} mots.\n"
        "- Prose narrative. Dialogues bienvenus. Chaque personnage parle avec "
        "la voix que lui donne la bible.\n"
        "- MONTRE : un geste, un objet, une replique valent mieux qu'une "
        "phrase qui explique ce que le personnage ressent.\n"
        "- Entre dans la scene le plus tard possible et sors-en le plus tot "
        "possible.\n"
        "- Le pivot doit avoir eu lieu quand la scene se termine.\n"
        "- N'ecris AUCUN titre, ni de niveau 1 ni de niveau 2 : le titre de "
        "la scene est ajoute automatiquement.\n"
        "- Pas de liste, pas de sous-titre, pas de « A retenir » : c'est une "
        "histoire, pas un guide.\n"
        "- Ne resume pas ce qui precede : le lecteur l'a lu.\n"
        "- Reponds uniquement par le texte de la scene."
    ).format(
        num=index + 1, total=total, bible=resumer_bible(bible),
        memoire=memoire or "(rien : c'est la premiere scene)",
        titre=scene["titre"],
        beat="{} — {}".format(scene["beat"] or "libre",
                              beat["evenement"] if beat else ""),
        lieu=scene["lieu"] or "libre",
        presents=", ".join(scene["personnages"]),
        pdv=scene["point_de_vue"],
        objectif=scene["objectif"] or "libre",
        obstacle=scene["obstacle"] or "libre",
        pivot=scene["pivot"] or "libre",
        fin_precedente=("FIN DE LA SCENE PRECEDENTE (enchaine dessus, ne la "
                        "repete pas) : « ...{} »\n".format(fin_precedente)
                        if fin_precedente else ""),
        reste=" | ".join(reste) or "aucune",
        mots=ctx.mots_par_chapitre,
    )

    reponse = equipe.REDACTEUR.travailler(
        ctx, invite, max_tokens=min(4096, int(ctx.mots_par_chapitre * 2.6)))
    texte = elaguer_markdown(reponse.texte)
    lignes = [l for l in texte.split("\n")]
    while lignes and lignes[0].startswith("#"):
        lignes.pop(0)
    return "\n".join(lignes).strip(), reponse.fournisseur


# --------------------------------------------------------------------------
# 5. Controle de continuite — deterministe, gratuit, instantane
# --------------------------------------------------------------------------


def _apparait(nom: str, texte: str) -> bool:
    """Le personnage est-il nomme dans ce texte ?

    On cherche chaque mot du nom separement : la bible dit « Madame Rivet »,
    le texte ecrit « Rivet ». Exiger le nom complet ferait declarer absent un
    personnage present a chaque page.

    Le prix de ce choix est assume : deux personnages qui partagent un nom de
    famille se reconnaissent l'un l'autre, et une mere citee seule marque sa
    fille comme presente. Le controle rate alors une absence au lieu d'en
    inventer une — c'est le bon sens de l'erreur pour un garde-fou qui doit
    etre cru quand il parle.
    """
    normalise = _normaliser(texte)
    morceaux = [m for m in _normaliser(nom).split() if len(m) >= 3]
    if not morceaux:
        return False
    return any(re.search(r"\b{}\b".format(re.escape(m)), normalise)
               for m in morceaux)


def _proximite(a: str, b: str) -> float:
    """Recouvrement de vocabulaire entre deux resumes successifs."""
    mots_a = {m for m in ctrl.mots(a) if len(m) >= 5}
    mots_b = {m for m in ctrl.mots(b) if len(m) >= 5}
    if not mots_a or not mots_b:
        return 0.0
    return len(mots_a & mots_b) / len(mots_a | mots_b)


def controler_continuite(bible: Dict[str, Any], grille: Dict[str, Any],
                         scenes: List[Tuple[str, str]],
                         memoires: List[str]) -> Dict[str, Any]:
    """Relit la bible contre le texte reellement ecrit.

    Ce sont les defauts propres a la fiction generee, et aucun ne demande un
    appel de modele pour etre vu : un personnage annonce puis oublie, une
    scene ou la distribution n'est pas la, un resume qui n'avance plus, un
    beat que la grille promet et qu'aucune scene ne livre.
    """
    anomalies: List[Dict[str, str]] = []
    texte_entier = "\n".join(corps for _, corps in scenes)
    heros = protagoniste(bible)

    # -- 1. un personnage declare mais jamais apparu ------------------------
    for personnage in bible["personnages"]:
        if not _apparait(personnage["nom"], texte_entier):
            anomalies.append({
                "genre": "personnage_absent",
                "gravite": "majeur" if personnage["role"].startswith("protagon")
                           else "mineur",
                "detail": "« {} » ({}) est dans la bible mais n'apparait dans "
                          "aucune scene".format(personnage["nom"],
                                                personnage["role"]),
            })

    # -- 2. le protagoniste doit porter l'histoire --------------------------
    if scenes:
        presences = sum(1 for _, corps in scenes if _apparait(heros, corps))
        part = presences / len(scenes)
        if part < 0.6:
            anomalies.append({
                "genre": "protagoniste_efface",
                "gravite": "majeur",
                "detail": "« {} » n'est present que dans {} scene(s) sur "
                          "{}".format(heros, presences, len(scenes)),
            })

    # -- 3. une scene sans personne de la distribution ----------------------
    noms = [p["nom"] for p in bible["personnages"]]
    for titre, corps in scenes:
        if not any(_apparait(nom, corps) for nom in noms):
            anomalies.append({
                "genre": "scene_hors_distribution",
                "gravite": "majeur",
                "detail": "aucun personnage de la bible n'est nomme dans "
                          "« {} »".format(titre),
            })

    # -- 4. un resume qui n'avance plus -------------------------------------
    for index in range(1, len(memoires)):
        if _proximite(memoires[index - 1], memoires[index]) > 0.92:
            titre = scenes[index][0] if index < len(scenes) else "?"
            anomalies.append({
                "genre": "scene_sans_pivot",
                "gravite": "mineur",
                "detail": "l'etat de l'histoire n'a pas bouge apres "
                          "« {} »".format(titre),
            })

    # -- 5. un tournant indispensable que rien ne livre ---------------------
    livres = {s["beat"] for s in grille.get("scenes", []) if s.get("beat")}
    for nom in BEATS_ESSENTIELS:
        if nom not in livres:
            anomalies.append({
                "genre": "beat_non_livre",
                "gravite": "majeur",
                "detail": "aucune scene ne livre le beat « {} »".format(nom),
            })

    graves = [a for a in anomalies if a["gravite"] == "majeur"]
    return {
        "anomalies": anomalies,
        "majeures": len(graves),
        "scenes": len(scenes),
        "personnages": len(bible["personnages"]),
        "resume": ("continuite tenue" if not anomalies else
                   "{} anomalie(s) de continuite, dont {} majeure(s)".format(
                       len(anomalies), len(graves))),
    }


# --------------------------------------------------------------------------
# 6. La chaine
# --------------------------------------------------------------------------


def produire(ctx: Contexte) -> Dict[str, Any]:
    """Produit la nouvelle complete et renvoie un resume des fichiers generes."""
    vise = ctx.nb_chapitres * ctx.mots_par_chapitre
    ctx.journal("Format vise : {} — {} scenes, environ {} mots.".format(
        format_fiction(vise), ctx.nb_chapitres, vise))
    ctx.journal("Etape 1/5 — la bible : distribution, cadre, enjeu...")
    bible = construire_bible(ctx)
    titre = bible["titre"]
    dossier = preparer(ctx, "nouvelle", titre)
    ctx.etape("bible", "ok", "{} personnage(s)".format(len(bible["personnages"])))
    ctx.journal('  Titre retenu : « {} »'.format(titre))
    ctx.journal("  Distribution : {}".format(
        ", ".join(p["nom"] for p in bible["personnages"])))

    ctx.journal("Etape 2/5 — la grille de beats...")
    grille = construire_grille(ctx, bible)
    scenes_prevues = grille["scenes"]
    total = len(scenes_prevues)
    ctx.etape("grille", "ok", "{} scene(s)".format(total))
    (dossier / "bible.json").write_text(
        json.dumps({"bible": bible, "grille": grille}, ensure_ascii=False,
                   indent=2), encoding="utf-8")

    alertes = securite.analyser_sujet(ctx.sujet)
    for domaine, avertissement in alertes:
        ctx.journal("  [!] domaine sensible « {} » : {}".format(domaine, avertissement))
        evenements.publier("alerte", domaine=domaine, detail=avertissement)

    ctx.journal("Etape 3/5 — redaction des {} scenes...".format(total))
    passes = ctx.nb_passes
    sections: List[Tuple[str, str]] = []
    memoires: List[str] = []
    local: Dict[str, List[ctrl.Controle]] = {}
    memoire = ""
    budget_epuise = False

    for index, scene in enumerate(scenes_prevues):
        ctx.journal("  [{}/{}] {}".format(index + 1, total, scene["titre"]))
        evenements.publier("section", etape="redaction", index=index + 1,
                           total=total, titre=scene["titre"])
        if budget_epuise:
            sections.append((scene["titre"], _repli(scene)))
            memoire = _memoire_de_secours(memoire, scene)
            memoires.append(memoire)
            ctx.etape("scene-{}".format(index + 1), "echec", "budget epuise")
            continue

        fin_precedente = sections[-1][1][-320:] if sections else ""
        try:
            corps, auteur = rediger_scene(ctx, bible, grille, index, scene,
                                          memoire, fin_precedente)
        except budget.BudgetEpuise as exc:
            budget_epuise = True
            ctx.journal("     {} — scenes restantes reduites a leur fiche".format(exc))
            ctx.etape("scene-{}".format(index + 1), "echec", str(exc))
            corps, auteur = _repli(scene), ""
        except Exception as exc:
            ctx.journal("     echec : {} — scene conservee en resume".format(exc))
            ctx.etape("scene-{}".format(index + 1), "echec", str(exc))
            corps, auteur = _repli(scene), ""
        else:
            # Controle local. « exiger_structure=False » : une scene n'a ni
            # sous-titre ni liste numerotee, et le lui reprocher la ferait
            # reecrire dans le sens contraire de ce qu'elle doit etre.
            try:
                corps, controles = equipe.controler_et_corriger(
                    ctx, corps, scene["titre"], ctx.mots_par_chapitre,
                    precedents=[c for _, c in sections],
                    tentatives=2 if passes else 1,
                    exiger_structure=False,
                )
                local[scene["titre"]] = controles
                ctx.journal("     controle : " + controles[-1].resume())
            except budget.BudgetEpuise as exc:
                budget_epuise = True
                ctx.journal("     {} — corrections interrompues".format(exc))

            if passes and not budget_epuise:
                try:
                    corps, _ = equipe.affiner(
                        ctx, corps, scene["titre"], bible.get("enjeu", ""),
                        auteur, passes=passes)
                    if passes >= 2:
                        corps = equipe.polir(ctx, corps, auteur)
                        ctx.journal("     style : resserre par le styliste")
                except budget.BudgetEpuise as exc:
                    budget_epuise = True
                    ctx.journal("     {} — relecture interrompue".format(exc))

        sections.append((scene["titre"], corps))

        # La memoire se met a jour meme quand tout le reste a echoue : c'est
        # elle qui porte la continuite des scenes suivantes.
        if budget_epuise:
            memoire = _memoire_de_secours(memoire, scene)
        else:
            try:
                memoire = mettre_a_jour_resume(ctx, memoire, scene, corps)
            except budget.BudgetEpuise as exc:
                budget_epuise = True
                ctx.journal("     {} — memoire figee sur les pivots".format(exc))
                memoire = _memoire_de_secours(memoire, scene)
            except Exception:
                memoire = _memoire_de_secours(memoire, scene)
        memoires.append(memoire)
        ctx.etape("scene-{}".format(index + 1), "ok", scene["titre"])

    ctx.journal("Etape 4/5 — controle de continuite...")
    continuite = controler_continuite(bible, grille, sections, memoires)
    ctx.journal("  " + continuite["resume"])
    for anomalie in continuite["anomalies"][:4]:
        ctx.journal("    [{}] {}".format(anomalie["gravite"], anomalie["detail"]))
    ctx.etape("continuite",
              "ok" if not continuite["majeures"] else "echec",
              continuite["resume"])
    (dossier / "continuite.json").write_text(
        json.dumps({"continuite": continuite, "memoires": memoires},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    ctx.journal("Etape 5/5 — mise en forme et export...")
    fichiers = exporter(ctx, bible, sections)

    rapport: Dict[str, Any] = {"continuite": continuite}
    if local:
        rapport["controle_local"] = {
            "note_moyenne_initiale": round(
                sum(s[0].note for s in local.values()) / len(local), 2),
            "note_moyenne_finale": round(
                sum(s[-1].note for s in local.values()) / len(local), 2),
        }
        ctx.journal("  controle local : {} -> {} / 10".format(
            rapport["controle_local"]["note_moyenne_initiale"],
            rapport["controle_local"]["note_moyenne_finale"]))
    rapport["mesure_finale"] = ctrl.controler_ensemble(
        sections, ctx.mots_par_chapitre)
    (dossier / "rapport-qualite.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.journal("  note finale mesuree : {} / 10".format(
        rapport["mesure_finale"]["note_moyenne"]))

    if alertes:
        (dossier / "AVERTISSEMENT.txt").write_text(
            securite.CLAUSE_RENFORCEE + "\n\nDomaines detectes : "
            + ", ".join(d for d, _ in alertes) + "\n", encoding="utf-8")

    mots = sum(D.compter_mots(corps) for _, corps in sections)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "sous_titre": bible.get("genre", ""),
        "dossier": str(dossier),
        "scenes": total,
        "chapitres": total,
        "mots": mots,
        "fichiers": [f.name for f in fichiers],
        "qualite": rapport,
        "budget_epuise": budget_epuise,
        "note": (rapport.get("mesure_finale") or {}).get("note_moyenne"),
        "alertes": [d for d, _ in alertes],
    }
    evenements.publier("produit", etat="termine", titre=titre, mots=mots,
                       dossier=str(dossier))
    terminer(ctx, fichiers, {
        "mots": mots, "scenes": total, "promesse": bible.get("premisse"),
        "note": (rapport.get("mesure_finale") or {}).get("note_moyenne"),
        "continuite": continuite["resume"],
        "defauts": [a["detail"] for a in continuite["anomalies"]],
    })
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _repli(scene: Dict[str, Any]) -> str:
    """Scene non redigee : sa fiche, en prose minimale.

    Comme pour l'ebook, livrer une scene reduite a sa fiche vaut mieux que
    perdre l'histoire entiere parce qu'un plafond est tombe a l'avant-derniere.
    """
    morceaux = [m for m in (
        "{} — {}".format(scene.get("lieu", ""), ", ".join(scene["personnages"])),
        scene.get("objectif", ""),
        scene.get("obstacle", ""),
        scene.get("pivot", ""),
    ) if m and m.strip(" —,")]
    return "\n\n".join(morceaux) or "Scene non redigee."


def exporter(ctx: Contexte, bible: Dict[str, Any],
             sections: List[Tuple[str, str]]) -> List[Path]:
    """Confie l'histoire a l'assemblage commun.

    Une nouvelle est de la prose sans mise en page particuliere : tout est le
    comportement par defaut de usine/render/livraison.py. Seuls changent le
    vocabulaire (« scenes ») et le style de couverture — une couverture de
    guide pratique sur une fiction se voit immediatement.
    """
    produit = livraison.Produit(
        type="nouvelle",
        titre=bible["titre"],
        sous_titre=bible.get("genre", ""),
        promesse=bible.get("premisse", ""),
        blocs=livraison.blocs_depuis_sections(sections),
        formats=("md", "pdf", "epub", "html", "txt"),
        police_corps="Times-Roman",
        style_couverture="literary fiction book cover, atmospheric, {}".format(
            bible.get("genre") or ctx.sujet),
        langue=ctx.langue_iso,
        libelle_sections="scenes",
    )
    return livraison.livrer(ctx, produit)
