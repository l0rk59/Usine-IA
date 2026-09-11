# La couverture

## Le défaut qui rendait tous les produits invendables

Jusqu'ici, chaque produit sortait de l'usine avec une couverture générée par
Pollinations. Le service est gratuit et ne demande aucune clé — mais au palier
anonyme, **il appose un filigrane `pollinations.ai` en bas de chaque image**.
Le paramètre `nologo` que sa documentation mentionne n'a aucun effet sans
jeton : vérifié, image à l'appui, deux fois à six mois d'écart.

Une couverture filigranée ne se vend pas. La place de marché la refuse, ou
l'acheteur la prend pour une contrefaçon.

Le plus gênant n'est pas l'erreur, c'est qu'elle était **écrite dans le fichier
qui la commettait** : `usine/core/images.py` documentait en tête, en
majuscules, que ces images ne devaient pas servir de couverture — puis
appelait Pollinations par défaut, à chaque produit.

Depuis, la couverture est **composée localement**, et c'est le défaut.
L'illustration par IA reste accessible (`usine reglages --definir
couverture=ia`) mais exige un jeton, précisément parce que sans jeton elle ne
sert à rien.

## Trois modules, aucune dépendance

```
typo.py        une fonte capitale, dessinée en polygones
raster.py      polygones → pixels → PNG (et flux PDF)
couverture.py  la mise en page, émise en PNG et en SVG
```

### Pourquoi dessiner une fonte

Pour écrire un titre sur une image, il faut les **contours** des lettres. Les
métriques AFM que le moteur PDF utilise ne donnent que des largeurs : le PDF
délègue le dessin au lecteur. Une image PNG n'a personne à qui déléguer.

Trois issues possibles : embarquer un fichier TrueType et écrire son analyseur
(un binaire dans un dépôt qui n'en a aucun), dépendre d'une fonte du système
(Termux n'en garantit aucune), ou dessiner les lettres. C'est la troisième —
cohérente avec un moteur PDF et un moteur WebGL déjà écrits à la main.

La fonte est **capitale uniquement**, et c'est un choix : un titre de
couverture se compose en capitales, un sous-titre en petites capitales
espacées. Dessiner soixante bas-de-casse pour ne jamais les utiliser aurait
doublé le travail sans rien ajouter à la page. Accents français compris —
composés, pas redessinés.

Les glyphes sont construits à partir de quatre primitives : barre, polygone,
oblique et anneau. Le remplissage suit la règle **nonzero**, ce qui permet de
composer une lettre à partir de traits qui se chevauchent — la jonction du K,
le sommet du A — sans calculer d'union géométrique.

### Pourquoi pas de JPEG

Le moteur PDF sait **incorporer** du JPEG. Il ne sait pas en **fabriquer**, et
écrire un encodeur JPEG — DCT, quantification, Huffman — pour afficher une
couverture aurait été disproportionné.

Le format PNG et le format PDF partagent pourtant un terrain : des pixels
bruts compressés par zlib. PNG les range en lignes préfixées d'un octet de
filtre ; PDF les accepte tels quels sous `/Filter /FlateDecode`. **Le même
tampon sert aux deux**, et zlib est dans la bibliothèque standard.

Conséquence visible : la couverture occupe la **page entière** du PDF, titre et
typographie compris, au lieu d'être une vignette carrée avec le titre réécrit
dessous.

## Le contraste est calculé, pas décrété

C'est le cœur du sujet. La version précédente choisissait la couleur du
sous-titre dans la palette. Sur le fond prune, cela donnait **du rose sur du
rose** : 1,4:1. Le texte était là, il n'était pas lisible, et rien ne le
signalait.

Trois règles ont remplacé ce choix :

1. **L'encre est celle qui contraste le plus** avec le fond — blanc ou noir,
   décidé par la luminance relative, pas par la palette.
2. **Une teinte d'accent n'est gardée que si elle tient.** Sinon l'opacité
   monte, puis on retombe sur l'encre du fond.
3. **Le fond, c'est ce qu'il y a vraiment derrière** : le dégradé, plus chaque
   décor déjà dessiné qui traverse la bande de texte. Un cercle d'accent à
   55 % change ce que le titre recouvre ; raisonner sur le seul dégradé
   revenait à ignorer ce qu'on venait soi-même de dessiner.

La troisième règle a été ajoutée parce que le test la réclamait : après avoir
corrigé les deux premières, huit combinaisons échouaient encore, toutes sur le
modèle `arcs`. Les anneaux passaient derrière la signature. L'opacité des
ornements a été ramenée à 30 % — **l'ornement cède le pas au texte**, pas
l'inverse.

### Le test qui l'aurait attrapé

`tests/test_couverture.py` rend chaque couverture **deux fois**, avec et sans
son texte, et compare les deux images pixel par pixel :

- le **fond** vient du rendu sans texte — c'est lui qu'il faut découvrir,
  parce qu'un bloc d'accent ne se devine pas depuis la palette ;
- l'**encre** est prise telle que la mise en page l'a décidée, pas telle que
  l'anticrénelage la restitue : mesurer les pixels de bord reviendrait à
  sanctionner l'adoucissement des contours.

Quarante combinaisons (8 palettes × 5 mises en page) doivent toutes atteindre
**4,5:1**, le seuil WCAG AA. Le code vise 5,2:1 en interne, pour absorber le
jeu d'un décor intermédiaire.

## Ce qui est livré

```
couverture.png     1200 × 1800 — Gumroad, Etsy, KDP (aucun n'accepte le SVG)
couverture.svg     même géométrie, vectorielle, pour retoucher
<produit>.pdf      la couverture occupe la première page, pleine page
```

## Les cinq mises en page

| Modèle | Composition |
|---|---|
| `bandeau` | titre bas-gauche, filet d'accent, grand cercle échancré |
| `centre` | titre centré entre deux filets, anneau en fond |
| `diagonale` | triangle d'accent plein depuis le coin haut-droit |
| `arcs` | anneaux concentriques en bas-droite, titre en haut |
| `bloc` | aplat d'accent sur le tiers supérieur, titre dessous |

Huit palettes, dont deux claires. Le style se déduit d'une empreinte du titre :
**deux appels avec le même titre donnent la même couverture**, ce qui permet de
régénérer un produit sans que sa fiche de vente change.

## Le corps du titre est calculé

Un titre de quatre lettres doit occuper la couverture ; un titre de douze mots
doit rester lisible. Le corps part d'un plafond haut et descend jusqu'à ce que
**l'ensemble** tienne — titre et sous-titre ensemble, en largeur comme en
hauteur.

Deux défauts trouvés à l'écriture de ce mécanisme :

- N'ajuster que le titre laissait le sous-titre déborder **sous le bord de la
  page**. Le texte existait, il n'était plus sur l'image.
- Le plancher était exprimé en pixels (18 px). Rendue en petit format, la même
  couverture débordait ; rendue en grand, non. Le plancher est maintenant
  proportionnel à la hauteur.

Et un garde-fou : si même au plancher l'ensemble ne rentre pas, **le sous-titre
saute**. Un sous-titre imprimé sous le bord de la page n'est pas un
sous-titre — c'est un défaut invisible au moment où on le crée.

## L'A/B testing teste enfin quelque chose de vendable

`usine ab creer --sur couverture` comparait jusqu'ici des images filigranées :
on choisissait entre quatre propositions dont **aucune ne pouvait être
vendue**. Les huit directions visuelles sont désormais des combinaisons
palette × mise en page de l'atelier. Ce qui gagne le test est ce qui part chez
l'acheteur.

## Coût

| | |
|---|---|
| Composition + rendu 1200 × 1800 | ~0,35 s |
| Poids du PNG | ~70 à 110 Ko |
| Couverture pleine page dans le PDF | ~30 Ko |
| Dépendances | aucune |
| Appels réseau | aucun |
