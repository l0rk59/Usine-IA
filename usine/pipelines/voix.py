"""Qui parle, et combien. Le controle des repliques d'une fiction.

La bible donne a chaque personnage une VOIX — « registre, tic de langage, ce
qu'il ne dit jamais » — et cette voix part dans l'invite de chaque scene :
« Chaque personnage parle avec la voix que lui donne la bible. » C'est une
promesse faite au modele, et jusqu'ici rien ne verifiait qu'elle avait ete
tenue. Le defaut est exactement celui que l'usine traque partout ailleurs :
une consigne emise, jamais relue.

Ce module releve les repliques et les rattache a qui les prononce, puis mesure
ce qui se mesure sans comprendre le francais : qui parle, combien, et de
quelle longueur.

CE QU'IL AFFIRME. Deux constats seulement, parce que deux seulement se tiennent
sans seuil invente :

  - un personnage present dans la prose et qui ne prend jamais la parole ;
  - un personnage qui confisque la parole a lui seul.

CE QU'IL N'AFFIRME PAS. « Les personnages parlent tous de la meme voix » est le
defaut le plus courant de la fiction generee, et ce module ne le declare pas.
Le declarer demanderait un seuil sur la distance entre deux profils, et ce
seuil n'a pas ete mesure sur de la fiction reelle : l'inventer produirait un
garde-fou qui crie a tort, donc un garde-fou que personne ne lit. Les profils
sont donc RENDUS — longueur moyenne des repliques, part de questions, part
d'exclamations, diversite du vocabulaire — et c'est un humain qui les regarde.
Une mesure honnete vaut mieux qu'un verdict fabrique.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .faits import _plat, nommes

# Verbes qui introduisent une replique dans une incise. La liste est fermee et
# se lit sans accent : c'est ce qui permet de rattacher « dit Camille » sans
# rattacher « Camille entra ».
VERBES_DE_PAROLE = (
    "dit", "dis", "repondit", "repond", "repliqua", "reprit", "ajouta",
    "demanda", "interrogea", "questionna", "murmura", "chuchota", "souffla",
    "cria", "hurla", "s'exclama", "exclama", "lanca", "lacha", "articula",
    "balbutia", "begaya", "grogna", "gronda", "soupira", "siffla", "glissa",
    "coupa", "insista", "protesta", "objecta", "admit", "avoua", "concéda",
    "conceda", "annonca", "declara", "affirma", "promit", "jura", "renchérit",
    "rencherit", "corrigea", "trancha", "conclut", "ironisa", "plaisanta",
    "expliqua", "precisa", "rappela", "appela", "supplia", "implora",
    "marmonna", "bredouilla", "constata", "remarqua", "observa", "nota",
    "fit", "reprend", "sourit", "grimaca",
)
_VERBE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in VERBES_DE_PAROLE) + r")\b")

# Trois facons d'ecrire un dialogue en francais, toutes trois produites par
# les modeles : le tiret cadratin en debut de ligne, les guillemets francais,
# les guillemets droits quand le modele oublie la typographie francaise.
_TIRET = re.compile(r"^\s*[—–-]\s*(.+)$")
_GUILLEMETS = re.compile(r"[«\"]\s*(.+?)\s*[»\"]", re.DOTALL)

# Une incise de plus de cette longueur n'est plus une incise : c'est de la
# narration, et le nom qu'on y trouve n'est pas forcement celui qui parle.
INCISE_MAX = 120

# En dessous, une moyenne ne veut rien dire. Trois repliques ne font pas une
# voix, et un profil calcule sur trois repliques inviterait a conclure.
REPLIQUES_MINIMUM = 4

# Part de la parole au-dela de laquelle un personnage l'a confisquee. Le
# controle de presence voisin retient 60 % pour le protagoniste ; ici le
# chiffre dit l'inverse — non pas « assez present » mais « trop seul » — et
# il est volontairement haut : dans une nouvelle a deux personnages, soixante
# pour cent des repliques pour l'un des deux est un equilibre normal.
PART_CONFISQUEE = 0.8


def _couper_incise(ligne: str) -> Tuple[str, str]:
    """Separe la replique de son incise dans « — Non, dit Camille ».

    Le tiret cadratin n'a pas de delimiteur de fin : la replique et l'incise
    partagent la ligne. On repere le DERNIER verbe de parole — une replique
    peut contenir « il m'a dit » sans que ce soit l'incise — puis on remonte a
    la virgule qui le precede, la ou le francais ouvre l'incise.
    """
    plate = _plat(ligne)
    dernier = None
    for trouve in _VERBE.finditer(plate):
        dernier = trouve
    if dernier is None:
        return ligne, ""
    virgule = ligne.rfind(",", 0, dernier.start())
    debut = virgule if virgule != -1 else dernier.start()
    return ligne[:debut], ligne[debut:debut + INCISE_MAX]


def _incise(ligne: str, replique: str) -> str:
    """Ce qui entoure une replique delimitee : c'est la qu'est le locuteur."""
    reste = ligne.replace(replique, " ", 1)
    return reste[:INCISE_MAX]


def _locuteur(incise: str, noms: Iterable[str]) -> Optional[str]:
    """Personnage a qui l'incise attribue la replique.

    Deux conditions, toutes deux necessaires : un verbe de parole, et un seul
    personnage nomme. Sans le verbe, « Camille recula. — Non. » attribuerait a
    Camille une replique qui peut etre de l'autre. Sans l'unicite, une incise
    qui nomme deux personnages ferait deviner lequel parle — et deviner est ce
    que ce module refuse de faire.
    """
    if not _VERBE.search(_plat(incise)):
        return None
    presents = nommes(incise, noms)
    return presents[0] if len(presents) == 1 else None


def repliques(sections: List[Tuple[str, str]],
              noms: Iterable[str]) -> List[Dict[str, str]]:
    """Repliques attribuees a un personnage nomme, dans l'ordre du texte."""
    noms = list(noms)
    trouvees: List[Dict[str, str]] = []
    for titre, corps in sections:
        for ligne in corps.splitlines():
            # Le meme mot s'ecrit de deux facons en Unicode : « é » en un
            # caractere, ou « e » suivi d'un accent combinant. Les modeles
            # produisent les deux. Sans recomposition, « _plat » rend un texte
            # PLUS COURT que l'original — et la coupe de l'incise, cherchee
            # dans l'un puis appliquee a l'autre, tombe quelques caracteres
            # plus loin : l'incise emporte alors la fin de la replique.
            ligne = unicodedata.normalize("NFC", ligne).strip()
            if not ligne:
                continue
            # Deux formes, deux facons de trouver l'incise. Entre guillemets,
            # la replique est delimitee : l'incise est tout le reste. Au tiret
            # cadratin, il faut la couper.
            candidates: List[Tuple[str, str]] = [
                (brute, _incise(ligne, brute))
                for brute in _GUILLEMETS.findall(ligne)
            ]
            tiret = _TIRET.match(ligne)
            if tiret and not candidates:
                candidates.append(_couper_incise(tiret.group(1)))
            for brute, incise in candidates:
                qui = _locuteur(incise, noms)
                if not qui:
                    continue
                texte = brute.strip(" ,;:—–-")
                if texte:
                    trouvees.append({"personnage": qui, "texte": texte,
                                     "section": titre})
    return trouvees


_MOT = re.compile(r"[^\W\d_]+", re.UNICODE)


def profil(textes: List[str]) -> Dict[str, Any]:
    """Ce qui se mesure d'une facon de parler, sans comprendre le francais."""
    if not textes:
        return {"repliques": 0}
    mots_par_replique = [len(_MOT.findall(t)) for t in textes]
    tous = [_plat(m) for t in textes for m in _MOT.findall(t)]
    return {
        "repliques": len(textes),
        "mots_moyens": round(statistics.mean(mots_par_replique), 1),
        "ecart_type": round(statistics.pstdev(mots_par_replique), 1)
                      if len(mots_par_replique) > 1 else 0.0,
        "questions": round(sum(1 for t in textes if "?" in t) / len(textes), 2),
        "exclamations": round(
            sum(1 for t in textes if "!" in t) / len(textes), 2),
        "diversite": round(len(set(tous)) / len(tous), 2) if tous else 0.0,
    }


def controler(sections: List[Tuple[str, str]],
              personnages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Qui parle dans ce texte, combien, et de quelle facon."""
    noms = [p["nom"] for p in personnages]
    dites = repliques(sections, noms)
    par_personnage: Dict[str, List[str]] = {nom: [] for nom in noms}
    for replique in dites:
        par_personnage[replique["personnage"]].append(replique["texte"])

    profils = {nom: profil(textes) for nom, textes in par_personnage.items()}
    anomalies: List[Dict[str, str]] = []

    # -- 1. un personnage qui ne prend jamais la parole ---------------------
    # Seulement s'il y a du dialogue ailleurs : une nouvelle entierement
    # narrative ne doit pas etre accusee pour chacun de ses personnages.
    texte_entier = "\n".join(corps for _, corps in sections)
    if dites:
        for personnage in personnages:
            nom = personnage["nom"]
            if par_personnage[nom]:
                continue
            if not nommes(texte_entier, [nom]):
                continue  # absent du texte : c'est l'autre controle qui le dit
            protagoniste = personnage.get("role", "").startswith("protagon")
            anomalies.append({
                "genre": "personnage_muet",
                "gravite": "majeur" if protagoniste else "mineur",
                "detail": "« {} » ({}) est present mais ne prend jamais la "
                          "parole".format(nom, personnage.get("role") or "role inconnu"),
            })

    # -- 2. un personnage qui confisque la parole ---------------------------
    if len(dites) >= REPLIQUES_MINIMUM and len(noms) > 1:
        for nom, textes in par_personnage.items():
            part = len(textes) / len(dites)
            if part >= PART_CONFISQUEE:
                anomalies.append({
                    "genre": "parole_confisquee",
                    "gravite": "mineur",
                    "detail": "« {} » prononce {} % des repliques ({} sur "
                              "{})".format(nom, int(part * 100), len(textes),
                                           len(dites)),
                })

    parlants = [n for n, p in profils.items()
                if p.get("repliques", 0) >= REPLIQUES_MINIMUM]
    return {
        "repliques": len(dites),
        "profils": profils,
        # Les profils ne valent d'etre compares qu'au-dela de quelques
        # repliques ; en dessous, la moyenne est du bruit. Ce chiffre dit sur
        # combien de personnages la comparaison a un sens.
        "comparables": parlants,
        "anomalies": anomalies,
        "resume": ("{} replique(s) attribuee(s) a {} personnage(s)".format(
            len(dites), sum(1 for p in profils.values() if p.get("repliques"))) 
            if dites else "aucun dialogue attribue"),
    }
