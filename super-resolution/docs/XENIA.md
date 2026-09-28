# USR dans Xenia — les jeux Xbox 360 émulés, sur ta Xbox Series X

**Notre propre version de Xenia** (l'émulateur Xbox 360, dans sa version
UWP pour Xbox en mode Développeur) avec **USR Universel** intégré.

- L'image du jeu, souvent en 1280x720, est agrandie par USR jusqu'à la
  résolution de ton écran.
- Au **niveau 2**, Xenia décale lui-même le rendu 3D d'une fraction de
  pixel à chaque image, ce qui permet une vraie super-résolution.
- **Tout se règle en jouant** : Vue + RB ouvre une surcouche. Le jeu
  continue, reste visible, et ne reçoit plus la manette tant qu'elle est
  ouverte.

> **Légalité.** Xenia et ces correctifs sont libres. Les jeux, eux, ne
> sont pas fournis : n'utilise que des copies de jeux que tu possèdes.
> Comme toute la famille Xenia, ce projet n'est affilié ni à Microsoft, ni
> aux développeurs de Xenia.

## Ce qu'il y a dans `xenia/`

On ne copie pas Xenia (des centaines de mégaoctets) : on livre
**4 correctifs** et un script qui les applique sur une version précise de
[xenia-canary-uwp](https://github.com/amitamit99/xenia-canary-uwp)
(commit `3e236f0`). Ce fork de Xenia Canary se compile avec CMake et
Visual Studio, et sait produire le paquet pour la Xbox.

| Fichier | Rôle |
|---|---|
| `patches/0001-…` | USR comme dépendance tierce (`third_party/usr`), liée au rendu D3D12 et à l'appli UWP |
| `patches/0002-…` | l'effet de sortie « USR » dans le présentateur Direct3D 12 (repli sur FSR si besoin) |
| `patches/0003-…` | niveau 2 : jitter sous-pixel injecté dans la scène 3D, et biais de mip-map |
| `patches/0004-…` | réglages en direct à la manette : surcouche, menu pause, fenêtre d'affichage (PC), variables `usr_*` |
| `appliquer.ps1` / `appliquer.sh` | clone Xenia, copie USR dans `third_party/usr`, applique les correctifs |
| `third_party_usr/CMakeLists.txt` | construit la bibliothèque et ses shaders (dxc du SDK Windows) |
| `tests/usr_menu_test.cc` | tests du menu de réglages (sans Xenia ni GPU) |

## Sans PC : tout depuis ton téléphone

Pas besoin de PC. GitHub compile l'appli pour toi (runners Windows,
gratuits pour un dépôt public), et tu l'installes sur la Xbox depuis le
navigateur de ton téléphone.

### A. Récupérer l'appli compilée

1. Sur ton téléphone, ouvre le dépôt sur github.com → onglet
   **Actions** → workflow **super-resolution**.
2. Ouvre le dernier passage réussi (coche verte) de la branche voulue.
   Pour en lancer un toi-même : **Run workflow**.
3. En bas, section *Artifacts* : télécharge **xenia-usr-xbox** (un
   `.zip`). La construction de Xenia prend environ une heure.
4. Dézippe-le (l'appli *Fichiers* du téléphone sait le faire). Il
   contient :
   - le paquet `….msixbundle` (ou `.appxbundle`) ;
   - le dossier `Dependencies\x64` (bibliothèques VCLibs) ;
   - `Xenia-USR.cer`, le certificat de test qui signe le paquet.

### B. Préparer la Xbox (une seule fois)

1. Sur la console, installe l'appli **Xbox Dev Mode** depuis le Store.
2. Lance-la : elle affiche un code. Sur ton téléphone, crée ton compte
   développeur **gratuit** sur Partner Center, puis saisis ce code sur la
   page d'activation que l'appli indique.
3. La console redémarre en mode Développeur et affiche **Dev Home**. Note
   l'adresse IP affichée.
4. Dans Dev Home, active le **Device Portal** et choisis un identifiant et
   un mot de passe (*Remote Access Settings*).

### C. Installer depuis le téléphone

1. Téléphone et Xbox sur le **même réseau** (Wi-Fi de la box).
2. Dans le navigateur du téléphone : `https://<IP de la Xbox>:11443`.
   Accepte l'avertissement de sécurité, puis connecte-toi.
3. **Add** → choisis le `.msixbundle` → **Next** → ajoute les fichiers de
   `Dependencies\x64` (et `Xenia-USR.cer` si la page propose un
   certificat) → **Start**.
4. Dans Dev Home, surligne **Xenia USR** → bouton **Affichage** de la
   manette → *View details* → *App type* : **Game**.

**Mise à jour** : chaque construction signe avec un nouveau certificat de
test. Si l'installation d'une nouvelle version est refusée, désinstalle
l'ancienne (Device Portal ou Dev Home), puis recommence. Pour éviter ça,
on peut enregistrer un certificat fixe dans les secrets du dépôt
(`USR_UWP_PFX_BASE64`, `USR_UWP_PFX_PASSWORD`).

L'appli s'appelle **Xenia USR** et a sa propre identité : elle s'installe
à côté d'un Xenia UWP d'origine sans le remplacer.

Pour les jeux, l'activation de USR et les commandes : sections 3 et 4
plus bas.

## 1. Construire (sur un PC Windows)

Il faut :

- **Windows 10 ou 11**, Git pour Windows, **Python 3** 64 bits (dans le
  `PATH`), **CMake 3.20** ou plus ;
- **Visual Studio 2022** (Community suffit), avec :
  - les charges *Développement Desktop en C++* et *Développement
    d'applications Windows universelles* ;
  - les *outils C++ pour la plateforme Windows universelle*, à cocher dans
    la seconde ;
- le **SDK Windows 11** (10.0.22000 ou plus récent), qui fournit le `dxc`
  utilisé pour les shaders de USR ;
- le **SDK Vulkan**, demandé par la construction de Xenia elle-même
  (voir le `docs/building.md` de Xenia).

Dans PowerShell :

```powershell
git clone https://github.com/l0rk59/Usine-IA.git
cd Usine-IA\super-resolution
powershell -ExecutionPolicy Bypass -File xenia\appliquer.ps1 C:\xenia-usr
```

Le script clone Xenia au bon commit avec ses sous-modules (quelques
minutes), copie USR et sa licence dans `third_party\usr`, et applique les
4 correctifs sur une branche `usr`.

Ensuite, dans une *Developer PowerShell for VS 2022* :

```powershell
cd C:\xenia-usr
cmake --preset vs
```

Le préréglage `vs` génère `build\xenia.sln`. Le projet UWP va chercher les
bibliothèques dans `build\obj\Windows\Release` : garde bien ce dossier
`build`.

### Le certificat (une seule fois)

Une appli UWP doit être signée. Le projet attend un certificat
`XeniaDevCert.pfx` que le dépôt ne fournit pas.

1. Ouvre `build\xenia.sln` dans Visual Studio.
2. Dans le projet **xenia-canary-uwp**, double-clique sur
   `Package.appxmanifest`, onglet **Empaquetage** (*Packaging*).
3. **Choisir le certificat… → Créer…** : un certificat de test à ton nom.

   Visual Studio met à jour l'éditeur (*Publisher*) du manifeste et le
   projet.

### Compiler et créer le paquet

1. Configuration **Release | x64**.
2. Clic droit sur **xenia-canary-uwp** → *Définir comme projet de
   démarrage*, puis **Générer**.

   Les bibliothèques de Xenia et `usr` sont compilées avant : c'est long
   la première fois.
3. Clic droit sur **xenia-canary-uwp** → **Publier → Créer des packages
   d'application…** → *Chargement indépendant* (sideloading), x64,
   Release.

Tu obtiens un dossier `AppPackages\…` qui contient :

- le paquet `.msixbundle` (ou `.appxbundle`) ;
- un dossier `Dependencies\x64` : bibliothèques d'exécution VCLibs.

Pour essayer sur le PC d'abord : le projet **xenia-app** est la version
Windows classique, avec les mêmes réglages.

## 2. Installer sur la Xbox

1. Passe la console en **mode Développeur**, une seule fois. La démarche
   est la même que pour USR Labo, décrite dans [LABO.md](LABO.md) (étape
   1).
2. Sur le PC, ouvre le **Device Portal** de la console :
   `https://<adresse IP de la Xbox>:11443`. L'adresse est affichée dans
   Dev Home.
3. **Add** :
   - choisis le paquet `.msixbundle` ;
   - **Next**, ajoute les fichiers de `Dependencies\x64` ;
   - **Start**.
4. **Indispensable** :
   1. dans Dev Home, surligne l'appli dans *Games & apps* ;
   2. bouton **Affichage** de la manette → *View details* ;
   3. *App type* : **Game**.

   En type « App », Windows ne lui laisse qu'une petite part du GPU.
5. Mets tes jeux à disposition comme pour tout Xenia UWP (clé USB ou
   dossier choisi dans l'appli) : voir le README du fork.

## 3. Activer USR

**Dans un jeu** : maintiens **Vue** et appuie sur **Menu** pour ouvrir le
menu pause de Xenia. Section **USR (Usine Super Resolution)** :

- **Activer USR** ;
- le bouton **Réglages en direct** ouvre la surcouche décrite plus bas.

Le choix est enregistré.

**Par le fichier de configuration** (`xenia-canary.config.toml`, section
`[Display]`) :

```toml
postprocess_scaling_and_sharpening = "usr"
postprocess_antialiasing = ""        # FXAA coupé : conseillé avec USR
```

Sur PC, la fenêtre des réglages d'affichage de Xenia propose aussi
« USR » à côté de FSR et CAS, avec tous ses réglages.

## 4. Régler en jouant : Vue + RB

Maintiens **Vue** et appuie sur **RB** : un petit panneau s'ouvre en haut
à gauche. Le jeu continue et reste visible, mais **ne reçoit plus la
manette** tant que le panneau est ouvert : tes appuis ne font rien dans le
jeu.

| Manette | Action |
|---|---|
| Croix ↑ ↓ | choisir une ligne |
| Croix ← → | changer la valeur |
| A | basculer (lignes oui / non), ou « oublier l'historique » |
| Y | oublier l'historique (après une coupure, si une traînée reste) |
| X | carte de diagnostic, au lieu de l'image |
| **LT maintenue** | **comparer** : FSR 1 tant que tu la tiens, USR quand tu la relâches |
| B, ou Vue + RB | fermer (les réglages sont enregistrés) |

Les lignes du panneau :

| Ligne | Valeurs | Ce qu'elle fait |
|---|---|---|
| Méthode | USR · FSR 1 · CAS · Bilinéaire | l'agrandissement final de Xenia |
| Niveau | 1 (image telle quelle) · **2 (jitter injecté)** | voir plus bas |
| Textures fines | **oui** · non | niveau 2 : biais de mip-map, textures deux fois plus fines |
| IA | **oui** · non (règles de base) | le petit réseau de neurones |
| Force de l'IA | 0 à 4, **1** | 1 = tel qu'entraîné ; 0 = règles seules ; au-delà = décisions amplifiées |
| Historique | 1 à 64 images, **10** | plus = plus fin à l'arrêt, mais oublie plus lentement |
| Anti-fantômes | 0,05 à 4, **0,30** | petit = oublie vite (moins de traînées, moins de détail) |
| Netteté | 0 à 100 %, **25 %** | accentuation finale (RCAS) |
| Diagnostic | image · carte | rouge = réactivité (pixel refait à neuf), vert = gain, bleu = confiance (mémoire accumulée) |
| Oublier l'historique | A | repartir de zéro |

En bas, le panneau affiche la taille de sortie de USR : la preuve qu'il
tourne. S'il ne s'affiche pas, Xenia est retombé sur FSR (voir *Si ça ne
marche pas*).

### Niveau 1 ou niveau 2 ?

- **Niveau 2 (par défaut)** : à chaque image, Xenia décale d'une fraction
  de pixel les dessins de la scène 3D. USR reçoit ce décalage exact et
  accumule de vrais détails.

  Un dessin est décalé s'il teste la profondeur et si sa zone de rendu a
  les proportions de l'image et de 40 à 105 % de sa taille. Les jeux
  « sous-HD » rendent souvent leur scène plus petite que l'image finale,
  d'où cette marge.

  Les pré-passes de profondeur seule sont décalées comme la couleur,
  sinon les pixels dessinés en test d'égalité disparaîtraient. Ne bougent
  pas :
  - les dessins sans profondeur (HUD, textes, menus, post-traitements) ;
  - les cartes d'ombre ;
  - les petites vues (rétroviseurs, cartes).
- **Niveau 1** : Xenia ne touche pas au jeu, USR n'a que l'image. Il se
  comporte alors comme un très bon agrandissement spatial, sans plus
  (voir les mesures).

Le niveau 2 intervient dans le rendu du jeu, et certains jeux peuvent le
supporter mal :

- des effets calculés à l'écran qui tremblent ou se décalent ;
- un HUD dessiné avec test de profondeur qui vibre ;
- un anticrénelage propre au jeu qui floute.

Si tu vois quelque chose de ce genre, passe au **niveau 1** pour ce jeu.
Si les textures fourmillent, coupe **Textures fines**.

## 5. Tous les paramètres (fichier de configuration)

| Variable | Défaut | Plage | Effet |
|---|---|---|---|
| `postprocess_scaling_and_sharpening` | `""` | `usr`, `fsr`, `cas`, `bilinear` | `usr` active USR |
| `usr_jitter` | `true` | | niveau 2 (sinon niveau 1) |
| `usr_lod_bias_enable` | `true` | | textures fines au niveau 2 |
| `usr_lod_bias` (section GPU) | `-1.0` | −2 à 0 | biais de mip-map ; pris en compte au lancement suivant |
| `usr_network` | `true` | | réseau de neurones |
| `usr_network_strength` | `1.0` | 0 à 4 | force de l'IA |
| `usr_history_length` | `10.0` | 1 à 64 | images accumulées au plus |
| `usr_anti_ghosting` | `0.3` | 0,05 à 4 | seuil anti-fantômes |
| `usr_sharpness` | `0.25` | 0 à 1 | netteté finale |

Conseils :

- **Coupe le FXAA** de Xenia (`postprocess_antialiasing = ""`). Il est
  appliqué *avant* USR et lisse précisément les détails sous-pixel que
  l'accumulation exploite.
- `draw_resolution_scale_x` / `_y` rendent le jeu en interne 2 ou 3 fois
  plus grand. C'est la méthode « force brute », très coûteuse en GPU. USR
  vise le même résultat bien moins cher, et les deux se combinent : USR
  agrandit alors une image déjà plus grande.

## 6. Ce qu'il faut en attendre

Mesures de USR Universel sur le scénario « jeu émulé » (détails et
protocole dans [UNIVERSEL.md](UNIVERSEL.md)). Rapport 3, soit un jeu en
720p sur un écran 4K, scène jamais vue à l'entraînement ; PSNR (dB) et
SSIM, plus haut = mieux :

| | Bilinéaire | Spatial (type FSR 1) | USR niveau 1 | **USR niveau 2** |
|---|---|---|---|---|
| caméra mobile | 26,55 / 0,800 | 26,44 / 0,836 | 26,59 / 0,820 | **27,08 / 0,864** |
| caméra fixe | 26,74 / 0,805 | 26,62 / 0,836 | 26,66 / 0,815 | **28,41 / 0,911** |

En clair :

- le **niveau 2** apporte un vrai gain, surtout quand l'image est stable ;
- le **niveau 1** égale un bon agrandissement spatial, sans le dépasser ;
- le scintillement en mouvement est un peu supérieur à celui de FSR 1 ;
- ce sont des mesures sur une scène **synthétique**, pas sur de vrais jeux
  Xbox 360.

## 7. Ce qui est vérifié, et ce qui ne l'est pas

Vérifié sous Linux, sans Windows, par le script
`xenia/tests/verifier_linux.sh`. Il a été exécuté pendant le
développement, et c'est aussi le job `xenia-linux` de l'intégration
continue :

- les 4 correctifs **s'appliquent** sans conflit sur un clone neuf de
  xenia-canary-uwp au commit de référence ;
- le **menu de réglages** passe ses tests (`xenia/tests/usr_menu_test.cc`,
  C++20 strict) : bornes, pas, lignes grisées, bascules, « oublier
  l'historique » ;
- la **cible CMake** `third_party/usr` se construit entièrement : les 12
  shaders par dxc, la bibliothèque en `-Wall -Wextra -Werror`.

Et par `tests/wine/universel_wine.sh` : **la bibliothèque et ses
shaders**, exécutés sous Wine + vkd3d-proton, donnent la même image que la
référence Python (voir [UNIVERSEL.md](UNIVERSEL.md)).

Vérifié à la main pendant le développement : les fichiers de Xenia
modifiés ont été compilés avec MinGW, sur des en-têtes Windows simulés.
Le but était d'éliminer les erreurs de C++ dans le code ajouté. Des
erreurs volontaires injectées dans ce code ont prouvé qu'il était bien
analysé.

Prévu dans l'intégration continue sous Windows, avec MSVC :

- job `xenia-windows` : la **version PC** complète (`xenia-app`), qui
  contient tout le code C++ des correctifs ;
- job `xenia-uwp` : l'**application UWP** pour la Xbox (sans signature du
  paquet).

Ces jobs **n'ont encore jamais tourné**. Les Actions GitHub du dépôt ne
démarrent actuellement aucune machine : tous les workflows, y compris
celui de l'usine, échouent en quelques secondes et sans journal. C'est un
réglage du compte GitHub (facturation ou limite de dépense des Actions),
pas le code.

**Pas encore vérifié** :

- la **compilation par MSVC** (voir ci-dessus). Xenia traite les
  avertissements comme des erreurs : si une erreur apparaît, c'est
  probablement un détail (avertissement, `#include` manquant) dans le code
  des correctifs ;
- le **fonctionnement sur Xbox** ;
- les performances (le Labo mesure le coût de USR Universel sur la
  console) ;
- le comportement du niveau 2 jeu par jeu.

### Si ça ne marche pas

- **La taille de sortie ne s'affiche pas dans le panneau** : USR ne
  tourne pas, et Xenia est passé sur FSR, qui marche toujours. Soit
  l'écran est plus petit que l'image du jeu (USR ne fait qu'agrandir),
  soit USR n'a pas pu démarrer. Le journal de Xenia contient une ligne
  « USR: … » :
  - au démarrage, les tailles, la période du jitter et l'état du réseau ;
  - en cas d'échec, sa raison.
- **Le jeu tremble ou un effet se décale** : niveau 1.
- **Des traînées derrière les objets** : baisse *Anti-fantômes*, ou
  appuie sur Y.
- **Image trop douce** : monte *Netteté* ou *Historique*.
