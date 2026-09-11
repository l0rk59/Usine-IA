"""Tableau de bord local : piloter l'usine depuis le navigateur du telephone.

Base sur http.server (bibliotheque standard). Ecoute sur 127.0.0.1 par defaut :
rien n'est expose au reseau sans demande explicite.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from ..core import config, llm, store
from ..pipelines import boite_outils, ebook, formation, idees, pack_prompts, social
from ..pipelines.base import TAILLES, TONS, Contexte
from .modele import PAGE

TRAVAUX: Dict[str, Dict[str, Any]] = {}
_VERROU = threading.Lock()

FABRIQUES = {
    "ebook": lambda ctx, opt: ebook.produire(ctx),
    "prompts": lambda ctx, opt: pack_prompts.produire(ctx, nombre=opt.get("nombre", 50)),
    "formation": lambda ctx, opt: formation.produire(ctx, modules=opt.get("nombre", 0)),
    "outils": lambda ctx, opt: boite_outils.produire(ctx, nombre=opt.get("nombre", 10)),
    "social": lambda ctx, opt: social.produire(
        ctx, nombre=opt.get("nombre", 30), reseau=opt.get("reseau", "linkedin")
    ),
    "idees": lambda ctx, opt: idees.produire(ctx, nombre=opt.get("nombre", 12)),
}


def _lancer(travail_id: str, type_produit: str, options: Dict[str, Any]) -> None:
    def journal(message: str) -> None:
        with _VERROU:
            TRAVAUX[travail_id]["journal"].append(
                {"ts": time.time(), "texte": message}
            )

    ctx = Contexte(
        sujet=options.get("sujet", ""),
        audience=options.get("audience") or "un public francophone motive",
        ton=options.get("ton") or "pro",
        taille=options.get("taille") or "standard",
        auteur=options.get("auteur") or "Usine-IA",
        sans_image=bool(options.get("sans_image")),
        journal=journal,
    )
    try:
        journal("Demarrage...")
        resultat = FABRIQUES[type_produit](ctx, options)
        with _VERROU:
            TRAVAUX[travail_id].update(statut="termine", resultat=resultat)
        journal("Termine.")
    except Exception as exc:
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=str(exc))
        journal("Echec : {}".format(exc))


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "UsineIA/" + __version__

    # -- utilitaires -----------------------------------------------------
    def _repondre(self, code: int, corps: bytes, type_mime: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(corps)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, donnees: Any, code: int = 200) -> None:
        self._repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:
        pass  # journal HTTP silencieux : la console reste lisible

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:
        chemin = urlparse(self.path).path
        if chemin == "/":
            self._repondre(200, _page().encode("utf-8"), "text/html; charset=utf-8")
        elif chemin == "/api/etat":
            self._json(_etat())
        elif chemin == "/api/produits":
            self._json({"produits": _produits()})
        elif chemin.startswith("/api/travaux/"):
            travail_id = chemin.rsplit("/", 1)[-1]
            with _VERROU:
                travail = TRAVAUX.get(travail_id)
            if travail is None:
                self._json({"erreur": "travail inconnu"}, 404)
            else:
                self._json(travail)
        elif chemin.startswith("/fichier/"):
            self._servir_fichier(unquote(chemin[len("/fichier/"):]))
        else:
            self._json({"erreur": "route inconnue"}, 404)

    def do_POST(self) -> None:
        chemin = urlparse(self.path).path
        if chemin != "/api/fabriquer":
            self._json({"erreur": "route inconnue"}, 404)
            return
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur > 64_000:
            self._json({"erreur": "requete trop volumineuse"}, 413)
            return
        brut = self.rfile.read(longueur).decode("utf-8", "replace")
        try:
            options = json.loads(brut) if brut.startswith("{") else {
                cle: valeur[0] for cle, valeur in parse_qs(brut).items()
            }
        except ValueError:
            self._json({"erreur": "corps illisible"}, 400)
            return

        type_produit = str(options.get("type") or "ebook")
        if type_produit not in FABRIQUES:
            self._json({"erreur": "type de produit inconnu"}, 400)
            return
        if not str(options.get("sujet") or "").strip():
            self._json({"erreur": "sujet manquant"}, 400)
            return
        try:
            options["nombre"] = int(options.get("nombre") or 0)
        except (TypeError, ValueError):
            options["nombre"] = 0
        if not options["nombre"]:
            options.pop("nombre")

        travail_id = uuid.uuid4().hex[:12]
        with _VERROU:
            TRAVAUX[travail_id] = {
                "id": travail_id,
                "type": type_produit,
                "sujet": options["sujet"],
                "statut": "en_cours",
                "debut": time.time(),
                "journal": [],
                "resultat": None,
                "erreur": "",
            }
        fil = threading.Thread(target=_lancer, args=(travail_id, type_produit, options),
                               daemon=True)
        fil.start()
        self._json({"travail": travail_id})

    def _servir_fichier(self, relatif: str) -> None:
        """Sert un fichier produit, en refusant toute sortie du dossier atelier."""
        if not relatif or ".." in relatif.split("/"):
            self._json({"erreur": "chemin refuse"}, 400)
            return
        racine = config.PRODUITS_DIR.resolve()
        cible = (racine / relatif).resolve()
        try:
            cible.relative_to(racine)
        except ValueError:
            self._json({"erreur": "chemin refuse"}, 403)
            return
        if not cible.is_file():
            self._json({"erreur": "fichier introuvable"}, 404)
            return
        type_mime = mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
        if cible.suffix in (".md", ".txt", ".csv"):
            type_mime = "text/plain; charset=utf-8"
        self._repondre(200, cible.read_bytes(), type_mime)


def _etat() -> Dict[str, Any]:
    fournisseurs = [
        {
            "nom": ligne["nom"],
            "disponible": ligne["disponible"],
            "local": ligne["local"],
            "aujourdhui": ligne["aujourdhui"],
            "rpd": ligne["rpd"],
        }
        for ligne in llm.diagnostic()
    ]
    with _VERROU:
        travaux = [
            {k: v for k, v in travail.items() if k != "journal"}
            for travail in sorted(TRAVAUX.values(), key=lambda t: -t["debut"])[:10]
        ]
    return {
        "version": __version__,
        "fournisseurs": fournisseurs,
        "actifs": sum(1 for f in fournisseurs if f["disponible"] and not f["local"]),
        "travaux": travaux,
        "tons": sorted(TONS),
        "tailles": sorted(TAILLES),
        "reseaux": sorted(social.RESEAUX),
    }


def _produits() -> List[Dict[str, Any]]:
    sortie = []
    for produit in store.lister_produits(40):
        meta = json.loads(produit.get("meta") or "{}")
        dossier = Path(produit["dossier"] or "")
        fichiers = []
        if dossier.exists():
            for fichier in sorted(dossier.rglob("*")):
                if fichier.is_file() and fichier.suffix in (
                    ".pdf", ".epub", ".html", ".md", ".csv", ".zip", ".txt"
                ):
                    fichiers.append(
                        {
                            "nom": str(fichier.relative_to(dossier)),
                            "url": "/fichier/{}/{}".format(
                                dossier.name, fichier.relative_to(dossier)
                            ),
                            "octets": fichier.stat().st_size,
                        }
                    )
        sortie.append(
            {
                "id": produit["id"],
                "titre": produit["titre"],
                "type": produit["type"],
                "statut": produit["statut"],
                "cree_le": produit["cree_le"],
                "mots": meta.get("mots"),
                "fichiers": fichiers[:14],
            }
        )
    return sortie


def _page() -> str:
    return PAGE.replace("{{VERSION}}", __version__)


def demarrer(port: int = 8777, hote: str = "127.0.0.1") -> int:
    config.load_env()
    config.ensure_dirs()
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    adresse = "http://{}:{}".format("localhost" if hote == "127.0.0.1" else hote, port)
    print("\n  Usine-IA — tableau de bord")
    print("  Ouvrez : {}".format(adresse))
    if hote not in ("127.0.0.1", "localhost"):
        print("  Attention : le tableau de bord est accessible depuis le reseau local.")
    print("  Sur Termux : termux-open-url {}".format(adresse))
    print("  Arreter : Ctrl+C\n")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\n  Tableau de bord arrete.")
    finally:
        serveur.server_close()
    return 0
