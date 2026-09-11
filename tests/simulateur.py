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


def _combien(invite: str, defaut: int) -> int:
    for motif in (r"LONGUEUR\s*:\s*(\d+)", r"de\s+(\d+)\s+(?:prompts|publications|outils|idees)",
                  r"en\s+(\d+)\s+modules", r"calendrier editorial de (\d+)"):
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


def simulateur(messages, role):
    """Signature attendue par llm.definir_simulateur : (messages, role) -> texte."""
    invite = messages[-1]["content"]
    bas = invite.lower()

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

    # --- tout le reste : du markdown ---------------------------------------
    if "json" in bas and "schema" in bas:
        return json.dumps({"elements": ["Element A", "Element B"]}, ensure_ascii=False)
    return _texte_markdown()
