# Pour la fiction, on ne cherche pas une niche

*Ajouté le 15/09/2026, à la demande : « je ne pense pas que ce soit des niches
que l'on recherche pour ce type de produit mais quelque chose d'autre, sauf
que je ne sais pas ».*

L'intuition était juste, et le défaut qu'elle désigne était réel.

## Ce qu'on demandait à un roman

Une niche, partout ailleurs dans l'usine, c'est un **problème que quelqu'un
paie pour résoudre**. Toute la prospection est bâtie là-dessus. L'invite
demandait, pour chaque idée :

```
"probleme": "le probleme precis resolu"
"acheteur": "qui paie et pourquoi"
"promesse": "..."
"concurrence": "faible|moyenne|forte"
"premier_canal": "ou trouver les 10 premiers acheteurs"
```

Appliqué à un roman, aucune de ces cinq questions n'a de réponse honnête.
Personne n'achète une romance pour résoudre un problème. Mais **un modèle à
qui l'on pose une question sans réponse en fabrique une** : on obtenait des
fictions habillées en produits pratiques, avec un « problème précis résolu »
inventé après coup.

C'est une variante de la règle que ce dépôt applique partout : *un réglage par
défaut n'est pas neutre, il est juste invisible*. Ici, c'est la **question** qui
n'était pas neutre.

## Ce qu'on cherche à la place : une promesse de lecture

Elle se décrit en cinq choses, toutes absentes du vocabulaire des niches :

| | |
|---|---|
| **genre et sous-genre** | où le livre se range, et qui le cherche |
| **tropes** | ce que le lecteur vient retrouver |
| **ambiance** | ce qu'il vient ressentir |
| **fin attendue** | ce qu'il ne pardonnera pas qu'on lui refuse |
| **chaleur** | ce qu'il attend, et dont l'inverse le fâche |

**Relevé le 15/09/2026** sur l'état du marché de l'édition indépendante : la
découverte se fait par **trope** avant de se faire par genre, et les
sous-genres se sont fragmentés en micro-genres (romantasy, dark romance,
romance sportive, cozy mystery). Un livre bien écrit déçoit quand l'emballage
promet une expérience et que le texte en livre une autre.

Concrètement : un lecteur ne tape pas « romance contemporaine », il tape
« ennemis puis amants ». **Un titre qui ne nomme pas son trope ne se trouve
pas.**

```bash
usine file --fiction              # l'usine choisit le point de départ
usine file --fiction "Bretagne"   # à partir d'un décor
```

```
  2 promesse(s) explorees, 2 mise(s) en file.
    « Le fantome du phare de Kerlouan » — cozy mystery / enquete au village, huis clos
    « Ce que la lande a garde » — romance contemporaine / seconde chance
    [!] « Ce que la lande a garde » : Une romance qui finit « tragique » rompt
        le contrat du genre.
```

## Le contrat de genre, vérifié avant de fabriquer

En romance, une fin malheureuse n'est pas un choix d'auteur : c'est un
**manquement au contrat**, et le premier motif de retour. Le vérifier après
avoir écrit le livre coûte le livre entier.

Le contrôle est **déterministe, zéro appel de modèle** : il compare deux
réglages entre eux, ce qui se vérifie sans lire une ligne. Et il **se tait dès
qu'il n'est pas sûr** — un sous-genre inconnu ne déclenche rien du tout,
parce qu'un garde-fou qui signale à tort finit ignoré.

| ce qu'il voit | ce qu'il dit |
|---|---|
| romance + fin tragique | rupture de contrat |
| policier + fin tragique | rien : la règle est propre à la romance |
| sous-genre inconnu + fin tragique | rien : il ne sait pas |
| jeunesse + chaleur explicite | à vérifier avant publication |

## Dix réglages qui ne sont pas ceux du non-fictionnel

Un guide se règle par audience, promesse de résultat et niveau de difficulté.
Ces trois-là n'ont aucun sens pour un roman. Les réglages de fiction sont
déclarés **une fois** (`catalogue.champs_de_fiction`) et partagés par tous les
types de la famille — les recopier type par type garantirait qu'un type ajouté
plus tard en oublie la moitié, et un réglage manquant ne se voit pas : la
chaîne se contente du défaut.

Un test vérifie les deux sens : chaque type de fiction les reçoit **tous**, et
aucun type pratique n'en reçoit **aucun**.

## Le chemin qu'un réglage doit parcourir pour ne pas être un mensonge

C'est le point où ce travail pouvait échouer en silence. Neuf réglages
saisissables, enregistrables — et lus par personne.

Deux chemins mènent à la fabrication, et ils ne portent pas les réglages de la
même façon : la ligne de commande sur un `Namespace`, la file de production
dans un dictionnaire. Aucun des deux mécanismes existants ne les transmettait
(`executer` ne passe en argument que les clés déclarées dans `options`).

D'où **un seul point de dépôt** — `ctx.meta["fiction"]` — et un seul lecteur.
Un champ ajouté à `champs_de_fiction` arrive ainsi dans les invites sans qu'on
touche à une seule chaîne.

Et deux endroits seulement où la promesse entre dans le texte :

- **la bible**, une fois, en entier : le sous-genre décide de la distribution,
  de la charpente et de la fin. Le poser après la bible revient à ne pas le
  poser ;
- **chaque scène**, en abrégé : le temps du récit, le point de vue et la
  chaleur. Ce sont les trois réglages qui se perdent phrase après phrase — un
  modèle qui tient le passé pendant huit scènes glisse au présent à la
  neuvième, et rien ne le rattrape. Répéter le bloc entier trente fois
  coûterait son volume multiplié par trente sans rien ajouter.

**Deux mutations ont montré que ce câblage n'était gardé par rien.** Les tests
vérifiaient `consignes_de_scene()` toute seule ; supprimer son injection dans
`rediger_scene` ne faisait échouer aucun test. L'ingrédient était gardé, le
câblage non — exactement le défaut que ce dépôt retrouve à chaque audit. Les
tests appellent maintenant la vraie rédaction et lisent l'invite envoyée.

## Situer une longueur, sans la juger

`MOTS_ATTENDUS` porte les fourchettes du marché par sous-genre. Sources :
guides de longueur par genre consultés le **15/09/2026** (Publishing Xpress,
WordTally, Authorlytica, Kevin Anderson & Associates), qui s'accordent à
quelques milliers de mots près.

Ce chiffre ne pilote rien. Il rend une **mesure** :

> *27 000 mots, en dessous de la fourchette attendue pour « romance
> contemporaine » (50 000 à 90 000). Un format court se vend, mais il se vend
> à un autre prix et à un autre lecteur.*

L'usine n'a pas de quoi trancher si un format court est un choix ou un
accident. Un test vérifie que le mot « trop court » n'y apparaît pas.

## Données recopiées, donc périssables

Comme les quotas de `config.py`. Les listes de genres, de sous-genres et de
tropes sont un **vocabulaire de départ**, pas une vérité. Elles servent à
proposer, jamais à interdire : un sous-genre absent de la liste reste
saisissable, et il est gardé tel quel — « romantasy » n'existait pas quand ces
listes ont commencé.
