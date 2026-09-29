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

## Correction du 15/09/2026 : ces listes étaient inventées

Reproche reçu, et exact : *« tu as inventé beaucoup, je voulais du réel, tu
aurais pu chercher sur internet pour ça »*.

La première version de ce module portait en commentaire « données recopiées,
donc périssables ». **Recopiées de personne.** Les genres, les sous-genres, les
soixante-dix tropes et les tranches d'âge d'un album sortaient de ma tête. Le
dépôt refuse un pourcentage énoncé sans marqueur de source ; il n'avait rien
pour refuser une *liste* énoncée sans source — et c'est le même défaut à plus
grande échelle, parce qu'un sous-genre inventé envoie fabriquer pour un rayon
qui n'existe pas.

### Ce qui remplace quoi

| donnée | avant | maintenant |
|---|---|---|
| catégories | 7 genres de mon cru | les catégories de premier niveau de la fiction **chez Amazon**, telles qu'elles s'appellent |
| sous-genres | ~40 traduits en français | ceux qu'une source nomme, en anglais — c'est le nom du rayon |
| tropes | ~70 inventés, 7 genres | les 8 les plus cherchés, **romance seulement** |
| fin exigée en romance | ma règle | définition **RWA** : *« a central love story and an emotionally satisfying and optimistic ending »* |
| album : pages | 12 et 16 | **14 doubles-pages** (standard 32 pages, norme SCBWI) |
| album : mots/phrase | 10, 14, 20 | **8** (comprise à ~100 %) et **14** (à plus de 90 %) |

Les tropes sont maintenant **dans la langue où ils circulent**. Un lecteur
francophone tape « enemies to lovers », pas « ennemis puis amants » : c'est
ainsi qu'il cherche, et c'est ce qui décide de la découvrabilité.

### Ce qui n'a pas de source le dit

Deux cas assumés :

- **les ambiances** — aucune source ne publie de liste. Leur entrée dans
  `SOURCES` commence par `SANS SOURCE`. Les garder est un choix ; les
  présenter comme un relevé serait un mensonge ;
- **les tropes hors romance** — aucune source consultée ne les recense avec la
  même régularité. `tropes_du_genre("policier")` rend donc **rien**, et
  l'invite n'en propose aucun plutôt que d'en proposer de faux. Combler le
  trou serait retomber dans le défaut que cette correction répare.

La liste des catégories est **partielle par construction**, et le dire fait
partie de la donnée : Amazon compte plus de seize mille catégories et n'en
publie aucune taxinomie complète.

### Le garde-fou qui empêche que ça recommence

`tests/test_sources_des_donnees.py` lit la structure du module et exige que
**chaque table de données ait son entrée dans `SOURCES`**, avec une date, un
aveu `SANS SOURCE`, ou la mention « pas une donnée de marché ». Il vérifie
aussi les **valeurs** : qu'un chiffre ne change pas sans que sa source change
— sinon on réinventerait sous couvert de provenance.

Et comme les deux fois précédentes, la campagne de mutation a montré qu'un
détecteur vert ne se garde pas lui-même : il a fallu lui donner un témoin qui
appelle **la même fonction** que le test.

---

## Seconde passe : « creuse ce point, et verifie aussi les autres donnees »

*15/09/2026, meme jour.* La premiere correction en avait laisse passer trois.

### Ma correction precedente etait fausse aussi

J'avais garde une tranche « 9-12 ans » pour le conte, en l'adossant aux
*early readers* (1 000 à 5 000 mots). Ces lecteurs-là ont **5 à 7 ans**.

Le relevé du jour est sans ambiguïté : à neuf ans, on ne lit plus un album,
on lit un livre **en chapitres** — 10 000 à 20 000 mots pour les 7-10 ans
(60 à 120 pages imprimées), 25 000 à 50 000 pour les 8-12 (35 000 en moyenne
pour un premier livre).

Ce n'est pas un album plus long : c'est un autre objet. Pas de doubles-pages,
pas une image par page, une structure de chapitres. **La tranche est
retirée**, et son absence est documentée dans `SOURCES` — sinon la prochaine
lecture la remettrait.

Ce que l'usine sait faire pour cet âge s'appelle `roman`, et les longueurs
sont dans `fiction.MOTS_ATTENDUS`, où `chapter books` et `middle grade`
figurent désormais.

### Deux fourchettes corrigées

| | avant | après |
|---|---|---|
| `epic fantasy` | 100 000 – 150 000 | **100 000 – 200 000** |
| `middle grade` | 20 000 – 40 000 | **25 000 – 50 000** |

La fantasy épique est le seul genre où les sources divergent vraiment : de
100–120 K si l'on lit « ce que le lecteur attend », jusqu'à 200 K si l'on lit
« ce qu'un premier roman fait ». La règle du module est de retenir la
**fourchette la plus large**.

### Amazon le dit mieux que moi

Ma source disait « plus de seize mille catégories ». C'est une reprise. La
page d'aide d'Amazon dit, elle : *« there are thousands of book categories in
each Amazon marketplace, and they can change over time »*, et renvoie à la
navigation du magasin plutôt qu'à une liste. C'est désormais cette
phrase-là qui est citée.

### Et les données qui n'étaient pas de la fiction

La vérification a été étendue à `pipelines/social.py`, qui n'avait **aucune
source** — et dont les chiffres étaient les plus périssables du dépôt :

| | avant | après |
|---|---|---|
| X/Twitter | « 240 caractères », sans source | **280** (gratuit) |
| TikTok | rien | **4 000** — passé de 2 200 en 2024, et l'usine ne l'aurait pas su |
| LinkedIn | « 120-220 mots » | **3 000**, replié après **210** |
| Instagram | « 60-140 mots » | **2 200**, replié après **125** |

Le second chiffre est celui qui compte, et il manquait partout. Un post
LinkedIn peut faire trois mille caractères — **seuls les deux cent dix
premiers s'affichent** avant « voir plus ». Ce qui décide qu'on clique tient
là. Et chez X, une adresse compte pour **23 caractères** quelle que soit sa
longueur : un fil qui colle un lien par message en perd vingt-trois à chaque
fois, sans que personne ne les voie partir.

Les consignes d'écriture sont désormais **bâties sur** ces limites, jamais
recopiées à côté : deux endroits pour le même chiffre divergent, et c'est
celui de l'invite qui ferait écrire des posts tronqués.
