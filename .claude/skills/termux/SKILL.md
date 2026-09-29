---
name: termux
description: Concevoir ou verifier un changement pour qu'il survive sur un telephone Android sous Termux — la seule cible qui compte vraiment. A utiliser des qu'on ecrit du code qui lance un sous-processus, pose un delai d'attente, ouvre un thread, ecrit un fichier volumineux, boucle longtemps, ou suppose qu'un binaire existe. A utiliser aussi quand on se demande pourquoi un delai est si long, pourquoi une fonction rend None au lieu d'une valeur, ou quand on integre une fonction du telephone (notification, batterie, partage).
allowed-tools: Bash, Read, Edit, Grep
---

# Ecrire pour un telephone

L'usine tourne sur Android, sous Termux, sur batterie, derriere un forfait
mobile. Ce n'est pas un environnement degrade : c'est **la** cible. Un
ordinateur de bureau est le cas facile.

Cinq contraintes en decoulent, et chacune a deja produit un defaut.

## 1. Le processus peut mourir sans preavis

Android tue une application en arriere-plan quand il veut. Tout etat qui doit
survivre va **en base**, pas en memoire.

Le routeur l'a appris : la mise au repos d'un fournisseur apres un 429 vivait
dans un dictionnaire de module. Elle disparaissait au premier redemarrage,
c'est-a-dire tout le temps. Un fournisseur qui venait de repondre 429 etait
resollicite dans la seconde — et repondait 429. La donnee etait deja en base
(`cles_journal`) ; il ne manquait que de la relire au demarrage.

Regle pratique : un cache en memoire est permis, mais la verite est en base et
se relit au premier acces.

## 2. Un modele local met des minutes, pas des secondes

Un modele de trois milliards de parametres produit entre trois et dix jetons
par seconde sur un processeur de telephone. Quatre mille jetons demandent donc
entre sept et vingt minutes.

C'est pourquoi `Provider.timeout` vaut 150 s pour un service distant et
**1200 s** pour `ollama` et `llamacpp`. Avec la limite commune, l'IA locale
etait cablee, annoncee dans le diagnostic — et incapable de terminer un
chapitre : chaque appel expirait avant la fin de la generation.

Et `max_sortie` vaut 4096 en local contre 8192 a distance : un telephone n'a
pas la memoire d'un long contexte de sortie.

## 3. Tout binaire externe est optionnel, et peut ne jamais repondre

`termux-api` installe **sans** l'application Termux:API ne rend pas la main :
la commande attend indefiniment. Chaque appel de `core/telephone.py` porte
donc un delai (`DELAI = 8`, 120 s pour un partage qui ouvre une interface).

Deux regles qui en decoulent :

- **Rendre `None` quand on ne sait pas, jamais une valeur par defaut.**
  `batterie()` rend `None` pour « je n'ai pas pu savoir », ce qui ne se
  confond pas avec « batterie vide ». Un garde-fou qui arrete la production
  sur une valeur devinee est pire qu'absent.
- **Ne relacher que ce qu'on a pris.** `veille_maintenue()` est un
  gestionnaire de contexte qui ne libere le verrou de veille que s'il l'a
  effectivement acquis : liberer celui d'un autre processus laisse le
  telephone s'endormir en pleine fabrication.

Meme discipline pour Node (`core/verification.py`) : present, la verification
du JavaScript genere est complete ; absent, elle passe en mode degrade et le
dit. Jamais d'echec dur pour un outil optionnel.

## 4. La batterie et l'espace sont des ressources finies

Une fabrication longue doit s'arreter proprement avant que le telephone ne
s'eteigne : `BATTERIE_PLANCHER = 20`, verifie entre deux produits par le
moteur continu, et ignore quand l'appareil est en charge.

L'espace disque aussi : `usine docteur` le mesure, parce qu'une fabrication
qui s'arrete faute de place laisse un produit a moitie ecrit sans dire
pourquoi.

## 5. Le systeme de fichiers n'est pas celui d'un serveur

- `/sdcard` ne supporte pas toujours le mode WAL de SQLite. `store.connect()`
  l'essaie et continue sans lui si le pragma echoue.
- Les chemins bougent selon l'installation (`~/Usine-IA`, `/sdcard/Usine-IA`).
  Rien n'est code en dur : `USINE_HOME` et `config.WORKDIR` decident.
- Une boucle qui dort doit rester interruptible. `_dormir()` du moteur continu
  se reveille chaque seconde pour verifier une demande d'arret : sinon Ctrl+C
  attend soixante secondes, et l'utilisateur tue le processus a la main —
  laissant la base dans l'etat qu'on imagine.

## Verifier sans telephone

Aucune de ces contraintes ne se teste sur la machine de developpement.
Ce qui se verifie :

```bash
python3 scripts/dependances.py    # rien hors bibliotheque standard
python3 -m usine --version        # le paquet se lance sans etre installe
python3 tests/fumee.py            # les chaines de bout en bout
```

Et la relecture, qui reste le vrai controle. Devant un nouveau bout de code,
quatre questions :

1. Si le processus meurt ici, qu'est-ce qui est perdu ?
2. Ce delai tient-il compte d'un modele local a cinq jetons par seconde ?
3. Ce binaire peut-il etre absent, ou pire, present et muet ?
4. Cette boucle peut-elle etre interrompue ?
