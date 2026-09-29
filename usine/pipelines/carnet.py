"""Le carnet d'une fabrication : ce qui est deja ecrit, sur le disque.

Mesure du 13/09/2026. Reseau coupe au sixieme appel d'un ebook de huit
chapitres : il restait sur le disque **un seul fichier**, « plan.json ». Le
plan, l'avant-propos et le premier chapitre — relu, controle, corrige — avaient
ete produits, payes, puis perdus avec le processus. La seule reprise possible
etait de tout relancer.

Le cache des reponses amortit une partie de cette perte, mais pas toute : une
section passe par plusieurs appels enchaines (redaction, controle, correction,
relecture), et chaque passe forge une invite qui depend de la precedente. Une
invite qui change d'un mot rate son entree de cache. Ce qu'il faut garder, ce
n'est donc pas l'appel : c'est la SECTION FINIE.

D'ou ce carnet. Chaque section est ecrite des qu'elle est terminee. Une
relance retrouve ce qui existe et ne refait que le reste — quelle que soit la
raison de l'arret : quota, reseau, batterie, processus tue par Android.

Le carnet vit dans le dossier du produit et non dans la base : un produit se
copie, s'archive et se restaure par son dossier, et une reprise doit survivre
a une base remise a zero.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NOM = "carnet.json"

# Au-dela, on refuse de relire : un carnet de cette taille n'a pas ete ecrit
# par l'usine, et le charger sur un telephone couterait plus que de refaire.
TAILLE_MAX = 40 * 1024 * 1024


def chemin(dossier: Path) -> Path:
    return Path(dossier) / NOM


def lire(dossier: Path) -> Dict[str, Any]:
    """Rend le carnet du produit, ou un carnet vide.

    Un carnet illisible est traite comme absent : on refait le travail. C'est
    plus cher qu'une reprise et infiniment moins cher qu'un produit assemble a
    partir de morceaux qu'on n'a pas su relire.
    """
    fichier = chemin(dossier)
    try:
        if not fichier.exists() or fichier.stat().st_size > TAILLE_MAX:
            return {"sections": {}}
    except OSError:
        return {"sections": {}}
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {"sections": {}}
    if not isinstance(charge, dict) or not isinstance(charge.get("sections"), dict):
        return {"sections": {}}
    return charge


def _ecrire(dossier: Path, carnet: Dict[str, Any]) -> None:
    """Ecrit le carnet d'un bloc, par un fichier temporaire.

    Le processus meurt sans preavis sur un telephone. Ecrire par-dessus le
    carnet expose a mourir au milieu : le carnet devient illisible, et la
    reprise repart de zero — exactement ce qu'il devait empecher.
    """
    fichier = chemin(dossier)
    # Un nom propre a l'ecrivain : deux fils qui partageaient « .json.tmp »
    # se le deplacaient l'un a l'autre, et le second mourait sur « No such
    # file ». La reprise est verrouillee par produit ; ceci est la seconde
    # ceinture, pour ce qui ecrirait le carnet par un autre chemin.
    provisoire = fichier.with_suffix(".json.{}-{}.tmp".format(
        os.getpid(), threading.get_ident()))
    provisoire.write_text(json.dumps(carnet, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    provisoire.replace(fichier)


def noter_section(dossier: Path, cle: str, titre: str, corps: str,
                  meta: Optional[Dict[str, Any]] = None) -> None:
    """Enregistre une section terminee. A appeler des qu'elle l'est.

    « Des qu'elle l'est » et pas a la fin de la boucle : le seul moment ou
    l'on est sur de pouvoir ecrire, c'est maintenant.
    """
    carnet = lire(dossier)
    carnet["sections"][str(cle)] = {
        "titre": titre, "corps": corps, "meta": meta or {},
    }
    _ecrire(dossier, carnet)


def section(dossier: Path, cle: str) -> Optional[Tuple[str, str]]:
    """Rend (titre, corps) d'une section deja ecrite, ou None."""
    entree = lire(dossier)["sections"].get(str(cle))
    if not isinstance(entree, dict):
        return None
    corps = entree.get("corps")
    titre = entree.get("titre")
    if not isinstance(corps, str) or not corps.strip() or not isinstance(titre, str):
        return None
    return titre, corps


def noter_plan(dossier: Path, plan: Dict[str, Any]) -> None:
    """Garde le plan : sans lui, une reprise ne sait meme pas quoi refaire."""
    carnet = lire(dossier)
    carnet["plan"] = plan
    _ecrire(dossier, carnet)


def plan(dossier: Path) -> Optional[Dict[str, Any]]:
    garde = lire(dossier).get("plan")
    return garde if isinstance(garde, dict) and garde.get("chapitres") else None


def compte(dossier: Path) -> int:
    return len(lire(dossier)["sections"])


# --------------------------------------------------------------------------
# La commande exacte qui a lance la fabrication
# --------------------------------------------------------------------------
#
# Une reprise doit rejouer la MEME commande. Reconstruire les arguments a
# partir des reglages ne suffit pas : un reglage par defaut peut avoir change
# entre-temps, et la reprise fabriquerait alors un second produit dans le
# dossier du premier — meme dossier, autre ton, autre longueur.
#
# Seul le point d'entree connait la commande telle qu'elle a ete tapee, et
# seul le pipeline connait le dossier ou l'ecrire. D'ou ce relais : un mot
# retenu d'un cote, relu de l'autre. C'est la seule variable de module de ce
# fichier, et elle existe pour cette raison-la.
_COMMANDE: List[str] = []


def retenir_commande(argv: List[str]) -> None:
    """Appele par le point d'entree, avant que la fabrication ne commence."""
    global _COMMANDE
    _COMMANDE = [str(a) for a in (argv or [])]


def noter_commande(dossier: Path) -> None:
    """Appele par le pipeline, des que le dossier du produit existe."""
    if not _COMMANDE:
        return
    carnet = lire(dossier)
    carnet["commande"] = list(_COMMANDE)
    _ecrire(dossier, carnet)


def commande(dossier: Path) -> List[str]:
    garde = lire(dossier).get("commande")
    if not isinstance(garde, list):
        return []
    return [str(a) for a in garde]


# --------------------------------------------------------------------------
# Le contexte tel qu'il etait, et la recette pour les autres portes
# --------------------------------------------------------------------------
#
# Mesure du 23/09/2026. La commande ci-dessus vient de « sys.argv », donc de
# la ligne de commande. Or le tableau de bord et l'usine continue fabriquent
# sans en passer par elle :
#
#   usine continue       carnet : ["usine", "demarrer"]
#   tableau de bord      carnet : la derniere commande vue par le processus,
#                        c'est-a-dire « web », ou celle d'un AUTRE produit
#
# « usine reprendre » rejouait donc « usine demarrer --reprendre-id ... » et
# mourait sur « unrecognized arguments » (code 2). Depuis le telephone, le
# bouton « Reprendre » d'un produit coupe par les quotas ne pouvait rien
# reprendre du tout.
#
# Et meme par la ligne de commande, la reprise reconstruisait le contexte
# depuis les arguments : le public, le ton et le volume que le brief avait
# decides n'y etaient pas. Les chapitres repris partaient « auto », d'une
# autre voix que les premiers.
#
# D'ou deux entrees de plus : le contexte RESOLU, tel que la chaine l'a recu
# — il fait foi a la reprise, quelle que soit la porte —, et pour les
# fabrications passees par le catalogue, le type et les options finales.


def noter_fabrication(dossier: Path, contexte: Dict[str, Any],
                      relance: Optional[Dict[str, Any]] = None) -> None:
    carnet = lire(dossier)
    # Aller-retour JSON : une option qui ne s'ecrit pas (un chemin, un objet)
    # ne doit pas rendre le carnet entier illisible a la reprise.
    carnet["contexte"] = json.loads(json.dumps(contexte, default=str))
    if relance:
        carnet["relance"] = json.loads(json.dumps(relance, default=str))
        # La commande vue par le processus n'est pas celle de ce produit.
        carnet.pop("commande", None)
    _ecrire(dossier, carnet)


def contexte_garde(dossier: Path) -> Optional[Dict[str, Any]]:
    garde = lire(dossier).get("contexte")
    return garde if isinstance(garde, dict) and garde.get("sujet") else None


def relance(dossier: Path) -> Optional[Dict[str, Any]]:
    garde = lire(dossier).get("relance")
    if isinstance(garde, dict) and garde.get("type"):
        return garde
    return None
