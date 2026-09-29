---
name: controle-qualite
description: Ajouter ou regler un controle qualite deterministe dans usine/core/controle.py — tics d'ecriture des modeles, promesses de resultat, chiffres sans source, rythme, repetitions. A utiliser quand un produit sort avec un defaut que rien n'a signale, quand on veut mesurer une nouvelle faiblesse du texte genere, quand un controle existant crie a tort ou reste muet, ou quand quelqu'un propose « demandons au modele de se relire ». Vaut aussi pour les controles propres a la fiction (continuite, faits contredits, repliques) dans usine/pipelines/.
allowed-tools: Bash, Read, Edit, Write, Grep
---

# Mesurer plutot que demander

`core/controle.py` note un texte **sans appeler un seul modele**. C'est un
choix, et il a deux raisons.

Un modele qui relit sa propre prose confirme ses erreurs au lieu de les voir :
c'est le meme reseau qui a produit le texte qui juge le texte. Et une mesure
ne coute rien, ne s'epuise pas, ne depend d'aucun quota, et donne le meme
verdict deux fois de suite — ce qu'aucune relecture par modele ne garantit.

La relecture par modele existe ailleurs (`agents/equipe.py`, croisee sur un
autre fournisseur). Elle vient **apres** la mesure, pas a sa place.

## Avant d'ecrire le controle

Trois questions, dans cet ordre. Elles ecartent la plupart des mauvaises
idees.

**1. Le defaut se mesure-t-il ?** « La prose est plate » ne se mesure pas.
« L'ecart-type de la longueur des phrases est inferieur a 4 mots » se mesure,
et dit a peu pres la meme chose — les humains alternent naturellement phrases
courtes et longues, les modeles beaucoup moins.

**2. Le vocabulaire est-il ferme ?** Un controle deterministe reconnait ce
qu'on peut enumerer : une liste de tics, un jeu de couleurs d'yeux, un motif
de pourcentage. Il ne reconnait pas un metier, un lieu de naissance, une
incoherence de motivation. Devant un vocabulaire ouvert, ne pas forcer : soit
le controle ne trouvera rien, soit il inventera.

**3. Le seuil a-t-il ete mesure ?** S'il faut un nombre pour trancher et que
ce nombre sort de l'intuition, **rendre la mesure et ne pas rendre de
verdict**. Un humain regarde. C'est ce que fait `pipelines/voix.py` : il
mesure la longueur des repliques de chaque personnage et refuse de declarer
« ils parlent tous pareil », faute d'un seuil mesure sur de la fiction reelle.
Une mesure honnete vaut mieux qu'un verdict fabrique.

## La forme d'une anomalie

```python
Anomalie(
    genre="chiffre_sans_source",
    gravite="majeur",            # bloquant | majeur | mineur
    detail="3 chiffre(s) precis annonces sans source ni marqueur d'exemple",
    extrait=suspects[0][:160],
    consigne="Sourcez chaque pourcentage ou presentez-le comme un exemple.",
    poids=0.0,                   # 0 = poids par defaut de la gravite
)
```

Les deux champs qu'on oublie et qui font la difference :

- **`consigne`** est injectee telle quelle dans l'invite de correction. Elle
  s'ecrit donc a l'imperatif, a destination du modele, et dit quoi faire — pas
  ce qui ne va pas. Sans elle, le controle constate et la boucle de correction
  n'a rien a corriger.
- **`poids`** existe parce que la gravite dit la categorie, pas l'ampleur. Un
  texte a 170 tics pour mille mots ne doit pas etre note comme un texte a 6
  tics, alors que les deux sont « bloquants ».

`gravite="bloquant"` empeche la livraison. Le reserver a ce qui rend le
produit invendable — une promesse de resultat, par exemple, qui est un risque
juridique pour le vendeur.

## La regle qui prime sur toutes les autres

**Un garde-fou qui crie a tort finit ignore, ce qui est pire que se taire.**

Quand l'attribution est ambigue, rater le defaut. Le dire dans la docstring,
pour que le prochain lecteur sache que c'est un choix et non un oubli :

- `pipelines/faits.py` n'attribue rien quand une phrase nomme deux
  personnages — a qui appartiennent « ses yeux verts » dans « Camille regarda
  Lucie » ?
- `pipelines/voix.py` exige un verbe de parole **et** un seul nom dans
  l'incise avant d'attribuer une replique.
- `_apparait()` dans `pipelines/nouvelle.py` cherche chaque mot du nom
  separement, et assume que deux personnages homonymes se reconnaissent l'un
  l'autre : il rate une absence plutot que d'en inventer une.

## Les faux positifs previsibles

Quatre pieges qui reviennent a chaque nouveau controle :

- **Les accents.** Comparer via une forme sans accent (`_plat`), mais
  attention si l'on cherche une **position** dans le texte : la forme aplatie
  peut etre plus courte que l'original, et la position ne correspond plus.
  Recomposer en NFC d'abord.
- **Les majuscules et la ponctuation** collees au mot cherche : utiliser des
  bornes de mot (`\b`), pas `in`.
- **La longueur du texte.** Un rapport brut mots uniques / mots totaux chute
  mecaniquement quand le texte s'allonge. `diversite_lexicale()` mesure par
  fenetres de 300 mots pour cette raison : sans cela, un long chapitre est
  toujours note plus mal qu'un court.
- **Le contexte legitime.** Un chiffre precis accompagne de « selon », « par
  exemple » ou « imaginons » n'est pas un chiffre sans source.
  `MARQUEUR_SOURCE` porte cette liste.

## Verifier

```bash
python3 -m unittest tests.test_controle -q
```

Puis, parce que ces controles sont exactement le genre de code qui passe les
tests sans jamais s'executer — skill `mutation`. Deux mutations a jouer au
minimum :

- **retirer le controle** : la suite doit echouer (sinon aucun test ne
  l'exerce) ;
- **elargir le controle** pour qu'il attrape aussi un cas legitime : la suite
  doit echouer aussi. C'est ce qui prouve qu'un test garde l'absence de faux
  positif, et pas seulement la presence de detection.

Le second est celui qu'on oublie, et c'est celui qui compte.
