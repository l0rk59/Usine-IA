"""Controle qualite deterministe, sans aucun appel IA.

Beaucoup de defauts d'un texte genere se mesurent localement : tics de
langage, repetitions, phrases toutes de la meme longueur, chiffres precis sans
source, promesses de resultat. Les detecter en Python plutot qu'en demandant a
un modele de les chercher a trois avantages : c'est instantane, c'est gratuit
en quota, et c'est reproductible — deux executions donnent la meme note.

Le relecteur IA n'intervient qu'ensuite, sur ce qui demande un jugement :
la pertinence, la progression, la tenue de la promesse.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------------
# 1. Tics d'ecriture des modeles (« slop »)
# --------------------------------------------------------------------------

TICS = [
    r"il est important de (noter|souligner|mentionner|comprendre)",
    r"il convient de (souligner|noter|rappeler)",
    r"il (ne )?faut (pas oublier|savoir|noter) que",
    r"dans (un monde|le monde) (ou|d'aujourd'hui)",
    r"a l'ere (du|de la|des)",
    r"en conclusion",
    r"pour (conclure|resumer|recapituler)",
    r"en (somme|definitive|resume)",
    r"force est de constater",
    r"nous allons (voir|explorer|decouvrir|aborder|plonger)",
    r"explorons (ensemble|maintenant)",
    r"plongeons dans",
    r"passons (maintenant )?a",
    r"comme nous l'avons vu",
    r"dans ce chapitre, nous",
    r"n'oublions pas que",
    r"gardons a l'esprit",
    r"il est essentiel de",
    r"joue un role (cle|crucial|essentiel|primordial)",
    r"revolutionn(e|er|aire)",
    r"a l'heure actuelle",
    r"de nos jours",
    r"que vous soyez .{3,40} ou .{3,40},",
    r"la cle (du|de la|reside)",
    r"veritable (atout|levier|game.changer)",
    r"incontournable",
    r"il n'en demeure pas moins",
    r"sans plus attendre",
    r"le monde (fascinant|passionnant) de",
]

# Ce qu'un modele laisse quand il n'a pas fini : une consigne a l'AUTEUR,
# jamais une phrase pour le lecteur. « [Inserer un exemple concret ici] » dans
# un livre vendu le fait paraitre inacheve, et rien ne le signalait. La
# chaine « ebook-factory », comparee le 23/09/2026, verifie l'absence de
# « TODO » et « LOREM » avant de livrer ; nous non.
#
# Vocabulaire ferme, et volontairement etroit. « [a completer] » n'y est pas :
# un guide pratique en met dans ses exercices, et c'est au lecteur qu'il
# parle. « [VOTRE PRODUIT] » non plus : c'est la variable d'un modele. Ni un
# « todo » nu : « ma todo list » est une phrase. On rate un marqueur plutot
# que d'accuser un exercice. Lu sur le texte sans accents.
_MARQUEURS_DE_TRAVAIL = re.compile(
    r"\blorem ipsum\b"
    r"|[\[(]\s*(?:inserer|todo|tbd|xxx+|placeholder|a rediger|a developper)"
    r"\b[^\])\n]{0,120}[\])]",
    re.IGNORECASE)


def tics_lisibles() -> List[str]:
    """Les tics de TICS, ecrits comme un auteur les lirait.

    Une seule liste pour les deux usages. Le detecteur en connaissait
    vingt-neuf ; la consigne envoyee aux agents en citait DEUX — « dans un
    monde ou », « il est important de noter ». Les vingt-sept autres n'etaient
    appris qu'apres coup, au prix d'une passe de correction par section : un
    appel de modele complet pour retirer « plongeons dans ». Les deux listes
    etaient tenues a la main, separement, et divergeaient deja.

    Chaque motif donne sa premiere variante : « (noter|souligner) » devient
    « noter », un groupe facultatif est garde (« il ne faut pas oublier »), et
    un intervalle libre devient « … ». Un test verifie qu'aucune syntaxe de
    motif ne passe dans la consigne quand on ajoute un tic.
    """
    rendus = []
    for motif in TICS:
        m = re.sub(r"\(([^()|]+)\)\?", r"\1", motif)            # facultatif garde
        m = re.sub(r"\(([^()|]+)(?:\|[^()]+)?\)", r"\1", m)      # 1re variante
        m = m.replace(".{3,40}", "…").replace(r"\b", "").replace(r"\s?", " ")
        m = m.replace("game.changer", "game changer")
        rendus.append(re.sub(r"\s+", " ", m).strip(" ,"))
    return rendus


# Promesses de resultat : risque commercial et juridique pour le vendeur.
PROMESSES = [
    r"garanti(e|s|es)?\b",
    r"resultats? garantis?",
    r"100\s?% (de reussite|efficace|garanti)",
    r"vous allez (forcement|obligatoirement|certainement) (gagner|reussir|doubler)",
    r"sans (aucun )?risque",
    r"argent facile",
    r"devenez riche",
    r"en un temps record",
    r"du jour au lendemain",
]

# Un chiffre precis sans source est la premiere cause de produit non credible.
CHIFFRE_PRECIS = re.compile(
    r"\b\d{1,3}(?:[.,]\d+)?\s?%|\b\d+\s?(?:fois plus|x plus)\b", re.IGNORECASE)
MARQUEUR_SOURCE = re.compile(
    r"\b(selon|d'apres|source\s*:|etude|sondage|rapport|enquete|par exemple|"
    r"exemple|imaginons|supposons|admettons|fictif|illustrat)", re.IGNORECASE)

_COMPILES_TICS = [re.compile(m, re.IGNORECASE) for m in TICS]
_COMPILES_PROMESSES = [re.compile(m, re.IGNORECASE) for m in PROMESSES]


def _sans_accent(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")


# --------------------------------------------------------------------------
# 2. Resultat
# --------------------------------------------------------------------------


@dataclass
class Anomalie:
    genre: str
    gravite: str            # bloquant | majeur | mineur
    detail: str
    extrait: str = ""
    consigne: str = ""      # instruction de correction, injectable dans un prompt
    poids: float = 0.0      # 0 = poids par defaut de la gravite

    def cout(self) -> float:
        """Points retires de la note.

        La gravite dit la categorie, le poids dit l'ampleur : un texte a
        170 tics pour 1000 mots ne doit pas etre note comme un texte a 6 tics,
        alors que les deux sont « bloquants ».
        """
        defauts = {"bloquant": 3.0, "majeur": 1.5, "mineur": 0.5}
        return self.poids if self.poids > 0 else defauts.get(self.gravite, 0.5)


@dataclass
class Controle:
    note: float                                   # sur 10
    mesures: Dict[str, Any] = field(default_factory=dict)
    anomalies: List[Anomalie] = field(default_factory=list)

    @property
    def bloquantes(self) -> List[Anomalie]:
        return [a for a in self.anomalies if a.gravite == "bloquant"]

    @property
    def acceptable(self) -> bool:
        return self.note >= 7.0 and not self.bloquantes

    def consignes(self) -> List[str]:
        """Instructions de correction, sans doublon, les plus graves d'abord."""
        ordre = {"bloquant": 0, "majeur": 1, "mineur": 2}
        vues: List[str] = []
        for anomalie in sorted(self.anomalies, key=lambda a: ordre.get(a.gravite, 3)):
            if anomalie.consigne and anomalie.consigne not in vues:
                vues.append(anomalie.consigne)
        return vues

    def resume(self) -> str:
        if not self.anomalies:
            return "{}/10 — aucun defaut mesurable".format(round(self.note, 1))
        return "{}/10 — {} defaut(s), dont {} bloquant(s)".format(
            round(self.note, 1), len(self.anomalies), len(self.bloquantes))


# --------------------------------------------------------------------------
# 3. Mesures elementaires
# --------------------------------------------------------------------------

_MOT = re.compile(r"\b[\wàâäéèêëîïôöùûüÿçœæ'-]+\b", re.IGNORECASE | re.UNICODE)
_PHRASE = re.compile(r"[^.!?…]+[.!?…]+", re.UNICODE)


def mots(texte: str) -> List[str]:
    return _MOT.findall(texte.lower())


def phrases(texte: str) -> List[str]:
    sans_titres = re.sub(r"^#{1,6} .*$", "", texte, flags=re.MULTILINE)
    sans_listes = re.sub(r"^\s*[-*+\d.)]+\s+", "", sans_titres, flags=re.MULTILINE)
    trouvees = [p.strip() for p in _PHRASE.findall(sans_listes) if len(p.strip()) > 1]
    return trouvees


def repetition_ngrammes(liste_mots: List[str], n: int = 4) -> float:
    """Part des n-grammes qui apparaissent plus d'une fois. 0 = aucune repetition."""
    if len(liste_mots) <= n:
        return 0.0
    grammes = [tuple(liste_mots[i:i + n]) for i in range(len(liste_mots) - n + 1)]
    return 1.0 - (len(set(grammes)) / len(grammes))


def diversite_lexicale(liste_mots: List[str]) -> float:
    """Diversite du vocabulaire, normalisee par fenetres de 300 mots.

    Le rapport brut mots uniques / mots total chute mecaniquement quand le
    texte s'allonge : le mesurer par fenetres rend les chapitres comparables
    entre eux quelle que soit leur longueur.
    """
    if not liste_mots:
        return 0.0
    fenetre = 300
    if len(liste_mots) <= fenetre:
        return len(set(liste_mots)) / len(liste_mots)
    scores = [
        len(set(liste_mots[i:i + fenetre])) / fenetre
        for i in range(0, len(liste_mots) - fenetre + 1, fenetre)
    ]
    return sum(scores) / len(scores)


def rythme(liste_phrases: List[str]) -> Tuple[float, float]:
    """(longueur moyenne, ecart-type) en mots.

    Un ecart-type faible trahit un texte genere : les humains alternent
    naturellement phrases courtes et longues.
    """
    longueurs = [len(mots(p)) for p in liste_phrases if mots(p)]
    if len(longueurs) < 3:
        return (float(sum(longueurs)) if longueurs else 0.0, 0.0)
    return (statistics.mean(longueurs), statistics.pstdev(longueurs))


def chiffres_sans_source(texte: str) -> List[str]:
    """Pourcentages et multiples enonces sans marqueur d'exemple ni de source."""
    suspects: List[str] = []
    for phrase in phrases(texte):
        if CHIFFRE_PRECIS.search(phrase) and not MARQUEUR_SOURCE.search(phrase):
            suspects.append(phrase.strip()[:160])
    return suspects


def continuite(texte: str, precedents: List[str]) -> float:
    """Recouvrement du vocabulaire specifique avec les sections precedentes.

    Mesure si la section s'inscrit dans le livre ou part ailleurs. On ne
    compare que les mots longs, porteurs de sens, et on rapporte au plus petit
    des deux ensembles pour ne pas penaliser une section courte.
    """
    if not precedents:
        return 1.0
    interessants = lambda t: {m for m in mots(t) if len(m) >= 6}  # noqa: E731
    avant = interessants(" ".join(precedents))
    ici = interessants(texte)
    if not avant or not ici:
        return 1.0
    commun = len(avant & ici)
    return min(1.0, commun / min(len(avant), len(ici)) * 2.2)


def structure(texte: str) -> Dict[str, int]:
    return {
        "titres2": len(re.findall(r"^## ", texte, re.MULTILINE)),
        "titres3": len(re.findall(r"^### ", texte, re.MULTILINE)),
        "listes": len(re.findall(r"^\s*(?:[-*+]|\d+[.)])\s+", texte, re.MULTILINE)),
        "paragraphes": len([b for b in texte.split("\n\n") if len(b.strip()) > 80]),
    }


# --------------------------------------------------------------------------
# 4. Controle complet
# --------------------------------------------------------------------------


def controler(
    texte: str,
    mots_cibles: int = 0,
    precedents: List[str] = None,
    exiger_structure: bool = True,
) -> Controle:
    """Analyse une section et renvoie une note sur 10 avec les corrections."""
    precedents = precedents or []
    liste_mots = mots(texte)
    liste_phrases = phrases(texte)
    nb_mots = len(liste_mots)
    anomalies: List[Anomalie] = []

    # --- tics d'ecriture ---------------------------------------------------
    trouves: List[str] = []
    normalise = _sans_accent(texte)
    for motif in _COMPILES_TICS:
        for occurrence in motif.findall(normalise):
            trouves.append(occurrence if isinstance(occurrence, str) else motif.pattern)
    densite_tics = (len(trouves) / nb_mots * 1000) if nb_mots else 0.0
    if len(trouves) >= 3 or densite_tics > 2.5:
        anomalies.append(Anomalie(
            "tics", "bloquant" if len(trouves) >= 6 else "majeur",
            "{} tics d'ecriture d'IA ({:.1f} pour 1000 mots)".format(
                len(trouves), densite_tics),
            consigne="Supprimer les transitions mecaniques et les formules creuses "
                     "(« il est important de noter », « en conclusion », « nous allons "
                     "voir », « dans un monde ou »). Entrer directement dans le propos.",
            poids=min(8.0, 1.0 + densite_tics / 22.0 + len(trouves) * 0.35),
        ))
    elif trouves:
        anomalies.append(Anomalie(
            "tics", "mineur", "{} tic(s) d'ecriture".format(len(trouves)),
            consigne="Retirer les quelques formules de transition generiques restantes."))

    # --- marqueurs de travail laisses par le modele --------------------------
    marqueurs = [m.group(0) for m in _MARQUEURS_DE_TRAVAIL.finditer(normalise)]
    if marqueurs:
        anomalies.append(Anomalie(
            "marqueur", "bloquant",
            "{} marqueur(s) de travail laisse(s) dans le texte".format(len(marqueurs)),
            extrait=marqueurs[0][:160],
            consigne="Remplacer chaque marqueur provisoire ([Inserer ...], "
                     "[TODO], lorem ipsum) par le contenu qu'il annonce, ecrit "
                     "en entier. Si ce contenu n'existe pas, supprimer la phrase.",
            poids=min(6.0, 3.0 + len(marqueurs)),
        ))

    # --- promesses de resultat ---------------------------------------------
    promesses = []
    for motif in _COMPILES_PROMESSES:
        promesses.extend(motif.findall(normalise))
    if promesses:
        anomalies.append(Anomalie(
            "promesse", "bloquant",
            "{} promesse(s) de resultat detectee(s)".format(len(promesses)),
            poids=min(6.0, 3.0 + len(promesses) * 0.8),
            consigne="Retirer toute promesse de resultat garanti ou de gain rapide : "
                     "reformuler en termes de methode et de probabilite, jamais de "
                     "certitude.",
        ))

    # --- chiffres invérifiables --------------------------------------------
    suspects = chiffres_sans_source(texte)
    if suspects:
        anomalies.append(Anomalie(
            "chiffre", "majeur" if len(suspects) > 1 else "mineur",
            "{} chiffre(s) precis sans source ni cadrage".format(len(suspects)),
            extrait=suspects[0],
            consigne="Pour chaque pourcentage ou multiple cite, soit l'introduire "
                     "explicitement comme un exemple (« imaginons », « par exemple »), "
                     "soit le supprimer. Ne jamais presenter un chiffre invente comme "
                     "une statistique.",
        ))

    # --- repetition ---------------------------------------------------------
    rep4 = repetition_ngrammes(liste_mots, 4)
    rep6 = repetition_ngrammes(liste_mots, 6)
    if rep4 > 0.06 or rep6 > 0.02:
        anomalies.append(Anomalie(
            "repetition", "majeur" if rep4 > 0.10 else "mineur",
            "repetition de blocs : {:.1%} sur 4 mots, {:.1%} sur 6".format(rep4, rep6),
            consigne="Reformuler les passages qui reprennent les memes suites de mots. "
                     "Varier le vocabulaire et la construction des phrases.",
        ))

    # --- diversite lexicale -------------------------------------------------
    diversite = diversite_lexicale(liste_mots)
    if nb_mots > 200 and diversite < 0.42:
        anomalies.append(Anomalie(
            "vocabulaire", "mineur",
            "vocabulaire pauvre (diversite {:.2f})".format(diversite),
            consigne="Enrichir le vocabulaire : remplacer les mots repetes par des "
                     "synonymes precis plutot que generiques.",
        ))

    # --- rythme --------------------------------------------------------------
    moyenne, ecart = rythme(liste_phrases)
    # On juge la variation RELATIVE : un ecart-type de 4 est faible sur des
    # phrases de 25 mots, mais large sur des phrases de 7. Le coefficient de
    # variation rend le critere independant du style choisi.
    variation = (ecart / moyenne) if moyenne else 0.0
    if len(liste_phrases) >= 6:
        if variation < 0.35:
            anomalies.append(Anomalie(
                "rythme", "majeur",
                "phrases trop uniformes (moyenne {:.0f} mots, variation {:.2f})".format(
                    moyenne, variation),
                consigne="Casser l'uniformite : alterner des phrases tres courtes "
                         "(3 a 6 mots) et des phrases longues. Une phrase breve apres "
                         "une longue cree le rythme.",
            ))
        if moyenne > 32:
            anomalies.append(Anomalie(
                "rythme", "mineur",
                "phrases trop longues (moyenne {:.0f} mots)".format(moyenne),
                consigne="Couper les phrases de plus de 30 mots en deux.",
            ))

    # --- structure -----------------------------------------------------------
    plan = structure(texte)
    if exiger_structure and nb_mots > 400:
        if plan["titres2"] == 0:
            anomalies.append(Anomalie(
                "structure", "majeur", "aucun sous-titre de niveau 2",
                consigne="Decouper le texte avec des sous-titres markdown de niveau 2 "
                         "(##), un par idee principale."))
        if plan["listes"] == 0:
            anomalies.append(Anomalie(
                "structure", "mineur", "aucune liste",
                consigne="Ajouter au moins une liste d'etapes numerotees applicables."))

    # --- volume --------------------------------------------------------------
    ratio = nb_mots / mots_cibles if mots_cibles else 1.0
    if mots_cibles and ratio < 0.6:
        anomalies.append(Anomalie(
            "volume", "bloquant" if ratio < 0.4 else "majeur",
            "{} mots pour {} attendus ({:.0%})".format(nb_mots, mots_cibles, ratio),
            consigne="Developper : ajouter un exemple detaille et une section "
                     "supplementaire pour atteindre environ {} mots.".format(mots_cibles),
            poids=min(6.0, (0.6 - ratio) * 10.0),
        ))

    # --- continuite -----------------------------------------------------------
    lien = continuite(texte, precedents)
    if precedents and lien < 0.35:
        anomalies.append(Anomalie(
            "continuite", "mineur",
            "faible lien avec les sections precedentes ({:.2f})".format(lien),
            consigne="Rattacher cette section au reste du livre : rappeler en une "
                     "phrase ce qui precede et ce que cette section y ajoute.",
        ))

    mesures = {
        "mots": nb_mots,
        "phrases": len(liste_phrases),
        "tics": len(trouves),
        "densite_tics": round(densite_tics, 2),
        "promesses": len(promesses),
        "chiffres_sans_source": len(suspects),
        "repetition_4grammes": round(rep4, 4),
        "repetition_6grammes": round(rep6, 4),
        "diversite_lexicale": round(diversite, 3),
        "phrase_moyenne": round(moyenne, 1),
        "phrase_ecart_type": round(ecart, 1),
        "phrase_variation": round(variation, 2),
        "continuite": round(lien, 2),
        "ratio_volume": round(ratio, 2),
    }
    mesures.update(plan)
    return Controle(note=_noter(anomalies), mesures=mesures, anomalies=anomalies)


def _noter(anomalies: List[Anomalie]) -> float:
    """10 moins le cout cumule des defauts, borne a 0."""
    return max(0.0, round(10.0 - sum(a.cout() for a in anomalies), 2))


def controler_ensemble(sections: List[Tuple[str, str]],
                       mots_cibles: int = 0) -> Dict[str, Any]:
    """Controle chaque section d'un produit, en tenant compte des precedentes."""
    resultats = []
    precedents: List[str] = []
    for titre, corps in sections:
        resultat = controler(corps, mots_cibles, precedents)
        resultats.append({
            "section": titre,
            "note": resultat.note,
            "mesures": resultat.mesures,
            "anomalies": [
                {"genre": a.genre, "gravite": a.gravite, "detail": a.detail,
                 "extrait": a.extrait}
                for a in resultat.anomalies
            ],
        })
        precedents.append(corps)
    notes = [r["note"] for r in resultats]
    return {
        "sections": resultats,
        "note_moyenne": round(sum(notes) / len(notes), 2) if notes else None,
        "note_min": min(notes) if notes else None,
        "sections_bloquantes": [
            r["section"] for r in resultats
            if any(a["gravite"] == "bloquant" for a in r["anomalies"])
        ],
    }
