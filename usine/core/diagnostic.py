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
import time
from typing import Any, Dict, List, Optional

from . import config, llm, store, telephone
from . import cles as pool_cles
from . import verification


def espace_libre() -> Dict[str, Any]:
    """Place restante la ou l'usine ecrit.

    Un telephone se remplit, et une fabrication qui s'arrete faute de place
    laisse un produit a moitie ecrit sans dire pourquoi.

    Publique parce que deux appelants la veulent : « docteur » pour son
    rapport, et le message de disque plein pour dire combien il reste. La
    recopier dans la CLI en aurait fait deux mesures qui divergent — un
    garde-fou de tests l'interdit, et il a servi.
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


def essayer_modeles(timeout: int = 30) -> Dict[str, Any]:
    """Appelle VRAIMENT chaque modele declare et dit lequel repond.

    « modeles_disparus » compare des listes : l'identifiant figure-t-il au
    catalogue du fournisseur ? C'est utile et cela ne coute rien, mais cela ne
    repond pas a la question posee par quelqu'un dont la fabrication echoue.
    Un modele peut etre LISTE et refuser de servir :

      - il existe, mais pas pour le palier gratuit du compte ;
      - il demande un credit que la cle n'a plus — et le service repond alors
        HTTP 200, « finish_reason: stop », un « usage » renseigne, et pour
        contenu « your key has reached its budget ». C'est la troisieme regle
        du depot : ne pas croire le code de retour, lire le contenu ;
      - il est servi mais expire avant de rendre quoi que ce soit.

    Aucun de ces trois cas ne se voit dans un catalogue. Celui-ci fait donc un
    vrai appel, le plus petit possible, et rapporte ce qui revient.

    Ce que ce controle NE dit PAS : un modele qui repond ici peut tres bien
    echouer sur une demande de quatre mille jetons, parce que le plafond par
    minute n'est pas le meme. Il mesure « ce modele repond », pas « ce modele
    suffit ».

    Il consomme du quota — un appel par identifiant declare — et n'est donc
    lance que sur demande explicite.
    """
    from . import llm
    from .http import HttpErreur

    lignes: List[Dict[str, Any]] = []
    for fournisseur in config.active_providers():
        # Un identifiant peut servir plusieurs roles : on ne l'essaie qu'une
        # fois, et on dit quels roles en dependent.
        par_modele: Dict[str, List[str]] = {}
        for role, identifiant in sorted(fournisseur.models.items()):
            if identifiant:
                par_modele.setdefault(identifiant, []).append(role)
        for identifiant, roles in sorted(par_modele.items()):
            ligne = {"fournisseur": fournisseur.name, "modele": identifiant,
                     "roles": roles, "etat": "", "detail": "", "latence": 0.0}
            debut = time.time()
            try:
                reponse = llm.essai_direct(fournisseur, identifiant,
                                           timeout=timeout)
                ligne["etat"] = "repond" if reponse else "vide"
                ligne["detail"] = reponse[:60]
            except HttpErreur as exc:
                ligne["etat"] = _nommer_le_refus(exc)
                # « HttpErreur » ecrit deja « HTTP 402 : ... » dans son
                # message : le repeter donnait « HTTP 402 — HTTP 402 : ... »
                # sur chaque ligne, et la moitie de la largeur d'un ecran de
                # telephone partait en doublon.
                message = str(exc)
                prefixe = "HTTP {} : ".format(exc.statut)
                if message.startswith(prefixe):
                    message = message[len(prefixe):]
                ligne["detail"] = "HTTP {} — {}".format(
                    exc.statut, message[:88])
            except Exception as exc:  # reseau coupe, DNS, TLS
                ligne["etat"] = "injoignable"
                ligne["detail"] = "{} : {}".format(type(exc).__name__,
                                                   str(exc)[:80])
            ligne["latence"] = round(time.time() - debut, 2)
            lignes.append(ligne)
    return {"essais": lignes,
            "repondent": [l for l in lignes if l["etat"] == "repond"],
            "muets": [l for l in lignes if l["etat"] != "repond"]}


def reparer_modeles(timeout: int = 30) -> Dict[str, Any]:
    """Remplace chaque identifiant mort par un qui REPOND, et le retient.

    « essayer_modeles » mesure. Celui-ci agit sur la mesure, et seulement sur
    elle : journal d'un utilisateur, le 15/09/2026, vingt modeles sur
    vingt-sept ne repondaient pas. Six portaient un identifiant que leur
    fournisseur ne connait plus — le reste etait du quota, du credit epuise
    ou une panne, qui ne se reparent pas en changeant de modele.

    Pourquoi reparer plutot que corriger config.py : les catalogues bougent
    toutes les quelques semaines, et chacun differe d'un compte a l'autre.
    NVIDIA LISTE « writer/palmyra-creative-122b » dans son catalogue public,
    et cette cle-la recoit 404 en le demandant. Un identifiant recopie d'un
    catalogue public repare la panne d'un compte, pas celle du compte voisin.
    L'usine essaie donc, chez CE compte, et garde ce qui a repondu.

    Chaque remplacant est APPELE avant d'etre retenu. Sans cela on
    remplacerait un identifiant mort par un autre, ce qui ne se verrait qu'a
    la fabrication suivante.
    """
    from . import llm, modeles as module_modeles
    from .http import HttpErreur

    repares: List[Dict[str, Any]] = []
    sans_recours: List[Dict[str, Any]] = []
    for fournisseur in config.active_providers():
        if fournisseur.local:
            continue
        servis = None
        # Ce qui a REPONDU chez ce fournisseur pendant cette reparation. On a
        # deja paye l'appel : s'en resservir ne coute rien.
        confirmes: List[str] = []
        restants: List[tuple] = []
        for role, identifiant in sorted(fournisseur.models.items()):
            if not identifiant:
                continue
            actuel = module_modeles.modele_effectif(fournisseur, role)
            try:
                llm.essai_direct(fournisseur, actuel, timeout=timeout)
                if actuel not in confirmes:
                    confirmes.append(actuel)
                continue  # il repond : rien a reparer
            except HttpErreur as exc:
                if not llm._modele_inconnu(exc):
                    # Quota, credit, panne : changer de modele n'y peut rien,
                    # et le faire masquerait la vraie cause.
                    continue
            except Exception:
                continue
            if servis is None:
                servis = module_modeles.catalogue(fournisseur) or []
            candidats = [m for m in servis if m != actuel]
            trouve, repli = "", False
            # Huit essais, pas quatre. Le classement par role met les gros
            # modeles en tete et un palier gratuit n'en sert aucun : quatre
            # essais partaient tous dessus sans jamais atteindre le petit
            # modele qui, lui, repond. Chaque essai est un vrai appel, d'ou
            # une borne — mais elle doit laisser sortir du haut du classement.
            for _ in range(8):
                candidat = module_modeles.choisir(candidats, role)
                if not candidat:
                    break
                candidats = [m for m in candidats if m != candidat]
                try:
                    llm.essai_direct(fournisseur, candidat, timeout=timeout)
                except Exception:
                    continue
                trouve = candidat
                if candidat not in confirmes:
                    confirmes.append(candidat)
                break
            if trouve:
                module_modeles.retenir(fournisseur.name, role, trouve)
                repares.append({"fournisseur": fournisseur.name, "role": role,
                                "avant": actuel, "apres": trouve,
                                "repli": repli})
            else:
                restants.append((role, actuel))

        # SECONDE PASSE, une fois le fournisseur entier essaye : un role sans
        # solution reprend un modele qui a DEJA repondu ici meme.
        #
        # Elle est separee parce que l'ordre des roles decidait du sort.
        # Rapport du 15/09/2026 : « gemini / costaud » repartait sans
        # remplacant alors que « long » et « standard » — partis du MEME
        # identifiant mort — venaient d'en trouver un. Le classement par role
        # met les gros modeles en tete, le palier gratuit ne les sert pas, et
        # les quatre essais partaient tous dessus. Comme « costaud » passe
        # avant les deux autres dans l'ordre alphabetique, rien n'avait encore
        # repondu quand son tour est venu : un repli lu au fil de l'eau ne
        # l'aurait pas sauve.
        #
        # Ce n'est pas le meilleur modele pour ce role — c'en est un qui
        # MARCHE, ce qui vaut mieux qu'un mort. Le rapport le dit.
        for role, actuel in restants:
            secours = next((m for m in confirmes if m != actuel), "")
            if secours:
                module_modeles.retenir(fournisseur.name, role, secours)
                repares.append({"fournisseur": fournisseur.name, "role": role,
                                "avant": actuel, "apres": secours,
                                "repli": True})
            else:
                sans_recours.append({"fournisseur": fournisseur.name,
                                     "role": role, "modele": actuel})
    return {"repares": repares, "sans_recours": sans_recours}


def _nommer_le_refus(exc: Any) -> str:
    """Le genre de refus, en un mot, parce que le geste a faire en depend."""
    from . import llm

    if llm._modele_inconnu(exc):
        return "inconnu"
    statut = getattr(exc, "statut", 0)
    # Statut 0 : la requete n'est jamais partie (serveur local eteint, DNS,
    # TLS). Ce n'est pas un refus du modele, et le confondre avec un refus
    # ferait chercher une cle la ou il faut demarrer un serveur.
    if not statut:
        return "injoignable"
    if statut == 200:
        # Le service a repondu : ce n'est ni une panne ni un refus. Le modele
        # marche, il lui faut seulement plus de place pour conclure.
        return "raisonnement seul"
    if statut in (401, 403):
        return "cle refusee"
    if statut == 402:
        return "credit epuise"
    if statut == 429:
        return "quota atteint"
    if statut >= 500:
        return "panne du service"
    return "refus"


def etat_installation(avec_reseau: bool = True,
                      avec_locaux: bool = True,
                      avec_modeles: bool = False) -> Dict[str, Any]:
    """Tout ce que « docteur » constate, en donnees.

    Les deux drapeaux existent parce que ces deux controles SORTENT sur le
    reseau : les tests ne doivent pas dependre d'une connexion, et le
    tableau de bord ne doit pas les refaire a chaque rafraichissement.
    """
    # D'abord la base : c'est le seul constat dont depend la possibilite meme
    # de constater. Quand elle est illisible, « docteur » mourait comme toutes
    # les autres commandes — alors que c'est precisement la commande qu'on
    # lance quand plus rien ne marche.
    base = store.diagnostic_base()
    fournisseurs = llm.diagnostic(compteurs=not base)
    distants = [f for f in fournisseurs if f["disponible"] and not f["local"]]

    etat: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "workdir": str(config.WORKDIR),
        "env_present": config.ENV_PATH.exists(),
        "node": verification.node_disponible(),
        "espace": espace_libre(),
        "telephone": telephone.etat(),
        "fournisseurs": fournisseurs,
        "distants_prets": len(distants),
        "pool": pool_cles.resume(),
        "base": base,
        "consommation": {} if base else store.stats_fournisseurs(),
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
    # Une base illisible passe avant les fournisseurs : dix cles valides ne
    # servent a rien si l'usine ne peut rien enregistrer.
    if etat.get("base"):
        # « remede » existe parce que le geste ne decoule pas de l'etat :
        # « bloque » conseillait « usine cles » quoi qu'il arrive, et une base
        # cassee ne se repare pas en ajoutant une cle.
        return {"etat": "bloque",
                "message": "Base illisible ({}). Vos produits restent sur le "
                           "disque.".format(etat["base"]),
                "remede": "usine sauvegarde --restaurer archive.zip --oui"}
    if etat["distants_prets"]:
        return {"etat": "pret", "remede": "",
                "message": "{} fournisseur(s) distant(s) pret(s). "
                           "L'usine peut produire.".format(etat["distants_prets"])}
    if etat["locaux"]:
        return {"etat": "local", "remede": "",
                "message": "IA locale detectee : {}. Production hors ligne "
                           "possible, mais comptez plusieurs minutes par "
                           "chapitre.".format(", ".join(etat["locaux"]))}
    return {"etat": "bloque", "remede": "usine cles",
            "message": "Aucun fournisseur pret. Lancez « usine cles »."}
