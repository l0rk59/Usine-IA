"""Etat de l'installation, sous forme de faits plutot que de texte.

« usine docteur » ecrivait ses constats directement a l'ecran. Le tableau de
bord ne pouvait donc pas les montrer — alors que c'est dans le navigateur
qu'on cherche le bouton « pourquoi ca ne marche pas ». Recopier les controles
cote web en aurait fait deux jeux qui divergent ; ils vivent ici, et les deux
interfaces les mettent en forme chacune a sa facon.
"""

from __future__ import annotations

import shutil
import sys
from typing import Any, Dict, List

from . import config, llm, store
from . import cles as pool_cles
from . import verification


def _espace_libre() -> Dict[str, Any]:
    """Place restante la ou l'usine ecrit.

    Un telephone se remplit, et une fabrication qui s'arrete faute de place
    laisse un produit a moitie ecrit sans dire pourquoi.
    """
    try:
        usage = shutil.disk_usage(str(config.WORKDIR))
    except OSError:
        return {"connu": False}
    return {"connu": True, "libre_mo": usage.free // (1024 * 1024),
            "total_mo": usage.total // (1024 * 1024)}


def locaux_actifs(timeout: int = 3) -> List[str]:
    """Serveurs d'IA locale qui repondent vraiment."""
    from .http import HttpErreur, requete

    actifs: List[str] = []
    for nom in ("ollama", "llamacpp"):
        fournisseur = config.PROVIDERS_BY_NAME[nom]
        url = fournisseur.base_url.rstrip("/") + "/models"
        try:
            statut, _ = requete(url, timeout=timeout)
        except (HttpErreur, OSError):
            continue
        if statut == 200:
            actifs.append(nom)
    return actifs


def etat_installation(avec_reseau: bool = True,
                      avec_locaux: bool = True) -> Dict[str, Any]:
    """Tout ce que « docteur » constate, en donnees.

    Les deux drapeaux existent parce que ces deux controles SORTENT sur le
    reseau : les tests ne doivent pas dependre d'une connexion, et le
    tableau de bord ne doit pas les refaire a chaque rafraichissement.
    """
    fournisseurs = llm.diagnostic()
    distants = [f for f in fournisseurs if f["disponible"] and not f["local"]]

    etat: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "workdir": str(config.WORKDIR),
        "env_present": config.ENV_PATH.exists(),
        "node": verification.node_disponible(),
        "espace": _espace_libre(),
        "fournisseurs": fournisseurs,
        "distants_prets": len(distants),
        "pool": pool_cles.resume(),
        "consommation": store.stats_fournisseurs(),
    }
    etat["reseau"] = _reseau() if avec_reseau else None
    etat["locaux"] = locaux_actifs() if avec_locaux else []
    etat["verdict"] = _verdict(etat)
    return etat


def _reseau() -> bool:
    from .http import HttpErreur, requete

    try:
        statut, _ = requete("https://pollinations.ai/", timeout=4)
    except (HttpErreur, OSError):
        return False
    return statut < 500


def _verdict(etat: Dict[str, Any]) -> Dict[str, str]:
    """Ce qu'on peut faire, en une phrase, et quoi faire sinon."""
    if etat["distants_prets"]:
        return {"etat": "pret",
                "message": "{} fournisseur(s) distant(s) pret(s). "
                           "L'usine peut produire.".format(etat["distants_prets"])}
    if etat["locaux"]:
        return {"etat": "local",
                "message": "IA locale detectee : {}. Production hors ligne "
                           "possible, mais comptez plusieurs minutes par "
                           "chapitre.".format(", ".join(etat["locaux"]))}
    return {"etat": "bloque",
            "message": "Aucun fournisseur pret. Lancez « usine cles »."}
