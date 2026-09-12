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
from .pipelines.base import (CHAPITRES_MAX, CHAPITRES_MIN, MOTS_MAX,
                             MOTS_MIN, TAILLES, TONS)

_COULEUR = sys.stdout.isatty()


def c(texte: str, code: str) -> str:
    return "\033[{}m{}\033[0m" .format(code, texte) if _COULEUR else texte


def effacer() -> None:
    if _COULEUR:
        print("\033[2J\033[H", end="")


def entete(titre: str) -> None:
    """Bandeau cyberpunk : cadre neon, coins coupes. Lisible meme sans couleur."""
    largeur = 46
    barre = "\u2500" * largeur
    print()
    print(c("  \u2584" + barre + "\u2584", "35"))
    print(c("  \u2588", "36") + c(("\u25b8 " + titre).center(largeur), "1;96")
          + c("\u2588", "36"))
    print(c("  \u2580" + barre + "\u2580", "35"))
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

def rang(connus: List[str], valeur: Any, hors_liste: int) -> int:
    """Numero a proposer par defaut, meme pour un reglage sur mesure.

    Le ton et le volume ne sont plus des listes fermees : « comme un vieux
    menuisier a son apprenti » est un ton valide, et « 15 » un volume. Le
    menu, lui, calculait son defaut par « connus.index(valeur) », qui leve
    ValueError des que la valeur enregistree sort de la liste. Un ton sur
    mesure — saisissable depuis ce meme menu — rendait donc « Fabriquer un
    produit » inaccessible, avec une trace Python en plein ecran de
    telephone, et sans rien indiquer de la cause.
    """
    texte = str(valeur or "")
    return connus.index(texte) + 1 if texte in connus else hors_liste


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
        # La derniere entree ouvre la saisie libre : les cinq tons sont des
        # raccourcis, et imposer cinq voix a tout un catalogue est ce qui
        # fait que les produits se ressemblent.
        index = choisir("Ton de redaction",
                        [(t, TONS[t]) for t in tons]
                        + [("autre...", "decrivez la voix que vous voulez")],
                        defaut=rang(tons, valeurs["ton"], len(tons) + 1))
        if index and index <= len(tons):
            arguments += ["-t", tons[index - 1]]
        elif index:
            # Un ton sur mesure deja enregistre est repropose tel quel :
            # le retaper a chaque produit etait le plus sur moyen de ne
            # jamais s'en servir.
            libre = demander("Decrivez le ton",
                             valeurs["ton"] if valeurs["ton"] not in TONS
                             else "comme un artisan qui explique a son apprenti")
            if libre:
                arguments += ["-t", libre]

        tailles = sorted(TAILLES, key=lambda t: TAILLES[t][0])
        index = choisir("Volume",
                        [(t, "{} sections d'environ {} mots".format(*TAILLES[t]))
                         for t in tailles]
                        + [("sur mesure...", "choisir le nombre de sections")],
                        defaut=rang(tailles, valeurs["taille"],
                                    len(tailles) + 1))
        if index and index <= len(tailles):
            arguments += ["-T", tailles[index - 1]]
        elif index:
            sections = demander("Combien de sections ({} a {})".format(
                CHAPITRES_MIN, CHAPITRES_MAX),
                str(valeurs["taille"]) if str(valeurs["taille"]).isdigit()
                else "12")
            if sections.isdigit():
                arguments += ["--chapitres", sections]
            mots = demander("Mots par section ({} a {}, Entree pour auto)".format(
                MOTS_MIN, MOTS_MAX), "")
            if mots.isdigit():
                arguments += ["--mots", mots]

        qualites = ["rapide", "standard", "exigeant"]
        index = choisir("Niveau de qualite", [
            ("rapide", "aucune relecture — le plus rapide et le plus econome"),
            ("standard", "1 relecture editoriale par section"),
            ("exigeant", "2 relectures — le meilleur resultat, 2 a 3 fois plus long"),
        ], defaut=rang(qualites, valeurs["qualite"],
                       qualites.index("standard") + 1))
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
            ("Laisser l'usine chercher", "niches voisines de ce qui a marche"),
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
            _prospecter(executer)
        elif choix == 3:
            _voir_la_file()
        elif choix == 4:
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
        elif choix == 5:
            executer(["usine", "arreter"])
            demander("\n  Appuyez sur Entree")
        elif choix == 6:
            _regler_budget()


def _prospecter(executer: Callable[[List[str]], int]) -> None:
    """Laisser l'usine proposer des niches voisines de ce qui a marche."""
    from .production import graine_de_depart

    entete("Prospection")
    graine = graine_de_depart()
    if graine:
        print("  Depart : « {} »".format(graine[:46]))
        print("  " + c("c'est la niche qui a le mieux rapporte, a defaut la "
                       "mieux notee.", "2"))
        if not demander_oui("Partir de la ?", True):
            graine = demander("Partir de quelle niche", obligatoire=True)
            if not graine:
                return
    else:
        print("  " + c("Aucun historique : l'usine ne sait pas encore ce qui "
                       "marche chez vous.", "33"))
        graine = demander("Partir de quelle niche", obligatoire=True)
        if not graine:
            return

    arguments = ["file", "--explorer", graine]
    combien = demander("Combien de pistes", "8")
    if combien.isdigit():
        arguments += ["-n", combien]
    if not demander_oui("Aller lire les discussions ? (plus lent)", True):
        arguments.append("--sans-veille")
    print()
    executer(arguments)
    demander("\n  Appuyez sur Entree")


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


def _dater_les_variantes() -> None:
    """Dit quelle variante etait en ligne a quelles dates.

    C'est la piece qui manque entre les ventes importees et le verdict :
    sans periode, une variante ne peut recevoir aucune vente, et « Rythme
    de vente reel » n'a que des lignes vides a montrer. La commande
    existait — « usine ab periode » — mais seulement au clavier.
    """
    numero = demander("Numero du test")
    if not numero.isdigit():
        return
    lot = experience.variantes(int(numero))
    if not lot:
        print(c("  Test inconnu ou sans variante.", "33"))
        demander("  Appuyez sur Entree")
        return

    entete("Dater les variantes")
    print("  " + c("Format AAAA-MM-JJ. Laissez vide pour passer.", "2"))
    print("  " + c("Fin vide : la variante est toujours en ligne.", "2"))
    print()
    for variante in lot:
        print("  [{}] {}".format(variante["etiquette"],
                                 variante["contenu"][:46]))
        if variante.get("debut"):
            print("      deja : du {} au {}".format(
                variante["debut"], variante.get("fin") or "aujourd'hui"))
        debut = demander("      en ligne a partir du",
                         variante.get("debut") or "")
        if not debut:
            continue
        fin = demander("      jusqu'au", variante.get("fin") or "")
        try:
            experience.fixer_periode(variante["id"], debut, fin)
            print(c("      enregistre.", "32"))
        except ValueError as exc:
            print(c("      refuse : {}".format(exc), "31"))
    demander("\n  Appuyez sur Entree")


def menu_ab(executer: Callable[[List[str]], int]) -> None:
    """Tests A/B : creer des variantes, les dater, lire le verdict.

    Les six entrees couvrent maintenant toute la chaine. « Dater les
    variantes » et « Rythme de vente reel » n'existaient qu'en ligne de
    commande : depuis un telephone, la comparaison sur les ventes
    reellement encaissees etait hors d'atteinte.
    """
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
            ("Dater les variantes", "quand chacune etait en ligne"),
            ("Rythme de vente reel", "comparer sur les ventes importees"),
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
            _dater_les_variantes()

        elif choix == 5:
            numero = demander("Numero du test")
            if numero.isdigit():
                executer(["ab", "rythme", numero])
                demander("\n  Appuyez sur Entree")

        elif choix == 6:
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


def _choisir_ton(actuelle: str) -> Optional[str]:
    """Les cinq raccourcis, plus la saisie libre."""
    tons = sorted(TONS)
    index = choisir("Ton de redaction",
                    [(t, TONS[t]) for t in tons]
                    + [("autre...", "decrivez la voix que vous voulez")],
                    defaut=rang(tons, actuelle, len(tons) + 1))
    if index == 0:
        return None
    if index <= len(tons):
        return tons[index - 1]
    libre = demander("Decrivez le ton",
                     actuelle if actuelle not in TONS else "")
    return libre or None


def _choisir_taille(actuelle: str) -> Optional[str]:
    """Les paliers, ou un nombre de sections."""
    tailles = sorted(TAILLES, key=lambda t: TAILLES[t][0])
    index = choisir("Volume par defaut",
                    [(t, "{} sections d'environ {} mots".format(*TAILLES[t]))
                     for t in tailles]
                    + [("sur mesure...", "un nombre de sections")],
                    defaut=rang(tailles, actuelle, len(tailles) + 1))
    if index == 0:
        return None
    if index <= len(tailles):
        return tailles[index - 1]
    sections = demander("Combien de sections ({} a {})".format(
        CHAPITRES_MIN, CHAPITRES_MAX),
        str(actuelle) if str(actuelle).isdigit() else "")
    return sections if sections.isdigit() else None


def _choisir_qualite(actuelle: str) -> Optional[str]:
    """Liste fermee : une qualite inventee ne veut rien dire nulle part."""
    qualites = ["rapide", "standard", "exigeant"]
    index = choisir("Niveau de qualite", [
        ("rapide", "aucune relecture — le plus rapide et le plus econome"),
        ("standard", "1 relecture editoriale par section"),
        ("exigeant", "2 relectures — le meilleur resultat, 2 a 3 fois plus long"),
    ], defaut=rang(qualites, actuelle, qualites.index("standard") + 1))
    return qualites[index - 1] if index else None


# Ces trois reglages ont des valeurs qui veulent dire quelque chose ailleurs
# dans l'usine. Les faire taper au clavier laissait enregistrer « rapidos »,
# qui vaut « standard » partout sans que rien ne le dise.
_A_CHOISIR = {"ton": _choisir_ton, "taille": _choisir_taille,
              "qualite": _choisir_qualite}


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
        elif ligne["nom"] in _A_CHOISIR:
            nouvelle = _A_CHOISIR[ligne["nom"]](str(actuelle))
            if nouvelle is None:
                continue
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


def _menu_prompts(executer: Callable[[List[str]], int]) -> None:
    """Les prompts et les personnalites d'agents, sans editer de JSON a l'aveugle."""
    entete("Prompts et agents")
    print("  Les prompts par defaut sont dans le code. Les exporter en")
    print("  ecrit une copie dans " + c("atelier/prompts/", "1") + " que vous")
    print("  pouvez modifier ; l'usine la relit a chaque fabrication.")
    choix = choisir("Que faire ?", [
        ("Voir ce qui est personnalise", "ce que l'usine lit en plus du defaut"),
        ("Exporter les prompts par defaut", "pour les modifier ensuite"),
        ("Tout remettre par defaut", "supprime vos personnalisations"),
    ], defaut=1)
    if choix == 1:
        executer(["prompts-systeme"])
    elif choix == 2:
        executer(["prompts-systeme", "--exporter"])
    elif choix == 3:
        if not demander_oui("Supprimer toutes les personnalisations ?", False):
            return
        executer(["prompts-systeme", "--reinitialiser"])
    else:
        return
    demander("\n  Appuyez sur Entree")


def _menu_cache(executer: Callable[[List[str]], int]) -> None:
    """Le cache evite de repayer un appel identique. Le vider n'est pas anodin."""
    entete("Cache IA")
    choix = choisir("Que faire ?", [
        ("Voir ce qu'il contient", "taille et nombre de reponses gardees"),
        ("Le vider", "les memes demandes reconsommeront du quota"),
    ], defaut=1)
    if choix == 1:
        executer(["cache"])
    elif choix == 2:
        if not demander_oui("Vider le cache ?", False):
            return
        executer(["cache", "--vider"])
    else:
        return
    demander("\n  Appuyez sur Entree")


def _menu_recon(executer: Callable[[List[str]], int]) -> None:
    """Audit d'un domaine pour la divulgation responsable.

    La porte d'autorisation est posee ICI, en clair, parce que c'est un acte
    de l'operateur : on ne coche pas « surface » a sa place. Sans elle,
    l'audit reste passif — que du public, aucun contact avec la cible.
    """
    entete("Recon & securite")
    print("  " + c("Passif", "1;36") + " : registres publics (crt.sh, DNS, RDAP).")
    print("           Aucun paquet vers la cible. Legal partout.")
    print("  " + c("Surface", "1;35") + " : une requete vers le domaine, pour "
          "lire sa")
    print("           posture. Reserve a un domaine dont vous avez la charge,")
    print("           ou couvert par un programme de bug bounty.")
    print()
    domaine = demander("Domaine a auditer", obligatoire=True)
    if not domaine:
        return
    args = ["recon", domaine]
    if demander_oui("\n  J'ai la charge de ce domaine (audit de surface) ?",
                    False):
        args.append("--autorise")
    if demander_oui("Ecrire un signalement pret a envoyer ?", False):
        args.append("--rapport")
        nom = demander("Votre nom pour le signaler (facultatif)")
        if nom:
            args += ["--chercheur", nom]
    print()
    executer(args)
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
            ("Veille de niche", "ce que les gens disent vraiment d'un sujet"),
            ("Recon & securite", "audit d'un domaine, divulgation responsable"),
            ("Mesurer un marche", "volumes reels sur quatre sources publiques"),
            ("Ce que l'usine a appris", "quel type, quel ton, quelle qualite"),
            ("Sauvegarder l'atelier", "ventes et historique dans une archive"),
            ("Cles et quotas", "etat des fournisseurs et du pool de cles"),
            ("Reglages", "auteur, marque, ton et qualite par defaut"),
            ("Prompts et agents", "personnaliser les voix de l'equipe"),
            ("Cache IA", "consulter ou vider les reponses gardees"),
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
            sujet = demander("Quelle niche explorer", obligatoire=True)
            if sujet:
                executer(["veille", sujet])
            demander("\n  Appuyez sur Entree")
        elif choix == 8:
            _menu_recon(executer)
        elif choix == 9:
            sujet = demander("Quel marche mesurer", obligatoire=True)
            if sujet:
                executer(["marche", sujet])
            demander("\n  Appuyez sur Entree")
        elif choix == 10:
            executer(["bilan"])
            demander("\n  Appuyez sur Entree")
        elif choix == 11:
            executer(["sauvegarde"])
            demander("\n  Appuyez sur Entree")
        elif choix == 12:
            menu_cles()
        elif choix == 13:
            menu_reglages()
        elif choix == 14:
            _menu_prompts(executer)
        elif choix == 15:
            _menu_cache(executer)
        elif choix == 16:
            executer(["web"])
        elif choix == 17:
            executer(["docteur"])
            demander("\n  Appuyez sur Entree")
