# Usine-IA

**Fabrique de produits digitaux générés par IA, conçue pour tourner sur un téléphone Android via Termux.**

Vous donnez un sujet. Une équipe de sept agents construit le plan, rédige le
contenu, **le fait relire par un autre modèle**, corrige, met en page un PDF et
un EPUB, dessine la couverture, écrit la page de vente et emballe le tout dans
une archive prête à mettre en ligne.

```bash
usine                 # menu interactif — l'entrée recommandée sur mobile
usine ebook "la prospection pour freelances débutants" --marketing --zip
usine usine demarrer  # production en boucle, sous budget
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
| `usine idees` | Étude de niche | 12 idées appuyées sur des **mesures de marché réelles** |
| `usine marche` | Signaux de marché | demande, concurrence, tendance — 4 sources sans clé |
| `usine bilan` | Mémoire de l'usine | ce que vos productions révèlent sur vos réglages |
| `usine complet` | **Offre complète** | Ebook + 2 bonus + kit de vente + archive ZIP |
| `usine file` | File de production | les niches en attente de fabrication |
| `usine usine` | **Usine continue** | produit en boucle, sous budget, jusqu'à l'arrêt |
| `usine ab` | Tests A/B | variantes de titres et de couvertures, verdict honnête |

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

## Mesurer, plutôt que déclarer

### Le contrôle local — sans appel IA

Beaucoup de défauts se **comptent** : tics d'écriture, répétitions en
n-grammes, phrases toutes de la même longueur, chiffres précis sans source,
promesses de résultat, volume, structure. L'usine les mesure en Python —
instantané, gratuit en quota, et reproductible au centième.

Le relecteur IA n'intervient qu'**ensuite**, sur ce qui demande un jugement.
Conséquence : un défaut mesurable coûte un appel (la correction) au lieu de
deux (la détection puis la correction).

```
   rédaction
      │
   contrôle local  ──►  0 appel IA, consignes déjà précises
      │
   correction      ──►  1 appel
      │
   relecture IA    ──►  pertinence, progression, promesse tenue
```

Étalonnage : un texte rédigé avec exemples et rythme varié obtient **10/10** ;
une sortie générique de modèle obtient **0 à 2/10**. Détails et seuils dans
[docs/QUALITE.md](docs/QUALITE.md).

### Les signaux de marché — sources réelles

```bash
usine marche "productivity"
```

Quatre sources publiques sans inscription : **Hacker News** (volume de
discussions), **Wikipedia pageviews** (intérêt dans le temps — l'API Google
Trends est fermée), **Stack Exchange** (questions non résolues), **Open
Library** (concurrence éditoriale). Les mesures alimentent `usine idees`, qui
raisonne dessus au lieu d'imaginer un marché.

> Ces sources sont anglophones. Une requête en français y renvoie peu de
> résultats — l'usine le détecte et le signale, au lieu de conclure « niche
> trop étroite ». Voir [docs/MARCHE.md](docs/MARCHE.md).

### La mémoire de production

```bash
usine bilan
```

Chaque produit laisse une trace mesurée : note, défauts restants, durée,
appels consommés, réglages utilisés. Au bout de quelques produits, l'usine
répond à des questions qu'aucun modèle ne peut trancher — quel ton donne vos
meilleures notes, si la relecture vaut son coût chez vous, quel défaut revient
assez souvent pour mériter une règle. Chaque conseil cite le nombre de
productions sur lequel il s'appuie.

## Tester des titres et des couvertures

```bash
usine ab creer --produit ebook-xxx --sur titre -n 5
usine ab observer 2 --vues 910 --actions 58
usine ab verdict 1
```

**Le chiffre à connaître : à 5 % de conversion, détecter un écart de 20 %
demande environ 7 600 vues par variante.** Un vendeur qui fait 300 vues par
mois ne l'atteindra jamais. Ce n'est pas une limite de l'outil, c'est la
quantité d'information nécessaire pour distinguer un effet du hasard.

La conséquence est assumée : **l'usine refuse de désigner un gagnant** tant
que les données ne le permettent pas.

```
[A] Facturer mieux en travaillant moins    140 vues   5 ventes   3.6%    9%
[B] Le systeme en 7 etapes du freelance    155 vues   9 ventes   5.8%   47%
[C] Pourquoi votre agenda se vide          130 vues   4 ventes   3.1%    6%

INDECIS — aucune variante ne se detache (47 % pour la mieux placee).
```

B fait presque le double de C, et il n'y a rien à conclure. Un outil qui
annoncerait « B gagne » ici vous ferait refaire une couverture pour rien.

La valeur immédiate est ailleurs :

- **des variantes réellement différentes** — chaque titre est écrit sur un
  angle imposé (bénéfice, méthode, problème, contraste, audience, délai), puis
  l'outil **vérifie** la distinction : au-delà de 55 % de vocabulaire commun,
  il le dit et régénère. Comparer cinq reformulations du même titre ne révèle
  jamais rien ;
- **un diagnostic local** de chaque titre, sans appel IA : chiffre, délai,
  audience nommée, mots creux, longueur. Des faits, pas une prédiction de CTR ;
- **une planche de comparaison** HTML qui met les variantes côte à côte.

Statistiques : modèle beta-binomial, tirage **conjoint** sur toutes les
variantes (ce qui évite le piège des comparaisons multiples), résultat graîné
donc reproductible, et vérifié dans les tests contre une formule exacte
indépendante.

> **Filigrane :** au palier anonyme, Pollinations marque chaque image
> « @pollinations.ai » — `nologo` n'a aucun effet sans jeton, vérifié octet pour
> octet. Les couvertures en ligne servent à choisir une direction ; pour une
> couverture livrable, `--sans-image` produit des SVG locaux sans filigrane.
> Détails : [docs/AB-TESTING.md](docs/AB-TESTING.md).

## L'usine continue

```bash
usine file --ajouter "la prospection" "la gestion du temps"
usine file --ajouter "50 prompts pour community managers" --type prompts --priorite 1
usine usine demarrer --budget appels_jour=250 produits_jour=3
usine usine statut          # depuis un autre terminal
usine usine arreter
```

**La file vit en base, pas en mémoire.** C'est la décision qui compte sur
Android : le système tue les processus en arrière-plan sans préavis. Relancer
reprend exactement où l'usine s'était arrêtée, et une niche laissée « en
cours » par une coupure revient en attente au démarrage suivant.

**Le budget s'applique à trois niveaux.** Avant chaque produit — l'usine
refuse d'en démarrer un qu'elle ne pourra pas finir. Avant chaque appel — une
réponse servie par le cache n'est jamais refusée, elle ne coûte rien. Et
pendant un produit : si un plafond tombe au dixième chapitre, **le livre sort
quand même**, chapitres rédigés conservés, suivants réduits à leur plan, PDF et
EPUB générés. Perdre neuf chapitres parce que le dixième a dépassé n'aurait
aucun sens.

`Ctrl+C` termine le produit en cours puis s'arrête ; un second coupe net. Un
verrou PID empêche deux usines simultanées, et un verrou laissé par un
processus tué est détecté comme orphelin puis nettoyé.

En `--auto`, quand la file se vide, l'usine explore de nouvelles niches à
partir des sujets qui ont donné vos meilleures notes. Sans historique, elle le
dit et s'arrête plutôt que d'inventer.

Détails et recette Termux (`termux-wake-lock`, `nohup`) :
[docs/USINE-CONTINUE.md](docs/USINE-CONTINUE.md).

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
  core/        fournisseurs, routeur IA, pool de clés, contrôle qualité
               déterministe, signaux de marché, mémoire de production,
               file de production, budget, A/B testing (beta-binomial),
               diagnostic de titre, prompts, réglages, sécurité,
               bus d'événements, HTTP, SQLite
  agents/      les sept rôles et la boucle critique → révision
  render/      moteur PDF, EPUB, HTML, modèle de document, métriques polices
  pipelines/   ebook, prompts, formation, outils, modèles, imprimables,
               social, idées, variantes
  marketing/   fiche produit, page de vente, séquence de lancement
  packaging/   notice, licence, archive ZIP
  web/         serveur SSE + tableau de bord 3D (statique/scene.js, app.js)
  production.py  usine continue : file, budget, verrou, arrêt propre
  menu.py      menu interactif Termux
  cli.py       interface en ligne de commande
tests/         157 tests + test de fumée, aucun appel réseau
install.sh     installation Termux
```

Sorties dans `atelier/produits/<identifiant>/` (modifiable via `USINE_HOME`,
par exemple `/sdcard/Usine-IA` pour écrire dans la mémoire du téléphone).

---

## Tests

```bash
python3 -m unittest discover -s tests -t .   # 157 tests
python3 tests/fumee.py                       # les 8 chaînes via la vraie CLI
```

Couvre notamment : validité de la table xref du PDF, conformité de l'archive
EPUB, bonne formation du XML, échappement HTML, isolation des chemins du
serveur, **rotation effective des clés sur un 429**, non-fuite des secrets dans
les erreurs et les événements, authentification du tableau de bord, diffusion
temps réel par SSE, évitement du fournisseur pour la relecture, refus d'une
révision tronquée, et le fait que le kit de vente ne parte pas chez l'acheteur.

L'A/B testing est testé sur ce qui compte : que la formule exacte et le tirage
aléatoire **concordent** sur six jeux de données, que cinq variantes identiques
ne produisent jamais de gagnant, et surtout que 8/100 contre 12/100 — 50 %
d'écart apparent — soit correctement refusé.

L'usine continue est testée sur ce qui peut réellement mal tourner : reprise
après un arrêt brutal, verrou orphelin d'un processus tué, refus de démarrer un
produit infinissable, et surtout **le produit exporté malgré un budget épuisé
en cours de route** — la promesse qui compte.

Le contrôle qualité est testé sur sa **reproductibilité** (deux exécutions
donnent la même note), sa calibration (bon texte 10/10, texte générique 2/10)
et ses garde-fous. Les sources de marché sont testées avec des réponses figées,
dont le cas « Freelance (2023 film) » qui ne doit jamais être retenu.

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
