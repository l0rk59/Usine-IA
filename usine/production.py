"""Usine continue : consomme la file de niches, sous budget, jusqu'a l'arret.

Trois contraintes ont dicte la conception, toutes liees a Android :

  1. le systeme tue les processus en arriere-plan sans preavis — donc tout
     l'etat vit en base, et une entree laissee « en cours » est reprise au
     demarrage suivant ;
  2. les quotas gratuits sont limites — donc le budget est verifie avant
     chaque produit et avant chaque appel ;
  3. l'utilisateur veut pouvoir interrompre proprement — donc Ctrl+C termine
     le produit en cours au lieu de l'abandonner a moitie ecrit.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .core import apprentissage, budget, config, evenements, file, llm, reglages
from .pipelines import (boite_outils, ebook, formation, idees, impression,
                        modeles, pack_prompts, social)
from .pipelines.base import Contexte

FABRIQUES: Dict[str, Callable[[Contexte, Dict[str, Any]], Dict[str, Any]]] = {
    "ebook": lambda ctx, opt: ebook.produire(ctx),
    "prompts": lambda ctx, opt: pack_prompts.produire(ctx, nombre=opt.get("nombre", 50)),
    "formation": lambda ctx, opt: formation.produire(ctx, modules=opt.get("nombre", 0)),
    "outils": lambda ctx, opt: boite_outils.produire(ctx, nombre=opt.get("nombre", 10)),
    "modeles": lambda ctx, opt: modeles.produire(ctx, nombre=opt.get("nombre", 4)),
    "impression": lambda ctx, opt: impression.produire(ctx, pages=opt.get("nombre", 12)),
    "social": lambda ctx, opt: social.produire(
        ctx, nombre=opt.get("nombre", 30), reseau=opt.get("reseau", "linkedin")),
}


def chemin_etat() -> Path:
    return config.WORKDIR / "usine-etat.json"


def chemin_verrou() -> Path:
    return config.WORKDIR / "usine.pid"


# --------------------------------------------------------------------------
# Verrou : une seule usine a la fois
# --------------------------------------------------------------------------


def _processus_vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, mais appartient a quelqu'un d'autre
    except OSError:
        return False
    return True


def verrou_actif() -> Optional[int]:
    """PID de l'usine en cours, ou None. Nettoie un verrou orphelin."""
    chemin = chemin_verrou()
    if not chemin.exists():
        return None
    try:
        pid = int(chemin.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        chemin.unlink(missing_ok=True)
        return None
    if _processus_vivant(pid):
        return pid
    # Le processus a ete tue (Android le fait sans preavis) : le verrou ment.
    chemin.unlink(missing_ok=True)
    return None


def _poser_verrou() -> None:
    config.ensure_dirs()
    chemin_verrou().write_text(str(os.getpid()), encoding="utf-8")


def _lever_verrou() -> None:
    chemin_verrou().unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Etat partage, lisible depuis un autre terminal
# --------------------------------------------------------------------------


def ecrire_etat(etat: Dict[str, Any]) -> None:
    """Ecriture atomique : « usine statut » ne doit jamais lire un fichier a moitie."""
    config.ensure_dirs()
    cible = chemin_etat()
    temporaire = cible.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(etat, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    temporaire.replace(cible)


def lire_etat() -> Dict[str, Any]:
    chemin = chemin_etat()
    if not chemin.exists():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def statut() -> Dict[str, Any]:
    """Vue complete pour « usine usine statut » et le tableau de bord."""
    pid = verrou_actif()
    etat = lire_etat()
    compteur = budget.Compteur()
    return {
        "en_marche": pid is not None,
        "pid": pid,
        "file": file.compter(),
        "budget": compteur.etat(),
        "session": etat,
        "prochaines": [
            {"id": e["id"], "sujet": e["sujet"], "type": e["type"],
             "priorite": e["priorite"]}
            for e in file.lister("en_attente", 8)
        ],
    }


def demander_arret() -> bool:
    """Depose une demande d'arret que l'usine lira entre deux produits."""
    pid = verrou_actif()
    if pid is None:
        return False
    (config.WORKDIR / "usine.stop").write_text(str(time.time()), encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# Le moteur
# --------------------------------------------------------------------------


class UsineContinue:
    def __init__(
        self,
        auto: bool = False,
        maximum: int = 0,
        journal: Optional[Callable[[str], None]] = None,
        pause: Optional[int] = None,
    ):
        self.auto = auto
        self.maximum = maximum
        self.journal = journal or (lambda message: print("  " + message))
        self.compteur = budget.Compteur()
        self.pause = (reglages.lire("pause_entre_produits", 60)
                      if pause is None else pause)
        self.arret_demande = False
        self.arret_immediat = False
        self.debut = time.time()
        self.faits: List[Dict[str, Any]] = []
        self.motif_fin = ""

    # -- signaux -----------------------------------------------------------
    def _installer_signaux(self) -> None:
        def gerer(signum, cadre):  # noqa: ARG001
            if self.arret_demande:
                self.arret_immediat = True
                self.journal("Second signal : arret immediat.")
                raise KeyboardInterrupt
            self.arret_demande = True
            self.journal("Arret demande — le produit en cours est termine "
                         "puis l'usine s'arrete. (Ctrl+C a nouveau pour couper)")

        for nom in ("SIGINT", "SIGTERM"):
            if hasattr(signal, nom):
                try:
                    signal.signal(getattr(signal, nom), gerer)
                except (ValueError, OSError):
                    pass  # pas de signaux hors du thread principal

    def _arret_externe(self) -> bool:
        drapeau = config.WORKDIR / "usine.stop"
        if drapeau.exists():
            drapeau.unlink(missing_ok=True)
            self.journal("Arret demande depuis un autre terminal.")
            return True
        return False

    # -- etat --------------------------------------------------------------
    def _publier(self, courant: Optional[Dict[str, Any]] = None) -> None:
        etat = {
            "pid": os.getpid(),
            "demarre_le": self.debut,
            "duree": round(time.time() - self.debut, 1),
            "auto": self.auto,
            "courant": courant,
            "faits": self.faits[-20:],
            "nombre_faits": len(self.faits),
            "budget": self.compteur.etat(),
            "file": file.compter(),
            "motif_fin": self.motif_fin,
        }
        ecrire_etat(etat)
        evenements.publier("usine", **{k: v for k, v in etat.items()
                                       if k in ("courant", "nombre_faits",
                                                "budget", "file", "motif_fin")})

    # -- remplissage automatique -------------------------------------------
    def _remplir(self) -> int:
        """Genere de nouvelles niches quand la file se vide.

        On part des sujets qui ont donne les meilleures notes : c'est la seule
        base dont l'usine dispose, et elle vaut mieux qu'un tirage au hasard.
        """
        graine = ""
        for production in apprentissage.historique(30):
            if production.get("sujet") and production.get("note"):
                graine = production["sujet"]
                break
        if not graine:
            self.journal("Mode auto : aucun historique pour choisir une niche. "
                         "Ajoutez une premiere niche a la main.")
            return 0

        self.journal("File vide — exploration a partir de « {} »...".format(graine))
        contexte = Contexte(sujet=graine, journal=lambda m: None,
                            sans_image=True)
        try:
            resultat = idees.produire(contexte, nombre=8, avec_marche=False)
        except Exception as exc:
            self.journal("Exploration impossible : {}".format(exc))
            return 0

        ajoutees = 0
        for idee in resultat.get("idees", []):
            identifiant = file.ajouter(
                idee["titre"], idee.get("type", "ebook"),
                options={"audience": idee.get("acheteur", "")},
                priorite=5, source="auto")
            if identifiant:
                ajoutees += 1
        self.journal("{} niche(s) ajoutee(s) automatiquement.".format(ajoutees))
        return ajoutees

    # -- fabrication d'une entree -------------------------------------------
    def _fabriquer(self, entree: Dict[str, Any]) -> bool:
        type_produit = entree["type"]
        if type_produit not in FABRIQUES:
            file.echouer(entree["id"], "type inconnu : {}".format(type_produit))
            self.journal("  type inconnu : {}".format(type_produit))
            return False

        profil = reglages.charger()
        options = entree.get("options") or {}
        contexte = Contexte(
            sujet=entree["sujet"],
            audience=options.get("audience") or profil["audience"],
            ton=options.get("ton") or profil["ton"],
            taille=options.get("taille") or profil["taille"],
            qualite=options.get("qualite") or profil["qualite"],
            auteur=profil["auteur"],
            sans_image=not profil["images"],
            journal=lambda message: self.journal("    " + message),
        )

        self.compteur.demarrer_produit()
        budget.brancher(self.compteur)
        debut = time.time()
        try:
            resume = FABRIQUES[type_produit](contexte, options)
        except budget.BudgetEpuise as exc:
            # Un plafond atteint n'est pas une faute de la niche : elle repart
            # en file, intacte, pour la prochaine session.
            file.echouer(entree["id"], "budget : {}".format(exc))
            self.compteur.terminer_produit(reussi=False)
            self.motif_fin = str(exc)
            self.arret_demande = True
            self.journal("  {} — l'usine s'arrete, la niche reste en file."
                         .format(exc))
            return False
        except Exception as exc:
            statut_suivant = file.echouer(entree["id"], str(exc))
            self.compteur.terminer_produit(reussi=False)
            self.journal("  echec : {} ({})".format(exc, statut_suivant))
            return False
        finally:
            budget.brancher(None)

        file.terminer(entree["id"], resume.get("produit_id", ""))
        self.compteur.terminer_produit(reussi=True)
        if resume.get("budget_epuise"):
            # Le produit est sorti, mais degrade : on s'arrete la plutot que
            # d'en entamer un autre qui sortirait plus abime encore.
            self.motif_fin = "budget epuise pendant la fabrication"
            self.arret_demande = True
            self.journal("  budget epuise : produit exporte en l'etat, "
                         "l'usine s'arrete.")
        self.faits.append({
            "sujet": entree["sujet"], "type": type_produit,
            "titre": resume.get("titre", ""), "note": resume.get("note"),
            "duree": round(time.time() - debut, 1),
            "dossier": resume.get("dossier", ""),
        })
        self.journal("  livre : « {} »{} en {:.0f} s".format(
            resume.get("titre", entree["sujet"]),
            " — note {}/10".format(resume["note"]) if resume.get("note") else "",
            time.time() - debut))
        return True

    # -- boucle principale ---------------------------------------------------
    def tourner(self) -> int:
        if verrou_actif() is not None:
            self.journal("Une usine tourne deja (pid {}). "
                         "Arretez-la avec « usine usine arreter ».".format(
                             verrou_actif()))
            return 1

        config.ensure_dirs()
        (config.WORKDIR / "usine.stop").unlink(missing_ok=True)
        _poser_verrou()
        self._installer_signaux()

        orphelines = file.liberer_orphelins()
        if orphelines:
            self.journal("{} niche(s) reprise(s) apres un arret precedent."
                         .format(orphelines))

        plafonds = self.compteur.plafonds
        if plafonds.actif():
            self.journal("Budget : {} appels/jour, {} appels/produit, "
                         "{} produits/jour, {} min/produit.".format(
                             plafonds.appels_jour or "illimite",
                             plafonds.appels_produit or "illimite",
                             plafonds.produits_jour or "illimite",
                             plafonds.minutes_produit or "illimite"))
        else:
            self.journal("Aucun budget defini : l'usine tournera jusqu'a "
                         "epuisement des quotas de vos cles.")

        code = 0
        try:
            while True:
                if self.arret_demande or self._arret_externe():
                    self.motif_fin = self.motif_fin or "arret demande"
                    break
                if self.maximum and len(self.faits) >= self.maximum:
                    self.motif_fin = "{} produit(s) demandes, tous livres".format(
                        self.maximum)
                    break

                refus = self.compteur.peut_demarrer_produit()
                if refus:
                    self.motif_fin = refus
                    self.journal(refus)
                    break

                entree = file.prochain()
                if entree is None:
                    if self.auto and self._remplir():
                        continue
                    self.motif_fin = "file vide"
                    self.journal("File vide — l'usine s'arrete.")
                    break

                self.journal("[{}] {} — « {} »".format(
                    len(self.faits) + 1, entree["type"], entree["sujet"]))
                self._publier(courant={"id": entree["id"], "sujet": entree["sujet"],
                                       "type": entree["type"],
                                       "depuis": time.time()})
                self._fabriquer(entree)
                self._publier()

                if self.arret_demande:
                    continue
                if self.pause and file.compter()["en_attente"]:
                    self.journal("Pause de {} s (respect des quotas par minute)."
                                 .format(self.pause))
                    if not self._dormir(self.pause):
                        break
        except KeyboardInterrupt:
            self.motif_fin = "interrompu"
            code = 130
        finally:
            budget.brancher(None)
            self._publier()
            _lever_verrou()

        self._bilan()
        return code

    def _dormir(self, secondes: int) -> bool:
        """Pause interruptible : Ctrl+C ne doit pas attendre 60 secondes."""
        fin = time.time() + secondes
        while time.time() < fin:
            if self.arret_demande or self._arret_externe():
                return False
            time.sleep(min(1.0, fin - time.time()))
        return True

    def _bilan(self) -> None:
        duree = (time.time() - self.debut) / 60
        self.journal("")
        self.journal("Session terminee : {} produit(s) en {:.0f} min — {}".format(
            len(self.faits), duree, self.motif_fin or "fin"))
        notes = [f["note"] for f in self.faits if f.get("note") is not None]
        if notes:
            self.journal("Note moyenne : {:.1f}/10".format(sum(notes) / len(notes)))
        restantes = file.compter()
        if restantes["en_attente"]:
            self.journal("{} niche(s) encore en file — relancez quand vous "
                         "voulez.".format(restantes["en_attente"]))
