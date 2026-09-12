"""Le journal sur disque d'une production.

« config.LOG_DIR » etait cree a chaque demarrage et n'a jamais rien recu. Le
dossier existait, la promesse aussi, et rien dedans.

Ce que cela coutait : l'usine continue tourne des heures sur un telephone, en
ecrivant dans un terminal dont Android reclame le tampon. Une niche qui echoue
a trois heures du matin ne laissait donc aucune trace lisible — la base retient
bien les etapes de chaque produit, mais pas ce qui s'est passe ENTRE eux : la
niche sautee, le fournisseur tombe, l'arret sur batterie faible.

Trois contraintes viennent du telephone, et chacune a dicte une decision.

  - **Le processus peut mourir sans preavis.** Le fichier est donc ouvert et
    referme a chaque ligne, au lieu d'une poignee gardee ouverte : un tampon
    perdrait exactement les lignes qui expliquent l'arret.
  - **Le disque est fini.** Un fichier par jour, les plus anciens effaces
    au-dela de JOURS_GARDES, et un fichier qui depasse TAILLE_MAX repart de
    zero. Un journal qui remplit le telephone fait echouer la fabrication
    qu'il etait cense documenter.
  - **Un jour est une date.** Il vient d'un argument de ligne de commande, et
    le poser tel quel dans un nom de fichier laissait « ../.. » designer un
    fichier hors du dossier des journaux.
  - **Une cle ne doit jamais toucher le disque.** Chaque ligne passe par
    « securite.expurger », et la premiere fois qu'un secret est reconnu, le
    journal le dit : masquer sans prevenir laisserait l'utilisateur avec une
    cle exposee quelque part et aucune raison de la renouveler.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

from . import config, securite

# Au-dela, on efface. Deux semaines couvrent « qu'est-ce qui s'est passe la
# nuit derniere » et « pourquoi ai-je moins de produits que prevu ce mois-ci »,
# ce qui est tout ce qu'on demande a un journal de fabrication.
JOURS_GARDES = 14

# Une ligne plus longue n'apprend rien de plus et remplit le fichier.
LIGNE_MAX = 500

_secret_signale = False


# Un journal d'une journee entiere tient largement dessous. Au-dela, on repart
# d'un fichier neuf plutot que de laisser grossir : sur un telephone, un
# fichier de trace qui remplit le disque fait echouer la fabrication qu'il
# documentait — meme contrainte que le nombre de jours gardes, a l'autre bout.
TAILLE_MAX = 2 * 1024 * 1024

_JOUR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fichier(jour: Optional[str] = None) -> Path:
    """Chemin du journal d'une journee.

    Le jour vient d'un argument de ligne de commande, donc d'une chaine
    libre : le poser tel quel dans un nom de fichier laissait
    « ../../quelque-chose » designer un fichier hors du dossier des journaux,
    que « nettoyer » aurait ensuite pu effacer. Un jour est une date et rien
    d'autre ; le reste retombe sur aujourd'hui.
    """
    if not jour or not _JOUR.match(jour):
        jour = time.strftime("%Y-%m-%d")
    return config.LOG_DIR / "usine-{}.log".format(jour)


def ecrire(message: str, categorie: str = "") -> None:
    """Ajoute une ligne au journal du jour. N'echoue jamais.

    Un journal qui empeche de produire est pire qu'un journal absent : c'est
    une trace, pas une fonction metier. Toute erreur d'ecriture est donc
    avalee — disque plein, /sdcard demonte, permission retiree.
    """
    global _secret_signale
    texte = (message or "").strip()
    if not texte:
        return
    propre = securite.expurger(texte)[:LIGNE_MAX]
    if securite.contient_un_secret(texte) and not _secret_signale:
        # Une seule fois par session : repeter l'alerte a chaque ligne la
        # rendrait invisible, et c'est une alerte qu'il faut lire.
        _secret_signale = True
        propre += ("  [!] une cle a ete masquee ici : elle a circule dans un "
                   "message, renouvelez-la")
    ligne = "{} {}{}\n".format(time.strftime("%H:%M:%S"),
                               "[{}] ".format(categorie) if categorie else "",
                               propre)
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        chemin = fichier()
        if chemin.exists() and chemin.stat().st_size > TAILLE_MAX:
            # On repart de zero plutot que de couper par le debut : relire un
            # fichier ampute en tete donnerait un journal qui commence au
            # milieu d'une phrase, et c'est la FIN qui interesse.
            chemin.unlink()
        # Ouvert et referme a chaque ligne, ce qui est plus couteux qu'une
        # poignee gardee ouverte — et c'est le but. Android tue le processus
        # sans preavis, et ce sont precisement les dernieres lignes qui
        # expliquent l'arret : un tampon les emporterait. La fermeture du
        # bloc vide le tampon, un « flush » explicite n'ajouterait rien.
        with open(chemin, "a", encoding="utf-8") as sortie:
            sortie.write(ligne)
    except OSError:
        pass


def relire(lignes: int = 40, jour: Optional[str] = None) -> List[str]:
    """Les dernieres lignes du journal, sans charger tout le fichier.

    Un journal de plusieurs heures se lit par la fin — c'est la que se trouve
    ce qui vient d'arriver.
    """
    chemin = fichier(jour)
    if not chemin.exists():
        return []
    try:
        contenu = chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [l for l in contenu.splitlines() if l][-max(1, lignes):]


def jours_disponibles() -> List[str]:
    """Les journees pour lesquelles un journal existe, la plus recente d'abord."""
    try:
        fichiers = sorted(config.LOG_DIR.glob("usine-*.log"), reverse=True)
    except OSError:
        return []
    return [f.stem.replace("usine-", "") for f in fichiers]


def nettoyer(jours_gardes: int = JOURS_GARDES) -> int:
    """Efface les journaux trop anciens. Rend le nombre de fichiers supprimes.

    Appele au demarrage d'une production : c'est le seul moment ou l'on sait
    qu'on va ecrire, donc le seul ou il vaut la peine de faire de la place.
    """
    supprimes = 0
    for jour in jours_disponibles()[max(0, jours_gardes):]:
        try:
            fichier(jour).unlink()
            supprimes += 1
        except OSError:
            pass
    return supprimes
