"""Bus d'evenements : diffusion en direct vers le tableau de bord.

Chaque etape de fabrication publie un evenement. Le serveur web les relaie en
Server-Sent Events, ce qui alimente le journal en direct, les compteurs et
l'animation 3D sans aucune bibliotheque cliente.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from typing import Any, Callable, Dict, List

from .securite import expurger

_abonnes: List["queue.Queue[Dict[str, Any]]"] = []
# Des ecouteurs SYNCHRONES : la ligne de commande n'a pas de file a vider,
# elle affiche au moment ou l'evenement arrive. Sans eux, une attente du
# routeur — jusqu'a deux minutes — laissait le terminal muet, et sur un
# telephone on tue un processus muet.
_ecouteurs: List[Callable[[Dict[str, Any]], None]] = []
_verrou = threading.Lock()
_compteur = itertools.count(1)
_HISTORIQUE_MAX = 400
_historique: List[Dict[str, Any]] = []


def publier(type_evenement: str, **donnees: Any) -> Dict[str, Any]:
    """Diffuse un evenement a tous les abonnes connectes."""
    evenement: Dict[str, Any] = {
        "id": next(_compteur),
        "type": type_evenement,
        "ts": time.time(),
    }
    for nom, valeur in donnees.items():
        evenement[nom] = expurger(valeur) if isinstance(valeur, str) else valeur

    with _verrou:
        _historique.append(evenement)
        if len(_historique) > _HISTORIQUE_MAX:
            del _historique[: len(_historique) - _HISTORIQUE_MAX]
        abonnes = list(_abonnes)

    for file in abonnes:
        try:
            file.put_nowait(evenement)
        except queue.Full:
            pass  # abonne trop lent : on saute plutot que de bloquer l'usine
    for ecouteur in list(_ecouteurs):
        try:
            ecouteur(evenement)
        except Exception:
            pass  # un affichage rate ne doit pas arreter une fabrication
    return evenement


def ecouter(ecouteur: Callable[[Dict[str, Any]], None]) -> None:
    """Appelle « ecouteur » a chaque evenement. Une seule fois par fonction."""
    with _verrou:
        if ecouteur not in _ecouteurs:
            _ecouteurs.append(ecouteur)


def ne_plus_ecouter(ecouteur: Callable[[Dict[str, Any]], None]) -> None:
    with _verrou:
        if ecouteur in _ecouteurs:
            _ecouteurs.remove(ecouteur)


def abonner(taille: int = 200) -> "queue.Queue[Dict[str, Any]]":
    file: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=taille)
    with _verrou:
        _abonnes.append(file)
    return file


def desabonner(file: "queue.Queue[Dict[str, Any]]") -> None:
    with _verrou:
        if file in _abonnes:
            _abonnes.remove(file)


def historique(depuis_id: int = 0) -> List[Dict[str, Any]]:
    with _verrou:
        return [e for e in _historique if e["id"] > depuis_id]


def vider() -> None:
    with _verrou:
        _historique.clear()
