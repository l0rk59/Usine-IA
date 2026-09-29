"""Le telephone comme machine : notifications, batterie, verrou de veille.

L'usine continue tourne des heures sur un Android pose sur un coin de table,
ecran eteint. Trois choses manquaient a cette situation, et `termux-api` les
donne exactement :

  1. **savoir qu'un produit est pret** sans reveiller le telephone pour lire
     un terminal — une notification Android ;
  2. **ne pas vider la batterie** : une usine qui tourne jusqu'a l'extinction
     laisse un produit a moitie ecrit et un telephone mort ;
  3. **empecher Android d'endormir Termux** pendant une longue fabrication
     (`termux-wake-lock`), et relacher le verrou apres.

Tout ici est **facultatif**. `termux-api` n'est pas une dependance Python : ce
sont des binaires installes par `pkg install termux-api`. Quand ils sont
absents — sur un PC, dans l'integration continue, sur un Termux nu — chaque
fonction renvoie None ou False, sans lever, et l'usine se comporte comme
avant. C'est la contrainte fondatrice du projet : zero dependance, et rien
d'obligatoire.

Un piege merite le delai d'attente present partout ici : le paquet
`termux-api` installe les commandes, mais elles dialoguent avec
l'application **Termux:API**, a installer separement. Si le paquet est la
sans l'application, `termux-battery-status` **ne rend jamais la main**. Sans
timeout, l'usine se figerait avant son premier produit sur un telephone mal
configure — le pire des echecs, parce qu'il ne dit rien.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Assez pour un aller-retour avec l'application Termux:API, assez court pour
# qu'une installation incomplete ne bloque pas une session de production.
DELAI = 8

# Niveau sous lequel l'usine continue s'arrete, sauf telephone en charge.
BATTERIE_PLANCHER = 20

_IDENTIFIANT = "usine-ia"


def _binaire(nom: str) -> Optional[str]:
    return shutil.which(nom)


def sous_termux() -> bool:
    """Vrai si l'on tourne dans Termux, meme sans termux-api."""
    return (os.environ.get("TERMUX_VERSION") is not None
            or "com.termux" in os.environ.get("PREFIX", ""))


def api_disponible() -> bool:
    """Les commandes termux-api sont-elles installees ?"""
    return _binaire("termux-battery-status") is not None


def _executer(commande: List[str], delai: int = DELAI) -> Optional[str]:
    """Lance une commande termux-* et rend sa sortie, ou None si elle echoue.

    Aucune erreur ne remonte : l'absence de termux-api est le cas NORMAL
    (tout PC, toute machine d'integration continue), pas une panne.
    """
    chemin = _binaire(commande[0])
    if chemin is None:
        return None
    try:
        resultat = subprocess.run([chemin] + commande[1:], capture_output=True,
                                  text=True, timeout=delai)
    except (OSError, subprocess.SubprocessError):
        return None
    if resultat.returncode != 0:
        return None
    return resultat.stdout


# --------------------------------------------------------------------------
# Batterie
# --------------------------------------------------------------------------


def batterie() -> Optional[Dict[str, Any]]:
    """Niveau et etat de charge, ou None si l'information est hors de portee.

    None signifie « je ne sais pas » et jamais « batterie vide » : un appelant
    qui ne sait pas ne doit rien couper.
    """
    sortie = _executer(["termux-battery-status"])
    if not sortie:
        return None
    try:
        brut = json.loads(sortie)
    except ValueError:
        return None
    if not isinstance(brut, dict):
        return None
    try:
        niveau = int(brut.get("percentage"))
    except (TypeError, ValueError):
        return None
    statut = str(brut.get("status") or "").upper()
    branchee = str(brut.get("plugged") or "").upper()
    return {
        "niveau": max(0, min(100, niveau)),
        # « FULL » sur un telephone branche a 100 % ne dit pas CHARGING : les
        # deux signes comptent, sinon l'usine s'arrete sur secteur.
        "en_charge": statut in ("CHARGING", "FULL") or branchee.startswith("PLUGGED"),
        "statut": statut,
        "sante": str(brut.get("health") or ""),
    }


def batterie_trop_faible(plancher: int = BATTERIE_PLANCHER) -> str:
    """Motif d'arret si la batterie est trop basse, chaine vide sinon.

    Trois raisons de ne rien dire : plancher a zero (garde-fou coupe),
    batterie illisible (pas de termux-api, ou pas un telephone), telephone
    en charge — dans ce dernier cas le niveau monte, il ne descend pas.
    """
    if plancher <= 0:
        return ""
    etat = batterie()
    if etat is None or etat["en_charge"]:
        return ""
    if etat["niveau"] > plancher:
        return ""
    return ("batterie a {} % (plancher {} %) — l'usine s'arrete pour laisser "
            "le telephone vivant".format(etat["niveau"], plancher))


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


def notifier(titre: str, contenu: str = "", identifiant: str = _IDENTIFIANT,
             ouvrir: Optional[Path] = None, urgente: bool = False) -> bool:
    """Affiche (ou remplace) une notification Android. False si impossible.

    Le meme `identifiant` REMPLACE la notification precedente au lieu d'en
    empiler une nouvelle : une session de dix produits doit laisser une ligne
    dans le volet, pas dix.
    """
    if not titre:
        return False
    commande = ["termux-notification", "--id", identifiant,
                "--title", titre, "--content", contenu or "",
                "--priority", "high" if urgente else "default"]
    if ouvrir is not None:
        # termux-notification passe l'action a un shell : le chemin doit etre
        # echappe, un titre de produit contient des espaces et des apostrophes.
        commande += ["--action", "termux-open {}".format(shlex.quote(str(ouvrir)))]
    return _executer(commande) is not None


# --------------------------------------------------------------------------
# Verrou de veille
# --------------------------------------------------------------------------


def verrou_veille(actif: bool) -> bool:
    """Prend ou relache le verrou qui empeche Android d'endormir Termux.

    `termux-wake-lock` vient de termux-tools, present dans tout Termux : il
    marche donc meme sans l'application Termux:API.
    """
    return _executer(
        ["termux-wake-lock" if actif else "termux-wake-unlock"]) is not None


@contextlib.contextmanager
def veille_maintenue(actif: bool = True) -> Iterator[bool]:
    """Verrou de veille pendant un bloc, relache quoi qu'il arrive.

    Ne relache que si l'on a effectivement pris le verrou : couper la veille
    d'un autre processus qui l'avait posee serait pire que de ne rien faire.
    """
    pris = verrou_veille(True) if actif else False
    try:
        yield pris
    finally:
        if pris:
            verrou_veille(False)


# --------------------------------------------------------------------------
# Fichiers
# --------------------------------------------------------------------------


def ouvrir(chemin: Path) -> bool:
    """Ouvre un fichier avec l'application Android qui sait le lire.

    « termux-open » vient de termux-tools, present dans tout Termux : ouvrir
    un PDF ne demande donc pas l'application Termux:API.
    """
    if not Path(chemin).exists():
        return False
    return _executer(["termux-open", str(chemin)]) is not None


def partager(chemin: Path, titre: str = "") -> bool:
    """Envoie un fichier au partage Android : Drive, courriel, Telegram.

    C'est la reponse a « ou est passe mon ZIP » : sur un telephone, chercher
    un fichier dans une arborescence Termux depuis une application Android
    est un chemin de croix. Le partage le pousse la ou on veut le lire.
    """
    if not Path(chemin).exists():
        return False
    commande = ["termux-share", "--action", "send"]
    if titre:
        commande += ["--title", titre]
    # Delai plus large : le selecteur de partage attend que l'utilisateur
    # choisisse une application, ce qui n'a rien d'instantane.
    return _executer(commande + [str(chemin)], delai=120) is not None


# --------------------------------------------------------------------------
# Vue d'ensemble, pour « usine docteur » et le tableau de bord
# --------------------------------------------------------------------------


def etat() -> Dict[str, Any]:
    return {
        "termux": sous_termux(),
        "api": api_disponible(),
        "batterie": batterie(),
    }
