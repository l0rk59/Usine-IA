"""Mise en carton : archive ZIP livrable, notice et licence."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

LICENCE = """LICENCE D'UTILISATION — {titre}

(c) {annee} {auteur}. Tous droits reserves.

CE QUE VOUS POUVEZ FAIRE
- Utiliser ce produit pour votre usage personnel ou professionnel.
- Appliquer les methodes decrites a votre activite, sans limite.
- Adapter les modeles fournis a vos propres besoins.

CE QUE VOUS NE POUVEZ PAS FAIRE
- Revendre, redistribuer ou partager les fichiers, meme gratuitement.
- Publier le contenu, en tout ou partie, sous votre nom.
- Inclure ce produit dans une offre groupee sans autorisation ecrite.

AVERTISSEMENT
Ce produit est fourni a titre informatif. Il ne constitue ni un conseil
juridique, ni un conseil fiscal, ni un conseil medical, ni un conseil en
investissement. Aucun resultat n'est garanti : les resultats dependent de
votre situation, de votre marche et de votre execution. L'auteur ne peut
etre tenu responsable des decisions prises sur la base de ce document.
{transparence}"""

# Mention d'assistance IA, ajoutee selon le reglage « signature_ia ». Beaucoup
# de places de marche et le reglement europeen sur l'IA attendent cette
# transparence ; on la met donc par defaut, tout en la rendant desactivable.
TRANSPARENCE = """

TRANSPARENCE
Ce produit a ete elabore avec l'assistance d'outils d'intelligence
artificielle, puis structure et mis en forme par Usine-IA. Relisez et
adaptez le contenu a votre contexte avant toute diffusion commerciale.
"""

# Version d'une ligne de la mention ci-dessus, pour la page de copyright de
# l'EPUB : une page de droits est un bloc dense et court, pas un paragraphe.
MENTION_IA_COURTE = ("Ouvrage elabore avec l'assistance d'outils "
                     "d'intelligence artificielle.")

NOTICE = """# {titre}

{promesse}

Merci pour votre achat.

## Ce que contient ce dossier

{fichiers}

## Par ou commencer

1. Ouvrez le fichier PDF : c'est la version de reference, mise en page pour
   la lecture et l'impression.
2. Sur liseuse ou telephone, preferez le fichier EPUB s'il est present.
3. Le fichier `lire.html` s'ouvre dans n'importe quel navigateur, y compris
   hors connexion, et s'imprime proprement.
4. Les fichiers `.md`, `.csv` et `.json` sont la pour que vous puissiez
   reutiliser le contenu dans vos propres outils.

## Accessibilite

Le fichier EPUB est structure pour la lecture assistee : ordre de lecture
logique, titres hierarchises, table des matieres navigable, texte
redimensionnable sans perte d'information, contraste verifie a 4,5:1 au
minimum. Aucun contenu clignotant ni sonore. Les metadonnees d'accessibilite
sont incluses dans le fichier.

Si un format vous convient mal, ecrivez a {contact} : une version adaptee
vous sera envoyee.

## Une question ?

Ecrivez a {contact}.

---
{auteur} — {date}
"""


def ecrire_notice(dossier: Path, titre: str, promesse: str, auteur: str,
                  contact: str = "votre adresse e-mail") -> Path:
    fichiers = sorted(
        f for f in dossier.iterdir()
        if f.is_file() and f.name not in ("LISEZ-MOI.md", "LICENCE.txt")
        and not f.name.endswith(".json")
    )
    bonus = sorted(d.name for d in dossier.iterdir()
                   if d.is_dir() and d.name.startswith("bonus-"))
    liste = "\n".join("- `{}`".format(f.name) for f in fichiers) or "- (dossier vide)"
    if bonus:
        liste += "\n" + "\n".join(
            "- `{}/` — contenu bonus".format(nom) for nom in bonus
        )
    chemin = dossier / "LISEZ-MOI.md"
    chemin.write_text(
        NOTICE.format(
            titre=titre, promesse=promesse or "", fichiers=liste,
            contact=contact, auteur=auteur, date=time.strftime("%d/%m/%Y"),
        ),
        encoding="utf-8",
    )
    return chemin


def ecrire_licence(dossier: Path, titre: str, auteur: str) -> Path:
    from ..core import reglages

    # La mention d'assistance IA est activee par defaut (transparence attendue
    # par les places de marche), mais « signature_ia » permet de la retirer.
    transparence = TRANSPARENCE if reglages.lire("signature_ia", True) else ""
    chemin = dossier / "LICENCE.txt"
    chemin.write_text(
        LICENCE.format(titre=titre, auteur=auteur, annee=time.strftime("%Y"),
                       transparence=transparence),
        encoding="utf-8",
    )
    return chemin


# Fichiers de travail : utiles a vous, sans interet pour l'acheteur.
FICHIERS_INTERNES = ["plan.json", "programme.json", "boite.json", "produit.json",
                     "idees.json"]
# Dossiers qui ne doivent JAMAIS partir chez l'acheteur : ce sont vos supports
# de vente (page de vente, sequence de lancement, prix plancher negociable).
DOSSIERS_INTERNES = ["marketing"]


def empaqueter(
    dossier: Path,
    nom_archive: str,
    titre: str,
    auteur: str,
    promesse: str = "",
    contact: str = "votre adresse e-mail",
    exclure: Optional[List[str]] = None,
    exclure_dossiers: Optional[List[str]] = None,
) -> Path:
    """Assemble l'archive destinee a l'acheteur.

    Le kit de vente reste dans le dossier de travail mais n'entre pas dans
    l'archive : livrer sa propre page de vente a son client serait une fuite.
    """
    exclure = exclure or list(FICHIERS_INTERNES)
    exclure_dossiers = (exclure_dossiers if exclure_dossiers is not None
                        else list(DOSSIERS_INTERNES))
    ecrire_notice(dossier, titre, promesse, auteur, contact)
    ecrire_licence(dossier, titre, auteur)

    archive = dossier.parent / "{}.zip".format(nom_archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for fichier in sorted(dossier.rglob("*")):
            if not fichier.is_file():
                continue
            relatif = fichier.relative_to(dossier)
            if relatif.name in exclure or relatif.suffix == ".zip":
                continue
            if any(partie in exclure_dossiers for partie in relatif.parts[:-1]):
                continue
            z.write(fichier, str(Path(nom_archive) / relatif))
    return archive


def inventaire(dossier: Path) -> Dict[str, Any]:
    fichiers = [f for f in sorted(dossier.rglob("*")) if f.is_file()]
    return {
        "nombre": len(fichiers),
        "octets": sum(f.stat().st_size for f in fichiers),
        "fichiers": [
            {"nom": str(f.relative_to(dossier)), "octets": f.stat().st_size}
            for f in fichiers
        ],
    }
