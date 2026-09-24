"""Mise en carton : archive ZIP livrable, notice et licence."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence

from ..render import libelles

# Les textes de la licence, du LISEZ-MOI et de la mention d'assistance IA
# vivent dans « render/libelles.py », en francais et en anglais : ils partent
# chez l'acheteur, et doivent donc etre dans la langue du produit.
#
# La mention d'assistance IA est ajoutee selon le reglage « signature_ia ».
# Beaucoup de places de marche et le reglement europeen sur l'IA attendent
# cette transparence ; on la met donc par defaut, tout en la rendant
# desactivable.
#
# Le contact ne s'ecrit que quand le vendeur en a donne un. « votre adresse
# e-mail » etait le repli, et il partait tel quel chez l'acheteur : « Ecrivez
# a votre adresse e-mail ». Un rappel destine au VENDEUR, imprime dans le
# document VENDU. Pire que ridicule : la section accessibilite promettait une
# version adaptee a une adresse qui n'existe pas, alors que cette promesse est
# precisement ce que la reglementation europeenne attend d'etre tenue. Sans
# adresse, la promesse n'est plus faite.


def ecrire_notice(dossier: Path, titre: str, promesse: str, auteur: str,
                  contact: str = "", langue: str = "fr") -> Path:
    """Ecrit le LISEZ-MOI que l'acheteur trouve dans le dossier.

    Sans adresse de contact, les deux passages qui en demandent une sont
    simplement absents : l'usine n'ecrit pas une promesse qu'elle ne peut pas
    tenir. « usine ebook --contact vous@exemple.fr », ou le reglage
    « contact », les fait revenir.
    """
    fichiers = sorted(
        f for f in dossier.iterdir()
        if f.is_file() and f.name not in FICHIERS_AJOUTES
        and not f.name.endswith(".json")
    )
    bonus = sorted(d.name for d in dossier.iterdir()
                   if d.is_dir() and d.name.startswith("bonus-"))
    t = libelles.textes(langue)
    liste = "\n".join("- `{}`".format(f.name) for f in fichiers) or t["dossier_vide"]
    if bonus:
        liste += "\n" + "\n".join(
            t["contenu_bonus"].format(nom=nom) for nom in bonus
        )
    chemin = dossier / t["fichier_notice"]
    chemin.write_text(
        t["notice"].format(
            titre=titre, promesse=promesse or "", fichiers=liste,
            contact_accessibilite=(
                t["contact_accessibilite"].format(contact=contact) if contact else ""),
            contact_question=(
                t["contact_question"].format(contact=contact) if contact else ""),
            auteur=auteur, date=time.strftime(t["format_date"]),
        ),
        encoding="utf-8",
    )
    return chemin


def ecrire_licence(dossier: Path, titre: str, auteur: str,
                   langue: str = "fr") -> Path:
    from ..core import reglages

    t = libelles.textes(langue)
    transparence = t["transparence"] if reglages.lire("signature_ia", True) else ""
    chemin = dossier / t["fichier_licence"]
    chemin.write_text(
        t["licence"].format(titre=titre, auteur=auteur, annee=time.strftime("%Y"),
                            transparence=transparence),
        encoding="utf-8",
    )
    return chemin


# Fichiers de travail : utiles a vous, sans interet pour l'acheteur.
#
# Cette liste est un FILET, pas la regle. Elle etait la regle, et c'est
# exactement pourquoi elle a fui : mesure du 14/09/2026 sur les neuf chaines,
# toutes laissaient partir au moins un fichier interne — « carnet.json » chez
# les neuf, « rapport-qualite.json » chez l'ebook et le roman, plus
# « bible.json », « continuite.json », « systeme.json », « cahier.json » et
# « verification.json » selon la chaine.
#
# L'acheteur ouvrait l'archive et y trouvait la note interne de son propre
# produit — 3,79/10 dans la mesure —, la liste de ses defauts, le texte de
# chaque section et la ligne de commande exacte qui l'avait fabrique.
#
# Une liste de noms tenue a la main ne peut pas suivre : elle est ecrite une
# fois, et chaque fichier ajoute ensuite part chez le client. La regle est
# donc devenue « on livre ce que la chaine a DECLARE livrer » — elle le
# declare deja, dans « meta["fichiers"] ». Ce filet ne sert plus qu'aux
# appels qui n'ont pas cette liste sous la main.
FICHIERS_INTERNES = ["plan.json", "programme.json", "boite.json", "produit.json",
                     "idees.json", "carnet.json", "rapport-qualite.json",
                     "bible.json", "continuite.json", "systeme.json",
                     "cahier.json", "verification.json", "quiz.json"]

# Ce que l'empaquetage ECRIT lui-meme, dans toutes les langues tenues. Un
# acheteur anglophone qui ouvre l'archive cherche « README », pas
# « LISEZ-MOI » : le nom suit la langue du produit, comme le texte.
FICHIERS_AJOUTES = sorted({t[cle] for t in libelles.LIBELLES.values()
                           for cle in ("fichier_notice", "fichier_licence")})
# Dossiers qui ne doivent JAMAIS partir chez l'acheteur : ce sont vos supports
# de vente (page de vente, sequence de lancement, prix plancher negociable).
DOSSIERS_INTERNES = ["marketing"]


def empaqueter(
    dossier: Path,
    nom_archive: str,
    titre: str,
    auteur: str,
    promesse: str = "",
    contact: str = "",
    exclure: Optional[List[str]] = None,
    exclure_dossiers: Optional[List[str]] = None,
    livres: Optional[Sequence[str]] = None,
    langue: str = "fr",
) -> Path:
    """Assemble l'archive destinee a l'acheteur.

    « livres » est la liste que la chaine a declaree livrer. Quand elle est
    fournie, elle fait loi : rien d'autre n'entre dans l'archive. C'est le
    seul sens qui tient — l'inverse, « tout sauf une liste noire », oblige a
    penser a chaque nouveau fichier de travail au moment ou on l'ajoute, six
    mois plus tard, dans un autre fichier, et personne n'y pense.

    Le kit de vente reste dans le dossier de travail mais n'entre pas dans
    l'archive : livrer sa propre page de vente a son client serait une fuite.
    """
    exclure = exclure or list(FICHIERS_INTERNES)
    exclure_dossiers = (exclure_dossiers if exclure_dossiers is not None
                        else list(DOSSIERS_INTERNES))
    # Seuls partent la notice et la licence de CETTE langue. Un produit
    # empaquete une premiere fois dans une autre langue — ou avant que le nom
    # suive la langue — garde l'ancienne notice dans son dossier ; la laisser
    # partir livrerait deux modes d'emploi, dont un perime.
    ajoutes = {ecrire_notice(dossier, titre, promesse, auteur, contact,
                             langue).name,
               ecrire_licence(dossier, titre, auteur, langue).name}

    declares = set(livres or ())
    # DANS le dossier du produit, pas a cote. A cote, le nom ne venait que du
    # titre, dans un dossier commun a tous les produits : deux produits de
    # meme titre — la meme niche refabriquee, que le cache resert avec le
    # meme titre — ou deux titres non latins, tous deux « produit », ecrivaient
    # la meme archive, et le second ecrasait le premier. Mesure du 24/09/2026 :
    # deux memos, une seule archive, celle du second. Et le menu comme le
    # tableau de bord cherchaient l'archive DANS le dossier : le partage
    # depuis le telephone ne la trouvait jamais. L'archive ne s'inclut pas
    # elle-meme : les « .zip » sont ecartes plus bas.
    archive = dossier / "{}.zip".format(nom_archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for fichier in sorted(dossier.rglob("*")):
            if not fichier.is_file():
                continue
            relatif = fichier.relative_to(dossier)
            if relatif.suffix == ".zip":
                continue
            if any(partie in exclure_dossiers for partie in relatif.parts[:-1]):
                continue
            if relatif.name in FICHIERS_AJOUTES and relatif.name not in ajoutes:
                continue
            if declares:
                if relatif.name not in declares and relatif.name not in ajoutes:
                    continue
            elif relatif.name in exclure:
                continue
            z.write(fichier, str(Path(nom_archive) / relatif))
    return archive


