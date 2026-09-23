"""Ce que l'usine decide quand on ne lui dit rien, et comment elle le montre.

Taper un sujet et rien d'autre etait possible, mais trompeur : les reglages
« par defaut » s'appliquaient — ton « pro », douze chapitres, « un public
francophone motive » — quel que soit le sujet. Un guide de fiscalite pour
experts-comptables et un carnet de recettes pour debutants sortaient donc avec
la meme voix, la meme longueur et la meme audience imaginaire. Ce n'etait pas
un defaut visible : le produit s'ecrivait, se notait, se vendait mal.

Un reglage par defaut n'est pas neutre. Il est juste invisible.

Ce module demande donc au modele ce que le sujet appelle : a qui l'on parle,
sur quel ton, en combien de sections, et dans quelle niche. Trois regles le
gouvernent :

1. **Ce que l'utilisateur a choisi n'est jamais touche.** Le brief ne remplit
   que les cases laissees vides. « --ton punchy » gagne toujours.
2. **Le brief se montre.** Une decision prise en silence ne se corrige pas :
   l'usine ecrit ce qu'elle a choisi et sous quel nom le redemander autrement.
3. **Il doit pouvoir echouer.** Un seul appel, court. Si le modele ne
   repond pas, le public et le ton deviennent une consigne explicite — « celui
   qui sert le mieux ce sujet » — et la taille retombe sur « standard ».
   Personne n'attend cinq minutes pour se voir proposer un ton.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core import llm
from .base import (CHAPITRES_MAX, CHAPITRES_MIN, MOTS_MAX, MOTS_MIN, TAILLES,
                   TONS)

# Le mot qui veut dire « decide pour moi ». Il vaut mieux qu'une case vide :
# une case vide se confond avec un reglage oublie, alors que « auto » est un
# choix — celui de ne pas choisir.
AUTO = "auto"

# Ce que lit le redacteur quand le brief n'a pas pu trancher.
#
# Mesure du 23/09/2026. Depuis que l'usine decide tout, les reglages par
# defaut valent « auto » — mais la regle d'echec disait encore « on garde les
# valeurs par defaut ». Les deux ensemble envoyaient litteralement
# « TON : auto » et « PUBLIC : auto » au modele de redaction : un mot sans
# sens la ou il attend une consigne. Ce n'est pas un reglage par defaut
# deguise : c'est la meme decision, confiee au redacteur qui a le sujet sous
# les yeux, et le journal le dit.
A_DEFAUT_DE_BRIEF = {
    "audience": "les lecteurs que ce sujet attire naturellement",
    "ton": "celui qui sert le mieux ce sujet et ce public",
}

# Ce qu'on demande au modele, et rien de plus : un brief court coute un appel
# court, et c'est le tout premier de la fabrication.
_INVITE = """Tu prepares la fabrication d'un {genre} sur ce sujet :

{sujet}

Decide ce qui convient VRAIMENT a ce sujet-la, pas ce qui conviendrait a
n'importe quoi. Reponds en JSON strict :

{{
  "audience": "a qui s'adresse ce produit, en une ligne precise (metier,
               niveau, situation) — surtout pas « un public motive »",
  "ton": "un des raccourcis ({tons}) OU une description libre de la voix",
  "sections": <nombre entier de sections entre {mini} et {maxi}>,
  "mots_par_section": <entier entre {mots_mini} et {mots_maxi}>,
  "niche": "le positionnement en trois a six mots",
  "promesse": "ce que le lecteur sait faire apres, en une phrase",
  "pourquoi": "en une phrase : pourquoi ce ton et cette longueur pour CE sujet"
}}

Un sujet technique et etroit merite peu de sections denses ; un sujet large et
debutant en merite davantage, plus courtes. Choisis en consequence."""


def _borner(valeur: Any, mini: int, maxi: int, defaut: int) -> int:
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return max(mini, min(maxi, nombre))


def demander(sujet: str, genre: str = "produit",
             journal: Optional[Any] = None) -> Dict[str, Any]:
    """Rend le brief du modele, ou {} s'il n'a pas pu etre obtenu.

    Rendre {} plutot que des valeurs inventees : l'appelant sait alors que
    rien n'a ete decide, et il le dit. Un brief a moitie devine serait pire que
    pas de brief — on croirait que le sujet a ete lu.
    """
    invite = _INVITE.format(
        genre=genre, sujet=sujet.strip()[:400],
        tons=", ".join(sorted(TONS)),
        mini=CHAPITRES_MIN, maxi=CHAPITRES_MAX,
        mots_mini=MOTS_MIN, mots_maxi=MOTS_MAX)
    try:
        brut = llm.generer_json(
            invite,
            systeme="Tu es un directeur editorial. Tu reponds en JSON strict, "
                    "en francais, sans commentaire autour.",
            # « raisonnement » : c'est un arbitrage, pas une redaction. Chez un
            # fournisseur qui n'a rien de tel, le role retombe sur standard.
            role="raisonnement",
            temperature=0.4,
            max_tokens=600,
        )
    except Exception as exc:          # pas de fournisseur, JSON illisible...
        if journal:
            journal("  brief automatique indisponible ({})".format(
                type(exc).__name__))
        return {}
    if not isinstance(brut, dict):
        return {}

    sections = _borner(brut.get("sections"), CHAPITRES_MIN, CHAPITRES_MAX,
                       TAILLES["standard"][0])
    mots = _borner(brut.get("mots_par_section"), MOTS_MIN, MOTS_MAX,
                   TAILLES["standard"][1])
    return {
        "audience": str(brut.get("audience") or "").strip()[:300],
        "ton": str(brut.get("ton") or "").strip()[:300],
        "sections": sections,
        "mots_par_section": mots,
        "niche": str(brut.get("niche") or "").strip()[:120],
        "promesse": str(brut.get("promesse") or "").strip()[:300],
        "pourquoi": str(brut.get("pourquoi") or "").strip()[:300],
    }


_INVITE_REGLAGES = """Tu prepares la fabrication de ce produit :

TYPE : {type_nom} — {type_resume}
SUJET : {sujet}
{connu}
Ces reglages n'ont pas ete choisis. Decide chacun d'apres le SUJET, pas
d'apres ce qui conviendrait a n'importe quoi :

{a_decider}

Reponds en JSON strict, une cle par reglage, rien d'autre :
{{{schema}}}"""


def decider_les_reglages(ctx: Any, type_produit: Any,
                         options: Dict[str, Any]) -> Dict[str, Any]:
    """Fait choisir a l'usine les reglages du type que personne n'a remplis.

    Pourquoi cette etape existe. Le brief automatique decidait trois choses —
    audience, ton, taille — et tout le reste tombait sur une valeur en dur :
    tout pack de posts partait sur LinkedIn, toute sequence d'e-mails etait
    une sequence de bienvenue, tout quiz etait de niveau intermediaire, tout
    outil logiciel etait une ligne de commande, tout album visait les 6-8 ans.

    Ces valeurs ne se voyaient nulle part. Un reglage par defaut n'est pas
    neutre, il est juste invisible — et l'usine est faite pour produire depuis
    ZERO, en decidant elle-meme a partir du sujet.

    Ce qui n'est PAS fait ici : deviner a la place de l'utilisateur. Un champ
    qu'il a rempli n'est jamais touche. Et si le modele ne repond pas, on rend
    {{}} : la chaine garde alors ce qu'elle avait, et le journal le dit — un
    reglage a moitie devine serait pire que pas de reglage, parce qu'on
    croirait que le sujet a ete lu.
    """
    champs = [c for c in (getattr(type_produit, "champs", None) or ())
              if not str(options.get(c.nom) or "").strip()
              and getattr(c, "decide_par_l_usine", True)
              # Un booleen decoche veut dire « fais-le », pas « decide a ma
              # place » : ce sont les seuls champs qui parlent de ce que
              # l'utilisateur veut depenser ou sauter, pas du produit.
              and c.genre != "booleen"]
    if not champs or not (ctx.sujet or "").strip():
        return {}

    lignes, schema = [], []
    for champ in champs:
        choix = [v for v in (champ.choix or ()) if v]
        attendu = ("un de : " + ", ".join(choix) if choix
                   else "un entier" if champ.genre == "entier"
                   else "oui ou non" if champ.genre == "booleen"
                   else "texte libre, court")
        lignes.append("- {} ({}) : {}".format(
            champ.nom, attendu, (champ.aide or champ.libelle)[:150]))
        schema.append('"{}": ""'.format(champ.nom))

    deja = [(c.libelle, options[c.nom]) for c in (type_produit.champs or ())
            if str(options.get(c.nom) or "").strip()]
    connu = ("DEJA CHOISI, a respecter : "
             + " ; ".join("{} = {}".format(n, v) for n, v in deja) + "\n"
             if deja else "")

    ctx.journal("L'usine decide {} reglage(s) : {}...".format(
        len(champs), ", ".join(c.nom for c in champs[:6])))
    try:
        brut = llm.generer_json(
            _INVITE_REGLAGES.format(
                type_nom=type_produit.nom, type_resume=type_produit.resume,
                sujet=(ctx.sujet or "").strip()[:400], connu=connu,
                a_decider="\n".join(lignes), schema=", ".join(schema)),
            systeme="Tu es un directeur editorial. Tu reponds en JSON strict, "
                    "en francais, sans commentaire autour.",
            role="raisonnement", temperature=0.4, max_tokens=700)
    except Exception as exc:
        ctx.journal("  l'usine n'a pas pu decider ({}) — les reglages "
                    "restent vides".format(type(exc).__name__))
        return {}
    if not isinstance(brut, dict):
        return {}

    decides: Dict[str, Any] = {}
    # Ce que le modele a repondu et qu'on n'a pas su lire. Ecarter est la
    # bonne decision ; se taire ne l'est pas.
    #
    # Journal reel du 16/09/2026, roman : « L'usine decide 9 reglage(s) »
    # puis HUIT valeurs. Le neuvieme etait « genre » — le plus structurant de
    # tous — auquel le modele avait repondu « drame contemporain », qui n'est
    # pas dans la liste fermee. Le roman est parti sans contrat de genre, et
    # rien ne l'a dit : il fallait compter les lignes du journal pour s'en
    # apercevoir.
    ecartes: List[str] = []
    for champ in champs:
        valeur = str(brut.get(champ.nom) or "").strip()
        if not valeur:
            ecartes.append("{} (sans reponse)".format(champ.nom))
            continue
        choix = [v for v in (champ.choix or ()) if v]
        if choix:
            # Le modele rend parfois une variante proche. On ne la corrige
            # pas : on l'ecarte. Accepter « thriller psychologique » la ou le
            # champ attend « thriller » ferait entrer dans la fiche une valeur
            # que rien d'autre ne sait relire.
            correspond = [v for v in choix if v.lower() == valeur.lower()]
            if not correspond:
                ecartes.append("{} : « {} » hors de la liste ({})".format(
                    champ.nom, valeur[:40], ", ".join(choix[:5])))
                continue
            valeur = correspond[0]
        elif champ.genre in ("entier", "decimal"):
            # Un modele rend « 12 », « 12 mm » ou « douze ». Les deux premiers
            # se lisent, le troisieme est ecarte plutot que devine. Oublier le
            # decimal faisait partir « reliure » en chaine de caracteres, et la
            # chaine d'impression comparait un texte a zero.
            try:
                nombre = float(str(valeur).replace(",", ".").split()[0])
            except (TypeError, ValueError, IndexError):
                ecartes.append("{} : « {} » n'est pas un nombre".format(
                    champ.nom, valeur[:40]))
                continue
            valeur = int(nombre) if champ.genre == "entier" else nombre
        elif champ.genre == "booleen":
            valeur = valeur.lower() in ("oui", "true", "vrai", "1")
        decides[champ.nom] = valeur

    for nom, valeur in decides.items():
        ctx.journal("  {} : {}".format(nom, valeur))
    for perdu in ecartes:
        ctx.journal("  [!] non retenu — {}".format(perdu))
    if ecartes:
        # Le compte, parce que huit lignes sous une annonce de neuf ne se
        # remarquent pas sur un ecran de telephone.
        ctx.journal("  {} reglage(s) sur {} restent a la charge de la chaine."
                    .format(len(ecartes), len(champs)))
    return decides


def a_decider(ctx: Any) -> List[str]:
    """Les champs que l'utilisateur a laisses a l'usine.

    Un champ vaut « auto » soit parce qu'il a ete demande ainsi, soit parce
    que le reglage par defaut le dit. Les deux veulent dire la meme chose, et
    c'est bien le point : ne pas choisir est un choix, et il se voit.
    """
    manquants = []
    if not (ctx.audience or "").strip() or (ctx.audience or "").strip() == AUTO:
        manquants.append("audience")
    if not (ctx.ton or "").strip() or (ctx.ton or "").strip() == AUTO:
        manquants.append("ton")
    if (not (ctx.taille or "").strip() or (ctx.taille or "").strip() == AUTO) \
            and not ctx.chapitres:
        manquants.append("taille")
    return manquants


def appliquer(ctx: Any, genre: str = "produit") -> Dict[str, Any]:
    """Complete le contexte avec ce que le modele propose, et le dit.

    Rend le brief applique (vide si rien n'a ete demande ou obtenu), pour que
    la chaine puisse le ranger dans la fiche du produit : une decision qu'on
    ne retrouve plus six mois apres n'aide pas a comprendre le resultat.
    """
    manquants = a_decider(ctx)
    if not manquants:
        return {}
    ctx.journal("Brief automatique : {} a decider...".format(
        ", ".join(manquants)))
    brief = demander(ctx.sujet, genre, journal=ctx.journal)
    if not brief:
        return _laisser_au_redacteur(ctx, manquants, {})

    applique: Dict[str, Any] = {}
    if "audience" in manquants and brief["audience"]:
        ctx.audience = brief["audience"]
        applique["audience"] = brief["audience"]
    if "ton" in manquants and brief["ton"]:
        ctx.ton = brief["ton"]
        applique["ton"] = brief["ton"]
    # Un brief obtenu peut laisser une case vide : elle ne doit pas partir
    # « auto » pour autant.
    _laisser_au_redacteur(ctx, manquants, applique)
    if "taille" in manquants:
        ctx.chapitres = brief["sections"]
        ctx.mots_section = brief["mots_par_section"]
        applique["sections"] = brief["sections"]
        applique["mots_par_section"] = brief["mots_par_section"]
    for cle in ("niche", "promesse", "pourquoi"):
        if brief.get(cle):
            applique[cle] = brief[cle]

    # Le brief se montre, et il se redemande autrement. Sans ces lignes, une
    # decision prise en silence ne se corrige pas.
    if applique.get("niche"):
        ctx.journal("  niche : {}".format(applique["niche"]))
    if applique.get("audience"):
        ctx.journal("  audience : {}".format(applique["audience"]))
    if applique.get("ton"):
        ctx.journal("  ton : {}".format(applique["ton"]))
    if applique.get("sections"):
        ctx.journal("  volume : {} sections de ~{} mots".format(
            applique["sections"], applique["mots_par_section"]))
    if applique.get("pourquoi"):
        ctx.journal("  pourquoi : {}".format(applique["pourquoi"]))
    ctx.journal("  (imposez le votre avec --ton, --audience, --chapitres)")
    return applique


def _laisser_au_redacteur(ctx: Any, manquants: List[str],
                          applique: Dict[str, Any]) -> Dict[str, Any]:
    """Remplace un « auto » que personne n'a tranche par une consigne lisible.

    Enrichit et rend « applique » : ce qui a ete confie au redacteur figure
    dans la fiche du produit comme le reste des decisions.
    """
    confies = []
    for cle in ("audience", "ton"):
        if cle in manquants and cle not in applique:
            setattr(ctx, cle, A_DEFAUT_DE_BRIEF[cle])
            confies.append(cle)
    if confies:
        applique["confie_au_redacteur"] = confies
        ctx.journal("  {} : laisse(s) au redacteur, qui a le sujet sous les "
                    "yeux".format(" et ".join(confies)))
    return applique


def completer(ctx: Any, genre: str, choisi: Any) -> Dict[str, Any]:
    """Ce qu'on fait avant toute fabrication, par quelque porte qu'on entre.

    Mesure du 23/09/2026 : seule la ligne de commande appelait le brief.
    Depuis le tableau de bord et l'usine continue — le bouton « Generer » et
    la boucle, c'est-a-dire l'usage reel sur un telephone —, quinze invites
    sur quinze portaient « TON : auto » et « PUBLIC : auto ». Zero sur treize
    par la ligne de commande. Rien n'echouait : le livre s'ecrivait, d'une
    voix que personne n'avait choisie. Le tableau de bord ne posait pas non
    plus la promesse de lecture d'une fiction.

    « choisi » est ce que l'utilisateur a fixe : un « Namespace » cote ligne
    de commande, un dictionnaire d'options cote tableau de bord et file. La
    promesse d'abord : pour une fiction, ce qui a ete choisi est justement le
    sous-genre et la fin, et le brief ne decide que du reste.
    """
    from . import fiction

    fiction.poser_la_promesse(ctx, choisi)
    ctx.meta["brief"] = appliquer(ctx, genre)
    return ctx.meta["brief"]
