# Ce que l'acheteur trouve dans l'archive

## La mesure

Les neuf chaînes, fabriquées avec `--zip`, et le contenu du ZIP comparé à ce
que chacune déclare livrer :

```
chaine       déclare  dans zip  en trop dans l'archive
ebook              5         9  carnet.json, rapport-qualite.json
formation          8        10  carnet.json
prompts            5         8  carnet.json
outils             5         8  carnet.json
social             5         8  carnet.json
modeles            8        12  carnet.json, systeme.json
impression         3         7  cahier.json, carnet.json
logiciel           5         9  carnet.json, verification.json
nouvelle           5        11  bible.json, carnet.json, continuite.json,
                                rapport-qualite.json
```

**Les neuf.** Sans exception.

L'acheteur ouvrait l'archive et y trouvait `rapport-qualite.json`, qui porte la
note interne de son propre produit — **3,79/10** dans la mesure — et la liste
de ses défauts. Et `carnet.json`, qui contient le texte de chaque section et la
ligne de commande exacte qui a fabriqué le produit.

## La cause n'est pas un oubli, c'est une forme

```python
FICHIERS_INTERNES = ["plan.json", "programme.json", "boite.json",
                     "produit.json", "idees.json"]
```

Une liste de noms, tenue à la main, écrite une fois. Elle ne connaît que le
passé : `carnet.json` est arrivé avec la reprise, `rapport-qualite.json` avec
le contrôle qualité, `bible.json` et `continuite.json` avec le roman. Chacun a
été ajouté dans un autre fichier, des mois plus tard, par quelqu'un qui ne
pensait pas à l'empaquetage — et chacun est parti chez des acheteurs.

Une règle « tout sauf une liste noire » demande qu'on pense à la liste **au
moment où l'on ajoute un fichier**. Personne n'y pense. C'est structurel, pas
négligent.

## La règle inverse

Chaque chaîne **déclare déjà** ce qu'elle livre : `terminer()` écrit
`meta["fichiers"]`, et c'est cette liste que le tableau de bord affiche. Elle
est juste, elle est à jour par construction, et personne n'avait pensé à s'en
servir ici.

L'archive se construit désormais à partir d'elle. La liste noire reste, mais
comme **filet** : elle sert aux appels qui n'ont pas la déclaration sous la
main — `usine livrer` sur un produit fabriqué avant que la déclaration
n'existe.

Les trois chemins qui fabriquent une archive — la fin d'une chaîne avec
`--zip`, `usine livrer`, le tableau de bord — passent tous la même liste. Trois
filtres différents finiraient par diverger, et c'est celui qu'on regarde le
moins qui fuirait.

## Et dans l'autre sens

Un filtre qui ne laisse rien passer livrerait une archive vide. Ce qui doit
partir part :

- les fichiers déclarés par la chaîne, **couverture comprise** ;
- `LISEZ-MOI.md` et `LICENCE.txt`, que l'empaquetage écrit lui-même.

## Deux tests qui ne gardaient rien

La campagne de mutation en a trouvé cinq au premier passage. Deux méritent
d'être racontées.

**La liste noire masquait la correction.** J'avais étendu `FICHIERS_INTERNES`
avec les six noms qui fuyaient *en même temps* que j'inversais la règle. Les
tests passaient donc aussi bien avec l'ancienne règle : la liste noire, une
fois complétée, couvrait tous les cas que je vérifiais. Le contrôle porte
maintenant sur un fichier au nom que **personne n'a prévu** — le seul cas
qu'une liste de noms ne peut pas couvrir, et précisément celui qui a fait fuir
les six autres.

**Un test tirait son attente de la chose qu'il contrôlait :**

```python
for nom in FICHIERS_AJOUTES:
    self.assertIn(nom, dans)
```

Vider `FICHIERS_AJOUTES` vide la boucle. Le test passait sur zéro tour pendant
que la notice et la licence disparaissaient de l'archive. Les deux noms sont
maintenant écrits dans le test : ce sont un contrat avec l'acheteur, pas une
variable.

Les huit mutations de la campagne sont vues.
