# Captures de vrais jeux : entraîner USR sur la Xbox 360

Jusqu'ici, USR Universel n'a vu que des jeux **simulés**
(`usr_ref/emul.py`). Toutes ses mesures portent sur ces scènes
synthétiques. Le mode capture de Xenia enregistre de vraies séquences de
jeu, avec leur vérité terrain, pour mesurer et entraîner USR sur de vrais
jeux Xbox 360.

Tout se fait sans PC : la Xbox capture, le téléphone transfère, GitHub
mesure et entraîne.

## L'idée : rendre le jeu 3 fois plus grand

Il faut, pour entraîner, deux choses que l'émulateur ne donne pas
d'ordinaire :

- l'image « basse résolution » que USR reçoit, avec un jitter connu ;
- la vérité terrain à la taille d'affichage.

Xenia sait rendre un jeu à une échelle interne de 3
(`draw_resolution_scale_x/y = 3`). Une image rendue à l'échelle 3
contient **exactement** les 9 images que le jeu rendrait à l'échelle 1
avec le jitter en grille 3×3 du niveau 2.

- Le pixel *k* à l'échelle 1, décalé de (*i* + 0,5)/3 − 0,5 pixel,
  échantillonne la scène au centre du pixel 3*k* + *i* à l'échelle 3.
- Garder une ligne et une colonne sur trois, à la phase (*i*, *j*), donne
  donc l'image décalée.
- Et l'image à l'échelle 3 elle-même sert de vérité, à la taille
  d'affichage du rapport 3 (un jeu en 720p sur un écran 4K).

Ce n'est pas une approximation. Le test
`tests/test_capture_jeu.py` le vérifie sur le jeu simulé : chaque phase
décimée égale l'image rendue avec le jitter correspondant, à l'arrondi de
10 bits près (écart maximal 0,00048).

### Ce que la capture ne reproduit pas

- **Les mip-maps** : à l'échelle 3, le jeu choisit des textures 3 fois
  plus fines, soit un biais d'environ −1,6. Le niveau 2 de Xenia ne les
  affine que 2 fois (biais −1).
- **Le HUD** : décimé avec la scène, il « bouge » avec le jitter. Or au
  niveau 2, Xenia ne décale que les dessins qui testent la profondeur.
- **La vérité n'est pas parfaite** : c'est une image rendue à l'échelle
  3, avec son propre crénelage, et non une image sur-échantillonnée comme
  celle des scènes simulées.
- **Le rythme du jeu** : si le jeu ralentit à l'échelle 3 et calcule son
  mouvement sur le temps réel, les objets bougent davantage d'une image à
  l'autre qu'en jeu normal.

## 1. Sur la Xbox : activer la capture

Le fichier de configuration de Xenia est dans le stockage de l'appli.
D'après le code de xenia-canary-uwp, il se trouve à
`LocalState\Xenia\xenia-canary.config.toml` (non vérifié sur la
console). Depuis le téléphone, avec le Device Portal
(`https://IP-de-la-Xbox:11443`, voir [XENIA.md](XENIA.md)) :

1. **File explorer** → `LocalAppData` → `UsineIA.XeniaUSR_…` →
   `LocalState` → `Xenia`.
2. Télécharge `xenia-canary.config.toml`.
3. Modifie ces lignes :

   ```toml
   draw_resolution_scale_x = 3
   draw_resolution_scale_y = 3
   usr_capture = true
   postprocess_antialiasing = ""
   ```

4. Renvoie le fichier au même endroit (bouton *Upload*).

Puis joue normalement, une dizaine de minutes, en variant les scènes :
déplacements, combats, menus.

Ce que fait la capture :

- elle enregistre des **séquences de 48 images consécutives**, découpées
  en 384×216 pixels à un endroit tiré au hasard dans l'image, dans les
  couleurs que USR reçoit (après la rampe gamma, 10 bits par canal) ;
- elle attend 300 images du jeu entre deux séquences, soit 10 s à
  30 images/s, pour varier les scènes ;
- elle s'arrête après **40 séquences** : 16 Mo chacune, 640 Mo en tout ;
- elle coupe le jitter du niveau 2 tant qu'elle est active, puisque la
  décimation l'exige ;
- elle n'enregistre rien si l'échelle n'est pas 3. Le journal de Xenia
  le dit (« USR capture : rien n'est enregistre… ») et donne le nom de
  chaque séquence enregistrée.

L'échelle 3 coûte cher en GPU : le jeu peut ralentir pendant la capture.
Une fois fini, remets `usr_capture = false` et les échelles à 1.

## 2. Récupérer les captures sur le téléphone

Toujours dans le **File explorer** du Device Portal, le dossier
`LocalState\Xenia\usr_captures` contient les fichiers
`usrc_<jeu>_<date>_<n>.bin`. Télécharge-les.

## 3. Les déposer sur GitHub

Sur github.com, depuis le navigateur du téléphone, ouvre la branche de
travail, puis le dossier `super-resolution/captures/`. Utilise
**Add file → Upload files**.

- Chaque fichier fait 16 Mo, sous la limite de 25 Mo d'un envoi par le
  site.
- Dépose-les par petits groupes.
- Ce dossier ne relance pas la compilation de Xenia : il est exclu du
  workflow `super-resolution`.

## 4. Mesurer et entraîner

Onglet **Actions** → **usr-captures** → **Run workflow**, sur la même
branche. En une demi-heure environ, le workflow :

1. mesure le réseau livré sur la **réserve** ;
2. réentraîne le réseau universel avec les scènes synthétiques **et** les
   autres captures, si la case est cochée ;
3. mesure le nouveau réseau sur la même réserve.

La **réserve**, c'est une capture sur quatre, qui n'est jamais apprise.
Mesurer sur les captures apprises donnerait un gain flatteur et faux.
Avec moins de quatre captures, il n'y a pas de réserve, et la commande
le signale.

Les résultats et les nouveaux poids sont dans l'artefact
`usr-captures` :

- `captures-reseau-livre.json` ;
- `captures-nouveau-reseau.json` ;
- `usr_universel_captures.json`.

Chaque ligne donne le PSNR et le scintillement de :

- Lanczos (sans historique) ;
- USR en règles de base ;
- USR avec IA ;

aux niveaux 1 et 2, capture par capture.

**Adopter les nouveaux poids** est une décision à part. On ne l'envisage
que si la réserve s'améliore sans que les scènes synthétiques se
dégradent, à vérifier avec `python -m usr_ref universel-banc --poids …`.
Il faut alors les copier dans `weights/usr_universel.json` et régénérer
l'en-tête C++ (`python -m usr_ref exporter --universel`).

## En local (avec un PC)

```bash
python -m usr_ref universel-captures captures/ --reserve
python -m usr_ref universel-entrainer --captures captures/ --sortie essai.json
python -m usr_ref universel-captures captures/ --reserve --poids essai.json
```

## Le format des fichiers

En-tête de 10 entiers de 32 bits (petit-boutiste), puis les images, lignes
jointives, un entier de 32 bits par pixel :

| Mot | Contenu |
|---|---|
| 0 | `0x43525355` (« USRC ») |
| 1 | version, 1 |
| 2, 3 | largeur, hauteur de la découpe (384, 216) |
| 4, 5 | échelle de rendu en x, en y (3, 3) |
| 6 | format DXGI des pixels : 24, `R10G10B10A2_UNORM` (R dans les bits 0 à 9) |
| 7 | images prévues (48) |
| 8, 9 | position de la découpe dans l'image du jeu, multiple de l'échelle |

Une séquence interrompue (Xenia fermé en pleine capture) garde ses images
complètes. La lecture (`usr_ref/capture_jeu.py`) les compte d'après la
taille du fichier.

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié :

- **le format et la décimation**, sur un jeu simulé
  (`tests/test_capture_jeu.py`) :
  - l'identité « phase décimée = image décalée » ;
  - l'ordre des phases, le niveau 1, une séquence interrompue ;
  - la réserve jamais apprise ;
  - trois défauts remis volontairement, tous attrapés : lignes et
    colonnes inversées, canaux inversés, jitter de signe opposé ;
- **le code de Xenia** (correctif 6) :
  - compilé sous Linux avec MinGW, sur des en-têtes Windows simulés, avec
    erreurs témoins ;
  - compilé par l'intégration continue avec MSVC ;
- **les commandes du workflow** `usr-captures`, rejouées en local sur
  5 captures simulées :
  - mesure de la réserve ;
  - entraînement rapide avec 8 séquences de captures (4 fichiers,
    2 niveaux) ;
  - nouvelle mesure de la réserve.

  Le workflow lui-même ne tournera qu'avec de vraies captures déposées.

Pas vérifié, faute de console :

- le chemin exact du dossier sur la Xbox ;
- le ralentissement à l'échelle 3 ;
- de vrais fichiers de capture, et donc un réseau entraîné sur de vrais
  jeux.
