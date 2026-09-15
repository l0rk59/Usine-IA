# « 8 pistes explorées, 0 mise(s) en file », indéfiniment

*Mesuré le 15/09/2026, sur le téléphone, puis reproduit en local.*

Le symptôme, rapporté tel quel : *« ça renvoie toujours qu'aucune niche n'a
été retenue, et ça a l'air d'être toujours les mêmes, et le même nombre, 8 ».*

Les trois observations sont justes, et la troisième — « toujours 8 » — est la
seule qui soit normale : c'est la valeur par défaut de `--nombre`
(`cli.py`, commande `niches --explorer`). Les deux autres sont un seul défaut.

## La mesure

Trois prospections de suite, avec un modèle simulé qui propose des idées
**différentes** à chaque appel :

```
TOUR 1 -> pistes=8 ajoutees=8
TOUR 2 -> pistes=8 ajoutees=0
TOUR 3 -> pistes=8 ajoutees=0

Appels reellement faits au modele : 1   (pour trois prospections)
```

**Un seul appel pour trois prospections.** Le modèle n'a jamais été
reconsulté : les tours 2 et 3 ont relu la réponse du tour 1.

## La cause

Le cache des réponses est indexé sur l'invite. L'invite ne dépendait que de la
graine. La graine ne changeait pas. Donc :

> même graine → même invite → même entrée de cache → mêmes 8 idées, pour
> toujours.

Et comme ces 8 idées avaient été mises en file au premier tour, chaque tour
suivant les rejetait comme doublons. **Le second lancement ne pouvait
mathématiquement rien ajouter**, et tous les suivants non plus.

C'est exactement le piège que `CLAUDE.md` énonce pour les tests — *« deux cas
qui partagent une invite partagent une entrée de cache, et le second n'exerce
rien »* — appliqué ici à la production elle-même.

## Une fausse piste, écartée par la mesure

Premier diagnostic, faux : j'ai cru que le filtre de dédoublonnage
(`empreinte.sujets_proches`) accusait à tort, parce que ma sonde affichait
*« Idee 1 du tour 1 » recouvre « Le systeme du freelance rentable »*.

C'était un défaut de ma sonde, pas du dépôt : mes titres de test
commençaient tous par « Idée », comme une donnée de démonstration présente
dans l'atelier — et ma sonde tournait sur l'atelier réel, parce que la
variable d'environnement que je croyais l'isoler n'existe pas. Refaite avec
`tests.atelier.isoler` et des titres réalistes, la mesure donne
`TOUR 1 -> ajoutees=8` : le dédoublonnage fonctionne.

## La correction

**1. L'invite porte ce qui existe déjà.** Les intitulés déjà fabriqués et
ceux déjà en file entrent dans la demande, avec la consigne de ne rien
proposer qui les recouvre.

Ce n'est pas un contournement du cache : c'est la bonne question. On
demandait des idées neuves à un modèle à qui l'on n'avait jamais dit ce qui
existait, puis on jetait ses propositions après coup. Il ne pouvait pas faire
mieux. Et comme la question change dès que l'atelier change, la clé de cache
change avec elle.

**2. L'exploration refuse le cache.** C'est la seule opération de l'usine
dont le *but* est de rendre autre chose que la fois d'avant. Le cas où
l'atelier ne change pas — toutes les pistes recouvrent un produit fabriqué,
donc aucune n'est retenue — laisse l'invite identique au mot près ; sans ce
refus, l'exploration y resterait bloquée.

Une campagne de mutation a montré que les deux moitiés se recouvraient : en
retirant le refus du cache, **aucun test n'échouait**, parce que tous les cas
faisaient changer l'atelier. Le cas à atelier constant a donc été ajouté, et
il vérifie d'abord que l'invite est bien identique — sans quoi il ne
mesurerait pas ce qu'il prétend mesurer.

**3. « Déjà en file » n'est pas « déjà fabriqué ».** Le rapport disait
*« toutes recouvrent un produit déjà fabriqué »* alors que l'atelier pouvait
être vide et les pistes simplement en attente. Deux refus différents, deux
gestes différents : l'un dit de chercher ailleurs, l'autre de produire ce qui
attend. Les confondre envoyait chercher un défaut de dédoublonnage là où il
n'y en avait pas — ce qui est précisément arrivé.

```
Aucune piste NEUVE : les 8 pistes sont deja en file d'attente.
      Lancez « usine produire » pour les fabriquer, ou explorez une autre graine.
```

## Après

```
TOUR 1 -> pistes=8 ajoutees=8
TOUR 2 -> pistes=8 ajoutees=8

Appels au modele : 2   (pour deux prospections)
```
