"""Sauvegarde et restauration de l'atelier.

Ce qui se perd avec le fichier `usine.db` n'est pas remplacable : l'historique
de production, les empreintes qui empechent de refabriquer deux fois le meme
livre, les tests A/B en cours, et surtout LES VENTES. Les produits, eux, se
refabriquent ; une annee de ventes importees, non.

L'usine tourne sur un telephone. Le dossier de travail est souvent sous
/sdcard, qu'une application de nettoyage vide sans prevenir, et Termux se
desinstalle en trois taps.

La base est copiee par l'API de sauvegarde de SQLite, pas par un copier-coller
de fichier : la copie est alors coherente meme si une usine tourne en meme
temps. Copier le fichier a la main laisserait un journal WAL a cote, et une
base restauree a moitie.

Ce qui N'EST PAS sauvegarde, et pourquoi :

  LES CLES API    elles vivent dans .env, hors de l'atelier. Les mettre dans
                  une archive qu'on copie sur un ordinateur ou dans un nuage
                  serait le plus court chemin vers une cle divulguee.
  LE CACHE IA     il se reconstruit, il pese lourd, et il ne contient rien
                  qu'on ne puisse regenerer.
  LES PRODUITS    optionnels, et volumineux : voir `avec_produits`.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, store

NOM_BASE = "usine.db"
NOM_REGLAGES = "reglages.json"
NOM_FICHE = "sauvegarde.json"
VERSION = 1


def _copie_coherente(destination: Path) -> None:
    """Copie la base par l'API de sauvegarde SQLite, journal compris."""
    source = store.connect()
    cible = sqlite3.connect(str(destination))
    try:
        source.backup(cible)
    finally:
        cible.close()


def creer(destination: Optional[Path] = None,
          avec_produits: bool = False) -> Path:
    """Ecrit une archive de l'atelier. Renvoie son chemin."""
    config.ensure_dirs()
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    archive = Path(destination) if destination else (
        config.WORKDIR / "sauvegardes" / "usine-{}.zip".format(horodatage))
    archive.parent.mkdir(parents=True, exist_ok=True)

    temporaire = archive.parent / ".{}.db".format(horodatage)
    _copie_coherente(temporaire)
    try:
        produits: List[Path] = []
        if avec_produits and config.PRODUITS_DIR.exists():
            produits = [f for f in config.PRODUITS_DIR.rglob("*") if f.is_file()]
        fiche = {
            "version": VERSION,
            "cree_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "avec_produits": bool(produits),
            "fichiers_produits": len(produits),
            "schema": _version_schema(temporaire),
        }
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_:
            zip_.write(temporaire, NOM_BASE)
            reglages = config.WORKDIR / NOM_REGLAGES
            if reglages.exists():
                zip_.write(reglages, NOM_REGLAGES)
            prompts = config.WORKDIR / "prompts"
            if prompts.exists():
                for fichier in sorted(prompts.rglob("*")):
                    if fichier.is_file():
                        zip_.write(fichier,
                                   "prompts/" + fichier.name)
            for fichier in produits:
                zip_.write(fichier,
                           "produits/" + str(fichier.relative_to(
                               config.PRODUITS_DIR)))
            zip_.writestr(NOM_FICHE,
                          json.dumps(fiche, ensure_ascii=False, indent=2))
    finally:
        temporaire.unlink(missing_ok=True)
    return archive


def _version_schema(base: Path) -> int:
    connexion = sqlite3.connect(str(base))
    try:
        return int(connexion.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connexion.close()


def inspecter(archive: Path) -> Dict[str, Any]:
    """Ce que contient une archive, sans rien restaurer."""
    archive = Path(archive)
    if not archive.exists():
        return {"valide": False, "probleme": "fichier introuvable"}
    try:
        with zipfile.ZipFile(archive) as zip_:
            noms = set(zip_.namelist())
            if NOM_BASE not in noms:
                return {"valide": False,
                        "probleme": "archive sans base de donnees"}
            fiche = {}
            if NOM_FICHE in noms:
                try:
                    fiche = json.loads(zip_.read(NOM_FICHE).decode("utf-8"))
                except ValueError:
                    fiche = {}
            produits = sum(1 for n in noms if n.startswith("produits/"))
    except zipfile.BadZipFile:
        return {"valide": False, "probleme": "archive illisible"}
    fiche.update({"valide": True, "probleme": "",
                  "fichiers_produits": produits,
                  "avec_reglages": NOM_REGLAGES in noms})
    return fiche


def restaurer(archive: Path, avec_produits: bool = True) -> Dict[str, Any]:
    """Remet l'atelier dans l'etat de l'archive.

    L'atelier actuel est d'abord mis de cote : restaurer par erreur ne doit
    pas etre irreversible. C'est le genre de commande qu'on lance a une heure
    ou l'on se trompe.
    """
    archive = Path(archive)
    fiche = inspecter(archive)
    if not fiche["valide"]:
        return fiche
    if int(fiche.get("schema") or 0) > store.VERSION_SCHEMA:
        return {"valide": False,
                "probleme": "archive ecrite par une version plus recente "
                            "de l'usine (schema {} contre {})".format(
                                fiche.get("schema"), store.VERSION_SCHEMA)}

    config.ensure_dirs()
    store.close()
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    ecarte = None
    if config.DB_PATH.exists():
        ecarte = config.DB_PATH.with_name("usine-remplacee-{}.db".format(
            horodatage))
        shutil.move(str(config.DB_PATH), str(ecarte))
        # Le journal WAL de l'ancienne base n'a plus de base : le laisser
        # ferait resurgir des ecritures par-dessus celle qu'on restaure.
        for suffixe in ("-wal", "-shm"):
            compagnon = Path(str(config.DB_PATH) + suffixe)
            compagnon.unlink(missing_ok=True)

    restaures = 0
    refuses: List[str] = []
    with zipfile.ZipFile(archive) as zip_:
        config.DB_PATH.write_bytes(zip_.read(NOM_BASE))
        if NOM_REGLAGES in zip_.namelist():
            (config.WORKDIR / NOM_REGLAGES).write_bytes(
                zip_.read(NOM_REGLAGES))
        if avec_produits:
            for nom in zip_.namelist():
                if not nom.startswith("produits/") or nom.endswith("/"):
                    continue
                cible = _cible_sure(nom[len("produits/"):])
                if cible is None:
                    refuses.append(nom)
                    continue
                cible.parent.mkdir(parents=True, exist_ok=True)
                cible.write_bytes(zip_.read(nom))
                restaures += 1

    # La base restauree peut venir d'une version plus ancienne : on la fait
    # passer par l'echelle de migrations avant de rendre la main.
    from . import reglages as module_reglages

    # charger(force=True) RELIT le fichier restaure. Surtout pas
    # reinitialiser(), qui le supprimerait : la restauration effacerait
    # les reglages qu'elle vient de remettre en place.
    module_reglages.charger(force=True)
    store.connect()
    return {"valide": True, "probleme": "", "fichiers_produits": restaures,
            "refuses": refuses,
            "ancienne_base": str(ecarte) if ecarte else ""}


def _cible_sure(relatif: str) -> Optional[Path]:
    """Chemin de destination, ou None si l'entree tente de sortir du dossier.

    Une archive de sauvegarde passe par un ordinateur ou un nuage — la
    docstring du module le recommande. Elle revient donc potentiellement
    modifiee. Une entree nommee « ../../.bashrc » ou « /etc/passwd »
    ecrirait alors hors de l'atelier : c'est la traversee de chemin par
    archive, et elle se corrige en comparant le chemin resolu a sa racine.
    """
    if not relatif or relatif.startswith("/") or ".." in relatif.split("/"):
        return None
    racine = config.PRODUITS_DIR.resolve()
    cible = (racine / relatif).resolve()
    try:
        cible.relative_to(racine)
    except ValueError:
        return None
    return cible
