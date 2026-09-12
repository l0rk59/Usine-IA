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
python3 -m usine      # sans le raccourci dans le PATH
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
| `usine logiciel` | **Outil logiciel** | Code source **vérifié**, CLI, app web ou extension Chrome |
| `usine idees` | Étude de niche | 12 idées appuyées sur des **mesures de marché réelles** |
| `usine marche` | Signaux de marché | demande, concurrence, tendance — 4 sources sans clé |
| `usine veille` | **Ce que les gens disent** | communautés, formulations de problème, leur vocabulaire |
| `usine bilan` | Mémoire de l'usine | ce que vos productions révèlent sur vos réglages |
| `usine doublons` | **Anti-répétition** | les produits qui se recouvrent, avant qu'un acheteur ne le voie |
| `usine ventes` | **Ce qui rapporte** | import Gumroad/Etsy, chiffre d'affaires par niche, prix réels |
| `usine sauvegarde` | Mettre à l'abri | ventes et historique dans une archive — le reste se refabrique |
| `usine complet` | **Offre complète** | Ebook + 2 bonus + kit de vente + archive ZIP |
| `usine file` | File de production | les niches en attente de fabrication |
| `usine usine` | **Usine continue** | produit en boucle, sous budget, jusqu'à l'arrêt |
| `usine ab` | Tests A/B | variantes de titres et de couvertures, verdict honnête |

`modeles` et `impression` sont, d'après les classements 2026 des places de
marché, les produits digitaux les plus vendus après l'ebook. `logiciel` est le
seul dont le livrable peut être **faux plutôt que médiocre** : rien n'en sort
sans avoir été analysé, réparé si besoin, et — pour un outil en ligne de
commande — réellement exécuté.

**Un seul endroit les déclare** : `usine/pipelines/catalogue.py`. La CLI, le
menu, la file de production, le tableau de bord et l'explorateur de niches le
lisent. Avant, la liste était recopiée dans sept fichiers — et deux avaient déjà
divergé : l'explorateur de niches ne connaissait ni `impression` ni `modeles`,
et convertissait silencieusement ces idées en ebooks.

« Vrai type » signifie : une chaîne de fabrication qui lui est propre. C'est la
différence entre neuf types et une énumération de soixante.
Voir [docs/TYPES-PRODUITS.md](docs/TYPES-PRODUITS.md).

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

# Un outil en ligne de commande, vérifié et réellement lancé avant livraison
usine logiciel "le nettoyage de fichiers en double" -c cli

# Une application web autonome, qui marche hors connexion
usine logiciel "le calcul de tarif pour freelances" -c web
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

### Le code généré est vérifié, pas supposé correct

Un ebook maladroit se vend quand même. Un script qui ne démarre pas se fait
rembourser. `usine logiciel` est donc le seul type dont **rien n'est livré sans
avoir été vérifié**.

```
   génération d'un fichier
      │
   analyse statique   ──►  syntaxe + appels système, réseau, eval,
      │                    écritures hors du dossier de travail
   réparation         ──►  l'erreur exacte est renvoyée au modèle
      │
   exécution réelle   ──►  bac à sable, limite de temps — cible « cli »
                           uniquement, et seulement si l'analyse est propre
```

L'exécution n'a lieu que sur du code dont l'arbre syntaxique ne contient rien
de dangereux : ce code vient d'un modèle, pas de vous, et un `os.system` généré
par accident dans un exemple effacerait le téléphone. Six échantillons hostiles
écrits pour l'analyseur — `os.system`, `shutil.rmtree`, `eval`, socket,
`subprocess`, écriture sur chemin absolu — sont tous refusés.

L'outil livré est lancé deux fois avant la mise en carton : `--help`, puis les
tests unitaires générés avec lui. Le rapport complet part avec le produit, dans
`verification.json` : le contrat annoncé à l'acheteur est **contrôlable**, pas
seulement affirmé.

> Catalyst, le dépôt dont cette usine reprend les idées, assemblait le code
> renvoyé par le modèle et le déclarait livrable. Aucune vérification de
> syntaxe, à aucun moment. Voir [docs/LOGICIEL.md](docs/LOGICIEL.md).

### La couverture est composée ici, et son contraste est mesuré

Chaque produit sortait avec une couverture générée par Pollinations. Au palier
anonyme, ce service **appose un filigrane `pollinations.ai` sur chaque image** —
`nologo` n'a aucun effet sans jeton, vérifié image à l'appui. Une couverture
filigranée ne se vend pas : la place de marché la refuse, ou l'acheteur la
prend pour une contrefaçon.

Le plus gênant n'était pas l'erreur mais qu'elle soit **écrite dans le fichier
qui la commettait** : `usine/core/images.py` documentait en tête, en majuscules,
pourquoi ces images ne pouvaient pas servir de couverture — puis appelait
Pollinations par défaut, à chaque produit.

La couverture est désormais **dessinée localement**, sans réseau ni dépendance :
une fonte capitale écrite en polygones, un rasteriseur, cinq mises en page et
huit palettes.

```
couverture.png     1200 × 1800 — Gumroad, Etsy, KDP n'acceptent pas le SVG
couverture.svg     même géométrie, vectorielle, pour retoucher
<produit>.pdf      la couverture occupe la première page, pleine page
```

**Le contraste n'est plus décrété, il est calculé.** L'ancienne version prenait
la couleur du sous-titre dans la palette : sur le fond prune, cela donnait du
rose sur du rose — 1,4:1. L'encre est maintenant retenue par son rapport de
contraste avec **ce qu'il y a vraiment derrière** — le dégradé, plus tout décor
qui traverse la bande de texte. Un test rend chaque couverture deux fois, avec
et sans son texte, et exige 4,5:1 (WCAG AA) sur les 40 combinaisons.

> Pourquoi une fonte dessinée plutôt qu'embarquée, pourquoi pas de JPEG, et ce
> que les tests ont trouvé : [docs/COUVERTURE.md](docs/COUVERTURE.md).

### Les CSV livrés ne s'exécutent pas chez l'acheteur

Un CSV produit par l'usine n'est pas un fichier de travail : les modèles
Notion, le calendrier éditorial et les tableaux de la boîte à outils partent
tels quels chez l'acheteur. Or Excel, LibreOffice et Google Sheets
**interprètent comme une formule** toute cellule commençant par `=`, `+`, `-`
ou `@`.

Deux conséquences, l'une gênante et l'autre grave. Une cellule légitime comme
« -50 % de temps passé » s'affichait `#NAME?` dans un fichier que l'acheteur a
payé. Et le contenu vient d'un modèle nourri de titres Hacker News et de
questions Stack Exchange récupérés sur internet : une cellule
`=HYPERLINK(...)` s'exécute à l'ouverture, sur **sa** machine (CWE-1236).

La parade tient en un caractère, invisible dans les trois tableurs. Vérifié en
faisant traverser une charge hostile à quatre chaînes réelles : **87 cellules
neutralisées, zéro exécutable**. Un test refuse par ailleurs toute écriture
CSV qui ne passerait pas par le filtre.

### Ce qui rapporte, et non plus seulement ce qui note bien

L'usine mesurait la qualité, la durée, les appels consommés. Elle ne savait
**rien de ce qui rapporte** : `usine bilan` pouvait répondre « quel ton donne
vos meilleures notes » et jamais « quelle niche a payé ».

```bash
usine ventes --importer export.csv --sur gumroad   # colonnes reconnues, puis affichées
usine ventes --rattacher                           # le nom en boutique → votre produit
```

L'importeur ne suppose aucun format : il cherche chaque champ par ses noms
possibles et **montre ce qu'il a reconnu** — une correspondance devinée qu'on
n'affiche pas est une erreur qu'on ne verra jamais. Point-virgule, virgule
décimale, dates `jj/mm/aaaa` et statuts en français compris.

Trois règles de prudence, parce qu'un chiffre d'affaires inventé est pire
qu'un chiffre d'affaires absent : **pas de conversion** entre devises, **pas
d'estimation** du net quand l'export ne le donne pas, **pas de doublon** si
vous réimportez le même fichier.

**Le prix cesse d'être inventé.** Le `prix_eur` d'une idée sortait du modèle :
les quatre sources de marché mesurent la demande et la concurrence, aucune ne
mesure un prix. Dès qu'un type compte trois ventes, l'étude de niche retient le
médian réellement encaissé — et écrit d'où il vient.
Détails : [docs/VENTES.md](docs/VENTES.md).

### L'usine se souvient de ce qu'elle a écrit

Le défaut n'apparaît qu'au volume : quatre produits par jour sur des niches
voisines, c'est **trois fois le même livre avec des mots différents**. Ni le
modèle ni le contrôle qualité ne peuvent le voir — chacun ne regarde qu'un
produit à la fois, et chacun le trouve bon.

La seule protection était une comparaison de chaînes : la file refusait le
couple (sujet, type) déjà en attente. « La prospection pour freelances » et
« Prospection freelance » y passaient sans encombre.

Deux mesures, parce que deux choses différentes se répètent :

- **le texte** — signature MinHash sur des groupes de 5 mots : taille fixe,
  insensible à la longueur, robuste au remaniement ;
- **le plan** — la charpente réduite à ses mots porteurs. C'est le cas
  fréquent : deux livres sans une phrase en commun peuvent être le même livre.
  `Chapitre 2 — Trouver vos premiers prospects` et `Étape 2 : trouver ses
  premiers prospects` donnent la même entrée.

```bash
usine doublons          # sort en code 1 s'il trouve : bon pour une tâche planifiée
```

Le produit n'est pas bloqué — comparer avant supposerait de deviner ce que le
modèle va écrire. Le quota est dépensé ; ce qu'on évite, c'est la mise en
vente. Détails : [docs/DOUBLONS.md](docs/DOUBLONS.md).

### Le sur-mesure, pas cinq tons pour tout un catalogue

Cinq tons fermés et quatre volumes imposaient les mêmes réglages à tous les
produits — ce qui est précisément ce qui les fait se ressembler.

```bash
usine ebook "la menuiserie du dimanche" \
     --chapitres 7 --mots 900 \
     -t "comme un vieux menuisier qui explique à son apprenti"
usine ebook "un sujet" -T 15        # 15 sections, volume déduit
```

Les cinq tons restent des **raccourcis** : `-t punchy` vaut sa description,
toute autre valeur passe telle quelle jusqu'à l'invite. Les valeurs absurdes
sont bornées, pas refusées — aucun quota gratuit ne tient neuf cents
chapitres.

Le sur-mesure est accessible depuis les **trois** interfaces : la ligne de
commande, le menu Termux (`autre...` / `sur mesure...`) et le tableau de bord.
Sur un téléphone, une option absente du menu n'existe pas.

#### Un réglage sur mesure doit aussi survivre au retour

Enregistrer un ton sur mesure **par défaut** cassait les deux interfaces
graphiques, chacune à sa manière — parce que l'une et l'autre cherchaient la
valeur enregistrée dans une liste de raccourcis qui, par construction, ne la
contient pas.

| | Symptôme | Cause |
|---|---|---|
| Menu Termux | `ValueError` en ouvrant « Fabriquer un produit » | `tons.index(valeur)` |
| Tableau de bord | le ton devenait `amical`, le volume `mini` | aucune `<option>` ne correspond : le navigateur retombe sur la première |

Le second est le plus grave : **rien ne s'affiche**. Le produit part avec une
voix et une longueur que personne n'a choisies.

Les deux interfaces reproposent maintenant la valeur enregistrée dans le champ
libre, pré-remplie. Le menu des réglages, lui, présente les raccourcis sous
forme de liste au lieu d'un champ de saisie : `qualite` est une liste fermée —
`rapidos` valait silencieusement `standard` partout — tandis que `ton` et
`taille` gardent leur entrée libre.

### L'usine choisit ses niches

```bash
usine file --explorer        # part de ce qui a le mieux rapporté
```

Un remplissage automatique existait : il partait du **dernier** produit
fabriqué — son commentaire disait pourtant « les meilleures notes » —,
explorait sans aucune mesure, et ne vérifiait pas si la piste avait déjà été
traitée.

Trois garde-fous maintenant : la graine vient de ce qui a **rapporté** (le
revenu mesure le marché, la note mesure l'usine) ; l'exploration reçoit les
quatre sources de marché **et** les discussions réelles ; et une piste trop
proche d'un produit déjà fabriqué est écartée **avant** d'entrer en file — la
file ne se dédoublonne que sur elle-même, et `usine doublons` ne rattrapait la
répétition qu'après coup, le quota dépensé.

### Aller voir ce que les gens disent

Les quatre sources de marché mesurent des **volumes** : elles disent si une
niche existe. Elles ne disent pas ce qui y fait mal, ni avec quels mots.

```bash
usine veille "freelance invoicing"
```

> `Leurs mots : freelancers (5), built (3), invoicing (2), tracking (2)`
> `The tool I built after 10 years of chasing late payments`

« chasing late payments » est une promesse produit écrite par quelqu'un qui a
le problème. `usine idees` s'en sert déjà.

**La recherche globale de Reddit ne marche pas** — vérifié : sur « meal
planning for busy parents » elle rend des chatons dans une bouche d'égout et
un séjour en Slovénie. Le chemin qui marche demande d'abord *qui* parle du
sujet, puis lit ce qui s'y dit. Détails et limites :
[docs/VEILLE.md](docs/VEILLE.md).

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

**Les chiffres viennent des ventes, plus de la saisie.** Renseignez la période
pendant laquelle chaque variante était en ligne, et l'usine lui attribue les
ventes réellement encaissées :

```bash
usine ab periode 3 --du 2026-07-01 --au 2026-07-30
usine ab rythme 1
```

Les vues, elles, ne figurent dans aucun export — il faut les relever à l'écran,
et l'usine ne les invente pas. Quand vous ne les avez pas, `usine ab rythme`
compare des **rythmes de vente** : « 7 ventes en 14 jours » contre « 4 en 12 »
n'est pas un problème binomial mais un comptage sur une durée, donc un modèle
gamma-poisson, vérifié lui aussi contre une formule exacte.

> Ce test est **séquentiel** : les variantes n'ont pas été exposées en même
> temps, une semaine de vacances se confond avec l'effet du titre, et aucun
> calcul ne répare cela. L'usine le dit à chaque verdict.

> Les couvertures comparées sont celles de l'atelier local : **ce qui gagne le
> test est ce qui part chez l'acheteur**. Avant, le test comparait des images
> filigranées — quatre propositions dont aucune n'était vendable.
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

### Ce que le navigateur sait faire, et que la console ne peut pas

Cinq outils n'existaient qu'en ligne de commande.

**Tests A/B.** Le manque le plus voyant, et le plus ironique : on compare des
**couvertures**, qui sont des images, et la seule interface avec un écran ne
les montrait pas. La carte fait tout le cycle — créer (les couvertures
s'affichent côte à côte, en vraie taille), reporter vues et actions, dater
chaque variante, lire le verdict qui se met à jour, retenir la gagnante.

**Ce que l'usine a appris.** `usine bilan` est la boucle de rétroaction du
projet : note moyenne, gain réel de la relecture, classement par type, par ton,
par qualité. Il n'était lisible qu'en console, donc invisible depuis le
téléphone. Un réglage n'apparaît qu'à partir de deux productions notées, et la
page le dit — sans cette phrase, un « Par ton » vide se lit comme « le ton ne
change rien ».

**Veille de niche.** La même consultation Reddit, en tâche de fond — `scouter`
s'impose trois secondes entre deux communautés, donc la page interroge
l'avancement au lieu d'attendre. Chaque titre trouvé porte un bouton
**→ sujet** qui l'écrit dans le champ de fabrication et le passe au contrôle
des domaines sensibles. Une plainte lue chez les gens devient un produit sans
recopie.

Les titres et les liens viennent d'un flux que personne ne signe, et cette
page pilote l'usine : seul un lien `https` vers `reddit.com` est transmis au
navigateur — un `javascript:` arrive comme une chaîne vide — et le texte est
échappé à l'affichage. Le serveur ne nettoie pas le titre lui-même : le
nettoyer mentirait sur ce que les gens ont écrit.

**Agir sur un produit.** La carte listait les produits et servait leurs
fichiers, sans savoir rien en faire — alors que c'est le moment où l'on veut
l'archive ZIP ou le kit de vente. Les deux boutons y sont. L'archive est écrite
*à côté* du dossier du produit, donc invisible dans la liste de fichiers : la
réponse porte son lien de téléchargement.

**Diagnostic.** Le bouton « pourquoi ça ne marche pas », là où on le cherche.
Les contrôles vivent dans `core/diagnostic.py` et servent les deux interfaces —
deux jeux finiraient par ne plus dire la même chose. Il gagne au passage
l'espace disque libre.

**Mesurer un marché.** À côté de la veille, dans la même carte : la veille dit
ce que les gens *disent*, le marché dit combien ils sont. La page affiche les
sources qui **n'ont pas répondu** — un silence de source n'est pas un marché
absent.

**Empreintes manquantes.** La carte des doublons affichait « aucun
recouvrement notable » après avoir comparé **zéro** produit — les empreintes
sont posées à la fabrication, et un catalogue plus ancien n'en a aucune. Elle
compte désormais ce qu'elle n'a pas pu comparer, et propose le bouton qui
répare.

**Sauvegarde.** Créer l'archive, la **télécharger** — c'est la partie qui
manquait : sur un téléphone, une archive restée dans `atelier/sauvegardes/`
ne protège de rien, et la ligne de commande ne sait pas l'en sortir — et la
**restaurer**, en deux temps. Un panneau dit d'abord ce que contient
l'archive ; le bouton rouge ne s'active qu'une fois la case cochée. Côté
serveur, `confirme` doit valoir exactement `true` : `"oui"` et `1`, vrais en
JavaScript, sont refusés. La restauration est par ailleurs refusée tant qu'une
fabrication, une veille ou l'usine continue tourne.

**Téléverser une archive** couvre le cas de la réinstallation : téléphone
effacé, sauvegarde sur l'ordinateur. Le corps est écrit par morceaux sur le
disque, jamais gardé en mémoire ; le plafond est vérifié sur le
`Content-Length` avant de lire quoi que ce soit ; le nom venu du navigateur
est réduit à un nom de fichier (`../../etc/passwd` → `passwd.zip`) ; un nom
déjà pris reçoit un rang au lieu d'écraser ; et ce qui n'est pas une archive
lisible ne reste pas sur le disque.

Une archive peut par ailleurs **annoncer bien plus qu'elle ne pèse** : six
cents kilo-octets compressés déclarant une base de six cents mégaoctets
suffiraient à faire tomber le téléphone, puisque `restaurer` lit la base d'un
seul bloc en mémoire. Les tailles décompressées annoncées sont donc bornées
dans `sauvegarde` — pas dans la page, car la ligne de commande acceptait déjà
n'importe quel chemin.

Ce dernier point a révélé un défaut que seule une interface à plusieurs
threads pouvait montrer : `store.close()` ne ferme que la connexion du thread
qui appelle, et la restauration *déplace* le fichier de base. Les autres
threads gardaient une poignée sur un fichier qui n'était plus la base de
personne — ils lisaient l'atelier d'avant, et ce qu'ils y écrivaient était
perdu sans erreur. Chaque connexion retient maintenant sa génération et se
refait quand la base a changé.

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
     ├──► couverture PNG + SVG (composée localement, sans filigrane)
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
               déterministe, vérification du code généré (AST + bac à sable),
               empreintes anti-doublon (MinHash), ventes réelles,
               signaux de marché, mémoire de production,
               file de production, budget, A/B testing (beta-binomial),
               diagnostic de titre, prompts, réglages, sécurité,
               bus d'événements, HTTP, SQLite
  agents/      les sept rôles et la boucle critique → révision
  render/      moteur PDF, EPUB, HTML, modèle de document, métriques polices,
               assemblage commun des livrables, fonte capitale en polygones,
               rasteriseur + encodeur PNG, composition de couverture
  pipelines/   catalogue (source unique des types), ebook, prompts, formation,
               outils, modèles, imprimables, social, logiciel, idées, variantes
  marketing/   fiche produit, page de vente, séquence de lancement
  packaging/   notice, licence, archive ZIP
  web/         serveur SSE + tableau de bord 3D (statique/scene.js, app.js)
  production.py  usine continue : file, budget, verrou, arrêt propre
  menu.py      menu interactif Termux
  cli.py       interface en ligne de commande
tests/         512 tests + test de fumée, aucun appel réseau
               un atelier temporaire par module (tests/atelier.py)
install.sh     installation Termux
```

Sorties dans `atelier/produits/<identifiant>/` (modifiable via `USINE_HOME`,
par exemple `/sdcard/Usine-IA` pour écrire dans la mémoire du téléphone).

---

## Tests

```bash
python3 -m unittest discover -s tests -t .   # 512 tests
python3 scripts/dependances.py               # zéro dépendance
python3 tests/fumee.py                       # les 9 chaînes via la vraie CLI
```

Couvre notamment : validité de la table xref du PDF, conformité de l'archive
EPUB, bonne formation du XML, échappement HTML, isolation des chemins du
serveur, **rotation effective des clés sur un 429**, non-fuite des secrets dans
les erreurs et les événements, authentification du tableau de bord, diffusion
temps réel par SSE, évitement du fournisseur pour la relecture, refus d'une
révision tronquée, et le fait que le kit de vente ne parte pas chez l'acheteur.

Un test exécute **chaque type de produit déclaré**, de bout en bout, et vérifie
que chaque format annoncé est réellement produit. Il a été ajouté après qu'une
erreur d'import ait cassé une chaîne sans qu'aucun des 157 tests d'alors ne s'en
aperçoive.

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

La couverture est testée en la **regardant** : chaque combinaison palette ×
mise en page est rendue deux fois, avec et sans son texte, et le contraste est
mesuré sur les pixels obtenus. Le test exige 4,5:1 et refuse qu'un titre
déborde de la page. Il a trouvé, à l'écriture, huit combinaisons illisibles,
un sous-titre imprimé sous le bord de la page, et cinq lettres mal dessinées.

La vérification du code généré est testée sur du code **hostile**, pas sur des
cas d'école : six échantillons (`os.system`, `shutil.rmtree`, `eval`, socket,
`subprocess`, écriture sur chemin absolu) doivent tous être refusés à
l'exécution, du code propre doit passer, et une boucle infinie doit être arrêtée
à la limite de temps. Les trois cibles logicielles sont produites de bout en
bout, et l'application web générée a été **ouverte dans un vrai Chromium**.

La géométrie 3D est vérifiée séparément : les matrices de rotation, de caméra
et la matrice normale inverse-transposée sont contrôlées numériquement, et le
tableau de bord est rendu dans un vrai Chromium.

Une **intégration continue** lance la suite et le test de fumée sur Python 3.9,
3.11 et 3.13, sur une installation nue — la contrainte fondatrice du projet
étant qu'il s'installe sur un Termux sans `pip`. Un script (`scripts/dependances.py`)
lit les imports dans l'arbre syntaxique et échoue à la première dépendance
étrangère ; un autre contrôle vérifie qu'aucune clé API n'est apparue dans le
dépôt. Deux tests gardent l'annonce elle-même : que toute la source se lise
en Python 3.9, et que la version plancher soit bien celle que la CI teste.

L'**accessibilité du tableau de bord** a été auditée dans un vrai navigateur,
ce qui a trouvé deux manques : deux listes déroulantes sans étiquette (donc
sans nom pour un lecteur d'écran) et l'absence de région principale. Les zones
qui changent pendant qu'on regarde — journal, états de veille, de sauvegarde,
de test — sont maintenant annonçables (`role="status"`, `role="log"`), et la
scène 3D est masquée aux lecteurs d'écran parce qu'elle **répète** ce que le
journal dit déjà en toutes lettres. Deux tests lisent la page servie et
refusent un champ sans étiquette.

Les routes du tableau de bord sont testées par le réseau, sur un vrai serveur
HTTP. Ce qui compte le plus y est ce qu'elles **refusent** : un lien
`javascript:` venu du flux de veille, un hôte qui imite Reddit, une sortie du
dossier des sauvegardes vers `usine.db`, un fichier qui n'est pas une archive.
Chaque garde a été retiré une fois pour vérifier que le test tombe.

Le **menu est piloté par son entrée standard**, comme un doigt sur un écran de
téléphone, et l'on regarde quelle commande il lance vraiment. Un sous-menu est
une table entre un numéro tapé et une branche de code, que rien ne vérifie à
l'exécution : insérer une entrée décale toutes les suivantes, et le menu lance
tranquillement la mauvaise commande. Chaque sous-menu est en outre promené sur
**toutes ses entrées avec des saisies absurdes**, atelier rempli : aucune ne
doit lever, et aucune ne doit refuser de rendre la main.

Chaque module de test travaille dans **son propre atelier**. Ce n'était pas le
cas : chacun posait bien son `USINE_HOME`, mais `config` résout ses chemins une
seule fois et `unittest discover` importe tous les modules avant d'en exécuter
un — le premier import gagnait pour toute la suite. Les quinze modules
partageaient une base et un dossier de produits, sans qu'aucun test n'échoue.
La bascule a lieu maintenant dans `setUpModule`, et trois tests interdisent le
retour en arrière.

---

## Ce qu'on pourrait ajouter

Une revue complète — état du câblage, ce que chaque type de produit sait et ne
sait pas faire, et ce qu'on peut y ajouter — est dans
[docs/EXTENSIONS.md](docs/EXTENSIONS.md). Les deux réponses courtes :

- **Romans et nouvelles : non, pas aujourd'hui.** Les chapitres d'un ebook sont
  rédigés indépendamment les uns des autres — une qualité pour un guide, un
  défaut rédhibitoire pour une fiction, qui a besoin d'une continuité que cette
  architecture ne porte pas. Il faut une chaîne distincte, avec une bible et un
  résumé roulant.
- **Sécurité : oui, du côté défense — et il y a maintenant un vrai outil.**
  `usine recon <domaine>` fait de la reconnaissance passive (crt.sh, DNS,
  RDAP) et, sur autorisation, un audit de surface. Il trouve de vraies failles
  signalables — e-mail usurpable, en-têtes absents, `.git` exposé, TLS faible —
  et rédige le signalement de divulgation. Pas d'outil qui attaque ce qui ne
  vous appartient pas. Voir [docs/RECON.md](docs/RECON.md).

## Ce que l'usine ne fait pas

- **Elle ne contourne aucun quota.** Pas de création de comptes automatisée,
  pas de contournement de restriction de fournisseur. La rotation multi-clés et
  l'addition de sept services gratuits donnent le même résultat sans risquer
  le bannissement.

- **Elle ne publie pas à votre place.** Aucune intégration Gumroad ou Etsy :
  vous téléversez l'archive vous-même. Elle lit en revanche vos exports de
  ventes, et s'en sert pour choisir les niches suivantes.
- **Elle ne sauvegarde pas toute seule.** `usine sauvegarde` existe, il faut
  la lancer — et copier l'archive hors du téléphone.
- **Elle ne vous dispense pas de publier lentement.** Produire quatre produits
  par jour et les déposer au même rythme est le profil exact d'un compte qui
  se fait fermer. L'usine le rappelle à la fin de chaque lot.
- **Elle ne relit pas pour vous.** Le contenu est généré par IA : relisez et
  corrigez avant de vendre. La licence livrée le mentionne explicitement.
- **Elle n'invente pas votre expertise.** Les meilleurs produits sortent d'un
  sujet que vous connaissez ; l'usine accélère la mise en forme, pas le savoir.
- **Elle ne garantit aucun revenu.** Les prix proposés sont des repères, pas
  des prévisions.

## Licence

MIT — voir `LICENSE`.
