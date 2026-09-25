"""La fiche technique de l'appareil : ce qu'il a, et ce qui lui manque.

« usine docteur » dit si l'usine peut produire maintenant. Ce module repond a
une autre question, et c'est celle qui manquait : **qu'est-ce qui devrait etre
dans install.sh pour que cet appareil-la marche sans bricolage ?**

La difference compte. Le docteur s'adresse a quelqu'un qui a un probleme ;
cette fiche s'adresse a quelqu'un qui veut corriger l'installation pour tout
le monde. Elle sort en Markdown, se pousse sur le depot, et devient une
donnee : « voila un vrai telephone, voila ce qui lui manquait ».

Ce qui est mesure, et jamais suppose : ce qui repond, ce qui existe, ce qui
est lisible. Un binaire absent est ecrit absent. Une chose qu'on ne peut pas
verifier ici est ecrite « non verifiable », pas « absente » — se tromper de
sens ferait ajouter a install.sh un paquet qui n'a jamais manque.

Aucune cle n'entre dans cette fiche. Elle est faite pour etre poussee sur un
depot public : ce qui s'y trouve est ce qu'on accepte de rendre public.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from . import config, telephone, verification

# Ce dont l'usine se sert, avec ce que son absence coute VRAIMENT. Le second
# membre est le plus important : « installez nodejs » sans dire pourquoi ne
# fait installer personne.
BINAIRES = (
    ("python3", "obligatoire", "l'usine entiere"),
    ("git", "recommande", "« usine maj » met a jour sans retelecharger"),
    ("node", "optionnel",
     "le JavaScript genere par la chaine « logiciel » n'est verifie qu'en "
     "mode degrade : une erreur de syntaxe fine passe"),
    ("termux-notification", "optionnel",
     "aucune notification quand un produit sort, pendant que l'ecran est "
     "eteint"),
    ("termux-battery-status", "optionnel",
     "l'usine continue ne peut pas s'arreter sur batterie faible"),
    ("termux-open", "optionnel", "impossible d'ouvrir un PDF depuis le menu"),
    ("termux-share", "optionnel", "impossible de partager une archive"),
    ("termux-wake-lock", "optionnel",
     "Android suspend une fabrication longue quand l'ecran s'eteint"),
    ("ollama", "optionnel", "pas de production hors ligne"),
    ("curl", "optionnel", "confort de diagnostic uniquement"),
)

# Modules de la bibliotheque standard dont l'usine ne peut pas se passer.
# Termux les livre avec python, SAUF quand le paquet a ete installe a la main
# ou que l'image est ancienne : sqlite3 et ssl manquent alors, et l'erreur
# qu'on obtient a l'usage ne dit pas quoi installer.
MODULES = ("sqlite3", "ssl", "zlib", "zipfile", "urllib.request", "hashlib",
           "unicodedata", "secrets", "threading")


def _binaire(nom: str) -> Optional[str]:
    return shutil.which(nom)


def _version_binaire(nom: str) -> str:
    """Version d'un outil, ou "" — sans jamais bloquer.

    Un sous-processus qui ne rend pas la main gele l'usine sur un telephone.
    Trois secondes suffisent a tout ce qu'on interroge ici.
    """
    chemin = _binaire(nom)
    if not chemin:
        return ""
    for option in ("--version", "-v", "version"):
        try:
            sortie = subprocess.run([chemin, option], capture_output=True,
                                    timeout=3, text=True)
        except (OSError, subprocess.SubprocessError):
            continue
        # Beaucoup d'outils ecrivent leur version sur la sortie d'erreur.
        texte = (sortie.stdout or "") or (sortie.stderr or "")
        premiere = texte.strip().splitlines()[0] if texte.strip() else ""
        # Un refus d'option n'est pas une version. Les outils termux-* n'ont
        # pas d'option de version : la fiche du telephone affichait
        # « getopt: unrecognized option `--version' » dans la colonne
        # Version. Et on s'arrete la, sans essayer l'option suivante :
        # « termux-open version » ou « termux-share version » pourraient
        # ouvrir ou partager quelque chose sur le telephone.
        if sortie.returncode != 0 and _REFUS_D_OPTION.search(premiere):
            return "(version inconnue)"
        if premiere:
            return premiere[:80]
    return "(version inconnue)"


_REFUS_D_OPTION = re.compile(
    r"unrecognized option|illegal option|invalid option|unknown option|usage:",
    re.IGNORECASE)


def _modules_absents() -> List[str]:
    absents = []
    for nom in MODULES:
        try:
            __import__(nom)
        except ImportError:
            absents.append(nom)
    return absents


def _memoire_mo() -> Optional[int]:
    """RAM totale, lue dans /proc — ou None ailleurs que sous Linux.

    Elle decide ce qu'un modele local peut faire : en dessous de 4 Go, un
    modele de 3 milliards de parametres fait tomber l'application.
    """
    try:
        with open("/proc/meminfo", encoding="utf-8") as fichier:
            for ligne in fichier:
                if ligne.startswith("MemTotal:"):
                    return int(ligne.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def relever() -> Dict[str, Any]:
    """Tout ce qui se mesure sur cet appareil, en donnees."""
    from . import cles as pool_cles

    espace = {}
    try:
        usage = shutil.disk_usage(str(config.WORKDIR))
        espace = {"libre_mo": usage.free // (1024 * 1024),
                  "total_mo": usage.total // (1024 * 1024)}
    except OSError:
        espace = {}

    binaires = []
    for nom, importance, cout in BINAIRES:
        chemin = _binaire(nom)
        binaires.append({
            "nom": nom, "importance": importance, "cout_si_absent": cout,
            "present": bool(chemin),
            "version": _version_binaire(nom) if chemin else "",
        })

    # Les cles ne sortent JAMAIS. On dit combien il y en a, pas lesquelles.
    fournisseurs = []
    for fournisseur in config.PROVIDERS:
        lot = pool_cles.pool(fournisseur.name, fournisseur.api_key_env)
        fournisseurs.append({
            "nom": fournisseur.name,
            "local": fournisseur.local,
            "sans_cle": fournisseur.keyless,
            "variable": fournisseur.api_key_env,
            "nb_cles": len(lot),
        })

    return {
        "releve_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "python_complet": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "plateforme": platform.platform(),
        "machine": platform.machine(),
        "systeme": platform.system(),
        "termux": telephone.etat(),
        "prefix": os.environ.get("PREFIX", ""),
        # « termux-setup-storage » cree ce dossier, et rien d'autre ne le cree.
        # C'est donc la mesure, pas une supposition.
        "stockage_partage": os.path.isdir(
            os.path.join(os.path.expanduser("~"), "storage")),
        "workdir": str(config.WORKDIR),
        "espace": espace,
        "memoire_mo": _memoire_mo(),
        "modules_absents": _modules_absents(),
        "binaires": binaires,
        "fournisseurs": fournisseurs,
        "node": verification.node_disponible(),
    }


def _manques(releve: Dict[str, Any]) -> List[Dict[str, str]]:
    """Ce qui manque, et la commande qui le pose. Rien d'autre.

    Une fiche qui enumere trente lignes vertes et cache la seule rouge ne sert
    a personne : cette liste est ce qu'on lit en premier.
    """
    termux = bool(releve["termux"].get("termux"))
    poser = "pkg install" if termux else "apt install"
    manques = []
    for module in releve["modules_absents"]:
        manques.append({
            "quoi": "module Python « {} »".format(module),
            "gravite": "bloquant",
            "commande": "{} python".format(poser),
            "pourquoi": "l'usine ne demarre pas sans lui",
        })
    paquets = {"node": "nodejs-lts", "ollama": "ollama", "git": "git",
               "curl": "curl"}
    for binaire in releve["binaires"]:
        if binaire["present"] or binaire["importance"] == "obligatoire":
            continue
        if binaire["nom"].startswith("termux-"):
            commande = "{} termux-api".format(poser)
            if not termux:
                continue  # hors Termux, ces outils n'existent pas : rien a dire
        else:
            commande = "{} {}".format(poser,
                                      paquets.get(binaire["nom"], binaire["nom"]))
        manques.append({
            "quoi": binaire["nom"],
            "gravite": binaire["importance"],
            "commande": commande,
            "pourquoi": binaire["cout_si_absent"],
        })
    if termux and not releve["stockage_partage"]:
        manques.append({
            "quoi": "acces au stockage partage",
            "gravite": "recommande",
            "commande": "termux-setup-storage",
            "pourquoi": "impossible d'enregistrer les produits dans /sdcard, "
                        "donc de les recuperer depuis une autre application",
        })
    if not any(f["nb_cles"] for f in releve["fournisseurs"]):
        # La fiche du telephone disait « bloquant » avec ollama installe, et
        # « ne suffit pas a un produit entier » d'un quota que personne ne
        # publie. Elle dit ce qui reste, avec les mots de la fiche du
        # fournisseur ; la fiche ne sonde aucun serveur, donc elle ne sait
        # pas si ollama sert un modele et le dit.
        ollama = any(b["nom"] == "ollama" and b["present"]
                     for b in releve["binaires"])
        manques.append({
            "quoi": "une cle API",
            "gravite": "recommande" if ollama else "bloquant",
            "commande": "usine cles",
            "pourquoi": (
                "sans cle, l'usine produit avec ollama s'il sert un modele "
                "(« ollama pull »), en plusieurs minutes par chapitre"
                if ollama else
                "sans cle, il ne reste que le palier anonyme de Pollinations : "
                "quota non publie, partage par adresse IP — assez pour "
                "essayer, pas pour produire en volume"),
        })
    return manques


def en_markdown(releve: Optional[Dict[str, Any]] = None) -> str:
    """La fiche, prete a etre poussee sur le depot."""
    releve = releve or relever()
    termux = releve["termux"]
    manques = _manques(releve)

    lignes = [
        "# Fiche technique de l'appareil",
        "",
        "Relevee par `usine specs` le {}.".format(releve["releve_le"]),
        "",
        "Ce document repond a une question que `usine docteur` ne pose pas :",
        "**qu'est-ce qui devrait etre dans `install.sh` pour que cet appareil",
        "marche sans bricolage ?** Aucune cle API n'y figure.",
        "",
        "## Ce qui manque",
        "",
    ]
    if not manques:
        lignes += ["Rien. Cet appareil a tout ce que l'usine sait utiliser.", ""]
    else:
        lignes += ["| Ce qui manque | Gravite | Pour l'avoir | Ce que son absence coute |",
                   "|---|---|---|---|"]
        for manque in manques:
            lignes.append("| {} | {} | `{}` | {} |".format(
                manque["quoi"], manque["gravite"], manque["commande"],
                manque["pourquoi"]))
        lignes.append("")

    lignes += [
        "## L'appareil",
        "",
        "| | |",
        "|---|---|",
        "| Systeme | {} |".format(releve["plateforme"]),
        "| Architecture | {} |".format(releve["machine"]),
        "| Python | {} |".format(releve["python_complet"]),
        "| Termux | {} |".format("oui" if termux.get("termux") else "non"),
        "| termux-api | {} |".format("present" if termux.get("api") else "absent"),
    ]
    if releve["memoire_mo"]:
        lignes.append("| Memoire vive | {} Mo |".format(releve["memoire_mo"]))
    if releve["espace"]:
        lignes.append("| Disque libre | {} Mo sur {} Mo |".format(
            releve["espace"]["libre_mo"], releve["espace"]["total_mo"]))
    if termux.get("batterie"):
        lignes.append("| Batterie | {} %{} |".format(
            termux["batterie"].get("niveau"),
            " (en charge)" if termux["batterie"].get("en_charge") else ""))
    lignes += ["| Dossier de travail | `{}` |".format(releve["workdir"]), ""]

    lignes += ["## Outils", "",
               "| Outil | Etat | Version | Si absent |", "|---|---|---|---|"]
    for binaire in releve["binaires"]:
        lignes.append("| `{}` | {} | {} | {} |".format(
            binaire["nom"],
            "present" if binaire["present"] else "**absent**",
            binaire["version"] or "—",
            "—" if binaire["present"] else binaire["cout_si_absent"]))
    lignes.append("")

    lignes += ["## Fournisseurs configures", "",
               "Nombre de cles seulement : aucune valeur n'est ecrite ici.",
               "",
               "| Fournisseur | Variable | Cles | Genre |", "|---|---|---|---|"]
    for fournisseur in releve["fournisseurs"]:
        genre = ("local" if fournisseur["local"]
                 else "sans cle" if fournisseur["sans_cle"] else "cle API")
        lignes.append("| {} | `{}` | {} | {} |".format(
            fournisseur["nom"], fournisseur["variable"] or "—",
            fournisseur["nb_cles"], genre))
    lignes += [
        "",
        "## Modules de la bibliotheque standard",
        "",
        "L'usine n'utilise que la bibliotheque standard. Ces modules-la sont "
        "ceux dont elle ne peut pas se passer :",
        "",
        "```",
        ", ".join(MODULES),
        "```",
        "",
    ]
    if releve["modules_absents"]:
        lignes += ["**Absents sur cet appareil : {}.** C'est bloquant.".format(
            ", ".join(releve["modules_absents"])), ""]
    else:
        lignes += ["Tous presents.", ""]
    return "\n".join(lignes)
