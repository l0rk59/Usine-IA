# Comment fonctionne USR

*Ce document décrit USR, qui reçoit du jeu la profondeur et les vecteurs
de mouvement. Le mode sans vecteurs (émulateurs, captures) est décrit dans
[UNIVERSEL.md](UNIVERSEL.md).*

## L'idée (la même que DLSS 2 et suivants)

Rendre en 1080p et afficher en 4K, c'est demander 4 pixels là où on n'en a
calculé qu'un. Un agrandissement classique (bilinéaire) ne peut qu'étaler
l'information : l'image est floue et les détails fins clignotent.

L'astuce : **décaler légèrement la caméra à chaque image** (le *jitter*,
moins d'un pixel). Sur 32 images, chaque pixel 4K a été « visité » par des
échantillons placés à des endroits différents. En suivant chaque point
d'une image à l'autre grâce aux **vecteurs de mouvement**, on accumule ces
échantillons dans un **historique** à pleine résolution. Sur une image
immobile, on converge vers une vraie image 4K anticrénelée.

Le problème, c'est quand l'historique ment : un objet est passé devant, un
écran s'est animé, une lumière s'est éteinte. Il faut alors le jeter, sinon
on voit des traînées fantômes. Mais si on le jette trop, on perd les détails
fins que seul l'historique connaissait. **Ce choix, pixel par pixel, est
exactement ce que le réseau de neurones apprend à faire.**

## Les trois passes

```
 résolution de rendu (ex. 1080p)            résolution d'affichage (ex. 4K)
 ┌──────────────────────────┐    ┌────────────────────────────────────────────┐
 │ 1. PRÉPARATION           │    │ 2. ACCUMULATION                            │
 │  profondeur, mouvement ──┼──▶ │  historique reprojeté (Catmull-Rom)         │
 │  • vecteur du voisin le  │    │  image courante reconstruite (3x3, jitter) │
 │    plus proche (bords)   │    │  boîte de couleurs du voisinage (YCoCg)    │
 │  • désocclusion (Z)      │    │  ┌──────────────────────────────┐          │
 └──────────────────────────┘    │  │ réseau 10 → 16 → 16 → 2       │          │
                                 │  │ alpha : croire l'image courante│         │
                                 │  │ beta  : garder l'historique brut│        │
                                 │  └──────────────────────────────┘          │
                                 │  mélange → nouvel historique (+ confiance) │
                                 └───────────────────┬────────────────────────┘
                                 ┌───────────────────▼────────────────────────┐
                                 │ 3. ACCENTUATION adaptative → sortie linéaire│
                                 └────────────────────────────────────────────┘
```

### 1. Préparation (`usr_prepare.hlsl`)

* **Dilatation** : chaque pixel prend le vecteur de mouvement du voisin
  3x3 le plus proche de la caméra. Sans cela, le bord d'un objet en
  mouvement hériterait du mouvement du décor et laisserait un liseré.
* **Désocclusion** : on regarde où était ce point à l'image précédente et
  ce qu'il y avait là. Si une surface nettement plus proche (écart relatif
  de profondeur > 2 à 6 %) occupait l'endroit, ce qu'on voit maintenant
  était caché : son historique n'existe pas.

### 2. Accumulation (`usr_accumulate.hlsl`)

1. **Reprojection** de l'historique au point `uv - mouvement`, avec un
   filtre de Catmull-Rom (16 lectures) qui reste net malgré les
   rééchantillonnages successifs.
2. **Image courante** : les 3x3 échantillons de rendu les plus proches,
   pondérés par une gaussienne centrée sur le pixel d'affichage, en tenant
   compte du jitter. Le noyau est large quand le pixel n'a pas d'historique
   (image propre tout de suite) et étroit ensuite (netteté maximale).
3. **Recadrage** : l'historique est ramené dans la boîte de couleurs du
   voisinage courant (moyenne ± 1,25 écart-type, bornée par le min/max,
   en YCoCg). C'est la protection classique des TAA contre les fantômes.
4. **Décision** : la règle heuristique (moyenne cumulée pondérée par la
   confiance) donne un `alpha` de départ. Le réseau le **corrige** et choisit
   `beta`, la part d'historique non recadré à conserver.
5. **Mélange** et écriture du nouvel historique : couleur compressée
   (`c / (1 + max(c))`, réversible, pour que le HDR ne bave pas) et
   confiance dans le canal alpha.

### 3. Accentuation (`usr_sharpen.hlsl`)

Accentuation adaptative au contraste (5 lectures) : forte dans les zones
douces, nulle sur les bords déjà francs, bornée par le voisinage (pas de
halo). Puis retour en couleurs linéaires.

## Le réseau

| | |
|---|---|
| Architecture | perceptron 10 → 16 → 16 → 2, ReLU |
| Paramètres | 482 (1,9 Ko) |
| Coût | ~420 multiplications-additions par pixel |
| Sorties | correction du logit d'`alpha`, `beta` (sigmoïde) |

Les 10 entrées, toutes calculées dans la passe :

| # | Entrée | Ce qu'elle dit au réseau |
|---|---|---|
| 0 | alpha heuristique | ce que ferait un TAA classique |
| 1 | écart historique / voisinage (en σ) | l'historique est-il plausible ? |
| 2 | amplitude du recadrage | combien le recadrage modifierait |
| 3 | contraste local | zone de détails ou aplat |
| 4 | désocclusion | la profondeur dit-elle « nouveau » ? |
| 5 | mouvement (log2 pixels) | immobile, lent, rapide |
| 6 | poids de l'image courante | un échantillon tombe-t-il près du pixel ? |
| 7 | confiance de l'historique | nombre d'images accumulées |
| 8 | écart image courante / voisinage | aliasing, point isolé |
| 9 | flou de rééchantillonnage | position sous-pixel de la reprojection |

Pourquoi si petit ? Parce que le réseau ne *dessine* rien : il arbitre
entre des couleurs déjà calculées. C'est ce qui le rend robuste, peu coûteux
sur un GPU sans unités matricielles, et impossible à faire « halluciner ».

## L'entraînement (`usr_ref/train.py`)

* **Données** : une scène procédurale (décor qui défile, objets qui se
  croisent, rayures et lignes plus fines qu'un pixel, points HDR, écran
  animé et néon *sans* vecteurs de mouvement). La vérité terrain est
  rendue à la résolution d'affichage avec 16 échantillons par pixel.
* **Perte** : erreur quadratique face à la vérité **+ stabilité
  temporelle** — la variation de la sortie d'une image à l'autre doit
  suivre celle de la vérité. Sans ce second terme, le réseau gagne en
  finesse mais scintille davantage.
  Le poids de ce terme se règle (`python -m usr_ref entrainer
  --stabilite N`) ; mesures sur les scènes de test :

  | Stabilité | PSNR caméra fixe | Scintillement caméra fixe |
  |---|---|---|
  | 0 | 28,7 – 29,9 dB | 0,0106 – 0,0108 |
  | **1 (par défaut)** | 28,4 – 29,4 dB | 0,0073 – 0,0078 |
  | 4 | 26,8 – 27,7 dB | 0,0053 – 0,0061 |
  | *sans IA* | *25,3 – 25,8 dB* | *0,0065 – 0,0083* |
* **En plusieurs tours** : l'historique dépend des décisions du réseau,
  donc chaque tour recollecte les données avec le réseau du tour précédent.
* **Sans PyTorch** : NumPy et une rétropropagation écrite à la main
  (vérifiée par différences finies dans les tests). Quelques minutes sur
  un processeur.

Les poids sont exportés en trois formats : `weights/usr_net.json`
(lisible), `weights/usr_net.bin` (chargé par `usr::SetWeights`) et
`src/usr_default_weights.h` (compilé dans la bibliothèque).

## Limites connues

* Entraîné sur une scène synthétique : il faudra le ré-entraîner sur de
  vraies captures du jeu visé (couleur, profondeur, mouvement + une image
  de référence en super-échantillonnage) pour en tirer le meilleur.
* Pas encore de masque « réactif » pour les particules et la transparence.
* Résolution de rendu fixe (pas de résolution dynamique).
* Pas de génération d'images intermédiaires (ce que DLSS 3/4 appelle
  *Frame Generation*) : c'est un autre problème (interpolation par flot
  optique), et sur console il ajoute de la latence.
