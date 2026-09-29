"""Ce qu'on cherche pour la fiction — et qui n'est pas une niche.

Une niche, dans le reste de l'usine, c'est un PROBLEME que quelqu'un paie
pour resoudre : « facturer sans se tromper quand on est auto-entrepreneur ».
Toute la prospection est batie la-dessus — probleme, acheteur, promesse de
resultat, concurrence, canal d'acquisition.

Applique a un roman, ce vocabulaire ne veut rien dire. Personne n'achete une
romance pour resoudre un probleme, et « quel probleme resout votre thriller »
n'a pas de reponse. L'usine posait quand meme la question, et obtenait donc
des reponses fabriquees : une fiction habillee en produit pratique, avec un
« probleme precis resolu » invente apres coup.

Ce que le lecteur de fiction achete, c'est une PROMESSE DE LECTURE. Elle se
decrit en cinq choses, et elles sont toutes absentes du vocabulaire des
niches :

  le GENRE et son SOUS-GENRE   ou le livre se range, et qui le cherche ;
  les TROPES                   ce que le lecteur veut retrouver ;
  l'AMBIANCE                   ce qu'il vient ressentir ;
  la FIN attendue              ce qu'il ne pardonnera pas qu'on lui refuse ;
  la CHALEUR                   ce qu'il attend, et son inverse le fache.

Releve du 15/09/2026 sur l'etat du marche de l'edition independante : la
decouverte se fait par TROPE avant de se faire par genre, et les
sous-genres se sont fragmentes en micro-genres (romantasy, dark romance,
romance sportive, cozy mystery). Un livre bien ecrit decoit quand
l'emballage promet une experience et que le texte en livre une autre.

DONNEES RECOPIEES, DONC PERISSABLES — comme les quotas de « config.py ». Les
listes ci-dessous sont un vocabulaire de depart, pas une verite. Elles
servent a proposer, jamais a interdire : un genre absent de la liste reste
saisissable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from ..core.controle import _sans_accent

# =========================================================================
# LES DONNEES, ET D'OU ELLES VIENNENT
# =========================================================================
#
# Premiere version de ce module : ces listes sortaient de ma tete, avec en
# commentaire « donnees recopiees, donc perissables ». Recopiees de personne.
# C'est exactement le defaut que ce depot traque ailleurs — un chiffre sans
# source — et il est plus grave ici qu'ailleurs, parce qu'une liste de
# sous-genres inventee envoie fabriquer pour un rayon qui n'existe pas.
#
# Tout ce qui suit porte donc sa source et sa date. « SOURCES » n'est pas
# decoratif : un test verifie que chaque liste y figure, et refuse une
# donnee ajoutee sans provenance.
SOURCES = {
    "EN_FRANCAIS": (
        "Ce n'est pas une donnee de marche : la traduction francaise des "
        "termes de genre releves, en regard du terme source. Le terme source "
        "reste la cle des releves de « MOTS_ATTENDUS » — la fourchette a ete "
        "relevee pour « contemporary romance », pas pour une traduction "
        "qu'on en aurait faite. Le libelle francais est ce que l'utilisateur "
        "lit, parce que tout s'affiche en francais ici."),
    "CATEGORIES": (
        "Categories de premier niveau de la fiction chez Amazon KDP, "
        "relevees le 15/09/2026. Amazon ne publie AUCUNE taxinomie complete, "
        "et le dit lui-meme sur sa page d'aide : « thousands of book "
        "categories in each Amazon marketplace, and they can change over "
        "time ». Elle renvoie a la navigation du magasin plutot qu'a une "
        "liste. Celle-ci est donc partielle par construction, et le dire "
        "fait partie de la donnee."),
    "SOUS_GENRES": (
        "Sous-categories effectivement nommees par les sources consultees le "
        "15/09/2026 (guides de categories KDP). La romance seule en compte "
        "plus de quarante ; on ne retient ici que celles qu'une source "
        "nomme."),
    "TROPES": (
        "Tropes les plus cherches et les plus cites, releves le 15/09/2026 "
        "sur les recensements publics de tendances de lecture. « Enemies to "
        "lovers » y est donne comme le plus recherche. Donnee la plus "
        "perissable du module : les tropes tournent d'une saison a l'autre."),
    "FINS_EXIGEES_EN_ROMANCE": (
        "Relevee le 15/09/2026. Definition du genre par la Romance Writers "
        "of America : « a central "
        "love story and an emotionally satisfying and optimistic ending », "
        "soit HEA (heureuse) ou HFN (heureuse pour l'instant). C'est une "
        "definition de genre, pas un avis : une fin malheureuse sort le "
        "livre du rayon."),
    "CHALEUR": (
        "Echelle relevee le 15/09/2026. Les paliers portent des noms "
        "differents selon les sources, mais la progression est partout la "
        "meme : rien, hors champ, a l'ecran, explicite."),
    "MOTS_ATTENDUS": (
        "Guides de longueur par genre consultes le 15/09/2026 (Publishing "
        "Xpress, WordTally, Authorlytica, Kevin Anderson & Associates), "
        "puis verifies une seconde fois le meme jour contre un guide "
        "d'attentes d'agents. Fourchettes les plus LARGES rapportees : "
        "les sources s'accordent a quelques milliers de mots pres, sauf "
        "sur la fantasy epique ou elles vont de 100 000 a 200 000."),
    "STRUCTURES": (
        "Relevees le 15/09/2026. Charpentes nommees et publiees : « Save the "
        "Cat » (quinze beats) et "
        "les beats de romance, qui suivent l'arc de la RELATION et non celui "
        "de l'intrigue exterieure."),
    "POINTS_DE_VUE": ("Vocabulaire de narratologie : pas une donnee de "
                      "marche, donc rien a relever ni a dater."),
    "TEMPS": ("Vocabulaire de narratologie : pas une donnee de marche, "
              "donc rien a relever ni a dater."),
}

# Les categories de premier niveau de la fiction chez Amazon, telles qu'elles
# s'appellent. Ce sont elles qui decident du rayon — donc de qui trouve le
# livre.
CATEGORIES: Tuple[str, ...] = (
    "Literature & Fiction",
    "Mystery, Thriller & Suspense",
    "Romance",
    "Science Fiction & Fantasy",
    "Horror",
    "Teen & Young Adult",
    "Children's eBooks",
    "LGBTQ+",
    "Religious & Inspirational Fiction",
)

# Categorie -> sous-genres NOMMES PAR UNE SOURCE. La liste est courte, et
# c'est voulu : Amazon en compte des milliers et n'en publie aucune liste
# complete. Un sous-genre absent d'ici reste saisissable — ces listes
# proposent, elles n'interdisent pas.
GENRES: Dict[str, Tuple[str, ...]] = {
    "romance": ("contemporary romance", "historical romance",
                "paranormal romance", "romantic suspense", "dark romance",
                "fantasy romance", "sports romance", "military romance",
                "clean & wholesome romance", "reverse harem",
                "small town & rural romance", "regency romance"),
    "policier": ("cozy mystery", "thriller", "espionage", "suspense",
                 "police procedural", "hard-boiled"),
    "imaginaire": ("epic fantasy", "urban fantasy", "science fiction",
                   "dystopian", "space opera", "steampunk"),
    "horreur": ("psychological horror", "gothic", "supernatural",
                "occult horror"),
    "litterature": ("literary fiction", "historical fiction",
                    "family saga", "coming of age"),
    "jeunesse": ("picture books", "early readers", "chapter books",
                 "middle grade", "young adult"),
}

# Ce que le lecteur vient retrouver, et par quoi il CHERCHE. Un lecteur de
# romance ne tape pas « contemporary romance », il tape « enemies to
# lovers ». Les noms sont donnes dans la langue ou ils circulent : c'est
# ainsi qu'ils sont cherches, y compris par les lecteurs francophones.
TROPES: Dict[str, Tuple[str, ...]] = {
    "romance": ("enemies to lovers", "forced proximity", "slow burn",
                "fake dating", "grumpy x sunshine", "friends to lovers",
                "second chance", "only one bed"),
}
# Les autres genres n'ont PAS de liste ici, et leur absence est une donnee :
# aucune source consultee ne recense leurs tropes avec la meme regularite
# que ceux de la romance. Inventer la liste manquante serait retomber dans
# le defaut que ce bloc corrige. « tropes_du_genre » rend donc « » pour eux,
# et l'invite n'en propose aucun plutot que d'en proposer de faux.

# Ce que le lecteur vient RESSENTIR. Aucune source ne publie de liste
# d'ambiances : celle-ci est un vocabulaire de travail, pas un releve, et
# elle est marquee comme telle.
AMBIANCES: Tuple[str, ...] = (
    "reconfortante", "tendue", "melancolique", "lumineuse", "sombre",
    "drole", "inquietante", "epique", "intime", "amere",
)
SOURCES["AMBIANCES"] = (
    "SANS SOURCE. Vocabulaire de travail pour decrire un ressenti, pas un "
    "releve de marche. Il sert a poser une consigne au modele ; il ne "
    "pretend pas nommer un rayon.")

POINTS_DE_VUE: Tuple[str, ...] = (
    "premiere personne", "troisieme personne limitee",
    "troisieme personne omnisciente", "points de vue alternes",
)
TEMPS: Tuple[str, ...] = ("passe", "present")

CHALEUR: Tuple[str, ...] = (
    "sans romance",          # le livre n'en contient pas
    "tendre",                # sentiments, baisers, rien de plus
    "porte fermee",          # l'intimite est impliquee, jamais montree
    "sensuelle",             # scenes a l'ecran, sans crudite
    "explicite",             # scenes detaillees, vocabulaire direct
)

FINS: Tuple[str, ...] = (
    "heureuse",              # HEA : le couple finit ensemble, pour de bon
    "heureuse pour l'instant",   # HFN
    "douce-amere", "ouverte", "tragique",
)
SOURCES["FINS"] = SOURCES["FINS_EXIGEES_EN_ROMANCE"]
SOURCES["GENRES"] = SOURCES["SOUS_GENRES"]
SOURCES["CLES"] = ("Derivee de « _ETIQUETTES » : les cles de reglage "
                   "d'un produit, pas une donnee de marche.")
FINS_EXIGEES_EN_ROMANCE = ("heureuse", "heureuse pour l'instant")

STRUCTURES: Tuple[str, ...] = (
    "trois actes", "beats de romance", "save the cat", "enquete",
    "voyage du heros", "recit choral", "episodique",
)

# Ce qu'on LIT en face de chaque valeur. Les valeurs restent les cles des
# invites et de la ligne de commande, sans accent ; le tableau de bord les
# affichait telles quelles — « melancolique », « voyage du heros »,
# « troisieme personne limitee » — dans les listes d'un produit vendu en
# francais. Un test exige une etiquette pour chaque valeur proposee.
AFFICHAGE: Dict[str, str] = {
    "reconfortante": "Réconfortante", "tendue": "Tendue",
    "melancolique": "Mélancolique", "lumineuse": "Lumineuse",
    "sombre": "Sombre", "drole": "Drôle", "inquietante": "Inquiétante",
    "epique": "Épique", "intime": "Intime", "amere": "Amère",
    "premiere personne": "Première personne",
    "troisieme personne limitee": "Troisième personne limitée",
    "troisieme personne omnisciente": "Troisième personne omnisciente",
    "points de vue alternes": "Points de vue alternés",
    "passe": "Passé", "present": "Présent",
    "sans romance": "Sans romance", "tendre": "Tendre",
    "porte fermee": "Porte fermée", "sensuelle": "Sensuelle",
    "explicite": "Explicite",
    "heureuse": "Heureuse", "heureuse pour l'instant": "Heureuse pour l'instant",
    "douce-amere": "Douce-amère", "ouverte": "Ouverte", "tragique": "Tragique",
    "trois actes": "Trois actes", "beats de romance": "Beats de romance",
    "save the cat": "Save the Cat", "enquete": "Enquête",
    "voyage du heros": "Voyage du héros", "recit choral": "Récit choral",
    "episodique": "Épisodique",
    "horreur": "Horreur", "imaginaire": "Imaginaire", "jeunesse": "Jeunesse",
    "litterature": "Littérature", "policier": "Policier", "romance": "Romance",
}

SOURCES["AFFICHAGE"] = ("SANS SOURCE. Les memes valeurs que les listes "
                        "ci-dessus, accentuees pour l'ecran : une "
                        "transcription, pas un releve.")


def etiquettes(valeurs) -> Tuple[Tuple[str, str], ...]:
    """Les paires (valeur, ce qu'on lit) d'une liste de reglage."""
    return tuple((v, AFFICHAGE[v]) for v in valeurs if v in AFFICHAGE)


# Longueurs attendues par le marche, EN MOTS. La mesure sert a SITUER un
# manuscrit, pas a le recaler.
MOTS_ATTENDUS: Dict[str, Tuple[int, int]] = {
    "contemporary romance": (50000, 90000),
    "historical romance": (70000, 100000),
    "paranormal romance": (60000, 100000),
    "romantic suspense": (80000, 100000),
    "dark romance": (60000, 100000),
    "fantasy romance": (90000, 150000),
    "sports romance": (50000, 90000),
    "clean & wholesome romance": (50000, 80000),
    "cozy mystery": (60000, 85000),
    "thriller": (70000, 100000),
    "espionage": (80000, 120000),
    "suspense": (70000, 90000),
    "police procedural": (80000, 100000),
    "hard-boiled": (70000, 90000),
    "epic fantasy": (100000, 200000),
    "urban fantasy": (70000, 100000),
    "science fiction": (80000, 120000),
    "dystopian": (70000, 100000),
    "chapter books": (10000, 20000),
    "middle grade": (25000, 50000),
    "young adult": (50000, 80000),
    "early readers": (1000, 5000),
    "picture books": (100, 800),
}


# Le nom FRANCAIS de chaque sous-genre et de chaque trope, en regard du terme
# source qu'il traduit.
#
# Les deux sont necessaires, et pour des raisons differentes.
#
# Le terme source est celui sous lequel une plateforme range le livre. C'est
# lui qui porte les longueurs attendues de « MOTS_ATTENDUS », et le remplacer
# ferait perdre la tracabilite du releve : « 50 000 a 90 000 mots » a ete
# relevee pour « contemporary romance », pas pour une traduction qu'on en
# aurait faite.
#
# Le nom francais est celui que l'utilisateur LIT. Tout est en francais dans
# ce depot, y compris ce qui s'affiche — et une liste de suggestions en
# anglais dans un tableau de bord francais est exactement ce qu'un
# utilisateur signale comme « bizarre ». C'est arrive le 15/09/2026 : le
# panneau d'un livre-jeu d'horreur proposait « chapter books, clean &
# wholesome romance, coming of age, cozy mystery, dark romance, dystopian,
# early readers... ».
#
# Quelques termes restent tels quels parce que le marche francophone les
# emploie tels quels : « dark romance », « slow burn », « young adult »,
# « space opera », « steampunk », « thriller ». Les traduire inventerait un
# vocabulaire que personne ne tape dans une barre de recherche.
EN_FRANCAIS: Dict[str, str] = {
    # Romance
    "contemporary romance": "romance contemporaine",
    "historical romance": "romance historique",
    "paranormal romance": "romance paranormale",
    "romantic suspense": "suspense romantique",
    "dark romance": "dark romance",
    "fantasy romance": "romance fantasy",
    "sports romance": "romance sportive",
    "military romance": "romance militaire",
    "clean & wholesome romance": "romance sans scène explicite",
    "reverse harem": "reverse harem",
    "small town & rural romance": "romance en petite ville",
    "regency romance": "romance Régence",
    # Policier
    "cozy mystery": "cosy mystery",
    "thriller": "thriller",
    "espionage": "espionnage",
    "suspense": "suspense",
    "police procedural": "procédure policière",
    "hard-boiled": "polar noir",
    # Imaginaire
    "epic fantasy": "fantasy épique",
    "urban fantasy": "fantasy urbaine",
    "science fiction": "science-fiction",
    "dystopian": "dystopie",
    "space opera": "space opera",
    "steampunk": "steampunk",
    # Horreur
    "psychological horror": "horreur psychologique",
    "gothic": "gothique",
    "supernatural": "surnaturel",
    "occult horror": "horreur occulte",
    # Litterature
    "literary fiction": "littérature générale",
    "historical fiction": "roman historique",
    "family saga": "saga familiale",
    "coming of age": "récit d'apprentissage",
    # Jeunesse
    "picture books": "album illustré",
    "early readers": "premières lectures",
    "chapter books": "premiers romans",
    "middle grade": "roman junior",
    "young adult": "young adult",
    # Tropes
    "enemies to lovers": "ennemis puis amants",
    "forced proximity": "huis clos forcé",
    "slow burn": "slow burn",
    "fake dating": "faux couple",
    "grumpy x sunshine": "grognon et rayon de soleil",
    "friends to lovers": "amis puis amants",
    "second chance": "seconde chance",
    "only one bed": "un seul lit",
}

# Les libelles portent leurs accents (« fantasy épique ») ; ce qu'on tape au
# clavier d'un telephone, souvent pas. Les deux doivent retrouver le meme
# terme source, sinon le reglage est choisi, affiche, et sans effet.
_VERS_SOURCE = {_sans_accent(fr).lower(): en for en, fr in EN_FRANCAIS.items()}


def libelle(terme: str) -> str:
    """Le nom francais d'un sous-genre ou d'un trope. Le terme tel quel sinon.

    « Tel quel sinon » n'est pas un repli paresseux : ces listes PROPOSENT,
    elles n'interdisent pas. Un utilisateur qui saisit un sous-genre absent
    de la table doit le voir ressortir intact, pas efface.
    """
    return EN_FRANCAIS.get((terme or "").strip().lower(), terme)


def terme_source(terme: str) -> str:
    """Le terme source d'un libelle francais, pour retrouver un releve.

    « MOTS_ATTENDUS » et « GENRES » sont indexes par le terme source. Sans ce
    retour, choisir « romance contemporaine » dans le tableau de bord ne
    trouverait aucune longueur attendue — le reglage serait affiche, choisi,
    et sans effet.
    """
    nu = (terme or "").strip().lower()
    return _VERS_SOURCE.get(_sans_accent(nu), nu)


def genre_du_sous_genre(sous_genre: str) -> str:
    """A quel genre ce sous-genre appartient-il ? Vide si on ne sait pas.

    Rend « » plutot que de deviner : c'est ce qui permet a un sous-genre
    saisi a la main de ne declencher AUCUN controle de convention, au lieu
    d'en declencher un tire au sort. Un garde-fou qui signale a tort finit
    ignore.
    """
    cible = (sous_genre or "").strip().lower()
    for genre, sous in GENRES.items():
        if cible in (s.lower() for s in sous):
            return genre
        if cible == genre:
            return genre
    return ""


def tropes_du_genre(genre: str) -> Tuple[str, ...]:
    """Les tropes d'un genre, en francais — c'est ce que l'utilisateur lit."""
    return tuple(libelle(t)
                 for t in TROPES.get((genre or "").strip().lower(), ()))


def mots_attendus(sous_genre: str) -> Tuple[int, int]:
    """La fourchette du marche, ou (0, 0) quand elle n'est pas connue.

    Accepte le libelle francais comme le terme source : le tableau de bord
    propose « romance contemporaine », et le releve est range sous
    « contemporary romance ».
    """
    return MOTS_ATTENDUS.get(terme_source(sous_genre), (0, 0))


def situer_la_longueur(mots: int, sous_genre: str) -> str:
    """Compare une longueur produite a ce que le marche attend.

    Rend une MESURE, pas un verdict : « 27 000 mots, le marche en attend
    50 000 a 90 000 ». C'est a l'auteur de decider si son format court est
    un choix ou un accident — l'usine n'a pas de quoi trancher, et un
    « trop court » affirme sur une fourchette recopiee serait un verdict non
    mesure.
    """
    bas, haut = mots_attendus(sous_genre)
    if not bas or not mots:
        return ""
    if bas <= mots <= haut:
        return ("{} mots : dans la fourchette attendue pour « {} » "
                "({} a {}).".format(mots, sous_genre, bas, haut))
    cote = "en dessous de" if mots < bas else "au-dessus de"
    return ("{} mots, {} la fourchette attendue pour « {} » ({} a {}). "
            "Un format court se vend, mais il se vend a un autre prix et a "
            "un autre lecteur.".format(mots, cote, sous_genre, bas, haut))


def promesse(options: Dict[str, Any]) -> Dict[str, str]:
    """La promesse de lecture, extraite des reglages du produit.

    Un seul endroit qui sait lire ces cles. Les chaines de fiction en
    demandent toutes le meme bloc, et six chaines qui le reconstruisent
    chacune a sa facon finissent par en oublier une — c'est ce qui est
    arrive aux en-tetes d'appel des fournisseurs.
    """
    lire = lambda cle: str(options.get(cle) or "").strip()  # noqa: E731
    sous_genre = lire("sous_genre")
    return {
        "genre": lire("genre") or genre_du_sous_genre(sous_genre),
        "sous_genre": sous_genre,
        "tropes": lire("tropes"),
        "ambiance": lire("ambiance"),
        "point_de_vue": lire("point_de_vue"),
        "temps": lire("temps"),
        "chaleur": lire("chaleur"),
        "fin": lire("fin"),
        "structure": lire("structure"),
    }


_ETIQUETTES = (
    ("sous_genre", "SOUS-GENRE"), ("genre", "GENRE"), ("tropes", "TROPES"),
    ("ambiance", "AMBIANCE"), ("point_de_vue", "POINT DE VUE"),
    ("temps", "TEMPS DU RECIT"), ("chaleur", "NIVEAU DE CHALEUR"),
    ("fin", "FIN ATTENDUE"), ("structure", "CHARPENTE"),
)


def promesse_pour_ia(options: Dict[str, Any]) -> str:
    """Le bloc de consignes a injecter dans les invites de fiction.

    Rend « » quand rien n'est regle : une invite qui enumere neuf champs
    vides apprend au modele que ces champs ne comptent pas.
    """
    valeurs = promesse(options)
    lignes = ["{} : {}".format(etiquette, valeurs[cle])
              for cle, etiquette in _ETIQUETTES if valeurs.get(cle)]
    if not lignes:
        return ""
    consignes = ["\n".join(lignes)]
    if valeurs["chaleur"]:
        consignes.append(_CONSIGNES_CHALEUR.get(valeurs["chaleur"], ""))
    if valeurs["fin"]:
        consignes.append(
            "La fin doit etre « {} », et le lecteur de ce sous-genre "
            "l'attend : elle n'est pas negociable.".format(valeurs["fin"]))
    if valeurs["genre"] and not valeurs["tropes"]:
        # Le cas le plus courant : l'utilisateur a choisi un sous-genre et
        # rien d'autre. Sans cette ligne, le modele invente des tropes hors
        # de ceux que le lecteur du genre vient chercher — et c'est par le
        # trope qu'on cherche un livre, pas par le sous-genre.
        connus = tropes_du_genre(valeurs["genre"])
        if connus:
            consignes.append(
                "Aucun trope impose. Ceux que le lecteur de ce genre vient "
                "retrouver : {}. Choisis-en deux ou trois et tiens-les."
                .format(", ".join(connus)))
    if valeurs["point_de_vue"] or valeurs["temps"]:
        consignes.append(
            "Tiens le point de vue et le temps d'un bout a l'autre. En "
            "changer sans raison est la maladresse la plus visible du "
            "genre.")
    return "\n\n" + "\n".join(c for c in consignes if c) + "\n"


_CONSIGNES_CHALEUR = {
    "sans romance":
        "Aucune intrigue amoureuse : ce livre ne l'a pas promise.",
    "tendre":
        "Sentiments et baisers, rien de plus. Pas de scene d'intimite.",
    "porte fermee":
        "L'intimite est impliquee puis la scene se ferme. Rien a l'ecran.",
    "sensuelle":
        "Les scenes d'intimite ont lieu a l'ecran, sans vocabulaire cru.",
    "explicite":
        "Les scenes d'intimite sont detaillees. Tous les personnages "
        "concernes sont des adultes, et leur consentement est explicite "
        "dans le texte.",
}


def types_de_fiction() -> Tuple[str, ...]:
    """Les cles du catalogue qui relevent de la fiction.

    Lues dans le catalogue, jamais recopiees : une liste en double ici
    oublierait le prochain type ajoute, et l'oubli ne se verrait qu'a
    l'usage — un roman a qui l'on demande « quel probleme resous-tu ».
    """
    from . import catalogue

    return tuple(f.cle for f in catalogue.TYPES if f.famille == "fiction")


def est_fiction(cle: str) -> bool:
    return (cle or "") in types_de_fiction()


def _catalogue_de_fiction() -> str:
    from . import catalogue

    return "\n".join(
        "- {} : {}".format(f.cle, f.resume)
        for f in catalogue.TYPES if f.famille == "fiction")


def explorer_promesses(ctx: Any, nombre: int = 8,
                       connus: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Cherche des PROMESSES DE LECTURE, la ou l'usine cherche des niches.

    La difference n'est pas cosmetique. La prospection de niches demande au
    modele un probleme, un acheteur, une promesse de resultat, une
    concurrence et un canal d'acquisition. Pour un roman, ces cinq questions
    n'ont pas de reponse honnete — et un modele a qui l'on pose une question
    sans reponse en fabrique une. On obtenait donc des fictions habillees en
    produits pratiques : « ce thriller resout le probleme du manque de
    suspense dans votre vie ».

    Ici on demande ce qui decide vraiment de l'achat d'une fiction : ou elle
    se range, ce que le lecteur vient y retrouver, ce qu'il vient ressentir,
    et ce qu'il ne pardonnera pas qu'on lui refuse.
    """
    from ..agents import equipe

    evite = ""
    if connus:
        evite = ("\n\nDEJA FABRIQUE OU DEJA EN FILE — ne propose rien qui "
                 "recouvre l'un de ces titres, ni une simple "
                 "reformulation :\n"
                 + "\n".join("- " + t for t in connus) + "\n")
    depart = ("\nPOINT DE DEPART : {}\n".format(ctx.sujet)
              if getattr(ctx, "sujet", "") else
              "\nAucun point de depart impose : choisis toi-meme, et varie "
              "les genres entre tes propositions.\n")
    invite = (
        "Tu cherches des PROMESSES DE LECTURE pour des fictions a ecrire.\n"
        "Ce n'est pas une recherche de niche : un lecteur de fiction "
        "n'achete pas la solution d'un probleme, il achete une experience "
        "qu'il veut revivre.\n"
        "{depart}{evite}\n"
        "Propose {n} promesses. Pour chacune :\n"
        "- un TITRE qui nomme son trope, parce que c'est par la qu'on "
        "cherche un livre ;\n"
        "- un SOUS-GENRE precis, pas un genre large ;\n"
        "- deux ou trois TROPES que le lecteur vient retrouver ;\n"
        "- l'AMBIANCE, ce qu'il vient ressentir ;\n"
        "- la FIN que ce sous-genre lui promet ;\n"
        "- un PITCH de deux phrases, au present, sans nom d'auteur.\n\n"
        "Le type doit etre l'un de ceux que l'usine sait fabriquer :\n"
        "{types}\n\n"
        "Sous-genres connus (tu peux en proposer d'autres) :\n{sous}\n"
        "Niveaux de chaleur : {chaleur}\nFins : {fins}\n"
        "Points de vue : {pdv}\n\n"
        "Schema JSON exact :\n"
        '{{"promesses": [{{"titre": "...", "type": "{cles}", '
        '"genre": "...", "sous_genre": "...", "tropes": "trope 1, trope 2", '
        '"ambiance": "...", "point_de_vue": "...", "temps": "passe|present", '
        '"chaleur": "...", "fin": "...", "structure": "...", '
        '"pitch": "...", "lecteur": "qui lit ca, et ce qu\'il a lu avant"}}]}}'
    ).format(
        depart=depart, evite=evite, n=nombre, types=_catalogue_de_fiction(),
        sous=", ".join(sorted(MOTS_ATTENDUS)),
        chaleur=" | ".join(CHALEUR), fins=" | ".join(FINS),
        pdv=" | ".join(POINTS_DE_VUE),
        cles="|".join(types_de_fiction()) or "nouvelle")

    donnees = equipe.PROSPECTEUR.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.9, max_tokens=4096,
        # Meme raison que pour les niches : une exploration mise en cache
        # rendrait a jamais la premiere reponse obtenue.
        cache=False)
    brut = donnees.get("promesses") if isinstance(donnees, dict) else donnees
    return [p for p in (_nettoyer_promesse(x) for x in (brut or [])) if p]


def _nettoyer_promesse(brut: Any) -> Dict[str, Any]:
    """Ramene une proposition du modele vers du vocabulaire connu.

    Ce qui n'est pas reconnu est GARDE tel quel, pas jete : le marche
    invente des sous-genres plus vite qu'on ne met a jour une liste, et
    « romantasy » n'existait pas quand ces listes ont commence.
    """
    from . import catalogue
    from .base import nettoyer_titre

    if not isinstance(brut, dict) or not brut.get("titre"):
        return {}
    type_produit = catalogue.normaliser(str(brut.get("type") or ""))
    if not est_fiction(type_produit):
        # Le modele a propose un type pratique pour une promesse de lecture.
        # Le forcer vers la fiction plutot que de jeter la proposition : ce
        # qu'il a trouve reste bon, c'est l'etiquette qui a glisse.
        type_produit = "nouvelle"
    sous_genre = str(brut.get("sous_genre") or "").strip()
    return {
        "titre": nettoyer_titre(str(brut["titre"])),
        "type": type_produit,
        "genre": (str(brut.get("genre") or "").strip()
                  or genre_du_sous_genre(sous_genre)),
        "sous_genre": sous_genre,
        "tropes": str(brut.get("tropes") or "").strip(),
        "ambiance": str(brut.get("ambiance") or "").strip(),
        "point_de_vue": str(brut.get("point_de_vue") or "").strip(),
        "temps": str(brut.get("temps") or "").strip(),
        "chaleur": str(brut.get("chaleur") or "").strip(),
        "fin": str(brut.get("fin") or "").strip(),
        "structure": str(brut.get("structure") or "").strip(),
        "pitch": str(brut.get("pitch") or "").strip(),
        "lecteur": str(brut.get("lecteur") or "").strip(),
    }


def contrat_de_genre(promesse_lue: Dict[str, str]) -> List[str]:
    """Ce que le sous-genre promet et que le reglage contredit.

    Controle DETERMINISTE, zero appel de modele. Il ne juge pas le texte —
    il compare deux reglages entre eux, ce qui est verifiable sans lire une
    ligne du livre.

    Il se tait des qu'il n'est pas sur : un sous-genre inconnu ne declenche
    rien du tout. Un controle qui signale a tort finit ignore, ce qui est
    pire que se taire.
    """
    alertes: List[str] = []
    genre = (promesse_lue.get("genre") or "").lower()
    fin = (promesse_lue.get("fin") or "").lower()
    chaleur = (promesse_lue.get("chaleur") or "").lower()
    if genre == "romance" and fin and fin not in FINS_EXIGEES_EN_ROMANCE:
        alertes.append(
            "Une romance qui finit « {} » rompt le contrat du genre : le "
            "lecteur de romance achete la fin heureuse, et son absence est "
            "le premier motif de retour.".format(fin))
    if genre == "romance" and chaleur == "sans romance":
        alertes.append(
            "« sans romance » dans un genre romance : l'un des deux "
            "reglages est faux.")
    if genre == "jeunesse" and chaleur in ("sensuelle", "explicite"):
        alertes.append(
            "Chaleur « {} » sur un livre jeunesse : a verifier avant "
            "publication.".format(chaleur))
    return alertes


CLES = tuple(cle for cle, _ in _ETIQUETTES)


def poser_la_promesse(ctx: Any, source: Any) -> Dict[str, str]:
    """Range la promesse de lecture dans le contexte, quelle qu'en soit la voie.

    Deux chemins arrivent a la fabrication, et ils ne portent pas les
    reglages de la meme facon : la ligne de commande les pose sur un
    « Namespace », la file de production dans un dictionnaire d'options. Les
    reglages de fiction ne passent par AUCUN des deux mecanismes existants —
    « executer » ne transmet en argument que les cles declarees dans
    « options », et y declarer neuf champs obligerait chaque chaine de
    fiction a les accepter un par un.

    D'ou un seul point de depot, « ctx.meta["fiction"] », et un seul
    lecteur : « promesse_du_contexte ». Un champ ajoute a
    « champs_de_fiction » arrive ainsi dans les invites sans qu'on touche a
    une seule chaine — c'est la difference entre un reglage et un reglage
    orphelin.
    """
    lire = (source.get if isinstance(source, dict)
            else lambda cle: getattr(source, cle, ""))
    valeurs = {cle: str(lire(cle) or "").strip() for cle in CLES}
    if not valeurs.get("genre"):
        valeurs["genre"] = genre_du_sous_genre(valeurs.get("sous_genre", ""))
    ctx.meta["fiction"] = valeurs
    return valeurs


def promesse_du_contexte(ctx: Any) -> Dict[str, str]:
    return dict(getattr(ctx, "meta", {}).get("fiction") or {})


def consignes(ctx: Any) -> str:
    """Le bloc de consignes de fiction pour ce produit, ou « »."""
    return promesse_pour_ia(promesse_du_contexte(ctx))


def consignes_de_scene(ctx: Any) -> str:
    """Les seules consignes de fiction qui gouvernent l'ECRITURE d'une scene.

    Le bloc complet dit ou le livre se range ; il a sa place une fois, dans
    la bible. Le repeter a chaque scene couterait son volume multiplie par
    trente sans rien ajouter — et c'est le genre de depense qui ne se voit
    que sur la facture.

    Ce qui doit revenir a chaque scene, en revanche, ce sont les trois
    reglages qui se perdent phrase apres phrase : le temps du recit, le
    point de vue, et la chaleur. Un modele qui tient le passe simple pendant
    huit scenes glisse au present a la neuvieme, et rien ne le rattrape.
    """
    valeurs = promesse_du_contexte(ctx)
    lignes = []
    if valeurs.get("temps"):
        lignes.append("TEMPS DU RECIT : {} — d'un bout a l'autre, sans "
                      "glisser.".format(valeurs["temps"]))
    if valeurs.get("point_de_vue"):
        lignes.append("POINT DE VUE IMPOSE : {}.".format(
            valeurs["point_de_vue"]))
    if valeurs.get("chaleur"):
        consigne = _CONSIGNES_CHALEUR.get(valeurs["chaleur"], "")
        if consigne:
            lignes.append("CHALEUR : " + consigne)
    if valeurs.get("ambiance"):
        lignes.append("AMBIANCE a tenir : {}.".format(valeurs["ambiance"]))
    return ("\n".join(lignes) + "\n") if lignes else ""
