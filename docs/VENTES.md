# Ce qui rapporte

## Ce que l'usine ne savait pas d'elle-même

L'usine mesurait la qualité, la durée, les appels consommés, les défauts
restants. Elle ne savait **rien de ce qui rapporte**.

`usine bilan` pouvait donc répondre « quel ton donne vos meilleures notes » et
jamais « quelle niche a payé ». Les deux questions n'ont aucune raison d'avoir
la même réponse, et c'est la seconde qui décide de ce qu'on fabrique ensuite.

```bash
usine ventes --importer export.csv --sur gumroad
usine ventes --rattacher
usine ventes
```

## Lire un export sans supposer son format

Les places de marché changent leurs colonnes sans prévenir, et deux d'entre
elles n'exportent jamais pareil. Coder en dur le format de Gumroad de ce
mois-ci aurait cassé au premier changement, silencieusement.

L'importeur cherche donc chaque champ par ses **noms possibles**, puis
**affiche ce qu'il a reconnu** :

```
  Colonnes reconnues :
    date           Purchase Date
    reference      Product Name
    unites         Quantity
    brut           Price
    net            Net Amount
    devise         Currency
    remboursement  Refunded
    identifiant    Sale ID
```

Une correspondance devinée qu'on ne montre pas est une erreur qu'on ne verra
jamais. Si la date ou le montant manquent, l'import s'arrête et **liste les
colonnes du fichier** au lieu de deviner.

Ce que ça encaisse, mesuré :

| | |
|---|---|
| Séparateur | virgule **ou** point-virgule (tableur français) |
| Décimales | `1 234,56 €`, `$1,234.56`, `1234.56` |
| Dates | `2026-08-03`, `03/08/2026` |
| Remboursements | `Refunded=true`, `Statut=Remboursé` |

## Trois règles de prudence

Un chiffre d'affaires inventé est pire qu'un chiffre d'affaires absent.

**Pas de conversion.** Les devises ne sont jamais mélangées ni additionnées.
Convertir sans source de taux reviendrait à fabriquer le résultat.

**Pas d'estimation.** Le net est enregistré s'il figure dans l'export, laissé
vide sinon — et l'affichage dit « inconnu ». Déduire une commission
« habituelle » donnerait un revenu qui n'existe pas.

**Pas de doublon.** Chaque ligne porte une empreinte : l'identifiant de
commande quand la place en fournit un, sinon l'empreinte de la ligne entière.
Réimporter le même export n'ajoute rien.

> Le compromis de l'empreinte, dit franchement : sans identifiant de commande,
> deux ventes strictement identiques le même jour comptent pour une. C'est le
> risque retenu contre le risque inverse — compter deux fois la même vente.

## Rattacher une vente à son produit

Le nom affiché sur la place de marché n'est pas le titre interne : il a été
raccourci, traduit, augmenté d'un « (PDF + EPUB) ».

`usine ventes --rattacher` compare les deux. Deux points ont demandé du soin :

**Les mentions de format ne sont pas du sujet.** « Le système du freelance
(PDF + EPUB) » et « Le système du freelance rentable » ne partageaient qu'un
mot porteur sur deux, parce que `pdf` et `epub` comptaient. Les segments entre
parenthèses partent en entier : une place de marché y met le format, la mention
« instant download », le nombre de pages — jamais le sujet.

**Le type de produit, lui, compte.** Comparer deux **niches** demande d'ignorer
le vocabulaire d'emballage — « guide », « cahier », « méthode ». Comparer deux
**noms de produits** demande l'inverse : entre « Cahier du freelance » et « Le
système du freelance rentable », c'est précisément `cahier` et `système` qui
font la différence. Les écarter rattachait la vente du cahier à l'ebook voisin.

Les deux comparaisons existent donc, avec deux listes de mots écartés
différentes.

## Le prix cesse d'être inventé

C'était la faiblesse la plus coûteuse. Le `prix_eur` d'une idée de produit
sortait du modèle, sans rien derrière : les quatre sources de marché mesurent
la demande et la concurrence, **aucune ne mesure un prix**. Le seul nombre qui
détermine le revenu était le moins fondé de tout le système.

Dès qu'un type de produit compte **trois ventes**, l'étude de niche retient le
prix médian réellement encaissé, et l'écrit :

```
- **Type :** impression | **Prix cible :** 14 EUR *(4 ventes constatées, fourchette 12 à 16)*
- **Type :** ebook | **Prix cible :** 19 EUR *(estimé, aucune vente pour l'étayer)*
```

Trois ventes, c'est peu. Mais trois observations valent mieux qu'aucune, et la
provenance reste affichée pour que la différence se voie.

## Ce que ça change pour la suite

`usine idees` reçoit désormais un résumé de ce qui s'est réellement vendu chez
vous. Ce que **votre** audience a acheté pèse plus qu'un avis général sur le
marché.

Et `usine bilan` sépare enfin les deux questions :

```
== Ce que les ventes disent
  EUR  6 unites, 95.50 encaisses

  Chiffre d'affaires par type
    ebook           58.00 EUR  sur 1 produit(s)
    impression      37.50 EUR  sur 1 produit(s)

  Prix median reellement encaisse : 29.00 EUR (3 ventes)
```

Tant qu'aucune vente n'est saisie, `usine bilan` le dit au lieu de laisser
croire que ses conseils portent sur le chiffre d'affaires :

> *Les conseils ci-dessous portent sur la QUALITÉ mesurée, pas sur ce qui se
> vend — l'usine n'en sait rien.*

## Saisie manuelle

Tout ne passe pas par un export.

```bash
usine ventes --ajouter <produit_id> --brut 29 --unites 2 --sur payhip
usine ventes --lier "Nom sur la boutique" <produit_id>
usine ventes --depuis 2026-01-01
```
