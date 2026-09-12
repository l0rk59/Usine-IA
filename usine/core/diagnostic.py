"""Etat de l'installation, sous forme de faits plutot que de texte.

« usine docteur » ecrivait ses constats directement a l'ecran. Le tableau de
bord ne pouvait donc pas les montrer — alors que c'est dans le navigateur
qu'on cherche le bouton « pourquoi ca ne marche pas ». Recopier les controles
cote web en aurait fait deux jeux qui divergent ; ils vivent ici, et les deux
interfaces les mettent en forme chacune a sa facon.
"""

from __future__ import annotations

import json
import shutil
import sys
from typing import Any, Dict, List, Optional

from . import config, llm, store, telephone
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


def _catalogue_distant(fournisseur: config.Provider,
                       timeout: int) -> Optional[List[str]]:
    """Identifiants de modeles que le fournisseur declare servir.

    Rend None quand la question n'a pas pu etre posee (pas de cle, service
    injoignable, endpoint absent) : « je ne sais pas » ne doit jamais se
    confondre avec « aucun modele », sous peine d'accuser a tort une
    configuration correcte.
    """
    from .http import HttpErreur, requete

    entetes = dict(fournisseur.extra_headers)
    if fournisseur.api_key_env:
        lot = pool_cles.pool(fournisseur.name, fournisseur.api_key_env)
        candidates = lot.disponibles() or lot.cles
        if candidates:
            entetes["Authorization"] = "Bearer {}".format(candidates[0].valeur)
        elif not fournisseur.keyless:
            return None  # sans cle, la question ne peut pas etre posee
    url = fournisseur.base_url.rstrip("/") + "/models"
    try:
        statut, brut = requete(url, entetes=entetes, timeout=timeout)
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
        if isinstance(entree, dict):
            nom = entree.get("id") or entree.get("name")
        else:
            nom = entree
        if isinstance(nom, str) and nom:
            noms.append(nom)
    return noms


def modeles_disparus(timeout: int = 10) -> Dict[str, Any]:
    """Modeles configures que leur fournisseur ne sert plus.

    Ce controle existe a cause d'une panne reelle et entierement silencieuse :
    le 16 aout 2026, Groq a retire du palier gratuit les deux modeles Llama
    que l'usine lui demandait. Chaque appel a repondu 404, le routeur a mis
    Groq au repos une demi-heure puis est passe au suivant — exactement le
    comportement prevu pour une panne passagere. Le fournisseur le plus rapide
    de la liste etait mort depuis des semaines, et rien, nulle part, ne le
    disait. Les catalogues bougent ; ce qui manquait, c'etait de les relire.

    Une ligne par ecart, avec les identifiants proposes par le fournisseur :
    la correction se fait dans usine/core/config.py.

    Le resultat dit aussi QUI a repondu. Sans cela, un controle qui n'a pu
    interroger personne rendait une liste vide, indistinguable d'un controle
    ou tout va bien — la meme fausse assurance que ce module existe pour
    supprimer.
    """
    ecarts: List[Dict[str, Any]] = []
    consultes: List[str] = []
    injoignables: List[str] = []
    for fournisseur in config.active_providers():
        if fournisseur.local:
            continue  # un modele local se verifie deja par « locaux_actifs »
        servis = _catalogue_distant(fournisseur, timeout)
        if servis is None:
            injoignables.append(fournisseur.name)
            continue
        consultes.append(fournisseur.name)
        connus = set(servis)
        manquants = sorted({m for m in fournisseur.models.values()
                            if m and m not in connus})
        if manquants:
            ecarts.append({
                "fournisseur": fournisseur.name,
                "manquants": manquants,
                "proposes": servis[:12],
            })
    return {"ecarts": ecarts, "consultes": consultes,
            "injoignables": injoignables}


def etat_installation(avec_reseau: bool = True,
                      avec_locaux: bool = True,
                      avec_modeles: bool = False) -> Dict[str, Any]:
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
        "telephone": telephone.etat(),
        "fournisseurs": fournisseurs,
        "distants_prets": len(distants),
        "pool": pool_cles.resume(),
        "consommation": store.stats_fournisseurs(),
    }
    etat["reseau"] = _reseau() if avec_reseau else None
    etat["locaux"] = locaux_actifs() if avec_locaux else []
    # Une requete par fournisseur : assez lent pour ne pas le faire a chaque
    # rafraichissement du tableau de bord, assez important pour que
    # « usine docteur --modeles » existe.
    etat["modeles"] = modeles_disparus() if avec_modeles else None
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
