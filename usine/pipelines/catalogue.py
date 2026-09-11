"""Catalogue des types de produits : la source unique de verite.

Jusqu'ici, la liste des types etait recopiee dans sept fichiers — la CLI, le
moteur continu, le serveur web, son gabarit HTML, le menu, et l'explorateur de
niches. Deux d'entre eux avaient deja diverge, avec une consequence concrete :
l'etude de niche ne pouvait pas proposer « impression » ni « modeles », les
deux types les plus vendus, parce qu'ils manquaient a sa liste locale. Les
idees correspondantes etaient silencieusement converties en ebooks.

Tout se declare desormais ici, une fois. Ajouter un type de produit consiste a
ecrire sa chaine de fabrication et a l'inscrire dans ce catalogue ; les six
autres endroits se mettent a jour seuls.

« Vrai type de produit » signifie : une chaine de fabrication qui lui est
propre, pas une etiquette dans une liste. Un type qui produirait le meme
fichier qu'un autre avec un nom different n'a pas sa place ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class TypeProduit:
    """Un type de produit reellement fabricable."""

    cle: str
    nom: str
    resume: str                       # une ligne, pour les listes
    detail: str                       # ce que l'acheteur recoit, pour le menu
    formats: Tuple[str, ...]          # extensions livrees
    minutes: Tuple[int, int]          # duree estimee (min, max)
    quantite: Optional[Tuple[str, str, str]] = None
    # (nom de l'argument, question posee, valeur par defaut)
    fabriquer: Optional[Callable[..., Dict[str, Any]]] = None
    vendable: bool = True             # False pour les outils d'analyse
    file: bool = True                 # peut entrer dans la file de production
    mots_cles: Tuple[str, ...] = ()   # aide l'explorateur de niches a choisir
    options: Dict[str, Any] = field(default_factory=dict)

    @property
    def duree(self) -> str:
        return "{} a {} min".format(*self.minutes)

    @property
    def nom_quantite(self) -> str:
        return self.quantite[0] if self.quantite else ""

    def defaut_quantite(self) -> int:
        if not self.quantite:
            return 0
        try:
            return int(self.quantite[2])
        except ValueError:
            return 0

    def executer(self, contexte: Any, options: Optional[Dict[str, Any]] = None):
        """Lance la fabrication en traduisant la quantite vers son argument."""
        if self.fabriquer is None:
            raise RuntimeError("type « {} » sans chaine de fabrication".format(self.cle))
        options = dict(options or {})
        arguments: Dict[str, Any] = {}
        if self.quantite:
            nom_argument = self.quantite[0]
            valeur = options.get("nombre") or options.get(nom_argument)
            if valeur:
                try:
                    arguments[nom_argument] = int(valeur)
                except (TypeError, ValueError):
                    pass
        for nom, valeur in self.options.items():
            if options.get(nom) is not None:
                arguments[nom] = options[nom]
            elif valeur is not None:
                arguments[nom] = valeur
        return self.fabriquer(contexte, **arguments)


def _chaines() -> Dict[str, Callable]:
    """Import tardif : le catalogue est lu par des modules que les chaines importent."""
    from . import (boite_outils, ebook, formation, idees, impression, modeles,
                   pack_prompts, social)

    return {
        "ebook": ebook.produire,
        "prompts": pack_prompts.produire,
        "formation": formation.produire,
        "outils": boite_outils.produire,
        "modeles": modeles.produire,
        "impression": impression.produire,
        "social": social.produire,
        "idees": idees.produire,
    }


TYPES: List[TypeProduit] = [
    TypeProduit(
        cle="ebook", nom="Ebook complet",
        resume="Un guide structure, du plan a la couverture",
        detail="PDF + EPUB + HTML + Markdown + couverture",
        formats=("pdf", "epub", "html", "md", "txt"),
        minutes=(10, 25),
        mots_cles=("guide", "methode", "livre", "manuel", "apprendre"),
    ),
    TypeProduit(
        cle="prompts", nom="Pack de prompts",
        resume="Une bibliotheque de prompts classee par intention",
        detail="PDF + CSV importable dans Notion + JSON",
        formats=("pdf", "csv", "json", "html", "md"),
        minutes=(5, 12),
        quantite=("nombre", "Combien de prompts", "50"),
        mots_cles=("prompt", "ia", "chatgpt", "automatisation", "productivite"),
    ),
    TypeProduit(
        cle="formation", nom="Mini-formation",
        resume="Des modules avec livrables et cahier d'exercices",
        detail="Manuel PDF + cahier d'exercices + sequence e-mail",
        formats=("pdf", "html", "md"),
        minutes=(12, 25),
        quantite=("modules", "Combien de modules", "6"),
        mots_cles=("formation", "cours", "apprendre", "module", "atelier"),
    ),
    TypeProduit(
        cle="outils", nom="Boite a outils",
        resume="Checklists, modeles et tableaux de suivi",
        detail="PDF imprimable + tableaux CSV + HTML",
        formats=("pdf", "csv", "html", "md"),
        minutes=(6, 14),
        quantite=("nombre", "Combien d'outils", "10"),
        mots_cles=("checklist", "modele", "outil", "procedure", "methode"),
    ),
    TypeProduit(
        cle="modeles", nom="Modeles Notion / tableur",
        resume="Des bases liees, prets a importer",
        detail="CSV par base + guide d'installation + PDF",
        formats=("csv", "pdf", "html", "md"),
        minutes=(5, 12),
        quantite=("nombre", "Combien de bases", "4"),
        mots_cles=("notion", "tableur", "modele", "systeme", "organisation",
                   "suivi", "tableau"),
    ),
    TypeProduit(
        cle="impression", nom="Cahier imprimable",
        resume="Des fiches a remplir a la main",
        detail="PDF aux formats A4 et Lettre US",
        formats=("pdf", "html"),
        minutes=(5, 12),
        quantite=("pages", "Combien de fiches", "12"),
        mots_cles=("planner", "imprimable", "cahier", "agenda", "fiche",
                   "planning", "journal"),
    ),
    TypeProduit(
        cle="social", nom="Pack de publications",
        resume="Un calendrier editorial redige",
        detail="Calendrier CSV + posts rediges + visuels optionnels",
        formats=("csv", "pdf", "json", "html", "md"),
        minutes=(5, 15),
        quantite=("nombre", "Combien de publications", "30"),
        options={"reseau": "linkedin"},
        mots_cles=("reseaux", "linkedin", "instagram", "contenu", "post",
                   "calendrier editorial"),
    ),
    TypeProduit(
        cle="idees", nom="Etude de niche",
        resume="Des pistes chiffrees, appuyees sur des mesures de marche",
        detail="Idees evaluees : prix, difficulte, concurrence",
        formats=("csv", "json", "html", "md"),
        minutes=(2, 4),
        quantite=("nombre", "Combien d'idees", "12"),
        options={"avec_marche": None},
        vendable=False, file=False,
    ),
]

# Les mots-cles sont compares a du texte normalise sans accent : un mot-cle
# accentue ne correspondrait jamais a rien. Mieux vaut le refuser bruyamment
# a l'import que le laisser silencieusement inoperant.
for _type in TYPES:
    for _mot in _type.mots_cles:
        assert all(ord(c) < 128 for c in _mot), (
            "mot-cle non ASCII dans « {} » : {!r}".format(_type.cle, _mot))

PAR_CLE: Dict[str, TypeProduit] = {t.cle: t for t in TYPES}
_cablees = False


def _cabler() -> None:
    global _cablees
    if _cablees:
        return
    chaines = _chaines()
    for type_produit in TYPES:
        type_produit.fabriquer = chaines.get(type_produit.cle)
    _cablees = True


def obtenir(cle: str) -> Optional[TypeProduit]:
    _cabler()
    return PAR_CLE.get(cle)


def tous(fabricables: bool = False, vendables: bool = False,
         en_file: bool = False) -> List[TypeProduit]:
    """Les types, filtres selon l'usage."""
    _cabler()
    selection = list(TYPES)
    if fabricables:
        selection = [t for t in selection if t.fabriquer is not None]
    if vendables:
        selection = [t for t in selection if t.vendable]
    if en_file:
        selection = [t for t in selection if t.file]
    return selection


def cles(**filtres: bool) -> List[str]:
    return [t.cle for t in tous(**filtres)]


def executer(cle: str, contexte: Any,
             options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    type_produit = obtenir(cle)
    if type_produit is None:
        raise ValueError("type de produit inconnu : {}".format(cle))
    return type_produit.executer(contexte, options)


def normaliser(cle: str, defaut: str = "ebook") -> str:
    """Ramene une cle proposee par un modele vers un type reellement fabricable."""
    propre = (cle or "").lower().strip()
    if propre in PAR_CLE:
        return propre
    # Tolerance sur les synonymes courants : un modele ecrit « e-book »,
    # « planner » ou « template » plutot que nos cles internes.
    synonymes = {
        "e-book": "ebook", "livre": "ebook", "guide": "ebook", "manuel": "ebook",
        "cours": "formation", "course": "formation", "masterclass": "formation",
        "template": "modeles", "templates": "modeles", "notion": "modeles",
        "tableur": "modeles", "spreadsheet": "modeles",
        "planner": "impression", "printable": "impression",
        "imprimable": "impression", "cahier": "impression",
        "checklist": "outils", "boite-a-outils": "outils", "toolkit": "outils",
        "prompt": "prompts", "prompt-pack": "prompts",
        "reseaux": "social", "contenu": "social", "social-media": "social",
    }
    if propre in synonymes:
        return synonymes[propre]
    for type_produit in TYPES:
        if any(mot in propre for mot in type_produit.mots_cles):
            return type_produit.cle
    return defaut


def resume_pour_ia() -> str:
    """Description du catalogue a injecter dans une invite."""
    lignes = []
    for type_produit in tous(vendables=True):
        lignes.append("- {} : {} ({})".format(
            type_produit.cle, type_produit.resume, type_produit.detail))
    return "\n".join(lignes)
