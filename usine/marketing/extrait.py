"""L'edition courte offerte : le livre qui sert a capter une adresse.

Un produit numerique se vend deux fois mieux quand on peut le faire essayer.
La pratique du marche est stable : une version courte, gratuite, qu'on echange
contre une adresse e-mail, et la version complete payante. L'extrait n'est
donc pas un cadeau — c'est la premiere marche d'un tunnel.

Deux decisions portent tout ce module.

**Aucun appel au modele.** L'extrait est DECOUPE dans le livre deja produit,
pas reecrit. C'est gratuit, instantane, reproductible, et surtout fidele : un
extrait regenere ne serait pas le debut du livre qu'on vend, ce qui est
exactement la promesse qu'un extrait fait.

**Il vit dans « marketing/ ».** Ce dossier ne part pas dans l'archive de
l'acheteur — un acheteur n'a que faire d'une version amputee de ce qu'il vient
de payer. L'extrait s'envoie a un prospect, depuis l'outil d'e-mailing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..render import libelles

# Part du livre offerte. Un quart est la coutume du marche : assez pour juger
# de la voix et de la methode, trop peu pour se passer d'acheter.
PART_OFFERTE = 0.25

# En dessous, un extrait n'a pas de sens : offrir deux chapitres sur trois
# revient a donner le livre, et offrir un chapitre d'un livre qui n'en a que
# deux aussi.
CHAPITRES_MINIMUM = 4

TITRE = re.compile(r"^# +(.+?)\s*$", re.MULTILINE)


def decouper(markdown: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Rend (bloc de titre, [(titre de chapitre, corps)]).

    Le markdown livre commence par « # Titre », le sous-titre en italique et
    l'auteur, puis un « # » par chapitre. On coupe donc sur les titres de
    niveau 1, le premier morceau etant l'en-tete.
    """
    positions = [(m.start(), m.end(), m.group(1)) for m in TITRE.finditer(markdown)]
    if not positions:
        return markdown.strip(), []
    entete = markdown[: positions[0][0]].strip()
    chapitres: List[Tuple[str, str]] = []
    for index, (_, fin, titre) in enumerate(positions):
        debut_suivant = (positions[index + 1][0] if index + 1 < len(positions)
                         else len(markdown))
        chapitres.append((titre, markdown[fin:debut_suivant].strip()))
    # Le premier « # » est le titre de l'ouvrage, pas un chapitre : son corps
    # est le sous-titre et la ligne d'auteur.
    if chapitres:
        entete = "{}\n\n{}".format(chapitres[0][0], chapitres[0][1]).strip()
        chapitres = chapitres[1:]
    return entete, chapitres


def nombre_offert(total: int, demande: int = 0) -> int:
    """Combien de chapitres entrent dans l'extrait.

    Jamais tous : un extrait complet n'est plus un extrait. Et au moins un,
    sinon il n'y a rien a lire.
    """
    if demande > 0:
        return max(1, min(demande, total - 1))
    return max(1, min(total - 1, round(total * PART_OFFERTE)))


def _page_de_suite(titre: str, restants: List[str], site: str,
                   contact: str, langue: str = "fr") -> str:
    """La derniere page : ce qui reste, et ou l'obtenir.

    C'est la seule page ecrite ici plutot que decoupee, et la seule qui
    compte commercialement — un extrait sans appel a l'action est un cadeau.
    """
    t = libelles.textes(langue)
    lignes = [
        # « le debut de Le systeme... » : les guillemets evitent l'article
        # double, que tout titre commencant par un determinant produirait.
        t["extrait_lu"].format(titre=titre),
        "",
        libelles.accorder(t["extrait_reste"].format(nombre=len(restants)),
                          langue),
        "",
    ]
    lignes += ["- {}".format(chapitre) for chapitre in restants]
    lignes += ["", "---", ""]
    if site:
        lignes.append(t["extrait_site"].format(site=site))
    if contact:
        lignes.append(t["extrait_question"].format(contact=contact))
    if not site and not contact:
        lignes.append(t["extrait_sans_site"])
    return "\n".join(lignes)


def produire(ctx: Any, dossier_produit: Path, titre: str,
             type_produit: str = "ebook", chapitres_offerts: int = 0,
             sous_titre: str = "") -> Optional[Dict[str, Any]]:
    """Ecrit l'edition courte dans « marketing/extrait ». None si sans objet.

    « ctx » sert d'auteur, de marque et de langue ; il n'est jamais utilise
    pour appeler un modele.
    """
    from ..core import reglages
    from ..pipelines.base import Contexte, code_langue, slug
    from ..render import livraison

    source = _markdown_du_produit(dossier_produit, type_produit)
    if source is None:
        return None
    entete, chapitres = decouper(source.read_text(encoding="utf-8"))
    if len(chapitres) < CHAPITRES_MINIMUM:
        return None

    offerts = nombre_offert(len(chapitres), chapitres_offerts)
    restants = [titre_chapitre for titre_chapitre, _ in chapitres[offerts:]]
    profil = reglages.charger()

    langue = code_langue(getattr(ctx, "langue", "") or
                         str(profil.get("langue") or "francais"))
    t = libelles.textes(langue)
    blocs = livraison.blocs_depuis_sections(chapitres[:offerts])
    blocs.append(livraison.bloc_markdown(
        t["extrait_suite"], _page_de_suite(titre, restants,
                                           str(profil.get("site") or ""),
                                           str(profil.get("contact") or ""),
                                           langue)))

    cible = dossier_produit / "marketing" / "extrait"
    cible.mkdir(parents=True, exist_ok=True)
    # Un contexte a part : la livraison ecrit dans « ctx.dossier », et
    # l'extrait ne doit rien poser a cote du produit vendu. Hors ligne, la
    # couverture est composee localement — gratuite, et sans reseau.
    contexte = Contexte(
        sujet=getattr(ctx, "sujet", "") or titre,
        auteur=getattr(ctx, "auteur", "") or str(profil.get("auteur") or ""),
        marque=getattr(ctx, "marque", "") or str(profil.get("marque") or ""),
        langue=getattr(ctx, "langue", "") or str(profil.get("langue") or "francais"),
        hors_ligne=True,
        journal=lambda message: None,
    )
    contexte.dossier = cible

    produit = livraison.Produit(
        type="extrait",
        titre=t["extrait_titre"].format(titre=titre),
        sous_titre=sous_titre or t["extrait_sous_titre"].format(nombre=offerts),
        promesse=t["extrait_promesse"].format(titre=titre),
        blocs=blocs,
        formats=("pdf", "epub"),
        police_corps="Times-Roman",
        style_couverture="book cover, {}".format(titre),
        langue=contexte.langue_iso,
        libelle_sections=t["unite_chapitres"],
        nom_fichier=t["fichier_extrait"].format(nom=slug(titre, 38)),
    )
    fichiers = livraison.livrer(contexte, produit)
    return {
        "dossier": str(cible),
        "chapitres_offerts": offerts,
        "chapitres_restants": len(restants),
        "fichiers": [f.name for f in fichiers],
    }


def _markdown_du_produit(dossier: Path, type_produit: str) -> Optional[Path]:
    """Le fichier markdown du produit, quel que soit son nom historique."""
    from ..render.livraison import _nom_markdown

    attendu = dossier / "{}.md".format(_nom_markdown(type_produit))
    if attendu.exists():
        return attendu
    autres = sorted(dossier.glob("*.md"))
    return autres[0] if autres else None
