"""Faux fournisseur IA : teste toute la chaine sans cle API ni reseau.

Le simulateur reconnait chaque schema JSON demande par les pipelines et renvoie
une structure conforme, afin que les tests exercent le vrai code de production.
"""

from __future__ import annotations

import json
import re

CORPS = (
    "Prenons un cas concret. Julie facture 320 euros la journee et remplit "
    "11 jours par mois. Le probleme n'est pas son tarif, c'est l'absence de "
    "systeme derriere. "
)


# Combien de critiques editoriales ont deja ete rendues, par section. Remis a
# zero par « atelier.isoler » : un module de test qui herite du compteur d'un
# autre verrait une premiere critique deja clemente.
_CRITIQUES: dict = {}


def reinitialiser() -> None:
    _CRITIQUES.clear()


def _premiere_critique(invite: str) -> bool:
    """Vrai la premiere fois qu'on critique CETTE section."""
    intitule = ""
    if "intitule : «" in invite:
        intitule = invite.split("intitule : «", 1)[1].split("»", 1)[0].strip()
    compte = _CRITIQUES.get(intitule, 0)
    _CRITIQUES[intitule] = compte + 1
    return compte == 0


# Aucun n'est contenu dans un autre : la chaine ecarterait le plus court.
_FRUITS = ("pomme", "poire", "cerise", "fraise", "banane", "citron", "orange",
           "mangue", "abricot", "prune", "figue", "melon", "kiwi", "raisin",
           "myrtille", "framboise", "groseille", "noisette", "amande", "pêche",
           "crème brûlée", "châtaigne", "clémentine", "pastèque", "ananas",
           "grenade", "papaye", "goyave", "litchi", "datte")


def _combien(invite: str, defaut: int) -> int:
    for motif in (r"LONGUEUR\s*:\s*(\d+)",
                  r"de\s+(\d+)\s+(?:prompts|publications|outils|idees|fiches|bases)",
                  r"en\s+(\d+)\s+modules", r"calendrier editorial de (\d+)",
                  r"(\d+)\s+scenes qui livrent",
                  r"systeme de (\d+) bases",
                  r"sequence de\s+(\d+)\s+e-mails",
                  r"en\s+(\d+)\s+blocs courts",
                  r"Ecris\s+(\d+)\s+questions",
                  r"Ecris\s+(\d+)\s+cartes de revision",
                  r"Prepare\s+(\d+)\s+grilles de mots meles",
                  # Sans ces deux-la, le simulateur rendait toujours sa
                  # valeur par defaut : sept recits quand le test en demandait
                  # trois, et une carte de douze sections quand on en voulait
                  # vingt. Le test passait — il n'exercait simplement pas ce
                  # qu'il croyait.
                  r"RECUEIL de\s+(\d+)\s+nouvelles",
                  r"FEUILLETON en\s+(\d+)\s+episodes",
                  r"en\s+(\d+)\s+doubles-pages",
                  r"sections numerotees de 1 a\s+(\d+)"):
        trouve = re.search(motif, invite, re.IGNORECASE)
        if trouve:
            return int(trouve.group(1))
    return defaut


def _texte_markdown() -> str:
    return (
        "Un paragraphe d'accroche qui plante le decor. " + CORPS + "\n\n"
        "## Le principe de base\n\n" + CORPS + CORPS + "\n\n"
        "1. Listez vos trois derniers clients.\n"
        "2. Calculez votre taux journalier reel.\n"
        "3. Supprimez l'offre la moins rentable.\n\n"
        "### Un exemple chiffre\n\n"
        "Avec 12 jours factures a 450 euros, le chiffre d'affaires mensuel "
        "atteint 5 400 euros.\n\n"
        "> Ce qui se mesure s'ameliore.\n\n"
        "**A retenir :** Choisissez une seule audience. Mesurez une metrique."
    )


def _beat_de_scene(beats, index: int, total: int) -> str:
    """Repartit les beats : declencheur tot, climax puis resolution a la fin."""
    if index == 0:
        return "situation"
    if index == 1:
        return "declencheur"
    if index == total - 1:
        return "resolution"
    if index == total - 2:
        return "climax"
    milieu = beats[2:-2] or ["complication"]
    return milieu[(index - 2) % len(milieu)]


def _texte_scene() -> str:
    """De la prose, pas du guide : ni sous-titre ni liste, et des noms propres.

    Le controle de continuite compte les personnages nommes : un texte de
    remplissage anonyme ferait echouer chaque scene pour « aucun personnage de
    la bible ».
    """
    return (
        "Camille Renard poussa la porte du depot. Le froid entrait par la "
        "verriere cassee, comme chaque hiver depuis trente ans.\n\n"
        "Hakim Oussaid l'attendait pres du quai deux, un dossier sous le bras. "
        "Il ne s'assit pas.\n\n"
        "« Sept jours, dit-il. Je n'y peux rien. »\n\n"
        "Elle regarda la motrice. Elle connaissait le bruit de ce moteur mieux "
        "que la voix de sa fille. Dehors, Lucie Renard attendait dans la "
        "voiture, moteur allume, et klaxonna une fois.\n\n"
        "Camille posa la main sur la tole glacee. Elle ne demanda rien. Elle "
        "n'avait jamais rien demande, et c'etait exactement le probleme.\n\n"
        "« Je conduirai le dernier », dit-elle enfin.\n\n"
        "Hakim Oussaid hocha la tete et nota quelque chose. La lettre restait "
        "dans la poche de Camille, toujours fermee.\n"
    )


def _code(invite: str) -> str:
    """Code reellement valide : le verificateur doit avoir quelque chose a valider.

    Le nom du fichier demande est extrait de la consigne, pas cherche n'importe
    ou dans l'invite : celle-ci contient aussi les fichiers deja ecrits, et une
    correspondance approximative renverrait du HTML pour un fichier .js.
    """
    import re as _re

    trouve = (_re.search(r"Ecris le fichier « ([^»]+) »", invite)
              or _re.search(r"FICHIER : (\S+)", invite))
    demande = trouve.group(1).strip() if trouve else ""
    modeles = {
        "outil.py": CODE_OUTIL,
        "test_outil.py": CODE_TESTS,
        "index.html": CODE_HTML,
        "manifest.json": CODE_MANIFESTE,
        "popup.html": ('<!doctype html>\n<html lang="fr"><head>'
                       '<meta charset="utf-8"/><title>Extension</title></head>'
                       '<body><h1>Compteur</h1><p id="total">0</p>'
                       '<script src="popup.js"></script></body></html>\n'),
        "popup.js": ('const zone = document.getElementById("total");\n'
                     'zone.textContent = "pret";\n'),
        "contenu.js": ('const compter = (texte) => texte.trim().split(/\\s+/).length;\n'
                       'console.log(compter(document.body.innerText));\n'),
    }
    return modeles.get(demande, "const pret = true;\nconsole.log(pret);\n")


def simulateur(messages, role):
    """Signature attendue par llm.definir_simulateur : (messages, role) -> texte."""
    invite = messages[-1]["content"]
    bas = invite.lower()

    # --- demarrage a froid : par ou commencer quand l'atelier est vide -----
    if '"pourquoi_maintenant"' in invite:
        return json.dumps({"domaines": [
            {"domaine": "la facturation des independants",
             "acheteur": "un freelance qui vient de depasser le seuil",
             "pourquoi_maintenant": "le regime a change en janvier"},
            {"domaine": "le potager en bac sur balcon",
             "acheteur": "un citadin sans jardin",
             "pourquoi_maintenant": "la saison commence"},
            {"domaine": "la reprise de course a pied apres 40 ans",
             "acheteur": "quelqu'un qui a arrete dix ans",
             "pourquoi_maintenant": "la rentree"},
        ]}, ensure_ascii=False)

    # --- l'usine decide les reglages que personne n'a remplis -------------
    #
    # Sans ce cas, le simulateur rendait une reponse illisible, l'usine
    # journalisait honnetement « n'a pas pu decider », et les tests
    # n'exercaient que le chemin degrade — celui ou rien n'est decide.
    if "Ces reglages n'ont pas ete choisis" in invite:
        # On repond avec une valeur PRISE DANS LA LISTE que l'invite propose :
        # repondre a cote ferait passer pour un defaut du modele ce qui est un
        # defaut du simulateur.
        reponse = {}
        for ligne in invite.splitlines():
            if not ligne.startswith("- "):
                continue
            nom = ligne[2:].split(" (", 1)[0].strip()
            attendu = ligne.split("(", 1)[1].split(")", 1)[0] if "(" in ligne else ""
            if attendu.startswith("un de : "):
                # « methode (Méthode pas à pas) » : la cle, sans son etiquette.
                premier = ligne.split("un de : ", 1)[1].split(",")[0]
                reponse[nom] = premier.split(" (", 1)[0].strip()
            elif attendu == "un entier":
                reponse[nom] = 7
            elif attendu == "oui ou non":
                reponse[nom] = "non"
            else:
                reponse[nom] = "decide par le simulateur"
        return json.dumps(reponse, ensure_ascii=False)

    # --- la lecture en lecteur de fiction --------------------------------
    #
    # Sans ce cas, le simulateur rendait un objet sans rapport et la lecture
    # revenait « 0 decrochage » quoi qu'il arrive : le test passait en
    # n'exercant que le chemin ou le lecteur n'a rien a dire. Un simulateur
    # qui ne sait pas repondre ne rend pas un test moins bon, il le rend
    # faux.
    if '"aurait_tourne_la_page"' in invite:
        return json.dumps({
            "aurait_tourne_la_page": True,
            "note_envie_de_lire": 7.5,
            "decrochages": [{"section": "Scene modele 2",
                             "passage": "Il comprit alors que tout etait joue",
                             "pourquoi": "on me dit ce que je devrais deviner"}],
            "fin_devinee": "des la scene 2",
            "personnages_confondus": ["Camille et Lucie"],
            "promesses_non_payees": ["la lettre fermee n'est jamais ouverte"],
        }, ensure_ascii=False)

    # --- cartes de revision : un lot, sans repeter les rectos deja ecrits -
    #
    # Les rectos sont numerotes a partir de ce que l'invite dit deja ecrit :
    # un simulateur qui rendrait toujours les memes cartes ferait ecarter
    # tout le deuxieme lot comme doublon, et le test n'exercerait que ca.
    if '"recto"' in invite and '"verso"' in invite:
        combien = _combien(invite, 12)
        deja = invite.count(" | ") + (1 if "DEJA ECRITES" in invite else 0)
        return json.dumps({"cartes": [
            {"recto": "Que veut dire la notion numero {} ?".format(deja + n),
             "verso": "La notion {} designe ce qu'on applique quand le cas "
                      "se presente, avec un exemple court.".format(deja + n),
             "theme": "Bases" if n % 2 else "Pratique"}
            for n in range(1, combien + 1)]}, ensure_ascii=False)

    # --- mots meles : des listes par sous-theme ------------------------------
    #
    # De vrais mots, accentues et composes (« crème brûlée ») : la chaine doit
    # les ramener a des lettres. Les sous-themes sont numerotes a partir de
    # ceux que l'invite dit deja pris, comme les cartes, sans quoi le second
    # lot serait ecarte entier comme doublon.
    if '"grilles"' in invite and '"mots"' in invite:
        combien = _combien(invite, 8)
        trouve = re.search(r"'mots' : (\d+) mots", invite)
        par_grille = int(trouve.group(1)) if trouve else 12
        deja = invite.count(" | ") + (1 if "DEJA PRIS" in invite else 0)
        return json.dumps({"grilles": [
            {"theme": "Sous-thème {}".format(deja + n),
             "mots": [_FRUITS[(7 * (deja + n) + k) % len(_FRUITS)]
                      for k in range(par_grille)]}
            for n in range(1, combien + 1)]}, ensure_ascii=False)

    # --- feuilleton : le « Precedemment », ecrit POUR LE LECTEUR ---------
    #
    # Sans ce cas, le simulateur rendait de la prose de guide pratique en
    # guise de rappel, et le controle du feuilleton signalait a chaque test
    # de fumee que le rappel ne nommait personne. Il avait raison — mais le
    # test n'exercait alors que le chemin degrade.
    if "precedemment" in bas and "rappel" in bas:
        return ("Camille Renard avait pousse la porte du depot, et Hakim "
                "Oussaid l'attendait avec une date : sept jours. Lucie "
                "Renard, elle, klaxonnait dehors sans descendre de voiture. "
                "Camille n'avait rien demande — elle n'avait jamais rien "
                "demande. Restait la question que personne n'osait poser : "
                "qui a signe l'ordre de fermeture ?")

    # --- feuilleton : un arc dont chaque episode ouvre une question ------
    if '"suspens"' in invite and '"episodes"' in invite:
        combien = _combien(invite, 8)
        return json.dumps({
            "titre": "Le dernier train",
            "promesse": "Sept jours avant la fermeture, et personne ne "
                        "veut le dire.",
            "episodes": [
                {"titre": "Jour {}".format(rang),
                 "question": "que cache le depot ce jour-la ?",
                 "evenement": "Camille avance d'un cran",
                 # Le dernier episode referme l'arc : lui reclamer un suspens
                 # reviendrait a reclamer une saison de plus.
                 "suspens": ("" if rang == combien
                             else "qui a signe l'ordre de fermeture ?")}
                for rang in range(1, combien + 1)],
        }, ensure_ascii=False)

    # --- conte jeunesse : des doubles-pages, pas des chapitres -----------
    #
    # Les phrases sont VOLONTAIREMENT courtes : un simulateur qui rendrait de
    # la prose d'adulte ferait echouer le controle d'age a chaque test de
    # fumee, et on finirait par le desactiver — alors que c'est lui la raison
    # d'etre de la chaine.
    if '"illustration"' in invite and '"pages"' in invite:
        combien = _combien(invite, 16)
        moments = [
            ("Le petit ours dort.", "un ourson roule en boule"),
            ("Dehors, la neige tombe.", "des flocons devant une fenetre"),
            ("Il ouvre un oeil.", "un oeil brillant dans le noir"),
            ("La foret est blanche.", "des sapins sous la neige"),
            ("Une trace file vers l'eau.", "des empreintes au sol"),
            ("L'ours suit la trace.", "un ourson de dos qui marche"),
            ("Au bout, un renard.", "un renard roux assis"),
            ("Le renard a froid.", "un renard qui tremble"),
        ]
        return json.dumps({
            "titre": "Le petit ours et la neige",
            "heros": "un ourson curieux",
            "pages": [
                {"numero": rang,
                 "texte": moments[(rang - 1) % len(moments)][0],
                 "illustration": moments[(rang - 1) % len(moments)][1]}
                for rang in range(1, combien + 1)],
        }, ensure_ascii=False)

    # --- recueil : des premisses qui DIFFERENT ---------------------------
    #
    # Le piege que ce cas doit eviter : un simulateur qui rendrait sept fois
    # la meme premisse ferait echouer le controle de variete a chaque test de
    # fumee, et on finirait par le desactiver — alors que c'est lui la raison
    # d'etre de la chaine. Les premisses ci-dessous different par qui les
    # vit, par l'epoque et par la fin.
    if '"premisse"' in invite and '"registre"' in invite:
        combien = _combien(invite, 7)
        graines = [
            ("Le quai numero deux", "Un cheminot decouvre que la ligne ferme "
             "dans sept jours et cache la lettre a sa fille.",
             "un cheminot", "sobre", "amere"),
            ("La couturiere de Roubaix", "Une couturiere retrouve la robe "
             "qu'elle avait cousue pour un mariage qui n'a pas eu lieu.",
             "une couturiere", "tendre", "ouverte"),
            ("Ce que la mer rend", "Un adolescent trouve un carnet dans une "
             "epave et reconnait l'ecriture de son grand-pere.",
             "un adolescent", "mysterieux", "heureuse"),
            ("Le dernier locataire", "Une proprietaire refuse de vendre "
             "l'immeuble tant que le vieux du troisieme y vit.",
             "une proprietaire", "ironique", "tragique"),
            ("Trois minutes de retard", "Une infirmiere rejoue la nuit ou "
             "elle est arrivee apres l'heure.", "une infirmiere",
             "tendu", "amere"),
            ("La boulangerie ferme a onze heures", "Un boulanger apprend a "
             "lire a soixante-deux ans, en secret.", "un boulanger",
             "lumineux", "heureuse"),
            ("Les cles du presbytere", "Une archiviste doit bruler des "
             "registres qu'elle vient de passer dix ans a classer.",
             "une archiviste", "grave", "ouverte"),
        ]
        return json.dumps({
            "titre": "Ce que le nord garde",
            "fil": "Sept personnes, une meme ville, et ce qu'elles n'ont "
                   "jamais dit.",
            "recits": [
                {"titre": t, "premisse": p, "qui": q, "registre": r,
                 "fin": f, "place": "rang {}".format(rang + 1)}
                for rang, (t, p, q, r, f) in enumerate(
                    (graines * 3)[:combien])],
        }, ensure_ascii=False)

    # --- livre-jeu : une carte VALIDE, sinon le test n'exerce rien --------
    #
    # Sans ce cas, le simulateur ne savait pas repondre a la demande de carte
    # et rendait du vide. La chaine elaguait donc un graphe vide, ecrivait
    # zero section, et le test de fumee declarait « abouti » un livre de zero
    # page. Un simulateur qui ne sait pas repondre ne rend pas un test
    # moins bon : il le rend faux.
    if '"vers"' in invite and '"fin"' in invite:
        combien = _combien(invite, 12)
        # Une chaine lineaire avec un embranchement par section, et deux fins
        # a la queue. Volontairement SIMPLE et JUSTE : ce que le test doit
        # exercer, c'est la chaine, pas la capacite du simulateur a se
        # tromper. Les cartes fausses sont exercees par les tests d'unite,
        # qui les fabriquent a la main.
        sections = []
        derniere, avant_derniere = combien, combien - 1
        for numero in range(1, combien + 1):
            if numero in (derniere, avant_derniere):
                sections.append({
                    "numero": numero, "intitule": "l'issue {}".format(numero),
                    "fin": True,
                    "issue": "heureuse" if numero == derniere else "malheureuse",
                    "choix": []})
                continue
            suivant = min(numero + 1, avant_derniere)
            sections.append({
                "numero": numero, "intitule": "le couloir {}".format(numero),
                "fin": False,
                "choix": [{"texte": "Avancer", "vers": suivant},
                          {"texte": "Rebrousser chemin", "vers": derniere}]})
        return json.dumps({"sections": sections}, ensure_ascii=False)

    # --- sequence e-mail : le plan, puis chaque message --------------------
    if '"messages"' in invite and '"angle"' in invite:
        combien = _combien(invite, 7)
        return json.dumps({"messages": [
            {"objet": "Ce que personne ne vous dit au depart",
             "angle": "poser le probleme avant de proposer quoi que ce soit",
             "action": "aucune" if rang == 1 else "repondre a ce message"}
            for rang in range(1, combien + 1)]}, ensure_ascii=False)
    if '"post_scriptum"' in invite:
        return json.dumps({
            "objet": "Ce que personne ne vous dit au depart",
            "apercu": "trois minutes de lecture, une idee a garder",
            "corps": _texte_markdown().replace("#", "").strip(),
            "post_scriptum": "Repondez-moi : je lis tout.",
        }, ensure_ascii=False)

    # --- memo : des blocs courts, pas de la prose --------------------------
    if '"blocs"' in invite and '"lignes"' in invite:
        combien = _combien(invite, 8)
        genres = ("liste", "etapes", "reperes", "tableau")
        return json.dumps({"blocs": [
            {"titre": "Repere {}".format(rang),
             "genre": genres[(rang - 1) % len(genres)],
             "lignes": ["Verifier le seuil avant de facturer",
                        "Garder une trace datee de chaque envoi",
                        "Relancer au huitieme jour, pas avant"]}
            for rang in range(1, combien + 1)]}, ensure_ascii=False)

    # --- quiz autonome : questions, propositions, corrige ------------------
    # La formation produit DEJA un quiz, avec la meme cle « propositions ».
    # Sans ce discriminant, cette branche repondait a sa place et la chaine
    # « formation » livrait zero question — deux cas qui partagent une invite
    # partagent aussi la reponse du simulateur.
    if '"propositions"' in invite and "ne suit aucune formation" in bas:
        combien = _combien(invite, 20)
        questions = []
        for rang in range(1, combien + 1):
            questions.append({
                "question": "Question {} : que verifier en premier ?".format(rang),
                "propositions": ["Le seuil legal", "La date d'envoi",
                                 "Le taux applique", "Le mode de paiement"],
                "reponse": rang % 4,
                "explication": "Le seuil conditionne tout le reste : les "
                               "trois autres reponses en decoulent, et les "
                               "verifier d'abord fait refaire le calcul.",
                "module": "Bases",
            })
        # Une question dont l'indice de bonne reponse sort du tableau : la
        # chaine doit l'ecarter plutot que livrer un corrige faux. Sans ce
        # cas, le controle qui l'ecarte ne s'executerait jamais sous test.
        questions.append({
            "question": "Question au corrige incoherent",
            "propositions": ["a", "b", "c", "d"], "reponse": 9,
            "explication": "", "module": "Bases"})
        return json.dumps({"questions": questions}, ensure_ascii=False)

    # --- le type de produit que l'usine choisit pour un sujet --------------
    if '"pourquoi"' in invite and '"type"' in invite and "se vend le mieux" in bas:
        return json.dumps({"type": "memo",
                           "pourquoi": "le sujet se consulte plus qu'il ne se lit"},
                          ensure_ascii=False)

    # --- lecture par l'audience --------------------------------------------
    if '"ce_que_je_ne_sais_toujours_pas_faire"' in invite:
        return json.dumps({
            "promesse_tenue": True,
            "note_clarte": 7.5,
            "decrochages": [
                {"section": "Chapitre modele 2",
                 "passage": "Le probleme n'est pas son tarif",
                 "pourquoi": "je ne vois pas de quel tarif on parle"}],
            "mots_non_expliques": ["taux journalier reel"],
            "ce_que_je_ne_sais_toujours_pas_faire": [
                "fixer mon propre tarif a partir de mes charges"],
        }, ensure_ascii=False)

    # --- deliberation : l'auteur conteste, le controleur tranche ------------
    if '"objections"' in invite:
        # L'auteur conteste le premier point, jamais les autres : un
        # simulateur qui contesterait tout empecherait de distinguer
        # « la deliberation marche » de « la relecture est annulee ».
        return json.dumps({"objections": [
            {"numero": 1, "raison": "cette correction demande d'inventer un "
                                    "chiffre que je ne peux pas sourcer"}]},
            ensure_ascii=False)
    if '"decisions"' in invite:
        return json.dumps({"decisions": [
            {"numero": 1, "appliquer": False,
             "motif": "l'auteur a raison : la correction ferait fabriquer une "
                      "statistique"}]}, ensure_ascii=False)

    # --- brief automatique : ce que l'usine decide quand on ne dit rien -----
    # En premier, et avant le plan : le brief demande lui aussi des
    # « sections », et une branche posee plus bas ne serait jamais atteinte.
    if '"mots_par_section"' in invite and '"niche"' in invite:
        return json.dumps({
            "audience": "Freelance en portage qui facture moins de 40 k par an",
            "ton": "pedagogue",
            "sections": _combien(invite, 9),
            "mots_par_section": 1000,
            "niche": "facturation des independants",
            "promesse": "Fixer un tarif qui tient et le defendre.",
            "pourquoi": "Sujet technique et anxiogene : ton pedagogue, "
                        "sections courtes.",
        }, ensure_ascii=False)

    # --- ebook : plan -----------------------------------------------------
    if '"chapitres"' in invite:
        n = _combien(invite, 8)
        return json.dumps({
            "titre": "Le systeme du freelance rentable",
            "sous_titre": "Facturer mieux en travaillant moins",
            "promesse": "Construire une offre claire et un canal d'acquisition fiable.",
            "lecteur_ideal": "Freelance debutant",
            "chapitres": [
                {"titre": "Chapitre modele {}".format(i + 1),
                 "objectif": "Objectif {}".format(i + 1),
                 "points": ["Point A", "Point B", "Point C"]}
                for i in range(n)
            ],
        }, ensure_ascii=False)

    # --- systeme de modeles (Notion / tableur) ------------------------------
    if '"bases"' in invite:
        n = _combien(invite, 4)
        return json.dumps({
            "titre": "Le systeme de pilotage du freelance",
            "promesse": "Quatre bases liees pour piloter son activite.",
            "bases": [
                {"nom": "Base modele {}".format(i + 1),
                 "role": "Suivre les elements {}".format(i + 1),
                 "colonnes": [
                     {"nom": "Nom", "type": "texte", "description": "Intitule"},
                     {"nom": "Statut", "type": "selection",
                      "options": ["A faire", "En cours", "Fait"],
                      "description": "Avancement"},
                     {"nom": "Echeance", "type": "date", "description": "Date limite"},
                 ],
                 "vues": [{"nom": "Cette semaine", "filtre": "Echeance < 7j",
                           "tri": "Echeance"}],
                 "exemples": [["Exemple A", "En cours", "2026-04-01"]]}
                for i in range(n)
            ],
            "mise_en_route": ["Importer les CSV", "Creer les relations"],
        }, ensure_ascii=False)

    # --- cahier imprimable --------------------------------------------------
    if '"fiches"' in invite:
        n = _combien(invite, 12)
        dispos = ["checklist", "planning", "suivi", "questions", "matrice", "notes"]
        return json.dumps({
            "titre": "Le cahier du freelance organise",
            "sous_titre": "12 fiches a imprimer",
            "promesse": "Une fiche par decision.",
            "fiches": [
                {"titre": "Fiche modele {}".format(i + 1),
                 "disposition": dispos[i % 6],
                 "consigne": "Remplissez cette fiche en debut de semaine.",
                 "elements": ["Point A", "Point B", "Point C", "Point D"],
                 "colonnes": ["Date", "Action", "Resultat"],
                 "quadrants": ["Urgent", "Important", "Delegable", "A supprimer"]}
                for i in range(n)
            ],
        }, ensure_ascii=False)

    # --- specification logicielle -------------------------------------------
    if '"fonctionnalites"' in invite and '"limites"' in invite:
        return json.dumps({
            "nom": "compteur-mots",
            "titre": "Compteur de mots en ligne de commande",
            "promesse": "Compter mots, lignes et caracteres d'un fichier texte.",
            "probleme": "Verifier la longueur d'un manuscrit sans ouvrir un traitement de texte.",
            "fonctionnalites": ["Compter les mots", "Compter les lignes",
                                "Afficher le resultat en JSON"],
            "utilisation": "python3 outil.py fichier.txt --json",
            "limites": ["Ne lit pas les PDF", "Ne corrige rien"],
        }, ensure_ascii=False)

    # --- generation de fichiers de code --------------------------------------
    if "Ecris le fichier" in invite or "CONTENU ACTUEL" in invite:
        return _code(invite)

    # --- pack de prompts : categories ------------------------------------
    if '"categories"' in invite:
        return json.dumps({
            "categories": [
                {"nom": "Strategie", "intention": "Clarifier l'offre",
                 "prompts": ["Definir son positionnement", "Choisir une niche"]},
                {"nom": "Vente", "intention": "Convertir",
                 "prompts": ["Ecrire une proposition", "Relancer un prospect"]},
            ]
        }, ensure_ascii=False)

    # --- pack de prompts : redaction d'une categorie ----------------------
    if '"prompts"' in invite and '"astuce"' in invite:
        intitules = re.findall(r"^- (.+)$", invite, re.MULTILINE) or ["Prompt"]
        return json.dumps({
            "prompts": [
                {"titre": intitule, "quand": "Au demarrage d'un projet.",
                 "prompt": "Tu es un consultant. Contexte : [VOTRE ACTIVITE]. "
                           "Objectif : {}. Reponds sous forme de tableau.".format(intitule),
                 "astuce": "Ajoutez un exemple de sortie attendue."}
                for intitule in intitules[:6]
            ]
        }, ensure_ascii=False)

    # --- formation : programme -------------------------------------------
    if '"modules"' in invite and '"livrable"' in invite:
        n = _combien(invite, 5)
        return json.dumps({
            "titre": "Formation : le systeme complet",
            "promesse": "Mettre en place un systeme d'acquisition en 30 jours.",
            "prerequis": "Aucun prerequis technique.",
            "modules": [
                {"titre": "Module modele {}".format(i + 1),
                 "objectif": "Objectif {}".format(i + 1),
                 "livrable": "Un document de synthese",
                 "notions": ["Notion A", "Notion B"],
                 "exercice": "Redigez votre fiche en 20 minutes."}
                for i in range(n)
            ],
        }, ensure_ascii=False)

    # --- formation : quiz d'auto-evaluation ---------------------------------
    if '"quiz"' in invite and '"propositions"' in invite:
        modules = re.findall(r"^- (.+?) — objectif", invite, re.MULTILINE)
        questions = []
        for titre in modules or ["Module modele 1"]:
            for rang in range(2):
                questions.append({
                    "module": titre,
                    "question": "Que faire en premier dans « {} » ({}) ?".format(
                        titre, rang + 1),
                    "propositions": ["Ouvrir un tableur et tout lister",
                                     "Poser l'objectif avant d'agir",
                                     "Demander a un collegue"],
                    "reponse": 1,
                    "explication": "L'objectif decide de tout le reste : sans "
                                   "lui, la liste ne sert a rien.",
                })
        return json.dumps({"quiz": questions}, ensure_ascii=False)

    # --- formation : script de narration -------------------------------------
    if "script de narration" in bas:
        return (
            "Vous avez deja perdu une matinee sur ce probleme. [PAUSE] "
            "Aujourd'hui, on le regle en trois gestes.\n\n"
            "Premier geste : vous posez l'objectif avant d'ouvrir quoi que ce "
            "soit. [INSISTER] Avant. Pas pendant.\n\n"
            "Deuxieme geste : vous notez le chiffre de depart. Julie facturait "
            "trois cent vingt euros la journee. Elle ne le savait pas.\n\n"
            "Troisieme geste : vous choisissez ce que vous arretez. [PAUSE]\n\n"
            "Dans le module suivant, on regarde ce que cela change sur un "
            "mois complet.\n")

    # --- sequences d'e-mails ---------------------------------------------
    if '"emails"' in invite:
        return json.dumps({
            "emails": [
                {"jour": i, "objet": "Objet {}".format(i),
                 "preheader": "Apercu {}".format(i),
                 "corps": "Bonjour,\n\n" + CORPS + "\n\nA demain.",
                 "action": "Ouvrez le module {}".format(i),
                 "cta": "Commencer maintenant"}
                for i in range(1, 6)
            ]
        }, ensure_ascii=False)

    # --- boite a outils : sommaire ---------------------------------------
    if '"outils"' in invite:
        n = _combien(invite, 6)
        types = ["checklist", "modele", "tableau"]
        return json.dumps({
            "titre": "La boite a outils du freelance",
            "promesse": "Dix documents pour decider vite.",
            "outils": [
                {"nom": "Outil modele {}".format(i + 1), "type": types[i % 3],
                 "quand": "Avant chaque nouveau client.",
                 "resultat": "Une decision ecrite."}
                for i in range(n)
            ],
        }, ensure_ascii=False)

    # --- boite a outils : contenu d'un outil ------------------------------
    if '"colonnes"' in invite:
        return json.dumps({
            "intro": "Ce tableau suit vos prospects.",
            "colonnes": ["Prospect", "Canal", "Date", "Statut"],
            "exemples": [["Societe A", "LinkedIn", "12/03", "En cours"],
                         ["Societe B", "E-mail", "14/03", "Gagne"]],
            "conseils": ["Mettez a jour chaque vendredi."],
        }, ensure_ascii=False)
    # --- relecture d'ensemble : contradictions entre sections ----------------
    if '"incoherences"' in invite:
        titres = re.findall(r"^### (.+)$", invite, re.MULTILINE)
        if len(titres) < 2:
            return json.dumps({"incoherences": []}, ensure_ascii=False)
        return json.dumps({"incoherences": [
            {"sections": titres[:2],
             "probleme": "les deux sections donnent un tarif de depart different",
             "gravite": "majeur"},
            {"sections": ["Un chapitre qui n'existe pas"],
             "probleme": "cite une section absente du produit",
             "gravite": "mineur"},
            {"sections": titres[:1], "probleme": "", "gravite": "mineur"},
        ]}, ensure_ascii=False)

    if '"sections"' in invite:
        return json.dumps({
            "intro": "Modele a completer.",
            "sections": [{"titre": "En-tete", "contenu": "Bonjour [PRENOM],"},
                         {"titre": "Corps", "contenu": "Voici [OFFRE]."}],
            "conseils": ["Personnalisez la premiere phrase."],
        }, ensure_ascii=False)
    if '"points"' in invite:
        return json.dumps({
            "intro": "A parcourir avant chaque envoi.",
            "points": ["Verifier le nom du client", "Relire le tarif",
                       "Confirmer le delai", "Joindre les conditions"],
            "conseils": ["Imprimez cette page."],
        }, ensure_ascii=False)

    # --- reseaux sociaux : calendrier -------------------------------------
    if '"publications"' in invite:
        n = _combien(invite, 10)
        return json.dumps({
            "publications": [
                {"jour": i + 1, "angle": "retour d'experience",
                 "sujet": "Sujet {}".format(i + 1),
                 "accroche": "Ce que j'aurais aime savoir plus tot.",
                 "objectif": "engagement"}
                for i in range(n)
            ]
        }, ensure_ascii=False)

    # --- reseaux sociaux : posts ------------------------------------------
    if '"posts"' in invite:
        jours = re.findall(r"^(\d+)\. angle=", invite, re.MULTILINE) or ["1"]
        return json.dumps({
            "posts": [
                {"jour": int(j), "texte": "Accroche forte.\n\n" + CORPS,
                 "hashtags": "#freelance #independant",
                 "visuel": "minimal blue abstract shapes"}
                for j in jours
            ]
        }, ensure_ascii=False)

    # --- idees de produits -------------------------------------------------
    if '"idees"' in invite:
        n = _combien(invite, 12)
        types = ["ebook", "prompts", "formation", "outils", "social"]
        return json.dumps({
            "idees": [
                {"titre": "Idee modele {}".format(i + 1), "type": types[i % 5],
                 "probleme": "Un probleme precis et couteux.",
                 "acheteur": "Un independant de 2 a 5 ans d'anciennete.",
                 "promesse": "Un resultat mesurable en 30 jours.",
                 "prix_eur": 19 + i, "difficulte": "moyenne",
                 "concurrence": "moyenne",
                 "angle_differenciant": "Un angle operationnel, pas theorique.",
                 "premier_canal": "Un groupe de discussion specialise."}
                for i in range(n)
            ]
        }, ensure_ascii=False)

    # --- critique editoriale ------------------------------------------------
    if '"points_forts"' in invite:
        # Premiere passe severe, passes suivantes clementes : la boucle doit
        # pouvoir converger et s'arreter d'elle-meme.
        #
        # On compte les critiques par section plutot que de chercher une
        # marque dans le texte. La marque etait posee par le RESIVEUR, or le
        # controle local passe par lui AVANT la relecture editoriale : la
        # toute premiere critique d'une section voyait donc deja un texte
        # « corrige » et sortait clemente. Consequence : la deliberation
        # entre agents n'etait jamais atteinte, et aucun test de bout en
        # bout ne pouvait la voir.
        severe = _premiere_critique(invite)
        if severe:
            return json.dumps({
                "note": 6.0,
                "points_forts": ["Structure claire"],
                "problemes": [
                    {"passage": "Prenons un cas concret.",
                     "probleme": "Ouverture trop generique.",
                     "gravite": "majeur",
                     "correction": "Remplacer par une situation datee et chiffree."},
                    {"passage": "5 400 euros",
                     "probleme": "Chiffre presente sans contexte.",
                     "gravite": "mineur",
                     "correction": "Preciser qu'il s'agit d'un exemple."},
                ],
                "verdict": "A retravailler.",
            }, ensure_ascii=False)
        return json.dumps({
            "note": 8.5, "points_forts": ["Exemples concrets"],
            "problemes": [], "verdict": "Publiable.",
        }, ensure_ascii=False)

    # --- revision : renvoyer le texte soumis, marque comme corrige ----------
    if "CORRECTIONS A APPLIQUER" in invite:
        for ouverture in ("--- TEXTE ACTUEL ---", "--- TEXTE ---"):
            if ouverture in invite:
                origine = invite.split(ouverture, 1)[1].split("--- FIN ---")[0]
                # Le simulateur produit un texte varie : sans cela, le controle
                # local signalerait a juste titre des phrases trop uniformes et
                # la boucle ne convergerait jamais.
                return ("deja corrige\n" + origine.strip()
                        + "\n\nUn dernier point. Il tient en une ligne, et il "
                          "change souvent tout le reste du raisonnement que vous "
                          "venez de lire attentivement.")
        return "deja corrige"

    # --- controle avant mise en vente ---------------------------------------
    if '"a_corriger_avant_vente"' in invite:
        return json.dumps({
            "pret": True, "note_globale": 8.2,
            "coherence_promesse": "La promesse est tenue.",
            "risques": [], "prix_juste": "correct",
            "a_corriger_avant_vente": ["Relire les chiffres."],
            "verdict": "Pret pour la mise en vente.",
        }, ensure_ascii=False)

    # --- variantes de titres -------------------------------------------------
    if '"pourquoi"' in invite and '"angle"' in invite:
        import re as _re
        angles = _re.findall(r"angle . ([a-z]+) .", invite) or ["benefice"]
        modeles = {
            "benefice": "Facturer mieux en travaillant moins chaque semaine",
            "methode": "Le systeme en 7 etapes du freelance rentable",
            "probleme": "Pourquoi votre agenda se vide apres chaque grosse mission",
            "contraste": "Baisser ses tarifs ne remplit pas un agenda",
            "audience": "Freelance depuis deux ans, toujours a court de clients",
            "delai": "Remplir son agenda en 30 jours sans demarchage froid",
            "question": "Combien vaut reellement votre journee de travail",
            "preuve": "Douze jours factures, trois canaux, zero demarchage",
        }
        return json.dumps({"titres": [
            {"angle": a, "titre": modeles.get(a, "Titre " + a),
             "pourquoi": "Repond a une attente precise du lecteur."}
            for a in angles
        ]}, ensure_ascii=False)

    # --- fiche de vente ----------------------------------------------------
    if '"prix_conseille"' in invite:
        return json.dumps({
            "titres": ["Titre A", "Titre B", "Titre C", "Titre D", "Titre E"],
            "accroche": "La methode complete, en un seul dossier.",
            "description": "## Ce que vous obtenez\n\nUn systeme applicable.",
            "benefices": ["Gagner du temps", "Facturer plus", "Choisir ses clients"],
            "contenu_livre": ["Un PDF de 80 pages", "Un EPUB", "Des modeles CSV"],
            "pour_qui": ["Freelances", "Consultants", "Artisans du numerique"],
            "pas_pour_qui": ["Ceux qui cherchent un gain immediat"],
            "objections": [{"objection": "Est-ce pour les debutants ?",
                            "reponse": "Oui, aucun prerequis."}],
            "mots_cles": ["freelance", "tarif", "prospection"],
            "prix_conseille": {"bas": 9, "cible": 29, "haut": 49,
                               "justification": "Volume et specificite."},
            "garantie": "Remboursement sous 14 jours.",
        }, ensure_ascii=False)

    # --- fiction : la bible -------------------------------------------------
    if '"personnages"' in invite and '"premisse"' in invite:
        return json.dumps({
            "titre": "Le dernier train de Roubaix",
            "genre": "drame social",
            "premisse": "Un cheminot decouvre que la ligne qu'il conduit "
                        "depuis trente ans ferme dans une semaine.",
            "cadre": {"lieu": "Roubaix, le depot", "epoque": "aujourd'hui",
                      "regles": ["La ligne ferme dans sept jours"]},
            "personnages": [
                {"nom": "Camille Renard", "role": "protagoniste",
                 "desir": "sauver la ligne", "defaut": "ne demande jamais d'aide",
                 "voix": "phrases courtes, jamais de plainte"},
                {"nom": "Hakim Oussaid", "role": "antagoniste",
                 "desir": "fermer le depot proprement",
                 "defaut": "confond fermete et durete",
                 "voix": "vocabulaire de gestion, poli"},
                {"nom": "Lucie Renard", "role": "secondaire",
                 "desir": "que sa mere parte a temps",
                 "defaut": "impatiente", "voix": "directe, coupe la parole"},
            ],
            "enjeu": "Camille perd le depot et la seule chose qui la tenait.",
            "fin_visee": "Camille conduit le dernier train et accepte l'aide "
                         "de sa fille.",
        }, ensure_ascii=False)

    # --- fiction : la grille de beats ---------------------------------------
    if '"scenes"' in invite and '"beat"' in invite:
        n = _combien(invite, 6)
        beats = ["situation", "declencheur", "engagement", "complication",
                 "crise", "climax", "resolution"]
        distribution = ["Camille Renard", "Hakim Oussaid", "Lucie Renard"]
        # Les noms de fils reprennent des mots que « _texte_scene » emploie
        # vraiment : le controle verifie qu'une scene PARLE du fil qu'elle
        # doit payer, et un simulateur qui l'ignorerait fabriquerait un
        # defaut au lieu d'exercer le controle.
        matiere = ["la lettre non ouverte", "la motrice du depot",
                   "le quai deux", "la porte du hangar", "la voiture de Lucie"]
        fils = []
        combien = max(1, min(10, round(n / 4)))
        for rang in range(combien):
            # Etales sur le recit : poses dans la premiere moitie, payes dans
            # la seconde. Les grouper au debut laisserait la fin sans rien a
            # resoudre, et le milieu sans rien a porter.
            pose = max(1, min(n - 1, 1 + round(rang * (n / 2 - 1) / max(1, combien))))
            paye = max(pose + 1, min(n, round(n / 2) + round(
                (rang + 1) * (n / 2) / max(1, combien))))
            fils.append({
                "nom": matiere[rang % len(matiere)],
                "pose": pose,
                "paye": paye,
                "quoi": "ce que le lecteur voit sans comprendre {}".format(rang),
                "paiement": "ce que cela revelait {}".format(rang),
            })
        arcs = [
            {"personnage": "Camille Renard", "depart": "refuse toute aide",
             "bascule": max(1, n - 1), "arrivee": "accepte l'aide de sa fille"},
            {"personnage": "Hakim Oussaid", "depart": "applique le reglement",
             "bascule": max(1, n // 2), "arrivee": "assume une decision"},
        ]
        # Intrigues secondaires : seulement quand le recit a la place. Leur
        # nom reprend des mots que « _texte_scene » emploie, comme les fils :
        # le controle verifie que la scene de resolution en PARLE.
        intrigues = []
        if n >= 10:
            combien = 1 if n < 18 else 2
            for rang in range(combien):
                debut = 2 + rang
                pas = max(2, (n - debut) // 3)
                portantes = [min(n, debut + pas * etape) for etape in range(3)]
                intrigues.append({
                    "nom": ["la voiture de Lucie", "la porte du hangar"][rang],
                    "personnage": ["Lucie Renard", "Hakim Oussaid"][rang],
                    "enjeu": "ce qui se joue a cote de l'histoire {}".format(rang),
                    "scenes": sorted(set(portantes)),
                    "resolution": "elle se termine par un depart {}".format(rang),
                })
        return json.dumps({
            "beats": [{"nom": nom, "evenement": "Evenement du beat {}".format(nom)}
                      for nom in beats],
            "fils": fils,
            "arcs": arcs,
            "intrigues": intrigues,
            "scenes": [
                {"titre": "Scene modele {}".format(i + 1),
                 # Les trois tournants indispensables sont places aux bons
                 # endroits : un simulateur qui les oublierait fabriquerait un
                 # defaut de continuite au lieu de l'exercer.
                 "beat": _beat_de_scene(beats, i, n),
                 "lieu": "le depot",
                 "personnages": [distribution[i % 3], distribution[(i + 1) % 3]],
                 "point_de_vue": "Camille Renard",
                 "objectif": "Obtenir un sursis {}".format(i + 1),
                 "obstacle": "Le reglement",
                 "pivot": "Camille apprend le detail {}".format(i + 1)}
                for i in range(n)
            ],
        }, ensure_ascii=False)

    # --- fiction : mise a jour du resume roulant -----------------------------
    if "reecris l'etat complet" in bas:
        # La memoire doit VARIER d'une scene a l'autre : un resume fige ferait
        # passer le controle de continuite pour vert alors qu'il doit signaler
        # une histoire qui n'avance pas.
        etapes = [
            "Camille Renard apprend la fermeture du depot de Roubaix ; elle "
            "n'en parle a personne.",
            "Hakim Oussaid refuse le sursis ; Camille cache la convocation "
            "dans sa poche.",
            "Lucie Renard trouve la lettre et comprend que sa mere ment "
            "depuis une semaine.",
            "La motrice tombe en panne ; les cheminots votent l'occupation "
            "du quai deux.",
            "L'occupation echoue, Camille perd son habilitation, Hakim "
            "signe l'arrete de fermeture.",
            "Camille obtient de conduire le dernier convoi ; Lucie monte "
            "avec elle dans la cabine.",
            "Le depot ferme ; Camille accepte l'aide de sa fille et quitte "
            "Roubaix sans regret.",
        ]
        # Le resume doit reellement progresser d'une scene a l'autre : le
        # controle de continuite compare le vocabulaire, et un etat qui ne
        # differe que par un chiffre ne bouge pas. Un simulateur qui figerait
        # la memoire ferait echouer un controle qui a raison.
        # Une nouvelle peut compter plus de scenes que d'etapes ci-dessus :
        # au-dela, l'etat continue d'avancer par un detail en suspens, sans
        # quoi le simulateur figerait la memoire et ferait echouer un
        # controle qui aurait raison.
        suspens = [
            "La convocation reste sur la table.",
            "Le syndicat promet une reponse mardi.",
            "Un journaliste local rode devant le portail.",
            "La sous-prefecture repousse l'audience.",
            "Les rails du quai trois sont demontes.",
            "Un ancien collegue revient de Lille.",
        ]
        # Fermeture d'une partie : la memoire hierarchique demande le resume
        # d'un bloc entier, pas l'etat apres une scene. Il doit differer d'une
        # partie a l'autre, sinon rien ne distinguerait les trois quarts d'un
        # livre dans l'invite de la derniere scene.
        partie = re.search(r"TEXTE A INTEGRER — Partie (\d+)", invite)
        if partie:
            numero = int(partie.group(1))
            # Sans prefixe « Partie N » : la mise en forme est le travail de
            # la memoire, et le modele ne repond que le texte de l'etat.
            return ("les evenements de ce bloc ont mene Camille Renard du "
                    "depot {} jusqu'au quai {}, et Hakim Oussaid y a tenu la "
                    "position {}.".format(numero, numero + 1, numero))
        trouve = re.search(r"Scene modele (\d+)", invite)
        rang = int(trouve.group(1)) - 1 if trouve else invite.count("Apres ")
        rang = max(rang, 0)
        etat = etapes[min(rang, len(etapes) - 1)]
        if rang >= len(etapes):
            etat = "{} {}".format(etat, suspens[rang % len(suspens)])
        return etat

    # --- fiction : le texte d'une scene --------------------------------------
    #
    # « la section » y est jointe pour le livre-jeu : sans elle, le
    # simulateur rendait de la prose de guide pratique — listes a puces,
    # « A retenir », chiffres d'affaires — dans un recit a embranchements. Le
    # test de fumee mesurait alors la qualite d'un texte qu'aucune chaine de
    # fiction ne produirait, ce qui ne prouve rien dans un sens ni dans
    # l'autre.
    if "ecris la scene" in bas or "ecris la section" in bas:
        return _texte_scene()

    # --- tout le reste : du markdown ---------------------------------------
    if "json" in bas and "schema" in bas:
        return json.dumps({"elements": ["Element A", "Element B"]}, ensure_ascii=False)
    return _texte_markdown()


CODE_OUTIL = '''#!/usr/bin/env python3
"""Compteur de mots, de lignes et de caracteres."""

import argparse
import json
import sys


def compter(texte):
    return {
        "mots": len(texte.split()),
        "lignes": len(texte.splitlines()),
        "caracteres": len(texte),
    }


def principal(argv=None):
    analyseur = argparse.ArgumentParser(description="Compte mots et lignes.")
    analyseur.add_argument("fichier", nargs="?", help="fichier a analyser")
    analyseur.add_argument("--json", action="store_true", help="sortie JSON")
    arguments = analyseur.parse_args(argv)

    if arguments.fichier:
        with open(arguments.fichier, encoding="utf-8") as flux:
            texte = flux.read()
    else:
        texte = ""

    resultat = compter(texte)
    if arguments.json:
        print(json.dumps(resultat, ensure_ascii=False))
    else:
        for cle, valeur in resultat.items():
            print("{}: {}".format(cle, valeur))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
'''

CODE_TESTS = '''import unittest

from outil import compter


class TestCompter(unittest.TestCase):
    def test_texte_vide(self):
        self.assertEqual(compter("")["mots"], 0)

    def test_trois_mots(self):
        self.assertEqual(compter("un deux trois")["mots"], 3)

    def test_lignes(self):
        self.assertEqual(compter("a\\nb\\nc")["lignes"], 3)


if __name__ == "__main__":
    unittest.main()
'''

CODE_HTML = '''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Compteur de mots</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto;
       padding: 0 1rem; }
textarea { width: 100%; min-height: 12rem; padding: .6rem; }
.chiffres { display: flex; gap: 1.5rem; margin-top: 1rem; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<h1>Compteur de mots</h1>
<textarea id="texte" placeholder="Collez votre texte ici"></textarea>
<div class="chiffres">
  <span><strong id="mots">0</strong> mots</span>
  <span><strong id="lignes">0</strong> lignes</span>
  <span><strong id="caracteres">0</strong> caracteres</span>
</div>
<script>
const zone = document.getElementById("texte");
function majuscules() {
  const valeur = zone.value;
  document.getElementById("mots").textContent =
    valeur.trim() ? valeur.trim().split(/\\s+/).length : 0;
  document.getElementById("lignes").textContent =
    valeur ? valeur.split("\\n").length : 0;
  document.getElementById("caracteres").textContent = valeur.length;
}
zone.addEventListener("input", majuscules);
majuscules();
</script>
</body>
</html>
'''

CODE_MANIFESTE = '''{
  "manifest_version": 3,
  "name": "Compteur de mots",
  "version": "1.0.0",
  "description": "Compte les mots de la page courante.",
  "permissions": ["activeTab"],
  "action": { "default_popup": "popup.html" }
}
'''
