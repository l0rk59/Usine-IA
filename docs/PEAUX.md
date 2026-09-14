# Les peaux du tableau de bord

## Deux nuances ne font pas deux interfaces

« Nuit » et « jour » étaient la même page : même police, même densité, même
taille de texte, mêmes animations. Seule la teinte changeait. Une peau qui ne
change que la teinte ne sert qu'à elle-même.

Or trois situations ne demandent pas une autre couleur, elles demandent une
autre interface :

- un écran de téléphone **en plein soleil** — le neon sur noir y est illisible,
  quelle que soit la nuance ;
- un **vieil appareil** que le canvas animé fait ramer — lui donner du gris
  clair ne change rien, il faut arrêter ce qui tourne ;
- quelqu'un qui **ne distingue pas** un cyan sur du noir — il lui faut des
  bords francs et du texte plus grand, pas une autre palette.

Quatre peaux s'ajoutent donc aux deux d'origine, et chacune change au moins la
police, la densité ou les animations :

| Peau | Police | Densité | Animée | Pour quoi |
|---|---|---|---|---|
| `nuit` | sans | 1 | oui | l'origine : neon sur noir, grille en fuite |
| `jour` | sans | 1 | oui | le même, en clair |
| `papier` | serif | 1 | **non** | atelier d'édition, pour travailler longtemps |
| `console` | mono | **0,72** | **non** | terminal dense — la même peau que Termux |
| `ambre` | mono | 1 | oui | écran monochrome ambre, comme un terminal de 1981 |
| `contraste` | sans | 1,15 | **non** | noir et blanc francs, texte à **18 px** |

`contraste` n'est pas une variante esthétique : c'est la peau qui rend le
tableau de bord utilisable à qui voit mal. Elle grossit le texte, épaissit
chaque bordure à 2 px et supprime les demi-teintes.

## Une seule liste, lue trois fois

Les peaux sont déclarées dans `usine/core/reglages.py`, dans `THEMES`, et
**nulle part ailleurs**. La CLI, le menu Termux et la page les lisent toutes
les trois.

C'est la règle du dépôt qui revient à chaque audit : une liste recopiée dans le
CSS et une autre dans le menu finiraient par ne plus proposer les mêmes, et
c'est toujours la copie qui vieillit. Le script du navigateur ne connaît donc
aucune peau : il reçoit la liste par `/api/etat` et remplit la liste déroulante
avec ce qu'on lui donne.

Quatre tests gardent ce point dans les deux sens : chaque peau déclarée a son
bloc CSS, **et** aucun bloc CSS ne propose une peau que personne ne peut
choisir — du style mort que le prochain lecteur prendra pour une régression.

Le réglage `theme` est une **liste fermée**. Un nom tapé à la main qui n'existe
pas laissait la page sans aucune couleur : le navigateur ne trouvait aucune
règle et affichait du noir sur du noir. Une peau inconnue retombe désormais sur
`nuit`, et le champ est devenu une liste déroulante.

## Ce qu'une peau calme arrête vraiment

Le CSS seul ne peut pas arrêter un canvas qui tourne. Le script pose donc un
drapeau `data-anime` sur `<html>`, et quatre choses s'éteignent ensemble : le
fond animé, la trame de balayage, les animations CSS et la scène 3D.

Deux règles ont le dernier mot sur la peau, dans cet ordre :

1. **Le système.** Quelqu'un qui a demandé moins d'animations à son téléphone
   (`prefers-reduced-motion`) n'en reçoit pas parce qu'une peau en prévoit.
2. **Le réglage `effets_3d`.** Une peau animée ne rallume pas la 3D chez
   quelqu'un qui l'a coupée parce que son appareil rame.

## Le défaut que le navigateur a montré

Une première version ne faisait que **cacher**. Elle marchait dans un sens :
`nuit` → `papier` éteignait bien tout. Mais revenir de `papier` à `nuit`
laissait la scène 3D éteinte jusqu'au rechargement de la page — on croyait la
peau cassée, alors que c'était le retour qui l'était.

Aucun test de texte ne pouvait le voir : le CSS était juste, le JavaScript
était juste ligne à ligne. Il a fallu ouvrir un vrai navigateur et faire
l'aller-retour :

```
  nuit       anime=oui scene_cachee=False fond_cache=False
  papier     anime=non scene_cachee=True  fond_cache=True
  nuit       anime=oui scene_cachee=False fond_cache=False
  console    anime=non scene_cachee=True  fond_cache=True
  ambre      anime=oui scene_cachee=False fond_cache=False
  contraste  anime=non scene_cachee=True  fond_cache=True
  jour       anime=oui scene_cachee=False fond_cache=False
  erreurs JS : aucune
```

La correction tient en une ligne : au lieu de cacher quand la peau est calme,
on **recalcule** l'état visible à chaque changement, en tenant compte des trois
sources de vérité à la fois.

```js
$('scene').hidden = !(anime && scene.actif && effets3dActifs());
```

## Deux tests qui ne gardaient rien

La campagne de mutation a trouvé deux tests décoratifs, tous les deux pour la
même raison — celle que le dépôt retrouve à chaque audit : *un garde-fou
satisfait par une homonymie ne garde rien.*

**Le premier** vérifiait que les peaux calmes coupent les animations en
cherchant `[data-anime="non"]` quelque part dans la feuille de style. Retirer
la règle qui éteint le canvas laissait le test vert, parce qu'une autre règle
— celle qui coupe les transitions — contenait le même mot. Il lit désormais
chaque sélecteur **séparément**, et vérifie chaque cible une par une : les
sélecteurs regroupés par virgule partagent une accolade, et lire le groupe
entier suffisait à confondre `data-inerte` avec `data-anime`.

**Le second** vérifiait que le menu Termux lit `reglages.THEMES` au lieu de
recopier la liste… en cherchant `reglages.THEMES` dans le fichier. Le nom y
figure deux fois : remplacer la liste des clés par deux peaux en dur laissait
le second appel — donc le mot — en place. Le menu ne proposait plus que `nuit`
et `jour`, et le test restait vert. Il **fait tourner** le menu et regarde ce
qu'il affiche.

Les quinze mutations de la campagne sont maintenant vues.

---

# Ce qu'une peau ne pouvait pas changer

*Mesure du 14/09/2026, au navigateur puis au pixel.*

Les six peaux tenaient dans des variables CSS. Vingt-cinq règles n'en
lisaient aucune : elles peignaient une couleur **en dur**. Une peau ajoutée
après coup héritait donc de la peau d'origine sur tout ce que ces règles
touchaient, et le défaut ne ressemblait pas à un oubli de variable — il
ressemblait à une peau ratée.

`papier` est une peau crème, faite pour travailler une heure. Elle portait :

| | ce qu'elle déclarait | ce qui s'affichait |
|---|---|---|
| barre du haut | crème (`--fond`) | bleu nuit `rgba(5,6,13,0.92)` |
| champs de saisie | crème | gris sombre `rgba(10,14,24,0.55)` |
| bouton de fabrication | brun | dégradé cyan → violet `#6f5bf5` |
| scène 3D | — | grille bleue |

Le titre brun sur cette barre bleu nuit donnait **1,07** de contraste. C'est
la mesure la plus basse de tout l'audit, sur le premier mot de la page.

## Ce que la mesure a trouvé, peau par peau

674 textes relevés : six peaux × six onglets, la page déroulée par paliers,
sur un écran de 412 × 915.

| peau | textes | sous 4,5 (avant) | cause |
|---|---|---|---|
| `console` | 121 | 0 | — |
| `contraste` | 122 | 0 | — |
| `papier` | 121 | 11 | barre en dur, champs en dur |
| `ambre` | 120 | 26 | scène et fond animé restés cyan |
| `nuit` | 122 | 27 | — *(voir plus bas : mesure biaisée)* |
| `jour` | 122 | **35** | `--accent` trop clair |

Que `console` et `contraste` sortent à zéro n'est pas une chance : ce sont les
deux peaux dont les couleurs ont été choisies **pour** être lisibles. Elles
servent ici de témoin — une mesure qui les aurait accusées aurait d'abord
accusé la mesure.

## Les deux défauts réels

**`jour --accent` valait `#008d9e`, soit 3,78.** Cet accent sert deux fois, et
les deux emplois tirent dans des sens opposés : en texte sur fond clair
(onglet actif, boutons discrets) il faut qu'il soit **sombre** ; en pavé sous
du texte blanc (titres de section) il faut aussi qu'il soit sombre. Les deux
tirant du même côté, il suffisait de descendre. `#007383` corrigeait la carte
(5,30) mais pas la barre d'onglets, à peine plus sombre : 4,39. C'est
`#006b7a` qui passe partout — 4,91 sur les onglets, 5,92 sur une carte, 6,21
sous du blanc.

**Le bouton « supprimer » écrivait `#fff` en dur sur `--rouge`.** Blanc sur le
rouge vif de cinq peaux sur six : 2,80 sur `console`, 2,85 sur `ambre`, 3,22
sur `contraste`, 3,45 sur `nuit` et `jour`. Le seul bouton de la page qui
détruit quelque chose était le moins lisible. Ces rouges-là veulent une encre
**sombre** (5,8 à 7,1) ; `papier`, dont le rouge est brique, garde une encre
claire et le déclare.

## Trois fois où la mesure s'est trompée avant de dire vrai

Elles se ressemblent toutes : la mesure rendait un chiffre crédible en
regardant autre chose que ce qu'elle annonçait.

**Lire la feuille de style.** Un titre peint en dégradé, un texte posé sur un
canvas : la couleur *calculée* ne dit rien de ce qu'on voit. Le premier
passage a rendu un fond blanc derrière toutes les peaux sombres.

**Poser `data-theme` à la main.** Le rafraîchissement d'état rendait la peau
enregistrée quelques instants plus tard. Trois peaux ont été mesurées sous les
couleurs de `nuit` — avec des pixels *identiques au bit près*, et c'est cette
identité qui a trahi le défaut. On passe désormais par `appliquerPeau()`,
c'est-à-dire par le chemin de l'utilisateur.

**Découper une capture avec `clip`.** Ses coordonnées sont celles du
**document**, celles d'un rectangle celles de la **fenêtre**. Dès qu'un onglet
était défilé, chaque vignette montrait un autre texte que celui qu'elle
nommait — et le verdict portait sur ce texte-là.

Trois précautions en sont sorties, qui valent pour toute mesure au pixel :

- **regarder les vignettes.** Chaque texte jugé est découpé et écrit sur le
  disque, *dans l'image qui vient de servir à la mesure*. Reprendre la
  vignette plus tard, en rechargeant l'onglet, montrait une bande vide alors
  que la mesure, elle, était juste : on ne vérifie pas une mesure avec une
  image prise ailleurs ;
- **avoir une boîte ne veut pas dire être peint.** Chromium garde le contenu
  d'un `<details>` fermé dans la mise en page, en `content-visibility: hidden`.
  Les vingt-neuf réglages des groupes repliés rendaient un fond uni, soit une
  faute inventée par réglage. Le test de survol tranche : ce qui n'est pas
  peint n'est pas touchable ;
- **l'encre se lit dans la feuille, le fond sur les pixels.** À douze pixels,
  presque aucun pixel de glyphe n'atteint la couleur déclarée : l'anticrénelage
  les mélange tous au fond. Lire l'encre sur les pixels sous-estimait le
  contraste d'environ quinze pour cent et fabriquait une vingtaine de fautes
  par peau qui n'existaient pas — c'est toute la colonne `--doux` du tableau
  ci-dessus. WCAG se calcule d'ailleurs sur les couleurs déclarées. Le fond,
  lui, se prend au pixel **médian** et non au plus fréquent : sur un bouton
  peint en dégradé aucune nuance de fond ne revient deux fois, tandis que
  l'encre est plate, et le mode rendait l'encre pour fond — 1,00 annoncé sur
  un bouton parfaitement lisible.

## Le garde-fou

`tests/test_peaux_couleurs.py`, sans navigateur et sans dépendance :

- aucune couleur écrite hors d'un bloc `:root` ;
- le contraste WCAG de `--encre`, `--doux` et `--accent` sur le fond que
  chaque peau produit **vraiment** — `--carte` est translucide, donc le fond
  d'une carte n'est pas `--fond` mais la carte *posée* sur le fond ;
- l'encre du bouton « supprimer » sur son rouge ;
- une encre au moins lisible sur le pavé d'accent ;
- chaque appel de dessin de la scène 3D reçoit une couleur de la palette.

Ce que ce garde-fou **ne voit pas**, et le dit dans sa docstring : le
contraste réel d'un texte posé sur un dégradé, un canvas ou un halo ne se
calcule pas depuis la feuille de style. Et un gris translucide dans une ombre
ou une étape de dégradé passe — il marche sous toutes les peaux, et le refuser
serait crier à tort.

### Deux fois où ce garde-fou a failli ne rien garder

**Il cherchait `getPropertyValue` quelque part dans `scene.js`.** Une mutation
l'a mis en défaut : on peut lire la palette, la ranger dans une variable, et
continuer à dessiner juste à côté avec un triplet écrit en dur. Le fichier
contenait le mot cherché, le contrôle était vert, la scène restait bleue. Il
lit désormais la **structure** — chaque appel de `_dessiner`, et l'argument
qui porte sa couleur. Réécrit ainsi, il a trouvé sur-le-champ une septième
couleur en dur que la relecture humaine avait laissée passer.

**Il découpait la feuille de style ligne par ligne.** Le voile de scanlines
étale son dégradé sur trois lignes ; une ligne isolée ne montre plus qu'on est
dans un `gradient(`, et le contrôle signalait une étape de dégradé comme un
aplat. Il découpe désormais par **déclaration**.

Les onze mutations de la campagne sont vues.
