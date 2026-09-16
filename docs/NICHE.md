# Quand on ne dit pas quoi produire

## Le trou que personne ne voyait

L'usine sait chercher des niches. La fonction s'appelle `prospecter()`, elle
existe depuis longtemps, elle est testée, et son commentaire dit exactement ce
qu'elle fait : « c'est ce qui permet à l'usine de CHOISIR ce qu'elle fabrique
au lieu d'attendre qu'on le lui dise ».

Elle cherche des niches **voisines d'une graine**. Et la graine vient de
`graine_de_depart()`, qui rend la niche ayant le mieux rapporté.

Sur une installation neuve, il n'y a rien. Donc pas de graine. Donc pas de
prospection :

```
graine sur un atelier neuf : ''
  journal: Aucun historique pour choisir une niche : ajoutez-en une a la main,
           l'usine partira de la.
resultat: {'graine': '', 'ajoutees': 0, 'ecartees': [], 'pistes': 0}
```

Rien n'échouait. Le message était poli, la fonction rendait un résultat
cohérent, aucun test ne bronchait — un test gardait même ce comportement, parce
qu'il avait été observé et qu'un comportement observé finit par passer pour un
comportement voulu.

**La seule fonction qui permet à l'usine de choisir seule était inatteignable
depuis le seul état où tout le monde commence.**

## Et le sujet était obligatoire

`_options_communes()` déclarait `sujet` en positionnel obligatoire pour les dix
chaînes. La seule façon de ne pas dicter la niche était donc de ne pas
produire.

Le tableau de bord, lui, refusait **en silence** :

```js
if (!sujet) { $('sujet').focus(); return; }
```

Pas de message, pas d'erreur, rien dans le journal. On recliquait sur le bouton
en croyant qu'il ne marchait pas.

## Proposer n'est pas mesurer

Le démarrage à froid aurait pu s'écrire en trois lignes : demander au modèle
huit niches et prendre la première. Ce dépôt s'y refuse — *pas de verdict non
mesuré*. Une niche sortie de l'imagination d'un modèle n'est pas un choix
motivé, et la présenter comme tel serait le pire des deux mondes : arbitraire,
et habillé en décision.

`domaines_de_depart()` fait donc trois choses, dans cet ordre :

1. **proposer large** — le `prospecteur` (celui qui a le rôle `raisonnement`)
   rend des *domaines*, pas des titres de produits : trois à six mots, tels
   qu'un acheteur les taperait ;
2. **mesurer chacun** sur les sources publiques, par `marche.sonder()` ;
3. **écarter ce dont la demande ne se voit pas**, et classer le reste par
   demande décroissante.

Ce qui n'a **pas pu** être mesuré — réseau coupé, sources muettes — est rendu
quand même, en fin de liste, et **dit comme tel** :

```
Aucune source de marche n'a repondu : ces domaines sont PROPOSES, pas mesures.
```

Une panne de réseau n'empêche pas de démarrer. Elle empêche de prétendre qu'on
a mesuré.

## Trois sources, pas une

Pour **un** produit, `choisir_une_niche()` regarde dans cet ordre :

| | |
|---|---|
| la **file d'attente** | une niche y attend déjà : quelqu'un, ou l'usine, l'a choisie avant. En inventer une onzième pendant que dix patientent gaspille un appel et fabrique un doublon |
| le **voisinage de ce qui a rapporté** | la seule source adossée à des ventes réelles |
| un **domaine de départ mesuré** | le cas de toute installation neuve |

La file se **regarde**, elle ne se consomme pas : `prochain()` marque l'entrée
« en cours », et une commande unique qui la volerait à l'usine continue
laisserait celle-ci refabriquer un sujet déjà traité.

## Ce que ça donne

```bash
usine ebook          # sans rien derrière
```

```
== L'usine choisit la niche
  3 domaines proposes — mesure sur les sources publiques...
    la facturation des independants — demande forte (2/4 sources)
    la reprise de course a pied apres 40 ans — demande moyenne (2/4 sources)
    ecarte « le potager en bac sur balcon » — 2/4 sources
  Premiere niche, choisie par l'usine : « la facturation des independants ».
  Brief automatique : audience, ton a decider...
```

Le choix se fait au même endroit pour les trois interfaces — ligne de commande,
menu Termux, tableau de bord. Deux façons de choisir une niche divergeraient, et
l'une des deux vieillirait sans que rien ne le dise.

Dans le navigateur, le choix a lieu dans le **fil de fabrication**, pas dans la
requête HTTP : un sondage de marché par domaine prend des dizaines de secondes,
et la page paraîtrait figée. La requête répond tout de suite avec un numéro de
travail, et la niche retenue arrive dans le journal en direct.

## Trois tests qui ne gardaient rien

La campagne de mutation en a trouvé trois, et le troisième est le plus
instructif :

**Une panne, ce n'est pas des sources muettes.** Le test coupait le réseau en
levant une exception — ce qui passe par la branche `except` et ne touchait
jamais la ligne qui décide si le classement est mesuré. Il était vert alors que
`mesure` pouvait valoir `True` en permanence. Le cas manquant est celui où les
sources **répondent** sans rien dire d'exploitable : tous les signaux ont l'air
normaux.

**Deux pièces qui marchent ne font pas une chaîne.** Un test vérifiait que
l'analyseur accepte un sujet vide, un autre que `choisir_une_niche()` choisit —
et rien ne vérifiait que la ligne de commande appelle la seconde. Retirer
l'appel laissait les deux tests verts, et `usine ebook` fabriquait sur le sujet
`""`.

**Un import renommé garde le nom.** Le test du tableau de bord cherchait
`choisir_une_niche` dans le source. Remplacer l'import par
`from ..production import prospecter as choisir_une_niche` laisse le nom en
place : test vert, fabrication partie sur autre chose. C'est la règle du dépôt,
retrouvée une fois de plus — *un garde-fou satisfait par une homonymie ne garde
rien*. Il fait maintenant tourner le fil et regarde le sujet retenu.

Les vingt-et-une mutations de la campagne sont vues.

## La recherche de niche ne pouvait pas aboutir

Signalé le 15/09/2026, journal à l'appui : huit domaines proposés, huit
écartés, « aucune niche trouvée ». À chaque fois.

```
8 domaines proposes — mesure sur les sources publiques...
  ecarte « cours de photographie smartphone » — 3/4 sources
  ecarte « guide méditation débutants stress » — 3/4 sources
  ...
Aucune niche trouvee : donnez-en une.
```

### Le message ment sur sa propre raison

« 3/4 sources » est la **fiabilité**, affichée là où devait figurer la raison.
Le rejet ne venait pas de la quatrième source : trois sur quatre répondaient.
On cherchait donc une panne de réseau là où il n'y en avait pas.

### Le verdict reposait sur une seule source, avec des seuils inventés

`demande` était calculé par Hacker News, et par lui seul. Wikipedia, Stack
Exchange et Open Library ne contribuaient rien au verdict qui décide.
Au-dessus de 3 000 discussions « forte », au-dessus de 400 « moyenne », en
dessous **« faible » — et écarté**.

Ces deux nombres n'avaient jamais été mesurés. Relevé du 15/09/2026 sur l'API
de recherche de Hacker News :

| requête | discussions |
|---|---|
| machine learning | 18 539 |
| kubernetes | 11 481 |
| photography | 5 203 |
| startup funding | 4 642 |
| python programming | 3 078 |
| meditation | 2 290 |
| personal finance | 1 819 |
| gardening | 566 |
| meal planning | 196 |
| freelance invoicing | 126 |
| **facturation freelance** | **0** |
| **potager balcon** | **0** |

L'échelle suit la **largeur du mot-clé** et sa présence dans un forum
anglophone de développeurs. Elle ne suit pas la demande d'un marché.

Or un nom de niche fait plusieurs mots par nature — « modèles CV créatifs
freelance » — et une niche francophone rend zéro quoi qu'il arrive. Même les
équivalents anglais des domaines proposés restaient sous le seuil :
*smartphone photography course* 1, *meditation for beginners* 10, *freelance
resume template* 5.

**Toutes les pistes que le prospecteur propose étaient donc écartées, par
construction.** C'était vrai depuis le premier jour.

Le code le savait, d'ailleurs. Il écrivait :

> « Ces sources sont anglophones : une requête en français y renvoie peu de
> résultats, ce qui ne dit RIEN du marché francophone. »

…et écartait la niche sur cette mesure-là.

### La correction

**Une source anglophone généraliste peut confirmer un intérêt ; elle ne peut
pas prouver son absence.** Zéro discussion sur Hacker News à propos de
« potager balcon » ne dit rien du marché francophone du potager en balcon.

Sous le seuil, `demande` vaut désormais `None` — *non mesurée* — et plus
jamais « faible ». Les deux seuils restent, sourcés par le relevé ci-dessus,
et ils servent à **promouvoir** une piste, jamais à l'écarter.

`production.py` n'écarte plus rien sur ces mesures : les pistes confirmées
passent devant, les non mesurées ferment la marche. Elles sont un filet, pas
une recommandation — et le journal le dit maintenant en toutes lettres.

### Ce qui garde la correction

Une campagne de mutation a d'abord rendu deux `[RATE]` : les tests de
sélection injectaient `demande` directement dans la lecture, sans jamais
exercer le calcul qui la produit. Remettre `demande = "faible"` dans Hacker
News ne faisait échouer aucun test — le défaut vivait précisément là où rien
ne regardait. `UneSourceAnglophoneNePeutPasRefuterUneNiche` teste désormais
`marche.interpreter` lui-même. Cinq mutations, toutes vues.


---

# Combien de sources, et laquelle mentait

Audit du 16/09/2026, en interrogeant les vraies API depuis une machine réelle.

## Quatre sources, et ce qu'elles couvrent vraiment

`hacker_news`, `wikipedia`, `stack_exchange`, `open_library`. Mesurées sur six
noms de niches françaises réalistes :

| source | répond | ce que ça vaut |
|---|---|---|
| hacker_news | 6/6 | des **zéros** sur du français |
| stack_exchange | 6/6 | des **zéros** sur du français |
| open_library | 6/6 | des **zéros** sur du français |
| wikipedia | **1/6** | et la seule réponse était fausse |

**Répondre n'est pas mesurer.** Trois sources sur quatre répondent toujours, et
répondent zéro dès que le mot-clé n'est ni anglais ni un terme de développeur.
`demande` vaut `None` sur les six.

## Le défaut : la seule source francophone rendait un chiffre inventé

Wikipedia est la seule des quatre à interroger le domaine **`fr`**. C'est donc
la seule qui puisse dire quelque chose d'une niche française. Elle disait faux.

| niche | article retenu | vues/mois |
|---|---|---|
| « le tricot » | **Le Tricheur à l'as de carreau** | 2 218 |
| « la facturation des indépendants » | **DKV Euro Service** | 145 |

Un tableau de Georges de La Tour, et une société de cartes carburant. Deux
défauts empilés, le second caché derrière le premier.

**1. `opensearch` compare des préfixes de titres.** Interrogée avec « le
tricot », l'API rend « Le Tricheur… » et **jamais** « Tricot » : l'article
défini français rend la bonne page inatteignable. On l'interroge maintenant
avec le nom nu — accents compris, car demander « meditation » rendait un
homonyme à 10 vues/mois quand « Méditation » en fait plusieurs milliers.

**2. Quand aucun titre ne correspondait, le code départageait les candidats à
la fréquentation** — c'est-à-dire qu'il élisait le plus consulté des articles
sans rapport. Le nombre avait l'air d'une mesure. On ne lui attribue plus rien,
et le rapport le dit.

## Ce que la recherche plein texte apporte

`opensearch` cherche des titres ; `list=search` cherche dans le texte. En
repli, elle trouve ce qu'un nom de niche ne titre jamais :

```
le tricot                             2 209 articles
la facturation des independants          232
la meditation pour debutants             183
le potager en bac sur balcon              21
la reparation de theremines a vapeur       0      (inventée)
le pliage de serviettes pour chats         0      (inventée)
```

Elle sépare le réel de l'inventé. Le compte est **rendu, jamais interprété** :
six points de relevé ne font pas un seuil, et un verdict non mesuré vaut moins
qu'une mesure honnête.

En repli et non en remplacement : quand le sujet **est** un titre d'article,
`opensearch` le trouve mieux, et le classement par proximité a été réglé sur
lui.

## Les sources écartées, et pourquoi

Testées en vrai le 16/09/2026, sans clé, depuis cet environnement :

| candidate | verdict |
|---|---|
| **iTunes podcasts** (`country=fr`) | **écartée** — 30 podcasts pour « le pliage de serviettes pour chats », 10 pour « le tricot ». Elle apparie des mots isolés. Un garde-fou qui crie à tort finit ignoré. |
| iTunes ebooks | plausible (0 sur les deux niches inventées) mais elle mesure la **concurrence éditoriale**, l'axe qu'`open_library` couvre déjà |
| Reddit | HTTP 403 — l'API publique refuse les adresses de centre de données |
| Google Books | HTTP 429 sans clé |
| OpenAlex | HTTP 429, et un axe académique sans rapport avec un marché |
| archive.org | 1 document sur une niche vivante : ne discrimine pas |

**La conclusion de l'audit n'est pas « il manque des sources ».** C'est que la
seule source capable de parler français mentait, et qu'une cinquième source
anglophone n'aurait rien changé. Ajouter une source qui apparie des mots au
hasard aurait ajouté du bruit en croyant ajouter du signal.

## Ce qui garde la correction

`tests/test_wikipedia_niche.py`, onze tests, **aucun ne sort sur le réseau** :
les réponses des deux API sont figées. Campagnes de mutation : 9 puis 3
mutations, toutes vues.

Une mutation a montré qu'un `_sans_accent` dans le retrait d'article ne servait
à rien — aucun article français ne porte d'accent. C'est la casse qui comptait.
Retiré.


---

# « Ça cherchera toujours les mêmes huit ? »

Deux craintes, et elles n'avaient pas le même sort.

## Les sujets ne sont pas écrits dans le code

« la facturation des indépendants », « le potager en bac sur balcon » —
ces domaines n'existent **que dans `tests/simulateur.py`**. C'est la réponse
figée que le simulateur rend aux tests, pour qu'aucun d'eux ne sorte sur le
réseau. En production, les domaines sont écrits par le modèle, à partir d'une
consigne qui ne nomme aucun sujet : « propose des domaines où un particulier
peut vendre un produit digital fait seul », en évitant ce qui exige une
certification, un stock ou une équipe.

## Mais ils étaient bel et bien figés, et pour une autre raison

Mesure du 16/09/2026, avec un modèle qui rend des domaines **différents à
chaque appel** :

```
tour 1 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
tour 2 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
tour 3 : ['domaine 1-1', 'domaine 1-2', 'domaine 1-3']
appels reellement passes au modele : 1 sur 3
```

Ce n'était donc pas le modèle qui se répétait : **c'était le cache**. La clé
du cache est un hachage de l'invite, et l'invite du démarrage à froid ne
variait jamais — ni sujet, ni historique, rien que le nombre demandé. Le
premier écran de tout le monde rendait la même liste jusqu'à la fin des temps.

`idees.explorer` avait reçu cette correction en septembre, et son commentaire
la raconte. Le démarrage à froid ne l'avait jamais eue.

La correction est la même, parce qu'il ne doit y en avoir qu'une : on injecte
dans l'invite ce que l'atelier contient déjà — produit ou seulement mis en
file. D'une pierre deux coups, et c'est ce qui rend le mécanisme honnête
plutôt que décoratif :

1. le modèle cesse de reproposer ce qui existe ;
2. **l'invite change dès que l'atelier change**, donc la clé de cache aussi.

Après :

```
tour 1 : ['domaine 1-1', ...]   tour 2 : ['domaine 2-1', ...]
tour 3 : ['domaine 3-1', ...]   appels au modele : 3 sur 3
```

Et le cas réel — installation neuve, deux appuis de suite sur « Trouver des
niches » sans rien produire entre les deux — repart bien de deux graines
différentes : le premier appui met une idée en file, ce qui suffit à faire
changer l'invite du second.

## Le huit

`DOMAINES_A_MESURER = 8`, dans `usine/production.py`. C'est un coût, pas une
opinion : chaque domaine est sondé sur quatre sources publiques, donc huit
domaines font trente-deux appels réseau avant qu'une seule ligne ne soit
écrite. Sur un téléphone en 4G, c'est ce qu'on attend devant l'écran.

Ce n'est pas une liste de huit sujets : c'est le nombre de propositions
**neuves** demandées à chaque tour, et elles diffèrent maintenant à chaque
fois. Le chiffre se change en une ligne si l'attente vaut le coup.

## Ce qui garde la correction

`tests/test_niches_variees.py`, quatre tests, aucun sur le réseau. Campagne de
mutation : quatre mutations, toutes vues — dont une qui neutralise la clé de
cache elle-même.

Trois de ces tests ont d'abord échoué, et pour la bonne raison : ils
partageaient le cache de réponses d'un test à l'autre. Le piège que ce dépôt
documente, retombé dans le test qui le documente. Chaque test repart d'un
atelier et d'un cache vides.
