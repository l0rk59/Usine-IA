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
from .core import config, llm, store
from .core.http import en_ligne
from .marketing import vente
from .packaging import livraison
from .pipelines import boite_outils, ebook, formation, idees, pack_prompts, social
from .pipelines.base import Contexte, TAILLES, TONS

# Couleurs ANSI : Termux les gere, mais on s'abstient si la sortie est redirigee.
_COULEUR = sys.stdout.isatty()


def _c(texte: str, code: str) -> str:
    return "\033[{}m{}\033[0m".format(code, texte) if _COULEUR else texte


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
    return Contexte(
        sujet=args.sujet,
        audience=args.audience,
        langue=args.langue,
        ton=args.ton,
        taille=args.taille,
        auteur=args.auteur,
        prix=getattr(args, "prix", "") or "",
        marque=getattr(args, "marque", "") or "",
        hors_ligne=args.hors_ligne,
        sans_image=args.sans_image or args.hors_ligne,
        journal=lambda message: print("  " + message),
    )


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
            )
            resume["marketing"] = kit["fichiers"]
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
    print("\n  Ouvrir sur Termux : " + _c(
        "termux-open '{}'".format(
            next((str(Path(resume["dossier"]) / n) for n in resume.get("fichiers", [])
                  if n.endswith(".pdf")), resume["dossier"])
        ), "2"))


def cmd_ebook(args: argparse.Namespace) -> int:
    if not _verifier_fournisseurs():
        return 2
    ctx = contexte_depuis(args)
    titre_console("Fabrication d'un ebook")
    resume = ebook.produire(ctx)
    description = "Ebook de {} chapitres, {} mots. {}".format(
        resume["chapitres"], resume["mots"], resume.get("sous_titre", "")
    )
    _resume_console(_apres_production(args, ctx, resume, description))
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
    resume = formation.produire(ctx, modules=args.modules)
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
    resultat = idees.produire(ctx, nombre=args.nombre)
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
    meta = json.loads(produit.get("meta") or "{}")
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
                             plateforme=args.plateforme)
    for nom in kit["fichiers"]:
        ok(nom)
    print("  Dossier : " + kit["dossier"])
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
    meta = json.loads(produit.get("meta") or "{}")
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
        meta = json.loads(produit.get("meta") or "{}")
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
    print(BANNIERE.format(version=__version__))
    titre_console("Environnement")
    ok("Python {}".format(sys.version.split()[0]))
    ok("Dossier de travail : {}".format(config.WORKDIR))
    ok("Fichier .env : {}".format(
        config.ENV_PATH if config.ENV_PATH.exists() else "absent (usine cles)"
    ))
    reseau = en_ligne()
    (ok if reseau else alerte)(
        "Reseau : {}".format("disponible" if reseau else
                             "indisponible — seule l'IA locale fonctionnera")
    )

    titre_console("Fournisseurs IA")
    lignes = llm.diagnostic()
    for ligne in lignes:
        genre = "local" if ligne["local"] else ("sans cle" if ligne["sans_cle"] else "cle API")
        if ligne["disponible"]:
            print("  {} {:<13} {:<9} {:<28} {}/{} aujourd'hui".format(
                _c("v", "32"), ligne["nom"], genre, ligne["modele"],
                ligne["aujourdhui"], ligne["rpd"]))
        else:
            print("  {} {:<13} {:<9} definir {} — {}".format(
                _c("-", "90"), ligne["nom"], genre, ligne["cle_env"], ligne["inscription"]))

    disponibles = [l for l in lignes if l["disponible"] and not l["local"]]
    locaux_actifs = _tester_locaux()
    titre_console("Verdict")
    if disponibles:
        ok("{} fournisseur(s) distant(s) pret(s). L'usine peut produire.".format(
            len(disponibles)))
    elif locaux_actifs:
        ok("IA locale detectee : {}. Production hors ligne possible.".format(
            ", ".join(locaux_actifs)))
    else:
        alerte("Aucun fournisseur pret. Lancez : " + _c("usine cles", "1"))

    stats = store.stats_fournisseurs()
    if stats:
        titre_console("Consommation du jour")
        for stat in stats:
            print("  {:<14} {} appels, {} reussis, {} tokens, {:.1f}s en moyenne".format(
                stat["fournisseur"], stat["total"], stat["reussites"] or 0,
                stat["tokens"] or 0, stat["latence"] or 0))
    return 0


def _tester_locaux() -> List[str]:
    """Verifie si un serveur d'IA locale repond."""
    from .core.http import HttpErreur, requete

    actifs: List[str] = []
    for nom in ("ollama", "llamacpp"):
        fournisseur = config.PROVIDERS_BY_NAME[nom]
        url = fournisseur.base_url.rstrip("/") + "/models"
        try:
            statut, _ = requete(url, timeout=3)
            if statut < 500:
                actifs.append(nom)
        except HttpErreur:
            continue
    return actifs


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
    sous.add_argument("-a", "--audience", default="un public francophone motive",
                      help="a qui s'adresse le produit")
    sous.add_argument("-t", "--ton", default="pro", choices=sorted(TONS),
                      help="ton de redaction (defaut : pro)")
    sous.add_argument("-T", "--taille", default="standard", choices=sorted(TAILLES),
                      help="volume du produit (defaut : standard)")
    sous.add_argument("--auteur", default="Usine-IA", help="nom affiche comme auteur")
    sous.add_argument("--langue", default="francais", help="langue de redaction")
    sous.add_argument("--marque", default="", help="nom de votre marque")
    sous.add_argument("--prix", default="", help="prix affiche, ex: 29 EUR")
    sous.add_argument("--contact", default="", help="e-mail de support dans la notice")
    sous.add_argument("--marketing", action="store_true",
                      help="generer aussi le kit de vente")
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
    p.set_defaults(fonction=cmd_ebook)

    p = sous_parseurs.add_parser("prompts", help="fabriquer un pack de prompts")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=50, help="nombre de prompts")
    p.set_defaults(fonction=cmd_prompts)

    p = sous_parseurs.add_parser("formation", help="fabriquer une mini-formation")
    _options_communes(p)
    p.add_argument("-m", "--modules", type=int, default=0, help="nombre de modules")
    p.set_defaults(fonction=cmd_formation)

    p = sous_parseurs.add_parser("outils", help="fabriquer une boite a outils")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=10, help="nombre d'outils")
    p.set_defaults(fonction=cmd_outils)

    p = sous_parseurs.add_parser("social", help="fabriquer un pack de publications")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=30, help="nombre de publications")
    p.add_argument("-r", "--reseau", default="linkedin",
                   choices=sorted(social.RESEAUX), help="reseau vise")
    p.add_argument("--visuels", type=int, default=0,
                   help="nombre de visuels a generer")
    p.set_defaults(fonction=cmd_social)

    p = sous_parseurs.add_parser("complet",
                                 help="offre complete : ebook + bonus + kit de vente + zip")
    _options_communes(p)
    p.add_argument("-r", "--reseau", default="linkedin", choices=sorted(social.RESEAUX))
    p.set_defaults(fonction=cmd_complet)

    p = sous_parseurs.add_parser("idees", help="trouver quoi vendre dans une niche")
    _options_communes(p)
    p.add_argument("-n", "--nombre", type=int, default=12, help="nombre d'idees")
    p.set_defaults(fonction=cmd_idees)

    p = sous_parseurs.add_parser("marketing", help="kit de vente d'un produit existant")
    p.add_argument("produit_id", help="identifiant du produit (voir : usine liste)")
    p.add_argument("--plateforme", default="gumroad", choices=sorted(vente.PLATEFORMES))
    p.add_argument("--prix", default="", help="prix affiche")
    p.set_defaults(fonction=cmd_marketing)

    p = sous_parseurs.add_parser("livrer", help="creer l'archive ZIP d'un produit")
    p.add_argument("produit_id", help="identifiant du produit")
    p.add_argument("--contact", default="", help="e-mail de support")
    p.set_defaults(fonction=cmd_livrer)

    p = sous_parseurs.add_parser("liste", help="lister les produits fabriques")
    p.add_argument("-n", "--nombre", type=int, default=25)
    p.set_defaults(fonction=cmd_liste)

    p = sous_parseurs.add_parser("docteur", help="diagnostiquer l'installation")
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


def principal(argv: Optional[List[str]] = None) -> int:
    config.load_env()
    config.ensure_dirs()
    parseur = construire_parseur()
    args = parseur.parse_args(argv)
    if not getattr(args, "commande", None):
        print(BANNIERE.format(version=__version__))
        parseur.print_help()
        return 0
    try:
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
