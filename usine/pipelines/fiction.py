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

# Genre -> sous-genres. Le sous-genre est ce qui decide de tout le reste :
# longueur attendue, chaleur, fin admissible. « Romance » seul ne suffit pas
# a ecrire une romance.
GENRES: Dict[str, Tuple[str, ...]] = {
    "romance": ("romance contemporaine", "romantasy", "dark romance",
                "romance sportive", "romance historique",
                "suspense romantique", "comedie romantique"),
    "policier": ("cozy mystery", "polar urbain", "thriller psychologique",
                 "roman noir", "procedural", "thriller d'espionnage"),
    "imaginaire": ("fantasy epique", "fantasy urbaine", "science-fiction",
                   "anticipation", "post-apocalyptique", "steampunk"),
    "fantastique": ("horreur psychologique", "fantastique gothique",
                    "surnaturel contemporain", "conte noir"),
    "litterature": ("recit intimiste", "saga familiale", "roman historique",
                    "autofiction", "recit choral"),
    "jeunesse": ("album illustre", "premiere lecture", "roman junior",
                 "roman ado", "conte moderne"),
    "aventure": ("survie", "exploration", "recit maritime", "western"),
}

# Ce que le lecteur vient retrouver. C'est par la qu'il cherche : un lecteur
# de romance ne tape pas « romance contemporaine », il tape « ennemis puis
# amants ». Un titre qui ne nomme pas son trope ne se trouve pas.
TROPES: Dict[str, Tuple[str, ...]] = {
    "romance": ("ennemis puis amants", "amis d'enfance retrouves",
                "mariage arrange", "une seule chambre", "seconde chance",
                "amour interdit", "faux couple", "proximite forcee",
                "celui qui protege", "retour au village"),
    "policier": ("huis clos", "enquete au village", "flic brise",
                 "temoin peu fiable", "crime parfait", "double vie",
                 "vieille affaire rouverte", "tueur qui nargue",
                 "duo mal assorti", "la victime cachait quelque chose"),
    "imaginaire": ("elu malgre lui", "magie a prix", "empire qui s'effondre",
                   "monde mourant", "compagnonnage", "quete d'objet",
                   "IA devenue consciente", "colonie coupee de la Terre",
                   "prophetie mal comprise", "academie de magie"),
    "fantastique": ("maison qui se souvient", "pacte", "double",
                    "village qui cache", "objet maudit", "boucle temporelle",
                    "revenant", "folie ou surnaturel"),
    "litterature": ("secret de famille", "retour au pays", "deuil",
                    "transmission", "trahison ancienne", "lettre retrouvee",
                    "trois generations", "ce qu'on n'a jamais dit"),
    "jeunesse": ("amitie improbable", "premier grand depart", "animal guide",
                 "peur surmontee", "difference assumee", "objet magique",
                 "secret partage", "grandir d'un cran"),
    "aventure": ("expedition qui tourne mal", "carte incomplete",
                 "traitre dans l'equipe", "nature hostile", "chasse a l'homme",
                 "dernier survivant"),
}

# Ce que le lecteur vient RESSENTIR. Deux livres du meme sous-genre et des
# memes tropes ne se vendent pas au meme lecteur si l'ambiance differe.
AMBIANCES: Tuple[str, ...] = (
    "reconfortante", "tendue", "melancolique", "lumineuse", "sombre",
    "drole", "inquietante", "epique", "intime", "amere",
)

# Le point de vue et le temps ne sont PAS des details de style : ce sont des
# conventions de sous-genre. La romance contemporaine se lit massivement a
# la premiere personne au present ; le polar a la troisieme au passe. Se
# tromper se lit comme une maladresse d'amateur des la premiere page.
POINTS_DE_VUE: Tuple[str, ...] = (
    "premiere personne", "troisieme personne limitee",
    "troisieme personne omnisciente", "points de vue alternes",
)
TEMPS: Tuple[str, ...] = ("passe", "present")

# Echelle de chaleur. Releve du 15/09/2026 : les paliers portent des noms
# differents selon les sources, mais la progression est partout la meme —
# rien, hors champ, a l'ecran, explicite. C'est une attente de lecteur, pas
# un curseur de gout : promettre l'un et livrer l'autre fache dans les DEUX
# sens.
CHALEUR: Tuple[str, ...] = (
    "sans romance",          # le livre n'en contient pas
    "tendre",                # sentiments, baisers, rien de plus
    "porte fermee",          # l'intimite est impliquee, jamais montree
    "sensuelle",             # scenes a l'ecran, sans crudite
    "explicite",             # scenes detaillees, vocabulaire direct
)

# La fin est une PROMESSE, pas un choix d'auteur. En romance, une fin
# malheureuse est un manquement au contrat de genre — le livre est rendu.
# Ailleurs elle est libre. D'ou cette liste, et le controle qui verifie
# qu'une romance n'en sort pas.
FINS: Tuple[str, ...] = (
    "heureuse",              # le couple finit ensemble, pour de bon
    "heureuse pour l'instant",
    "douce-amere", "ouverte", "tragique",
)
FINS_EXIGEES_EN_ROMANCE = ("heureuse", "heureuse pour l'instant")

# Comment l'histoire est charpentee. « Les beats de romance » suivent l'arc
# de la RELATION, pas celui de l'intrigue exterieure : dans une romance, la
# relation est la charpente, et la traiter en second plan se voit.
STRUCTURES: Tuple[str, ...] = (
    "trois actes", "beats de romance", "enquete", "voyage du heros",
    "recit choral", "episodique",
)

# Longueurs attendues par le marche, EN MOTS. Sources : guides de longueur
# par genre consultes le 15/09/2026 (Publishing Xpress, WordTally,
# Authorlytica, Kevin Anderson & Associates), qui s'accordent a quelques
# milliers de mots pres. Les fourchettes retenues sont les plus larges
# rapportees : la mesure sert a SITUER un manuscrit, pas a le recaler.
#
# Ce chiffre ne pilote rien tout seul. Il sert a dire « ce que vous
# fabriquez fait 27 000 mots, le marche en attend 50 000 a 90 000 pour ce
# sous-genre » — une mesure, et un humain qui tranche.
MOTS_ATTENDUS: Dict[str, Tuple[int, int]] = {
    "romance contemporaine": (50000, 90000),
    "comedie romantique": (50000, 80000),
    "romance historique": (70000, 100000),
    "romance sportive": (50000, 90000),
    "dark romance": (60000, 100000),
    "romantasy": (90000, 150000),
    "suspense romantique": (80000, 100000),
    "cozy mystery": (60000, 85000),
    "polar urbain": (70000, 90000),
    "thriller psychologique": (70000, 100000),
    "roman noir": (70000, 90000),
    "procedural": (80000, 100000),
    "thriller d'espionnage": (80000, 120000),
    "fantasy epique": (100000, 150000),
    "fantasy urbaine": (70000, 100000),
    "science-fiction": (80000, 120000),
    "anticipation": (70000, 100000),
    "roman junior": (20000, 40000),
    "roman ado": (50000, 80000),
    "premiere lecture": (1000, 5000),
    "album illustre": (500, 1500),
}


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
    return TROPES.get((genre or "").strip().lower(), ())


def mots_attendus(sous_genre: str) -> Tuple[int, int]:
    """La fourchette du marche, ou (0, 0) quand elle n'est pas connue."""
    return MOTS_ATTENDUS.get((sous_genre or "").strip().lower(), (0, 0))


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
