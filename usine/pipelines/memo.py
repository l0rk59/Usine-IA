"""Memo : l'antiseche d'une ou deux pages, celle qu'on garde a cote de soi.

C'est l'inverse exact de l'ebook, et c'est pour cela qu'il fallait une chaine
separee plutot qu'une option. Un ebook se lit une fois ; un memo se consulte
vingt fois, debout, en cherchant une ligne precise. Tout ce qui fait un bon
livre — la progression, les transitions, les exemples deployes — fait un
mauvais memo.

Deux consequences dans le code :

  - le controle qualite de prose est coupe pour ce type (« prose=False » au
    catalogue). Il mesure le rythme des phrases et la diversite lexicale ;
    sur des lignes de trois mots il rend un chiffre qui n'a aucun sens, et un
    chiffre sans sens est pire que pas de chiffre parce qu'on le croit ;

  - la longueur est une CONTRAINTE, pas une consequence. Le nombre de blocs
    est demande au modele, puis verifie ici : un memo de neuf pages n'est
    plus un memo, c'est un ebook rate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import document as D
from ..render import livraison
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

# Au-dela, ce n'est plus une antiseche. La borne n'est pas decorative : elle
# est appliquee, et le journal le dit quand le modele deborde.
BLOCS_MAX = 14


def _structure(ctx: Contexte, nombre: int) -> List[Dict[str, Any]]:
    invite = (
        "Construis un memo de reference sur : {sujet}\n"
        "POUR : {audience}\n\n"
        "Un memo se consulte, il ne se lit pas : celui qui l'ouvre cherche "
        "UNE ligne precise, souvent en travaillant. Organise-le en {n} blocs "
        "courts, chacun repondant a une question qu'on se pose vraiment.\n\n"
        "Pour chaque bloc :\n"
        "- 'titre' : 2 a 5 mots, ce qu'on cherche.\n"
        "- 'genre' : 'liste' pour des points a retenir, 'etapes' pour une "
        "marche a suivre numerotee, 'tableau' pour une comparaison, "
        "'reperes' pour des chiffres ou des seuils.\n"
        "- 'lignes' : 3 a 7 entrees, une ligne chacune, 12 mots maximum. "
        "Pas de phrase complete, pas de transition.\n\n"
        "Schema JSON exact :\n"
        '{{"blocs": [{{"titre": "...", "genre": "liste|etapes|tableau|reperes", '
        '"lignes": ["...", "..."]}}]}}'
    ).format(sujet=ctx.sujet, audience=ctx.audience, n=nombre)
    donnees = equipe.BIBLIOTHECAIRE.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.6, max_tokens=2200)
    blocs = donnees.get("blocs") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for bloc in blocs or []:
        if not isinstance(bloc, dict):
            continue
        lignes = [str(l).strip() for l in (bloc.get("lignes") or []) if str(l).strip()]
        if not lignes:
            continue
        genre = str(bloc.get("genre") or "liste").strip().lower()
        propres.append({
            "titre": nettoyer_titre(str(bloc.get("titre") or "Reperes")),
            "genre": genre if genre in ("liste", "etapes", "tableau", "reperes")
                     else "liste",
            "lignes": lignes,
        })
    if not propres:
        raise ValueError("Aucun bloc exploitable")
    return propres


def produire(ctx: Contexte, nombre: int = 8,
             recto_verso: bool = False) -> Dict[str, Any]:
    nombre = max(3, min(int(nombre or 8), BLOCS_MAX))
    titre = "Memo — {}".format(ctx.sujet)
    dossier = preparer(ctx, "memo", titre)

    ctx.journal("Etape 1/2 — structure du memo...")
    blocs = _structure(ctx, nombre)
    # Le modele deborde volontiers : on tranche ici, et on le DIT. Livrer
    # dix-neuf blocs sous le nom de « memo » serait tenir une promesse pour
    # une autre.
    if len(blocs) > BLOCS_MAX:
        ctx.journal("  {} blocs proposes, {} gardes : au-dela ce n'est plus "
                    "un memo.".format(len(blocs), BLOCS_MAX))
        blocs = blocs[:BLOCS_MAX]
    ctx.etape("structure", "ok", "{} blocs".format(len(blocs)))

    ctx.journal("Etape 2/2 — export...")
    fichiers = _exporter(ctx, titre, blocs, recto_verso)
    entrees = sum(len(b["lignes"]) for b in blocs)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "blocs": len(blocs),
        "entrees": entrees,
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"blocs": len(blocs), "entrees": entrees})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _exporter(ctx: Contexte, titre: str, blocs: List[Dict[str, Any]],
              recto_verso: bool) -> List[Path]:
    # « sur une page » etait imprime sur la couverture d'un PDF de six pages.
    # Une promesse qu'on lit avant d'ouvrir le fichier, et que le fichier ne
    # tient pas, coute plus qu'elle ne rapporte : on annonce ce qu'il y a.
    lignes = sum(len(b["lignes"]) for b in blocs)
    sous_titre = "{} repere(s) en {} bloc(s)".format(lignes, len(blocs))
    sections = [livraison.Bloc(
        titre=bloc["titre"],
        corps=_markdown_bloc(bloc),
        rendu_pdf=_mise_en_page(bloc, premier=(rang == 0)),
        rendu_html=_html_bloc(bloc),
        # Le titre est compose par « _mise_en_page » : sans cela, chaque
        # bloc ouvrait sa propre page. Rien a declarer cote sommaire ici —
        # « titre_pdf=False » fait que le moteur n'inscrit aucune entree.
        titre_pdf=False,
    ) for rang, bloc in enumerate(blocs)]

    produit = livraison.Produit(
        type="memo", titre=titre, sous_titre=sous_titre,
        # Rien a declarer cote sommaire : « titre_pdf=False » sur les blocs
        # fait qu'aucune entree n'est inscrite, donc la page de sommaire ne
        # sort pas. Poser en plus « sommaire=False » ici serait un drapeau qui
        # ne garde rien — une campagne de mutation l'a montre, le retirer ne
        # faisait echouer aucun test.
        promesse="L'essentiel, a garder a cote de soi", blocs=sections,
        tableaux=[livraison.Tableau(
            nom="memo", colonnes=["Bloc", "Genre", "Ligne"],
            lignes=[[bloc["titre"], bloc["genre"], ligne]
                    for bloc in blocs for ligne in bloc["lignes"]])],
        donnees={"titre": titre, "blocs": blocs},
        nom_donnees="memo",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        # Un memo se lit a plat sur un bureau : les marges d'un livre y
        # gaspillent le quart de la page utile.
        marge=34.0,
        # Recto-verso : une marge de reliure n'a de sens que si les deux
        # faces sont imprimees, sinon elle decale le texte pour rien.
        reliure=10.0 if recto_verso else 0.0,
        style_couverture="reference card, minimal grid, high contrast",
        nom_fichier=slug(titre, 48),
    )
    return livraison.livrer(ctx, produit)


def _markdown_bloc(bloc: Dict[str, Any]) -> str:
    if bloc["genre"] == "etapes":
        return "\n".join("{}. {}".format(i, l)
                         for i, l in enumerate(bloc["lignes"], 1))
    return "\n".join("- {}".format(l) for l in bloc["lignes"])


def _mise_en_page(bloc: Dict[str, Any], premier: bool = False):
    """Un bloc de memo, qui ENCHAINE au lieu d'ouvrir une page.

    Le moteur commun ecrit le titre d'un bloc en corps de chapitre, et un
    titre de niveau 1 ouvre une nouvelle page. Quatre blocs faisaient donc
    quatre pages, plus la couverture, plus un sommaire : six pages pour une
    antiseche, alors que ce module dit en tete « l'antiseche d'une ou deux
    pages » et « un memo de neuf pages n'est plus un memo, c'est un ebook
    rate ». Le code faisait exactement ce que sa docstring interdisait.

    Un memo se lit a plat, d'un coup d'oeil : ses blocs se suivent.

    « premier » n'est pas un detail. La premiere version supprimait TOUS les
    sauts de page, et le memo tombait a une seule page — le compte exact que
    la docstring reclame. Il a fallu ouvrir le PDF pour voir que le contenu
    s'imprimait PAR-DESSUS la couverture, texte sombre sur fond sombre. Le
    seul saut qui compte est celui-la.
    """

    def rendre(doc) -> None:
        if premier:
            doc.nouvelle_page()
        # Niveau 2 : lisible comme un intitule, sans ouvrir de page.
        doc.titre(bloc["titre"], 2, sommaire=False)
        if bloc["genre"] == "etapes":
            for index, ligne in enumerate(bloc["lignes"], 1):
                doc.paragraphe("{}. {}".format(index, ligne), taille=10)
        elif bloc["genre"] == "reperes":
            # Des chiffres se lisent en colonne, pas en paragraphe.
            for ligne in bloc["lignes"]:
                doc.paragraphe("  " + ligne, taille=10,
                               police="Helvetica-Bold")
        else:
            doc.liste(bloc["lignes"])

    return rendre


def _html_bloc(bloc: Dict[str, Any]) -> str:
    balise = "ol" if bloc["genre"] == "etapes" else "ul"
    entrees = "".join("<li>{}</li>".format(D.inline_html(l))
                      for l in bloc["lignes"])
    return "<{0}>{1}</{0}>".format(balise, entrees)
