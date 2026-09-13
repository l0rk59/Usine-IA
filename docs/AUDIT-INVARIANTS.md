# Audit par invariants — septembre 2026

Une seule méthode, appliquée quatorze fois : **choisir une propriété que le
dépôt prétend tenir, la mesurer sur tout le code, corriger ce qui manque, puis
poser le garde-fou qui empêche la récidive.**

Mesurer plutôt que supposer, parce que les trois quarts de ce qui suit étaient
invisibles à la lecture. Et poser le garde-fou, parce qu'une correction sans
garde-fou revient dans les six mois.

---

## Ce que les mesures ont trouvé

| Invariant | Mesuré | Trouvé |
|---|---|---|
| Options du catalogue proposées par le menu | 8 options | **1 sur 8** |
| Commandes CLI atteignables depuis le menu | 32 commandes | 1 manquante |
| Notes de `docs/` référencées quelque part | 22 notes | 2 orphelines |
| Fonctions publiques avec un appelant | ~400 | **6 mortes** |
| Imports employés | tous les modules | **17 inutiles** |
| Événements publiés ayant un consommateur | 9 événements | 2 sans destinataire |
| Routes servies ayant un appelant | 20 routes | 1 sans appelant |
| Quotas comptés par clé | pool de clés | **le pool ne multipliait rien** |
| Un secret ne se change pas par la surface qu'il garde | `POST /api/reglages` | **le jeton du tableau de bord** |
| Un nom de fichier ne vient pas d'une chaîne libre | `usine journal <jour>` | traversée de répertoire |
| Un journal ne remplit pas le téléphone | `core/trace.py` | taille non bornée |
| Une refabrication n'écrit que dans l'atelier | `--rafraichir` | dossier non vérifié |
| Arguments communs de la CLI branchés | 18 arguments | rien |
| Champs de `Provider` lus | 14 champs | rien |
| Réglages déclarés branchés | 26 réglages | rien |
| Tables du schéma lues *et* écrites | 12 tables | rien |
| Modules de test isolant leur atelier | 38 modules | rien |
| TODO en souffrance | tout le code | rien |

Les six dernières lignes comptent autant que les autres : **elles disent que
les garde-fous existants font leur travail.** Un audit qui ne rapporte que ses
trouvailles ne dit pas si le reste tient.

---

## Les trois défauts qui coûtaient le plus

### Le pool de clés ne multipliait rien

Sa raison d'être tient en une phrase : *ne jamais s'arrêter pour cause de
quota.* Il ne l'obtenait pas.

```
quota d'UNE cle : 1000 requetes/jour
cle A a consomme : 1000
cle B a consomme : 0
le routeur declare groq utilisable ? -> False
```

Les plafonds d'un fournisseur s'appliquent à un **compte**, donc à une clé ; le
routeur les comptait pour tout le fournisseur. Sur le débit par minute, deux
clés se **freinaient l'une l'autre** — le pool ralentissait la production au
lieu de l'accélérer.

### Six leviers n'existaient que dans la ligne de commande

Le catalogue déclare une option par type de produit : relire le livre entier,
produire le script de narration, poser une marge de reliure… La vraie porte
d'entrée de cette usine est un menu sur un téléphone, et **une seule de ces
options y était proposée**. Quelqu'un qui fabriquait un cahier broché depuis
son canapé ne pouvait pas poser de marge de reliure — et son intérieur perdait
ses premiers caractères dans la pliure.

C'est le défaut du réglage orphelin déplacé d'un cran : le réglage orphelin est
affiché et jamais lu, l'option inaccessible est lue et jamais proposée.

### Le tableau de bord pouvait effacer le mot de passe qui le protège

`POST /api/reglages` acceptait tout réglage déclaré, `jeton_web` compris. Qui
atteignait la page pouvait s'y enfermer en posant un jeton, ou l'ouvrir à tous
en l'effaçant. **Un identifiant ne se change jamais par la surface qu'il
garde** — c'est laisser la porte décider de sa propre serrure.

---

## Ce que l'audit a appris sur les tests

Sept garde-fous écrits pendant cet audit ne gardaient rien à leur première
version. Le motif se répète, et il mérite d'être nommé : **ils lisaient le
texte du code au lieu d'observer son comportement.**

- Le garde des options du menu cherchait le nom de l'option dans le source —
  il se satisfaisait d'un commentaire. Il pilote maintenant le menu par son
  entrée standard, comme un doigt sur un écran.
- Le garde des routes cherchait l'URL n'importe où dans la page, et se
  satisfaisait du commentaire qui expliquait justement que personne ne
  l'appelait. Il ne regarde plus que les `fetch` et les `EventSource`.
- Le garde des sous-menus vérifiait qu'une entrée « ne lance aucune commande »
  — ce qui est vrai d'un sous-menu comme d'une branche vide.
- Le détecteur d'imports inutiles cherchait le nom dans tout le fichier, ligne
  d'import comprise : chaque import se justifiait lui-même.

Deux autres échecs, d'une autre nature :

- Un test **dépendait de l'ordre de ses voisins** : unittest classe les
  méthodes alphabétiquement, et l'assertion « le tome 1 ne connaît pas le tome
  2 à sa naissance » lisait un fichier qu'un test précédent avait déjà
  rafraîchi.
- Un test était **ignoré** faute de couverture dans l'atelier de test. Un test
  ignoré ne garde rien.

Et un commentaire de ma main affirmait qu'un `flush()` explicite protégeait
d'un processus tué sans préavis. C'est faux : la fermeture du bloc vide déjà le
tampon, et aucune mutation ne distinguait les deux versions. La vraie
protection est d'ouvrir et refermer à chaque ligne.

---

## L'état à la clôture

| | |
|---|---:|
| Code | 24 423 lignes |
| Tests | 13 822 lignes, **976 tests** |
| Chaînes de production | 10 |
| Commandes `usine` | 32 |
| Skills du projet | 8 |
| Dépendances hors bibliothèque standard | **0** |

Aucun test n'a cassé en retirant les six fonctions mortes. C'est précisément la
preuve qu'elles ne protégeaient personne — et la raison pour laquelle « laissé
pour éviter du brassage » était un mauvais motif. Une fonction gardée au cas où
est une fonction qu'on ne supprimera jamais, parce que le cas n'arrive pas et
que personne n'osera décider.

La liste d'exemptions du garde-fou est **vide**. Y ajouter un nom demandera
d'écrire pourquoi.
