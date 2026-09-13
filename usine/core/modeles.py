"""Choisir un modele dans le catalogue que le fournisseur sert VRAIMENT.

Le probleme que ce module resout est le plus perissable du depot, et il est
silencieux. Mesure du 13/09/2026, sur le catalogue reel de NVIDIA :

    configure : meta/llama-3.1-8b-instruct, meta/llama-3.3-70b-instruct
    servi     : ni l'un ni l'autre — 82 modeles, aucun des deux

Chaque appel renvoyait donc 404. Le routeur en tirait la seule conclusion
possible pour lui — « modele inconnu » — et mettait NVIDIA au repos pour une
demi-heure. Pour l'utilisateur, une cle NVIDIA valide ne servait a rien, et
rien ne disait pourquoi. Meme constat chez OpenRouter, dont les deux modeles
« :free » configures ne figurent plus dans les dix-neuf servis.

Recopier les bons identifiants aurait repare la panne d'aujourd'hui et pas
celle du mois prochain : ces catalogues bougent toutes les quelques semaines.
Le fournisseur, lui, sait ce qu'il sert. On le lui demande.

D'ou les deux idees de ce module :

1. **Le catalogue vivant.** « GET /v1/models » chez le fournisseur, garde en
   cache quelques heures, parce que la question ne doit pas se poser a chaque
   appel — et parce qu'un telephone hors ligne doit continuer de fabriquer.

2. **Le role plutot que le nom.** L'usine ne demande pas
   « meta/llama-3.3-70b » : elle demande « un modele costaud », ou « un
   modele qui ecrit de la fiction ». Le choix se fait par motifs sur le
   catalogue du jour, donc il survit a un renommage.

Ce qui n'est PAS fait ici, et volontairement : deviner. Sans catalogue
lisible, on rend le modele configure et on laisse le routeur signaler le 404.
Substituer a l'aveugle ferait appeler n'importe quoi — un modele
d'embeddings, un classificateur de securite — et rendrait des « chapitres »
que personne ne comprendrait.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

from . import config, store

# Duree de vie du catalogue en cache. Quelques heures : assez long pour qu'une
# session entiere ne repose jamais la question, assez court pour qu'un modele
# retire le matin soit vu dans la journee.
DUREE_CACHE = 6 * 3600

# Ce qui ne sait pas ecrire, et ne doit donc JAMAIS etre choisi pour du texte.
# Un modele d'embeddings appele en redaction ne leve pas d'erreur : il rend un
# vecteur, ou une phrase vide, ou du bruit. C'est exactement le genre de
# substitution qui produit un chapitre incomprehensible sans rien casser.
_INTERDITS = (
    "embed", "embedqa", "rerank", "guard", "safety", "content-safety",
    "topic-control", "reward", "parse", "ocr", "translate", "vision", "vlm",
    "clip", "detector", "moderation", "whisper", "tts", "stt", "image",
    "diffusion", "video", "retriever", "calibration",
)

# Motifs par role, du plus specifique au plus general. Le premier qui touche
# gagne. Ils decrivent des FAMILLES de noms, pas des versions : « nano » et
# « ultra » survivront a « nemotron-3 » comme ils ont survecu a « nemotron-2 ».
PREFERENCES: Dict[str, Tuple[str, ...]] = {
    # Fiction : un modele entraine pour ecrire, pas pour resumer. NVIDIA sert
    # « writer/palmyra-creative-122b », qui existe pour cela.
    "creatif": ("palmyra-creative", "creative", "muse", "writer/",
                "gemma-4", "-31b", "super"),
    # Le pipeline logiciel produit du code qui doit compiler.
    "code": ("codestral", "starcoder", "-coder", "code-", "codellama",
             "north-mini-code", "laguna", "granite-.*code"),
    # Structure et arbitrage : un modele qui raisonne. Son brouillon est
    # retire par « core.texte », donc il ne pollue plus le produit.
    "raisonnement": ("reasoning", "thinking", "-r1", "deepseek-v4-pro",
                     "deepseek-r"),
    # Relecture d'un livre entier : c'est le contexte qui compte.
    "long": ("lightning", "-1m", "inkling", "long", "128k", "ultra"),
    # Le meilleur disponible, pour le plan, l'edition et le controle.
    "costaud": ("ultra", "-pro", "550b", "405b", "340b", "-large", "122b",
                "120b", "90b", "-70b", "k3", "k2"),
    "standard": ("super", "flash", "-31b", "-30b", "instruct", "chat", "-it"),
    # Beaucoup d'appels courts : petit modele, gros quota.
    "rapide": ("nano", "-mini", "lite", "small", "-2.6b", "-4b", "-7b",
               "-8b", "flash"),
}


# Les modeles qui raisonnent a voix haute avant de repondre. Excellents pour
# un plan ou un arbitrage, ruineux pour le reste : leur brouillon consomme le
# plafond de jetons par minute, qui est la contrainte reelle de l'usine. Un
# « rapide » qui reflechit trois cents jetons avant de rendre un titre n'a de
# rapide que le nom.
_RAISONNEURS = ("reasoning", "thinking", "-r1", "deepseek-r")

# Les roles ou reflechir vaut ce que cela coute.
_ROLES_PENSEURS = ("raisonnement", "costaud")


def _utilisable(nom: str) -> bool:
    bas = nom.lower()
    return not any(mot in bas for mot in _INTERDITS)


def _raisonne(nom: str) -> bool:
    bas = nom.lower()
    return any(mot in bas for mot in _RAISONNEURS)


def choisir(catalogue: List[str], role: str,
            prefere: str = "") -> str:
    """Le meilleur modele du catalogue pour ce role, ou "" si aucun ne convient.

    « prefere » l'emporte s'il est encore servi : on ne change jamais un
    modele qui marche. La substitution n'existe que pour les cas ou il ne
    marche plus.
    """
    servis = [m for m in catalogue if _utilisable(m)]
    if not servis:
        return ""
    if prefere and prefere in catalogue:
        return prefere
    if role not in _ROLES_PENSEURS:
        # On les ecarte S'IL RESTE autre chose. Un catalogue qui ne sert que
        # des raisonneurs vaut mieux qu'aucun modele du tout.
        sans_brouillon = [m for m in servis if not _raisonne(m)]
        servis = sans_brouillon or servis
    for motif in PREFERENCES.get(role, ()) + PREFERENCES["standard"]:
        trouves = [m for m in servis if re.search(motif, m, re.IGNORECASE)]
        if trouves:
            # A motif egal, le nom le plus court : « gemma-4-31b-it » plutot
            # que « gemma-4-31b-it-preview-experimental ». Les variantes
            # longues sont des declinaisons, rarement le modele principal.
            return min(trouves, key=len)
    return min(servis, key=len)


# --------------------------------------------------------------------------
# Le catalogue vivant
# --------------------------------------------------------------------------

_verrou = threading.Lock()
# Catalogue en memoire pour la session : {fournisseur: (instant, [modeles])}.
_memoire: Dict[str, Tuple[float, List[str]]] = {}
# Substitutions retenues : {(fournisseur, role): modele}.
_substitutions: Dict[Tuple[str, str], str] = {}


def _cle_cache(fournisseur: str) -> str:
    return "catalogue-modeles:" + fournisseur


def _lire_cache(cle: str) -> str:
    """Lit le cache sans jamais faire tomber l'appelant.

    Ce module est interroge par « usine docteur », c'est-a-dire par la
    commande qu'on lance quand la base ne se lit plus. Laisser remonter une
    « DatabaseError » d'ici la faisait mourir exactement comme les autres — et
    ce chemin-la avait deja ete repare une fois.
    """
    try:
        return store.cache_get(cle) or ""
    except sqlite3.DatabaseError:
        return ""


def _ecrire_cache(cle: str, valeur: str, genre: str, detail: str) -> None:
    try:
        store.cache_set(cle, valeur, genre, detail)
    except sqlite3.DatabaseError:
        pass  # sans base, la substitution ne vaut que pour cette session


def catalogue(fournisseur: config.Provider,
              timeout: int = 10,
              forcer: bool = False) -> Optional[List[str]]:
    """Ce que le fournisseur declare servir, ou None si la question n'a pas pu
    etre posee.

    « None » et « liste vide » ne veulent pas dire la meme chose, et les
    confondre ferait accuser une configuration correcte : sans cle, sans
    reseau, ou chez un fournisseur qui n'expose pas « /models », on ne sait
    pas — on ne decide donc rien.
    """
    if fournisseur.local:
        # Un serveur local sert ce qu'on y a installe : la question a du sens,
        # mais son catalogue change a chaque « ollama pull ». On ne le garde
        # donc pas plus longtemps que la session.
        forcer = forcer or _memoire.get(fournisseur.name) is None
    maintenant = time.time()
    with _verrou:
        garde = _memoire.get(fournisseur.name)
        if garde and not forcer and maintenant - garde[0] < DUREE_CACHE:
            return list(garde[1])

    if not forcer:
        # Le cache sur disque survit au redemarrage du processus — ce qui
        # arrive sans arret sur un telephone.
        depuis_base = _lire_cache(_cle_cache(fournisseur.name))
        if depuis_base:
            try:
                noms = json.loads(depuis_base)
            except ValueError:
                noms = None
            if isinstance(noms, list) and noms:
                with _verrou:
                    _memoire[fournisseur.name] = (maintenant, [str(n) for n in noms])
                return [str(n) for n in noms]

    noms = interroger(fournisseur, timeout)
    if noms is None:
        return None
    with _verrou:
        _memoire[fournisseur.name] = (maintenant, list(noms))
    _ecrire_cache(_cle_cache(fournisseur.name),
                  json.dumps(noms, ensure_ascii=False), "catalogue", "modeles")
    return list(noms)


def interroger(fournisseur: config.Provider,
               timeout: int = 10) -> Optional[List[str]]:
    """Demande « /models » au fournisseur, sans cache. Rend None si on ne sait pas."""
    from . import cles as pool_cles
    from .http import HttpErreur, requete

    entetes = dict(fournisseur.extra_headers)
    if fournisseur.api_key_env:
        lot = pool_cles.pool(fournisseur.name, fournisseur.api_key_env)
        candidates = lot.disponibles() or lot.cles
        if candidates:
            entetes["Authorization"] = "Bearer {}".format(candidates[0].valeur)
        elif not fournisseur.keyless:
            return None  # sans cle, la question ne peut pas etre posee
    try:
        statut, brut = requete(fournisseur.base_url.rstrip("/") + "/models",
                               entetes=entetes, timeout=timeout)
    except (HttpErreur, OSError):
        return None
    if statut != 200:
        return None
    try:
        charge = json.loads(brut.decode("utf-8", "replace"))
    except ValueError:
        return None
    entrees = charge.get("data") if isinstance(charge, dict) else charge
    if not isinstance(entrees, list):
        return None
    noms: List[str] = []
    for entree in entrees:
        nom = entree.get("id") or entree.get("name") if isinstance(entree, dict) else entree
        if isinstance(nom, str) and nom:
            noms.append(nom)
    return noms


def substituer(fournisseur: config.Provider, role: str,
               refuse: str) -> str:
    """Trouve un remplacant au modele que le fournisseur vient de refuser.

    Rend "" quand il n'y a rien a proposer — pas de catalogue lisible, ou
    aucun modele utilisable dedans. Le routeur reprend alors son cours normal
    et signale le 404, ce qui est la bonne reponse : mieux vaut une panne
    nommee qu'un chapitre ecrit par un modele d'embeddings.
    """
    servis = catalogue(fournisseur)
    if not servis:
        return ""
    # Le modele refuse est retire d'office : le fournisseur peut le lister et
    # ne plus le servir, et on retomberait dessus indefiniment.
    restants = [m for m in servis if m != refuse]
    remplacant = choisir(restants, role)
    if not remplacant or remplacant == refuse:
        return ""
    retenir(fournisseur.name, role, remplacant)
    return remplacant


def retenir(fournisseur: str, role: str, modele: str) -> None:
    """Garde la substitution pour la session ET pour les suivantes.

    Sans memoire, chaque appel refait le meme 404, la meme interrogation du
    catalogue, et le meme choix — trois fois par chapitre.
    """
    with _verrou:
        _substitutions[(fournisseur, role)] = modele
    _ecrire_cache("substitution:{}:{}".format(fournisseur, role),
                  modele, "substitution", role)


def modele_effectif(fournisseur: config.Provider, role: str) -> str:
    """Le modele a appeler : celui configure, ou sa substitution retenue."""
    with _verrou:
        garde = _substitutions.get((fournisseur.name, role))
    if garde:
        return garde
    depuis_base = _lire_cache("substitution:{}:{}".format(
        fournisseur.name, role))
    if depuis_base:
        with _verrou:
            _substitutions[(fournisseur.name, role)] = depuis_base
        return depuis_base
    return fournisseur.model_for(role)


def substitutions() -> Dict[str, str]:
    """Ce que l'usine appelle reellement, la ou ce n'est pas ce qui est configure.

    Montre par « usine docteur » : une substitution silencieuse serait le
    genre de reparation qui fait perdre une journee au moment ou elle cesse
    de suffire.
    """
    trouvees: Dict[str, str] = {}
    # Le disque d'abord : une substitution retenue lors d'une fabrication
    # precedente doit se voir dans un nouveau processus, sinon « usine cache »
    # affirme qu'il n'y en a aucune alors que l'usine en applique trois.
    try:
        connues = store.cache_par_prefixe("substitution:")
    except sqlite3.DatabaseError:
        connues = {}
    for cle, modele in connues.items():
        morceaux = cle.split(":")
        if len(morceaux) == 3:
            trouvees["{} / {}".format(morceaux[1], morceaux[2])] = modele
    with _verrou:
        for (f, r), m in _substitutions.items():
            trouvees["{} / {}".format(f, r)] = m
    return trouvees


def oublier() -> None:
    """Vide catalogues et substitutions — en memoire ET sur le disque.

    Oublier a moitie serait pire que ne pas oublier : apres un changement de
    cle, la memoire repartirait a zero et le disque continuerait de servir le
    catalogue de l'ancien compte, sans que rien ne le signale. Les reponses du
    modele, elles, ne sont pas touchees : les jeter ferait repayer une
    fabrication entiere.
    """
    with _verrou:
        _memoire.clear()
        _substitutions.clear()
    try:
        store.cache_oublier_prefixe("catalogue-modeles:")
        store.cache_oublier_prefixe("substitution:")
    except sqlite3.DatabaseError:
        pass  # une base illisible a de toute facon tout oublie
