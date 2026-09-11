# Les produits logiciels

Un ebook qui contient une phrase maladroite se vend quand même. Un script qui
ne démarre pas ne se vend pas : l'acheteur demande un remboursement et ne
revient pas. C'est la différence entre les huit autres types de produits et
celui-ci — et c'est pourquoi `logiciel` est le seul type dont **rien n'est
livré sans avoir été vérifié**.

## Trois cibles, une seule chaîne

| Cible | Ce qui est livré | Vérification |
|---|---|---|
| `cli` | `outil.py` + `test_outil.py`, Python 3.8+, stdlib seule | AST, puis **exécution réelle** |
| `web` | `index.html` autonome, CSS et JS en ligne | analyseur HTML + chasse aux dépendances externes |
| `extension` | `manifest.json`, `popup.html`, `popup.js`, `contenu.js` | schéma Manifest V3 + `node --check` |

```
usine logiciel "le calcul de tarif pour freelances" -c web
usine logiciel "le nettoyage de fichiers en double" -c cli
usine logiciel "la lecture sans distraction" -c extension --sans-essai
```

Les quatre étapes sont les mêmes pour les trois : spécification → génération
fichier par fichier → **vérification et réparation** → mise en carton.

## Pourquoi la vérification existe

Catalyst, le dépôt dont cette usine reprend les idées, avait un
`software_packager.py`. Il assemblait le code renvoyé par le modèle, écrivait
le ZIP, et le déclarait livrable. **Aucune vérification de syntaxe, à aucun
moment.** Un modèle produit du code *plausible*, pas du code *correct* — et la
différence ne se voit qu'en la mesurant.

Ici, chaque fichier passe par `usine/core/verification.py` avant d'être écrit
sur le disque. Quand il est cassé, **l'erreur exacte est renvoyée au modèle**
avec le contenu fautif, et il corrige ; une tentative de réparation par fichier
par défaut. C'est ce qui distingue une vérification d'un simple test : le
résultat sert à quelque chose.

## Deux niveaux, dans cet ordre

### 1. Analyse statique — toujours

Pour Python, l'arbre syntaxique est parcouru. Sont relevés :

- les **modules sensibles** : `subprocess`, `socket`, `ctypes`, `shutil`,
  `requests`, `urllib`, `pickle`, `importlib`…
- les **fonctions interdites** : `eval`, `exec`, `compile`, `__import__`
- les **appels système** : `os.system`, `os.popen`, `os.remove`, `os.chmod`,
  `os.fork`, `os.kill`…
- les **écritures hors du dossier courant** : tout `open()` en mode écriture
  sur un chemin absolu ou remontant par `..`

Pour le JavaScript, `node --check` quand Node est présent — et un contrôle
structurel de repli quand il ne l'est pas, ce qui est le cas courant sur
Termux. Pour le manifeste, le schéma Chrome MV3 et les permissions demandées :
réclamer `<all_urls>` quand `activeTab` suffit fait rejeter l'extension.

### 2. Exécution — seulement si l'analyse est propre

Ce code vient d'un modèle de langage, pas de vous. Un `os.system("rm -rf ~")`
généré par accident dans un exemple d'illustration effacerait le téléphone.
L'exécution n'a donc lieu que si l'arbre syntaxique ne contient rien de ce qui
précède — c'est ce que signifie le champ `executable` d'un rapport : **sûreté,
pas succès**.

Quand elle a lieu, c'est dans un dossier temporaire, hors du projet, avec le
proxy retiré de l'environnement et une limite de temps (15 s pour `--help`,
30 s pour la suite de tests). Un dépassement est rapporté comme boucle infinie
probable, pas comme une erreur mystérieuse.

L'outil est lancé deux fois : `--help`, puis les tests unitaires que le modèle
a lui-même écrits. « Le fichier compile » ne dit pas qu'il démarre.

`--sans-essai` désactive entièrement cette seconde phase. L'analyse statique,
elle, ne se désactive pas.

## Ce que l'acheteur reçoit

```
logiciel-compteur-de-mots-20260911-120556-de69/
├── source/
│   ├── outil.py
│   └── test_outil.py
├── notice.md            présentation, installation, rapport de vérification
├── compteur-mots.pdf
├── lire.html
├── verification.json    le détail, fichier par fichier
└── produit.json
```

`verification.json` contient la spécification, le verdict de chaque analyseur
et le résultat de chaque essai. Le contrat annoncé est donc **contrôlable par
l'acheteur lui-même**, pas seulement affirmé.

## Ce qui a été mesuré

L'analyseur a été confronté à six échantillons hostiles écrits pour lui —
`os.system`, `shutil.rmtree`, `eval`, ouverture d'un socket, `subprocess`,
écriture sur un chemin absolu. **Les six sont refusés à l'exécution.** Du code
propre passe, et une boucle infinie est arrêtée à la limite de temps plutôt que
de bloquer la production.

Les trois cibles ont été produites de bout en bout :

- `cli` — code valide, l'outil généré répond à `--help` et ses tests unitaires
  passent ;
- `web` — le fichier a été **ouvert dans un vrai Chromium** : la saisie
  « un deux trois quatre / cinq six » a bien renvoyé 6 mots, 2 lignes,
  29 caractères, sans une seule erreur JavaScript ;
- `extension` — manifeste, popup et script de contenu valides, chacun dans son
  propre dossier.

## Un bug trouvé en chemin

Les trois cibles produites à la suite se sont retrouvées **dans le même
dossier**, leurs `source/` mélangés. L'identifiant de produit était bâti sur un
horodatage à la seconde : trois produits créés dans la même seconde partageaient
un nom. Aucun autre type ne l'avait révélé, parce qu'aucun autre ne se fabrique
assez vite pour que cela arrive.

`usine/pipelines/base.py` y ajoute désormais `secrets.token_hex(2)`.

## Limites, dites franchement

- **La vérification prouve que le code démarre, pas qu'il est utile.** Un outil
  qui compile, passe ses tests et répond à `--help` peut rester un mauvais
  produit. C'est le contrôle qualité (`docs/QUALITE.md`) qui juge la promesse,
  pas l'analyseur.
- **Les tests unitaires sont écrits par le même modèle que le code.** Ils
  attrapent les régressions grossières, pas les erreurs de raisonnement
  partagées entre les deux.
- **L'analyse JavaScript est plus faible sans Node.** Le contrôle structurel de
  repli voit les accolades déséquilibrées et les dépendances externes, pas une
  erreur de syntaxe fine. `usine docteur` indique si Node est disponible.
- **Une extension n'est pas publiée pour autant.** Le Chrome Web Store demande
  un compte développeur payant et une revue humaine ; ce qui est livré est le
  dossier prêt à charger en mode développeur ou à téléverser.
