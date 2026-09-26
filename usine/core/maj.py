"""Mettre a jour l'usine depuis le depot, sans toucher a l'atelier.

Sur un telephone, « git pull » n'est pas acquis : git n'est pas installe par
defaut sur Termux, et l'usine a justement ete ecrite pour ne rien exiger. Il y
a donc deux chemins, et le second existe pour ceux qui n'ont pas le premier :

1. **Depot git.** Si le dossier est un clone et que git repond, on tire. C'est
   le chemin propre : l'historique reste, les modifications locales sont vues,
   et rien n'est ecrase en silence.

2. **Archive.** Sinon, on telecharge l'archive du depot et on remplace les
   fichiers de code. Zero dependance, comme le reste : « urllib » et
   « zipfile » sont dans la bibliotheque standard.

Ce qui n'est JAMAIS touche, dans les deux cas : « atelier/ » et « .env ».
C'est tout le travail de l'utilisateur et sa seule cle. Les ecraser en
mettant a jour serait la pire facon de perdre quelqu'un — il ne se sert plus
jamais de la commande, et il a raison.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

DEPOT = "l0rk59/Usine-IA"
BRANCHE_DEFAUT = "main"

# Ce que la mise a jour remplace. Tout ce qui n'est pas la liste reste tel
# quel : l'atelier, le .env, et tout ce que l'utilisateur a pose a cote.
DOSSIERS_CODE = ("usine", "scripts", "tests", "docs", ".claude")
FICHIERS_CODE = ("install.sh", "README.md", "CLAUDE.md", ".env.exemple",
                 ".gitignore", "LICENSE")

# Au-dela, ce n'est pas l'archive du depot : on refuse plutot que de deballer
# une centaine de megaoctets sur un telephone.
TAILLE_MAX = 60 * 1024 * 1024


def racine() -> Path:
    """Le dossier d'installation : celui qui contient « usine/ »."""
    return Path(__file__).resolve().parent.parent.parent


def est_un_clone(dossier: Optional[Path] = None) -> bool:
    return (Path(dossier or racine()) / ".git").exists()


def git_disponible() -> bool:
    return bool(shutil.which("git"))


def _git(args: List[str], dossier: Path, timeout: int = 120):
    return subprocess.run(["git"] + args, cwd=str(dossier), text=True,
                          capture_output=True, timeout=timeout)


def modifications_locales(dossier: Optional[Path] = None) -> List[str]:
    """Fichiers suivis modifies sur place. Vide si git ne peut pas repondre.

    « Vide » ici veut dire « je ne sais pas », et c'est assume : l'appelant ne
    doit pas s'en servir pour conclure que tout est propre, seulement pour
    prevenir quand il sait que ca ne l'est pas.
    """
    dossier = Path(dossier or racine())
    if not (est_un_clone(dossier) and git_disponible()):
        return []
    try:
        sortie = _git(["status", "--porcelain", "--untracked-files=no"], dossier,
                      timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if sortie.returncode != 0:
        return []
    return [ligne[3:].strip() for ligne in sortie.stdout.splitlines()
            if ligne.strip()]


def par_git(branche: str = "", dossier: Optional[Path] = None) -> Dict[str, object]:
    """Tire la derniere version. Ne force rien, jamais.

    « --ff-only » est le point important : une mise a jour qui fabrique un
    commit de fusion sur le telephone de quelqu'un le laisse avec un depot
    dont il ne saura pas sortir. Si l'avance rapide est impossible, on le dit
    et on s'arrete.
    """
    dossier = Path(dossier or racine())
    try:
        actuelle = _git(["rev-parse", "--short", "HEAD"], dossier, timeout=30)
        avant = actuelle.stdout.strip()
        if not branche:
            nom = _git(["rev-parse", "--abbrev-ref", "HEAD"], dossier, timeout=30)
            branche = nom.stdout.strip() or BRANCHE_DEFAUT
        tirage = _git(["pull", "--ff-only", "origin", branche], dossier)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "erreur": "git n'a pas repondu : {}".format(exc)}
    if tirage.returncode != 0:
        return {"ok": False,
                "erreur": (tirage.stderr or tirage.stdout or "echec").strip()[:400],
                "branche": branche}
    apres = _git(["rev-parse", "--short", "HEAD"], dossier, timeout=30).stdout.strip()
    return {"ok": True, "voie": "git", "branche": branche,
            "avant": avant, "apres": apres,
            "change": avant != apres,
            "journal": (tirage.stdout or "").strip()[:600]}


def url_archive(branche: str = BRANCHE_DEFAUT) -> str:
    return "https://codeload.github.com/{}/zip/refs/heads/{}".format(DEPOT, branche)


def par_archive(branche: str = BRANCHE_DEFAUT,
                dossier: Optional[Path] = None) -> Dict[str, object]:
    """Telecharge l'archive du depot et remplace le code.

    Le deballage est fait dans un dossier temporaire et VERIFIE avant de
    toucher a quoi que ce soit : une archive qui ne contient pas « usine/ »
    n'est pas celle qu'on attend, et l'avoir a moitie deballee sur
    l'installation serait pire que de ne pas avoir essaye.
    """
    from .http import get_bytes, insister

    dossier = Path(dossier or racine())
    try:
        # Une archive de plusieurs mega-octets sur un forfait mobile : c'est
        # le telechargement le plus long de l'usine, donc celui qui a le plus
        # de chances d'etre coupe en route. Abandonner au premier hoquet
        # laissait l'utilisateur sur une version ancienne en croyant avoir
        # essaye.
        brut = insister(lambda: get_bytes(url_archive(branche), timeout=180))
    except Exception as exc:
        # Un depot PRIVE repond 404 a une requete sans jeton, exactement comme
        # une branche qui n'existe pas. On ne peut pas distinguer les deux
        # d'ici, alors on nomme les deux : chercher une panne de reseau pendant
        # une heure parce que le depot est prive est un temps entierement
        # perdu.
        return {"ok": False,
                "erreur": "archive introuvable pour « {} » ({}). Deux causes "
                          "possibles : la branche n'existe pas, ou le dépôt "
                          "est privé — l'archive ne marche que sur un dépôt "
                          "public. Dans ce cas, installez git (pkg install "
                          "git) et clonez : « usine maj » passera par lui."
                          .format(branche, exc)}
    if len(brut) > TAILLE_MAX:
        return {"ok": False,
                "erreur": "archive inattendue ({} Mo)".format(len(brut) // 1048576)}
    try:
        archive = zipfile.ZipFile(io.BytesIO(brut))
    except zipfile.BadZipFile:
        return {"ok": False, "erreur": "le fichier telecharge n'est pas une archive"}

    with tempfile.TemporaryDirectory(prefix="usine-maj-") as brouillon:
        temporaire = Path(brouillon)
        for membre in archive.namelist():
            # Un nom de membre vient du reseau : il ne doit pas pouvoir sortir
            # du dossier temporaire. « .. » et les chemins absolus sont
            # exactement ce qu'on refuse.
            cible = (temporaire / membre).resolve()
            try:
                cible.relative_to(temporaire.resolve())
            except ValueError:
                return {"ok": False,
                        "erreur": "archive refusée : un fichier sortait du dossier"}
        archive.extractall(temporaire)
        racines = [p for p in temporaire.iterdir() if p.is_dir()]
        if len(racines) != 1 or not (racines[0] / "usine").is_dir():
            return {"ok": False,
                    "erreur": "l'archive ne contient pas l'usine attendue"}
        source = racines[0]

        remplaces = []
        for nom in DOSSIERS_CODE:
            origine = source / nom
            if not origine.is_dir():
                continue
            destination = dossier / nom
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(origine, destination)
            remplaces.append(nom + "/")
        for nom in FICHIERS_CODE:
            origine = source / nom
            if origine.is_file():
                shutil.copy2(origine, dossier / nom)
                remplaces.append(nom)
    return {"ok": True, "voie": "archive", "branche": branche,
            "remplaces": remplaces, "change": True}


def variables_manquantes(dossier: Optional[Path] = None) -> List[str]:
    """Variables de fournisseur absentes du « .env » de l'utilisateur.

    On compare au CATALOGUE des fournisseurs, pas a « .env.exemple » : c'est
    le catalogue qui fait foi, et le modele pourrait lui-meme avoir du retard.
    """
    from . import config

    fichier = Path(dossier or racine()) / ".env"
    if not fichier.exists():
        return []
    try:
        present = fichier.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    attendues = [p.api_key_env for p in config.PROVIDERS
                 if p.api_key_env and not p.local]
    # Une ligne commentee compte comme presente : l'utilisateur l'a vue et a
    # choisi de ne pas s'en servir. La completer reviendrait a la lui remettre
    # sous le nez a chaque mise a jour.
    lignes = [l.strip().lstrip("#").strip() for l in present.splitlines()]
    deja = {l.split("=", 1)[0].strip() for l in lignes if "=" in l}
    return [v for v in attendues if v not in deja]


def completer_env(dossier: Optional[Path] = None) -> List[str]:
    """Ajoute au « .env » les variables de fournisseur qui n'y sont pas.

    Le defaut que cela corrige n'a rien de spectaculaire, et c'est pour cela
    qu'il a dure : « install.sh » ne cree « .env » que s'il n'existe pas, et
    « usine maj » ne le touche jamais — a raison, il contient les cles. Donc
    tout fournisseur ajoute APRES la premiere installation n'apparait jamais
    chez quelqu'un qui a deja installe. Il ouvre « nano .env », ne voit pas la
    variable, et en conclut que l'integration n'existe pas.

    L'ecart grandit a chaque fournisseur ajoute, sans que rien ne le dise.

    AJOUT SEUL. Aucune ligne existante n'est lue, modifiee ni reordonnee : le
    fichier contient des cles, et un outil qui les reecrit est un outil qu'on
    n'ose plus lancer. En cas de doute, on n'ecrit rien.
    """
    from . import config

    manquantes = variables_manquantes(dossier)
    if not manquantes:
        return []
    fichier = Path(dossier or racine()) / ".env"
    fiches = {p.api_key_env: p for p in config.PROVIDERS}
    morceaux = ["", "",
                "# --- Ajoute par « usine maj » : fournisseurs apparus depuis",
                "#     votre installation. Vos clés existantes n'ont pas été",
                "#     touchées. -------------------------------------------"]
    for variable in manquantes:
        fiche = fiches.get(variable)
        if fiche is not None and fiche.signup:
            morceaux.append("# {} — {}".format(fiche.name, fiche.signup))
        morceaux.append("{}=".format(variable))
    try:
        with fichier.open("a", encoding="utf-8") as flux:
            flux.write("\n".join(morceaux) + "\n")
    except OSError:
        return []
    return manquantes


def version_installee() -> str:
    from .. import __version__

    return __version__


def verifier(dossier: Optional[Path] = None) -> Dict[str, object]:
    """L'usine demarre-t-elle apres la mise a jour ?

    On relance un processus neuf plutot que de reimporter : les modules deja
    charges dans CELUI-ci sont l'ancienne version, et ils repondraient « tout
    va bien » quoi qu'on ait installe.
    """
    dossier = Path(dossier or racine())
    try:
        sortie = subprocess.run(
            [os.environ.get("PYTHON", "python3"), "-m", "usine.cli", "--version"],
            cwd=str(dossier), capture_output=True, text=True, timeout=90,
            env=dict(os.environ, PYTHONPATH=str(dossier)))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "erreur": str(exc)}
    if sortie.returncode != 0:
        return {"ok": False,
                "erreur": (sortie.stderr or sortie.stdout).strip()[:400]}
    return {"ok": True, "version": (sortie.stdout or "").strip()}
