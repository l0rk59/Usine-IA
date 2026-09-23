"""Usine continue : consomme la file de niches, sous budget, jusqu'a l'arret.

Trois contraintes ont dicte la conception, toutes liees a Android :

  1. le systeme tue les processus en arriere-plan sans preavis — donc tout
     l'etat vit en base, et une entree laissee « en cours » est reprise au
     demarrage suivant ;
  2. les quotas gratuits sont limites — donc le budget est verifie avant
     chaque produit et avant chaque appel ;
  3. l'utilisateur veut pouvoir interrompre proprement — donc Ctrl+C termine
     le produit en cours au lieu de l'abandonner a moitie ecrit ;
  4. le telephone sert aussi a autre chose — donc l'usine prend le verrou de
     veille pour ne pas etre endormie, previent par notification quand un
     produit sort, et s'arrete avant de vider la batterie. Tout cela passe
     par « core.telephone », et ne fait rien du tout hors de Termux.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .core import (apprentissage, budget, config, empreinte, evenements,
                   file, llm, marche, reglages, store, telephone, trace,
                   verrou)
from .pipelines import catalogue, idees
from .pipelines.base import Contexte

# Combien de reprises sans une section de plus, fournisseurs disponibles,
# avant de renoncer a finir un produit tout seul.
REPRISES_SANS_PROGRES = 3
# Attente minimale entre deux reprises, en secondes, selon le nombre de
# reprises restees sans progres. Une minute d'abord : un 429 se leve vite. Une
# heure au plus : au-dela, c'est le quota du jour, et le routeur le sait.
PALIERS_D_ATTENTE = (60, 300, 900, 1800, 3600)


def types_disponibles() -> List[str]:
    """Types que la file accepte. Lu du catalogue, jamais recopie."""
    return catalogue.cles(en_file=True)


def chemin_etat() -> Path:
    return config.WORKDIR / "usine-etat.json"


def chemin_verrou() -> Path:
    return config.WORKDIR / "usine.pid"


# --------------------------------------------------------------------------
# Verrou : une seule usine a la fois
# --------------------------------------------------------------------------


def verrou_actif() -> Optional[int]:
    """PID de l'usine en cours, ou None. Nettoie un verrou orphelin."""
    return verrou.detenteur(chemin_verrou()) or None


def _poser_verrou() -> bool:
    """Prend le verrou. Rend False si une autre usine le detient deja.

    « verrou_actif() puis ecrire » etait un controle suivi d'un geste, avec
    un intervalle entre les deux : deux usines lancees dans la meme seconde
    voyaient toutes deux le verrou libre, et toutes deux l'ecrivaient. La
    seconde ecrasait le PID de la premiere — « usine usine arreter » n'en
    arretait donc qu'une, et l'autre continuait a consommer le budget et a
    tirer sur la meme file. Voir « core.verrou ».
    """
    config.ensure_dirs()
    return verrou.prendre(chemin_verrou())


def _lever_verrou() -> None:
    chemin_verrou().unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Etat partage, lisible depuis un autre terminal
# --------------------------------------------------------------------------


def ecrire_etat(etat: Dict[str, Any]) -> None:
    """Ecriture atomique : « usine statut » ne doit jamais lire un fichier a moitie."""
    config.ensure_dirs()
    cible = chemin_etat()
    temporaire = cible.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(etat, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    temporaire.replace(cible)


def lire_etat() -> Dict[str, Any]:
    chemin = chemin_etat()
    if not chemin.exists():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def statut() -> Dict[str, Any]:
    """Vue complete pour « usine usine statut » et le tableau de bord."""
    pid = verrou_actif()
    etat = lire_etat()
    compteur = budget.Compteur()
    return {
        "en_marche": pid is not None,
        "pid": pid,
        "file": file.compter(),
        "budget": compteur.etat(),
        "session": etat,
        "prochaines": [
            {"id": e["id"], "sujet": e["sujet"], "type": e["type"],
             "priorite": e["priorite"]}
            for e in file.lister("en_attente", 8)
        ],
    }


def demander_arret() -> bool:
    """Depose une demande d'arret que l'usine lira entre deux produits."""
    pid = verrou_actif()
    if pid is None:
        return False
    (config.WORKDIR / "usine.stop").write_text(str(time.time()), encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# Le moteur
# --------------------------------------------------------------------------


def graine_de_depart() -> str:
    """Le sujet a partir duquel chercher des niches voisines.

    L'ancienne version prenait la production la plus RECENTE portant une
    note, alors que son commentaire annoncait « les sujets qui ont donne les
    meilleures notes ». Entre une niche notee 9,5 et une notee 4,0 produite
    apres, elle repartait de celle a 4,0.

    Le classement se fait maintenant par chiffre d'affaires d'abord, note
    ensuite : le revenu est une mesure du marche, la note une mesure de
    l'usine, et quand les deux existent c'est le marche qui tranche.
    """
    meilleure = meilleure_niche()
    return meilleure["sujet"] if meilleure else ""


def meilleure_niche() -> Optional[Dict[str, Any]]:
    """La meilleure niche AVEC ce qui la rend meilleure.

    Le classement retombe sur la note qualite quand rien n'a ete vendu — et
    la note est une mesure de l'usine, pas du marche. Le journal disait
    pourtant « Exploration autour de ce qui a le mieux marche : « Cannabis » »
    a quelqu'un qui n'avait jamais rien vendu et dont « Cannabis » etait un
    essai. Journal reel du 16/09/2026.

    Ce n'est pas le classement qui est faux, c'est la phrase : on rend donc
    de quoi la dire juste, et l'appelant choisit ses mots.
    """
    meilleures = apprentissage.meilleures_niches(1)
    return meilleures[0] if meilleures else None


# Le catalogue de depart n'est pas ecrit ici : l'usine le DEMANDE, puis le
# MESURE. Une liste de niches recopiee dans le code aurait deux defauts que
# ce depot connait bien — elle vieillit sans que rien ne le dise, et elle
# donne le meme premier produit a tous ceux qui installent l'usine.
DOMAINES_A_MESURER = 8


def domaines_de_depart(
        journal: Optional[Callable[[str], None]] = None,
        nombre: int = DOMAINES_A_MESURER) -> Dict[str, Any]:
    """Par quoi commencer quand l'atelier est vide.

    C'est le trou que personne ne voyait : « prospecter » cherche des niches
    VOISINES d'une graine, et la graine vient de ce qui a deja rapporte. Sur
    une installation neuve il n'y a rien, donc pas de graine, donc pas de
    prospection — l'usine repondait « ajoutez-en une a la main ». La seule
    fonction qui lui permet de choisir seule etait inatteignable depuis le
    seul etat ou tout le monde commence.

    Proposer suffit a demarrer, mais pas a etre honnete : un domaine sorti de
    l'imagination d'un modele n'est pas une mesure. On propose donc large,
    puis on SONDE chaque domaine sur les sources publiques, et on ne garde que
    ceux ou la demande se voit. Ce qui n'a pas pu etre mesure est rendu
    quand meme, dit comme tel, et jamais presente comme mesure.
    """
    dire = journal or (lambda message: None)
    contexte = Contexte(sujet="", journal=lambda _m: None, sans_image=True)
    # Ce que l'atelier contient deja — fabrique ou seulement mis en file.
    #
    # Deux effets, et le second est celui qui manquait ici. Le modele cesse de
    # reproposer ce qui existe ; et surtout L'INVITE CHANGE des que l'atelier
    # change. Le cache des reponses est indexe sur l'invite : avec une invite
    # figee, le demarrage a froid rendait les MEMES domaines pour toujours.
    #
    # Mesure du 16/09/2026, modele rendant des domaines differents a chaque
    # appel : trois tours, UN seul appel reellement passe au modele, trois
    # fois la meme liste. « idees.explorer » avait recu cette correction en
    # septembre ; le demarrage a froid, qui est pourtant le premier ecran de
    # tout le monde, ne l'avait jamais eue.
    connus = idees.deja_connu()
    deja = ("\n\nL'atelier connait deja ceci — propose AUTRE CHOSE :\n"
            + "\n".join("- " + t for t in connus) + "\n") if connus else ""
    invite = (
        "Un vendeur installe l'usine et n'a encore rien produit : aucun "
        "historique, aucune vente, aucune niche de depart.{deja}\n\n"
        "Propose {n} DOMAINES de depart differents les uns des autres — pas "
        "des titres de produits, des domaines ou un particulier peut vendre "
        "un produit digital fait seul. Chacun en trois a six mots, tel qu'un "
        "acheteur le taperait dans une recherche.\n\n"
        "Evite ce qui exige une certification (medical, juridique, financier "
        "reglemente) et ce qui demande un stock ou une equipe.\n\n"
        'Schema JSON exact :\n'
        '{{"domaines": [{{"domaine": "...", "acheteur": "qui paie et pourquoi", '
        '"pourquoi_maintenant": "..."}}]}}'
    ).format(n=nombre, deja=deja)
    try:
        donnees = idees.equipe.PROSPECTEUR.travailler_json(
            contexte, invite, role_modele="raisonnement",
            temperature=0.9, max_tokens=1600)
    except Exception as exc:
        dire("Impossible de proposer un domaine de depart : {}".format(exc))
        return {"retenus": [], "mesures": [], "mesure": False}

    proposes = donnees.get("domaines") if isinstance(donnees, dict) else donnees
    propres = [d for d in (proposes or [])
               if isinstance(d, dict) and (d.get("domaine") or "").strip()]
    if not propres:
        dire("Le prospecteur n'a propose aucun domaine exploitable.")
        return {"retenus": [], "mesures": [], "mesure": False}

    dire("{} domaines proposes — mesure sur les sources publiques..."
         .format(len(propres)))
    retenus: List[Dict[str, Any]] = []
    mesures: List[Dict[str, Any]] = []
    mesure_possible = False
    for piste in propres:
        nom = piste["domaine"].strip()
        try:
            rapport = marche.sonder(nom)
        except Exception as exc:
            # Le reseau peut tomber au milieu. On ne transforme pas une
            # absence de mesure en mauvaise note : la piste reste candidate,
            # et « mesure » dira que le classement n'en est pas un.
            mesures.append({"domaine": nom, "demande": "", "erreur": str(exc)})
            retenus.append({**piste, "demande": "", "fiabilite": ""})
            continue
        lecture = rapport.get("lecture", {})
        demande = lecture.get("demande", "")
        mesure_possible = mesure_possible or bool(rapport.get("sources_disponibles"))
        mesures.append({"domaine": nom, "demande": demande,
                        "fiabilite": lecture.get("fiabilite", ""),
                        "verdict": lecture.get("verdict", "")})
        # Plus aucune piste n'est ECARTEE sur ces mesures, et c'est le coeur
        # de la correction. Les quatre sources sont anglophones et
        # generalistes : elles peuvent confirmer qu'un sujet interesse, jamais
        # prouver qu'il n'interesse personne. Le detail du releve est au-dessus
        # de « marche.DISCUSSIONS_FORTE ».
        #
        # Ce que faisait l'ancien code : ecarter toute piste dont la demande
        # etait « faible ». Or « faible » tombait des que le mot-cle faisait
        # plusieurs mots ou n'etait pas anglais — c'est-a-dire sur TOUTES les
        # pistes que le prospecteur propose. Huit domaines mesures, huit
        # ecartes, « aucune niche trouvee ». Le journal affichait en prime la
        # fiabilite (« 3/4 sources ») a la place de la raison, ce qui envoyait
        # chercher une panne de source la ou il n'y en avait pas.
        #
        # Les pistes non mesurees ne sont pas perdues : elles ferment la
        # marche du classement, juste apres celles que la mesure a confirmees.
        if demande:
            dire("  {} « {} » — demande {} ({})".format(
                "retenu" if demande == "forte" else "garde", nom, demande,
                lecture.get("fiabilite", "")))
        else:
            dire("  garde « {} » — demande non mesuree ({}) : ces sources ne "
                 "savent pas juger ce mot-cle".format(
                     nom, lecture.get("fiabilite", "")))
        retenus.append({**piste, "demande": demande or "",
                        "fiabilite": lecture.get("fiabilite", "")})

    # Le plus demande d'abord. Les non mesures ferment la marche : ils
    # servent de filet, pas de recommandation.
    rang = {"forte": 0, "moyenne": 1, "": 2}
    retenus.sort(key=lambda d: rang.get(d.get("demande", ""), 2))
    if not mesure_possible:
        dire("Aucune source de marche n'a repondu : ces domaines sont "
             "PROPOSES, pas mesures.")
    # Une seule ligne de conclusion : chaque piste a deja eu la sienne
    # au-dessus. Les repeter toutes les trois faisait un journal ou l'on
    # lisait deux fois la meme chose, et ou la conclusion se noyait.
    if retenus:
        tete = retenus[0]
        dire("  en tete : « {} » — demande {}".format(
            tete["domaine"], tete.get("demande") or "non mesuree"))
    return {"retenus": retenus, "mesures": mesures, "mesure": mesure_possible}


AUTO = "auto"


def _une_promesse_de_lecture(
        type_produit: str,
        dire: Callable[[str], None]) -> Optional[Dict[str, Any]]:
    """Ce qu'on cherche pour une fiction : un lecteur, pas un acheteur.

    Les neuf reglages de genre voyagent avec la promesse. C'est tout
    l'interet : le journal montrait l'usine trouver une niche pratique, puis
    RE-DEVINER genre, tropes, ambiance et fin a partir d'elle — neuf reglages
    decides sur un malentendu. Ici, ils arrivent avec le sujet et lui sont
    accordes.
    """
    from .pipelines import fiction

    dire("Recherche d'une promesse de lecture...")
    contexte = Contexte(sujet="", journal=lambda _m: None, sans_image=True)
    try:
        promesses = fiction.explorer_promesses(
            contexte, nombre=4, connus=idees.deja_connu())
    except Exception as exc:
        dire("Recherche de promesse impossible : {}".format(exc))
        return None
    for piste in promesses:
        titre = (piste.get("titre") or "").strip()
        if not titre:
            continue
        propose = str(piste.get("type") or "") or type_produit
        # Le type demande est une contrainte : une promesse concue pour un
        # conte jeunesse ne fait pas un roman.
        if propose != type_produit:
            continue
        if empreinte.sujets_proches(titre, type_produit):
            continue
        options = {cle: piste[cle] for cle in
                   ("genre", "sous_genre", "tropes", "ambiance",
                    "point_de_vue", "temps", "chaleur", "fin", "structure")
                   if piste.get(cle)}
        if piste.get("lecteur"):
            options["audience"] = piste["lecteur"]
        dire("Promesse retenue : « {} ».".format(titre))
        return {"sujet": titre, "type": type_produit, "source": "fiction",
                "options": options}
    return None


def choisir_une_niche(
        journal: Optional[Callable[[str], None]] = None,
        type_produit: str = "ebook") -> Dict[str, Any]:
    """Le sujet d'UN produit, choisi par l'usine plutot que dicte.

    Repond a la question posee par quelqu'un qui lance « usine ebook » sans
    rien derriere : les dix chaines exigeaient un sujet en positionnel, donc
    la seule facon de ne pas en donner etait de ne pas produire. L'usine
    savait deja chercher des niches — mais seulement dans la boucle continue,
    et seulement une fois qu'il existait un historique.

    DEUX QUESTIONS, ET NON UNE. Pour un guide, on cherche un probleme que
    quelqu'un paie pour resoudre. Pour un roman, cette question n'a pas de
    reponse honnete — et un modele a qui l'on pose une question sans reponse
    en fabrique une. Journal reel du 16/09/2026, « roman » demande, aucun
    sujet donne :

        Exploration autour de ce qui a le mieux marche : « Cannabis »...
        8 domaines proposes — mesure sur les sources publiques...
          garde « cours video montage video » ...
        Premiere niche, choisie par l'usine : « cours video montage video ».
        Titre retenu : « L'Ame du Montage »

    Un roman sur un cours de montage video. « fiction.explorer_promesses »
    existait deja pour cela, et son docstring annoncait exactement ce
    defaut — mais rien ne l'appelait depuis ce chemin-ci : seuls le bouton
    « Trouver des idees de fiction » et la ligne de commande y menaient. Le
    chemin le plus court, celui du bouton « Lancer », posait la question des
    niches a un roman.

    Trois sources, dans cet ordre, parce qu'elles ne valent pas la meme chose :

      1. une niche qui ATTEND DEJA en file — quelqu'un, ou l'usine, l'a
         choisie avant ; la reprendre vaut mieux que d'en inventer une
         onzieme pendant que dix patientent ;
      2. l'exploration autour de ce qui a RAPPORTE, quand l'atelier a un
         historique : c'est la seule source adossee aux ventes reelles ;
      3. un domaine de depart mesure, quand il n'y a rien — le cas de toute
         installation neuve.
    """
    dire = journal or (lambda message: None)
    # « auto » : l'usine choisit AUSSI le type. C'est le seul mode ou le type
    # rendu peut differer de celui demande, et l'appelant doit alors le
    # suivre. Partout ailleurs, le type demande est une contrainte, pas une
    # preference.
    libre = not type_produit or type_produit == AUTO
    vise = "" if libre else type_produit

    def convient(candidat: str) -> bool:
        """Ce type fait-il l'affaire pour la demande en cours ?

        Un sujet est concu POUR un type. « 30 posts LinkedIn pour freelances »
        est un pack de publications ; en faire un ebook donne un ebook dont le
        titre annonce trente posts. Mesure du 14/09/2026 : sur quatre demandes
        de type different, trois repartaient avec un sujet concu pour un
        autre — la file etait lue sans regarder le type, et le type rendu
        etait ensuite jete par les deux appelants.
        """
        return libre or not candidat or candidat == vise

    # 1. La file. On regarde sans prendre : « prochain() » marque l'entree en
    # cours, et une commande unique qui volerait une entree a l'usine continue
    # laisserait celle-ci reprendre un sujet deja fabrique.
    for entree in file.lister(statut="en_attente", limite=40):
        if not convient(entree.get("type") or ""):
            continue
        dire("Une niche attendait en file : « {} ».".format(entree["sujet"]))
        return {"sujet": entree["sujet"],
                "type": entree.get("type") or type_produit or "ebook",
                "source": "file"}

    # 2. Pour une fiction, la question change. On ne la pose qu'ici, apres la
    # file : une promesse qui attend deja vaut mieux qu'une neuve, et le
    # filtre par type a deja fait le tri.
    fiche = catalogue.obtenir(vise) if vise else None
    if fiche is not None and fiche.famille == "fiction":
        promesse = _une_promesse_de_lecture(vise, dire)
        if promesse:
            return promesse
        dire("Aucune promesse neuve : l'usine cherche autrement.")

    meilleure = meilleure_niche()
    graine = meilleure["sujet"] if meilleure else ""
    if graine:
        # « ce qui a le mieux marche » ne se dit que si quelque chose s'est
        # VENDU. Sinon c'est la note de l'usine qui classe, et l'annoncer
        # comme un resultat de marche envoie explorer autour d'un essai.
        if (meilleure or {}).get("brut"):
            dire("Exploration autour de ce qui a le mieux marche : "
                 "« {} » ({} EUR encaisses)...".format(
                     graine, meilleure["brut"]))
        else:
            dire("Rien n'a encore ete vendu : exploration autour du produit "
                 "le mieux NOTE, « {} » — c'est une note de l'usine, pas une "
                 "mesure du marche.".format(graine))
        contexte = Contexte(sujet=graine, journal=lambda _m: None,
                            sans_image=True)
        try:
            pistes = idees.explorer(contexte, nombre=6)
        except Exception as exc:
            dire("Exploration impossible : {}".format(exc))
            pistes = []
        for piste in pistes:
            titre = (piste.get("titre") or "").strip()
            propose = str(piste.get("type") or "")
            if not convient(propose):
                continue
            # Le meme filtre que la file : une piste trop proche d'un produit
            # deja fabrique coute un quota pour un doublon.
            if titre and not empreinte.sujets_proches(
                    titre, propose or type_produit or "ebook"):
                dire("Niche retenue : « {} ».".format(titre))
                return {"sujet": titre,
                        "type": propose or type_produit or "ebook",
                        "source": "voisinage"}
        dire("Toutes les pistes recouvrent un produit deja fait.")

    froid = domaines_de_depart(journal=dire)
    # Un domaine de depart n'a pas de type : c'est un sujet, pas un produit.
    # En mode libre il faut donc en choisir un, et l'ebook est le seul type
    # que tout domaine supporte — les dix autres supposent quelque chose du
    # sujet (une fiction, un logiciel, un reseau social).
    defaut = type_produit if not libre else "ebook"
    for piste in froid["retenus"]:
        nom = piste["domaine"]
        if not empreinte.sujets_proches(nom, defaut):
            dire("Premiere niche, choisie par l'usine : « {} ».".format(nom))
            return {"sujet": nom, "type": defaut,
                    "source": "froid", "mesure": froid["mesure"]}
    return {"sujet": "", "type": defaut, "source": ""}


def prospecter_fiction(nombre: int = 8, graine: str = "",
                       journal: Optional[Callable[[str], None]] = None
                       ) -> Dict[str, Any]:
    """Cherche des PROMESSES DE LECTURE, et non des niches.

    Pourquoi une entree separee plutot qu'un drapeau dans « prospecter » :
    les deux ne posent pas la meme question, ne lisent pas les memes
    sources, et ne remplissent pas les memes reglages. La prospection de
    niches interroge des mesures de marche et des discussions reelles pour
    trouver un probleme que quelqu'un paie pour resoudre. Aucune de ces
    sources ne dit quoi que ce soit d'utile sur le prochain cozy mystery.

    Ce que cette exploration remplit, ce sont les reglages de fiction du
    produit mis en file : sous-genre, tropes, ambiance, chaleur, fin. Sans
    cela, la fiction partait avec les valeurs par defaut — qui ne sont pas
    neutres, seulement invisibles.
    """
    from .pipelines import fiction

    dire = journal or (lambda message: None)
    contexte = Contexte(sujet=graine, journal=lambda m: None, sans_image=True)
    dire("Recherche de promesses de lecture{}...".format(
        " a partir de « {} »".format(graine) if graine else ""))
    try:
        promesses = fiction.explorer_promesses(
            contexte, nombre=nombre, connus=idees.deja_connu())
    except Exception as exc:
        dire("Exploration impossible : {}".format(exc))
        return {"graine": graine, "ajoutees": 0, "ecartees": [], "en_file": 0,
                "pistes": 0, "promesses": []}

    ajoutees, ecartees, en_file = 0, [], 0
    for piste in promesses:
        titre, type_produit = piste["titre"], piste["type"]
        proches = empreinte.sujets_proches(titre, type_produit)
        if proches:
            ecartees.append((titre, proches[0]["titre"] or proches[0]["sujet"]))
            continue
        # Les reglages de fiction voyagent avec la piste. C'est tout
        # l'interet : une promesse trouvee ici arrive en fabrication avec sa
        # chaleur et sa fin, au lieu d'etre re-devinee scene par scene.
        options = {cle: piste[cle] for cle in
                   ("genre", "sous_genre", "tropes", "ambiance",
                    "point_de_vue", "temps", "chaleur", "fin", "structure")
                   if piste.get(cle)}
        if piste.get("lecteur"):
            options["audience"] = piste["lecteur"]
        if file.ajouter(titre, type_produit, options=options, priorite=5,
                        source="auto"):
            ajoutees += 1
        else:
            en_file += 1

    dire("{} promesse(s) explorees, {} mise(s) en file.".format(
        len(promesses), ajoutees))
    for piste in promesses[:3]:
        if piste.get("sous_genre"):
            dire("  « {} » — {} / {}".format(
                piste["titre"][:34], piste["sous_genre"],
                piste.get("tropes", "")[:38]))
    # Le contrat de genre se verifie AVANT de fabriquer : une romance a fin
    # tragique coute un livre entier a decouvrir apres coup.
    for piste in promesses:
        for alerte in fiction.contrat_de_genre(piste):
            dire("  [!] « {} » : {}".format(piste["titre"][:30], alerte))
    if en_file:
        dire("  {} promesse(s) etaient deja en file d'attente.".format(en_file))
    return {"graine": graine, "ajoutees": ajoutees, "ecartees": ecartees,
            "en_file": en_file, "pistes": len(promesses),
            "promesses": promesses}


def prospecter(nombre: int = 8, graine: str = "",
               journal: Optional[Callable[[str], None]] = None,
               avec_veille: bool = True) -> Dict[str, Any]:
    """Cherche des niches voisines et met en file celles qui sont nouvelles.

    C'est ce qui permet a l'usine de CHOISIR ce qu'elle fabrique au lieu
    d'attendre qu'on le lui dise. Trois garde-fous, dans cet ordre :

      1. la graine vient de ce qui a RAPPORTE, pas du dernier produit fait ;
      2. l'exploration s'appuie sur des discussions reelles et sur les
         mesures de marche, pas sur la seule imagination du modele. Le
         remplissage automatique se passait des deux ;
      3. une piste trop proche d'un produit DEJA FABRIQUE est ecartee avant
         d'entrer en file. La file ne se dedoublonne que sur elle-meme :
         sans ce filtre, l'usine refabriquait une niche deja traitee, et
         « usine doublons » ne le signalait qu'apres coup, le quota depense.
    """
    dire = journal or (lambda message: None)
    graine = graine or graine_de_depart()
    depart_a_froid = False
    if not graine:
        # Le cas de TOUT LE MONDE le premier jour. Renvoyer l'utilisateur
        # vers une saisie manuelle revenait a lui refuser la seule fonction
        # pour laquelle il avait allume l'usine.
        dire("Atelier vide : l'usine cherche elle-meme par ou commencer.")
        froid = domaines_de_depart(journal=dire)
        if not froid["retenus"]:
            dire("Aucun domaine de depart n'a pu etre trouve. Donnez-en un "
                 "et l'usine repartira de la.")
            return {"graine": "", "ajoutees": 0, "ecartees": [], "pistes": 0,
                    "froid": froid}
        graine = froid["retenus"][0]["domaine"]
        depart_a_froid = True

    dire("Exploration a partir de « {} »{}...".format(
        graine, " (premiere niche, choisie par l'usine)" if depart_a_froid else ""))
    contexte = Contexte(sujet=graine, journal=lambda m: None, sans_image=True)
    try:
        resultat = idees.produire(contexte, nombre=nombre, avec_marche=True,
                                  avec_veille=avec_veille)
    except Exception as exc:
        # « froid » doit survivre a l'echec : c'est justement quand
        # l'exploration rate qu'on a besoin de savoir si la graine venait de
        # l'historique ou d'un choix que l'usine vient de faire seule.
        dire("Exploration impossible : {}".format(exc))
        return {"graine": graine, "ajoutees": 0, "ecartees": [], "pistes": 0,
                "froid": depart_a_froid}

    pistes = resultat.get("idees", [])
    ajoutees, ecartees = 0, []
    # Deja fabrique et deja en file sont deux refus DIFFERENTS, et les
    # confondre envoyait sur une fausse piste : le rapport disait « toutes
    # recouvrent un produit deja fabrique » alors que l'atelier etait vide et
    # que les pistes etaient simplement celles du tour precedent, encore en
    # attente. On cherchait un defaut de dedoublonnage la ou il n'y en avait
    # pas.
    en_file = 0
    for idee in pistes:
        titre = idee.get("titre") or ""
        type_produit = idee.get("type", "ebook")
        proches = empreinte.sujets_proches(titre, type_produit)
        if proches:
            ecartees.append((titre, proches[0]["titre"] or proches[0]["sujet"]))
            continue
        if file.ajouter(titre, type_produit,
                        options={"audience": idee.get("acheteur", "")},
                        priorite=5, source="auto"):
            ajoutees += 1
        else:
            en_file += 1

    dire("{} piste(s) explorees, {} mise(s) en file.".format(
        len(pistes), ajoutees))
    for titre, deja in ecartees[:4]:
        dire("  ecartee : « {} » recouvre « {} »".format(
            titre[:38], (deja or "")[:38]))
    if en_file:
        dire("  {} piste(s) etaient deja en file d'attente.".format(en_file))
    return {"graine": graine, "ajoutees": ajoutees, "ecartees": ecartees,
            "en_file": en_file,
            "pistes": len(pistes), "froid": depart_a_froid}


def confier_a_la_boucle(type_produit: str, sujet: str, produit_id: str,
                        manquants: int) -> Optional[int]:
    """Met en tete de file un produit inacheve fabrique HORS de la boucle.

    Le bouton « Generer » du tableau de bord fabrique un produit a part. Coupe
    par les quotas, ce produit attendait qu'on revienne appuyer sur
    « Reprendre » — c'est-a-dire, dans l'usage reel, qu'on s'apercoive
    qu'il manquait dix scenes. La boucle sait deja attendre qu'un fournisseur
    rouvre et finir un produit depuis son carnet : on le lui confie, plutot
    que de recopier cette attente dans le serveur.
    """
    identifiant = file.ajouter(sujet, type_produit, priorite=0, source="reprise")
    if identifiant is not None:
        file.a_finir(identifiant, produit_id, manquants)
    return identifiant


class UsineContinue:
    def __init__(
        self,
        auto: bool = False,
        maximum: int = 0,
        journal: Optional[Callable[[str], None]] = None,
        pause: Optional[int] = None,
    ):
        self.auto = auto
        self.maximum = maximum
        # Tout ce qui est dit a l'ecran est aussi ecrit sur disque. Une
        # production continue tourne des heures sur un telephone dont Android
        # reclame le tampon du terminal : sans cela, une niche qui echoue a
        # trois heures du matin ne laisse aucune trace lisible.
        afficher = journal or (lambda message: print("  " + message))
        self.journal = lambda message: (afficher(message),
                                        trace.ecrire(message))[0]
        self.compteur = budget.Compteur()
        self.pause = (reglages.lire("pause_entre_produits", 60)
                      if pause is None else pause)
        self.batterie_minimum = int(reglages.lire("batterie_minimum", 0) or 0)
        self.notifications = bool(reglages.lire("notifications", True))
        self.veille = bool(reglages.lire("verrou_veille", True))
        self._veille_prise = False
        self.arret_batterie = False
        self.arret_demande = False
        self.arret_immediat = False
        self.debut = time.time()
        trace.nettoyer()
        self.faits: List[Dict[str, Any]] = []
        self.motif_fin = ""

    # -- signaux -----------------------------------------------------------
    def _installer_signaux(self) -> None:
        def gerer(signum, cadre):  # noqa: ARG001
            if self.arret_demande:
                self.arret_immediat = True
                self.journal("Second signal : arret immediat.")
                raise KeyboardInterrupt
            self.arret_demande = True
            self.journal("Arret demande — le produit en cours est termine "
                         "puis l'usine s'arrete. (Ctrl+C a nouveau pour couper)")

        for nom in ("SIGINT", "SIGTERM"):
            if hasattr(signal, nom):
                try:
                    signal.signal(getattr(signal, nom), gerer)
                except (ValueError, OSError):
                    pass  # pas de signaux hors du thread principal

    def _arret_externe(self) -> bool:
        drapeau = config.WORKDIR / "usine.stop"
        if drapeau.exists():
            drapeau.unlink(missing_ok=True)
            self.journal("Arret demande depuis un autre terminal.")
            return True
        return False

    # -- etat --------------------------------------------------------------
    def _publier(self, courant: Optional[Dict[str, Any]] = None) -> None:
        etat = {
            "pid": os.getpid(),
            "demarre_le": self.debut,
            "duree": round(time.time() - self.debut, 1),
            "auto": self.auto,
            "courant": courant,
            "faits": self.faits[-20:],
            "nombre_faits": len(self.faits),
            "budget": self.compteur.etat(),
            "file": file.compter(),
            "motif_fin": self.motif_fin,
        }
        ecrire_etat(etat)
        evenements.publier("usine", **{k: v for k, v in etat.items()
                                       if k in ("courant", "nombre_faits",
                                                "budget", "file", "motif_fin")})

    # -- notifications Android ----------------------------------------------
    def _fichier_a_montrer(self, resume: Dict[str, Any]) -> Optional[Path]:
        """Ce que la notification ouvre quand on la tape.

        Le PDF d'abord : c'est le fichier qu'on regarde pour juger un produit.
        A defaut l'EPUB, puis le dossier lui-meme.

        La liste vient du resume de fabrication, dans l'ordre ou les fichiers
        ont ete ecrits — le document principal d'abord, ses annexes ensuite.
        Un simple glob trie ne donne pas cet ordre : « guide-annexe.pdf »
        passe AVANT « guide.pdf », le tiret triant avant le point.
        """
        dossier = resume.get("dossier") or ""
        if not dossier:
            return None
        noms = resume.get("fichiers") or []
        for extension in (".pdf", ".epub", ".html"):
            nom = next((n for n in noms if n.endswith(extension)), "")
            if nom and (Path(dossier) / nom).exists():
                return Path(dossier) / nom
        return Path(dossier) if Path(dossier).exists() else None

    def _notifier(self, titre: str, contenu: str = "",
                  ouvrir: Optional[Path] = None, urgente: bool = False) -> None:
        """Previent le telephone. Sans termux-api, ne fait rien et ne coute rien."""
        if self.notifications:
            telephone.notifier(titre, contenu, ouvrir=ouvrir, urgente=urgente)

    # -- remplissage automatique -------------------------------------------
    def _remplir(self) -> int:
        """Genere de nouvelles niches quand la file se vide."""
        return prospecter(nombre=8, journal=self.journal)["ajoutees"]

    # -- fabrication d'une entree -------------------------------------------
    def _fabriquer(self, entree: Dict[str, Any]) -> bool:
        type_produit = entree["type"]
        if catalogue.obtenir(type_produit) is None:
            file.echouer(entree["id"], "type inconnu : {}".format(type_produit))
            self.journal("  type inconnu : {}".format(type_produit))
            return False

        options = entree.get("options") or {}

        def journal(message: str) -> None:
            self.journal("    " + message)

        from .pipelines import porte
        from .pipelines import reprise as module_reprise

        reprise_id = str(options.get("reprendre_id") or "")
        self.compteur.demarrer_produit()
        budget.brancher(self.compteur)
        debut = time.time()
        try:
            if reprise_id and module_reprise.par_le_catalogue(reprise_id):
                self.journal("  reprise du produit inacheve, depuis son carnet "
                             "({} section(s) a ecrire)".format(
                                 options.get("manquants", "?")))
                resume = module_reprise.reprendre(reprise_id, journal=journal)
            else:
                # Le meme chemin que le bouton « Generer » du tableau de bord.
                contexte = porte.contexte(entree["sujet"], options, journal)
                resume = porte.fabriquer(type_produit, contexte, options, journal)
        except module_reprise.DejaEnReprise as exc:
            # Quelqu'un finit deja ce produit — le bouton « Reprendre »,
            # presse pendant que la boucle attendait. Il n'y a rien a faire
            # de plus, et le compter comme un echec de la niche la ferait
            # abandonner alors que le produit est en train d'aboutir.
            file.terminer(entree["id"], reprise_id)
            self.compteur.terminer_produit(reussi=False)
            self.journal("  {} : la boucle le laisse faire.".format(exc))
            return False
        except budget.BudgetEpuise as exc:
            # Un plafond atteint n'est pas une faute de la niche : elle repart
            # en file, intacte, pour la prochaine session.
            file.echouer(entree["id"], "budget : {}".format(exc))
            self.compteur.terminer_produit(reussi=False)
            self.motif_fin = str(exc)
            self.arret_demande = True
            self.journal("  {} — l'usine s'arrete, la niche reste en file."
                         .format(exc))
            return False
        except Exception as exc:
            statut_suivant = file.echouer(entree["id"], str(exc))
            self.compteur.terminer_produit(reussi=False)
            self.journal("  echec : {} ({})".format(exc, statut_suivant))
            return False
        finally:
            budget.brancher(None)

        fiche = store.lire_produit(resume.get("produit_id", "")) or {}
        if fiche.get("statut") == "en_cours" and not self.compteur.refus:
            return self._inacheve(entree, resume, fiche)

        file.terminer(entree["id"], resume.get("produit_id", ""))
        self.compteur.terminer_produit(reussi=True)
        if self.compteur.refus:
            # Le plafond que l'utilisateur s'est fixe : c'est a lui de le
            # lever, pas a l'usine d'attendre qu'il disparaisse.
            self.motif_fin = "budget epuise pendant la fabrication"
            self.arret_demande = True
            self.journal("  budget epuise ({}) : produit exporte en l'etat, "
                         "l'usine s'arrete.".format(self.compteur.refus))
        elif resume.get("budget_epuise"):
            self.journal("  plus rien a demander pendant la fabrication : "
                         "produit exporte en l'etat.")
        # Le signalement de doublon est pose par la chaine de fabrication
        # dans la fiche du produit : on le relit ici pour en tenir compte au
        # bilan de session, la ou la decision de publier se prend.
        meta = fiche.get("meta") or {}
        self.faits.append({
            "sujet": entree["sujet"], "type": type_produit,
            "titre": resume.get("titre", ""), "note": resume.get("note"),
            "duree": round(time.time() - debut, 1),
            "dossier": resume.get("dossier", ""),
            "doublon": meta.get("doublon"),
        })
        self.journal("  livre : « {} »{} en {:.0f} s".format(
            resume.get("titre", entree["sujet"]),
            " — note {}/10".format(resume["note"]) if resume.get("note") else "",
            time.time() - debut))
        self._notifier(
            "Produit {} pret".format(len(self.faits)),
            "{}{}".format(
                resume.get("titre", entree["sujet"])[:70],
                " — note {}/10".format(resume["note"]) if resume.get("note") else ""),
            ouvrir=self._fichier_a_montrer(resume))
        if resume.get("budget_epuise") and not self.compteur.refus:
            # Le produit est complet ; seule une etape facultative a ete
            # perdue. Le suivant ne ferait pas mieux tant que rien n'a rouvert.
            self._attendre_de_quoi_continuer(0, entree)
        return True

    # -- produit inacheve : le reprendre, sans qu'on le demande -----------------
    def _inacheve(self, entree: Dict[str, Any], resume: Dict[str, Any],
                  fiche: Dict[str, Any]) -> bool:
        """Un produit sorti avec des sections manquantes.

        Journal reel du 16/09/2026, roman de dix-huit scenes : les quotas
        s'epuisent a la huitieme, dix scenes restent a ecrire, et l'usine
        continue marquait la niche « faite » avant de s'arreter. Le produit
        attendait sur le disque qu'on pense a appuyer sur « Reprendre ».
        Pour une usine dont la promesse est « appuyer sur Generer et rien
        d'autre », c'etait la panne la plus probable, et la plus silencieuse.
        """
        manquants = len((fiche.get("meta") or {}).get("manquants") or [])
        options = file.a_finir(entree["id"], fiche["id"], manquants)
        self.compteur.terminer_produit(reussi=False)
        sans_progres = int(options.get("sans_progres") or 0)
        epuise = bool(resume.get("budget_epuise"))
        # Renoncer seulement quand rien ne s'epuisait : la meme section qui
        # echoue trois fois de suite, fournisseurs disponibles, ne reussira
        # pas a la quatrieme. Un quota vide, lui, se remplit — attendre est
        # la bonne reponse, aussi longtemps qu'il le faut.
        if sans_progres >= REPRISES_SANS_PROGRES and not epuise:
            file.abandonner(entree["id"], "inacheve : {} section(s) echouent "
                            "encore apres {} reprises".format(manquants, sans_progres))
            self.journal("  {} section(s) echouent encore apres {} reprises : le "
                         "produit reste inacheve (« usine reprendre » pour "
                         "reessayer a la main).".format(manquants, sans_progres))
            return False
        self.journal("  inacheve : {} section(s) a ecrire — il repart en tete de "
                     "file et sera fini automatiquement.".format(manquants))
        if epuise:
            self._attendre_de_quoi_continuer(sans_progres, entree)
        return False

    def _attendre_de_quoi_continuer(self, sans_progres: int,
                                    entree: Dict[str, Any]) -> None:
        """Attendre qu'un fournisseur rouvre, plutot que de s'arreter.

        Avant, un quota epuise arretait l'usine : « budget epuise pendant la
        fabrication ». C'est juste pour le budget de l'UTILISATEUR, qu'il
        s'est fixe lui-meme ; la boucle s'arrete alors d'elle-meme au tour
        suivant. Pour les quotas des fournisseurs, qui repartent seuls, c'est
        attendre qu'il faut — et c'est le routeur qui sait jusqu'a quand.
        """
        if self.compteur.peut_demarrer_produit():
            return                 # budget de l'utilisateur : la boucle s'arrete
        ouverture = llm.prochaine_ouverture()
        if ouverture is None:
            self.motif_fin = ("aucun fournisseur ne pourra repondre : ajoutez "
                              "une cle (« usine cles ») ou lancez un serveur local")
            self.arret_demande = True
            self.journal("  " + self.motif_fin)
            return
        # Le routeur ne voit ni un reseau coupe ni un credit epuise sans
        # repos : « 0 » n'y est pas une promesse. D'ou un plancher, qui
        # s'allonge tant que les reprises ne font rien avancer.
        palier = PALIERS_D_ATTENTE[min(sans_progres, len(PALIERS_D_ATTENTE) - 1)]
        attente = max(ouverture, palier)
        fin = time.time() + attente
        self.journal("  plus rien a demander aux fournisseurs : reprise "
                     "automatique vers {} ({} min).".format(
                         time.strftime("%H:%M", time.localtime(fin)),
                         int(round(attente / 60.0))))
        self._publier(courant={"id": entree["id"], "sujet": entree["sujet"],
                               "type": entree["type"], "depuis": time.time(),
                               "attente_jusqu_a": fin})
        # Pendant une longue attente, le verrou de veille ne sert qu'a vider
        # la batterie : rien ne calcule. Relache, Android peut endormir
        # Termux, et l'attente se termine au premier reveil apres l'heure —
        # « time.time() » a avance pendant le sommeil.
        relache = self._veille_prise
        if relache:
            telephone.verrou_veille(False)
            self._veille_prise = False
        try:
            self._dormir(int(attente))
        finally:
            if relache:
                self._veille_prise = telephone.verrou_veille(True)

    # -- boucle principale ---------------------------------------------------
    def tourner(self) -> int:
        config.ensure_dirs()
        if not _poser_verrou():
            self.journal("Une usine tourne deja (pid {}). "
                         "Arretez-la avec « usine usine arreter ».".format(
                             verrou_actif()))
            return 1
        (config.WORKDIR / "usine.stop").unlink(missing_ok=True)
        self._installer_signaux()

        # Sans ce verrou, Android suspend Termux quelques minutes apres
        # l'extinction de l'ecran : la fabrication s'arrete en plein chapitre.
        self._veille_prise = telephone.verrou_veille(True) if self.veille else False
        if self._veille_prise:
            self.journal("Veille bloquee pendant la session "
                         "(relachee a la fin).")

        orphelines = file.liberer_orphelins()
        if orphelines:
            self.journal("{} niche(s) reprise(s) apres un arret precedent."
                         .format(orphelines))

        plafonds = self.compteur.plafonds
        if plafonds.actif():
            self.journal("Budget : {} appels/jour, {} appels/produit, "
                         "{} produits/jour, {} min/produit.".format(
                             plafonds.appels_jour or "illimite",
                             plafonds.appels_produit or "illimite",
                             plafonds.produits_jour or "illimite",
                             plafonds.minutes_produit or "illimite"))
        else:
            self.journal("Aucun budget defini : l'usine tournera jusqu'a "
                         "epuisement des quotas de vos cles.")

        code = 0
        try:
            while True:
                if self.arret_demande or self._arret_externe():
                    self.motif_fin = self.motif_fin or "arret demande"
                    break
                if self.maximum and len(self.faits) >= self.maximum:
                    self.motif_fin = "{} produit(s) demandes, tous livres".format(
                        self.maximum)
                    break

                faible = telephone.batterie_trop_faible(self.batterie_minimum)
                if faible:
                    self.motif_fin = faible
                    self.arret_batterie = True
                    self.journal(faible)
                    break

                refus = self.compteur.peut_demarrer_produit()
                if refus:
                    self.motif_fin = refus
                    self.journal(refus)
                    break

                entree = file.prochain()
                if entree is None:
                    if self.auto and self._remplir():
                        continue
                    self.motif_fin = "file vide"
                    self.journal("File vide — l'usine s'arrete.")
                    break

                self.journal("[{}] {} — « {} »".format(
                    len(self.faits) + 1, entree["type"], entree["sujet"]))
                self._publier(courant={"id": entree["id"], "sujet": entree["sujet"],
                                       "type": entree["type"],
                                       "depuis": time.time()})
                self._fabriquer(entree)
                self._publier()

                if self.arret_demande:
                    continue
                if self.pause and file.compter()["en_attente"]:
                    self.journal("Pause de {} s (respect des quotas par minute)."
                                 .format(self.pause))
                    if not self._dormir(self.pause):
                        break
        except KeyboardInterrupt:
            self.motif_fin = "interrompu"
            code = 130
        finally:
            budget.brancher(None)
            self._publier()
            _lever_verrou()
            if self._veille_prise:
                telephone.verrou_veille(False)

        self._bilan()
        return code

    def _dormir(self, secondes: int) -> bool:
        """Pause interruptible : Ctrl+C ne doit pas attendre 60 secondes."""
        fin = time.time() + secondes
        while time.time() < fin:
            if self.arret_demande or self._arret_externe():
                return False
            time.sleep(min(1.0, fin - time.time()))
        return True

    def _bilan(self) -> None:
        duree = (time.time() - self.debut) / 60
        self._notifier(
            "Usine arretee — {} produit(s)".format(len(self.faits)),
            self.motif_fin or "fin de session",
            # Une batterie a plat demande un geste ; « file vide » non.
            urgente=self.arret_batterie)
        self.journal("")
        self.journal("Session terminee : {} produit(s) en {:.0f} min — {}".format(
            len(self.faits), duree, self.motif_fin or "fin"))
        notes = [f["note"] for f in self.faits if f.get("note") is not None]
        if notes:
            self.journal("Note moyenne : {:.1f}/10".format(sum(notes) / len(notes)))
        restantes = file.compter()
        if restantes["en_attente"]:
            self.journal("{} niche(s) encore en file — relancez quand vous "
                         "voulez.".format(restantes["en_attente"]))
        self._avant_de_publier()

    def _avant_de_publier(self) -> None:
        """Deux rappels a la fin d'un lot, parce que c'est la qu'on publie.

        Fabriquer vite et publier au meme rythme est le profil exact d'un
        compte qui se fait fermer : KDP limite la creation a dix titres par
        format et par semaine (verifie le 12 septembre 2026 sur la page
        d'aide d'Amazon — c'etait trois par jour jusqu'a fin 2025, un plafond
        plus large pour qui ne publie qu'en numerique) et ferme les comptes de
        contenu depose en volume. Un compte ferme emporte l'historique de
        ventes et les avis ; ralentir les depots ne coute rien.
        """
        if not self.faits:
            return
        doublons = [f for f in self.faits if f.get("doublon")]
        self.journal("")
        if doublons:
            self.journal("[!] {} produit(s) de cette session ressemblent a "
                         "des produits deja faits.".format(len(doublons)))
            self.journal("    Verifiez avant de les mettre en vente : "
                         "usine doublons")
        if len(self.faits) > 1:
            self.journal("Produire n'est pas publier : deposez un a deux "
                         "produits par semaine")
            self.journal("et par plateforme. Voir docs/VENDRE.md.")
