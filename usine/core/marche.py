"""Signaux de marche reels, depuis des sources publiques sans cle API.

Demander a un modele « ce sujet se vend-il ? » produit une reponse fluide et
sans valeur : il n'a pas acces au marche, il produit du plausible. Ce module
va chercher des mesures verifiables, puis les donne au modele comme matiere.

Quatre sources, toutes accessibles sans inscription :

  Hacker News (Algolia)  volume et intensite des discussions sur un sujet
  Wikipedia pageviews    interet reel dans le temps, par langue
  Stack Exchange         volume de questions = douleurs concretes non resolues
  Open Library           nombre d'ouvrages existants = niveau de concurrence

Chaque source est facultative : si l'une tombe, les autres suffisent et le
rapport le signale honnetement plutot que d'inventer un chiffre.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .http import HttpErreur, insister, requete


def _sans_accent(texte: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")


# Hacker News, Stack Exchange et Open Library sont massivement anglophones.
# Une requete en francais y renvoie peu ou rien, ce qui n'a rien a voir avec
# la taille du marche francophone : il faut le dire, pas le laisser croire.
_MOTS_FRANCAIS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "pour", "avec", "sans",
    "comment", "pourquoi", "sur", "dans", "chez", "aux", "et", "ou", "son",
    "ses", "mon", "votre", "vos", "ce", "cette", "qui", "que",
}


def _semble_francais(sujet: str) -> bool:
    mots = [m for m in sujet.lower().split() if m]
    if len(mots) < 2:
        return False
    return sum(1 for m in mots if m in _MOTS_FRANCAIS) >= 1


# Ce que « discussions_totales » mesure vraiment. Releve du 15/09/2026 sur
# l'API de recherche de Hacker News :
#
#     machine learning      18 539       kubernetes            11 481
#     photography            5 203       startup funding        4 642
#     python programming     3 078       meditation             2 290
#     personal finance       1 819       gardening                566
#     meal planning            196       freelance invoicing      126
#     facturation freelance      0       potager balcon             0
#
# L'echelle suit la LARGEUR du mot-cle et sa presence dans un forum
# anglophone de developpeurs. Elle ne suit pas la demande d'un marche : un nom
# de niche fait plusieurs mots par nature, et une niche francophone rend zero
# quoi qu'il arrive.
#
# Ces deux seuils n'avaient jamais ete mesures, et le troisieme cas — « en
# dessous, la demande est FAIBLE » — ecartait donc toutes les pistes que le
# prospecteur propose. Huit domaines mesures, huit ecartes, « aucune niche
# trouvee » : la recherche de niche ne pouvait pas aboutir, et c'etait vrai
# depuis le premier jour.
#
# Ils servent desormais a PROMOUVOIR une piste, jamais a l'ecarter.
DISCUSSIONS_FORTE = 3000
DISCUSSIONS_MOYENNE = 400


@dataclass
class Source:
    nom: str
    disponible: bool = False
    donnees: Dict[str, Any] = field(default_factory=dict)
    erreur: str = ""


def _json(url: str, timeout: int = 20) -> Any:
    """Une source du sondage, rejouee si elle a echoue de facon temporaire.

    Les quatre services publics interroges ici tombent regulierement — ce
    sont des API gratuites et sans engagement. Mesure du 15/09/2026 : un
    seul essai par source, aucune attente. Une source absente ne fait pas
    echouer le sondage, elle le rend plus pauvre en silence, et « 3/4
    sources » ressemble a « 4/4 » dans un rapport que personne ne relit.

    Deux essais et non trois : un sondage interroge quatre services de suite,
    et l'utilisateur attend devant son telephone.
    """
    def appel():
        _, brut = requete(url, "GET", {"Accept": "application/json"}, None,
                          timeout)
        return json.loads(brut.decode("utf-8", "replace"))

    return insister(appel, tentatives=2)


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def hacker_news(sujet: str, timeout: int = 20) -> Source:
    """Discussions reelles : volume, engagement, sujets qui remontent."""
    source = Source("hacker_news")
    try:
        url = ("https://hn.algolia.com/api/v1/search?query={}&tags=story"
               "&hitsPerPage=30").format(urllib.parse.quote(sujet))
        data = _json(url, timeout)
        hits = data.get("hits") or []
        points = [h.get("points") or 0 for h in hits]
        commentaires = [h.get("num_comments") or 0 for h in hits]
        source.disponible = True
        source.donnees = {
            "discussions_totales": data.get("nbHits", 0),
            "points_median": sorted(points)[len(points) // 2] if points else 0,
            "commentaires_median": (sorted(commentaires)[len(commentaires) // 2]
                                    if commentaires else 0),
            "titres_forts": [
                {"titre": h.get("title") or "", "points": h.get("points") or 0,
                 "commentaires": h.get("num_comments") or 0}
                for h in sorted(hits, key=lambda x: -(x.get("points") or 0))[:8]
                if h.get("title")
            ],
        }
    except (HttpErreur, ValueError, KeyError) as exc:
        source.erreur = str(exc)
    return source


# Les mots qui ouvrent un nom de niche sans rien en dire. « le tricot » ne
# titre aucun article ; « Tricot » si. Sans cette liste, les deux n'avaient
# aucune proximite, et le classement se rabattait sur la frequentation — qui
# elisait un tableau de Georges de La Tour.
_ARTICLES = ("le ", "la ", "les ", "l'", "un ", "une ", "des ", "du ",
             "de la ", "de l'", "d'")


def _sans_article(texte: str) -> str:
    """Le nom sans son article defini, ACCENTS COMPRIS.

    Deux usages qu'il ne faut pas confondre. Pour COMPARER deux titres, on
    retire les accents — « Meditation » et « Méditation » sont le meme mot.
    Pour INTERROGER Wikipedia, il faut les garder : demander « meditation »
    rendait un article homonyme a 10 vues par mois la ou « Méditation » en
    fait plusieurs milliers. Un chiffre qui a l'air d'une mesure et n'en est
    pas une — exactement le defaut que ce module vient de corriger ailleurs.
    """
    propre = texte.strip()
    change = True
    while change:
        change = False
        for article in _ARTICLES:
            # « .lower() » et rien de plus : aucun article francais ne
            # porte d'accent, donc les retirer ici ne faisait rien — une
            # campagne de mutation l'a montre en le supprimant sans qu'un
            # test bronche.
            if propre.lower().startswith(article):
                propre = propre[len(article):].strip()
                change = True
                break
    return propre


def _nu(texte: str) -> str:
    """Le nom, sans accent, sans casse et sans son article defini."""
    propre = _sans_accent(texte).lower().strip()
    # En boucle : « d'une niche » en porte deux. Bornee par la longueur, donc
    # elle s'arrete — et un titre qui ne serait fait que d'articles se reduit
    # a rien, ce qui est la bonne reponse.
    change = True
    while change:
        change = False
        for article in _ARTICLES:
            if propre.startswith(article):
                propre = propre[len(article):].strip()
                change = True
                break
    return propre


def wikipedia_interet(sujet: str, langue: str = "fr", mois: int = 12,
                      timeout: int = 20) -> Source:
    """Interet reel dans le temps. Remplace Google Trends, dont l'API est fermee."""
    source = Source("wikipedia")
    try:
        # « opensearch » compare des PREFIXES de titres. Interroge avec
        # « le tricot », il rend « Le Tricheur a l'as de carreau » et jamais
        # « Tricot » : l'article defini rend la bonne page inatteignable. On
        # l'interroge donc avec le nom nu, qui est ce qui titre les articles.
        recherche = ("https://{}.wikipedia.org/w/api.php?action=opensearch"
                     "&search={}&limit=4&format=json").format(
                         langue, urllib.parse.quote(_sans_article(sujet)))
        resultat = _json(recherche, timeout)
        titres = resultat[1] if len(resultat) > 1 else []
        articles = 0
        if not titres:
            # « opensearch » ne compare que des TITRES. Un nom de niche n'en
            # est pas un : « la facturation des independants » ne titre aucun
            # article, donc la source abandonnait ici — avant meme d'atteindre
            # les vues, qui sont pourtant la mesure qu'elle existe pour rendre.
            #
            # Mesure du 16/09/2026 sur six noms de niches realistes : Wikipedia
            # ne repondait que sur UN — « le tricot », qui se trouve etre un
            # titre d'article. La recherche plein texte les trouve tous, et
            # elle separe le reel de l'invente :
            #
            #     le tricot                             2 209 articles
            #     la facturation des independants          232
            #     la meditation pour debutants             183
            #     le potager en bac sur balcon              21
            #     la reparation de theremines a vapeur       0
            #     le pliage de serviettes pour chats         0
            #
            # En REPLI et non en remplacement : quand le sujet EST un titre
            # d'article, « opensearch » le trouve mieux, et le classement par
            # proximite ci-dessous a ete regle sur lui.
            # Ici la phrase ENTIERE, et non le nom nu : la recherche plein
            # texte se nourrit des mots, c'est ce qui la rend capable de
            # trouver « Jardinage en carres » a partir de « potager en bac ».
            plein_texte = ("https://{}.wikipedia.org/w/api.php?action=query"
                           "&list=search&srsearch={}&srlimit=4&format=json"
                           ).format(langue, urllib.parse.quote(sujet))
            trouve = _json(plein_texte, timeout).get("query") or {}
            titres = [p["title"] for p in (trouve.get("search") or [])]
            articles = int((trouve.get("searchinfo") or {}).get("totalhits", 0))
        if not titres:
            source.erreur = "aucun article correspondant"
            return source

        fin = datetime.utcnow().replace(day=1)
        debut = fin - timedelta(days=31 * mois)

        # Deux pieges opposes : le premier resultat n'est pas toujours le bon
        # (« Productivity software » avant « Productivity »), mais choisir le
        # plus consulte ne l'est pas non plus (« Freelance » renverrait le film
        # de 2023). On classe donc d'abord sur la proximite du titre, et la
        # frequentation ne sert qu'a departager a proximite egale.
        cible = _nu(sujet)

        def proximite(titre: str) -> int:
            nom = _nu(titre)
            if "(" in nom and "(" not in cible:
                return 0            # page homonyme : film, album, personne
            if nom == cible:
                return 3
            if nom.startswith(cible) or cible.startswith(nom):
                return 2
            return 1

        classes = sorted(titres[:4], key=lambda t: -proximite(t))
        meilleure_proximite = proximite(classes[0]) if classes else 0
        # Aucun titre n'a de rapport avec le sujet : on ne lui attribue PAS
        # une frequentation. Departager par les vues des candidats restants,
        # c'est ce qui donnait « la facturation des independants » -> « DKV
        # Euro Service » (145 vues/mois, une societe de cartes carburant) et
        # « le tricot » -> « Le Tricheur a l'as de carreau » (2 218 vues/mois,
        # un tableau de Georges de La Tour). Le nombre avait l'air d'une
        # mesure et n'en etait pas une.
        #
        # Le compte d'articles, lui, reste vrai : il ne pretend rien attribuer.
        if meilleure_proximite < 2:
            source.disponible = bool(articles)
            source.donnees = {"article": "", "articles_fr": articles,
                              "frequentation": "non attribuee",
                              "candidats": classes[:3]}
            if not articles:
                source.erreur = "aucun article correspondant"
            return source
        retenus = [t for t in classes if proximite(t) == meilleure_proximite]

        article, vues = "", []
        for candidat in retenus:
            url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                   "{}.wikipedia/all-access/user/{}/monthly/{}/{}").format(
                       langue, urllib.parse.quote(candidat.replace(" ", "_"), safe=""),
                       debut.strftime("%Y%m%d00"), fin.strftime("%Y%m%d00"))
            try:
                items = (_json(url, timeout).get("items") or [])
            except (HttpErreur, ValueError):
                continue
            mesures = [i.get("views", 0) for i in items]
            if mesures and sum(mesures) > sum(vues):
                article, vues = candidat, mesures
        if not vues:
            # Le titre correspond, mais l'API des vues n'a rien rendu. Le
            # compte d'articles reste vrai et ne doit pas partir avec :
            # l'ancienne version renvoyait une source vide, donc « 3/4 » au
            # lieu de « 4/4 », pour une mesure qu'on avait pourtant.
            source.disponible = bool(articles)
            source.donnees = {"article": "", "articles_fr": articles,
                              "frequentation": "non attribuee"}
            if not articles:
                source.erreur = "aucune mesure de frequentation"
            return source

        moitie = max(1, len(vues) // 2)
        recent = sum(vues[-moitie:]) / moitie
        ancien = sum(vues[:moitie]) / moitie
        moyenne_vues = int(sum(vues) / len(vues))
        source.disponible = True
        source.donnees = {
            "article": article,
            # Combien d'articles francophones parlent du sujet. Rendu, jamais
            # interprete : six points de releve ne font pas un seuil, et un
            # verdict non mesure vaut moins qu'une mesure honnete. Il sert a
            # l'humain qui lit le rapport.
            "articles_fr": articles,
            # Sous 200 vues/mois, l'article est trop confidentiel : la tendance
            # devient du bruit statistique et ne doit pas peser dans le verdict.
            "significatif": moyenne_vues >= 200,
            "vues_mensuelles_moyennes": moyenne_vues,
            "vues_dernier_mois": vues[-1],
            "tendance": ("hausse" if recent > ancien * 1.15 else
                         "baisse" if recent < ancien * 0.85 else "stable"),
            "variation_pourcent": round((recent - ancien) / ancien * 100, 1)
            if ancien else 0.0,
            "historique": vues,
        }
    except (HttpErreur, ValueError, KeyError, IndexError) as exc:
        source.erreur = str(exc)
    return source


def stack_exchange(sujet: str, site: str = "stackoverflow",
                   timeout: int = 20) -> Source:
    """Volume de questions : une douleur repetee est un produit potentiel."""
    source = Source("stack_exchange")
    try:
        url = ("https://api.stackexchange.com/2.3/search/advanced?order=desc"
               "&sort=votes&q={}&site={}&pagesize=20&filter=default").format(
                   urllib.parse.quote(sujet), site)
        data = _json(url, timeout)
        items = data.get("items") or []
        sans_reponse = sum(1 for i in items if not i.get("is_answered"))
        source.disponible = True
        source.donnees = {
            "site": site,
            "questions_trouvees": len(items),
            "sans_reponse_acceptee": sans_reponse,
            "quota_restant": data.get("quota_remaining"),
            "questions_fortes": [
                {"titre": i.get("title", ""), "votes": i.get("score", 0),
                 "vues": i.get("view_count", 0), "resolue": i.get("is_answered", False)}
                for i in items[:6]
            ],
        }
    except (HttpErreur, ValueError, KeyError) as exc:
        source.erreur = str(exc)
    return source


def open_library(sujet: str, timeout: int = 20) -> Source:
    """Concurrence editoriale : combien d'ouvrages traitent deja le sujet."""
    source = Source("open_library")
    try:
        url = ("https://openlibrary.org/search.json?q={}&limit=20"
               "&fields=title,first_publish_year,author_name").format(
                   urllib.parse.quote(sujet))
        data = _json(url, timeout)
        docs = data.get("docs") or []
        annees = [d.get("first_publish_year") for d in docs
                  if isinstance(d.get("first_publish_year"), int)]
        recents = [a for a in annees if a >= datetime.utcnow().year - 5]
        source.disponible = True
        source.donnees = {
            "ouvrages_totaux": data.get("numFound", 0),
            "echantillon": len(docs),
            "recents_dans_echantillon": len(recents),
            "annee_mediane": sorted(annees)[len(annees) // 2] if annees else None,
            "exemples": [
                {"titre": d.get("title", ""), "annee": d.get("first_publish_year")}
                for d in docs[:6]
            ],
        }
    except (HttpErreur, ValueError, KeyError) as exc:
        source.erreur = str(exc)
    return source


# --------------------------------------------------------------------------
# Agregation
# --------------------------------------------------------------------------

SOURCES = {
    "hacker_news": hacker_news,
    "wikipedia": wikipedia_interet,
    "stack_exchange": stack_exchange,
    "open_library": open_library,
}


def sonder(sujet: str, journal=None, timeout: int = 20) -> Dict[str, Any]:
    """Interroge toutes les sources et agrege un rapport factuel."""
    resultats: Dict[str, Source] = {}
    for nom, fonction in SOURCES.items():
        if journal:
            journal("  source {}...".format(nom))
        debut = time.time()
        source = fonction(sujet, timeout=timeout)
        source.donnees["duree"] = round(time.time() - debut, 1)
        resultats[nom] = source

    rapport: Dict[str, Any] = {
        "sujet": sujet,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "sources": {
            nom: {"disponible": s.disponible, "erreur": s.erreur, **s.donnees}
            for nom, s in resultats.items()
        },
        "sources_disponibles": [n for n, s in resultats.items() if s.disponible],
        "sources_indisponibles": [n for n, s in resultats.items() if not s.disponible],
    }
    rapport["lecture"] = interpreter(rapport)
    return rapport


def interpreter(rapport: Dict[str, Any]) -> Dict[str, Any]:
    """Transforme les mesures brutes en signaux lisibles.

    Volontairement prudent : sans source disponible, on dit qu'on ne sait pas,
    au lieu de produire un verdict rassurant et vide.
    """
    sources = rapport["sources"]
    signaux: List[str] = []
    demande: Optional[str] = None
    concurrence: Optional[str] = None
    tendance: Optional[str] = None

    hn = sources.get("hacker_news", {})
    if hn.get("disponible"):
        total = hn.get("discussions_totales", 0)
        if total > DISCUSSIONS_FORTE:
            demande = "forte"
            signaux.append("{} discussions sur Hacker News : sujet tres debattu"
                           .format(total))
        elif total > DISCUSSIONS_MOYENNE:
            demande = "moyenne"
            signaux.append("{} discussions sur Hacker News".format(total))
        else:
            # Et surtout PAS « faible ». Voir le releve au-dessus de
            # « DISCUSSIONS_FORTE » : sous ce niveau, le compte ne distingue
            # plus une niche sans marche d'une niche simplement etroite ou
            # francophone. « potager balcon » rend exactement zero, et cela ne
            # dit rien du marche francophone du potager en balcon.
            #
            # Une source anglophone generaliste peut CONFIRMER un interet ;
            # elle ne peut pas prouver son absence. On laisse donc « demande »
            # a None — « non mesuree » — plutot que de rendre un verdict que
            # la mesure ne porte pas.
            signaux.append(
                "{} discussion(s) sur Hacker News : sous le seuil ou ce compte "
                "distingue quelque chose — la demande n'est pas mesuree ici"
                .format(total))

    wiki = sources.get("wikipedia", {})
    if wiki.get("disponible"):
        if wiki.get("frequentation") == "non attribuee":
            # Le cas le plus frequent sur un nom de niche : des articles
            # parlent du sujet, mais aucun ne s'intitule comme lui. On rend le
            # compte, qui est vrai, et on ne fabrique pas de frequentation.
            signaux.append(
                "Wikipedia : {} article(s) francophones citent ce sujet, mais "
                "aucun ne lui correspond assez pour lui attribuer une "
                "frequentation".format(wiki.get("articles_fr", 0)))
        elif wiki.get("significatif"):
            tendance = wiki.get("tendance")
            signaux.append(
                "Wikipedia « {} » : {} vues/mois, tendance {} ({:+.0f} %)".format(
                    wiki.get("article", ""), wiki.get("vues_mensuelles_moyennes", 0),
                    tendance, wiki.get("variation_pourcent", 0)))
        else:
            signaux.append(
                "Wikipedia « {} » : seulement {} vues/mois — trop peu pour conclure, "
                "la tendance n'est pas retenue".format(
                    wiki.get("article", ""), wiki.get("vues_mensuelles_moyennes", 0)))

    se = sources.get("stack_exchange", {})
    if se.get("disponible") and se.get("questions_trouvees"):
        sans = se.get("sans_reponse_acceptee", 0)
        if sans:
            signaux.append(
                "{} question(s) sans reponse acceptee sur {} : autant de douleurs "
                "non resolues".format(sans, se.get("site", "Stack Exchange")))

    ol = sources.get("open_library", {})
    if ol.get("disponible"):
        total = ol.get("ouvrages_totaux", 0)
        recents = ol.get("recents_dans_echantillon", 0)
        if total > 5000:
            concurrence = "forte"
        elif total > 500:
            concurrence = "moyenne"
        else:
            concurrence = "faible"
        signaux.append(
            "{} ouvrages recenses (concurrence {}) ; {} des {} premiers resultats "
            "datent des 5 dernieres annees".format(
                total, concurrence, recents, ol.get("echantillon", 0)))

    francais = _semble_francais(rapport.get("sujet", ""))
    if not rapport["sources_disponibles"]:
        verdict = ("Aucune source n'a repondu. Impossible de qualifier ce marche : "
                   "verifiez la connexion, ou decidez sans ce signal.")
    elif demande == "forte" and concurrence == "faible":
        verdict = ("Beaucoup d'interet, peu d'offre editoriale : creneau interessant, "
                   "a condition d'un angle precis.")
    elif demande == "forte" and concurrence == "forte":
        verdict = ("Marche actif mais encombre : ne pas viser le sujet general, "
                   "viser un segment et un probleme precis.")
    elif demande is None:
        verdict = ("Aucune source n'a pu qualifier la demande : ces mesures sont "
                   "anglophones et generalistes, et un nom de niche n'y laisse "
                   "pas de trace. Le sujet n'est ni valide ni invalide — il "
                   "est non mesure.")
    else:
        verdict = ("Signaux moyens. Le sujet tient, la difference se fera sur l'angle "
                   "et sur la preuve apportee.")
    if tendance == "baisse":
        verdict += " Attention : l'interet mesure recule sur douze mois."
    if francais and demande is None:
        verdict = (
            "Ces sources sont anglophones : une requete en francais y renvoie peu "
            "de resultats, ce qui ne dit RIEN du marche francophone. Relancez avec "
            "le mot-cle anglais equivalent pour obtenir un signal exploitable. "
            "(" + verdict + ")"
        )

    return {
        "requete_francophone": francais,
        "demande": demande,
        "concurrence": concurrence,
        "tendance": tendance,
        "signaux": signaux,
        "verdict": verdict,
        "fiabilite": "{}/{} sources".format(
            len(rapport["sources_disponibles"]), len(SOURCES)),
    }


def resume_pour_ia(rapport: Dict[str, Any], limite: int = 1800) -> str:
    """Condense le rapport en matiere exploitable dans une invite."""
    lecture = rapport.get("lecture", {})
    lignes = ["DONNEES DE MARCHE MESUREES le {} ({})".format(
        rapport.get("date", ""), lecture.get("fiabilite", ""))]
    for signal in lecture.get("signaux", []):
        lignes.append("- " + signal)

    hn = rapport["sources"].get("hacker_news", {})
    if hn.get("titres_forts"):
        lignes.append("Discussions les plus suivies :")
        for element in hn["titres_forts"][:5]:
            lignes.append("  - « {} » ({} points, {} commentaires)".format(
                element["titre"][:90], element["points"], element["commentaires"]))

    se = rapport["sources"].get("stack_exchange", {})
    if se.get("questions_fortes"):
        lignes.append("Questions recurrentes :")
        for element in se["questions_fortes"][:4]:
            lignes.append("  - « {} » ({} votes, {} vues{})".format(
                element["titre"][:90], element["votes"], element["vues"],
                "" if element["resolue"] else ", non resolue"))

    ol = rapport["sources"].get("open_library", {})
    if ol.get("exemples"):
        lignes.append("Ouvrages deja publies :")
        for element in ol["exemples"][:4]:
            lignes.append("  - « {} » ({})".format(
                element["titre"][:80], element["annee"] or "date inconnue"))

    if lecture.get("verdict"):
        lignes.append("Lecture : " + lecture["verdict"])
    texte = "\n".join(lignes)
    return texte[:limite]
