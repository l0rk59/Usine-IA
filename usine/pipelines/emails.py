"""Sequence e-mail : la serie qu'un vendeur envoie apres une inscription.

C'est le produit digital le plus achete par ceux qui vendent deja quelque
chose d'autre, et l'usine ne savait pas le fabriquer. Elle savait ecrire un
livre de deux cents pages et trente posts LinkedIn, mais pas les sept
messages qui separent une inscription d'un premier achat.

Ce qui distingue une sequence d'une suite d'articles, et qui explique la
forme de cette chaine : elle se lit dans l'ORDRE, a jours d'intervalle, par
quelqu'un qui a oublie le message precedent. Chaque message doit donc se
tenir seul ET renvoyer au suivant. C'est pour cela que le plan est etabli en
un appel — la progression est le produit — puis les messages rediges par
lots, chacun sachant ce qui le precede et ce qui le suit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import document as D
from ..render import libelles, livraison
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

# Ce que la sequence cherche a obtenir. Le vocabulaire du metier, parce que
# c'est celui dans lequel l'acheteur pense son besoin.
OBJECTIFS = {
    "bienvenue": "accueillir un nouvel inscrit et installer la confiance",
    "vente": "amener a un premier achat, sans forcer",
    "fidelisation": "faire revenir un client qui a deja achete",
    "relance": "reveiller une liste devenue silencieuse",
}


def _plan(ctx: Contexte, nombre: int, objectif: str, rythme: int) -> List[Dict[str, Any]]:
    """La progression de la sequence, en un appel.

    En un seul appel parce que la progression EST le produit : demander les
    messages un par un donnerait sept bons messages qui ne vont nulle part.
    """
    invite = (
        "Construis une sequence de {n} e-mails sur : {sujet}\n"
        "DESTINATAIRE : {audience}\n"
        "OBJECTIF DE LA SEQUENCE : {but}\n"
        "RYTHME : un message tous les {rythme} jour(s)\n\n"
        "Chaque message doit se tenir seul — le lecteur a oublie le "
        "precedent — et donner envie d'ouvrir le suivant. Fais progresser :"
        " on ne demande rien au premier message, et le dernier ne decouvre "
        "pas le sujet.\n\n"
        "Pour chaque message :\n"
        "- 'objet' : la ligne d'objet, 6 a 9 mots, sans majuscules criardes "
        "ni point d'exclamation.\n"
        "- 'angle' : en une phrase, ce que ce message apporte et lui seul.\n"
        "- 'action' : ce qu'on demande au lecteur, ou \"aucune\" quand on ne "
        "demande rien — et pour un accueil, la plupart n'en demandent pas.\n\n"
        "Schema JSON exact :\n"
        '{{"messages": [{{"objet": "...", "angle": "...", "action": "..."}}]}}\n'
        "Exactement {n} messages, dans l'ordre d'envoi."
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience,
             but=OBJECTIFS.get(objectif, OBJECTIFS["bienvenue"]), rythme=rythme)
    donnees = equipe.MARKETEUR.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.7, max_tokens=2400)
    messages = donnees.get("messages") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for rang, message in enumerate(messages or [], 1):
        if not isinstance(message, dict) or not message.get("objet"):
            continue
        action = str(message.get("action") or "").strip()
        propres.append({
            "rang": rang,
            "jour": (rang - 1) * rythme,
            "objet": nettoyer_titre(str(message["objet"])),
            "angle": str(message.get("angle") or "").strip(),
            # « aucune » est une reponse valable, et la garder telle quelle
            # evite de fabriquer un appel a l'action la ou le plan disait
            # justement de ne rien demander.
            "action": "" if action.lower() in ("aucune", "aucun", "none") else action,
        })
    if not propres:
        raise ValueError("Aucun message exploitable dans le plan")
    return propres


def _rediger(ctx: Contexte, message: Dict[str, Any], plan: List[Dict[str, Any]],
             objectif: str) -> Dict[str, str]:
    """Le corps d'un message, qui sait ce qui l'entoure."""
    rang = message["rang"]
    avant = plan[rang - 2]["objet"] if rang >= 2 else ""
    apres = plan[rang]["objet"] if rang < len(plan) else ""
    invite = (
        "Sujet de la sequence : {sujet}\nDestinataire : {audience}\n"
        "Objectif : {but}\nTon : {ton}\n\n"
        "MESSAGE {rang} SUR {total} — jour {jour}\n"
        "Objet : {objet}\nAngle : {angle}\n"
        "Ce qu'on demande : {action}\n"
        "{contexte}\n\n"
        "Redige le corps du message : 180 a 320 mots. Ecris a une personne, "
        "pas a une liste. Commence par quelque chose qui se lit sans le "
        "message precedent. Pas de formule d'ouverture creuse, pas de "
        "« j'espere que vous allez bien ».\n\n"
        "Schema JSON exact :\n"
        "{{\"objet\": \"la ligne d'objet, retouchee si tu fais mieux\", "
        '"apercu": "la ligne de preheader, 8 a 12 mots", '
        '"corps": "le message complet, paragraphes separes par des sauts de '
        "ligne\", \"post_scriptum\": \"un P.S. d'une ligne, ou une chaine vide\"}}"
    ).format(
        sujet=ctx.sujet, audience=ctx.audience, ton=ctx.ton,
        but=OBJECTIFS.get(objectif, OBJECTIFS["bienvenue"]),
        rang=rang, total=len(plan), jour=message["jour"],
        objet=message["objet"], angle=message["angle"],
        action=message["action"] or "rien — ce message ne demande rien",
        contexte=("Message precedent : « {} »\n".format(avant) if avant else
                  "C'est le premier message de la sequence.\n")
        + ("Message suivant : « {} »".format(apres) if apres else
           "C'est le dernier message de la sequence."))
    donnees = equipe.REDACTEUR.travailler_json(
        ctx, invite, role_modele="standard", temperature=0.75, max_tokens=1600)
    if not isinstance(donnees, dict) or not str(donnees.get("corps") or "").strip():
        raise ValueError("message vide")
    return {
        "objet": nettoyer_titre(str(donnees.get("objet") or message["objet"])),
        "apercu": str(donnees.get("apercu") or "").strip(),
        "corps": str(donnees["corps"]).strip(),
        "post_scriptum": str(donnees.get("post_scriptum") or "").strip(),
    }


def produire(ctx: Contexte, nombre: int = 7, intention: str = "bienvenue",
             rythme: int = 2) -> Dict[str, Any]:
    nombre = max(3, min(int(nombre or 7), 20))
    rythme = max(1, min(int(rythme or 2), 14))
    objectif = intention if intention in OBJECTIFS else "bienvenue"

    titre = libelles.libelle(ctx.langue_iso, "sequence_titre", titre=ctx.sujet)
    dossier = preparer(ctx, "emails", titre)

    ctx.journal("Étape 1/3 — progression de la séquence...")
    plan = _plan(ctx, nombre, objectif, rythme)
    ctx.etape("plan", "ok", "{} messages".format(len(plan)))

    ctx.journal("Étape 2/3 — rédaction des messages...")
    for message in plan:
        ctx.journal("  [{}/{}] {}".format(message["rang"], len(plan),
                                          message["objet"]))
        perdu = ""
        try:
            message.update(_rediger(ctx, message, plan, objectif))
        except Exception as exc:
            perdu = str(exc)
            ctx.journal("     échec : {}".format(exc))
            # Un message reduit a son angle est une sequence trouee : on le
            # dit, et « essentiel » rend le produit invendable tant qu'il
            # manque. Une sequence de sept messages dont trois sont vides ne
            # se vend pas — elle se termine.
            message.setdefault("apercu", "")
            message.setdefault("corps", message["angle"] or message["objet"])
            message.setdefault("post_scriptum", "")
        ctx.etape("message-{}".format(message["rang"]),
                  "echec" if perdu else "ok", perdu or message["objet"])

    ctx.journal("Étape 3/3 — export...")
    fichiers = _exporter(ctx, titre, plan, objectif, rythme)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "messages": len(plan),
        "jours": plan[-1]["jour"] if plan else 0,
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"messages": len(plan), "objectif": objectif})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _exporter(ctx: Contexte, titre: str, plan: List[Dict[str, Any]],
              objectif: str, rythme: int) -> List[Path]:
    t = libelles.textes(ctx.langue_iso)
    sous_titre = t["emails_sous_titre"].format(nombre=len(plan), rythme=rythme)

    def mode_emploi(doc) -> None:
        doc.paragraphe(t["emails_ordre"], justifier=True)
        doc.paragraphe(t["emails_csv"], justifier=True)
        doc.encadre(t["emails_avant_titre"], t["emails_avant"])

    # Voir le commentaire de « quiz.py » : sans « corps », ce bloc n'existe
    # que dans le PDF, et la page HTML — celle qu'on ouvre sur un telephone —
    # s'ouvre directement sur le premier message, sans mode d'emploi.
    avant = t["emails_avant"]
    blocs = [livraison.Bloc(
        titre=t["emails_mode_emploi_titre"],
        corps="{}\n\n{}\n\n**{}** — {}".format(
            t["emails_ordre"], t["emails_csv"], t["emails_avant_titre"],
            avant[:1].lower() + avant[1:]),
        rendu_pdf=mode_emploi)]
    for message in plan:
        blocs.append(livraison.Bloc(
            titre=t["sequence_jour"].format(jour=message["jour"],
                                            objet=message["objet"]),
            corps=_markdown_message(message, t),
            rendu_pdf=_mise_en_page(message, t),
            rendu_html=_html_message(message, t),
        ))

    produit = livraison.Produit(
        type="emails", titre=titre, sous_titre=sous_titre,
        promesse=t["emails_objectifs"].get(objectif,
                                           OBJECTIFS[objectif]).capitalize(),
        blocs=blocs,
        tableaux=[livraison.Tableau(
            nom="sequence",
            colonnes=list(t["emails_colonnes"]),
            # Le CSV s'importe dans un outil d'e-mailing, qui envoie le texte
            # tel quel : un « **mot** » y arrivait, etoiles comprises, dans la
            # boite de chaque abonne. La page et le PDF, eux, rendent le gras.
            lignes=[[str(m["jour"]), m["objet"],
                     D.nettoyer_inline(m.get("apercu", "")),
                     D.nettoyer_inline(m.get("corps", "")),
                     D.nettoyer_inline(m.get("post_scriptum", "")),
                     D.nettoyer_inline(m.get("action", ""))] for m in plan],
            # Les outils d'emailing francais ouvrent ce fichier dans Excel
            # avant de l'importer : sans marqueur d'encodage, les accents des
            # objets arrivent casses jusque dans la boite du destinataire.
            bom=True)],
        donnees={"titre": titre, "objectif": objectif, "rythme": rythme,
                 "messages": plan},
        nom_donnees="sequence",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture="minimal envelope, email sequence, clean",
        nom_fichier=slug(titre, 48),
    )
    return livraison.livrer(ctx, produit)


def _markdown_message(message: Dict[str, Any], t: Dict[str, Any]) -> str:
    lignes = [t["deux_points"].format(libelle="**{}**".format(t["emails_objet"]),
                                      texte=message["objet"])]
    if message.get("apercu"):
        lignes.append(t["deux_points"].format(
            libelle="**{}**".format(t["emails_apercu"]), texte=message["apercu"]))
    lignes.append("")
    lignes.append(message.get("corps", ""))
    if message.get("post_scriptum"):
        lignes.append("\n*P.S. — {}*".format(message["post_scriptum"]))
    if message.get("action"):
        lignes.append("\n> " + t["deux_points"].format(
            libelle=t["emails_demande"], texte=message["action"]))
    return "\n".join(lignes)


def _mise_en_page(message: Dict[str, Any], t: Dict[str, Any]):
    def rendre(doc) -> None:
        doc.paragraphe(t["deux_points"].format(libelle=t["emails_objet"],
                                               texte=message["objet"]),
                       taille=11, police="Helvetica-Bold")
        if message.get("apercu"):
            doc.paragraphe(t["deux_points"].format(libelle=t["emails_apercu"],
                                                   texte=message["apercu"]), taille=9,
                           police="Helvetica-Oblique")
        # Le corps passe par l'analyseur, comme dans la page : une citation,
        # une liste, un encadre « A retenir » sortaient avec leurs « > » et
        # leurs « ** » quand le PDF l'imprimait ligne a ligne.
        D.vers_pdf(D.analyser(str(message.get("corps", ""))), doc)
        if message.get("post_scriptum"):
            doc.paragraphe("P.S. — " + message["post_scriptum"], taille=10,
                           police="Helvetica-Oblique")
        if message.get("action"):
            doc.encadre(t["emails_demande"], message["action"])

    return rendre


def _html_message(message: Dict[str, Any], t: Dict[str, Any]) -> str:
    corps = ["<p>{}</p>".format(t["deux_points"].format(
        libelle="<strong>{}</strong>".format(D.inline_html(t["emails_objet"])),
        texte=D.inline_html(message["objet"])))]
    if message.get("apercu"):
        corps.append("<p><em>{}</em></p>".format(D.inline_html(message["apercu"])))
    corps.append(D.vers_html(D.analyser(message.get("corps", ""))))
    if message.get("post_scriptum"):
        corps.append("<p><em>P.S. — {}</em></p>".format(
            D.inline_html(message["post_scriptum"])))
    if message.get("action"):
        corps.append('<aside class="encadre"><p class="encadre-titre">'
                     "{}</p><p>{}</p></aside>".format(
                         D.inline_html(t["emails_demande"]),
                         D.inline_html(message["action"])))
    return "\n".join(corps)
