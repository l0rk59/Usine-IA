"""Menu interactif pour Termux.

Taper « usine ebook "..." --marketing --zip -T long » au clavier d'un telephone
est penible. Ce menu pose les questions une par une, se souvient des reglages
et n'attend que des chiffres.

Volontairement sans curses : sur Termux, curses se comporte mal selon le
clavier virtuel utilise. Ici, tout passe par input() et des numeros.
"""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__
from .core import cles as pool_cles
from .core import config, llm, reglages, securite, store
from .pipelines.base import TAILLES, TONS

_COULEUR = sys.stdout.isatty()


def c(texte: str, code: str) -> str:
    return "\033[{}m{}\033[0m" .format(code, texte) if _COULEUR else texte


def effacer() -> None:
    if _COULEUR:
        print("\033[2J\033[H", end="")


def entete(titre: str) -> None:
    largeur = 46
    print()
    print(c("  " + "-" * largeur, "36"))
    print(c("  " + titre.center(largeur), "1;36"))
    print(c("  " + "-" * largeur, "36"))
    print()


def demander(question: str, defaut: str = "", obligatoire: bool = False) -> str:
    indice = " [{}]".format(defaut) if defaut else ""
    while True:
        try:
            reponse = input("  {}{} : ".format(question, indice)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return defaut
        if reponse:
            return reponse
        if defaut:
            return defaut
        if not obligatoire:
            return ""
        print(c("     Cette information est necessaire.", "33"))


def demander_oui(question: str, defaut: bool = True) -> bool:
    indice = "O/n" if defaut else "o/N"
    reponse = demander("{} ({})".format(question, indice)).lower()
    if not reponse:
        return defaut
    return reponse[0] in ("o", "y", "1")


def choisir(titre: str, options: List[Tuple[str, str]],
            defaut: int = 1, retour: str = "Retour") -> int:
    """Affiche une liste numerotee. Renvoie l'index (1..n), ou 0 pour revenir."""
    print()
    print(c("  " + titre, "1"))
    print()
    for numero, (libelle, detail) in enumerate(options, 1):
        marque = c("{:>2}".format(numero), "1;36")
        print("  {}. {}".format(marque, libelle))
        if detail:
            print("      {}".format(c(detail, "2")))
    print()
    print("  {}. {}".format(c(" 0", "2"), retour))
    print()
    while True:
        brut = demander("Votre choix", str(defaut) if defaut else "")
        if brut in ("q", "Q"):
            return 0
        try:
            valeur = int(brut)
        except ValueError:
            print(c("     Entrez un numero.", "33"))
            continue
        if 0 <= valeur <= len(options):
            return valeur
        print(c("     Numero hors liste.", "33"))


# --------------------------------------------------------------------------
# Catalogue des produits fabricables
# --------------------------------------------------------------------------

PRODUITS: List[Dict[str, Any]] = [
    {"cle": "ebook", "nom": "Ebook complet",
     "detail": "PDF + EPUB + HTML + couverture — 10 a 25 min",
     "quantite": None},
    {"cle": "prompts", "nom": "Pack de prompts",
     "detail": "PDF + CSV importable dans Notion — 5 a 12 min",
     "quantite": ("Combien de prompts", "50")},
    {"cle": "formation", "nom": "Mini-formation",
     "detail": "Manuel + cahier d'exercices + sequence e-mail — 12 a 25 min",
     "quantite": ("Combien de modules", "6")},
    {"cle": "outils", "nom": "Boite a outils",
     "detail": "Checklists, modeles et tableaux — 6 a 14 min",
     "quantite": ("Combien d'outils", "10")},
    {"cle": "modeles", "nom": "Modeles Notion / tableur",
     "detail": "Bases liees + CSV a importer — 5 a 12 min",
     "quantite": ("Combien de bases", "4")},
    {"cle": "impression", "nom": "Cahier imprimable",
     "detail": "Plannings et fiches, formats A4 et Lettre US — 5 a 12 min",
     "quantite": ("Combien de fiches", "12")},
    {"cle": "social", "nom": "Pack de publications",
     "detail": "Calendrier editorial + posts rediges — 5 a 15 min",
     "quantite": ("Combien de publications", "30")},
    {"cle": "idees", "nom": "Etude de niche",
     "detail": "Idees chiffrees : prix, difficulte, concurrence — 2 a 4 min",
     "quantite": ("Combien d'idees", "12")},
    {"cle": "complet", "nom": "Offre complete",
     "detail": "Ebook + 2 bonus + kit de vente + archive — 25 a 45 min",
     "quantite": None},
]


def menu_fabriquer(executer: Callable[[List[str]], int]) -> None:
    choix = choisir(
        "Que voulez-vous fabriquer ?",
        [(p["nom"], p["detail"]) for p in PRODUITS],
        defaut=1,
    )
    if choix == 0:
        return
    produit = PRODUITS[choix - 1]
    valeurs = reglages.charger()

    entete(produit["nom"])
    sujet = demander("Sujet du produit", obligatoire=True)
    if not sujet:
        return

    alertes = securite.analyser_sujet(sujet)
    for domaine, avertissement in alertes:
        print()
        print(c("  [!] Domaine sensible : {}".format(domaine), "33"))
        print("      " + avertissement)
    if alertes and not demander_oui("\n  Continuer malgre tout ?", True):
        return

    audience = demander("Pour qui", valeurs["audience"])
    arguments: List[str] = [produit["cle"], sujet, "-a", audience]

    if produit["quantite"]:
        question, defaut = produit["quantite"]
        quantite = demander(question, defaut)
        if quantite.isdigit():
            arguments += (["-m", quantite] if produit["cle"] == "formation"
                          else ["-n", quantite])

    if demander_oui("Personnaliser le ton, le volume et la qualite ?", False):
        tons = sorted(TONS)
        index = choisir("Ton de redaction",
                        [(t, TONS[t]) for t in tons],
                        defaut=tons.index(valeurs["ton"]) + 1)
        if index:
            arguments += ["-t", tons[index - 1]]

        tailles = sorted(TAILLES, key=lambda t: TAILLES[t][0])
        index = choisir("Volume",
                        [(t, "{} sections d'environ {} mots".format(*TAILLES[t]))
                         for t in tailles],
                        defaut=tailles.index(valeurs["taille"]) + 1)
        if index:
            arguments += ["-T", tailles[index - 1]]

        qualites = ["rapide", "standard", "exigeant"]
        index = choisir("Niveau de qualite", [
            ("rapide", "aucune relecture — le plus rapide et le plus econome"),
            ("standard", "1 relecture editoriale par section"),
            ("exigeant", "2 relectures — le meilleur resultat, 2 a 3 fois plus long"),
        ], defaut=qualites.index(valeurs["qualite"]) + 1)
        if index:
            arguments += ["--qualite", qualites[index - 1]]
    else:
        arguments += ["-t", valeurs["ton"], "-T", valeurs["taille"],
                      "--qualite", valeurs["qualite"]]

    if produit["cle"] != "complet":
        if demander_oui("Generer aussi le kit de vente ?", True):
            arguments.append("--marketing")
        if demander_oui("Produire l'archive ZIP livrable ?", True):
            arguments.append("--zip")
    if not valeurs["images"] or not demander_oui("Generer les images ?",
                                                 bool(valeurs["images"])):
        arguments.append("--sans-image")

    if valeurs["auteur"]:
        arguments += ["--auteur", valeurs["auteur"]]
    if valeurs["contact"]:
        arguments += ["--contact", valeurs["contact"]]

    entete("Recapitulatif")
    print("  Produit  : " + c(produit["nom"], "1"))
    print("  Sujet    : " + sujet)
    print("  Audience : " + audience)
    print("  Commande : " + c("usine " + " ".join(
        a if " " not in a else '"{}"'.format(a) for a in arguments), "2"))
    print()
    if not demander_oui("Lancer la fabrication ?", True):
        return

    print()
    executer(arguments)
    print()
    demander("Appuyez sur Entree pour revenir au menu")


def menu_produits(executer: Callable[[List[str]], int]) -> None:
    produits = [p for p in store.lister_produits(20)
                if p["statut"] != "bonus_integre"]
    if not produits:
        entete("Mes produits")
        print("  Aucun produit pour l'instant.")
        demander("\n  Appuyez sur Entree")
        return
    options = [
        ("{} — {}".format(p["titre"][:40], p["type"]),
         "{} · {}".format(p["statut"], p["id"][-15:]))
        for p in produits
    ]
    index = choisir("Mes produits", options, defaut=0)
    if index == 0:
        return
    produit = produits[index - 1]
    action = choisir("« {} »".format(produit["titre"][:38]), [
        ("Voir le detail", "fichiers et etapes de fabrication"),
        ("Generer le kit de vente", "fiche, page de vente, sequence"),
        ("Creer l'archive ZIP", "fichier livrable pour la boutique"),
    ])
    if action == 1:
        entete(produit["titre"][:44])
        from pathlib import Path

        dossier = Path(produit["dossier"])
        if dossier.exists():
            for fichier in sorted(dossier.rglob("*")):
                if fichier.is_file():
                    print("  {:<46} {:>7} Ko".format(
                        str(fichier.relative_to(dossier))[:46],
                        fichier.stat().st_size // 1024))
        print()
        for etape in store.etapes_produit(produit["id"])[-12:]:
            marque = c("v", "32") if etape["statut"] == "ok" else c("x", "31")
            print("  {} {} {}".format(marque, etape["nom"], etape["detail"][:40]))
        demander("\n  Appuyez sur Entree")
    elif action == 2:
        executer(["marketing", produit["id"]])
        demander("\n  Appuyez sur Entree")
    elif action == 3:
        executer(["livrer", produit["id"]])
        demander("\n  Appuyez sur Entree")


def menu_reglages() -> None:
    while True:
        entete("Reglages")
        lignes = reglages.lignes_affichables()
        for numero, ligne in enumerate(lignes, 1):
            print("  {:>2}. {:<14} {}".format(
                numero, ligne["nom"], c(ligne["valeur"][:28], "1")))
            print("      " + c(ligne["description"][:58], "2"))
        print()
        print("  {}. Tout reinitialiser".format(c("99", "33")))
        print("  {}. Retour".format(c(" 0", "2")))
        print()
        brut = demander("Numero a modifier")
        if not brut or brut == "0":
            return
        if brut == "99":
            if demander_oui("Effacer tous les reglages ?", False):
                reglages.reinitialiser()
            continue
        if not brut.isdigit() or not 1 <= int(brut) <= len(lignes):
            continue
        ligne = lignes[int(brut) - 1]
        actuelle = reglages.lire(ligne["nom"])
        print()
        print("  " + c(ligne["description"], "2"))
        if isinstance(reglages.DEFAUTS[ligne["nom"]], bool):
            nouvelle = demander_oui("Activer « {} »".format(ligne["nom"]),
                                    bool(actuelle))
        else:
            nouvelle = demander("Nouvelle valeur", str(actuelle))
        reglages.ecrire({ligne["nom"]: nouvelle})
        print(c("  Enregistre.", "32"))


def menu_cles() -> None:
    entete("Cles et quotas")
    lignes = llm.diagnostic()
    for ligne in lignes:
        if ligne["local"]:
            etat, couleur = "local", "33"
        elif ligne["sans_cle"]:
            etat, couleur = "sans cle", "36"
        elif ligne["disponible"]:
            etat, couleur = "{} cle(s)".format(ligne["nb_cles"]), "32"
        else:
            etat, couleur = "absente", "90"
        print("  {:<13} {:<11} {:>4}/{:<6} {}".format(
            ligne["nom"], c(etat, couleur), ligne["aujourdhui"], ligne["rpd"],
            c(ligne["modele"][:24], "2")))

    details = pool_cles.resume()
    if details:
        print()
        print(c("  Detail du pool (rotation automatique)", "1"))
        for detail in details:
            statut = (c("disponible", "32") if detail["disponible"]
                      else c("repos {}s".format(detail["repos_restant"]), "33"))
            print("    {:<13} {:<14} {:>3} appels  {}".format(
                detail["fournisseur"], detail["cle"], detail["appels_jour"], statut))

    manquants = [l for l in lignes if not l["disponible"] and not l["local"]]
    if manquants:
        print()
        print(c("  Cles gratuites a recuperer (2 minutes chacune)", "1"))
        for ligne in manquants[:5]:
            print("    {:<13} {}".format(ligne["nom"], c(ligne["inscription"], "2")))
        print()
        print("  Ajoutez-les dans : " + c(str(config.ENV_PATH), "1"))
        print("  Plusieurs cles pour un meme fournisseur : separez-les par des")
        print("  virgules, ou utilisez GROQ_API_KEY_2, GROQ_API_KEY_3, etc.")
    demander("\n  Appuyez sur Entree")


def menu_principal(executer: Callable[[List[str]], int]) -> int:
    while True:
        effacer()
        entete("USINE-IA  v{}".format(__version__))
        disponibles = config.active_providers()
        distants = [p for p in disponibles if not p.local]
        avec_cle = [p for p in distants if not p.keyless]
        if avec_cle:
            print("  " + c("v", "32") + " {} fournisseur(s) avec cle, "
                  "rotation active".format(len(avec_cle)))
        elif distants:
            print("  " + c("!", "33") + " Aucune cle API : quota tres limite")
        else:
            print("  " + c("x", "31") + " Aucun fournisseur — voir « Cles et quotas »")
        produits = [p for p in store.lister_produits(50)
                    if p["statut"] != "bonus_integre"]
        print("  " + c("*", "36") + " {} produit(s) fabrique(s)".format(len(produits)))

        choix = choisir("Menu principal", [
            ("Fabriquer un produit", "ebook, prompts, formation, imprimables..."),
            ("Mes produits", "consulter, vendre, empaqueter"),
            ("Cles et quotas", "etat des fournisseurs et du pool de cles"),
            ("Reglages", "auteur, marque, ton et qualite par defaut"),
            ("Tableau de bord 3D", "interface visuelle dans le navigateur"),
            ("Diagnostic complet", "verifier toute l'installation"),
        ], defaut=1, retour="Quitter")

        if choix == 0:
            print("\n  A bientot.\n")
            return 0
        if choix == 1:
            menu_fabriquer(executer)
        elif choix == 2:
            menu_produits(executer)
        elif choix == 3:
            menu_cles()
        elif choix == 4:
            menu_reglages()
        elif choix == 5:
            executer(["web"])
        elif choix == 6:
            executer(["docteur"])
            demander("\n  Appuyez sur Entree")
