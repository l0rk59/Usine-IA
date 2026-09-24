"""Ce que le modele ajoute au texte, et qui n'a rien a faire dans un produit.

Deux familles, et la seconde est la plus couteuse.

**Les restes de fabrication.** Un modele de raisonnement emet son brouillon
entre « <think> » et « </think> » ; un modele local mal servi laisse passer ses
jetons de dialogue ; un octet mal decode en chemin transforme « é » en deux
caracteres illisibles. Rien de tout cela n'echoue : le texte arrive, le
controle qualite le note, le PDF le met en page, et l'acheteur lit le brouillon
du modele.

**Les refus deguises en reponse.** Mesure du 13/09/2026 sur pollinations :

    HTTP 200, finish_reason « stop », usage renseigne, et pour tout contenu :
    « The API key used for this request has reached its budget. Please raise
    the key budget, then try again. »

Tous les signaux disent « reponse valide ». Le routeur l'a donc acceptee, mise
en cache, et ecrite dans un chapitre. C'est le pire cas possible : un quota
epuise qui ne ressemble pas a un quota epuise. L'usine ne bascule pas sur un
autre fournisseur — puisque rien n'a echoue — et le produit part avec un
message de facturation anglais au milieu d'un livre francais.

D'ou la regle de ce module : **ne pas croire le code HTTP, lire le texte.**
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

# --------------------------------------------------------------------------
# Restes de fabrication
# --------------------------------------------------------------------------

# Les balises dans lesquelles un modele de raisonnement enferme son brouillon.
# La liste vient des familles reellement servies par les fournisseurs gratuits
# (DeepSeek R1, Qwen3, les « thinking » de NVIDIA NIM) — relevee le 13/09/2026.
_RAISONNEMENT = ("think", "thinking", "reason", "reasoning", "scratchpad",
                 "analysis", "reflection")

_BLOCS = [re.compile(r"<\s*{0}\s*>.*?<\s*/\s*{0}\s*>".format(nom),
                     re.DOTALL | re.IGNORECASE) for nom in _RAISONNEMENT]

# Une ouverture sans fermeture : le modele a ete coupe au plafond de jetons AU
# MILIEU de son brouillon. Tout ce qui suit est du brouillon — il n'y a pas de
# reponse. On coupe donc jusqu'a la fin ; le texte devient vide, l'appelant
# voit une reponse vide et redemande. C'est le bon comportement : mieux vaut un
# appel de plus qu'un chapitre fait de reflexions a voix haute.
_OUVERTURE = re.compile(r"<\s*(?:{})\s*>".format("|".join(_RAISONNEMENT)),
                        re.IGNORECASE)

# Jetons de dialogue des modeles ouverts. Ils sortent quand le serveur
# n'applique pas le bon gabarit de discussion — cas courant sur llama.cpp et
# sur les passerelles qui reexposent un modele brut.
_JETONS = re.compile(
    r"<\|(?:im_start|im_end|endoftext|eot_id|start_header_id|end_header_id"
    r"|begin_of_text|end_of_text|assistant|user|system)\|>"
    r"|\[/?INST\]|\[/?SYS\]",
    re.IGNORECASE)

# « <s> » et « </s> » se traitent a part : « <s> » est aussi une balise HTML
# legitime (texte barre). On ne les retire qu'en debut ou fin de texte, la ou
# ils ne peuvent etre que des jetons de modele.
_JETONS_BORDS = re.compile(r"^\s*<\s*s\s*>|<\s*/\s*s\s*>\s*$", re.IGNORECASE)

# Caracteres invisibles qui voyagent avec la sortie d'un modele. Ils ne se
# voient pas a l'ecran et cassent la recherche, la cesure et l'EPUB. U+FFFD est
# le caractere de remplacement : il ne signale jamais autre chose qu'un octet
# perdu en route.
_INVISIBLES = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0xFFFC, 0xFFFD], None)

# Signatures d'un texte UTF-8 relu comme du latin-1 : un caractere accentue
# y devient deux caracteres, dont le premier est A-tilde, A-circonflexe ou
# a-circonflexe. Ecrites en points de code et jamais en litteral : un fichier
# source qui CONTIENT du mojibake est exactement ce qu'un editeur, un outil de
# formatage ou une relecture distraite « corrige » tout seul — et le garde-fou
# s'eteindrait sans que rien ne le dise.
_MOJIBAKE = re.compile(
    "[\u00c3][\u0080-\u00bf]"          # e, a, c accentues
    "|\u00e2\u0080[\u0080-\u00bf\u2019]"  # guillemets et tirets typographiques
    "|[\u00c2][\u00a0-\u00bf]")        # espace insecable, chevrons



def _sans_raisonnement(texte: str) -> str:
    for bloc in _BLOCS:
        texte = bloc.sub("", texte)
    ouverture = _OUVERTURE.search(texte)
    if ouverture:
        texte = texte[:ouverture.start()]
    return texte


def reparer_encodage(texte: str) -> str:
    """Repare un texte UTF-8 relu comme du latin-1 — et seulement s'il l'est.

    La conversion est brutale : reencoder en latin-1 puis redecoder en UTF-8.
    Deux conditions la retiennent, et ce sont les deux seules qui protegent
    reellement un texte sain :

    1. **Une signature doit etre presente.** Sans elle, on ne touche a rien.
       « é«» » se reencode en trois octets qui forment un ideogramme chinois
       parfaitement valide : sans cette premiere condition, un texte francais
       ordinaire pouvait etre transforme en silence.
    2. **Le redecodage doit reussir.** C'est le garde-fou principal, et il est
       redoutablement efficace : un accent francais reel donne un octet isole
       (é = 0xE9) qui n'est jamais un debut de sequence UTF-8 valide. Un texte
       a moitie abime — une signature quelque part, de vrais accents ailleurs —
       echoue donc au decodage et sort intact.

    Une troisieme condition a existe : n'accepter la reparation que si elle
    fait BAISSER le nombre de signatures. Elle a ete retiree apres mesure —
    aucune entree, sur une recherche exhaustive de toutes les combinaisons de
    deux a quatre caracteres du vocabulaire mojibake, n'atteint ce cas. Une
    condition qu'aucune entree ne peut atteindre ne protege de rien ; elle
    donne seulement l'impression d'une precaution supplementaire, et c'est
    exactement ce qui fait relacher la vraie.
    """
    if not _MOJIBAKE.search(texte):
        return texte
    try:
        return texte.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texte


def assainir(texte: str) -> str:
    """Retire du texte du modele ce qui appartient a sa fabrication.

    Applique a CHAQUE reponse, au niveau du routeur : une correction posee
    dans un seul pipeline laisse les neuf autres avec le defaut, et personne
    ne s'en apercoit avant de lire le produit fini.
    """
    if not texte:
        return texte
    texte = _sans_raisonnement(texte)
    texte = _JETONS.sub("", texte)
    texte = _JETONS_BORDS.sub("", texte)
    texte = reparer_encodage(texte)
    texte = texte.translate(_INVISIBLES)
    # Les caracteres de controle restants, sauf ceux qui font le texte.
    texte = "".join(c for c in texte
                    if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    # Trois lignes vides ou plus : reste d'un bloc retire au milieu.
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    # Espaces en fin de ligne : invisibles, et ils font des paragraphes
    # fantomes dans certains lecteurs EPUB.
    texte = re.sub(r"[ \t]+\n", "\n", texte)
    return texte.strip()


# --------------------------------------------------------------------------
# Refus deguises en reponse
# --------------------------------------------------------------------------

# Tournures qui n'appartiennent qu'a un service, jamais a un chapitre. Elles
# sont en anglais parce que ces messages le sont toujours, meme quand l'invite
# etait en francais — c'est d'ailleurs le signal le plus net.
_PHRASES_SERVICE = (
    "api key", "rate limit", "rate-limit", "quota", "credit balance",
    "insufficient credits", "insufficient_quota", "reached its budget",
    "raise the key budget", "billing", "payment required", "upgrade your plan",
    "try again later", "service unavailable", "internal server error",
    "bad gateway", "upstream error", "provider returned", "no endpoints found",
    "model not found", "model_not_found", "invalid api key", "unauthorized",
    "please contact support", "temporarily unavailable", "overloaded",
)

# Adresses de consoles de facturation. Aucun chapitre ne renvoie l'acheteur
# vers la page de credits d'un fournisseur d'IA.
_CONSOLES = ("console.groq.com", "openrouter.ai/credits", "enter.pollinations.ai",
             "platform.openai.com/account", "console.mistral.ai",
             "cloud.cerebras.ai", "build.nvidia.com", "aistudio.google.com",
             "/edit-key", "/billing")

# Mots-outils francais. Leur ABSENCE dans un texte suffisamment long est un
# signal — mais seulement quand on attendait du francais : pour un livre
# anglais, elle est la regle, et le routeur ne la compte plus.
_FRANCAIS = re.compile(
    r"\b(?:le|la|les|des|une|un|du|de|et|que|qui|pour|dans|avec|vous|nous|"
    r"est|sont|plus|cette|ce|son|sa|ses|par|sur|aux|ou|mais|donc)\b",
    re.IGNORECASE)

# Au-dela, un texte est trop long pour etre un message de service : ces
# messages sont courts. Le plus long recolte faisait 346 caracteres.
LONGUEUR_MAX_MESSAGE = 700


def refus_deguise(texte: str, attend_francais: bool = True) -> str:
    """Rend la raison si le texte est un message de service, ou "" sinon.

    Le detecteur demande DEUX signaux independants, jamais un seul. Un manuel
    sur les API parlera legitimement de « rate limit » ; un chapitre peut citer
    une phrase anglaise. Ce qui n'arrive pas, c'est qu'un chapitre soit a la
    fois court, ecrit sans un mot de francais, et truffe de vocabulaire de
    facturation.

    Le detecteur rate donc des refus plutot que d'accuser un vrai chapitre :
    se tromper ici couterait un chapitre valide jete et un quota redepense.
    """
    if not texte:
        return ""
    net = texte.strip()
    if len(net) > LONGUEUR_MAX_MESSAGE:
        return ""
    bas = net.lower()

    phrases = [m for m in _PHRASES_SERVICE if m in bas]
    console = [u for u in _CONSOLES if u in bas]
    # Un texte de plus de 120 caracteres sans un seul mot-outil francais n'est
    # pas une reponse a une invite francaise.
    sans_francais = attend_francais and len(net) > 120 and not _FRANCAIS.search(net)

    signaux: List[str] = []
    if phrases:
        signaux.append("vocabulaire de service (« {} »)".format(phrases[0]))
    if console:
        signaux.append("renvoi vers « {} »".format(console[0]))
    if sans_francais:
        signaux.append("aucun mot francais")

    if len(signaux) < 2:
        return ""
    return "message du service pris pour une reponse : " + ", ".join(signaux)


# Ce qui, dans un refus deguise, ressemble a un quota plutot qu'a une panne.
_QUOTA = ("quota", "budget", "credit", "rate limit", "rate-limit", "billing",
          "payment required", "upgrade your plan", "insufficient")


def ressemble_a_un_quota(texte: str) -> bool:
    """Distingue « plus de credit » de « le service a hoquete ».

    Les deux demandent de changer de fournisseur, mais pas pour la meme duree :
    revenir dans dix secondes chez un service qui n'a plus de credit rebrule un
    appel pour rien.
    """
    bas = (texte or "").lower()
    return any(m in bas for m in _QUOTA)
