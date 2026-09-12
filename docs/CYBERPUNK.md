# La peau cyberpunk du tableau de bord

Le tableau de bord a été entièrement reskinné : néon sur noir, grille en
fuite, scanlines, verre dépoli. Tout tient en **CSS + un canvas léger**, sans
une seule dépendance ajoutée — la contrainte fondatrice du projet.

## Ce qui compose l'effet

- **Palette néon** — cyan `#00f0ff` et magenta `#ff2bd6` sur un noir presque
  pur. Tout passe par des variables CSS (`--accent`, `--magenta`, `--neon`),
  donc le thème « jour » n'a qu'à redéfinir la palette : cyberpunk clair,
  même néon en plus discret.
- **Fond animé** (`cyber.js`) — une grille en perspective qui défile vers le
  spectateur, façon Tron, plus une pluie de glyphes. Canvas 2D, derrière tout,
  jamais cliquable.
- **Voile de scanlines** — un `body:after` en `repeating-linear-gradient`,
  effet CRT.
- **Titre à glitch** — « USINE-IA » avec aberration chromatique cyan/magenta,
  en CSS pur (deux pseudo-éléments animés).
- **Cartes en verre dépoli** — `backdrop-filter: blur`, bord néon, coins
  coupés (`clip-path`), un filet lumineux en haut à gauche comme une soudure
  de circuit.
- **Boutons néon**, champs à liseré cyan au focus, jauges et rails lumineux.
- Le menu Termux gagne un **bandeau encadré** cyan/magenta.

## Accessibilité et performance, non négociées

- Tout le mouvement se coupe sous **`prefers-reduced-motion`** : le fond animé
  et les scanlines disparaissent, le glitch s'arrête, la page reste
  entièrement utilisable.
- Le canvas de fond et la scène 3D sont **`aria-hidden`** : ils répètent
  visuellement ce que le texte dit déjà.
- Les deux thèmes tiennent à **380 px sans débordement horizontal**, et le
  rendu a été vérifié dans un vrai navigateur, sans erreur console.

Voir aussi les [tendances cyberpunk 2026](https://dev.to/sebyx07/introducing-cybercore-css-a-cyberpunk-design-framework-for-futuristic-uis-2e6c)
et le [dark glassmorphism](https://medium.com/@developer_89726/dark-glassmorphism-the-aesthetic-that-will-define-ui-in-2026-93aa4153088f)
dont l'esthétique s'inspire.
