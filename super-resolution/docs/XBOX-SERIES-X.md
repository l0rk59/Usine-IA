# La Xbox Series X, et comment y faire tourner USR

## Quelle carte graphique ?

La Xbox Series X n'a pas de « carte graphique » au sens PC : CPU et GPU sont
sur une même puce (un *APU*) conçue par AMD pour Microsoft. Le GPU est un
**AMD RDNA 2 sur mesure** — la même génération que les Radeon RX 6000.

| | Xbox Series X | Xbox Series S |
|---|---|---|
| Unités de calcul (CU) | 52 à 1,825 GHz | 20 à 1,565 GHz |
| Calcul FP32 | 12,15 TFLOPS | 4 TFLOPS |
| Calcul FP16 (compacté) | ~24 TFLOPS | ~8 TFLOPS |
| Entiers pour l'IA | 49 TOPS INT8, 97 TOPS INT4 | proportionnellement moins |
| Mémoire | 16 Go GDDR6 (10 Go à 560 Go/s + 6 Go à 336 Go/s) | 10 Go |
| API | DirectX 12 Ultimate | DirectX 12 Ultimate |

Ce qui compte pour un upscaler à réseau de neurones :

* **Pas de Tensor Cores.** Ce sont des unités matricielles propres aux
  GeForce RTX de NVIDIA ; RDNA 2 n'a pas d'équivalent (AMD n'a ajouté des
  instructions matricielles qu'avec RDNA 3, et des unités dédiées plus
  tard). C'est l'une des raisons pour lesquelles DLSS ne peut pas y tourner.
* **Mais des instructions « IA » quand même** : produits scalaires compactés
  en FP16, INT8 et INT4 (exposés en HLSL par `dot2add`,
  `dot4add_i8packed`…). Microsoft les a ajoutés à la demande pour ce genre
  d'usage. USR garde donc un réseau **minuscule** (482 poids, ~420
  multiplications-additions par pixel) qui tient dans ce budget.

## Pourquoi pas « DLSS 5 » sur la Xbox ?

1. **DLSS appartient à NVIDIA.** Code fermé, réseaux non distribués,
   licence limitée aux GPU NVIDIA RTX. Aucune version (2, 3, 4…) ne peut
   légalement ni techniquement être portée sur un GPU AMD.
2. **La console est une plateforme fermée.** Les jeux du commerce sont
   signés et chiffrés ; il n'existe aucun moyen autorisé d'injecter un
   upscaler dans *Forza*, *Halo* ou *Call of Duty*. Les contournements
   (piratage de la console) exposent au bannissement et sortent du cadre
   de ce projet.
3. **Les jeux Series X ont déjà leur upscaler** : FSR 2/3 d'AMD, TSR
   d'Unreal Engine 5, ou une reconstruction maison. C'est le studio qui
   choisit.

Ce qui est possible — et ce que fait USR — c'est un upscaler **du même
principe que DLSS** (images basse résolution décalées, vecteurs de
mouvement, historique, réseau de neurones qui arbitre) écrit pour ce GPU,
et que l'on intègre dans **ses propres jeux et applications**.

## Quatre façons de l'exécuter

### 1. Sur la console, en mode Développeur (accessible à tous)

Toute Xbox Series X|S de commerce peut passer en *mode Développeur* :

1. créer un compte développeur individuel sur Microsoft Partner Center
   (**gratuit** pour les particuliers depuis 2025) ;
2. installer l'application **Xbox Dev Mode** depuis le Microsoft Store de
   la console et suivre l'activation ;
3. redémarrer en mode Développeur, puis déployer une application **UWP
   DirectX 12** depuis Visual Studio (ou le *Device Portal*).

USR s'intègre dans une telle application sans modification : bytecode
DXIL standard, Shader Model 6.0, compute uniquement. Ce que Microsoft
accorde aux applications UWP sur Series X|S :

| | Type « App » (défaut) | Type « Game » |
|---|---|---|
| GPU | part de ~45 %, partagée | accès complet |
| Mémoire | 1 Go | 5 Go |
| Direct3D 12 | niveau 11.0, Shader Model 5.1 à 6.4 | idem |

Le type se change dans **Dev Home** : surligner l'application dans la
liste *Games & apps*, appuyer sur le bouton **Affichage** (View, les deux
petits carrés) de la manette, choisir *View details*, puis *App type* :
**Game**. Indispensable pour un upscaler. Pas de HDR ni de ray tracing
en UWP.

**Important** : en mode Développeur, la console **ne lance pas** les jeux
du commerce ; il faut quitter ce mode (bouton *Leave developer mode* de
Dev Home) pour rejouer. Les deux ne tournent jamais en même temps.

### 2. Sur la console, avec le GDK (studios, programme ID@Xbox)

Les jeux publiés utilisent le **Microsoft GDK** avec les extensions console,
réservées aux développeurs inscrits (ID@Xbox pour les indépendants).
L'en-tête `usr.h` choisit alors `d3d12_xs.h` (macro `_GAMING_XBOX_SCARLETT`),
et les shaders doivent être compilés par le `dxc` **du GDK**, qui produit
le code machine de la console :

```bash
cmake -B build-xbox --toolchain <toolchain GDK Scarlett> \
      -DUSR_DXC="<GDK>/bin/Scarlett/dxc.exe" \
      -DUSR_DXC_FLAGS="<options console du GDK>"
```

> Non testé : ce dépôt a été construit sans accès au GDK console. Le code
> n'utilise que l'API D3D12 standard, mais attendez-vous à quelques
> ajustements.

### 3. Sur PC (pour développer et comparer)

N'importe quel GPU Direct3D 12 (AMD, NVIDIA, Intel). C'est le moyen le
plus simple de mettre au point l'intégration avant de passer sur console :
un Radeon RX 6000 est d'ailleurs de la même famille que le GPU de la Series X.

### 4. Dans les jeux Xbox 360 émulés (Xenia, mode Développeur)

L'émulateur **Xenia** existe en version UWP pour la Xbox en mode
Développeur. Pour un jeu Xbox 360, c'est l'émulateur qui dessine l'image
sur la console. Notre version de Xenia peut donc l'agrandir avec **USR
Universel**, le mode qui n'a besoin que de l'image, réglable en jouant
(Vue + RB). Au **niveau 2**, l'émulateur décale lui-même la scène 3D du
jeu pour une vraie super-résolution. Construction, installation et
commandes : [XENIA.md](XENIA.md).

## Budget GPU estimé (à mesurer sur la console)

Estimation *théorique* en sortie 4K (1080p → 2160p, 8,3 millions de
pixels), pas une mesure :

| Passe | Travail par pixel | Ordre de grandeur |
|---|---|---|
| Préparation (1080p) | 9 lectures de profondeur, 4 de l'historique | < 0,2 ms |
| Accumulation + réseau (4K) | 16 + 9 lectures, ~420 MAC du réseau | 0,8 à 2 ms |
| Accentuation (4K) | 5 lectures | < 0,2 ms |

Soit **de l'ordre de 1 à 2,5 ms par image**, à comparer aux ~8 ms gagnés en
rendant 4 fois moins de pixels. Deux leviers si c'est trop : compiler avec
`USR_NETWORK_HALF` (réseau en FP16 compacté, jusqu'à 2x plus rapide sur la
partie réseau), ou créer le contexte avec `kCreateDisableNetwork`
(heuristique seule). Les chiffres réels se mesurent avec PIX sur la console.

**USR Universel** coûte plus cher : il estime lui-même le mouvement, sur
une pyramide d'images à la résolution de rendu (recherche de candidats,
motifs 5x5, Lucas-Kanade). Sur le GPU logiciel des tests, c'est environ
6 fois USR, mais ce rapport ne dit rien d'un vrai GPU. Pour Xenia, il
travaille en général sur du 720p (le flot) et sort en 4K
(l'accumulation). Le Labo affiche son temps GPU réel sur la console, vue
*USR Universel* : c'est la mesure à faire.
