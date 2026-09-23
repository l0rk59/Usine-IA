"""Configuration de l'usine : chemins, fichier .env, catalogue des fournisseurs IA.

Tout est resolu a la volee pour rester utilisable sur Termux ou l'arborescence
est souvent deplacee (~/Usine-IA, /sdcard/Usine-IA, etc.).
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Dict, List, Optional

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_workdir() -> Path:
    """Repertoire de travail : sorties, base de donnees, cache."""
    env = os.environ.get("USINE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return ROOT / "atelier"


WORKDIR = _resolve_workdir()
PRODUITS_DIR = WORKDIR / "produits"
CACHE_DIR = WORKDIR / "cache"
LOG_DIR = WORKDIR / "logs"
DB_PATH = WORKDIR / "usine.db"
ENV_PATH = ROOT / ".env"


def ensure_dirs() -> None:
    for path in (WORKDIR, PRODUITS_DIR, CACHE_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Chargement du .env (parseur minimaliste, pas de dependance python-dotenv)
# --------------------------------------------------------------------------

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env(path: Optional[Path] = None, override: bool = False) -> Dict[str, str]:
    """Charge un fichier .env dans os.environ et renvoie les paires lues."""
    path = path or ENV_PATH
    found: Dict[str, str] = {}
    if not path.exists():
        return found
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _LINE.match(raw)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        value = value.split(" #")[0].strip() if not value.startswith("#") else ""
        found[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return found


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def env_bool(key: str, default: bool = False) -> bool:
    value = env(key, "1" if default else "0").lower()
    return value in ("1", "true", "yes", "oui", "on")


# --------------------------------------------------------------------------
# Catalogue des fournisseurs IA (tous compatibles API OpenAI /chat/completions)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Quota:
    """Ce qu'un palier gratuit autorise vraiment.

    Compter les requetes ne suffit pas. Groq annonce 30 requetes par minute
    sur son palier gratuit, mais 8 000 JETONS par minute : une seule demande
    de chapitre (une invite de trois mille jetons et huit mille de sortie)
    depasse a elle seule le budget de la minute. Le routeur qui ne compte que
    les requetes croit avoir droit a trente appels, en tente un, recolte un
    429, met le fournisseur au repos — et recommence la minute suivante.
    Meme ecart chez Cerebras : 5 requetes par minute annoncees, la ou l'usine
    en supposait 25.

    Un plafond a zero signifie « non publie par le fournisseur », donc non
    modelise : on ne l'invente pas.

    « portee » dit a quoi le quota s'applique. Chez Google il est compte PAR
    MODELE (flash et flash-lite ont chacun le sien) ; ailleurs il vaut pour
    tout le fournisseur. Le distinguer evite de s'interdire flash-lite parce
    que flash a consomme sa journee.
    """

    rpm: int = 20                   # requetes / minute
    rpd: int = 500                  # requetes / jour
    tpm: int = 0                    # jetons / minute (0 = non publie)
    tpd: int = 0                    # jetons / jour   (0 = non publie)
    portee: str = "fournisseur"     # ou "modele"


@dataclass
class Provider:
    """Un fournisseur de texte compatible OpenAI."""

    name: str
    base_url: str
    api_key_env: str
    models: Dict[str, str]          # role logique -> identifiant du modele
    rpm: int = 20                   # requetes / minute (quota gratuit prudent)
    rpd: int = 500                  # requetes / jour
    local: bool = False             # tourne sur l'appareil (llama.cpp, ollama)
    keyless: bool = False           # utilisable sans cle API
    signup: str = ""                # ou obtenir une cle gratuite
    notes: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Variables d'environnement qui, en plus de la cle, doivent etre
    # renseignees pour que le fournisseur fonctionne. Cloudflare met
    # l'identifiant de compte dans l'URL : avec la cle seule, chaque appel
    # partait vers une adresse fausse, et le routeur l'aurait mis au repos
    # comme une panne — au lieu de dire qu'il manque un reglage.
    autres_variables: Tuple[str, ...] = ()
    # En-tete de session exige par le service, s'il en exige un. Sa valeur ne
    # peut pas etre ecrite ici : elle se derive de la cle, et la cle n'est
    # connue qu'a l'appel. « entetes_appel » s'en charge.
    entete_session: str = ""
    # Secondes avant d'abandonner un appel. Un service distant repond en
    # quelques secondes ; un modele de 3 milliards de parametres sur le
    # processeur d'un telephone produit entre trois et dix jetons par
    # seconde. Quatre mille jetons demandent donc entre sept et vingt
    # minutes. Avec la limite commune de 150 secondes, l'IA locale etait
    # cablee, annoncee dans le diagnostic — et incapable de terminer un
    # chapitre : chaque appel expirait avant la fin de la generation.
    timeout: int = 150
    # Jetons de SORTIE que le fournisseur accepte pour une seule reponse. Le
    # routeur y ramene la demande de l'appelant : demander plus ne produit pas
    # plus, cela produit une erreur chez certains et un silence chez d'autres.
    max_sortie: int = 8192
    # Plafonds detailles, par identifiant de modele. Ce qui n'y figure pas
    # retombe sur rpm/rpd ci-dessus, valables pour le fournisseur entier.
    quotas: Dict[str, Quota] = field(default_factory=dict)

    def quota(self, role: str = "standard") -> Quota:
        """Plafonds applicables au modele qui servira ce role."""
        precis = self.quotas.get(self.model_for(role))
        if precis is not None:
            return precis
        return Quota(rpm=self.rpm, rpd=self.rpd)

    @property
    def api_key(self) -> str:
        """Premiere cle declaree. Le routeur utilise le pool, pas cette propriete."""
        return env(self.api_key_env) if self.api_key_env else ""

    def nb_cles(self) -> int:
        if not self.api_key_env:
            return 0
        from . import cles as pool_cles

        return len(pool_cles.pool(self.name, self.api_key_env))

    def available(self) -> bool:
        if any(not env(nom) for nom in self.autres_variables):
            return False
        if self.local or self.keyless:
            return True
        return self.nb_cles() > 0

    def model_for(self, role: str) -> str:
        return self.models.get(role) or self.models.get("standard") or ""


# Roles logiques. L'usine ne demande jamais un modele par son nom : elle
# demande un role, et « core.modeles » le resout sur le catalogue que le
# fournisseur sert REELLEMENT ce jour-la.
#
#   rapide       -> titres, JSON courts, classement (petit modele, gros quota)
#   standard     -> redaction courante
#   costaud      -> plan detaille, edition, controle (le meilleur disponible)
#   long         -> condenser beaucoup de texte d'un coup (relecture d'ensemble,
#                   fermeture d'une partie de roman) : c'est le contexte qui
#                   compte, pas la finesse
#   creatif      -> fiction. Un modele entraine pour ecrire, pas pour resumer ;
#                   NVIDIA sert « writer/palmyra-creative-122b », qui existe
#                   exactement pour cela, et le roman le demande
#   code         -> la chaine logicielle, dont le code doit compiler
#   raisonnement -> structure et arbitrage entre agents. Reflechir coute des
#                   jetons, donc on ne le demande que la ou cela se justifie —
#                   et le brouillon est retire par « core.texte »
#
# « model_for » retombe sur « standard » quand un fournisseur n'a rien de mieux
# a offrir : declarer un role ne coute rien la ou il n'apporte rien.

PROVIDERS: List[Provider] = [
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        # Les deux modeles Llama configures ici jusqu'au 16 aout 2026 ont ete
        # retires du palier gratuit ce jour-la (console.groq.com/docs/
        # deprecations). L'usine a donc appele pendant des semaines un modele
        # inexistant : chaque tentative renvoyait 404, le routeur mettait Groq
        # au repos une demi-heure et passait au suivant, sans que rien ne le
        # dise. « usine docteur --modeles » existe pour que cela ne puisse
        # plus arriver en silence.
        models={
            "rapide": "openai/gpt-oss-20b",
            "standard": "openai/gpt-oss-120b",
            "costaud": "openai/gpt-oss-120b",
        },
        # Releves le 12/09/2026 sur console.groq.com/docs/rate-limits. La date
        # racontee plus haut est celle d'une depreciation passee, pas celle
        # d'un releve : elle dit pourquoi ces modeles-ci sont configures, elle
        # ne dit pas quand ces quotas-la ont ete verifies. Le garde-fou de
        # tests/test_fournisseurs_declares.py ne fait pas la difference — et
        # c'est voulu, un lecteur non plus.
        rpm=30,
        rpd=1000,
        quotas={
            # 8 000 jetons par minute : c'est LA contrainte, pas les 30
            # requetes. Une demande de chapitre n'y entre pas — le routeur
            # confiera donc les gros travaux a un autre fournisseur et
            # gardera Groq pour ce qui est court, ce qu'il fait tres vite.
            "openai/gpt-oss-20b": Quota(rpm=30, rpd=1000, tpm=8000, tpd=200000),
            "openai/gpt-oss-120b": Quota(rpm=30, rpd=1000, tpm=8000, tpd=200000),
        },
        signup="https://console.groq.com/keys",
        notes="Le plus rapide. Gratuit, sans carte bancaire. Budget serre en "
              "jetons (8 000/min, 200 000/jour) : ideal pour les appels courts.",
    ),
    Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        # Le catalogue gratuit s'est reduit a deux modeles ; les Llama
        # configures ici n'y figurent plus (inference-docs.cerebras.ai).
        models={
            "rapide": "qwen-3.8-27b",
            "standard": "gpt-oss-120b",
            "costaud": "gpt-oss-120b",
        },
        # 5 requetes par minute, pas 25 : l'usine en supposait cinq fois trop
        # et s'attirait des 429 a chaque enchainement de chapitres.
        # Releve le 12/09/2026 sur inference-docs.cerebras.ai.
        rpm=5,
        rpd=200,
        quotas={
            "gpt-oss-120b": Quota(rpm=5, rpd=200, tpm=30000, tpd=1000000),
            "qwen-3.8-27b": Quota(rpm=5, rpd=200, tpm=30000, tpd=1000000),
        },
        signup="https://cloud.cerebras.ai/ (carte bancaire exigee)",
        # Le palier gratuit SANS CARTE a pris fin : Cerebras l'a remplace par un
        # essai de 5 dollars qui exige une carte bancaire, et une cle sans
        # credit repond 402. Releve du 11/09/2026 (klymentiev.com/blog/free-llm-
        # api), qui recoupe exactement nos propres chiffres Groq — c'est ce qui
        # permet de s'y fier.
        #
        # Le fournisseur reste declare : une cle creditee fonctionne, et la
        # vitesse est reelle. Mais il n'est plus « gratuit », et le dire
        # ailleurs serait envoyer quelqu'un creer un compte pour un 402.
        notes="PAYANT depuis septembre 2026 : essai de 5 $ avec carte. Tres "
              "rapide, 5 requetes par minute.",
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        models={
            # Les « 2.5 » ont ete retires : 404 sur les deux, mesure deux
            # fois a un jour d'intervalle sur un compte reel (15/09/2026).
            # Les remplacants ci-dessous ont ete APPELES sur ce compte-la et
            # ont repondu. Le prefixe « models/ » est celui que le catalogue
            # de Google emploie, et l'endpoint compatible OpenAI l'accepte.
            #
            # Source : un seul compte, une seule date. Un autre palier peut
            # ne pas servir les memes : c'est « usine docteur --reparer » qui
            # tranche pour chaque installation.
            "rapide": "models/gemini-3.1-flash-lite",
            "standard": "models/gemini-3.5-flash",
            "costaud": "models/gemini-3.5-flash",
            "long": "models/gemini-3.5-flash",
        },
        rpm=10,
        rpd=250,
        max_sortie=8192,
        # Google compte PAR MODELE. Un seul couple rpm/rpd pour tout le
        # fournisseur interdisait flash-lite — mille requetes par jour — des
        # que flash avait epuise les siennes, quatre fois moins nombreuses.
        # Google ne publie plus ces chiffres dans sa documentation (ils sont
        # renvoyes vers AI Studio, derriere une authentification) : les
        # valeurs ci-dessous sont les plus basses rapportees, parce qu'une
        # sous-estimation coute une attente et une surestimation coute un 429.
        quotas={
            "models/gemini-3.5-flash": Quota(rpm=10, rpd=250, tpm=250000,
                                      portee="modele"),
            "models/gemini-3.1-flash-lite": Quota(rpm=15, rpd=1000, tpm=250000,
                                           portee="modele"),
        },
        signup="https://aistudio.google.com/apikey",
        notes="Contexte 1M tokens. Ideal pour les longs manuscrits. "
              "Quotas comptes par modele : flash-lite est le plus genereux.",
    ),
    Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        models={
            "rapide": "mistral-small-latest",
            "standard": "mistral-small-latest",
            "costaud": "mistral-medium-latest",
        },
        # Poses le 11/09/2026 et JAMAIS confrontes a la documentation du
        # fournisseur : le depot n'en porte aucune trace. Ce sont donc des
        # bornes prudentes, pas un releve — a revalider sur
        # docs.mistral.ai/deployment/laplateforme/tier/, ou avec
        # « usine docteur --modeles » qui interroge le service lui-meme.
        rpm=20,
        rpd=500,
        signup="https://console.mistral.ai/api-keys/",
        notes="Excellent en francais. Palier gratuit 'Experiment'.",
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        # Releve sur « GET /api/v1/models » le 13/09/2026 : 19 modeles « :free »
        # sur 445, et ni « llama-3.3-70b:free » ni « deepseek-chat-v3:free »
        # n'en font plus partie. Les identifiants « :free » sont les plus
        # volatils du depot — un modele y passe payant du jour au lendemain.
        models={
            "rapide": "nex-agi/nex-n2.5-mini:free",
            "standard": "google/gemma-4-31b-it:free",
            "costaud": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "long": "nvidia/nemotron-3.5-lightning:free",
            "creatif": "google/gemma-4-31b-it:free",
            "code": "cohere/north-mini-code:free",
            "raisonnement": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        },
        rpm=20,
        rpd=50,
        signup="https://openrouter.ai/keys",
        notes="19 modeles « :free », 20 requetes/minute et 50 par jour "
              "(1000 apres un rechargement unique de 10 USD).",
        extra_headers={
            "HTTP-Referer": "https://github.com/l0rk59/usine-ia",
            "X-Title": "Usine-IA",
        },
    ),
    Provider(
        name="cloudflare",
        # L'identifiant de compte fait partie de l'URL : sans lui, l'adresse
        # est fausse. D'ou « autres_variables » plus bas — le fournisseur ne se
        # dit disponible que si le jeton ET le compte sont renseignes.
        base_url="https://api.cloudflare.com/client/v4/accounts/{}/ai/v1".format(
            env("CLOUDFLARE_ACCOUNT_ID")),
        api_key_env="CLOUDFLARE_API_TOKEN",
        autres_variables=("CLOUDFLARE_ACCOUNT_ID",),
        # Identifiants et tarifs releves le 23/09/2026 sur la documentation
        # officielle (developers.cloudflare.com/workers-ai/models/ et
        # /platform/pricing/). Les trois sont servis par /v1/chat/completions.
        models={
            "rapide": "@cf/openai/gpt-oss-20b",
            "standard": "@cf/openai/gpt-oss-120b",
            "costaud": "@cf/openai/gpt-oss-120b",
            "long": "@cf/openai/gpt-oss-120b",
        },
        # 10 000 « neurones » par jour, gratuits, sans carte, remis a zero a
        # 00:00 UTC. gpt-oss-120b coute 68 182 neurones par million de jetons
        # de sortie et 31 818 par million en entree : un appel typique de
        # l'usine (3 000 jetons lus, 3 000 ecrits) en consomme environ 300,
        # soit une trentaine d'appels par jour — un roman court, a peu pres.
        #
        # Le plafond par minute publie est 300 ; on declare le quotidien que
        # le budget en neurones permet vraiment, pour que le routeur ne brule
        # pas la reserve du jour sur les premiers appels.
        rpm=60,
        rpd=33,
        quotas={
            "@cf/openai/gpt-oss-120b": Quota(rpm=60, rpd=33),
            # 27 273 neurones par million en sortie : quatre fois moins cher.
            "@cf/openai/gpt-oss-20b": Quota(rpm=60, rpd=140),
        },
        signup="https://dash.cloudflare.com/ : Workers AI, puis « Use REST "
               "API » pour le jeton et l'identifiant de compte",
        notes="Gratuit sans carte : 10 000 neurones par jour, soit environ "
              "trente appels a gpt-oss-120b. Demande DEUX valeurs : le jeton "
              "et l'identifiant de compte.",
    ),
    Provider(
        name="opencode",
        base_url="https://opencode.ai/zen/go/v1",
        api_key_env="OPENCODE_API_KEY",
        # Ce service refuse tout appel sans en-tete de session. Releve le
        # 15/09/2026, en clair dans le corps de son HTTP 400 :
        #
        #   MissingSessionID — « Request is missing x-opencode-session
        #   and cannot be routed »
        #
        # Six modeles, six cents requetes par jour, un abonnement paye, et
        # pas un seul appel n'aboutissait. Le code seul (400) n'en disait
        # rien ; c'est le CORPS de la reponse qui l'a nomme, et c'est pour
        # cela que le rapport de quotas le rend desormais.
        entete_session="x-opencode-session",
        # ATTENTION — ce fournisseur n'expose AUCUN endpoint « /v1/models ».
        # (Demande faite puis fermee : anomalyco/opencode, issue 2901.)
        #
        # C'est la seule entree de cette liste dans ce cas, et cela change
        # quelque chose d'important : « core/modeles.py » relit le catalogue
        # vivant de chaque fournisseur pour rattraper un identifiant renomme.
        # Ici il n'y a rien a relire. Un modele renomme se verra donc en 404
        # nomme par le routeur — ce qui reste le bon comportement, mieux vaut
        # une panne nommee qu'un chapitre ecrit par un modele d'embeddings —
        # mais sans correction automatique. C'est exactement le defaut qui
        # avait rendu une cle NVIDIA valide inutilisable pendant des jours.
        #
        # Identifiants RELEVES DE LA DOCUMENTATION le 14/09/2026, et non
        # d'un catalogue interroge : donnee perissable au carre. Le premier
        # appel reel dira s'ils sont justes.
        models={
            "rapide": "glm-5.3-flash",
            "standard": "glm-5.3",
            "costaud": "kimi-k3",
            "long": "minimax-m3",
            "creatif": "kimi-k3",
            "code": "qwen3.8-max",
            "raisonnement": "deepseek-v4-pro",
        },
        # Les plafonds d'OpenCode Go ne se comptent pas en requetes mais en
        # DOLLARS : 20 % du mensuel par tranche de cinq heures, 50 % par
        # semaine, 100 % par mois (documentation du 14/09/2026). Le routeur,
        # lui, compte des requetes. Les valeurs ci-dessous sont donc une
        # prudence, pas une transcription : elles evitent de vider une
        # tranche de cinq heures en quelques minutes de fabrication continue.
        # Le vrai garde-fou reste le compteur d'OpenCode, et le routeur
        # basculera sur un autre fournisseur des le premier refus.
        rpm=20,
        rpd=600,
        signup="https://opencode.ai/go (abonnement payant, ~10 $/mois)",
        notes="OpenCode Go : une trentaine de modeles ouverts derriere une "
              "seule cle, compatible OpenAI. Plafonds en dollars, pas en "
              "requetes — et pas de catalogue interrogeable.",
    ),
    Provider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_API_KEY",
        # Releve sur « GET /v1/models » le 13/09/2026 : 82 modeles servis, et
        # AUCUN des deux « meta/llama » configures jusque-la. Chaque appel
        # rendait 404, le routeur mettait NVIDIA au repos une demi-heure, et
        # une cle valide ne servait a rien sans que rien ne le dise. C'est le
        # catalogue le plus fourni des fournisseurs gratuits : un modele par
        # role y a un sens, et « core.modeles » rattrape le prochain
        # renommage tout seul.
        models={
            # 404 sur le compte mesure le 15/09/2026. Celui-ci a repondu.
            "rapide": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "standard": "nvidia/nemotron-3-super-120b-a12b",
            "costaud": "nvidia/nemotron-3-ultra-550b-a55b",
            "long": "nvidia/nemotron-3.5-lightning-30b-a3b",
            # « writer/palmyra-creative-122b » FIGURE au catalogue public de
            # NVIDIA — verifie, parmi 81 — et rend 404 sur le compte mesure,
            # deux fois a un jour d'intervalle. Listé ne veut pas dire
            # appelable : le catalogue public et ce qu'un palier sert sont
            # deux choses differentes.
            "creatif": "meta/muse-glimmer-30b",
            "code": "nvidia/nemotron-3-super-120b-a12b",
            "raisonnement": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        },
        rpm=40,
        rpd=800,
        signup="https://build.nvidia.com/",
        notes="NVIDIA NIM : 82 modeles, 40 requetes/minute. Le catalogue le "
              "plus fourni du palier gratuit — un modele par role.",
    ),
    Provider(
        name="pollinations",
        base_url="https://text.pollinations.ai/openai",
        api_key_env="POLLINATIONS_TOKEN",
        # Seul « openai-fast » est ouvert au palier anonyme : les autres renvoient 402.
        models={"rapide": "openai-fast", "standard": "openai-fast",
                "costaud": "openai-fast"},
        # Poses le 11/09/2026 au juge : le palier anonyme de Pollinations ne
        # publie aucun chiffre. Trois par minute est ce qui passait sans 429
        # lors de l'integration ; ce n'est pas un quota annonce, et le service
        # peut le changer sans prevenir.
        rpm=3,
        rpd=60,
        max_sortie=4096,
        keyless=True,
        signup="aucune inscription requise",
        notes="Filet de securite sans cle API. Quota anonyme etroit et partage par "
              "adresse IP : suffisant pour essayer l'usine, pas pour produire en "
              "volume. Renvoie 402 des le quota atteint.",
    ),
    Provider(
        name="ollama",
        base_url=env("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1",
        api_key_env="",
        models={
            "rapide": env("OLLAMA_MODEL_RAPIDE") or "qwen2.5:0.5b",
            "standard": env("OLLAMA_MODEL") or "qwen2.5:3b",
            "costaud": env("OLLAMA_MODEL") or "qwen2.5:3b",
        },
        rpm=600,
        rpd=100000,
        timeout=1200,
        # Un telephone n'a pas la memoire d'un long contexte de sortie.
        max_sortie=4096,
        local=True,
        signup="pkg install ollama && ollama serve",
        notes="IA locale, 100%% hors ligne.",
    ),
    Provider(
        name="llamacpp",
        base_url=env("LLAMACPP_BASE_URL") or "http://127.0.0.1:8080/v1",
        api_key_env="",
        models={
            "rapide": "local",
            "standard": "local",
            "costaud": "local",
        },
        rpm=600,
        rpd=100000,
        timeout=1200,
        max_sortie=4096,
        local=True,
        signup="llama-server -m modele.gguf --port 8080",
        notes="IA locale via llama.cpp (serveur compatible OpenAI).",
    ),
]

PROVIDERS_BY_NAME: Dict[str, Provider] = {p.name: p for p in PROVIDERS}

DEFAULT_ORDER = [
    "groq",
    "gemini",
    "mistral",
    "nvidia",
    # Paye et genereux : 600 requetes par jour. Il passe avant les paliers
    # gratuits, qui s'epuisent en une fabrication.
    "opencode",
    # Une trentaine d'appels par jour, pas davantage : en tete de liste, il
    # s'epuiserait sur les titres et les reglages avant la premiere scene. Il
    # sert de reserve quand les gros quotas sont tombes.
    "cloudflare",
    "openrouter",
    # Payant depuis septembre 2026 : n'est appele que si une cle creditee
    # est posee, et alors tard, parce qu'il coute.
    "cerebras",
    "pollinations",
    "ollama",
    "llamacpp",
]


def provider_order() -> List[str]:
    """Ordre de bascule, surchargeable via USINE_PROVIDERS."""
    custom = env("USINE_PROVIDERS")
    if custom:
        names = [n.strip() for n in custom.replace(";", ",").split(",") if n.strip()]
        known = [n for n in names if n in PROVIDERS_BY_NAME]
        if known:
            return known
    # Tout fournisseur DECLARE qui ne figure pas dans l'ordre est ajoute a la
    # fin plutot que perdu. Sans cela, « opencode » — declare, dote d'une cle,
    # affiche « disponible » par le diagnostic, et absent de cette liste —
    # n'a jamais ete appele une seule fois. Le journal du 15/09/2026 le
    # montre : sur vingt-sept modeles essayes, aucun n'etait le sien.
    #
    # C'est le defaut que ce depot appelle un reglage orphelin, deplace d'un
    # cran : une chose declaree, visible, et que rien ne lit. Deriver l'ordre
    # du catalogue rend l'oubli impossible au lieu de le corriger une fois.
    # Et l'inverse : un nom de l'ordre qui n'est plus DECLARE est ignore
    # plutot que de faire tomber l'usine. Le retrait de GitHub Models, le
    # 23/09/2026, a laisse son nom dans cette liste le temps d'une
    # modification — et « active_providers » levait KeyError, c'est-a-dire que
    # plus aucune fabrication ne demarrait. Retirer un fournisseur ferme ne
    # doit jamais couter la production entiere.
    connus = [n for n in DEFAULT_ORDER if n in PROVIDERS_BY_NAME]
    return connus + [p.name for p in PROVIDERS if p.name not in connus]


def _identifiant_de_session(nom: str, cle: str) -> str:
    """Un identifiant de session stable, derive de la cle.

    Stable, parce qu'une session qui change a chaque appel n'est pas une
    session. Derive de la CLE plutot que tire au sort et range quelque part,
    pour trois raisons : deux installations du meme compte partagent la meme
    session, ce qui est le comportement attendu ; il n'y a rien a persister,
    donc rien a migrer ni a perdre ; et une cle changee change la session
    sans qu'on ait a y penser.

    Le condensat ne laisse pas remonter a la cle, ce qui compte : cet
    identifiant part sur le reseau a chaque appel.
    """
    brut = hashlib.sha256("usine-ia:{}:{}".format(nom, cle).encode("utf-8"))
    h = brut.hexdigest()
    # Forme d'un UUID. Aucun service n'a dit l'exiger — mais c'est la forme
    # que prend un identifiant de session partout, et un condensat brut de
    # soixante-quatre caracteres est ce qui a le plus de chances d'etre
    # refuse par un controle de format.
    return "{}-{}-{}-{}-{}".format(h[:8], h[8:12], h[12:16], h[16:20], h[20:32])


def entetes_appel(p: Provider, cle: str = "",
                  corps_json: bool = True) -> Dict[str, str]:
    """Les en-tetes d'UN appel a ce fournisseur, cle comprise.

    Quatre endroits construisaient ces en-tetes, chacun a sa facon : le
    routeur, la sonde directe, et les deux lecteurs de catalogue. Tant qu'il
    n'y avait que « Content-Type » et « Authorization », la repetition ne
    coutait rien.

    Elle a commence a couter le jour ou un fournisseur a exige un en-tete de
    plus. Corriger un appelant sur quatre aurait donne le defaut favori de ce
    depot : la chose marche a un endroit, echoue ailleurs, et l'ecart ne se
    voit qu'a l'usage. Un test verifie qu'aucun autre endroit ne pose
    « Authorization » lui-meme.
    """
    entetes: Dict[str, str] = {}
    if corps_json:
        entetes["Content-Type"] = "application/json"
    entetes.update(p.extra_headers)
    if cle:
        entetes["Authorization"] = "Bearer {}".format(cle)
        if p.entete_session:
            entetes[p.entete_session] = _identifiant_de_session(p.name, cle)
    return entetes


def active_providers(include_unavailable: bool = False) -> List[Provider]:
    """Fournisseurs utilisables, dans l'ordre de bascule.

    Les fournisseurs locaux passent toujours en dernier : ce sont le
    dernier recours demande, pas le choix par defaut.
    """
    order = provider_order()
    chosen = [PROVIDERS_BY_NAME[n] for n in order]
    if not include_unavailable:
        chosen = [p for p in chosen if p.available()]
    distants = [p for p in chosen if not p.local]
    locaux = [p for p in chosen if p.local]
    if env_bool("USINE_LOCAL_FIRST"):
        return locaux + distants
    return distants + locaux
