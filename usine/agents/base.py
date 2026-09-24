"""Socle des agents.

Un agent est un role de metier : une personnalite, une mission, un modele
adapte a sa tache. Les separer produit de meilleurs textes qu'une invite unique
parce que chacun n'a qu'un objectif a tenir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..core import evenements, llm, prompts


def signaler_troncature(contexte: Any, agent: str,
                        reponse: llm.Reponse) -> None:
    """Dit qu'une reponse a ete coupee au plafond de jetons.

    Le routeur sait depuis longtemps reconnaitre une reponse tronquee — il
    refuse meme de la mettre en cache, pour ne pas figer la coupure. Mais il
    le savait tout seul : ni le journal, ni le rapport qualite, ni le tableau
    de bord n'en portaient trace. Un chapitre tranche au milieu d'une phrase
    traversait donc toute la fabrication en passant pour termine, ce qui est
    exactement le defaut que la detection etait censee rendre visible.

    Deux destinations, parce qu'elles repondent a deux questions
    differentes : le journal le dit TOUT DE SUITE, pendant qu'il est encore
    temps de reduire la longueur demandee ; le contexte l'accumule pour que
    le rapport du produit livre puisse dire combien de sections sont
    concernees.
    """
    detail = {"agent": agent, "fournisseur": reponse.fournisseur,
              "modele": reponse.modele}
    meta = getattr(contexte, "meta", None)
    if isinstance(meta, dict):
        meta.setdefault("tronquees", []).append(detail)
    journal = getattr(contexte, "journal", None)
    if callable(journal):
        journal("  [!] reponse coupee au plafond de jetons ({} via {}) : "
                "le texte s'arrete avant sa fin".format(agent,
                                                        reponse.fournisseur))


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
    # Les agents dont le texte passe ensuite par le detecteur de tics. Pour
    # eux, et pour eux seuls, la liste complete va dans la consigne : chaque
    # tic qu'ils ecrivent coute une passe de correction, soit un appel entier.
    # Pour les autres, quatre cents jetons de plus a chaque appel ne se
    # rembourseraient pas — un agent qui rend un titre ou un plan JSON n'ecrit
    # pas « plongeons dans ».
    tics: bool = False

    def systeme(self, contexte: Any) -> str:
        regles = "\n".join("- " + r for r in self.regles)
        interdits = prompts.modele("interdits")
        if self.tics:
            from ..core import controle

            interdits += ("\n- Jamais ces tournures, que le controle retire "
                          "ensuite une a une : {}.".format(", ".join(
                              "« {} »".format(t) for t in controle.tics_lisibles())))
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
            interdits=interdits,
        )

    def travailler(
        self,
        contexte: Any,
        invite: str,
        max_tokens: int = 4000,
        temperature: Optional[float] = None,
        eviter: Optional[Sequence[str]] = None,
        cache: bool = True,
        role_modele: Optional[str] = None,
    ) -> llm.Reponse:
        """« role_modele » surclasse le role habituel de l'agent pour un appel.

        Un redacteur reste un redacteur ; mais condenser une partie entiere
        demande un modele de long contexte, pas une autre personnalite.
        """
        from ..pipelines.base import code_langue

        evenements.publier("agent", agent=self.nom, etat="debut", emoji=self.emoji)
        reponse = llm.generer(
            invite,
            systeme=self.systeme(contexte),
            role=role_modele or self.role_modele,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
            cache=cache,
            eviter=eviter,
            # La langue que le systeme vient de demander au modele : le routeur
            # en a besoin pour lire la reponse. Vide pour une langue inconnue —
            # « rien n'y est francais » n'y prouve alors rien.
            langue=code_langue(getattr(contexte, "langue", "francais"), defaut=""),
        )
        evenements.publier("agent", agent=self.nom, etat="fin", emoji=self.emoji,
                           fournisseur=reponse.fournisseur, tokens=reponse.tokens)
        if reponse.tronquee:
            signaler_troncature(contexte, self.nom, reponse)
        return reponse

    def travailler_json(
        self,
        contexte: Any,
        invite: str,
        max_tokens: int = 4000,
        temperature: Optional[float] = None,
        eviter: Optional[Sequence[str]] = None,
        avec_fournisseur: bool = False,
        role_modele: Optional[str] = None,
        cache: bool = True,
    ) -> Any:
        """Rend l'objet decode, ou (objet, fournisseur) si on le demande.

        Le fournisseur sert a PROUVER la relecture croisee : sans lui, la
        chaine affirmait qu'un autre modele avait relu sans pouvoir le dire.
        """
        evenements.publier("agent", agent=self.nom, etat="debut", emoji=self.emoji)
        resultat, fournisseur = llm.generer_json(
            invite,
            systeme=self.systeme(contexte),
            # Un agent garde son metier ; ce qui change, c'est le modele.
            # Batir une structure demande un modele costaud la ou remplir une
            # fiche n'en demande pas — et c'est le meme agent qui fait les
            # deux.
            role=role_modele or self.role_modele,
            temperature=0.45 if temperature is None else temperature,
            max_tokens=max_tokens,
            eviter=eviter,
            avec_fournisseur=True,
            cache=cache,
        )
        evenements.publier("agent", agent=self.nom, etat="fin", emoji=self.emoji,
                           fournisseur=fournisseur)
        return (resultat, fournisseur) if avec_fournisseur else resultat


@dataclass
class Critique:
    """Verdict d'une relecture."""

    note: float                      # sur 10
    problemes: List[Dict[str, str]] = field(default_factory=list)
    points_forts: List[str] = field(default_factory=list)
    verdict: str = ""
    # Qui a ecrit, qui a relu. La chaine ANNONCE une relecture par un autre
    # modele ; sans ces deux champs, elle ne pouvait pas le prouver — et
    # l'ecart existe reellement : quand un seul fournisseur est configure,
    # « eviter » se desactive pour ne pas perdre la relecture.
    fournisseur_auteur: str = ""
    fournisseur_relecteur: str = ""
    # La relecture a-t-elle EU LIEU ? Une relecture qui echoue rendait une
    # note de 7,5 — pile le seuil d'acceptation — avec zero probleme. Journal
    # reel du 16/09/2026 : huit scenes, huit « relecture : 7,5/10, 0
    # correction(s) », identiques au dixieme pres. L'editeur n'avait pas relu
    # une seule fois, et rien ne le disait.
    #
    # C'est la pire forme de defaut de ce depot : tous les signaux disent
    # « valide ». Pire encore, 7,5 >= 7,5 rendait la critique « acceptable »,
    # ce qui arretait la boucle d'amelioration en annoncant que le texte etait
    # assez bon.
    mesuree: bool = True

    @property
    def croisee(self) -> bool:
        """La relecture a-t-elle eu lieu sur un AUTRE modele que l'auteur ?"""
        return bool(self.fournisseur_auteur and self.fournisseur_relecteur
                    and self.fournisseur_auteur != self.fournisseur_relecteur)

    @property
    def acceptable(self) -> bool:
        """Non mesuree n'est pas acceptable : c'est inconnu.

        Le contraire arretait la boucle d'amelioration sur une relecture qui
        n'avait jamais eu lieu.
        """
        return self.mesuree and self.note >= 7.5

    @property
    def bloquants(self) -> List[Dict[str, str]]:
        return [p for p in self.problemes
                if str(p.get("gravite", "")).lower() in ("bloquant", "majeur", "eleve")]

    def resume(self) -> str:
        if not self.mesuree:
            return "relecture indisponible — pas de note ({})".format(
                self.verdict or "aucune reponse")
        if not self.problemes:
            return "{}/10 — rien a corriger".format(self.note)
        return "{}/10 — {} correction(s), dont {} majeure(s)".format(
            self.note, len(self.problemes), len(self.bloquants)
        )
