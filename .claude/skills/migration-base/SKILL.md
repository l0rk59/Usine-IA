---
name: migration-base
description: Faire evoluer le schema SQLite de l'atelier sans detruire ce que l'utilisateur a deja produit. A utiliser des qu'on ajoute une colonne, une table ou un index a usine/core/store.py, ou a une table creee a la demande (file, experiences, apprentissage). A utiliser aussi devant une erreur « no such column » ou « no such table » chez quelqu'un d'autre, devant un import de sauvegarde qui refuse une archive, ou quand on se demande pourquoi une table existe chez soi et pas chez un utilisateur.
allowed-tools: Bash, Read, Edit, Grep
---

# Changer le schema sans perdre l'atelier

C'est le seul endroit du depot ou une erreur detruit des donnees que personne
ne peut reconstituer : l'historique de production, les ventes saisies et les
empreintes anti-doublons vivent sur le telephone de l'utilisateur, et nulle
part ailleurs.

Le piege est que **le defaut ne se voit pas chez qui developpe.** Une base
creee ce matin a deja toutes ses tables ; elle saute les paliers. La panne
apparait des semaines plus tard, chez quelqu'un d'autre, sous la forme d'un
`no such column` en pleine fabrication.

## La regle

`CREATE TABLE IF NOT EXISTS` suffit pour une base neuve et **reste sans effet
sur une base existante**. Toute evolution s'inscrit donc aussi dans l'echelle
de migrations.

Trois gestes, dans cet ordre, dans `usine/core/store.py` :

1. **Modifier `SCHEMA`** — c'est ce que verra une installation neuve.
2. **Incrementer `VERSION_SCHEMA`.**
3. **Ajouter le palier dans `MIGRATIONS`**, sous le nouveau numero.

```python
VERSION_SCHEMA = 5

MIGRATIONS = {
    # v4 -> v5 : <ce que le palier ajoute, et pourquoi>
    5: ["CREATE TABLE IF NOT EXISTS ...",
        "CREATE INDEX IF NOT EXISTS ..."],
}
```

Un palier peut aussi etre une **fonction** quand l'ordre SQL ne suffit pas —
par exemple quand la table visee est creee a la demande par un autre module et
peut ne pas exister :

```python
4: [lambda conn: _ajouter_colonnes(
    conn, "variantes", (("debut", "TEXT"), ("fin", "TEXT")))],
```

## Ce qui compte vraiment

**Une colonne s'ajoute par `ALTER`, jamais par une redefinition.** C'est le
seul cas que l'echelle traite et que le schema ne peut pas : `CREATE TABLE IF
NOT EXISTS` ne touche pas une table deja creee. Passer par
`_ajouter_colonnes`, qui verifie d'abord que la table existe et que la colonne
manque.

**Ne jamais recreer une table pour la « mettre a jour ».** Un `DROP` puis
`CREATE` rend le schema correct et l'atelier vide. La migration a reussi, et
l'utilisateur a tout perdu.

**`base_neuve` se mesure AVANT `executescript(SCHEMA)`.** Apres, toutes les
tables existent et une base d'hier ressemble a une base de ce matin. C'est ce
que fait `connect()` en comptant la table `produits` avant d'executer le
schema. Ne pas deplacer cette mesure.

**Un palier numerote au-dela de `VERSION_SCHEMA` ne s'execute jamais.** Il est
ecrit, commite, et ne tourne chez personne. Un test le refuse.

## Les tables creees a la demande

`core/file.py`, `core/experience.py` et `core/apprentissage.py` creent leurs
tables au premier usage et retiennent « c'est fait » chacun de leur cote. Ces
drapeaux doivent tomber quand la base change sous eux — c'est ce
qu'orchestre `store.oublier_avec_la_base()`. Un module qui pose sa propre
table sans s'enregistrer la produira une fois, puis croira eternellement
qu'elle existe : apres une restauration de sauvegarde, la premiere requete
leve `no such table`.

## Verifier

Les tests vivent dans `tests/test_atelier.py`, classe
`TestEchelleDeMigrations`. Ils fabriquent une base **vraiment ancienne** —
tables du palier vise, `PRAGMA user_version` a la main — puis la font monter.

Ajouter un cas pour le nouveau palier, sur le modele de
`test_une_colonne_ajoutee_par_un_palier_apparait`. Deux pieges appris en
ecrivant ces tests :

- **Verifier la presence d'une table ne prouve rien.** Les paliers 2 et 3 ne
  font que creer des tables, et le `CREATE TABLE IF NOT EXISTS` du schema les
  recree de toute facon. Un tel test passe meme si l'echelle ne tourne pas.
  C'est la **colonne** ajoutee a une table existante qui distingue les deux.
- **Verifier que les donnees d'avant sont encore la**, pas seulement que le
  schema est correct. Une migration qui recree proprement en perdant tout
  passerait le premier controle.

Puis, parce qu'un test qui n'a jamais echoue ne garde rien — skill
`mutation` :

```bash
python3 .claude/skills/mutation/scripts/muter.py campagne.json
```

Mutations qui doivent toutes etre vues : retirer l'appel a `_migrer`, forcer
`neuve = True`, vider la boucle des paliers, retirer l'ecriture de
`user_version`.

## Sauvegardes

`core/sauvegarde.py` inscrit `VERSION_SCHEMA` dans l'archive et **refuse une
archive plus recente que le code** — restaurer une base d'une version future
donnerait un schema que le code ne comprend pas. Incrementer
`VERSION_SCHEMA` rend donc les anciennes archives restaurables (elles
repassent par l'echelle) et les futures refusees. C'est le sens voulu.
