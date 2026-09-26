# Usine-IA

**Une fabrique de produits digitaux qui tourne sur un téléphone Android, sous
Termux.**

Vous donnez un sujet — ou vous n'en donnez pas, et l'usine le cherche
elle-même. Treize agents construisent le plan, rédigent, **font relire le texte
par un autre modèle que celui qui l'a écrit**, corrigent, mesurent, mettent en
page un PDF et un EPUB, dessinent la couverture, écrivent la page de vente, et
emballent le tout dans une archive prête à mettre en ligne.

```bash
usine ebook "la prospection pour freelances débutants"
```

Dix à vingt-cinq minutes plus tard, vous avez un livre.

---

## La contrainte qui explique tout le reste

**Rien hors de la bibliothèque standard de Python.** Pas de `pip install`, pas
de CDN, pas de Node, pas de Java.

Termux ne sait pas compiler de roue native, et une dépendance ajoutée par
mégarde ne se voit qu'au moment où quelqu'un installe sur un téléphone neuf —
c'est-à-dire trop tard.

C'est pourquoi les moteurs PDF et EPUB sont écrits à la main, pourquoi la
conformité EPUB 3 est refaite en Python plutôt que d'appeler EPUBCheck (qui est
un programme Java), et pourquoi le tableau de bord 3D n'utilise aucune
bibliothèque graphique.

Le prix est réel : le PDF ne sait écrire que l'alphabet latin, et il le
[dit quand il rencontre autre chose](docs/CARACTERES.md). Le gain l'est aussi :
l'installation tient en une commande sur un appareil que tout le monde a déjà
dans la poche.

---

## Installation

### Sur Termux (Android)

```bash
pkg update -y && pkg install -y python git openssl ca-certificates
termux-setup-storage
git clone https://github.com/l0rk59/Usine-IA.git
cd Usine-IA && bash install.sh
```

`install.sh` installe la commande `usine`, crée le dossier de travail, et
termine par la liste de ce qui manque encore sur **cet** appareil.

### Sur Linux ou macOS

La même chose, sans les deux premières lignes. Python 3.9 minimum.

### Une clé API

L'usine tourne sans clé, sur le quota anonyme partagé de Pollinations — mais il
ne suffit pas à un produit entier. Sept services gratuits sont préconfigurés :

```bash
usine cles          # les liens pour en obtenir, un par un
nano .env           # coller la clé sur la bonne ligne
usine docteur       # vérifier que l'usine peut produire
```

Une seule clé suffit pour commencer. L'usine en accepte plusieurs par
fournisseur et bascule toute seule quand l'une sature.

---

## Le premier produit

```bash
usine ebook "la facturation pour indépendants"
```

Et si vous ne savez pas quoi vendre :

```bash
usine ebook
```

Sans sujet, l'usine en cherche un : elle propose des domaines, les **mesure**
sur des sources publiques, écarte ceux dont la demande ne se voit pas, et part
du mieux placé. Le détail : [docs/NICHE.md](docs/NICHE.md).

---

## Ce qu'elle sait fabriquer

| Commande | Produit | Ce que vous recevez | Durée |
|---|---|---|---|
| `usine ebook` | Ebook complet | PDF + EPUB + HTML + Markdown + couverture | 10–25 min |
| `usine nouvelle` | Nouvelle | Fiction courte, personnages et continuité tenus | 12–30 min |
| `usine roman` | Roman | Trente scènes, en parties, continuité contrôlée | 60–180 min |
| `usine interactive` | Livre dont le lecteur est le héros | Un récit à embranchements, dont la carte est vérifiée avant d'écrire | 25–70 min |
| `usine recueil` | Recueil de nouvelles | Plusieurs récits liés par un fil, dont on mesure la variété | 45–120 min |
| `usine feuilleton` | Feuilleton | Des épisodes qui se lisent seuls et appellent le suivant | 40–110 min |
| `usine conte` | Conte jeunesse illustré | Un album en doubles-pages, vérifié contre sa tranche d'âge | 10–30 min |
| `usine formation` | Mini-formation | Manuel + cahier d'exercices + séquence e-mail | 12–25 min |
| `usine prompts` | Pack de prompts | Bibliothèque classée, PDF + CSV + JSON | 5–12 min |
| `usine outils` | Boîte à outils | Checklists, modèles, tableaux de suivi | 6–14 min |
| `usine modeles` | Modèles Notion / tableur | Bases liées, prêtes à importer | 5–12 min |
| `usine impression` | Cahier imprimable | Fiches à remplir, A4 et Lettre US | 5–12 min |
| `usine social` | Pack de publications | Calendrier éditorial + visuels | 5–15 min |
| `usine logiciel` | Outil logiciel | Un programme qui démarre, vérifié avant livraison | 8–20 min |
| `usine emails` | Séquence e-mail | Les messages qui suivent une inscription, + CSV à importer | 6–14 min |
| `usine memo` | Mémo / antisèche | L'essentiel sur une page qu'on garde à côté de soi | 4–9 min |
| `usine quiz` | Quiz avec corrigé | Questions, corrigé expliqué, et une page qui se corrige seule | 7–16 min |
| `usine idees` | Étude de niche | Pistes chiffrées, appuyées sur des mesures | 2–4 min |

Et quand vous ne savez pas encore quoi fabriquer :

| Commande | Ce qu'elle fait |
|---|---|
| `usine auto` | L'usine choisit la niche **et** le type de produit |
| `usine auto "votre sujet"` | Vous donnez le sujet, elle choisit le type qui se vend le mieux dessus |

Les quinze commandes ci-dessus demandent le type d'abord. Or le choisir suppose
de savoir ce qui se vend dans une niche qu'on n'a pas encore cherchée : c'est
l'ordre inverse de celui dans lequel la question se pose. Le tableau de bord
propose le même choix, en tête de la liste des types.

Le détail de chacun : [docs/TYPES-PRODUITS.md](docs/TYPES-PRODUITS.md). Pour la
fiction, qui suit une chaîne à part : [docs/FICTION.md](docs/FICTION.md). Pour
les produits logiciels : [docs/LOGICIEL.md](docs/LOGICIEL.md).

---

## Trois façons de s'en servir

| | |
|---|---|
| `usine menu` | tout au clavier, sans rien retenir — **recommandé sur téléphone** |
| `usine ebook "..."` | la ligne de commande, pour les habitués et les scripts |
| `usine web` | le tableau de bord, dans le navigateur du téléphone |

Les trois lisent le même catalogue et les mêmes réglages : ce que vous changez
dans l'un vaut dans les autres.

Le tableau de bord montre la fabrication en direct — l'équipe d'agents qui
travaille, le journal, l'avancement — et propose six peaux, dont une pour lire
en plein soleil et une pour voir de loin :
[docs/PEAUX.md](docs/PEAUX.md). Sa scène 3D est écrite en WebGL brut :
[docs/CYBERPUNK.md](docs/CYBERPUNK.md).

---

## Dire ce que vous voulez — ou laisser décider

Tout est facultatif. Ce que vous ne dites pas, l'usine le décide en lisant le
sujet, et elle dit pourquoi.

```bash
usine ebook "la fiscalité du freelance" \
  --audience "freelances en première année" \
  --ton pedagogue \
  --chapitres 12 \
  --qualite exigeant
```

| Option | Ce qu'elle change |
|---|---|
| `--audience` | à qui le produit parle |
| `--ton` | `amical`, `expert`, `pedagogue`, `pro`, `punchy` — ou une phrase libre |
| `--taille` / `--chapitres` | le volume |
| `--qualite` | `rapide` (0 relecture), `standard` (1), `exigeant` (2) |
| `--forme` (ebook) | `methode`, `reference`, `programme`, `cas`, `questions` : la charpente du livre |
| `--niveau` (ebook) | `debutant`, `intermediaire`, `avance` |
| `--exercices` (ebook) | `avec` : un exercice encadré par chapitre |
| `--marketing` | ajoute le kit de vente |
| `--zip` | emballe l'archive à livrer |
| `--hors-ligne` | aucune connexion ne sort du téléphone : IA locale seulement, couverture dessinée sur place |

Pour ne pas retaper les mêmes à chaque fois :

```bash
usine reglages                                    # les voir, groupés
usine reglages --definir auteur="Votre Nom" qualite=exigeant
```

Trente réglages, rangés en six groupes : qui vend, comment l'usine écrit, ce
qui part avec le produit, ce qu'elle a le droit de dépenser, le téléphone,
l'affichage.

---

## Produire en boucle

```bash
usine usine demarrer       # enchaîne les produits, sous budget
usine usine statut         # où elle en est
usine usine arreter        # termine le produit en cours, puis s'arrête
```

Elle s'arrête d'elle-même sur le plafond du jour, sur batterie faible, ou quand
la file se vide — et si vous le lui demandez, elle **remplit la file toute
seule** en cherchant des niches voisines de ce qui a le mieux marché.

Le plafond est tenu à l'appel près, et sous un petit budget l'usine refuse de
commencer un produit qu'elle ne pourrait pas finir :
[docs/USINE-CONTINUE.md](docs/USINE-CONTINUE.md).

---

## Quand ça casse

```bash
usine docteur      # ce qui ne va pas, et la commande pour le réparer
usine liste        # ce qui est fabriqué, et ce qui est resté inachevé
usine reprendre    # finit un produit coupé, sans repayer ce qui est fait
usine maj          # met à jour depuis le dépôt
usine specs        # fiche technique de l'appareil, à pousser sur GitHub
```

Une coupure — réseau, quota, batterie, processus tué par Android — ne perd rien
de ce qui est déjà écrit. Le produit reste marqué **inachevé**, il nomme les
sections qui lui manquent, et `usine reprendre` ne refait que celles-là :
[docs/TROUS.md](docs/TROUS.md) et [docs/PANNES.md](docs/PANNES.md).

Et pour mettre l'atelier à l'abri :

```bash
usine sauvegarde creer --avec-produits
```

L'archive ne contient **jamais** vos clés API — elles vivent dans `.env`, hors
de l'atelier : [docs/SAUVEGARDE.md](docs/SAUVEGARDE.md).

---

## Les fournisseurs de modèles

Sept services gratuits sont préconfigurés — Groq, Cerebras, Gemini, Mistral,
OpenRouter, GitHub Models, NVIDIA — plus Pollinations sans clé, et l'IA locale
(Ollama, llama.cpp) en dernier recours.

Le routeur choisit selon le **rôle** demandé (« un modèle costaud », « un
modèle qui écrit de la fiction ») et non selon un nom : un identifiant renommé
chez un fournisseur est rattrapé tout seul en relisant son catalogue vivant.
[docs/ROUTEUR.md](docs/ROUTEUR.md), [docs/QUOTAS.md](docs/QUOTAS.md).

**Abonnement payant, facultatif.** [OpenCode Go](https://opencode.ai/go) donne
accès à une trentaine de modèles ouverts derrière une seule clé. Il est
compatible OpenAI, donc l'usine sait lui parler :

```bash
# dans .env
OPENCODE_API_KEY=votre-cle
```

Deux différences à connaître : ses plafonds se comptent en **dollars** et non
en requêtes, et il n'expose **aucun catalogue interrogeable**. Si un modèle est
renommé chez eux, l'usine le verra en erreur nommée et basculera sur un autre
fournisseur — sans pouvoir se corriger toute seule comme elle le fait ailleurs.

---

## Ce que l'usine mesure

C'est le parti pris du projet : **mesurer plutôt que déclarer**.

Là où d'autres font relire par un modèle, l'usine mesure — répétitions,
rythme des phrases, diversité lexicale, chiffres avancés sans source,
continuité d'une section à l'autre. Une mesure ne coûte rien, ne s'épuise pas,
et rend le même verdict deux fois de suite.

Chaque produit relu reçoit un rapport section par section : la note avant, la
note après, ce qui a été corrigé, ce qui reste signalé.
[docs/QUALITE.md](docs/QUALITE.md).

Le prix de ce parti pris est dit aussi : un contrôle déterministe rate ce qu'il
ne sait pas nommer. Et il ne mesure que de la **prose** — appliqué à une liste
de prompts ou à du code, il rendrait un chiffre sans signification, donc il
s'abstient et dit pourquoi : [docs/MESURE.md](docs/MESURE.md).

Deux règles complètent cela, et reviennent à chaque audit :

- **Un garde-fou satisfait par une homonymie ne garde rien.** Chercher un nom
  « quelque part dans le code » a déjà laissé passer trois défauts.
- **Ne pas croire le code de retour, lire le contenu.** Un fournisseur peut
  répondre `HTTP 200`, `finish_reason: stop`, et pour tout contenu « votre clé
  a épuisé son budget ».

---

## Ce que l'usine ne fait pas

- **Elle ne publie pas à votre place.** Pas d'API Etsy, Gumroad ou KDP : elle
  produit les fichiers et le kit de vente, vous les mettez en ligne.
- **Elle ne promet aucun revenu.** `usine bilan` ne parle que de ce qui a été
  mesuré, et dit sur combien de produits repose chaque moyenne.
- **Elle n'écrit que de l'alphabet latin en PDF.** L'EPUB, lui, porte tout.
- **Elle ne remplace pas votre jugement.** Un contrôle automatique rate ce
  qu'il ne sait pas nommer ; relisez avant de vendre.

---

## Pour aller plus loin

Une note par sujet, chacune racontant un défaut **mesuré** et sa correction.

### Fabriquer

| | |
|---|---|
| [TYPES-PRODUITS.md](docs/TYPES-PRODUITS.md) | ce que chaque chaîne produit exactement |
| [FICTION.md](docs/FICTION.md) | pourquoi la fiction suit une chaîne à part |
| [FICTION-PROMESSE.md](docs/FICTION-PROMESSE.md) | pour la fiction, on ne cherche pas une niche |
| [LOGICIEL.md](docs/LOGICIEL.md) | un programme vérifié, et réellement lancé, avant livraison |
| [NICHE.md](docs/NICHE.md) | quand on ne dit pas quoi produire |
| [PROSPECTION.md](docs/PROSPECTION.md) | pourquoi l'exploration rendait toujours les mêmes huit idées |
| [AUDIT-ORGANISATION.md](docs/AUDIT-ORGANISATION.md) | compter plutôt que lire : copies, câblage, code à l'abandon |
| [ILLUSTRATIONS.md](docs/ILLUSTRATIONS.md) | quatorze illustrations produites, zéro livrée — et pourquoi rien n'échouait |
| [COMPTES.md](docs/COMPTES.md) | la couverture annonçait sept prompts, le pack en contenait douze |
| [UN-BOUTON.md](docs/UN-BOUTON.md) | un type, un clic : ce que la mesure a dit, et les deux choses qui ne suivaient pas |
| [AUDIT-AGENTS-FOURNISSEURS.md](docs/AUDIT-AGENTS-FOURNISSEURS.md) | les dix-sept agents, les onze fournisseurs, et quatre réglages qui ne faisaient rien |
| [PLAFONDS.md](docs/PLAFONDS.md) | les plafonds de jetons sont les nôtres, et une coupure ne lève aucune erreur |
| [PROSE.md](docs/PROSE.md) | la phrase, que les contrôles de charpente ne regardaient pas |
| [RESEAU.md](docs/RESEAU.md) | ce qui se passe quand une API échoue : réessais, attente, bascule |
| [DEPUIS-ZERO.md](docs/DEPUIS-ZERO.md) | l'usine décide tout à partir du sujet : plus aucun réglage par défaut |
| [USINE-CONTINUE.md](docs/USINE-CONTINUE.md) | produire en boucle, sous budget |
| [COUVERTURE.md](docs/COUVERTURE.md) | la couverture, dessinée sans bibliothèque |
| [LANGUE-LIVREE.md](docs/LANGUE-LIVREE.md) | un livre anglais habillé en français : le texte fixe suit la langue |

### Qualité

| | |
|---|---|
| [QUALITE.md](docs/QUALITE.md) | mesurer plutôt que déclarer |
| [MESURE.md](docs/MESURE.md) | ce que l'usine sait de ce qu'elle vient de fabriquer |
| [AGENTS.md](docs/AGENTS.md) | les treize agents et la boucle de relecture |
| [TROUS.md](docs/TROUS.md) | un produit livré avec un trou doit le dire |
| [CARACTERES.md](docs/CARACTERES.md) | ce que le PDF ne sait pas écrire |
| [DOUBLONS.md](docs/DOUBLONS.md) | reconnaître ce qui a déjà été écrit |
| [AB-TESTING.md](docs/AB-TESTING.md) | tester des titres et des couvertures |

### Vendre

| | |
|---|---|
| [VENDRE.md](docs/VENDRE.md) | du fichier à la première vente |
| [ARCHIVE.md](docs/ARCHIVE.md) | ce que l'acheteur trouve dans l'archive |
| [MARCHE.md](docs/MARCHE.md) | mesurer un marché sur des sources publiques |
| [VEILLE.md](docs/VEILLE.md) | aller voir ce que les gens disent vraiment |
| [VENTES.md](docs/VENTES.md) | importer ses ventes, et ce qui rapporte |

### La machine

| | |
|---|---|
| [TERMUX.md](docs/TERMUX.md) | guide pas à pas sur téléphone |
| [ROUTEUR.md](docs/ROUTEUR.md) | le routeur multi-fournisseurs |
| [QUOTAS.md](docs/QUOTAS.md) | ce que les paliers gratuits autorisent vraiment |
| [PANNES.md](docs/PANNES.md) | disque plein, base écrasée, réseau coupé |
| [SAUVEGARDE.md](docs/SAUVEGARDE.md) | mettre l'atelier à l'abri, et le remettre |
| [SECURITE.md](docs/SECURITE.md) | ce qui ne doit jamais sortir de l'appareil |
| [PEAUX.md](docs/PEAUX.md) | les six peaux du tableau de bord |
| [CYBERPUNK.md](docs/CYBERPUNK.md) | la scène 3D, en WebGL brut |

### Ce qui a été mesuré

| | |
|---|---|
| [AUDIT-INVARIANTS.md](docs/AUDIT-INVARIANTS.md) | des propriétés mesurées sur tout le code |
| [AUDIT.md](docs/AUDIT.md) | l'audit complet, câblage compris |
| [ERGONOMIE.md](docs/ERGONOMIE.md) | ce qu'un utilisateur a trouvé en dix minutes |
| [COMPARAISON.md](docs/COMPARAISON.md) | l'usine face à ce qui existe ailleurs |
| [EXTENSIONS.md](docs/EXTENSIONS.md) | ce qu'elle pourrait faire de plus |

---

## Développer

```bash
python3 -m unittest discover -s tests -t . -q   # la suite complète
python3 tests/fumee.py                          # les dix chaînes, de bout en bout
python3 scripts/dependances.py                  # zéro dépendance externe
```

Les conventions du dépôt — et surtout **pourquoi** elles sont ce qu'elles
sont — sont dans `CLAUDE.md`. La règle qui les résume : un test ne vaut que si
on l'a vu échouer. Après une correction, on remet le défaut et on vérifie que
la suite le remarque.

---

## Licence

MIT — voir `LICENSE`.
