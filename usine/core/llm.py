"""Routeur IA multi-fournisseurs.

Tous les fournisseurs retenus exposent l'API /chat/completions d'OpenAI : un
seul adaptateur suffit. Le routeur :
  1. respecte les quotas gratuits (RPM / RPD comptes en base) ;
  2. bascule automatiquement au fournisseur suivant en cas d'echec ou de 429 ;
  3. met en cache chaque reponse (relancer une generation ne recoute rien) ;
  4. termine par l'IA locale (ollama / llama.cpp) en dernier recours.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from . import budget as budget_module
from . import cles as pool_cles
from . import config, store
from .http import HttpErreur, post_json

# Fournisseurs mis au repos apres un echec dur : nom -> timestamp de reprise
_REPOS: Dict[str, float] = {}
# Injection de test : si non nul, remplace tout appel reseau
_SIMULATEUR = None


class PlusDeFournisseur(RuntimeError):
    """Aucun fournisseur n'a pu repondre."""


@dataclass
class Reponse:
    texte: str
    fournisseur: str
    modele: str
    tokens: int = 0
    depuis_cache: bool = False
    cle: str = ""          # empreinte masquee de la cle utilisee


def definir_simulateur(fonction) -> None:
    """Branche une fonction (messages, role) -> texte, pour les tests hors-ligne."""
    global _SIMULATEUR
    _SIMULATEUR = fonction


def _cle_cache(messages: Sequence[Dict[str, str]], role: str, temperature: float) -> str:
    brut = json.dumps(
        {"m": list(messages), "r": role, "t": round(temperature, 2)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _expliquer(p: config.Provider, exc: Exception) -> str:
    """Traduit l'echec d'un serveur local en geste a faire.

    « HTTP 404 » ou « Connection refused » ne disent rien a qui vient
    d'installer Ollama sur son telephone. Ces trois pannes sont les seules
    qu'on rencontre vraiment, et chacune a une reponse d'une ligne.
    """
    texte = str(exc)
    if not p.local:
        return texte
    minuscules = texte.lower()
    if isinstance(exc, HttpErreur) and exc.statut == 404:
        return ("modele absent du serveur. Telechargez-le : {}"
                .format("ollama pull " + p.model_for("standard")
                        if p.name == "ollama"
                        else "verifiez le fichier .gguf passe a llama-server"))
    if any(mot in minuscules for mot in
           ("refused", "refusee", "unreachable", "timed out", "timeout",
            "connexion", "urlerror", "no route")):
        if "timed out" in minuscules or "timeout" in minuscules:
            return ("pas de reponse en {} s. Un modele de cette taille est "
                    "peut-etre trop lourd pour cet appareil : essayez un "
                    "modele plus petit (OLLAMA_MODEL=qwen2.5:0.5b)."
                    .format(p.timeout))
        return ("serveur injoignable sur {}. Lancez-le : {}"
                .format(p.base_url, p.signup))
    return texte


def _quota_ok(p: config.Provider) -> bool:
    if _REPOS.get(p.name, 0) > time.time():
        return False
    if p.local:
        return True
    if store.compteur_jour(p.name) >= p.rpd:
        return False
    return True


def _attente_rpm(p: config.Provider) -> float:
    """Secondes a patienter pour rester sous la limite par minute."""
    if p.local:
        return 0.0
    utilises = store.compteur_minute(p.name)
    if utilises < p.rpm:
        return 0.0
    return min(62.0, 60.0 / max(p.rpm, 1) + 1.0)


def _appel(
    p: config.Provider,
    messages: Sequence[Dict[str, str]],
    role: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    timeout: int,
    cle: Optional[pool_cles.Cle] = None,
) -> Reponse:
    modele = p.model_for(role)
    charge: Dict[str, Any] = {
        "model": modele,
        "messages": list(messages),
        "temperature": temperature,
    }
    if max_tokens:
        charge["max_tokens"] = max_tokens
    if json_mode and p.name not in ("pollinations", "llamacpp"):
        charge["response_format"] = {"type": "json_object"}

    entetes = {"Content-Type": "application/json"}
    entetes.update(p.extra_headers)
    if cle is not None and cle.valeur:
        entetes["Authorization"] = "Bearer {}".format(cle.valeur)

    url = p.base_url.rstrip("/") + "/chat/completions"
    debut = time.time()
    data = post_json(url, charge, entetes, timeout=timeout)
    latence = time.time() - debut

    choix = (data.get("choices") or [{}])[0]
    message = choix.get("message") or {}
    texte = (message.get("content") or "").strip()
    if not texte:
        raise HttpErreur(502, "reponse vide de {}".format(p.name))
    tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
    identifiant = cle.id if cle else ""
    store.enregistrer_appel(p.name, modele, True, tokens, latence, cle_id=identifiant)
    return Reponse(texte=texte, fournisseur=p.name, modele=modele, tokens=tokens,
                   cle=cle.affichage if cle else "")


def generer(
    invite: str,
    systeme: str = "",
    role: str = "standard",
    temperature: float = 0.7,
    max_tokens: int = 4000,
    json_mode: bool = False,
    cache: bool = True,
    timeout: int = 150,
    tentatives_par_fournisseur: int = 2,
    eviter: Optional[Sequence[str]] = None,
) -> Reponse:
    """Genere du texte en basculant de fournisseur en fournisseur si besoin.

    `eviter` ecarte des fournisseurs nommes. C'est ce qui permet de faire
    relire un texte par un modele different de celui qui l'a ecrit : un modele
    qui se relit lui-meme confirme ses propres erreurs au lieu de les voir.
    """
    messages: List[Dict[str, str]] = []
    if systeme:
        messages.append({"role": "system", "content": systeme})
    messages.append({"role": "user", "content": invite})

    cle_cache = _cle_cache(messages, role, temperature)
    if cache:
        garde = store.cache_get(cle_cache)
        if garde is not None:
            return Reponse(garde, "cache", role, depuis_cache=True)

    budget_module.verifier()

    if _SIMULATEUR is not None:
        texte = _SIMULATEUR(messages, role)
        # Un appel simule reste un appel : le journaliser rend le budget et les
        # statistiques verifiables sans toucher au reseau.
        store.enregistrer_appel("simulateur", role, True)
        if cache:
            store.cache_set(cle_cache, texte, "simulateur", role)
        return Reponse(texte, "simulateur", role)

    fournisseurs = config.active_providers()
    if eviter:
        exclus = {n.lower() for n in eviter}
        restants = [f for f in fournisseurs if f.name not in exclus]
        # On n'ecarte un fournisseur que s'il en reste un autre : mieux vaut une
        # relecture par le meme modele que pas de relecture du tout.
        if restants:
            fournisseurs = restants
    if not fournisseurs:
        raise PlusDeFournisseur(
            "Aucun fournisseur configure. Lancez 'usine cles' pour la marche a suivre."
        )

    erreurs: List[str] = []
    for p in fournisseurs:
        if not _quota_ok(p):
            erreurs.append("{} : quota journalier atteint ou en repos".format(p.name))
            continue

        # Un fournisseur peut detenir plusieurs cles : on les essaie toutes avant
        # de le declarer indisponible. C'est la rotation de cles.
        lot = pool_cles.pool(p.name, p.api_key_env)
        candidates: List[Optional[pool_cles.Cle]] = []
        if p.api_key_env and len(lot):
            candidates = list(lot.ordonnees(p.rpd))
            if not candidates:
                erreurs.append("{} : toutes les cles sont saturees".format(p.name))
                continue
        else:
            candidates.append(None)  # fournisseur local ou sans cle

        fournisseur_hors_jeu = False
        for cle in candidates:
            if fournisseur_hors_jeu:
                break
            pause = _attente_rpm(p)
            if pause:
                time.sleep(pause)

            for essai in range(tentatives_par_fournisseur):
                try:
                    # Le delai du fournisseur prime sur celui de l'appelant :
                    # un modele local a besoin de minutes la ou un service
                    # distant a besoin de secondes.
                    rep = _appel(p, messages, role, temperature, max_tokens,
                                 json_mode, max(timeout, p.timeout), cle)
                    if cache:
                        store.cache_set(cle_cache, rep.texte, rep.fournisseur,
                                        rep.modele)
                    return rep
                except HttpErreur as exc:
                    store.enregistrer_appel(p.name, p.model_for(role), False, 0, 0,
                                            str(exc), cle_id=cle.id if cle else "")
                    erreurs.append("{}{} : {}".format(
                        p.name, "/" + cle.affichage if cle else "",
                        _expliquer(p, exc)))

                    if exc.statut in (401, 403):
                        # Cle refusee : on ecarte la cle, pas le fournisseur.
                        if cle:
                            lot.mettre_au_repos(cle, 3600, "cle refusee")
                        else:
                            _REPOS[p.name] = time.time() + 3600
                        break
                    if exc.statut == 429:
                        if cle:
                            lot.mettre_au_repos(cle, 120, "limite de debit")
                        else:
                            _REPOS[p.name] = time.time() + 90
                        break
                    if exc.statut == 402:
                        if cle:
                            lot.mettre_au_repos(cle, 3600, "credit epuise")
                        else:
                            _REPOS[p.name] = time.time() + 1800
                        break
                    if exc.statut == 404:
                        # Modele inconnu : changer de cle n'y changerait rien.
                        _REPOS[p.name] = time.time() + 1800
                        fournisseur_hors_jeu = True
                        break
                    if not exc.temporaire:
                        break
                    time.sleep(min(8.0, 1.5 * (essai + 1)) + random.random())
                except Exception as exc:
                    store.enregistrer_appel(p.name, p.model_for(role), False, 0, 0,
                                            repr(exc), cle_id=cle.id if cle else "")
                    erreurs.append("{} : {}".format(p.name, _expliquer(p, exc)))
                    break

    raise PlusDeFournisseur(
        "Tous les fournisseurs ont echoue :\n  - " + "\n  - ".join(erreurs[-10:])
    )


# --------------------------------------------------------------------------
# Sortie structuree
# --------------------------------------------------------------------------

_BLOC = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extraire_json(texte: str) -> Any:
    """Recupere un objet JSON meme noye dans du bavardage ou un bloc markdown."""
    candidats: List[str] = []
    bloc = _BLOC.search(texte)
    if bloc:
        candidats.append(bloc.group(1).strip())
    candidats.append(texte.strip())
    for ouvrant, fermant in (("{", "}"), ("[", "]")):
        debut = texte.find(ouvrant)
        fin = texte.rfind(fermant)
        if debut != -1 and fin > debut:
            candidats.append(texte[debut : fin + 1])
    for essai in candidats:
        try:
            return json.loads(essai)
        except (json.JSONDecodeError, ValueError):
            # Tolere les virgules finales, frequentes chez les petits modeles
            nettoye = re.sub(r",(\s*[}\]])", r"\1", essai)
            try:
                return json.loads(nettoye)
            except (json.JSONDecodeError, ValueError):
                continue
    raise ValueError("JSON introuvable dans la reponse du modele")


def generer_json(
    invite: str,
    systeme: str = "",
    role: str = "standard",
    temperature: float = 0.4,
    max_tokens: int = 4000,
    essais: int = 3,
    eviter: Optional[Sequence[str]] = None,
) -> Any:
    """Comme generer(), mais garantit un objet Python decode depuis du JSON."""
    consigne = (
        "\n\nReponds UNIQUEMENT avec du JSON valide, sans texte avant ni apres,"
        " sans bloc de code markdown."
    )
    derniere = None
    for tentative in range(essais):
        rep = generer(
            invite + consigne,
            systeme=systeme,
            role=role,
            temperature=temperature + 0.1 * tentative,
            max_tokens=max_tokens,
            json_mode=True,
            cache=(tentative == 0),
            eviter=eviter,
        )
        try:
            return extraire_json(rep.texte)
        except ValueError as exc:
            derniere = exc
    raise ValueError("Impossible d'obtenir du JSON exploitable : {}".format(derniere))


def diagnostic() -> List[Dict[str, Any]]:
    """Etat de chaque fournisseur (pour 'usine docteur')."""
    lignes: List[Dict[str, Any]] = []
    for p in config.PROVIDERS:
        lignes.append(
            {
                "nom": p.name,
                "disponible": p.available(),
                "local": p.local,
                "sans_cle": p.keyless,
                "cle_env": p.api_key_env,
                "nb_cles": len(pool_cles.pool(p.name, p.api_key_env)),
                "modele": p.model_for("standard"),
                "aujourdhui": store.compteur_jour(p.name),
                "rpd": p.rpd,
                "inscription": p.signup,
                "notes": p.notes,
            }
        )
    return lignes
