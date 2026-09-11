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
    for motif in (r"LONGUEUR\s*:\s*(\d+)",
                  r"de\s+(\d+)\s+(?:prompts|publications|outils|idees|fiches|bases)",
                  r"en\s+(\d+)\s+modules", r"calendrier editorial de (\d+)",
                  r"systeme de (\d+) bases"):
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

    # --- critique editoriale ------------------------------------------------
    if '"points_forts"' in invite:
        # Premiere passe severe, passes suivantes clementes : la boucle doit
        # pouvoir converger et s'arreter d'elle-meme.
        severe = "deja corrige" not in invite
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
