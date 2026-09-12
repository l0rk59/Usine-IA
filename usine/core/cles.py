"""Pool de cles API avec rotation automatique.

Objectif : ne jamais s'arreter pour cause de quota. Vous fournissez plusieurs
cles legitimes (la votre, celle de votre entreprise, celle d'un associe, ou
simplement des cles chez plusieurs fournisseurs) et l'usine passe a la suivante
des qu'une saturation apparait.

Ce module ne cree aucun compte et ne contourne aucune restriction : il exploite
au mieux les cles que vous possedez deja. Creer des comptes en serie pour
echapper a un quota viole les conditions d'utilisation de tous les
fournisseurs et fait bannir l'appareil.

Declaration des cles, trois formes acceptees :
    GROQ_API_KEY=cle1
    GROQ_API_KEY=cle1,cle2,cle3
    GROQ_API_KEY_2=cle2   (ou _3, _4, ...)

Securite : la cle elle-meme n'est jamais ecrite en base ni dans les journaux.
Seule une empreinte tronquee sert d'identifiant.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import store


def empreinte(cle: str) -> str:
    """Identifiant stable et non reversible d'une cle."""
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()[:16]


def masquer(cle: str) -> str:
    """Representation affichable : jamais la cle complete."""
    if not cle:
        return "(vide)"
    if len(cle) <= 10:
        return cle[:2] + "***"
    return "{}***{}".format(cle[:6], cle[-3:])


@dataclass
class Cle:
    valeur: str
    fournisseur: str
    rang: int = 0
    repos_jusqu_a: float = 0.0
    echecs: int = 0

    @property
    def id(self) -> str:
        return empreinte(self.valeur)

    @property
    def affichage(self) -> str:
        return masquer(self.valeur)

    def disponible(self, maintenant: Optional[float] = None) -> bool:
        return self.repos_jusqu_a <= (maintenant or time.time())


@dataclass
class Pool:
    fournisseur: str
    cles: List[Cle] = field(default_factory=list)
    _curseur: int = 0

    def __len__(self) -> int:
        return len(self.cles)

    def disponibles(self) -> List[Cle]:
        maintenant = time.time()
        return [c for c in self.cles if c.disponible(maintenant)]

    def ordonnees(self, plafond_journalier: int) -> List[Cle]:
        """Toutes les cles utilisables, de la moins sollicitee a la plus sollicitee.

        Le routeur a besoin de la LISTE, pas seulement du meilleur candidat :
        s'il n'obtenait qu'une cle a la fois, un refus la renverrait a
        l'identique au tour suivant (son compteur n'a pas bouge) et la rotation
        n'aurait jamais lieu.
        """
        candidates = []
        for cle in self.disponibles():
            utilisation = store.compteur_jour_cle(self.fournisseur, cle.id)
            if plafond_journalier and utilisation >= plafond_journalier:
                continue
            candidates.append((utilisation, cle.rang, cle))
        candidates.sort(key=lambda t: (t[0], t[1]))
        return [c for _, _, c in candidates]

    def choisir(self, plafond_journalier: int) -> Optional[Cle]:
        """La cle la moins sollicitee, ou None si toutes sont saturees."""
        ordre = self.ordonnees(plafond_journalier)
        return ordre[0] if ordre else None

    def mettre_au_repos(self, cle: Cle, secondes: float, raison: str = "") -> None:
        cle.repos_jusqu_a = time.time() + secondes
        cle.echecs += 1
        store.journal_cle(self.fournisseur, cle.id, raison, secondes)

    def reinitialiser(self) -> None:
        for cle in self.cles:
            cle.repos_jusqu_a = 0.0
            cle.echecs = 0


_pools: Dict[str, Pool] = {}


def _lire_variables(nom_variable: str) -> List[str]:
    """Collecte toutes les valeurs declarees pour une variable d'environnement."""
    brutes: List[str] = []
    principale = os.environ.get(nom_variable, "")
    if principale:
        brutes.append(principale)
    for suffixe in range(2, 21):
        valeur = os.environ.get("{}_{}".format(nom_variable, suffixe), "")
        if valeur:
            brutes.append(valeur)

    cles: List[str] = []
    for brute in brutes:
        # Une variable peut contenir plusieurs cles separees par virgule.
        for morceau in brute.replace(";", ",").split(","):
            propre = morceau.strip().strip('"').strip("'")
            if propre and propre not in cles:
                cles.append(propre)
    return cles


def charger(fournisseur: str, nom_variable: str) -> Pool:
    """Construit (ou recharge) le pool d'un fournisseur depuis l'environnement."""
    valeurs = _lire_variables(nom_variable) if nom_variable else []
    pool = Pool(fournisseur, [
        Cle(valeur=v, fournisseur=fournisseur, rang=i) for i, v in enumerate(valeurs)
    ])
    # Le repos survit au processus : c'est la base qui le porte, pas la
    # memoire. Un telephone qui redemarre ne doit pas resolliciter une cle
    # que le service vient de refuser.
    try:
        persistes = store.repos_actifs()
    except Exception:
        persistes = {}
    for cle in pool.cles:
        fin = persistes.get((fournisseur, cle.id))
        if fin:
            cle.repos_jusqu_a = fin
    ancien = _pools.get(fournisseur)
    if ancien:
        # On conserve l'etat de repos des cles deja connues.
        etat = {c.id: c for c in ancien.cles}
        for cle in pool.cles:
            precedente = etat.get(cle.id)
            if precedente:
                cle.repos_jusqu_a = max(cle.repos_jusqu_a,
                                        precedente.repos_jusqu_a)
                cle.echecs = precedente.echecs
    _pools[fournisseur] = pool
    return pool


def pool(fournisseur: str, nom_variable: str = "") -> Pool:
    existant = _pools.get(fournisseur)
    if existant is not None and (not nom_variable or existant.cles or not _lire_variables(nom_variable)):
        return existant
    return charger(fournisseur, nom_variable)


def oublier() -> None:
    """Vide le cache des pools (utile apres un rechargement du .env)."""
    _pools.clear()


def resume() -> List[Dict[str, object]]:
    """Etat de tous les pools, pour le diagnostic et le tableau de bord."""
    lignes: List[Dict[str, object]] = []
    maintenant = time.time()
    for fournisseur, p in sorted(_pools.items()):
        for cle in p.cles:
            lignes.append({
                "fournisseur": fournisseur,
                "cle": cle.affichage,
                "id": cle.id,
                "rang": cle.rang,
                "appels_jour": store.compteur_jour_cle(fournisseur, cle.id),
                "disponible": cle.disponible(maintenant),
                "repos_restant": max(0, int(cle.repos_jusqu_a - maintenant)),
                "echecs": cle.echecs,
            })
    return lignes
