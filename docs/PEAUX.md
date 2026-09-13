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
