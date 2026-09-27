"""Un atelier par module de test.

Le defaut repare ici ne faisait echouer aucun test — c'est justement ce qui
le rendait durable. Chaque module posait bien son propre USINE_HOME :

    os.environ["USINE_HOME"] = tempfile.mkdtemp(prefix="usine-ab-")

mais `config` resout ses chemins UNE fois, au premier import, et
`unittest discover` importe TOUS les modules de test avant d'en executer un
seul. Le premier import gagnait donc pour toute la suite : les quinze
modules partageaient une base, un dossier de produits, un cache. Les tests
passaient, et rien ne garantissait plus qu'un test ne s'appuyait pas sur ce
qu'un autre avait laisse derriere lui — ni qu'il ne le detruisait pas. Un
test lance seul et un test lance dans la suite ne voyaient pas le meme
monde, ce qui est la pire facon de perdre une journee.

La bascule doit donc avoir lieu au moment ou unittest passe a un module, pas
a l'import. C'est exactement ce qu'est `setUpModule`. Chaque module de test
appelle :

    def setUpModule():
        atelier.isoler("ab")

Ce qu'il faut faire tomber au passage, ce ne sont pas seulement les chemins :
la connexion SQLite ouverte, les drapeaux « schema deja cree » et les caches
de reglages et de prompts parlent tous de l'atelier precedent.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict

# --------------------------------------------------------------------------
# Aucun test ne sort sur le reseau
# --------------------------------------------------------------------------
#
# La regle est dans CLAUDE.md depuis le debut, et rien ne la faisait respecter.
# Mesure du 15/09/2026 : « test_equipe » appelait cinq services publics reels
# — hn.algolia.com, fr.wikipedia.org, api.stackexchange.com, openlibrary.org,
# www.reddit.com — a chaque execution de la suite.
#
# Personne ne l'avait vu parce que l'echec coutait zero seconde : sans reseau,
# les cinq appels rataient instantanement et le test passait quand meme, en
# exercant un chemin degrade qu'il ne pretendait pas tester. Le jour ou les
# reessais sont arrives, le meme test est passe de 2,6 a 30,8 secondes — et
# c'est la seule raison pour laquelle la violation s'est vue.
#
# Un test qui sort sur le reseau ne mesure pas ce qu'il croit : il mesure
# l'humeur d'un service gratuit, il echoue dans un train, et il est lent.
#
# Le garde-fou coupe a la DERNIERE porte — « urlopen » — et non a
# « http.requete » : un module qui appellerait urllib directement passerait a
# cote d'un controle pose plus haut.


class SortieReseauInterdite(RuntimeError):
    """Un test a tente un appel vers une machine distante."""


# La boucle locale n'est pas « le reseau ». Les tests du tableau de bord
# demarrent leur propre serveur et lui parlent ; ceux de l'IA locale parlent a
# un ollama sur le port 11434. Les refuser ferait crier le garde-fou sur
# quarante tests parfaitement legitimes — et un controle qui signale a tort
# finit desactive, ce qui vaut moins que pas de controle du tout.
_MACHINES_LOCALES = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]")


def _est_local(url: str) -> bool:
    if url.startswith("file:"):
        return True
    reste = url.split("//", 1)[-1]
    hote = reste.split("/", 1)[0].split("@")[-1]
    return hote.split(":")[0].strip("[]") in tuple(
        m.strip("[]") for m in _MACHINES_LOCALES)


def _refuser(requete, *args, **kwargs):
    url = str(getattr(requete, "full_url", requete))
    if _est_local(url):
        return _urlopen_reel(requete, *args, **kwargs)
    raise SortieReseauInterdite(
        "Aucun test ne sort sur le réseau, et celui-ci a tenté « {} ».\n"
        "Injectez la réponse : « tests/simulateur.py » pour le routeur, ou "
        "remplacez « marche.sonder », « http.requete » ou "
        "« images.image_pollinations » selon le cas.".format(url[:120]))


_urlopen_reel = urllib.request.urlopen
urllib.request.urlopen = _refuser


RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# Un module rappele deux fois (module lance seul, puis dans la suite) doit
# retrouver SON atelier, pas un neuf.
_ATELIERS: Dict[str, Path] = {}

_COURANT = ""


def courant() -> str:
    """Nom du module dont l'atelier est actuellement en place."""
    return _COURANT


def attendre_les_travaux(delai: float = 120.0) -> None:
    """Attend la fin des fils de travail du tableau de bord encore vivants.

    Au-dela du delai, on le DIT sur la sortie d'erreur plutot que de
    continuer en silence : un fil fantome qui ecrit dans l'atelier suivant
    fait echouer un test qui n'y est pour rien, et c'est ce message qui
    permet de remonter a sa source.
    """
    import sys
    import threading

    serveur = sys.modules.get("usine.web.serveur")
    if serveur is None:
        return
    fin = time.monotonic() + delai
    for fil in threading.enumerate():
        if fil.name != serveur.FIL_DE_TRAVAIL or fil is threading.current_thread():
            continue
        fil.join(max(0.0, fin - time.monotonic()))
        if fil.is_alive():
            sys.stderr.write("[atelier] un travail du tableau de bord tourne "
                             "encore apres {:.0f} s : il ecrira dans "
                             "l'atelier suivant.\n".format(delai))


def isoler(nom: str) -> Path:
    """Bascule l'usine entiere sur l'atelier du module « nom »."""
    global _COURANT
    from usine.core import config, prompts, reglages, store

    dossier = _ATELIERS.get(nom)
    if dossier is None:
        dossier = Path(tempfile.mkdtemp(prefix="usine-{}-".format(nom)))
        _ATELIERS[nom] = dossier
        atexit.register(shutil.rmtree, str(dossier), True)

    # Un travail que le module precedent a lance depuis le tableau de bord
    # tourne peut-etre encore : il survit a l'arret du serveur. Le laisser
    # courir, c'est le laisser ecrire dans CET atelier-ci, avec le simulateur
    # du module suivant — deux echecs intermittents en integration continue,
    # « no such table » puis un produit compte a 3 appels pour 11.
    attendre_les_travaux()

    # Fermer AVANT de deplacer les chemins : sinon on ferme la connexion du
    # nouvel atelier en croyant fermer celle de l'ancien. close() fait aussi
    # tomber les drapeaux de schema, chez store et chez ceux qui se sont
    # inscrits par « oublier_avec_la_base ».
    store.close()

    os.environ["USINE_HOME"] = str(dossier)
    config.WORKDIR = dossier
    config.PRODUITS_DIR = dossier / "produits"
    config.CACHE_DIR = dossier / "cache"
    config.LOG_DIR = dossier / "logs"
    config.DB_PATH = dossier / "usine.db"
    config.ensure_dirs()

    # Ces caches gardent le contenu de fichiers qui vivent DANS l'atelier.
    reglages._cache = {}
    prompts._cache_agents = None
    prompts._cache_modeles = None

    # Le simulateur compte les relectures deja rendues pour savoir si la
    # premiere passe doit etre severe. Ce compteur parle de l'atelier
    # precedent, comme les caches ci-dessus.
    try:
        from tests import simulateur

        simulateur.reinitialiser()
    except ImportError:      # atelier utilise hors de la suite
        pass

    _COURANT = nom
    return dossier
