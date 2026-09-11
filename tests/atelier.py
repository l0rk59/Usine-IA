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
from pathlib import Path
from typing import Dict

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


def isoler(nom: str) -> Path:
    """Bascule l'usine entiere sur l'atelier du module « nom »."""
    global _COURANT
    from usine.core import config, prompts, reglages, store

    dossier = _ATELIERS.get(nom)
    if dossier is None:
        dossier = Path(tempfile.mkdtemp(prefix="usine-{}-".format(nom)))
        _ATELIERS[nom] = dossier
        atexit.register(shutil.rmtree, str(dossier), True)

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

    _COURANT = nom
    return dossier
