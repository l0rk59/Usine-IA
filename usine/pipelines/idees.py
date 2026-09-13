"""Recherche d'idees de produits : que fabriquer, pour qui, a quel prix."""

from __future__ import annotations

import csv
import json
from typing import Any, Dict, List

from ..core import config, llm, marche, veille, ventes
from . import catalogue
from ..render import document as D
from ..render import tableur
from ..render.page import ecrire_page
from .base import Contexte, nettoyer_titre

ROLE = (
    "un analyste de marche des produits digitaux, lucide sur ce qui se vend "
    "reellement et sur la saturation des niches"
)


def explorer(ctx: Contexte, nombre: int = 12,
             donnees_marche: str = "",
             terrain: str = "") -> List[Dict[str, Any]]:
    contexte_marche = (
        "\n\n{}\n\nAppuie-toi sur ces mesures reelles plutot que sur des "
        "impressions : cite-les quand elles soutiennent ou contredisent une "
        "idee.\n".format(donnees_marche) if donnees_marche else "")
    # Ce que ce vendeur a REELLEMENT vendu pese plus qu'un avis general sur
    # le marche : c'est la seule mesure qui porte sur son audience a lui.
    constate = ventes.resume_pour_ia()
    # Les mesures de marche disent si une niche existe ; la veille dit avec
    # quels mots on y parle des problemes. Un titre qui reprend le
    # vocabulaire des gens se trouve ; un titre ecrit en langue de brochure
    # ne se cherche pas.
    discussions = ("\n\n{}\n".format(terrain) if terrain else "")
    historique = ("\n\n{}\n\nTiens-en compte : ce qui s'est deja vendu chez "
                  "ce vendeur vaut mieux qu'une intuition de marche.\n"
                  .format(constate) if constate else "")
    invite = (
        "NICHE : {niche}\nAUDIENCE VISEE : {audience}\n"
        "{marche}{constate}{terrain}\n"
        "Propose {n} idees de produits digitaux realisables par une seule personne, "
        "sans stock ni equipe. Le type doit etre l'un de ceux que l'usine sait "
        "reellement fabriquer :\n{catalogue}\n\n"
        "Sois honnete : signale la concurrence quand elle est forte, et evite les "
        "idees qui exigent une expertise certifiee (medical, juridique, financier "
        "reglemente).\n\n"
        "Schema JSON exact :\n"
        '{{"idees": [{{"titre": "...", "type": "{types}", '
        '"probleme": "le probleme precis resolu", "acheteur": "qui paie et pourquoi", '
        '"promesse": "...", "prix_eur": 19, "difficulte": "facile|moyenne|elevee", '
        '"concurrence": "faible|moyenne|forte", '
        '"angle_differenciant": "...", "premier_canal": "ou trouver les 10 premiers '
        'acheteurs"}}]}}'
    ).format(niche=ctx.sujet, audience=ctx.audience, n=nombre,
             marche=contexte_marche, constate=historique,
             terrain=discussions,
             catalogue=catalogue.resume_pour_ia(),
             types="|".join(catalogue.cles(vendables=True)))
    donnees = llm.generer_json(invite, systeme=ctx.systeme(ROLE), role="costaud",
                               temperature=0.85, max_tokens=4096)
    idees = donnees.get("idees") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for idee in idees or []:
        if not isinstance(idee, dict) or not idee.get("titre"):
            continue
        # Le catalogue tolere les synonymes : un modele ecrit « planner » ou
        # « Notion » plutot que nos cles internes. Sans cela, ces idees
        # etaient silencieusement converties en ebooks.
        type_produit = catalogue.normaliser(str(idee.get("type") or ""))
        propres.append(
            {
                "titre": nettoyer_titre(str(idee["titre"])),
                "type": type_produit,
                "probleme": str(idee.get("probleme") or "").strip(),
                "acheteur": str(idee.get("acheteur") or "").strip(),
                "promesse": str(idee.get("promesse") or "").strip(),
                "prix_eur": idee.get("prix_eur") or 19,
                # Ces deux cles existent pour TOUTES les idees, meme quand
                # aucune vente ne vient les remplir : le CSV est ecrit avec
                # les cles de la premiere idee, et une cle qui n'apparait que
                # sur la troisieme ferait echouer l'export.
                "prix_source": "modele",
                "prix_fourchette": "",
                "difficulte": str(idee.get("difficulte") or "moyenne").strip(),
                "concurrence": str(idee.get("concurrence") or "moyenne").strip(),
                "angle_differenciant": str(idee.get("angle_differenciant") or "").strip(),
                "premier_canal": str(idee.get("premier_canal") or "").strip(),
            }
        )
    _ancrer_les_prix(propres)
    if not propres:
        raise ValueError("Aucune idee exploitable")
    return propres


def _ancrer_les_prix(idees: List[Dict[str, Any]]) -> None:
    """Remplace le prix devine par le prix reellement encaisse, quand il existe.

    Le « prix_eur » que renvoie le modele ne s'appuie sur rien : les quatre
    sources de marche mesurent la demande et la concurrence, aucune ne mesure
    un prix. Le seul nombre qui determine le revenu etait donc le moins fonde
    de tout le systeme.

    Trois ventes suffisent a preferer la mesure a l'intuition — c'est peu,
    mais trois observations valent mieux qu'aucune, et la provenance est
    inscrite dans « prix_source » pour que la difference reste visible.
    """
    for idee in idees:
        observes = ventes.prix_observes(idee["type"])
        retenu = next((o for o in observes if o["ventes"] >= 3), None)
        if retenu and retenu["devise"] == "EUR":
            idee["prix_eur"] = round(retenu["median"])
            idee["prix_source"] = "{} ventes constatees".format(retenu["ventes"])
            idee["prix_fourchette"] = "{:.0f} a {:.0f}".format(
                retenu["bas"], retenu["haut"])


def produire(ctx: Contexte, nombre: int = 12,
             avec_marche: bool = True,
             avec_veille: bool = True) -> Dict[str, Any]:
    rapport_marche: Dict[str, Any] = {}
    resume_marche = ""
    if avec_marche and not ctx.hors_ligne:
        ctx.journal("Mesure du marche (sources publiques)...")
        try:
            rapport_marche = marche.sonder(ctx.sujet, journal=ctx.journal)
            resume_marche = marche.resume_pour_ia(rapport_marche)
            lecture = rapport_marche["lecture"]
            ctx.journal("  {} — {}".format(lecture["fiabilite"],
                                           lecture["verdict"][:90]))
        except Exception as exc:
            ctx.journal("  marche indisponible : {}".format(exc))

    resume_terrain = ""
    rapport_veille = None
    if avec_veille and not ctx.hors_ligne:
        ctx.journal("Veille : ce que les gens en disent...")
        try:
            rapport_veille = veille.scouter(ctx.sujet)
            if rapport_veille.utilisable:
                resume_terrain = veille.resume_pour_ia(rapport_veille)
                ctx.journal("  {} discussions dans {} communaute(s) : {}".format(
                    len(rapport_veille.discussions),
                    len(rapport_veille.communautes),
                    ", ".join(m for m, _ in rapport_veille.mots[:5])))
            else:
                ctx.journal("  " + (rapport_veille.indisponible
                                    or "rien d'exploitable"))
        except Exception as exc:
            ctx.journal("  veille indisponible : {}".format(exc))

    ctx.journal("Exploration de la niche « {} »...".format(ctx.sujet))
    idees = explorer(ctx, nombre, resume_marche, resume_terrain)

    config.ensure_dirs()
    from .base import slug

    dossier = config.PRODUITS_DIR / "idees-{}".format(slug(ctx.sujet, 40))
    dossier.mkdir(parents=True, exist_ok=True)

    (dossier / "idees.json").write_text(
        json.dumps({"niche": ctx.sujet, "idees": idees, "marche": rapport_marche},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    chemin_csv = dossier / "idees.csv"
    with chemin_csv.open("w", encoding="utf-8", newline="") as flux:
        colonnes = list(idees[0].keys())
        auteur = csv.DictWriter(flux, fieldnames=colonnes)
        auteur.writeheader()
        auteur.writerows({c: tableur.cellule(i.get(c, "")) for c in colonnes}
                         for i in idees)

    lignes = ["# Idees de produits — {}\n".format(ctx.sujet)]
    if rapport_marche:
        lecture = rapport_marche["lecture"]
        lignes.append("\n## Ce que disent les donnees\n")
        lignes.append("*Mesure du {} — {}*\n".format(
            rapport_marche["date"], lecture["fiabilite"]))
        for signal in lecture["signaux"]:
            lignes.append("- " + signal)
        lignes.append("\n> {}\n".format(lecture["verdict"]))
    for index, idee in enumerate(idees, 1):
        lignes.append("\n## {}. {}\n".format(index, idee["titre"]))
        # La provenance du prix est affichee : « 19 EUR » sorti d'un modele
        # et « 19 EUR » constate sur douze ventes ne meritent pas la meme
        # confiance, et rien ne les distinguait.
        source = idee.get("prix_source", "modele")
        prix = "{} EUR".format(idee["prix_eur"])
        if source == "modele":
            prix += " *(estime, aucune vente pour l'etayer)*"
        else:
            prix += " *({}, fourchette {})*".format(
                source, idee.get("prix_fourchette", "-"))
        lignes.append("- **Type :** {} | **Prix cible :** {} | "
                      "**Difficulte :** {} | **Concurrence :** {}".format(
                          idee["type"], prix,
                          idee["difficulte"], idee["concurrence"]))
        lignes.append("- **Probleme :** {}".format(idee["probleme"]))
        lignes.append("- **Acheteur :** {}".format(idee["acheteur"]))
        lignes.append("- **Promesse :** {}".format(idee["promesse"]))
        lignes.append("- **Angle :** {}".format(idee["angle_differenciant"]))
        lignes.append("- **Premier canal :** {}".format(idee["premier_canal"]))
        lignes.append("\n```\nusine {} \"{}\"\n```".format(idee["type"], idee["titre"]))
    markdown = "\n".join(lignes)
    (dossier / "idees.md").write_text(markdown, encoding="utf-8")
    ecrire_page(dossier / "idees.html", "Idees de produits — {}".format(ctx.sujet),
                D.vers_html(D.analyser(markdown), niveau_depart=1),
                sous_titre="{} pistes evaluees".format(len(idees)), meta=ctx.auteur)

    return {"niche": ctx.sujet, "idees": idees, "dossier": str(dossier),
            "marche": rapport_marche.get("lecture", {})}
