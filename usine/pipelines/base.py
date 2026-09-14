"""Socle commun a toutes les chaines de production."""

from __future__ import annotations

import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core import (apprentissage, budget, config, controle, empreinte,
                    llm, store)
from . import carnet

TONS = {
    "expert": "expert, precis, appuye sur des faits et des chiffres",
    "amical": "chaleureux, direct, tutoiement, comme un ami qui explique",
    "pro": "professionnel, sobre, vouvoiement, orientation resultats",
    "punchy": "percutant, phrases courtes, rythme soutenu, verbes d'action",
    "pedagogue": "pedagogue, progressif, beaucoup d'exemples concrets",
}

TAILLES = {
    "mini": (6, 700),
    "court": (8, 950),
    "standard": (12, 1100),
    "long": (18, 1300),
}

# Bornes du sur-mesure. En dessous de deux sections, il n'y a pas de plan ;
# au-dela de soixante, aucun quota gratuit ne tient la distance et le livre
# se repete. Un mot par section sous trois cents ne fait pas une section,
# au-dela de quatre mille le modele coupe au milieu d'une phrase.
CHAPITRES_MIN, CHAPITRES_MAX = 2, 60
MOTS_MIN, MOTS_MAX = 300, 4000

# Jetons par mot en francais. Mesure haute plutot que moyenne : un texte qui
# tient dans son plafond vaut mieux qu'un texte coupe au milieu d'une phrase,
# et les jetons non consommes ne coutent rien.
# Une seule conversion « francais -> jetons » pour tout le depot, et elle vit
# dans le module qui compte les jetons. En tenir une seconde ici, c'est ce qui
# a permis aux deux de diverger d'un facteur 1,63 sans que personne ne le voie.
from ..core.llm import JETONS_PAR_MOT  # noqa: F401  (re-export historique)
# Plafond absolu d'une reponse. Le routeur le ramene ensuite a ce que le
# fournisseur choisi sait reellement emettre (Provider.max_sortie).
JETONS_MAX = 8192


def jetons_pour(mots: int, marge: int = 400) -> int:
    """Plafond de jetons a demander pour produire « mots » mots.

    Ce calcul etait recopie en « min(4096, mots * 2.6) » a chaque appel. Le
    resultat : au-dela de mille cinq cents mots par section, la demande etait
    silencieusement ramenee a 4096 — soit moins de la moitie de ce qu'on
    annoncait au modele — et rien ne lisait « finish_reason » pour s'en
    apercevoir. Les quatre paliers y echappaient ; le sur-mesure, non.
    """
    return max(512, min(JETONS_MAX, int(mots * JETONS_PAR_MOT) + marge))


def resoudre_ton(valeur: str) -> str:
    """Description du ton, qu'il vienne des raccourcis ou de l'utilisateur.

    Les cinq tons predefinis sont des RACCOURCIS, pas une liste fermee :
    « -t expert » vaut sa description, « -t "comme un vieux menuisier qui
    explique a son apprenti" » passe telle quelle. Une liste de choix fermee
    obligeait a choisir entre cinq voix pour tous les produits d'un
    catalogue, ce qui est exactement ce qui les fait se ressembler.
    """
    propre = (valeur or "").strip()
    if not propre:
        return TONS["pro"]
    return TONS.get(propre.lower(), propre)


def resoudre_taille(taille: str, chapitres: int = 0,
                    mots: int = 0) -> Tuple[int, int]:
    """(sections, mots par section), du raccourci au sur-mesure.

    « -T long » reste valable. « -T 15 » demande quinze sections. Et
    « --chapitres 15 --mots 1400 » decide des deux.
    """
    defaut = TAILLES.get((taille or "").strip().lower())
    if defaut is None and (taille or "").strip().isdigit():
        # « -T 15 » : un nombre de sections, avec le volume du palier le
        # plus proche pour ne pas avoir a le preciser aussi.
        demande = int(taille)
        proche = min(TAILLES.values(), key=lambda v: abs(v[0] - demande))
        defaut = (demande, proche[1])
    if defaut is None:
        defaut = TAILLES["standard"]
    nombre = int(chapitres) if chapitres else defaut[0]
    volume = int(mots) if mots else defaut[1]
    return (max(CHAPITRES_MIN, min(CHAPITRES_MAX, nombre)),
            max(MOTS_MIN, min(MOTS_MAX, volume)))


def slug(texte: str, longueur: int = 60) -> str:
    """Transforme un titre en nom de dossier sur : sans accent ni espace."""
    normalise = unicodedata.normalize("NFKD", texte)
    ascii_seul = normalise.encode("ascii", "ignore").decode("ascii")
    propre = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_seul).strip("-").lower()
    return (propre[:longueur].strip("-")) or "produit"


def identifiant(type_produit: str, titre: str) -> str:
    """Identifiant unique d'un produit, qui sert aussi de nom de dossier.

    L'horodatage seul ne suffit pas : sa precision est la seconde, et l'usine
    continue peut livrer deux produits dans la meme seconde. Les quatre
    caracteres aleatoires evitent que le second ecrase les fichiers du premier.
    """
    return "{}-{}-{}-{}".format(
        type_produit, slug(titre, 32), time.strftime("%Y%m%d-%H%M%S"),
        secrets.token_hex(2))


# Le reglage « langue » est saisi en clair — « francais », « anglais » — mais
# un EPUB, un PDF et un lecteur d'ecran attendent un code BCP 47. La chaine
# ebook faisait la conversion pour elle seule, sur deux langues ; les huit
# autres types livraient « fr » quoi qu'on demande. Un lecteur d'ecran
# prononcait donc un texte anglais avec la phonetique francaise.
CODES_LANGUE = {
    "francais": "fr", "french": "fr", "fr": "fr",
    "anglais": "en", "english": "en", "en": "en",
    "espagnol": "es", "spanish": "es", "es": "es",
    "allemand": "de", "german": "de", "de": "de",
    "italien": "it", "italian": "it", "it": "it",
    "portugais": "pt", "portuguese": "pt", "pt": "pt",
    "neerlandais": "nl", "dutch": "nl", "nl": "nl",
}


def code_langue(nom: str, defaut: str = "fr") -> str:
    """Code BCP 47 a partir d'un nom de langue ecrit en clair."""
    propre = unicodedata.normalize("NFKD", (nom or "").strip().lower())
    propre = propre.encode("ascii", "ignore").decode("ascii")
    if propre in CODES_LANGUE:
        return CODES_LANGUE[propre]
    for cle, code in CODES_LANGUE.items():
        if propre.startswith(cle[:4]) and len(cle) > 3:
            return code
    return defaut


# Les deux facons de n'avoir plus rien a demander a un modele, et pourquoi
# elles se traitent ensemble.
#
# « BudgetEpuise » est le plafond que l'utilisateur s'est fixe ; « PlusDeFournisseur »
# est le monde exterieur qui se tait — quota du jour atteint partout, reseau
# coupe, cles refusees. Les pipelines n'attrapaient que la premiere. La seconde
# remontait donc jusqu'a la CLI et **tuait la fabrication entiere** : le plan,
# l'avant-propos et les chapitres deja ecrits partaient avec le processus. Or
# la reponse est la meme dans les deux cas : cesser de demander, garder ce qui
# existe, et le dire.
PLUS_RIEN_A_DEMANDER: Tuple[type, ...] = (budget.BudgetEpuise, llm.PlusDeFournisseur)



@dataclass
class Contexte:
    """Tout ce dont une chaine de production a besoin."""

    sujet: str
    audience: str = "un public francophone motive"
    langue: str = "francais"
    ton: str = "pro"
    taille: str = "standard"
    auteur: str = "Usine-IA"
    prix: str = ""
    marque: str = ""
    dedicace: str = ""            # page liminaire de l'EPUB, omise si vide
    hors_ligne: bool = False
    sans_image: bool = False
    qualite: str = "standard"
    relectures: int = -1          # -1 : deduit du niveau de qualite
    chapitres: int = 0            # 0 : deduit de la taille
    mots_section: int = 0         # 0 : deduit de la taille
    produit_id: str = ""
    demarre_le: float = field(default_factory=time.time)
    dossier: Path = field(default_factory=Path)

    @property
    def langue_iso(self) -> str:
        """Code BCP 47 de la langue de redaction, pour les metadonnees."""
        return code_langue(self.langue)
    journal: Callable[[str], None] = print
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def description_ton(self) -> str:
        return resoudre_ton(self.ton)

    @property
    def nb_passes(self) -> int:
        """Nombre de relectures editoriales appliquees a chaque section."""
        if self.relectures >= 0:
            return self.relectures
        from ..core import reglages

        return reglages.relectures_pour(self.qualite)

    @property
    def nb_chapitres(self) -> int:
        return resoudre_taille(self.taille, self.chapitres, self.mots_section)[0]

    @property
    def mots_par_chapitre(self) -> int:
        return resoudre_taille(self.taille, self.chapitres, self.mots_section)[1]

    def systeme(self, role_metier: str) -> str:
        return (
            "Tu es {role}. Tu ecris en {langue}, d'un ton {ton}. "
            "Tu t'adresses a : {audience}. "
            "Tes textes sont concrets, structures, sans remplissage ni formule creuse. "
            "Tu bannis les tournures d'IA generique (« dans un monde ou », « il est "
            "important de noter », « en conclusion »). Tu donnes des exemples chiffres, "
            "des scripts reutilisables et des etapes numerotees. "
            "Tu ne promets jamais de resultats garantis et tu n'inventes ni statistique "
            "precise ni citation attribuee a une personne reelle."
        ).format(
            role=role_metier,
            langue=self.langue,
            ton=self.description_ton,
            audience=self.audience,
        )

    def etape(self, nom: str, statut: str = "ok", detail: str = "",
              essentiel: bool = True) -> None:
        """Note une etape. Un echec ESSENTIEL rend le produit invendable.

        « essentiel » vaut True par defaut, et c'est le sens qu'il faut :
        une chaine qui oublie d'y penser fait du bruit plutot que du silence.
        Le silence est le defaut qu'on corrige ici — sept chaines sur neuf
        avalaient une etape perdue, ecrivaient une ligne de journal, et
        livraient un produit marque « pret ».

        Une illustration ratee, un quiz manquant, une sequence e-mail
        indisponible ne rendent pas un produit invendable : ces etapes-la se
        declarent « essentiel=False ». Elles restent notees et dites — mais
        un garde-fou qui crie a tort finit ignore, et « usine reprendre »
        n'aurait bientot plus signale que du bruit.

        Trois statuts, et la difference compte :

        | | |
        |---|---|
        | `ok` | l'etape a tourne, rien a signaler |
        | `echec` | l'etape N'A PAS PU tourner : il manque son resultat |
        | `anomalie` | l'etape a tourne et a TROUVE quelque chose |

        Les deux derniers etaient confondus sous « echec », et le controle de
        continuite d'un roman se retrouvait dans les sections a refaire — ou
        « usine reprendre » serait alle reecrire une scene qui existe, sans
        jamais corriger l'anomalie, qu'aucune reecriture ne corrige.
        """
        if statut == "echec" and not essentiel:
            statut = "echec-optionnel"
        if self.produit_id:
            store.journal_etape(self.produit_id, nom, statut, detail)


def preparer(ctx: Contexte, type_produit: str, titre: str) -> Path:
    """Cree le dossier du produit et l'enregistre au catalogue."""
    config.ensure_dirs()
    ctx.produit_id = ctx.produit_id or identifiant(type_produit, titre)
    dossier = config.PRODUITS_DIR / ctx.produit_id
    dossier.mkdir(parents=True, exist_ok=True)
    ctx.dossier = dossier
    store.creer_produit(
        ctx.produit_id,
        type_produit,
        titre,
        sujet=ctx.sujet,
        audience=ctx.audience,
        langue=ctx.langue,
        dossier=str(dossier),
        meta={"ton": ctx.ton, "taille": ctx.taille, "auteur": ctx.auteur},
    )
    # La commande d'origine, pour que « usine reprendre » rejoue exactement
    # celle-la. Ecrite ici parce que c'est le premier instant ou le dossier
    # existe — et une fabrication peut mourir des le chapitre suivant.
    carnet.noter_commande(dossier)
    return dossier


_ENTETE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)


def _matiere(fichiers: List[Path]) -> Tuple[str, List[str]]:
    """Le texte redige du produit et la liste de ses sections.

    On relit ce qui a ete ECRIT plutot que de se faire passer le plan : c'est
    le fichier livre qui compte, et toutes les chaines n'ont pas la meme
    structure interne. Le markdown quand il existe, le JSON de travail sinon.
    """
    for extension in (".md", ".txt"):
        for chemin in fichiers:
            if chemin.suffix == extension and chemin.exists():
                texte = chemin.read_text(encoding="utf-8", errors="replace")
                return texte, _ENTETE.findall(texte)
    for chemin in fichiers:
        if chemin.suffix == ".json" and chemin.exists():
            try:
                charge = json.loads(chemin.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            morceaux, titres = [], []
            _aplatir(charge, morceaux, titres)
            return "\n".join(morceaux), titres
    return "", []


def _aplatir(noeud: Any, morceaux: List[str], titres: List[str]) -> None:
    """Descend dans un JSON en retenant le texte et ce qui fait office de titre."""
    if isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            if isinstance(valeur, str) and cle in ("titre", "nom", "intitule"):
                titres.append(valeur)
            _aplatir(valeur, morceaux, titres)
    elif isinstance(noeud, list):
        for element in noeud:
            _aplatir(element, morceaux, titres)
    elif isinstance(noeud, str) and len(noeud) > 12:
        morceaux.append(noeud)


def empreinte_depuis_dossier(produit_id: str, type_produit: str, titre: str,
                             sujet: str, dossier: Path) -> bool:
    """Calcule l'empreinte d'un produit deja fabrique, depuis ses fichiers.

    Les empreintes sont posees a la fabrication : un catalogue constitue
    avant cette version n'en a aucune, et « usine doublons » n'a donc rien a
    comparer chez celui qui en aurait le plus besoin. On relit ici ce qui est
    sur le disque, exactement comme la chaine l'aurait fait en livrant.
    """
    if not dossier.exists():
        return False
    fichiers = sorted(f for f in dossier.iterdir() if f.is_file())
    texte, titres = _matiere(fichiers)
    if not texte:
        return False
    store.enregistrer_empreinte(
        produit_id, type_produit, titre, sujet,
        empreinte.encoder(empreinte.signature(texte)),
        empreinte.encoder(empreinte.plan(titres)),
        len(empreinte.mots_normalises(texte)))
    return True


def _verifier_doublon(ctx: Contexte, type_produit: str, fichiers: List[Path],
                      titre: str) -> Optional[Dict[str, Any]]:
    """Compare le produit fini a ceux deja fabriques, puis l'enregistre.

    La verification a lieu APRES fabrication, et c'est un compromis assume :
    comparer avant supposerait de deviner ce que le modele va ecrire. Le
    produit n'est donc pas bloque — il est signale, et la trace reste dans
    « usine doublons ». Le quota est depense ; ce qu'on evite, c'est la mise
    en vente.
    """
    texte, titres = _matiere(fichiers)
    if not texte:
        return None
    connus = []
    for ligne in store.lister_empreintes(type_produit, sauf=ctx.produit_id):
        connus.append({
            "produit_id": ligne["produit_id"], "titre": ligne["titre"],
            "sujet": ligne["sujet"],
            "signature": empreinte.decoder(ligne["signature"]),
            "plan": empreinte.decoder(ligne["plan"]),
        })
    ma_signature = empreinte.signature(texte)
    mon_plan = empreinte.plan(titres)
    voisins = empreinte.comparer(texte, titres, connus,
                                 mienne=ma_signature, mon_plan=mon_plan)
    store.enregistrer_empreinte(
        ctx.produit_id, type_produit, titre, ctx.sujet,
        empreinte.encoder(ma_signature), empreinte.encoder(mon_plan),
        len(empreinte.mots_normalises(texte)))
    proches = [v for v in voisins if v.doublon]
    if not proches:
        return None
    ctx.journal("  [!] Deja fabrique de tres proche :")
    for voisin in proches[:3]:
        ctx.journal("      " + voisin.resume())
    return {"produits": [v.produit_id for v in proches[:5]],
            "motif": proches[0].motif,
            "texte": round(proches[0].texte, 3),
            "plan": round(proches[0].plan, 3)}


def _mesurer_le_livre(ctx: Contexte, genre: str, fichiers: List[Path],
                      deja: Dict[str, Any]) -> Dict[str, Any]:
    """Volume et note du produit livre, quand la chaine ne les donne pas.

    Le decompte vaut pour TOUS les types : c'est un decompte, pas un verdict.
    La note, non — le controle deterministe mesure de la prose, et le
    catalogue dit lesquels en sont. Applique a une liste de prompts ou a du
    code, il rend un chiffre qui n'a pas de sens, et un chiffre sans sens est
    pire que pas de chiffre parce qu'on le croit : mesure faite, trente-et-un
    posts sociaux de deux lignes obtenaient 9,98/10.
    """
    from .catalogue import obtenir

    mesure: Dict[str, Any] = {}
    texte, titres = _matiere(fichiers)
    if not texte.strip():
        # Un cahier a remplir ne livre que des PDF : il n'y a pas de texte
        # suivi a compter. Zero est alors un fait, pas un oubli.
        return mesure
    if not deja.get("mots"):
        mesure["mots"] = len(texte.split())
    if not deja.get("sections") and not deja.get("chapitres"):
        mesure["sections"] = len(titres)
    if deja.get("note") is not None:
        return mesure

    fiche = obtenir(genre)
    if fiche is not None and not fiche.prose:
        # Dit, plutot que laisse vide : une case vide se lit comme un oubli,
        # et quelqu'un finirait par « reparer » en notant quand meme.
        mesure["note_non_mesuree"] = (
            "le controle deterministe mesure de la prose ; ce type n'en est "
            "pas")
        return mesure

    sections = _decouper(texte)
    if not sections:
        return mesure

    # Le controle mesure de la prose PAR SECTION, et il lui en faut assez
    # pour mordre. Mesure du 14/09/2026, faite en coupant un meme texte de
    # plus en plus fin :
    #
    #   mots/section :  60   80  100  120  140  200  300  400
    #   note         : 10.0 10.0 8.69 8.56 7.56 7.19 6.93  6.5
    #
    # En dessous de cent mots, la note vaut 10 quoi que dise le texte : elle
    # mesure le decoupage, pas l'ecriture. Une boite a outils de vingt-cinq
    # mots par fiche obtenait ainsi 9,91/10, et ce chiffre serait parti se
    # comparer dans « usine bilan » a un ebook note 4,33 sur des chapitres de
    # deux cents mots. Un chiffre sans sens est pire que pas de chiffre,
    # parce qu'on le croit.
    tailles = sorted(len(corps.split()) for _titre, corps in sections)
    median = tailles[len(tailles) // 2]
    mesure["mots_par_section"] = median
    if median < 100:
        mesure["note_non_mesuree"] = (
            "sections de {} mots en mediane : sous cent mots, le controle "
            "rend 10/10 quel que soit le texte".format(median))
        return mesure

    rapport = controle.controler_ensemble(sections)
    if rapport["note_moyenne"] is None:
        return mesure
    mesure["note"] = rapport["note_moyenne"]
    mesure["defauts"] = sorted({
        anomalie["genre"]
        for section in rapport["sections"] for anomalie in section["anomalies"]})
    chemin = ctx.dossier / "rapport-qualite.json"
    try:
        chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        fichiers.append(chemin)
    except OSError as exc:
        # Un disque plein ne doit pas emporter un produit deja ecrit : la
        # note reste sur la fiche, seul le detail se perd.
        ctx.journal("  rapport qualite non ecrit : {}".format(exc))
    ctx.journal("  qualite mesuree : {}/10 sur {} section(s)".format(
        rapport["note_moyenne"], len(sections)))
    return mesure


_NIVEAU = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def _ce_que_le_pdf_ne_sait_pas_ecrire(ctx: Contexte, fichiers: List[Path],
                                      titre: str = "") -> Dict[str, Any]:
    """Les lettres que le PDF livre a remplacees par « ? ».

    Le moteur PDF est ecrit a la main et n'embarque aucune police : il tient
    le francais entier et rien au-dela de l'alphabet latin. Un livre intitule
    « la cuisine japonaise <ideogrammes> » sortait donc avec « ?? » sur sa
    couverture, livre marque « pret » — alors que l'EPUB du meme produit
    etait parfait, et que rien ne disait lequel des deux fichiers croire.

    Ce n'est pas une anomalie du texte : le texte va bien. C'est une limite
    d'un des formats livres, et c'est a ce titre qu'on la dit.
    """
    from ..render.pdf import caracteres_absents

    if not any(chemin.suffix == ".pdf" for chemin in fichiers):
        return {}
    # Le titre et le sujet AUTANT que le corps : ils vont sur la couverture et
    # sur la page de titre, qui sont justement les pages qu'on regarde. Une
    # premiere version ne lisait que le corps du livre — et le cas qui a
    # ouvert le sujet, « la cuisine japonaise <ideogrammes> », passait
    # inapercu, parce que les ideogrammes etaient dans le titre.
    texte, _titres = _matiere(fichiers)
    perdus = caracteres_absents(
        "\n".join([texte, titre or "", ctx.sujet or "", ctx.auteur or ""]))
    if not perdus:
        return {}
    ctx.journal(
        "[!] Le PDF ne sait pas ecrire {} caractere(s) : {}. Ils y "
        "apparaissent en « ? » — l'EPUB et le HTML, eux, les gardent."
        .format(len(perdus), " ".join(perdus[:12])))
    return {"pdf_caracteres_absents": perdus[:40]}


def _decouper(texte: str) -> List[Tuple[str, str]]:
    """Le texte livre, coupe a ses entetes de PREMIER niveau utile.

    Couper a n'importe quel entete coupait trop fin : un module de formation
    porte « ## Objectif » et « ## Notions » a l'interieur, et decouper la
    donnait des sections de trente-quatre mots pour un module qui en fait cent
    quarante. Or la note du controle depend fortement de la longueur des
    sections — sous cent mots elle vaut 10/10 quoi qu'il arrive. Un mauvais
    decoupage ne rendait donc pas une note imprecise : il rendait une note
    inventee.

    On prend le niveau de titre le PLUS HAUT present sous le titre du
    document, c'est-a-dire l'unite que la chaine a elle-meme choisie.
    """
    entetes = list(_NIVEAU.finditer(texte))
    if not entetes:
        return [("", texte)] if texte.strip() else []
    profondeurs = {len(m.group(1)) for m in entetes}
    # Le « # » unique est le titre du document, pas une section : on ne
    # coupe dessus que s'il n'y a rien d'autre.
    utiles = sorted(d for d in profondeurs if d > 1) or sorted(profondeurs)
    niveau = utiles[0]
    coupes = [m for m in entetes if len(m.group(1)) == niveau]
    morceaux: List[Tuple[str, str]] = []
    for rang, marque in enumerate(coupes):
        fin = (coupes[rang + 1].start() if rang + 1 < len(coupes)
               else len(texte))
        corps = texte[marque.end():fin]
        if corps.strip():
            morceaux.append((marque.group(2), corps))
    return morceaux


def terminer(ctx: Contexte, fichiers: List[Path], meta: Optional[Dict[str, Any]] = None,
             type_produit: str = "") -> None:
    infos = dict(meta or {})
    # Une reponse coupee au plafond de jetons traverse toute la fabrication
    # sans rien casser : le texte est la, il s'arrete juste avant sa fin. Le
    # routeur le detecte et refuse de la mettre en cache ; c'est ici qu'on le
    # DIT, sur la fiche du produit livre, pour les dix chaines a la fois.
    tronquees = (ctx.meta or {}).get("tronquees") or []
    if tronquees:
        infos["tronquees"] = len(tronquees)
        infos["tronquees_detail"] = tronquees[:8]
        ctx.journal(
            "[!] {} reponse(s) coupees au plafond de jetons : le texte "
            "correspondant s'arrete avant sa fin. Reduisez --mots, ou "
            "relancez : le passage coupe n'a pas ete mis en cache."
            .format(len(tronquees)))
    produit_avant = store.lire_produit(ctx.produit_id) or {}
    genre = type_produit or produit_avant.get("type", "inconnu")
    doublon = _verifier_doublon(ctx, genre, fichiers,
                                produit_avant.get("titre", "") or ctx.sujet)
    if doublon:
        infos["doublon"] = doublon
    # « pret » veut dire vendable. Un produit dont des sections ont ete
    # remplacees par leur plan ne l'est pas : il etait pourtant marque pret
    # comme les autres, et se presentait au catalogue, au tableau de bord et
    # a « usine livrer » sans rien signaler. On le laisse « en_cours », ce qui
    # le fait apparaitre « inacheve » et le rend reprenable.
    # Les etapes perdues en cours de route, relues du journal. Chaque chaine
    # les note deja par « ctx.etape(..., "echec") » ; personne ne les relisait,
    # donc « terminer » ne voyait que le « manquants » que deux chaines sur
    # neuf prenaient la peine de remplir. Le mecanisme etait juste, c'est son
    # alimentation qui manquait.
    #
    # Le DERNIER statut de chaque etape gagne : une etape qui a echoue puis
    # reussi a la reprise n'est pas un trou. Prendre n'importe quel echec
    # aurait marque inacheve tout produit ayant connu une seule erreur
    # rattrapee — un garde-fou qui crie a tort finit ignore.
    dernier: Dict[str, str] = {}
    for pas in store.etapes_produit(ctx.produit_id):
        dernier[str(pas.get("nom") or "")] = str(pas.get("statut") or "")
    perdues = sorted(n for n, s in dernier.items() if s == "echec")
    facultatives = sorted(n for n, s in dernier.items() if s == "echec-optionnel")
    # Un controle qui a TROUVE quelque chose : le produit est complet, et
    # quelque chose cloche dedans. Ni un trou ni un silence — sans cette
    # ligne, une anomalie de continuite ne vivait que dans le defilement du
    # terminal, c'est-a-dire nulle part sur un telephone.
    anomalies = sorted(n for n, s in dernier.items() if s == "anomalie")
    if anomalies:
        infos["anomalies"] = anomalies
        ctx.journal("[!] {} controle(s) ont trouve quelque chose : {}. Le "
                    "produit est complet — c'est son contenu qu'il faut "
                    "regarder.".format(len(anomalies), ", ".join(anomalies[:6])))
    if facultatives:
        infos["incomplets"] = facultatives
        ctx.journal(
            "[!] {} etape(s) facultative(s) perdue(s) : {}. Le produit reste "
            "vendable — relancez la commande pour les obtenir."
            .format(len(facultatives), ", ".join(facultatives[:6])))

    manquants = [str(m) for m in (infos.get("manquants") or [])]
    manquants += [n for n in perdues if n not in manquants]
    if manquants:
        infos["manquants"] = manquants
        ctx.journal(
            "[!] {} section(s) non ecrites : {}. Le produit reste inacheve — "
            "« usine reprendre » ne refera que celles-la."
            .format(len(manquants), ", ".join(manquants[:6])))
    # Le volume et la note, pour les chaines qui ne les rendent pas elles-memes.
    #
    # Sept types sur neuf sortaient sans aucune mesure : ni note, ni rapport,
    # ni meme un nombre de mots. « usine bilan » annoncait « 0 mots produits »
    # apres quatre vraies fabrications, et « usine conseils » calculait des
    # conseils « tires de vos donnees » sur rien. Plus loin encore :
    # « graine_de_depart » classe par chiffre d'affaires PUIS par note, donc
    # ces sept types ne pouvaient jamais servir de point de depart a la
    # prospection.
    #
    # On relit le texte LIVRE plutot que de se faire passer un plan : toutes
    # les chaines n'ont pas la meme structure interne, et c'est le fichier qui
    # part chez l'acheteur qui compte.
    infos.update(_mesurer_le_livre(ctx, genre, fichiers, infos))
    infos.update(_ce_que_le_pdf_ne_sait_pas_ecrire(
        ctx, fichiers, produit_avant.get("titre", "")))

    store.maj_produit(
        ctx.produit_id,
        statut="en_cours" if manquants else "pret",
        meta=dict(infos, fichiers=[f.name for f in fichiers]),
    )
    # Trace mesuree : c'est elle qui alimente « usine bilan » et « usine conseils ».
    appels = store.compteur_intervalle(ctx.demarre_le)
    fournisseurs = store.fournisseurs_intervalle(ctx.demarre_le)
    apprentissage.enregistrer(
        produit_id=ctx.produit_id,
        type_produit=genre,
        sujet=ctx.sujet,
        audience=ctx.audience,
        ton=ctx.ton,
        taille=ctx.taille,
        qualite=ctx.qualite,
        note=infos.get("note"),
        note_avant=infos.get("note_avant"),
        mots=int(infos.get("mots") or 0),
        sections=int(infos.get("sections") or infos.get("chapitres") or 0),
        duree=round(time.time() - ctx.demarre_le, 1),
        appels=appels,
        fournisseurs=infos.get("fournisseurs") or fournisseurs,
        defauts=infos.get("defauts") or [],
    )


def nettoyer_titre(texte: str) -> str:
    """Retire guillemets, numerotation et balisage laisses par le modele."""
    texte = texte.strip().strip('"').strip("'").strip()
    texte = re.sub(r"^#+\s*", "", texte)
    texte = re.sub(r"^(chapitre|module|partie|section|etape|jour)\s*\d+\s*[:.\-–]\s*",
                   "", texte, flags=re.IGNORECASE)
    texte = re.sub(r"^\d+\s*[:.)\-–]\s*", "", texte)
    texte = texte.replace("**", "").strip()
    return texte or "Sans titre"


def elaguer_markdown(texte: str) -> str:
    """Supprime le bavardage et les cloture de code laisses autour d'un markdown."""
    indesirables = (
        "voici", "bien sur", "bien sûr", "certainement", "j'espere", "j'espère",
        "n'hesitez pas", "n'hésitez pas", "voila", "voilà", "parfait", "avec plaisir voici",
    )
    texte = texte.strip()
    # Le preambule peut preceder la cloture markdown : deux passes suffisent.
    for _ in range(2):
        lignes = texte.split("\n")
        while lignes and lignes[0].strip().lower().startswith(indesirables):
            lignes.pop(0)
        while lignes and not lignes[0].strip():
            lignes.pop(0)
        texte = "\n".join(lignes).strip()
        texte = re.sub(r"^```(?:markdown|md|text)?[ \t]*\n", "", texte)
        texte = re.sub(r"\n?```[ \t]*$", "", texte).strip()
    return texte
