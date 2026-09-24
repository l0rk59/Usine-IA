"""Budget de production : ce qui empeche l'usine de vider vos quotas.

Une usine qui tourne seule pendant la nuit peut epuiser toutes vos cles avant
le matin. Le budget fixe des plafonds et les fait respecter a trois niveaux :

  - avant chaque produit : refuse d'en demarrer un si le reste est insuffisant ;
  - pendant un produit   : coupe les appels au-dela du plafond par produit ;
  - au fil de l'eau      : compte les appels reels, pas une estimation.

Un depassement en cours de produit n'annule rien. Les chapitres deja rediges
sont conserves et le livre est exporte tel quel : mieux vaut un ebook de huit
chapitres sur douze qu'un dossier vide.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from . import reglages, store


class BudgetEpuise(RuntimeError):
    """Leve quand un appel ferait depasser un plafond."""

    def __init__(self, plafond: str, consomme: int, limite: int):
        super().__init__(
            "budget « {} » atteint : {} / {}".format(plafond, consomme, limite))
        self.plafond = plafond
        self.consomme = consomme
        self.limite = limite


@dataclass
class Plafonds:
    """Limites de production. 0 signifie « pas de limite »."""

    appels_jour: int = 0
    appels_produit: int = 0
    produits_jour: int = 0
    minutes_produit: int = 0
    jetons_jour: int = 0

    @classmethod
    def depuis_reglages(cls) -> "Plafonds":
        return cls(
            appels_jour=int(reglages.lire("budget_appels_jour", 0) or 0),
            appels_produit=int(reglages.lire("budget_appels_produit", 0) or 0),
            produits_jour=int(reglages.lire("budget_produits_jour", 0) or 0),
            minutes_produit=int(reglages.lire("budget_minutes_produit", 0) or 0),
            jetons_jour=int(reglages.lire("budget_jetons_jour", 0) or 0),
        )

    def actif(self) -> bool:
        return any((self.appels_jour, self.appels_produit,
                    self.produits_jour, self.minutes_produit,
                    self.jetons_jour))


class Compteur:
    """Suit la consommation d'une session de production.

    Les appels du jour sont lus en base (ils survivent a un redemarrage, ce qui
    compte sur Termux ou Android tue les processus). Les compteurs par produit
    sont remis a zero a chaque nouveau produit.
    """

    def __init__(self, plafonds: Optional[Plafonds] = None):
        self.plafonds = plafonds or Plafonds.depuis_reglages()
        self.produits_faits = 0
        self._debut_produit = 0.0
        # Les requetes du produit en cours, comptees ICI et pas relues en
        # base : la base recoit aussi celles des autres fils. Voir
        # « brancher » pour la mesure.
        self._appels_produit = 0
        # Le plafond de l'UTILISATEUR qui a coupe le produit en cours, s'il y
        # en a un. Les chaines attrapent de la meme facon ce refus et le
        # silence des fournisseurs (« PLUS_RIEN_A_DEMANDER ») ; l'usine
        # continue doit pourtant les distinguer : l'un l'arrete, l'autre la
        # fait attendre que les quotas repartent.
        self.refus = ""

    # -- consommation reelle ---------------------------------------------
    def appels_aujourdhui(self) -> int:
        debut = time.mktime(time.strptime(
            time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
        return store.compteur_intervalle(debut)

    def appels_produit(self) -> int:
        return self._appels_produit if self._debut_produit else 0

    def jetons_aujourdhui(self) -> int:
        debut = time.mktime(time.strptime(
            time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
        return store.tokens_intervalle(debut)

    def minutes_produit(self) -> float:
        if not self._debut_produit:
            return 0.0
        return (time.time() - self._debut_produit) / 60.0

    # -- cycle de vie ------------------------------------------------------
    def demarrer_produit(self) -> None:
        self.refus = ""
        self._debut_produit = time.time()
        self._appels_produit = 0

    def terminer_produit(self, reussi: bool = True) -> None:
        if reussi:
            self.produits_faits += 1
        self._debut_produit = 0.0

    # -- verifications -----------------------------------------------------
    def peut_demarrer_produit(self) -> Optional[str]:
        """Renvoie le motif de refus, ou None si on peut lancer un produit."""
        p = self.plafonds
        if p.produits_jour and self.produits_faits >= p.produits_jour:
            return "plafond de {} produit(s) par jour atteint".format(p.produits_jour)
        if p.jetons_jour and self.jetons_aujourdhui() >= p.jetons_jour:
            return "plafond de {} jetons par jour atteint".format(p.jetons_jour)
        if p.appels_jour:
            restants = p.appels_jour - self.appels_aujourdhui()
            if restants <= 0:
                return "plafond de {} appels par jour atteint".format(p.appels_jour)
            # Demarrer un produit qu'on ne pourra pas finir gaspille le reste
            # du budget ET laisse un dossier incomplet.
            minimum = max(8, (p.appels_produit or 20) // 3)
            if restants < minimum:
                return ("il reste {} appel(s) sur {} : trop peu pour un produit "
                        "complet".format(restants, p.appels_jour))
        return None

    def verifier_appel(self) -> None:
        """Appele avant chaque requete IA. Leve BudgetEpuise si un plafond tombe."""
        try:
            self._verifier_appel()
        except BudgetEpuise as exc:
            self.refus = str(exc)
            raise
        self._appels_produit += 1

    def _verifier_appel(self) -> None:
        p = self.plafonds
        if p.jetons_jour:
            consommes = self.jetons_aujourdhui()
            if consommes >= p.jetons_jour:
                raise BudgetEpuise("jetons par jour", consommes, p.jetons_jour)
        if p.appels_jour:
            consomme = self.appels_aujourdhui()
            if consomme >= p.appels_jour:
                raise BudgetEpuise("appels par jour", consomme, p.appels_jour)
        if p.appels_produit and self._debut_produit:
            consomme = self.appels_produit()
            if consomme >= p.appels_produit:
                raise BudgetEpuise("appels par produit", consomme, p.appels_produit)
        if p.minutes_produit and self._debut_produit:
            ecoulees = self.minutes_produit()
            if ecoulees >= p.minutes_produit:
                raise BudgetEpuise("minutes par produit",
                                   int(ecoulees), p.minutes_produit)

    def etat(self) -> Dict[str, Any]:
        p = self.plafonds
        return {
            "actif": p.actif(),
            "appels_jour": self.appels_aujourdhui(),
            "appels_jour_max": p.appels_jour,
            "appels_produit": self.appels_produit(),
            "appels_produit_max": p.appels_produit,
            "produits_faits": self.produits_faits,
            "produits_jour_max": p.produits_jour,
            "minutes_produit": round(self.minutes_produit(), 1),
            "minutes_produit_max": p.minutes_produit,
            "jetons_jour": self.jetons_aujourdhui(),
            "jetons_jour_max": p.jetons_jour,
            "reste_aujourdhui": (p.appels_jour - self.appels_aujourdhui()
                                 if p.appels_jour else None),
        }


# --------------------------------------------------------------------------
# Garde branchee sur le routeur IA
# --------------------------------------------------------------------------

# Une garde PAR FIL. Le tableau de bord fait tourner l'usine continue dans un
# fil, et l'on peut appuyer sur « Generer » pendant ce temps. Mesure du
# 24/09/2026, plafond de douze appels par produit, deux ebooks qui en
# demandent dix chacun : seuls, ils passaient ; ensemble, les DEUX sortaient
# inacheves et l'usine s'arretait sur « budget epuise ». La garde etait
# globale — le produit du tableau de bord, qui n'a aucun plafond, se faisait
# couper par celui de la boucle — et le compte par produit relisait en base
# les appels de tous les fils.
_local = threading.local()


def brancher(compteur: Optional[Compteur]) -> None:
    """Installe (ou retire) la garde du fil courant."""
    _local.garde = compteur.verifier_appel if compteur is not None else None


def verifier() -> None:
    """Appele par le routeur. Sans budget branche dans ce fil, ne fait rien."""
    garde: Optional[Callable[[], None]] = getattr(_local, "garde", None)
    if garde is not None:
        garde()
