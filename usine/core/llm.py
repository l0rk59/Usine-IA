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
from . import config, evenements, store
from .http import HttpErreur, post_json

# Fournisseurs mis au repos apres un echec dur : nom -> timestamp de reprise.
# Le dictionnaire est un cache ; la verite est en base, pour survivre a un
# processus tue par Android (voir _reposer et _repos_jusqu_a).
_REPOS: Dict[str, float] = {}
_REPOS_CHARGE = False
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
    # Le modele a-t-il ete coupe au plafond de jetons plutot que d'avoir fini ?
    tronquee: bool = False


def definir_simulateur(fonction) -> None:
    """Branche une fonction (messages, role) -> texte, pour les tests hors-ligne."""
    global _SIMULATEUR
    _SIMULATEUR = fonction


def _cle_cache(messages: Sequence[Dict[str, str]], role: str,
               temperature: float, max_tokens: int = 0,
               json_mode: bool = False) -> str:
    """Empreinte de ce qui determine la reponse.

    Le plafond de jetons et le mode JSON en font partie : deux appels qui ne
    different que par eux recevaient la meme entree de cache, donc le meme
    texte — un texte parfois coupe plus court que ce que le second demandait.
    """
    brut = json.dumps(
        {"m": list(messages), "r": role, "t": round(temperature, 2),
         "j": int(max_tokens or 0), "s": bool(json_mode)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _expliquer(p: config.Provider, exc: Exception, modele: str = "") -> str:
    """Traduit un echec technique en geste a faire.

    « HTTP 404 » ou « Connection refused » ne disent rien a qui vient
    d'installer Ollama sur son telephone. Ces trois pannes sont les seules
    qu'on rencontre vraiment, et chacune a une reponse d'une ligne.

    Chez un fournisseur distant, un 404 a une seule cause : le modele demande
    n'existe plus. C'est arrive pour de bon — Groq a retire ses modeles Llama
    du palier gratuit le 16 aout 2026 — et le message brut « HTTP 404 » ne
    laissait aucune chance de comprendre pourquoi le fournisseur le plus
    rapide de la liste avait cesse de servir.
    """
    texte = str(exc)
    if not p.local:
        if isinstance(exc, HttpErreur) and exc.statut == 404:
            return ("le modele « {} » n'existe plus chez {}. Les fournisseurs "
                    "retirent leurs modeles sans prevenir : verifiez avec "
                    "« usine docteur --modeles », puis corrigez "
                    "usine/core/config.py.".format(modele or p.model_for("standard"),
                                                   p.name))
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


def _charger_repos() -> None:
    """Relit en base les mises au repos d'un processus precedent."""
    global _REPOS_CHARGE
    if _REPOS_CHARGE:
        return
    _REPOS_CHARGE = True
    try:
        for (fournisseur, cle_id), fin in store.repos_actifs().items():
            if not cle_id:
                _REPOS[fournisseur] = max(_REPOS.get(fournisseur, 0.0), fin)
    except Exception:
        pass  # une base illisible ne doit pas empecher de produire


def _reposer(nom: str, secondes: float, raison: str) -> None:
    """Met un fournisseur au repos, en memoire ET en base.

    Sans la base, le repos disparaissait au premier redemarrage — c'est-a-dire
    tout le temps sur un telephone.
    """
    _REPOS[nom] = time.time() + secondes
    try:
        store.journal_cle(nom, "", raison, secondes)
    except Exception:
        pass


def _compte_pour(p: config.Provider, role: str) -> str:
    """Modele sur lequel imputer le quota, ou "" si le quota vaut pour tout.

    Google compte par modele : flash-lite garde ses mille requetes du jour
    meme quand flash a epuise ses deux cent cinquante.
    """
    return p.model_for(role) if p.quota(role).portee == "modele" else ""


# Caracteres francais par jeton. Les tokeniseurs BPE des modeles courants
# decoupent l'anglais autour de quatre caracteres par jeton, le francais un
# peu plus finement : accents, elisions et terminaisons y produisent plus de
# fragments. Trois caracteres et demi surestiment donc legerement le cout,
# et c'est le bon sens de l'erreur : sous-estimer fait tenter un appel que le
# fournisseur refusera, surestimer fait seulement choisir un autre.
CARACTERES_PAR_JETON = 3.5


def _cout_estime(messages: Sequence[Dict[str, str]], max_tokens: int,
                 p: config.Provider) -> int:
    """Jetons qu'un appel va peser, entree ET sortie comprises.

    Les plafonds par minute se comptent sur la somme des deux, et les
    fournisseurs reservent la sortie DEMANDEE, pas celle qui sera produite :
    Groq comme Cerebras demandent explicitement d'ajuster max_tokens pour
    cette raison.
    """
    caracteres = sum(len(m.get("content") or "") for m in messages)
    entree = int(caracteres / CARACTERES_PAR_JETON) + 8 * len(messages)
    sortie = min(max_tokens, p.max_sortie) if max_tokens else p.max_sortie
    return entree + sortie


def _au_repos(p: config.Provider) -> bool:
    """Le fournisseur entier est-il en repos ? Cela ne depend d'aucune cle."""
    _charger_repos()
    return _REPOS.get(p.name, 0) > time.time()


def _quota_ok(p: config.Provider, role: str = "standard",
              cle_id: str = "") -> bool:
    """Ce quota est-il encore ouvert pour CETTE cle ?

    Les plafonds d'un fournisseur s'appliquent a un compte, donc a une cle.
    Les compter pour tout le fournisseur additionnait les consommations de
    cles independantes : deux cles donnaient un seul quota, et le pool — dont
    toute la raison d'etre est de ne jamais s'arreter faute de quota — ne
    multipliait rien. Mesure : mille appels sur la premiere cle de Groq
    suffisaient a declarer le fournisseur epuise, la seconde n'ayant servi a
    rien.

    Le cas connu qui va dans l'autre sens est Google, qui compte par PROJET :
    deux cles d'un meme projet partagent leur quota, et compter par cle y est
    optimiste. Le prix en est un 429, que le routeur sait deja traiter en
    mettant la cle au repos — alors qu'un comptage trop prudent rend le pool
    entierement inutile, ce qui est pire.
    """
    if _au_repos(p):
        return False
    if p.local:
        return True
    q = p.quota(role)
    modele = _compte_pour(p, role)
    if store.compteur_jour(p.name, modele, cle_id) >= q.rpd:
        return False
    # Plusieurs paliers gratuits s'epuisent en JETONS bien avant de s'epuiser
    # en requetes : Groq n'en accorde que deux cent mille par jour, de quoi
    # ecrire un livre et pas deux. Ne compter que les requetes revenait a
    # decouvrir la limite sous forme de 429 en pleine fabrication.
    if q.tpd and store.jetons_jour(p.name, modele, cle_id) >= q.tpd:
        return False
    return True


def _attente(p: config.Provider, role: str, cout: int,
             cle_id: str = "") -> Optional[float]:
    """Secondes a patienter pour rester sous les plafonds par minute.

    Rend None quand aucune attente ne suffira : la demande pese a elle seule
    plus que le budget d'une minute entiere chez ce fournisseur. Attendre
    serait alors une facon lente d'aller chercher un 429 — le routeur passe
    au suivant, qui lui saura la servir. C'est exactement le cas d'un
    chapitre confie a Groq : huit mille jetons de budget par minute, et une
    demande qui en pese onze mille.
    """
    if p.local:
        return 0.0
    q = p.quota(role)
    modele = _compte_pour(p, role)
    attente = 0.0
    if store.compteur_minute(p.name, modele, cle_id) >= q.rpm:
        attente = min(62.0, 60.0 / max(q.rpm, 1) + 1.0)
    if q.tpm:
        if cout > q.tpm:
            return None
        utilises, plus_ancien = store.jetons_minute(p.name, modele, cle_id)
        if utilises + cout > q.tpm and plus_ancien:
            # La fenetre glisse : la place se libere quand le plus vieil
            # appel en sort, pas a la minute ronde.
            attente = max(attente, min(62.0, 61.0 - (time.time() - plus_ancien)))
    return attente


def _laisser_passer(p: config.Provider, role: str, cout: int,
                    cle_id: str = "") -> bool:
    """Attend si besoin, et dit si cette cle peut servir la demande."""
    pause = _attente(p, role, cout, cle_id)
    if pause is None:
        return False
    if pause > 0:
        time.sleep(pause)
        pause = _attente(p, role, cout, cle_id)
    return bool(pause == 0.0)


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
        # Demander plus que ce que le fournisseur sait emettre ne produit pas
        # plus : selon les services, une erreur ou un silence.
        charge["max_tokens"] = min(max_tokens, p.max_sortie)
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
    # « length » signifie : le modele n'avait pas fini, il a ete coupe au
    # plafond. Ne pas le lire faisait passer un chapitre tranche au milieu
    # d'une phrase pour un chapitre termine — le defaut le plus couteux du
    # routeur, parce qu'il est invisible partout en aval.
    tronquee = str(choix.get("finish_reason") or "").lower() in ("length",
                                                                "max_tokens")
    identifiant = cle.id if cle else ""
    store.enregistrer_appel(p.name, modele, True, tokens, latence, cle_id=identifiant)
    return Reponse(texte=texte, fournisseur=p.name, modele=modele, tokens=tokens,
                   cle=cle.affichage if cle else "", tronquee=tronquee)


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

    cle_cache = _cle_cache(messages, role, temperature, max_tokens, json_mode)
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
        # Le repos vaut pour le fournisseur entier ; le quota, lui, se
        # verifie cle par cle plus bas — c'est tout l'interet d'en avoir
        # plusieurs.
        if _au_repos(p):
            erreurs.append("{} : en repos".format(p.name))
            continue
        cout = _cout_estime(messages, max_tokens, p)

        # Un fournisseur peut detenir plusieurs cles : on les essaie toutes avant
        # de le declarer indisponible. C'est la rotation de cles.
        lot = pool_cles.pool(p.name, p.api_key_env)
        candidates: List[Optional[pool_cles.Cle]] = []
        if p.api_key_env and len(lot):
            candidates = list(lot.ordonnees(p.quota(role).rpd,
                                            _compte_pour(p, role)))
            if not candidates:
                erreurs.append("{} : toutes les cles sont saturees".format(p.name))
                continue
        else:
            candidates.append(None)  # fournisseur local ou sans cle

        fournisseur_hors_jeu = False
        for cle in candidates:
            if fournisseur_hors_jeu:
                break
            identifiant_cle = cle.id if cle else ""
            if not _quota_ok(p, role, identifiant_cle):
                erreurs.append("{}{} : quota du jour atteint".format(
                    p.name, "/" + cle.affichage if cle else ""))
                continue
            if not _laisser_passer(p, role, cout, identifiant_cle):
                erreurs.append(
                    "{} : {} jetons demandes, budget par minute insuffisant"
                    .format(p.name, cout))
                break

            for essai in range(tentatives_par_fournisseur):
                try:
                    # Le delai du fournisseur prime sur celui de l'appelant :
                    # un modele local a besoin de minutes la ou un service
                    # distant a besoin de secondes.
                    rep = _appel(p, messages, role, temperature, max_tokens,
                                 json_mode, max(timeout, p.timeout), cle)
                    if rep.tronquee:
                        evenements.publier(
                            "tronquee", fournisseur=rep.fournisseur,
                            modele=rep.modele,
                            plafond=min(max_tokens, p.max_sortie))
                    if cache and not rep.tronquee:
                        store.cache_set(cle_cache, rep.texte, rep.fournisseur,
                                        rep.modele)
                    return rep
                except HttpErreur as exc:
                    store.enregistrer_appel(p.name, p.model_for(role), False, 0, 0,
                                            str(exc), cle_id=cle.id if cle else "")
                    erreurs.append("{}{} : {}".format(
                        p.name, "/" + cle.affichage if cle else "",
                        _expliquer(p, exc, p.model_for(role))))

                    if exc.statut in (401, 403):
                        # Cle refusee : on ecarte la cle, pas le fournisseur.
                        if cle:
                            lot.mettre_au_repos(cle, 3600, "cle refusee")
                        else:
                            _reposer(p.name, 3600, "cle refusee")
                        break
                    if exc.statut == 429:
                        # Le service dit lui-meme combien de temps attendre :
                        # l'ecouter evite d'attendre dix minutes pour cinq
                        # secondes, ou de revenir trop tot et de reprendre un
                        # 429 — ce qui, lui, consomme du quota.
                        demande = exc.patienter()
                        if cle:
                            lot.mettre_au_repos(cle, demande or 120,
                                                "limite de debit")
                        else:
                            _reposer(p.name, demande or 90, "limite de debit")
                        break
                    if exc.statut == 402:
                        if cle:
                            lot.mettre_au_repos(cle, 3600, "credit epuise")
                        else:
                            _reposer(p.name, 1800, "credit epuise")
                        break
                    if exc.statut == 404:
                        # Modele inconnu : changer de cle n'y changerait rien.
                        _reposer(p.name, 1800, "modele inconnu")
                        fournisseur_hors_jeu = True
                        break
                    if not exc.temporaire:
                        break
                    time.sleep(min(8.0, 1.5 * (essai + 1)) + random.random())
                except Exception as exc:
                    store.enregistrer_appel(p.name, p.model_for(role), False, 0, 0,
                                            repr(exc), cle_id=cle.id if cle else "")
                    erreurs.append("{} : {}".format(
                        p.name, _expliquer(p, exc, p.model_for(role))))
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
    avec_fournisseur: bool = False,
) -> Any:
    """Comme generer(), mais garantit un objet Python decode depuis du JSON.

    « avec_fournisseur » rend (objet, nom du fournisseur) : c'est ce qui
    permet de verifier qu'une relecture a bien eu lieu sur un autre modele
    que celui qui a ecrit.
    """
    consigne = (
        "\n\nReponds UNIQUEMENT avec du JSON valide, sans texte avant ni apres,"
        " sans bloc de code markdown."
    )
    derniere = None
    # Un fournisseur qui repond en prose a une consigne « JSON uniquement »
    # recommencera : c'est presque toujours un modele trop petit pour tenir
    # un format. Reessayer chez lui brulait trois appels pour rien, puis tuait
    # la production — alors que « generer » sait deja ecarter un fournisseur,
    # et qu'il en reste neuf autres. On l'ecarte donc au fur et a mesure.
    ecartes = list(eviter or [])
    tentes: List[str] = []
    for tentative in range(essais):
        rep = generer(
            invite + consigne,
            systeme=systeme,
            role=role,
            temperature=temperature + 0.1 * tentative,
            max_tokens=max_tokens,
            json_mode=True,
            cache=(tentative == 0),
            eviter=ecartes,
        )
        try:
            decode = extraire_json(rep.texte)
        except ValueError as exc:
            derniere = exc
            if rep.fournisseur not in tentes:
                tentes.append(rep.fournisseur)
            if rep.fournisseur not in ecartes:
                ecartes.append(rep.fournisseur)
            continue
        return (decode, rep.fournisseur) if avec_fournisseur else decode
    # Le message dit quoi faire, pas seulement ce qui a echoue : « JSON
    # introuvable » n'apprend rien a qui produit depuis un telephone.
    raise ValueError(
        "Aucun modele n'a su repondre en JSON apres {} essais ({}). C'est "
        "presque toujours un modele trop petit pour tenir un format : "
        "essayez un autre fournisseur, ou un modele plus grand si vous etes "
        "en IA locale. Detail : {}".format(
            essais, ", ".join(tentes) or "aucun fournisseur", derniere))


def diagnostic() -> List[Dict[str, Any]]:
    """Etat de chaque fournisseur (pour 'usine docteur')."""
    lignes: List[Dict[str, Any]] = []
    for p in config.PROVIDERS:
        q = p.quota("standard")
        modele = _compte_pour(p, "standard")
        lignes.append(
            {
                "nom": p.name,
                "disponible": p.available(),
                "local": p.local,
                "sans_cle": p.keyless,
                "cle_env": p.api_key_env,
                "nb_cles": len(pool_cles.pool(p.name, p.api_key_env)),
                "modele": p.model_for("standard"),
                "aujourdhui": store.compteur_jour(p.name, modele),
                "rpd": q.rpd,
                "rpm": q.rpm,
                # Les plafonds en jetons sont ceux qui arretent vraiment une
                # fabrication : les afficher evite de chercher la cause
                # ailleurs quand le fournisseur le plus rapide se tait.
                "tpm": q.tpm,
                "tpd": q.tpd,
                "jetons_aujourdhui": store.jetons_jour(p.name, modele),
                "inscription": p.signup,
                "notes": p.notes,
            }
        )
    return lignes
