"""Catalogue des types de produits : la source unique de verite.

Jusqu'ici, la liste des types etait recopiee dans sept fichiers — la CLI, le
moteur continu, le serveur web, son gabarit HTML, le menu, et l'explorateur de
niches. Deux d'entre eux avaient deja diverge, avec une consequence concrete :
l'etude de niche ne pouvait pas proposer « impression » ni « modeles », les
deux types les plus vendus, parce qu'ils manquaient a sa liste locale. Les
idees correspondantes etaient silencieusement converties en ebooks.

Tout se declare desormais ici, une fois. Ajouter un type de produit consiste a
ecrire sa chaine de fabrication et a l'inscrire dans ce catalogue ; les six
autres endroits se mettent a jour seuls.

« Vrai type de produit » signifie : une chaine de fabrication qui lui est
propre, pas une etiquette dans une liste. Un type qui produirait le meme
fichier qu'un autre avec un nom different n'a pas sa place ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


def reseaux_sociaux() -> Tuple[str, ...]:
    """Les reseaux que la chaine « social » sait vraiment viser.

    Lus la ou ils sont declares. Les recopier ici en ferait deux listes, et
    c'est celle du formulaire qui proposerait un reseau retire.
    """
    from .social import RESEAUX

    return tuple(sorted(RESEAUX))


def objectifs_email() -> Tuple[str, ...]:
    """Ce qu'une sequence e-mail cherche a obtenir.

    Lus la ou ils sont declares : les recopier ici en ferait deux listes, et
    c'est celle du formulaire qui proposerait un objectif retire.
    """
    from .emails import OBJECTIFS

    return tuple(OBJECTIFS)


def niveaux_quiz() -> Tuple[str, ...]:
    """Les trois niveaux qu'un quiz sait viser."""
    from .quiz import NIVEAUX

    return tuple(NIVEAUX)


def cibles_logiciel() -> Tuple[str, ...]:
    """Ce qu'un produit logiciel peut etre : outil, page web, extension."""
    from .logiciel import CIBLES

    return tuple(sorted(CIBLES))


def nouvelle_scenes() -> int:
    """Le nombre de scenes d'un roman, lu la ou il est decide.

    Le recopier ici en ferait deux chiffres qui divergent — et celui du menu
    finirait par promettre une longueur que la chaine ne fabrique pas.
    """
    from .nouvelle import ROMAN_SCENES

    return ROMAN_SCENES


def recueil_recits() -> int:
    """Le nombre de nouvelles d'un recueil, lu la ou il est decide."""
    from .recueil import RECITS

    return RECITS


def interactive_sections() -> int:
    """Le nombre de sections d'un livre-jeu, lu la ou il est decide.

    Le recopier ici en ferait deux chiffres qui divergent — et c'est celui du
    menu qui promettrait une longueur que la chaine ne fabrique pas.
    """
    from .interactive import SECTIONS

    return SECTIONS


@dataclass(frozen=True)
class Champ:
    """Une option propre a UN type de produit, declaree une seule fois.

    Les options communes — sujet, ton, audience, qualite — vivent dans
    « _options_communes » de la CLI : elles valent pour les onze types et
    n'ont rien a faire ici.

    Ce qui est declare la, ce sont les reglages qu'un seul type comprend : le
    nombre de modules d'une formation, la cible d'un outil logiciel, la marge
    de reliure d'un cahier imprimable.

    Mesure du 14/09/2026 : sur les dix-sept options propres aux types
    fabricables, HUIT etaient inatteignables depuis le tableau de bord. On ne
    pouvait pas choisir, depuis le navigateur, si un outil logiciel devait
    etre une ligne de commande ou une application web.

    La cause n'etait pas un oubli mais une forme : le formulaire etait du HTML
    ecrit a la main, avec des blocs caches et montres par le script. Ajouter
    un type demandait d'editer le gabarit, le script ET le serveur — et les
    options tombaient entre les mailles, une par une, sans que rien ne le dise.

    Une declaration, trois lecteurs : l'analyseur d'arguments la transforme en
    « add_argument », le serveur la sert au navigateur, le tableau de bord en
    fait la section du type. Un champ ajoute ici apparait partout.
    """

    nom: str                          # le « dest » cote CLI, la cle cote JSON
    drapeau: str                      # « --narration », « -n/--nombre »
    libelle: str                      # ce que l'utilisateur lit
    genre: str = "texte"              # texte | entier | decimal | booleen | choix
    defaut: Any = ""
    choix: Tuple[str, ...] = ()
    aide: str = ""
    unite: str = ""                   # « mm », « mots »... affiche apres le champ

    @property
    def drapeaux(self) -> Tuple[str, ...]:
        """Les formes acceptees en ligne de commande, courte puis longue."""
        return tuple(part for part in self.drapeau.split("/") if part)


def champs_de_fiction() -> Tuple[Champ, ...]:
    """Les reglages que TOUTE fiction comprend, et qu'aucun guide ne comprend.

    Declares une fois, partages par les types de la famille « fiction ». Les
    recopier type par type garantirait qu'un type ajoute plus tard en oublie
    la moitie — et un reglage manquant ne se voit pas : la chaine se contente
    du defaut, qui n'est pas neutre, seulement invisible.

    Ce ne sont PAS les reglages du non-fictionnel renommes. Un guide se regle
    par audience, promesse de resultat et niveau de difficulte ; ces trois-la
    n'ont pas de sens pour un roman. Une fiction se regle par ou elle se
    range, ce que le lecteur vient y retrouver, et ce qu'il ne pardonnera pas
    qu'on lui refuse.
    """
    from . import fiction

    sous_genres = tuple(sorted(
        s for sous in fiction.GENRES.values() for s in sous))
    return (
        Champ("genre", "--genre", "Genre", genre="choix",
              choix=("",) + tuple(sorted(fiction.GENRES)),
              aide="Laissez vide : il se deduit du sous-genre."),
        Champ("sous_genre", "--sous-genre", "Sous-genre",
              aide="C'est lui qui decide de tout le reste — longueur "
                   "attendue, chaleur, fin admissible. « Romance » seul ne "
                   "suffit pas a ecrire une romance. Suggestions : "
                   + ", ".join(sous_genres[:8]) + "..."),
        Champ("tropes", "--tropes", "Tropes",
              aide="Ce que le lecteur vient retrouver, separes par des "
                   "virgules. C'est par la qu'il cherche un livre : il ne "
                   "tape pas « romance contemporaine », il tape « ennemis "
                   "puis amants »."),
        Champ("ambiance", "--ambiance", "Ambiance", genre="choix",
              choix=("",) + fiction.AMBIANCES,
              aide="Ce que le lecteur vient ressentir. Deux livres du meme "
                   "sous-genre ne visent pas le meme lecteur si l'ambiance "
                   "differe."),
        Champ("point_de_vue", "--point-de-vue", "Point de vue", genre="choix",
              choix=("",) + fiction.POINTS_DE_VUE,
              aide="Convention de sous-genre, pas detail de style : se "
                   "tromper se lit comme une maladresse des la premiere "
                   "page."),
        Champ("temps", "--temps", "Temps du recit", genre="choix",
              choix=("",) + fiction.TEMPS),
        Champ("chaleur", "--chaleur", "Niveau de chaleur", genre="choix",
              choix=("",) + fiction.CHALEUR,
              aide="Une attente de lecteur, pas un curseur de gout : "
                   "promettre l'un et livrer l'autre fache dans les DEUX "
                   "sens."),
        Champ("fin", "--fin", "Fin attendue", genre="choix",
              choix=("",) + fiction.FINS,
              aide="En romance, une fin malheureuse est un manquement au "
                   "contrat de genre. Ailleurs, elle est libre."),
        Champ("structure", "--structure", "Charpente", genre="choix",
              choix=("",) + fiction.STRUCTURES,
              aide="« Beats de romance » suit l'arc de la RELATION : dans "
                   "une romance, c'est elle la charpente, et la traiter en "
                   "second plan se voit."),
        Champ("serie", "--serie", "Serie",
              aide="Laissez vide pour un recit isole. Un tome reprend le "
                   "monde, la distribution et les faits des precedents."),
    )


@dataclass
class TypeProduit:
    """Un type de produit reellement fabricable."""

    cle: str
    nom: str
    resume: str                       # une ligne, pour les listes
    detail: str                       # ce que l'acheteur recoit, pour le menu
    formats: Tuple[str, ...]          # extensions livrees
    minutes: Tuple[int, int]          # duree estimee (min, max)
    quantite: Optional[Tuple[str, str, str]] = None
    # (nom de l'argument, question posee, valeur par defaut)
    fabriquer: Optional[Callable[..., Dict[str, Any]]] = None
    vendable: bool = True             # False pour les outils d'analyse
    file: bool = True                 # peut entrer dans la file de production
    # Une edition courte offerte a un sens pour un produit qu'on LIT. Pour un
    # outil logiciel, « les deux premiers chapitres » ne veut rien dire : ce
    # qu'on vend est un programme qui marche, pas un texte qu'on goute.
    extrait: bool = True
    # Le controle qualite deterministe mesure de la PROSE : rythme des
    # phrases, repetition de n-grammes, diversite lexicale, continuite d'une
    # section a l'autre. Applique a autre chose, il rend un chiffre qui n'a
    # pas de sens — et un chiffre sans sens est pire que pas de chiffre,
    # parce qu'on le croit.
    #
    # Mesure du 14/09/2026, en faisant tourner le controle sur un produit de
    # chaque type : 9,98/10 pour trente-et-un posts sociaux de deux lignes,
    # 9,83 pour un outil logiciel — note en fait sur sa notice, pas sur son
    # code —, et six signalements de « rythme » sur une liste de prompts, ou
    # le rythme n'existe pas. Ces notes-la ne mesuraient rien.
    #
    # Le nombre de mots et de sections, lui, se compte pour tout le monde :
    # c'est un decompte, pas un verdict.
    prose: bool = True
    # « fiction » ou « pratique ». Ce n'est pas un rangement de menu : c'est
    # ce qui decide de la QUESTION qu'on pose au modele avant de fabriquer.
    # Pour un guide, on cherche un probleme que quelqu'un paie pour resoudre.
    # Pour un roman, cette question n'a pas de reponse honnete — et un modele
    # a qui l'on pose une question sans reponse en fabrique une. On obtenait
    # « ce thriller resout le probleme du manque de suspense dans votre vie ».
    famille: str = "pratique"
    mots_cles: Tuple[str, ...] = ()   # aide l'explorateur de niches a choisir
    options: Dict[str, Any] = field(default_factory=dict)
    # Les reglages que CE type comprend, et lui seul. Voir « Champ ».
    champs: Tuple[Champ, ...] = ()

    @property
    def duree(self) -> str:
        return "{} a {} min".format(*self.minutes)

    @property
    def nom_quantite(self) -> str:
        return self.quantite[0] if self.quantite else ""

    def defaut_quantite(self) -> int:
        if not self.quantite:
            return 0
        try:
            return int(self.quantite[2])
        except ValueError:
            return 0

    def executer(self, contexte: Any, options: Optional[Dict[str, Any]] = None):
        """Lance la fabrication en traduisant la quantite vers son argument."""
        if self.fabriquer is None:
            raise RuntimeError("type « {} » sans chaine de fabrication".format(self.cle))
        options = dict(options or {})
        arguments: Dict[str, Any] = {}
        if self.quantite:
            nom_argument = self.quantite[0]
            valeur = options.get("nombre") or options.get(nom_argument)
            if valeur:
                try:
                    arguments[nom_argument] = int(valeur)
                except (TypeError, ValueError):
                    pass
        for nom, valeur in self.options.items():
            if options.get(nom) is not None:
                arguments[nom] = options[nom]
            elif valeur is not None:
                arguments[nom] = valeur
        return self.fabriquer(contexte, **arguments)


def _chaines() -> Dict[str, Callable]:
    """Import tardif : le catalogue est lu par des modules que les chaines importent."""
    from . import (boite_outils, ebook, emails, formation, idees, impression,
                   interactive, logiciel, memo, modeles, nouvelle,
                   pack_prompts, quiz, recueil, social)

    return {
        "ebook": ebook.produire,
        "nouvelle": nouvelle.produire,
        "roman": nouvelle.produire_roman,
        "interactive": interactive.produire,
        "recueil": recueil.produire,
        "prompts": pack_prompts.produire,
        "formation": formation.produire,
        "outils": boite_outils.produire,
        "modeles": modeles.produire,
        "impression": impression.produire,
        "social": social.produire,
        "logiciel": logiciel.produire,
        "emails": emails.produire,
        "memo": memo.produire,
        "quiz": quiz.produire,
        "idees": idees.produire,
    }


TYPES: List[TypeProduit] = [
    TypeProduit(
        cle="ebook", nom="Ebook complet",
        resume="Un guide structure, du plan a la couverture",
        detail="PDF + EPUB + HTML + Markdown + couverture",
        formats=("pdf", "epub", "html", "md", "txt"),
        minutes=(10, 25),
        # Un appel de modele par produit, sur le livre entier : a la demande.
        options={"relecture_ensemble": None},
        mots_cles=("guide", "methode", "livre", "manuel", "apprendre"),
    ),
    TypeProduit(
        cle="nouvelle", nom="Nouvelle (fiction)", famille="fiction",
        resume="Une histoire courte, avec bible et continuite tenue",
        detail="PDF + EPUB + HTML + Markdown + couverture",
        formats=("pdf", "epub", "html", "md", "txt"),
        minutes=(12, 30),
        # Volontairement etroits : « nouvelle » ou « histoire » designent
        # aussi bien un recit qu'une nouvelle methode ou l'histoire d'un
        # marche. Un mot-cle trop large enverrait des guides a la fiction.
        mots_cles=("fiction", "recit", "roman", "conte", "intrigue"),
        # Une serie fait du tome suivant une vente au lecteur du precedent.
        options={"serie": None},
        champs=champs_de_fiction(),
    ),
    TypeProduit(
        cle="roman", nom="Roman (fiction longue)", famille="fiction",
        resume="Un roman : trente scenes en parties, continuite tenue",
        detail="PDF + EPUB + HTML + Markdown + couverture",
        formats=("pdf", "epub", "html", "md", "txt"),
        # Trente scenes relues et controlees : c'est long, et le dire evite
        # qu'on croie l'usine bloquee au bout d'un quart d'heure.
        minutes=(60, 180),
        quantite=("chapitres", "Combien de scenes", str(nouvelle_scenes())),
        mots_cles=("roman", "fiction longue", "saga", "polar", "thriller",
                   "fantasy", "romance"),
        options={"serie": None},
        # Le nombre de scenes n'est PAS declare ici : « --chapitres » est une
        # option commune aux onze types, ajoutee par « _options_communes ».
        # La declarer une seconde fois donnait deux champs de meme nom dans
        # le formulaire — celui d'en haut et celui de la section du type — et
        # le second ecrasait le premier a l'envoi.
        champs=champs_de_fiction(),
    ),
    TypeProduit(
        cle="interactive", nom="Livre dont le lecteur est le heros",
        famille="fiction",
        resume="Un recit a embranchements, dont la carte est verifiee",
        detail="PDF + EPUB + HTML + Markdown + carte du livre",
        formats=("pdf", "epub", "html", "md", "txt"),
        # Une section par appel, plus la bible et la carte. Vingt-quatre
        # sections courtes coutent moins qu'un roman, mais la carte demande
        # un modele costaud et parfois deux essais.
        minutes=(25, 70),
        quantite=("sections", "Combien de sections", str(interactive_sections())),
        # Etroits a dessein : « choix » et « aventure » designent aussi bien
        # un livre-jeu qu'un guide de developpement personnel.
        mots_cles=("livre-jeu", "dont vous etes le heros", "embranchements",
                   "recit interactif"),
        # « sections » n'est PAS declare en option : c'est deja la quantite
        # ci-dessus. Le declarer deux fois donnait deux chemins pour le meme
        # chiffre — et un garde-fou du depot l'a vu tout de suite, parce que
        # le menu n'en proposait qu'un des deux.
        champs=champs_de_fiction(),
    ),
    TypeProduit(
        cle="recueil", nom="Recueil de nouvelles", famille="fiction",
        resume="Plusieurs recits lies par un fil, dont on mesure la variete",
        detail="PDF + EPUB + HTML + Markdown + couverture",
        formats=("pdf", "epub", "html", "md", "txt"),
        # Sept recits de quatre scenes : c'est plus long qu'une nouvelle et
        # moins qu'un roman, et chaque recit paie sa propre bible.
        minutes=(45, 120),
        quantite=("recits", "Combien de nouvelles", str(recueil_recits())),
        mots_cles=("recueil", "nouvelles", "anthologie", "textes courts"),
        champs=champs_de_fiction(),
    ),
    TypeProduit(
        cle="prompts", nom="Pack de prompts",
        resume="Une bibliotheque de prompts classee par intention",
        detail="PDF + CSV importable dans Notion + JSON",
        formats=("pdf", "csv", "json", "html", "md"),
        minutes=(5, 12),
        quantite=("nombre", "Combien de prompts", "50"),
        mots_cles=("prompt", "ia", "chatgpt", "automatisation", "productivite"),
        # Une liste de prompts : pas de rythme, pas de continuite, et la repetition y est voulue.
        prose=False,
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de prompts",
                  genre="entier", defaut=50),
        ),
    ),
    TypeProduit(
        cle="formation", nom="Mini-formation",
        resume="Des modules avec livrables et cahier d'exercices",
        detail="Manuel PDF + cahier d'exercices + sequence e-mail",
        formats=("pdf", "html", "md"),
        minutes=(12, 25),
        quantite=("modules", "Combien de modules", "6"),
        # Un appel de modele par module : c'est a l'utilisateur de decider.
        options={"narration": None},
        mots_cles=("formation", "cours", "apprendre", "module", "atelier"),
        champs=(
            Champ("modules", "-m/--modules", "Nombre de modules",
                  genre="entier", defaut=0,
                  aide="0 : l'usine décide en lisant le sujet."),
            Champ("narration", "--narration", "Script à lire à voix haute",
                  genre="booleen", defaut=False,
                  aide="Un appel de modèle par module, en plus. Utile si vous "
                       "comptez enregistrer la formation."),
        ),
    ),
    TypeProduit(
        cle="outils", nom="Boite a outils",
        resume="Checklists, modeles et tableaux de suivi",
        detail="PDF imprimable + tableaux CSV + HTML",
        formats=("pdf", "csv", "html", "md"),
        minutes=(6, 14),
        quantite=("nombre", "Combien d'outils", "10"),
        mots_cles=("checklist", "modele", "outil", "procedure", "methode"),
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre d'outils",
                  genre="entier", defaut=10),
        ),
    ),
    TypeProduit(
        cle="modeles", nom="Modeles Notion / tableur",
        resume="Des bases liees, prets a importer",
        detail="CSV par base + guide d'installation + PDF",
        formats=("csv", "pdf", "html", "md"),
        minutes=(5, 12),
        quantite=("nombre", "Combien de bases", "4"),
        mots_cles=("notion", "tableur", "modele", "systeme", "organisation",
                   "suivi", "tableau"),
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de bases",
                  genre="entier", defaut=4),
        ),
    ),
    TypeProduit(
        cle="impression", nom="Cahier imprimable",
        resume="Des fiches a remplir a la main",
        detail="PDF aux formats A4 et Lettre US",
        formats=("pdf", "html"),
        minutes=(5, 12),
        quantite=("pages", "Combien de fiches", "12"),
        options={"reliure": None},
        mots_cles=("planner", "imprimable", "cahier", "agenda", "fiche",
                   "planning", "journal"),
        # Des pages a remplir : le PDF livre ne contient presque pas de texte suivi.
        prose=False,
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de fiches",
                  genre="entier", defaut=12),
            Champ("reliure", "--reliure", "Marge de reliure",
                  genre="decimal", defaut=0, unite="mm",
                  aide="Marge intérieure pour l'impression à la demande. "
                       "0 = aucune ; votre imprimeur publie la sienne."),
        ),
    ),
    TypeProduit(
        cle="social", nom="Pack de publications",
        resume="Un calendrier editorial redige",
        detail="Calendrier CSV + posts rediges + visuels optionnels",
        formats=("csv", "pdf", "json", "html", "md"),
        minutes=(5, 15),
        quantite=("nombre", "Combien de publications", "30"),
        options={"reseau": "linkedin"},
        mots_cles=("reseaux", "linkedin", "instagram", "contenu", "post",
                   "calendrier editorial"),
        # Trente posts de deux lignes. Le controle n'a rien a mordre et rend 9,98/10 quoi qu'il arrive.
        prose=False,
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de publications",
                  genre="entier", defaut=30),
            Champ("reseau", "-r/--reseau", "Réseau visé", genre="choix",
                  defaut="linkedin", choix=reseaux_sociaux()),
            Champ("visuels", "--visuels", "Visuels à générer",
                  genre="entier", defaut=0,
                  aide="0 : aucun. Chacun coûte un appel d'image."),
        ),
    ),
    TypeProduit(
        cle="logiciel", nom="Outil logiciel", extrait=False,
        resume="Un outil qui demarre, verifie avant livraison",
        detail="Code source + documentation + rapport de verification",
        formats=("py", "md", "pdf", "html"),
        minutes=(8, 20),
        options={"cible": "cli", "executer": None},
        mots_cles=("outil", "script", "application", "extension", "logiciel",
                   "automatisation", "convertisseur", "generateur",
                   "calculateur", "tableau de bord"),
        # Ce qu'on vend est un programme qui marche. Le seul texte relisible est sa notice — noter l'un pour l'autre serait un verdict fabrique ; « usine logiciel » verifie deja le code.
        prose=False,
        champs=(
            Champ("cible", "-c/--cible", "Ce que vous livrez", genre="choix",
                  defaut="cli", choix=cibles_logiciel(),
                  aide="cli : outil en ligne de commande. web : page "
                       "autonome. extension : Chrome Manifest V3."),
            Champ("sans_essai", "--sans-essai", "Ne pas exécuter le code",
                  genre="booleen", defaut=False,
                  aide="L'usine analyse le code sans jamais le lancer. Plus "
                       "prudent, mais elle ne saura pas s'il démarre."),
        ),
    ),
    TypeProduit(
        cle="emails", nom="Sequence e-mail",
        resume="La serie de messages qui suit une inscription",
        detail="PDF + HTML + Markdown + CSV pret a importer",
        formats=("pdf", "html", "md", "csv"),
        minutes=(6, 14),
        quantite=("nombre", "Combien de messages", "7"),
        mots_cles=("email", "e-mail", "mail", "newsletter", "sequence",
                   "infolettre", "autorepondeur", "nurturing"),
        options={"intention": "bienvenue", "rythme": 2},
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de messages",
                  genre="entier", defaut=7),
            Champ("intention", "-o/--intention", "Ce que la sequence cherche",
                  genre="choix", defaut="bienvenue", choix=objectifs_email(),
                  aide="Une sequence de bienvenue ne demande presque rien ; "
                       "une sequence de vente construit vers un achat."),
            Champ("rythme", "--rythme", "Un message tous les", genre="entier",
                  defaut=2, unite="jours",
                  aide="Sert a ecrire les rappels et a calculer le "
                       "calendrier d'envoi livre avec la sequence."),
        )),
    TypeProduit(
        cle="memo", nom="Memo / antiseche",
        resume="L'essentiel d'un sujet, sur une page qu'on garde",
        detail="PDF + HTML + Markdown + CSV",
        formats=("pdf", "html", "md", "csv"),
        minutes=(4, 9),
        quantite=("nombre", "Combien de blocs", "8"),
        # Un memo n'est pas de la prose : trois mots par ligne. Le controle
        # de rythme et de diversite lexicale y rendrait un chiffre sans sens,
        # et un chiffre sans sens est pire que pas de chiffre.
        prose=False,
        # « Les deux premieres pages » d'un memo d'une page ne veut rien dire.
        extrait=False,
        mots_cles=("memo", "antiseche", "cheatsheet", "aide-memoire",
                   "reference", "fiche", "recapitulatif"),
        options={"recto_verso": False},
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de blocs",
                  genre="entier", defaut=8),
            Champ("recto_verso", "--recto-verso", "Impression recto-verso",
                  genre="booleen", defaut=False,
                  aide="Ajoute une marge de reliure. Inutile — et genante — "
                       "pour une impression simple face."),
        )),
    TypeProduit(
        cle="quiz", nom="Quiz avec corrige",
        resume="Des questions, leurs reponses, et pourquoi",
        detail="PDF + HTML + Markdown + CSV",
        formats=("pdf", "html", "md", "csv"),
        minutes=(7, 16),
        quantite=("nombre", "Combien de questions", "20"),
        # Une question et quatre propositions ne se mesurent pas comme un
        # chapitre. Seules les explications sont de la prose, et elles font
        # le quart du produit.
        prose=False,
        mots_cles=("quiz", "qcm", "test", "evaluation", "examen",
                   "auto-evaluation", "questionnaire", "revision"),
        options={"niveau": "intermediaire", "sans_bareme": False},
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de questions",
                  genre="entier", defaut=20),
            Champ("niveau", "--niveau", "Niveau vise", genre="choix",
                  defaut="intermediaire", choix=niveaux_quiz()),
            Champ("sans_bareme", "--sans-bareme", "Ne pas inclure de bareme",
                  genre="booleen", defaut=False,
                  aide="Le bareme donne des seuils en nombre de bonnes "
                       "reponses, calcules sur les questions reellement "
                       "retenues."),
        )),
    TypeProduit(
        cle="idees", nom="Etude de niche",
        resume="Des pistes chiffrees, appuyees sur des mesures de marche",
        detail="Idees evaluees : prix, difficulte, concurrence",
        formats=("csv", "json", "html", "md"),
        minutes=(2, 4),
        quantite=("nombre", "Combien d'idees", "12"),
        options={"avec_marche": None},
        vendable=False, file=False,
        champs=(
            Champ("nombre", "-n/--nombre", "Nombre de pistes",
                  genre="entier", defaut=12),
            Champ("sans_marche", "--sans-marche", "Ne pas mesurer le marché",
                  genre="booleen", defaut=False,
                  aide="Plus rapide, et les pistes ne sont alors appuyées sur "
                       "aucune mesure."),
            Champ("sans_veille", "--sans-veille", "Ne pas lire les discussions",
                  genre="booleen", defaut=False,
                  aide="La veille est lente par construction : trois secondes "
                       "entre deux communautés."),
        ),
    ),
]

# Les mots-cles sont compares a du texte normalise sans accent : un mot-cle
# accentue ne correspondrait jamais a rien. Mieux vaut le refuser bruyamment
# a l'import que le laisser silencieusement inoperant.
for _type in TYPES:
    for _mot in _type.mots_cles:
        assert all(ord(c) < 128 for c in _mot), (
            "mot-cle non ASCII dans « {} » : {!r}".format(_type.cle, _mot))

PAR_CLE: Dict[str, TypeProduit] = {t.cle: t for t in TYPES}
_cablees = False


def _cabler() -> None:
    global _cablees
    if _cablees:
        return
    chaines = _chaines()
    for type_produit in TYPES:
        type_produit.fabriquer = chaines.get(type_produit.cle)
    _cablees = True


def obtenir(cle: str) -> Optional[TypeProduit]:
    _cabler()
    return PAR_CLE.get(cle)


def tous(fabricables: bool = False, vendables: bool = False,
         en_file: bool = False) -> List[TypeProduit]:
    """Les types, filtres selon l'usage."""
    _cabler()
    selection = list(TYPES)
    if fabricables:
        selection = [t for t in selection if t.fabriquer is not None]
    if vendables:
        selection = [t for t in selection if t.vendable]
    if en_file:
        selection = [t for t in selection if t.file]
    return selection


def cles(**filtres: bool) -> List[str]:
    return [t.cle for t in tous(**filtres)]


def executer(cle: str, contexte: Any,
             options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    type_produit = obtenir(cle)
    if type_produit is None:
        raise ValueError("type de produit inconnu : {}".format(cle))
    return type_produit.executer(contexte, options)


def accepte_extrait(cle: str) -> bool:
    """Ce type de produit se prete-t-il a une edition courte offerte ?"""
    type_produit = obtenir(cle)
    return bool(type_produit.extrait) if type_produit else False


def normaliser(cle: str, defaut: str = "ebook") -> str:
    """Ramene une cle proposee par un modele vers un type reellement fabricable."""
    propre = (cle or "").lower().strip()
    if propre in PAR_CLE:
        return propre
    # Tolerance sur les synonymes courants : un modele ecrit « e-book »,
    # « planner » ou « template » plutot que nos cles internes.
    synonymes = {
        "e-book": "ebook", "livre": "ebook", "guide": "ebook", "manuel": "ebook",
        "cours": "formation", "course": "formation", "masterclass": "formation",
        "template": "modeles", "templates": "modeles", "notion": "modeles",
        "tableur": "modeles", "spreadsheet": "modeles",
        "planner": "impression", "printable": "impression",
        "imprimable": "impression", "cahier": "impression",
        "checklist": "outils", "boite-a-outils": "outils", "toolkit": "outils",
        "prompt": "prompts", "prompt-pack": "prompts",
        "reseaux": "social", "contenu": "social", "social-media": "social",
    }
    if propre in synonymes:
        return synonymes[propre]
    for type_produit in TYPES:
        if any(mot in propre for mot in type_produit.mots_cles):
            return type_produit.cle
    return defaut


def type_pour_sujet(contexte: Any, sujet: str, defaut: str = "ebook") -> str:
    """Quel type de produit ce sujet appelle-t-il ?

    « usine auto "la prospection pour freelances" » pose une question que les
    dix commandes de fabrication ne savent pas poser : elles exigent le type
    d'abord. Or choisir le type suppose de savoir ce qui se vend sur ce
    sujet-la, ce qui vient apres.

    Le modele choisit parmi les types REELLEMENT fabricables, lus au
    catalogue plutot que recopies : un type ajoute arrive ici tout seul. Sa
    reponse passe ensuite par « normaliser », qui rattrape les synonymes — un
    modele ecrit volontiers « planner » ou « template ».

    En cas d'echec (modele muet, JSON illisible, reseau coupe), on rend le
    defaut : un type raisonnable vaut mieux qu'une fabrication qui s'arrete,
    et l'appelant dit lequel il a retenu.
    """
    from ..agents import equipe

    invite = (
        "Un vendeur veut fabriquer UN produit digital sur ce sujet :\n"
        "« {sujet} »\n\n"
        "Quel type de produit se vend le mieux sur ce sujet, parmi ceux que "
        "l'usine sait fabriquer ?\n{catalogue}\n\n"
        "Choisis en pensant a l'acheteur : ce qu'il cherche, et sous quelle "
        "forme il accepte de le payer. Un sujet tres pratique se vend mieux "
        "en modeles ou en boite a outils qu'en livre ; un sujet narratif "
        "appelle une fiction.\n\n"
        'Schema JSON exact :\n{{"type": "{types}", "pourquoi": "une phrase"}}'
    ).format(sujet=sujet[:300], catalogue=resume_pour_ia(),
             types="|".join(cles(vendables=True)))
    try:
        donnees = equipe.PROSPECTEUR.travailler_json(
            contexte, invite, role_modele="rapide",
            temperature=0.2, max_tokens=300)
    except Exception:
        return defaut
    if not isinstance(donnees, dict):
        return defaut
    return normaliser(str(donnees.get("type") or ""), defaut=defaut)


def resume_pour_ia() -> str:
    """Description du catalogue a injecter dans une invite."""
    lignes = []
    for type_produit in tous(vendables=True):
        lignes.append("- {} : {} ({})".format(
            type_produit.cle, type_produit.resume, type_produit.detail))
    return "\n".join(lignes)
