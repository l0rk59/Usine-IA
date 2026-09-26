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
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from .. import __version__
from ..agents import equipe
from ..core import cles as pool_cles
from ..core import config, empreinte, evenements, experience
from ..core import file as file_prod, llm
from ..core import reglages, securite, store, ventes
from ..pipelines import catalogue, social
from ..production import AUTO
from ..pipelines.base import TAILLES, TONS, Contexte, code_langue

STATIQUE = Path(__file__).resolve().parent / "statique"

TRAVAUX: Dict[str, Dict[str, Any]] = {}
# Les travaux termines qu'on garde. La page n'en montre que dix ; les autres
# restaient en memoire, journal complet compris, tant que le serveur tournait
# — des jours sur un telephone. Le produit, lui, est en base.
TRAVAUX_TERMINES_GARDES = 30


def _ranger_travaux() -> None:
    """Oublie les plus anciens travaux termines. A appeler sous « _VERROU »."""
    finis = sorted((t for t in TRAVAUX.values() if t.get("statut") != "en_cours"),
                   key=lambda t: t.get("debut") or 0)
    for travail in finis[:max(0, len(finis) - TRAVAUX_TERMINES_GARDES)]:
        TRAVAUX.pop(travail.get("id"), None)
# La veille est lente par construction : Reddit repond 429 des le deuxieme
# appel rapproche, donc « scouter » s'impose une pause de trois secondes
# entre deux communautes. Une requete HTTP synchrone laisserait la page
# tourner une demi-minute sans rien dire.
VEILLES: Dict[str, Dict[str, Any]] = {}

# Plafond du televersement d'archive. Il borne ce qu'on ECRIT sur le
# disque du telephone ; ce qu'il faudra ensuite decompresser est
# borne separement, dans « sauvegarde ».
TELEVERSEMENT_MAX = 200 * 1024 * 1024

# Le sondage de marche interroge quatre services publics l'un apres l'autre.
# Comme la veille, il est trop long pour une requete qui attend.
MARCHES: Dict[str, Dict[str, Any]] = {}
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
         "defaut": t.defaut_quantite(),
         # Fiction ou pratique. Le navigateur en fait deux groupes dans la
         # liste : melangees, « Roman » se cherchait entre « Pack de
         # prompts » et « Sequence e-mail », et les reglages qui suivaient
         # n'avaient aucun rapport les uns avec les autres.
         "famille": t.famille,
         # Les reglages que CE type comprend. Ecrits a la main dans le gabarit
         # et dans le script, huit sur dix-sept avaient fini par n'exister que
         # dans l'analyseur d'arguments : on ne pouvait pas choisir, depuis le
         # navigateur, si un outil logiciel etait une ligne de commande ou une
         # application web. Le formulaire se construit maintenant a partir de
         # cette liste, donc un champ ajoute au catalogue y apparait seul.
         "champs": [
             {"nom": c.nom, "libelle": c.libelle, "genre": c.genre,
              "defaut": c.defaut, "choix": list(c.choix), "aide": c.aide,
              "unite": c.unite, "etiquettes": dict(c.etiquettes),
              "decide_par_l_usine": c.decide_par_l_usine}
             for c in t.champs
         ]}
        for t in catalogue.tous(fabricables=True)
    ]


def _types_offerts() -> List[Dict[str, Any]]:
    """Le catalogue, precede du choix « l'usine decide ».

    Ce choix manquait, et son absence se voyait a l'envers : la chaine
    « idees » trouve des pistes en leur donnant DEJA un type, et ce type
    n'etait suivi nulle part parce que le formulaire obligeait a en imposer
    un. Choisir le type d'abord suppose de savoir ce qui se vend sur une
    niche qu'on n'a pas encore cherchee — c'est l'ordre inverse de celui dans
    lequel la question se pose.

    Il est en tete parce que c'est le choix le plus souvent juste quand on ne
    sait pas encore. Il ne porte aucun champ : les reglages d'un type ne
    peuvent pas etre demandes avant que le type soit connu.
    """
    return [{"cle": AUTO, "nom": "L'usine decide",
             "resume": "l'usine choisit le type qui se vend le mieux",
             "detail": "Elle lit le sujet, ou cherche une niche, puis choisit "
                       "parmi les {} types qu'elle sait fabriquer".format(
                           len(catalogue.tous(fabricables=True))),
             "duree": "variable", "quantite": "", "defaut": 0,
             "famille": "", "champs": []}] + _catalogue()


def _entier(valeur: Any) -> int:
    """Un champ de formulaire vide vaut zero, pas une erreur."""
    try:
        return max(0, int(valeur or 0))
    except (TypeError, ValueError):
        return 0


def _journal_de(travail_id: str) -> Callable[[str], None]:
    """La voix d'un travail : ce qu'il ecrit va au navigateur et au flux.

    Cette fermeture etait recopiee CINQ fois dans ce fichier, a l'octet pres
    — une par lanceur de travail. Trois choses y sont enchainees et doivent
    le rester : le verrou, l'expurgation, et la publication. Le jour ou l'une
    manque a une copie, une cle d'API part dans le journal d'un seul type de
    travail, et rien ne le dit.
    """
    def journal(message: str) -> None:
        with _VERROU:
            TRAVAUX[travail_id]["journal"].append(
                {"ts": time.time(), "texte": securite.expurger(message)})
        evenements.publier("journal", message=message, travail=travail_id)

    return journal


def _lancer_la_boucle(auto: bool = False, maximum: int = 0) -> threading.Thread:
    """L'usine continue, dans un fil a part, qui parle au flux du navigateur."""
    from ..production import UsineContinue

    def tourner() -> None:
        UsineContinue(
            auto=auto, maximum=maximum,
            journal=lambda message: evenements.publier("journal", message=message),
        ).tourner()

    return _en_tache_de_fond(tourner)


# Le nom que portent les fils de travail du tableau de bord. Ils survivent a
# la requete qui les lance — c'est leur raison d'etre — et donc aussi a
# l'arret du serveur. Mesure du 24/09/2026 en integration continue : une
# fabrication lancee par un module de tests tournait encore dans le module
# suivant, avec le simulateur de ce module et pendant sa bascule de base —
# « no such table » un jour, un produit compte a 3 appels pour 11 le
# lendemain. Nommes, ils peuvent etre attendus (« tests/atelier.py »), et se
# reconnaissent dans un vidage de fils.
FIL_DE_TRAVAIL = "usine-travail"


def _en_tache_de_fond(cible: Callable[..., Any], *arguments: Any) -> threading.Thread:
    """Lance un travail du tableau de bord dans son propre fil, nomme."""
    fil = threading.Thread(target=cible, args=arguments, daemon=True,
                           name=FIL_DE_TRAVAIL)
    fil.start()
    return fil


def _finir_plus_tard(type_produit: str, produit_id: str, epuise: bool,
                     sujet: str, journal: Callable[[str], None]) -> None:
    """Un produit coupe par les quotas est confie a la boucle, qui attendra.

    Seulement quand les fournisseurs se sont tus : un produit inacheve pour
    une autre raison (une section illisible) se reprend a la main, parce
    qu'attendre ne le reparerait pas.

    Coupe AVANT l'export, le produit existe aussi — son dossier, son carnet,
    son titre au catalogue. Il restait la, inacheve, sans rien pour le finir :
    seul le produit coupe apres l'export etait confie a la boucle.
    """
    from ..production import confier_a_la_boucle, verrou_actif

    fiche = (store.lire_produit(produit_id) or {}) if produit_id else {}
    if fiche.get("statut") != "en_cours" or not epuise:
        return
    manquants = len((fiche.get("meta") or {}).get("manquants") or [])
    confier_a_la_boucle(type_produit, sujet, fiche["id"], manquants)
    if manquants:
        journal("Les fournisseurs n'ont plus rien à donner : {} section(s) à "
                "écrire. L'usine finira ce produit seule dès qu'ils rouvrent — "
                "rien à faire.".format(manquants))
    else:
        journal("Le produit est commencé et gardé au carnet. L'usine le "
                "finira seule dès que les fournisseurs rouvrent — rien à "
                "faire.")
    if verrou_actif() is None:
        # Pour ce produit seulement : la file peut contenir d'autres niches,
        # que personne n'a demande de fabriquer maintenant.
        _lancer_la_boucle(maximum=1)


def _lancer(travail_id: str, type_produit: str, options: Dict[str, Any]) -> None:
    journal = _journal_de(travail_id)

    sujet = str(options.get("sujet") or "").strip()
    if type_produit == AUTO and sujet:
        # Sujet donne, type a decider : la question la plus utile, et celle
        # que le formulaire obligeait a trancher en premier.
        journal("L'usine choisit le type de produit...")
        ctx_choix = Contexte(sujet=sujet, journal=lambda _m: None,
                             sans_image=True)
        type_produit = catalogue.type_pour_sujet(ctx_choix, sujet)
        fiche = catalogue.obtenir(type_produit)
        journal("Type retenu : {}".format(fiche.nom if fiche else type_produit))
        evenements.publier("type_choisi", type=type_produit,
                           nom=fiche.nom if fiche else type_produit)
    if not sujet:
        # Le cas « je ne sais pas quoi vendre, trouve ». Il passe par le meme
        # chemin que la ligne de commande : une seule facon de choisir une
        # niche, sinon les deux divergent et l'une des deux vieillit.
        from ..production import choisir_une_niche

        journal("L'usine choisit la niche...")
        choix = choisir_une_niche(journal=journal, type_produit=type_produit)
        sujet = choix["sujet"]
        # En mode « auto », le type vient avec la niche — une idee trouvee par
        # la chaine « idees » porte deja le sien. Le jeter, comme le faisaient
        # les deux appelants, fabriquait un ebook a partir d'un sujet intitule
        # « 30 posts LinkedIn pour freelances ».
        if type_produit == AUTO:
            type_produit = choix.get("type") or "ebook"
            fiche = catalogue.obtenir(type_produit)
            journal("Type retenu : {}".format(
                fiche.nom if fiche else type_produit))
            evenements.publier("type_choisi", type=type_produit,
                               nom=fiche.nom if fiche else type_produit)
        if not sujet:
            # Des fournisseurs muets ne sont pas une absence de niche : le
            # tableau de bord disait « donnez-en une », ce qui n'aurait rien
            # change — la fabrication aurait echoue au premier appel.
            erreur = (securite.expurger(choix.get("erreur") or "")
                      if choix.get("muets") else "") or "aucune niche trouvee"
            with _VERROU:
                TRAVAUX[travail_id].update(statut="echec", erreur=erreur)
            journal("Les fournisseurs ne répondent pas : {}".format(erreur)
                    if choix.get("muets")
                    else "Aucune niche trouvee : donnez-en une.")
            return
        if choix.get("source") == "froid" and not choix.get("mesure", True):
            journal("Aucune source de marche n'a repondu : cette niche est "
                    "proposée, pas mesurée.")
        options["sujet"] = sujet
        # Les reglages qui voyagent avec une promesse de lecture. Sans cette
        # ligne, la chaine RE-DEVINE genre, tropes, ambiance et fin a partir
        # du seul titre — neuf reglages decides une seconde fois, et sans le
        # contexte qui les avait fait choisir.
        for cle, valeur in (choix.get("options") or {}).items():
            options.setdefault(cle, valeur)
        with _VERROU:
            TRAVAUX[travail_id]["sujet"] = sujet[:300]
        evenements.publier("niche", sujet=sujet, source=choix.get("source", ""))

    # Le meme chemin que l'usine continue : contexte, brief, fabrication,
    # kit et archive. Les deux portes le recopiaient chacune, et la boucle
    # avait perdu en route trois reglages « a chaque produit ».
    from ..pipelines import porte

    ctx = porte.contexte(sujet, options, journal)
    try:
        journal("Démarrage...")
        resultat = porte.fabriquer(type_produit, ctx, options, journal)
        _finir_plus_tard(type_produit, str(resultat.get("produit_id") or ""),
                         bool(resultat.get("budget_epuise")), sujet, journal)
        with _VERROU:
            TRAVAUX[travail_id].update(statut="termine", resultat=resultat)
        journal("Terminé.")
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Échec : {}".format(message))
        evenements.publier("produit", etat="echec", detail=message)
        if isinstance(exc, llm.PlusDeFournisseur):
            _finir_plus_tard(type_produit, ctx.produit_id, True, sujet, journal)


def _lancer_prospection(travail_id: str, fiction: bool = False) -> None:
    """Remplit la file, hors du fil HTTP.

    « fiction » choisit la QUESTION posee, pas seulement le type de produit.
    Une fiction ne se cherche pas comme une niche : le lecteur n'achete pas
    la solution d'un probleme. Sans ce chemin, la recherche de promesses
    n'existait qu'en ligne de commande — donc pas pour qui pilote l'usine
    depuis son telephone, c'est-a-dire l'usage normal.
    """
    journal = _journal_de(travail_id)

    from ..production import prospecter, prospecter_fiction

    try:
        resultat = (prospecter_fiction(nombre=8, journal=journal) if fiction
                    else prospecter(nombre=8, journal=journal))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="termine", resultat=resultat)
        if resultat["ajoutees"]:
            journal("{} niche(s) mise(s) en file.".format(resultat["ajoutees"]))
        elif resultat.get("en_file"):
            # Le tableau de bord disait « 0 niche(s) mise(s) en file » sans
            # dire pourquoi. Sur un ecran de telephone, c'est indiscernable
            # d'une panne.
            journal("Aucune niche neuve : les {} pistes sont déjà en file. "
                    "Lancez la production, ou explorez une autre graine."
                    .format(resultat["en_file"]))
        else:
            journal("Aucune niche neuve : les pistes recouvrent des produits "
                    "déjà fabriqués.")
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Échec : {}".format(message))


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

    def _hotes_admis(self) -> set:
        """Les noms sous lesquels CE serveur peut legitimement etre joint."""
        hote, port = self.server.server_address[:2]
        noms = {"127.0.0.1", "localhost", "[::1]", "::1"}
        if hote not in ("0.0.0.0", "::", ""):
            noms.add(hote)
        return {"{}:{}".format(n, port) for n in noms} | noms

    def _origine_sure(self, modifie: bool) -> bool:
        """Refuse ce qu'un SITE ETRANGER fait envoyer par le navigateur.

        Le tableau de bord local n'a pas de mot de passe, parce que
        « 127.0.0.1, c'est moi ». Sur un telephone, c'est faux : n'importe
        quelle page ouverte dans le navigateur peut ecrire a 127.0.0.1:8777.
        Mesure du 23/09/2026 : un POST « text/plain » — une requete que le
        navigateur envoie sans verification prealable — venu de
        https://evil.example a reecrit « marque » et « site ». Or « site »
        part dans la notice et le kit de vente de CHAQUE produit livre : une
        page visitee au hasard aurait signe les produits de quelqu'un d'autre.
        Le meme essai sous un faux nom d'hote (« DNS rebinding ») passait aussi.

        Deux verifications, les memes que celles des carnets Jupyter :

          - l'en-tete Host doit nommer ce serveur. Un domaine etranger qui
            resout vers 127.0.0.1 garde son nom dans Host : c'est ce qui
            trahit le rebinding, y compris pour une simple LECTURE ;
          - sur ce qui MODIFIE, l'en-tete Origin, quand il est present, doit
            designer ce serveur. Un navigateur l'envoie toujours sur un POST
            venu d'un autre site, meme en « no-cors ».

        Ce qui n'envoie pas d'Origin — la ligne de commande, un script Termux,
        curl — reste admis : c'est un processus du telephone, et c'est la
        frontiere de confiance que ce tableau de bord a toujours eue.
        """
        admis = self._hotes_admis()
        hote = (self.headers.get("Host") or "").strip().lower()
        if hote and hote not in admis:
            self._json({"erreur": "hote refuse : {}".format(hote[:60])}, 403)
            return False
        if not modifie:
            return True
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            self._json({"erreur": "requete venue d'un autre site"}, 403)
            return False
        origine = (self.headers.get("Origin") or "").strip().lower()
        if origine and origine != "null":
            nom = urlparse(origine).netloc
            if nom not in admis:
                self._json({"erreur": "origine refusee : {}".format(
                    origine[:60])}, 403)
                return False
        elif origine == "null":
            # Une page ouverte depuis un fichier, un iframe isole : aucune
            # raison legitime de modifier l'atelier depuis la.
            self._json({"erreur": "origine opaque refusee"}, 403)
            return False
        return True

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
        if not self._origine_sure(modifie=False) or not self._autorise():
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
        elif chemin == "/api/ab":
            self._json({"tests": _tests_ab()})
        elif chemin.startswith("/api/ab/"):
            try:
                identifiant = int(chemin.rsplit("/", 1)[-1])
            except ValueError:
                self._json({"erreur": "numero de test invalide"}, 400)
                return
            detail = _detail_ab(identifiant)
            self._json(detail, 200 if "erreur" not in detail else 404)
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
        elif chemin == "/api/docteur":
            from ..core import diagnostic as module_diagnostic

            # Le reseau et les serveurs locaux sont sondes seulement ici :
            # la page ne demande le diagnostic que sur un clic.
            self._json(module_diagnostic.etat_installation())
        elif chemin == "/api/bilan":
            from ..core import apprentissage

            self._json(apprentissage.bilan())
        elif chemin.startswith("/api/marche/"):
            marche_id = chemin.rsplit("/", 1)[-1]
            with _VERROU:
                sondage = MARCHES.get(marche_id)
            self._json(sondage if sondage else {"erreur": "sondage inconnu"},
                       200 if sondage else 404)
        elif chemin.startswith("/archive/"):
            self._servir_archive(unquote(chemin[len("/archive/"):]))
        elif chemin.startswith("/fichier/"):
            self._servir_produit(unquote(chemin[len("/fichier/"):]))
        else:
            self._json({"erreur": "route inconnue"}, 404)

    def do_POST(self) -> None:
        chemin = urlparse(self.path).path
        if not self._origine_sure(modifie=True) or not self._autorise():
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
                {k: v for k, v in options.items()
                 if k in reglages.DEFAUTS and k not in reglages.HORS_WEB})})
        elif chemin == "/api/veille":
            options = self._corps_json()
            if options is None:
                return
            self._json(*self._lancer_veille(options))
        elif chemin == "/api/marche":
            options = self._corps_json()
            if options is None:
                return
            self._json(*self._lancer_marche(options))
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
        elif chemin == "/api/televerser":
            self._televerser()
        elif chemin == "/api/ab":
            options = self._corps_json()
            if options is None:
                return
            self._json(*self._gerer_ab(options))
        elif chemin == "/api/produit":
            options = self._corps_json()
            if options is None:
                return
            self._json(*self._gerer_produit(options))
        else:
            self._json({"erreur": "route inconnue"}, 404)

    # -- implementations -------------------------------------------------
    def _fabriquer(self) -> None:
        options = self._corps_json()
        if options is None:
            return
        type_produit = str(options.get("type") or "ebook")
        # « auto » n'est pas un type du catalogue : c'est la demande de le
        # faire choisir. Le choix coute un appel de modele, donc il a lieu
        # dans le fil de fabrication, comme celui de la niche.
        if type_produit != AUTO and catalogue.obtenir(type_produit) is None:
            self._json({"erreur": "type de produit inconnu"}, 400)
            return
        # Un sujet vide n'est plus un refus : c'est une demande. Le choix
        # coute un appel de modele et une mesure de marche, donc il se fait
        # dans le fil de fabrication — refuser ici bloquait la requete HTTP
        # le temps du sondage, et le navigateur voyait une page figee.
        sujet = str(options.get("sujet") or "").strip()
        options["sujet"] = sujet
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
            _ranger_travaux()
            TRAVAUX[travail_id] = {
                "id": travail_id, "type": type_produit,
                "sujet": sujet[:300] or "(l'usine choisit)", "statut": "en_cours",
                "debut": time.time(), "journal": [], "resultat": None, "erreur": "",
            }
        _en_tache_de_fond(_lancer, travail_id, type_produit, options)
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
        if action in ("prospecter", "prospecter-fiction"):
            # Le jumeau manuel de « remplir seule » : la boucle continue sait
            # deja chercher des niches, mais seulement quand elle tourne. On
            # ne peut pas prospecter dans le fil HTTP — un sondage de marche
            # par domaine met des dizaines de secondes et le navigateur
            # verrait une page figee —, donc un fil dedie, comme une
            # fabrication.
            fiction = action == "prospecter-fiction"
            travail_id = uuid.uuid4().hex[:12]
            with _VERROU:
                _ranger_travaux()
                TRAVAUX[travail_id] = {
                    "id": travail_id, "type": "prospection",
                    "sujet": ("recherche de promesses de lecture" if fiction
                              else "recherche de niches"),
                    "statut": "en_cours",
                    "debut": time.time(), "journal": [], "resultat": None,
                    "erreur": "",
                }
            _en_tache_de_fond(_lancer_prospection, travail_id, fiction)
            return {"travail": travail_id}
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
        from ..production import demander_arret, verrou_actif

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
        _lancer_la_boucle(auto=bool(options.get("auto")), maximum=maximum)
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
        entetes = {"Cache-Control": "no-cache"}
        if mime.startswith("text/html"):
            # La page ne charge rien d'exterieur : le dire au navigateur coute
            # une ligne et arrete net un script qui aurait passe l'echappement.
            # « data: » pour la seule exception, l'icone d'onglet ;
            # « unsafe-inline » pour les largeurs de jauges posees en style=.
            # « frame-ancestors » : encadree dans une page tierce, la commande
            # de fabrication se cliquerait a travers un calque invisible.
            entetes["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'")
            entetes["X-Frame-Options"] = "DENY"
        self._repondre(200, cible.read_bytes(), mime, entetes)

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
        _en_tache_de_fond(_scouter, veille_id, sujet, periode, combien)
        return ({"veille": veille_id}, 200)

    def _lancer_marche(self, options: Dict[str, Any]):
        """Mesure une niche depuis quatre sources publiques, en tache de fond."""
        sujet = str(options.get("sujet") or "").strip()
        if not sujet:
            return ({"erreur": "sujet manquant"}, 400)
        with _VERROU:
            if any(m["statut"] == "en_cours" for m in MARCHES.values()):
                return ({"erreur": "un sondage est deja en cours"}, 429)
            marche_id = uuid.uuid4().hex[:12]
            MARCHES[marche_id] = {"id": marche_id, "sujet": sujet[:300],
                                  "statut": "en_cours", "debut": time.time(),
                                  "resultat": None, "erreur": ""}
        _en_tache_de_fond(_sonder_marche, marche_id, sujet)
        return ({"marche": marche_id}, 200)

    def _gerer_doublons(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Reconstruit les empreintes manquantes.

        Les empreintes sont posees a la fabrication. Un catalogue constitue
        avant leur introduction n'en a aucune, et la carte des doublons
        reste vide chez celui qui en aurait le plus besoin.
        """
        if str(options.get("action") or "") != "reconstruire":
            return {"erreur": "action inconnue"}
        return _reconstruire_empreintes()

    def _gerer_ab(self, options: Dict[str, Any]):
        """Creer un test, reporter des chiffres, dater, conclure.

        Renvoie (corps, code). La creation part en tache de fond : elle
        appelle le modele, et pour les couvertures elle dessine quatre
        images — trop long pour une requete qui attend.
        """
        action = str(options.get("action") or "")

        if action == "creer":
            sur = str(options.get("sur") or "titre")
            if sur not in ("titre", "couverture", "accroche", "prix"):
                return ({"erreur": "sujet de test inconnu"}, 400)
            produit = str(options.get("produit") or "")
            titre = str(options.get("titre") or "").strip()
            if produit and not store.lire_produit(produit):
                return ({"erreur": "produit inconnu"}, 400)
            if not produit and not titre:
                return ({"erreur": "indiquez un produit ou un titre"}, 400)
            with _VERROU:
                en_cours = [t for t in TRAVAUX.values()
                            if t["statut"] == "en_cours"]
                if len(en_cours) >= 2:
                    return ({"erreur": "deux travaux sont deja en cours"}, 429)
                travail_id = uuid.uuid4().hex[:12]
                _ranger_travaux()
                TRAVAUX[travail_id] = {
                    "id": travail_id, "type": "ab",
                    "sujet": (titre or produit)[:300], "statut": "en_cours",
                    "debut": time.time(), "journal": [], "resultat": None,
                    "erreur": "",
                }
            _en_tache_de_fond(_lancer_ab, travail_id, options)
            return ({"travail": travail_id}, 200)

        if action == "observer":
            identifiant = _entier(options.get("variante"))
            try:
                experience.observer(identifiant,
                                    vues=_entier(options.get("vues")),
                                    actions=_entier(options.get("actions")))
            except ValueError as exc:
                # « plus d'actions que de vues » est une erreur de saisie,
                # pas une panne : elle se corrige a l'ecran.
                return ({"erreur": str(exc)}, 400)
            return ({"observe": identifiant}, 200)

        if action == "periode":
            identifiant = _entier(options.get("variante"))
            try:
                pose = experience.fixer_periode(
                    identifiant, str(options.get("du") or ""),
                    str(options.get("au") or ""))
            except ValueError as exc:
                return ({"erreur": str(exc)}, 400)
            if not pose:
                return ({"erreur": "variante introuvable"}, 404)
            return ({"datee": identifiant}, 200)

        if action == "clore":
            identifiant = _entier(options.get("id"))
            if experience.lire(identifiant) is None:
                return ({"erreur": "test inconnu"}, 404)
            experience.cloturer(identifiant, _entier(options.get("gagnante")),
                                str(options.get("note") or ""))
            return ({"close": identifiant}, 200)

        if action == "supprimer":
            identifiant = _entier(options.get("id"))
            return ({"supprime": experience.supprimer(identifiant)}, 200)

        return ({"erreur": "action inconnue"}, 400)

    def _gerer_produit(self, options: Dict[str, Any]):
        """Ce qui se fait APRES avoir regarde un produit : vendre, empaqueter.

        La carte listait les produits et servait leurs fichiers, sans savoir
        rien en faire — alors que c'est exactement le moment ou l'on veut le
        kit de vente ou l'archive.
        """
        action = str(options.get("action") or "")
        produit_id = str(options.get("id") or "")
        produit = store.lire_produit(produit_id) if produit_id else None
        if produit is None:
            return ({"erreur": "produit inconnu"}, 404)
        if action in ("livrer", "marketing"):
            from ..pipelines import apres

            refus = apres.pas_encore_vendable(produit)
            if refus:
                return ({"erreur": refus}, 409)

        if action == "livrer":
            # Empaqueter ne coute aucun appel : c'est de la copie de fichiers.
            from ..packaging import livraison
            from ..pipelines.base import slug

            dossier = Path(produit["dossier"] or "")
            if not dossier.exists():
                return ({"erreur": "dossier du produit introuvable"}, 404)
            meta = produit.get("meta") or {}
            archive = livraison.empaqueter(
                dossier, slug(produit["titre"] or produit_id, 46),
                produit["titre"] or produit_id,
                str(meta.get("auteur") or reglages.lire("auteur") or "Usine-IA"),
                promesse=str(meta.get("promesse") or ""),
                contact=str(reglages.lire("contact") or ""),
                livres=meta.get("fichiers"),
                langue=code_langue(produit.get("langue") or ""))
            return ({"archive": _lien_fichier(archive),
                     "ko": max(1, archive.stat().st_size // 1024)}, 200)

        if action == "marketing":
            # Le kit de vente appelle le modele : en tache de fond, comme
            # une fabrication.
            with _VERROU:
                if len([t for t in TRAVAUX.values()
                        if t["statut"] == "en_cours"]) >= 2:
                    return ({"erreur": "deux travaux sont deja en cours"}, 429)
                travail_id = uuid.uuid4().hex[:12]
                _ranger_travaux()
                TRAVAUX[travail_id] = {
                    "id": travail_id, "type": "marketing",
                    "sujet": (produit["titre"] or produit_id)[:300],
                    "statut": "en_cours", "debut": time.time(), "journal": [],
                    "resultat": None, "erreur": "",
                }
            _en_tache_de_fond(_lancer_marketing, travail_id, produit_id,
                              str(options.get("prix") or ""))
            return ({"travail": travail_id}, 200)

        if action == "reprendre":
            # Reprendre appelle le modele : en tache de fond, comme une
            # fabrication — sinon la requete tient dix minutes et le
            # navigateur la coupe avant la fin.
            from ..pipelines import carnet

            dossier = Path(produit["dossier"] or "")
            commande = carnet.commande(dossier)
            if not commande:
                return ({"erreur": "ce produit n'a pas garde la commande qui "
                                   "l'a fabrique ; relancez-la a la main"}, 409)
            with _VERROU:
                if len([t for t in TRAVAUX.values()
                        if t["statut"] == "en_cours"]) >= 2:
                    return ({"erreur": "deux travaux sont deja en cours"}, 429)
                travail_id = uuid.uuid4().hex[:12]
                _ranger_travaux()
                TRAVAUX[travail_id] = {
                    "id": travail_id, "type": "reprise",
                    "sujet": (produit["titre"] or produit_id)[:300],
                    "statut": "en_cours", "debut": time.time(), "journal": [],
                    "resultat": None, "erreur": "",
                }
            _en_tache_de_fond(_lancer_reprise, travail_id, produit_id)
            return ({"travail": travail_id}, 200)

        if action == "supprimer":
            # Effacer depuis le navigateur demande la meme prudence qu'ailleurs :
            # le dossier doit etre SOUS l'atelier. Une fiche dont le chemin a
            # ete modifie a la main ne doit pas pouvoir faire effacer autre
            # chose, et un POST egare non plus — d'ou la confirmation exigee.
            import shutil

            if not options.get("confirme"):
                return ({"erreur": "confirmation manquante"}, 400)
            dossier = Path(produit["dossier"] or "")
            if dossier.exists() and dossier.is_dir():
                try:
                    dossier.resolve().relative_to(config.PRODUITS_DIR.resolve())
                except ValueError:
                    return ({"erreur": "dossier hors de l'atelier"}, 400)
                shutil.rmtree(dossier, ignore_errors=True)
            store.supprimer_produit(produit_id)
            return ({"efface": produit_id, "produits": _produits()}, 200)

        return ({"erreur": "action inconnue"}, 400)

    def _gerer_sauvegarde(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Ecrire une archive, regarder ce qu'elle contient, ou la remettre.

        Restaurer remplace l'atelier entier. Ce n'est pas une operation
        qu'on lance par inadvertance, donc la page la demande en deux
        temps — et le serveur exige que la confirmation lui parvienne
        explicitement : un POST egare ne doit rien remplacer.
        """
        from ..core import sauvegarde

        action = str(options.get("action") or "creer")
        if action == "creer":
            try:
                archive = sauvegarde.creer(
                    avec_produits=bool(options.get("avec_produits")))
            except OSError as exc:
                return {"erreur": securite.expurger(str(exc))}
            return {"archive": _fiche_archive(archive),
                    "sauvegardes": _sauvegardes()["archives"]}

        if action == "inspecter":
            archive = _archive_nommee(options.get("nom"))
            if archive is None:
                return {"erreur": "archive introuvable"}
            fiche = sauvegarde.inspecter(archive)
            fiche["nom"] = archive.name
            fiche["schema_courant"] = store.VERSION_SCHEMA
            return fiche

        if action == "restaurer":
            return self._restaurer(sauvegarde, options)

        return {"erreur": "action inconnue"}

    def _restaurer(self, sauvegarde, options: Dict[str, Any]) -> Dict[str, Any]:
        """Remet l'atelier dans l'etat d'une archive."""
        if options.get("confirme") is not True:
            # Ce n'est pas une politesse : la confirmation est un argument
            # de la requete, pas un etat de la page. Une page rechargee,
            # un rejeu de requete ou un script tiers n'en herite pas.
            return {"erreur": "restauration non confirmee"}
        archive = _archive_nommee(options.get("nom"))
        if archive is None:
            return {"erreur": "archive introuvable"}

        occupe = _atelier_occupe()
        if occupe:
            # Remplacer la base sous un produit en cours de fabrication le
            # ferait ecrire dans un atelier qui n'existe plus.
            return {"erreur": occupe}

        resultat = sauvegarde.restaurer(
            archive, avec_produits=bool(options.get("avec_produits", True)))
        if not resultat["valide"]:
            return {"erreur": resultat["probleme"]}
        evenements.publier("journal",
                           message="atelier restaure depuis " + archive.name)
        return {"restaure": True, "nom": archive.name,
                "fichiers_produits": resultat["fichiers_produits"],
                "refuses": resultat["refuses"],
                "ancienne_base": Path(resultat["ancienne_base"]).name
                if resultat["ancienne_base"] else ""}

    def _televerser(self) -> None:
        """Recoit une archive venue d'ailleurs et la range avec les autres.

        C'est le cas de la reinstallation : le telephone a ete efface, et
        l'archive est sur un ordinateur ou dans un nuage. Sans cela, ni la
        page ni la ligne de commande ne savent la faire revenir — toutes
        deux veulent un fichier deja sur l'appareil.

        Le corps est ecrit par morceaux sur le disque, jamais garde en
        memoire : une archive avec les fichiers de produits pese plus que
        ce qu'un telephone peut tenir en RAM.
        """
        from ..core import sauvegarde

        try:
            annonce = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            annonce = 0
        if annonce <= 0:
            self._json({"erreur": "archive vide"}, 400)
            return
        if annonce > TELEVERSEMENT_MAX:
            self._json({"erreur": "archive de {} Mo : la limite est {} Mo"
                        .format(annonce // (1024 * 1024),
                                TELEVERSEMENT_MAX // (1024 * 1024))}, 413)
            return

        dossier = _dossier_sauvegardes()
        dossier.mkdir(parents=True, exist_ok=True)
        entrant = dossier / ".entrant-{}.zip".format(uuid.uuid4().hex[:12])
        recus = 0
        try:
            with entrant.open("wb") as sortie:
                while recus < annonce:
                    morceau = self.rfile.read(min(65536, annonce - recus))
                    if not morceau:
                        break
                    recus += len(morceau)
                    sortie.write(morceau)
            if recus != annonce:
                entrant.unlink(missing_ok=True)
                self._json({"erreur": "transfert interrompu"}, 400)
                return

            # On ne garde que ce qui est lisible : une archive invalide
            # rangee avec les autres ferait croire a une sauvegarde.
            fiche = sauvegarde.inspecter(entrant)
            if not fiche["valide"]:
                entrant.unlink(missing_ok=True)
                self._json({"erreur": fiche["probleme"]}, 400)
                return

            depose = _nom_libre(dossier, _nom_archive_sur(
                (parse_qs(urlparse(self.path).query).get("nom") or [""])[0]))
            entrant.rename(depose)
        except OSError as exc:
            entrant.unlink(missing_ok=True)
            self._json({"erreur": securite.expurger(str(exc))}, 500)
            return

        fiche["nom"] = depose.name
        fiche["schema_courant"] = store.VERSION_SCHEMA
        self._json({"archive": _fiche_archive(depose), "fiche": fiche,
                    "sauvegardes": _sauvegardes()["archives"]})

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

    # Les types de documents dans lesquels un navigateur execute du script :
    # HTML, XHTML, SVG, XML (feuilles XSLT). Une image matricielle ou un PDF
    # n'en font pas partie, et n'ont pas a payer le bac a sable.
    SCRIPTABLES = frozenset({
        "text/html", "application/xhtml+xml", "image/svg+xml",
        "text/xml", "application/xml",
    })

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
        # Ces fichiers sont du contenu GENERE — et pour les produits
        # « logiciel », du code que le modele a ecrit, index.html compris.
        # Servis tels quels, ils partageaient l'origine du tableau de bord :
        # un script dedans parlait a /api/usine ou /api/fabriquer en
        # meme-origine, sans jeton. Mesure du 26/09/2026 dans Chromium : une
        # page deposee dans un dossier de produit lisait /api/etat et posait
        # une demande d'arret. Le bac a sable donne au document une origine
        # opaque : le quiz continue de se corriger (allow-scripts), les
        # images relatives se chargent, mais /api redevient une autre origine.
        # Seuls les types capables de porter un script y passent : un PDF en
        # bac a sable ne s'affiche plus dans certains navigateurs.
        entetes = None
        if type_mime.split(";")[0] in self.SCRIPTABLES:
            entetes = {"Content-Security-Policy": "sandbox allow-scripts"}
        self._repondre(200, cible.read_bytes(), type_mime, entetes)


def _lien_fichier(chemin: Any) -> str:
    """URL de telechargement d'un fichier de produit, ou chaine vide.

    Les variantes de couverture sont des PNG poses dans l'atelier. Le
    tableau de bord est la seule interface capable de les MONTRER — c'est
    tout l'interet de comparer des couvertures — mais il ne sert que ce qui
    est sous le dossier des produits.
    """
    texte = str(chemin or "")
    if not texte:
        return ""
    try:
        relatif = Path(texte).resolve().relative_to(config.PRODUITS_DIR.resolve())
    except (ValueError, OSError):
        return ""
    return "/fichier/" + "/".join(quote(part) for part in relatif.parts)


def _tests_ab(limite: int = 20) -> List[Dict[str, Any]]:
    """Les tests A/B, avec l'etat de leur verdict."""
    sortie = []
    for essai in experience.lister(limite):
        analyse = experience.analyser(essai["id"])
        sortie.append({
            "id": essai["id"], "titre": essai["titre"], "sujet": essai["sujet"],
            "statut": essai["statut"], "produit_id": essai["produit_id"],
            "nb_variantes": essai["nb_variantes"],
            "verdict": analyse["verdict"]["etat"],
        })
    return sortie


def _detail_ab(experience_id: int) -> Dict[str, Any]:
    """Un test au complet : variantes, images, verdict, rythme de vente."""
    from ..pipelines import variantes as pipeline_variantes

    analyse = experience.analyser(experience_id)
    if "erreur" in analyse:
        return analyse

    # « variantes.fichier » est un nom de fichier, pas un chemin : il ne
    # vaut que rapporte au dossier du test.
    essai_courant = analyse["experience"]
    dossier = pipeline_variantes.dossier_du_test(
        essai_courant["produit_id"] or "", essai_courant["titre"] or "")

    rythmes = {}
    mesures = experience.mesures_reelles(experience_id)
    if not mesures.get("probleme"):
        for mesure in mesures["variantes"]:
            rythmes[mesure["variante"]["id"]] = {
                "periode": mesure["periode"], "ventes": mesure["ventes"],
                "jours": round(mesure["jours"], 1)}

    lot = []
    for variante in analyse["variantes"]:
        meta = variante.get("meta") or {}
        lot.append({
            "id": variante["id"], "etiquette": variante["etiquette"],
            "contenu": variante["contenu"],
            "image": _lien_fichier(dossier / variante["fichier"]
                                   if variante.get("fichier") else ""),
            "vues": variante["total_vues"], "actions": variante["total_actions"],
            "debut": variante.get("debut") or "", "fin": variante.get("fin") or "",
            "angle": str(meta.get("angle") or meta.get("style") or ""),
            "pourquoi": str(meta.get("pourquoi") or meta.get("diagnostic") or ""),
            "stats": variante.get("stats") or {},
            "rythme": rythmes.get(variante["id"], {}),
        })

    essai = essai_courant
    return {
        "id": essai["id"], "titre": essai["titre"], "sujet": essai["sujet"],
        "statut": essai["statut"], "produit_id": essai["produit_id"],
        "gagnante": essai.get("gagnante") or 0,
        "variantes": lot,
        "verdict": analyse["verdict"],
        "minimum_actions": experience.MINIMUM_ACTIONS,
        # Ce que le rythme ne peut pas dire tant qu'il manque des dates :
        # la page doit l'afficher, pas laisser croire a un resultat vide.
        "rythme_probleme": mesures.get("probleme", ""),
        "sans_periode": sum(1 for v in lot if not v["debut"]),
    }


def _lancer_ab(travail_id: str, options: Dict[str, Any]) -> None:
    """Fabrique les variantes d'un test. Lent : IA, et parfois des images."""
    from ..pipelines import variantes as pipeline_variantes

    journal = _journal_de(travail_id)

    try:
        produit_id = str(options.get("produit") or "")
        produit = store.lire_produit(produit_id) if produit_id else None
        titre = (produit["titre"] if produit
                 else str(options.get("titre") or "")).strip()
        description = ""
        if produit:
            meta = produit.get("meta") or {}
            description = str(meta.get("promesse") or produit.get("sujet") or "")

        from ..pipelines import porte

        profil = reglages.charger()
        ctx = porte.contexte_existant(
            produit_id if produit else "", journal,
            sujet=description or titre,
            audience=options.get("audience") or profil["audience"],
            ton=profil["ton"], taille=profil["taille"],
            qualite=profil["qualite"], auteur=profil["auteur"],
            sans_image=bool(options.get("sans_image")) or not profil["images"])

        dossier = pipeline_variantes.dossier_du_test(produit_id, titre)
        journal("Preparation du test A/B...")
        resultat = pipeline_variantes.preparer_test(
            ctx, titre, dossier, sujet=str(options.get("sur") or "titre"),
            nombre=_entier(options.get("nombre")) or 5,
            description=description, produit_id=produit_id)
        with _VERROU:
            TRAVAUX[travail_id].update(
                statut="termine",
                resultat={"experience_id": resultat["experience_id"],
                          "distinction": resultat["distinction"],
                          "planche": _lien_fichier(resultat["planche"])})
        journal("Test A/B prêt.")
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Échec : " + message)


def _lancer_marketing(travail_id: str, produit_id: str, prix: str) -> None:
    """Kit de vente d'un produit deja fabrique."""
    from ..marketing import vente

    journal = _journal_de(travail_id)

    try:
        produit = store.lire_produit(produit_id)
        meta = produit.get("meta") or {}
        from ..pipelines import porte

        profil = reglages.charger()
        ctx = porte.contexte_existant(
            produit_id, journal,
            sujet=produit["sujet"] or produit["titre"] or produit_id,
            audience=produit["audience"] or profil["audience"],
            auteur=str(meta.get("auteur") or profil["auteur"]),
            ton=str(meta.get("ton") or profil["ton"]))
        ctx.prix = prix
        ctx.produit_id = produit_id
        journal("Rédaction du kit de vente...")
        description = "Produit de type {}. {}".format(
            produit["type"], meta.get("promesse") or produit["sujet"] or "")
        resultat = vente.produire_kit(
            ctx, produit["titre"] or produit_id, description,
            Path(produit["dossier"]))
        dossier = Path(resultat["dossier"])
        with _VERROU:
            TRAVAUX[travail_id].update(
                statut="termine",
                resultat={"fichiers": [_lien_fichier(dossier / nom)
                                       for nom in resultat["fichiers"]]})
        journal("Kit de vente prêt.")
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Échec : " + message)


def _lancer_reprise(travail_id: str, produit_id: str) -> None:
    """Finit un produit interrompu, en rejouant sa commande d'origine.

    On passe par la CLI plutot que par le pipeline : c'est elle qui sait
    reconstruire le contexte a partir des arguments, et une seconde
    reconstruction cote web aurait fini par diverger de la premiere.
    """
    from .. import cli
    from ..pipelines import carnet

    journal = _journal_de(travail_id)

    try:
        from ..pipelines import reprise

        if reprise.par_le_catalogue(produit_id):
            # Le cas ordinaire depuis le telephone : un produit fabrique ici
            # n'a pas de ligne de commande, et en rejouer une le faisait
            # mourir sur « unrecognized arguments ».
            journal("Reprise depuis le carnet...")
            reprise.reprendre(produit_id, journal=journal)
            code = 0
        else:
            produit = store.lire_produit(produit_id) or {}
            commande = carnet.commande(Path(produit.get("dossier") or ""))
            journal("Reprise : usine " + " ".join(commande))
            try:
                code = cli.principal(list(commande) + ["--reprendre-id", produit_id])
            except SystemExit as exc:
                # argparse sort par « SystemExit », qu'un « except Exception »
                # laisse passer : le fil mourait, et le travail restait
                # « en cours » pour toujours dans le tableau de bord.
                journal("La commande gardée pour ce produit ne se rejoue pas "
                        "(produit fabrique avant la version qui garde son "
                        "contexte) : relancez-le.")
                code = exc.code if isinstance(exc.code, int) else 2
        fini = store.lire_produit(produit_id) or {}
        manquants = (fini.get("meta") or {}).get("manquants") or []
        with _VERROU:
            TRAVAUX[travail_id].update(
                statut="termine" if code == 0 else "echec",
                resultat={"statut": fini.get("statut"),
                          "manquants": manquants,
                          "produits": _produits()})
        journal("Produit termine." if not manquants
                else "{} section(s) manquent encore.".format(len(manquants)))
    except Exception as exc:
        message = securite.expurger(str(exc))
        with _VERROU:
            TRAVAUX[travail_id].update(statut="echec", erreur=message)
        journal("Échec : " + message)


def _sonder_marche(marche_id: str, sujet: str) -> None:
    from ..core import marche as module_marche

    try:
        rapport = module_marche.sonder(sujet)
        with _VERROU:
            MARCHES[marche_id].update(statut="termine", resultat=rapport)
    except Exception as exc:
        with _VERROU:
            MARCHES[marche_id].update(statut="echec",
                                      erreur=securite.expurger(str(exc)))


def _dossier_sauvegardes() -> Path:
    return config.WORKDIR / "sauvegardes"


def _fiche_archive(archive: Path) -> Dict[str, Any]:
    etat = archive.stat()
    return {"nom": archive.name, "ko": max(1, etat.st_size // 1024),
            "ts": etat.st_mtime}


def _nom_archive_sur(propose: Any) -> str:
    """Un nom de fichier, jamais un chemin.

    Le nom arrive du navigateur, donc de la machine d'en face. « Path.name »
    coupe tout dossier, et le reste des caracteres est ramene a ce qui ne
    veut rien dire pour un systeme de fichiers.
    """
    brut = PurePosixPath(str(propose or "").replace("\\", "/")).name
    propre = re.sub(r"[^A-Za-z0-9._-]+", "-", brut).strip("-.")
    if propre.lower().endswith(".zip"):
        propre = propre[:-4]
    return (propre[:72] or "archive-recue") + ".zip"


def _nom_libre(dossier: Path, nom: str) -> Path:
    """Le meme nom, augmente d'un rang s'il est deja pris.

    Ecraser une archive existante serait la pire facon de recevoir une
    sauvegarde : on remplacerait celle qui protege par celle qu'on teste.
    """
    cible = dossier / nom
    if not cible.exists():
        return cible
    souche = nom[:-4]
    for rang in range(2, 1000):
        cible = dossier / "{}-{}.zip".format(souche, rang)
        if not cible.exists():
            return cible
    return dossier / "{}-{}.zip".format(souche, uuid.uuid4().hex[:8])


def _archive_nommee(nom: Any) -> Optional[Path]:
    """L'archive portant ce nom dans le dossier des sauvegardes, ou None.

    Meme controle que pour le telechargement : le dossier des sauvegardes
    est a cote de « usine.db », et un nom est un nom, pas un chemin.
    """
    texte = str(nom or "")
    if not texte or "/" in texte or "\\" in texte or ".." in texte:
        return None
    if not texte.endswith(".zip"):
        return None
    racine = _dossier_sauvegardes().resolve()
    cible = (racine / texte).resolve()
    try:
        cible.relative_to(racine)
    except ValueError:
        return None
    return cible if cible.is_file() else None


def _atelier_occupe() -> str:
    """Raison de ne pas toucher a la base maintenant, ou chaine vide.

    Le verrou de l'usine continue est verifie par « sauvegarde », pour que
    la ligne de commande en beneficie aussi. Restent les travaux propres au
    tableau de bord, qu'elle ne peut pas connaitre.
    """
    from ..core import sauvegarde

    occupe = sauvegarde.occupe()
    if occupe:
        return occupe
    with _VERROU:
        if any(t["statut"] == "en_cours" for t in TRAVAUX.values()):
            return "une fabrication est en cours : attendez qu'elle se termine"
        if any(v["statut"] == "en_cours" for v in VEILLES.values()):
            return "une veille est en cours : attendez qu'elle se termine"
    return ""


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


# Reglages qu'on ne change PAS depuis le tableau de bord.
#
# « jeton_web » est le mot de passe qui protege ce tableau de bord. Le rendre
# modifiable par lui revenait a laisser la porte decider de sa propre serrure :
# qui atteint la page peut s'y enfermer en posant un jeton, ou l'ouvrir a tous
# en l'effacant. Un identifiant ne se change jamais par la surface qu'il garde
# — il se change depuis la machine, par « usine reglages » ou le menu.


def _etat() -> Dict[str, Any]:
    from ..core import serie as module_serie

    # La base d'abord, et on s'arrete la si elle ne se lit plus. Tout ce qui
    # suit l'interroge — fournisseurs, pool, series, file — et le tableau de
    # bord mourait donc sur sa toute premiere requete : la page restait vide,
    # y compris le bouton « docteur » qui, lui, aurait su repondre.
    base = store.diagnostic_base()
    if base:
        return {"version": __version__, "base": base,
                "remede": "usine sauvegarde --restaurer archive.zip --oui"}

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
        "base": "",
        "fournisseurs": fournisseurs,
        # Une cle, pas un genre de fournisseur : un jeton Pollinations est
        # une cle, et « sans_cle » le faisait compter pour rien — la page
        # disait « Aucune cle API » a qui en avait une.
        "avec_cle": sum(1 for f in fournisseurs
                        if f["disponible"] and not f["local"] and f["nb_cles"]),
        "cles": pool_cles.resume(),
        "travaux": travaux,
        "types": _types_offerts(),
        # La liste sert a proposer les suites en cours plutot qu'a faire
        # retaper leur nom : une faute de frappe cree une seconde serie vide,
        # et le tome repartirait de zero sans rien dire.
        "series": [s["nom"] for s in module_serie.lister()],
        "agents": [{"nom": a.nom, "emoji": a.emoji,
                    "etiquette": equipe.ETIQUETTES.get(a.nom, a.nom)}
                   for a in equipe.EQUIPE.values()],
        "tons": sorted(TONS),
        "tailles": sorted(TAILLES, key=lambda t: TAILLES[t][0]),
        "qualites": ["rapide", "standard", "exigeant"],
        "reseaux": sorted(social.RESEAUX),
        # TOUS les reglages, moins les secrets. Le tableau de bord n'en
        # montrait que huit sur vingt-six : les dix-huit autres — le contact
        # imprime dans la notice de l'acheteur, la marque, les budgets qui
        # arretent l'usine continue — n'existaient que dans un fichier JSON
        # que personne n'ouvre.
        "reglages": {k: v for k, v in profil.items()
                     if k in reglages.DEFAUTS and k not in reglages.HORS_WEB},
        # Les peaux viennent d'ici, pas du navigateur : les recopier dans le
        # script en ferait une seconde liste, et c'est celle du navigateur qui
        # vieillirait sans que rien ne le dise.
        "peaux": [{"cle": t["cle"], "nom": t["nom"],
                   "description": t["description"], "anime": t["anime"]}
                  for t in reglages.THEMES],
        # La structure, pour que la page range comme le menu Termux range.
        "groupes_reglages": [
            {"cle": g["cle"], "titre": g["titre"], "aide": g["aide"],
             "reglages": [
                 {"nom": nom,
                  "etiquette": reglages.ETIQUETTES.get(nom, nom),
                  "description": reglages.DESCRIPTIONS.get(nom, ""),
                  "genre": ("booleen" if isinstance(reglages.DEFAUTS[nom], bool)
                            else "entier"
                            if isinstance(reglages.DEFAUTS[nom], int)
                            else "texte"),
                  "choix": list(reglages.FERMES.get(nom, ()))}
                 for nom in g["reglages"] if nom not in reglages.HORS_WEB]}
            for g in reglages.GROUPES],
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
            # Ce qui reste a ecrire : la page en fait un bouton « Reprendre »
            # plutot qu'un produit qu'on croit fini.
            "manquants": [str(m) for m in (meta.get("manquants") or [])],
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
