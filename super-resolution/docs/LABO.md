# USR Labo — l'appli pour essayer USR sur ta Xbox

USR Labo est une application **UWP** pour Xbox Series X|S en **mode
Développeur** (elle tourne aussi sur PC). Elle fait tourner USR en direct
sur le GPU de la console, sur une scène de test, et te laisse **tout
régler à la manette** : résolution, puissance de l'IA, modèle, mémoire,
anti-fantômes, netteté, jitter… avec comparaison côte à côte, loupe et
temps GPU de chaque étape.

![Menu du Labo : page IA, comparaison USR + IA / USR sans IA](labo-menu.png)

*Le menu (page « IA ») et les mesures. À gauche USR avec l'IA, à droite
sans : la grille de lignes fines tient à gauche, s'efface à droite.*

![Loupe x4 à cheval sur la séparation : USR + IA à gauche, bilinéaire à droite](labo-loupe.png)

*Loupe x4 à cheval sur la séparation : USR + IA à gauche, simple
agrandissement bilinéaire à droite.*

> Ces deux captures viennent de la vraie application Windows, exécutée
> **sans carte graphique** sur la machine de développement (Direct3D 12
> traduit en Vulkan, GPU logiciel) : les temps affichés sont ceux d'un
> processeur qui imite un GPU, pas ceux d'une Xbox.

## Ce que le Labo n'est pas

- **Ce n'est pas un filtre pour tes jeux.** Il travaille sur sa propre
  scène de test. En mode Développeur, la console ne lance même pas les jeux
  du commerce, et aucune application ne peut lire l'image d'un autre jeu.
- **Ce n'est pas DLSS 5.** DLSS 5 (NVIDIA, septembre 2026) est un modèle
  génératif qui repeint l'éclairage, intégré jeu par jeu par les studios,
  sur cartes RTX 50. USR est un upscaler à IA du type DLSS 2 à 4 : il
  retrouve les détails d'une image calculée en basse résolution.

## Installer sur la Xbox, pas à pas

Il faut : la Xbox Series X ou S, un **PC Windows 10/11**, et le même
réseau local pour les deux (câble conseillé).

### 1. Passer la console en mode Développeur (une seule fois)

1. Sur le PC, créer un **compte développeur individuel** sur Microsoft
   Partner Center (gratuit pour les particuliers depuis 2025).
2. Sur la Xbox, installer l'application **Xbox Dev Mode** depuis le
   Microsoft Store, la lancer, et saisir le code affiché sur la page
   d'activation indiquée par l'application.
3. La console redémarre en mode Développeur et affiche **Dev Home**. Pour
   rejouer à tes jeux : bouton *Leave developer mode* dans Dev Home (tu
   peux passer d'un mode à l'autre quand tu veux).

### 2. Préparer le PC

1. Installer **Visual Studio 2022 Community** (gratuit) avec les charges
   de travail *Développement de jeux en C++* et *Développement
   d'applications Windows universelles* (cocher les *outils C++ pour la
   plateforme Windows universelle*), et le **SDK Windows 11 (10.0.22621)**
   ou plus récent.
2. Cloner ce dépôt, puis dans une *Developer Command Prompt for VS 2022* :

   ```bat
   cd super-resolution
   cmake -B build-uwp -A x64 -DCMAKE_SYSTEM_NAME=WindowsStore ^
         -DCMAKE_SYSTEM_VERSION=10.0.22621.0
   ```

   Si CMake ne trouve pas `dxc`, ajouter
   `-DUSR_DXC="C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\dxc.exe"`.

### 3. Envoyer l'appli sur la console

1. Ouvrir `build-uwp\usr.sln`, choisir le projet **USRLabo** comme projet
   de démarrage, configuration **Release | x64**.
2. Propriétés du projet → *Débogage* : *Machine distante*, nom = l'adresse
   IP affichée dans Dev Home, authentification *Universal (Unencrypted
   Protocol)*.
3. **F5**. La première fois, Visual Studio demande un code : sur la
   console, Dev Home → *Pair with Visual Studio*.
4. **Important** : dans Dev Home, surligner *USR Labo* dans *Games &
   apps*, bouton **Affichage** de la manette → *View details* → *App
   type* : **Game**. En type « App », Windows ne lui laisse qu'environ
   45 % du GPU.

Sans Visual Studio connecté à la console : *Projet → Publier → Créer des
packages d'application* (distribution directe, « sideloading »), puis
installer le paquet `.msix` et ses dépendances depuis le **Device Portal**
de la console (`https://<IP de la Xbox>:11443`, bouton *Add*).

### Sur PC

La même application existe en version Windows classique :

```bat
cmake -B build -A x64
cmake --build build --config Release
build\Release\usr_labo.exe --largeur 1920 --hauteur 1080
```

## Les commandes

| Manette | Clavier (PC) | Action |
|---|---|---|
| Croix / stick gauche | Flèches | choisir un réglage, le changer (maintenir = accélère) |
| LB / RB | Maj+Tab / Tab | page précédente / suivante |
| A | Entrée | valider (actions, préréglages) |
| B | Échap | fermer le menu |
| Menu (≡) | F1 | afficher / masquer le menu |
| Affichage (⧉) | F2 | afficher / masquer les mesures |
| X | X | effacer l'historique |
| Y | Y | échanger gauche et droite |
| LT / RT | Q / E | déplacer la séparation |
| Stick droit | I J K L | déplacer la loupe |
| Clic stick droit | Z | loupe : coupée, x2, x4, x8 |

Menu fermé, la croix change directement les vues : ↑↓ la moitié gauche,
←→ la moitié droite.

## Tous les réglages

| Page | Réglage | Ce qu'il fait |
|---|---|---|
| Image | Mode d'agrandissement | Natif 1,0x · Qualité 1,5x · Équilibré 1,7x · Performance 2,0x · Ultra 3,0x · Personnalisé |
| | Rapport personnalisé | de 1,0x à 4,0x |
| | Netteté | accentuation finale, 0 à 100 % |
| | Jitter | le décalage sous-pixel ; coupé, la super-résolution disparaît |
| | Phases de jitter | Auto (8 × rapport²) ou 4 à 128 |
| IA | IA | réseau activé ou règle fixe (TAA classique) |
| | Modèle | Stable · Équilibré · Détail |
| | **Puissance de l'IA** | 0 à 300 % : 0 = sans IA, 100 % = tel qu'entraîné, au-delà = décisions amplifiées |
| Accumulation | Mémoire | 1 à 64 images accumulées |
| | Anti-fantômes | tolérance de l'historique (0,25 à 8) |
| | Finesse du noyau | 25 à 400 % |
| | Effacer l'historique | repartir de zéro |
| Comparaison | Moitié gauche / droite | USR + IA, USR sans IA, Bilinéaire, Vérité terrain, Entrée brute, diagnostics (alpha, bêta, confiance, désocclusion), Mouvement |
| | Séparation | position de la ligne |
| | Loupe | coupée, x2, x4, x8 |
| Scène | Caméra, Objets, Vitesse, Pause | pour rendre la tâche facile ou difficile |
| | Vérité terrain | 1 à 16 échantillons par pixel |
| Préréglages | | Par défaut · Qualité maximale · Performance maximale · **IA à fond (300 %)** · Sans IA · Sans jitter · Comparer IA / sans IA · Voir ce que décide l'IA |

Les vues de diagnostic montrent ce que décide le réseau : *alpha* (clair =
il fait confiance à l'image courante, sombre = à l'historique), *bêta* (part
d'historique gardée sans recadrage), *confiance* (mémoire accumulée),
*désocclusion* (zones découvertes).

## Ce qui a été vérifié

- Les shaders du Labo (scène, vérité terrain, agrandissements,
  composition, texte) donnent la même image que leur version Python
  (`tests/test_labo.py`).
- Le cœur de l'appli (menu, réglages, préréglages, texte, animation de la
  scène) passe ses tests en C++ strict (`labo/tests/test_labo_core.cpp`).
- **L'application Windows elle-même** : compilée pour Windows, exécutée
  sur Direct3D 12 (Wine + vkd3d-proton, GPU logiciel), sa sortie USR est
  identique à la référence Python sur 60 images (écart > 60 dB,
  `labo/tests/capture_wine.sh` + `tests/test_labo_bout_en_bout.py`).

Pas encore vérifié : la version **UWP** n'a été ni compilée (il faut le SDK
Windows) ni lancée sur une vraie Xbox, et les performances sur console
restent à mesurer. Si quelque chose coince à la compilation ou au
déploiement, c'est là qu'il faudra regarder en premier.
