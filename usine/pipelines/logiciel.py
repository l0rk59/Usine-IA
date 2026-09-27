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
from ..render import libelles, livraison
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
                "motif": execution.motif,
                "valeur": execution.valeur,
                "tests": chemin.startswith("test_"),
                "erreur": execution.erreur[:600],
                "sortie": execution.sortie[:600],
            })
            if execution.refus:
                ctx.journal("      {} : non exécuté ({})".format(
                    intitule, execution.refus[:60]))
            elif execution.reussi:
                ctx.journal("      {} : démarre correctement".format(intitule))
            else:
                ctx.journal("      {} : ÉCHEC — {}".format(
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

    ctx.journal("Étape 1/4 — spécification ({})...".format(fiche["nom"]))
    specification = _specification(ctx, cible)
    titre = specification["titre"]
    dossier = preparer(ctx, "logiciel", titre)
    ctx.etape("specification", "ok", cible)
    ctx.journal('  « {} » — {}'.format(titre, specification.get("promesse", "")))

    ctx.journal("Étape 2/4 — génération et vérification du code...")
    fichiers, rapports = _ecrire_et_verifier(ctx, specification, cible)
    synthese = verification.synthese(rapports)
    # Le verificateur a tourne : c'est une anomalie, pas une etape perdue. La
    # relancer ne regenererait pas le code — elle refait la meme verification
    # sur les memes fichiers.
    ctx.etape("code", "ok" if synthese["tout_valide"] else "anomalie",
              "{}/{} fichiers valides".format(synthese["valides"],
                                              synthese["fichiers"]))

    ctx.journal("Étape 3/4 — essai réel...")
    essais = _essai_reel(ctx, fichiers, rapports) if (
        executer and cible == "cli") else {"essais": [], "tout_demarre": None}

    ctx.journal("Étape 4/4 — mise en carton...")
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
    t = libelles.textes(ctx.langue_iso)
    blocs = [
        livraison.Bloc(t["logiciel_ce_que_fait"],
                       _markdown_presentation(specification, t)),
        livraison.Bloc(t["logiciel_installation"],
                       _markdown_installation(specification, cible, t)),
        livraison.Bloc(t["logiciel_verification"],
                       _markdown_verification(synthese, essais, t)),
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
        libelle_sections=t["unite_sections_simple"],
    )
    return livraison.livrer(ctx, produit)


def _markdown_presentation(specification: Dict[str, Any],
                           t: Dict[str, Any]) -> str:
    lignes = []
    if specification.get("probleme"):
        lignes.append(specification["probleme"] + "\n")
    if specification.get("fonctionnalites"):
        lignes.append("## {}\n".format(t["logiciel_fonctions"]))
        lignes += ["- " + f for f in specification["fonctionnalites"]]
    if specification.get("limites"):
        lignes.append("\n## {}\n".format(t["logiciel_limites"]))
        lignes += ["- " + l for l in specification["limites"]]
        lignes.append("\n" + t["logiciel_limites_pourquoi"])
    return "\n".join(lignes)


def _markdown_installation(specification: Dict[str, Any], cible: str,
                           t: Dict[str, Any]) -> str:
    if cible == "cli":
        return t["logiciel_cli"].format(
            utilisation=specification.get("utilisation", "python3 source/outil.py"))
    if cible == "web":
        return t["logiciel_web"]
    return t["logiciel_extension"]


def _refus_lisible(essai: Dict[str, Any], t: Dict[str, Any]) -> str:
    """Le refus d'executer, dans la langue du produit.

    L'entete (« analyse statique ») et le motif du souci se traduisent ; la
    valeur — un nom de module, le message de Python — reste telle quelle. Un
    motif inconnu garde son texte : mieux vaut un detail en francais qu'un
    detail perdu.
    """
    refus = essai["refus"]
    tete, separateur, reste = refus.partition(" : ")
    traduit = t["logiciel_refus"].get(tete)
    if not traduit or not separateur:
        return refus
    gabarit = t["logiciel_soucis"].get(essai.get("motif") or "")
    if gabarit:
        reste = gabarit.format(valeur=essai.get("valeur", ""))
    return t["deux_points"].format(libelle=traduit, texte=reste)


def _markdown_verification(synthese: Dict[str, Any],
                           essais: Dict[str, Any], t: Dict[str, Any]) -> str:
    lignes = [
        t["logiciel_verifie"],
        "| {} |".format(" | ".join(t["logiciel_colonnes"])),
        "| --- | --- | --- |",
    ]
    for detail in synthese["detail"]:
        etat = t["logiciel_correct"] if detail["valide"] else t["logiciel_a_corriger"]
        lignes.append("| `{}` | {} | {} |".format(
            detail["fichier"],
            t["logiciel_verifie_par"].get(detail["verifie_par"],
                                          detail["verifie_par"]), etat))

    for essai in essais.get("essais", []):
        if essai["refus"]:
            resultat = t["logiciel_non_execute"].format(
                refus=_refus_lisible(essai, t))
        elif essai["reussi"]:
            resultat = t["logiciel_demarre"]
        else:
            resultat = t["logiciel_echec"]
        quoi = (t["logiciel_tests_unitaires"] if essai.get("tests")
                else essai["quoi"])
        lignes.append("| `{}` | {} | {} |".format(
            quoi, t["logiciel_execution"], resultat))

    # Le fichier ou ces remarques sont detaillees reste a l'atelier : la
    # notice y renvoyait l'acheteur, qui ne l'a jamais recu.
    if synthese["avertissements"]:
        # Au moins une remarque ici : les deux langues accordent pareil.
        lignes.append("\n" + libelles.accorder(t["logiciel_remarques"].format(
            nombre=synthese["avertissements"])))
    if not synthese["tout_valide"]:
        lignes.append("\n" + t["logiciel_attention"])
    return "\n".join(lignes)
