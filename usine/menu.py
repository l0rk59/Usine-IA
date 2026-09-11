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
from .core import config, experience
from .core import file as file_prod
from .core import llm, reglages, securite, store
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

def produits_offerts(en_file: bool = False) -> List[Dict[str, Any]]:
    """Types proposes par le menu, lus du catalogue.

    Cette liste etait autrefois recopiee ici. Elle avait diverge de celle de
    l'explorateur de niches, qui ne connaissait pas deux types pourtant
    fabricables.
    """
    from .pipelines import catalogue

    offerts = [
        {"cle": t.cle, "nom": t.nom,
         "detail": "{} — {}".format(t.detail, t.duree),
         "quantite": (t.quantite[1], t.quantite[2]) if t.quantite else None}
        for t in catalogue.tous(fabricables=True, en_file=en_file)
    ]
    if not en_file:
        offerts.append({
            "cle": "complet", "nom": "Offre complete",
            "detail": "Ebook + 2 bonus + kit de vente + archive — 25 a 45 min",
            "quantite": None,
        })
    return offerts


def menu_fabriquer(executer: Callable[[List[str]], int]) -> None:
    offerts = produits_offerts()
    choix = choisir(
        "Que voulez-vous fabriquer ?",
        [(p["nom"], p["detail"]) for p in offerts],
        defaut=1,
    )
    if choix == 0:
        return
    produit = offerts[choix - 1]
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


def menu_usine(executer: Callable[[List[str]], int]) -> None:
    """Usine continue : file de niches, budget, marche/arret."""
    from .production import statut, verrou_actif

    while True:
        etat = statut()
        entete("Usine continue")
        if etat["en_marche"]:
            session = etat["session"]
            print("  " + c("EN MARCHE", "1;32")
                  + "  (pid {}, {} produit(s))".format(
                      etat["pid"], session.get("nombre_faits", 0)))
            courant = session.get("courant")
            if courant:
                print("  en cours : {} — {}".format(
                    courant["type"], courant["sujet"][:34]))
        else:
            print("  " + c("A L'ARRET", "90"))
        compte = etat["file"]
        print("  file : {} en attente, {} livre(s), {} echec(s)".format(
            compte["en_attente"], compte["fait"], compte["echec"]))
        b = etat["budget"]
        if b["actif"] and b["appels_jour_max"]:
            print("  budget : {} / {} appels aujourd'hui".format(
                b["appels_jour"], b["appels_jour_max"]))

        choix = choisir("Que faire ?", [
            ("Ajouter une niche a la file", "elle sera fabriquee a son tour"),
            ("Voir la file", "consulter, retirer, relancer un echec"),
            ("Demarrer l'usine", "produit en boucle jusqu'au budget ou a la fin"),
            ("Arreter l'usine", "termine le produit en cours puis s'arrete"),
            ("Regler le budget", "plafonds d'appels et de produits"),
        ], defaut=1)

        if choix == 0:
            return
        if choix == 1:
            _ajouter_a_la_file()
        elif choix == 2:
            _voir_la_file()
        elif choix == 3:
            if verrou_actif() is not None:
                print(c("\n  Une usine tourne deja.", "33"))
                demander("  Appuyez sur Entree")
                continue
            if not etat["file"]["en_attente"]:
                print(c("\n  La file est vide : ajoutez au moins une niche.", "33"))
                demander("  Appuyez sur Entree")
                continue
            arguments = ["usine", "demarrer"]
            maximum = demander("Arreter apres combien de produits ? (vide = tous)")
            if maximum.isdigit():
                arguments += ["--max", maximum]
            if demander_oui("Remplir la file automatiquement quand elle se vide ?",
                            False):
                arguments.append("--auto")
            print(c("\n  Ctrl+C arrete proprement apres le produit en cours.\n", "2"))
            executer(arguments)
            demander("\n  Appuyez sur Entree")
        elif choix == 4:
            executer(["usine", "arreter"])
            demander("\n  Appuyez sur Entree")
        elif choix == 5:
            _regler_budget()


def _ajouter_a_la_file() -> None:
    offerts = produits_offerts(en_file=True)
    index = choisir("Type de produit",
                    [(p["nom"], p["detail"]) for p in offerts], defaut=1)
    if index == 0:
        return
    produit = offerts[index - 1]
    entete("Ajouter a la file")
    sujet = demander("Sujet", obligatoire=True)
    if not sujet:
        return
    for domaine, avertissement in securite.analyser_sujet(sujet):
        print("\n  " + c("[!] {} : {}".format(domaine, avertissement[:60]), "33"))

    options = {}
    if produit["quantite"]:
        question, defaut = produit["quantite"]
        quantite = demander(question, defaut)
        if quantite.isdigit():
            options["nombre"] = int(quantite)
    priorite = demander("Priorite (1 = en premier, 9 = en dernier)", "5")
    identifiant = file_prod.ajouter(
        sujet, produit["cle"], options=options,
        priorite=int(priorite) if priorite.isdigit() else 5)
    if identifiant:
        print(c("\n  Ajoute a la file (numero {}).".format(identifiant), "32"))
    else:
        print(c("\n  Deja en file.", "33"))
    demander("  Appuyez sur Entree")


def _voir_la_file() -> None:
    entrees = file_prod.lister(limite=30)
    entete("File de production")
    if not entrees:
        print("  File vide.")
        demander("\n  Appuyez sur Entree")
        return
    couleurs = {"en_attente": "36", "en_cours": "1;33", "fait": "32",
                "echec": "31", "annule": "90"}
    for entree in entrees:
        print("  {:>4}  {:<11} {:<11} {}".format(
            entree["id"], c(entree["statut"], couleurs.get(entree["statut"], "0")),
            entree["type"], entree["sujet"][:32]))
    print()
    action = choisir("Action", [
        ("Retirer une entree", "elle ne sera pas fabriquee"),
        ("Relancer les echecs", "les remet en file"),
        ("Nettoyer", "supprime les entrees livrees et annulees"),
    ], defaut=0)
    if action == 1:
        numero = demander("Numero a retirer")
        if numero.isdigit() and file_prod.retirer(int(numero)):
            print(c("  Retiree.", "32"))
        else:
            print(c("  Introuvable ou deja terminee.", "33"))
        demander("  Appuyez sur Entree")
    elif action == 2:
        print(c("  {} entree(s) remise(s) en file.".format(file_prod.rejouer()), "32"))
        demander("  Appuyez sur Entree")
    elif action == 3:
        print(c("  {} entree(s) supprimee(s).".format(file_prod.vider()), "32"))
        demander("  Appuyez sur Entree")


def _regler_budget() -> None:
    champs = [
        ("budget_appels_jour", "Appels IA maximum par jour"),
        ("budget_appels_produit", "Appels IA maximum par produit"),
        ("budget_produits_jour", "Produits maximum par jour"),
        ("budget_minutes_produit", "Duree maximum d'un produit, en minutes"),
        ("pause_entre_produits", "Pause entre deux produits, en secondes"),
    ]
    entete("Budget de production")
    print("  " + c("0 signifie « pas de limite ».", "2"))
    print()
    for nom, description in champs:
        valeur = demander("{} [{}]".format(description, reglages.lire(nom)),
                          str(reglages.lire(nom)))
        reglages.ecrire({nom: valeur})
    print(c("\n  Budget enregistre.", "32"))
    demander("  Appuyez sur Entree")


def menu_ab(executer: Callable[[List[str]], int]) -> None:
    """Tests A/B : creer des variantes, reporter les chiffres, lire le verdict."""
    while True:
        tests = experience.lister(20)
        entete("Tests A/B")
        if tests:
            for test in tests:
                analyse = experience.analyser(test["id"])
                couleur = {"gagnant": "32", "tendance": "33"}.get(
                    analyse["verdict"]["etat"], "90")
                print("  {:>3}  {:<11} {:<22} {}".format(
                    test["id"], test["sujet"], test["titre"][:22],
                    c(analyse["verdict"]["etat"], couleur)))
        else:
            print("  Aucun test pour l'instant.")

        choix = choisir("Que faire ?", [
            ("Tester des titres", "5 variantes sur des angles differents"),
            ("Tester des couvertures", "4 directions visuelles distinctes"),
            ("Reporter des chiffres", "vues et ventes observees"),
            ("Voir un verdict", "ce que disent reellement vos donnees"),
        ], defaut=1)

        if choix == 0:
            return
        if choix in (1, 2):
            sujet = "titre" if choix == 1 else "couverture"
            entete("Tester des {}s".format(sujet))
            produits = [p for p in store.lister_produits(20)
                        if p["statut"] != "bonus_integre"]
            arguments = ["ab", "creer", "--sur", sujet]
            if produits and demander_oui("Partir d'un produit existant ?", True):
                index = choisir("Quel produit ?",
                                [(p["titre"][:40], p["type"]) for p in produits],
                                defaut=1)
                if index == 0:
                    continue
                arguments += ["--produit", produits[index - 1]["id"]]
            else:
                titre = demander("Titre actuel du produit", obligatoire=True)
                if not titre:
                    continue
                arguments += ["--titre", titre]
            nombre = demander("Combien de variantes", "5" if choix == 1 else "4")
            if nombre.isdigit():
                arguments += ["-n", nombre]
            if not reglages.lire("images", True) and choix == 2:
                arguments.append("--sans-image")
            print()
            executer(arguments)
            demander("\n  Appuyez sur Entree")

        elif choix == 3:
            numero = demander("Numero du test")
            if not numero.isdigit():
                continue
            lot = experience.variantes(int(numero))
            if not lot:
                print(c("  Test inconnu ou sans variante.", "33"))
                demander("  Appuyez sur Entree")
                continue
            entete("Reporter les chiffres")
            print("  " + c("Laissez vide pour passer une variante.", "2"))
            print()
            for variante in lot:
                print("  [{}] {}".format(variante["etiquette"],
                                         variante["contenu"][:46]))
                print("      deja : {} vue(s), {} action(s)".format(
                    variante["total_vues"], variante["total_actions"]))
                vues = demander("      vues a ajouter")
                if not vues.isdigit():
                    continue
                actions = demander("      ventes ou clics a ajouter", "0")
                try:
                    experience.observer(variante["id"], vues=int(vues),
                                        actions=int(actions) if actions.isdigit()
                                        else 0)
                    print(c("      enregistre.", "32"))
                except ValueError as exc:
                    print(c("      refuse : {}".format(exc), "31"))
            executer(["ab", "verdict", numero])
            demander("\n  Appuyez sur Entree")

        elif choix == 4:
            numero = demander("Numero du test")
            if numero.isdigit():
                executer(["ab", "verdict", numero])
                demander("\n  Appuyez sur Entree")


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


def menu_ventes(executer) -> None:
    """Saisir ou importer des ventes, puis lire ce qu'elles disent."""
    while True:
        entete("Ventes")
        index = choisir("Ventes", [
            ("Voir le bilan", "chiffre d'affaires, par produit, par type"),
            ("Importer un export", "fichier CSV d'une place de marche"),
            ("Saisir une vente", "a la main, pour une vente unique"),
            ("Rattacher automatiquement", "relier les references aux produits"),
        ], defaut=1)
        if index == 0:
            return
        if index == 1:
            executer(["ventes"])
        elif index == 2:
            chemin = demander("Chemin du fichier CSV")
            if not chemin:
                continue
            plateforme = demander("Plateforme", "gumroad")
            executer(["ventes", "--importer", chemin, "--sur", plateforme])
        elif index == 3:
            produits = store.lister_produits(20)
            if not produits:
                print("\n  Aucun produit fabrique.")
                demander("  Appuyez sur Entree")
                continue
            rang = choisir("Quel produit", [(p["titre"][:46], p["type"])
                                            for p in produits], defaut=1)
            if rang == 0:
                continue
            montant = demander("Montant encaisse (ex : 29)")
            if not montant.replace(".", "").replace(",", "").isdigit():
                continue
            unites = demander("Combien d'unites", "1")
            executer(["ventes", "--ajouter", produits[rang - 1]["id"],
                      "--brut", montant.replace(",", "."),
                      "--unites", unites if unites.isdigit() else "1"])
        elif index == 4:
            executer(["ventes", "--rattacher"])
        demander("\n  Appuyez sur Entree")


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

        compte = file_prod.compter()
        if compte["en_attente"] or compte["en_cours"]:
            print("  " + c("~", "33") + " {} niche(s) en file".format(
                compte["en_attente"] + compte["en_cours"]))

        choix = choisir("Menu principal", [
            ("Fabriquer un produit", "ebook, prompts, formation, imprimables..."),
            ("Usine continue", "file de niches, budget, production en boucle"),
            ("Tests A/B", "titres et couvertures : comparer et decider"),
            ("Mes produits", "consulter, vendre, empaqueter"),
            ("Ventes", "importer un export, voir ce qui rapporte vraiment"),
            ("Doublons", "les produits qui se recouvrent"),
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
            menu_usine(executer)
        elif choix == 3:
            menu_ab(executer)
        elif choix == 4:
            menu_produits(executer)
        elif choix == 5:
            menu_ventes(executer)
        elif choix == 6:
            executer(["doublons"])
            demander("\n  Appuyez sur Entree")
        elif choix == 7:
            menu_cles()
        elif choix == 8:
            menu_reglages()
        elif choix == 9:
            executer(["web"])
        elif choix == 10:
            executer(["docteur"])
            demander("\n  Appuyez sur Entree")
