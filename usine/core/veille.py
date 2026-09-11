"""Scout de niches : ce que les gens disent vraiment de leurs problemes.

Les quatre sources deja en place mesurent des VOLUMES — combien de
discussions, combien de pages vues, combien de livres. Elles disent si une
niche existe. Elles ne disent pas ce qui y fait mal, avec quels mots, ni
quelle phrase un acheteur taperait dans une barre de recherche.

Reddit repond a cette question-la, et sans cle : ses flux Atom sont ouverts.
Un titre de discussion est une formulation de probleme ecrite par quelqu'un
qui l'a — c'est la matiere premiere d'une promesse produit.

EN DEUX TEMPS, ET PAS EN UN. La recherche globale de Reddit
(« /search.rss?q=... ») a ete essayee d'abord : sur « meal planning for busy
parents » elle a rendu des discussions sur des chatons dans une bouche
d'egout, un sejour en Slovenie et r/meirl. Elle elargit la requete jusqu'a
rendre du populaire hors sujet, ce qui aurait nourri le modele de bruit —
pire que de ne rien lui donner.

Le chemin qui marche passe par les communautes : on demande d'abord QUI
parle du sujet, puis on lit ce qui s'y dit. Les titres sont alors sur le
sujet par construction.

CE QUE CE MODULE NE FAIT PAS, et il faut le dire :

  IL NE MESURE PAS LA DEMANDE COMMERCIALE. Un sujet tres discute peut
  n'avoir aucun acheteur : les gens se plaignent gratuitement. Le volume
  Reddit est un signal de DOULEUR, pas d'intention d'achat.
  IL N'EST PAS REPRESENTATIF. Reddit est anglophone, jeune, technophile et
  americain. Une niche francaise de retraites jardiniers n'y laissera
  aucune trace, ce qui ne dit rien de son marche.
  IL N'INSISTE PAS. Reddit limite fermement le debit et repond 429 sans
  prevenir. Un refus est rapporte comme tel, jamais comme un resultat vide
  — « aucune discussion » et « on n'a pas pu regarder » ne se confondent
  pas.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .http import HttpErreur, requete

RACINE = "https://www.reddit.com"
# Reddit exige un agent identifiable et refuse les agents de bibliotheque.
AGENT = "usine-ia/1.0 (veille de niches, un appel a la fois)"

_ENTREE = re.compile(r"<entry>(.*?)</entry>", re.S)
_BALISE = re.compile(r"<(\w+)[^>]*>(.*?)</\1>", re.S)
_HTML = re.compile(r"<[^>]+>")

# Formulations qui trahissent un probleme, pas une conversation. Ce sont
# elles qui distinguent « j'ai reussi a » d'un appel a l'aide.
_DOULEUR = (
    "how do i", "how do you", "how to", "what do you use", "any tips",
    "advice", "help", "struggling", "stuck", "cant figure", "can't figure",
    "is there a", "looking for", "recommend", "best way", "anyone else",
    "problem", "issue", "frustrated", "hate", "tired of", "why does",
    "comment faire", "besoin d aide", "je galere", "conseil", "probleme",
)


@dataclass
class Discussion:
    titre: str
    lien: str
    communaute: str = ""
    date: str = ""

    @property
    def douleur(self) -> bool:
        propre = self.titre.lower()
        return any(marqueur in propre for marqueur in _DOULEUR)


@dataclass
class Veille:
    """Ce qu'une consultation a rapporte, et ce qu'elle n'a pas pu voir."""

    niche: str = ""
    communautes: List[Dict[str, str]] = field(default_factory=list)
    discussions: List[Discussion] = field(default_factory=list)
    mots: List[Tuple[str, int]] = field(default_factory=list)
    indisponible: str = ""      # non vide = on n'a pas pu regarder

    @property
    def utilisable(self) -> bool:
        return not self.indisponible and bool(self.discussions)

    @property
    def douleurs(self) -> List[Discussion]:
        return [d for d in self.discussions if d.douleur]


def _texte(fragment: str, balise: str) -> str:
    trouve = re.search(r"<{0}[^>]*>(.*?)</{0}>".format(balise), fragment, re.S)
    if not trouve:
        return ""
    brut = _HTML.sub(" ", trouve.group(1))
    for avant, apres in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&apos;", "'")):
        brut = brut.replace(avant, apres)
    return re.sub(r"\s+", " ", brut).strip()


def _lien(fragment: str) -> str:
    trouve = re.search(r'<link[^>]*href="([^"]+)"', fragment)
    return trouve.group(1) if trouve else ""


def _flux(chemin: str, timeout: int = 15, patience: float = 20.0
          ) -> Tuple[List[str], str]:
    """Lit un flux Atom Reddit. Renvoie (entrees, raison d'indisponibilite).

    Reddit repond 429 des le deuxieme appel rapproche. Un seul reessai, apres
    une vraie attente : insister davantage prolonge le blocage au lieu de le
    lever, et l'usine a mieux a faire que d'attendre un site gratuit.
    """
    for tentative in range(2):
        try:
            statut, corps = requete(RACINE + chemin,
                                    entetes={"User-Agent": AGENT},
                                    timeout=timeout)
        except HttpErreur as exc:
            if exc.statut == 429 and tentative == 0:
                time.sleep(patience)
                continue
            if exc.statut == 429:
                return ([], "Reddit limite le debit (429). Reessayez dans "
                            "quelques minutes : la veille n'insiste pas.")
            return ([], "Reddit injoignable ({}).".format(exc.statut))
        except OSError as exc:
            return ([], "Reddit injoignable ({}).".format(exc))
        if statut != 200:
            return ([], "Reddit a repondu {}.".format(statut))
        return (_ENTREE.findall(corps.decode("utf-8", "replace")), "")
    return ([], "Reddit limite le debit (429).")


def communautes(niche: str, limite: int = 6) -> Tuple[List[Dict[str, str]], str]:
    """Communautes qui parlent de cette niche."""
    chemin = "/subreddits/search.rss?q={}".format(
        urllib.parse.quote(niche[:120]))
    entrees, probleme = _flux(chemin)
    trouvees = []
    for fragment in entrees[:limite]:
        lien = _lien(fragment)
        nom = ""
        trouve = re.search(r"/r/([A-Za-z0-9_]+)", lien)
        if trouve:
            nom = trouve.group(1)
        if nom:
            trouvees.append({"nom": nom,
                             "titre": _texte(fragment, "title")[:80],
                             "lien": lien})
    return trouvees, probleme


def discussions(communaute: str, periode: str = "year",
                limite: int = 25) -> Tuple[List[Discussion], str]:
    """Discussions les plus suivies d'UNE communaute.

    Pas de recherche globale : elle rend du populaire hors sujet. Une
    communaute, elle, parle de son sujet.
    """
    chemin = "/r/{}/top.rss?t={}".format(
        urllib.parse.quote(communaute[:60]), periode)
    entrees, probleme = _flux(chemin)
    trouvees = []
    for fragment in entrees[:limite]:
        titre = _texte(fragment, "title")
        if not titre:
            continue
        trouvees.append(Discussion(titre=titre[:200], lien=_lien(fragment),
                                   communaute=communaute,
                                   date=_texte(fragment, "updated")[:10]))
    return trouvees, probleme


# Mots trop generaux pour distinguer une niche d'une autre.
_VIDES = {
    "the", "and", "for", "you", "your", "with", "that", "this", "have", "has",
    "are", "was", "were", "been", "being", "but", "not", "any", "can", "get",
    "got", "how", "what", "who", "why", "when", "where", "from", "just",
    "like", "about", "out", "one", "two", "all", "now", "only", "them",
    "they", "their", "there", "here", "its", "our", "some", "more", "most",
    "very", "much", "many", "into", "over", "after", "before", "than",
    "then", "also", "even", "still", "back", "make", "made", "want", "need",
    "know", "think", "going", "would", "could", "should", "will", "did",
    "does", "doing", "day", "days", "week", "year", "years", "time", "first",
    "new", "old", "good", "bad", "best", "post", "thread", "update", "edit",
    "les", "des", "une", "pour", "avec", "dans", "que", "qui", "sur", "pas",
    "plus", "est", "son", "ses", "mon", "mes", "vous", "nous", "mais", "sont",
    "cette", "comme", "tout", "tous", "fait", "faire", "bien", "encore",
    "reddit", "http", "https", "www", "com", "amp", "nbsp",
}
_MOT = re.compile(r"[a-z][a-z'\-]{2,}")


def vocabulaire(lot: Sequence[Discussion], limite: int = 14
                ) -> List[Tuple[str, int]]:
    """Mots qui reviennent dans les titres, du plus frequent au moins.

    C'est le vocabulaire des gens, pas celui du modele. Un titre de produit
    qui reprend leurs mots se trouve ; un titre qui reprend ceux d'un modele
    de langage ne se cherche pas.
    """
    comptes: Dict[str, int] = {}
    for discussion in lot:
        vus = set()
        for mot in _MOT.findall(discussion.titre.lower()):
            if mot in _VIDES or mot in vus:
                continue
            vus.add(mot)
            comptes[mot] = comptes.get(mot, 0) + 1
    classes = sorted(comptes.items(), key=lambda c: (-c[1], c[0]))
    return [c for c in classes if c[1] > 1][:limite]


def scouter(niche: str, periode: str = "year", combien: int = 2,
            pause: float = 3.0) -> Veille:
    """Consultation d'une niche : qui en parle, puis ce qui s'y dit.

    `combien` communautes seulement, et une pause entre chaque : Reddit
    repond 429 des le deuxieme appel rapproche, et un 429 ne rapporte rien.
    Deux communautes donnent une cinquantaine de titres, ce qui suffit
    largement a degager un vocabulaire.
    """
    veille = Veille(niche=niche)
    trouvees, probleme = communautes(niche)
    if probleme and not trouvees:
        veille.indisponible = probleme
        return veille
    veille.communautes = trouvees
    if not trouvees:
        veille.indisponible = ("aucune communaute ne correspond a cette "
                               "niche sur Reddit. Cela ne dit rien de son "
                               "marche : Reddit est anglophone.")
        return veille

    echecs = []
    for rang, communaute in enumerate(trouvees[:max(1, combien)]):
        if rang or pause:
            time.sleep(pause)
        lot, souci = discussions(communaute["nom"], periode)
        if souci:
            echecs.append(souci)
            continue
        veille.discussions.extend(lot)
    if not veille.discussions:
        veille.indisponible = (echecs[0] if echecs
                               else "aucune discussion recuperee.")
        return veille
    veille.mots = vocabulaire(veille.discussions)
    return veille


def resume_pour_ia(veille: Veille, maximum: int = 12) -> str:
    """Ce que la veille apprend, a injecter dans une invite."""
    if not veille.utilisable:
        return ""
    lignes = ["Discussions reelles sur cette niche (source : Reddit, donc "
              "anglophone et non representative d'un marche francais) :"]
    # Les formulations de probleme d'abord, le reste ensuite — mais jamais
    # le reste a la place. Ne montrer que les douleurs quand le reperage
    # n'en trouve qu'une revenait a cacher quarante-neuf discussions
    # derriere un filtre approximatif.
    retenues = list(veille.douleurs)
    vues = {d.titre for d in retenues}
    retenues.extend(d for d in veille.discussions if d.titre not in vues)
    for discussion in retenues[:maximum]:
        lignes.append("- {}{}".format(
            discussion.titre[:150],
            " (r/{})".format(discussion.communaute) if discussion.communaute
            else ""))
    if veille.mots:
        lignes.append("Mots qui reviennent : " + ", ".join(
            "{} ({})".format(mot, nombre) for mot, nombre in veille.mots[:10]))
    if veille.communautes:
        lignes.append("Communautes : " + ", ".join(
            "r/" + c["nom"] for c in veille.communautes[:5]))
    lignes.append("Reprends LEURS mots pour formuler les promesses, pas un "
                  "vocabulaire de brochure.")
    return "\n".join(lignes)
