"""Le texte que l'usine ecrit elle-meme dans ce qu'elle livre, par langue.

Le modele ecrit le contenu dans la langue reglee. Tout le reste — licence,
LISEZ-MOI, page de copyright, sommaire, page de vente, et les mots fixes de
chaque genre (« Chapitre », « Precedemment », « rendez-vous au ») — etait ecrit
en dur, en francais. Mesure du 24/09/2026, langue reglee sur « anglais » : les
dix-huit types livraient un contenu anglais habille d'un mobilier francais,
jusqu'a la licence et au mode d'emploi. Pour un livre vendu en anglais, c'est
un defaut que l'acheteur voit a la premiere page.

Deux langues sont tenues ici, le francais et l'anglais, ecrites a la main.
Toute autre langue du reglage recoit le mobilier anglais, et la fabrication
le dit (voir « base.preparer ») : un livre espagnol au mobilier anglais n'est
pas juste, mais l'acheteur le lit, et l'usine ne pretend pas le contraire.

Ce qui s'adresse au VENDEUR — les rubriques de la fiche produit, le journal,
les conseils — reste en francais : c'est la langue de celui qui fabrique, pas
celle de celui qui achete.

Le francais est recopie tel qu'il sortait : un test compare les deux langues
cle par cle, et les memes champs a remplir de part et d'autre.
"""

from __future__ import annotations

from typing import Any, Dict

LANGUES_TENUES = ("fr", "en")

FR: Dict[str, Any] = {
    # --- l'archive : licence et LISEZ-MOI ---------------------------------
    "licence": """LICENCE D'UTILISATION — {titre}

(c) {annee} {auteur}. Tous droits réservés.

CE QUE VOUS POUVEZ FAIRE
- Utiliser ce produit pour votre usage personnel ou professionnel.
- Appliquer les méthodes décrites à votre activité, sans limite.
- Adapter les modèles fournis à vos propres besoins.

CE QUE VOUS NE POUVEZ PAS FAIRE
- Revendre, redistribuer ou partager les fichiers, même gratuitement.
- Publier le contenu, en tout ou partie, sous votre nom.
- Inclure ce produit dans une offre groupée sans autorisation écrite.

AVERTISSEMENT
Ce produit est fourni à titre informatif. Il ne constitue ni un conseil
juridique, ni un conseil fiscal, ni un conseil médical, ni un conseil en
investissement. Aucun résultat n'est garanti : les résultats dépendent de
votre situation, de votre marché et de votre exécution. L'auteur ne peut
être tenu responsable des décisions prises sur la base de ce document.
{transparence}""",
    "transparence": """

TRANSPARENCE
Ce produit a été élaboré avec l'assistance d'outils d'intelligence
artificielle, puis structuré et mis en forme par Usine-IA. Relisez et
adaptez le contenu à votre contexte avant toute diffusion commerciale.
""",
    "mention_ia_courte": ("Ouvrage élaboré avec l'assistance d'outils "
                          "d'intelligence artificielle."),
    "notice": """# {titre}

{promesse}

Merci pour votre achat.

## Ce que contient ce dossier

{fichiers}

## Par où commencer

1. Ouvrez le fichier PDF : c'est la version de référence, mise en page pour
   la lecture et l'impression.
2. Sur liseuse ou téléphone, préférez le fichier EPUB s'il est présent.
3. Le fichier `lire.html` s'ouvre dans n'importe quel navigateur, y compris
   hors connexion, et s'imprime proprement.
4. Les fichiers `.md`, `.csv` et `.json` sont là pour que vous puissiez
   réutiliser le contenu dans vos propres outils.

## Accessibilité

Le fichier EPUB est structuré pour la lecture assistée : ordre de lecture
logique, titres hiérarchisés, table des matières navigable, texte
redimensionnable sans perte d'information, contraste vérifié à 4,5:1 au
minimum. Aucun contenu clignotant ni sonore. Les métadonnées d'accessibilité
sont incluses dans le fichier.
{contact_accessibilite}{contact_question}
---
{auteur} — {date}
""",
    "contact_accessibilite": """
Si un format vous convient mal, écrivez à {contact} : une version adaptée
vous sera envoyée.
""",
    "contact_question": """
## Une question ?

Écrivez à {contact}.
""",
    "dossier_vide": "- (dossier vide)",
    "contenu_bonus": "- `{nom}/` — contenu bonus",
    "format_date": "%d/%m/%Y",

    # --- EPUB : page de copyright, sommaire, accessibilite ------------------
    "droits_reserves": ("Tous droits réservés. Aucune partie de cet ouvrage ne "
                        "peut être reproduite ou diffusée sans l'autorisation "
                        "écrite de l'auteur."),
    "edite_par": "Édité par {editeur}",
    "premiere_edition": "Première édition : {date}",
    "identifiant_publication": "Identifiant de la publication : {identifiant}",
    "mois": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"),
    "resume_accessibilite": (
        "Publication textuelle. Ordre de lecture logique, titres hiérarchisés, "
        "table des matières navigable, texte redimensionnable sans perte "
        "d'information. Contraste vérifié à 4,5:1 au minimum sur l'ensemble de la "
        "feuille de style. Aucun contenu clignotant ni sonore. La couverture porte "
        "un texte de remplacement ; elle est décorative et ne porte aucune "
        "information absente du texte."),
    "sommaire": "Sommaire",
    "couverture": "Couverture",

    # --- page de vente : ce que lit l'acheteur ---------------------------------
    "vente_change": "Ce que ce produit change pour vous",
    "vente_recevez": "Ce que vous recevez",
    "vente_pour_qui": "Pour qui c'est fait",
    "vente_pas_pour_qui": "Pour qui ce n'est pas fait",
    "vente_questions": "Vos questions",
    "vente_prix": "Prix",
    "vente_acces": "<strong>{prix}</strong> — accès immédiat après paiement, "
                   "téléchargement direct.",
    "vente_obtenir": "Obtenir « {titre} »",

    # --- extrait offert ------------------------------------------------------
    "extrait_lu": "Vous venez de lire le début de « **{titre}** ».",
    "extrait_reste": "La version complète contient {nombre} chapitre(s) de plus :",
    "extrait_site": "Le livre complet : {site}",
    "extrait_question": "Une question : {contact}",
    "extrait_sans_site": ("Le livre complet est disponible à la vente. "
                          "Répondez à cet e-mail pour le lien."),
    "extrait_suite": "La suite",
    "extrait_titre": "{titre} — extrait",
    "extrait_sous_titre": "Les {nombre} premiers chapitres",
    "extrait_promesse": "Extrait offert de « {titre} ».",

    # --- unites comptees sous le titre de la page de lecture -----------------
    "unite_chapitres": "chapitres",
    # --- les types « livre » ------------------------------------------------
    "ebook_avant_propos": "Avant-propos : pourquoi ce livre",
    "ebook_conclusion": "Et maintenant : votre plan des 30 prochains jours",
    "ebook_conclusion_reference": "Aide-mémoire : l'essentiel à garder sous la main",
    "ebook_conclusion_programme": "Après le programme : garder le cap",
    "ebook_conclusion_cas": "Ce que ces cas ont en commun",
    "ebook_conclusion_questions": "Les questions que vous vous poserez ensuite",
    "unite_scenes": "scènes",
    "unite_nouvelles": "nouvelle(s)",
    "unite_sections": "section(s)",
    "unite_episodes": "épisode(s)",
    "unite_doubles_pages": "double(s)-page(s)",
    "unite_modules": "modules",
    "recueil_sous_titre": "{nombre} nouvelles",
    "recueil_fil": "Le fil",
    "recueil_fil_defaut": "Sept textes, un même fil.",
    "interactif_sous_titre": "{sections} sections, {fins} fins",
    "interactif_mode_emploi_titre": "Comment lire ce livre",
    "interactif_mode_emploi": (
        "Ce livre ne se lit pas dans l'ordre. Commencez à la section **1**, "
        "puis suivez le numéro du choix que vous faites. Il y a {fins} fins : "
        "celle que vous atteindrez dépend de vous."),
    "interactif_le_livre": "Le livre",
    "interactif_fin": "*Fin.*",
    "interactif_choix": "Si vous voulez {action}, rendez-vous au **{vers}**.",
    "interactif_choix_direct": "{action} : rendez-vous au **{vers}**.",
    # Les tetes de phrase sur lesquelles « Si vous voulez » ne se greffe pas.
    "interactif_pronoms": ("vous", "tu", "je", "j'", "il", "elle", "on", "nous",
                           "ils", "elles"),
    "feuilleton_saison": "La saison",
    "feuilleton_saison_defaut": "Une saison en {nombre} épisodes.",
    "feuilleton_precedemment": "**Précédemment.** ",
    "feuilleton_a_suivre": "*À suivre.*",
    "feuilleton_episode": "Épisode {rang} — {titre}",
    "feuilleton_sous_titre": "{nombre} épisodes",
    "conte_page": "Page {numero}",
    "conte_sous_titre": "{nombre} doubles-pages — {tranche}",
    "conte_tranche": "{debut}-{fin} ans",
    "conte_note_illustration": "> **Illustration** : {texte}",
    "conte_illustration_a_dessiner": "Illustration à dessiner",

    # --- pack de prompts -----------------------------------------------------
    "prompts_titre": "{nombre} prompts pour {sujet}",
    "prompts_sous_titre": "Prêt à copier-coller",
    "prompts_mode_emploi_titre": "Comment utiliser ce pack",
    "prompts_mode_emploi": (
        "Chaque prompt est autonome. Remplacez les variables entre crochets par "
        "vos informations, puis collez le texte dans l'IA de votre choix "
        "(Claude, ChatGPT, Gemini, Mistral ou un modèle local). Les prompts "
        "sont classés par intention : commencez par la catégorie qui "
        "correspond à votre tâche du jour."),
    "prompts_conseil_titre": "Conseil",
    "prompts_conseil": (
        "Gardez le contexte d'une conversation à l'autre : plus l'IA connaît "
        "votre activité, meilleurs sont les résultats. Collez d'abord un "
        "descriptif de votre activité, puis enchaînez les prompts du pack."),
    "prompts_colonnes": ("Catégorie", "Titre", "Quand l'utiliser", "Prompt",
                         "Astuce"),
    "prompts_quand": "Quand l'utiliser",
    "prompts_astuce": "Astuce",
    "prompts_categorie": "Catégorie",
    # « libelle : texte » — l'espace avant les deux-points est francais.
    "deux_points": "{libelle} : {texte}",

    # --- quiz auto-corrige ------------------------------------------------------
    "quiz_titre": "{titre} — quiz",
    "quiz_sous_titre": "{nombre} question(s) pour vérifier ce qui est acquis",
    "quiz_intro": ("Répondez à toutes les questions, puis corrigez. Rien n'est "
                   "envoyé : la correction se fait dans votre navigateur, hors "
                   "ligne. C'est une auto-évaluation — les réponses sont dans "
                   "la page."),
    "quiz_corriger": "Corriger mes réponses",
    # Les textes que le script de la page affiche en corrigeant.
    "quiz_script": {
        "sans_reponse": "Sans réponse.",
        "juste": "Juste. ",
        "faux_avant": "Faux : la bonne réponse était « ",
        "faux_apres": " ». ",
        "score_sur": " bonne(s) réponse(s) sur ",
        "sans_reponse_nombre": " question(s) sans réponse.",
    },

    # --- formation ---------------------------------------------------------------
    "module_titre": "Module {numero} — {titre}",
    "module_plan": "## Objectif\n\n{objectif}\n\n## Notions\n\n{notions}",
    "formation_avant": "Avant de commencer",
    "formation_prerequis": "Prérequis",
    "formation_methode": (
        "Traitez un module par session de travail. Ne passez au suivant "
        "qu'après avoir produit le livrable demandé : c'est lui qui "
        "transforme la lecture en résultat."),
    "cahier_titre": "Cahier d'exercices",
    "cahier_titre_courant": "{titre} — cahier d'exercices",
    "cahier_objectif": "Objectif",
    "cahier_livrable": "Livrable attendu",
    "cahier_consigne": "Consigne",
    "cahier_notes": "Vos notes",
    "sequence_titre": "Séquence e-mail — {titre}",
    "sequence_jour": "Jour {jour} — {objet}",
    "sequence_action": "Action demandée",

    # --- boite a outils ------------------------------------------------------------
    "outils_mode_emploi_titre": "Comment utiliser cette boîte à outils",
    "outils_mode_emploi": (
        "Ces documents sont faits pour être imprimés ou remplis à l'écran. "
        "Choisissez l'outil correspondant à votre situation du moment : chacun "
        "produit un résultat en une seule session de travail."),
    "outils_quand": "Quand l'utiliser",
    "outils_quand_court": "Quand",
    "outils_a_verifier": "À vérifier",
    "outils_colonnes": "Colonnes du tableau",
    "outils_a_completer": "À compléter",

    # --- systeme de modeles (Notion, tableur) -----------------------------------
    "modeles_mise_en_route": "Mise en route",
    "modeles_guide": "Guide d'installation",
    "modeles_structure": "Structure",
    "modeles_colonnes": ("Colonne", "Type", "Rôle"),
    "modeles_vues": "Vues à créer",
    "modeles_vues_md": "**Vues à créer :**",
    "modeles_vue": "{nom} — filtre : {filtre} — tri : {tri}",
    "modeles_aucun": "aucun",
    # Les types de colonne sont des noms que l'invite impose au modele ; en
    # francais, ils s'affichent tels quels.
    "modeles_types": {},

    # --- imprimables -----------------------------------------------------------------
    "impression_comment_remplir": "Comment remplir cette fiche",
    "impression_notes": "Notes",
    "impression_jours": ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi",
                         "Samedi", "Dimanche"),
    "impression_priorites": "Priorités de la semaine",
    "impression_semaine": "Semaine",
    "impression_suivi_colonnes": ("Date", "Action", "Résultat", "Suite"),
    "impression_question": "Question",
    "impression_mode_emploi_titre": "Mode d'emploi",
    "impression_mode_emploi": (
        "Imprimez ce cahier en recto simple, sur papier ordinaire. Chaque fiche "
        "tient sur une page et se remplit à la main. Vous pouvez aussi le "
        "compléter à l'écran avec une application d'annotation PDF."),
    "impression_a_la_demande_titre": "Impression à la demande",
    "impression_a_la_demande": (
        "Ce cahier est mis en page pour une reliure : le contenu est décalé de "
        "{mm} mm vers l'extérieur, alternativement à gauche et à droite, pour "
        "que rien ne disparaisse dans la pliure. Imprimez-le en recto-verso."),
    "impression_apporte": "Ce que ce cahier vous apporte",
    "impression_disposition": "Disposition",
    "impression_dispositions": {},

    # --- pack de contenu pour les reseaux -------------------------------------------
    "social_titre": "{nombre} posts {reseau} — {sujet}",
    "social_sous_titre": "Calendrier éditorial prêt à publier",
    "social_pack": "Pack de contenu {reseau}",
    "social_jour": "Jour {jour}",
    "social_colonnes": ("Jour", "Angle", "Objectif", "Texte", "Hashtags",
                        "Idée de visuel"),
    "social_mode_emploi_titre": "Mode d'emploi",
    "social_mode_emploi": (
        "Publiez une pièce de contenu par jour ouvré. Adaptez les chiffres et "
        "les exemples à votre réalité : un post crédible vaut mieux qu'un post "
        "parfait. Le fichier calendrier.csv s'importe directement dans un "
        "tableur ou un outil de programmation."),

    # --- sequence e-mail -------------------------------------------------------------
    "emails_sous_titre": "{nombre} messages, un tous les {rythme} jour(s)",
    "emails_mode_emploi_titre": "Comment envoyer cette séquence",
    "emails_ordre": (
        "Cette séquence s'envoie dans l'ordre, à partir du jour de "
        "l'inscription. Le calendrier ci-dessous donne le décalage de chaque "
        "message ; la plupart des outils d'emailing le demandent sous cette "
        "forme."),
    "emails_csv": (
        "Le fichier CSV livré avec ce document s'importe directement dans un "
        "outil d'emailing : une ligne par message, avec l'objet, l'aperçu et "
        "le corps."),
    "emails_avant_titre": "Avant d'envoyer",
    "emails_avant": (
        "Relisez chaque message en pensant à une personne précise de votre "
        "liste. Remplacez les crochets par vos informations, et vérifiez que le "
        "lien de désinscription est présent : il est obligatoire, et son "
        "absence suffit à faire classer vos envois en indésirables."),
    "emails_colonnes": ("Jour", "Objet", "Aperçu", "Corps", "P.S.", "Action"),
    "emails_objet": "Objet",
    "emails_apercu": "Aperçu",
    "emails_demande": "Ce que ce message demande",
    # Vide : en francais, les objectifs s'affichent tels que « emails.OBJECTIFS »
    # les ecrit.
    "emails_objectifs": {},

    # --- memo ----------------------------------------------------------------------
    "memo_titre": "Mémo — {sujet}",
    "memo_sous_titre": "{lignes} repère(s) en {blocs} bloc(s)",
    "memo_promesse": "L'essentiel, à garder à côté de soi",
    "memo_colonnes": ("Bloc", "Genre", "Ligne"),
    # Les genres de bloc sont des noms internes ; en francais, tels quels.
    "memo_genres": {},

    # --- logiciel -------------------------------------------------------------------
    "unite_sections_simple": "sections",
    "logiciel_ce_que_fait": "Ce que fait cet outil",
    "logiciel_installation": "Installation et utilisation",
    "logiciel_verification": "Vérification du code",
    "logiciel_fonctions": "Fonctions",
    "logiciel_limites": "Ce que cet outil ne fait pas",
    "logiciel_limites_pourquoi": ("Le dire évite les déceptions, et les "
                                  "demandes de remboursement qui vont avec."),
    "logiciel_cli": (
        "Aucune installation : le script n'utilise que la bibliothèque "
        "standard de Python.\n\n"
        "```\npython3 source/outil.py --help\n```\n\n"
        "Utilisation type :\n\n```\n{utilisation}\n```\n\n"
        "Les tests se lancent avec :\n\n```\npython3 source/test_outil.py\n```"),
    "logiciel_web": (
        "Ouvrez `source/index.html` dans n'importe quel navigateur. Il n'y a "
        "rien à installer et rien à configurer : tout le code est dans ce "
        "fichier, il fonctionne hors connexion.\n\n"
        "Pour le mettre en ligne, déposez ce seul fichier chez n'importe quel "
        "hébergeur statique."),
    "logiciel_extension": (
        "1. Ouvrez `chrome://extensions` dans Chrome.\n"
        "2. Activez le « mode développeur » en haut à droite.\n"
        "3. Cliquez sur « Charger l'extension non empaquetée ».\n"
        "4. Choisissez le dossier `source/`.\n\n"
        "Pour la publier, compressez le dossier `source/` et déposez l'archive "
        "sur le Chrome Web Store."),
    "logiciel_verifie": ("Ce code a été vérifié avant livraison. Voici "
                         "exactement ce qui a été contrôlé.\n"),
    "logiciel_colonnes": ("Fichier", "Vérification", "Résultat"),
    "logiciel_correct": "correct",
    "logiciel_a_corriger": "**à corriger**",
    "logiciel_non_execute": "non exécuté : {refus}",
    "logiciel_demarre": "démarre correctement",
    "logiciel_echec": "**échec**",
    "logiciel_execution": "exécution réelle",
    "logiciel_remarques": ("{nombre} remarque(s) sans gravité ont été relevées "
                           "par la vérification."),
    "logiciel_attention": (
        "**Attention :** un ou plusieurs fichiers n'ont pas passé la "
        "vérification. Relisez-les avant toute mise en vente."),
    # Ce que la verification a controle, et les causes d'un refus d'executer :
    # des libelles de « core/verification.py », en francais tels quels.
    "logiciel_verifie_par": {},
    "logiciel_refus": {},
    # Les motifs pour lesquels l'analyse statique refuse de lancer un script.
    # « core/verification.py » compose ses messages a partir d'ICI : une
    # seule source pour les deux, et la notice francaise ne change pas.
    "logiciel_soucis": {
        "syntaxe": "erreur de syntaxe : {valeur}",
        "import": "importe « {valeur} » : accès système ou réseau",
        "appel": "appelle « {valeur}() »",
        "ecriture": "écrit hors du dossier de travail : {valeur}",
    },
    "logiciel_tests_unitaires": "tests unitaires",

    # --- le quiz vendu seul --------------------------------------------------
    "quiz_produit_sous_titre": "{nombre} questions — niveau {niveau}",
    # Les niveaux s'affichaient tels qu'ils sont stockes : le francais les
    # garde a l'identique.
    "quiz_niveaux": {},
    "quiz_promesse": "Se tester, et comprendre ses erreurs",
    "quiz_promesse_page": ("Corrigez-vous sans rien envoyer : tout se passe "
                           "dans votre navigateur."),
    "quiz_consignes": "Consignes",
    "quiz_consigne": ("Répondez à toutes les questions avant de consulter le "
                      "corrigé. Une seule proposition est juste par question."),
    "quiz_bareme": "Barème",
    "quiz_bareme_texte": (
        "{acquis} bonnes réponses ou plus : c'est acquis.\n"
        "{revoir} à {presque} : relisez les explications des questions "
        "manquées.\n"
        "Moins de {revoir} : reprenez le sujet avant de vous retester."),
    "quiz_questions": "Questions",
    "quiz_corrige": "Corrigé",
    "quiz_reponse_pdf": "{numero}. Réponse {lettre} — {texte}",
    "quiz_colonnes": ("Module", "Question", "A", "B", "C", "D", "Bonne",
                      "Explication"),

    # --- la derniere page d'un tome de serie ------------------------------------
    "serie_page": "La suite",
    "serie_tome_lu": ("Vous venez de lire le tome {rang} de la série **{serie}**. "
                      "Chaque tome se lit seul, mais ils se répondent."),
    "serie_appartient": "Ce récit appartient à la série **{serie}**.",
    "serie_precede": "### Ce qui précède",
    "serie_suite": "### La suite",
    "serie_tome": "**Tome {rang} — {titre}**",
    "serie_avis": (
        "Si cette histoire vous a plu, le meilleur service que vous puissiez "
        "rendre à son auteur tient en deux lignes d'avis là où vous l'avez "
        "achetée. C'est ce qui décide si quelqu'un d'autre la trouvera."),

    # --- les noms de fichiers que l'acheteur ouvre en premier ---------------------
    "fichier_notice": "LISEZ-MOI.md",
    "fichier_licence": "LICENCE.txt",
    "fichier_cahier": "cahier-exercices",
    "fichier_manuel": "-manuel",
    "fichier_extrait": "{nom}-extrait",
    "fichier_tableau": "tableau-{rang:02d}-{nom}.csv",
}

EN: Dict[str, Any] = {
    "licence": """LICENSE — {titre}

(c) {annee} {auteur}. All rights reserved.

WHAT YOU MAY DO
- Use this product for your personal or professional purposes.
- Apply the methods described to your own work, without limit.
- Adapt the templates provided to your own needs.

WHAT YOU MAY NOT DO
- Resell, redistribute or share the files, even for free.
- Publish the content, in whole or in part, under your own name.
- Include this product in a bundle without written permission.

DISCLAIMER
This product is provided for information purposes only. It is not legal,
tax, medical or investment advice. No result is guaranteed: results depend
on your situation, your market and how you apply it. The author cannot be
held liable for decisions made on the basis of this document.
{transparence}""",
    "transparence": """

TRANSPARENCY
This product was created with the assistance of artificial intelligence
tools, then structured and formatted by Usine-IA. Review it and adapt it to
your own context before any commercial use.
""",
    "mention_ia_courte": ("Created with the assistance of artificial "
                          "intelligence tools."),
    "notice": """# {titre}

{promesse}

Thank you for your purchase.

## What this folder contains

{fichiers}

## Where to start

1. Open the PDF file: it is the reference version, laid out for reading and
   printing.
2. On an e-reader or a phone, prefer the EPUB file if there is one.
3. The `lire.html` file opens in any browser, even offline, and prints
   cleanly.
4. The `.md`, `.csv` and `.json` files are there so you can reuse the
   content in your own tools.

## Accessibility

The EPUB file is structured for assisted reading: logical reading order,
hierarchical headings, navigable table of contents, text that can be resized
without loss of information, contrast checked at 4.5:1 minimum. No flashing
or audio content. Accessibility metadata is included in the file.
{contact_accessibilite}{contact_question}
---
{auteur} — {date}
""",
    "contact_accessibilite": """
If a format does not suit you, write to {contact}: an adapted version will
be sent to you.
""",
    "contact_question": """
## A question?

Write to {contact}.
""",
    "dossier_vide": "- (empty folder)",
    "contenu_bonus": "- `{nom}/` — bonus content",
    "format_date": "%Y-%m-%d",

    "droits_reserves": ("All rights reserved. No part of this work may be "
                        "reproduced or distributed without the written "
                        "permission of the author."),
    "edite_par": "Published by {editeur}",
    "premiere_edition": "First edition: {date}",
    "identifiant_publication": "Publication identifier: {identifiant}",
    "mois": ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"),
    "resume_accessibilite": (
        "Text publication. Logical reading order, hierarchical headings, "
        "navigable table of contents, text resizable without loss of "
        "information. Contrast checked at 4.5:1 minimum across the whole "
        "stylesheet. No flashing or audio content. The cover has alternative "
        "text; it is decorative and carries no information absent from the "
        "text."),
    "sommaire": "Contents",
    "couverture": "Cover",

    "vente_change": "What this product changes for you",
    "vente_recevez": "What you get",
    "vente_pour_qui": "Who it is for",
    "vente_pas_pour_qui": "Who it is not for",
    "vente_questions": "Your questions",
    "vente_prix": "Price",
    "vente_acces": "<strong>{prix}</strong> — instant access after payment, "
                   "direct download.",
    "vente_obtenir": "Get “{titre}”",

    "extrait_lu": "You have just read the beginning of “**{titre}**”.",
    "extrait_reste": "The full version contains {nombre} more chapter(s):",
    "extrait_site": "The full book: {site}",
    "extrait_question": "A question: {contact}",
    "extrait_sans_site": ("The full book is available for purchase. "
                          "Reply to this e-mail for the link."),
    "extrait_suite": "What comes next",
    "extrait_titre": "{titre} — excerpt",
    "extrait_sous_titre": "The first {nombre} chapters",
    "extrait_promesse": "Free excerpt of “{titre}”.",

    "unite_chapitres": "chapters",
    "ebook_avant_propos": "Foreword: why this book",
    "ebook_conclusion": "What now: your plan for the next 30 days",
    "ebook_conclusion_reference": "Quick reference: what to keep at hand",
    "ebook_conclusion_programme": "After the programme: staying on course",
    "ebook_conclusion_cas": "What these cases have in common",
    "ebook_conclusion_questions": "The questions you will ask next",
    "unite_scenes": "scenes",
    "unite_nouvelles": "story(ies)",
    "unite_sections": "section(s)",
    "unite_episodes": "episode(s)",
    "unite_doubles_pages": "spread(s)",
    "unite_modules": "modules",
    "recueil_sous_titre": "{nombre} stories",
    "recueil_fil": "The thread",
    "recueil_fil_defaut": "Seven stories, one thread.",
    "interactif_sous_titre": "{sections} sections, {fins} endings",
    "interactif_mode_emploi_titre": "How to read this book",
    "interactif_mode_emploi": (
        "This book is not read in order. Start at section **1**, then follow "
        "the number of the choice you make. There are {fins} endings: the one "
        "you reach depends on you."),
    "interactif_le_livre": "The book",
    "interactif_fin": "*The End.*",
    "interactif_choix": "If you want to {action}, turn to **{vers}**.",
    "interactif_choix_direct": "{action}: turn to **{vers}**.",
    "interactif_pronoms": ("you", "i", "we", "he", "she", "they", "it",
                           "i'm", "you're", "we're"),
    "feuilleton_saison": "The season",
    "feuilleton_saison_defaut": "A season in {nombre} episodes.",
    "feuilleton_precedemment": "**Previously.** ",
    "feuilleton_a_suivre": "*To be continued.*",
    "feuilleton_episode": "Episode {rang} — {titre}",
    "feuilleton_sous_titre": "{nombre} episodes",
    "conte_page": "Page {numero}",
    "conte_sous_titre": "{nombre} spreads — {tranche}",
    "conte_tranche": "ages {debut}-{fin}",
    "conte_note_illustration": "> **Illustration**: {texte}",
    "conte_illustration_a_dessiner": "Illustration to draw",

    "prompts_titre": "{nombre} prompts for {sujet}",
    "prompts_sous_titre": "Ready to copy and paste",
    "prompts_mode_emploi_titre": "How to use this pack",
    "prompts_mode_emploi": (
        "Each prompt stands on its own. Replace the variables in square "
        "brackets with your own information, then paste the text into the AI "
        "of your choice (Claude, ChatGPT, Gemini, Mistral or a local model). "
        "The prompts are grouped by intent: start with the category that "
        "matches today's task."),
    "prompts_conseil_titre": "Tip",
    "prompts_conseil": (
        "Keep the context from one conversation to the next: the more the AI "
        "knows about your work, the better the results. Paste a description "
        "of your work first, then run the prompts of the pack one after "
        "another."),
    "prompts_colonnes": ("Category", "Title", "When to use it", "Prompt", "Tip"),
    "prompts_quand": "When to use it",
    "prompts_astuce": "Tip",
    "prompts_categorie": "Category",
    "deux_points": "{libelle}: {texte}",

    "quiz_titre": "{titre} — quiz",
    "quiz_sous_titre": "{nombre} question(s) to check what you have learned",
    "quiz_intro": ("Answer every question, then check your answers. Nothing is "
                   "sent: checking happens in your browser, offline. It is a "
                   "self-assessment — the answers are in the page."),
    "quiz_corriger": "Check my answers",
    "quiz_script": {
        "sans_reponse": "No answer.",
        "juste": "Correct. ",
        "faux_avant": "Wrong: the right answer was “",
        "faux_apres": "”. ",
        "score_sur": " correct answer(s) out of ",
        "sans_reponse_nombre": " question(s) unanswered.",
    },

    "module_titre": "Module {numero} — {titre}",
    "module_plan": "## Objective\n\n{objectif}\n\n## Key ideas\n\n{notions}",
    "formation_avant": "Before you start",
    "formation_prerequis": "Prerequisites",
    "formation_methode": (
        "Work through one module per session. Move on only once you have "
        "produced the deliverable asked for: it is what turns reading into "
        "results."),
    "cahier_titre": "Workbook",
    "cahier_titre_courant": "{titre} — workbook",
    "cahier_objectif": "Objective",
    "cahier_livrable": "Expected deliverable",
    "cahier_consigne": "Instructions",
    "cahier_notes": "Your notes",
    "sequence_titre": "E-mail sequence — {titre}",
    "sequence_jour": "Day {jour} — {objet}",
    "sequence_action": "Requested action",

    "outils_mode_emploi_titre": "How to use this toolkit",
    "outils_mode_emploi": (
        "These documents are made to be printed or filled in on screen. Pick "
        "the tool that fits your situation right now: each one produces a "
        "result in a single work session."),
    "outils_quand": "When to use it",
    "outils_quand_court": "When",
    "outils_a_verifier": "To check",
    "outils_colonnes": "Table columns",
    "outils_a_completer": "To fill in",

    "modeles_mise_en_route": "Getting started",
    "modeles_guide": "Setup guide",
    "modeles_structure": "Structure",
    "modeles_colonnes": ("Column", "Type", "Role"),
    "modeles_vues": "Views to create",
    "modeles_vues_md": "**Views to create:**",
    "modeles_vue": "{nom} — filter: {filtre} — sort: {tri}",
    "modeles_aucun": "none",
    "modeles_types": {"texte": "text", "texte_long": "long text",
                      "nombre": "number", "selection": "select",
                      "multi_selection": "multi-select",
                      "case_a_cocher": "checkbox", "formule": "formula"},

    "impression_comment_remplir": "How to fill in this sheet",
    "impression_notes": "Notes",
    "impression_jours": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                         "Saturday", "Sunday"),
    "impression_priorites": "Priorities for the week",
    "impression_semaine": "Week",
    "impression_suivi_colonnes": ("Date", "Action", "Result", "Next step"),
    "impression_question": "Question",
    "impression_mode_emploi_titre": "How to use this workbook",
    "impression_mode_emploi": (
        "Print this workbook single-sided on ordinary paper. Each sheet fits on "
        "one page and is filled in by hand. You can also complete it on screen "
        "with a PDF annotation app."),
    "impression_a_la_demande_titre": "Print on demand",
    "impression_a_la_demande": (
        "This workbook is laid out for binding: the content is shifted {mm} mm "
        "outwards, alternately left and right, so that nothing disappears into "
        "the gutter. Print it double-sided."),
    "impression_apporte": "What this workbook gives you",
    "impression_disposition": "Layout",
    # Complete, meme la ou le mot ne change pas : le test de couverture lit
    # « impression.DISPOSITIONS », et une disposition ajoutee la-bas sans
    # entree ici s'afficherait en francais sans que rien n'echoue.
    "impression_dispositions": {"checklist": "checklist", "planning": "planner",
                                "suivi": "tracker", "questions": "questions",
                                "notes": "notes", "matrice": "matrix"},

    "social_titre": "{nombre} {reseau} posts — {sujet}",
    "social_sous_titre": "Editorial calendar, ready to publish",
    "social_pack": "{reseau} content pack",
    "social_jour": "Day {jour}",
    "social_colonnes": ("Day", "Angle", "Goal", "Text", "Hashtags",
                        "Visual idea"),
    "social_mode_emploi_titre": "How to use this pack",
    "social_mode_emploi": (
        "Publish one piece of content per working day. Adapt the figures and "
        "examples to your own reality: a credible post beats a perfect one. "
        "The calendrier.csv file imports directly into a spreadsheet or a "
        "scheduling tool."),

    "emails_sous_titre": "{nombre} messages, one every {rythme} day(s)",
    "emails_mode_emploi_titre": "How to send this sequence",
    "emails_ordre": (
        "This sequence is sent in order, starting on the day of sign-up. The "
        "schedule below gives the delay for each message; most e-mail tools "
        "ask for it in this form."),
    "emails_csv": (
        "The CSV file delivered with this document imports directly into an "
        "e-mail tool: one line per message, with the subject, the preview and "
        "the body."),
    "emails_avant_titre": "Before you send",
    "emails_avant": (
        "Reread each message with one specific person on your list in mind. "
        "Replace the square brackets with your own information, and check that "
        "the unsubscribe link is there: it is mandatory, and leaving it out is "
        "enough to get your e-mails filtered as spam."),
    "emails_colonnes": ("Day", "Subject", "Preview", "Body", "P.S.", "Action"),
    "emails_objet": "Subject",
    "emails_apercu": "Preview",
    "emails_demande": "What this message asks for",
    "emails_objectifs": {
        "bienvenue": "welcome a new subscriber and build trust",
        "vente": "lead to a first purchase, without pushing",
        "fidelisation": "bring back a customer who has already bought",
        "relance": "wake up a list that has gone quiet",
    },

    "memo_titre": "Cheat sheet — {sujet}",
    "memo_sous_titre": "{lignes} point(s) in {blocs} block(s)",
    "memo_promesse": "The essentials, to keep at hand",
    "memo_colonnes": ("Block", "Kind", "Line"),
    "memo_genres": {"liste": "list", "etapes": "steps", "tableau": "table",
                    "reperes": "key points"},

    "unite_sections_simple": "sections",
    "logiciel_ce_que_fait": "What this tool does",
    "logiciel_installation": "Installation and use",
    "logiciel_verification": "Code check",
    "logiciel_fonctions": "Features",
    "logiciel_limites": "What this tool does not do",
    "logiciel_limites_pourquoi": ("Saying so avoids disappointment, and the "
                                  "refund requests that come with it."),
    "logiciel_cli": (
        "Nothing to install: the script only uses the Python standard "
        "library.\n\n"
        "```\npython3 source/outil.py --help\n```\n\n"
        "Typical use:\n\n```\n{utilisation}\n```\n\n"
        "Run the tests with:\n\n```\npython3 source/test_outil.py\n```"),
    "logiciel_web": (
        "Open `source/index.html` in any browser. There is nothing to install "
        "and nothing to configure: all the code is in this file, and it works "
        "offline.\n\n"
        "To put it online, upload this single file to any static host."),
    "logiciel_extension": (
        "1. Open `chrome://extensions` in Chrome.\n"
        "2. Turn on “Developer mode” at the top right.\n"
        "3. Click “Load unpacked”.\n"
        "4. Choose the `source/` folder.\n\n"
        "To publish it, zip the `source/` folder and upload the archive to the "
        "Chrome Web Store."),
    "logiciel_verifie": ("This code was checked before delivery. Here is "
                         "exactly what was checked.\n"),
    "logiciel_colonnes": ("File", "Check", "Result"),
    "logiciel_correct": "passed",
    "logiciel_a_corriger": "**needs fixing**",
    "logiciel_non_execute": "not run: {refus}",
    "logiciel_demarre": "starts correctly",
    "logiciel_echec": "**failed**",
    "logiciel_execution": "actual run",
    "logiciel_remarques": "The check raised {nombre} minor remark(s).",
    "logiciel_attention": (
        "**Warning:** one or more files did not pass the check. Review them "
        "before any sale."),
    "logiciel_verifie_par": {
        "syntaxe + arbre syntaxique": "syntax + syntax tree",
        "controle structurel (node indisponible)": "structural check (node unavailable)",
        "controle structurel (node absent)": "structural check (node missing)",
    },
    # Le debut d'un motif de refus ; le detail technique qui suit reste tel
    # que la verification l'a ecrit.
    "logiciel_refus": {"analyse statique": "static analysis",
                       "lancement impossible": "could not start"},
    "logiciel_soucis": {
        "syntaxe": "syntax error: {valeur}",
        "import": "imports “{valeur}”: system or network access",
        "appel": "calls “{valeur}()”",
        "ecriture": "writes outside the working folder: {valeur}",
    },
    "logiciel_tests_unitaires": "unit tests",

    # --- the quiz sold on its own -----------------------------------------------
    "quiz_produit_sous_titre": "{nombre} questions — {niveau} level",
    "quiz_niveaux": {"debutant": "beginner", "intermediaire": "intermediate",
                     "avance": "advanced"},
    "quiz_promesse": "Test yourself, and understand your mistakes",
    "quiz_promesse_page": ("Check your answers without sending anything: "
                           "everything happens in your browser."),
    "quiz_consignes": "Instructions",
    "quiz_consigne": ("Answer every question before looking at the answer key. "
                      "Only one option is correct per question."),
    "quiz_bareme": "Scoring",
    "quiz_bareme_texte": (
        "{acquis} correct answers or more: you have it.\n"
        "{revoir} to {presque}: reread the explanations of the questions "
        "you missed.\n"
        "Fewer than {revoir}: go back over the topic before testing "
        "yourself again."),
    "quiz_questions": "Questions",
    "quiz_corrige": "Answer key",
    "quiz_reponse_pdf": "{numero}. Answer {lettre} — {texte}",
    "quiz_colonnes": ("Module", "Question", "A", "B", "C", "D", "Correct",
                      "Explanation"),

    # --- the last page of a volume in a series ----------------------------------
    "serie_page": "What comes next",
    "serie_tome_lu": ("You have just read volume {rang} of the **{serie}** "
                      "series. Each volume stands on its own, but they "
                      "answer one another."),
    "serie_appartient": "This story belongs to the **{serie}** series.",
    "serie_precede": "### What came before",
    "serie_suite": "### What comes next",
    "serie_tome": "**Volume {rang} — {titre}**",
    "serie_avis": (
        "If you enjoyed this story, the best thing you can do for its author "
        "takes two lines: a review where you bought it. That is what decides "
        "whether someone else will find it."),

    # --- the file names the buyer opens first -------------------------------------
    "fichier_notice": "README.md",
    "fichier_licence": "LICENSE.txt",
    "fichier_cahier": "workbook",
    "fichier_manuel": "-manual",
    "fichier_extrait": "{nom}-excerpt",
    "fichier_tableau": "table-{rang:02d}-{nom}.csv",
}

LIBELLES: Dict[str, Dict[str, Any]] = {"fr": FR, "en": EN}


def mobilier(code: str) -> str:
    """La langue du mobilier pour un code de langue : la sienne, ou l'anglais."""
    return code if code in LIBELLES else "en"


def textes(code: str) -> Dict[str, Any]:
    """Tous les libelles d'une langue."""
    return LIBELLES[mobilier(code or "fr")]


def libelle(code: str, cle: str, **valeurs: Any) -> Any:
    """Un libelle, rempli s'il y a des valeurs."""
    gabarit = textes(code)[cle]
    return gabarit.format(**valeurs) if valeurs else gabarit
