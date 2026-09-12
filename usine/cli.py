"""Interface en ligne de commande de l'Usine-IA.

Usage : usine <commande> [arguments]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .core import cles as pool_cles
from .core import apprentissage, budget, config, experience, images
from .core import file as file_prod
from .core import llm, marche
from .core import prompts as registre_prompts
from .core import empreinte, reglages, securite, store, telephone, ventes
from .core import verification
from .core.http import en_ligne
from .marketing import vente
from .packaging import livraison
from .pipelines import (boite_outils, catalogue, ebook, formation, idees,
                        impression, logiciel, modeles, nouvelle, pack_prompts,
                        social)
from .pipelines.base import (CHAPITRES_MAX, CHAPITRES_MIN, Contexte, MOTS_MAX,
                             MOTS_MIN, TAILLES, TONS)

# Couleurs ANSI : Termux les gere, mais on s'abstient si la sortie est redirigee.
_COULEUR = sys.stdout.isatty()


def _c(texte: str, code: str) -> str:
    return "\033[{}m{}\033[0m".format(code, texte) if _COULEUR else texte


def _milliers(nombre: int) -> str:
    """Nombre lisible a l'oeil : 200000 devient « 200 000 »."""
    return "{:,}".format(int(nombre)).replace(",", "\u202f")


def titre_console(texte: str) -> None:
    print("\n" + _c("== " + texte, "1;36"))


def ok(texte: str) -> None:
    print(_c("  [ok] ", "32") + texte)


def alerte(texte: str) -> None:
    print(_c("  [!] ", "33") + texte)


def erreur(texte: str) -> None:
    print(_c("  [x] ", "31") + texte, file=sys.stderr)


BANNIERE = r"""
  _   _     _              ___    _
 | | | |___(_)_ _  ___ ___|_ _|  /_\
 | |_| (_-< | ' \/ -_)___ | |  / _ \
  \___//__/_|_||_\___|    |___/_/ \_\   v{version}
  fabrique de produits digitaux — tourne sur Termux
"""


def contexte_depuis(args: argparse.Namespace) -> Contexte:
    """Construit le contexte : options de la commande, puis reglages, puis defauts."""
    profil = reglages.charger()

    def choisir(nom: str, defaut_profil: str) -> str:
        valeur = getattr(args, nom, None)
        return valeur if valeur else profil.get(defaut_profil, "")

    return Contexte(
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


def _apres_production(args: argparse.Namespace, ctx: Contexte,
                      resume: Dict[str, Any], description: str) -> Dict[str, Any]:
    """Kit de vente + archive, si demandes."""
    dossier = Path(resume["dossier"])
    if getattr(args, "marketing", False):
        titre_console("Kit de vente")
        try:
            kit = vente.produire_kit(
                ctx, resume["titre"], description, dossier,
                plateforme=getattr(args, "plateforme", "gumroad"),
                couverture=next(
                    (n for n in resume.get("fichiers", []) if n.startswith("couverture")), ""
                ),
                # Le nom de la commande EST la cle du catalogue : c'est
                # l'invariant du projet, autant s'y appuyer.
                type_produit=getattr(args, "commande", "ebook"),
                chapitres_offerts=getattr(args, "extrait", 0) or 0,
            )
            resume["marketing"] = kit["fichiers"]
            if kit.get("extrait"):
                resume["extrait"] = kit["extrait"]
            prix = (kit["fiche"].get("prix_conseille") or {}).get("cible")
            ok("Kit de vente pret ({} fichiers)".format(len(kit["fichiers"])))
            if prix:
                ok("Prix conseille : {} EUR".format(prix))
        except Exception as exc:
            alerte("Kit de vente non genere : {}".format(exc))

    if getattr(args, "zip", False):
        titre_console("Mise en carton")
        from .pipelines.base import slug

        archive = livraison.empaqueter(
            dossier, slug(resume["titre"], 46), resume["titre"], ctx.auteur,
            promesse=description[:200], contact=getattr(args, "contact", "") or
            "votre adresse e-mail",
        )
        resume["archive"] = str(archive)
        ok("Archive : {} ({} Ko)".format(archive.name, archive.stat().st_size // 1024))
    return resume


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
    _avertir_sujet(args.sujet)
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un ebook")
    resume = ebook.produire(
        ctx, relecture_ensemble=getattr(args, "relecture_ensemble", False))
    description = "Ebook de {} chapitres, {} mots. {}".format(
        resume["chapitres"], resume["mots"], resume.get("sous_titre", "")
    )
    _resume_console(_apres_production(args, ctx, resume, description))
    return 0


def cmd_nouvelle(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    _avertir_sujet(args.sujet)
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une nouvelle")
    resume = nouvelle.produire(ctx, serie=getattr(args, "serie", "") or "")
    description = "Nouvelle{}, {} scenes, {} mots.".format(
        " — " + resume["sous_titre"] if resume.get("sous_titre") else "",
        resume["scenes"], resume["mots"])
    if resume.get("rang"):
        description = "Tome {} de « {} ». ".format(
            resume["rang"], args.serie) + description
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


def cmd_prompts(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un pack de prompts")
    resume = pack_prompts.produire(ctx, nombre=args.nombre)
    _resume_console(_apres_production(
        args, ctx, resume, "Pack de {} prompts professionnels.".format(resume["prompts"])
    ))
    return 0


def cmd_formation(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'une mini-formation")
    resume = formation.produire(ctx, modules=args.modules,
                                narration=getattr(args, "narration", False))
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
    resume = boite_outils.produire(ctx, nombre=args.nombre)
    _resume_console(_apres_production(
        args, ctx, resume, "Boite de {} outils pratiques.".format(resume["outils"])
    ))
    return 0


def cmd_modeles(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication de modeles Notion / tableur")
    resume = modeles.produire(ctx, nombre=args.nombre)
    _resume_console(_apres_production(
        args, ctx, resume,
        "Systeme de {} bases liees, CSV prets a importer.".format(resume["bases"])))
    return 0


def cmd_impression(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un cahier imprimable")
    resume = impression.produire(ctx, pages=args.nombre,
                                 reliure=getattr(args, "reliure", 0) or 0)
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
    resume = logiciel.produire(ctx, cible=args.cible,
                               executer=not args.sans_essai)
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
        "devise": (args.devise or "EUR").upper(),
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
            alerte("Aucune piste retenue : toutes recouvrent un produit deja "
                   "fabrique.")
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
            if courant:
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
        print("  Note moyenne : {} /10   (meilleure {} — pire {})".format(
            donnees["note_moyenne"], donnees["note_meilleure"], donnees["note_pire"]))
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
    resume = social.produire(ctx, nombre=args.nombre, reseau=args.reseau,
                             visuels=args.visuels)
    _resume_console(_apres_production(
        args, ctx, resume, "Pack de {} publications prets a publier.".format(resume["posts"])
    ))
    return 0


def cmd_idees(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Exploration de niche")
    resultat = idees.produire(ctx, nombre=args.nombre,
                              avec_marche=not getattr(args, "sans_marche", False),
                              avec_veille=not getattr(args, "sans_veille", False))
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
        bonus_social = social.produire(ctx_social, nombre=10, reseau=args.reseau,
                                       visuels=0)
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
    dossier = Path(produit["dossier"])
    meta = produit.get("meta") or {}
    ctx = Contexte(
        sujet=produit["sujet"] or produit["titre"],
        audience=produit["audience"] or "un public francophone motive",
        auteur=meta.get("auteur", "Usine-IA"),
        ton=meta.get("ton", "pro"),
        prix=args.prix or "",
        journal=lambda message: print("  " + message),
    )
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
        contact=args.contact or "votre adresse e-mail",
    )
    ok("Archive : {} ({} Ko)".format(archive, archive.stat().st_size // 1024))
    return 0


def cmd_liste(args: argparse.Namespace) -> int:
    produits = store.lister_produits(args.nombre)
    if not produits:
        print("  Aucun produit pour l'instant. Essayez : "
              + _c('usine ebook "votre sujet"', "1"))
        return 0
    titre_console("Produits fabriques")
    for produit in produits:
        meta = produit.get("meta") or {}
        marque = "pret" if produit["statut"] == "pret" else produit["statut"]
        print("  {}  {}".format(
            _c(time.strftime("%d/%m %H:%M", time.localtime(produit["cree_le"])), "2"),
            _c(produit["titre"][:58], "1"),
        ))
        print("     {} | {} | {}".format(produit["type"], marque, produit["id"]))
        if meta.get("mots"):
            print("     {} mots".format(meta["mots"]))
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
                    ligne.get("jetons_aujourdhui", 0), _milliers(ligne["tpd"]))
            print("  {} {:<13} {:<9} {:<28} {}/{} aujourd'hui{}{}".format(
                _c("v", "32"), ligne["nom"], genre, ligne["modele"],
                ligne["aujourdhui"], ligne["rpd"], _c(budget, "90"),
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

    titre_console("Verdict")
    verdict = etat["verdict"]
    (alerte if verdict["etat"] == "bloque" else ok)(verdict["message"])
    if verdict["etat"] == "local":
        print("      Comptez plusieurs minutes par chapitre : un modele de 3")
        print("      milliards de parametres produit 3 a 10 jetons par seconde")
        print("      sur un telephone. Le delai d'attente est regle en")
        print("      consequence ({} s par appel).".format(
            config.PROVIDERS_BY_NAME["ollama"].timeout))
    elif verdict["etat"] == "bloque":
        print("      " + _c("usine cles", "1"))

    details = etat["pool"]
    if details:
        titre_console("Pool de cles — rotation automatique")
        for detail in details:
            etat = (_c("disponible", "32") if detail["disponible"]
                    else _c("repos {}s".format(detail["repos_restant"]), "33"))
            print("  {:<13} {:<14} {:>4} appels aujourd'hui   {}".format(
                detail["fournisseur"], detail["cle"], detail["appels_jour"], etat))

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
    if args.vider:
        nombre = store.cache_vider()
        ok("{} reponses supprimees du cache".format(nombre))
    else:
        with store.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cache")
            print("  {} reponses en cache".format(cur.fetchone()[0]))
        print("  Vider : usine cache --vider")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .web.serveur import demarrer

    return demarrer(args.port, args.hote)


# --------------------------------------------------------------------------
# Analyse des arguments
# --------------------------------------------------------------------------


def _options_communes(sous: argparse.ArgumentParser, avec_sujet: bool = True) -> None:
    if avec_sujet:
        sous.add_argument("sujet", help="le sujet du produit, entre guillemets")
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
    sous.add_argument("-q", "--qualite", default="",
                      choices=["", "rapide", "standard", "exigeant"],
                      help="rapide (sans relecture) | standard (1) | exigeant (2)")
    sous.add_argument("--marketing", action="store_true",
                      help="generer aussi le kit de vente")
    sous.add_argument("--extrait", type=int, default=0, metavar="N",
                      help="chapitres de l'edition courte offerte "
                           "(defaut : un quart du livre)")
    sous.add_argument("--plateforme", default="gumroad",
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
    p.add_argument("--serie", default="",
                   help="ranger ce recit dans une serie : le tome reprend le "
                        "monde, la distribution et les faits des precedents, "
                        "et la continuite est verifiee contre eux")
    p.set_defaults(fonction=cmd_nouvelle)

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
    p.add_argument("-n", "--nombre", type=int, default=50, help="nombre de prompts")
    p.set_defaults(fonction=cmd_prompts)

    p = sous_parseurs.add_parser("formation", help="fabriquer une mini-formation")
    _options_communes(p)
    p.add_argument("--narration", action="store_true",
                   help="script a lire a voix haute (un appel IA par module)")
    p.add_argument("-m", "--modules", type=int, default=0, help="nombre de modules")
    p.set_defaults(fonction=cmd_formation)

    p = sous_parseurs.add_parser("outils", help="fabriquer une boite a outils")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=10, help="nombre d'outils")
    p.set_defaults(fonction=cmd_outils)

    p = sous_parseurs.add_parser("modeles",
                                 help="fabriquer des modeles Notion / tableur")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=4, help="nombre de bases")
    p.set_defaults(fonction=cmd_modeles)

    p = sous_parseurs.add_parser("impression",
                                 help="fabriquer un cahier imprimable")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=12, help="nombre de fiches")
    p.add_argument("--reliure", type=float, default=0, metavar="MM",
                   help="marge interieure en mm pour l'impression a la demande "
                        "(0 = aucune ; votre imprimeur publie la sienne)")
    p.set_defaults(fonction=cmd_impression)

    p = sous_parseurs.add_parser("social", help="fabriquer un pack de publications")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=30, help="nombre de publications")
    p.add_argument("-r", "--reseau", default="linkedin",
                   choices=sorted(social.RESEAUX), help="reseau vise")
    p.add_argument("--visuels", type=int, default=0,
                   help="nombre de visuels a generer")
    p.set_defaults(fonction=cmd_social)

    p = sous_parseurs.add_parser("logiciel",
                                 help="fabriquer un outil logiciel verifie")
    _options_communes(p)
    p.add_argument("-c", "--cible", default="cli", choices=sorted(logiciel.CIBLES),
                   help="cli (outil en ligne de commande), web (page autonome), "
                        "extension (Chrome Manifest V3)")
    p.add_argument("--sans-essai", dest="sans_essai", action="store_true",
                   help="analyser le code sans jamais l'executer")
    p.set_defaults(fonction=cmd_logiciel)

    p = sous_parseurs.add_parser("complet",
                                 help="offre complete : ebook + bonus + kit de vente + zip")
    _options_communes(p)
    p.add_argument("-r", "--reseau", default="linkedin", choices=sorted(social.RESEAUX))
    p.set_defaults(fonction=cmd_complet)

    p = sous_parseurs.add_parser("idees", help="trouver quoi vendre dans une niche")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=12, help="nombre d'idees")
    p.add_argument("--sans-veille", dest="sans_veille", action="store_true",
                   help="ne pas aller lire les discussions (Reddit limite le "
                        "debit : deux appels espaces, parfois une attente)")
    p.add_argument("--sans-marche", dest="sans_marche", action="store_true",
                   help="ne pas interroger les sources de marche")
    p.set_defaults(fonction=cmd_idees)

    p = sous_parseurs.add_parser("marketing", help="kit de vente d'un produit existant")
    p.add_argument("produit_id", help="identifiant du produit (voir : usine liste)")
    p.add_argument("--plateforme", default="gumroad", choices=sorted(vente.PLATEFORMES))
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
    p.add_argument("--devise", default="EUR")
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
    p.set_defaults(fonction=cmd_docteur)

    p = sous_parseurs.add_parser("cles", help="obtenir des cles API gratuites")
    p.set_defaults(fonction=cmd_cles)

    p = sous_parseurs.add_parser("cache", help="consulter ou vider le cache IA")
    p.add_argument("--vider", action="store_true")
    p.set_defaults(fonction=cmd_cache)

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


def principal(argv: Optional[List[str]] = None) -> int:
    config.load_env()
    config.ensure_dirs()
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
    except llm.PlusDeFournisseur as exc:
        erreur(str(exc))
        print("\n  Diagnostic : " + _c("usine docteur", "1"))
        print("  Nouvelle cle : " + _c("usine cles", "1"))
        return 3
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
