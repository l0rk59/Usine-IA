"""Securite : secrets, acces au tableau de bord, garde-fous de contenu.

Trois risques traites :
  1. une cle API recopiee dans un journal, un produit ou une capture d'ecran ;
  2. un tableau de bord ouvert au reseau local sans authentification ;
  3. un produit genere sur un sujet qui exposerait son vendeur.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import List, Tuple

# --------------------------------------------------------------------------
# 1. Expurgation des secrets
# --------------------------------------------------------------------------

# Prefixes connus des principaux fournisseurs, plus une regle generique.
_MOTIFS_SECRETS = [
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),              # Groq
    re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"),         # OpenRouter
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),               # OpenAI et compatibles
    re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}"),           # Google
    re.compile(r"\bcsk-[A-Za-z0-9]{20,}"),              # Cerebras
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"),         # NVIDIA
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),        # GitHub
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}"),     # en-tete HTTP
]


def expurger(texte: str) -> str:
    """Remplace tout secret reconnaissable par un marqueur.

    Applique a chaque message de journal et a chaque message d'erreur avant
    qu'il n'atteigne la console, le fichier de log ou le tableau de bord.
    """
    if not texte:
        return texte
    resultat = texte
    for motif in _MOTIFS_SECRETS:
        resultat = motif.sub("[CLE MASQUEE]", resultat)
    return resultat


def contient_un_secret(texte: str) -> bool:
    return any(motif.search(texte or "") for motif in _MOTIFS_SECRETS)


# --------------------------------------------------------------------------
# 2. Acces au tableau de bord
# --------------------------------------------------------------------------


def nouveau_jeton() -> str:
    """Jeton d'acces au tableau de bord, sur 32 caracteres."""
    return secrets.token_urlsafe(24)


def jeton_valide(attendu: str, fourni: str) -> bool:
    """Comparaison a temps constant : pas de fuite par mesure de duree."""
    if not attendu:
        return True  # aucun jeton configure : acces local libre
    return hmac.compare_digest(attendu.encode("utf-8"), (fourni or "").encode("utf-8"))


def empreinte_courte(valeur: str) -> str:
    return hashlib.sha256(valeur.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# 3. Noms de fichiers
# --------------------------------------------------------------------------

_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVES = {
    "CON", "PRN", "AUX", "NUL",
    *("COM{}".format(i) for i in range(1, 10)),
    *("LPT{}".format(i) for i in range(1, 10)),
}


def nom_de_fichier_sur(propose: str, defaut: str = "fichier") -> str:
    """Nom de fichier utilisable sur Android, Windows et Linux.

    Neutralise la traversee de repertoire, les caracteres interdits et les
    noms reserves de Windows (un acheteur sur deux est sous Windows).
    """
    normalise = unicodedata.normalize("NFKD", propose or "")
    ascii_seul = normalise.encode("ascii", "ignore").decode("ascii")
    propre = _INTERDITS.sub("-", ascii_seul).replace("..", "-").strip(" .-")
    propre = re.sub(r"[-\s]+", "-", propre)[:120].strip("-")
    if not propre or propre.upper().split(".")[0] in _RESERVES:
        return defaut
    return propre


# --------------------------------------------------------------------------
# 4. Garde-fous de contenu
# --------------------------------------------------------------------------

# Domaines ou un produit genere par IA expose son vendeur a un risque reel :
# responsabilite professionnelle, reglementation, ou prejudice direct au lecteur.
# Les motifs sont ecrits SANS accent : le sujet est normalise avant comparaison,
# ce qui permet de reconnaitre « guerir » comme « guerir ».
DOMAINES_SENSIBLES: List[Tuple[str, str, str]] = [
    ("sante", r"(diagnostic|posologie|traitement medical|guerir|guerison|cancer|"
              r"maladie|medicament|ordonnance|therapie|psychiatr|depression|"
              r"anxiete|symptome)",
     "Conseil medical : exige un professionnel de sante. Un guide generique "
     "peut nuire au lecteur et engager votre responsabilite."),
    ("finance", r"(investir|investissement|trading|crypto|bourse|placement|"
                r"rendement garanti|defiscalisation|forex|action en bourse)",
     "Conseil en investissement : active en France un cadre reglementaire "
     "(AMF). Restez sur la pedagogie, jamais sur la recommandation."),
    ("juridique", r"(contrat type|clause juridique|litige|procedure judiciaire|"
                  r"divorce|licenciement|porter plainte|droit du travail)",
     "Conseil juridique : la redaction d'actes est reservee aux professionnels "
     "du droit."),
    ("nutrition", r"(regime alimentaire|perte de poids|maigrir|jeune intermittent|"
                  r"calories par jour|complement alimentaire)",
     "Nutrition prescriptive : encadree, et dangereuse sans suivi individuel."),
    ("mineurs", r"(enfant de moins de|mineur|adolescent en difficulte|scolarite "
                r"obligatoire)",
     "Contenu visant des mineurs : verifiez les obligations de protection et "
     "de moderation de votre plateforme."),
]


def _sans_accent(texte: str) -> str:
    normalise = unicodedata.normalize("NFKD", texte or "")
    return normalise.encode("ascii", "ignore").decode("ascii").lower()


def analyser_sujet(sujet: str) -> List[Tuple[str, str]]:
    """Signale les domaines sensibles detectes dans un sujet.

    Ne bloque rien : informe le vendeur pour qu'il decide en connaissance de
    cause et renforce la clause de non-responsabilite si necessaire.
    """
    detectes: List[Tuple[str, str]] = []
    normalise = _sans_accent(sujet)
    for nom, motif, avertissement in DOMAINES_SENSIBLES:
        if re.search(motif, normalise):
            detectes.append((nom, avertissement))
    return detectes


CLAUSE_RENFORCEE = (
    "AVERTISSEMENT IMPORTANT\n"
    "Ce document est un contenu pedagogique general. Il ne remplace en aucun "
    "cas l'avis d'un professionnel qualifie et ne constitue ni un diagnostic, "
    "ni une prescription, ni un conseil personnalise. Consultez un "
    "professionnel avant toute decision engageant votre sante, votre "
    "patrimoine ou votre situation juridique."
)
