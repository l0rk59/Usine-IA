# Audit : les agents, les fournisseurs, et par où ils passent

Audit du 15/09/2026. Chaque affirmation ci-dessous est mesurée — l'arbre
syntaxique pour le câblage, un compteur pour l'exécution, un produit sur le
disque pour l'effet.

## Les agents : rien de mort, mais un agent muet là où ça compte

**Câblage.** Dix-sept agents déclarés. Un détecteur qui lit l'arbre syntaxique
(pas les noms — chercher `ARCHITECTE` en texte trouve sa propre définition)
donne : **15 fonctions publiques sur 15 et 17 agents sur 17 joignables** depuis
une chaîne de fabrication, par huit points d'entrée.

Cinq agents n'ont aucun appelant hors de `equipe.py`. Ce n'est pas un défaut :
ils servent à travers la relecture croisée, qui part bien d'un pipeline. La
joignabilité transitive le confirme.

**Exécution.** Compté sur une fabrication des dix-huit types : **153 appels
d'agents**. Trois agents restent muets — `CONTROLEUR`, `LECTEUR`, `STYLISTE`.

Deux le sont légitimement : ils ne s'allument qu'au niveau `exigeant`, et ce
réglage les réveille vraiment. Même mesure, `qualite="exigeant"` :

| agent | standard | exigeant |
|---|---|---|
| CONTROLEUR | 0 | 9 |
| STYLISTE | 0 | 9 |
| EDITEUR | 9 | 18 |
| REDACTEUR | 15 | 24 |

Le troisième, non.

## Le défaut : quatre réglages cochés qui ne faisaient rien

`LECTEUR` dépend de `relecture_ensemble`, pas de `qualite`. Mesure par le
chemin réel du bouton, les quatre réglages activés :

| réglage | ce qu'il annonce | ce qui sortait |
|---|---|---|
| `relecture_ensemble` | relire le produit entier | LECTEUR a parlé **0 fois** |
| `marketing_auto` | le kit de vente sans le demander | aucun kit |
| `archive_auto` | l'archive ZIP livrable | aucune archive |
| `extrait_offert` | N chapitres offerts | aucun extrait |

Le travail existait — `cli._apres_production` le faisait depuis toujours — mais
il vivait derrière des arguments `argparse`. Le tableau de bord s'arrêtait à
`catalogue.executer`.

Un réglage affiché, sauvegardé et jamais lu est un mensonge fait à
l'utilisateur. Le dépôt avait déjà trouvé ce défaut une fois, sur `plateforme`
et `devise` ; le commentaire qui le raconte est encore dans `cli.py`. Il était
revenu **sur le chemin du téléphone**, c'est-à-dire l'usage normal de cette
usine.

**La correction n'est pas de recopier le code dans le serveur** : deux copies
divergent, et c'est ainsi que la première avait vieilli. Le travail vit
maintenant dans `usine/pipelines/apres.py`, que la ligne de commande et le
bouton appellent tous les deux. Le verdict « le réglage décide, l'appelant
tranche » vit dans `apres.veut`, en un seul endroit, avec son troisième
état — `None`, « je ne me prononce pas » — sans lequel un réglage ne peut ni
s'appliquer ni s'annuler.

Après correction, même mesure : LECTEUR parle, le kit fait 4 fichiers,
l'extrait offre bien 2 chapitres sur 14, l'archive est écrite.

## Les fournisseurs : onze déclarés, tous joignables, quatre sans date

**Rôles.** Sept rôles logiques, tous demandés par le code. Trois seulement
(`openrouter`, `opencode`, `nvidia`) déclarent un modèle pour `creatif`, `code`
et `raisonnement` ; ailleurs `model_for` retombe sur `standard`. C'est
documenté et voulu — et `modeles.choisir` résout de toute façon le rôle sur le
catalogue que le fournisseur sert réellement ce jour-là.

Un détecteur trop large avait signalé quatre rôles « non documentés » :
`titre`, `marque`, `auteur`, `sous-titre`. Ce sont des rôles **typographiques**
du moteur de couverture. Faux positif — noté ici parce qu'un contrôle qui
signale à tort finit ignoré, et que celui-là ne sera pas gardé.

**Quotas.** La règle du dépôt est qu'un chiffre recopié porte sa date de
vérification. Quatre fournisseurs distants ne l'avaient pas :

- `cerebras` citait sa source (`inference-docs.cerebras.ai`) sans dire quand ;
- `mistral`, `github` et `pollinations` n'avaient ni source ni date ;
- `groq` portait une date, mais celle d'une **dépréciation passée** — elle dit
  pourquoi ces modèles-ci sont configurés, pas quand ces quotas-là ont été
  relevés. C'est la distinction que le garde-fou ne fait pas, et un lecteur non
  plus.

Ces quotas n'ont pas été re-relevés ici : aucun accès aux documentations des
fournisseurs depuis cet environnement, et inventer une date de vérification
serait exactement le défaut qu'on corrige. Chaque fiche dit désormais **ce qui
est vrai** : quand la valeur a été posée (relevé par `git blame`), d'où elle
vient quand on le sait, et qu'elle reste à revalider — par `usine docteur
--modeles`, qui interroge le service lui-même.

## Le garde-fou ne gardait que deux fiches sur onze

Le test qui exige ces dates existait, bien raisonné — il documente même la
première erreur, « chercher une date n'importe où dans le fichier ». Mais sa
portée était une **liste de deux noms écrite à la main**, dans un fichier qui
en déclare onze. Les neuf autres pouvaient vieillir sans que rien ne le dise.

Il lit maintenant `config.PROVIDERS`, en exemptant les fournisseurs locaux —
« 600 par minute » sur ollama veut dire « autant que le téléphone en
supporte », ce n'est pas un chiffre pris chez quelqu'un.

Et il **compte** ce qu'il a vérifié, parce qu'un détecteur vert ne se garde pas
lui-même : une campagne de mutation a montré qu'on pouvait réduire sa boucle à
deux fournisseurs sans qu'un seul test bronche. La panne d'origine survivait à
sa propre correction.

## Ce que la refonte a révélé sur un autre garde-fou

Le détecteur de réglages orphelins a immédiatement signalé `marketing_auto` et
`archive_auto`. Il avait raison de se plaindre : il exige que la clé apparaisse
sur une ligne qui la **lit**, et il connaît la liste des verbes de lecture.
`veut(` n'en faisait pas partie.

Une liste de verbes est une liste — elle ne devine pas. C'est le prix d'un
détecteur qui lit la structure plutôt qu'un nom « quelque part dans le code »,
et c'est un prix qui vaut d'être payé : il a signalé un vrai changement de
câblage dans la minute.

## Ce qui garde tout cela

- `tests/test_reglages_du_bouton.py` — 9 tests qui passent par le serveur et
  regardent le produit. Campagne de mutation : 8 mutations, toutes vues.
- `tests/test_fournisseurs_declares.py` — portée élargie et auto-vérifiée.
  Campagne : 6 mutations, toutes vues.

Un test de ce module a d'abord cassé un module voisin : le harnais posait dans
`serveur.TRAVAUX`, partagé par tout le processus, une fiche incomplète qu'il ne
retirait pas. Un harnais de test qui abîme l'état d'autrui fait perdre plus de
temps qu'il n'en fait gagner.

## La seconde moitié : le local, la CI, les trois portes

Suite du même audit, le 23/09/2026. Chaque ligne a été mesurée avant d'être
corrigée, et chaque correction vue échouer quand on remet le défaut.

| Ce qui allait mal | Mesure | Où c'est expliqué |
|---|---|---|
| Une page web quelconque réécrivait les réglages du tableau de bord | `POST text/plain` depuis `evil.example` : `marque` et `site` modifiés | [SECURITE.md](SECURITE.md) |
| Un ollama éteint coûtait 11 s à chaque appel | 11 s → 0,04 s | [ROUTEUR.md](ROUTEUR.md) |
| La CI était rouge depuis sa création, et cachait un vrai échec sous Python 3.9 | 14 faux secrets dès le 12/09 ; `dependances.py` rendait 0 sans vérifier | [SECURITE.md](SECURITE.md) |
| Le bouton « Générer » et la boucle envoyaient « TON : auto » au rédacteur | 15 invites sur 15, contre 0 sur 13 en ligne de commande | [UN-BOUTON.md](UN-BOUTON.md) |
| Un réglage de fiction du formulaire n'atteignait pas l'écriture | 1 invite sur 28 → 11 sur 23 | [UN-BOUTON.md](UN-BOUTON.md) |
| « Reprendre » ne reprenait rien hors ligne de commande | `unrecognized arguments`, code 2 ; travail figé « en cours » | [UN-BOUTON.md](UN-BOUTON.md) |
| Un roman coupé par les quotas attendait qu'on revienne | niche marquée « faite », dix scènes jamais écrites | [USINE-CONTINUE.md](USINE-CONTINUE.md) |
| Trois réglages « à chaque produit » ignorés par la boucle | 1, 1, 1 au tableau de bord ; 0, 0, 0 dans la boucle | [USINE-CONTINUE.md](USINE-CONTINUE.md) |
| Kit de vente et test A/B parlaient d'une voix « auto » | toutes leurs invites | [UN-BOUTON.md](UN-BOUTON.md) |
| Deux reprises du même produit se tuaient l'une l'autre | vu dans la suite de tests, une passe sur trois | [UN-BOUTON.md](UN-BOUTON.md) |
| Une consigne laissée à l'auteur partait dans le livre | rien ne la signalait | [QUALITE.md](QUALITE.md) |
| La langue et la marque réglées étaient ignorées par le tableau de bord et la boucle | 0 invite sur 7 en anglais, EPUB déclaré `fr` | [UN-BOUTON.md](UN-BOUTON.md) |
| Le message « tous les fournisseurs ont échoué » coupait le premier essayé | 10 dernières lignes sur 11, doublons | [ROUTEUR.md](ROUTEUR.md) |
| Du markdown en clair et des gabarits `<…>` invisibles chez l'acheteur | `**` dans les PDF de 12 types sur 18 ; `<VOTRE NOM>` avalé 99 fois dans 4 pages | [QUALITE.md](QUALITE.md) |
| La ligne de commande et le menu ne faisaient décider aucun réglage de type | 0 décision sur 17 types, contre 17 sur 17 au tableau de bord | [DEPUIS-ZERO.md](DEPUIS-ZERO.md) |

### Lu quelque part n'est pas appliqué partout

Deux garde-fous étaient verts sur ces défauts, et avaient raison selon leurs
propres termes.

Le détecteur de réglages orphelins exige que chaque réglage soit **lu**
quelque part. `marketing_auto` l'était — par `apres.veut`, qu'appelaient la
ligne de commande et le tableau de bord. La boucle ne l'appelait pas. Le
réglage n'était pas orphelin ; il était appliqué par deux portes sur trois.

Le garde-fou de la promesse de lecture vérifiait que deux chemins la posaient :
la ligne de commande et la file. Le troisième, le tableau de bord, ne la posait
pas, et ce garde-fou ne le regardait pas.

C'est la même leçon que l'homonymie (voir `CLAUDE.md`), sous une autre forme :
un contrôle qui énumère les chemins à la main vieillit dès qu'un chemin
s'ajoute. La réponse n'a pas été un contrôle de plus, mais un chemin de moins :
le tableau de bord et la boucle passent maintenant par `pipelines/porte.py`,
et les trois portes par `brief.completer`.

### Ce qui reste à faire de votre côté

- Vérifier les modèles OpenRouter `:free` et les quotas sans date de
  vérification : `usine docteur --modeles`, avec une clé — ce sont des données
  recopiées, et elles vieillissent sans rien casser.
- Si vous voulez Cloudflare Workers AI : `CLOUDFLARE_API_TOKEN` et
  `CLOUDFLARE_ACCOUNT_ID` dans `.env`.

