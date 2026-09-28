# USR — Usine Super Résolution

**Un upscaler à réseau de neurones « à la DLSS », écrit pour le GPU de la
Xbox Series X** (AMD RDNA 2), qui tourne aussi sur tout PC Direct3D 12.

Le jeu rend en basse résolution (par exemple 1080p) avec un léger décalage
différent à chaque image ; USR accumule ces images grâce aux vecteurs de
mouvement et reconstruit l'image en haute résolution (4K). Un petit réseau
de neurones décide, pour chaque pixel, ce qu'il faut garder du passé et ce
qu'il faut prendre de l'image courante.

---

## D'abord, trois vérités sur ta console

**1. Sa carte graphique.** La Xbox Series X a un GPU **AMD RDNA 2** conçu
sur mesure pour Microsoft : 52 unités de calcul à 1,825 GHz, 12 TFLOPS,
DirectX 12 Ultimate — la même famille que les Radeon RX 6000. Détails dans
[docs/XBOX-SERIES-X.md](docs/XBOX-SERIES-X.md).

**2. DLSS ne peut pas y tourner.** DLSS (toutes versions, 2 à 5) appartient
à NVIDIA : code fermé, réservé aux GeForce RTX et à leurs *Tensor Cores*,
que le GPU AMD de la Xbox n'a pas. D'où ce projet : **même principe, code
ouvert, écrit pour RDNA 2**. (Et un autre nom, « DLSS » étant une marque
de NVIDIA.)

**3. On ne peut pas l'ajouter aux jeux du commerce.** La Xbox est une
plateforme fermée : les jeux sont signés et chiffrés, rien ne peut s'y
injecter sans pirater la console. USR s'intègre dans **tes propres jeux et
applications** DirectX 12 :

| Où | Pour qui | Comment |
|---|---|---|
| Xbox en **mode Développeur** | tout le monde (~20 € une fois) | application UWP DirectX 12 |
| Xbox via le **GDK** | studios inscrits (ID@Xbox) | jeu publié, shaders compilés par le dxc du GDK |
| **PC** Direct3D 12 | tout le monde | n'importe quel GPU AMD, NVIDIA, Intel |

---

## Résultats

Mesurés sur des scènes de test **jamais vues à l'entraînement** (mode
Performance, rendu 128x72 → affichage 256x144, 40 images, vérité terrain à
16 échantillons par pixel). PSNR : plus haut = plus fidèle ; scintillement :
plus bas = plus stable.

| Scène | Bilinéaire | USR sans IA | **USR avec IA** |
|---|---|---|---|
| 101, caméra fixe | 24,51 dB / 0,0006 | 25,32 dB / 0,0065 | **28,41 dB** / 0,0073 |
| 101, caméra mobile | 24,73 dB / 0,0398 | 25,14 dB / 0,0310 | **27,55 dB** / 0,0286 |
| 202, caméra fixe | 25,91 dB / 0,0008 | 25,78 dB / 0,0083 | **29,35 dB** / 0,0078 |
| 202, caméra mobile | 25,52 dB / 0,0354 | 25,34 dB / 0,0291 | **27,88 dB** / 0,0266 |

![De gauche à droite : bilinéaire, USR sans IA, USR avec IA, vérité terrain](docs/comparaison.png)

*De gauche à droite : bilinéaire, USR sans IA, **USR avec IA**, vérité
terrain (rendu 192x108 → 384x216, agrandi 3x). Sans IA, le recadrage
anti-fantômes efface la grille de lignes fines ; le réseau apprend à la
garder.*

Le réseau apporte **+2,4 à +3,6 dB** par rapport au même algorithme sans IA,
sans scintiller davantage. (Le bilinéaire ne « scintille » pas en caméra
fixe parce qu'il ne fait rien : pas de jitter, pas d'anticrénelage.)

À lire honnêtement : c'est une scène **synthétique** à petite résolution,
pas un vrai jeu, et rien n'a encore été mesuré sur une console. Voir
« Ce qui est vérifié » plus bas.

---

## Essayer en 2 minutes (sans Xbox, sans carte graphique)

```bash
cd super-resolution
pip install numpy
python -m usr_ref demo            # écrit resultats/comparaison.png
python -m usr_ref banc            # le tableau ci-dessus
```

`resultats/comparaison.png` montre côte à côte : bilinéaire, USR sans IA,
USR avec IA, et la vérité terrain.

Pour aller plus loin :

```bash
python -m usr_ref entrainer       # ré-entraîne le réseau (quelques minutes)
python -m usr_ref parite          # exécute les VRAIS shaders et compare
                                  # (pip install slangpy + pilote Vulkan)
```

## L'intégrer dans un jeu (C++ / Direct3D 12)

```bash
cmake -B build -A x64       # Windows : trouve dxc dans le SDK Windows
cmake --build build --config Release
```

```cpp
#include <usr/usr.h>

usr::CreateDesc cd = {};
cd.device = device;
cd.displayWidth = 3840;  cd.displayHeight = 2160;
usr::GetRenderSize(usr::QualityMode::Performance, 3840, 2160,
                   &cd.renderWidth, &cd.renderHeight);      // 1920x1080
usr::Context* ctx;
usr::CreateContext(cd, &ctx);

// chaque image : décaler la projection avec usr::GetJitterOffset, rendre,
// puis
usr::Dispatch(ctx, dispatchDesc);   // couleur + profondeur + mouvement -> 4K
```

Toutes les conventions (jitter, vecteurs de mouvement, profondeur, états
des ressources) : [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Comment ça marche

Trois passes compute (Shader Model 6.0) par image :

1. **Préparation** (résolution de rendu) — vecteurs de mouvement du voisin
   le plus proche, détection des zones découvertes par la profondeur ;
2. **Accumulation** (résolution d'affichage) — historique reprojeté,
   image courante reconstruite, recadrage anti-fantômes, et le **réseau**
   (10 → 16 → 16 → 2, 482 poids) qui arbitre pixel par pixel ;
3. **Accentuation** adaptative au contraste, retour en linéaire.

Le réseau ne dessine rien : il choisit entre des couleurs déjà calculées.
C'est ce qui le rend minuscule, rapide sur un GPU sans unités matricielles,
et incapable d'« halluciner ». Explication complète :
[docs/ALGORITHME.md](docs/ALGORITHME.md).

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié automatiquement (voir `tests/` et `.github/workflows/super-resolution.yml`) :

- l'algorithme de référence (NumPy) et son gain mesuré face au
  bilinéaire et à l'heuristique ;
- la rétropropagation du réseau (différences finies) et ses exports ;
- **les shaders HLSL compilent** avec DXC (DXIL SM 6.0, SM 6.2 en FP16,
  SPIR-V) sans avertissement ;
- **les shaders calculent la même image que la référence** : exécutés sur
  un GPU logiciel (Mesa llvmpipe, Vulkan), écart > 55 dB de PSNR, aux
  arrondis FP16 près ;
- la bibliothèque C++ se construit avec CMake en `-Wall -Wextra -Werror`
  (g++ et clang, avec les en-têtes DirectX ouverts de Microsoft).

**Pas encore vérifié** — il faut une machine Windows ou une Xbox :

- la compilation sous Windows avec MSVC (prévue dans l'intégration
  continue, job `windows`, pas encore exécutée) ;
- l'exécution de la bibliothèque C++ sur un vrai runtime Direct3D 12 ;
- la compilation avec le GDK console et le fonctionnement sur Xbox ;
- les performances réelles (estimation : 1 à 2,5 ms en 4K sur Series X) ;
- la qualité sur un vrai jeu (le réseau n'a vu que la scène synthétique).

## Arborescence

```
super-resolution/
├── shaders/          les 3 passes HLSL (le code qui tourne sur la Xbox)
├── include/usr/      API C++ publique
├── src/              implémentation Direct3D 12 + poids par défaut
├── usr_ref/          référence Python : algorithme, scène, entraînement
├── weights/          poids du réseau (.json lisible, .bin pour le GPU)
├── tests/            tests unitaires, cohérence, parité GPU
└── docs/             Xbox Series X, intégration, algorithme
```

## Feuille de route

- [ ] Mesures sur Xbox Series X (mode Développeur) et sur PC
- [ ] Ré-entraînement sur de vraies captures de jeu
- [ ] Résolution dynamique
- [ ] Masque « réactif » pour particules et transparence
- [ ] Réseau en INT8 (`dot4add_i8packed`) pour les TOPS INT8 de RDNA 2
- [ ] Génération d'images intermédiaires (à évaluer : latence sur console)

## Licence

MIT, comme le reste du dépôt. DLSS est une marque de NVIDIA Corporation,
Xbox une marque de Microsoft ; ce projet n'est affilié à aucune des deux.
