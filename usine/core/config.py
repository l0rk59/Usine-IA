"""Configuration de l'usine : chemins, fichier .env, catalogue des fournisseurs IA.

Tout est resolu a la volee pour rester utilisable sur Termux ou l'arborescence
est souvent deplacee (~/Usine-IA, /sdcard/Usine-IA, etc.).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


def env_bool(key: str, default: bool = False) -> bool:
    value = env(key, "1" if default else "0").lower()
    return value in ("1", "true", "yes", "oui", "on")


# --------------------------------------------------------------------------
# Catalogue des fournisseurs IA (tous compatibles API OpenAI /chat/completions)
# --------------------------------------------------------------------------


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
    # Secondes avant d'abandonner un appel. Un service distant repond en
    # quelques secondes ; un modele de 3 milliards de parametres sur le
    # processeur d'un telephone produit entre trois et dix jetons par
    # seconde. Quatre mille jetons demandent donc entre sept et vingt
    # minutes. Avec la limite commune de 150 secondes, l'IA locale etait
    # cablee, annoncee dans le diagnostic — et incapable de terminer un
    # chapitre : chaque appel expirait avant la fin de la generation.
    timeout: int = 150

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
        if self.local or self.keyless:
            return True
        return self.nb_cles() > 0

    def model_for(self, role: str) -> str:
        return self.models.get(role) or self.models.get("standard") or ""


# Roles logiques :
#   rapide   -> brouillons, titres, variations (petit modele, gros quota)
#   standard -> redaction courante
#   costaud  -> plan detaille, revision finale (meilleur modele dispo)

PROVIDERS: List[Provider] = [
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models={
            "rapide": "llama-3.1-8b-instant",
            "standard": "llama-3.3-70b-versatile",
            "costaud": "llama-3.3-70b-versatile",
        },
        rpm=28,
        rpd=900,
        signup="https://console.groq.com/keys",
        notes="Le plus rapide. Gratuit, sans carte bancaire.",
    ),
    Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models={
            "rapide": "llama3.1-8b",
            "standard": "llama-3.3-70b",
            "costaud": "llama-3.3-70b",
        },
        rpm=25,
        rpd=800,
        signup="https://cloud.cerebras.ai/",
        notes="Tres rapide, quota journalier genereux en tokens.",
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        models={
            "rapide": "gemini-2.5-flash-lite",
            "standard": "gemini-2.5-flash",
            "costaud": "gemini-2.5-flash",
        },
        rpm=12,
        rpd=400,
        signup="https://aistudio.google.com/apikey",
        notes="Contexte 1M tokens. Ideal pour les longs manuscrits.",
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
        rpm=20,
        rpd=500,
        signup="https://console.mistral.ai/api-keys/",
        notes="Excellent en francais. Palier gratuit 'Experiment'.",
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models={
            "rapide": "meta-llama/llama-3.3-70b-instruct:free",
            "standard": "meta-llama/llama-3.3-70b-instruct:free",
            "costaud": "deepseek/deepseek-chat-v3-0324:free",
        },
        rpm=18,
        rpd=45,
        signup="https://openrouter.ai/keys",
        notes="Beaucoup de modeles :free mais seulement ~50 requetes/jour.",
        extra_headers={
            "HTTP-Referer": "https://github.com/l0rk59/usine-ia",
            "X-Title": "Usine-IA",
        },
    ),
    Provider(
        name="github",
        base_url="https://models.github.ai/inference",
        api_key_env="GITHUB_MODELS_TOKEN",
        models={
            "rapide": "openai/gpt-4o-mini",
            "standard": "openai/gpt-4o-mini",
            "costaud": "openai/gpt-4o",
        },
        rpm=14,
        rpd=140,
        signup="https://github.com/settings/tokens (token classique, scope models:read)",
        notes="GitHub Models : gratuit avec un simple token GitHub.",
    ),
    Provider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_API_KEY",
        models={
            "rapide": "meta/llama-3.1-8b-instruct",
            "standard": "meta/llama-3.3-70b-instruct",
            "costaud": "meta/llama-3.3-70b-instruct",
        },
        rpm=20,
        rpd=800,
        signup="https://build.nvidia.com/",
        notes="NVIDIA NIM, credits gratuits renouveles.",
    ),
    Provider(
        name="pollinations",
        base_url="https://text.pollinations.ai/openai",
        api_key_env="POLLINATIONS_TOKEN",
        # Seul « openai-fast » est ouvert au palier anonyme : les autres renvoient 402.
        models={"rapide": "openai-fast", "standard": "openai-fast",
                "costaud": "openai-fast"},
        rpm=3,
        rpd=60,
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
        local=True,
        signup="llama-server -m modele.gguf --port 8080",
        notes="IA locale via llama.cpp (serveur compatible OpenAI).",
    ),
]

PROVIDERS_BY_NAME: Dict[str, Provider] = {p.name: p for p in PROVIDERS}

DEFAULT_ORDER = [
    "groq",
    "cerebras",
    "gemini",
    "mistral",
    "nvidia",
    "github",
    "openrouter",
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
    return list(DEFAULT_ORDER)


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
