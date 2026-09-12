---
name: mutation
description: Verifier qu'un test garde vraiment ce qu'il pretend garder, en remettant le defaut dans le code et en confirmant que la suite echoue. A utiliser des qu'on vient de corriger un bug et d'ecrire le test qui l'accompagne, avant de commiter une correction, quand on doute qu'un garde-fou s'execute reellement, ou quand on demande « est-ce que ce test sert a quelque chose ». A utiliser aussi apres avoir ajoute plusieurs controles d'un coup : c'est la qu'un test decoratif se cache le mieux.
allowed-tools: Bash, Read, Edit, Write, Grep
---

# Tester les tests

Un test qui passe ne prouve rien tant qu'on ne l'a pas vu echouer.

C'est particulierement vrai des garde-fous de ce depot, qui sont presque tous
ecrits pour attraper un defaut precis. Un tel test peut tres bien ne jamais
s'executer sur le chemin qu'il croit couvrir : un autre filtre l'a devance, le
cache des reponses IA a servi le texte d'avant, ou le cas choisi ne distingue
pas les deux comportements. Le test est vert, il ne garde rien, et personne ne
le saura avant que le defaut ne revienne.

La verification tient en une question : **si je remets le defaut, est-ce que
la suite echoue ?**

## Comment faire

Ecrire une campagne — un tableau JSON, une entree par correction :

```json
[
  {"titre": "le quota se compte par modele",
   "fichier": "usine/core/llm.py",
   "avant": "return p.model_for(role) if p.quota(role).portee == \"modele\" else \"\"",
   "apres": "return \"\"",
   "tests": ["tests.test_routeur"]}
]
```

Puis la jouer :

```bash
python3 .claude/skills/mutation/scripts/muter.py campagne.json
```

`exemple.json`, a cote de ce fichier, est la campagne reelle qui garde le
routeur : dix mutations, une par defaut corrige. Elle sert de modele.

Le script applique chaque mutation, lance les tests, **restaure toujours** le
fichier, et rend trois verdicts :

| | |
|---|---|
| `[vu]` | la suite echoue quand le defaut revient — le test garde vraiment |
| `[RATE]` | la suite passe quand meme — le test est decoratif |
| `[?]` | le motif n'est plus dans le fichier, ou y figure plusieurs fois |

Le code de sortie vaut 1 des qu'une mutation survit : la campagne peut donc
servir de garde-fou en integration continue.

## Ce qu'on fait d'un `[RATE]`

Un `[RATE]` ne se repare pas en durcissant le code : le code va bien, c'est le
test qui ne le touche pas. Chercher **pourquoi** le test ne voit rien, la
reponse est toujours instructive.

Trois causes reelles, rencontrees dans ce depot :

- **Le cas choisi ne distingue pas les deux comportements.** Un test de quota
  par modele saturait `gemini-2.5-flash` (250 requetes). En comptant pour tout
  le fournisseur, 250 restait sous le plafond de `flash-lite` (1 000) : les
  deux comptages donnaient le meme verdict. Il fallait saturer le modele le
  plus genereux pour que la difference apparaisse.
- **Le cache a repondu a la place du modele.** Deux cas de test qui partagent
  une invite partagent une entree de cache : le second recoit la reponse du
  premier et n'exerce rien. Varier le titre ou le sujet suffit.
- **L'assertion est trop lache.** Un test d'extraction verifiait que le
  resultat ne contenait pas un mot parasite ; la coupe pouvait deraper de
  trois caracteres sans que ce mot apparaisse. Comparer le texte **exact** l'a
  rendu sensible.

## Deux pieges du procede lui-meme

**Le `.pyc` perime.** Python reutilise un fichier compile quand la taille et
la date du source n'ont pas change. Une mutation remplace souvent un motif par
un autre de meme longueur, et l'ecriture puis la restauration tiennent dans la
meme seconde : les tests tournent alors sur du code qui n'existe plus. Le
script pose `PYTHONDONTWRITEBYTECODE=1` pour cette raison. En jouant une
campagne a la main, penser a `find . -name __pycache__ -exec rm -rf {} +`.

Cas reel : `PART_CONFISQUEE = 1.1` tournait encore alors que le fichier disait
`0.8`, ce qui a fait echouer un test correct et perdre un quart d'heure.

**Le motif ambigu.** Un `avant` present plusieurs fois dans le fichier mute la
premiere occurrence, qui n'est pas forcement celle qu'on visait. Le script
refuse ce cas plutot que de choisir : allonger le motif jusqu'a ce qu'il soit
unique.

## Quand s'en passer

La mutation coute une execution de la suite par entree. Sur une correction
isolee dont le test echoue visiblement quand on defait le code, la verifier a
la main suffit. Elle devient payante des qu'il y a plusieurs corrections d'un
coup — c'est la, quand l'attention se dilue sur huit controles, qu'un test
decoratif passe inapercu.
