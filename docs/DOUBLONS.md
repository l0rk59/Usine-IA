# Ce que l'usine a déjà écrit

## Le défaut n'apparaît qu'au volume

Une usine qui fabrique quatre produits par jour sur des niches voisines — « la
prospection pour freelances », « trouver des clients en freelance »,
« démarcher sans se vendre » — produit **trois fois le même livre avec des mots
différents**.

Ni le modèle ni le contrôle qualité ne peuvent le voir : chacun ne regarde
qu'un produit à la fois, et chacun le trouve bon. C'est un défaut qu'aucune
relecture, humaine ou non, ne repère à l'échelle d'un produit.

Les conséquences sont commerciales, pas esthétiques :

- une place de marché retire les doublons, et sanctionne le compte qui en
  dépose ;
- un acheteur qui a pris deux de vos produits et découvre le même livre demande
  **deux remboursements**, puis ne revient pas.

## Ce qui existait avant

Une comparaison de **chaînes de caractères**. La file refusait le couple
(sujet, type) déjà en attente :

```python
# usine/core/file.py
"""Le doublon est ecarte sur le couple (sujet, type)."""
```

« La prospection pour freelances » et « Prospection freelance » y passaient
sans encombre. Rien, nulle part, ne comparait le **contenu** produit.

## Deux mesures, parce que deux choses se répètent

### Le texte — MinHash sur des quintuplets de mots

Chaque produit est réduit à l'ensemble de ses groupes de 5 mots consécutifs,
puis à une signature de 128 empreintes. Comparer deux signatures donne une
estimation du coefficient de Jaccard des deux ensembles.

Pourquoi cette forme plutôt qu'une comparaison directe :

| | |
|---|---|
| **Taille fixe** | 128 entiers, qu'il s'agisse d'un pack de 8 pages ou d'un livre de 200 |
| **Insensible à la longueur** | un livre court inclus dans un long reste détecté |
| **Robuste au remaniement** | changer quelques mots ne casse pas la correspondance |
| **Coût constant** | comparer à 400 produits ne coûte pas 400 lectures de fichiers |

Le groupe de 5 mots est un compromis mesuré : à 2 ou 3, deux textes du même
domaine se ressemblent tous ; à 8 ou plus, la moindre reformulation casse la
correspondance.

### Le plan — la charpente sous d'autres mots

**C'est le cas fréquent, et celui qu'une comparaison de texte seule laisse
passer.** Deux livres peuvent n'avoir pas une phrase en commun et rester le
même livre :

```
Chapitre 2 — Trouver vos premiers prospects
Étape 2 : trouver ses premiers prospects
```

Chaque titre de section est réduit à ses mots porteurs, triés, sans accent,
sans pluriel, sans numéro. Les deux lignes ci-dessus donnent la même entrée.

La comparaison des plans est **volontairement asymétrique par la taille** : un
livre de six chapitres entièrement contenu dans un livre de douze est un
doublon, même si l'inverse ne se dit pas. Le Jaccard classique le noterait 0,5
et laisserait passer.

## Quand la vérification a lieu

```
usine file --ajouter "..."   ──►  comparaison des INTITULÉS    (0 appel IA)
         │
    fabrication
         │
   terminer()               ──►  comparaison du CONTENU        (0 appel IA)
                                 empreinte enregistrée
```

**Le produit n'est pas bloqué**, et c'est un compromis assumé : comparer avant
supposerait de deviner ce que le modèle va écrire. Le quota est dépensé — ce
qu'on évite, c'est la mise en vente.

Le garde-fou d'avant fabrication ne voit que l'intitulé, donc il rate les
doublons de contenu. Mais il coûte zéro appel, là où la vérification d'après
fabrication coûte le produit entier.

## En pratique

```bash
usine doublons              # toutes les paires qui se recouvrent
usine doublons -t ebook     # un seul type
```

Sort en **code 1** quand il trouve quelque chose — de quoi le mettre dans une
tâche planifiée.

Un ebook et un cahier imprimable sur le même sujet **ne sont pas des
doublons** : la comparaison ne se fait qu'entre produits de même type. Ils sont
complémentaires, et se vendent d'ailleurs ensemble.

## Les seuils

| Mesure | Seuil | Ce que cela veut dire |
|---|---|---|
| Texte | 0,30 | un tiers des groupes de mots en commun |
| Plan | 0,55 | plus d'une section sur deux se correspond |
| Intitulé | 0,75 | trois mots porteurs sur quatre en commun |

Ils sont délibérément bas. Un faux positif coûte une relecture ; un faux
négatif coûte un compte fermé.

## Ce que les tests vérifient

- que l'**estimation MinHash suit le calcul exact** de Jaccard, sur quatre
  paires de textes, à 0,12 près ;
- qu'un texte légèrement remanié reste détecté (> 0,55) et qu'un texte
  étranger ne l'est pas (< 0,05) ;
- que le **même livre sous d'autres mots** est attrapé — le test vérifie
  d'abord que le texte seul échoue, puis que le plan rattrape ;
- que les fonctions de hachage **ne changent pas d'une exécution à l'autre**.
  Un tirage aléatoire au démarrage rendrait incomparables les produits d'avant
  et d'après un redémarrage : le module serait silencieusement inutile.

## Note sur la base de données

Ce travail a ajouté une table, ce qui a révélé une deuxième lacune :
`CREATE TABLE IF NOT EXISTS` crée une base neuve, mais **reste sans effet sur
une base existante**. Une colonne ajoutée plus tard n'aurait jamais été créée
chez qui a déjà produit, et l'erreur SQL serait tombée des semaines après, sur
un téléphone, avec tout l'historique dedans.

Le schéma porte désormais un `PRAGMA user_version` et une échelle de
migrations. Le cas « base d'hier, sans numéro de version » est testé sur une
vraie base ancienne, données comprises.

## « Aucun recouvrement » ou « rien n'a été comparé » ?

Les deux se lisaient pareil sur le tableau de bord, et l'un est une bonne
nouvelle quand l'autre est une lacune. Les empreintes sont posées **à la
fabrication** : un catalogue constitué avant leur introduction n'en a aucune,
et la carte affichait paisiblement « aucun recouvrement notable » après avoir
comparé zéro produit.

La carte compte désormais les produits sans empreinte, le dit, et propose le
bouton qui répare — `usine doublons --reconstruire` a maintenant son
équivalent dans le navigateur. Les produits dont le dossier a été déplacé
sont nommés, pas comptés comme vides.

