"""Point d'entree du module : « python3 -m usine ».

C'est la premiere chose qu'on essaie quand le raccourci « usine » n'est pas
encore dans le PATH — juste apres une installation, ou depuis un clone du
depot. Sans ce fichier, Python repond « No module named usine.__main__ »,
ce qui ne dit pas quoi faire.
"""

from __future__ import annotations

import sys

from .cli import principal

if __name__ == "__main__":
    sys.exit(principal())
