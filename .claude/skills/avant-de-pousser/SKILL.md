---
name: avant-de-pousser
description: Lancer en local exactement ce que l'integration continue va verifier, avant de commiter ou de pousser. A utiliser quand on s'apprete a pousser, quand on demande « est-ce que c'est bon ? », apres une serie de modifications, ou quand la CI vient d'echouer et qu'on veut reproduire la panne sans attendre un aller-retour GitHub. Couvre la suite complete, le test de fumee, la compilation, l'absence de dependance externe et l'absence de cle API dans le depot.
allowed-tools: Bash, Read, Grep
---

# Ce que la CI verifie, en local

Un aller-retour GitHub coute plusieurs minutes et une notification ; les cinq
controles ci-dessous prennent moins d'une minute sur une machine, quelques-unes
sur un telephone. Ils sont la copie fidele de `.github/workflows/tests.yml`.

```bash
python3 -m unittest discover -s tests -t . -q   # la suite
python3 tests/fumee.py                          # les chaines via la vraie CLI
python3 -m compileall -q usine tests            # tout doit compiler
python3 scripts/dependances.py                  # aucun import hors stdlib
python3 -m usine --version                      # le module se lance tel quel
```

Et le controle des secrets, que la CI fait aussi :

```bash
git ls-files | grep -qx '.env' && echo "DANGER: .env est suivi par git"
git grep -nE '\b(gsk_|sk-[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{30})' \
  -- . ':!.github/workflows' && echo "DANGER: cle API apparente"
```

## Pourquoi chacun existe

**La suite** est evidente, mais lancer un seul module de test ne suffit pas :
l'isolation des ateliers (`atelier.isoler`) ne se verifie qu'en suite
complete, et c'est precisement la que les interferences entre modules
apparaissent.

**Le test de fumee** exerce chaque chaine par la vraie ligne de commande, avec
le simulateur a la place du routeur IA. Il attrape ce que les tests unitaires
ne voient pas : un cablage manquant dans le catalogue, un argument de CLI mal
nomme, un export qui n'ecrit rien.

**`compileall`** attrape une erreur de syntaxe dans un module qu'aucun test
n'importe. Il y en a : les modules de rendu rarement touches, par exemple.

**`dependances.py`** lit les imports dans l'arbre syntaxique plutot que
d'executer le code — un module qui plante a l'import passerait autrement
inapercu. C'est la contrainte fondatrice du projet : Termux ne sait pas
compiler de roue native, et une dependance ajoutee par megarde ne se voit
qu'au moment ou quelqu'un installe sur un telephone neuf, c'est-a-dire trop
tard.

**`python3 -m usine --version`** verifie que le paquet se lance sans etre
installe. C'est ainsi qu'il tourne sur un telephone.

## Si la CI echoue alors que le local passe

Trois causes, dans cet ordre de frequence :

1. **La version de Python.** La CI teste 3.9, 3.11 et 3.13. Une syntaxe
   recente (`match`, un generique `list[str]` sans `from __future__`) passe en
   local et casse en 3.9.
2. **Un `.pyc` perime en local.** Deux versions d'un fichier de meme taille
   ecrites dans la meme seconde partagent leur cache compile — les tests
   tournent alors sur du code qui n'existe plus.
   `find . -name __pycache__ -exec rm -rf {} +` puis relancer.
3. **Un fichier non suivi par git.** Le code marche en local parce qu'un
   fichier existe ; il n'est pas dans le commit. `git status --short` le dit.

## Apres une correction de bug

Les cinq controles disent que rien n'est casse. Ils ne disent pas que la
correction est **gardee** : un test peut passer sans jamais exercer le chemin
qu'il croit couvrir. Pour cela, remettre le defaut et verifier que la suite
echoue — voir la skill `mutation`.
