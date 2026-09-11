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

## Le filigrane des couvertures

**Vérifié :** au palier anonyme, Pollinations appose un filigrane
« @pollinations.ai » sur chaque image. Le paramètre `nologo` que mentionne la
documentation **n'a aucun effet** sans jeton — la réponse est identique octet
pour octet avec ou sans lui.

Conséquence pratique :

- les couvertures générées en ligne servent à **choisir une direction
  visuelle**, pas à être vendues ;
- pour une couverture livrable, utilisez `--sans-image` : les couvertures SVG
  sont générées localement, sans filigrane, et vous appartiennent entièrement ;
- ou fournissez votre propre illustration.

L'usine vous prévient au moment de créer un test de couvertures.

## Depuis le téléphone

Le menu (`usine`, sans argument) → **Tests A/B** : créer des variantes,
reporter les chiffres variante par variante, lire le verdict. Aucune option à
retenir.
