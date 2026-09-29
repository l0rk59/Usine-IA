# Ce que l'usine sait de ce qu'elle vient de fabriquer

## La mesure qui a ouvert le sujet

Un exemplaire de chaque type, le 14/09/2026 :

```
chaine          note   rapport
ebook           4.33       oui
formation          —       non
prompts            —       non
outils             —       non
social             —       non
modeles            —       non
impression         —       non
logiciel           —       non
nouvelle        4.21       oui
```

**Sept types sur neuf sortaient sans rien** — pas de note, pas de rapport, pas
même un nombre de mots.

Ce n'est pas une coquetterie de tableau de bord. Après quatre vraies
fabrications (une formation, un pack de prompts, une boîte à outils, un pack
social), `usine bilan` affichait :

```
  4 production(s), 4 reussie(s), 0 echec(s)
  0 mots produits, 33 appels IA
```

Et en dessous, sous le titre **« Conseils tirés de vos données »** : « aucun
écart significatif ». Ce qui est vrai de n'importe quel ensemble vide.

Plus loin encore : `graine_de_depart()` classe les niches par chiffre
d'affaires **puis par note**. Sans note, ces sept types ne pouvaient jamais
servir de point de départ à la prospection — y compris à celle qui vient
d'être écrite pour qu'une installation neuve sache par où commencer.

## Une correction partagée, pas sept

`terminer()` — le point de sortie commun aux dix chaînes — relit désormais le
texte **livré** et en tire le volume. Il y avait déjà pour cela une fonction,
`_matiere()`, écrite avec le bon réflexe : *« on relit ce qui a été ÉCRIT
plutôt que de se faire passer le plan : c'est le fichier livré qui compte. »*

Une seule correction, à un seul endroit — et la onzième chaîne écrite dans six
mois en héritera sans rien faire.

## Mais tout ne se note pas

C'est là que la première version était fausse, et c'est la partie intéressante.

**Premier piège : le type.** Le contrôle déterministe mesure de la *prose* —
rythme des phrases, répétition de n-grammes, diversité lexicale, continuité
d'une section à l'autre. Appliqué ailleurs, il rend un chiffre sans
signification. Mesuré :

| | |
|---|---|
| 31 posts sociaux de deux lignes | **9,98/10** |
| un outil logiciel | **9,83/10** — noté en fait sur sa notice, pas sur son code |
| une liste de prompts | 6 signalements de « rythme », où le rythme n'existe pas |

Le catalogue porte donc un drapeau `prose`, à côté de `extrait` qui existait
déjà pour une raison jumelle (« *les deux premiers chapitres* » ne veut rien
dire pour un programme).

**Second piège : la longueur des sections.** Le même texte, coupé de plus en
plus fin :

```
mots/section :  60   80  100  120  140  200  300  400
note         : 10.0 10.0 8.69 8.56 7.56 7.19 6.93  6.5
```

**Sous cent mots, la note vaut 10 quoi que dise le texte.** Elle mesure le
découpage, pas l'écriture.

Une boîte à outils de vingt-cinq mots par fiche obtenait ainsi 9,91/10 — et ce
chiffre serait parti se comparer, dans `usine bilan`, à un ebook noté 4,33 sur
des chapitres de deux cents mots. *Un chiffre sans sens est pire que pas de
chiffre, parce qu'on le croit.*

Le seuil de cent mots n'est pas choisi : il est **lu dans le tableau ci-dessus**,
et un test le rejoue — sinon ce serait un chiffre sans source, ce que ce dépôt
refuse dans un produit comme dans son propre code.

## Un mauvais découpage ne rend pas une note imprécise, il la rend inventée

Première version : couper à n'importe quel en-tête. Or un module de formation
porte `## Objectif` et `## Notions` **à l'intérieur**. Le découpage donnait des
sections de trente-quatre mots pour un module qui en fait cent quarante — donc,
par la règle ci-dessus, 10/10 par construction.

On prend maintenant le niveau de titre le plus haut sous le titre du document :
l'unité que la chaîne a elle-même choisie.

## Ce que ça donne

```
chaine         note   mots  sect mots/sect  sans note, pourquoi
ebook          4.33   2012     9         —
formation       8.5   1393    28       148
prompts           —    705    15         —  pas de la prose
outils            —    280    11        69  sections trop courtes
social            —   1031    31         —  pas de la prose
modeles         8.0    424     7       371
impression        —      0     0         —  aucun texte suivi livré
logiciel          —    193     6         —  pas de la prose
nouvelle       4.21   1539    10         —
```

Chaque produit dit son volume. Chaque note absente dit **pourquoi** — une case
vide se lit comme un oubli, et quelqu'un finirait par la « réparer » en notant
quand même.

## Et le bilan dit sur quoi il repose

```
  4 production(s), 4 reussie(s), 0 echec(s)
  Note moyenne : 8.5 /10   (meilleure 8.5 — pire 8.5)
    sur 1 produit(s) sur 4 : les autres ne sont pas de la prose, ou leurs
    sections sont trop courtes pour etre mesurees
  3401 mots produits, 33 appels IA
```

Sans cette ligne, une moyenne affichée sous « 4 production(s) » se lit comme la
moyenne des quatre. Le chiffre était juste et racontait quelque chose de faux.

Les douze mutations de la campagne sont vues.
