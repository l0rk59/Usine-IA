"""Socle des agents.

Un agent est un role de metier : une personnalite, une mission, un modele
adapte a sa tache. Les separer produit de meilleurs textes qu'une invite unique
parce que chacun n'a qu'un objectif a tenir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..core import evenements, llm, prompts


@dataclass
class Agent:
    """Un role de metier dote de sa propre voix et de son propre modele."""

    nom: str
    metier: str
    mission: str
    regles: List[str] = field(default_factory=list)
    role_modele: str = "standard"        # rapide | standard | costaud
    temperature: float = 0.75
    emoji: str = "*"

    def systeme(self, contexte: Any) -> str:
        regles = "\n".join("- " + r for r in self.regles)
        return (
            "Tu es {metier}.\n"
            "MISSION : {mission}\n"
            "LANGUE : {langue}\n"
            "TON : {ton}\n"
            "PUBLIC : {audience}\n"
            "REGLES ABSOLUES :\n{regles}\n{interdits}"
        ).format(
            metier=self.metier,
            mission=self.mission,
            langue=getattr(contexte, "langue", "francais"),
            ton=getattr(contexte, "description_ton", "professionnel"),
            audience=getattr(contexte, "audience", "un public francophone"),
            regles=regles or "- Aucune regle specifique.",
            interdits=prompts.modele("interdits"),
        )

    def travailler(
        self,
        contexte: Any,
        invite: str,
        max_tokens: int = 4000,
        temperature: Optional[float] = None,
        eviter: Optional[Sequence[str]] = None,
        cache: bool = True,
    ) -> llm.Reponse:
        evenements.publier("agent", agent=self.nom, etat="debut", emoji=self.emoji)
        reponse = llm.generer(
            invite,
            systeme=self.systeme(contexte),
            role=self.role_modele,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
            cache=cache,
            eviter=eviter,
        )
        evenements.publier("agent", agent=self.nom, etat="fin", emoji=self.emoji,
                           fournisseur=reponse.fournisseur, tokens=reponse.tokens)
        return reponse

    def travailler_json(
        self,
        contexte: Any,
        invite: str,
        max_tokens: int = 4000,
        temperature: Optional[float] = None,
        eviter: Optional[Sequence[str]] = None,
    ) -> Any:
        evenements.publier("agent", agent=self.nom, etat="debut", emoji=self.emoji)
        resultat = llm.generer_json(
            invite,
            systeme=self.systeme(contexte),
            role=self.role_modele,
            temperature=0.45 if temperature is None else temperature,
            max_tokens=max_tokens,
            eviter=eviter,
        )
        evenements.publier("agent", agent=self.nom, etat="fin", emoji=self.emoji)
        return resultat


@dataclass
class Critique:
    """Verdict d'une relecture."""

    note: float                      # sur 10
    problemes: List[Dict[str, str]] = field(default_factory=list)
    points_forts: List[str] = field(default_factory=list)
    verdict: str = ""

    @property
    def acceptable(self) -> bool:
        return self.note >= 7.5

    @property
    def bloquants(self) -> List[Dict[str, str]]:
        return [p for p in self.problemes
                if str(p.get("gravite", "")).lower() in ("bloquant", "majeur", "eleve")]

    def resume(self) -> str:
        if not self.problemes:
            return "{}/10 — rien a corriger".format(self.note)
        return "{}/10 — {} correction(s), dont {} majeure(s)".format(
            self.note, len(self.problemes), len(self.bloquants)
        )
