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
