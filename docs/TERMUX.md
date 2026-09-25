# Guide Termux pas à pas

Tout ce qui suit se tape dans Termux, sur le téléphone. Aucun ordinateur n'est
nécessaire.

## 1. Installer Termux

**N'installez pas Termux depuis le Play Store** : cette version est abandonnée
depuis des années et ses paquets sont cassés. Prenez celle de
[F-Droid](https://f-droid.org/packages/com.termux/) ou des
[releases GitHub](https://github.com/termux/termux-app/releases).

## 2. Préparer le système

```bash
pkg update && pkg upgrade -y
pkg install -y git python
termux-setup-storage        # autorise l'accès à la mémoire du téléphone
```

`termux-setup-storage` fait apparaître une demande de permission Android.
Acceptez-la : c'est ce qui permettra d'enregistrer vos produits dans
`/sdcard` et de les ouvrir depuis votre gestionnaire de fichiers.

## 3. Installer l'usine

```bash
git clone https://github.com/l0rk59/usine-ia.git
cd usine-ia
bash install.sh
```

## 4. Ajouter une clé gratuite

```bash
usine cles          # affiche les liens
nano .env
```

Dans `nano` : collez votre clé après le `=`, puis `Ctrl+O`, `Entrée`, `Ctrl+X`.

```bash
usine docteur       # doit afficher au moins un « v » sur une ligne « cle API »
```

## 5. Fabriquer

```bash
usine idees "votre niche"
usine ebook "votre sujet" --marketing --zip
```

## 6. Récupérer les fichiers

Le plus simple est le menu : `usine` → **Mes produits** → choisir le produit →
*Ouvrir sur le téléphone* ou *Partager l'archive*. À la main :

```bash
# Ouvrir un PDF avec l'application du téléphone
termux-open ~/usine-ia/atelier/produits/<dossier>/<fichier>.pdf

# Ou copier toute la production dans la mémoire partagée
mkdir -p ~/storage/shared/Usine-IA
cp -r ~/usine-ia/atelier/produits/* ~/storage/shared/Usine-IA/
```

Pour écrire directement dans `/sdcard` dès le départ, ajoutez au `.env` :

```
USINE_HOME=/sdcard/Usine-IA
```

> Note : la base SQLite fonctionne sur `/sdcard`, mais Android y interdit le
> mode WAL. L'usine le détecte et bascule silencieusement en mode journal
> classique — c'est un peu plus lent, sans autre conséquence.

---

## Le téléphone comme machine

Installez `termux-api` — le paquet **et** l'application :

```bash
pkg install termux-api
```

L'application **Termux:API** s'installe à part, depuis
[F-Droid](https://f-droid.org/packages/com.termux.api/), comme Termux. Le
paquet seul ne suffit pas : les commandes attendraient une application qui
n'existe pas. L'usine s'en protège par un délai d'attente, mais vous n'auriez
ni notification ni garde batterie.

Ce que l'usine en fait, sans rien demander :

| Quand | Ce qui se passe |
|---|---|
| Pendant une fabrication | **Verrou de veille** pris, relâché à la fin : Android n'endort plus Termux en plein chapitre |
| Quand un produit sort | **Notification** Android — la taper ouvre le PDF |
| Batterie sous 20 % | L'usine continue **s'arrête** entre deux produits, la file intacte, et le dit dans une notification prioritaire |
| Téléphone en charge | Rien ne s'arrête : le niveau monte |
| Écran **Mes produits** du menu | *Ouvrir sur le téléphone* lance le PDF dans votre lecteur ; *Partager l'archive* l'envoie vers Drive, un courriel ou Telegram |

Trois réglages commandent tout cela :

```bash
usine reglages --definir notifications=non        # silence complet
usine reglages --definir batterie_minimum=35      # arrêt plus tôt
usine reglages --definir batterie_minimum=0       # jamais d'arrêt batterie
usine reglages --definir verrou_veille=non        # laisser Android décider
```

`usine docteur` affiche l'état de `termux-api` et le niveau de batterie.

Ajoutez aussi Termux à la liste des applications non optimisées :
*Paramètres → Applications → Termux → Batterie → Sans restriction*.

**Sans `termux-api`**, rien de tout cela n'existe et rien ne casse : l'usine
produit exactement comme avant. C'est la contrainte fondatrice du projet —
zéro dépendance, rien d'obligatoire.

Si la fabrication est quand même interrompue, relancez exactement la même
commande : le cache restitue tout ce qui avait déjà été généré, sans
reconsommer un seul appel d'API.

---

## Utiliser une IA locale

```bash
pkg install ollama
ollama serve &
ollama pull qwen2.5:3b       # ~2 Go
usine docteur                # doit détecter ollama
usine ebook "mon sujet" --hors-ligne
```

`--hors-ligne` garantit qu'**aucune connexion ne sort du téléphone** : ni
invite vers une API, ni image, ni sondage du marché, pas même pour vérifier si
le réseau répond. Seuls restent permis la boucle locale et l'adresse de votre
serveur d'IA locale — y compris un ordinateur du réseau de la maison, si
`OLLAMA_BASE_URL` y pointe. Jusqu'au 25/09/2026, l'option ne tenait pas cette
promesse pour le texte : il partait chez le premier fournisseur distant qui
avait une clé.

Choix du modèle selon la RAM du téléphone :

| RAM | Modèle conseillé | Qualité |
|---|---|---|
| 3–4 Go | `qwen2.5:1.5b` | dépannage |
| 6 Go | `qwen2.5:3b` | correcte |
| 8 Go et plus | `qwen2.5:7b` ou `llama3.1:8b` | bonne |

L'IA locale est lente sur téléphone (comptez 3 à 10 fois plus de temps qu'une
API) et reste moins bonne sur les plans structurés en JSON. Utilisez-la comme
filet de sécurité, pas comme moteur principal — c'est exactement la place que
lui donne la chaîne de bascule.

### Ce que « docteur » vérifie, et ce qu'il disait à tort

`usine docteur` demande à chaque serveur local **ce qu'il sert**, pas
seulement s'il répond. Une ligne par serveur :

| Ce qui s'affiche | Ce que cela veut dire |
|---|---|
| `v ollama local qwen2.5:3b` | prêt, avec le modèle configuré |
| `v ollama local qwen2.5:0.5b (« qwen2.5:3b » absent : …)` | prêt, mais c'est ce modèle-là qui écrira |
| `! ollama local repond, mais ne sert aucun modele` | `ollama pull` a été oublié |
| `- ollama local ne repond pas` | le serveur n'est pas lancé |

Trois défauts, corrigés le 25/09/2026, que la fiche du téléphone rendait
visibles (ollama installé, aucune clé) :

- **Sans aucune clé, le verdict était « prêt, l'usine peut produire ».** Le
  palier anonyme de Pollinations est toujours disponible, et il comptait
  comme un fournisseur prêt. Au même moment, le menu et le tableau de bord
  disaient « quota très limité ». Le verdict est désormais **« essai »** :
  l'usine démarre, sur un quota que Pollinations ne publie pas. Et les
  verdicts « bloqué » et « local », qui ne pouvaient plus s'afficher, le
  peuvent de nouveau.
- **Un ollama sans aucun modèle passait pour une IA locale prête.** La
  vérification du modèle existait, mais elle avait perdu son appelant le
  12/09/2026 ; elle se taisait d'ailleurs sur ce cas précis, et prenait
  `qwen2.5:0.5b` pour `qwen2.5:3b` parce qu'elle ne comparait que le début du
  nom. Le routeur, qui attend un serveur local pour reprendre, s'y fiait
  aussi.
- **La liste des fournisseurs cochait en vert un ollama jamais installé.**
  Un fournisseur local est toujours « disponible » : c'est une adresse, pas
  une preuve.

`usine specs` ne sonde aucun serveur. Avec ollama installé et sans clé, sa
fiche classe la clé en « recommandé » et non plus en « bloquant » — sans
prétendre savoir si un modèle est tiré.

---

## Problèmes courants

**`usine : command not found`**
La commande a été installée dans `$PREFIX/bin`. Si elle reste introuvable :
```bash
cd ~/usine-ia && PYTHONPATH=. python3 -m usine.cli docteur
```

**`certificate verify failed`**
```bash
pkg install ca-certificates openssl
```

**`Tous les fournisseurs ont échoué`**
L'usine teste elle-même la connexion avant de conseiller : si le réseau est
coupé, elle vous dit de rebrancher le wifi plutôt que de créer une clé. Sinon :
```bash
usine docteur      # montre quelle clé manque et quel quota est atteint
```
Les quotas journaliers se remettent à zéro toutes les 24 h. Ajoutez une
deuxième clé chez un autre fournisseur pour ne plus jamais attendre.

Dans les deux cas, **relancez la même commande** : les réponses déjà obtenues
sont en cache, la fabrication reprend où elle s'était arrêtée sans repayer ce
qui est fait. `usine liste` marque **inachevé** les produits coupés en route.

**La fabrication semble figée**
Un appel IA peut prendre 60 à 150 secondes sur un modèle chargé. Le journal
affiche chaque chapitre terminé. En cas de doute : `Ctrl+C`, puis relancez —
le cache reprendra où vous en étiez.

**Mettre l'usine à jour**
```bash
usine maj
```
Elle ne touche ni à `atelier/` ni à `.env` : vos produits, votre historique et
votre clé restent en place. Avec `git` installé, elle tire la dernière version
du dépôt ; sans lui, elle télécharge une archive — ce qui ne marche que sur un
dépôt **public**. Si le vôtre est privé :
```bash
pkg install git
```
et clonez-le une fois ; `usine maj` passera par git ensuite.

**Savoir ce qui manque à cet appareil**
```bash
usine specs
```
Écrit `SPECS-APPAREIL.md` : ce qui manque, la commande qui le pose, et ce que
son absence coûte. Aucune clé API n'y figure — c'est fait pour être poussé sur
le dépôt.

**`no space left on device`**
Le message vous dit combien il reste et que le travail déjà fait n'est pas
perdu. Les produits pèsent quelques mégaoctets, mais le cache grossit :
```bash
usine cache --vider
```

**`Ecriture refusée` dans un dossier de `/sdcard`**
Android demande l'autorisation de stockage :
```bash
termux-setup-storage
```

**`La base de l'atelier est illisible`**
Une carte SD fatiguée ou un processus tué en pleine écriture. **Vos produits
sont intacts** : ce sont des fichiers dans `produits/`, pas des lignes de la
base. Si vous avez une archive :
```bash
usine sauvegarde --restaurer archive.zip --oui
```
Sinon, mettez la base de côté — l'usine en recrée une vide au démarrage
suivant. Vous perdez l'historique, les ventes, les bibles de série et le cache,
rien d'autre. `usine docteur` continue de fonctionner dans cet état : c'est lui
qui nomme le fichier et le remède.

Le détail de ces trois pannes, et ce qui a été mesuré : [PANNES.md](PANNES.md).
