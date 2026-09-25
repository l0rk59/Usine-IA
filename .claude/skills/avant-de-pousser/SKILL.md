---
name: avant-de-pousser
description: Lancer en local exactement ce que l'integration continue va verifier, avant de commiter ou de pousser. A utiliser quand on s'apprete a pousser, quand on demande « est-ce que c'est bon ? », apres une serie de modifications, ou quand la CI vient d'echouer et qu'on veut reproduire la panne sans attendre un aller-retour GitHub. Couvre la suite complete, le test de fumee, la compilation, l'absence de dependance externe et l'absence de cle API dans le depot.
allowed-tools: Bash, Read, Grep
---

# Ce que la CI verifie, en local

Un aller-retour GitHub coute plusieurs minutes et une notification ; les six
controles ci-dessous prennent moins de deux minutes sur une machine, quelques-unes
sur un telephone. Ils sont la copie fidele de `.github/workflows/tests.yml`.

```bash
python3 -m unittest discover -s tests -t . -q   # la suite
python3 tests/fumee.py                          # les chaines via la vraie CLI
python3 -m compileall -q usine tests            # tout doit compiler
python3 scripts/dependances.py                  # aucun import hors stdlib
python3 scripts/fuites.py                       # aucune cle API suivie par git
python3 -m usine --version                      # le module se lance tel quel
```

**Lire le code de sortie, pas la derniere ligne.** `python3 tests/fumee.py |
tail -3` rend le code de `tail`, c'est-a-dire zero : le 25/09/2026, une fumee
en echec (« ECHECS : idees, ab-creer ») est passee pour verte de cette facon,
et seul un nombre de fichiers en baisse l'a trahie. Pour abreger la sortie,
`set -o pipefail` d'abord.

**Puis regarder la CI elle-meme**, pas seulement le local. Du 12 au 23/09/2026
elle a ete rouge a chaque poussee sans que personne ne le remarque : le
controle des secrets cherchait « gsk_ » seul et signalait la documentation et
les cles factices des tests. Un controle toujours rouge n'est plus lu — et il
a cache pendant huit jours un echec reel, sous Python 3.9 seulement.

## Pourquoi chacun existe

**La suite** est evidente, mais lancer un seul module de test ne suffit pas :
l'isolation des ateliers (`atelier.isoler`) ne se verifie qu'en suite
complete, et c'est precisement la que les interferences entre modules
apparaissent.

**Le test de fumee** exerce chaque chaine par la vraie ligne de commande, avec
le simulateur a la place du routeur IA. Il attrape ce que les tests unitaires
ne voient pas : un cablage manquant dans le catalogue, un argument de CLI mal
nomme, un export qui n'ecrit rien. Ce qu'il ne peut pas voir : le routeur
lui-meme, que le simulateur remplace. « --hors-ligne : zero connexion » a ete
mesure ainsi, et c'etait faux — le texte partait chez Groq. Ce qui touche au
reseau se teste par le vrai routeur, contre de faux serveurs
(`tests/test_hors_ligne.py`).

**`compileall`** attrape une erreur de syntaxe dans un module qu'aucun test
n'importe. Il y en a : les modules de rendu rarement touches, par exemple.

**`dependances.py`** lit les imports dans l'arbre syntaxique plutot que
d'executer le code — un module qui plante a l'import passerait autrement
inapercu. C'est la contrainte fondatrice du projet : Termux ne sait pas
compiler de roue native, et une dependance ajoutee par megarde ne se voit
qu'au moment ou quelqu'un installe sur un telephone neuf, c'est-a-dire trop
tard.

**`fuites.py`** cherche une cle d'API dans les fichiers suivis, avec les
motifs qui la masquent dans le journal (`usine/core/securite.py`) : une seule
definition de ce qu'est une cle. Une cle factice de test s'assemble a
l'execution (`"gsk_" + "A" * 32`) ; ecrite en clair, elle serait signalee.

**`python3 -m usine --version`** verifie que le paquet se lance sans etre
installe. C'est ainsi qu'il tourne sur un telephone.

## Si la CI echoue alors que le local passe

Quatre causes, dans cet ordre de frequence :

1. **La version de Python.** La CI teste 3.9, 3.11, 3.13 et 3.14 — la
   derniere est celle du telephone (`SPECS-APPAREIL.md`). Une syntaxe recente
   (`match`, un generique `list[str]` sans `from __future__`) passe en local
   et casse en 3.9 ; une API retiree passe en 3.9 et casse sur le telephone.
   `uv python install 3.14` donne la seconde en local.
2. **Un `.pyc` perime en local.** Deux versions d'un fichier de meme taille
   ecrites dans la meme seconde partagent leur cache compile — les tests
   tournent alors sur du code qui n'existe plus.
   `find . -name __pycache__ -exec rm -rf {} +` puis relancer.
3. **Un fichier non suivi par git.** Le code marche en local parce qu'un
   fichier existe ; il n'est pas dans le commit. `git status --short` le dit.
4. **Un fil qui survit a son module.** Le meme commit passe sur une execution
   et echoue sur l'autre : ce n'est pas un alea, c'est un fil lance par un
   module precedent qui tourne encore — il ecrit dans l'atelier suivant et
   utilise son simulateur. Vu le 24/09/2026 : « no such table » un jour, un
   compte d'appels faux le lendemain. `atelier.isoler` attend desormais les
   fils du tableau de bord (`attendre_les_travaux`, dans `tests/atelier.py`) ;
   un nouveau fil d'arriere-plan doit passer par le meme point, ou etre
   attendu de la meme facon. Ne jamais relancer la CI pour voir : lire le
   journal de l'execution rouge.

## Apres une correction de bug

Les six controles disent que rien n'est casse. Ils ne disent pas que la
correction est **gardee** : un test peut passer sans jamais exercer le chemin
qu'il croit couvrir. Pour cela, remettre le defaut et verifier que la suite
echoue — voir la skill `mutation`.
