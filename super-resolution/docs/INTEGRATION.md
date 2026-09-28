# Intégrer USR dans un moteur Direct3D 12

## Ce que le jeu doit fournir

À chaque image, en **résolution de rendu** :

| Entrée | Format typique | Remarque |
|---|---|---|
| Couleur | `R16G16B16A16_FLOAT`, `R11G11B10_FLOAT` | linéaire, **avant** post-traitements (flou, grain, HUD) |
| Profondeur | `D32_FLOAT`, `D24_UNORM_S8_UINT` | la profondeur du tampon Z telle quelle |
| Vecteurs de mouvement | `R16G16_FLOAT` | pour **chaque** objet qui bouge, pas seulement la caméra |

Et une texture de sortie en **résolution d'affichage**, créée avec
`ALLOW_UNORDERED_ACCESS` (pas de format sRGB : une UAV ne peut pas en être).

Le HUD, le flou de mouvement, la profondeur de champ et le grain se
dessinent **après** USR, à pleine résolution.

## Les trois conventions à respecter

### 1. Le jitter

Chaque image est rendue avec un décalage sous-pixel différent. USR fournit
la suite (Halton 2,3) :

```cpp
const uint32_t phases = usr::GetJitterPhaseCount(renderW, displayW);
float jx, jy;
usr::GetJitterOffset(frameIndex, phases, &jx, &jy);   // dans [-0.5, 0.5]

// Décaler la projection (convention D3D, y de l'écran vers le bas) :
proj._31 += -2.0f * jx / renderW;   // colonne de translation en x
proj._32 +=  2.0f * jy / renderH;   // ... en y
```

(`_31`/`_32` pour une matrice ligne-majeure « vecteur × matrice » comme
DirectXMath ; `_13`/`_23` dans la convention colonne.)

Passez ensuite **les mêmes** `jx, jy` dans `DispatchDesc`. Signification :
le pixel de rendu `(i, j)` contient la scène vue en
`((i + 0.5 + jx) / w, (j + 0.5 + jy) / h)`.

Les vecteurs de mouvement, eux, se calculent **sans** le jitter (matrices
de projection non décalées de l'image courante et de la précédente).

### 2. Les vecteurs de mouvement

USR attend : `uv_précédent = uv_courant - mv * motionScale`, en
coordonnées de texture (0..1, y vers le bas).

| Votre moteur écrit… | `motionScaleX`, `motionScaleY` |
|---|---|
| uv, courant − précédent | `1, 1` |
| pixels, courant − précédent | `1/renderW, 1/renderH` |
| NDC, courant − précédent | `0.5, -0.5` |
| … précédent − courant | mêmes valeurs, signe opposé |

Un signe faux se voit tout de suite : l'image traîne dans le sens du
mouvement au lieu de rester nette.

### 3. La profondeur

USR linéarise la profondeur avec deux paramètres :

```cpp
float p0, p1;
usr::GetDepthParams(nearZ, farZ, /*reversedZ*/ true, /*infiniteFar*/ true,
                    &p0, &p1);
```

Elle sert à deux choses : suivre le mouvement de l'objet le plus proche
sur les bords, et repérer les zones **désoccluses** (découvertes depuis
l'image précédente), où l'historique est jeté.

## Cycle de vie

```cpp
#include <usr/usr.h>

usr::CreateDesc cd = {};
cd.device = device;
cd.displayWidth = 3840;  cd.displayHeight = 2160;
usr::GetRenderSize(usr::QualityMode::Performance, 3840, 2160,
                   &cd.renderWidth, &cd.renderHeight);
cd.maxFramesInFlight = 3;              // comme votre boucle de rendu
usr::Context* ctx = nullptr;
if (usr::CreateContext(cd, &ctx) != usr::Result::Ok) { /* ... */ }

// Chaque image, après le rendu de la scène :
usr::DispatchDesc d = {};
d.commandList   = commandList;
d.color         = sceneColor;    // NON_PIXEL_SHADER_RESOURCE
d.depth         = depthBuffer;   // NON_PIXEL_SHADER_RESOURCE
d.motionVectors = velocity;      // NON_PIXEL_SHADER_RESOURCE
d.output        = upscaled;      // UNORDERED_ACCESS
d.jitterX = jx;  d.jitterY = jy;
d.motionScaleX = 1.0f / cd.renderWidth;
d.motionScaleY = 1.0f / cd.renderHeight;
d.depthP0 = p0;  d.depthP1 = p1;
d.sharpness = 0.3f;
d.reset = cameraCut;             // coupure de plan, téléportation, chargement
usr::Dispatch(ctx, d);

// USR a lié SON tas de descripteurs : re-liez le vôtre.
commandList->SetDescriptorHeaps(1, &myHeap);

// À la fermeture, après avoir attendu le GPU :
usr::DestroyContext(ctx);
```

## Réglages avancés

Tous se changent d'une image à l'autre, sans recréer le contexte. Les
valeurs par défaut sont celles avec lesquelles le réseau a été entraîné.

| Champ de `DispatchDesc` | Défaut | Effet |
|---|---|---|
| `networkStrength` | 1.0 | 0 = heuristique seule, 1 = réseau tel qu'entraîné, jusqu'à 4 = décisions amplifiées |
| `historyLength` | 10 | images accumulées au maximum : plus = plus fin à l'arrêt, plus lent à oublier |
| `antiGhosting` | 1.25 | boîte anti-fantômes en écarts-types : petit = moins de traînées, plus de scintillement |
| `kernelWidth` | 1.0 | noyau d'accumulation : < 1 plus net mais plus bruité, > 1 plus doux |
| `sharpness` | 0 | accentuation finale, 0 à 1 |
| `debugOutput` | aucun | texture RGBA qui reçoit par pixel alpha, beta, confiance, désocclusion |

## Points d'attention

* **Tas de descripteurs** : `Dispatch` appelle `SetDescriptorHeaps` avec le
  tas interne de USR. Re-liez le vôtre juste après.
* **Images en vol** : USR réserve `maxFramesInFlight` tranches de
  descripteurs. Ne soumettez jamais plus d'images d'avance que ce nombre.
* **Ordre d'exécution** : les appels `Dispatch` doivent s'exécuter sur le
  GPU dans l'ordre où ils ont été enregistrés (même file de commandes).
* **Résolution de rendu fixe** : cette version ne gère pas encore la
  résolution dynamique ; changer de taille = recréer le contexte.
* **Exposition** : en HDR, passez l'exposition du jeu dans `exposure` pour
  que la compression interne travaille sur des valeurs « affichables ».
* **Transparence, particules** : sans vecteurs de mouvement, ils peuvent
  laisser des traînées. Dessinez-les après USR si possible (un masque
  « réactif » est prévu dans la feuille de route).
* **Poids du réseau** : `usr::SetWeights` charge un autre fichier `.bin`
  (produit par `python -m usr_ref entrainer`), entre deux images.

## Diagnostiquer

| Symptôme | Cause probable |
|---|---|
| Image floue qui ne s'affine jamais | jitter non appliqué à la projection, ou pas transmis à USR |
| Traînées derrière les objets | signe ou échelle des vecteurs de mouvement ; objets animés sans vecteurs |
| Scintillement des détails fins | suite de jitter qui recommence trop tôt (`frameIndex` remis à zéro) |
| Halos sur les bords d'objets | profondeur mal linéarisée (`reversedZ` inversé) |
| Tout noir / erreur de périphérique | états des ressources (voir tableau ci-dessus) ou UAV sRGB |
