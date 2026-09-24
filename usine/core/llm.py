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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import budget as budget_module
from . import cles as pool_cles
from . import modeles as module_modeles
from . import texte as module_texte
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


# Ce qu'un fournisseur repond quand l'identifiant de modele ne lui dit rien.
# Aucun ne le dit de la meme facon, et surtout : aucun ne s'accorde sur le
# CODE. Mesure du 14/09/2026, en rejouant les quatre formes connues contre le
# routeur : seul un 404 declenchait la substitution. Groq et Mistral rendent
# 400, Cerebras 422 — pour eux, un identifiant perime mettait le fournisseur
# entier au repos une demi-heure, sans substitution et sans un mot. Trois
# fournisseurs sur onze ne pouvaient donc PAS se remettre d'un identifiant
# vieilli, alors que la cle etait bonne et que le catalogue contenait de quoi
# le remplacer.
#
# C'est la deuxieme des trois regles du depot, dans sa forme la plus nue : ne
# pas croire le code de retour, lire le contenu.
_AVEUX_DE_MODELE_INCONNU = (
    "model_not_found", "model not found", "does not exist", "n'existe pas",
    "invalid model", "modele inconnu", "unknown model", "invalid_model",
    "no such model", "model is not available", "unsupported model",
)


def _service_ferme(exc: Exception) -> bool:
    """Le fournisseur a-t-il ete retire, plutot que d'etre en panne ?

    HTTP 410 veut dire « parti, et ne reviendra pas » — c'est la seule
    reponse HTTP qui le dise. La distinguer d'un 404 ou d'un 503 change le
    geste a faire : il n'y a rien a reparer, il faut arreter de compter
    dessus.
    """
    if not isinstance(exc, HttpErreur):
        return False
    if exc.statut == 410:
        return True
    return "retirement" in (exc.corps or "").lower()


def _modele_inconnu(exc: Exception) -> bool:
    """Le fournisseur dit-il que l'identifiant de modele ne lui dit rien ?

    Un 404 distant n'a pas d'autre cause, on le prend tel quel. Au-dela, on
    lit le corps — et seulement pour les codes qui portent une demande mal
    formee (4xx). Un 500 ou un 503 qui contiendrait ces mots par accident
    parle d'une panne du service, pas d'un identifiant : substituer alors
    changerait de modele pour rien et masquerait l'incident.

    Ce controle rate un defaut plutot que d'en inventer un : un fournisseur
    qui refuserait un modele sans le dire dans le corps ni rendre 404 passe
    au travers, et le routeur reprend son cours normal.
    """
    if not isinstance(exc, HttpErreur):
        return False
    if exc.statut == 404:
        return True
    if not 400 <= exc.statut < 500:
        return False
    corps = (exc.corps or "").lower()
    return any(aveu in corps for aveu in _AVEUX_DE_MODELE_INCONNU)


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
        if _service_ferme(exc):
            # Un 410 n'est pas une panne : c'est un service qui a ete retire.
            # Journal d'un utilisateur, le 15/09/2026 : GitHub Models rendait
            # « HTTP 410 : Gone », et le corps disait
            # « github_models_retirement_brownout ». Le message brut donnait a
            # chercher une cle ou un identifiant de modele, alors qu'il n'y
            # avait rien a corriger — le service ferme.
            return ("{} ne sert plus : le service a ete retire par son "
                    "editeur. Ce n'est ni votre cle ni votre configuration. "
                    "Retirez-le de usine/core/config.py, ou laissez l'usine "
                    "passer au suivant.".format(p.name))
        if _modele_inconnu(exc):
            return ("le modele « {} » n'existe plus chez {}. Les fournisseurs "
                    "retirent leurs modeles sans prevenir : verifiez avec "
                    "« usine docteur --modeles », puis corrigez "
                    "usine/core/config.py.".format(modele or p.model_for("standard"),
                                                   p.name))
        # Les trois statuts qui disent quoi faire, et que « HTTP 401 :
        # Unauthorized » ne disait pas : la cle, le debit, le credit.
        statut = getattr(exc, "statut", None)
        if statut in (401, 403):
            return "cle refusee (HTTP {}) : verifiez {} dans .env".format(
                statut, p.api_key_env or "la cle")
        if statut == 429:
            return "limite de debit atteinte (HTTP 429)"
        if statut == 402:
            return "credit epuise (HTTP 402)"
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


def _connexion_refusee(exc: BaseException) -> bool:
    """Rien n'ecoute a cette adresse. Ce n'est pas une reponse illisible.

    urllib enveloppe le refus : URLError(reason=ConnectionRefusedError). On
    descend la chaine des causes plutot que de lire le message, qui change
    selon le systeme et la langue.
    """
    vu: Optional[BaseException] = exc
    for _ in range(5):
        if vu is None:
            return False
        if isinstance(vu, ConnectionRefusedError):
            return True
        vu = (getattr(vu, "reason", None) if isinstance(
            getattr(vu, "reason", None), BaseException) else None) \
            or vu.__cause__ or vu.__context__
    return False


def _heure(ts: float) -> str:
    """« 14:32 » aujourd'hui, « le 25/09 a 14:32 » au-dela."""
    local = time.localtime(ts)
    if time.strftime("%Y-%m-%d", local) == time.strftime("%Y-%m-%d"):
        return time.strftime("%H:%M", local)
    return time.strftime("le %d/%m a %H:%M", local)


class _Bilan:
    """Ce qu'on dit quand personne n'a repondu : par fournisseur, pas par essai.

    Mesure du 24/09/2026, huit fournisseurs actifs, chacun en panne a sa
    facon. Le message gardait les DIX DERNIERES lignes d'une liste qui en
    avait onze — une par essai. Groq, le premier essaye, avait disparu ;
    mistral, openrouter et pollinations apparaissaient deux fois ; « cerebras :
    en repos » ne disait ni jusqu'a quand ni pourquoi ; une cle Gemini refusee
    se lisait « HTTP 401 : Unauthorized » ; et les trois fournisseurs sans cle
    n'etaient nommes nulle part. C'est pourtant le message qu'on lit au moment
    precis ou il faut decider quoi faire.
    """

    def __init__(self) -> None:
        self.essayes: Dict[str, List[str]] = {}
        self.ecartes: Dict[str, str] = {}

    def essai(self, nom: str, texte: str) -> None:
        self.essayes.setdefault(nom, []).append(texte)
        self.ecartes.pop(nom, None)

    def ecarte(self, nom: str, texte: str) -> None:
        # Une cle ecartee puis une autre essayee : le fournisseur a ete
        # essaye, c'est ce qui compte pour qui lit.
        if nom not in self.essayes:
            self.ecartes.setdefault(nom, texte)

    def _repos(self, p: config.Provider) -> str:
        """« au repos jusqu'a 14:32 (limite de debit) », ou rien."""
        fin, raison = 0.0, ""
        if _au_repos(p):
            fin = _REPOS[p.name]
            try:
                raison = store.raison_du_repos(p.name)
            except Exception:
                raison = ""   # base illisible : l'heure suffit
        else:
            lot = pool_cles.pool(p.name, p.api_key_env)
            fins = [c.repos_jusqu_a for c in lot.cles if not c.disponible()]
            if fins and len(fins) == len(lot.cles):
                fin = min(fins)
        if not fin:
            return ""
        return "au repos jusqu'a {}{}".format(
            _heure(fin), " ({})".format(raison) if raison else "")

    def message(self) -> str:
        lignes = ["Aucun fournisseur n'a pu repondre."]
        if self.essayes:
            lignes.append("  Essayes :")
            for nom, textes in self.essayes.items():
                p = config.PROVIDERS_BY_NAME.get(nom)
                vus: List[str] = []
                for texte in textes:
                    if texte not in vus:
                        vus.append(texte)
                ligne = "    - {} : {}".format(nom, " ; ".join(vus[-2:]))
                if len(textes) > 1:
                    ligne += " ({} essais)".format(len(textes))
                repos = self._repos(p) if p else ""
                if repos:
                    ligne += " — " + repos
                lignes.append(ligne)
        if self.ecartes:
            lignes.append("  Pas essayes :")
            for nom, texte in self.ecartes.items():
                p = config.PROVIDERS_BY_NAME.get(nom)
                repos = self._repos(p) if p else ""
                lignes.append("    - {} : {}".format(nom, repos or texte))
        sans_cle = [p.name for p in config.active_providers(include_unavailable=True)
                    if not p.available()]
        if sans_cle:
            lignes.append("  Sans cle : " + ", ".join(sans_cle))
        retour = _premier_retour_connu()
        if retour:
            lignes.append("  Le premier devrait rouvrir vers {}.".format(
                _heure(retour)))
        return "\n".join(lignes)


def _patienter(secondes: float) -> None:
    """Attend par tranches d'une seconde, pour ne pas retarder un Ctrl+C.

    Un « time.sleep(8) » d'un bloc fait attendre huit secondes a qui veut
    arreter la production. Sur un telephone, l'utilisateur tue alors le
    processus a la main.
    """
    fin = time.time() + max(0.0, secondes)
    while time.time() < fin:
        time.sleep(min(1.0, fin - time.time()))


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
    # Le modele effectif, sinon une substitution ferait compter le quota sur
    # un identifiant que plus personne n'appelle — et le vrai passerait sans
    # plafond.
    return (module_modeles.modele_effectif(p, role)
            if p.quota(role).portee == "modele" else "")


# --------------------------------------------------------------------------
# Combien de jetons pese du francais
#
# Deux estimateurs coexistaient et se contredisaient : celui qui fixe le
# plafond de sortie comptait 2,6 jetons par mot, celui qui pese une demande
# avant de l'envoyer comptait 3,5 caracteres par jeton. Sur mille mots de
# francais, l'un annoncait 2 600 jetons et l'autre 1 598 — un facteur 1,63,
# et une contradiction que personne ne pouvait voir puisque les deux vivaient
# dans des modules differents.
#
# MESURE : 5,59 caracteres par mot, espace compris, sur les 27 375 mots de
# francais de docs/. C'est le seul des deux chiffres qu'on puisse mesurer ici
# — le second demanderait le tokeniseur du modele, qu'on n'a pas.
#
# CHOIX : le ratio jetons-par-mot fait foi, et le ratio par caractere en
# decoule. Aligner dans l'autre sens ferait demander MOINS de jetons de
# sortie, donc des textes coupes ; aligner dans ce sens-ci ne fait qu'ecarter
# un fournisseur un peu plus tot. Surestimer coute une bascule, sous-estimer
# coute un 429 ou une phrase tranchee.
CARACTERES_PAR_MOT = 5.59
JETONS_PAR_MOT = 2.6
CARACTERES_PAR_JETON = CARACTERES_PAR_MOT / JETONS_PAR_MOT


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


def prochaine_ouverture(role: str = "standard") -> Optional[float]:
    """Secondes avant qu'un fournisseur puisse servir ce role.

    0 : il y en a un des maintenant. None : aucun ne le pourra sans un geste
    de l'utilisateur — pas de cle, et aucun serveur local qui ecoute.

    Rien n'est devine : ce sont les repos que le routeur a lui-meme poses,
    par fournisseur et par cle, et les quotas du jour, qui repartent a minuit
    UTC comme le compteur de la base (« store._jour »). Un serveur local n'a
    ni repos ni quota : il ecoute ou il n'ecoute pas, et on le lui demande.

    Ce que cela ne sait pas voir : un reseau coupe, un credit epuise sans
    repos pose. Le fournisseur y parait ouvert ; l'appelant doit donc garder
    une attente minimale, et ne pas prendre « 0 » pour une promesse.
    """
    ouvert, ouvertures = _ouvertures_connues(role)
    if ouvert:
        return 0.0
    locaux = [p.name for p in config.active_providers() if p.local]
    if locaux:
        from . import diagnostic

        if set(locaux) & set(diagnostic.locaux_actifs(timeout=3)):
            return 0.0
    if not ouvertures:
        return None
    return max(0.0, min(ouvertures) - time.time())


def _ouvertures_connues(role: str = "standard") -> Tuple[bool, List[float]]:
    """(un distant est ouvert maintenant, dates de reouverture connues).

    Sans rien sonder : ce sont les repos et les quotas que le routeur tient
    deja. Les serveurs locaux n'y sont pas — il faut leur demander.
    """
    maintenant = time.time()
    minuit_utc = (int(maintenant // 86400) + 1) * 86400.0
    ouvertures: List[float] = []
    for p in config.active_providers():
        if p.local:
            continue
        if _au_repos(p):
            ouvertures.append(_REPOS[p.name])
            continue
        lot = pool_cles.pool(p.name, p.api_key_env)
        if p.api_key_env and len(lot):
            for cle in lot.cles:
                if not cle.disponible(maintenant):
                    ouvertures.append(cle.repos_jusqu_a)
                elif _quota_ok(p, role, cle.id):
                    return True, ouvertures
                else:
                    ouvertures.append(minuit_utc)
        elif _quota_ok(p, role):
            return True, ouvertures
        else:
            ouvertures.append(minuit_utc)
    return False, ouvertures


def _premier_retour_connu(role: str = "standard") -> Optional[float]:
    """L'heure a laquelle le premier distant rouvrira, si elle est connue.

    None quand un distant parait deja ouvert : il vient d'echouer pour une
    raison passagere (reseau, 503), et annoncer une heure serait inventer.
    """
    ouvert, ouvertures = _ouvertures_connues(role)
    if ouvert or not ouvertures:
        return None
    return min(ouvertures)


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
        # Jusqu'a soixante-deux secondes : c'est la plus longue attente de
        # l'usine, et elle etait d'un seul bloc. Un Ctrl+C attendait donc une
        # minute entiere avant d'etre entendu, et sur un telephone
        # l'utilisateur tue le processus a la main bien avant — en laissant la
        # base dans l'etat qu'on imagine.
        _patienter(pause)
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
    # Le modele EFFECTIF, pas celui qui est ecrit dans config.py : un
    # identifiant retire du catalogue a ete remplace par son equivalent, une
    # fois, et la substitution vaut pour la suite.
    modele = module_modeles.modele_effectif(p, role)
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

    entetes = config.entetes_appel(
        p, cle.valeur if cle is not None else "")

    url = p.base_url.rstrip("/") + "/chat/completions"
    debut = time.time()
    data = post_json(url, charge, entetes, timeout=timeout)
    latence = time.time() - debut

    choix = (data.get("choices") or [{}])[0]
    message = choix.get("message") or {}
    brut = (message.get("content") or "").strip()

    # On assainit AVANT tout le reste. Un modele de raisonnement rend son
    # brouillon entre « <think> » et « </think> » : sans ce passage, le
    # brouillon entrait dans le chapitre, etait note par le controle qualite,
    # mis en page dans le PDF, et lu par l'acheteur. Le faire ici plutot que
    # dans un pipeline evite d'avoir a se souvenir de le faire dix fois.
    texte = module_texte.assainir(brut)
    if not texte:
        raise HttpErreur(502, "reponse vide de {}".format(p.name))

    # Puis on lit ce que le service a VRAIMENT repondu. Mesure du 13/09/2026 :
    # pollinations rend HTTP 200, finish_reason « stop », usage renseigne — et
    # pour contenu « The API key ... has reached its budget ». Tous les signaux
    # disent « reponse valide ». Le routeur l'acceptait donc, la mettait en
    # cache, et l'ecrivait dans un chapitre : un quota epuise qui ne ressemble
    # pas a un quota epuise, et une usine qui ne bascule pas puisque rien n'a
    # echoue. On leve, et le fournisseur sort du jeu comme pour un vrai 402.
    refus = module_texte.refus_deguise(texte, attend_francais=not json_mode)
    if refus:
        statut = 402 if module_texte.ressemble_a_un_quota(texte) else 503
        raise HttpErreur(statut, "{} : {}".format(p.name, refus),
                         corps=texte[:300])
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

    bilan = _Bilan()
    for p in fournisseurs:
        # Le repos vaut pour le fournisseur entier ; le quota, lui, se
        # verifie cle par cle plus bas — c'est tout l'interet d'en avoir
        # plusieurs.
        if _au_repos(p):
            bilan.ecarte(p.name, "en repos")
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
                bilan.ecarte(p.name, "toutes les cles sont saturees")
                continue
        else:
            candidates.append(None)  # fournisseur local ou sans cle

        fournisseur_hors_jeu = False
        for cle in candidates:
            if fournisseur_hors_jeu:
                break
            identifiant_cle = cle.id if cle else ""
            if not _quota_ok(p, role, identifiant_cle):
                bilan.ecarte(p.name, "quota du jour atteint — il repart a "
                             "{} (minuit UTC)".format(_heure(
                                 (int(time.time() // 86400) + 1) * 86400.0)))
                continue
            if not _laisser_passer(p, role, cout, identifiant_cle):
                bilan.ecarte(p.name, "{} jetons demandes, budget par minute "
                                     "insuffisant".format(cout))
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
                    store.enregistrer_appel(p.name,
                                            module_modeles.modele_effectif(p, role),
                                            False, 0, 0,
                                            str(exc), cle_id=cle.id if cle else "")
                    bilan.essai(p.name, _expliquer(
                        p, exc, module_modeles.modele_effectif(p, role)))

                    if _service_ferme(exc):
                        # Le seul echec vraiment definitif du lot, et le seul
                        # qui n'avait aucun repos : un service retire repondait
                        # « retire » a chaque bascule, sur chaque scene, pour
                        # toujours. Journal du 15/09/2026 puis du 16/09/2026,
                        # meme fournisseur, meme reponse — deux observations,
                        # un jour d'ecart.
                        #
                        # Vingt-quatre heures et non « pour toujours » : une
                        # fermeture progressive peut se reouvrir, et l'usine
                        # n'a pas a trancher a la place de l'editeur. Ce qu'elle
                        # peut trancher, c'est qu'un service qui se declare
                        # retire ne reviendra pas dans l'heure.
                        _reposer(p.name, 86400, "service retire")
                        break
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
                    if _modele_inconnu(exc):
                        # Modele inconnu. Avant de mettre le fournisseur au
                        # repos une demi-heure, on lui demande ce qu'il sert.
                        #
                        # Mesure du 13/09/2026 : les deux modeles NVIDIA
                        # configures ne figuraient plus dans les 82 servis.
                        # Chaque appel rendait donc 404, NVIDIA passait au
                        # repos, et une cle valide ne servait a rien sans que
                        # rien ne le dise. Un catalogue de fournisseur bouge
                        # toutes les quelques semaines : recopier le bon
                        # identifiant reparait la panne du jour, pas la
                        # suivante.
                        refuse = module_modeles.modele_effectif(p, role)
                        remplacant = module_modeles.substituer(p, role, refuse)
                        if remplacant:
                            bilan.essai(p.name, "« {} » n'est plus servi, "
                                        "l'usine passe a « {} »".format(
                                            refuse, remplacant))
                            evenements.publier(
                                "substitution", fournisseur=p.name, role=role,
                                avant=refuse, apres=remplacant)
                            continue
                        _reposer(p.name, 1800, "modele inconnu")
                        fournisseur_hors_jeu = True
                        break
                    if not exc.temporaire:
                        break
                    # Sauf un serveur LOCAL qui refuse la connexion. « _appel »
                    # l'enveloppe en « HTTP 0 : reseau indisponible », marque
                    # temporaire — ce qui est juste pour un service distant
                    # (sur un telephone, passer du wifi a la 4G coupe vraiment
                    # quelques secondes) et faux pour 127.0.0.1 : rien n'ecoute
                    # sur ce port, et rien n'y ecoutera 1,5 seconde plus tard.
                    # Seul l'utilisateur peut lancer ollama.
                    #
                    # Mesure du 23/09/2026 : onze secondes perdues a CHAQUE
                    # appel, deux essais par serveur eteint, jamais de repos —
                    # des que les services distants etaient epuises, c'est-a-
                    # dire exactement quand on a besoin du repli local.
                    #
                    # Pas de repos non plus : un refus est instantane, le
                    # redemander a l'appel suivant ne coute rien, et c'est ce
                    # qui permet de reprendre ollama a la seconde ou on le lance.
                    if p.local and _connexion_refusee(exc):
                        break
                    _patienter(min(8.0, 1.5 * (essai + 1)) + random.random())
                except Exception as exc:
                    store.enregistrer_appel(p.name,
                                            module_modeles.modele_effectif(p, role),
                                            False, 0, 0,
                                            repr(exc), cle_id=cle.id if cle else "")
                    bilan.essai(p.name, _expliquer(
                        p, exc, module_modeles.modele_effectif(p, role)))
                    # Une exception qui n'est pas une « HttpErreur » veut dire,
                    # en pratique, qu'on n'a pas su LIRE la reponse : un JSON
                    # tronque par une coupure, un corps vide, une structure
                    # inattendue. C'est transitoire — le meme modele redemande
                    # rend en general quelque chose de lisible.
                    #
                    # Mesure du 15/09/2026 : ce « break » etait sec. Une
                    # « HttpErreur » temporaire valait deux essais et six
                    # secondes d'attente ; une reponse illisible valait UN
                    # essai et zero seconde, et le fournisseur etait abandonne.
                    # Les deux pannes se ressemblent pourtant du point de vue
                    # de l'usine : le service n'a rien donne d'exploitable.
                    if essai == tentatives_par_fournisseur - 1:
                        break
                    _patienter(min(8.0, 1.5 * (essai + 1)) + random.random())

    raise PlusDeFournisseur(bilan.message())


# --------------------------------------------------------------------------
# Sortie structuree
# --------------------------------------------------------------------------

_BLOC = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


# Jusqu'ou le plafond d'une demande JSON peut grandir quand la reponse revient
# coupee. C'est le plafond de sortie le plus large qu'un fournisseur du
# catalogue accepte (« Provider.max_sortie »), et le routeur le ramene de
# toute facon a ce que le fournisseur choisi sait reellement emettre : monter
# plus haut ne produirait pas plus, cela produirait une erreur chez certains
# et un silence chez d'autres.
PLAFOND_RELANCE = max(p.max_sortie for p in config.PROVIDERS)


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
    cache: bool = True,
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
    # Le plafond peut GRANDIR en cours de route, et c'est ce qui manquait.
    # Quand une reponse revient coupee, le JSON est incomplet donc illisible —
    # et l'ancienne version en concluait que le fournisseur ne savait pas
    # tenir un format, l'ecartait, et recommencait AU MEME PLAFOND chez le
    # suivant. Trois fournisseurs brules pour une limite que nous avions
    # posee nous-memes.
    #
    # « nouvelle._grille_ou_retente » avait deja trouve la bonne reponse pour
    # un seul appel : ne pas inventer un plafond plus gros et esperer, mais
    # lire ce que le routeur mesure DEJA — « finish_reason: length » — et
    # redemander avec de la place. Ce qui valait pour la grille de beats vaut
    # pour les quarante autres appels JSON du depot.
    plafond = max_tokens
    for tentative in range(essais):
        rep = generer(
            invite + consigne,
            systeme=systeme,
            role=role,
            temperature=temperature + 0.1 * tentative,
            max_tokens=plafond,
            json_mode=True,
            # La premiere tentative seule peut lire le cache : une reponse
            # illisible relue depuis le cache le resterait a chaque essai.
            # Et un appelant qui refuse le cache le refuse pour toutes.
            cache=cache and tentative == 0,
            eviter=ecartes,
        )
        try:
            decode = extraire_json(rep.texte)
        except ValueError as exc:
            derniere = exc
            if rep.fournisseur not in tentes:
                tentes.append(rep.fournisseur)
            # Coupee au plafond : la faute est a NOUS, pas au fournisseur. On
            # lui redonne sa chance avec de la place, une seule fois — si le
            # double ne suffit pas, c'est autre chose, et le traitement
            # ordinaire reprend.
            if rep.tronquee and plafond < PLAFOND_RELANCE:
                plafond = min(PLAFOND_RELANCE, plafond * 2)
                continue
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


def essai_direct(p: config.Provider, modele: str, timeout: int = 30,
                 observe: Optional[Dict[str, Any]] = None) -> str:
    """Un appel minimal a UN modele nomme, sans routage ni cache.

    Le routeur existe pour ne jamais s'arreter : il bascule, substitue,
    patiente, reessaie. C'est exactement ce qu'il ne faut pas ici — on veut
    savoir si CE modele-la repond, et une bascule silencieuse repondrait a la
    place d'un autre. D'ou un chemin separe, volontairement bete.

    Il passe tout de meme par « _reponse », qui lit le CONTENU : un service
    peut rendre 200 avec « votre cle a epuise son budget » pour texte, et une
    sonde qui ne regarderait que le code declarerait ce modele en bon etat.
    """
    charge: Dict[str, Any] = {
        "model": modele,
        "messages": [{"role": "user", "content": "Reponds exactement : OK"}],
        "temperature": 0.0,
        # Seize jetons suffisent pour « OK » — mais pas pour un modele de
        # RAISONNEMENT, qui redige d'abord son brouillon entre « <think> » et
        # « </think> ». « core.texte » retire ce brouillon, et il ne restait
        # rien : la sonde declarait « vide » les deux modeles de Groq, alors
        # que Groq venait de servir quatorze mille jetons le jour meme.
        # Un diagnostic qui accuse a tort est pire que pas de diagnostic.
        "max_tokens": min(256, p.max_sortie),
    }
    valeur = ""
    if p.api_key_env:
        lot = pool_cles.pool(p.name, p.api_key_env)
        candidates = lot.disponibles() or lot.cles
        if candidates:
            valeur = candidates[0].valeur
    entetes = config.entetes_appel(p, valeur)
    url = p.base_url.rstrip("/") + "/chat/completions"
    from .http import requete_complete

    _statut, brut_reponse, entetes_recus = requete_complete(
        url, "POST", entetes,
        json.dumps(charge, ensure_ascii=False).encode("utf-8"), timeout)
    data = json.loads(brut_reponse.decode("utf-8", "replace"))
    if observe is not None:
        # Les en-tetes portent les quotas que le service applique VRAIMENT.
        # L'appelant les recupere ici plutot que de refaire l'appel — et avec
        # eux le cout de CET appel : l'audit doit pouvoir se retirer de sa
        # propre mesure, sinon il se compte lui-meme comme un ecart.
        observe["entetes"] = dict(entetes_recus)
        usage = data.get("usage") or {}
        observe["jetons"] = int(usage.get("total_tokens") or 0)
        # Ce qui a ete DEMANDE et ce qui a ete PRODUIT, separement. Certains
        # services decomptent la reservation — l'invite plus le plafond de
        # sortie — et non la sortie reelle. La difference n'est pas theorique
        # : chez un fournisseur a 8000 jetons par minute, reserver 8192 par
        # appel epuise la minute en un appel. On rend les deux chiffres pour
        # que l'audit puisse constater laquelle des deux conventions le
        # service applique, au lieu de la supposer.
        observe["jetons_sortie"] = int(usage.get("completion_tokens") or 0)
        observe["plafond_demande"] = int(charge["max_tokens"])
    choix = (data.get("choices") or [{}])[0]
    brut = ((choix.get("message") or {}).get("content") or "").strip()
    texte = module_texte.assainir(brut)
    if not texte and brut:
        # Le modele a parle, et tout ce qu'il a dit etait du brouillon. Le
        # dire ainsi plutot que « vide » : le geste a faire n'est pas le meme,
        # et ce modele-la fonctionne.
        raise HttpErreur(
            200, "{} : raisonnement seul, pas de reponse en {} jetons"
            .format(p.name, charge["max_tokens"]), corps=brut[:200])
    refus = module_texte.refus_deguise(texte, attend_francais=False)
    if refus:
        statut = 402 if module_texte.ressemble_a_un_quota(texte) else 503
        raise HttpErreur(statut, "{} : {}".format(p.name, refus),
                         corps=texte[:300])
    return texte


def diagnostic(compteurs: bool = True) -> List[Dict[str, Any]]:
    """Etat de chaque fournisseur (pour 'usine docteur').

    « compteurs=False » quand la base est illisible : la consommation du jour
    y est enregistree, et elle devient alors inconnaissable. On rend None, pas
    zero. Zero serait un chiffre sans source, et le pire moment pour en
    inventer un est celui ou l'utilisateur cherche ce qui a casse.
    """
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
                "aujourdhui": (store.compteur_jour(p.name, modele)
                               if compteurs else None),
                "rpd": q.rpd,
                "rpm": q.rpm,
                # Les plafonds en jetons sont ceux qui arretent vraiment une
                # fabrication : les afficher evite de chercher la cause
                # ailleurs quand le fournisseur le plus rapide se tait.
                "tpm": q.tpm,
                "tpd": q.tpd,
                "jetons_aujourdhui": (store.jetons_jour(p.name, modele)
                                      if compteurs else None),
                "inscription": p.signup,
                "notes": p.notes,
            }
        )
    return lignes
