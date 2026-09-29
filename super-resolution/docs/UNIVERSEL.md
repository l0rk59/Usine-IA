# USR Universel — l'upscaler qui n'a besoin que de l'image

USR « normal » est intégré **dans le jeu** : le moteur lui donne, à chaque
image, la couleur HDR, la profondeur, les vecteurs de mouvement et le
décalage sous-pixel (jitter) qu'il a utilisé. Un **émulateur** comme Xenia,
ou une capture vidéo, n'a rien de tout cela : seulement l'image finale,
déjà compressée pour l'écran, HUD compris.

**USR Universel** est le mode fait pour ce cas. Il estime lui-même le
mouvement sur l'image et accumule les images successives sans rien
demander au jeu. C'est lui qui tourne dans notre version de Xenia
([XENIA.md](XENIA.md)), et le Labo permet de le comparer à USR sur la
console ([LABO.md](LABO.md), page « Universel »).

| | USR (dans un jeu) | USR Universel (émulateur, capture) |
|---|---|---|
| Entrées | couleur HDR, profondeur, vecteurs de mouvement, jitter | l'image affichée (8 bits), et le jitter s'il est injecté (niveau 2) |
| Mouvement | fourni par le jeu, exact | **estimé** sur l'image (flot optique) |
| Zones découvertes | par la profondeur | par l'écart à l'historique et le doute du flot |
| Réseau | 10 → 16 → 16 → 2 (482 poids) | même taille, entraîné sur le scénario « jeu émulé » |
| Passes GPU | 3 | 9 programmes (flot sur une pyramide de 3 à 6 niveaux, puis accumulation) |

## Les deux niveaux

**Niveau 1 : l'image telle quelle.** L'émulateur ne touche pas au jeu.
Le jeu échantillonne toujours le centre des mêmes pixels, donc deux images
successives n'apportent **aucun détail nouveau**. USR Universel ne peut
alors guère faire mieux qu'un bon agrandissement spatial. Mesuré :
**autant que Lanczos, pas mieux** (29,08 dB contre 29,03 dB). Il reste
stable, ne crée pas de traînées, et sert de socle au niveau 2.

**Niveau 2 : l'émulateur injecte le jitter.** À chaque image, Xenia décale
la scène 3D d'une fraction de pixel **connue**, sans décaler le HUD.
USR Universel reçoit ce décalage. Si le rapport d'agrandissement est entier
(2x ou 3x), c'est une grille : chaque pixel d'écran reçoit un échantillon
exactement en son centre toutes les 4 ou 9 images. Sinon, c'est une suite
de Halton. Xenia rend en plus les textures **plus fines** (biais de
mip-map de −1). C'est là qu'apparaît la vraie super-résolution.

Une subtilité mesurée : le jitter **seul** ne suffit pas (28,89 dB, pas
mieux que le niveau 1). Les textures d'un jeu sont filtrées pour sa
résolution (mip-maps) : le détail qu'on voudrait accumuler n'y est déjà
plus. C'est le biais de mip-map qui le remet dans l'image. Les deux vont
ensemble, et c'est le réglage par défaut du niveau 2.

## Mesures

Scénario « jeu émulé » (`usr_ref/emul.py`), sur des scènes que le réseau
n'a **jamais vues** (graines 101 et 202 ; il a été entraîné sur 1 à 9) :

- décor texturé filtré comme dans un vrai jeu ;
- objets en mouvement ;
- écrans animés et néon qui changent **sans** mouvement ;
- HUD fixe (barre de vie, texte, viseur).

L'image est rendue en 192x108 (rapport 2) ou 128x72 (rapport 3), puis
agrandie en 384x216. Elle est comparée au même jeu rendu directement en
384x216 à 16 échantillons par pixel. Chaque séquence fait 32 images, et
les 8 premières ne comptent pas. PSNR en dB, puis SSIM : plus haut = plus
fidèle.

**Rapport 2** (écran 4K pour un jeu en 1080p, ou 1440p pour du 720p)

| Scène | Bilinéaire | Lanczos | Spatial (type FSR 1) | USR-U niveau 1 | **USR-U niveau 2** |
|---|---|---|---|---|---|
| 101, caméra mobile | 28,88 / 0,893 | 29,03 / 0,915 | 28,66 / 0,924 | 29,08 / 0,916 | **29,44 / 0,934** |
| 101, caméra fixe | 29,05 / 0,889 | 29,20 / 0,908 | 28,76 / 0,915 | 29,16 / 0,910 | **30,71 / 0,950** |
| 202, caméra mobile | 28,80 / 0,887 | 28,79 / 0,908 | 28,23 / 0,916 | 28,99 / 0,910 | **29,34 / 0,928** |
| 101 « brute »\* | 25,12 / 0,798 | 24,95 / 0,819 | 23,81 / 0,789 | **25,24** / 0,818 | 25,15 / **0,824** |

**Rapport 3** (un jeu Xbox 360 en 720p sur un écran 4K)

| Scène | Bilinéaire | Lanczos | Spatial (type FSR 1) | USR-U niveau 1 | **USR-U niveau 2** |
|---|---|---|---|---|---|
| 101, caméra mobile | 26,55 / 0,800 | 26,55 / 0,818 | 26,44 / 0,836 | 26,59 / 0,820 | **27,08 / 0,864** |
| 101, caméra fixe | 26,74 / 0,805 | 26,74 / 0,820 | 26,62 / 0,836 | 26,66 / 0,815 | **28,41 / 0,911** |
| 202, caméra mobile | 26,57 / 0,792 | 26,46 / 0,807 | 26,24 / 0,824 | 26,54 / 0,809 | **26,93 / 0,853** |

\* Scène « brute » : l'ancienne scène de test, sans textures filtrées. Ses
lignes plus fines qu'un pixel scintillent d'une image à l'autre : c'est la
plus difficile. Le biais de mip-map n'y change rien. C'est aussi la scène
du Labo.

Ce qu'il faut en retenir, honnêtement :

- **Le niveau 2 est le seul vrai gain.** Contre le meilleur agrandissement
  spatial, il gagne +0,4 à +0,5 dB (SSIM +0,01 à +0,03) en mouvement, et
  +1,5 à +1,7 dB (SSIM +0,04 à +0,08) quand l'image est stable. C'est
  cohérent : plus l'image est stable, plus l'historique est utilisable.
- **Le réseau est indispensable.** Les mêmes règles sans lui perdent 0,9
  à 1,6 dB, et font souvent moins bien que Lanczos.
- **Le scintillement** en mouvement (rapport 2) est légèrement supérieur à
  celui de FSR 1 : 0,013 contre 0,011 (écart moyen de la variation d'une
  image à l'autre par rapport à la vérité).
- **Par régions** (rapport 2, caméra mobile) :
  - les **objets en mouvement** gagnent le plus : 28,76 dB contre 25,89
    pour Lanczos et 28,02 pour FSR 1 ;
  - les **écrans animés sans mouvement** ne perdent rien : 31,0 dB, comme
    Lanczos ;
  - le **HUD**, non décalé, ne gagne rien et perd même un peu au niveau
    2 : 15,5 dB contre 16,0 au niveau 1.
- Tout cela est mesuré sur une **scène synthétique** en petite
  résolution, pas sur un vrai jeu Xbox 360, et rien n'a encore tourné sur
  une console.

Le tableau complet (avec les régions et le scintillement) est dans
[mesures_universel.json](mesures_universel.json). Pour le refaire :

```bash
cd super-resolution
python -m usr_ref universel-banc --sortie mesures.json   # ~20 min
python -m usr_ref universel-banc --rapide                # scène 101, x2
```

## Comment ça marche

Toutes les passes sont des compute shaders (Shader Model 6.0), dans
`shaders/usr_u_*.hlsl`. Chacune a son jumeau NumPy, formule pour formule,
dans `usr_ref/flow.py` et `usr_ref/universel.py`.

### 1. Estimer le mouvement (résolution de rendu)

- **Luminance entière** (`usr_u_luma`) : R + 2G + B sur les valeurs 8 bits
  (0 à 1020), puis une **pyramide** de moitié en moitié (`usr_u_down`)
  jusqu'à environ 24 pixels, et son gradient (`usr_u_grad`).
- **Recherche par candidats** (`usr_u_flow`), du niveau le plus grossier
  au plus fin :
  - au sommet, toute la grille ±4 pixels, plus le mouvement de l'image
    précédente à ±1 près ;
  - ensuite, le mouvement du parent et de ses 4 voisins, zéro, et le
    mouvement précédent ;
  - chaque candidat est noté par la différence absolue sur un motif 5x5,
    plus une petite pénalité s'il s'écarte du mouvement attendu ;
  - le meilleur est affiné par une itération de **Lucas-Kanade**.
- **Médiane vectorielle** 3x3 (`usr_u_median`) contre les valeurs
  aberrantes.
- **Doute du flot** (`usr_u_finalize`) : après recalage, ce qui reste de
  différence, rapporté au contraste local. 0 = mouvement bien retrouvé,
  1 = aucune correspondance (apparition, transparence, écran animé).
- **Deux tests exacts** qui priment sur l'estimation :
  - un pixel **identique** à l'image précédente, alors que le jitter a
    changé, n'a pas été décalé (HUD, bandes noires) : il est traité comme
    fixe à l'écran ;
  - au niveau 2, un pixel identique à l'image d'il y a une période de
    jitter est **immobile**.

  Ce sont eux qui rendent le HUD et les décors fixes parfaitement stables.

Le jitter est compensé partout. Le mouvement cherché est celui de la
**scène**, pas le décalage de l'échantillonnage.

### 2. Accumuler (résolution d'affichage)

- **Résidu** (`usr_u_residual`) : pour chaque nouvel échantillon, on
  compare ce que l'historique prédit à sa position exacte (Catmull-Rom).
  La différence est l'**information nouvelle**. S'il sort franchement de
  la plage de ses voisins (test de boîte), c'est un changement, pas un
  détail.
- **Accumulation** (`usr_u_accumulate`) :
  - l'historique reprojeté reçoit le résidu interpolé, multiplié par un
    **gain** ;
  - le résultat est tiré vers une image fraîche (Lanczos-2, sans
    rebond), selon une **réactivité** ;
  - les règles de base fixent les deux : réactivité = sortie de boîte ou
    doute du flot, gain = proximité / (confiance + proximité) ;
  - le **réseau** (10 entrées, 2 sorties) corrige ces deux décisions,
    pixel par pixel.

  Comme pour USR, il ne dessine rien : il choisit entre des valeurs déjà
  calculées.
- **Accentuation** RCAS (`usr_u_output`), réglable de 0 à 100 %.

### Même résultat sur tous les GPU

Un flot optique prend des décisions discrètes (quel candidat gagne).
Une différence d'un ulp (la plus petite possible) sur l'entrée, due à un
autre GPU qui arrondit autrement la conversion 8 bits, pouvait faire
basculer un choix. L'écart grandissait ensuite d'image en image : 45,9 dB
seulement entre deux implémentations pourtant correctes.

D'où la luminance entière et des coûts comparés à résolution fixe (1/4096)
: le choix ne dépend plus de ces arrondis
(`tests/test_universel.py::test_insensible_a_l_arrondi`). La bibliothèque
C++, exécutée sous Wine, redonne alors l'image de la référence à plus de
57 dB.

## L'utiliser (C++ / Direct3D 12)

```cpp
#include <usr/usr.h>

usr::UniversalCreateDesc cd = {};
cd.device = device;
cd.renderWidth = 1280;  cd.renderHeight = 720;    // image du jeu
cd.displayWidth = 3840; cd.displayHeight = 2160;  // écran
// niveau 2 : période de la suite de jitter que tu injectes (sinon 0)
cd.jitterPeriod = usr::GetUniversalJitterPeriod(1280, 720, 3840, 2160);
usr::UniversalContext* u = nullptr;
usr::CreateUniversalContext(cd, &u);

// chaque image
usr::UniversalDispatchDesc d = {};
d.commandList = cl;
d.color = gameImage;       // NON_PIXEL_SHADER_RESOURCE, vue UNORM (pas sRGB)
d.output = upscaled;       // UNORDERED_ACCESS, résolution d'écran
usr::GetUniversalJitter(frame, 1280, 720, 3840, 2160, &d.jitterX, &d.jitterY);
d.reset = sceneCut;        // coupure, chargement
usr::DispatchUniversal(u, d);   // lie son tas de descripteurs : re-lier le sien
```

Conventions :

- **L'image** est celle que verrait l'écran (valeurs de 0 à 1, déjà
  compressées). Lis-la en UNORM, pas en sRGB, pour garder les valeurs de
  l'écran. La sortie est dans le même espace.
- **Le jitter** passé à `DispatchUniversal` doit être exactement celui
  injecté dans le rendu de cette image. L'échantillon est au centre du
  pixel + (jitterX, jitterY), en pixels de rendu, y vers le bas. Au
  niveau 1, laisser 0 et `jitterPeriod = 0`.
- **Réglages** modifiables à chaque image : `sharpness` (0 à 1),
  `networkStrength` (0 = règles seules, jusqu'à 4), `historyLength` (1 à
  64 images), `antiGhosting` (0,05 à 4, défaut 0,3).
- **Diagnostic** : `debugOutput` (RGBA, résolution d'écran) reçoit par
  pixel la réactivité, le gain, la mémoire accumulée et le doute du flot.
- **DLAA** : `displayWidth/Height` égaux à la taille de rendu. Le jitter
  est alors Halton, sur 8 phases.
- **Génération d'images** : après `DispatchUniversal`, et avant le
  suivant, `usr::InterpolateUniversal` fabrique l'image du milieu entre
  la sortie précédente et celle-ci, avec le flot tout juste estimé.
  - Il faut garder la sortie précédente dans une seconde texture.
  - L'appel rend `NotReady` tant qu'aucun flot n'existe : première image,
    ou juste après une coupure.
  - Mesures et limites : [GENERATION.md](GENERATION.md).

## Vérifié, et pas encore vérifié

Vérifié automatiquement :

- tests de la référence (`tests/test_universel.py`) : flot sous-pixel,
  grands déplacements, image fixe, HUD, test « même phase », insensibilité
  aux arrondis, convergence de l'accumulation ;
- **les shaders calculent la même chose que la référence**, exécutés sur
  GPU logiciel (`tests/test_parite_gpu.py`) ;
- ils compilent sans avertissement avec dxc (DXIL SM 6.0, FP16 SM 6.2,
  SPIR-V) ;
- la bibliothèque C++ (`src/usr_universal_dx12.cpp`) :
  - compile en `-Wall -Wextra -Werror` ;
  - **tourne sous Wine + vkd3d-proton** avec une sortie identique à la
    référence (plus de 55 dB exigés, 16 images, remise à zéro comprise :
    `tests/wine/universel_wine.sh`) ;
- dans **l'application USR Labo** (vue Universel), la sortie est identique
  à la référence sur 24 images (`tests/test_labo_bout_en_bout.py`).

Pas encore vérifié :

- la qualité sur de **vrais jeux** ;
- le **coût réel** sur Xbox Series X. Il est plus élevé que celui de USR,
  car le flot se calcule sur toute une pyramide : sur le GPU logiciel,
  environ 6 fois USR. Le Labo affiche le temps GPU de chaque passe : c'est
  sur la console qu'il faut le lire.

Pour ré-entraîner le réseau (une demi-heure environ sur un processeur ;
`--rapide` pour essayer) :

```bash
python -m usr_ref universel-entrainer
```
