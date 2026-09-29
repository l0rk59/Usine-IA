# Audit d'organisation et de câblage

*15/09/2026. Demandé ainsi : « il doit y avoir des choses mal construites,
dans l'organisation, le câblage et tout le reste, ne laisse aucune ligne de
code à l'abandon ».*

Méthode : **compter, pas lire**. Chaque question posée à l'arbre syntaxique,
à l'analyseur d'arguments réel, ou au navigateur — jamais à l'impression que
donne le code.

Point de départ : **88 modules, 33 503 lignes, 1 077 fonctions.**

---

## Ce qui a été trouvé, et corrigé

### 1. Trois corps de fonction écrits deux fois

Un *nom* partagé ne prouve rien : `produire` est un protocole, chaque chaîne
a le sien. Ce qui coûte, c'est la **copie**. La mesure compare la structure
du corps — deux copies qui diffèrent par un commentaire ou un nom de variable
locale restent deux copies.

| | |
|---|---|
| `_assurer` | identique dans `core/file.py` et `core/apprentissage.py` |
| `_oublier` | identique dans `file.py`, `apprentissage.py`, `experience.py` |
| `journal` | **cinq fois** dans `web/serveur.py`, à l'octet près |

Les deux premiers sont le même mécanisme : créer ses tables au premier usage,
et remettre le drapeau à zéro quand la base change. Trois copies d'un
mécanisme de remise à zéro, c'est trois endroits où corriger le jour où il se
trompe, et deux qu'on oubliera — or ce mécanisme existe précisément parce
qu'un drapeau qui ment sur une base restaurée est un défaut invisible.
`store.tables_a_la_demande()` les remplace.

Le troisième enchaîne trois choses qui doivent le rester : le verrou,
l'expurgation des clés, la publication. Le jour où l'une manque à une copie,
**une clé d'API part dans le journal d'un seul type de travail**, et rien ne
le dit.

Après correction : `aucun`.

### 2. Une nouvelle de trois scènes en annonçait six

Le titre d'une scène est ajouté par la chaîne. Un titre laissé dans le corps
en fabrique un second, qui entre au sommaire du PDF et dans la navigation de
l'EPUB.

```
# Scene modele 1
## Le principe de base     ← fantôme
# Scene modele 2
## Le principe de base     ← fantôme
```

La consigne interdisait déjà ces titres ; le nettoyage ne rattrapait que le
cas où le modèle **commençait** par là. Il couvre maintenant tout le corps —
et le même `sans_titres` sert aux six chaînes de fiction, au lieu des deux
copies qui commençaient à apparaître.

Ce défaut touchait `nouvelle` et `roman`, c'est-à-dire les deux types de
fiction les plus anciens.

### 3. La recherche de fiction n'existait qu'en ligne de commande

Traité dans son propre commit. Rappelé ici parce que c'est le défaut qui a
motivé le contrôle de parité ci-dessous.

---

## Ce qui a été mesuré et n'a rien donné

Une mesure qui ne trouve rien est un résultat, pas un échec. Et deux de mes
détecteurs ont d'abord **accusé à tort** — ce qui est la chose à ne pas
livrer.

| mesure | résultat |
|---|---|
| modules jamais importés | un seul, `usine/__main__.py`, qui est le point d'entrée |
| boutons du tableau de bord sans écouteur | aucun |
| options du catalogue jamais lues | aucune (invariants déjà en place) |
| fonctions publiques sans appelant | aucune (invariant déjà en place) — mais voir ci-dessous |
| docs citant du code disparu | **aucune** — voir ci-dessous |

**« Aucune fonction sans appelant » ne regardait que les fonctions
publiques.** Le 25/09/2026, `cli._detailler_local` était sans appelant depuis
treize jours : c'est elle qui vérifiait qu'un ollama servait un modèle, et
`usine docteur` disait « prêt » à un ollama vide. Le tiret bas dit « pas pour
les autres modules », pas « appelée par quelqu'un ». Le détecteur couvre
désormais les fonctions privées et les méthodes ; il en a trouvé deux autres,
retirées : `feuilleton._phrases`, jamais appelée depuis sa création, et
`Provider.api_key`, qui lisait une clé en contournant le pool. Seules restent
exemptées les méthodes que la bibliothèque standard appelle par leur nom
(`do_GET`, `handle_starttag`…), et la liste est nommée dans le test.

**Mon détecteur de docs a accusé 26 fois, et il avait tort 26 fois.** Il
comparait les chemins à la racine du dépôt, alors que les notes citent
`core/llm.py` relativement à `usine/`. Corrigé, il en restait 19 — tous des
noms de fichiers **produits** (`bible.json`, `quiz.html`, `index.html`), pas
des sources. Le dernier, `web/modele.py`, est cité par `TYPES-PRODUITS.md`
comme *code mort supprimé* : la note a raison.

Un détecteur incapable de distinguer un chemin de source d'un nom de fichier
produit crierait à tort à chaque nouvelle note. Il n'est pas livré.

---

## Ce qui reste volontairement hors du navigateur

Deux commandes n'existent qu'en ligne de commande, et c'est un choix :

| | |
|---|---|
| `usine specs` | écrit `SPECS-APPAREIL.md` à la racine du dépôt, pour le pousser — sur le téléphone seulement ; ailleurs, dans l'atelier |
| `usine prompts-systeme` | exporte des fichiers à éditer dans un éditeur de texte |

Ce sont des gestes de mainteneur. Un bouton sur un téléphone n'y changerait
rien. La liste est **dans le test**, chaque entrée porte sa raison, et un
second contrôle vérifie qu'aucune n'y désigne une commande disparue — une
exception périmée est un mensonge tranquille : elle laisse croire qu'on a
examiné le cas.

---

## Ce que l'audit laisse derrière lui

Un audit qui corrige laisse le dépôt propre un jour. Un audit qui laisse un
**détecteur** le laisse propre. Quatre sont ajoutés (`test_audit_organisation`) :

1. aucun corps de fonction n'est écrit deux fois ;
2. chaque commande est atteignable depuis le navigateur, ou figure dans les
   exceptions avec sa raison ;
3. aucun bouton du gabarit n'est sans écouteur ;
4. les chaînes de fiction retirent tous les titres — vérifié sur l'**appel**,
   pas sur le nom.

### Un détecteur vert ne se garde pas lui-même

La campagne de mutation l'a montré sans appel : **cinq mutations sur neuf ne
faisaient échouer personne.** Neutraliser un détecteur qui n'a rien à trouver
ne casse rien.

Chacun a donc son **témoin** : un cas fabriqué qu'on lui montre accuser. Et
la première version de ces témoins ne valait rien non plus — ils
*recopiaient* le calcul au lieu de l'appeler, si bien que neutraliser celui
du test laissait le témoin vert. La détection est maintenant dans une méthode
unique, appelée par le test **et** par son témoin.

C'est la même leçon que le dépôt retrouve partout, appliquée cette fois aux
outils de l'audit : *un garde-fou satisfait par une homonymie ne garde rien*
— et un témoin qui refait le calcul ne garde que sa propre copie.
