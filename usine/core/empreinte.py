"""Ce que l'usine a deja ecrit.

Le probleme que ce module resout n'apparait qu'au volume. Une usine qui
fabrique quatre produits par jour sur des niches voisines — « la prospection
pour freelances », « trouver des clients en freelance », « demarcher sans se
vendre » — produit trois fois le meme livre avec des mots differents. Ni le
modele ni le controle qualite ne peuvent le voir : chacun ne regarde qu'un
produit a la fois, et chacun le trouve bon.

Les consequences sont commerciales, pas esthetiques. Une place de marche
retire les doublons. Un acheteur qui a pris deux de vos produits et decouvre
le meme livre demande deux remboursements et ne revient pas.

Jusqu'ici, la seule protection etait une comparaison de CHAINES : la file
refusait le couple (sujet, type) deja en attente. « La prospection pour
freelances » et « Prospection freelance » y passaient sans encombre.

Ce module compare ce qui est ecrit, pas ce qui est demande. Deux mesures,
parce que deux choses differentes peuvent se repeter :

  TEXTE    des phrases reprises telles quelles, mesurees par MinHash sur des
           quintuplets de mots — robuste au remaniement, insensible a la
           longueur.
  PLAN     la meme charpente sous d'autres mots : deux livres dont les
           chapitres se correspondent un a un sont le meme livre, meme si
           aucune phrase n'est commune. C'est le cas le plus frequent, et
           celui qu'une comparaison de texte seule laisse passer.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Taille de la signature. 128 empreintes donnent une erreur type d'environ
# 1/sqrt(128), soit ~9 points de Jaccard — assez fin pour distinguer 0,2 de
# 0,6, ce qui est la seule decision a prendre. Monter a 512 couterait quatre
# fois plus pour un gain que les seuils ne sauraient pas exploiter.
EMPREINTES = 128

# Longueur des groupes de mots compares. Trop court (2-3), deux textes du
# meme domaine se ressemblent tous ; trop long (8+), la moindre reecriture
# casse la correspondance.
GROUPE = 5

_MOT = re.compile(r"[a-z0-9]+")
_PREMIER = (1 << 61) - 1          # premier de Mersenne : modulo rapide et sur

_SEUIL_TEXTE = 0.30
_SEUIL_PLAN = 0.55


def _sans_accent(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")


def mots_normalises(texte: str) -> List[str]:
    """Mots comparables : sans accent, sans casse, sans ponctuation."""
    return _MOT.findall(_sans_accent(texte or "").lower())


def _hacher(valeur: str) -> int:
    return int(hashlib.blake2b(valeur.encode("utf-8"), digest_size=8).hexdigest(), 16)


def _coefficients() -> List[Tuple[int, int]]:
    """Les EMPREINTES fonctions de hachage, derivees d'une graine fixe.

    Fixe, et c'est indispensable : deux signatures ne sont comparables que si
    elles ont ete calculees avec les memes fonctions. Tirer au hasard rendrait
    incomparables les produits d'avant et d'apres un redemarrage.
    """
    couples = []
    for index in range(EMPREINTES):
        a = _hacher("usine-a-{}".format(index)) | 1      # impair : jamais nul
        b = _hacher("usine-b-{}".format(index))
        couples.append((a % _PREMIER, b % _PREMIER))
    return couples


_COEFFICIENTS = _coefficients()


def groupes(texte: str, taille: int = GROUPE) -> Set[int]:
    """Empreintes des groupes de `taille` mots consecutifs."""
    liste = mots_normalises(texte)
    if len(liste) < taille:
        return {_hacher(" ".join(liste))} if liste else set()
    return {_hacher(" ".join(liste[i:i + taille]))
            for i in range(len(liste) - taille + 1)}


def signature(texte: str) -> List[int]:
    """Signature MinHash d'un texte. Longueur fixe, quelle que soit la taille."""
    empreintes = groupes(texte)
    if not empreintes:
        return []
    resultat = []
    for a, b in _COEFFICIENTS:
        resultat.append(min((a * e + b) % _PREMIER for e in empreintes))
    return resultat


def ressemblance(une: Sequence[int], autre: Sequence[int]) -> float:
    """Jaccard estime entre deux signatures : 0 = rien en commun, 1 = identique."""
    if not une or not autre or len(une) != len(autre):
        return 0.0
    communs = sum(1 for x, y in zip(une, autre) if x == y)
    return communs / len(une)


def jaccard(une: Set[int], autre: Set[int]) -> float:
    """Jaccard exact entre deux ensembles. Sert a verifier l'estimation."""
    if not une or not autre:
        return 0.0
    return len(une & autre) / len(une | autre)


# --------------------------------------------------------------------------
# La charpente
# --------------------------------------------------------------------------

_VIDES = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "ou",
    "a", "au", "aux", "en", "pour", "par", "sur", "dans", "avec", "sans",
    "ce", "cette", "ces", "son", "sa", "ses", "votre", "vos", "que", "qui",
    "comment", "pourquoi", "quand", "chapitre", "module", "partie", "etape",
}


def _racine(mot: str) -> str:
    """Racinisation minimale : le pluriel francais, et rien de plus.

    « freelances » et « freelance » designent la meme niche. Sans cette
    reduction, « La prospection pour freelances » et « Prospection freelance »
    ne partageaient qu'un mot sur deux et passaient sous le seuil.
    """
    if len(mot) > 4 and mot[-1] in ("s", "x") and mot[-2:] not in ("ss", "us"):
        return mot[:-1]
    return mot


def _porteurs(texte: str, vides: Set[str]) -> Set[str]:
    return {_racine(m) for m in mots_normalises(texte)
            if m not in vides and not m.isdigit() and len(m) > 2}


def plan(titres: Iterable[str]) -> List[str]:
    """Charpente comparable : chaque titre reduit a ses mots porteurs.

    « Chapitre 3 — Comment trouver vos premiers clients » et « Etape 2 :
    trouver ses premiers clients » donnent la meme entree. C'est voulu : ce
    sont les memes chapitres.
    """
    reduits = []
    for titre in titres:
        porteurs = sorted(_porteurs(titre, _VIDES))
        if porteurs:
            reduits.append(" ".join(porteurs))
    return reduits


def ressemblance_plan(une: Sequence[str], autre: Sequence[str]) -> float:
    """Part des sections de la plus courte qui trouvent leur equivalent.

    Volontairement asymetrique par la taille : un livre de six chapitres
    entierement contenu dans un livre de douze est un doublon, meme si
    l'inverse ne se dit pas. Le Jaccard classique, lui, le noterait 0,5 et
    laisserait passer.
    """
    if not une or not autre:
        return 0.0
    gauche, droite = set(une), set(autre)
    return len(gauche & droite) / min(len(gauche), len(droite))


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

@dataclass
class Voisin:
    """Un produit deja fabrique, et ce qu'il partage avec celui qui arrive."""

    produit_id: str
    titre: str
    sujet: str
    texte: float          # 0 a 1
    plan: float           # 0 a 1

    @property
    def doublon(self) -> bool:
        return self.texte >= _SEUIL_TEXTE or self.plan >= _SEUIL_PLAN

    @property
    def motif(self) -> str:
        if self.texte >= _SEUIL_TEXTE and self.plan >= _SEUIL_PLAN:
            return "texte et plan"
        if self.texte >= _SEUIL_TEXTE:
            return "texte"
        return "plan"

    def resume(self) -> str:
        return "« {} » — {} commun ({:.0f} % de texte, {:.0f} % de plan)".format(
            self.titre[:48], self.motif, self.texte * 100, self.plan * 100)


def comparer(texte: str, titres: Sequence[str],
             connus: Sequence[Dict[str, object]],
             mienne: Optional[Sequence[int]] = None,
             mon_plan: Optional[Sequence[str]] = None) -> List[Voisin]:
    """Classe les produits deja faits par ressemblance decroissante.

    `connus` : des enregistrements portant produit_id, titre, sujet,
    signature (liste d'entiers) et plan (liste de chaines).
    """
    # La signature d'un ebook de quarante mille mots coute pres de deux
    # secondes : l'appelant qui l'a deja calculee la passe plutot que de la
    # faire refaire.
    mienne = list(mienne) if mienne is not None else signature(texte)
    mon_plan = list(mon_plan) if mon_plan is not None else plan(titres)
    voisins = []
    for connu in connus:
        voisin = Voisin(
            produit_id=str(connu.get("produit_id") or ""),
            titre=str(connu.get("titre") or ""),
            sujet=str(connu.get("sujet") or ""),
            texte=ressemblance(mienne, connu.get("signature") or []),
            plan=ressemblance_plan(mon_plan, connu.get("plan") or []),
        )
        voisins.append(voisin)
    voisins.sort(key=lambda v: (v.texte + v.plan), reverse=True)
    return voisins


# Le vocabulaire de l'emballage, a exclure de la comparaison des niches :
# « Le guide complet de la couture » et « Le guide complet de la peche »
# partagent leur emballage, pas leur sujet.
_VIDES_SUJET = _VIDES | {
    "guide", "complet", "complete", "methode", "manuel", "pack", "kit",
    "systeme", "formation", "cahier", "modele", "livre", "ebook", "cours",
    "tout", "toute", "faire", "reussir", "maitriser", "apprendre", "debutant",
    "debutants", "pro", "professionnel", "pratique", "facile", "simple",
    "meilleur", "meilleure", "nouveau", "nouvelle", "petit", "grand",
}

SEUIL_SUJET = 0.75


# Ce qu'une place de marche colle au nom d'un produit et qui ne dit rien de
# son sujet : le format, le mode de livraison, l'emballage.
_FORMATS = {
    "pdf", "epub", "mobi", "azw", "docx", "doc", "xlsx", "csv", "zip", "png",
    "jpg", "svg", "notion", "canva", "telechargement", "download", "instant",
    "digital", "numerique", "imprimable", "printable", "editable", "bundle",
    "lot", "version", "fichier", "fichiers", "file", "files", "page", "pages",
}

_PARENTHESES = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")


def nettoyer_reference(texte: str) -> str:
    """Retire d'un nom de place de marche ce qui n'est pas son sujet.

    « Le systeme du freelance (PDF + EPUB) » et « Le systeme du freelance
    rentable » ne partageaient qu'un mot porteur sur deux, parce que « pdf »
    et « epub » comptaient comme du sujet. Le produit ne se rattachait donc
    pas a sa propre vente.

    Les segments entre parentheses partent en entier : une place de marche y
    met le format, la mention « instant download », le nombre de pages —
    jamais le sujet.
    """
    sans = _PARENTHESES.sub(" ", texte or "")
    mots = [m for m in mots_normalises(sans) if _racine(m) not in _FORMATS]
    return " ".join(mots)


def ressemblance_reference(reference: str, titre: str) -> float:
    """Proximite d'un nom de vente et d'un titre de produit.

    La liste de mots ecartes n'est PAS celle des niches. Comparer deux
    niches demande d'ignorer le vocabulaire d'emballage — « guide »,
    « cahier », « methode » — parce qu'il ne dit rien du sujet. Comparer
    deux noms de produits demande l'inverse : entre « Cahier du freelance »
    et « Le systeme du freelance rentable », c'est precisement « cahier »
    et « systeme » qui font la difference. Les ecarter rattachait la vente
    d'un cahier a l'ebook voisin.
    """
    vides = _VIDES | _FORMATS
    gauche = _porteurs(nettoyer_reference(reference), vides)
    droite = _porteurs(titre, vides)
    if not gauche or not droite:
        return 0.0
    return len(gauche & droite) / min(len(gauche), len(droite))


def ressemblance_sujet(un: str, autre: str) -> float:
    """Proximite de deux intitules de niche, avant toute fabrication.

    « La prospection pour freelances » et « Prospection freelance » ne se
    ressemblent pas en tant que chaines — la file les acceptait donc toutes
    les deux. Elles partagent pourtant tous leurs mots porteurs.
    """
    gauche = _porteurs(un, _VIDES_SUJET)
    droite = _porteurs(autre, _VIDES_SUJET)
    if not gauche or not droite:
        return 0.0
    return len(gauche & droite) / min(len(gauche), len(droite))



def sujets_proches(sujet: str, type_produit: str = "",
                   seuil: float = SEUIL_SUJET) -> List[Dict[str, object]]:
    """Niches deja fabriquees dont l'intitule recouvre celui-ci.

    Garde-fou d'avant fabrication : il ne voit que l'intitule, donc il rate
    les doublons de contenu — mais il coute zero appel, la ou la verification
    d'apres fabrication coute le produit entier.
    """
    from . import store

    proches = []
    for ligne in store.lister_empreintes(type_produit):
        score = ressemblance_sujet(sujet, str(ligne["sujet"] or ""))
        if score >= seuil:
            proches.append({"produit_id": ligne["produit_id"],
                            "titre": ligne["titre"], "sujet": ligne["sujet"],
                            "score": round(score, 2)})
    proches.sort(key=lambda p: p["score"], reverse=True)
    return proches


def encoder(valeurs: Sequence[object]) -> str:
    return json.dumps(list(valeurs), separators=(",", ":"))


def decoder(brut: Optional[str]) -> List:
    if not brut:
        return []
    try:
        charge = json.loads(brut)
    except (ValueError, TypeError):
        return []
    return charge if isinstance(charge, list) else []
