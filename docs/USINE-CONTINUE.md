# L'usine continue

## Le journal sur disque

Une production continue tourne des heures sur un téléphone dont Android
réclame le tampon du terminal. Une niche qui échoue à trois heures du matin ne
laissait donc **aucune trace lisible** : la base retient bien les étapes de
chaque produit, mais pas ce qui s'est passé *entre* eux — la niche sautée, le
fournisseur tombé, l'arrêt sur batterie faible.

`config.LOG_DIR` était créé à chaque démarrage et n'avait jamais rien reçu.

```bash
usine journal                # les 40 dernières lignes du jour
usine journal 2026-09-10 -n 200
```

Sur un téléphone : « Usine continue » → « Journal ».

Trois contraintes de l'appareil ont dicté la forme du module
(`core/trace.py`) :

| Contrainte | Décision |
|---|---|
| le processus meurt sans préavis | le fichier est **ouvert et refermé à chaque ligne** — plus coûteux qu'une poignée gardée ouverte, et c'est le but : un tampon emporterait précisément les lignes qui expliquent l'arrêt |
| le disque est fini | un fichier par jour, les plus anciens effacés au-delà de 14 jours. Un journal qui remplit le téléphone fait échouer la fabrication qu'il était censé documenter |
| une clé ne doit jamais toucher le disque | chaque ligne passe par `securite.expurger` |

Sur ce dernier point, le journal **dit** que le masquage a eu lieu, une seule
fois par session : masquer en silence laisserait l'utilisateur avec une clé
exposée quelque part et aucune raison de la renouveler. Répétée à chaque
ligne, l'alerte deviendrait invisible — et c'est une alerte qu'il faut lire.

Le journal est une trace, pas une fonction métier : toute erreur d'écriture
est avalée. Un journal qui empêche de produire est pire qu'un journal absent.

Vous remplissez une file de niches, vous fixez un budget, vous lancez. L'usine
produit en boucle et s'arrête toute seule — sur la fin de la file, sur le
budget, ou sur votre demande.

```bash
usine file --ajouter "la prospection pour freelances" "la gestion du temps"
usine file --ajouter "50 prompts pour community managers" --type prompts -n 50 --priorite 1
usine usine demarrer --budget appels_jour=250 produits_jour=3
```

## L'usine choisit ses niches

Jusqu'ici, la file attendait qu'on la remplisse. Un remplissage automatique
existait — il partait du **dernier** produit fabriqué, explorait sans aucune
mesure, et ne vérifiait pas si la piste avait déjà été traitée.

```bash
usine file --explorer                  # part de ce qui a le mieux rapporté
usine file --explorer "une niche"      # part d'où vous voulez
usine file --explorer --sans-veille    # sans aller lire les discussions
```

### Trois garde-fous, dans cet ordre

**1. La graine vient de ce qui a rapporté.** Le commentaire de l'ancienne
version annonçait « les sujets qui ont donné les meilleures notes ». Le code
prenait le plus **récent** portant une note : entre une niche à 9,5 et une à
4,0 produite après, il repartait de celle à 4,0.

Le classement se fait maintenant par chiffre d'affaires d'abord, note ensuite.
Le revenu mesure le marché, la note mesure l'usine — quand les deux existent,
c'est le marché qui tranche.

**2. L'exploration s'appuie sur des mesures.** Le remplissage automatique
appelait l'explorateur avec `avec_marche=False` et sans veille : il tournait
sur la seule imagination du modèle. Il reçoit désormais les quatre sources de
marché **et** les discussions réelles.

**3. Une piste déjà fabriquée est écartée avant d'entrer en file.** La file ne
se dédoublonne que sur elle-même — sur le couple exact (sujet, type). Sans ce
filtre, l'usine refabriquait une niche déjà traitée sous un titre voisin, et
`usine doublons` ne le signalait qu'**après coup**, le quota dépensé.

```
  Exploration a partir de « la prospection pour freelances »...
  8 piste(s) explorees, 6 mise(s) en file.
    ecartee : « Prospection freelance » recouvre « Le systeme du freelance »
```

### Depuis le téléphone

Menu → *Usine continue* → **Laisser l'usine chercher**. Il propose la graine,
dit d'où elle vient, et laisse la remplacer.

## La file

Persistée en base, pas en mémoire — et c'est la décision qui compte le plus
sur Android : le système tue les processus en arrière-plan sans préavis. Une
file en mémoire disparaîtrait avec le processus. Ici, relancer reprend
exactement où l'usine s'était arrêtée, et une entrée laissée « en cours » par
une coupure est remise en attente au démarrage suivant.

```bash
usine file                          # voir la file
usine file --ajouter "niche" --type impression --priorite 1
usine file --retirer 3
usine file --rejouer                # remettre les échecs en file
usine file --vider                  # nettoyer les entrées livrées
```

| Comportement | Pourquoi |
|---|---|
| Priorité 1 passe avant priorité 9 | vous décidez de l'ordre, pas l'ordre d'ajout |
| Un doublon en attente est refusé | relancer la même commande ne produit pas deux fois le même livre |
| Un sujet **déjà livré** peut être relancé | refaire un produit est légitime |
| 2 tentatives avant condamnation | une coupure réseau ne doit pas condamner une niche |

## Le budget

C'est lui qui empêche l'usine de vider vos quotas pendant la nuit.

```bash
usine reglages --definir budget_appels_jour=250 budget_appels_produit=80 \
                        budget_produits_jour=4 budget_minutes_produit=45
usine usine demarrer --budget appels_jour=120     # ou à la volée
```

`0` signifie « pas de limite ». Trois niveaux de contrôle :

**Avant chaque produit.** L'usine refuse d'en démarrer un qu'elle ne pourra
pas finir. Entamer un ebook avec 5 appels restants gaspille le budget *et*
laisse un dossier incomplet — mieux vaut s'arrêter proprement et garder la
niche en file.

**Avant chaque appel.** Une garde est consultée par le routeur IA. Une réponse
servie par le cache n'est jamais refusée : elle ne coûte rien.

**Pendant un produit.** Si un plafond tombe au dixième chapitre, **le livre
sort quand même** : les chapitres déjà rédigés sont conservés, les suivants
sont réduits à leur plan, le PDF et l'EPUB sont générés. Perdre neuf chapitres
parce que le dixième a dépassé n'aurait aucun sens. L'usine s'arrête ensuite :
c'est **votre** plafond, c'est à vous de le lever.

## Quand les fournisseurs se taisent : attendre, puis finir

Les quotas gratuits des fournisseurs ne sont pas votre budget. Ils se vident
en pleine fabrication, et ils se remplissent seuls — au bout d'une minute pour
un 429, à minuit UTC pour un quota du jour.

Journal réel du 16/09/2026, roman de dix-huit scènes : tous les fournisseurs
épuisés à la huitième, dix scènes à écrire. L'usine marquait alors la niche
**« faite »** et s'arrêtait. Le roman attendait sur le disque, inachevé, qu'on
pense à appuyer sur « Reprendre ». Pour une usine dont la promesse est
« appuyer sur Générer et rien d'autre », c'était la panne la plus probable,
et la plus silencieuse.

Désormais, un produit resté inachevé **repart en tête de file**, avec de quoi
reprendre *ce* produit plutôt qu'en fabriquer un autre. L'usine demande au
routeur quand un fournisseur rouvrira (`llm.prochaine_ouverture`) — il le sait
sans rien deviner : ce sont les repos qu'il a lui-même posés, par fournisseur
et par clé, et les quotas du jour — puis elle attend, et finit le produit
depuis son carnet :

```
[1] ebook — « la facturation des independants »
    [!] 1 section(s) non ecrites : conclusion. Le produit reste inacheve — ...
  inacheve : 1 section(s) a ecrire — il repart en tete de file et sera fini automatiquement.
  plus rien a demander aux fournisseurs : reprise automatique vers 22:59 (5 min).
[1] ebook — « la facturation des independants »
  reprise du produit inacheve, depuis son carnet (1 section(s) a ecrire)
  livre : « Le systeme du freelance rentable » — note 3.79/10 en 0 s
```

(Journal du scénario de `tests/test_reprise_auto.py`, fournisseurs coupés au
neuvième appel, routeur annonçant une réouverture dans cinq minutes.)

Trois garde-fous :

- **Un plancher.** Le routeur ne voit ni un réseau coupé ni un crédit épuisé
  sans repos posé : pour lui, le fournisseur paraît ouvert. « Tout de suite »
  n'est donc pas une promesse, et l'attente vaut au moins une minute, puis
  cinq, quinze, trente, une heure tant que les reprises ne font rien avancer.
- **Le verrou de veille est relâché pendant l'attente.** Elle peut durer
  jusqu'à minuit UTC ; garder le téléphone éveillé pour ne rien calculer
  viderait la batterie. Android peut endormir Termux, et l'attente se termine
  au premier réveil après l'heure.
- **Renoncer, mais seulement quand rien ne s'épuisait.** Une section qui
  échoue trois reprises de suite alors que les fournisseurs répondent ne
  réussira pas à la quatrième : la niche sort de la file, le produit reste
  inachevé, et le journal dit d'essayer `usine reprendre` à la main. Un quota
  vide, lui, se remplit — attendre est la bonne réponse, aussi longtemps qu'il
  le faut.

Et si aucun fournisseur ne peut revenir — aucune clé, aucun serveur local qui
écoute — l'usine le dit et s'arrête ; la niche attend en tête de file la
prochaine session.

## Ce que la boucle oubliait de faire

Le tableau de bord et l'usine continue reçoivent la même chose — un type, un
sujet, des options — et fabriquaient chacun à sa façon. Mesure du 23/09/2026,
mêmes réglages activés des deux côtés :

| Réglage « à chaque produit » | tableau de bord | usine continue |
|---|---|---|
| `relecture_ensemble` | 1 | **0** |
| `archive_auto` | 1 | **0** |
| `marketing_auto` | 1 | **0** |

La boucle — précisément là où l'on fabrique sans surveiller — ignorait aussi
les chapitres, les mots et l'auteur passés en options. Les deux portes passent
maintenant par `pipelines/porte.py`, qui n'invente rien : c'est ce que faisait
le tableau de bord, sorti de son fichier.

## Piloter

```bash
usine usine statut      # depuis n'importe quel terminal, même pendant la production
usine usine arreter     # termine le produit en cours, puis s'arrête
```

`Ctrl+C` fait la même chose : le produit en cours est terminé et exporté. Un
second `Ctrl+C` coupe immédiatement — le travail non exporté est alors perdu,
mais la niche reste en file.

Un seul processus à la fois : un verrou PID l'empêche. Si Android a tué
l'usine, le verrou est détecté comme orphelin et nettoyé automatiquement au
lancement suivant.

## Le mode automatique

```bash
usine usine demarrer --auto
```

Quand la file se vide, l'usine explore de nouvelles niches à partir des sujets
qui ont donné vos **meilleures notes** — c'est la seule base dont elle dispose,
et elle vaut mieux qu'un tirage au hasard. Sans historique, elle vous le dit et
s'arrête plutôt que d'inventer.

## Sur Termux

Android suspend les applications en arrière-plan. L'usine prend donc
elle-même le **verrou de veille** au démarrage de la session et le relâche à
la fin — y compris après un `Ctrl+C`. Il n'y a plus rien à taper autour :

```bash
nohup usine usine demarrer --max 5 > ~/usine.log 2>&1 &
usine usine statut          # suivre depuis un autre onglet
tail -f ~/usine.log
```

Ajoutez aussi Termux aux applications non optimisées :
*Paramètres → Applications → Termux → Batterie → Sans restriction*.

Si l'usine est tuée malgré tout, relancez la même commande : la file reprend,
et le cache restitue ce qui avait déjà été généré sans reconsommer un appel.

### La batterie, et savoir que c'est prêt

Avec `termux-api` installé (paquet **et** application Termux:API — voir
[TERMUX.md](TERMUX.md)), deux choses changent pour une session qui dure :

- **l'usine s'arrête sous 20 % de batterie**, entre deux produits, la file
  intacte. Une usine qui tourne jusqu'à l'extinction laisse un produit à
  moitié écrit et un téléphone mort. Un téléphone **en charge** ne déclenche
  rien : son niveau monte ;
- **une notification** annonce chaque produit livré, puis la fin de session.
  La taper ouvre le PDF. Les notifications se remplacent l'une l'autre :
  dix produits laissent une ligne dans le volet, pas dix.

Sans `termux-api`, aucune des deux ne se produit et rien ne casse.

## Réglages utiles

| Réglage | Défaut | Effet |
|---|---|---|
| `budget_appels_jour` | 250 | plafond global sur 24 h |
| `budget_appels_produit` | 80 | plafond par produit |
| `budget_produits_jour` | 3 | nombre de produits par jour |
| `budget_minutes_produit` | 45 | durée maximum d'un produit |
| `budget_jetons_jour` | 0 | jetons IA par jour, tous fournisseurs confondus — plusieurs paliers gratuits comptent ainsi plutôt qu'en requêtes |
| `pause_entre_produits` | 60 | secondes entre deux produits, pour laisser respirer les quotas par minute |
| `batterie_minimum` | 20 | % de batterie sous lequel la session s'arrête (0 = jamais) |
| `notifications` | oui | notification Android à chaque produit livré |
| `verrou_veille` | oui | empêche Android d'endormir la fabrication |

## Depuis le téléphone

Le menu (`usine`, sans argument) expose tout cela sans une seule option à
taper : **Usine continue** → ajouter une niche, voir la file, démarrer,
arrêter, régler le budget.

Le tableau de bord (`usine web`) affiche la file en direct, permet d'ajouter
ou retirer une niche, et de démarrer ou arrêter l'usine depuis le navigateur.

## Deux usines ne tournent jamais ensemble

Le verrou était pris en deux temps — vérifier qu'il est libre, puis l'écrire —
avec un intervalle entre les deux. **Deux `usine usine demarrer` lancées dans
la même seconde le voyaient toutes deux libre**, et la seconde écrasait le PID
de la première.

Le dégât n'est pas théorique : `usine usine arreter` ne visait plus qu'un des
deux processus, et l'autre continuait à consommer le budget d'appels et à
tirer sur la même file — deux produits pour la même niche, et un plafond
d'appels franchi sans que personne l'ait demandé.

La prise est maintenant une **création exclusive** : c'est le système de
fichiers qui tranche, pas nous. Un verrou orphelin — Android tue les processus
sans préavis — est toujours repris, sinon la moindre coupure interdirait toute
production jusqu'au prochain redémarrage.

