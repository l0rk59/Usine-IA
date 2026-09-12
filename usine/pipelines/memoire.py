"""La memoire d'une fiction : ce que la scene N sait de la scene 1.

La chaine « nouvelle » porte un resume roulant : un etat de l'histoire, en
quatre-vingt-dix mots, reecrit apres chaque scene. Il tient une nouvelle. La
question posee par le roman est : jusqu'ou ?

## Ce qui a ete mesure

Un resume de taille FIXE reecrit a chaque scene est un tampon : il ne grandit
pas, et ce qu'on y ajoute chasse ce qui y etait. La mesure est arithmetique
avant d'etre litteraire — enoncer un evenement demande environ sept mots
(« Camille cache la convocation dans sa poche »), donc quatre-vingt-dix mots
portent une douzaine d'evenements, pas davantage. Au-dela, les plus anciens
sortent, quelle que soit la qualite du modele qui redige.

`tests/test_memoire.py` le mesure sur la vraie boucle, avec un compresseur
deterministe qui represente le MEILLEUR cas possible pour une memoire plate :
aucune perte de paraphrase, uniquement la limite de capacite. Les faits
plantes scene par scene y disparaissent a partir de la treizieme.

S'y ajoute un second effet, invisible dans l'arithmetique : un fait pose a la
scene 1 traverse N-1 reecritures avant la scene N. Chaque reecriture est un
reencodage avec perte. Le tampon ne se contente pas de se remplir — il
deforme ce qu'il garde.

## Ce qui en decoule

Agrandir le resume ne resout rien : il faudrait sept mots de plus par scene,
donc un resume proportionnel a la longueur du livre, qu'il faudrait relire
entierement a chaque scene. C'est le cout qu'on voulait eviter.

La memoire hierarchique, elle, repose sur une seule propriete : **le resume
d'une partie close est ecrit UNE fois et n'est plus jamais reecrit.** Il ne
subit donc ni troncature ni reencodage. La capacite devient
« nombre de parties x taille d'un resume », et croit avec le livre, tandis
que le cout par scene reste celui d'un seul resume roulant — celui de la
partie en cours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Union

# Mots necessaires pour enoncer un evenement de facon exploitable. Mesure sur
# les etats reellement produits, pas choisi : voir tests/test_memoire.py.
MOTS_PAR_EVENEMENT = 7


def capacite(mots_resume: int, mots_par_evenement: int = MOTS_PAR_EVENEMENT) -> int:
    """Nombre de scenes qu'un resume de cette taille peut porter."""
    if mots_par_evenement <= 0:
        return 0
    return max(1, mots_resume // mots_par_evenement)


# Type de la fonction qui redige un resume :
#     (etat precedent, texte a integrer, intitule) -> nouvel etat
# Elle est injectee plutot qu'appelee directement, pour deux raisons : la
# mesure y substitue un compresseur deterministe, et la chaine y met son
# repli quand le modele ne repond pas. L'intitule existe parce que la memoire
# hierarchique demande DEUX choses differentes — l'etat courant apres une
# scene, et le resume d'une partie qui se ferme — et que les distinguer par
# « l'etat est vide » serait un piege pour la premiere scene.
Redacteur = Callable[[str, str, str], str]


@dataclass
class MemoirePlate:
    """Un seul etat, reecrit apres chaque scene. Le comportement d'origine.

    Suffisante tant que l'histoire tient dans sa capacite, et moins chere que
    toute autre : un appel par scene, rien de plus.
    """

    etat: str = ""

    def pour_invite(self) -> str:
        return self.etat or "(rien : c'est la premiere scene)"

    def apres_scene(self, redacteur: Redacteur, texte: str, intitule: str = "",
                    index: int = 0, total: int = 0) -> None:  # noqa: ARG002
        self.etat = redacteur(self.etat, texte, intitule)

    def etat_courant(self) -> str:
        """L'etat qui vient de bouger.

        Le controle de continuite compare deux etats successifs pour reperer
        une scene qui n'a rien fait avancer : il doit donc lire ce qui CHANGE,
        pas l'historique accumule.
        """
        return self.etat


@dataclass
class MemoireHierarchique:
    """Des parties closes, figees, plus l'etat de la partie en cours.

    Une partie qui se ferme est resumee UNE fois, puis n'est plus touchee.
    C'est toute l'idee : ce qui ne se reecrit pas ne se degrade pas.

    Le cout par scene reste celui d'un resume roulant — la partie en cours —
    et s'y ajoute un appel a chaque fermeture de partie, soit trois ou quatre
    pour un livre entier.
    """

    scenes_par_partie: int = 6
    closes: List[str] = field(default_factory=list)
    courante: str = ""
    # Texte accumule de la partie en cours, d'ou son resume sera tire.
    _matiere: List[str] = field(default_factory=list, repr=False)

    def pour_invite(self) -> str:
        morceaux = []
        for numero, partie in enumerate(self.closes, 1):
            morceaux.append("Partie {} : {}".format(numero, partie))
        if self.courante:
            morceaux.append("Partie en cours : {}".format(self.courante))
        return "\n".join(morceaux) or "(rien : c'est la premiere scene)"

    def apres_scene(self, redacteur: Redacteur, texte: str, intitule: str = "",
                    index: int = 0, total: int = 0) -> None:
        """index est celui de la scene qui vient d'etre ecrite, a partir de 0."""
        self.courante = redacteur(self.courante, texte, intitule)
        self._matiere.append(texte)
        if self._ferme_une_partie(index, total):
            numero = len(self.closes) + 1
            self.closes.append(redacteur("", "\n".join(self._matiere),
                                         "Partie {}".format(numero)))
            self._matiere = []
            self.courante = ""

    def _ferme_une_partie(self, index: int, total: int) -> bool:
        """Vrai quand la scene qui vient d'etre ecrite termine une partie.

        La derniere scene du livre ne ferme rien : figer une partie que plus
        aucune scene ne lira couterait un appel pour personne.
        """
        if total and index >= total - 1:
            return False
        return (index + 1) % max(1, self.scenes_par_partie) == 0

    def etat_courant(self) -> str:
        """Seulement la partie en cours — voir MemoirePlate.etat_courant.

        Rendre l'historique entier ferait comparer au controle de continuite
        deux etats qui partagent toutes leurs parties closes : leur
        recouvrement serait quasi total, et chaque scene serait signalee comme
        ne faisant rien avancer.
        """
        return self.courante


def choisir(nb_scenes: int,
            mots_resume: int) -> Union[MemoirePlate, MemoireHierarchique]:
    """La memoire la moins chere qui tienne l'histoire demandee.

    En dessous de la capacite mesuree, la memoire plate suffit et coute moins :
    la hierarchie n'apporterait que des appels de fermeture pour rien. Au-dela,
    elle ne suffit plus, et ce n'est pas une question de reglage.

    Les parties font la moitie de la capacite : l'etat de la partie en cours
    doit porter ses propres scenes AVEC de la marge, puisqu'il porte aussi ce
    qui reste en suspens.
    """
    plafond = capacite(mots_resume)
    if nb_scenes <= plafond:
        return MemoirePlate()
    return MemoireHierarchique(scenes_par_partie=max(2, plafond // 2))
