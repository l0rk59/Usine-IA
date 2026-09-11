# Tester des titres et des couvertures

```bash
usine ab creer --produit ebook-xxx --sur titre -n 5
usine ab creer --titre "Mon titre actuel" --sur couverture -n 4
usine ab observer 2 --vues 910 --actions 58
usine ab verdict 1
```

## Le chiffre à connaître avant de commencer

**À 5 % de conversion, détecter un écart de 20 % demande environ 7 600 vues
par variante.** À 2 %, il en faut 19 600. À 1 %, près de 40 000.

Un vendeur qui fait 300 vues par mois n'atteindra jamais ce seuil. Ce n'est
pas une limite de cet outil : c'est la quantité d'information nécessaire pour
distinguer un vrai effet du hasard.

La conséquence est assumée : **l'usine refuse de désigner un gagnant** tant
que les données ne le permettent pas. Un outil qui annonce « B gagne » après
40 visiteurs fabrique de la fausse certitude, et vous fait refaire une
couverture pour rien — en vous laissant convaincu d'avoir compris votre marché.

Exemple réel, produit par l'outil :

```
[A] Facturer mieux en travaillant moins       140 vues   5 ventes   3.6%    9%
[B] Le systeme en 7 etapes du freelance       155 vues   9 ventes   5.8%   47%
[C] Pourquoi votre agenda se vide             130 vues   4 ventes   3.1%    6%

INDECIS
Aucune variante ne se detache (47 % pour la mieux placee).
```

B fait presque le double de C. Et pourtant : rien à conclure. Avec ces
effectifs, cet écart apparaît par hasard une fois sur deux.

## Ce que l'outil vous apporte vraiment

**La génération de variantes vraiment différentes.** Chaque titre est écrit
sur un angle imposé et distinct — bénéfice, méthode, problème, contraste,
audience nommée, délai, question, preuve. Puis l'outil **vérifie** que le
résultat est distinct : si deux variantes partagent plus de 55 % de leur
vocabulaire significatif, il le dit et régénère.

C'est le contrôle que les outils d'A/B testing oublient. Comparer cinq
reformulations du même titre ne révélera jamais rien, quelle que soit la durée
du test.

**Le diagnostic local de chaque titre**, sans appel IA : longueur, présence
d'un chiffre, d'un délai, d'une audience nommée, de mots creux
(« ultime », « révolutionnaire », « secret »), de majuscules excessives. Ce
sont des faits, pas une prédiction de taux de clic — personne ne sait prédire
un CTR à partir du texte seul.

**La planche de comparaison.** Une page HTML qui met les variantes côte à
côte, lisible sur téléphone. Comparer quatre couvertures en ouvrant quatre
fichiers l'un après l'autre ne permet pas de choisir ; les voir ensemble, si.

## La méthode statistique

Modèle beta-binomial. Chaque variante reçoit une postérieure
Beta(1 + succès, 1 + échecs) — l'a priori uniforme signifie « je ne sais rien
avant de mesurer ». Le tirage est **conjoint** sur toutes les variantes, ce qui
évite le piège des comparaisons multiples : avec cinq variantes, comparer deux
à deux gonfle mécaniquement les chances de trouver un gagnant qui n'existe pas.

Vous obtenez pour chaque variante :

| Sortie | Sens |
|---|---|
| taux observé | ce que vous avez mesuré |
| intervalle crédible 90 % | la fourchette où se trouve vraiment le taux |
| P(meilleure) | probabilité que cette variante soit la meilleure de toutes |
| perte espérée | ce que vous risquez de perdre en la choisissant |

Verdict :

| État | Condition |
|---|---|
| **gagnant** | P ≥ 95 % **et** perte espérée ≤ 0,5 point |
| **tendance** | P ≥ 80 %, insuffisant pour trancher |
| **indécis** | aucune ne se détache |
| **insuffisant** | moins de 25 actions au total |
| **sans données** | rien n'a encore été observé |

Le tirage est graîné : deux lectures des mêmes données donnent le même
verdict. Un résultat qui changerait d'un appel à l'autre serait indéfendable.

La formule exacte `probabilite_superieure()` sert de contre-vérification au
tirage dans les tests : deux méthodes indépendantes qui concordent valent
mieux qu'une seule qu'on croit sur parole.

## Comment collecter des chiffres sans plateforme d'A/B testing

Gumroad et Etsy ne permettent pas de découper le trafic. La méthode réaliste :

1. Publiez la variante A pendant une semaine. Relevez vues et ventes.
2. Remplacez par la variante B la semaine suivante. Relevez à nouveau.
3. Reportez : `usine ab observer <id> --vues 120 --actions 4`

Les relevés s'additionnent, vous pouvez donc reporter chaque semaine.

**Limite honnête de cette méthode :** un test séquentiel confond l'effet du
titre avec celui de la période. Une semaine de vacances scolaires ou un partage
inattendu fausse la comparaison. Alternez les variantes sur plusieurs cycles
plutôt que de faire une seule semaine chacune.

## Les couvertures testées sont vendables

Ce test comparait jusqu'ici des images générées par Pollinations. **Vérifié,
deux fois :** au palier anonyme, ce service appose un filigrane
`pollinations.ai` sur chaque image, et le paramètre `nologo` que mentionne sa
documentation n'a aucun effet sans jeton.

On choisissait donc entre quatre propositions dont aucune ne pouvait être
vendue — un test dont le gagnant était inutilisable.

Les huit directions visuelles sont désormais des combinaisons palette × mise
en page de l'atelier local : PNG 1200 × 1800, sans filigrane, prêtes à
téléverser. **Ce qui gagne le test est ce qui part chez l'acheteur.** Voir
[COUVERTURE.md](COUVERTURE.md).

## Les chiffres viennent des ventes, plus de la saisie

Reporter à la main les ventes de chaque variante était la partie la plus
pénible et la plus facile à rater. Elle n'est plus nécessaire.

```bash
usine ab periode 3 --du 2026-07-01 --au 2026-07-30
usine ab periode 4 --du 2026-08-01
usine ab rythme 1
```

Une fois la période de mise en ligne renseignée, l'usine attribue à chaque
variante les ventes réellement encaissées pendant qu'elle était affichée.
`usine ab observer --vues 800` reprend le nombre d'actions de cette source au
lieu de vous le faire compter.

### Les vues, elles, ne sont dans aucun export

Il faut aller les relever à l'écran. **L'usine ne les invente pas** — elle
compte ce qu'elle a et dit ce qui lui manque.

### Comparer sans les vues

Ce qu'un vendeur possède sans effort, c'est le nombre de ventes et la durée
pendant laquelle chaque variante était en ligne. Comparer « 7 ventes en 14
jours » à « 4 ventes en 12 jours » n'est **pas un problème binomial** : il n'y
a pas d'essais, il y a un comptage sur une durée. Le modèle qui convient est
gamma-poisson.

| | Modèle | Ce qu'il exige |
|---|---|---|
| `usine ab verdict` | beta-binomial | vues **et** actions |
| `usine ab rythme` | gamma-poisson | ventes **et** durée d'exposition |

La loi a priori est `Gamma(1, 0)` — plate sur le rythme — et la loi a
posteriori `Gamma(1 + ventes, durée)` reste propre dès que la durée est non
nulle. Sa forme entière permet de **vérifier le tirage aléatoire contre une
formule exacte**, exactement comme pour le beta-binomial : les tests comparent
les deux sur six jeux de données.

Le seuil porte sur le nombre de **ventes**, jamais sur la durée. Dix jours
d'exposition sans vente ne renseignent sur rien, et laisser le temps tenir
lieu de preuve serait le principal piège de ce modèle.

### Ce que ce test ne peut pas réparer

**Il est séquentiel.** Les variantes n'ont pas été exposées en même temps. Une
semaine de vacances scolaires ou un partage inattendu se confond avec l'effet
du titre, et aucun calcul ne corrige cela. L'usine l'affiche à chaque verdict.
Alternez les variantes sur plusieurs cycles plutôt que de leur donner une
seule période chacune.

## Depuis le téléphone

Le menu (`usine`, sans argument) → **Tests A/B** : créer des variantes,
reporter les chiffres variante par variante, lire le verdict. Aucune option à
retenir.
