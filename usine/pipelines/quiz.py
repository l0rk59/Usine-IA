"""Quiz : les questions, leurs reponses, et pourquoi.

Un quiz se vend seul (auto-evaluation, preparation d'examen) et se glisse
dans une formation. L'usine savait faire des exercices — la chaine
« formation » livre un cahier — mais pas un quiz note, qui n'est pas la meme
chose : un exercice se corrige en lisant, un quiz se corrige en comptant.

Ce qui fait la valeur d'un quiz n'est pas la question, c'est l'EXPLICATION.
Une bonne question a des mauvaises reponses plausibles, et l'explication dit
pourquoi chacune est fausse — sans quoi celui qui se trompe apprend qu'il a
tort, pas ce qu'il faut penser. C'est ce que cette chaine demande au modele,
et c'est ce qu'elle verifie : une question dont toutes les propositions se
valent, ou dont l'indice de bonne reponse sort du tableau, est jetee plutot
que livree — un corrige faux vaut moins que pas de corrige.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import document as D
from ..render import libelles, livraison
from ..render import quiz as rendu_quiz
from .base import Contexte, nettoyer_titre, preparer, slug, terminer

NIVEAUX = ("debutant", "intermediaire", "avance")


def _questions(ctx: Contexte, nombre: int, niveau: str) -> List[Dict[str, Any]]:
    invite = (
        "Ecris {n} questions a choix multiple sur : {sujet}\n"
        "CANDIDAT : {audience}\nNIVEAU : {niveau}\n\n"
        "Chaque question a exactement quatre propositions. Les trois "
        "mauvaises doivent etre PLAUSIBLES : une erreur que quelqu'un "
        "commet vraiment, pas une absurdite qu'on ecarte d'un coup d'oeil. "
        "Une question dont la bonne reponse saute aux yeux ne mesure rien.\n\n"
        "Pour chaque question :\n"
        "- 'question' : l'enonce, une phrase.\n"
        "- 'propositions' : les quatre reponses, dans le desordre.\n"
        "- 'reponse' : l'INDICE de la bonne proposition, a partir de 0.\n"
        "- 'explication' : pourquoi elle est bonne ET pourquoi les autres "
        "sont fausses. 40 a 90 mots. C'est la partie que le candidat relit.\n"
        "- 'module' : deux ou trois mots, pour regrouper les resultats.\n\n"
        "Schema JSON exact :\n"
        '{{"questions": [{{"question": "...", "propositions": ["a","b","c","d"], '
        '"reponse": 0, "explication": "...", "module": "..."}}]}}\n'
        "Ce quiz est autonome : il ne suit aucune formation."
    ).format(n=nombre, sujet=ctx.sujet, audience=ctx.audience, niveau=niveau)
    donnees = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="costaud", temperature=0.6, max_tokens=4000)
    brutes = donnees.get("questions") if isinstance(donnees, dict) else donnees
    propres: List[Dict[str, Any]] = []
    for brute in brutes or []:
        question = _valider(brute)
        if question is not None:
            propres.append(question)
    if not propres:
        raise ValueError("Aucune question exploitable")
    return propres


def _valider(brute: Any) -> Any:
    """Une question dont le corrige est faux est pire que pas de question.

    Le modele se trompe d'indice assez souvent pour que ce soit la premiere
    chose a verifier : « bonne » vaut parfois 4 sur quatre propositions, ou
    arrive en toutes lettres. Un corrige faux se decouvre apres la vente, par
    l'acheteur, et il n'a aucun moyen de savoir si c'est lui ou le quiz.
    """
    if not isinstance(brute, dict) or not str(brute.get("question") or "").strip():
        return None
    propositions = [str(p).strip() for p in (brute.get("propositions") or [])
                    if str(p).strip()]
    if len(propositions) < 2:
        return None
    # Deux propositions identiques rendent la question insoluble : deux
    # reponses justes, un seul indice.
    if len({p.lower() for p in propositions}) != len(propositions):
        return None
    try:
        reponse = int(brute.get("reponse"))
    except (TypeError, ValueError):
        return None
    if not 0 <= reponse < len(propositions):
        return None
    # Le texte d'un quiz n'est pas un document markdown : il part dans une
    # page, un PDF et le verdict qu'affiche le script de correction. Un
    # « **mot** » du modele y restait en clair — mesure du 24/09/2026 : dans
    # les trois. On retire le balisage ici, une fois.
    return {
        "question": D.nettoyer_inline(str(brute["question"])),
        "propositions": [D.nettoyer_inline(p) for p in propositions],
        # « reponse », comme l'attend « render/quiz.py » qui existait deja :
        # une seconde forme pour la meme chose aurait rendu la page muette.
        "reponse": reponse,
        "explication": D.nettoyer_inline(str(brute.get("explication") or "")),
        "module": nettoyer_titre(str(brute.get("module") or "General")),
    }


def produire(ctx: Contexte, nombre: int = 20, niveau: str = "intermediaire",
             sans_bareme: bool = False) -> Dict[str, Any]:
    nombre = max(5, min(int(nombre or 20), 60))
    if niveau not in NIVEAUX:
        niveau = "intermediaire"
    titre = "Quiz — {}".format(ctx.sujet)
    dossier = preparer(ctx, "quiz", titre)

    ctx.journal("Étape 1/2 — rédaction des questions...")
    questions = _questions(ctx, nombre, niveau)
    perdues = nombre - len(questions)
    if perdues > 0:
        # On le dit plutot que de le taire : un quiz de douze questions vendu
        # pour vingt est un produit troue, et c'est a l'etape de le porter.
        ctx.journal("  {} question(s) écartées : corrigé incohérent."
                    .format(perdues))
    ctx.etape("questions",
              "partiel" if perdues else "ok",
              "{} questions retenues sur {}".format(len(questions), nombre))

    ctx.journal("Étape 2/2 — export...")
    fichiers = _exporter(ctx, titre, questions, niveau, not sans_bareme)
    # La page qui se corrige seule, hors ligne. Elle existait deja pour la
    # formation — « render/quiz.py » — et c'est exactement ce qu'un acheteur
    # de quiz attend : le PDF sert a imprimer, la page sert a se tester.
    try:
        fichiers.append(rendu_quiz.ecrire(
            ctx.dossier / "quiz.html", titre, questions,
            promesse=libelles.libelle(ctx.langue_iso, "quiz_promesse_page"),
            langue=ctx.langue_iso))
        ctx.etape("page-interactive", "ok", "quiz.html")
    except Exception as exc:
        # Le PDF et le corrige sont deja ecrits : perdre la page interactive
        # ne rend pas le quiz invendable, donc « essentiel=False ».
        ctx.journal("  page interactive indisponible : {}".format(exc))
        ctx.etape("page-interactive", "echec", str(exc), essentiel=False)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "questions": len(questions),
        "themes": sorted({q["module"] for q in questions}),
        "fichiers": [f.name for f in fichiers],
    }
    terminer(ctx, fichiers, {"questions": len(questions), "niveau": niveau})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _lettre(index: int) -> str:
    return "ABCDEFGH"[index] if 0 <= index < 8 else "?"


def _exporter(ctx: Contexte, titre: str, questions: List[Dict[str, Any]],
              niveau: str, avec_bareme: bool) -> List[Path]:
    t = libelles.textes(ctx.langue_iso)
    sous_titre = t["quiz_produit_sous_titre"].format(
        nombre=len(questions), niveau=t["quiz_niveaux"].get(niveau, niveau))

    def consigne(doc) -> None:
        doc.paragraphe(t["quiz_consigne"], justifier=True)
        if avec_bareme:
            doc.encadre(t["quiz_bareme"], _bareme(len(questions), t))

    # Le « corps » n'est pas un doublon de « rendu_pdf » : sans lui, ce bloc
    # n'existe QUE dans le PDF. Mesure du 14/09/2026 en relisant « lire.html »
    # de trois chaines : les consignes, le bareme et le mode d'emploi
    # disparaissaient pour qui ouvre la page HTML — c'est-a-dire pour la
    # plupart des acheteurs sur telephone. Un bloc sans corps ni rendu HTML
    # ne rend rien du tout, en silence.
    corps_consignes = [t["quiz_consigne"]]
    if avec_bareme:
        corps_consignes.append("\n**{}**\n".format(t["quiz_bareme"]))
        corps_consignes.append(_bareme(len(questions), t))
    blocs = [livraison.Bloc(titre=t["quiz_consignes"],
                            corps="\n".join(corps_consignes),
                            rendu_pdf=consigne)]
    blocs.append(livraison.Bloc(
        titre=t["quiz_questions"],
        corps=_markdown_questions(questions),
        rendu_pdf=_page_questions(questions),
        rendu_html=_html_questions(questions)))
    # Le corrige vient en dernier, et separe : imprime a la suite des
    # questions, il se lit par transparence sur du papier ordinaire.
    blocs.append(livraison.Bloc(
        titre=t["quiz_corrige"],
        corps=_markdown_corrige(questions),
        rendu_pdf=_page_corrige(questions, t),
        rendu_html=_html_corrige(questions)))

    produit = livraison.Produit(
        type="quiz",
        sommaire=False, titre=titre, sous_titre=sous_titre,
        promesse=t["quiz_promesse"], blocs=blocs,
        tableaux=[livraison.Tableau(
            nom="questions",
            colonnes=list(t["quiz_colonnes"]),
            lignes=[[q["module"], q["question"]]
                    + [q["propositions"][i] if i < len(q["propositions"]) else ""
                       for i in range(4)]
                    + [_lettre(q["reponse"]), q["explication"]]
                    for q in questions])],
        donnees={"titre": titre, "niveau": niveau, "questions": questions},
        nom_donnees="quiz",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture="quiz, question mark pattern, academic",
        nom_fichier=slug(titre, 48),
    )
    return livraison.livrer(ctx, produit)


def _bareme(total: int, t: Dict[str, Any]) -> str:
    """Des seuils, exprimes en nombre de bonnes reponses.

    En proportions plutot qu'en points : un bareme sur vingt ne veut rien
    dire quand le quiz compte douze questions parce que huit ont ete
    ecartees. Les seuils sont arrondis a la question entiere, puisque c'est
    l'unite dans laquelle on compte.
    """
    return t["quiz_bareme_texte"].format(acquis=max(1, round(total * 0.8)),
                     revoir=max(1, round(total * 0.5)),
                     presque=max(1, round(total * 0.8)) - 1)


def _markdown_questions(questions: List[Dict[str, Any]]) -> str:
    lignes = []
    for index, question in enumerate(questions, 1):
        lignes.append("\n**{}. {}**\n".format(index, question["question"]))
        for rang, proposition in enumerate(question["propositions"]):
            lignes.append("- {}. {}".format(_lettre(rang), proposition))
    return "\n".join(lignes)


def _markdown_corrige(questions: List[Dict[str, Any]]) -> str:
    lignes = []
    for index, question in enumerate(questions, 1):
        lignes.append("\n**{}. {} — {}**\n".format(
            index, _lettre(question["reponse"]),
            question["propositions"][question["reponse"]]))
        if question["explication"]:
            lignes.append(question["explication"])
    return "\n".join(lignes)


def _page_questions(questions: List[Dict[str, Any]]):
    def rendre(doc) -> None:
        for index, question in enumerate(questions, 1):
            doc.paragraphe("{}. {}".format(index, question["question"]),
                           taille=11, police="Helvetica-Bold")
            doc.liste(["{}. {}".format(_lettre(rang), proposition)
                       for rang, proposition
                       in enumerate(question["propositions"])],
                      taille=10, puce=" ")

    return rendre


def _page_corrige(questions: List[Dict[str, Any]], t: Dict[str, Any]):
    def rendre(doc) -> None:
        for index, question in enumerate(questions, 1):
            doc.paragraphe(t["quiz_reponse_pdf"].format(
                numero=index, lettre=_lettre(question["reponse"]),
                texte=question["propositions"][question["reponse"]]),
                taille=11, police="Helvetica-Bold")
            if question["explication"]:
                doc.paragraphe(question["explication"], taille=10,
                               justifier=True)

    return rendre


def _html_questions(questions: List[Dict[str, Any]]) -> str:
    morceaux = []
    for index, question in enumerate(questions, 1):
        morceaux.append("<p><strong>{}. {}</strong></p>".format(
            index, D.inline_html(question["question"])))
        morceaux.append("<ol type=\"A\">{}</ol>".format("".join(
            "<li>{}</li>".format(D.inline_html(p))
            for p in question["propositions"])))
    return "\n".join(morceaux)


def _html_corrige(questions: List[Dict[str, Any]]) -> str:
    morceaux = []
    for index, question in enumerate(questions, 1):
        morceaux.append("<p><strong>{}. {} — {}</strong></p>".format(
            index, _lettre(question["reponse"]),
            D.inline_html(question["propositions"][question["reponse"]])))
        if question["explication"]:
            morceaux.append("<p>{}</p>".format(
                D.inline_html(question["explication"])))
    return "\n".join(morceaux)
