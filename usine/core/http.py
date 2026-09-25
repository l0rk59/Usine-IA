"""Petit client HTTP base sur urllib (aucune dependance, Termux-friendly).

Et le point unique ou l'on decide de RECOMMENCER. Mesure du 15/09/2026 :
le routeur IA rejouait un appel deux fois avec attente et basculait de
fournisseur, mais tout le reste du reseau tentait UNE fois, sans attendre —
les illustrations, le sondage de marche, le catalogue de modeles, la mise a
jour, la veille. Une coupure d'une seconde sur un forfait mobile perdait
donc une illustration pour de bon, et le journal disait « 0 image ».
"""

from __future__ import annotations

import contextlib
import gzip
import json
import random
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

USER_AGENT = "Usine-IA/1.0 (+termux; python-stdlib)"


class HttpErreur(Exception):
    def __init__(self, statut: int, message: str, corps: str = "",
                 entetes: Optional[Dict[str, str]] = None):
        super().__init__("HTTP {} : {}".format(statut, message))
        self.statut = statut
        self.corps = corps
        # Les en-tetes de la reponse. « Retry-After » y dit combien de temps
        # le service demande d'attendre : sans eux, le routeur ne pouvait que
        # deviner, et il devinait toujours la meme chose.
        self.entetes = dict(entetes or {})

    def patienter(self) -> float:
        """Secondes demandees par « Retry-After », ou 0 si le service se tait.

        Deux formes existent : un nombre de secondes, ou une date HTTP. La
        seconde est rare mais legale, et la lire evite d'attendre zero quand
        le service demandait dix minutes.
        """
        brut = ""
        for nom, valeur in self.entetes.items():
            if nom.lower() == "retry-after":
                brut = str(valeur).strip()
                break
        if not brut:
            return 0.0
        try:
            return max(0.0, min(3600.0, float(brut)))
        except ValueError:
            pass
        try:
            from email.utils import parsedate_to_datetime

            cible = parsedate_to_datetime(brut)
        except (TypeError, ValueError):
            return 0.0
        if cible is None:
            return 0.0
        reste = cible.timestamp() - time.time()
        return max(0.0, min(3600.0, reste))

    @property
    def temporaire(self) -> bool:
        return self.statut in (408, 409, 425, 429, 500, 502, 503, 504, 529, 0)


class HorsLigne(HttpErreur):
    """Une connexion que l'usine se refuse : « --hors-ligne » est en cours.

    Definitive, pas temporaire : « insister » ne doit pas la rejouer avec
    attente, elle dirait non dans deux secondes comme maintenant.
    """

    def __init__(self, hote: str):
        super().__init__(0, "hors ligne : aucune connexion vers {}".format(
            hote or "?"))

    @property
    def temporaire(self) -> bool:
        return False


_fil = threading.local()
_BOUCLE = ("127.0.0.1", "localhost", "::1")


@contextlib.contextmanager
def hors_ligne(actif: bool = True):
    """Le temps du bloc, ce fil ne sort pas de l'appareil.

    « --hors-ligne » promettait « ne rien telecharger ». Chaque module
    devait s'en souvenir, et le routeur IA ne le faisait pas : ses invites
    partaient chez le premier fournisseur distant. L'audit du 14/09/2026 avait
    compte « zero connexion » — avec le simulateur, qui remplace le routeur,
    donc exactement la ou la fuite se produisait. Toute connexion passe par
    ce module : c'est ici qu'on la refuse, une fois pour toutes.

    Restent permis la boucle locale et l'adresse des serveurs d'IA locale,
    qui peut etre celle d'un ordinateur du reseau domestique : l'utilisateur
    l'a configuree pour cela. Par fil, parce que le tableau de bord fabrique
    plusieurs produits a la fois dans le meme processus.
    """
    avant = getattr(_fil, "hors_ligne", False)
    _fil.hors_ligne = avant or bool(actif)
    try:
        yield
    finally:
        _fil.hors_ligne = avant


def hors_ligne_actif() -> bool:
    return bool(getattr(_fil, "hors_ligne", False))


def _verifier_sortie(url: str) -> None:
    if not hors_ligne_actif():
        return
    hote = (urllib.parse.urlsplit(url).hostname or "").lower()
    if hote in _BOUCLE:
        return
    from . import config

    locaux = {(urllib.parse.urlsplit(p.base_url).hostname or "").lower()
              for p in config.PROVIDERS if p.local}
    if hote not in locaux:
        raise HorsLigne(hote)


def _contexte_ssl() -> ssl.SSLContext:
    return ssl.create_default_context()


def requete(
    url: str,
    methode: str = "GET",
    entetes: Optional[Dict[str, str]] = None,
    donnees: Optional[bytes] = None,
    timeout: int = 120,
) -> Tuple[int, bytes]:
    """Effectue une requete et renvoie (statut, corps brut)."""
    statut, brut, _ = requete_complete(url, methode, entetes, donnees, timeout)
    return statut, brut


def requete_complete(
    url: str,
    methode: str = "GET",
    entetes: Optional[Dict[str, str]] = None,
    donnees: Optional[bytes] = None,
    timeout: int = 120,
) -> Tuple[int, bytes, Dict[str, str]]:
    """Comme « requete », mais rend aussi les en-tetes de la reponse.

    Ils etaient jetes, et c'est une source de verite qu'on n'avait pas : un
    fournisseur y annonce sa limite de requetes, sa limite de jetons, ce qu'il
    en reste, et dans combien de temps le compteur repart. Les quotas ecrits
    dans « config.py » sont recopies d'une page de documentation — donnee
    perissable s'il en est — et rien ne les avait jamais confrontes a ce que
    le service DIT lui-meme.
    """
    _verifier_sortie(url)
    tetes = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    tetes.update(entetes or {})
    req = urllib.request.Request(url, data=donnees, headers=tetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_contexte_ssl()) as rep:
            brut = rep.read()
            if rep.headers.get("Content-Encoding", "") == "gzip":
                brut = gzip.decompress(brut)
            return rep.status, brut, dict(rep.headers)
    except urllib.error.HTTPError as exc:
        corps = b""
        try:
            corps = exc.read()
            if exc.headers.get("Content-Encoding", "") == "gzip":
                corps = gzip.decompress(corps)
        except Exception:
            pass
        raise HttpErreur(exc.code, exc.reason or "erreur",
                         corps.decode("utf-8", "replace"),
                         entetes=dict(exc.headers.items()) if exc.headers else None)
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as exc:
        raise HttpErreur(0, "reseau indisponible : {}".format(exc))


def post_json(
    url: str,
    charge: Dict[str, Any],
    entetes: Optional[Dict[str, str]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    tetes = {"Content-Type": "application/json"}
    tetes.update(entetes or {})
    corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
    _, brut = requete(url, "POST", tetes, corps, timeout)
    return json.loads(brut.decode("utf-8", "replace"))


def get_bytes(url: str, entetes: Optional[Dict[str, str]] = None, timeout: int = 180) -> bytes:
    _, brut = requete(url, "GET", entetes, None, timeout)
    return brut


def en_ligne(timeout: int = 6) -> bool:
    """Teste la connectivite sortante.

    On passe par HTTPS plutot que par un socket brut : c'est le seul test qui
    reste valable derriere un proxy d'entreprise ou un reseau mobile filtre.
    """
    if hors_ligne_actif():
        return False  # meme pas pour savoir : c'est une connexion
    try:
        statut, _ = requete("https://text.pollinations.ai/", "GET", timeout=timeout)
        return statut < 500
    except HttpErreur as exc:
        # Une reponse HTTP, meme en erreur, prouve que la sortie reseau fonctionne.
        if exc.statut > 0:
            return True
    except Exception:
        pass
    for hote in ("1.1.1.1", "8.8.8.8"):
        try:
            sock = socket.create_connection((hote, 53), timeout=min(timeout, 4))
            sock.close()
            return True
        except OSError:
            continue
    return False


def attendre(secondes: float) -> None:
    if secondes > 0:
        time.sleep(secondes)


# Trois essais, pas dix. Sur un telephone, une panne qui dure plus de quelques
# secondes dure en general des minutes : le forfait est coupe, le Wi-Fi a
# saute, le service est en panne. Insister dix fois vide la batterie pour
# arriver au meme resultat, plus tard — et la bascule de fournisseur du
# routeur, elle, repond en une seconde.
TENTATIVES = 3
ATTENTE_INITIALE = 1.5
ATTENTE_MAXIMALE = 20.0

T = TypeVar("T")


def patienter(secondes: float, arret: Optional[Callable[[], bool]] = None) -> bool:
    """Attend, par tranches d'une seconde. Faux si « arret » a demande la fin.

    Un « time.sleep(20) » d'un seul bloc fait attendre vingt secondes a un
    Ctrl+C. L'utilisateur tue alors le processus a la main, en laissant la
    base dans l'etat qu'on imagine. C'est la meme raison qui a fait ecrire
    « _dormir » dans le moteur continu, et c'est la meme regle ici : une
    boucle qui dort reste interruptible.
    """
    fin = time.time() + max(0.0, secondes)
    while time.time() < fin:
        if arret is not None and arret():
            return False
        time.sleep(min(1.0, fin - time.time()))
    return True


def insister(action: Callable[[], T], tentatives: int = TENTATIVES,
             attente: float = ATTENTE_INITIALE,
             plafond: float = ATTENTE_MAXIMALE,
             journal: Optional[Callable[[str], None]] = None,
             arret: Optional[Callable[[], bool]] = None) -> T:
    """Rejoue une action reseau tant qu'elle echoue de facon TEMPORAIRE.

    Ce qui est rejoue, et pourquoi :

      - une « HttpErreur » temporaire (429, 5xx, et le statut 0 qui signifie
        « le reseau n'a pas repondu ») : le service dira peut-etre oui dans
        deux secondes ;
      - toute AUTRE exception, parce qu'en pratique c'est une reponse qu'on
        n'a pas su lire — un JSON tronque par une coupure, un corps vide. Le
        cout d'un essai inutile est un appel ; le cout de ne pas reessayer
        est une illustration perdue ou une scene manquante.

    Ce qui n'est PAS rejoue : une « HttpErreur » definitive. Une cle refusee
    (401), un acces interdit (403), un modele qui n'existe pas (404), un
    credit epuise (402) ne changeront pas d'avis en deux secondes, et
    insister ne fait que retarder le message utile.

    « Retry-After » prime sur le calcul : quand le service dit lui-meme
    combien de temps attendre, deviner a sa place revient soit a patienter
    dix minutes pour cinq secondes, soit a revenir trop tot et reprendre un
    429 — ce qui, lui, consomme du quota.
    """
    dernier: Optional[BaseException] = None
    for essai in range(max(1, tentatives)):
        try:
            return action()
        except HttpErreur as exc:
            if not exc.temporaire:
                raise
            dernier = exc
            pause = exc.patienter() or min(plafond, attente * (2 ** essai))
        except Exception as exc:          # noqa: BLE001 — voir la docstring
            dernier = exc
            pause = min(plafond, attente * (2 ** essai))
        if essai == tentatives - 1:
            break
        # Le hasard evite que dix appels partis ensemble reviennent ensemble :
        # le service les refuserait tous une seconde fois.
        pause = min(plafond, pause + random.random())
        if journal is not None:
            journal("  reseau : {} — nouvel essai dans {:.0f} s ({}/{})".format(
                dernier, pause, essai + 1, tentatives - 1))
        if not patienter(pause, arret):
            break
    assert dernier is not None
    raise dernier
