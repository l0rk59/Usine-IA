# Usine-IA

**Fabrique de produits digitaux générés par IA, conçue pour tourner sur un téléphone Android via Termux.**

Vous donnez un sujet. Une équipe de sept agents construit le plan, rédige le
contenu, **le fait relire par un autre modèle**, corrige, met en page un PDF et
un EPUB, dessine la couverture, écrit la page de vente et emballe le tout dans
une archive prête à mettre en ligne.

```bash
usine                 # menu interactif — l'entrée recommandée sur mobile
usine ebook "la prospection pour freelances débutants" --marketing --zip
usine web             # tableau de bord 3D en temps réel
```

---

## Ce qui rend ce projet utilisable sur un téléphone

| Contrainte Termux | Réponse retenue |
|---|---|
| `pip install` échoue souvent (compilation C) | **Zéro dépendance** : uniquement la bibliothèque standard Python |
| `reportlab` ne compile pas | Moteur **PDF écrit à la main** (polices standard, images JPEG, sommaire) |
| Pas de `Pillow` | Couvertures **SVG générées localement**, ou images via API sans clé |
| Connexion mobile instable | **Bascule automatique** entre 10 fournisseurs IA + reprise sur cache |
| Quotas gratuits serrés | Compteurs RPM/RPD en base, **cache SQLite** de chaque réponse |
| Coupure réseau totale | Repli sur **IA locale** (ollama / llama.cpp) |
| Pas de CDN hors ligne | Moteur **3D WebGL écrit à la main**, zéro bibliothèque |
| Clavier virtuel pénible | **Menu interactif** : tout se fait avec des numéros |

---

## Installation

```bash
pkg install git python
git clone https://github.com/l0rk59/usine-ia.git
cd usine-ia
bash install.sh
```

L'installeur vérifie Python, crée le `.env`, installe la commande `usine`
et lance une vérification. Aucune bibliothèque tierce n'est téléchargée.

### Le menu, plutôt que des commandes

```bash
usine
```

Sans argument, sur un terminal, l'usine ouvre un menu numéroté : choisir le
type de produit, saisir le sujet, régler le ton et la qualité, lancer. Aucune
option à mémoriser. Les commandes restent disponibles pour l'automatisation.

### Obtenir une clé gratuite (2 minutes)

```bash
usine cles      # affiche les liens et le format de chaque clé
nano .env       # collez-en au moins une
usine docteur   # vérifie que tout répond
```

Une seule clé suffit. Avec deux ou trois, l'usine bascule automatiquement
quand un quota est atteint et ne s'arrête jamais au milieu d'un livre.

| Fournisseur | Gratuit | Carte bancaire | Pourquoi le prendre |
|---|---|---|---|
| [Groq](https://console.groq.com/keys) | oui | non | le plus rapide |
| [Google AI Studio](https://aistudio.google.com/apikey) | oui | non | contexte 1M, idéal pour les longs livres |
| [Cerebras](https://cloud.cerebras.ai/) | oui | non | très rapide, quota généreux |
| [Mistral](https://console.mistral.ai/api-keys/) | oui | non | excellent en français |
| [OpenRouter](https://openrouter.ai/keys) | oui | non | beaucoup de modèles `:free` |
| [GitHub Models](https://github.com/settings/tokens) | oui | non | un simple token GitHub |
| [NVIDIA NIM](https://build.nvidia.com/) | oui | non | crédits renouvelés |
| Pollinations | oui | **aucune inscription** | dernier recours, quota étroit par IP |

> **Sans aucune clé**, l'usine fonctionne quand même via Pollinations — mais son
> quota anonyme est partagé par adresse IP et s'épuise vite. C'est fait pour
> essayer, pas pour produire en volume.

### Ne jamais être bloqué par un quota

Déclarez toutes les clés que vous possédez, y compris plusieurs pour un même
fournisseur :

```
GROQ_API_KEY=cle_une,cle_deux
GEMINI_API_KEY_2=une_autre_cle
```

Le pool répartit la charge sur la clé la moins sollicitée, met au repos celle
qui refuse (2 min sur un 429, 1 h sur un 401 ou un 402) et passe à la suivante
— sans faire tomber le fournisseur entier. Les clés ne sont **jamais** écrites
en base ni dans un journal : seule une empreinte tronquée circule.

> L'usine ne crée **pas** de comptes automatiquement pour contourner un quota :
> c'est interdit par les CGU de tous les fournisseurs et cela fait bannir
> l'appareil. L'addition de sept services gratuits donne davantage de quota,
> sans aucun risque. Voir [docs/SECURITE.md](docs/SECURITE.md).

### Hors ligne, IA locale

```bash
pkg install ollama
ollama serve &
ollama pull qwen2.5:3b     # ~2 Go, correct dès 4 Go de RAM
usine ebook "mon sujet" --hors-ligne
```

L'IA locale est **toujours placée en dernier** dans la chaîne de bascule, comme
demandé : elle prend le relais seulement quand les API distantes sont
indisponibles. Pour l'utiliser en priorité : `USINE_LOCAL_FIRST=1` dans le `.env`.

---

## Les produits fabricables

| Commande | Produit | Contenu livré |
|---|---|---|
| `usine ebook` | Ebook complet | PDF, EPUB, HTML, Markdown, TXT, couverture |
| `usine prompts` | Pack de prompts | PDF, CSV (import Notion), JSON, HTML |
| `usine formation` | Mini-formation | Manuel PDF, cahier d'exercices, séquence e-mail |
| `usine outils` | Boîte à outils | Checklists imprimables, modèles, tableaux CSV |
| `usine modeles` | **Modèles Notion / tableur** | Bases liées, CSV prêts à importer, vues |
| `usine impression` | **Cahier imprimable** | Plannings et fiches à remplir, A4 **et** Lettre US |
| `usine social` | Pack de publications | Calendrier CSV, posts, visuels optionnels |
| `usine idees` | Étude de niche | 12 idées chiffrées : prix, difficulté, concurrence |
| `usine complet` | **Offre complète** | Ebook + 2 bonus + kit de vente + archive ZIP |

Les deux types marqués en gras sont, d'après les classements 2026 des places de
marché, les produits digitaux les plus vendus après l'ebook.

### Exemples

```bash
# Trouver quoi vendre
usine idees "le jardinage urbain" -n 15

# Un ebook long, ton pédagogue, avec kit de vente et archive
usine ebook "cultiver sur un balcon" -T long -t pedagogue --marketing --zip

# 80 prompts pour community managers, fiche Etsy
usine prompts "la gestion de réseaux sociaux" -n 80 --marketing --plateforme etsy

# Une offre complète, sans rien télécharger
usine complet "la méditation pour parents débordés" --hors-ligne

# 30 posts LinkedIn avec 10 visuels générés
usine social "le freelancing" -r linkedin -n 30 --visuels 10
```

### Options communes

```
-a, --audience   à qui s'adresse le produit
-t, --ton        expert | amical | pro | punchy | pedagogue
-T, --taille     mini (6 ch.) | court (8) | standard (12) | long (18)
-q, --qualite    rapide (0 relecture) | standard (1) | exigeant (2)
    --auteur     nom affiché comme auteur
    --marketing  générer aussi le kit de vente
    --plateforme gumroad | etsy | payhip | site
    --zip        produire l'archive livrable
    --hors-ligne ne rien télécharger
    --sans-image ne pas générer d'images
```

### Réglages : ne rien retaper

```bash
usine reglages                                      # tout voir
usine reglages --definir auteur="Votre Nom" qualite=exigeant marque="Atelier"
```

Auteur, marque, contact, ton, volume, qualité, plateforme, thème du tableau de
bord : enregistrés une fois dans `atelier/reglages.json` et repris par toutes
les commandes. Une option passée en ligne de commande reste prioritaire.

---

## L'équipe d'agents

Sept rôles, et surtout un mécanisme : **écrire, faire relire par un autre
modèle, corriger.**

| Agent | Rôle |
|---|---|
| `architecte` | conçoit le plan qui tient la promesse commerciale |
| `redacteur` | écrit le contenu |
| `editeur` | note sur 10 et cite les passages fautifs |
| `reviseur` | applique les corrections, sans rien casser d'autre |
| `styliste` | retire les tics d'écriture des IA |
| `marketeur` | écrit la page de vente |
| `controleur` | valide, ou refuse, la mise en vente |

Le relecteur n'est **jamais** le fournisseur qui a écrit le texte : un modèle
qui se relit lui-même confirme ses propres erreurs. La boucle est bornée à
deux passes, au-delà le gain s'épuise. Chaque produit relu reçoit un
`rapport-qualite.json` avec la note avant et après, section par section.

Les personnalités sont modifiables sans toucher au code :

```bash
usine prompts-systeme --exporter    # écrit atelier/prompts/agents.json
```

Détails : [docs/AGENTS.md](docs/AGENTS.md).

---

## Tableau de bord 3D

```bash
usine web
termux-open-url http://localhost:8777
```

Une scène WebGL **écrite à la main** — pas de three.js, pas de CDN, donc elle
fonctionne hors connexion sur le téléphone :

- le **socle** est l'atelier ;
- les **orbes en orbite** sont les dix fournisseurs ; celui qui répond s'allume
  en vert ;
- la **colonne centrale** est le produit : une dalle bleue par section
  terminée, des dalles fantômes pour ce qui reste ;
- les **particules dorées** sont les jetons qui remontent du fournisseur vers
  le produit.

Le direct passe par des Server-Sent Events : une seule connexion, pas de
sondage. Les pastilles d'agents s'allument, le compteur s'anime, le journal
défile. La caméra suit la hauteur de la pile et recule automatiquement en
portrait. Si le pilote WebGL du téléphone refuse, la page bascule sur un
message clair et **tout le reste continue de fonctionner**.

Le serveur écoute sur `127.0.0.1`. Ouvert au réseau local
(`usine web --hote 0.0.0.0`), un **jeton d'accès est généré automatiquement**
et devient obligatoire.

---

## Comment ça marche

```
   sujet
     │
     ▼
┌──────────────────────────────────────────────┐
│ Routeur IA      quotas · cache · bascule     │
│ groq → cerebras → gemini → mistral → nvidia  │
│   → github → openrouter → pollinations       │
│   → ollama → llama.cpp        (local en      │
│                                dernier)      │
└──────────────────────────────────────────────┘
     │
     ▼
  plan JSON ──► rédaction chapitre par chapitre
     │
     ▼
┌──────────────────────────────────────────────┐
│ Modèle de document unique (blocs Markdown)   │
└──────────────────────────────────────────────┘
     │
     ├──► PDF    (moteur maison, sommaire, images)
     ├──► EPUB 3 (+ toc.ncx pour les vieilles liseuses)
     ├──► HTML   (responsive, thème clair/sombre, imprimable)
     ├──► CSV / JSON / Markdown / TXT
     ├──► couverture (API sans clé, ou SVG local)
     └──► kit de vente + archive ZIP
```

Trois mécanismes rendent la production fiable sur un forfait mobile :

1. **Cache systématique.** Chaque réponse est stockée par empreinte du prompt.
   Relancer une génération interrompue ne reconsomme aucun quota.
2. **Dégradation progressive.** Un chapitre qui échoue n'arrête pas le livre :
   il est remplacé par son plan détaillé, et l'échec est journalisé.
3. **Quotas comptés localement.** RPM et RPD sont suivis en base, le routeur
   attend ou bascule avant que le fournisseur ne réponde 429.

---

## Structure

```
usine/
  core/        fournisseurs, routeur IA, pool de clés, prompts, réglages,
               sécurité, bus d'événements, HTTP, images, SQLite
  agents/      les sept rôles et la boucle critique → révision
  render/      moteur PDF, EPUB, HTML, modèle de document, métriques polices
  pipelines/   ebook, prompts, formation, outils, modèles, imprimables,
               social, idées
  marketing/   fiche produit, page de vente, séquence de lancement
  packaging/   notice, licence, archive ZIP
  web/         serveur SSE + tableau de bord 3D (statique/scene.js, app.js)
  menu.py      menu interactif Termux
  cli.py       interface en ligne de commande
tests/         78 tests + test de fumée, aucun appel réseau
install.sh     installation Termux
```

Sorties dans `atelier/produits/<identifiant>/` (modifiable via `USINE_HOME`,
par exemple `/sdcard/Usine-IA` pour écrire dans la mémoire du téléphone).

---

## Tests

```bash
python3 -m unittest discover -s tests -t .   # 78 tests
python3 tests/fumee.py                       # les 8 chaînes via la vraie CLI
```

Couvre notamment : validité de la table xref du PDF, conformité de l'archive
EPUB, bonne formation du XML, échappement HTML, isolation des chemins du
serveur, **rotation effective des clés sur un 429**, non-fuite des secrets dans
les erreurs et les événements, authentification du tableau de bord, diffusion
temps réel par SSE, évitement du fournisseur pour la relecture, refus d'une
révision tronquée, et le fait que le kit de vente ne parte pas chez l'acheteur.

La géométrie 3D est vérifiée séparément : les matrices de rotation, de caméra
et la matrice normale inverse-transposée sont contrôlées numériquement, et le
tableau de bord est rendu dans un vrai Chromium.

---

## Ce que l'usine ne fait pas

- **Elle ne contourne aucun quota.** Pas de création de comptes automatisée,
  pas de contournement de restriction de fournisseur. La rotation multi-clés et
  l'addition de sept services gratuits donnent le même résultat sans risquer
  le bannissement.

- **Elle ne publie pas à votre place.** Aucune intégration Gumroad ou Etsy :
  vous téléversez l'archive vous-même.
- **Elle ne relit pas pour vous.** Le contenu est généré par IA : relisez et
  corrigez avant de vendre. La licence livrée le mentionne explicitement.
- **Elle n'invente pas votre expertise.** Les meilleurs produits sortent d'un
  sujet que vous connaissez ; l'usine accélère la mise en forme, pas le savoir.
- **Elle ne garantit aucun revenu.** Les prix proposés sont des repères, pas
  des prévisions.

## Licence

MIT — voir `LICENSE`.
