"""Generation de variantes a tester : titres et couvertures.

Un test A/B ne vaut que par ce qu'il compare. Deux reformulations du meme
titre ne reveleront jamais rien, quelle que soit la duree du test. Ces
generateurs imposent donc des ANGLES differents, puis verifient que le
resultat est effectivement distinct avant de le proposer.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents import equipe
from ..core import config, diagnostic_titre, evenements, experience, images
from ..core import store
from ..render.page import ecrire_page
from .base import Contexte, nettoyer_titre, slug

# Angles volontairement eloignes les uns des autres : c'est ce qui rend le
# test informatif. Chaque variante repond a une question differente du lecteur.
ANGLES = [
    ("benefice", "le resultat concret obtenu, formule au present"),
    ("methode", "le systeme ou le nombre d'etapes, avec un chiffre"),
    ("probleme", "la douleur que le lecteur reconnait immediatement"),
    ("contraste", "ce qu'il croyait vrai et qui ne l'est pas"),
    ("audience", "le lecteur nomme explicitement, avec sa situation"),
    ("delai", "le resultat et le temps qu'il demande"),
    ("question", "une question a laquelle le lecteur veut la reponse"),
    ("preuve", "un fait verifiable qui rend la promesse credible"),
]

# Directions visuelles nettement distinctes : comparer six degrades de bleu ne
# testerait rien non plus. Chaque direction combine une mise en page et une
# palette de l'atelier — donc des couvertures REELLEMENT LIVRABLES. Tester
# des images filigranees revenait a choisir entre deux propositions dont
# aucune ne pouvait etre vendue.
STYLES_COUVERTURE = [
    ("bandeau-nuit", 0, 0), ("centre-encre", 1, 1),
    ("diagonale-foret", 2, 2), ("arcs-prune", 3, 3),
    ("bloc-acier", 4, 4), ("bandeau-argile", 6, 0),
    ("centre-menthe", 7, 1), ("arcs-safran", 5, 3),
]


# --------------------------------------------------------------------------
# Titres
# --------------------------------------------------------------------------


def generer_titres(
    ctx: Contexte,
    titre_actuel: str,
    description: str = "",
    nombre: int = 5,
    rattrapage: bool = True,
) -> List[Dict[str, str]]:
    """Produit des titres sur des angles differents, puis verifie la distinction."""
    angles = ANGLES[: max(2, min(nombre, len(ANGLES)))]
    consignes = "\n".join(
        "- angle « {} » : {}".format(nom, description_angle)
        for nom, description_angle in angles)

    invite = (
        "TITRE ACTUEL : {actuel}\n"
        "CONTENU DU PRODUIT : {contenu}\n"
        "LECTEUR : {audience}\n\n"
        "Propose un titre de vente par angle, en respectant STRICTEMENT l'angle "
        "demande. Les titres doivent etre franchement differents entre eux : "
        "s'ils se ressemblent, le test ne revelera rien.\n\n"
        "{consignes}\n\n"
        "Contraintes : 40 a 70 caracteres, pas de mot creux "
        "(« ultime », « revolutionnaire », « secret »), pas de promesse de "
        "resultat garanti, pas de point d'exclamation.\n\n"
        "Schema JSON exact :\n"
        '{{"titres": [{{"angle": "...", "titre": "...", '
        '"pourquoi": "en une phrase, pourquoi ce titre peut fonctionner"}}]}}'
    ).format(actuel=titre_actuel, contenu=(description or ctx.sujet)[:1200],
             audience=ctx.audience, consignes=consignes)

    donnees = equipe.MARKETEUR.travailler_json(ctx, invite, max_tokens=2200)
    propositions = donnees.get("titres") if isinstance(donnees, dict) else donnees
    resultat: List[Dict[str, str]] = []
    for element in propositions or []:
        if not isinstance(element, dict) or not element.get("titre"):
            continue
        resultat.append({
            "titre": nettoyer_titre(str(element["titre"])),
            "angle": str(element.get("angle") or "").strip(),
            "pourquoi": str(element.get("pourquoi") or "").strip(),
        })
    resultat = resultat[:nombre]
    if not resultat:
        raise ValueError("aucun titre exploitable")

    # Verification de distinction : c'est ce que les outils d'A/B testing
    # omettent, et c'est ce qui condamne la plupart des tests avant le depart.
    controle = diagnostic_titre.distinguer([t["titre"] for t in resultat])
    if not controle["testable"] and rattrapage:
        ctx.journal("  variantes trop proches — nouvelle tentative")
        doublons = {p["b"] for p in controle["paires_trop_proches"]}
        garde = [t for i, t in enumerate(resultat) if i not in doublons]
        complement = _completer(ctx, titre_actuel, description,
                                garde, nombre - len(garde))
        resultat = (garde + complement)[:nombre]
        controle = diagnostic_titre.distinguer([t["titre"] for t in resultat])

    for entree in resultat:
        diagnostic = diagnostic_titre.diagnostiquer(entree["titre"])
        entree["diagnostic"] = diagnostic.resume()
        entree["mesures"] = diagnostic.mesures
    return resultat


def _completer(ctx: Contexte, titre_actuel: str, description: str,
               deja: List[Dict[str, str]], manquants: int) -> List[Dict[str, str]]:
    """Complete la serie en nommant explicitement ce qu'il faut eviter."""
    if manquants <= 0:
        return []
    invite = (
        "TITRE ACTUEL : {actuel}\nCONTENU : {contenu}\nLECTEUR : {audience}\n\n"
        "Ces titres existent deja et ne doivent PAS etre repris ni reformules :\n"
        "{existants}\n\n"
        "Propose {n} titre(s) supplementaire(s) qui abordent le produit sous un "
        "angle completement different : autre promesse, autre vocabulaire, autre "
        "entree en matiere. Aucun mot significatif en commun avec les titres "
        "ci-dessus.\n\n"
        'Schema JSON exact :\n{{"titres": [{{"angle": "...", "titre": "...", '
        '"pourquoi": "..."}}]}}'
    ).format(actuel=titre_actuel, contenu=(description or ctx.sujet)[:800],
             audience=ctx.audience, n=manquants,
             existants="\n".join("- " + t["titre"] for t in deja))
    try:
        donnees = equipe.MARKETEUR.travailler_json(ctx, invite, max_tokens=1200,
                                                   temperature=0.9)
    except Exception:
        return []
    propositions = donnees.get("titres") if isinstance(donnees, dict) else donnees
    return [
        {"titre": nettoyer_titre(str(e["titre"])),
         "angle": str(e.get("angle") or "").strip(),
         "pourquoi": str(e.get("pourquoi") or "").strip()}
        for e in (propositions or [])
        if isinstance(e, dict) and e.get("titre")
    ][:manquants]


# --------------------------------------------------------------------------
# Couvertures
# --------------------------------------------------------------------------


def generer_couvertures(
    ctx: Contexte,
    titre: str,
    dossier: Path,
    nombre: int = 4,
    sous_titre: str = "",
) -> List[Dict[str, str]]:
    """Une couverture livrable par direction visuelle."""
    dossier.mkdir(parents=True, exist_ok=True)
    styles = STYLES_COUVERTURE[: max(2, min(nombre, len(STYLES_COUVERTURE)))]
    resultat: List[Dict[str, str]] = []
    for index, (nom_style, palette, modele) in enumerate(styles):
        ctx.journal("  couverture {}/{} — style « {} »".format(
            index + 1, len(styles), nom_style))
        evenements.publier("section", etape="couverture", index=index + 1,
                           total=len(styles), titre=nom_style)
        chemin = images.generer_couverture(
            dossier, titre, sous_titre, ctx.auteur,
            en_ligne=False,          # l'atelier, toujours : on teste du vendable
            nom="couverture-{}-{}".format(index + 1, nom_style),
            palette=palette, modele=modele,
            marque=getattr(ctx, "marque", "") or "",
        )
        resultat.append({
            "style": nom_style,
            "fichier": chemin.name,
            "chemin": str(chemin),
            "genere": "atelier",
        })
    return resultat


# --------------------------------------------------------------------------
# Planche de comparaison
# --------------------------------------------------------------------------


def planche(experience_id: int, dossier: Path) -> Path:
    """Page de comparaison cote a cote, lisible sur telephone.

    Comparer quatre couvertures en ouvrant quatre fichiers l'un apres l'autre
    ne permet pas de choisir. Les voir ensemble, si.
    """
    analyse = experience.analyser(experience_id)
    exp = analyse["experience"]
    lot = analyse["variantes"]
    verdict_courant = analyse["verdict"]

    cartes = []
    for variante in lot:
        stats = variante.get("stats") or {}
        meta = variante.get("meta") or {}
        visuel = ""
        if variante.get("fichier"):
            visuel = '<img src="{}" alt="Variante {}"/>'.format(
                html.escape(variante["fichier"]), html.escape(variante["etiquette"]))
        if stats.get("vues"):
            mesures = (
                '<p class="chiffres">{} vues · {} action(s) · '
                '<strong>{:.1f} %</strong><br/>'
                '<span class="proba">{:.0f} % de chances d\'etre la meilleure</span>'
                "</p>"
            ).format(stats["vues"], stats["actions"], stats["taux"] * 100,
                     stats["probabilite_meilleure"] * 100)
        else:
            mesures = '<p class="chiffres vide">aucune observation</p>'

        cartes.append(
            '<article class="variante">'
            '<div class="etiquette">{etiquette}</div>'
            "{visuel}"
            "<h3>{contenu}</h3>"
            "{angle}{diagnostic}{mesures}</article>".format(
                etiquette=html.escape(variante["etiquette"]),
                visuel=visuel,
                contenu=html.escape(variante["contenu"]),
                angle='<p class="angle">angle : {}</p>'.format(
                    html.escape(str(meta["angle"]))) if meta.get("angle") else "",
                diagnostic='<p class="diagnostic">{}</p>'.format(
                    html.escape(str(meta["diagnostic"])))
                    if meta.get("diagnostic") else "",
                mesures=mesures,
            )
        )

    corps = [
        '<p class="verdict {etat}">{message}</p>'.format(
            etat=html.escape(verdict_courant.get("etat", "")),
            message=html.escape(verdict_courant.get("message", ""))),
        '<div class="grille-variantes">{}</div>'.format("".join(cartes)),
        "<h2>Comment reporter vos chiffres</h2>",
        "<p>Publiez une variante a la fois, une semaine chacune, puis relevez "
        "les vues et les ventes :</p>",
        "<pre><code>" + "\n".join(
            "usine ab observer {} --vues 120 --actions 4".format(v["id"])
            for v in lot) + "</code></pre>",
        "<p>Puis : <code>usine ab verdict {}</code></p>".format(experience_id),
    ]

    style_supplementaire = """
<style>
.grille-variantes { display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); }
.variante { border: 1px solid var(--bordure); border-radius: 12px;
  padding: 0.9rem; position: relative; }
.variante .etiquette { position: absolute; top: -0.7rem; left: 0.9rem;
  background: var(--accent); color: #fff; font-family: Helvetica, sans-serif;
  font-weight: 700; font-size: 0.78rem; padding: 0.12rem 0.55rem;
  border-radius: 999px; }
.variante img { width: 100%; border-radius: 8px; margin-bottom: 0.6rem; }
.variante h3 { margin: 0.3rem 0 0.5rem; font-size: 1rem; line-height: 1.35; }
.variante .angle, .variante .diagnostic { font-size: 0.78rem; color: var(--doux);
  margin: 0.2rem 0; }
.variante .chiffres { font-size: 0.82rem; margin: 0.6rem 0 0;
  padding-top: 0.5rem; border-top: 1px solid var(--bordure); }
.variante .chiffres.vide { color: var(--doux); font-style: italic; }
.variante .proba { color: var(--doux); font-size: 0.76rem; }
.verdict { border-left: 4px solid var(--accent); padding: 0.7rem 1rem;
  background: var(--encadre); border-radius: 0 8px 8px 0; }
.verdict.gagnant { border-color: #16a34a; }
.verdict.insuffisant, .verdict.indecis, .verdict.sans_donnees { border-color: #d97706; }
</style>
"""
    chemin = dossier / "planche-{}.html".format(experience_id)
    ecrire_page(
        chemin,
        "Variantes — {}".format(exp["titre"]),
        style_supplementaire + "\n".join(corps),
        sous_titre="{} · objectif : {}".format(
            exp["sujet"], experience.OBJECTIFS.get(exp["objectif"], exp["objectif"])),
        meta="experience n° {}".format(experience_id),
    )
    return chemin


# --------------------------------------------------------------------------
# Chaine complete
# --------------------------------------------------------------------------


def dossier_du_test(produit_id: str, titre: str) -> Path:
    """Ou vivent les variantes d'un test : a cote du produit, ou a part.

    La regle etait recopiee dans la ligne de commande et dans le tableau de
    bord, avec deja deux facons differentes d'abreger le titre. Deux copies
    d'une regle de CHEMIN qui divergent, ce sont des fichiers qu'une des
    deux interfaces ne retrouve plus.
    """
    produit = store.lire_produit(produit_id) if produit_id else None
    if produit and produit.get("dossier"):
        return Path(produit["dossier"]) / "variantes"
    return config.PRODUITS_DIR / "variantes-{}".format(slug(titre, 40))


def preparer_test(
    ctx: Contexte,
    titre_actuel: str,
    dossier: Path,
    sujet: str = "titre",
    nombre: int = 5,
    description: str = "",
    produit_id: str = "",
) -> Dict[str, Any]:
    """Genere les variantes, cree l'experience, ecrit la planche de comparaison."""
    dossier.mkdir(parents=True, exist_ok=True)
    experience_id = experience.creer(
        titre_actuel, sujet=sujet,
        objectif="ventes" if sujet in ("titre", "prix") else "clics",
        produit_id=produit_id)

    if sujet == "couverture":
        ctx.journal("Generation des couvertures...")
        elements = generer_couvertures(ctx, titre_actuel, dossier, nombre)
        for element in elements:
            experience.ajouter_variante(
                experience_id, "Couverture « {} »".format(element["style"]),
                fichier=element["fichier"],
                meta={"style": element["style"], "diagnostic": element["genere"]})
        distinction = {"testable": True,
                       "message": "{} directions visuelles distinctes.".format(
                           len(elements))}
    else:
        ctx.journal("Generation des titres...")
        elements = generer_titres(ctx, titre_actuel, description, nombre)
        for element in elements:
            experience.ajouter_variante(
                experience_id, element["titre"],
                meta={"angle": element["angle"], "pourquoi": element["pourquoi"],
                      "diagnostic": element["diagnostic"]})
        distinction = diagnostic_titre.distinguer([e["titre"] for e in elements])
        ctx.journal("  " + distinction["message"])

    chemin_planche = planche(experience_id, dossier)
    (dossier / "experience-{}.json".format(experience_id)).write_text(
        json.dumps({"experience_id": experience_id, "sujet": sujet,
                    "variantes": elements, "distinction": distinction},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {
        "experience_id": experience_id,
        "sujet": sujet,
        "variantes": elements,
        "distinction": distinction,
        "planche": str(chemin_planche),
        "dossier": str(dossier),
    }
