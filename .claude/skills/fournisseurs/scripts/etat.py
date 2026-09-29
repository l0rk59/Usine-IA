#!/usr/bin/env python3
"""Ce que l'usine croit des fournisseurs, et ou verifier si c'est encore vrai.

Les identifiants de modeles et les quotas gratuits sont des donnees recopiees
d'un service tiers. Elles pourrissent, et leur pourrissement est silencieux :
un modele retire fait repondre 404, le routeur met le fournisseur au repos et
passe au suivant — exactement comme pour une panne passagere. C'est arrive
pour de bon, et le fournisseur le plus rapide de la liste est reste mort
pendant trois semaines sans que rien ne le dise.

Ce script ne verifie rien tout seul : aucun fournisseur ne publie ses quotas
sous une forme lisible par un programme. Il met cote a cote ce que le depot
declare et l'adresse ou le lire, pour que la comparaison soit une lecture et
pas une fouille.

Pour les identifiants de modeles, en revanche, il existe un controle
automatique : « usine docteur --modeles ».
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RACINE))

from usine.core import config  # noqa: E402

# Pages qui font foi, fournisseur par fournisseur. Les tableaux de quotas y
# bougent sans annonce ; c'est la qu'il faut aller, pas dans un billet de blog
# ni dans un resume d'agregateur.
SOURCES = {
    "groq": ("https://console.groq.com/docs/models",
             "https://console.groq.com/docs/rate-limits",
             "https://console.groq.com/docs/deprecations"),
    "cerebras": ("https://inference-docs.cerebras.ai/models/overview",
                 "https://inference-docs.cerebras.ai/support/rate-limits"),
    "gemini": ("https://ai.google.dev/gemini-api/docs/models",
               "https://aistudio.google.com/rate-limit"),
    "mistral": ("https://docs.mistral.ai/getting-started/models/models_overview/",
                "https://docs.mistral.ai/deployment/laplateforme/tier/"),
    "openrouter": ("https://openrouter.ai/models?max_price=0",
                   "https://openrouter.ai/docs/api-reference/limits"),
    "github": ("https://github.com/marketplace/models",
               "https://docs.github.com/en/github-models/prototyping-with-ai-models"),
    "nvidia": ("https://build.nvidia.com/models",),
    "pollinations": ("https://text.pollinations.ai/models",),
}


def main() -> int:
    for fournisseur in config.PROVIDERS:
        if fournisseur.local:
            continue
        print("\n== {} ".format(fournisseur.name) + "=" * (56 - len(fournisseur.name)))
        vus = []
        for role in ("rapide", "standard", "costaud", "long"):
            modele = fournisseur.models.get(role)
            if not modele or modele in vus:
                continue
            vus.append(modele)
            quota = fournisseur.quota(role)
            print("  {:<9} {}".format(role, modele))
            print("            {} req/min · {} req/jour{}{}  [{}]".format(
                quota.rpm, quota.rpd,
                " · {} jetons/min".format(quota.tpm) if quota.tpm else "",
                " · {} jetons/jour".format(quota.tpd) if quota.tpd else "",
                quota.portee))
        if not fournisseur.quota("standard").tpm:
            # Ce n'est pas « pas de limite » : c'est « non publie ». Le
            # distinguer evite de croire le routeur mieux informe qu'il ne l'est.
            print("  (aucun plafond en jetons modelise : non publie)")
        for url in SOURCES.get(fournisseur.name, ()):
            print("  voir      " + url)

    print("\n" + "-" * 60)
    print("Identifiants de modeles : « python3 -m usine.cli docteur --modeles »")
    print("interroge le /models de chaque fournisseur et compare au configure.")
    print("Quotas : a relire a la main sur les pages ci-dessus. Aucun service")
    print("ne les publie sous une forme lisible par un programme ; ils portent")
    print("donc une date de verification en commentaire dans core/config.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
