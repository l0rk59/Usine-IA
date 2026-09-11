"""Socle commun a toutes les chaines de production."""

from __future__ import annotations

import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core import apprentissage, config, store

TONS = {
    "expert": "expert, precis, appuye sur des faits et des chiffres",
    "amical": "chaleureux, direct, tutoiement, comme un ami qui explique",
    "pro": "professionnel, sobre, vouvoiement, orientation resultats",
    "punchy": "percutant, phrases courtes, rythme soutenu, verbes d'action",
    "pedagogue": "pedagogue, progressif, beaucoup d'exemples concrets",
}

TAILLES = {
    "mini": (6, 700),
    "court": (8, 950),
    "standard": (12, 1100),
    "long": (18, 1300),
}


def slug(texte: str, longueur: int = 60) -> str:
    """Transforme un titre en nom de dossier sur : sans accent ni espace."""
    normalise = unicodedata.normalize("NFKD", texte)
    ascii_seul = normalise.encode("ascii", "ignore").decode("ascii")
    propre = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_seul).strip("-").lower()
    return (propre[:longueur].strip("-")) or "produit"


def identifiant(type_produit: str, titre: str) -> str:
    """Identifiant unique d'un produit, qui sert aussi de nom de dossier.

    L'horodatage seul ne suffit pas : sa precision est la seconde, et l'usine
    continue peut livrer deux produits dans la meme seconde. Les quatre
    caracteres aleatoires evitent que le second ecrase les fichiers du premier.
    """
    return "{}-{}-{}-{}".format(
        type_produit, slug(titre, 32), time.strftime("%Y%m%d-%H%M%S"),
        secrets.token_hex(2))


@dataclass
class Contexte:
    """Tout ce dont une chaine de production a besoin."""

    sujet: str
    audience: str = "un public francophone motive"
    langue: str = "francais"
    ton: str = "pro"
    taille: str = "standard"
    auteur: str = "Usine-IA"
    prix: str = ""
    marque: str = ""
    hors_ligne: bool = False
    sans_image: bool = False
    qualite: str = "standard"
    relectures: int = -1          # -1 : deduit du niveau de qualite
    produit_id: str = ""
    demarre_le: float = field(default_factory=time.time)
    dossier: Path = field(default_factory=Path)
    journal: Callable[[str], None] = print
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def description_ton(self) -> str:
        return TONS.get(self.ton, TONS["pro"])

    @property
    def nb_passes(self) -> int:
        """Nombre de relectures editoriales appliquees a chaque section."""
        if self.relectures >= 0:
            return self.relectures
        from ..core import reglages

        return reglages.relectures_pour(self.qualite)

    @property
    def nb_chapitres(self) -> int:
        return TAILLES.get(self.taille, TAILLES["standard"])[0]

    @property
    def mots_par_chapitre(self) -> int:
        return TAILLES.get(self.taille, TAILLES["standard"])[1]

    def systeme(self, role_metier: str) -> str:
        return (
            "Tu es {role}. Tu ecris en {langue}, d'un ton {ton}. "
            "Tu t'adresses a : {audience}. "
            "Tes textes sont concrets, structures, sans remplissage ni formule creuse. "
            "Tu bannis les tournures d'IA generique (« dans un monde ou », « il est "
            "important de noter », « en conclusion »). Tu donnes des exemples chiffres, "
            "des scripts reutilisables et des etapes numerotees. "
            "Tu ne promets jamais de resultats garantis et tu n'inventes ni statistique "
            "precise ni citation attribuee a une personne reelle."
        ).format(
            role=role_metier,
            langue=self.langue,
            ton=self.description_ton,
            audience=self.audience,
        )

    def etape(self, nom: str, statut: str = "ok", detail: str = "") -> None:
        if self.produit_id:
            store.journal_etape(self.produit_id, nom, statut, detail)


def preparer(ctx: Contexte, type_produit: str, titre: str) -> Path:
    """Cree le dossier du produit et l'enregistre au catalogue."""
    config.ensure_dirs()
    ctx.produit_id = ctx.produit_id or identifiant(type_produit, titre)
    dossier = config.PRODUITS_DIR / ctx.produit_id
    dossier.mkdir(parents=True, exist_ok=True)
    ctx.dossier = dossier
    store.creer_produit(
        ctx.produit_id,
        type_produit,
        titre,
        sujet=ctx.sujet,
        audience=ctx.audience,
        langue=ctx.langue,
        dossier=str(dossier),
        meta={"ton": ctx.ton, "taille": ctx.taille, "auteur": ctx.auteur},
    )
    return dossier


def terminer(ctx: Contexte, fichiers: List[Path], meta: Optional[Dict[str, Any]] = None,
             type_produit: str = "") -> None:
    infos = dict(meta or {})
    store.maj_produit(
        ctx.produit_id,
        statut="pret",
        meta=dict(infos, fichiers=[f.name for f in fichiers]),
    )
    # Trace mesuree : c'est elle qui alimente « usine bilan » et « usine conseils ».
    produit = store.lire_produit(ctx.produit_id) or {}
    appels = store.compteur_intervalle(ctx.demarre_le)
    fournisseurs = store.fournisseurs_intervalle(ctx.demarre_le)
    apprentissage.enregistrer(
        produit_id=ctx.produit_id,
        type_produit=type_produit or produit.get("type", "inconnu"),
        sujet=ctx.sujet,
        audience=ctx.audience,
        ton=ctx.ton,
        taille=ctx.taille,
        qualite=ctx.qualite,
        note=infos.get("note"),
        note_avant=infos.get("note_avant"),
        mots=int(infos.get("mots") or 0),
        sections=int(infos.get("sections") or infos.get("chapitres") or 0),
        duree=round(time.time() - ctx.demarre_le, 1),
        appels=appels,
        fournisseurs=infos.get("fournisseurs") or fournisseurs,
        defauts=infos.get("defauts") or [],
    )


def nettoyer_titre(texte: str) -> str:
    """Retire guillemets, numerotation et balisage laisses par le modele."""
    texte = texte.strip().strip('"').strip("'").strip()
    texte = re.sub(r"^#+\s*", "", texte)
    texte = re.sub(r"^(chapitre|module|partie|section|etape|jour)\s*\d+\s*[:.\-–]\s*",
                   "", texte, flags=re.IGNORECASE)
    texte = re.sub(r"^\d+\s*[:.)\-–]\s*", "", texte)
    texte = texte.replace("**", "").strip()
    return texte or "Sans titre"


def elaguer_markdown(texte: str) -> str:
    """Supprime le bavardage et les cloture de code laisses autour d'un markdown."""
    indesirables = (
        "voici", "bien sur", "bien sûr", "certainement", "j'espere", "j'espère",
        "n'hesitez pas", "n'hésitez pas", "voila", "voilà", "parfait", "avec plaisir voici",
    )
    texte = texte.strip()
    # Le preambule peut preceder la cloture markdown : deux passes suffisent.
    for _ in range(2):
        lignes = texte.split("\n")
        while lignes and lignes[0].strip().lower().startswith(indesirables):
            lignes.pop(0)
        while lignes and not lignes[0].strip():
            lignes.pop(0)
        texte = "\n".join(lignes).strip()
        texte = re.sub(r"^```(?:markdown|md|text)?[ \t]*\n", "", texte)
        texte = re.sub(r"\n?```[ \t]*$", "", texte).strip()
    return texte
