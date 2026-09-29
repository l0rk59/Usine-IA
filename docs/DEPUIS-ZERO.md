# L'usine décide, on ne remplit rien

C'est sa raison d'être : des appels d'API, un sujet, un produit. Pas un
formulaire de dix menus qu'un humain remplit.

## Ce qu'elle décidait, et ce qu'elle imposait

Le brief automatique décidait **trois** choses — audience, ton, taille. Tout
le reste tombait sur une valeur en dur, et en silence :

| type | réglage | valeur imposée |
|---|---|---|
| `social` | réseau | toujours **linkedin** |
| `emails` | intention | toujours **bienvenue** |
| `quiz` | niveau | toujours **intermédiaire** |
| `logiciel` | cible | toujours **cli** |
| `conte` | tranche d'âge | toujours **6-8 ans** |

Cinq de ces champs n'offraient **même pas d'option vide** : on ne *pouvait*
pas dire « que l'usine décide ». Tout pack de posts partait donc sur LinkedIn,
toute séquence d'e-mails était une séquence de bienvenue, tout outil logiciel
était une ligne de commande.

Et pour la fiction, aucun des neuf réglages de promesse n'était décidé. Le
modèle écrivait **sans contrat de genre** — alors que toute la couche de
promesse existait, construite pour ça.

> Un réglage par défaut n'est pas neutre, il est juste invisible.

## Ce qui a changé

**Plus aucun choix imposé.** Tout champ de choix offre le vide, et le vide
veut dire « que l'usine décide ».

**Une étape qui décide, au point unique.** `brief.decider_les_reglages` lit la
déclaration du catalogue — le libellé de chaque champ, ses valeurs admises,
son aide — et demande au modèle de choisir **d'après le sujet**. Elle est
appelée depuis `catalogue.executer`, par où passent la ligne de commande, le
menu Termux, le tableau de bord et la boucle continue. Une implémentation,
quatre interfaces, et un type ajouté demain en hérite sans qu'on y touche.

**La décision se voit.** Chaque valeur choisie part dans le journal et dans la
fiche du produit. Une décision qu'on ne retrouve plus six mois après n'aide
pas à comprendre le résultat — c'est la même opacité qu'un défaut invisible,
avec une étape en plus.

## Ce que l'usine ne décide pas

Elle décide **le produit**. Elle ne décide pas ce que vous voulez dépenser ou
sauter.

| laissé à vous | pourquoi |
|---|---|
| `sans_marche`, `sans_veille`, `sans_essai`, `sans_bareme` | une case décochée veut dire « fais-le », pas « décide à ma place » |
| `visuels` | chaque visuel coûte un appel d'image |
| `reliure` | la marge dépend de l'imprimeur, pas du sujet |
| `serie` | vide veut dire **aucune** — un récit isolé |

Ce dernier point est une correction dans la correction : la première version
faisait inventer un nom de série à chaque nouvelle. Tout champ vide ne veut
pas dire « décide pour moi ».

## Trois refus, écrits dans le code

**Un champ rempli n'est jamais touché.** Ce que vous avez choisi tient.

**Une valeur hors liste est écartée, pas corrigée.** Accepter « thriller
psychologique » là où le champ attend « thriller » ferait entrer dans la fiche
une valeur que rien d'autre ne sait relire.

**Un modèle muet laisse les réglages vides, et le dit.** Un réglage à moitié
deviné serait pire que pas de réglage : on croirait que le sujet a été lu.

## Le maillon qui manquait

Les réglages de fiction ne voyagent pas en arguments — ils sont déposés dans
`ctx.meta["fiction"]`, et la promesse était posée **avant** la décision.
L'usine choisissait donc un genre, une ambiance et une fin, et la chaîne
écrivait sans les voir. Mesuré : promesse **vide** après une fabrication
depuis zéro. `executer` repose la promesse une fois la décision prise.

## Ce qui garde tout cela

`tests/test_depuis_zero.py`, quinze tests. Dix mutations, toutes vues.

Deux pièges du dépôt s'y sont présentés : le **cache des réponses IA** — deux
cas de test qui partagent une invite partagent une entrée, et le second
n'exerce rien, ce qui a rendu vert un test qui ne testait plus rien — et le
**simulateur qui ne sait pas répondre**, qui faisait passer le chemin dégradé
pour le chemin normal.

## La ligne de commande et le menu n'en profitaient pas

Mesure du 24/09/2026, en comptant les appels de décision par porte, pour les
dix-sept types qui ont des réglages à décider :

| Porte | Décisions de l'usine |
|---|---|
| tableau de bord | 1 par produit, 17 types sur 17 |
| ligne de commande | **0**, 17 types sur 17 |

La décision vit dans `catalogue.executer`, que le tableau de bord et la boucle
appellent. Les commandes de la ligne de commande appelaient chacune leur
chaîne directement, avec leurs propres valeurs : `--reseau` valait
« linkedin », l'intention d'une séquence « bienvenue », le niveau d'un quiz
« intermediaire », et chaque nombre la valeur du catalogue — un « 50 » par
défaut que rien ne distingue d'un « -n 50 » tapé. Le menu Termux passe par
ces commandes ; il avait en plus ses propres défauts, qu'Entrée choisissait.

Toutes les commandes passent maintenant par le catalogue. Un argument que
personne n'a tapé vaut `None`, et c'est ce qui le laisse à l'usine ; un
argument tapé est respecté et n'est pas redemandé. Le menu propose en tête de
chaque liste « L'usine décide », et c'est ce qu'Entrée choisit.
