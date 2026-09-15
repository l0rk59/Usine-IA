"""Fiction dont le lecteur choisit : un graphe, pas une ligne.

Pourquoi une chaine a part, et pas une option de « nouvelle ». Toute la
machinerie de fiction du depot suppose une SUITE : des scenes numerotees, un
resume roulant qui avance, une grille de beats ou la scene 11 paie ce que la
scene 3 a promis. Un recit a embranchements n'a rien de tout cela. La scene
qui suit la section 4 depend du lecteur, le « resume de ce qui precede » n'a
pas de valeur unique, et deux lecteurs n'auront pas lu le meme livre.

Ce que cette chaine ajoute, et qui n'existe nulle part ailleurs :

  1. UNE CARTE, ecrite avant le premier mot : des sections numerotees, leurs
     choix, et leurs cibles. C'est un graphe oriente, et c'est le produit.
  2. UNE VERIFICATION DETERMINISTE DE CE GRAPHE, avant de payer une seule
     redaction. C'est le coeur de la chaine : les defauts d'un livre-jeu
     sont des defauts de STRUCTURE, ils se voient en parcourant le graphe, et
     ils coutent le livre entier a decouvrir a la lecture.

Les quatre defauts que la verification attrape, et qu'un lecteur decouvre
sinon a sa place :

  le CHOIX MORT       « rendez-vous a la section 12 », et la 12 n'existe pas ;
  la SECTION ORPHELINE ecrite, payee, et qu'aucun chemin n'atteint ;
  le PIEGE            on y entre, on n'en sort plus, et aucune fin n'est
                      joignable — le lecteur boucle jusqu'a fermer le livre ;
  la FIN UNIQUE       un livre a choix qui n'a qu'une issue n'est pas un
                      livre a choix, c'est un roman avec des pages en
                      desordre.

Aucun de ces quatre ne demande un appel de modele pour etre vu. Ils se
comptent.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Set

from ..agents import equipe
from ..render import livraison
from . import fiction
from .base import Contexte, elaguer_markdown, jetons_pour, preparer, terminer

# Combien de sections par defaut. Un livre-jeu court se lit en une soiree ;
# en dessous de douze, l'arbre n'a pas la place de se ramifier et le lecteur
# voit le fond tout de suite.
SECTIONS = 24
SECTIONS_MIN, SECTIONS_MAX = 8, 80
# Mots par section. Une section de livre-jeu est courte par nature : elle se
# termine sur un choix, et un lecteur qui doit tourner trois pages avant de
# choisir a perdu le fil de ce qu'il choisissait.
MOTS_SECTION = 220
# Deux fins, c'est le minimum sous lequel le format ne veut plus rien dire.
FINS_MINIMUM = 2


def _invite_carte(ctx: Contexte, bible: Dict[str, Any], sections: int,
                  fautes: Sequence[str] = ()) -> str:
    correction = ""
    if fautes:
        # On NOMME les defauts plutot que de redemander la meme chose : un
        # modele a qui l'on dit « recommence » refait la meme carte. Un
        # modele a qui l'on dit « la section 7 renvoie vers 31, qui n'existe
        # pas » corrige ce point-la.
        correction = (
            "\n\nTa carte precedente avait ces defauts PRECIS. Corrige-les "
            "sans tout refaire :\n" + "\n".join("- " + f for f in fautes)
            + "\n")
    return (
        "Concois la CARTE d'un livre dont le lecteur est le heros.\n\n"
        "--- BIBLE (ne la contredis pas) ---\n{bible}\n"
        "{promesse}{correction}\n"
        "Une carte est un graphe de sections numerotees de 1 a {n}.\n\n"
        "Regles absolues — une carte qui les viole est inutilisable :\n"
        "- la section 1 est le depart ;\n"
        "- chaque choix renvoie vers un numero qui EXISTE, entre 1 et {n} ;\n"
        "- toute section doit etre atteignable depuis la 1 ;\n"
        "- depuis n'importe quelle section, on doit pouvoir atteindre une "
        "fin : pas de boucle sans issue ;\n"
        "- au moins {fins} fins differentes, et au moins une heureuse et une "
        "malheureuse ;\n"
        "- une fin n'a AUCUN choix ; toute autre section en a deux ou trois.\n\n"
        "Pour chaque section : un intitule court (ce qui s'y passe, pas un "
        "titre de chapitre), et ses choix. Le texte de chaque choix est ce "
        "que le LECTEUR decide de faire, a l'infinitif ou a la deuxieme "
        "personne.\n\n"
        "Schema JSON exact :\n"
        '{{"sections": [{{"numero": 1, "intitule": "...", "fin": false, '
        '"choix": [{{"texte": "Pousser la porte", "vers": 4}}]}}, '
        '{{"numero": 2, "intitule": "...", "fin": true, "issue": '
        '"heureuse|malheureuse|ambigue", "choix": []}}]}}'
    ).format(bible=_resume_bible(bible), n=sections, fins=FINS_MINIMUM,
             promesse=fiction.consignes(ctx), correction=correction)


def _resume_bible(bible: Dict[str, Any]) -> str:
    personnages = ", ".join(
        "{} ({})".format(p.get("nom", ""), p.get("desir", ""))
        for p in bible.get("personnages", [])[:4])
    cadre = bible.get("cadre") or {}
    return ("TITRE : {}\nPREMISSE : {}\nLIEU : {}\nEPOQUE : {}\n"
            "PERSONNAGES : {}\nENJEU : {}").format(
                bible.get("titre", ""), bible.get("premisse", ""),
                cadre.get("lieu", ""), cadre.get("epoque", ""),
                personnages, bible.get("enjeu", ""))


def normaliser_carte(brut: Any, sections: int) -> List[Dict[str, Any]]:
    """Ramene la reponse du modele a une carte manipulable.

    Ne REPARE rien : elle jette ce qui n'est pas lisible (un numero qui n'en
    est pas un, un choix sans cible) et laisse la verification dire ce qui
    manque. Reparer ici en silence ferait passer une carte trouee pour une
    carte juste — et c'est justement ce qu'on veut pouvoir compter.
    """
    entrees = brut.get("sections") if isinstance(brut, dict) else brut
    carte: Dict[int, Dict[str, Any]] = {}
    for entree in entrees or []:
        if not isinstance(entree, dict):
            continue
        try:
            numero = int(entree.get("numero"))
        except (TypeError, ValueError):
            continue
        if not 1 <= numero <= sections or numero in carte:
            continue
        choix = []
        for propose in entree.get("choix") or []:
            if not isinstance(propose, dict):
                continue
            texte = str(propose.get("texte") or "").strip()
            try:
                vers = int(propose.get("vers"))
            except (TypeError, ValueError):
                continue
            if texte:
                choix.append({"texte": texte, "vers": vers})
        fin = bool(entree.get("fin")) or not choix
        carte[numero] = {
            "numero": numero,
            "intitule": str(entree.get("intitule") or "").strip(),
            "fin": fin,
            "issue": str(entree.get("issue") or "").strip() if fin else "",
            "choix": [] if fin else choix,
        }
    return [carte[n] for n in sorted(carte)]


def _index(carte: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {s["numero"]: s for s in carte}


def atteignables(carte: List[Dict[str, Any]], depart: int = 1) -> Set[int]:
    """Les sections qu'un lecteur peut vraiment atteindre depuis le depart."""
    par_numero = _index(carte)
    if depart not in par_numero:
        return set()
    vus, a_voir = {depart}, [depart]
    while a_voir:
        courant = par_numero[a_voir.pop()]
        for choix in courant["choix"]:
            cible = choix["vers"]
            if cible in par_numero and cible not in vus:
                vus.add(cible)
                a_voir.append(cible)
    return vus


def _menent_a_une_fin(carte: List[Dict[str, Any]]) -> Set[int]:
    """Les sections depuis lesquelles une fin est joignable.

    Calcul a l'envers : on part des fins et on remonte les choix. Le faire a
    l'endroit demanderait d'explorer chaque chemin, et un graphe avec des
    boucles n'en finirait pas.
    """
    par_numero = _index(carte)
    sortantes = {s["numero"] for s in carte if s["fin"]}
    entrants: Dict[int, List[int]] = {}
    for section in carte:
        for choix in section["choix"]:
            entrants.setdefault(choix["vers"], []).append(section["numero"])
    a_voir = list(sortantes)
    while a_voir:
        courant = a_voir.pop()
        for precedent in entrants.get(courant, []):
            if precedent in par_numero and precedent not in sortantes:
                sortantes.add(precedent)
                a_voir.append(precedent)
    return sortantes


def verifier_carte(carte: List[Dict[str, Any]],
                   sections: int) -> List[str]:
    """Les defauts de STRUCTURE, comptes avant d'ecrire une seule ligne.

    Zero appel de modele, et c'est ce qui rend ce controle possible : il
    tourne AVANT la redaction, donc un livre-jeu troue ne coute pas un livre
    entier a decouvrir.

    Il enonce des faits verifiables — « la section 7 renvoie vers 31, qui
    n'existe pas » —, pas des impressions. Un defaut nomme se corrige ; un
    « la carte semble incoherente » se relit trois fois sans rien trouver.
    """
    fautes: List[str] = []
    if not carte:
        return ["La carte est vide."]
    par_numero = _index(carte)
    if 1 not in par_numero:
        fautes.append("Il n'y a pas de section 1 : le lecteur ne peut pas "
                      "commencer.")

    for section in carte:
        for choix in section["choix"]:
            if choix["vers"] not in par_numero:
                fautes.append(
                    "Section {} : « {} » renvoie vers la section {}, qui "
                    "n'existe pas.".format(section["numero"],
                                           choix["texte"][:40], choix["vers"]))
        if not section["fin"] and len(section["choix"]) < 2:
            fautes.append(
                "Section {} n'est pas une fin mais n'offre {} : soit elle "
                "propose au moins deux choix, soit c'est une fin.".format(
                    section["numero"],
                    "qu'un choix" if section["choix"] else "aucun choix"))

    joignables = atteignables(carte)
    orphelines = sorted(set(par_numero) - joignables)
    if orphelines:
        fautes.append(
            "Aucun chemin ne mene aux sections {} : elles seraient ecrites, "
            "payees, et jamais lues.".format(
                ", ".join(str(n) for n in orphelines[:8])))

    vers_une_fin = _menent_a_une_fin(carte)
    pieges = sorted(joignables - vers_une_fin)
    if pieges:
        fautes.append(
            "Depuis les sections {}, aucune fin n'est joignable : le lecteur "
            "y tourne en rond jusqu'a fermer le livre.".format(
                ", ".join(str(n) for n in pieges[:8])))

    fins = [s for s in carte if s["fin"]]
    if len(fins) < FINS_MINIMUM:
        fautes.append(
            "Il n'y a que {} fin(s). Un livre a choix qui n'a qu'une issue "
            "n'est pas un livre a choix.".format(len(fins)))
    return fautes


def elaguer(carte: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le dernier recours : rendre une carte LISIBLE, et le dire.

    Appelee seulement quand le modele n'a pas su corriger. Elle ne repare pas
    l'histoire — elle coupe ce qui la rend injouable, pour qu'il sorte un
    livre qu'on peut lire de bout en bout plutot qu'un livre qui bloque a la
    section 7.

    Trois coupes, dans cet ordre : les choix vers le vide disparaissent ; une
    section qui n'a plus de choix devient une fin ; ce qu'aucun chemin
    n'atteint n'est pas ecrit. C'est une degradation, elle est annoncee, et
    elle vaut mieux qu'un produit qu'on ne peut pas finir.
    """
    par_numero = _index(carte)
    for section in carte:
        section["choix"] = [c for c in section["choix"]
                            if c["vers"] in par_numero
                            and c["vers"] != section["numero"]]
        if not section["choix"]:
            section["fin"] = True
            section["issue"] = section["issue"] or "ambigue"
    # Un piege devient une fin : c'est la seule facon de le rendre jouable
    # sans inventer une suite que personne n'a ecrite.
    for numero in set(_index(carte)) - _menent_a_une_fin(carte):
        par_numero[numero]["fin"] = True
        par_numero[numero]["issue"] = "ambigue"
        par_numero[numero]["choix"] = []
    joignables = atteignables(carte)
    return [s for s in carte if s["numero"] in joignables]


def _rediger_section(ctx: Contexte, bible: Dict[str, Any],
                     section: Dict[str, Any], mots: int) -> str:
    """Le texte d'UNE section. Les choix ne sont pas demandes au modele.

    Ils sont deja dans la carte, deja verifies, et deja numerotes. Les faire
    reecrire par le redacteur les ferait deriver de la carte — le texte
    proposerait trois portes la ou le graphe en connait deux, et la
    verification qu'on vient de payer ne garderait plus rien.
    """
    if section["fin"]:
        consigne = (
            "C'est une FIN ({issue}). Elle se suffit : le lecteur ferme le "
            "livre ici. Ne propose aucun choix, n'annonce aucune suite, et "
            "ne renvoie vers aucune section."
        ).format(issue=section["issue"] or "ambigue")
    else:
        consigne = (
            "La section se termine JUSTE AVANT le choix. N'ecris pas les "
            "options — elles sont ajoutees ensuite, mot pour mot :\n{choix}\n"
            "Amene-les : a la derniere ligne, le lecteur doit sentir ces "
            "possibilites-la et pas d'autres."
        ).format(choix="\n".join(
            "  - {}".format(c["texte"]) for c in section["choix"]))

    invite = (
        "Ecris la section {num} d'un livre dont le lecteur est le heros.\n\n"
        "--- BIBLE (source de verite) ---\n{bible}\n\n"
        "CE QUI S'Y PASSE : {intitule}\n"
        "{promesse}\n{consigne}\n\n"
        "Consignes :\n"
        "- Environ {mots} mots.\n"
        "- Le lecteur est « vous ». C'est lui le personnage, pas un tiers "
        "qu'on observe.\n"
        "- Cette section se lit sans savoir par ou l'on est arrive : "
        "plusieurs chemins y menent. Ne dis donc jamais « apres avoir fait "
        "X ».\n"
        "- N'ecris aucun titre, aucun numero de section.\n"
        "- Reponds uniquement par le texte."
    ).format(num=section["numero"], bible=_resume_bible(bible),
             intitule=section["intitule"] or "libre",
             promesse=fiction.consignes_de_scene(ctx),
             consigne=consigne, mots=mots)
    reponse = equipe.REDACTEUR.travailler(ctx, invite, max_tokens=jetons_pour(mots))
    return _sans_titres(elaguer_markdown(reponse.texte))


def _sans_titres(texte: str) -> str:
    """Retire les titres que le modele ajoute malgre la consigne.

    Ce n'est pas de la cosmetique ici, contrairement aux autres chaines. Le
    numero de section EST un titre de niveau 2 dans le document rendu : un
    « ## Le principe de base » laisse dans le corps d'une section fabrique une
    section fantome au sommaire, et le lecteur a qui l'on dit « rendez-vous
    au 7 » trouve deux entrees entre le 6 et le 8.
    """
    lignes = [l for l in texte.split("\n") if not l.lstrip().startswith("#")]
    return "\n".join(lignes).strip()


def _markdown(carte: List[Dict[str, Any]]) -> str:
    morceaux = []
    for section in carte:
        morceaux.append("## {}".format(section["numero"]))
        morceaux.append(section.get("texte") or "")
        if section["fin"]:
            morceaux.append("*Fin.*")
        else:
            for choix in section["choix"]:
                morceaux.append("- {} → **{}**".format(
                    choix["texte"], choix["vers"]))
        morceaux.append("")
    return "\n\n".join(morceaux)


def produire(ctx: Contexte, sections: int = 0) -> Dict[str, Any]:
    """Un livre dont le lecteur est le heros : carte verifiee, puis redigee."""
    from .nouvelle import construire_bible

    demande = int(sections or ctx.chapitres or SECTIONS)
    demande = max(SECTIONS_MIN, min(demande, SECTIONS_MAX))
    mots = ctx.mots_section or MOTS_SECTION

    ctx.journal("Etape 1/4 — la bible : distribution, cadre, enjeu...")
    bible = construire_bible(ctx)
    titre = bible["titre"]
    dossier = preparer(ctx, "interactive", titre)
    ctx.etape("bible", "ok", "{} personnage(s)".format(len(bible["personnages"])))

    ctx.journal("Etape 2/4 — la carte : {} sections et leurs "
                "embranchements...".format(demande))
    carte: List[Dict[str, Any]] = []
    fautes: List[str] = []
    # Deux tentatives, et la seconde NOMME les defauts de la premiere. Un
    # modele a qui l'on dit « recommence » refait la meme carte.
    for tentative in range(2):
        brut = equipe.ARCHITECTE.travailler_json(
            ctx, _invite_carte(ctx, bible, demande, fautes),
            role_modele="costaud", temperature=0.6, max_tokens=4000,
            cache=tentative == 0)
        carte = normaliser_carte(brut, demande)
        fautes = verifier_carte(carte, demande)
        if not fautes:
            break
        ctx.journal("  carte incoherente, {} defaut(s) — on les nomme et on "
                    "redemande :".format(len(fautes)))
        for faute in fautes[:4]:
            ctx.journal("    " + faute)

    elaguee = False
    if fautes:
        # Le modele n'a pas su. On rend le livre JOUABLE plutot que juste, et
        # on le dit : un produit degrade qui s'annonce vaut mieux qu'un
        # produit bloque qui se tait.
        avant = len(carte)
        carte = elaguer(carte)
        elaguee = True
        ctx.journal("  carte elaguee pour rester jouable : {} section(s) sur "
                    "{} retenues.".format(len(carte), avant))
    restantes = verifier_carte(carte, demande)
    ctx.etape("carte", "partiel" if restantes or elaguee else "ok",
              "{} sections, {} fins".format(
                  len(carte), sum(1 for s in carte if s["fin"])))

    ctx.journal("Etape 3/4 — redaction de {} section(s)...".format(len(carte)))
    for rang, section in enumerate(carte, 1):
        try:
            section["texte"] = _rediger_section(ctx, bible, section, mots)
        except Exception as exc:
            # Une section perdue ne doit pas emporter le livre : son intitule
            # tient la place, le chemin reste parcourable, et le trou est
            # visible plutot que silencieux.
            ctx.journal("  section {} indisponible : {}".format(
                section["numero"], exc))
            section["texte"] = "*({})*".format(
                section["intitule"] or "section manquante")
        if rang % 5 == 0 or rang == len(carte):
            ctx.journal("  {}/{} sections".format(rang, len(carte)))
    ctx.etape("sections", "ok", "{} sections redigees".format(len(carte)))

    ctx.journal("Etape 4/4 — export...")
    fins = [s for s in carte if s["fin"]]
    produit = livraison.Produit(
        type="interactive", titre=titre,
        sous_titre="{} sections, {} fins".format(len(carte), len(fins)),
        promesse=bible.get("premisse", ""),
        blocs=[
            livraison.Bloc(
                titre="Comment lire ce livre",
                corps="Ce livre ne se lit pas dans l'ordre. Commencez a la "
                      "section **1**, puis suivez le numero du choix que "
                      "vous faites. Il y a {} fins : celle que vous "
                      "atteindrez depend de vous.".format(len(fins))),
            livraison.Bloc(titre="Le livre", corps=_markdown(carte)),
        ],
        donnees={"bible": bible, "carte": carte},
        nom_donnees="carte",
        formats=("md", "pdf", "html", "epub", "txt"),
        libelle_sections="section(s)",
    )
    fichiers = livraison.livrer(ctx, produit)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "sections": len(carte),
        "fins": len(fins),
        "carte_elaguee": elaguee,
        # Ce qui reste faux est rendu, pas tu : c'est ce que l'acheteur
        # rencontrerait, et c'est ce qui decide s'il faut refabriquer.
        "defauts_restants": restantes,
        "mots": sum(len((s.get("texte") or "").split()) for s in carte),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"sections": len(carte), "fins": len(fins)})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume
