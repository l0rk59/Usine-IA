#!/usr/bin/env python3
"""Verifie qu'aucune cle d'API ne figure dans les fichiers suivis par git.

Une cle poussee sur un depot public est a renouveler : des robots lisent les
depots en continu. Le fichier « .env », qui les contient, ne doit pas etre
suivi ; aucun autre fichier ne doit en porter une recopiee.

Ce qu'est « une cle » est defini une seule fois, dans
« usine/core/securite.py » : les memes motifs masquent les cles dans le
journal et le tableau de bord. Ils exigent la longueur d'une cle apres le
prefixe, pas le prefixe seul.

Mesure du 23/09/2026 : la CI cherchait « gsk_ » tout court. Le prefixe
figure dans la documentation (« gsk_ab***xyz »), dans l'aide de la ligne de
commande (« GROQ_API_KEY=gsk_... ») et dans les cles factices des tests
(« gsk_secrete »). Le job etait rouge depuis sa creation, le 12/09, sur
quatorze lignes dont aucune n'etait une cle. Un controle toujours rouge
n'est plus lu : il a masque huit jours durant l'echec du job Python 3.9,
qui lui etait reel.

Consequence pour les tests : une cle factice qui a la forme d'une vraie
s'assemble a l'execution (« "gsk_" + "A" * 32 »). Ecrite en clair, elle
serait signalee, et a raison — rien ne distingue une cle factice bien
imitee d'une vraie.

Le rapport donne le fichier et la ligne, jamais la ligne elle-meme.
L'ancien controle affichait ce qu'il trouvait : sur une vraie fuite, il
aurait recopie la cle dans le journal public de la CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from usine.core import securite  # noqa: E402


def fichiers_suivis() -> List[Path]:
    sortie = subprocess.run(["git", "ls-files", "-z"], cwd=str(RACINE),
                            capture_output=True, check=True).stdout
    return [RACINE / nom for nom in sortie.decode("utf-8", "replace").split("\0")
            if nom]


def fuites(fichiers: Iterable[Path]) -> List[str]:
    """« fichier:ligne » pour chaque cle apparente, et « .env » s'il est suivi."""
    trouvees = []
    for fichier in fichiers:
        try:
            nom = str(fichier.relative_to(RACINE))
        except ValueError:
            nom = str(fichier)
        if fichier.name == ".env":
            trouvees.append("{} : le fichier des cles est suivi par git".format(nom))
            continue
        try:
            texte = fichier.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                   # image, police, archive : pas de texte
        for numero, ligne in enumerate(texte.splitlines(), 1):
            if securite.contient_un_secret(ligne):
                trouvees.append("{}:{}".format(nom, numero))
    return trouvees


def principal() -> int:
    try:
        fichiers = fichiers_suivis()
    except (OSError, subprocess.CalledProcessError) as exc:
        # Rendre 0 ici serait annoncer « aucune fuite » sans avoir regarde.
        print("Liste des fichiers suivis illisible ({}) : verification "
              "impossible.".format(exc))
        return 2
    trouvees = fuites(fichiers)
    if trouvees:
        print("Cle d'API apparente dans le depot :")
        for ligne in trouvees:
            print("  " + ligne)
        print("\nUne cle poussee est a renouveler chez le fournisseur.")
        return 1
    print("Aucune cle d'API dans les {} fichiers suivis.".format(len(fichiers)))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
