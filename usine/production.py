"""Usine continue : consomme la file de niches, sous budget, jusqu'a l'arret.

Trois contraintes ont dicte la conception, toutes liees a Android :

  1. le systeme tue les processus en arriere-plan sans preavis — donc tout
     l'etat vit en base, et une entree laissee « en cours » est reprise au
     demarrage suivant ;
  2. les quotas gratuits sont limites — donc le budget est verifie avant
     chaque produit et avant chaque appel ;
  3. l'utilisateur veut pouvoir interrompre proprement — donc Ctrl+C termine
     le produit en cours au lieu de l'abandonner a moitie ecrit ;
  4. le telephone sert aussi a autre chose — donc l'usine prend le verrou de
     veille pour ne pas etre endormie, previent par notification quand un
     produit sort, et s'arrete avant de vider la batterie. Tout cela passe
     par « core.telephone », et ne fait rien du tout hors de Termux.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .core import (apprentissage, budget, config, empreinte, evenements,
                   file, llm, reglages, store, telephone)
from .pipelines import catalogue, idees
from .pipelines.base import Contexte

def types_disponibles() -> List[str]:
    """Types que la file accepte. Lu du catalogue, jamais recopie."""
    return catalogue.cles(en_file=True)


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


def graine_de_depart() -> str:
    """Le sujet a partir duquel chercher des niches voisines.

    L'ancienne version prenait la production la plus RECENTE portant une
    note, alors que son commentaire annoncait « les sujets qui ont donne les
    meilleures notes ». Entre une niche notee 9,5 et une notee 4,0 produite
    apres, elle repartait de celle a 4,0.

    Le classement se fait maintenant par chiffre d'affaires d'abord, note
    ensuite : le revenu est une mesure du marche, la note une mesure de
    l'usine, et quand les deux existent c'est le marche qui tranche.
    """
    meilleures = apprentissage.meilleures_niches(1)
    return meilleures[0]["sujet"] if meilleures else ""


def prospecter(nombre: int = 8, graine: str = "",
               journal: Optional[Callable[[str], None]] = None,
               avec_veille: bool = True) -> Dict[str, Any]:
    """Cherche des niches voisines et met en file celles qui sont nouvelles.

    C'est ce qui permet a l'usine de CHOISIR ce qu'elle fabrique au lieu
    d'attendre qu'on le lui dise. Trois garde-fous, dans cet ordre :

      1. la graine vient de ce qui a RAPPORTE, pas du dernier produit fait ;
      2. l'exploration s'appuie sur des discussions reelles et sur les
         mesures de marche, pas sur la seule imagination du modele. Le
         remplissage automatique se passait des deux ;
      3. une piste trop proche d'un produit DEJA FABRIQUE est ecartee avant
         d'entrer en file. La file ne se dedoublonne que sur elle-meme :
         sans ce filtre, l'usine refabriquait une niche deja traitee, et
         « usine doublons » ne le signalait qu'apres coup, le quota depense.
    """
    dire = journal or (lambda message: None)
    graine = graine or graine_de_depart()
    if not graine:
        dire("Aucun historique pour choisir une niche : ajoutez-en une a la "
             "main, l'usine partira de la.")
        return {"graine": "", "ajoutees": 0, "ecartees": [], "pistes": 0}

    dire("Exploration a partir de « {} »...".format(graine))
    contexte = Contexte(sujet=graine, journal=lambda m: None, sans_image=True)
    try:
        resultat = idees.produire(contexte, nombre=nombre, avec_marche=True,
                                  avec_veille=avec_veille)
    except Exception as exc:
        dire("Exploration impossible : {}".format(exc))
        return {"graine": graine, "ajoutees": 0, "ecartees": [], "pistes": 0}

    pistes = resultat.get("idees", [])
    ajoutees, ecartees = 0, []
    for idee in pistes:
        titre = idee.get("titre") or ""
        type_produit = idee.get("type", "ebook")
        proches = empreinte.sujets_proches(titre, type_produit)
        if proches:
            ecartees.append((titre, proches[0]["titre"] or proches[0]["sujet"]))
            continue
        if file.ajouter(titre, type_produit,
                        options={"audience": idee.get("acheteur", "")},
                        priorite=5, source="auto"):
            ajoutees += 1

    dire("{} piste(s) explorees, {} mise(s) en file.".format(
        len(pistes), ajoutees))
    for titre, deja in ecartees[:4]:
        dire("  ecartee : « {} » recouvre « {} »".format(
            titre[:38], (deja or "")[:38]))
    return {"graine": graine, "ajoutees": ajoutees, "ecartees": ecartees,
            "pistes": len(pistes)}


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
        self.batterie_minimum = int(reglages.lire("batterie_minimum", 0) or 0)
        self.notifications = bool(reglages.lire("notifications", True))
        self.veille = bool(reglages.lire("verrou_veille", True))
        self._veille_prise = False
        self.arret_batterie = False
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

    # -- notifications Android ----------------------------------------------
    def _fichier_a_montrer(self, resume: Dict[str, Any]) -> Optional[Path]:
        """Ce que la notification ouvre quand on la tape.

        Le PDF d'abord : c'est le fichier qu'on regarde pour juger un produit.
        A defaut l'EPUB, puis le dossier lui-meme.

        La liste vient du resume de fabrication, dans l'ordre ou les fichiers
        ont ete ecrits — le document principal d'abord, ses annexes ensuite.
        Un simple glob trie ne donne pas cet ordre : « guide-annexe.pdf »
        passe AVANT « guide.pdf », le tiret triant avant le point.
        """
        dossier = resume.get("dossier") or ""
        if not dossier:
            return None
        noms = resume.get("fichiers") or []
        for extension in (".pdf", ".epub", ".html"):
            nom = next((n for n in noms if n.endswith(extension)), "")
            if nom and (Path(dossier) / nom).exists():
                return Path(dossier) / nom
        return Path(dossier) if Path(dossier).exists() else None

    def _notifier(self, titre: str, contenu: str = "",
                  ouvrir: Optional[Path] = None, urgente: bool = False) -> None:
        """Previent le telephone. Sans termux-api, ne fait rien et ne coute rien."""
        if self.notifications:
            telephone.notifier(titre, contenu, ouvrir=ouvrir, urgente=urgente)

    # -- remplissage automatique -------------------------------------------
    def _remplir(self) -> int:
        """Genere de nouvelles niches quand la file se vide."""
        return prospecter(nombre=8, journal=self.journal)["ajoutees"]

    # -- fabrication d'une entree -------------------------------------------
    def _fabriquer(self, entree: Dict[str, Any]) -> bool:
        type_produit = entree["type"]
        if catalogue.obtenir(type_produit) is None:
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
            resume = catalogue.executer(type_produit, contexte, options)
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
        # Le signalement de doublon est pose par la chaine de fabrication
        # dans la fiche du produit : on le relit ici pour en tenir compte au
        # bilan de session, la ou la decision de publier se prend.
        fiche = store.lire_produit(resume.get("produit_id", "")) or {}
        meta = fiche.get("meta") or {}
        self.faits.append({
            "sujet": entree["sujet"], "type": type_produit,
            "titre": resume.get("titre", ""), "note": resume.get("note"),
            "duree": round(time.time() - debut, 1),
            "dossier": resume.get("dossier", ""),
            "doublon": meta.get("doublon"),
        })
        self.journal("  livre : « {} »{} en {:.0f} s".format(
            resume.get("titre", entree["sujet"]),
            " — note {}/10".format(resume["note"]) if resume.get("note") else "",
            time.time() - debut))
        self._notifier(
            "Produit {} pret".format(len(self.faits)),
            "{}{}".format(
                resume.get("titre", entree["sujet"])[:70],
                " — note {}/10".format(resume["note"]) if resume.get("note") else ""),
            ouvrir=self._fichier_a_montrer(resume))
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

        # Sans ce verrou, Android suspend Termux quelques minutes apres
        # l'extinction de l'ecran : la fabrication s'arrete en plein chapitre.
        self._veille_prise = telephone.verrou_veille(True) if self.veille else False
        if self._veille_prise:
            self.journal("Veille bloquee pendant la session "
                         "(relachee a la fin).")

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

                faible = telephone.batterie_trop_faible(self.batterie_minimum)
                if faible:
                    self.motif_fin = faible
                    self.arret_batterie = True
                    self.journal(faible)
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
            if self._veille_prise:
                telephone.verrou_veille(False)

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
        self._notifier(
            "Usine arretee — {} produit(s)".format(len(self.faits)),
            self.motif_fin or "fin de session",
            # Une batterie a plat demande un geste ; « file vide » non.
            urgente=self.arret_batterie)
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
        self._avant_de_publier()

    def _avant_de_publier(self) -> None:
        """Deux rappels a la fin d'un lot, parce que c'est la qu'on publie.

        Fabriquer vite et publier au meme rythme est le profil exact d'un
        compte qui se fait fermer : KDP limite la creation a dix titres par
        format et par semaine (verifie le 12 septembre 2026 sur la page
        d'aide d'Amazon — c'etait trois par jour jusqu'a fin 2025, un plafond
        plus large pour qui ne publie qu'en numerique) et ferme les comptes de
        contenu depose en volume. Un compte ferme emporte l'historique de
        ventes et les avis ; ralentir les depots ne coute rien.
        """
        if not self.faits:
            return
        doublons = [f for f in self.faits if f.get("doublon")]
        self.journal("")
        if doublons:
            self.journal("[!] {} produit(s) de cette session ressemblent a "
                         "des produits deja faits.".format(len(doublons)))
            self.journal("    Verifiez avant de les mettre en vente : "
                         "usine doublons")
        if len(self.faits) > 1:
            self.journal("Produire n'est pas publier : deposez un a deux "
                         "produits par semaine")
            self.journal("et par plateforme. Voir docs/VENDRE.md.")
