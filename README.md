# Usine-IA

**Fabrique de produits digitaux générés par IA, conçue pour tourner sur un téléphone Android via Termux.**

Vous donnez un sujet. L'usine construit le plan, rédige le contenu, met en page un
PDF et un EPUB, dessine la couverture, écrit la page de vente et emballe le tout
dans une archive prête à mettre en ligne.

```
usine ebook "la prospection pour freelances débutants" --marketing --zip
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
| `usine social` | Pack de publications | Calendrier CSV, posts, visuels optionnels |
| `usine idees` | Étude de niche | 12 idées chiffrées : prix, difficulté, concurrence |
| `usine complet` | **Offre complète** | Ebook + 2 bonus + kit de vente + archive ZIP |

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
    --auteur     nom affiché comme auteur
    --marketing  générer aussi le kit de vente
    --plateforme gumroad | etsy | payhip | site
    --zip        produire l'archive livrable
    --hors-ligne ne rien télécharger
    --sans-image ne pas générer d'images
```

---

## Tableau de bord

```bash
usine web
termux-open-url http://localhost:8777
```

Interface pensée pour un écran de téléphone : lancement d'une fabrication,
journal en direct, état des quotas, accès aux fichiers produits. Le serveur
écoute sur `127.0.0.1` uniquement — rien n'est exposé au réseau sans
`--hote 0.0.0.0` explicite.

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
  core/        config (fournisseurs), routeur IA, HTTP, images, SQLite
  render/      moteur PDF, EPUB, HTML, modèle de document, métriques polices
  pipelines/   ebook, prompts, formation, boîte à outils, social, idées
  marketing/   fiche produit, page de vente, séquence de lancement
  packaging/   notice, licence, archive ZIP
  web/         tableau de bord (http.server)
  cli.py       interface en ligne de commande
tests/         38 tests, aucun appel réseau
install.sh     installation Termux
```

Sorties dans `atelier/produits/<identifiant>/` (modifiable via `USINE_HOME`,
par exemple `/sdcard/Usine-IA` pour écrire dans la mémoire du téléphone).

---

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Couvre : validité de la table xref du PDF, conformité de l'archive EPUB,
bonne formation du XML, échappement HTML, isolation des chemins du serveur web,
efficacité du cache, priorité de l'IA locale, et une fabrication d'ebook de
bout en bout avec un simulateur.

---

## Ce que l'usine ne fait pas

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
