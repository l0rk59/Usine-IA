"""Generation d'images : couverture, visuels reseaux sociaux.

Source par defaut : l'atelier local (usine/render/couverture.py), qui compose
la couverture en Python pur — degrade, geometrie, titre compose dans une
fonte dessinee pour l'occasion. Aucun reseau, aucune cle, aucun filigrane.

POURQUOI CE N'EST PAS POLLINATIONS QUI EST PAR DEFAUT, alors que le service
est gratuit et sans cle : au palier anonyme, il appose un filigrane
« pollinations.ai » en bas de chaque image. Le parametre « nologo » que la
documentation mentionne n'a aucun effet sans jeton — verifie, image a
l'appui. Une couverture filigranee ne se vend pas : la place de marche la
refuse ou l'acheteur la prend pour une contrefacon.

L'usine a donc longtemps produit, par defaut, des couvertures inutilisables
tout en documentant, dans ce meme fichier, qu'elles l'etaient. L'illustration
par IA reste disponible — reglage « couverture=ia » — mais elle exige un
jeton, justement parce que sans jeton elle ne sert a rien.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

from . import config
from ..render import couverture
from .http import HttpErreur, get_bytes, insister

def image_pollinations(
    invite: str,
    largeur: int = 1024,
    hauteur: int = 1024,
    modele: str = "sana",
    graine: Optional[int] = None,
    timeout: int = 180,
) -> bytes:
    """Genere une image via Pollinations (sans cle API). Leve HttpErreur si echec."""
    params = {
        "width": str(largeur),
        "height": str(hauteur),
        "model": modele,
        # Conserve parce qu'il devient effectif avec un jeton ; sans jeton il
        # est ignore et le filigrane reste.
        "nologo": "true",
        "referrer": "usine-ia",
    }
    if graine is None:
        graine = abs(hash(invite)) % 1_000_000
    params["seed"] = str(graine)
    url = "https://image.pollinations.ai/prompt/{}?{}".format(
        urllib.parse.quote(invite[:900], safe=""), urllib.parse.urlencode(params)
    )
    entetes = {}
    jeton = config.env("POLLINATIONS_TOKEN")
    if jeton:
        entetes["Authorization"] = "Bearer {}".format(jeton)
    brut = get_bytes(url, entetes, timeout=timeout)
    if len(brut) < 1024:
        raise HttpErreur(502, "image trop petite, generation probablement refusee")
    return brut


def extension_image(brut: bytes) -> str:
    if brut[:3] == b"\xff\xd8\xff":
        return "jpg"
    if brut[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if brut[:4] == b"RIFF" and brut[8:12] == b"WEBP":
        return "webp"
    return "bin"


def filigrane_probable() -> bool:
    """Vrai si les images generees porteront un filigrane.

    Sert a prevenir avant de livrer : une couverture filigranee est
    inutilisable sur une fiche de vente.
    """
    return not bool(config.env("POLLINATIONS_TOKEN"))


LARGEUR_COUVERTURE = 1200
HAUTEUR_COUVERTURE = 1800


def illustration_demandee() -> bool:
    """Vrai si l'utilisateur a explicitement demande une couverture par IA."""
    from . import reglages
    return str(reglages.lire("couverture", "atelier")).lower() == "ia"


# Le service d'images repond-il, MAINTENANT ? Une panne se constate une fois.
#
# Mesure du 15/09/2026, chemin reel du tableau de bord, aucun fournisseur
# d'images joignable : un conte prenait 83 secondes, dont 77,5 en images —
# quinze appels, chacun rejouant trois tentatives avec attente. Les quatorze
# derniers rapprenaient, a cinq secondes piece, ce que le premier avait deja
# etabli.
#
# Les reessais restent justes pour un hoquet : c'est de les payer QUINZE FOIS
# qui ne l'est pas. Apres un « insister » epuise — trois tentatives sur cinq
# secondes, c'est deja la mesure — les appels suivants tentent leur chance une
# seule fois. Aucun delai, aucun seuil a inventer : le premier succes efface
# le constat et l'insistance reprend, donc un service qui revient au milieu
# d'un album est repris au vol.
_SERVICE_MUET = False


def _demander_une_image(faire):
    """Un appel au service d'images, insistant ou non selon ce qu'on sait."""
    global _SERVICE_MUET
    try:
        brut = faire() if _SERVICE_MUET else insister(faire)
    except Exception:
        _SERVICE_MUET = True
        raise
    _SERVICE_MUET = False
    return brut


def generer_couverture(
    dossier: Path,
    titre: str,
    sous_titre: str = "",
    auteur: str = "",
    style: str = "",
    en_ligne: bool = True,
    nom: str = "couverture",
    palette: Optional[int] = None,
    graine: Optional[int] = None,
    marque: str = "",
    modele: Optional[int] = None,
) -> Path:
    """Ecrit une couverture dans `dossier`. Renvoie le chemin du PNG.

    Le PNG est le fichier qui compte : Gumroad, Etsy et KDP n'acceptent pas
    le SVG. Le SVG est ecrit a cote, meme geometrie, pour qui veut retoucher.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    if en_ligne and illustration_demandee() and not filigrane_probable():
        invite = (
            "book cover artwork, {style}, abstract editorial design, bold geometric shapes, "
            "premium minimal poster, theme: {titre}. No text, no letters, no words."
        ).format(style=style or "modern flat vector", titre=titre)
        try:
            # Une coupure d'une seconde ne doit pas decider de la couverture
            # d'un livre. Le repli local existe et il est bon, mais il n'a pas
            # a servir parce que le forfait a hoquete au mauvais moment.
            brut = _demander_une_image(
                lambda: image_pollinations(invite, 1024, 1365, graine=graine))
            chemin = dossier / "{}.{}".format(nom, extension_image(brut))
            chemin.write_bytes(brut)
            return chemin
        except Exception:
            pass  # repli sur l'atelier : un produit n'attend pas le reseau
    dessin = couverture.composer(
        titre, sous_titre, auteur, marque,
        largeur=LARGEUR_COUVERTURE, hauteur=HAUTEUR_COUVERTURE,
        palette=palette, modele=modele)
    chemin = dossier / "{}.png".format(nom)
    chemin.write_bytes(couverture.png(dessin))
    (dossier / "{}.svg".format(nom)).write_text(couverture.svg(dessin),
                                                encoding="utf-8")
    return chemin


def couverture_pleine_page(
    titre: str, sous_titre: str = "", auteur: str = "", marque: str = "",
    palette: Optional[int] = None, modele: Optional[int] = None,
    largeur: int = 760, hauteur: int = 1075,
) -> Tuple[bytes, int, int]:
    """Pixels bruts de la meme couverture, au format d'une page PDF.

    Recomposee plutot que redimensionnee : la mise en page se reajuste au
    rapport de la page, et le rendu reste net. La palette et le modele
    derivent du titre, donc le PDF et le PNG montrent le meme dessin.
    """
    dessin = couverture.composer(titre, sous_titre, auteur, marque,
                                 largeur=largeur, hauteur=hauteur,
                                 palette=palette, modele=modele)
    toile = couverture.toile(dessin)
    return (toile.rvb(), toile.largeur, toile.hauteur)


def generer_visuel(
    dossier: Path,
    nom: str,
    invite: str,
    largeur: int = 1080,
    hauteur: int = 1080,
    en_ligne: bool = True,
) -> Optional[Path]:
    """Visuel carre pour les reseaux sociaux. Renvoie None si indisponible."""
    if not en_ligne:
        return None
    try:
        # Ici il n'y a AUCUN repli : une illustration d'album qui ne vient pas
        # ne vient pas du tout, et le livre sort avec une note « a dessiner »
        # a sa place. Mesure du 15/09/2026 : un seul essai, zero seconde
        # d'attente — une coupure d'une seconde coutait l'image pour de bon,
        # et le journal annoncait « 0 image(s) sur 14 » sans dire pourquoi.
        brut = _demander_une_image(
            lambda: image_pollinations(invite, largeur, hauteur))
    except Exception:
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "{}.{}".format(nom, extension_image(brut))
    chemin.write_bytes(brut)
    return chemin
