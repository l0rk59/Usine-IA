"""Menu interactif pour Termux.

Taper « usine ebook "..." --marketing --zip -T long » au clavier d'un telephone
est penible. Ce menu pose les questions une par une, se souvient des reglages
et n'attend que des chiffres.

Volontairement sans curses : sur Termux, curses se comporte mal selon le
clavier virtuel utilise. Ici, tout passe par input() et des numeros.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import (Any, Callable, Dict, List, Optional,
                    Tuple)

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


def choisir_ou_laisser(titre: str, options: List[Tuple[str, str]]) -> int:
    """Comme « choisir », avec en tete « l'usine decide » — et c'est le defaut.

    Rend l'index dans « options » (1..n), ou 0 si l'on laisse l'usine decider
    ou qu'on revient.

    Mesure du 24/09/2026 : chaque liste du menu avait un defaut en dur, et
    Entree le choisissait — « linkedin », « bienvenue », « intermediaire », la
    tranche d'age par defaut, la premiere forme d'outil. Appuyer sur Entree
    pour aller vite fabriquait donc exactement les produits sans relief que
    l'usine sait eviter depuis qu'elle decide ces reglages d'apres le sujet.
    """
    index = choisir(titre, [("L'usine decide", "d'apres le sujet")] + options,
                    defaut=1)
    return index - 1 if index > 1 else 0


# Ce qu'on lit a cote d'un nombre qu'on peut laisser a l'usine.
LAISSER = " (Entree : l'usine decide)"


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
    # Plus « obligatoire » : une reponse vide veut dire « trouve-la ». C'etait
    # la seule facon de ne pas dicter la niche depuis le telephone — et donc
    # la seule facon de ne pas produire du tout. La ligne de commande et le
    # tableau de bord se comportent desormais pareil.
    print(c("  Laissez vide et l'usine cherche la niche elle-meme.", "2"))
    sujet = demander("Sujet du produit (facultatif)", "")

    alertes = securite.analyser_sujet(sujet)
    for domaine, avertissement in alertes:
        print()
        print(c("  [!] Domaine sensible : {}".format(domaine), "33"))
        print("      " + avertissement)
    if alertes and not demander_oui("\n  Continuer malgre tout ?", True):
        return

    audience = demander("Pour qui", valeurs["audience"])
    # Un sujet vide ne se passe PAS en argument : argparse le prendrait pour
    # une chaine vide a fabriquer, et l'usine ne choisirait rien.
    arguments: List[str] = [produit["cle"]]
    if sujet:
        arguments.append(sujet)
    arguments += ["-a", audience]

    if produit["quantite"]:
        # Sans valeur proposee : Entree envoyait « -n 50 », un choix que
        # personne n'avait fait, et l'usine ne decidait plus le nombre.
        question = produit["quantite"][0]
        quantite = demander(question + LAISSER, "")
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

    # Les options propres a chaque type. Elles n'existaient que dans la ligne
    # de commande — c'est-a-dire pour personne : la vraie porte d'entree de
    # cette usine est ce menu, sur un telephone. Six leviers de qualite
    # etaient ainsi invisibles a qui produit depuis son canape.
    arguments += _arguments_du_type(produit["cle"])

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


def _options_du_type(cle: str) -> Dict[str, object]:
    """Options propres a un type de produit, demandees a l'utilisateur.

    Le catalogue declare ces options ; chaque interface doit les proposer.
    Une option declaree et inaccessible depuis le telephone est un levier
    qu'on croit avoir et qu'on n'a pas — c'est le reglage orphelin deplace
    d'un cran, et six d'entre elles etaient dans ce cas.

    Rend les noms du CATALOGUE, pas des arguments de ligne de commande : la
    file de production stocke ce dictionnaire tel quel, et « catalogue.
    executer » le transmet a la chaine. La conversion en arguments se fait
    au-dessus, une seule fois, et c'est la qu'une inversion comme
    « avec_marche » / « --sans-marche » se traite.
    """
    if cle in ("nouvelle", "roman"):
        choisies = _promesse_de_fiction(cle)
        nom_serie = _demander_serie()
        if nom_serie:
            choisies["serie"] = nom_serie
        return choisies
    if cle in ("interactive", "recueil", "feuilleton"):
        return _promesse_de_fiction(cle)
    if cle == "conte":
        # La tranche d'age decide de TOUT pour un album : nombre de pages,
        # longueur des phrases, vocabulaire. La demander en dernier, ou pas
        # du tout, reviendrait a fabriquer pour un enfant qu'on n'a pas
        # choisi — et le controle de lisibilite se comparerait alors a une
        # consigne que personne n'a voulue.
        from .pipelines import conte as chaine_conte

        tranches = list(chaine_conte.TRANCHES)
        index = choisir_ou_laisser(
            "Tranche d'age",
            [(t, "{} pages, phrases de {} mots au maximum".format(
                chaine_conte.TRANCHES[t]["pages"],
                chaine_conte.TRANCHES[t]["mots_phrase"])) for t in tranches])
        choisies = {"tranche": tranches[index - 1]} if index else {}
        choisies.update(_promesse_de_fiction(cle))
        return choisies
    if cle == "ebook":
        # Lu sur le catalogue : la forme, le niveau et les exercices y sont
        # declares avec leur etiquette, et ce menu est la vraie porte
        # d'entree sur un telephone.
        choisies = _champs_du_catalogue(cle, ("forme", "niveau", "exercices"))
        if demander_oui("Relire le livre entier a la recherche des "
                        "contradictions entre chapitres ? (1 appel IA)", False):
            choisies["relecture_ensemble"] = True
        return choisies
    if cle == "formation":
        return {"narration": True} if demander_oui(
            "Produire le script de narration a lire a voix haute ? "
            "(1 appel IA par module)", False) else {}
    if cle == "impression":
        # Un interieur broche dont la marge interieure vaut l'exterieure perd
        # ses premiers caracteres dans la pliure. L'imprimeur publie la sienne.
        marge = demander("Marge de reliure en mm (0 = impression a domicile)", "0")
        try:
            valeur = float(marge)
        except ValueError:
            return {}
        return {"reliure": valeur} if valeur > 0 else {}
    if cle == "social":
        from .pipelines import social as chaine_social

        reseaux = sorted(chaine_social.RESEAUX)
        index = choisir_ou_laisser(
            "Reseau", [(r, chaine_social.RESEAUX[r].split("(")[-1][:58])
                       for r in reseaux])
        return {"reseau": reseaux[index - 1]} if index else {}
    if cle == "logiciel":
        from .pipelines import logiciel as chaine_logiciel

        cibles = sorted(chaine_logiciel.CIBLES)
        index = choisir_ou_laisser(
            "Forme de l'outil",
            [(c, chaine_logiciel.CIBLES[c]["nom"]) for c in cibles])
        return {"cible": cibles[index - 1]} if index else {}
    if cle == "idees":
        return {} if demander_oui(
            "Interroger les sources de marche ? (plus lent, mais chiffre)",
            True) else {"avec_marche": False}
    if cle == "emails":
        from .pipelines.emails import OBJECTIFS

        buts = list(OBJECTIFS)
        index = choisir_ou_laisser("Ce que la sequence cherche",
                                   [(b, OBJECTIFS[b]) for b in buts])
        choisies: Dict[str, object] = (
            {"intention": buts[index - 1]} if index else {})
        jours = demander("Un message tous les combien de jours ?" + LAISSER, "")
        try:
            rythme = int(jours)
        except ValueError:
            rythme = 0
        if rythme > 0:
            choisies["rythme"] = rythme
        return choisies
    if cle == "memo":
        # La marge de reliure n'a de sens qu'imprime en recto-verso : posee
        # sur une simple face, elle decale le texte sans rien servir.
        return {"recto_verso": True} if demander_oui(
            "Impression recto-verso ? (ajoute une marge de reliure)",
            False) else {}
    if cle == "quiz":
        from .pipelines.quiz import NIVEAUX

        index = choisir_ou_laisser("Niveau vise", [(n, "") for n in NIVEAUX])
        choisies = {"niveau": NIVEAUX[index - 1]} if index else {}
        if not demander_oui("Inclure un bareme de correction ?", True):
            choisies["sans_bareme"] = True
        return choisies
    return {}


def _champs_du_catalogue(cle: str, noms: Tuple[str, ...]) -> Dict[str, object]:
    """Les champs declares au catalogue, proposes avec « l'usine decide ».

    Une liste s'affiche avec ses etiquettes et part avec sa cle : « Manuel
    de référence » se lit, « --forme reference » se tape. Un texte vide,
    comme une liste laissee sur sa premiere entree, reste a l'usine.
    """
    from .pipelines import catalogue

    fiche = catalogue.obtenir(cle)
    choisies: Dict[str, object] = {}
    for champ in (fiche.champs if fiche else ()):
        if champ.nom not in noms:
            continue
        if champ.genre == "choix":
            valeurs = [v for v in champ.choix if v]
            etiquettes = dict(champ.etiquettes)
            index = choisir_ou_laisser(
                champ.libelle, [(etiquettes.get(v, v), "") for v in valeurs])
            if index:
                choisies[champ.nom] = valeurs[index - 1]
        elif champ.genre == "texte":
            valeur = demander(champ.libelle + LAISSER, "").strip()
            if valeur:
                choisies[champ.nom] = valeur
    return choisies


# Ce qu'une fiction se voit proposer dans le menu, dans l'ordre ou l'on se
# pose les questions : ou le livre se range, ce qu'on vient y chercher, puis
# la facon de le raconter. Mesure du 26/09/2026 : depuis le telephone, aucun
# de ces neuf reglages n'etait atteignable — seuls la serie de la nouvelle et
# la tranche d'age du conte l'etaient. Choisir « romance, fin heureuse »
# exigeait la ligne de commande.
PROMESSE_DE_FICTION = ("genre", "sous_genre", "tropes", "ambiance", "fin",
                       "chaleur", "point_de_vue", "temps", "structure")


def _promesse_de_fiction(cle: str) -> Dict[str, object]:
    """Les reglages de fiction, sur demande : sinon l'usine les decide."""
    if not demander_oui("Choisir le genre, l'ambiance et la fin ? "
                        "(sinon l'usine decide d'apres le sujet)", False):
        return {}
    return _champs_du_catalogue(cle, PROMESSE_DE_FICTION)


# Comment chaque option du catalogue s'ecrit en ligne de commande. Deux
# d'entre elles ne portent pas le meme nom des deux cotes : la CLI expose
# « --sans-marche », le catalogue declare « avec_marche ». Recopier cette
# correspondance dans chaque appelant etait la facon sure de la voir diverger.
_ARGUMENTS = {
    "serie": lambda v: ["--serie", str(v)],
    "relecture_ensemble": lambda v: ["--relecture-ensemble"] if v else [],
    "narration": lambda v: ["--narration"] if v else [],
    "reliure": lambda v: ["--reliure", str(v)],
    "reseau": lambda v: ["--reseau", str(v)],
    "cible": lambda v: ["--cible", str(v)],
    "avec_marche": lambda v: [] if v else ["--sans-marche"],
    "intention": lambda v: ["--intention", str(v)],
    "rythme": lambda v: ["--rythme", str(v)],
    "recto_verso": lambda v: ["--recto-verso"] if v else [],
    "niveau": lambda v: ["--niveau", str(v)],
    "forme": lambda v: ["--forme", str(v)],
    "genre": lambda v: ["--genre", str(v)],
    "sous_genre": lambda v: ["--sous-genre", str(v)],
    "tropes": lambda v: ["--tropes", str(v)],
    "ambiance": lambda v: ["--ambiance", str(v)],
    "fin": lambda v: ["--fin", str(v)],
    "chaleur": lambda v: ["--chaleur", str(v)],
    "point_de_vue": lambda v: ["--point-de-vue", str(v)],
    "temps": lambda v: ["--temps", str(v)],
    "structure": lambda v: ["--structure", str(v)],
    "tranche": lambda v: ["--tranche", str(v)],
    "exercices": lambda v: ["--exercices", str(v)],
    "sans_bareme": lambda v: ["--sans-bareme"] if v else [],
}


def _arguments_du_type(cle: str) -> List[str]:
    """Les memes options, en arguments pour la ligne de commande."""
    arguments: List[str] = []
    for nom, valeur in _options_du_type(cle).items():
        traduire = _ARGUMENTS.get(nom)
        if traduire is not None:
            arguments += traduire(valeur)
    return arguments


def _demander_serie() -> str:
    """Ranger ce recit dans une suite ? Les series connues sont proposees.

    Retaper le nom a la main invite a la faute de frappe, et une faute de
    frappe cree une seconde serie vide : le tome repartirait de zero sans
    rien dire. Le module de serie normalise la casse et les accents, pas les
    lettres manquantes.
    """
    from .core import serie as module_serie

    connues = module_serie.lister()
    if not connues:
        return demander("Serie (Entree pour un recit isole)", "")

    index = choisir(
        "Serie",
        [("recit isole", "aucune suite")]
        + [(s["nom"], "{} tome(s) deja ecrits".format(s["tomes"]))
           for s in connues]
        + [("nouvelle serie...", "en commencer une")],
        defaut=1)
    if index <= 1:
        return ""
    if index <= len(connues) + 1:
        return connues[index - 2]["nom"]
    return demander("Nom de la nouvelle serie", "")


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
            ("Journal", "ce qui s'est passe pendant qu'on ne regardait pas"),
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

        elif choix == 7:
            executer(["journal"])
            demander("\n  Appuyez sur Entree")


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
        # Sans valeur proposee : Entree envoyait « -n 50 », un choix que
        # personne n'avait fait, et l'usine ne decidait plus le nombre.
        question = produit["quantite"][0]
        quantite = demander(question + LAISSER, "")
        if quantite.isdigit():
            options["nombre"] = int(quantite)
    options.update(_options_du_type(produit["cle"]))
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
        ("budget_jetons_jour", "Jetons IA maximum par jour (0 = illimite)"),
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
    # La reprise n'est proposee que si elle a un sens : un produit fini n'a
    # rien a reprendre, et une entree morte dans un menu fait douter de tout
    # le menu.
    inacheve = produit["statut"] == "en_cours"
    actions = [
        ("Voir le detail", "fichiers et etapes de fabrication"),
        ("Generer le kit de vente", "fiche, page de vente, sequence"),
        ("Creer l'archive ZIP", "fichier livrable pour la boutique"),
        ("Ouvrir sur le telephone", "le PDF, dans votre lecteur habituel"),
        ("Partager l'archive", "vers Drive, un courriel, Telegram..."),
    ]
    # Les numeros ne sont pas fixes : « Reprendre » n'apparait que pour un
    # produit inacheve. On les retient au moment ou on les ajoute, plutot que
    # de les recalculer plus bas — c'est la que le decalage se glisse.
    rang_reprendre = 0
    if inacheve:
        manquants = (produit.get("meta") or {}).get("manquants") or []
        actions.append(("Reprendre la fabrication",
                        "{} section(s) a finir, sans repayer le reste"
                        .format(len(manquants)) if manquants
                        else "finir ce qui manque"))
        rang_reprendre = len(actions)
    actions.append(("Effacer ce produit", "la fiche et le dossier, definitivement"))
    rang_effacer = len(actions)
    action = choisir("« {} »".format(produit["titre"][:38]), actions)
    if action == 1:
        entete(produit["titre"][:44])
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
    elif action == 4:
        _ouvrir_produit(produit)
        demander("\n  Appuyez sur Entree")
    elif action == 5:
        _partager_produit(produit, executer)
        demander("\n  Appuyez sur Entree")
    elif action == rang_reprendre:
        executer(["reprendre", produit["id"]])
        demander("\n  Appuyez sur Entree")
    elif action == rang_effacer:
        _effacer_produit(produit, executer)


def _effacer_produit(produit: Dict[str, Any],
                     executer: Callable[[List[str]], int]) -> None:
    """Demande confirmation ici plutot que de laisser la CLI la demander.

    La CLI lit la reponse sur l'entree standard ; le menu aussi. Enchainer les
    deux ferait poser la question deux fois, et la seconde mangerait la touche
    Entree de la premiere.
    """
    entete("Effacer « {} »".format(produit["titre"][:40]))
    print("  Type   : {}".format(produit["type"]))
    print("  Statut : {}".format(produit["statut"]))
    print("  Dossier: {}".format(produit["dossier"]))
    print()
    print(c("  Cette suppression est definitive.", "33"))
    if demander("  Taper EFFACER pour confirmer").strip() != "EFFACER":
        print("  Annule.")
        demander("\n  Appuyez sur Entree")
        return
    executer(["supprimer", produit["id"], "--oui"])
    demander("\n  Appuyez sur Entree")


def _fichier_a_ouvrir(dossier: Path) -> Optional[Path]:
    """Le PDF principal du produit, ou a defaut ce qui se lit le mieux.

    Les annexes portent le meme nom de base suivi d'un tiret
    (« guide-annexe.pdf ») : trier les noms mettrait l'annexe en tete, le
    tiret triant avant le point. On prend donc le plus GROS, qui est le
    document principal dans tous les cas observes.
    """
    for motif in ("*.pdf", "*.epub", "*.html"):
        trouves = [f for f in dossier.glob(motif) if f.is_file()]
        if trouves:
            return max(trouves, key=lambda f: f.stat().st_size)
    return None


def _sans_termux_api(outil: str) -> None:
    print(c("     {} n'est pas disponible ici.".format(outil), "33"))
    print("     Sur Termux : " + c("pkg install termux-api", "1")
          + " (et l'application Termux:API)")


def _ouvrir_produit(produit: Dict[str, Any]) -> None:
    from .core import telephone

    dossier = Path(produit["dossier"])
    cible = _fichier_a_ouvrir(dossier) if dossier.exists() else None
    if cible is None:
        print(c("     Aucun fichier lisible dans ce produit.", "33"))
        return
    print("  Ouverture de {}...".format(cible.name))
    if not telephone.ouvrir(cible):
        _sans_termux_api("termux-open")
        print("     Chemin du fichier : " + str(cible))


def _partager_produit(produit: Dict[str, Any],
                      executer: Callable[[List[str]], int]) -> None:
    """Pousse l'archive vers une application Android.

    Sans archive, on propose de la creer : c'est le geste que l'utilisateur
    voulait faire, et l'envoyer chercher la commande « livrer » pour revenir
    ici serait un detour inutile.
    """
    from .core import telephone

    dossier = Path(produit["dossier"])
    archives = sorted(dossier.glob("*.zip"), key=lambda f: f.stat().st_mtime)
    if not archives:
        print(c("     Ce produit n'a pas encore d'archive.", "33"))
        if not demander_oui("     La creer maintenant ?"):
            return
        executer(["livrer", produit["id"]])
        archives = sorted(dossier.glob("*.zip"), key=lambda f: f.stat().st_mtime)
        if not archives:
            return
    archive = archives[-1]
    print("  Partage de {} ({} Ko)...".format(
        archive.name, archive.stat().st_size // 1024))
    if not telephone.partager(archive, produit["titre"][:60]):
        _sans_termux_api("termux-share")
        print("     Chemin de l'archive : " + str(archive))


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


def _choisir_theme(actuelle: str) -> Optional[str]:
    """Les peaux du tableau de bord, lues la ou elles sont declarees.

    Les recopier ici en ferait une seconde liste — et c'est celle du menu qui
    proposerait encore une peau retiree six mois plus tot.
    """
    cles = [t["cle"] for t in reglages.THEMES]
    index = choisir("Peau du tableau de bord", [
        (t["nom"], t["description"]) for t in reglages.THEMES
    ], defaut=rang(cles, actuelle, 1))
    return cles[index - 1] if index else None


# Ces quatre reglages ont des valeurs qui veulent dire quelque chose ailleurs
# dans l'usine. Les faire taper au clavier laissait enregistrer « rapidos »,
# qui vaut « standard » partout sans que rien ne le dise — ou un theme qui
# n'existe pas, et la page s'affichait alors sans aucune couleur.
_A_CHOISIR = {"ton": _choisir_ton, "taille": _choisir_taille,
              "qualite": _choisir_qualite, "theme": _choisir_theme}


def menu_series(executer: Callable[[List[str]], int]) -> None:
    """Les suites en cours, et la seule action qui rapporte : rafraichir.

    Un tome fabrique quand il etait le dernier porte une derniere page qui
    n'annonce rien de ce qui est venu apres. Or c'est le lecteur du tome 1 —
    celui qui a paye en premier et qui est revenu — qui ne voit rien.
    """
    from .core import serie as module_serie

    while True:
        effacer()
        entete("Mes series")
        series = module_serie.lister()
        if not series:
            print("  Aucune serie pour l'instant.\n")
            print("  Une serie commence a son premier tome : choisissez")
            print("  « Fabriquer un produit », puis « Nouvelle ».")
            demander("\n  Appuyez sur Entree")
            return

        entrees = []
        for ligne in series:
            attente = module_serie.tomes_a_rafraichir(ligne["nom"])
            entrees.append((ligne["nom"], "{} tome(s){}".format(
                ligne["tomes"],
                ", {} a rafraichir".format(len(attente)) if attente else "")))
        index = choisir("Series", entrees, defaut=1)
        if index == 0:
            return
        nom = series[index - 1]["nom"]

        while True:
            effacer()
            entete("Serie « {} »".format(nom))
            executer(["series", nom])
            action = choisir("Que faire", [
                ("Rafraichir les derniers tomes",
                 "leur derniere page annoncera les tomes parus depuis"),
                ("Ecrire le tome suivant", "reprend le monde et la distribution"),
            ], defaut=1)
            if action == 0:
                break
            if action == 1:
                executer(["series", nom, "--rafraichir"])
                demander("\n  Appuyez sur Entree")
            elif action == 2:
                sujet = demander("Sujet du tome suivant", obligatoire=True)
                if sujet:
                    executer(["nouvelle", sujet, "--serie", nom])
                demander("\n  Appuyez sur Entree")


def menu_reglages() -> None:
    while True:
        entete("Reglages")
        # Par groupe, et dans l'ordre du module : trente reglages a plat
        # etaient illisibles sur un ecran de telephone, et rien ne disait
        # lesquels allaient ensemble. Les groupes viennent de « reglages »,
        # pas d'ici : le tableau de bord montre exactement les memes.
        lignes = reglages.lignes_affichables()
        groupe_courant = ""
        for numero, ligne in enumerate(lignes, 1):
            if ligne["groupe"] != groupe_courant:
                groupe_courant = ligne["groupe"]
                print()
                print("  " + c(ligne["titre_groupe"], "1;36"))
                print("  " + c(ligne["aide_groupe"], "2"))
            print("  {:>2}. {:<30} {}".format(
                numero, ligne["etiquette"], c(ligne["valeur"][:24], "1")))
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
            nouvelle = demander_oui("Activer « {} »".format(ligne["etiquette"]),
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
        # « ? » et non « 0 » : une base illisible n'est pas une journee sans
        # appel, et c'est ce menu qu'on regarde quand on doute de son quota.
        jour = "?" if ligne["aujourdhui"] is None else ligne["aujourdhui"]
        print("  {:<13} {:<11} {:>4}/{:<6} {}".format(
            ligne["nom"], c(etat, couleur), jour, ligne["rpd"],
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


# --------------------------------------------------------------------------
# Les cinq sections du menu
# --------------------------------------------------------------------------
#
# Le menu principal a compte jusqu'a dix-sept entrees a plat. Sur un ecran de
# telephone, cela fait deux ecrans et demi a faire defiler pour trouver
# « Reglages » — et surtout, rien n'y disait ce qui allait avec quoi : la
# veille de niche et le cache IA se suivaient sans avoir le moindre rapport.
#
# Cinq sections, donc, et le critere est le MOMENT ou l'on s'en sert :
# fabriquer, regarder ce qu'on a fabrique, comprendre le marche, regler,
# entretenir la machine. Une entree qui n'entre dans aucune de ces cinq n'a
# probablement rien a faire dans le menu principal.


def _menu_fabrication(executer: Callable[[List[str]], int]) -> None:
    while True:
        compte = file_prod.compter()
        en_file = compte["en_attente"] + compte["en_cours"]
        choix = choisir("Fabriquer", [
            ("Un produit", "ebook, roman, formation, imprimable, logiciel..."),
            ("Trouver des idees", "explorer une niche et en tirer des sujets"),
            ("Produire en boucle", "{} niche(s) en file".format(en_file)
             if en_file else "l'usine enchaine seule"),
        ])
        if choix == 0:
            return
        if choix == 1:
            menu_fabriquer(executer)
        elif choix == 2:
            # Facultatif ici aussi : sans niche, l'exploration part de ce que
            # l'usine trouve elle-meme.
            sujet = demander("Quelle niche explorer (facultatif)", "")
            executer(["idees", sujet] if sujet else ["idees"])
            demander("\n  Appuyez sur Entree")
        elif choix == 3:
            menu_usine(executer)


def _menu_mes_produits(executer: Callable[[List[str]], int]) -> None:
    while True:
        produits = [p for p in store.lister_produits(50)
                    if p["statut"] != "bonus_integre"]
        inacheves = [p for p in produits if p["statut"] == "en_cours"]
        choix = choisir("Mes produits", [
            ("La liste", "{} produit(s){}".format(
                len(produits),
                ", dont {} inacheve(s)".format(len(inacheves))
                if inacheves else "")),
            ("Mes series", "suites en cours, et leur derniere page"),
            ("Tests A/B", "titres et couvertures : comparer et decider"),
        ])
        if choix == 0:
            return
        if choix == 1:
            menu_produits(executer)
        elif choix == 2:
            menu_series(executer)
        elif choix == 3:
            menu_ab(executer)


def _menu_marche(executer: Callable[[List[str]], int]) -> None:
    while True:
        choix = choisir("Comprendre le marche", [
            ("Veille de niche", "ce que les gens disent vraiment d'un sujet"),
            ("Mesurer un marche", "volumes reels sur quatre sources publiques"),
            ("Mes ventes", "importer un export, voir ce qui rapporte"),
            ("Doublons", "les produits qui se recouvrent"),
            ("Ce que l'usine a appris", "quel type, quel ton, quelle qualite"),
        ])
        if choix == 0:
            return
        if choix == 1:
            sujet = demander("Quelle niche explorer", obligatoire=True)
            if sujet:
                executer(["veille", sujet])
            demander("\n  Appuyez sur Entree")
        elif choix == 2:
            sujet = demander("Quel marche mesurer", obligatoire=True)
            if sujet:
                executer(["marche", sujet])
            demander("\n  Appuyez sur Entree")
        elif choix == 3:
            menu_ventes(executer)
        elif choix == 4:
            executer(["doublons"])
            demander("\n  Appuyez sur Entree")
        elif choix == 5:
            executer(["bilan"])
            demander("\n  Appuyez sur Entree")


def _menu_reglages_general(executer: Callable[[List[str]], int]) -> None:
    while True:
        choix = choisir("Reglages", [
            ("Vos reglages", "auteur, marque, ton, qualite, budget"),
            ("Cles et quotas", "etat des fournisseurs et du pool de cles"),
            ("Prompts et agents", "personnaliser les voix de l'equipe"),
            ("Cache IA", "reponses gardees, catalogues des fournisseurs"),
        ])
        if choix == 0:
            return
        if choix == 1:
            menu_reglages()
        elif choix == 2:
            menu_cles()
        elif choix == 3:
            _menu_prompts(executer)
        elif choix == 4:
            _menu_cache(executer)


def _menu_machine(executer: Callable[[List[str]], int]) -> None:
    while True:
        choix = choisir("La machine", [
            ("Diagnostic complet", "verifier toute l'installation"),
            ("Fiche technique", "ce qui manque a CET appareil, en Markdown"),
            ("Mettre a jour", "recuperer la derniere version du depot"),
            ("Sauvegarder l'atelier", "ventes et historique dans une archive"),
        ])
        if choix == 0:
            return
        if choix == 1:
            executer(["docteur"])
        elif choix == 2:
            executer(["specs"])
        elif choix == 3:
            executer(["maj"])
        elif choix == 4:
            executer(["sauvegarde"])
        demander("\n  Appuyez sur Entree")


def etat_des_fournisseurs() -> str:
    """La ligne d'accueil : combien de fournisseurs ont une cle.

    Une cle, pas un genre de fournisseur : un jeton Pollinations en est une,
    et le compter pour rien faisait dire « Aucune cle API » a qui en avait.
    """
    disponibles = config.active_providers()
    distants = [p for p in disponibles if not p.local]
    avec_cle = [p for p in distants if p.nb_cles()]
    if avec_cle:
        return ("  " + c("v", "32") + " {} fournisseur(s) avec cle, "
                "rotation active".format(len(avec_cle)))
    if distants:
        return "  " + c("!", "33") + " Aucune cle API : quota tres limite"
    return "  " + c("x", "31") + " Aucun fournisseur — voir « Cles et quotas »"


def menu_principal(executer: Callable[[List[str]], int]) -> int:
    while True:
        effacer()
        entete("USINE-IA  v{}".format(__version__))
        print(etat_des_fournisseurs())
        produits = [p for p in store.lister_produits(50)
                    if p["statut"] != "bonus_integre"]
        print("  " + c("*", "36") + " {} produit(s) fabrique(s)".format(len(produits)))

        compte = file_prod.compter()
        if compte["en_attente"] or compte["en_cours"]:
            print("  " + c("~", "33") + " {} niche(s) en file".format(
                compte["en_attente"] + compte["en_cours"]))

        choix = choisir("Menu principal", [
            ("Fabriquer", "un produit, tout de suite"),
            # Separee de « Fabriquer » — comme dans le tableau de bord, et
            # pour la meme raison : cachee en deuxieme ligne d'un sous-menu,
            # la seule fonction qui produit sans qu'on dicte quoi que ce soit
            # etait la moins visible de l'usine.
            ("Produire en boucle", "l'usine enchaine seule, sous budget"),
            ("Mes produits", "consulter, reprendre, vendre, effacer"),
            ("Comprendre le marche", "veille, volumes reels, ventes, doublons"),
            ("Reglages", "auteur, ton, qualite, cles, agents"),
            ("La machine", "diagnostic, sauvegarde, mise a jour, fiche technique"),
            ("Tableau de bord", "l'interface visuelle, dans le navigateur"),
        ], defaut=1, retour="Quitter")

        if choix == 0:
            print("\n  A bientot.\n")
            return 0
        if choix == 1:
            _menu_fabrication(executer)
        elif choix == 2:
            menu_usine(executer)
        elif choix == 3:
            _menu_mes_produits(executer)
        elif choix == 4:
            _menu_marche(executer)
        elif choix == 5:
            _menu_reglages_general(executer)
        elif choix == 6:
            _menu_machine(executer)
        elif choix == 7:
            executer(["web"])

