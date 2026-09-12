"""Petit client HTTP base sur urllib (aucune dependance, Termux-friendly)."""

from __future__ import annotations

import gzip
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

USER_AGENT = "Usine-IA/1.0 (+termux; python-stdlib)"


class HttpErreur(Exception):
    def __init__(self, statut: int, message: str, corps: str = ""):
        super().__init__("HTTP {} : {}".format(statut, message))
        self.statut = statut
        self.corps = corps

    @property
    def temporaire(self) -> bool:
        return self.statut in (408, 409, 425, 429, 500, 502, 503, 504, 529, 0)


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
    tetes = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    tetes.update(entetes or {})
    req = urllib.request.Request(url, data=donnees, headers=tetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_contexte_ssl()) as rep:
            brut = rep.read()
            if rep.headers.get("Content-Encoding", "") == "gzip":
                brut = gzip.decompress(brut)
            return rep.status, brut
    except urllib.error.HTTPError as exc:
        corps = b""
        try:
            corps = exc.read()
            if exc.headers.get("Content-Encoding", "") == "gzip":
                corps = gzip.decompress(corps)
        except Exception:
            pass
        raise HttpErreur(exc.code, exc.reason or "erreur", corps.decode("utf-8", "replace"))
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
