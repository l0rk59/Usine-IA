# Quatorze illustrations produites, zéro illustration livrée

## Le défaut

La chaîne `conte` fabrique un album jeunesse : quatorze doubles-pages, une
illustration par page, générées par le modèle d'images et **écrites sur le
disque**. Le résumé du produit l'annonçait correctement :

```
Etape 2/3 — illustrations...
  6 image(s) sur 6
```

Aucune n'arrivait dans le livre. Le markdown produit était
`![](images/page-01.jpg)` — un markdown parfaitement correct — mais le modèle
de document du dépôt (`usine/render/document.py`) ne connaissait pas cette
forme. Elle tombait dans le cas « paragraphe » et ressortait **imprimée telle
quelle**, point d'exclamation, crochets et parenthèses compris, dans les
quatre formats à la fois :

| format | ce que l'acheteur voyait |
|---|---|
| PDF | `! (images/page-01.jpg)` en corps de texte |
| HTML | `![](images/page-01.jpg)` en clair dans la page |
| EPUB | la même chaîne, dans un `<p>` |
| TXT | la même chaîne |
| MD | l'image, correctement — le seul format juste |

## Pourquoi rien n'échouait

Chaque contrôle du dépôt regardait ailleurs, et chacun avait raison de son
point de vue :

- le markdown livré était **valide**, et c'est lui que lisent les tests de la
  chaîne ;
- l'EPUB était **conforme** — le contrôle EPUB 3 vérifie la structure du
  conteneur, pas qu'une illustration attendue s'y trouve ;
- le PDF **s'ouvrait** ;
- le contrôle qualité ne mesure que du texte ;
- le test de fumée comptait les fichiers produits, et ils étaient tous là.

C'est la forme la plus coûteuse de défaut de ce dépôt : celle où tous les
signaux disent « valide ». Il ne s'est vu qu'en **ouvrant le PDF** — ce que
personne n'avait fait pour cette chaîne.

## La correction

**Un type de bloc « image » dans le modèle de document.** Une image seule sur
sa ligne devient un bloc typé, et chaque rendu sait quoi en faire : `<img>` en
HTML et dans l'EPUB, `[Illustration : …]` en texte brut. Le détecteur lit le
point d'exclamation, pour qu'un lien ordinaire `[voir](carte.html)` ne
devienne jamais une image.

**Une méthode `image()` dans le moteur PDF.** Deux formats entrent dans un PDF
sans décodeur : le JPEG tel quel (`DCTDecode`) et des pixels bruts
(`FlateDecode`). Une image rapportée du réseau n'est ni l'un ni l'autre dès
qu'elle arrive en PNG ou en WebP, et écrire un décodeur PNG à la main
coûterait ici plus que ce qu'il rapporte. La méthode rend donc **faux** au
lieu de lever : l'appelant écrit sa note d'illustration à la place, et le
livre sort. Un album avec une note « à dessiner » se vend ; un album qui lève
une exception à l'export n'existe pas.

**Des ressources dans l'EPUB.** Un EPUB est une archive fermée : une image
citée par un chapitre mais absente du conteneur ne s'affiche pas chez le
lecteur, et le distributeur refuse le fichier. `construire_epub` prend
désormais les fichiers à embarquer, les écrit dans `OEBPS/` et les déclare au
manifeste avec le type mime déduit de l'extension.

## Le second défaut, sur la même page

Le conte appliquait à un album **la mise en page d'un guide** : le titre du
bloc en vingt-quatre points avec son filet bleu, puis du texte de onze points
justifié. Sur la page, cela donnait « Page 1 » en corps de chapitre au-dessus
d'une seule ligne — *« Le petit ours dort. »* — et le reste de la page blanc.

Et la note d'illustration sortait en texte ordinaire, donc indistinguable du
récit : l'adulte qui lit l'album à voix haute enchaînait « Illustration : un
ourson roulé en boule » sur le même ton que l'histoire.

La chaîne compose maintenant ses pages elle-même :

- une page de PDF par double-page, sans titre de chapitre ;
- pas de sommaire — quatorze lignes « Page 1 »… « Page 14 » ne renseignent
  personne, et une page « Sommaire » vide sortait tant que personne ne
  regardait ;
- l'illustration en haut, jusqu'à 52 % de la hauteur ;
- le récit en **dix-neuf points**, centré dans le blanc que l'illustration
  laisse : un album se lit à voix haute, l'enfant regardant la page à côté de
  l'adulte ; onze points, c'est un guide ;
- la note d'illustration dans un encadré, qui la désigne comme une consigne à
  l'illustrateur — et en citation dans les autres formats, où elle se
  distingue aussi.

## Ce qui garde la correction

`tests/test_illustrations.py`, dix-neuf tests en quatre groupes : le modèle de
document, le moteur PDF, le conteneur EPUB, et **la chaîne complète de
`generer_visuel` jusqu'au fichier livré**. Ce dernier groupe est le seul qui
mesure ce qui manquait vraiment : le défaut d'origine ne tenait à aucun
maillon cassé — ils fonctionnaient tous — mais à ce que rien ne les reliait.

Campagne de mutation : quinze mutations, toutes vues.

## Ce que l'outil de mutation a appris ce jour-là

La première campagne a rendu **quinze `[vu]` sur quinze**, et deux d'entre eux
étaient faux. La suite était déjà rouge — un test cassé par un changement de
format de sortie — et sur une suite rouge chaque mutation « est détectée » par
le test qui échouait déjà.

C'est le pire verdict possible pour un outil dont le rôle est de ne pas se
laisser rassurer : il annonce que tout est gardé au moment précis où plus rien
ne l'est. `muter.py` lance désormais les modules de la campagne **sans muter**
avant de commencer, et refuse de continuer s'ils échouent.
