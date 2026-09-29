# DLAA et génération d'images

Deux usages de USR Universel au-delà de l'agrandissement. Tous deux sont
livrés dans Xenia (correctif 5, voir [XENIA.md](XENIA.md)), désactivés
par défaut :

- la **sortie native** (DLAA) : USR à la taille de l'image du jeu,
  anticrénelage seul ;
- la **génération d'images** : une image fabriquée entre deux images du
  jeu.

Toutes les mesures viennent du scénario « jeu émulé » de
[UNIVERSEL.md](UNIVERSEL.md) : scènes synthétiques jamais vues à
l'entraînement, image finale 384×216, 8 premières images ignorées. Ce ne
sont **pas** des mesures sur de vrais jeux Xbox 360.

## Sortie native (DLAA)

USR reçoit l'image du jeu et rend une image **de la même taille**. FSR 1
agrandit ensuite jusqu'à l'écran. La vérité terrain est la scène rendue
avec 16 échantillons par pixel ; l'image brute du jeu n'en a qu'un, elle
est donc crénelée.

`python -m usr_ref universel-dlaa`, réseau livré :

| Scène | Méthode | Niveau | PSNR (dB) | SSIM | Scintillement |
|---|---|---|---|---|---|
| mobile | image brute | – | 32,89 | 0,977 | 0,0042 |
| mobile | USR, règles | 1 | 32,03 | 0,969 | 0,0070 |
| mobile | USR, IA | 1 | 32,99 | 0,978 | 0,0042 |
| mobile | USR, IA | 2 | 33,80 | 0,977 | 0,0060 |
| mobile | USR, IA | 2, textures fines | **33,89** | **0,979** | 0,0053 |
| fixe | image brute | – | 33,08 | 0,977 | 0,0002 |
| fixe | USR, IA | 1 | 33,10 | 0,977 | 0,0003 |
| fixe | USR, IA | 2 | 34,73 | 0,983 | 0,0019 |
| fixe | USR, IA | 2, textures fines | **34,81** | **0,984** | 0,0019 |

Ce qu'il faut en retenir :

- **Sans jitter (niveau 1), USR n'apporte rien à taille égale**, +0,1 dB.
  C'est attendu : sans décalage, deux images successives d'une scène
  immobile portent les mêmes échantillons, il n'y a rien à accumuler. Les
  règles seules font même moins bien que l'image brute. Xenia ne propose
  donc le DLAA qu'avec son conseil : au niveau 2.
- **Au niveau 2, le gain est réel mais modeste** : +1,0 dB en mouvement,
  +1,7 dB à l'arrêt.
- **Le scintillement augmente**, contrairement à ce qu'on attend d'un
  anticrénelage temporel : 0,0053 contre 0,0042 en mouvement. Le jitter
  lui-même se voit un peu à travers l'accumulation.
- **Le réseau n'a jamais vu le rapport 1** : il est entraîné sur les
  rapports 2 et 3. Un entraînement qui l'inclut reste à faire, et à
  mesurer.

## Génération d'images

À chaque nouvelle image du jeu, USR vient d'estimer le flot : pour chaque
pixel, où il était dans l'image précédente. La génération fabrique
l'image du **milieu** entre la sortie précédente et la courante. Le code
est dans `usr_ref/interpolation.py` (référence), `usr_u_interp_ecart.hlsl`
et `usr_u_interp.hlsl` (GPU), et dans l'appel `usr::InterpolateUniversal`.

### Deux hypothèses par pixel

- **Suivre le flot** : chercher le point à mi-chemin dans les deux
  images. Le flot est relu à la position estimée dans l'image courante.
  Sans cette seconde lecture, le bord d'un objet rapide prend le
  mouvement du fond qu'il recouvre.
- **Rester sur place** : un fondu. C'est ce qui sauve un néon qui
  clignote ou un écran dont le contenu change : rien n'y « bouge », au
  sens du flot.

Elles sont départagées par l'accord des deux images recalées, moyenné sur
3×3 pour qu'un pixel isolé ne décide pas seul. Si aucune n'accorde les
deux images (désocclusion), c'est l'image courante recalée seule qui est
prise. Un mélange y montrerait deux objets fantômes superposés.

### Le défaut mesuré : les motifs périodiques

La première version, sans ce qui suit, s'effondrait sur l'écran animé
d'une scène : **17,9 dB contre 29,7 dB pour un simple fondu**. L'écran
montre une sinusoïde qui défile, et le flot y accroche un décalage d'une
période entière : jusqu'à 16 pixels là où le vrai mouvement est de
0,7.

Le piège : les deux images recalées **s'accordent** alors parfaitement
sur une réponse fausse. Le test d'accord ne peut pas le voir, et la
« confiance » du flot non plus : elle mesure la même chose.

Ce sont deux témoins portés par le flot lui-même qui le trahissent :

- son écart à ses **voisins** ;
- son écart au **flot de l'image précédente**, lu là où le point était.
  Un mouvement réel varie peu d'une image à l'autre, alors qu'un alias
  saute.

Au-delà de 2 pixels de rendu, l'hypothèse « suivre le flot » perd son
poids, et devient nulle à 4 pixels. Sur cet écran, le résultat remonte
de 17,9 à 26,3 dB. Le fondu reste meilleur à cet endroit : c'est la
limite actuelle.

### Mesures

`python -m usr_ref universel-generation` : le jeu produit les images
*t* = pas × *f*, et l'image générée au milieu est jugée contre la vérité
à cet instant. Au **pas 1**, ce sont les scènes du banc (0,7 pixel de
rendu par image). Au **pas 3**, elles vont trois fois plus vite : c'est
là qu'un fondu dédouble les objets. USR tourne ici en règles de base : le
réseau ne change pas le flot, qui fait l'interpolation.

PSNR (dB), plus haut = mieux. « Répétition » est ce que montre un jeu à
30 images/s sans génération : l'image précédente, encore.

| Scène | Pas | Répétition | Fondu | **USR** | USR − fondu, objets | USR − fondu, écrans animés |
|---|---|---|---|---|---|---|
| réaliste 101 | 1 | 27,44 | 28,07 | **28,19** | +0,75 | +0,34 |
| réaliste 202 | 1 | 27,59 | **28,39** | 27,94 | +0,32 | −3,13 |
| géométrique 101 | 1 | 23,31 | **24,14** | 23,67 | +0,97 | – |
| réaliste 101 | 3 | 24,01 | 26,00 | **26,16** | +1,71 | −2,38 |
| réaliste 202 | 3 | 24,01 | 26,04 | **26,29** | +1,73 | −3,22 |
| géométrique 101 | 3 | 21,44 | 22,57 | **23,29** | +0,64 | – |

Ce qu'il faut en retenir :

- **Face à l'absence de génération**, le gain est net partout :
  +0,35 à +2,3 dB.
- **Face à un simple fondu**, c'est plus partagé :
  - en mouvement rapide, USR gagne sur toutes les scènes, et nettement
    sur les objets qui bougent (jusqu'à +1,7 dB) ;
  - en mouvement lent, le fondu fait aussi bien, voire mieux : les deux
    images diffèrent si peu qu'un mélange est déjà presque juste (38 dB,
    mesuré entre vraies images sur la scène réaliste 202).
- **Le point faible** reste les motifs répétitifs qui défilent : −2 à
  −3 dB face au fondu sur les écrans animés.
- **Le PSNR avantage le fondu** : il pardonne le flou et punit un contour
  un peu décalé, alors que l'œil voit surtout les doubles contours du
  fondu. Aucune mesure perceptive n'est faite ici. Le verdict visuel
  reste à porter à l'écran, et le Labo ne montre pas encore la génération
  d'images.

### Dans Xenia

À chaque nouvelle image du jeu :

1. l'image générée est présentée ;
2. l'image réelle suit, à la synchronisation verticale suivante
   (`Present(1)`).

Sur un écran à 60 Hz, un jeu à 30 images/s devient 60 images à l'écran.

- **Latence** : l'image du milieu a besoin de la suivante, ce qui coûte
  une demi-image de latence. C'est le prix de toute génération d'images
  ; rien ici ne la compense (pas d'équivalent de NVIDIA Reflex).
- **Seuil de 25 ms** : la génération ne se déclenche que si le jeu laisse
  au moins 25 ms entre deux images. Plus rapide, la paire ne tiendrait
  pas dans deux balayages de 16,7 ms, et la file de présentation pleine
  ralentirait l'émulation elle-même.
- **Deux sorties** : USR garde la sortie précédente dans une seconde
  texture, échangée à chaque image.

### Ce qui est vérifié

- **Référence Python contre shaders** : identiques au bit près sous
  llvmpipe (`tests/test_parite_gpu.py`, `PariteGpuGeneration`). Le test
  exige 70 dB.
  - Quatre défauts remis volontairement ont tous été attrapés : seuil du
    flot, repli sur flot douteux, moyenne 3×3, instant du recalage.
  - Le repli mal branché ne coûtait que 50 à 57 dB. Un seuil à 55 dB
    l'aurait laissé passer.
- **Bibliothèque C++ sous Wine + vkd3d-proton** : les images générées
  sont à 73 dB de la référence (`tests/test_universel_bout_en_bout.py`).
  Cette limite vient du stockage sur 16 bits ; aucune image n'est générée
  sans flot, après une coupure.
- **Code de Xenia** :
  - compilé sous Linux avec MinGW, sur des en-têtes Windows simulés, avec
    erreurs témoins ;
  - compilé par l'intégration continue avec MSVC : l'exécutable doit
    contenir le message d'échec de la génération, preuve que ce code y
    est.
- **Pas vérifié** : la cadence réelle à l'écran, sur la console.
