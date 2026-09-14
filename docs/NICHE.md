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
