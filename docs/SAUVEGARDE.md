# Sauvegarder l'atelier

## Ce qui ne se refabrique pas

Les produits se refabriquent : relancez la commande, l'usine les régénère.
**Une année de ventes importées, non.**

Le fichier `atelier/usine.db` contient l'historique de production, les
empreintes qui empêchent de refabriquer deux fois le même livre, les tests A/B
en cours, et les ventes. C'est le seul endroit où ces données existent.

L'usine tourne sur un téléphone. Le dossier de travail est souvent sous
`/sdcard`, qu'une application de nettoyage vide sans prévenir, et Termux se
désinstalle en trois taps.

```bash
usine sauvegarde                      # archive dans atelier/sauvegardes/
usine sauvegarde --vers /sdcard/Download/usine.zip
usine sauvegarde --avec-produits      # + les fichiers livrés (volumineux)
usine sauvegarde --inspecter archive.zip
usine sauvegarde --restaurer archive.zip --oui
```

## Une copie cohérente, pas un copier-coller

La base est copiée par **l'API de sauvegarde de SQLite**, pas par une copie de
fichier. La différence compte : en mode WAL, les écritures récentes vivent dans
un fichier `usine.db-wal` séparé. Copier `usine.db` seul pendant qu'une usine
tourne donnerait une base amputée de ses dernières transactions — et le
problème ne se verrait qu'à la restauration.

## Ce qui n'est pas dans l'archive, et pourquoi

| | |
|---|---|
| **Les clés API** | elles vivent dans `.env`, hors de l'atelier. Les mettre dans une archive qu'on copie sur un ordinateur ou dans un nuage serait le plus court chemin vers une clé divulguée. Un test le vérifie. |
| **Le cache IA** | il se reconstruit, il pèse lourd, et il ne contient rien qu'on ne puisse régénérer. |
| **Les produits** | optionnels : `--avec-produits`. Sans eux, une archive pèse quelques dizaines de kilo-octets. |

## La restauration est réversible

`--restaurer` remplace l'atelier, donc il exige `--oui`. **L'ancienne base
n'est pas supprimée** : elle est renommée `usine-remplacee-<date>.db` à côté.
C'est le genre de commande qu'on lance à une heure où l'on se trompe.

Une archive écrite par une version plus récente de l'usine est **refusée** :
mieux vaut refuser que d'installer un schéma qu'on ne sait pas lire.

## Un défaut trouvé en écrivant ceci

`store._schema_pret` est un drapeau de module qui survivait à la fermeture de
la connexion. Après une restauration, le fichier de base a changé sous nos
pieds — et sans oublier ce drapeau, la reconnexion **sautait la création des
tables et l'échelle de migrations**. Une archive plus ancienne revenait avec
son schéma d'origine, et la première requête sur une table récente échouait,
longtemps après la restauration.

`store.close()` oublie désormais l'état du schéma. Un test le vérifie en
restaurant puis en relisant `PRAGMA user_version`.

### Et ce n'était pas le seul drapeau

`_schema_pret` couvrait les tables déclarées dans `store.SCHEMA`. Trois
modules — la file de production, les expériences A/B et l'apprentissage —
créent les leurs **à la demande**, au premier usage, et retenaient chacun
« c'est fait » dans un drapeau de module identique. Ces trois-là survivaient
toujours à la restauration.

Restaurer une archive écrite avant l'ajout de la file laissait donc le
processus convaincu que `file_production` existait. La table n'était pas
recréée, et la requête suivante levait `no such table: file_production` —
jusqu'au redémarrage, qui « réparait » tout seul le défaut et le rendait
introuvable.

Ces modules s'inscrivent maintenant auprès de `store.oublier_avec_la_base()`,
et `store.close()` fait tomber tous les drapeaux ensemble. Le test construit
une archive dont la base n'a que le schéma de `store`, la restaure, puis
utilise la file : sans l'inscription, il échoue avec exactement l'erreur
ci-dessus.

## Empreintes des produits déjà fabriqués

Les empreintes anti-doublon sont posées **à la fabrication**. Un catalogue
constitué avant leur introduction n'en a aucune — et `usine doublons` n'a donc
rien à comparer chez celui qui en aurait le plus besoin.

```bash
usine doublons --reconstruire
```

relit ce qui est sur le disque, exactement comme la chaîne l'aurait fait en
livrant. Les produits dont le dossier a été déplacé ou supprimé sont nommés,
pas comptés comme vides.

## Depuis le tableau de bord

La carte **Sauvegarder l'atelier** écrit l'archive et, surtout, la
**télécharge**. C'est la partie qui manquait vraiment : sur un téléphone, une
archive écrite dans `atelier/sauvegardes/` ne protège de rien tant qu'elle
n'est pas sortie de l'appareil, et la ligne de commande ne sait pas la sortir.

**Restaurer y est aussi**, mais en deux temps. Un seul geste séparant « je
consulte mes sauvegardes » de « j'efface aujourd'hui » serait trop peu,
surtout au pouce.

1. **Restaurer** sur une archive ouvre un panneau qui dit ce qu'elle contient :
   sa date lisible, son numéro de schéma comparé à celui de l'usine, si les
   réglages y sont, combien de fichiers de produits. On ne remplace pas son
   atelier par quelque chose qu'on n'a pas regardé.
2. Le bouton **Remplacer l'atelier** naît inactif et ne s'active qu'une fois
   la case cochée. Un clic forcé dessus avant cela ne fait rien — c'est
   vérifié dans un vrai navigateur.

Côté serveur, la confirmation est un **argument de la requête**, pas un état
de la page : `confirme` doit valoir exactement `true`. `"oui"`, `1` ou
`"true"` — tous vrais en JavaScript — sont refusés. Une page rechargée, un
rejeu de requête ou un script tiers n'hérite pas d'une case cochée dans un
navigateur que le serveur ne voit pas.

### Faire revenir une archive qui n'est pas sur l'appareil

**Téléverser une archive…** couvre le cas de la réinstallation : le téléphone
a été effacé, et la sauvegarde est sur un ordinateur ou dans un nuage. Ni la
page ni la ligne de commande ne savaient la faire revenir — toutes deux
veulent un fichier déjà là.

Le corps est écrit **par morceaux sur le disque**, jamais gardé en mémoire :
une archive contenant les fichiers de produits pèse plus que ce qu'un
téléphone tient en RAM. Le plafond (200 Mo) est vérifié sur le `Content-Length`
**avant** de lire quoi que ce soit ; sinon un envoi annoncé à dix gigaoctets
remplirait le disque avant d'être refusé.

Ce qui arrive n'est gardé que si c'est lisible : une archive invalide rangée
avec les autres ferait croire à une sauvegarde. Le nom vient de la machine
d'en face, donc c'est un **nom, pas un chemin** — `../../etc/passwd` devient
`passwd.zip` — et un nom déjà pris reçoit un rang plutôt que d'écraser :
remplacer l'archive qui protège par celle qu'on teste serait la pire façon de
recevoir une sauvegarde.

### Une archive peut annoncer bien plus qu'elle ne pèse

`restaurer` lit `usine.db` **d'un seul bloc en mémoire**. Six cents
kilo-octets compressés annonçant six cents mégaoctets suffiraient à faire
tomber le téléphone.

`inspecter` mesure donc les tailles **décompressées annoncées** — celles que
`zipfile` fait respecter à la lecture — et refuse au-delà de 512 Mo pour la
base, 2 Go au total, 100 000 entrées. La borne est dans `sauvegarde`, pas
dans la page : la ligne de commande acceptait déjà n'importe quel chemin.

### Ce que la page refuse de faire

La restauration est refusée tant que **l'usine continue tourne**, qu'une
fabrication est en cours, ou qu'une veille est en route. Remplacer la base
sous un produit en cours de fabrication le ferait écrire dans un atelier qui
n'existe plus. La ligne de commande n'a pas ce garde-fou : elle est tapée
délibérément, la page se touche du pouce.

### Un défaut que seule la page pouvait révéler

Une connexion SQLite appartient au thread qui l'a créée, et `store.close()`
ne ferme **que celle du thread qui appelle**. Or la restauration *déplace* le
fichier de base : les autres threads gardaient une poignée ouverte sur un
fichier qui n'était plus la base de personne.

Le tableau de bord sert chaque connexion HTTP dans son propre thread, et les
garde ouvertes. Restaurer depuis la page affichait donc l'atelier d'avant,
indéfiniment — et ce que ce thread y écrivait partait dans le fichier mis de
côté, **sans la moindre erreur**.

Chaque connexion retient désormais la génération où elle est née, et se refait
quand elle a changé. Le test monte un second thread, lui fait ouvrir sa
connexion *avant* la restauration, et vérifie qu'il voit ensuite le bon
atelier. Sans le correctif, il voit l'ancien.

### La route qui sert les archives ne sert qu'elles

Le dossier des sauvegardes est **à côté** de `usine.db` et de
`reglages.json`. Une sortie de dossier livrerait la base en clair — ventes et
historique compris — à qui a atteint le tableau de bord. La route refuse tout
nom contenant un séparateur, vérifie que le chemin résolu reste sous le
dossier, et ne sert que les fichiers `.zip`. Les trois barrières sont testées,
la dernière parce qu'elle est la seule à empêcher de lire un fichier
quelconque déposé là.

