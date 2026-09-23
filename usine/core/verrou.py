"""Un seul a la fois : le systeme de fichiers tranche, pas nous.

Deux verrous vivent sur ces primitives : celui de l'usine continue (une seule
boucle par atelier) et celui d'un produit en reprise (une seule reprise par
produit). Elles etaient ecrites dans « production.py » pour le premier ; le
second en avait besoin, et une copie aurait fini par diverger de l'original.
"""

from __future__ import annotations

import os
from pathlib import Path


def processus_vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, mais appartient a quelqu'un d'autre
    except OSError:
        return False
    return True


def creer_exclusif(chemin: Path) -> bool:
    """Cree le fichier et y met notre PID, ou rend False s'il existe deja.

    La creation exclusive est atomique. « Verifier qu'il est libre, puis
    l'ecrire » laisse un intervalle entre les deux, et deux processus lances
    dans la meme seconde y passent ensemble.
    """
    try:
        with open(chemin, "x", encoding="utf-8") as sortie:
            sortie.write(str(os.getpid()))
        return True
    except (FileExistsError, OSError):
        return False


def detenteur(chemin: Path) -> int:
    """PID qui tient ce verrou, ou 0. Un verrou orphelin est nettoye.

    Android tue les processus sans preavis : un verrou dont le processus est
    mort mentirait pour toujours, et interdirait ce qu'il protege.
    """
    if not chemin.exists():
        return 0
    try:
        pid = int(chemin.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        chemin.unlink(missing_ok=True)
        return 0
    if processus_vivant(pid):
        return pid
    chemin.unlink(missing_ok=True)
    return 0


def prendre(chemin: Path) -> bool:
    """Prend le verrou, en reprenant un verrou orphelin."""
    if creer_exclusif(chemin):
        return True
    if detenteur(chemin):
        return False
    return creer_exclusif(chemin)
