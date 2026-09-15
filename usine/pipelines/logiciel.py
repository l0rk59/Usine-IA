"""Chaine de production d'un produit logiciel.

Trois cibles, un meme enchainement : specification, generation fichier par
fichier, VERIFICATION, reparation si necessaire, mise en carton.

  cli        un outil en ligne de commande Python, un seul fichier, stdlib
  web        une application HTML autonome, qui marche hors ligne
  extension  une extension Chrome au format Manifest V3

Ce qui distingue cette chaine des autres : rien n'est livre sans avoir ete
verifie. Un modele produit du code plausible, pas du code correct. Chaque
fichier passe par un analyseur, et quand il est casse, l'erreur exacte est
renvoyee au modele pour correction. Les outils en ligne de commande sont en
plus reellement executes — dans un dossier temporaire, avec une limite de
temps, et seulement si l'analyse statique ne trouve rien de dangereux.

Le contrat annonce a l'acheteur est donc verifiable : ce qui est livre demarre.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..agents import equipe
from ..core import evenements, verification
from ..render import livraison
from .base import Contexte, elaguer_markdown, nettoyer_titre, preparer, slug, terminer

CIBLES = {
    "cli": {
        "nom": "outil en ligne de commande",
        "contrainte": (
            "Python 3.8+, bibliotheque standard UNIQUEMENT — aucun pip install. "
            "Un seul fichier executable, plus un fichier de tests. Interface via "
            "argparse, avec --help utile. Aucun acces reseau, aucun appel "
            "systeme, aucune ecriture en dehors du dossier courant."),
        "fichiers": [("outil.py", "le programme complet, executable"),
                     ("test_outil.py", "tests unittest, executables sans reseau")],
        "verifier": "python",
    },
    "web": {
        "nom": "application web autonome",
        "contrainte": (
            "UN SEUL fichier HTML contenant le CSS et le JavaScript en ligne. "
            "Aucune dependance externe, aucun CDN : le fichier doit fonctionner "
            "en double-cliquant dessus, hors connexion. JavaScript moderne sans "
            "transpilation. Interface utilisable sur telephone."),
        "fichiers": [("index.html", "l'application entiere, autonome")],
        "verifier": "html",
    },
    "extension": {
        "nom": "extension Chrome",
        "contrainte": (
            "Manifest V3. Permissions minimales : demander « tabs » ou "
            "« <all_urls> » quand « activeTab » suffit fait rejeter l'extension "
            "et inquiete l'utilisateur. Aucune dependance externe."),
        "fichiers": [("manifest.json", "manifeste Chrome MV3"),
                     ("popup.html", "interface de la fenetre"),
                     ("popup.js", "logique de la fenetre"),
                     ("contenu.js", "script injecte dans la page")],
        "verifier": "mixte",
    },
}

ROLE = ("un developpeur qui livre des outils petits, sans dependances et qui "
        "demarrent du premier coup")


def _specification(ctx: Contexte, cible: str) -> Dict[str, Any]:
    fiche = CIBLES[cible]
    invite = (
        "Concois un {type} vendable sur ce sujet : {sujet}\n"
        "UTILISATEUR : {audience}\n\n"
        "CONTRAINTES TECHNIQUES IMPERATIVES :\n{contrainte}\n\n"
        "L'outil doit resoudre UN probleme precis et le resoudre entierement. "
        "Un outil qui fait une chose bien se vend ; un outil qui en fait dix a "
        "moitie ne se vend pas.\n\n"
        "Schema JSON exact :\n"
        '{{"nom": "nom court du produit", "titre": "titre commercial", '
        '"promesse": "ce que l\'utilisateur obtient, en une phrase", '
        '"probleme": "la situation precise que cela resout", '
        '"fonctionnalites": ["3 a 6 fonctions, formulees a l\'infinitif"], '
        '"utilisation": "la commande ou le geste type, en une ligne", '
        '"limites": ["2 a 3 choses que l\'outil ne fait PAS"]}}'
    ).format(type=fiche["nom"], sujet=ctx.sujet, audience=ctx.audience,
             contrainte=fiche["contrainte"])

    specification = equipe.ARCHITECTE.travailler_json(ctx, invite, max_tokens=2000)
    if not isinstance(specification, dict) or not specification.get("titre"):
        raise ValueError("specification logicielle invalide")
    specification["titre"] = nettoyer_titre(str(specification["titre"]))
    specification["nom"] = slug(str(specification.get("nom") or
                                    specification["titre"]), 30)
    for cle in ("fonctionnalites", "limites"):
        valeurs = specification.get(cle) or []
        specification[cle] = [str(v).strip() for v in valeurs if str(v).strip()]
    return specification


def _generer_fichier(ctx: Contexte, specification: Dict[str, Any], cible: str,
                     chemin: str, role: str,
                     deja: Dict[str, str]) -> str:
    """Produit un fichier. Les fichiers deja ecrits sont donnes en contexte."""
    fiche = CIBLES[cible]
    contexte_existant = ""
    if deja:
        contexte_existant = "\n\nFICHIERS DEJA ECRITS, avec lesquels celui-ci doit " \
                            "etre coherent :\n" + "\n".join(
            "--- {} ---\n{}".format(nom, contenu[:2500])
            for nom, contenu in deja.items())

    invite = (
        "PRODUIT : {titre}\nPROMESSE : {promesse}\n"
        "FONCTIONS : {fonctions}\nNE FAIT PAS : {limites}\n\n"
        "CONTRAINTES TECHNIQUES IMPERATIVES :\n{contrainte}\n"
        "{existant}\n\n"
        "Ecris le fichier « {chemin} » : {role}.\n\n"
        "Le code doit fonctionner du premier coup. Pas de « TODO », pas de "
        "fonction laissee vide, pas de dependance a installer. Commente ce qui "
        "n'est pas evident, pas ce qui l'est.\n\n"
        "Reponds UNIQUEMENT avec le contenu du fichier, sans explication avant "
        "ni apres, sans bloc de code markdown."
    ).format(titre=specification["titre"], promesse=specification.get("promesse", ""),
             fonctions=" ; ".join(specification.get("fonctionnalites", [])),
             limites=" ; ".join(specification.get("limites", [])) or "non precise",
             contrainte=fiche["contrainte"], existant=contexte_existant,
             chemin=chemin, role=role)

    # Role « code » : ce texte-la doit compiler, pas se lire agreablement.
    # Chez NVIDIA, cela envoie sur Codestral plutot que sur un modele de
    # redaction ; chez un fournisseur qui n'a rien de tel, « model_for »
    # retombe sur « standard » et rien ne change.
    reponse = equipe.REDACTEUR.travailler(ctx, invite, max_tokens=4096,
                                          temperature=0.35,
                                          role_modele="code")
    return _nettoyer_code(reponse.texte)


def _nettoyer_code(texte: str) -> str:
    """Retire les clotures markdown que les modeles ajoutent malgre la consigne."""
    propre = elaguer_markdown(texte)
    lignes = propre.split("\n")
    if lignes and lignes[0].strip().startswith("```"):
        lignes.pop(0)
    if lignes and lignes[-1].strip() == "```":
        lignes.pop()
    return "\n".join(lignes).strip() + "\n"


def _reparer(ctx: Contexte, chemin: str, contenu: str,
             rapport: verification.Rapport) -> str:
    """Renvoie l'erreur exacte au modele pour qu'il corrige."""
    invite = (
        "Ce fichier ne passe pas la verification.\n\n"
        "FICHIER : {chemin}\n\n"
        "--- CONTENU ACTUEL ---\n{contenu}\n--- FIN ---\n\n"
        "PROBLEMES RELEVES :\n{problemes}\n\n"
        "Corrige uniquement ces problemes. Renvoie le fichier COMPLET corrige, "
        "sans explication, sans bloc de code markdown."
    ).format(chemin=chemin, contenu=contenu[:12000],
             problemes=rapport.instructions_correction())
    reponse = equipe.REVISEUR.travailler(ctx, invite, max_tokens=4096,
                                         temperature=0.25)
    return _nettoyer_code(reponse.texte)


def _ecrire_et_verifier(ctx: Contexte, specification: Dict[str, Any], cible: str,
                        tentatives: int = 2) -> Tuple[Dict[str, str],
                                                      List[verification.Rapport]]:
    """Genere chaque fichier, le verifie, le fait corriger si besoin."""
    fichiers: Dict[str, str] = {}
    rapports: List[verification.Rapport] = []

    for index, (chemin, role) in enumerate(CIBLES[cible]["fichiers"], 1):
        ctx.journal("  [{}/{}] {}".format(index, len(CIBLES[cible]["fichiers"]),
                                          chemin))
        evenements.publier("section", etape="code", index=index,
                           total=len(CIBLES[cible]["fichiers"]), titre=chemin)
        contenu = _generer_fichier(ctx, specification, cible, chemin, role, fichiers)

        rapport = verification.analyser_fichier(chemin, contenu)
        for tour in range(tentatives - 1):
            if rapport.valide:
                break
            ctx.journal("      {} — correction {}/{}".format(
                rapport.casse[0].message[:52], tour + 1, tentatives - 1))
            contenu = _reparer(ctx, chemin, contenu, rapport)
            rapport = verification.analyser_fichier(chemin, contenu)

        ctx.journal("      " + rapport.resume())
        fichiers[chemin] = contenu
        rapports.append(rapport)
    return fichiers, rapports


def _essai_reel(ctx: Contexte, fichiers: Dict[str, str],
                rapports: List[verification.Rapport]) -> Dict[str, Any]:
    """Execute reellement l'outil, dans un dossier temporaire.

    C'est la seule preuve qui compte : « le fichier compile » ne dit pas qu'il
    demarre. On lance --help puis la suite de tests generee.
    """
    par_nom = {r.fichier: r for r in rapports}
    essais: List[Dict[str, Any]] = []
    bac = Path(tempfile.mkdtemp(prefix="usine-essai-"))
    try:
        for chemin, contenu in fichiers.items():
            (bac / chemin).parent.mkdir(parents=True, exist_ok=True)
            (bac / chemin).write_text(contenu, encoding="utf-8")

        for chemin in fichiers:
            if not chemin.endswith(".py"):
                continue
            rapport = par_nom.get(Path(chemin).name)
            if chemin.startswith("test_"):
                execution = verification.executer_python(
                    bac / chemin, ["-v"], rapport, secondes=30)
                intitule = "tests unitaires"
            else:
                execution = verification.executer_python(
                    bac / chemin, ["--help"], rapport, secondes=15)
                intitule = "{} --help".format(chemin)
            essais.append({
                "quoi": intitule,
                "lance": execution.lance,
                "reussi": execution.reussi,
                "code_retour": execution.code_retour,
                "refus": execution.refus,
                "erreur": execution.erreur[:600],
                "sortie": execution.sortie[:600],
            })
            if execution.refus:
                ctx.journal("      {} : non execute ({})".format(
                    intitule, execution.refus[:60]))
            elif execution.reussi:
                ctx.journal("      {} : demarre correctement".format(intitule))
            else:
                ctx.journal("      {} : ECHEC — {}".format(
                    intitule, (execution.erreur or "code {}".format(
                        execution.code_retour))[:70]))
    finally:
        shutil.rmtree(bac, ignore_errors=True)
    return {"essais": essais,
            "tout_demarre": all(e["reussi"] for e in essais) if essais else None}


def produire(ctx: Contexte, cible: str = "cli",
             executer: bool = True) -> Dict[str, Any]:
    cible = cible if cible in CIBLES else "cli"
    fiche = CIBLES[cible]

    ctx.journal("Etape 1/4 — specification ({})...".format(fiche["nom"]))
    specification = _specification(ctx, cible)
    titre = specification["titre"]
    dossier = preparer(ctx, "logiciel", titre)
    ctx.etape("specification", "ok", cible)
    ctx.journal('  « {} » — {}'.format(titre, specification.get("promesse", "")))

    ctx.journal("Etape 2/4 — generation et verification du code...")
    fichiers, rapports = _ecrire_et_verifier(ctx, specification, cible)
    synthese = verification.synthese(rapports)
    # Le verificateur a tourne : c'est une anomalie, pas une etape perdue. La
    # relancer ne regenererait pas le code — elle refait la meme verification
    # sur les memes fichiers.
    ctx.etape("code", "ok" if synthese["tout_valide"] else "anomalie",
              "{}/{} fichiers valides".format(synthese["valides"],
                                              synthese["fichiers"]))

    ctx.journal("Etape 3/4 — essai reel...")
    essais = _essai_reel(ctx, fichiers, rapports) if (
        executer and cible == "cli") else {"essais": [], "tout_demarre": None}

    ctx.journal("Etape 4/4 — mise en carton...")
    chemins = _ecrire_sources(dossier, fichiers)
    livrables = _livrer(ctx, specification, cible, fichiers, synthese, essais)

    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "cible": cible,
        "fichiers_code": len(fichiers),
        "code_valide": synthese["tout_valide"],
        "demarre": essais["tout_demarre"],
        "fichiers": [f.name for f in chemins + livrables],
    }
    (dossier / "verification.json").write_text(
        json.dumps({"specification": specification, "verification": synthese,
                    "essais": essais}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    terminer(ctx, chemins + livrables, {
        "cible": cible, "fichiers_code": len(fichiers),
        "code_valide": synthese["tout_valide"],
        "defauts": synthese["casses"] + synthese["a_relire"],
    }, type_produit="logiciel")
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _ecrire_sources(dossier: Path, fichiers: Dict[str, str]) -> List[Path]:
    cible = dossier / "source"
    cible.mkdir(parents=True, exist_ok=True)
    chemins = []
    for chemin, contenu in fichiers.items():
        fichier = cible / chemin
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(contenu, encoding="utf-8")
        chemins.append(fichier)
    return chemins


def _livrer(ctx: Contexte, specification: Dict[str, Any], cible: str,
            fichiers: Dict[str, str], synthese: Dict[str, Any],
            essais: Dict[str, Any]) -> List[Path]:
    """Documentation du produit, via l'assemblage commun."""
    fiche = CIBLES[cible]
    blocs = [
        livraison.Bloc("Ce que fait cet outil", _markdown_presentation(specification)),
        livraison.Bloc("Installation et utilisation",
                       _markdown_installation(specification, cible)),
        livraison.Bloc("Verification du code", _markdown_verification(synthese, essais)),
    ]
    produit = livraison.Produit(
        type="logiciel", titre=specification["titre"],
        # Une notice d'outil se lit a l'ecran, comme un fichier « LISEZ-MOI » :
        # ses trois sections s'enchainent. Chacune sur sa page donnait cinq
        # pages dont trois aux deux tiers blanches, et un sommaire de trois
        # entrees par-dessus.
        sections_enchainees=True, sommaire=False,
        sous_titre=specification.get("promesse", ""),
        promesse=specification.get("promesse", ""),
        blocs=blocs,
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture="developer tool cover, technical, monospace aesthetic",
        nom_fichier=specification["nom"],
        libelle_sections="sections",
    )
    return livraison.livrer(ctx, produit)


def _markdown_presentation(specification: Dict[str, Any]) -> str:
    lignes = []
    if specification.get("probleme"):
        lignes.append(specification["probleme"] + "\n")
    if specification.get("fonctionnalites"):
        lignes.append("## Fonctions\n")
        lignes += ["- " + f for f in specification["fonctionnalites"]]
    if specification.get("limites"):
        lignes.append("\n## Ce que cet outil ne fait pas\n")
        lignes += ["- " + l for l in specification["limites"]]
        lignes.append("\nLe dire evite les deceptions, et les demandes de "
                      "remboursement qui vont avec.")
    return "\n".join(lignes)


def _markdown_installation(specification: Dict[str, Any], cible: str) -> str:
    if cible == "cli":
        return (
            "Aucune installation : le script n'utilise que la bibliotheque "
            "standard de Python.\n\n"
            "```\npython3 source/outil.py --help\n```\n\n"
            "Utilisation type :\n\n```\n{}\n```\n\n"
            "Les tests se lancent avec :\n\n```\npython3 source/test_outil.py\n```"
        ).format(specification.get("utilisation", "python3 source/outil.py"))
    if cible == "web":
        return (
            "Ouvrez `source/index.html` dans n'importe quel navigateur. Il n'y a "
            "rien a installer et rien a configurer : tout le code est dans ce "
            "fichier, il fonctionne hors connexion.\n\n"
            "Pour le mettre en ligne, deposez ce seul fichier chez n'importe quel "
            "hebergeur statique."
        )
    return (
        "1. Ouvrez `chrome://extensions` dans Chrome.\n"
        "2. Activez le « mode developpeur » en haut a droite.\n"
        "3. Cliquez sur « Charger l'extension non empaquetee ».\n"
        "4. Choisissez le dossier `source/`.\n\n"
        "Pour la publier, compressez le dossier `source/` et deposez l'archive "
        "sur le Chrome Web Store."
    )


def _markdown_verification(synthese: Dict[str, Any],
                           essais: Dict[str, Any]) -> str:
    lignes = [
        "Ce code a ete verifie avant livraison. Voici exactement ce qui a ete "
        "controle.\n",
        "| Fichier | Verification | Resultat |",
        "| --- | --- | --- |",
    ]
    for detail in synthese["detail"]:
        etat = "correct" if detail["valide"] else "**a corriger**"
        lignes.append("| `{}` | {} | {} |".format(
            detail["fichier"], detail["verifie_par"], etat))

    for essai in essais.get("essais", []):
        if essai["refus"]:
            resultat = "non execute : {}".format(essai["refus"])
        elif essai["reussi"]:
            resultat = "demarre correctement"
        else:
            resultat = "**echec**"
        lignes.append("| `{}` | execution reelle | {} |".format(
            essai["quoi"], resultat))

    if synthese["avertissements"]:
        lignes.append("\n{} remarque(s) sans gravite figurent dans "
                      "`verification.json`.".format(synthese["avertissements"]))
    if not synthese["tout_valide"]:
        lignes.append("\n**Attention :** un ou plusieurs fichiers n'ont pas passe "
                      "la verification. Relisez-les avant toute mise en vente.")
    return "\n".join(lignes)
