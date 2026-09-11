"""Tableau de bord local : piloter l'usine depuis le navigateur du telephone.

Base sur http.server (bibliotheque standard). Ecoute sur 127.0.0.1 par defaut :
rien n'est expose au reseau sans demande explicite. Si le tableau de bord est
ouvert au reseau local, un jeton d'acces devient obligatoire.

Le direct passe par des Server-Sent Events : une seule connexion HTTP longue,
pas de sondage, pas de bibliotheque cliente.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from ..agents import equipe
from ..core import cles as pool_cles
from ..core import config, empreinte, evenements, file as file_prod, llm
from ..core import reglages, securite, store, ventes
from ..pipelines import catalogue, social
from ..pipelines.base import TAILLES, TONS, Contexte

STATIQUE = Path(__file__).resolve().parent / "statique"

TRAVAUX: Dict[str, Dict[str, Any]] = {}
# La veille est lente par construction : Reddit repond 429 des le deuxieme
# appel rapproche, donc « scouter » s'impose une pause de trois secondes
# entre deux communautes. Une requete HTTP synchrone laisserait la page
# tourner une demi-minute sans rien dire.
VEILLES: Dict[str, Dict[str, Any]] = {}
_VERROU = threading.Lock()


def _lien_sur(url: str) -> str:
    """Ne laisse passer qu'un lien Reddit en https.

    Les titres et les liens viennent d'un flux exterieur, que n'importe qui
    peut alimenter. Un « javascript: » rendu dans une ancre du tableau de
    bord serait une execution de script dans la page qui pilote l'usine.
    """
    try:
        morceaux = urlparse(url)
    except ValueError:
        return ""
    if morceaux.scheme != "https":
        return ""
    hote = (morceaux.hostname or "").lower()
    if hote != "reddit.com" and not hote.endswith(".reddit.com"):
        return ""
    return url


def _veille_json(rapport: Any) -> Dict[str, Any]:
    """Le rapport de veille, en JSON, sans les liens douteux."""
    def discussion(d: Any) -> Dict[str, Any]:
        return {"titre": d.titre, "lien": _lien_sur(d.lien),
                "communaute": d.communaute, "date": d.date,
                "douleur": d.douleur}

    return {
        "niche": rapport.niche,
        "indisponible": rapport.indisponible,
        "communautes": [{"nom": c["nom"], "titre": c.get("titre", ""),
                         "lien": _lien_sur(c.get("lien", ""))}
                        for c in rapport.communautes],
        "mots": [[mot, nombre] for mot, nombre in rapport.mots],
        "douleurs": [discussion(d) for d in rapport.douleurs],
        "discussions": [discussion(d) for d in rapport.discussions],
    }


def _scouter(veille_id: str, sujet: str, periode: str, combien: int) -> None:
    from ..core import veille as module_veille

    try:
        rapport = module_veille.scouter(sujet, periode=periode, combien=combien)
        with _VERROU:
            VEILLES[veille_id].update(statut="termine",
                                      resultat=_veille_json(rapport))
    except Exception as exc:
        with _VERROU:
            VEILLES[veille_id].update(statut="echec",
                                      erreur=securite.expurger(str(exc)))


def _catalogue() -> List[Dict[str, Any]]:
    """Types offerts par l'interface. Lu du catalogue, jamais recopie."""
    return [
        {"cle": t.cle, "nom": t.nom, "resume": t.resume, "detail": t.detail,
         "duree": t.duree, "quantite": t.nom_quantite,
         "defaut": t.defaut_quantite()}
        for t in catalogue.tous(fabricables=True)
    ]


def _entier(valeur: Any) -> int:
    """Un champ de formulaire vide vaut zero, pas une erreur."""
    try:
        return max(0, int(valeur or 0))
    except (TypeError, ValueError):
        return 0


def _lancer(travail_id: str, type_produit: str, options: Dict[str, Any]) -> None:
    def journal(message: str) -> None:
        with _VERROU:
            TRAVAUX[travail_id]["journal"].append(
                {"ts": time.time(), "texte": securite.expurger(message)})
        evenements.publier("journal", message=message, travail=travail_id)

    profil = reglages.charger()
    ctx = Contexte(
        sujet=options.get("sujet", ""),
        audience=options.get("audience") or profil["audience"],
        ton=options.get("ton") or profil["ton"],
        taille=options.get("taille") or profil["taille"],
        qualite=options.get("qualite") or profil["qualite"],
        chapitres=_entier(options.get("chapitres")),
        mots_section=_entier(options.get("mots")),
        auteur=options.get("auteur") or profil["auteur"],
        sans_image=bool(options.get("sans_image")) or not profil["images"],
        journal=journal,
    )
    try:
        journal("Demarrage...")
        resultat = catalogue.executer(type_produit, ctx, options)
        with _VERROU:
            TRAVAUX[travail_id].update(statut="termine", resultat=resultat)
        journal("Termine.")
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Echec : {}".format(message))
        evenements.publier("produit", etat="echec", detail=message)


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "UsineIA/" + __version__
    protocol_version = "HTTP/1.1"

    # -- utilitaires -----------------------------------------------------
    def _repondre(self, code: int, corps: bytes, type_mime: str,
                  entetes: Optional[Dict[str, str]] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        try:
            self.wfile.write(corps)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, donnees: Any, code: int = 200) -> None:
        self._repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def _corps_json(self) -> Optional[Dict[str, Any]]:
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur > 64_000:
            self._json({"erreur": "requete trop volumineuse"}, 413)
            return None
        brut = self.rfile.read(longueur).decode("utf-8", "replace")
        try:
            if brut.startswith("{"):
                return json.loads(brut)
            return {cle: valeur[0] for cle, valeur in parse_qs(brut).items()}
        except ValueError:
            self._json({"erreur": "corps illisible"}, 400)
            return None

    def _autorise(self) -> bool:
        """Verifie le jeton quand le tableau de bord n'est pas purement local."""
        attendu = reglages.lire("jeton_web", "")
        if not attendu:
            return True
        requete = urlparse(self.path)
        fourni = (parse_qs(requete.query).get("jeton") or [""])[0]
        if not fourni:
            entete = self.headers.get("Authorization", "")
            if entete.startswith("Bearer "):
                fourni = entete[7:]
        if securite.jeton_valide(attendu, fourni):
            return True
        self._json({"erreur": "jeton d'acces invalide"}, 401)
        return False

    def log_message(self, format: str, *args: Any) -> None:
        pass  # journal HTTP silencieux : la console reste lisible

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:
        chemin = urlparse(self.path).path
        if not self._autorise():
            return
        if chemin in ("/", "/index.html"):
            self._servir_statique("tableau.html", "text/html; charset=utf-8")
        elif chemin.startswith("/statique/"):
            self._servir_statique(chemin[len("/statique/"):])
        elif chemin == "/api/etat":
            self._json(_etat())
        elif chemin == "/api/produits":
            self._json({"produits": _produits()})
        elif chemin == "/api/commerce":
            self._json(_commerce())
        elif chemin == "/api/usine":
            from ..production import statut

            self._json(statut())
        elif chemin == "/api/flux":
            self._flux()
        elif chemin == "/api/evenements":
            depuis = int((parse_qs(urlparse(self.path).query).get("depuis")
                          or ["0"])[0] or 0)
            self._json({"evenements": evenements.historique(depuis)})
        elif chemin.startswith("/api/travaux/"):
            travail_id = chemin.rsplit("/", 1)[-1]
            with _VERROU:
                travail = TRAVAUX.get(travail_id)
            self._json(travail if travail else {"erreur": "travail inconnu"},
                       200 if travail else 404)
        elif chemin.startswith("/api/veille/"):
            veille_id = chemin.rsplit("/", 1)[-1]
            with _VERROU:
                consultation = VEILLES.get(veille_id)
            self._json(consultation if consultation
                       else {"erreur": "veille inconnue"},
                       200 if consultation else 404)
        elif chemin == "/api/sauvegardes":
            self._json(_sauvegardes())
        elif chemin.startswith("/archive/"):
            self._servir_archive(unquote(chemin[len("/archive/"):]))
        elif chemin.startswith("/fichier/"):
            self._servir_produit(unquote(chemin[len("/fichier/"):]))
        else:
            self._json({"erreur": "route inconnue"}, 404)

    def do_POST(self) -> None:
        chemin = urlparse(self.path).path
        if not self._autorise():
            return
        if chemin == "/api/fabriquer":
            self._fabriquer()
        elif chemin == "/api/file":
            options = self._corps_json()
            if options is None:
                return
            self._json(self._gerer_file(options))
        elif chemin == "/api/usine":
            options = self._corps_json()
            if options is None:
                return
            self._json(self._gerer_usine(options))
        elif chemin == "/api/verifier-sujet":
            options = self._corps_json()
            if options is None:
                return
            alertes = securite.analyser_sujet(str(options.get("sujet") or ""))
            self._json({"alertes": [{"domaine": d, "detail": t} for d, t in alertes]})
        elif chemin == "/api/reglages":
            options = self._corps_json()
            if options is None:
                return
            self._json({"reglages": reglages.ecrire(
                {k: v for k, v in options.items() if k in reglages.DEFAUTS})})
        elif chemin == "/api/veille":
            options = self._corps_json()
            if options is None:
                return
            self._json(*self._lancer_veille(options))
        elif chemin == "/api/doublons":
            options = self._corps_json()
            if options is None:
                return
            self._json(self._gerer_doublons(options))
        elif chemin == "/api/sauvegarde":
            options = self._corps_json()
            if options is None:
                return
            self._json(self._gerer_sauvegarde(options))
        else:
            self._json({"erreur": "route inconnue"}, 404)

    # -- implementations -------------------------------------------------
    def _fabriquer(self) -> None:
        options = self._corps_json()
        if options is None:
            return
        type_produit = str(options.get("type") or "ebook")
        if catalogue.obtenir(type_produit) is None:
            self._json({"erreur": "type de produit inconnu"}, 400)
            return
        if not str(options.get("sujet") or "").strip():
            self._json({"erreur": "sujet manquant"}, 400)
            return
        with _VERROU:
            en_cours = [t for t in TRAVAUX.values() if t["statut"] == "en_cours"]
        if len(en_cours) >= 2:
            self._json({"erreur": "deux fabrications sont deja en cours ; "
                                  "attendez qu'elles se terminent"}, 429)
            return
        try:
            options["nombre"] = int(options.get("nombre") or 0)
        except (TypeError, ValueError):
            options["nombre"] = 0
        if not options["nombre"]:
            options.pop("nombre", None)

        travail_id = uuid.uuid4().hex[:12]
        with _VERROU:
            TRAVAUX[travail_id] = {
                "id": travail_id, "type": type_produit,
                "sujet": str(options["sujet"])[:300], "statut": "en_cours",
                "debut": time.time(), "journal": [], "resultat": None, "erreur": "",
            }
        threading.Thread(target=_lancer, args=(travail_id, type_produit, options),
                         daemon=True).start()
        self._json({"travail": travail_id})

    def _gerer_file(self, options: Dict[str, Any]) -> Dict[str, Any]:
        action = str(options.get("action") or "ajouter")
        if action == "ajouter":
            sujet = str(options.get("sujet") or "").strip()
            type_produit = str(options.get("type") or "ebook")
            if not sujet:
                return {"erreur": "sujet manquant"}
            if catalogue.obtenir(type_produit) is None:
                return {"erreur": "type inconnu"}
            try:
                nombre = int(options.get("nombre") or 0)
            except (TypeError, ValueError):
                nombre = 0
            identifiant = file_prod.ajouter(
                sujet, type_produit,
                options={k: v for k, v in (("nombre", nombre),
                                           ("audience", options.get("audience")),
                                           ("ton", options.get("ton")),
                                           ("qualite", options.get("qualite")))
                         if v},
                priorite=5, source="web")
            return {"ajoute": identifiant, "doublon": identifiant is None,
                    "file": file_prod.compter()}
        if action == "retirer":
            try:
                identifiant = int(options.get("id") or 0)
            except (TypeError, ValueError):
                return {"erreur": "identifiant invalide"}
            return {"retire": file_prod.retirer(identifiant),
                    "file": file_prod.compter()}
        if action == "rejouer":
            return {"remis": file_prod.rejouer(), "file": file_prod.compter()}
        if action == "vider":
            return {"supprimes": file_prod.vider(), "file": file_prod.compter()}
        return {"erreur": "action inconnue"}

    def _gerer_usine(self, options: Dict[str, Any]) -> Dict[str, Any]:
        from ..production import UsineContinue, demander_arret, verrou_actif

        action = str(options.get("action") or "")
        if action == "arreter":
            return {"arret_demande": demander_arret()}
        if action != "demarrer":
            return {"erreur": "action inconnue"}
        if verrou_actif() is not None:
            return {"erreur": "une usine tourne deja (pid {})".format(verrou_actif())}
        if not file_prod.compter()["en_attente"] and not options.get("auto"):
            return {"erreur": "la file est vide"}

        try:
            maximum = int(options.get("max") or 0)
        except (TypeError, ValueError):
            maximum = 0

        def tourner() -> None:
            moteur = UsineContinue(
                auto=bool(options.get("auto")), maximum=maximum,
                journal=lambda message: evenements.publier(
                    "journal", message=message),
            )
            moteur.tourner()

        threading.Thread(target=tourner, daemon=True).start()
        return {"demarre": True}

    def _flux(self) -> None:
        """Server-Sent Events : le direct sans sondage ni bibliotheque."""
        depuis = int((parse_qs(urlparse(self.path).query).get("depuis")
                      or ["0"])[0] or 0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        file = evenements.abonner()
        try:
            for evenement in evenements.historique(depuis):
                self._pousser(evenement)
            while True:
                try:
                    evenement = file.get(timeout=20)
                    self._pousser(evenement)
                except queue.Empty:
                    # Battement : garde la connexion ouverte a travers les
                    # coupures d'inactivite du reseau mobile.
                    self.wfile.write(b": battement\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # l'onglet a ete ferme
        finally:
            evenements.desabonner(file)

    def _pousser(self, evenement: Dict[str, Any]) -> None:
        charge = json.dumps(evenement, ensure_ascii=False)
        self.wfile.write("id: {}\ndata: {}\n\n".format(
            evenement.get("id", 0), charge).encode("utf-8"))
        self.wfile.flush()

    def _servir_statique(self, relatif: str,
                         type_mime: Optional[str] = None) -> None:
        # On decode d'abord : sans cela, « %2e%2e » ne serait bloque que parce
        # qu'il ne correspond a aucun dossier reel — une protection fortuite.
        relatif = unquote(relatif)
        if not relatif or ".." in relatif.split("/") or relatif.startswith("/"):
            self._json({"erreur": "chemin refuse"}, 400)
            return
        cible = (STATIQUE / relatif).resolve()
        try:
            cible.relative_to(STATIQUE.resolve())
        except ValueError:
            self._json({"erreur": "chemin refuse"}, 403)
            return
        if not cible.is_file():
            self._json({"erreur": "fichier introuvable"}, 404)
            return
        mime = type_mime or mimetypes.guess_type(cible.name)[0] or "text/plain"
        if cible.suffix == ".js":
            mime = "application/javascript; charset=utf-8"
        elif cible.suffix == ".css":
            mime = "text/css; charset=utf-8"
        self._repondre(200, cible.read_bytes(), mime,
                       {"Cache-Control": "no-cache"})

    # -- veille, doublons, sauvegarde ------------------------------------
    def _lancer_veille(self, options: Dict[str, Any]):
        """Demarre une consultation de niche en tache de fond.

        Renvoie (corps, code) : la veille est lente et peut echouer pour des
        raisons qui ne sont pas des erreurs de l'usine — Reddit limite le
        debit, et une niche francaise peut n'y laisser aucune trace.
        """
        sujet = str(options.get("sujet") or "").strip()
        if not sujet:
            return ({"erreur": "sujet manquant"}, 400)
        periode = str(options.get("periode") or "year")
        if periode not in ("day", "week", "month", "year", "all"):
            return ({"erreur": "periode inconnue"}, 400)
        combien = min(4, max(1, _entier(options.get("communautes")) or 2))

        with _VERROU:
            en_cours = [v for v in VEILLES.values() if v["statut"] == "en_cours"]
            if en_cours:
                # Deux consultations simultanees se prennent mutuellement
                # le 429 : Reddit compte par adresse, pas par onglet.
                return ({"erreur": "une veille est deja en cours"}, 429)
            veille_id = uuid.uuid4().hex[:12]
            VEILLES[veille_id] = {
                "id": veille_id, "sujet": sujet[:300], "periode": periode,
                "statut": "en_cours", "debut": time.time(),
                "resultat": None, "erreur": "",
            }
        threading.Thread(target=_scouter,
                         args=(veille_id, sujet, periode, combien),
                         daemon=True).start()
        return ({"veille": veille_id}, 200)

    def _gerer_doublons(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Reconstruit les empreintes manquantes.

        Les empreintes sont posees a la fabrication. Un catalogue constitue
        avant leur introduction n'en a aucune, et la carte des doublons
        reste vide chez celui qui en aurait le plus besoin.
        """
        if str(options.get("action") or "") != "reconstruire":
            return {"erreur": "action inconnue"}
        return _reconstruire_empreintes()

    def _gerer_sauvegarde(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Ecrit une archive de l'atelier.

        Restaurer ne passe pas par ici, et c'est deliberé : l'operation
        remplace l'atelier entier, et c'est le genre de bouton sur lequel
        on ne clique jamais volontairement. Elle reste a la ligne de
        commande, qui demande confirmation.
        """
        from ..core import sauvegarde

        if str(options.get("action") or "creer") != "creer":
            return {"erreur": "action inconnue"}
        try:
            archive = sauvegarde.creer(
                avec_produits=bool(options.get("avec_produits")))
        except OSError as exc:
            return {"erreur": securite.expurger(str(exc))}
        return {"archive": _fiche_archive(archive),
                "sauvegardes": _sauvegardes()["archives"]}

    def _servir_archive(self, relatif: str) -> None:
        """Sert une archive de sauvegarde, et rien d'autre.

        Le dossier des sauvegardes est a cote de la base et des reglages :
        une sortie de dossier livrerait « usine.db » en clair a qui a
        atteint le tableau de bord.
        """
        if not relatif or "/" in relatif or ".." in relatif:
            self._json({"erreur": "chemin refuse"}, 400)
            return
        racine = _dossier_sauvegardes().resolve()
        cible = (racine / relatif).resolve()
        try:
            cible.relative_to(racine)
        except ValueError:
            self._json({"erreur": "chemin refuse"}, 403)
            return
        if cible.suffix != ".zip" or not cible.is_file():
            self._json({"erreur": "archive introuvable"}, 404)
            return
        self._repondre(200, cible.read_bytes(), "application/zip",
                       {"Content-Disposition":
                        'attachment; filename="{}"'.format(cible.name)})

    def _servir_produit(self, relatif: str) -> None:
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


def _dossier_sauvegardes() -> Path:
    return config.WORKDIR / "sauvegardes"


def _fiche_archive(archive: Path) -> Dict[str, Any]:
    etat = archive.stat()
    return {"nom": archive.name, "ko": max(1, etat.st_size // 1024),
            "ts": etat.st_mtime}


def _sauvegardes() -> Dict[str, Any]:
    """Les archives deja ecrites, la plus recente d'abord."""
    dossier = _dossier_sauvegardes()
    archives = sorted(dossier.glob("*.zip"), key=lambda f: -f.stat().st_mtime) \
        if dossier.is_dir() else []
    return {"archives": [_fiche_archive(a) for a in archives[:12]],
            "dossier": str(dossier)}


def _sans_empreinte() -> List[Dict[str, Any]]:
    """Produits fabriques avant l'arrivee des empreintes.

    Ce sont eux qui rendent la carte des doublons trompeuse : elle affiche
    « aucun recouvrement » alors qu'elle n'a simplement rien compare.
    """
    connues = {e["produit_id"] for e in store.lister_empreintes(limite=5000)}
    return [p for p in store.lister_produits(1000)
            if p["id"] not in connues and p["statut"] != "bonus_integre"]


def _reconstruire_empreintes() -> Dict[str, Any]:
    """Calcule les empreintes manquantes a partir des fichiers sur le disque."""
    from ..pipelines.base import empreinte_depuis_dossier

    faits, sans_matiere = 0, []
    for produit in _sans_empreinte():
        if empreinte_depuis_dossier(produit["id"], produit["type"],
                                    produit["titre"] or "",
                                    produit["sujet"] or "",
                                    Path(produit["dossier"] or "")):
            faits += 1
        else:
            sans_matiere.append(produit["titre"] or produit["id"])
    return {"reconstruites": faits,
            "sans_matiere": sans_matiere[:8],
            "reste": len(sans_matiere)}


def _commerce() -> Dict[str, Any]:
    """Ce que le tableau de bord ne montrait pas : l'argent et les repetitions.

    Deux mesures que rien n'affichait alors qu'elles decident de ce qu'on
    fabrique ensuite — le chiffre d'affaires reel, et les produits qui se
    recouvrent assez pour qu'une place de marche les retire.
    """
    charges = [{
        "produit_id": ligne["produit_id"], "titre": ligne["titre"],
        "type": ligne["type"],
        "signature": empreinte.decoder(ligne["signature"]),
        "plan": empreinte.decoder(ligne["plan"]),
    } for ligne in store.lister_empreintes()]

    paires = []
    for index, courant in enumerate(charges):
        for autre in charges[index + 1:]:
            if courant["type"] != autre["type"]:
                continue
            voisin = empreinte.Voisin(
                produit_id=autre["produit_id"], titre=autre["titre"] or "",
                sujet="",
                texte=empreinte.ressemblance(courant["signature"],
                                             autre["signature"]),
                plan=empreinte.ressemblance_plan(courant["plan"],
                                                 autre["plan"]))
            if voisin.doublon:
                paires.append({
                    "un": courant["titre"] or courant["produit_id"],
                    "autre": voisin.titre or voisin.produit_id,
                    "type": courant["type"], "motif": voisin.motif,
                    "texte": round(voisin.texte, 2),
                    "plan": round(voisin.plan, 2),
                })
    paires.sort(key=lambda p: p["texte"] + p["plan"], reverse=True)

    return {
        "devises": ventes.total_par_devise(),
        "produits": ventes.par_produit(12),
        "types": ventes.par_champ("type"),
        "prix": ventes.prix_observes(),
        "doublons": paires[:12],
        "produits_compares": len(charges),
        # Sans ce compte, « aucun recouvrement notable » se lit comme une
        # bonne nouvelle alors qu'il peut vouloir dire « rien n'a ete
        # compare ». La difference decide de ce qu'on fabrique ensuite.
        "sans_empreinte": len(_sans_empreinte()),
    }


def _etat() -> Dict[str, Any]:
    fournisseurs = [
        {
            "nom": ligne["nom"], "disponible": ligne["disponible"],
            "local": ligne["local"], "sans_cle": ligne["sans_cle"],
            "aujourdhui": ligne["aujourdhui"], "rpd": ligne["rpd"],
            "nb_cles": ligne.get("nb_cles", 0),
        }
        for ligne in llm.diagnostic()
    ]
    with _VERROU:
        travaux = [{k: v for k, v in t.items() if k != "journal"}
                   for t in sorted(TRAVAUX.values(), key=lambda t: -t["debut"])[:10]]
    profil = reglages.charger()
    return {
        "version": __version__,
        "fournisseurs": fournisseurs,
        "avec_cle": sum(1 for f in fournisseurs
                        if f["disponible"] and not f["local"] and not f["sans_cle"]),
        "cles": pool_cles.resume(),
        "travaux": travaux,
        "types": _catalogue(),
        "agents": [{"nom": a.nom, "emoji": a.emoji} for a in equipe.EQUIPE.values()],
        "tons": sorted(TONS),
        "tailles": sorted(TAILLES, key=lambda t: TAILLES[t][0]),
        "qualites": ["rapide", "standard", "exigeant"],
        "reseaux": sorted(social.RESEAUX),
        "reglages": {k: profil[k] for k in
                     ("auteur", "audience", "ton", "taille", "qualite", "images")},
        "file": file_prod.compter(),
        # Volontairement absent : _commerce() compare toutes les paires de
        # produits, ce qui coute pres d'une seconde a quatre cents produits.
        # Le tableau de bord interroge /api/commerce de son cote, toutes les
        # trente secondes ; l'embarquer ici le faisait recalculer toutes les
        # quinze, pour un resultat que personne ne lisait.
    }


def _produits() -> List[Dict[str, Any]]:
    sortie = []
    for produit in store.lister_produits(40):
        if produit["statut"] == "bonus_integre":
            continue
        meta = produit.get("meta") or {}
        dossier = Path(produit["dossier"] or "")
        fichiers = []
        if dossier.exists():
            for fichier in sorted(dossier.rglob("*")):
                if fichier.is_file() and fichier.suffix in (
                        ".pdf", ".epub", ".html", ".md", ".csv", ".zip", ".txt"):
                    fichiers.append({
                        "nom": str(fichier.relative_to(dossier)),
                        "url": "/fichier/{}/{}".format(
                            dossier.name, fichier.relative_to(dossier)),
                        "octets": fichier.stat().st_size,
                    })
        note = None
        rapport = dossier / "rapport-qualite.json"
        if rapport.exists():
            try:
                note = json.loads(rapport.read_text(encoding="utf-8")).get(
                    "note_moyenne_finale")
            except (ValueError, OSError):
                note = None
        sortie.append({
            "id": produit["id"], "titre": produit["titre"], "type": produit["type"],
            "statut": produit["statut"], "cree_le": produit["cree_le"],
            "mots": meta.get("mots"), "note": note, "fichiers": fichiers[:16],
        })
    return sortie


def demarrer(port: int = 8777, hote: str = "127.0.0.1") -> int:
    config.load_env()
    config.ensure_dirs()

    local = hote in ("127.0.0.1", "localhost", "::1")
    jeton = reglages.lire("jeton_web", "")
    if not local and not jeton:
        # Ouvrir au reseau local sans authentification exposerait les produits
        # et la commande de fabrication a tout l'appareil du voisinage.
        jeton = securite.nouveau_jeton()
        reglages.ecrire({"jeton_web": jeton})
        print("\n  Acces reseau detecte : un jeton a ete genere automatiquement.")

    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    serveur.daemon_threads = True
    adresse = "http://{}:{}".format("localhost" if local else hote, port)
    if jeton:
        adresse += "/?jeton=" + jeton

    print("\n  Usine-IA — tableau de bord")
    print("  Ouvrez : {}".format(adresse))
    if not local:
        print("  Attention : accessible depuis tout le reseau local.")
    print("  Sur Termux : termux-open-url '{}'".format(adresse))
    print("  Arreter : Ctrl+C\n")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\n  Tableau de bord arrete.")
    finally:
        serveur.server_close()
    return 0
