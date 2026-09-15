# La phrase, que rien ne regardait

## Ce qui existait déjà

La fiction du dépôt est contrôlée sérieusement — mais uniquement sur sa
**charpente** :

| | |
|---|---|
| `pipelines/faits.py` | le registre de ce qui a été affirmé : l'âge d'un personnage, la couleur d'une porte |
| `pipelines/voix.py` | qui parle, combien, et qui ne parle jamais |
| `nouvelle.controler_continuite` | douze contrôles : personnages, promesses, beats, canon de série |
| `core/controle.py` | tics de langage, répétitions, rythme, chiffres sans source |

Aucun ne regarde la phrase. Or c'est là que se voit, d'une ligne, qu'un texte
a été généré.

## Les cinq relevés

`usine/pipelines/prose.py`. Tous portent sur la **narration** : les répliques
sont retirées d'abord. Un personnage a le droit de dire « je suis triste », et
le compter serait un garde-fou qui crie à tort.

**1. Les mots filtres.** « Elle vit que la porte était ouverte » interpose une
conscience entre la scène et le lecteur ; « la porte était ouverte » met le
lecteur dans la pièce. Le détecteur exige la construction `verbe + que`, et
pas seulement le verbe. Ce n'est pas une commodité d'écriture : « il vit »
seul est ambigu — vivre ou voir — et le dépôt préfère **rater un défaut
plutôt qu'en inventer un**. « Elle sentit le froid » est un mot filtre que ce
module laisse passer, volontairement.

**2. L'émotion nommée.** « Il était furieux » au lieu de le montrer. La liste
est fermée et ne contient **que des états** : « il était grand » et « elle
était médecin » n'en sont pas. Relever tout `était + adjectif` ferait crier le
contrôle à chaque description.

**3. Les mots en « -ment ».** Rendus **sans être classés**. « Changement » et
« lentement » se ressemblent trop en français pour qu'un détecteur les sépare
sans dictionnaire, et un dictionnaire ne tient pas dans ce dépôt. Seule la
longueur écarte quelque chose — quatre lettres au minimum avant « -ment », ce
qui retire *moment*, *ciment*, *dément* — au prix d'une poignée d'adverbes
rares (*dûment*, *crûment*). Ce qui sort est la liste des mots répétés trois
fois ou plus : un humain voit en une seconde que « gouvernement » est un nom
et que « doucement » onze fois est un tic.

**4. Les incises.** La part des répliques introduites par « dit », et la liste
des verbes employés à la place, avec leur nombre. Le relevé porte sur les
lignes de réplique, pas sur la narration : un « il murmura » au milieu d'un
paragraphe descriptif n'introduit rien.

**5. La part de dialogue.** Même méthode que le relevé cité plus bas : la part
des **caractères** compris dans une réplique, pas le nombre de répliques. Une
réplique de trois mots et un monologue de trois cents ne pèsent pas pareil
dans la lecture.

## Pourquoi aucun de ces cinq ne rend de verdict

Parce qu'aucun seuil n'a été mesuré sur de la fiction française.

Les repères chiffrés qui existent sont anglais. Ben Blatt a compté les
adverbes en « -ly » de cinquante et un romans de Stephen King : **101 pour dix
mille mots**, contre **80 chez Hemingway**. En français, « -ment » porte aussi
des noms très courants, et personne n'a publié l'équivalent. Écrire « 140 pour
dix mille mots, c'est trop » serait donc un chiffre faux comparé à un seuil
étranger.

Pour le dialogue, la mesure existe — et c'est **son écart** qui interdit le
verdict. Mark Liberman a mesuré la part de caractères entre guillemets dans
des romans publiés :

| | |
|---|---|
| Virginia Woolf, *To the Lighthouse* | 3,3 % |
| Conan Doyle, *Sherlock Holmes* | 47,0 % |
| Bram Stoker, *Dracula* | 47,5 % |
| Fitzgerald, *Gatsby* | 51,3 % |
| Agatha Christie, *The Mysterious Affair at Styles* (1920) | 49,2 % |
| Agatha Christie, *Elephants Can Remember* (1972) | 79,4 % |

De 3 % à 79 %, tous publiés, tous lus. **Il n'y a pas de bonne part de
dialogue.** L'usine situe donc le texte parmi ces romans-là, et ne dit pas
s'il a raison.

Pour les incises, la seule référence trouvée est une recommandation d'éditeur
— « 90 à 95 % des incises devraient employer *dit* » — pas une mesure sur un
corpus. Elle est citée dans `SOURCES`, elle ne sert pas de verdict.

## Ce que l'usine affiche

Les relevés partent dans le journal, dans `produit.json`, et à l'écran de la
CLI — mais **jamais en alerte**. Ce sont des comptes, pas des fautes. Les
passer par le canal jaune ferait clignoter un texte qui n'a rien de fautif, et
un signal qui se déclenche à chaque production finit ignoré, y compris les
fois où il dit quelque chose.

Un test garde ce point précis, parce que la première version s'y était trompée
et faisait sortir « en alerte » un feuilleton parfaitement sain — au motif que
le mot « exactement » revenait neuf fois.

## Les quatre chaînes qui le mesurent

`nouvelle` (donc `roman`), `recueil`, `feuilleton`, `interactive`.

Pas `conte` : un album fait trois cents mots, n'a pas d'incise, et une part de
dialogue calculée sur quatorze phrases ne mesure rien.

## Ce qui garde la correction

`tests/test_prose.py`, vingt-cinq tests. La moitié vérifie que le contrôle
**ne crie pas à tort** — un personnage qui dit « je suis triste », un
narrateur qui écrit « il vit à Rouen », une description qui dit « il était
grand ». Campagne de mutation : quinze mutations, toutes vues.
