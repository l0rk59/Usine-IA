# Un type, un bouton

## Ce qui était demandé

> « Je veux juste que tout fonctionne, une usine où je n'ai besoin de rien
> faire à part appuyer sur générer — en gardant quand même le choix du type
> de produit. »

## Ce que la mesure a dit

Le moteur y répondait déjà. Mesure du 15/09/2026, par le **chemin réel du
tableau de bord** (`serveur._lancer`), un type choisi et des options **vides**,
pour les dix-huit types : **dix-huit produits livrés, zéro échec**. Vérifié sur
le disque, pas sur le code de retour — entre 8 et 11 fichiers par produit, 149
à 365 Ko, statut `pret`.

Deux choses ne suivaient pas.

## Le conte mettait 83 secondes quand les autres en mettaient 6

Dont **77,5 en images**. Quinze appels — une couverture, quatorze
illustrations — et aucun fournisseur d'images joignable. Chaque appel rejouait
trois tentatives avec attente : les quatorze derniers réapprenaient, à cinq
secondes pièce, ce que le premier avait établi.

C'est un défaut **introduit par le travail sur les réessais** : avant lui, une
image ratée coûtait zéro seconde. Les réessais restent justes pour un
hoquet — c'est de les payer quinze fois qui ne l'est pas.

`images._demander_une_image` retient donc le constat. Après un `insister`
épuisé — trois tentatives sur cinq secondes, c'est déjà la mesure — les appels
suivants tentent leur chance **une fois**. Aucun délai, aucun seuil à
inventer : le premier succès efface le constat et l'insistance reprend, donc un
service qui revient au milieu d'un album est repris au vol.

**83 s → 12,8 s**, dont 6,1 en images.

Le test qui garde cela a d'abord fait tomber un test voisin, et il avait
raison : le constat traverse les appels — c'est tout son intérêt — donc il
traverse aussi les tests, et le premier qui échouait rendait le suivant
complaisant. Chaque mesure le remet à zéro.

## Le formulaire demandait sept choses avant le bouton

Type, sujet, audience, ton, volume, qualité, auteur — plus une carte entière
de réglages propres au type. Tous facultatifs depuis toujours : un champ vide
veut déjà dire « décide pour moi ». Mais **dépliés, ça ne se voit pas**. Sept
cases vides se lisent comme sept questions auxquelles il faut répondre, et on
cherche quoi écrire dans « Audience » au lieu d'appuyer.

L'onglet « Fabriquer » tient maintenant en trois éléments :

1. le type de produit — le choix qui reste ;
2. une phrase qui dit que le formulaire est fini ;
3. un repli « Choisir moi-même », fermé, qui contient tout le reste.

Rien n'est retiré. Le choix est à un clic, et il est complet.

Trois chemins renvoient le curseur dans le champ « sujet » — mettre le sujet
en file, reprendre un titre trouvé par la veille, signaler un sujet manquant.
Ils ouvrent le repli d'abord : sans cela, `focus()` viserait un champ dans un
bloc fermé et rien ne bougerait à l'écran — exactement le défaut déjà corrigé
quand ce champ vivait dans un onglet caché.

## La vérification qui compte

Pas une fonction appelée depuis un test : **le vrai navigateur, le vrai
serveur, le vrai bouton**, dans une fenêtre de téléphone (412 × 915).

Un geste — choisir « memo » dans la liste — puis un clic. Résultat :

```
L'usine choisit la niche...
3 domaines proposes — mesure sur les sources publiques...
Aucune source de marche n'a repondu : ces domaines sont PROPOSES, pas mesures.
Premiere niche, choisie par l'usine : « la facturation des independants ».
L'usine decide 1 reglage(s) : nombre...
  nombre : 7
Etape 1/2 — structure du memo...
Etape 2/2 — export...
```

Et sur le disque : `Memo — la facturation des independants`, statut `pret`,
huit fichiers — couverture PNG et SVG, PDF, page HTML, CSV, markdown, JSON.

Le journal reste honnête là où il pourrait se taire : aucune source de marché
n'ayant répondu, il dit que la niche est **proposée, pas mesurée**. Une usine
qui se tait sur ce qu'elle n'a pas pu vérifier est une usine qu'on cesse de
croire.
