"""Interface en ligne de commande de l'Usine-IA.

Usage : usine <commande> [arguments]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .core import apprentissage, budget, config, experience, images
from .core import file as file_prod
from .core import llm, marche
from .core import prompts as registre_prompts
from .core import empreinte, reglages, securite, store, telephone, ventes
from .core import verification
from .marketing import vente
from .packaging import livraison
from .pipelines import apres
from .pipelines import boite_outils, catalogue, ebook, logiciel, social
from .pipelines.base import (CHAPITRES_MAX, CHAPITRES_MIN, MOTS_MAX, MOTS_MIN,
                             TAILLES, TONS, Contexte, code_langue)

# Couleurs ANSI : Termux les gere, mais on s'abstient si la sortie est redirigee.
_COULEUR = sys.stdout.isatty()


def _c(texte: str, code: str) -> str:
    return "\033[{}m{}\033[0m".format(code, texte) if _COULEUR else texte


def _compte(valeur: Optional[int]) -> str:
    """Un compteur du jour, ou « ? » quand la base ne se lit plus.

    Ecrire « 0 » serait plus joli et faux : zero appel et compteur illisible
    ne demandent pas la meme chose a l'utilisateur.
    """
    return "?" if valeur is None else str(valeur)


def _milliers(nombre: int) -> str:
    """Nombre lisible a l'oeil : 200000 devient « 200 000 »."""
    return "{:,}".format(int(nombre)).replace(",", "\u202f")


def titre_console(texte: str) -> None:
    print("\n" + _c("== " + texte, "1;36"))


def ok(texte: str) -> None:
    print(_c("  [ok] ", "32") + texte)


def alerte(texte: str) -> None:
    print(_c("  [!] ", "33") + texte)


def dire_la_prose(resume: Dict[str, Any]) -> None:
    """Les releves de prose, a l'ecran, et jamais en alerte.

    Ce sont des COMPTES, pas des verdicts : « six mots filtres », « doucement
    onze fois ». Les passer par « alerte » ferait clignoter en jaune un texte
    qui n'a rien de fautif, et un signal jaune qui se declenche a chaque
    production finit ignore — y compris les fois ou il dit quelque chose.
    """
    mesure = resume.get("prose") or {}
    if mesure.get("mots"):
        from .pipelines import prose as module_prose

        print("  " + module_prose.situer_le_dialogue(
            mesure.get("part_de_dialogue") or 0.0))
    for lecture in resume.get("lectures_prose") or []:
        print("  " + _c("[prose] ", "36") + lecture)


def erreur(texte: str) -> None:
    print(_c("  [x] ", "31") + texte, file=sys.stderr)


BANNIERE = r"""
  _   _     _              ___    _
 | | | |___(_)_ _  ___ ___|_ _|  /_\
 | |_| (_-< | ' \/ -_)___ | |  / _ \
  \___//__/_|_||_\___|    |___/_/ \_\   v{version}
  fabrique de produits digitaux — tourne sur Termux
"""


class SujetIntrouvable(Exception):
    """L'usine devait choisir une niche et n'a pas pu.

    Rendre une chaine vide etait la premiere version, et c'etait un defaut :
    la fabrication CONTINUAIT avec un sujet vide. Elle annoncait « aucune
    niche a proposer », puis sondait un marche pour «  », lancait une veille
    pour «  », et mourait une minute plus tard sur un message sans rapport.
    Quatre appels reseau et beaucoup de confusion apres avoir deja dit qu'elle
    s'arretait.
    """


def sujet_ou_choix(args: argparse.Namespace) -> str:
    """Le sujet donne, ou celui que l'usine choisit quand on n'en donne pas.

    Un seul endroit pour les dix chaines : le mettre dans chaque commande
    aurait garanti qu'une d'elles l'oublie, et personne ne s'en apercevrait
    avant de taper « usine social » sans rien derriere.
    """
    sujet = (getattr(args, "sujet", "") or "").strip()
    if sujet:
        return sujet
    from .production import choisir_une_niche

    titre_console("L'usine choisit la niche")
    choix = choisir_une_niche(journal=lambda m: print("  " + m),
                              type_produit=getattr(args, "_type", "ebook"))
    if not choix["sujet"]:
        raise SujetIntrouvable(
            "L'usine devait choisir une niche et n'a pas pu.")
    if choix.get("source") == "froid" and not choix.get("mesure", True):
        # Un domaine propose et non mesure reste un choix du modele. Le dire
        # ici est le seul moment ou cela change quelque chose pour celui qui
        # decide de continuer ou non.
        alerte("Aucune source de marche n'a repondu : cette niche est "
               "proposee, pas mesuree.")
    args.sujet = choix["sujet"]
    # Les reglages de fiction voyagent avec la promesse : ils sont poses sur
    # « args » pour que « contexte_depuis » les trouve comme s'ils avaient ete
    # tapes. Sans cela la chaine les re-devinerait a partir du seul titre.
    for cle, valeur in (choix.get("options") or {}).items():
        if not getattr(args, cle, ""):
            setattr(args, cle, valeur)
    return choix["sujet"]


def contexte_depuis(args: argparse.Namespace) -> Contexte:
    """Construit le contexte : options de la commande, puis reglages, puis defauts."""
    # Une reprise d'abord, et avant tout le reste : c'est le contexte de la
    # premiere fabrication qui fait foi. Passer par « sujet_ou_choix » avec
    # un sujet laisse vide a l'origine faisait choisir une NOUVELLE niche,
    # ecrite ensuite dans le dossier de l'ancienne.
    reprise = getattr(args, "reprendre_id", "") or ""
    if reprise:
        from .pipelines import reprise as module_reprise

        garde = module_reprise.contexte_garde(
            reprise, journal=lambda message: print("  " + message))
        if garde is not None:
            return garde
    # Le sujet d'abord, et ici plutot que dans chaque commande : les quatorze
    # chaines passent toutes par cette fonction, et aucune autre ligne n'est
    # commune aux quatorze. Une niche choisie par l'usine doit ensuite passer
    # les memes controles qu'une niche tapee a la main — dont l'avertissement
    # sur les domaines ou un produit genere expose son vendeur.
    sujet_ou_choix(args)
    _avertir_sujet(getattr(args, "sujet", "") or "")
    profil = reglages.charger()

    def choisir(nom: str, defaut_profil: str) -> str:
        valeur = getattr(args, nom, None)
        return valeur if valeur else profil.get(defaut_profil, "")

    # « --reprendre-id » fait ecrire la fabrication dans le dossier d'un
    # produit existant au lieu d'en creer un neuf. C'est tout ce qui separe
    # une reprise d'une relance : le carnet qui s'y trouve fait le reste.
    contexte = Contexte(
        sujet=args.sujet,
        audience=choisir("audience", "audience"),
        langue=choisir("langue", "langue"),
        ton=choisir("ton", "ton"),
        taille=choisir("taille", "taille"),
        auteur=choisir("auteur", "auteur"),
        qualite=choisir("qualite", "qualite"),
        chapitres=int(getattr(args, "chapitres", 0) or 0),
        mots_section=int(getattr(args, "mots", 0) or 0),
        prix=getattr(args, "prix", "") or "",
        marque=getattr(args, "marque", "") or profil.get("marque", ""),
        dedicace=getattr(args, "dedicace", "") or "",
        hors_ligne=args.hors_ligne,
        sans_image=args.sans_image or args.hors_ligne or not profil.get("images", True),
        journal=lambda message: print("  " + message),
    )
    if reprise:
        # Produit d'avant le contexte garde au carnet : on reprend depuis les
        # arguments. Sans rebriefer — redecider donnerait au second tiers du
        # livre un autre ton que le premier.
        contexte.produit_id = reprise
        contexte.dossier = config.PRODUITS_DIR / reprise
        return contexte
    # Ce que l'utilisateur n'a pas choisi, l'usine le decide en lisant le
    # sujet — ici, en un seul endroit, pour les dix chaines a la fois.
    from .pipelines import brief

    brief.completer(contexte, getattr(args, "commande", "produit"), args)
    return contexte


def _avertir_sujet(sujet: str) -> None:
    """Signale les domaines ou un produit genere expose son vendeur."""
    for domaine, avertissement in securite.analyser_sujet(sujet):
        alerte("Domaine sensible detecte : {}".format(domaine))
        print("      " + avertissement)


def _verifier_fournisseurs() -> bool:
    disponibles = config.active_providers()
    if disponibles:
        distants = [p.name for p in disponibles if not p.local]
        locaux = [p.name for p in disponibles if p.local]
        details = []
        if distants:
            details.append("API : " + ", ".join(distants))
        if locaux:
            details.append("local : " + ", ".join(locaux))
        ok("Fournisseurs actifs — " + " | ".join(details))
        avec_cle = [p for p in disponibles if not p.local and not p.keyless]
        if not avec_cle and not locaux:
            alerte("Seul Pollinations est disponible : son quota anonyme est partage "
                   "par adresse IP et s'epuise vite.")
            alerte("Pour fabriquer un produit entier, ajoutez une cle gratuite : "
                   + _c("usine cles", "1"))
        return True
    erreur("Aucun fournisseur IA disponible.")
    print("\n  Lancez " + _c("usine cles", "1") + " pour obtenir une cle gratuite "
          "en 2 minutes,\n  ou demarrez une IA locale (voir " +
          _c("usine docteur", "1") + ").")
    return False


# --------------------------------------------------------------------------
# Commandes de fabrication
# --------------------------------------------------------------------------


def _tranche(args: argparse.Namespace, option: str) -> Optional[bool]:
    """Ce que la ligne de commande dit d'une etape facultative.

    Trois etats, et c'est ce qui compte : « --zip » veut oui, « --sans-zip »
    veut non, et l'absence des deux veut « None » — laisse le reglage decider.
    Ecraser ce troisieme etat par « False » rendrait le reglage inapplicable,
    ce qui est la facon la plus discrete de creer un reglage orphelin.
    """
    if getattr(args, "sans_" + option, False):
        return False
    if getattr(args, option, False):
        return True
    return None


def _apres_production(args: argparse.Namespace, ctx: Contexte,
                      resume: Dict[str, Any], description: str) -> Dict[str, Any]:
    """Kit de vente + archive, si demandes.

    Le travail lui-meme vit dans « pipelines/apres.py », parce que le tableau
    de bord doit faire exactement la meme chose : il l'a longtemps ignore, et
    quatre reglages coches depuis le telephone ne produisaient rien. Ici ne
    restent que la lecture des options de la ligne de commande et l'affichage.
    """
    if not (getattr(args, "contact", "") or reglages.lire("contact", "")):
        # La notice promet d'envoyer une version adaptee a qui en demande une.
        # C'est ce que la reglementation europeenne d'accessibilite attend
        # d'etre tenu — et sans adresse, la promesse n'est pas ecrite. Le
        # vendeur doit le savoir : c'est lui qui decide, pas nous.
        alerte("Aucune adresse de contact : la notice livree ne propose donc "
               "pas de version adaptee aux lecteurs qui en auraient besoin.")
        print("      " + _c("usine reglages", "1")
              + "  ou  " + _c("--contact vous@exemple.fr", "1"))
    # « --marketing » force, « --sans-marketing » empeche, et sans les deux on
    # laisse le reglage decider. Un vendeur qui empaquette toujours ses
    # produits retapait « --zip » cent fois ; celui qui ne le fait jamais
    # n'avait pas a le voir.
    veut_kit = _tranche(args, "marketing")
    veut_zip = _tranche(args, "zip")
    if veut_kit is not False:
        titre_console("Kit de vente")
    return apres.apres_production(
        ctx, resume, description,
        type_produit=getattr(args, "commande", "ebook"),
        kit=veut_kit, archive=veut_zip,
        plateforme=getattr(args, "plateforme", ""),
        extrait=getattr(args, "extrait", 0),
        contact=getattr(args, "contact", ""),
        journal=ok,
    )


def _resume_console(resume: Dict[str, Any]) -> None:
    titre_console("Produit livre")
    print("  " + _c(resume["titre"], "1"))
    print("  Dossier : " + resume["dossier"])
    for nom in resume.get("fichiers", []):
        print("    - " + nom)
    if resume.get("archive"):
        print("  Archive : " + resume["archive"])
    a_ouvrir = next(
        (Path(resume["dossier"]) / n for n in resume.get("fichiers", [])
         if n.endswith(".pdf")), Path(resume["dossier"]))
    print("\n  Ouvrir sur Termux : " + _c(
        "termux-open '{}'".format(a_ouvrir), "2"))
    # Une fabrication dure 10 a 20 minutes : personne ne regarde le terminal
    # pendant ce temps. La notification est ce qui rappelle le telephone.
    if reglages.lire("notifications", True):
        telephone.notifier("Produit pret", resume["titre"][:70], ouvrir=a_ouvrir)


def cmd_ebook(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un ebook")
    resume = _par_le_catalogue(
        args, "ebook", ctx,
        relecture_ensemble=(getattr(args, "relecture_ensemble", False)
                            or bool(reglages.lire("relecture_ensemble", False))))
    description = "Ebook de {} chapitres, {} mots. {}".format(
        resume["chapitres"], resume["mots"], resume.get("sous_titre", "")
    )
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_nouvelle(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une nouvelle")
    resume = _par_le_catalogue(args, "nouvelle", ctx)
    description = "Nouvelle{}, {} scenes, {} mots.".format(
        " — " + resume["sous_titre"] if resume.get("sous_titre") else "",
        resume["scenes"], resume["mots"])
    if resume.get("rang"):
        description = "Tome {} de « {} ». ".format(
            resume["rang"], args.serie) + description
    dire_la_prose(resume)
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_roman(args: argparse.Namespace) -> int:
    """Un roman : la meme chaine que la nouvelle, a l'echelle du format.

    Il etait deja fabricable et invisible — « usine nouvelle --chapitres 40 » —
    donc inexistant pour qui ne lit pas le code.
    """
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un roman")
    print("  Trente scenes relues et controlees : comptez une a trois heures.")
    print("  Une coupure ne perd rien : " + _c("usine reprendre", "1")
          + " finit ce qui manque.")
    resume = _par_le_catalogue(args, "roman", ctx)
    description = "Roman{}, {} scenes, {} mots.".format(
        " — " + resume["sous_titre"] if resume.get("sous_titre") else "",
        resume["scenes"], resume["mots"])
    dire_la_prose(resume)
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    """Ce que l'usine a fait pendant qu'on ne regardait pas."""
    from .core import trace

    jours = trace.jours_disponibles()
    if not jours:
        print("  Aucun journal pour l'instant. Il s'ecrit pendant une")
        print("  production continue : " + _c("usine usine demarrer", "1"))
        return 0
    jour = args.jour or jours[0]
    if jour not in jours:
        alerte("Aucun journal pour le {}. Disponibles : {}".format(
            jour, ", ".join(jours[:7])))
        return 1
    lignes = trace.relire(args.lignes, jour)
    titre_console("Journal du {}".format(jour))
    for ligne in lignes:
        print("  " + ligne)
    if len(jours) > 1:
        print("\n  " + _c("Autres jours : " + ", ".join(jours[1:7]), "90"))
    return 0


def cmd_series(args: argparse.Namespace) -> int:
    """Ce que l'usine a accumule pour chaque suite en cours."""
    from .core import serie as module_serie

    if args.nom and getattr(args, "rafraichir", False):
        from .pipelines import nouvelle as chaine_nouvelle

        if not module_serie.lire(args.nom):
            alerte("Aucune serie « {} ».".format(args.nom))
            return 1
        titre_console("Rafraichissement de « {} »".format(args.nom))
        refaits = chaine_nouvelle.rafraichir_serie(args.nom, journal=print)
        if not refaits:
            ok("Aucun tome anterieur a refaire : leur page de fin est a jour.")
            return 0
        ok("{} tome(s) refaits. Leur derniere page annonce desormais les "
           "tomes parus depuis.".format(len(refaits)))
        print("      Redeposez ces fichiers chez votre distributeur pour que "
              "les lecteurs les voient.")
        return 0

    if args.nom:
        bible = module_serie.lire(args.nom)
        if not bible:
            alerte("Aucune serie « {} ». Elle naitra au premier tome : "
                   "usine nouvelle \"...\" --serie \"{}\"".format(
                       args.nom, args.nom))
            return 1
        titre_console("Serie « {} »".format(bible.get("nom") or args.nom))
        cadre = bible.get("cadre") or {}
        if cadre.get("lieu") or cadre.get("epoque"):
            print("  Cadre : {} — {}".format(cadre.get("lieu") or "?",
                                             cadre.get("epoque") or "?"))
        for regle in cadre.get("regles") or []:
            print("  Regle : " + regle)
        if bible.get("personnages"):
            titre_console("Distribution")
            for personnage in bible["personnages"]:
                faits = (bible.get("faits") or {}).get(personnage.get("nom"), {})
                print("  {:<24} {:<14} {}".format(
                    personnage.get("nom", ""), personnage.get("role", ""),
                    _c(", ".join("{} : {}".format(a, v)
                                 for a, v in sorted(faits.items())), "90")))
        titre_console("Tomes")
        for tome in bible.get("tomes") or []:
            print("  {}. {}".format(tome.get("rang"), tome.get("titre")))
            if tome.get("resume"):
                print("     " + _c(tome["resume"][:160], "90"))
        # Le lecteur du tome 1 est celui qui a paye en premier et qui revient.
        # Sa derniere page ne connait pourtant aucun des tomes suivants.
        attente = module_serie.tomes_a_rafraichir(args.nom)
        if attente:
            print()
            alerte("{} tome(s) ont une derniere page qui n'annonce pas les "
                   "suivants.".format(len(attente)))
            print("      " + _c('usine series "{}" --rafraichir'.format(args.nom), "1"))
        return 0

    series = module_serie.lister()
    if not series:
        print("Aucune serie. Une serie commence a son premier tome :")
        print("  " + _c('usine nouvelle "votre idee" --serie "Nom de la serie"', "1"))
        return 0
    titre_console("Series")
    for ligne in series:
        print("  {:<28} {} tome(s), {} personnage(s)".format(
            ligne["nom"], ligne["tomes"], ligne["personnages"]))
    print("\n  Detail : " + _c("usine series \"<nom>\"", "1"))
    return 0


def cmd_auto(args: argparse.Namespace) -> int:
    """L'usine choisit la niche ET le type de produit.

    Les dix commandes de fabrication demandent un type : « usine ebook »,
    « usine social ». Choisir le type suppose deja de savoir ce qui se vend
    dans une niche qu'on n'a pas encore cherchee — c'est l'ordre inverse de
    celui dans lequel la question se pose.

    Il manquait donc le point d'entree ou l'usine decide des deux. Une idee
    trouvee par la chaine « idees » porte deja son type ; il n'etait suivi
    nulle part, parce que rien ne savait quoi en faire.
    """
    if not _verifier_fournisseurs():
        return 2
    from .production import AUTO, choisir_une_niche

    donne = (getattr(args, "sujet", "") or "").strip()
    if donne:
        # Sujet impose : il ne reste que le type a decider, et c'est la
        # question la plus utile — celle que les dix autres commandes
        # obligent a trancher AVANT de savoir ce qui se vend.
        titre_console("L'usine choisit le type de produit")
        args._type = "ebook"
        ctx_choix = contexte_depuis(args)
        cle = catalogue.type_pour_sujet(ctx_choix, donne)
        choix = {"sujet": donne, "type": cle, "source": "sujet donne"}
    else:
        titre_console("L'usine choisit la niche et le type")
        choix = choisir_une_niche(journal=lambda m: print("  " + m),
                                  type_produit=AUTO)
        if not choix["sujet"]:
            raise SujetIntrouvable(
                "L'usine devait choisir une niche et n'a pas pu.")
    fiche = catalogue.obtenir(choix["type"]) or catalogue.obtenir("ebook")
    ok("Type retenu : {} — « {} »".format(fiche.nom, choix["sujet"]))
    if choix.get("source") == "froid" and not choix.get("mesure", True):
        alerte("Aucune source de marche n'a repondu : cette niche est "
               "proposee, pas mesuree.")
    args.sujet = choix["sujet"]
    args._type = fiche.cle
    ctx = contexte_depuis(args)
    titre_console("Fabrication : {}".format(fiche.nom))
    # Les options propres au type gardent leurs valeurs par defaut : personne
    # n'a pu les donner, puisque le type vient d'etre decide.
    resume = catalogue.executer(fiche.cle, ctx, _defauts_du_type(fiche))
    _resume_console(_apres_production(args, ctx, resume, fiche.resume))
    return 0


def _par_le_catalogue(args: argparse.Namespace, cle: str, ctx: Contexte,
                      **supplement: Any) -> Dict[str, Any]:
    """Fabrique par le point unique du catalogue, avec ce que la commande a fixe.

    Mesure du 24/09/2026 : dix-sept types sur dix-sept, zero reglage decide
    par l'usine en ligne de commande — contre un appel de decision par
    produit depuis le tableau de bord. Chaque commande appelait sa chaine
    directement, avec des valeurs en dur : tout pack de posts partait sur
    LinkedIn, toute sequence d'e-mails etait de « bienvenue », tout quiz de
    niveau « intermediaire », tout roman sans genre choisi. Le menu Termux
    passe par ces commandes : il avait le meme defaut.

    Un argument que personne n'a tape vaut None (voir « _options_du_type ») :
    c'est ce qui le distingue d'une valeur choisie, et ce qui laisse
    « executer » le faire decider a partir du sujet.
    """
    fiche = catalogue.obtenir(cle)
    options: Dict[str, Any] = {}
    for champ in (fiche.champs if fiche else ()):
        valeur = getattr(args, champ.nom, None)
        if valeur is None or valeur == "" or valeur is False:
            continue
        options[champ.nom] = valeur
    options.update(supplement)
    return catalogue.executer(cle, ctx, options)


def _defauts_du_type(fiche) -> Dict[str, Any]:
    """Les valeurs par defaut declarees au catalogue pour ce type.

    Elles sont lues sur la fiche plutot que recopiees : un champ ajoute au
    catalogue arrive ici tout seul. Recopier la liste aurait garanti qu'un
    champ ajoute un jour manque ici sans que rien n'echoue — le type serait
    fabrique avec un zero a la place de sa quantite.
    """
    options: Dict[str, Any] = {}
    if fiche.quantite:
        options["nombre"] = fiche.defaut_quantite
    for champ in fiche.champs:
        if champ.defaut not in (None, ""):
            options[champ.nom] = champ.defaut
    return options


def cmd_prompts(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un pack de prompts")
    resume = _par_le_catalogue(args, "prompts", ctx)
    _resume_console(_apres_production(
        args, ctx, resume, "Pack de {} prompts professionnels.".format(resume["prompts"])
    ))
    return 0


def cmd_emails(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une sequence e-mail")
    resume = _par_le_catalogue(args, "emails", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Sequence de {} messages, etalee sur {} jours.".format(
            resume["messages"], resume["jours"])))
    return 0


def cmd_memo(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un memo")
    resume = _par_le_catalogue(args, "memo", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Memo de {} blocs, {} reperes.".format(
            resume["blocs"], resume["entrees"])))
    return 0


def cmd_quiz(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un quiz")
    resume = _par_le_catalogue(args, "quiz", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Quiz de {} questions, corrige explique.".format(resume["questions"])))
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un livre dont le lecteur est le heros")
    # Comme pour le roman : la quantite arrive par « --chapitres », l'option
    # commune aux types. Un « --sections » propre a ce type ferait deux
    # drapeaux pour le meme chiffre, et le second ecraserait le premier.
    resume = _par_le_catalogue(args, "interactive", ctx)
    description = "{} sections, {} fins.".format(
        resume["sections"], resume["fins"])
    if resume.get("carte_elaguee"):
        # Une degradation se dit a l'ecran, pas seulement dans le JSON : c'est
        # la seule facon que l'utilisateur sache s'il doit refabriquer.
        alerte("La carte a du etre elaguee pour rester jouable.")
    for defaut in resume.get("defauts_restants") or []:
        alerte(defaut)
    dire_la_prose(resume)
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_recueil(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un recueil de nouvelles")
    resume = _par_le_catalogue(args, "recueil", ctx)
    description = "{} nouvelles, {} mots.".format(
        resume["recits"], resume["mots"])
    # La variete est la raison d'etre de cette chaine : elle se dit a l'ecran,
    # pas seulement dans le JSON que personne n'ouvre.
    variete = resume["variete"]
    print("  {} protagoniste(s) distinct(s), {} forme(s) de fin.".format(
        variete["protagonistes_distincts"], variete["fins_distinctes"]))
    proche = variete.get("proximite_maximale") or {}
    if proche.get("titres"):
        print("  Les deux recits les plus proches : « {} » et « {} » "
              "({}).".format(proche["titres"][0][:26],
                             proche["titres"][1][:26], proche["score"]))
    for lecture in resume.get("lectures") or []:
        alerte(lecture)
    dire_la_prose(resume)
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_feuilleton(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un feuilleton")
    resume = _par_le_catalogue(args, "feuilleton", ctx)
    for lecture in resume.get("lectures") or []:
        alerte(lecture)
    if resume.get("episodes_sans_suspens"):
        alerte("Episodes sans suspens declare : {} — le lecteur n'a aucune "
               "raison de revenir.".format(", ".join(
                   str(e) for e in resume["episodes_sans_suspens"])))
    dire_la_prose(resume)
    _resume_console(_apres_production(
        args, ctx, resume,
        "{} episodes, {} mots.".format(resume["episodes"], resume["mots"])))
    return 0


def cmd_conte(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un conte jeunesse")
    resume = _par_le_catalogue(args, "conte", ctx)
    lisibilite = resume["lisibilite"]
    print("  {} mots par phrase en moyenne, pour {} demandes au maximum "
          "({}).".format(lisibilite["mots_par_phrase"],
                         lisibilite["plafond_demande"], resume["tranche"]))
    for lecture in resume.get("lectures") or []:
        alerte(lecture)
    _resume_console(_apres_production(
        args, ctx, resume,
        "{} doubles-pages, {} illustration(s).".format(
            resume["pages"], resume["illustrations"])))
    return 0


def cmd_formation(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une mini-formation")
    resume = _par_le_catalogue(args, "formation", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Mini-formation en {} modules, cahier d'exercices inclus.".format(resume["modules"])
    ))
    return 0


def cmd_outils(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une boite a outils")
    resume = _par_le_catalogue(args, "outils", ctx)
    _resume_console(_apres_production(
        args, ctx, resume, "Boite de {} outils pratiques.".format(resume["outils"])
    ))
    return 0


def cmd_modeles(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication de modeles Notion / tableur")
    resume = _par_le_catalogue(args, "modeles", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Systeme de {} bases liees, CSV prets a importer.".format(resume["bases"])))
    return 0


def cmd_impression(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un cahier imprimable")
    resume = _par_le_catalogue(args, "impression", ctx)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Cahier de {} fiches a imprimer, formats A4 et Lettre US.".format(
            resume["fiches"])))
    return 0


def cmd_logiciel(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un outil logiciel")
    resume = _par_le_catalogue(args, "logiciel", ctx)
    if not resume["code_valide"]:
        alerte("Du code n'a pas passe la verification : voir verification.json")
    etat = "verifie"
    if resume["demarre"] is True:
        etat = "verifie et demarre"
    elif resume["demarre"] is False:
        etat = "verifie, mais l'essai reel a echoue"
    _resume_console(_apres_production(
        args, ctx, resume,
        "{} en {} fichiers, {}.".format(
            logiciel.CIBLES[resume["cible"]]["nom"].capitalize(),
            resume["fichiers_code"], etat)))
    return 0 if resume["code_valide"] else 1


def cmd_ventes(args: argparse.Namespace) -> int:
    """Enregistrer, importer et lire les ventes reelles."""
    if args.importer:
        return _importer_ventes(args)
    if args.ajouter:
        return _ajouter_vente(args)
    if args.lier:
        reference, produit_id = args.lier
        nombre = ventes.lier(reference, produit_id)
        (ok if nombre else alerte)(
            "{} vente(s) rattachee(s) a {}".format(nombre, produit_id))
        return 0 if nombre else 1
    if args.rattacher:
        propositions = ventes.rattacher_automatiquement()
        if not propositions:
            print("  Rien a rattacher : toutes les ventes ont deja leur produit,")
            print("  ou aucun titre connu ne ressemble aux references importees.")
            return 0
        for reference, produit_id, score in propositions:
            ventes.lier(reference, produit_id)
            ok("« {} » -> {} (proximite {:.0%})".format(
                reference[:44], produit_id[:38], score))
        return 0
    return _resume_ventes(args)


def _ajouter_vente(args: argparse.Namespace) -> int:
    if args.brut is None:
        erreur("Precisez le montant encaisse : --brut 29")
        return 1
    ligne = {
        "date": args.date or time.strftime("%Y-%m-%d"),
        "reference": args.reference or args.ajouter,
        "unites": max(1, args.unites), "brut": args.brut, "net": args.net,
        "devise": (args.devise or reglages.lire("devise", "EUR")).upper(),
        "remboursement": 1 if args.remboursement else 0,
        "plateforme": args.plateforme_vente, "source": "manuel",
    }
    ligne["empreinte"] = None       # saisie manuelle : pas de dedoublonnage
    if ventes.enregistrer(ligne, produit_id=args.ajouter):
        ok("{} x {:.2f} {} enregistre pour {}".format(
            ligne["unites"], ligne["brut"], ligne["devise"], args.ajouter))
    return 0


def _importer_ventes(args: argparse.Namespace) -> int:
    chemin = Path(args.importer)
    if not chemin.exists():
        erreur("Fichier introuvable : {}".format(chemin))
        return 1
    lecture = ventes.lire_export(
        chemin.read_text(encoding="utf-8-sig", errors="replace"),
        args.plateforme_vente)

    titre_console("Import — {}".format(chemin.name))
    if lecture.manquants:
        erreur("Colonnes introuvables : {}".format(", ".join(lecture.manquants)))
        print("  Colonnes du fichier : " + ", ".join(lecture.colonnes[:14]))
        print("  Il faut au minimum une date et un montant.")
        return 1

    # La correspondance est AFFICHEE : une association devinee qu'on ne
    # montre pas est une erreur qu'on ne verra jamais.
    print("  Colonnes reconnues :")
    for champ in ("date", "reference", "unites", "brut", "net", "devise",
                  "remboursement", "identifiant"):
        colonne = lecture.correspondance.get(champ)
        print("    {:<14} {}".format(
            champ, colonne if colonne else _c("— absente", "90")))

    ajoutes = sum(1 for ligne in lecture.lignes if ventes.enregistrer(ligne))
    deja = len(lecture.lignes) - ajoutes
    print()
    ok("{} vente(s) ajoutee(s)".format(ajoutes))
    if deja:
        print("  {} deja connue(s) — reimporter le meme export n'ajoute rien."
              .format(deja))
    if lecture.ignorees:
        alerte("{} ligne(s) sans date ou sans montant lisible, ignorees."
               .format(lecture.ignorees))
    if "net" not in lecture.correspondance:
        alerte("Aucune colonne de revenu net : seul le brut sera connu.")
        print("      Le net n'est pas estime — une commission supposee")
        print("      donnerait un revenu qui n'existe pas.")
    propositions = ventes.rattacher_automatiquement()
    if propositions:
        print("\n  Rattachements possibles (usine ventes --rattacher) :")
        for reference, produit_id, score in propositions[:6]:
            print("    « {} » -> {} ({:.0%})".format(
                reference[:40], produit_id[:36], score))
    return 0


def _resume_ventes(args: argparse.Namespace) -> int:
    titre_console("Ventes")
    totaux = ventes.total_par_devise(args.depuis)
    if not totaux:
        print("  Aucune vente enregistree.")
        print("\n  " + _c("usine ventes --importer export.csv --sur gumroad", "1"))
        print("  " + _c("usine ventes --ajouter <produit_id> --brut 29", "1"))
        print("\n  Sans cette donnee, « usine bilan » sait quel ton donne vos")
        print("  meilleures notes, jamais quelle niche a paye.")
        return 0

    for total in totaux:
        net = ("{:.2f}".format(total["net"]) if not total["net_inconnu"]
               else _c("inconnu", "90"))
        print("  {}  {:>4} unites   brut {:>10.2f}   net {}".format(
            _c(total["devise"], "1"), total["unites"] or 0,
            total["brut"] or 0, net))
        if total["net_inconnu"]:
            print("      {} ligne(s) sans revenu net dans l'export.".format(
                total["net_inconnu"]))
        if total["rembourses"]:
            print("      {} remboursement(s), deja deduit(s).".format(
                total["rembourses"]))

    produits = ventes.par_produit(args.nombre)
    if produits:
        titre_console("Par produit")
        for produit in produits:
            print("  {:>8.2f} {}  {:>3} u.  {}".format(
                produit["brut"] or 0, produit["devise"], produit["unites"] or 0,
                (produit["titre"] or produit["produit_id"])[:44]))
    types = ventes.par_champ("type")
    if types:
        titre_console("Par type de produit")
        for ligne in types:
            print("  {:<12} {:>8.2f} {}  sur {} produit(s)".format(
                ligne["valeur"] or "?", ligne["brut"] or 0, ligne["devise"],
                ligne["produits"]))
    prix = ventes.prix_observes()
    if prix:
        titre_console("Prix reellement encaisses")
        for ligne in prix:
            print("  {} : median {:.2f}, moitie centrale {:.2f} a {:.2f}"
                  " ({} ventes)".format(ligne["devise"], ligne["median"],
                                        ligne["bas"], ligne["haut"],
                                        ligne["ventes"]))
    return 0


def cmd_veille(args: argparse.Namespace) -> int:
    """Aller voir ce que les gens disent d'une niche."""
    from .core import veille

    titre_console("Veille — « {} »".format(args.sujet))
    print("  Deux appels espaces : Reddit limite fermement le debit.\n")
    rapport = veille.scouter(args.sujet, periode=args.periode,
                             combien=args.communautes)
    if rapport.indisponible:
        alerte(rapport.indisponible)
        return 1

    print("  " + _c("Communautes", "1"))
    for communaute in rapport.communautes[:8]:
        print("    r/{:<22} {}".format(communaute["nom"][:22],
                                       communaute["titre"][:44]))

    if rapport.mots:
        print("\n  " + _c("Leurs mots", "1"))
        print("    " + ", ".join("{} ({})".format(mot, nombre)
                                 for mot, nombre in rapport.mots))

    douleurs = rapport.douleurs
    if douleurs:
        print("\n  " + _c("Formulations de probleme", "1"))
        for discussion in douleurs[:args.nombre]:
            print("    - {}".format(discussion.titre[:72]))

    print("\n  " + _c("Discussions les plus suivies", "1"))
    for discussion in rapport.discussions[:args.nombre]:
        print("    [{:<14}] {}".format(discussion.communaute[:14],
                                       discussion.titre[:60]))

    print("\n  " + _c("Ce que ceci n'est pas", "33"))
    for ligne in _envelopper(
            "Un signal de DOULEUR, pas d'intention d'achat : on se plaint "
            "gratuitement. Reddit est par ailleurs anglophone et "
            "technophile — une niche francaise peut n'y laisser aucune "
            "trace sans que cela dise rien de son marche.", 68):
        print("    " + ligne)
    print("\n  " + _c('usine idees "{}"'.format(args.sujet[:36]), "1")
          + " s'en sert deja pour formuler les promesses.")
    return 0


def cmd_sauvegarde(args: argparse.Namespace) -> int:
    """Mettre l'atelier a l'abri, ou le remettre en place."""
    from .core import sauvegarde

    if args.restaurer:
        return _restaurer(args, sauvegarde)
    if args.inspecter:
        fiche = sauvegarde.inspecter(Path(args.inspecter))
        titre_console("Contenu de l'archive")
        if not fiche["valide"]:
            erreur(fiche["probleme"])
            return 1
        print("  Creee le      : {}".format(fiche.get("cree_le", "?")))
        print("  Schema        : version {}".format(fiche.get("schema", "?")))
        print("  Reglages      : {}".format(
            "inclus" if fiche.get("avec_reglages") else "absents"))
        print("  Fichiers de produits : {}".format(
            fiche.get("fichiers_produits", 0)))
        print("  Invites personnalisees : {}".format(
            fiche.get("fichiers_invites", 0)))
        return 0

    titre_console("Sauvegarde de l'atelier")
    archive = sauvegarde.creer(
        Path(args.vers) if args.vers else None,
        avec_produits=args.avec_produits)
    taille = archive.stat().st_size
    ok("{} ({} Ko)".format(archive, max(1, taille // 1024)))
    print("\n  Contient l'historique de production, les empreintes, les tests")
    print("  A/B et " + _c("les ventes", "1") + " — c'est cette derniere qui ne")
    print("  se refabrique pas.")
    if not args.avec_produits:
        print("\n  Les fichiers des produits ne sont PAS inclus : "
              + _c("--avec-produits", "1"))
    print("  Les cles API non plus : elles vivent dans .env, et une archive")
    print("  se copie sur un ordinateur ou dans un nuage.")
    print("\n  Copiez-la hors du telephone. Une sauvegarde restee sur")
    print("  l'appareil ne protege de rien.")
    return 0


def _restaurer(args: argparse.Namespace, sauvegarde) -> int:
    chemin = Path(args.restaurer)
    fiche = sauvegarde.inspecter(chemin)
    titre_console("Restauration")
    if not fiche["valide"]:
        erreur(fiche["probleme"])
        return 1
    print("  Archive du {}, schema {}".format(
        fiche.get("cree_le", "?"), fiche.get("schema", "?")))
    if not args.oui:
        alerte("Cette operation remplace l'atelier actuel.")
        print("      L'ancienne base est mise de cote, pas supprimee.")
        print("      Confirmez avec " + _c("--oui", "1"))
        return 1
    resultat = sauvegarde.restaurer(chemin, avec_produits=not args.sans_produits)
    if not resultat["valide"]:
        erreur(resultat["probleme"])
        if "usine continue" in resultat["probleme"]:
            # Deux sessions Termux ouvertes est la situation ordinaire, pas
            # le cas tordu : « --oui » dit qu'on a compris l'operation, pas
            # qu'on veut la lancer sous un produit en cours.
            print("      " + _c("usine usine arreter", "1")
                  + " attend la fin du produit en cours.")
        return 1
    ok("Atelier restaure ({} fichier(s) de produits).".format(
        resultat["fichiers_produits"]))
    if resultat["ancienne_base"]:
        print("  Ancienne base conservee : {}".format(
            resultat["ancienne_base"]))
    return 0


def cmd_doublons(args: argparse.Namespace) -> int:
    """Les produits qui se recouvrent, tous types confondus."""
    if args.reconstruire:
        return _reconstruire_empreintes()
    titre_console("Ce que l'usine a ecrit deux fois")
    empreintes = store.lister_empreintes(args.type or "")
    if len(empreintes) < 2:
        print("  Moins de deux produits enregistres : rien a comparer.")
        print("  Les empreintes sont posees a la fabrication ; les produits")
        print("  fabriques avant cette version n'en ont pas.")
        return 0

    charges = [{
        "produit_id": e["produit_id"], "titre": e["titre"], "sujet": e["sujet"],
        "type": e["type"], "signature": empreinte.decoder(e["signature"]),
        "plan": empreinte.decoder(e["plan"]),
    } for e in empreintes]

    paires = []
    for index, courant in enumerate(charges):
        for autre in charges[index + 1:]:
            if courant["type"] != autre["type"]:
                continue
            voisin = empreinte.Voisin(
                produit_id=autre["produit_id"], titre=autre["titre"],
                sujet=autre["sujet"],
                texte=empreinte.ressemblance(courant["signature"],
                                             autre["signature"]),
                plan=empreinte.ressemblance_plan(courant["plan"], autre["plan"]),
            )
            if voisin.doublon:
                paires.append((courant, voisin))
    paires.sort(key=lambda p: p[1].texte + p[1].plan, reverse=True)

    if not paires:
        ok("{} produits compares, aucun recouvrement notable.".format(len(charges)))
        return 0

    alerte("{} paire(s) de produits se recouvrent :".format(len(paires)))
    for courant, voisin in paires[:args.nombre]:
        print("\n  {}".format(_c(courant["titre"][:58], "1")))
        print("    et {}".format(voisin.titre[:58]))
        print("    {} commun — {:.0f} % de texte, {:.0f} % de plan".format(
            voisin.motif, voisin.texte * 100, voisin.plan * 100))
        print("    {}  |  {}".format(courant["produit_id"][:34],
                                     voisin.produit_id[:34]))
    print("\n  Une place de marche retire les doublons, et un acheteur qui")
    print("  prend deux fois le meme livre demande deux remboursements.")
    return 1


def _reconstruire_empreintes() -> int:
    """Calcule les empreintes des produits fabriques avant cette version."""
    from .pipelines.base import empreinte_depuis_dossier

    titre_console("Reconstruction des empreintes")
    connues = {e["produit_id"] for e in store.lister_empreintes(limite=5000)}
    produits = [p for p in store.lister_produits(1000)
                if p["id"] not in connues and p["statut"] != "bonus_integre"]
    if not produits:
        ok("Tous les produits connus ont deja leur empreinte.")
        return 0

    faits, sans_matiere = 0, []
    for produit in produits:
        dossier = Path(produit["dossier"] or "")
        if empreinte_depuis_dossier(produit["id"], produit["type"],
                                    produit["titre"] or "",
                                    produit["sujet"] or "", dossier):
            faits += 1
        else:
            sans_matiere.append(produit["titre"] or produit["id"])
    ok("{} empreinte(s) reconstituee(s).".format(faits))
    if sans_matiere:
        alerte("{} produit(s) sans texte relisible sur le disque :".format(
            len(sans_matiere)))
        for titre in sans_matiere[:6]:
            print("      {}".format(titre[:56]))
        print("      Dossier deplace ou supprime, ou type sans fichier texte.")
    if faits:
        print("\n  " + _c("usine doublons", "1") + " compare desormais tout "
              "le catalogue.")
    return 0


def cmd_reglages(args: argparse.Namespace) -> int:
    if args.definir:
        modifications = {}
        for paire in args.definir:
            if "=" not in paire:
                erreur("Format attendu : nom=valeur (recu : {})".format(paire))
                return 1
            nom, valeur = paire.split("=", 1)
            nom = nom.strip()
            if nom not in reglages.DEFAUTS:
                erreur("Reglage inconnu : {}".format(nom))
                print("  Reglages valides : " + ", ".join(reglages.DEFAUTS))
                return 1
            modifications[nom] = valeur
        reglages.ecrire(modifications)
        for nom in modifications:
            ok("{} = {}".format(nom, reglages.lire(nom)))
        return 0
    if args.reinitialiser:
        reglages.reinitialiser()
        ok("Reglages remis a zero.")
        return 0
    titre_console("Reglages")
    for ligne in reglages.lignes_affichables():
        print("  {:<14} {}".format(ligne["nom"], _c(ligne["valeur"], "1")))
        print("  {:<14} {}".format("", _c(ligne["description"], "2")))
    print("\n  Modifier : " + _c('usine reglages --definir auteur="Votre Nom"', "1"))
    print("  Fichier  : " + str(reglages.chemin()))
    return 0


# --------------------------------------------------------------------------
# File de production et usine continue
# --------------------------------------------------------------------------

_ETIQUETTES = {
    "en_attente": ("en attente", "36"),
    "en_cours": ("en cours", "1;33"),
    "fait": ("livre", "32"),
    "echec": ("echec", "31"),
    "annule": ("annule", "90"),
}


def cmd_file(args: argparse.Namespace) -> int:
    """Gerer la file des niches a fabriquer."""
    if args.ajouter:
        ajoutees, doublons = [], []
        for sujet in args.ajouter:
            identifiant = file_prod.ajouter(
                sujet, args.type,
                options={k: v for k, v in (("nombre", args.nombre),
                                           ("audience", args.audience),
                                           ("ton", args.ton),
                                           ("qualite", args.qualite)) if v},
                priorite=args.priorite)
            (ajoutees if identifiant else doublons).append(sujet)
        for sujet in ajoutees:
            ok("ajoute : {} ({})".format(sujet, args.type))
        for sujet in doublons:
            alerte("deja en file : {}".format(sujet))
        for sujet in ajoutees:
            for proche in empreinte.sujets_proches(sujet, args.type)[:2]:
                alerte("« {} » recouvre une niche deja produite : « {} »".format(
                    sujet, proche["sujet"]))
                print("      Produit : {} — verifiez avant de vendre les deux."
                      .format(proche["titre"][:52]))
        print("\n  File : " + _resume_file())
        return 0

    if getattr(args, "fiction", None) is not None:
        from .production import prospecter_fiction

        titre_console("Promesses de lecture")
        print("  Une fiction ne se cherche pas comme une niche. Le lecteur\n"
              "  n'achete pas la solution d'un probleme : il achete une\n"
              "  experience qu'il veut revivre — un sous-genre, des tropes,\n"
              "  une ambiance, et une fin qu'on ne lui refuse pas.\n")
        rapport = prospecter_fiction(
            nombre=args.nombre or 8, graine=args.fiction or "",
            journal=lambda message: print("  " + message))
        if rapport["ajoutees"]:
            ok("{} promesse(s) mise(s) en file.".format(rapport["ajoutees"]))
        elif rapport["en_file"]:
            alerte("Aucune promesse NEUVE : les {} sont deja en file."
                   .format(rapport["en_file"]))
        elif rapport["pistes"]:
            alerte("Aucune promesse retenue : toutes recouvrent un recit "
                   "deja ecrit.")
        print("\n  File : " + _resume_file())
        return 0 if rapport["ajoutees"] else 1

    if args.explorer is not None:
        from .production import prospecter

        titre_console("Prospection")
        rapport = prospecter(nombre=args.nombre or 8,
                             graine=args.explorer or "",
                             journal=lambda message: print("  " + message),
                             avec_veille=not args.sans_veille)
        if not rapport["graine"]:
            return 1
        if rapport["ajoutees"]:
            ok("{} niche(s) ajoutee(s) a la file.".format(rapport["ajoutees"]))
        elif rapport["pistes"]:
            # Nommer la VRAIE cause. « Toutes recouvrent un produit deja
            # fabrique » etait affiche meme quand aucune ne recouvrait quoi
            # que ce soit : elles etaient deja en file, ce qui appelle un
            # autre geste — produire ce qui attend, pas chercher ailleurs.
            if rapport.get("en_file") and not rapport["ecartees"]:
                alerte("Aucune piste NEUVE : les {} pistes sont deja en file "
                       "d'attente.".format(rapport["en_file"]))
                print("      Lancez « usine produire » pour les fabriquer, ou "
                      "explorez une autre graine.")
            else:
                alerte("Aucune piste retenue : toutes recouvrent un produit "
                       "deja fabrique, ou sont deja en file.")
        print("\n  File : " + _resume_file())
        return 0 if rapport["ajoutees"] else 1

    if args.retirer:
        for identifiant in args.retirer:
            if file_prod.retirer(identifiant):
                ok("entree {} retiree".format(identifiant))
            else:
                alerte("entree {} introuvable ou deja terminee".format(identifiant))
        print("\n  File : " + _resume_file())
        return 0

    if args.rejouer is not None:
        nombre = file_prod.rejouer(args.rejouer or 0)
        ok("{} entree(s) remise(s) en file".format(nombre))
        return 0

    if args.vider or args.tout_vider:
        nombre = file_prod.vider(tout=args.tout_vider)
        ok("{} entree(s) supprimee(s)".format(nombre))
        return 0

    entrees = file_prod.lister(args.statut, 60)
    titre_console("File de production")
    if not entrees:
        print("  File vide.")
        print("\n  Ajouter : " + _c('usine file --ajouter "votre niche"', "1"))
        return 0
    for entree in entrees:
        libelle, couleur = _ETIQUETTES.get(entree["statut"], (entree["statut"], "0"))
        print("  {:>4}  {:<11} {:<12} {}".format(
            entree["id"], _c(libelle, couleur), entree["type"],
            entree["sujet"][:44]))
        if entree["erreur"]:
            print("        " + _c(entree["erreur"][:66], "31"))
    print("\n  " + _resume_file())
    return 0


def _resume_file() -> str:
    compte = file_prod.compter()
    return "{} en attente, {} en cours, {} livre(s), {} echec(s)".format(
        compte["en_attente"], compte["en_cours"], compte["fait"], compte["echec"])


def cmd_usine(args: argparse.Namespace) -> int:
    """Demarrer, suivre ou arreter l'usine continue."""
    from .production import UsineContinue, demander_arret, statut, verrou_actif

    if args.action == "arreter":
        if demander_arret():
            ok("Arret demande. L'usine termine le produit en cours puis s'arrete.")
            return 0
        alerte("Aucune usine en marche.")
        return 1

    if args.action == "statut":
        etat = statut()
        titre_console("Usine continue")
        if etat["en_marche"]:
            session = etat["session"]
            ok("en marche (pid {}) depuis {:.0f} min".format(
                etat["pid"], (session.get("duree") or 0) / 60))
            courant = session.get("courant")
            if courant and courant.get("attente_jusqu_a"):
                # Une attente de quota se lisait « En cours » pendant des
                # heures : on croyait l'usine bloquee.
                print("  En attente des fournisseurs — reprise automatique "
                      "vers {} : « {} »".format(
                          time.strftime("%H:%M", time.localtime(
                              courant["attente_jusqu_a"])), courant["sujet"]))
            elif courant:
                print("  En cours : {} — « {} »".format(
                    courant["type"], courant["sujet"]))
            print("  Produits livres cette session : {}".format(
                session.get("nombre_faits", 0)))
        else:
            print("  " + _c("a l'arret", "90"))
            if etat["session"].get("motif_fin"):
                print("  Derniere session : " + etat["session"]["motif_fin"])

        compte = etat["file"]
        print("\n  " + _c("File", "1") + "   : " + _resume_file())
        for entree in etat["prochaines"]:
            print("    {:>4}  {:<12} {}".format(
                entree["id"], entree["type"], entree["sujet"][:44]))

        b = etat["budget"]
        if b["actif"]:
            print("\n  " + _c("Budget du jour", "1"))
            if b["appels_jour_max"]:
                print("    appels   : {} / {}   (reste {})".format(
                    b["appels_jour"], b["appels_jour_max"], b["reste_aujourdhui"]))
            if b["jetons_jour_max"]:
                print("    jetons   : {} / {}".format(
                    b["jetons_jour"], b["jetons_jour_max"]))
            if b["produits_jour_max"]:
                print("    produits : {} / {}".format(
                    b["produits_faits"], b["produits_jour_max"]))
        else:
            alerte("Aucun budget defini : "
                   + _c("usine reglages --definir budget_appels_jour=250", "1"))
        return 0

    # action « demarrer »
    if not _verifier_fournisseurs():
        return 2
    if verrou_actif() is not None:
        erreur("Une usine tourne deja (pid {}).".format(verrou_actif()))
        print("  Suivre : " + _c("usine usine statut", "1"))
        print("  Arreter : " + _c("usine usine arreter", "1"))
        return 1

    for paire in args.budget or []:
        if "=" not in paire:
            erreur("Format attendu : appels_jour=300")
            return 1
        nom, valeur = paire.split("=", 1)
        cle = "budget_" + nom.strip() if not nom.startswith("budget_") else nom.strip()
        if cle not in reglages.DEFAUTS:
            erreur("Budget inconnu : {}".format(nom))
            print("  Disponibles : appels_jour, appels_produit, produits_jour, "
                  "minutes_produit, jetons_jour")
            return 1
        reglages.ecrire({cle: valeur})

    compte = file_prod.compter()
    if not compte["en_attente"] and not args.auto:
        alerte("La file est vide.")
        print("  Ajouter : " + _c('usine file --ajouter "votre niche"', "1"))
        print("  Ou remplir automatiquement : " + _c("usine usine demarrer --auto", "1"))
        return 1

    titre_console("Usine continue")
    moteur = UsineContinue(auto=args.auto, maximum=args.max,
                           journal=lambda message: print("  " + message),
                           pause=args.pause)
    return moteur.tourner()


# --------------------------------------------------------------------------
# A/B testing
# --------------------------------------------------------------------------

_COULEURS_VERDICT = {
    "gagnant": "32", "tendance": "33", "indecis": "33",
    "insuffisant": "33", "sans_donnees": "90", "vide": "90",
}


def _barre(bas: float, haut: float, maximum: float, largeur: int = 22) -> str:
    """Intervalle credible rendu en caracteres : visible sur un ecran etroit."""
    if maximum <= 0:
        return " " * largeur
    debut = int(bas / maximum * largeur)
    fin = max(debut + 1, int(haut / maximum * largeur))
    return ("." * debut + "#" * (fin - debut) + "." * (largeur - fin))[:largeur]


def _actions_reelles(variante_id: int) -> Optional[int]:
    """Ventes a AJOUTER au journal pour cette variante.

    « observer » tient un journal additif : les chiffres s'ajoutent aux
    releves precedents. Les ventes, elles, sont un cumul depuis le debut de
    la periode. Reporter le cumul deux fois comptait donc chaque vente
    deux fois — et pouvait faire depasser le nombre de vues, ce qui fait
    lever une erreur de saisie sur une saisie pourtant correcte.

    On retranche ce qui est deja au journal, et on ne redescend jamais en
    dessous de zero : un remboursement enregistre apres coup reduit le
    cumul, mais un journal additif ne sait pas defaire.
    """
    with store.cursor() as cur:
        ligne = cur.execute(
            "SELECT experience_id FROM variantes WHERE id=?",
            (variante_id,)).fetchone()
    if not ligne:
        return None
    mesures = experience.mesures_reelles(int(ligne["experience_id"]))
    if mesures.get("probleme"):
        return None
    for mesure in mesures["variantes"]:
        if mesure["variante"]["id"] == variante_id and mesure["periode"]:
            deja = int(mesure["variante"].get("total_actions") or 0)
            return max(0, mesure["ventes"] - deja)
    return None


def _rythme_ab(args: argparse.Namespace) -> int:
    """Compare les variantes sur leur rythme de vente reel."""
    mesures = experience.mesures_reelles(args.identifiant)
    titre_console("Rythme de vente par variante")
    if mesures.get("probleme"):
        erreur(mesures["probleme"])
        if "sans produit" in mesures["probleme"]:
            print("  Creez le test depuis un produit : "
                  + _c("usine ab creer --produit <produit_id>", "1"))
        return 1

    sans_periode = [m for m in mesures["variantes"] if not m["periode"]]
    for mesure in mesures["variantes"]:
        variante = mesure["variante"]
        if not mesure["periode"]:
            print("  {} {:<40} {}".format(
                _c("[" + variante["etiquette"] + "]", "1;36"),
                variante["contenu"][:40], _c("periode non renseignee", "33")))
            continue
        print("  {} {:<40} {:>3} vente(s) en {:>3.0f} j = {:.2f}/jour".format(
            _c("[" + variante["etiquette"] + "]", "1;36"),
            variante["contenu"][:40], mesure["ventes"], mesure["jours"],
            mesure["ventes"] / mesure["jours"]))
        print("      {}".format(_c(mesure["periode"], "90")))
    if sans_periode:
        print()
        alerte("{} variante(s) sans periode : elles ne peuvent rien recevoir."
               .format(len(sans_periode)))
        print("      " + _c("usine ab periode <variante> --du AAAA-MM-JJ", "1"))

    utiles = [m for m in mesures["variantes"] if m["periode"]]
    if len(utiles) < 2:
        print("\n  Il faut au moins deux variantes datees pour comparer.")
        return 1

    comparaison = experience.comparer_rythmes(
        [(m["ventes"], m["jours"]) for m in utiles],
        etiquettes=[m["variante"]["etiquette"] for m in utiles])
    titre_console("Comparaison")
    for resultat in comparaison["variantes"]:
        variante = {"etiquette": resultat["etiquette"]}
        print("  {}  P(meilleure) {:>5.0f} %   rythme median {:.2f}/jour"
              "   (90 % entre {:.2f} et {:.2f})".format(
                  _c("[" + variante["etiquette"] + "]", "1;36"),
                  resultat["probabilite_meilleure"] * 100,
                  resultat["rythme_median"], resultat["bas"], resultat["haut"]))

    conclusion = experience.verdict_rythme(comparaison)
    print()
    print("  " + _c(conclusion["etat"].upper(),
                    _COULEURS_VERDICT.get(conclusion["etat"], "0")))
    for ligne in _envelopper(conclusion["message"], 70):
        print("  " + ligne)
    print()
    print("  " + _c("Ce test est sequentiel", "1") + " : les variantes n'ont pas")
    print("  ete exposees en meme temps. Une semaine de vacances ou un partage")
    print("  inattendu se confond avec l'effet du titre, et aucun calcul ne")
    print("  repare cela. Alternez les variantes sur plusieurs cycles.")
    return 0 if conclusion["etat"] in ("gagnant", "tendance") else 1


def cmd_ab(args: argparse.Namespace) -> int:
    """Creer, alimenter et lire un test A/B."""
    from .pipelines import variantes as pipeline_variantes

    action = args.action

    if action == "creer":
        if not _verifier_fournisseurs():
            return 2
        titre_actuel, produit_id, description = args.titre, "", ""
        if args.produit:
            produit = store.lire_produit(args.produit)
            if not produit:
                erreur("Produit inconnu : {}".format(args.produit))
                print("  Liste : " + _c("usine liste", "1"))
                return 1
            titre_actuel = produit["titre"]
            produit_id = produit["id"]
            meta = produit.get("meta") or {}
            description = str(meta.get("promesse") or produit.get("sujet") or "")
        if not titre_actuel:
            erreur("Indiquez --titre \"...\" ou --produit <identifiant>.")
            return 1

        ctx = contexte_depuis(argparse.Namespace(
            sujet=description or titre_actuel, audience=args.audience,
            ton="", taille="", auteur="", langue="", qualite="",
            marque="", prix="", hors_ligne=args.hors_ligne,
            sans_image=args.sans_image))
        dossier = pipeline_variantes.dossier_du_test(produit_id, titre_actuel)

        titre_console("Test A/B — {}".format(args.sur))
        resultat = pipeline_variantes.preparer_test(
            ctx, titre_actuel, dossier, sujet=args.sur, nombre=args.nombre,
            description=description, produit_id=produit_id)

        print()
        for variante in experience.variantes(resultat["experience_id"]):
            meta = variante["meta"]
            print("  {} {}".format(_c("[" + variante["etiquette"] + "]", "1;36"),
                                   variante["contenu"]))
            if meta.get("angle"):
                print("      angle : {}".format(_c(meta["angle"], "2")))
            if meta.get("diagnostic"):
                print("      {}".format(_c(meta["diagnostic"], "2")))
            print("      " + _c("usine ab observer {} --vues N --actions N".format(
                variante["id"]), "2"))

        if not resultat["distinction"]["testable"]:
            print()
            alerte(resultat["distinction"]["message"])

        print()
        ok("Planche de comparaison : {}".format(resultat["planche"]))
        print("  Ouvrir sur Termux : " + _c(
            "termux-open '{}'".format(resultat["planche"]), "2"))
        _rappel_echelle()
        return 0

    if action == "liste":
        experiences = experience.lister()
        titre_console("Tests A/B")
        if not experiences:
            print("  Aucun test.")
            print("\n  Creer : " + _c('usine ab creer --titre "votre titre"', "1"))
            return 0
        for exp in experiences:
            analyse = experience.analyser(exp["id"])
            verdict_courant = analyse["verdict"]
            print("  {:>3}  {:<11} {:<10} {}".format(
                exp["id"], exp["sujet"], exp["statut"], exp["titre"][:38]))
            print("       {} variante(s) — {}".format(
                exp["nb_variantes"],
                _c(verdict_courant["etat"],
                   _COULEURS_VERDICT.get(verdict_courant["etat"], "0"))))
        return 0

    if action == "periode":
        try:
            pose = experience.fixer_periode(args.identifiant, args.du, args.au)
        except ValueError as exc:
            erreur(str(exc))
            return 1
        if not pose:
            erreur("Variante {} introuvable.".format(args.identifiant))
            return 1
        ok("Variante {} en ligne du {} au {}".format(
            args.identifiant, args.du, args.au or "aujourd'hui"))
        print("  Les ventes de cette periode lui seront attribuees :")
        print("  " + _c("usine ab rythme <numero du test>", "1"))
        return 0

    if action == "rythme":
        return _rythme_ab(args)

    if action == "observer":
        if args.vues is None and args.actions is None:
            erreur("Indiquez au moins --vues ou --actions.")
            return 1
        # Les actions peuvent venir des ventes reellement encaissees : c'est
        # le chiffre le plus penible a compter a la main, et le plus facile a
        # se tromper. Les vues, elles, ne figurent dans aucun export.
        if args.actions is None and args.vues is not None:
            reelles = _actions_reelles(args.identifiant)
            if reelles is not None:
                args.actions = reelles
                ok("{} action(s) reprises des ventes enregistrees.".format(
                    reelles))
        try:
            experience.observer(args.identifiant, vues=args.vues or 0,
                                actions=args.actions or 0, note=args.note or "")
        except ValueError as exc:
            erreur(str(exc))
            return 1
        ok("Observation enregistree : +{} vue(s), +{} action(s)".format(
            args.vues or 0, args.actions or 0))
        print("  Les chiffres s'additionnent aux releves precedents.")
        return 0

    if action in ("verdict", "planche", "clore"):
        analyse = experience.analyser(args.identifiant)
        if "erreur" in analyse:
            erreur(analyse["erreur"])
            return 1
        if action == "planche":
            from .pipelines import variantes as pipeline_variantes

            exp = analyse["experience"]
            dossier = config.PRODUITS_DIR
            if exp["produit_id"]:
                produit = store.lire_produit(exp["produit_id"])
                if produit and produit["dossier"]:
                    dossier = Path(produit["dossier"]) / "variantes"
            chemin = pipeline_variantes.planche(args.identifiant, dossier)
            ok("Planche : {}".format(chemin))
            return 0
        if action == "clore":
            experience.cloturer(args.identifiant, args.gagnante or 0,
                                args.note or "")
            ok("Test cloture.")
            return 0
        _afficher_verdict(analyse)
        return 0

    if action == "supprimer":
        (ok if experience.supprimer(args.identifiant) else alerte)(
            "test {} supprime".format(args.identifiant))
        return 0

    erreur("Action inconnue : {}".format(action))
    return 1


def _afficher_verdict(analyse: Dict[str, Any]) -> None:
    exp = analyse["experience"]
    lot = analyse["variantes"]
    verdict_courant = analyse["verdict"]

    titre_console("Test A/B n° {} — {}".format(exp["id"], exp["sujet"]))
    print("  Produit : {}".format(exp["titre"][:56]))
    print("  Objectif : {}".format(
        experience.OBJECTIFS.get(exp["objectif"], exp["objectif"])))
    print()

    maximum = max((v["stats"]["haut"] for v in lot if v.get("stats")), default=0.01)
    print("  {:<3} {:<34} {:>6} {:>7} {:>7}  {}".format(
        "", "variante", "vues", "actions", "taux", "intervalle credible 90 %"))
    for variante in lot:
        stats = variante.get("stats") or {}
        tete = (verdict_courant.get("gagnante") == stats.get("index")
                or verdict_courant.get("tete") == stats.get("index"))
        print("  {:<3} {:<34} {:>6} {:>7} {:>6.1f}%  {} {:>4.0f}%".format(
            _c("[" + variante["etiquette"] + "]", "1;36" if tete else "0"),
            variante["contenu"][:34],
            stats.get("vues", 0), stats.get("actions", 0),
            stats.get("taux", 0) * 100,
            _barre(stats.get("bas", 0), stats.get("haut", 0), maximum),
            stats.get("probabilite_meilleure", 0) * 100))
    print("  {:<3} {:<34} {:>6} {:>7} {:>7}  {}".format(
        "", "", "", "", "", _c("^ probabilite d'etre la meilleure", "2")))

    print()
    couleur = _COULEURS_VERDICT.get(verdict_courant["etat"], "0")
    print("  " + _c(verdict_courant["etat"].upper(), "1;" + couleur))
    for ligne in _envelopper(verdict_courant["message"], 70):
        print("  " + ligne)
    if verdict_courant.get("besoin_par_variante"):
        print()
        print("  " + _c("Ordre de grandeur : environ {} vues par variante pour "
                        "detecter un ecart de 20 %.".format(
                            verdict_courant["besoin_par_variante"]), "2"))


def _rappel_echelle() -> None:
    print()
    print("  " + _c("A savoir avant de lancer le test", "1"))
    for ligne in _envelopper(
        "Un test A/B honnete demande beaucoup de trafic : a 5 % de conversion, "
        "il faut de l'ordre de 7 600 vues par variante pour detecter un ecart "
        "de 20 %. En dessous, l'usine refusera de designer un gagnant — et "
        "c'est voulu. La valeur immediate de ces variantes est ailleurs : "
        "choisir a l'oeil celle qui vous ressemble le plus, et garder les "
        "autres pour vos publications.", 70):
        print("  " + _c(ligne, "2"))


def cmd_marche(args: argparse.Namespace) -> int:
    """Mesurer un marche depuis des sources publiques, sans aucune cle API."""
    titre_console("Signaux de marche — « {} »".format(args.sujet))
    rapport = marche.sonder(args.sujet, journal=lambda m: print(m))
    lecture = rapport["lecture"]

    print()
    for signal in lecture["signaux"]:
        ok(signal)
    for nom in rapport["sources_indisponibles"]:
        alerte("{} : {}".format(nom, rapport["sources"][nom].get("erreur", "muette")))

    print()
    print("  " + _c("Demande", "1") + "      : {}".format(lecture["demande"] or "inconnue"))
    print("  " + _c("Concurrence", "1") + "  : {}".format(lecture["concurrence"] or "inconnue"))
    print("  " + _c("Tendance", "1") + "     : {}".format(lecture["tendance"] or "inconnue"))
    print("  " + _c("Fiabilite", "1") + "    : {}".format(lecture["fiabilite"]))
    print()
    for ligne in _envelopper(lecture["verdict"], 70):
        print("  " + ligne)

    if args.json:
        config.ensure_dirs()
        from .pipelines.base import slug

        chemin = config.PRODUITS_DIR / "marche-{}.json".format(slug(args.sujet, 40))
        chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        print("\n  Rapport complet : " + str(chemin))
    print("\n  Etape suivante : " + _c('usine idees "{}"'.format(args.sujet), "1"))
    return 0


def _envelopper(texte: str, largeur: int) -> List[str]:
    lignes, courante = [], ""
    for mot in texte.split():
        if len(courante) + len(mot) + 1 > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = (courante + " " + mot).strip()
    if courante:
        lignes.append(courante)
    return lignes


def cmd_bilan(args: argparse.Namespace) -> int:
    """Ce que l'usine a appris de vos productions."""
    donnees = apprentissage.bilan()
    if donnees["productions"] == 0:
        titre_console("Bilan")
        print("  " + donnees["message"])
        print("  Fabriquez un produit : " + _c('usine ebook "votre sujet"', "1"))
        return 0

    titre_console("Bilan de production")
    print("  {} production(s), {} reussie(s), {} echec(s)".format(
        donnees["productions"], donnees["reussites"], donnees["echecs"]))
    if donnees["note_moyenne"] is not None:
        notees = donnees.get("productions_notees") or 0
        print("  Note moyenne : {} /10   (meilleure {} — pire {})".format(
            donnees["note_moyenne"], donnees["note_meilleure"],
            donnees["note_pire"]))
        # Dire sur combien : une moyenne affichee sous « 4 production(s) » se
        # lit comme la moyenne des quatre, meme quand une seule etait
        # mesurable. Le controle mesure de la prose ; un pack de prompts ou
        # un outil logiciel n'en sont pas, et n'ont donc pas de note.
        if notees and notees < donnees["reussites"]:
            print("    " + _c("sur {} produit(s) sur {} : les autres ne sont "
                              "pas de la prose, ou leurs sections sont trop "
                              "courtes pour etre mesurees"
                              .format(notees, donnees["reussites"]), "2"))
    if donnees["gain_moyen_relecture"] is not None:
        print("  Gain moyen de la relecture : {:+.2f} point".format(
            donnees["gain_moyen_relecture"]))
    print("  {} mots produits, {} appels IA".format(
        donnees["mots_totaux"], donnees["appels_totaux"]))

    for critere, libelle in (("par_type", "Par type de produit"),
                             ("par_ton", "Par ton"),
                             ("par_qualite", "Par niveau de qualite")):
        groupes = donnees[critere]
        if not groupes:
            continue
        print("\n  " + _c(libelle, "1"))
        for groupe in groupes:
            print("    {:<14} {:>5} /10   {:>3} production(s)   {:>5} appels".format(
                groupe["valeur"][:14], groupe["note_moyenne"], groupe["productions"],
                groupe["appels_moyens"]))

    if donnees["defauts_frequents"]:
        print("\n  " + _c("Defauts les plus frequents", "1"))
        for defaut in donnees["defauts_frequents"][:5]:
            print("    {:>3}x  {}".format(defaut["occurrences"], defaut["defaut"]))

    _bilan_des_ventes()

    titre_console("Conseils tires de vos donnees")
    for conseil in apprentissage.conseils():
        print("  " + _c("[{}]".format(conseil["sujet"]), "36"))
        for ligne in _envelopper(conseil["conseil"], 68):
            print("    " + ligne)
        print("    " + _c("appui : " + conseil["appui"], "2"))
    return 0


def _bilan_des_ventes() -> None:
    """Ce que les notes ne disent pas.

    Une bonne note et un produit qui se vend sont deux choses differentes, et
    rien ne garantit qu'elles se rencontrent. Tant que les ventes ne sont pas
    saisies, l'usine ne peut conseiller que sur la premiere — et le dit.
    """
    totaux = ventes.total_par_devise()
    if not totaux:
        print("\n  " + _c("Aucune vente enregistree", "33"))
        print("    Les conseils ci-dessous portent sur la QUALITE mesuree,")
        print("    pas sur ce qui se vend — l'usine n'en sait rien.")
        print("    " + _c("usine ventes --importer export.csv", "1"))
        return
    titre_console("Ce que les ventes disent")
    for total in totaux:
        print("  {}  {} unites, {:.2f} encaisses".format(
            _c(total["devise"], "1"), total["unites"] or 0, total["brut"] or 0))
    types = ventes.par_champ("type")
    if types:
        print("\n  " + _c("Chiffre d'affaires par type", "1"))
        for ligne in types[:6]:
            print("    {:<14} {:>8.2f} {}  sur {} produit(s)".format(
                (ligne["valeur"] or "?")[:14], ligne["brut"] or 0,
                ligne["devise"], ligne["produits"]))
    prix = ventes.prix_observes()
    for ligne in prix:
        if ligne["ventes"] >= 3:
            print("\n  Prix median reellement encaisse : {:.2f} {}"
                  " ({} ventes)".format(ligne["median"], ligne["devise"],
                                        ligne["ventes"]))


def cmd_prompts_systeme(args: argparse.Namespace) -> int:
    """Exporter, inspecter ou reinitialiser les prompts de l'usine."""
    if args.exporter:
        fichiers = registre_prompts.exporter()
        titre_console("Prompts exportes")
        for fichier in fichiers:
            ok(str(fichier))
        print("\n  Editez ces fichiers, puis relancez une fabrication :")
        print("  les modifications sont prises en compte au demarrage suivant.")
        print("  Revenir aux valeurs d'origine : supprimez le fichier.")
        return 0
    if args.reinitialiser:
        repertoire = registre_prompts.dossier()
        if repertoire.exists():
            import shutil

            shutil.rmtree(repertoire)
        registre_prompts.oublier()
        ok("Prompts remis aux valeurs d'origine.")
        return 0

    titre_console("Prompts de l'usine")
    modifies = registre_prompts.personnalises()
    for nom, fiche in registre_prompts.agents().items():
        marque = _c(" (personnalise)", "33") if "agent : " + nom in modifies else ""
        print("  {} {}{}".format(_c(fiche.get("emoji", "*"), "36"),
                                 _c(nom, "1"), marque))
        print("      {}".format(_c(str(fiche.get("mission", ""))[:66], "2")))
    print()
    print("  Dossier : " + str(registre_prompts.dossier()))
    if modifies:
        alerte("{} element(s) personnalise(s)".format(len(modifies)))
    else:
        print("  Aucune personnalisation : " + _c("usine prompts-systeme --exporter", "1"))
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    from .menu import menu_principal

    return menu_principal(lambda arguments: principal(arguments))


def cmd_social(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un pack de contenu")
    resume = _par_le_catalogue(args, "social", ctx)
    _resume_console(_apres_production(
        args, ctx, resume, "Pack de {} publications prets a publier.".format(resume["posts"])
    ))
    return 0


def cmd_idees(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Exploration de niche")
    resultat = _par_le_catalogue(args, "idees", ctx)
    if resultat.get("marche", {}).get("signaux"):
        print()
        for signal in resultat["marche"]["signaux"]:
            ok(signal)
    for index, idee in enumerate(resultat["idees"], 1):
        print("\n  {}. {}".format(_c(str(index), "1;36"), _c(idee["titre"], "1")))
        print("     type={} prix={} EUR difficulte={} concurrence={}".format(
            idee["type"], idee["prix_eur"], idee["difficulte"], idee["concurrence"]))
        print("     " + idee["probleme"][:110])
        print("     " + _c('usine {} "{}"'.format(idee["type"], idee["titre"]), "2"))
    print("\n  Fiches completes : " + resultat["dossier"])
    return 0


def cmd_complet(args: argparse.Namespace) -> int:
    """Offre complete : produit principal + bonus + kit de vente + archive."""
    if not _verifier_fournisseurs():
        return 2
    debut = time.time()
    ctx = contexte_depuis(args)
    titre_console("Offre complete — produit principal")
    principal = ebook.produire(ctx)
    dossier = Path(principal["dossier"])

    titre_console("Bonus 1 — boite a outils")
    ctx_outils = contexte_depuis(args)
    ctx_outils.sujet = principal["titre"]
    ctx_outils.sans_image = True
    try:
        bonus_outils = boite_outils.produire(ctx_outils, nombre=6)
        _deplacer_bonus(Path(bonus_outils["dossier"]), dossier / "bonus-boite-outils",
                        bonus_outils["produit_id"])
        ok("Boite a outils integree ({} outils)".format(bonus_outils["outils"]))
    except Exception as exc:
        alerte("Bonus boite a outils ignore : {}".format(exc))

    titre_console("Bonus 2 — pack de contenu de lancement")
    ctx_social = contexte_depuis(args)
    ctx_social.sujet = principal["titre"]
    ctx_social.sans_image = True
    try:
        # Le reseau decide a partir du sujet, comme pour un pack seul : il
        # valait « linkedin » en dur, quel que soit le livre.
        bonus_social = catalogue.executer(
            "social", ctx_social,
            dict({"nombre": 10}, **({"reseau": args.reseau} if args.reseau else {})))
        _deplacer_bonus(Path(bonus_social["dossier"]), dossier / "bonus-publications",
                        bonus_social["produit_id"])
        ok("Pack de contenu integre ({} publications)".format(bonus_social["posts"]))
    except Exception as exc:
        alerte("Bonus publications ignore : {}".format(exc))

    args.marketing = True
    args.zip = True
    resume = _apres_production(
        args, ctx, principal,
        "Ebook de {} chapitres ({} mots), boite a outils et pack de publications "
        "de lancement inclus.".format(principal["chapitres"], principal["mots"]),
    )
    _resume_console(resume)
    print("\n  Duree totale : {:.0f} min".format((time.time() - debut) / 60))
    return 0


def _deplacer_bonus(source: Path, cible: Path, produit_id: str = "") -> None:
    """Range un produit annexe dans le dossier du produit principal.

    Le catalogue doit suivre le deplacement, sinon « usine liste » et le
    tableau de bord pointeraient vers un dossier disparu.
    """
    import shutil

    if not source.exists():
        return
    cible.parent.mkdir(parents=True, exist_ok=True)
    if cible.exists():
        shutil.rmtree(cible)
    shutil.move(str(source), str(cible))
    if produit_id:
        store.maj_produit(produit_id, dossier=str(cible), statut="bonus_integre")


# --------------------------------------------------------------------------
# Commandes utilitaires
# --------------------------------------------------------------------------


def cmd_marketing(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    produit = store.lire_produit(args.produit_id)
    if not produit:
        erreur("Produit inconnu : {}".format(args.produit_id))
        print("  Liste des produits : usine liste")
        return 1
    from .pipelines import apres, brief, porte

    refus = apres.pas_encore_vendable(produit)
    if refus:
        erreur("Pas de kit de vente : " + refus)
        return 1
    dossier = Path(produit["dossier"])
    meta = produit.get("meta") or {}

    # Le contexte de la fabrication, garde au carnet. Les valeurs en dur de
    # cette commande — « pro », « un public francophone motive » — donnaient
    # au kit de vente d'un conte pour enfants la voix d'un rapport annuel.
    ctx = porte.contexte_existant(
        produit["id"], lambda message: print("  " + message),
        sujet=produit["sujet"] or produit["titre"],
        audience=produit["audience"] or brief.AUTO,
        auteur=meta.get("auteur") or reglages.lire("auteur", "Usine-IA"),
        ton=meta.get("ton") or brief.AUTO)
    ctx.prix = args.prix or ""
    ctx.produit_id = produit["id"]
    titre_console("Kit de vente — {}".format(produit["titre"]))
    description = "Produit de type {}. {}".format(
        produit["type"], meta.get("promesse") or produit["sujet"]
    )
    kit = vente.produire_kit(ctx, produit["titre"], description, dossier,
                             plateforme=args.plateforme,
                             type_produit=produit["type"],
                             chapitres_offerts=getattr(args, "extrait", 0) or 0)
    for nom in kit["fichiers"]:
        ok(nom)
    print("  Dossier : " + kit["dossier"])
    if kit.get("extrait"):
        edition = kit["extrait"]
        ok("Extrait offert : {} chapitre(s), {} fichiers".format(
            edition["chapitres_offerts"], len(edition["fichiers"])))
        print("  Dossier : " + edition["dossier"])
    return 0


def cmd_livrer(args: argparse.Namespace) -> int:
    produit = store.lire_produit(args.produit_id)
    if not produit:
        erreur("Produit inconnu : {}".format(args.produit_id))
        return 1
    from .pipelines import apres

    refus = apres.pas_encore_vendable(produit)
    if refus:
        erreur("Pas d'archive pour l'acheteur : " + refus)
        return 1
    dossier = Path(produit["dossier"])
    if not dossier.exists():
        erreur("Dossier introuvable : {}".format(dossier))
        return 1
    meta = produit.get("meta") or {}
    from .pipelines.base import slug

    archive = livraison.empaqueter(
        dossier, slug(produit["titre"], 46), produit["titre"],
        meta.get("auteur", "Usine-IA"),
        promesse=str(meta.get("promesse") or ""),
        contact=args.contact or "",
        livres=meta.get("fichiers"),
        langue=code_langue(produit.get("langue") or ""),
    )
    ok("Archive : {} ({} Ko)".format(archive, archive.stat().st_size // 1024))
    return 0


def _produit_vise(reference: str, statut: str = "") -> Optional[Dict[str, Any]]:
    """Le produit designe, ou le dernier du genre demande.

    Taper un identifiant de quarante caracteres sur un clavier de telephone
    est le genre de detail qui fait abandonner une fonction. « dernier » — ou
    rien du tout — designe le plus recent.
    """
    reference = (reference or "").strip()
    if reference and reference != "dernier":
        produit = store.lire_produit(reference)
        if produit:
            return produit
        # Un identifiant partiel suffit : la fin d'un identifiant est ce qu'on
        # lit a l'ecran, et c'est la partie qui distingue deux produits.
        candidats = [p for p in store.lister_produits(200)
                     if reference in p["id"]]
        return candidats[0] if len(candidats) == 1 else None
    for produit in store.lister_produits(200):
        if not statut or produit["statut"] == statut:
            return produit
    return None


def cmd_reprendre(args: argparse.Namespace) -> int:
    """Refait les sections manquantes d'un produit, et elles seules.

    Ce qui rendait cette commande necessaire : une fabrication coupee — quota,
    reseau, batterie — laissait le travail deja paye sur le disque sans aucun
    moyen de le reprendre. La seule issue etait de tout relancer, donc de tout
    repayer.
    """
    produit = _produit_vise(getattr(args, "produit_id", ""), statut="en_cours")
    if not produit:
        erreur("Aucun produit inacheve a reprendre.")
        print("  Liste : " + _c("usine liste", "1"))
        return 1
    dossier = Path(produit["dossier"] or "")
    from .pipelines import carnet
    from .pipelines import reprise as module_reprise

    manquants = (produit.get("meta") or {}).get("manquants") or []
    if module_reprise.par_le_catalogue(produit["id"]):
        # Fabrique depuis le tableau de bord ou l'usine continue : il n'y a
        # pas de ligne de commande a rejouer, et il n'en faut pas.
        titre_console("Reprise — {}".format(produit["titre"]))
        _annoncer_ce_qui_manque(manquants, dossier)
        _resume_console(module_reprise.reprendre(
            produit["id"], journal=lambda message: print("  " + message)))
        return 0
    commande = carnet.commande(dossier)
    if not commande:
        erreur("Ce produit n'a pas garde la commande qui l'a fabrique.")
        print("  Il date d'avant le carnet de reprise. Relancez la commande "
              "d'origine : les reponses deja obtenues sont en cache.")
        return 1
    titre_console("Reprise — {}".format(produit["titre"]))
    _annoncer_ce_qui_manque(manquants, dossier)
    print("  Commande : usine " + " ".join(commande))
    return principal(list(commande) + ["--reprendre-id", produit["id"]])


def cmd_supprimer(args: argparse.Namespace) -> int:
    """Efface un produit : sa fiche au catalogue ET son dossier.

    Effacer la fiche seule laissait des megaoctets sur un telephone sans que
    rien ne les montre ; effacer le dossier seul laissait une fiche qui
    pointait vers le vide, et « usine livrer » echouait dessus.
    """
    produit = _produit_vise(getattr(args, "produit_id", ""))
    if not produit:
        erreur("Produit inconnu : {}".format(
            getattr(args, "produit_id", "") or "(aucun)"))
        print("  Liste des produits : " + _c("usine liste", "1"))
        return 1
    dossier = Path(produit["dossier"] or "")
    poids = 0
    if dossier.exists():
        poids = sum(f.stat().st_size for f in dossier.rglob("*") if f.is_file())
    print("  {} — {} ({})".format(
        produit["titre"], produit["type"], produit["id"]))
    print("  Dossier : {} ({} Ko)".format(dossier, poids // 1024))
    if not getattr(args, "oui", False):
        # Une suppression ne se devine pas : on la fait confirmer, sauf
        # demande explicite. Le produit n'est pas recuperable ensuite.
        reponse = input("  Effacer definitivement ? [o/N] ").strip().lower()
        if reponse not in ("o", "oui", "y", "yes"):
            print("  Annule.")
            return 0
    import shutil

    if dossier.exists() and dossier.is_dir():
        # Garde-fou : on n'efface que sous le dossier des produits. Une fiche
        # dont le chemin a ete modifie a la main ne doit pas pouvoir faire
        # effacer autre chose.
        try:
            dossier.resolve().relative_to(config.PRODUITS_DIR.resolve())
        except ValueError:
            erreur("Dossier hors de l'atelier, rien n'a ete efface : {}"
                   .format(dossier))
            return 1
        shutil.rmtree(dossier, ignore_errors=True)
    store.supprimer_produit(produit["id"])
    ok("Produit efface ({} Ko liberes).".format(poids // 1024))
    return 0


def cmd_liste(args: argparse.Namespace) -> int:
    produits = store.lister_produits(args.nombre)
    if not produits:
        print("  Aucun produit pour l'instant. Essayez : "
              + _c('usine ebook "votre sujet"', "1"))
        return 0
    titre_console("Produits fabriques")
    inacheves = 0
    for produit in produits:
        meta = produit.get("meta") or {}
        # « en_cours » ne veut dire qu'une chose : la fabrication s'est
        # arretee en chemin — coupure de reseau, quota, processus tue par
        # Android. Le mot seul ne le disait pas, et la ligne s'affichait sous
        # « Produits fabriques » comme les autres.
        inacheve = produit["statut"] == "en_cours"
        inacheves += int(inacheve)
        marque = _c("inacheve", "33") if inacheve else produit["statut"]
        print("  {}  {}".format(
            _c(time.strftime("%d/%m %H:%M", time.localtime(produit["cree_le"])), "2"),
            _c(produit["titre"][:58], "1"),
        ))
        print("     {} | {} | {}".format(produit["type"], marque, produit["id"]))
        if meta.get("mots"):
            print("     {} mots".format(meta["mots"]))
    if inacheves:
        print("\n  {} produit(s) inacheve(s). {}".format(
            inacheves, _explique_le_cache()))
    return 0


def cmd_docteur(args: argparse.Namespace) -> int:
    """Diagnostic complet. Les constats viennent de « core.diagnostic ».

    Ils y vivent parce que le tableau de bord les montre aussi : deux jeux
    de controles finiraient par ne plus dire la meme chose.
    """
    from .core import diagnostic as module_diagnostic

    etat = module_diagnostic.etat_installation(
        avec_modeles=getattr(args, "modeles", False))
    print(BANNIERE.format(version=__version__))
    titre_console("Environnement")
    ok("Python {}".format(etat["python"]))
    ok("Dossier de travail : {}".format(etat["workdir"]))
    ok("Fichier .env : {}".format(
        config.ENV_PATH if etat["env_present"] else "absent (usine cles)"))
    espace = etat["espace"]
    if espace["connu"]:
        (ok if espace["libre_mo"] > 200 else alerte)(
            "Espace libre : {} Mo".format(espace["libre_mo"]))
    (ok if etat["reseau"] else alerte)(
        "Reseau : {}".format("disponible" if etat["reseau"] else
                             "indisponible — seule l'IA locale fonctionnera")
    )

    # Le telephone n'est un sujet que sur un telephone : sur un PC, ces
    # lignes n'apprendraient rien a personne.
    tel = etat["telephone"]
    if tel["termux"]:
        if tel["api"]:
            ok("termux-api present : notifications et garde batterie actives")
        else:
            alerte("termux-api absent : ni notification de fin, ni arret sur "
                   "batterie faible (pkg install termux-api)")
        if tel["batterie"]:
            niveau = tel["batterie"]["niveau"]
            (ok if niveau > 20 or tel["batterie"]["en_charge"] else alerte)(
                "Batterie : {} %{}".format(
                    niveau, " (en charge)" if tel["batterie"]["en_charge"] else ""))

    # Node n'est pas requis pour produire, mais son absence affaiblit la
    # verification du JavaScript genere : le repli structurel ne voit pas une
    # erreur de syntaxe fine.
    if etat["node"]:
        ok("Node.js present : verification complete du JavaScript genere")
    else:
        alerte("Node.js absent : le JavaScript genere sera verifie en mode "
               "degrade (pkg install nodejs-lts)")

    titre_console("Fournisseurs IA")
    lignes = etat["fournisseurs"]
    for ligne in lignes:
        genre = "local" if ligne["local"] else ("sans cle" if ligne["sans_cle"] else "cle API")
        if ligne["disponible"]:
            nb = ligne.get("nb_cles", 0)
            suffixe = " [{} cles]".format(nb) if nb > 1 else ""
            # Le plafond en jetons est souvent celui qui s'epuise le premier :
            # Groq accorde mille requetes par jour mais deux cent mille
            # jetons, soit un livre. L'afficher evite de chercher ailleurs.
            budget = ""
            if ligne.get("tpd"):
                budget = " · {}/{} jetons".format(
                    _compte(ligne.get("jetons_aujourdhui")),
                    _milliers(ligne["tpd"]))
            print("  {} {:<13} {:<9} {:<28} {}/{} aujourd'hui{}{}".format(
                _c("v", "32"), ligne["nom"], genre, ligne["modele"],
                _compte(ligne["aujourdhui"]), ligne["rpd"], _c(budget, "90"),
                _c(suffixe, "36")))
        else:
            print("  {} {:<13} {:<9} definir {} — {}".format(
                _c("-", "90"), ligne["nom"], genre, ligne["cle_env"], ligne["inscription"]))

    controle = etat.get("modeles")
    if controle is not None:
        titre_console("Catalogues des fournisseurs")
        for ecart in controle["ecarts"]:
            alerte("{} ne sert plus : {}".format(
                ecart["fournisseur"], ", ".join(ecart["manquants"])))
            if ecart["proposes"]:
                print("      propose a la place : " +
                      ", ".join(ecart["proposes"][:6]))
        if controle["ecarts"]:
            print("      Corrigez les identifiants dans usine/core/config.py.")
        intacts = [n for n in controle["consultes"]
                   if n not in {e["fournisseur"] for e in controle["ecarts"]}]
        if intacts:
            ok("Modeles confirmes chez : " + ", ".join(intacts))
        # « Personne n'a repondu » ne doit pas se lire « tout va bien » :
        # c'est precisement la confusion qui a laisse Groq mourir en silence.
        if controle["injoignables"]:
            alerte("Non verifie (pas de cle, ou service injoignable) : "
                   + ", ".join(controle["injoignables"]))
        if not controle["consultes"]:
            alerte("Aucun fournisseur n'a pu etre interroge : ce controle ne "
                   "dit rien, ni dans un sens ni dans l'autre.")

    if getattr(args, "essai", False):
        from .core import diagnostic as _d

        titre_console("Essai reel de chaque modele")
        print("  Un appel minimal par identifiant declare. Un modele peut "
              "figurer\n  au catalogue et refuser de servir : c'est "
              "precisement ce qu'un\n  catalogue ne peut pas dire.\n")
        essais = _d.essayer_modeles()
        for ligne in essais["essais"]:
            marque = _c("v", "32") if ligne["etat"] == "repond" else _c("x", "31")
            print("  {} {:12} {:40} {:14} {:>6}s".format(
                marque, ligne["fournisseur"], ligne["modele"][:40],
                ligne["etat"], ligne["latence"]))
            if ligne["etat"] != "repond" and ligne["detail"]:
                print("      {}".format(_c(ligne["detail"][:86], "90")))
        print()
        if not essais["essais"]:
            alerte("Aucun fournisseur disponible : rien n'a pu etre essaye.")
        elif essais["muets"]:
            alerte("{} modele(s) sur {} ne repondent pas.".format(
                len(essais["muets"]), len(essais["essais"])))
            # Un identifiant perime se corrige dans config.py ; un credit
            # epuise ou un quota atteint ne se corrigent pas la, et envoyer
            # tout le monde au meme endroit ferait perdre du temps.
            inconnus = [l for l in essais["muets"] if l["etat"] == "inconnu"]
            if inconnus:
                print("      Identifiants a corriger dans usine/core/config.py :")
                for ligne in inconnus:
                    print("        {} : {}".format(ligne["fournisseur"],
                                                   ligne["modele"]))
        else:
            ok("Les {} modeles declares repondent.".format(len(essais["essais"])))

    if getattr(args, "quotas", False):
        from .core import diagnostic as _d

        titre_console("Quotas ecrits contre quotas annonces")
        print("  Les chiffres de config.py sont recopies d'une page de\n"
              "  documentation. La plupart des services annoncent les leurs\n"
              "  dans les en-tetes de chaque reponse : un appel suffit.\n")
        audit = _d.auditer_quotas()
        muets = []
        for ligne in audit["lignes"]:
            entete = "  {:12}".format(ligne["fournisseur"])
            if ligne["erreur"] and not any(
                    m.get("annonce") for m in ligne["mesures"]):
                alerte("{} : {} — aucun quota lisible.".format(
                    ligne["fournisseur"], ligne["erreur"]))
                if ligne.get("detail"):
                    # Le code seul ne dit pas quoi faire ; le message, si —
                    # a condition de le montrer en entier. Tronque a cent
                    # cinquante signes, celui de Pollinations perdait le lien
                    # qui permet de relever le budget, donc le seul geste a
                    # faire. On plie, on ne tranche pas.
                    # Ni sur un trait d'union, ni au milieu d'un mot : le
                    # premier essai a coupe « edit-key?id=... » en deux et a
                    # rendu le lien inutilisable — le defaut meme qu'on
                    # corrigeait, deplace d'un cran.
                    for bout in textwrap.wrap(
                            ligne["detail"], 68, break_on_hyphens=False,
                            break_long_words=False) or [""]:
                        print("      " + _c(bout, "90"))
                continue
            for mesure in ligne["mesures"]:
                if mesure["verdict"] == "non publie":
                    muets.append("{}/{}".format(ligne["fournisseur"],
                                                mesure["genre"]))
                    continue
                marque = _c("v", "32") if mesure["verdict"] == "accorde" \
                    else _c("?", "33")
                if mesure["correspond"]:
                    print("{} {} {:9} : {:>9} annonce — c'est le quota "
                          "« {} » ecrit".format(
                              entete, marque, mesure["genre"],
                              mesure["annonce"], mesure["correspond"]))
                else:
                    print("{} {} {:9} : {:>9} annonce — ne correspond a aucun "
                          "quota ecrit".format(entete, marque, mesure["genre"],
                                               mesure["annonce"]))
                    if mesure["fenetre"]:
                        print("               (remise a zero : {})".format(
                            mesure["fenetre"]))
                if mesure.get("reste") is not None:
                    print("               il en reste {} pour cette fenetre"
                          .format(mesure["reste"]))
                service = mesure.get("consomme_service")
                usine = mesure.get("compte_usine")
                if service is not None and usine is not None:
                    # Le compteur de l'usine sert a s'arreter AVANT le 429.
                    # S'il derive, un quota exact ne protege de rien.
                    accord = "concorde" if abs(service - usine) <= max(
                        1, service // 10) else _c("ECART", "33")
                    print("               consomme : {} selon le service, "
                          "{} selon l'usine — {}".format(service, usine, accord))
            for nom, valeur in sorted(ligne["inconnus"].items()):
                print("               {} {} : {}".format(
                    _c("?", "90"), nom, str(valeur)[:44]))
        if muets:
            print()
            # « Non publie » n'est pas « tout va bien » : c'est « on ne sait
            # pas ». Les confondre, c'est prendre un silence pour un accord.
            alerte("Aucun chiffre publie par : " + ", ".join(sorted(muets)))
            print("      Ce n'est pas un accord, c'est une absence de "
                  "reponse : ces quotas-la restent invérifiés.")

    if getattr(args, "reparer", False):
        from .core import diagnostic as _d

        titre_console("Reparation des identifiants morts")
        print("  Chaque remplacant est APPELE avant d'etre retenu : sinon on\n"
              "  remplacerait un identifiant mort par un autre, et cela ne se\n"
              "  verrait qu'a la fabrication suivante.\n")
        bilan = _d.reparer_modeles()
        for ligne in bilan["repares"]:
            ok("{} / {} : « {} » -> « {} »{}".format(
                ligne["fournisseur"], ligne["role"],
                ligne["avant"], ligne["apres"],
                # Un repli n'est pas le meilleur modele pour ce role : c'en
                # est un qui marche. Le taire donnerait a croire que le
                # catalogue a rendu l'equivalent.
                "  (repli : aucun modele de ce rang ne repond)"
                if ligne.get("repli") else ""))
        for ligne in bilan["sans_recours"]:
            alerte("{} / {} : « {} » ne repond pas, et rien dans son "
                   "catalogue ne le remplace.".format(
                       ligne["fournisseur"], ligne["role"], ligne["modele"]))
        # Ce qui a ete ECARTE : ce n'est pas reparable ici, mais le taire
        # ferait lire « rien a reparer » comme « tout va bien ».
        par_cause = {}
        for ligne in bilan.get("ecartes", []):
            par_cause.setdefault((ligne["fournisseur"], ligne["cause"]),
                                 []).append(ligne["role"])
        if par_cause:
            print()
            for (fournisseur, cause), roles in sorted(par_cause.items()):
                alerte("{} : {} — {} role(s) non verifiable(s) ici."
                       .format(fournisseur, cause, len(roles)))
            print("      Ces pannes-la ne se reparent pas en changeant de "
                  "modele :")
            print("      un quota se recharge, un credit s'achete, un service "
                  "retire ne revient pas.")
        vivants = bilan.get("vivants", [])
        if vivants:
            noms = sorted({l["fournisseur"] for l in vivants})
            print()
            ok("{} modele(s) repondent, chez : {}".format(
                len(vivants), ", ".join(noms)))
        if not bilan["repares"] and not bilan["sans_recours"]:
            if par_cause and not vivants:
                # Le cas qui ne doit surtout pas se lire « tout va bien ».
                alerte("Aucun identifiant mort — mais aucun modele n'a "
                       "repondu non plus. Ce controle ne dit rien.")
            else:
                ok("Aucun identifiant mort : rien a reparer.")
        elif bilan["repares"]:
            print("\n      Ces choix sont gardes pour les prochaines "
                  "fabrications.")
            print("      Pour les oublier : "
                  + _c("usine cache --catalogues", "1"))

    titre_console("Verdict")
    verdict = etat["verdict"]
    (alerte if verdict["etat"] == "bloque" else ok)(verdict["message"])
    if verdict["etat"] == "local":
        print("      Comptez plusieurs minutes par chapitre : un modele de 3")
        print("      milliards de parametres produit 3 a 10 jetons par seconde")
        print("      sur un telephone. Le delai d'attente est regle en")
        print("      consequence ({} s par appel).".format(
            config.PROVIDERS_BY_NAME["ollama"].timeout))
    elif verdict.get("remede"):
        print("      " + _c(verdict["remede"], "1"))

    details = etat["pool"]
    if details:
        titre_console("Pool de cles — rotation automatique")
        for detail in details:
            # Surtout pas « etat » : cette boucle ecrasait le dictionnaire du
            # diagnostic par une chaine de couleur, et la section suivante
            # mourait sur « string indices must be integers ». Le defaut ne
            # sortait que chez qui possede une cle — le pool est vide sans cle,
            # donc la boucle ne tournait jamais dans la suite de tests. Autrement
            # dit : « usine docteur » plantait pour tous les vrais utilisateurs,
            # et pour eux seuls.
            repos = (_c("disponible", "32") if detail["disponible"]
                     else _c("repos {}s".format(detail["repos_restant"]), "33"))
            print("  {:<13} {:<14} {:>4} appels aujourd'hui   {}".format(
                detail["fournisseur"], detail["cle"], detail["appels_jour"],
                repos))

    stats = etat["consommation"]
    if stats:
        titre_console("Consommation du jour")
        for stat in stats:
            print("  {:<14} {} appels, {} reussis, {} tokens, {:.1f}s en moyenne".format(
                stat["fournisseur"], stat["total"], stat["reussites"] or 0,
                stat["tokens"] or 0, stat["latence"] or 0))
    return 0


def _detailler_local(fournisseur, corps: bytes) -> None:
    """Dit si le modele attendu est REELLEMENT present sur le serveur.

    Un serveur qui repond n'est pas un serveur pret : ollama demarre sans
    aucun modele. « ollama serve » lance, « ollama pull » oublie, et la
    production echouait au premier chapitre avec un 404 que rien
    n'expliquait.
    """
    attendu = fournisseur.model_for("standard")
    try:
        charge = json.loads(corps.decode("utf-8", "replace"))
        presents = [str(m.get("id") or "") for m in (charge.get("data") or [])]
    except (ValueError, AttributeError):
        presents = []
    if not presents:
        return
    if any(attendu == m or m.startswith(attendu.split(":")[0])
           for m in presents):
        ok("  {} : modele « {} » present".format(fournisseur.name, attendu))
    else:
        alerte("  {} repond, mais « {} » n'y est pas.".format(
            fournisseur.name, attendu))
        print("      Presents : {}".format(", ".join(presents[:4]) or "aucun"))
        if fournisseur.name == "ollama":
            print("      " + _c("ollama pull " + attendu, "1"))


def cmd_cles(args: argparse.Namespace) -> int:
    print(BANNIERE.format(version=__version__))
    print("""
  L'usine marche avec n'importe quelle cle gratuite. Une seule suffit pour
  demarrer ; avec deux ou trois, elle bascule automatiquement quand un quota
  est atteint et ne s'arrete jamais en plein milieu d'un livre.

  {rec}

  1. GROQ — le plus rapide, sans carte bancaire
     https://console.groq.com/keys
     GROQ_API_KEY=gsk_...

  2. GOOGLE AI STUDIO (Gemini) — contexte enorme, ideal pour les longs textes
     https://aistudio.google.com/apikey
     GEMINI_API_KEY=AIza...

  3. CEREBRAS — tres rapide, quota journalier genereux
     https://cloud.cerebras.ai/
     CEREBRAS_API_KEY=csk-...

  4. MISTRAL — excellent en francais
     https://console.mistral.ai/api-keys/
     MISTRAL_API_KEY=...

  5. OPENROUTER — beaucoup de modeles :free (environ 50 requetes/jour)
     https://openrouter.ai/keys
     OPENROUTER_API_KEY=sk-or-...

  {aucune}

  Pollinations fonctionne sans aucune inscription : l'usine l'utilise
  automatiquement en dernier recours, et pour generer les couvertures.

  {local}

  Sans reseau, installez une IA locale :
     pkg install ollama && ollama serve
     ollama pull qwen2.5:3b        (environ 2 Go, correct des 4 Go de RAM)
  Puis relancez l'usine : elle detecte le serveur toute seule.

  {miseenplace}

     cp .env.exemple .env
     nano .env            (collez vos cles, une par ligne)
     usine docteur        (verifie que tout repond)
""".format(
        rec=_c("-- LES CLES GRATUITES, PAR ORDRE DE PRIORITE --", "1;36"),
        aucune=_c("-- SANS AUCUNE CLE --", "1;36"),
        local=_c("-- HORS LIGNE, IA LOCALE --", "1;36"),
        miseenplace=_c("-- MISE EN PLACE --", "1;36"),
    ))
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    from .core import modeles as module_modeles

    if getattr(args, "catalogues", False):
        # Le catalogue des fournisseurs est garde a part du cache des
        # reponses : le premier vieillit en quelques semaines, le second vaut
        # de l'argent. Les jeter ensemble ferait repayer une fabrication
        # entiere pour rafraichir une liste de modeles.
        module_modeles.oublier()
        ok("Catalogues et substitutions oublies : ils seront redemandes aux "
           "fournisseurs au prochain appel.")
        return 0
    if args.vider:
        nombre = store.cache_vider()
        module_modeles.oublier()
        ok("{} reponses supprimees du cache".format(nombre))
    else:
        print("  {} reponses en cache".format(store.compter_reponses_cachees()))
        remplaces = module_modeles.substitutions()
        if remplaces:
            # Une substitution silencieuse est le genre de reparation qui fait
            # perdre une journee le jour ou elle cesse de suffire.
            print("\n  Modeles remplaces (l'identifiant configure n'est plus servi) :")
            for ou, modele in sorted(remplaces.items()):
                print("    {:26} -> {}".format(ou, modele))
        print("\n  Vider les reponses : " + _c("usine cache --vider", "1"))
        print("  Rafraichir les catalogues : "
              + _c("usine cache --catalogues", "1"))
    return 0


def cmd_specs(args: argparse.Namespace) -> int:
    """Ecrit la fiche technique de l'appareil, prete a etre poussee.

    « usine docteur » dit si l'usine peut produire maintenant. Cette
    fiche-la repond a l'autre question : ce qui devrait etre dans install.sh
    pour que CET appareil marche sans bricolage. Aucune cle n'y figure.
    """
    from .core import maj as module_maj
    from .core import specs as module_specs

    titre_console("Fiche technique de l'appareil")
    releve = module_specs.relever()
    texte = module_specs.en_markdown(releve)

    # A la racine du depot par defaut : c'est de la que la fiche part sur
    # GitHub, et la chercher ailleurs ferait perdre du temps a chaque fois.
    #
    # Mais seulement sur le telephone. Cette fiche-la decrit l'appareil pour
    # lequel le depot est ecrit ; lancee sur un ordinateur ou dans un
    # conteneur, la commande la remplacait par celle de la machine du moment.
    # C'est arrive deux fois : le 14/09/2026 (un test) puis le 24/09/2026 (un
    # balayage des commandes), la fiche d'un telephone Android devenant celle
    # d'un serveur x86_64 — sans erreur, a un « git add » pres d'etre poussee.
    sur_le_telephone = bool((releve.get("termux") or {}).get("termux"))
    if args.vers:
        cible = Path(args.vers)
    elif sur_le_telephone:
        cible = module_maj.racine() / "SPECS-APPAREIL.md"
    else:
        cible = config.WORKDIR / "SPECS-APPAREIL.md"
        alerte("Cet appareil n'est pas un telephone sous Termux : la fiche du "
               "depot, qui decrit le telephone, n'est pas remplacee.")
        print("      Pour l'ecrire ailleurs : " + _c("usine specs --vers FICHIER", "1"))
    try:
        cible.write_text(texte, encoding="utf-8")
    except OSError as exc:
        erreur(_expliquer_ecriture(exc) or str(exc))
        return 1

    manques = [m for m in module_specs._manques(releve)]
    bloquants = [m for m in manques if m["gravite"] == "bloquant"]
    for manque in manques:
        (erreur if manque["gravite"] == "bloquant" else alerte)(
            "{} — {}".format(manque["quoi"], manque["pourquoi"]))
        print("      " + _c(manque["commande"], "1"))
    if not manques:
        ok("Rien ne manque sur cet appareil.")
    ok("Fiche ecrite : {}".format(cible))

    if module_maj.est_un_clone() and (sur_le_telephone or args.vers):
        print("\n  La pousser sur le depot :")
        print("    " + _c("git add {} && git commit -m \"fiche technique\""
                          " && git push".format(cible.name), "1"))
    return 1 if bloquants else 0


def cmd_maj(args: argparse.Namespace) -> int:
    """Met a jour le code depuis le depot, sans toucher a l'atelier."""
    from .core import maj as module_maj

    titre_console("Mise a jour de l'usine")
    dossier = module_maj.racine()
    print("  Installation : {}".format(dossier))
    print("  Version      : {}".format(module_maj.version_installee()))
    print("  L'atelier et le fichier .env ne sont jamais touches.")

    par_git = module_maj.est_un_clone() and module_maj.git_disponible()
    if getattr(args, "archive", False):
        par_git = False
    sales = module_maj.modifications_locales() if par_git else []
    if sales and not getattr(args, "oui", False):
        alerte("{} fichier(s) modifie(s) ici seraient perdus :".format(len(sales)))
        for nom in sales[:8]:
            print("      " + nom)
        print("  Relancez avec " + _c("--oui", "1") + " si vous les abandonnez.")
        return 1

    if par_git:
        print("\n  Depot git detecte : mise a jour par « git pull --ff-only ».")
        resultat = module_maj.par_git(getattr(args, "branche", "") or "")
    else:
        branche = getattr(args, "branche", "") or module_maj.BRANCHE_DEFAUT
        print("\n  Pas de depot git ici : telechargement de l'archive « {} »."
              .format(branche))
        resultat = module_maj.par_archive(branche)

    if not resultat.get("ok"):
        erreur(str(resultat.get("erreur") or "mise a jour impossible"))
        if par_git:
            # « ff-only » refuse quand l'historique local a diverge. Le dire
            # evite de chercher une panne de reseau la ou il y a un commit
            # local.
            print("  Si votre depot a diverge, l'archive ignore l'historique : "
                  + _c("usine maj --archive", "1"))
        return 1

    if not resultat.get("change"):
        ok("Deja a jour ({}).".format(resultat.get("apres") or ""))
        return 0

    # On verifie dans un processus NEUF : les modules deja charges ici sont
    # l'ancienne version et repondraient « tout va bien » quoi qu'on installe.
    controle = module_maj.verifier()
    if not controle.get("ok"):
        erreur("L'usine mise a jour ne demarre pas : {}".format(
            controle.get("erreur")))
        if par_git:
            print("  Revenir en arriere : "
                  + _c("git -C {} reset --hard {}".format(
                      dossier, resultat.get("avant", "HEAD@{1}")), "1"))
        return 1
    ok("Mise a jour faite — {}".format(controle.get("version") or ""))
    # Les fournisseurs apparus depuis l'installation n'existent pas dans le
    # « .env » de quelqu'un qui a deja installe : « install.sh » ne le cree
    # qu'une fois, et la mise a jour n'y touche pas. Il ouvre « nano .env », ne
    # voit pas la variable, et conclut que l'integration n'existe pas.
    ajoutees = module_maj.completer_env(dossier)
    if ajoutees:
        ok("{} fournisseur(s) ajoute(s) a votre .env : {}".format(
            len(ajoutees), ", ".join(ajoutees)))
        print("  Vos cles existantes n'ont pas ete touchees. Pour coller les "
              "nouvelles : " + _c("nano {}/.env".format(dossier), "1"))
    if resultat.get("remplaces"):
        print("  Remplaces : " + ", ".join(str(n) for n in resultat["remplaces"]))
    print("\n  Verifier l'installation : " + _c("usine docteur", "1"))
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .web.serveur import demarrer

    return demarrer(args.port, args.hote)


# --------------------------------------------------------------------------
# Analyse des arguments
# --------------------------------------------------------------------------


def _options_du_type(sous: argparse.ArgumentParser, cle: str) -> None:
    """Ajoute les options que CE type de produit comprend, et lui seul.

    Elles sont declarees dans le catalogue, pas ici. Ecrites a la main dans
    trois endroits — l'analyseur, le gabarit du tableau de bord et son script —
    huit d'entre elles sur dix-sept avaient fini par ne plus exister que dans
    l'analyseur : on ne pouvait pas choisir, depuis le navigateur, si un outil
    logiciel etait une ligne de commande ou une application web.
    """
    from .pipelines.catalogue import obtenir

    fiche = obtenir(cle)
    if fiche is None:
        return
    for champ in fiche.champs:
        if champ.genre == "booleen":
            sous.add_argument(*champ.drapeaux, action="store_true",
                              help=champ.aide or champ.libelle)
            continue
        genre = {"entier": int, "decimal": float}.get(champ.genre, str)
        extra = {}
        if champ.choix:
            extra["choices"] = list(champ.choix)
        if champ.unite:
            extra["metavar"] = champ.unite.upper()
        # None, et pas la valeur du catalogue, pour ce que l'usine decide :
        # un « 50 » par defaut ne se distingue pas d'un « -n 50 » tape, et le
        # reglage n'etait donc jamais laisse a l'usine en ligne de commande.
        sous.add_argument(*champ.drapeaux, type=genre,
                          default=None if champ.decide_par_l_usine else champ.defaut,
                          help=champ.aide or champ.libelle, **extra)


def _options_communes(sous: argparse.ArgumentParser, avec_sujet: bool = True) -> None:
    if avec_sujet:
        # « nargs="?" » et non un positionnel obligatoire : sans sujet,
        # l'usine en choisit un. Le rendre obligatoire faisait que la seule
        # facon de ne pas dicter la niche etait de ne pas produire — alors
        # que choisir la niche est precisement ce qu'on lui demande.
        sous.add_argument("sujet", nargs="?", default="",
                          help="le sujet du produit, entre guillemets. "
                               "Omettez-le et l'usine choisit la niche "
                               "elle-meme.")
    # Les valeurs par defaut sont vides : elles sont reprises des reglages
    # (usine reglages), ce qui evite de retaper --auteur a chaque commande.
    sous.add_argument("-a", "--audience", default="",
                      help="a qui s'adresse le produit")
    # Pas de « choices » : les cinq tons sont des raccourcis, pas une liste
    # fermee. Imposer cinq voix a tout un catalogue est precisement ce qui
    # fait que les produits se ressemblent.
    sous.add_argument("-t", "--ton", default="",
                      help="raccourci ({}) ou description libre, ex : "
                           "-t \"comme un menuisier a son apprenti\""
                           .format("|".join(sorted(TONS))))
    sous.add_argument("-T", "--taille", default="",
                      help="raccourci ({}) ou nombre de sections, ex : -T 15"
                           .format("|".join(sorted(TAILLES))))
    sous.add_argument("--chapitres", type=int, default=0,
                      help="nombre exact de sections ({} a {})".format(
                          CHAPITRES_MIN, CHAPITRES_MAX))
    sous.add_argument("--mots", type=int, default=0,
                      help="mots visés par section ({} a {})".format(
                          MOTS_MIN, MOTS_MAX))
    sous.add_argument("--auteur", default="", help="nom affiche comme auteur")
    sous.add_argument("--langue", default="", help="langue de redaction")
    sous.add_argument("--marque", default="", help="nom de votre marque")
    sous.add_argument("--prix", default="", help="prix affiche, ex: 29 EUR")
    sous.add_argument("--dedicace", default="",
                      help="page de dedicace de l'EPUB, ex: \"Pour Julie\"")
    sous.add_argument("--contact", default="", help="e-mail de support dans la notice")
    # Pose par « usine reprendre », jamais tapee a la main : elle fait ecrire
    # la fabrication dans le dossier d'un produit existant.
    sous.add_argument("--reprendre-id", dest="reprendre_id", default="",
                      help=argparse.SUPPRESS)
    sous.add_argument("-q", "--qualite", default="",
                      choices=["", "rapide", "standard", "exigeant"],
                      help="rapide (sans relecture) | standard (1) | exigeant (2)")
    # « action="store_true" » et defaut None : on distingue « non demande »
    # de « refuse », sans quoi le reglage ne pourrait jamais etre actif.
    sous.add_argument("--sans-marketing", dest="sans_marketing",
                      action="store_true",
                      help="ne pas produire le kit de vente, meme si le "
                           "reglage « marketing_auto » le demande")
    sous.add_argument("--sans-zip", dest="sans_zip", action="store_true",
                      help="ne pas ecrire l'archive, meme si le reglage "
                           "« archive_auto » la demande")
    sous.add_argument("--marketing", action="store_true",
                      help="generer aussi le kit de vente")
    sous.add_argument("--extrait", type=int, default=0, metavar="N",
                      help="chapitres de l'edition courte offerte "
                           "(defaut : un quart du livre)")
    # Le defaut vient du REGLAGE, pas d'une constante. « gumroad » etait ecrit
    # en dur ici : le reglage « plateforme » etait affiche dans les trois
    # interfaces, enregistre sur disque, et lu par personne. Un reglage
    # orphelin est un mensonge fait a l'utilisateur — il croit avoir regle
    # quelque chose.
    sous.add_argument("--plateforme",
                      default=str(reglages.lire("plateforme", "gumroad")),
                      choices=sorted(vente.PLATEFORMES), help="plateforme de vente visee")
    sous.add_argument("--zip", action="store_true", help="produire l'archive livrable")
    sous.add_argument("--hors-ligne", dest="hors_ligne", action="store_true",
                      help="ne rien telecharger (IA locale, couverture generee sur place)")
    sous.add_argument("--sans-image", dest="sans_image", action="store_true",
                      help="ne pas generer d'images")


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="usine",
        description="Usine-IA — fabrique de produits digitaux, concue pour Termux.",
        epilog="Exemple : usine ebook \"la productivite pour freelances\" --marketing --zip",
    )
    parseur.add_argument("-v", "--version", action="version",
                         version="Usine-IA {}".format(__version__))
    sous_parseurs = parseur.add_subparsers(dest="commande")

    p = sous_parseurs.add_parser("ebook", help="fabriquer un ebook complet")
    _options_communes(p)
    p.add_argument("--relecture-ensemble", action="store_true",
                   help="une lecture du livre entier a la recherche des "
                        "contradictions entre chapitres (1 appel IA de plus)")
    p.set_defaults(fonction=cmd_ebook)

    p = sous_parseurs.add_parser(
        "nouvelle", help="fabriquer une nouvelle (fiction courte)")
    _options_communes(p)
    # Lus du catalogue, pas ecrits ici. « --serie » y etait declare a la
    # main, et le jour ou la fiction a recu neuf reglages de plus,
    # l'analyseur n'en a vu aucun : ils etaient saisissables depuis le
    # navigateur et introuvables en ligne de commande.
    _options_du_type(p, "nouvelle")
    p.set_defaults(fonction=cmd_nouvelle)

    p = sous_parseurs.add_parser(
        "roman", help="un roman : fiction longue, en parties, continuite tenue")
    _options_communes(p)
    _options_du_type(p, "roman")
    p.set_defaults(fonction=cmd_roman)

    p = sous_parseurs.add_parser(
        "interactive",
        help="un livre dont le lecteur est le heros (carte verifiee)")
    _options_communes(p)
    _options_du_type(p, "interactive")
    p.set_defaults(fonction=cmd_interactive, _type="interactive")

    p = sous_parseurs.add_parser(
        "recueil", help="un recueil de nouvelles liees par un fil")
    _options_communes(p)
    _options_du_type(p, "recueil")
    p.set_defaults(fonction=cmd_recueil, _type="recueil")

    p = sous_parseurs.add_parser(
        "feuilleton", help="un feuilleton : des episodes qui se lisent seuls")
    _options_communes(p)
    _options_du_type(p, "feuilleton")
    p.set_defaults(fonction=cmd_feuilleton, _type="feuilleton")

    p = sous_parseurs.add_parser(
        "conte", help="un conte jeunesse illustre, en doubles-pages")
    _options_communes(p)
    _options_du_type(p, "conte")
    p.set_defaults(fonction=cmd_conte, _type="conte")

    p = sous_parseurs.add_parser(
        "journal", help="ce que l'usine a fait pendant qu'on ne regardait pas")
    p.add_argument("jour", nargs="?", default="",
                   help="jour au format AAAA-MM-JJ (defaut : le plus recent)")
    p.add_argument("-n", "--lignes", type=int, default=40,
                   help="nombre de lignes a afficher")
    p.set_defaults(fonction=cmd_journal)

    p = sous_parseurs.add_parser(
        "series", help="lister les series et leurs tomes")
    p.add_argument("nom", nargs="?", default="",
                   help="detail d'une serie : sa distribution et ses faits")
    p.add_argument("--rafraichir", action="store_true",
                   help="refaire la derniere page des tomes anterieurs pour "
                        "qu'elle annonce les tomes parus depuis")
    p.set_defaults(fonction=cmd_series)

    p = sous_parseurs.add_parser("prompts", help="fabriquer un pack de prompts")
    _options_communes(p)
    _options_du_type(p, "prompts")
    p.set_defaults(fonction=cmd_prompts)

    p = sous_parseurs.add_parser("formation", help="fabriquer une mini-formation")
    _options_communes(p)
    _options_du_type(p, "formation")
    p.set_defaults(fonction=cmd_formation)

    p = sous_parseurs.add_parser("outils", help="fabriquer une boite a outils")
    _options_communes(p)
    _options_du_type(p, "outils")
    p.set_defaults(fonction=cmd_outils)

    p = sous_parseurs.add_parser("modeles",
                                 help="fabriquer des modeles Notion / tableur")
    _options_communes(p)
    _options_du_type(p, "modeles")
    p.set_defaults(fonction=cmd_modeles)

    p = sous_parseurs.add_parser("impression",
                                 help="fabriquer un cahier imprimable")
    _options_communes(p)
    _options_du_type(p, "impression")
    p.set_defaults(fonction=cmd_impression)

    p = sous_parseurs.add_parser("social", help="fabriquer un pack de publications")
    _options_communes(p)
    _options_du_type(p, "social")
    p.set_defaults(fonction=cmd_social)

    p = sous_parseurs.add_parser(
        "emails", help="fabriquer une sequence e-mail")
    _options_communes(p)
    _options_du_type(p, "emails")
    p.set_defaults(fonction=cmd_emails, _type="emails")

    p = sous_parseurs.add_parser(
        "memo", help="fabriquer un memo / une antiseche")
    _options_communes(p)
    _options_du_type(p, "memo")
    p.set_defaults(fonction=cmd_memo, _type="memo")

    p = sous_parseurs.add_parser(
        "quiz", help="fabriquer un quiz avec corrige")
    _options_communes(p)
    _options_du_type(p, "quiz")
    p.set_defaults(fonction=cmd_quiz, _type="quiz")

    p = sous_parseurs.add_parser("logiciel",
                                 help="fabriquer un outil logiciel verifie")
    _options_communes(p)
    _options_du_type(p, "logiciel")
    p.set_defaults(fonction=cmd_logiciel)

    p = sous_parseurs.add_parser("complet",
                                 help="offre complete : ebook + bonus + kit de vente + zip")
    _options_communes(p)
    p.add_argument("-r", "--reseau", default="", choices=[""] + sorted(social.RESEAUX),
                   help="reseau du pack bonus (decide par l'usine si absent)")
    p.set_defaults(fonction=cmd_complet)

    p = sous_parseurs.add_parser(
        "auto", help="l'usine choisit la niche ET le type de produit")
    _options_communes(p)
    p.set_defaults(fonction=cmd_auto, _type="auto")

    p = sous_parseurs.add_parser("idees", help="trouver quoi vendre dans une niche")
    _options_communes(p)
    # Lues au catalogue, comme pour les autres types : ecrites a la main ici,
    # « --nombre » valait 12 en dur, et l'usine ne le decidait jamais.
    _options_du_type(p, "idees")
    p.set_defaults(fonction=cmd_idees)

    p = sous_parseurs.add_parser("marketing", help="kit de vente d'un produit existant")
    p.add_argument("produit_id", help="identifiant du produit (voir : usine liste)")
    p.add_argument("--plateforme",
                   default=str(reglages.lire("plateforme", "gumroad")),
                   choices=sorted(vente.PLATEFORMES))
    p.add_argument("--prix", default="", help="prix affiche")
    p.add_argument("--extrait", type=int, default=0, metavar="N",
                   help="chapitres de l'edition courte offerte")
    p.set_defaults(fonction=cmd_marketing)

    p = sous_parseurs.add_parser("livrer", help="creer l'archive ZIP d'un produit")
    p.add_argument("produit_id", help="identifiant du produit")
    p.add_argument("--contact", default="", help="e-mail de support")
    p.set_defaults(fonction=cmd_livrer)

    p = sous_parseurs.add_parser("liste", help="lister les produits fabriques")
    p.add_argument("-n", "--nombre", type=int, default=25)
    p.set_defaults(fonction=cmd_liste)

    p = sous_parseurs.add_parser(
        "reprendre", help="finir un produit interrompu, sans repayer le reste")
    p.add_argument("produit_id", nargs="?", default="dernier",
                   help="identifiant, fin d'identifiant, ou « dernier »")
    p.set_defaults(fonction=cmd_reprendre)

    p = sous_parseurs.add_parser(
        "supprimer", help="effacer un produit et son dossier")
    p.add_argument("produit_id", nargs="?", default="dernier",
                   help="identifiant, fin d'identifiant, ou « dernier »")
    p.add_argument("--oui", action="store_true",
                   help="ne pas demander confirmation")
    p.set_defaults(fonction=cmd_supprimer)

    p = sous_parseurs.add_parser("ab", help="tester des titres et des couvertures")
    p.add_argument("action",
                   choices=["creer", "liste", "observer", "periode",
                            "rythme", "verdict", "planche", "clore",
                            "supprimer"])
    p.add_argument("identifiant", nargs="?", type=int, default=0,
                   help="numero du test, ou de la variante pour « observer »")
    p.add_argument("--produit", default="", help="partir d'un produit existant")
    p.add_argument("--titre", default="", help="titre actuel a ameliorer")
    p.add_argument("--sur", default="titre",
                   choices=["titre", "couverture", "accroche", "prix"],
                   help="ce que le test compare")
    p.add_argument("-n", "--nombre", type=int, default=5,
                   help="nombre de variantes")
    p.add_argument("-a", "--audience", default="")
    p.add_argument("--vues", type=int, help="vues observees, pour « observer »")
    p.add_argument("--actions", type=int,
                   help="clics ou ventes observes, pour « observer »")
    p.add_argument("--du", default="", metavar="AAAA-MM-JJ",
                   help="debut de mise en ligne, pour « periode »")
    p.add_argument("--au", default="", metavar="AAAA-MM-JJ",
                   help="fin de mise en ligne (defaut : toujours en ligne)")
    p.add_argument("--note", default="", help="commentaire libre")
    p.add_argument("--gagnante", type=int, default=0,
                   help="variante retenue, pour « clore »")
    p.add_argument("--hors-ligne", dest="hors_ligne", action="store_true")
    p.add_argument("--sans-image", dest="sans_image", action="store_true")
    p.set_defaults(fonction=cmd_ab)

    p = sous_parseurs.add_parser(
        "file",
        help="gerer la file des niches a produire",
        epilog="Types disponibles :\n" + "\n".join(
            "  {:<12} {} — {}".format(t.cle, t.resume, t.duree)
            for t in catalogue.tous(en_file=True)),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ajouter", nargs="+", metavar="NICHE",
                   help="ajouter une ou plusieurs niches")
    p.add_argument("--explorer", nargs="?", const="", default=None,
                   metavar="NICHE",
                   help="chercher des niches voisines et les mettre en file "
                        "(sans argument : part de ce qui a le mieux rapporte)")
    p.add_argument("--sans-veille", dest="sans_veille", action="store_true",
                   help="explorer sans aller lire les discussions")
    p.add_argument("--fiction", nargs="?", const="", default=None,
                   metavar="DEPART",
                   help="chercher des PROMESSES DE LECTURE au lieu de niches : "
                        "sous-genre, tropes, ambiance, chaleur, fin. Un "
                        "lecteur de roman n'achete pas la solution d'un "
                        "probleme (sans argument : l'usine choisit)")
    p.add_argument("--type", default="ebook", choices=catalogue.cles(en_file=True),
                   help="type de produit a fabriquer")
    p.add_argument("-n", "--nombre", type=int, default=0,
                   help="quantite (prompts, fiches, modules...)")
    p.add_argument("-a", "--audience", default="")
    p.add_argument("-t", "--ton", default="")
    p.add_argument("-q", "--qualite", default="")
    p.add_argument("--priorite", type=int, default=5,
                   help="1 = prioritaire, 9 = en dernier")
    p.add_argument("--statut", default="",
                   choices=["", "en_attente", "en_cours", "fait", "echec", "annule"])
    p.add_argument("--retirer", nargs="+", type=int, metavar="ID")
    p.add_argument("--rejouer", nargs="?", type=int, const=0, metavar="ID",
                   help="remettre en file les echecs (tous si aucun ID)")
    p.add_argument("--vider", action="store_true",
                   help="supprimer les entrees livrees et annulees")
    p.add_argument("--tout-vider", dest="tout_vider", action="store_true")
    p.set_defaults(fonction=cmd_file)

    p = sous_parseurs.add_parser(
        "usine", help="usine continue : produire en boucle sous budget")
    p.add_argument("action", nargs="?", default="statut",
                   choices=["demarrer", "statut", "arreter"])
    p.add_argument("--auto", action="store_true",
                   help="remplir la file automatiquement quand elle se vide")
    p.add_argument("--max", type=int, default=0,
                   help="s'arreter apres N produits")
    p.add_argument("--pause", type=int, default=None,
                   help="secondes entre deux produits")
    p.add_argument("--budget", nargs="+", metavar="NOM=VALEUR",
                   help="ex : --budget appels_jour=300 produits_jour=3")
    p.set_defaults(fonction=cmd_usine)

    p = sous_parseurs.add_parser(
        "marche", help="mesurer un marche depuis des sources publiques")
    p.add_argument("sujet", help="le sujet ou la niche a mesurer")
    p.add_argument("--json", action="store_true", help="enregistrer le rapport complet")
    p.set_defaults(fonction=cmd_marche)

    p = sous_parseurs.add_parser(
        "bilan", help="ce que l'usine a appris de vos productions")
    p.set_defaults(fonction=cmd_bilan)

    p = sous_parseurs.add_parser("menu", help="menu interactif (recommande sur mobile)")
    p.set_defaults(fonction=cmd_menu)

    p = sous_parseurs.add_parser(
        "ventes", help="enregistrer et lire les ventes reelles")
    p.add_argument("--importer", default="", metavar="FICHIER.csv",
                   help="importer un export de place de marche")
    p.add_argument("--sur", dest="plateforme_vente", default="gumroad",
                   help="plateforme d'origine (gumroad, etsy, payhip, site...)")
    p.add_argument("--ajouter", default="", metavar="PRODUIT_ID",
                   help="saisir une vente a la main")
    p.add_argument("--brut", type=float, default=None, help="montant encaisse")
    p.add_argument("--net", type=float, default=None,
                   help="ce qui reste apres commission, si vous le connaissez")
    p.add_argument("--unites", type=int, default=1)
    # Meme defaut orphelin que « plateforme » : qui vend en francs suisses
    # reglait sa devise et voyait « EUR » a chaque import.
    p.add_argument("--devise", default=str(reglages.lire("devise", "EUR")))
    p.add_argument("--date", default="", help="AAAA-MM-JJ (defaut : aujourd'hui)")
    p.add_argument("--reference", default="",
                   help="nom du produit tel qu'il apparait sur la plateforme")
    p.add_argument("--remboursement", action="store_true")
    p.add_argument("--lier", nargs=2, metavar=("REFERENCE", "PRODUIT_ID"),
                   help="rattacher une reference a un produit")
    p.add_argument("--rattacher", action="store_true",
                   help="rattacher automatiquement ce qui peut l'etre")
    p.add_argument("--depuis", default="", help="ne compter qu'a partir de AAAA-MM-JJ")
    p.add_argument("-n", "--nombre", type=int, default=15)
    p.set_defaults(fonction=cmd_ventes)

    p = sous_parseurs.add_parser(
        "veille", help="ce que les gens disent vraiment d'une niche")
    p.add_argument("sujet", help="la niche a explorer, entre guillemets")
    p.add_argument("-n", "--nombre", type=int, default=12,
                   help="discussions affichees")
    p.add_argument("-c", "--communautes", type=int, default=2,
                   help="communautes lues (chacune coute un appel)")
    p.add_argument("--periode", default="year",
                   choices=["day", "week", "month", "year", "all"],
                   help="fenetre de temps")
    p.set_defaults(fonction=cmd_veille)

    p = sous_parseurs.add_parser(
        "sauvegarde", help="mettre l'atelier a l'abri, ou le remettre en place")
    p.add_argument("--vers", default="", metavar="FICHIER.zip",
                   help="ou ecrire l'archive")
    p.add_argument("--avec-produits", dest="avec_produits",
                   action="store_true",
                   help="inclure les fichiers des produits (volumineux)")
    p.add_argument("--restaurer", default="", metavar="FICHIER.zip",
                   help="remettre l'atelier dans l'etat de cette archive")
    p.add_argument("--sans-produits", dest="sans_produits",
                   action="store_true",
                   help="a la restauration, ne pas reecrire les produits")
    p.add_argument("--inspecter", default="", metavar="FICHIER.zip",
                   help="voir ce que contient une archive, sans rien changer")
    p.add_argument("--oui", action="store_true",
                   help="confirmer une restauration")
    p.set_defaults(fonction=cmd_sauvegarde)

    p = sous_parseurs.add_parser(
        "doublons", help="reperer les produits qui se recouvrent")
    p.add_argument("-t", "--type", default="", choices=[""] + catalogue.cles(),
                   help="ne comparer qu'un type de produit")
    p.add_argument("-n", "--nombre", type=int, default=12,
                   help="nombre de paires affichees")
    p.add_argument("--reconstruire", action="store_true",
                   help="calculer les empreintes des produits deja fabriques")
    p.set_defaults(fonction=cmd_doublons)

    p = sous_parseurs.add_parser("reglages", help="consulter ou modifier vos reglages")
    p.add_argument("--definir", nargs="+", metavar="NOM=VALEUR",
                   help='ex : --definir auteur="Votre Nom" qualite=exigeant')
    p.add_argument("--reinitialiser", action="store_true")
    p.set_defaults(fonction=cmd_reglages)

    p = sous_parseurs.add_parser(
        "prompts-systeme",
        help="consulter ou personnaliser les prompts et les agents")
    p.add_argument("--exporter", action="store_true",
                   help="ecrire les prompts par defaut dans atelier/prompts/")
    p.add_argument("--reinitialiser", action="store_true",
                   help="supprimer toutes les personnalisations")
    p.set_defaults(fonction=cmd_prompts_systeme)

    p = sous_parseurs.add_parser("docteur", help="diagnostiquer l'installation")
    p.add_argument("--modeles", action="store_true",
                   help="verifier que les modeles configures existent encore "
                        "chez leur fournisseur (une requete par fournisseur)")
    p.add_argument("--essai", action="store_true",
                   help="appeler vraiment chaque modele declare et dire "
                        "lequel repond (un appel par modele, consomme du quota)")
    p.add_argument("--quotas", action="store_true",
                   help="confronter les quotas ecrits a ceux que chaque "
                        "service annonce dans ses en-tetes (un appel par "
                        "fournisseur)")
    p.add_argument("--reparer", action="store_true",
                   help="remplacer chaque identifiant mort par un qui repond "
                        "chez VOTRE compte, et le retenir")
    p.set_defaults(fonction=cmd_docteur)

    p = sous_parseurs.add_parser("cles", help="obtenir des cles API gratuites")
    p.set_defaults(fonction=cmd_cles)

    p = sous_parseurs.add_parser("cache", help="consulter ou vider le cache IA")
    p.add_argument("--vider", action="store_true",
                   help="supprimer les reponses gardees (elles seront repayees)")
    p.add_argument("--catalogues", action="store_true",
                   help="oublier la liste des modeles servis par chaque "
                        "fournisseur, sans toucher aux reponses")
    p.set_defaults(fonction=cmd_cache)

    p = sous_parseurs.add_parser(
        "specs", help="fiche technique de l'appareil, a pousser sur le depot")
    p.add_argument("--vers", default="",
                   help="ou ecrire la fiche (defaut : SPECS-APPAREIL.md a la "
                        "racine de l'installation)")
    p.set_defaults(fonction=cmd_specs)

    p = sous_parseurs.add_parser(
        "maj", help="mettre a jour l'usine depuis le depot")
    p.add_argument("--branche", default="",
                   help="branche a suivre (defaut : celle du clone, ou « {} »)"
                        .format("main"))
    p.add_argument("--archive", action="store_true",
                   help="telecharger l'archive meme si git est disponible")
    p.add_argument("--oui", action="store_true",
                   help="accepter de perdre les modifications locales")
    p.set_defaults(fonction=cmd_maj)

    p = sous_parseurs.add_parser("web", help="tableau de bord dans le navigateur")
    p.add_argument("-p", "--port", type=int, default=8777)
    p.add_argument("--hote", default="127.0.0.1")
    p.set_defaults(fonction=cmd_web)

    return parseur


def _fabrication(commande: str) -> bool:
    """Cette commande fabrique-t-elle un produit (donc : longue) ?

    Lu du catalogue plutot que recopie : un type ajoute demain prendra le
    verrou de veille sans qu'on y pense.
    """
    if not reglages.lire("verrou_veille", True):
        return False
    return commande in set(catalogue.cles()) | {"complet"}


def _annoncer_ce_qui_manque(manquants: List[Any], dossier: Path) -> None:
    """L'en-tete d'une reprise.

    Un produit coupe avant son export n'a pas de liste de sections
    manquantes : la chaine s'est arretee avant de la dresser. L'en-tete
    annoncait alors « 0 section(s) a refaire : inconnues » — zero, pour un
    produit a qui il manque tout ce qui suit la coupure.
    """
    from .pipelines import carnet

    if manquants:
        print("  {} section(s) a refaire : {}".format(
            len(manquants), ", ".join(str(m) for m in manquants[:8])))
    else:
        print("  Coupe avant la fin de sa fabrication : elle reprend la ou "
              "elle s'est arretee.")
    print("  {} deja au carnet, elles ne seront pas repayees."
          .format(carnet.compte(dossier)))


def _explique_le_cache() -> str:
    """Ce que l'utilisateur ignore et qui change tout : relancer ne repart pas de zero.

    Chaque reponse du modele est gardee en cache par empreinte de l'invite.
    Relancer la meme commande rejoue donc gratuitement tout ce qui avait deja
    ete paye, et ne facture que la suite. Sans cette phrase, l'utilisateur
    croit avoir brule sa journee de quota pour rien, et n'essaie pas.

    Mesure du 13/09/2026, ebook de 8 chapitres via le simulateur : 27 appels
    d'un trait ; coupe apres 6, la relance en a coute 21. La difference est
    exactement ce que le cache a rendu. On ne promet donc PAS une relance
    gratuite — ce serait faux des la premiere interruption precoce — mais une
    relance qui ne repaie pas ce qui est fait.
    """
    return ("Les reponses deja obtenues sont en cache : relancer la MEME "
            "commande reprend ou vous en etiez, sans repayer ce qui est fait.")


def _expliquer_ecriture(exc: OSError) -> str:
    """Traduit un echec d'ecriture en geste a faire — ou rend "" si ce n'en est pas un.

    Rendre "" plutot que deviner. « OSError » ne parle pas que du disque :
    « Address already in use » (tableau de bord deja lance) en est une, et
    annoncer un disque plein a qui a simplement lance « usine web » deux fois
    est exactement le garde-fou qui crie a tort. Le message generique, lui,
    reste juste. On ne parle donc que des trois errno qu'on sait traduire.
    """
    import errno

    if exc.errno == errno.ENOSPC:
        from .core import diagnostic as module_diagnostic

        espace = module_diagnostic.espace_libre()
        reste = (" Il reste {} Mo.".format(espace["libre_mo"])
                 if espace["connu"] else "")
        return ("Plus de place sur l'appareil.{} Faites de la place, puis "
                "relancez. {}".format(reste, _explique_le_cache()))
    if exc.errno in (errno.EACCES, errno.EPERM):
        return ("Ecriture refusee dans {}. Sur Android, un dossier de /sdcard "
                "demande l'autorisation de stockage : « termux-setup-storage ». "
                "{}".format(config.WORKDIR, _explique_le_cache()))
    if exc.errno == errno.EROFS:
        return ("Le dossier de travail est en lecture seule ({}). Choisissez-en "
                "un autre : USINE_HOME=~/Usine-IA. {}".format(
                    config.WORKDIR, _explique_le_cache()))
    return ""


def _expliquer_base(defaut: str) -> str:
    """Ce qu'on dit quand le fichier de base ne se lit plus.

    La panne rend l'usine ENTIEREMENT muette : toutes les commandes passent
    par la base, « docteur » et « sauvegarde » compris. L'utilisateur voyait
    « DatabaseError : file is not a database » sur chacune, sans savoir quel
    fichier, ni que ses produits, eux, sont intacts.

    Ce dernier point est le seul qui compte vraiment : les produits sont des
    FICHIERS dans produits/, et les reglages un JSON a cote. Ce que la base
    garde et qu'on perdrait, c'est l'historique, les ventes, les bibles de
    serie et le cache des reponses. On le dit tel quel plutot que de
    rassurer : une bible de serie perdue, c'est du contenu perdu.

    On n'efface rien : deplacer soi-meme la base de quelqu'un serait decider
    a sa place que son historique ne vaut rien.
    """
    return (
        "La base de l'atelier est illisible : {defaut}.\n"
        "  Fichier : {base}\n"
        "  Vos produits sont intacts : ce sont des fichiers dans {produits},\n"
        "  et vos reglages sont dans reglages.json. La base contient\n"
        "  l'historique, les ventes, les bibles de serie et le cache.\n"
        "\n"
        "  Si vous avez une sauvegarde :\n"
        "    usine sauvegarde --restaurer archive.zip --oui\n"
        "  Sinon, mettez la base de cote — l'usine en recreera une vide :\n"
        "    mv {base} {base}.casse"
    ).format(defaut=defaut, base=config.DB_PATH, produits=config.PRODUITS_DIR)


def _produit_commence(depuis: float) -> Optional[Dict[str, Any]]:
    """Le produit que cette commande a eu le temps de creer, s'il est inacheve.

    Coupee par le silence des fournisseurs, la commande conseillait de se
    relancer telle quelle. Mais une fois le dossier cree, la relancer en
    fabrique un SECOND : le premier restait « inacheve » dans la liste, et
    « usine reprendre » finissait par le refaire a cote de l'autre. La boucle
    et le tableau de bord le reprennent ; la ligne de commande doit le dire.
    """
    for produit in store.lister_produits(5):
        if (float(produit.get("cree_le") or 0) >= depuis
                and produit.get("statut") == "en_cours"):
            return produit
    return None


def principal(argv: Optional[List[str]] = None) -> int:
    config.load_env()
    config.ensure_dirs()
    # Retenue avant tout le reste : c'est ici, et seulement ici, qu'on connait
    # la commande telle qu'elle a ete tapee. « usine reprendre » la rejouera.
    from .pipelines import carnet

    carnet.retenir_commande(list(argv) if argv is not None else sys.argv[1:])
    parseur = construire_parseur()
    args = parseur.parse_args(argv)
    if not getattr(args, "commande", None):
        # Sur un terminal, le menu est plus praticable qu'une page d'aide ;
        # dans un script ou un tube, on garde l'aide.
        if sys.stdin.isatty() and sys.stdout.isatty():
            from .menu import menu_principal

            return menu_principal(lambda arguments: principal(arguments))
        print(BANNIERE.format(version=__version__))
        parseur.print_help()
        return 0
    debut = time.time()
    try:
        # Android suspend Termux quelques minutes apres l'extinction de
        # l'ecran. Une fabrication de 15 minutes n'y survit pas : le verrou
        # de veille est pris pour elle seule, et relache a la sortie.
        with telephone.veille_maintenue(_fabrication(args.commande)):
            return args.fonction(args)
    except KeyboardInterrupt:
        print()
        alerte("Interrompu. Le travail deja produit est conserve dans " +
               str(config.PRODUITS_DIR))
        return 130
    except SujetIntrouvable as exc:
        erreur(str(exc))
        # La cause est presque toujours la meme, et elle est verifiable : sans
        # fournisseur joignable, le prospecteur ne peut rien proposer. Le dire
        # ici evite de renvoyer vers « usine cles » quelqu'un dont le wifi est
        # simplement coupe.
        print()
        if not config.active_providers():
            print("  Aucun fournisseur n'est configure.")
            print("  Obtenir une cle gratuite : " + _c("usine cles", "1"))
        else:
            print("  Les fournisseurs configures n'ont pas repondu.")
            print("  Diagnostic : " + _c("usine docteur", "1"))
        print("\n  Vous pouvez aussi donner la niche vous-meme :")
        print("    " + _c('usine {} "votre sujet"'.format(
            getattr(args, "commande", "ebook")), "1"))
        return 3
    except llm.PlusDeFournisseur as exc:
        erreur(str(exc))
        # Le geste depend de la cause, et la cause se mesure : « usine cles »
        # est un conseil absurde quand le telephone est simplement sorti du
        # wifi. On demande donc au reseau, une fois, avant de conseiller.
        from .core.http import en_ligne

        commence = _produit_commence(debut)
        if commence:
            print("\n  Le produit « {} » est commence et garde au carnet. "
                  "Pour le finir sans repayer ce qui est fait :".format(
                      commence.get("titre") or commence["id"]))
            print("    " + _c("usine reprendre " + commence["id"], "1"))
        else:
            print("\n  " + _explique_le_cache())
        if not en_ligne():
            print("  Le reseau est coupe. Rebranchez le wifi ou les donnees "
                  "mobiles, puis relancez la meme commande.")
        else:
            print("\n  Diagnostic : " + _c("usine docteur", "1"))
            print("  Nouvelle cle : " + _c("usine cles", "1"))
        return 3
    except sqlite3.DatabaseError as exc:
        # On ne croit pas l'exception sur parole : « DatabaseError » couvre
        # aussi les defauts de requete. On rouvre le fichier et on demande a
        # SQLite. Sans base cassee, on retombe sur le message generique.
        defaut = store.diagnostic_base()
        erreur(_expliquer_base(defaut) if defaut
               else "{} : {}".format(type(exc).__name__, exc))
        if config.env_bool("USINE_DEBUG"):
            raise
        return 1
    except OSError as exc:
        # La panne la plus previsible sur un telephone, et celle que le
        # message brut expliquait le moins : « [Errno 28] No space left on
        # device » ne dit ni ou, ni quoi faire, ni — surtout — que le travail
        # deja fait n'est pas perdu.
        explication = _expliquer_ecriture(exc)
        erreur(explication or "{} : {}".format(type(exc).__name__, exc))
        if config.env_bool("USINE_DEBUG"):
            raise
        if not explication:
            print("  Details complets : USINE_DEBUG=1 usine ...")
        return 1
    except Exception as exc:
        erreur("{} : {}".format(type(exc).__name__, exc))
        if config.env_bool("USINE_DEBUG"):
            raise
        print("  Details complets : USINE_DEBUG=1 usine ...")
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(principal())
