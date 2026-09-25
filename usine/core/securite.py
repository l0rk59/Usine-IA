"""Securite : secrets, acces au tableau de bord, garde-fous de contenu.

Trois risques traites :
  1. une cle API recopiee dans un journal, un produit ou une capture d'ecran ;
  2. un tableau de bord ouvert au reseau local sans authentification ;
  3. un produit genere sur un sujet qui exposerait son vendeur.
"""

from __future__ import annotations

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

    Applique aux deux endroits ou un message quitte le processus pour de
    bon : le tableau de bord, qui l'envoie sur le reseau local, et le journal
    sur disque (« core/trace.py »), qui l'y laisse des semaines.

    La console n'y passe pas, et c'est un constat plutot qu'un oubli : rien
    n'y fait transiter de secret. Le corps d'une reponse HTTP en erreur —
    le seul endroit ou un service renverrait une cle — est porte par
    « HttpErreur.corps », et un seul endroit l'affiche : l'audit des quotas
    (« diagnostic »), qui le fait passer par ici. Cette docstring
    annoncait trois destinations pour une seule ; une garantie de securite
    qui surestime sa couverture est pire qu'une absence de garantie, parce
    qu'on cesse de chercher.
    """
    if not texte:
        return texte
    resultat = texte
    for motif in _MOTIFS_SECRETS:
        resultat = motif.sub("[CLE MASQUEE]", resultat)
    return resultat


def contient_un_secret(texte: str) -> bool:
    """Un secret figure-t-il dans ce texte ?

    Distinct d'« expurger » : masquer repare la fuite, reconnaitre permet de
    la DIRE. Une cle masquee en silence laisse l'utilisateur avec une cle
    exposee quelque part et aucune raison de la renouveler. Le journal sur
    disque s'en sert pour alerter, une fois.
    """
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
    # La securite informatique est le domaine ou la frontiere entre expliquer
    # et outiller compte le plus — et c'est celui qui manquait. Un « guide de
    # test d'intrusion » passait sans un mot.
    ("securite", r"(test d.intrusion|pentest|penetration testing|piratage|"
                 r"hacking|hacker un|exploit|faille de securite|vulnerabilite|"
                 r"craquer un mot de passe|forcer un mot de passe|keylogger|"
                 r"ransomware|malware|phishing|hameconnage|deni de service|"
                 r"contourner une protection|anonymat total)",
     "Securite informatique : expliquer une attaque est legal, en outiller "
     "une ne l'est pas. Ce qui est autorise sur VOTRE materiel ne l'est pas "
     "ailleurs, et les places de marche retirent ce qu'elles jugent offensif. "
     "Restez sur la defense, la sensibilisation et l'audit de son propre parc."),
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
