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

## Empêcher Android de tuer la fabrication

Un ebook long prend 10 à 20 minutes. Android peut suspendre Termux pendant ce
temps s'il est en arrière-plan.

```bash
termux-wake-lock       # avant de lancer une longue fabrication
usine ebook "..." -T long
termux-wake-unlock     # après
```

Ajoutez aussi Termux à la liste des applications non optimisées :
*Paramètres → Applications → Termux → Batterie → Sans restriction*.

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
```bash
usine docteur      # montre quelle clé manque et quel quota est atteint
```
Les quotas journaliers se remettent à zéro toutes les 24 h. Ajoutez une
deuxième clé chez un autre fournisseur pour ne plus jamais attendre.

**La fabrication semble figée**
Un appel IA peut prendre 60 à 150 secondes sur un modèle chargé. Le journal
affiche chaque chapitre terminé. En cas de doute : `Ctrl+C`, puis relancez —
le cache reprendra où vous en étiez.

**`no space left on device`**
Les produits pèsent quelques mégaoctets, mais le cache grossit :
```bash
usine cache --vider
```
