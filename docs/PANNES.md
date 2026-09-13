# Quand la machine lâche

Trois pannes qu'un téléphone produit vraiment, et qu'aucun test ne provoquait :
le disque se remplit au milieu d'une fabrication, la base de l'atelier est
écrasée, le réseau tombe. Elles ont en commun d'arriver **au pire moment** —
après que les appels au modèle ont été payés — et d'être annoncées par un
message que Python écrit pour un programmeur, pas pour quelqu'un qui voulait
juste fabriquer un livre dans le métro.

Cette note dit ce qui a été mesuré, et ce que l'usine répond maintenant.

## Le message est une pièce de l'usine

C'est le point qui gouverne tout le reste. Devant

```
[x] OSError : [Errno 28] No space left on device
```

l'utilisateur ne sait ni **où** (quel dossier), ni **quoi faire**, ni — le plus
coûteux — que le travail déjà payé n'est pas perdu. Il refait donc soit rien,
soit tout. Les deux sont chers : le premier abandonne un produit à moitié fini,
le second rebrûle un quota quotidien.

Un message qui n'oriente pas est une panne de plus.

## Disque plein, permission refusée, lecture seule

`usine/cli.py` traduit trois `errno` en geste à faire :

| errno | ce qu'on dit |
|---|---|
| `ENOSPC` | « Plus de place. Il reste *N* Mo. » — le chiffre vient de `diagnostic.espace_libre()`, la même mesure que `usine docteur` |
| `EACCES` / `EPERM` | le dossier, et `termux-setup-storage` — sur Android, `/sdcard` demande l'autorisation de stockage |
| `EROFS` | `USINE_HOME=~/Usine-IA` — le dossier de travail est en lecture seule |

**Et rien d'autre.** `_expliquer_ecriture()` rend `""` pour tout autre `errno`,
et l'appelant retombe sur le message brut. La raison : `OSError` ne parle pas
que du disque. « Address already in use » en est une — c'est `usine web` lancé
deux fois. Annoncer un disque plein à quelqu'un dont le port est occupé
l'enverrait chercher exactement à l'opposé du défaut. Le garde-fou se tait
quand il ne sait pas.

## Ce que le cache rend, et ce qu'il ne rend pas

Chaque réponse du modèle est gardée en cache par empreinte de l'invite. Une
fabrication interrompue a donc déjà payé ses appels : la relancer les rejoue
gratuitement.

La première version du message disait « relancer ne reconsommera aucun quota ».
**C'était faux**, et la mesure l'a montré :

> ebook de 8 chapitres via le simulateur, 13/09/2026 : 27 appels d'un trait.
> Coupé après 6, la relance en a coûté **21**. La différence — exactement 6 —
> est ce que le cache a rendu.

Une coupure précoce laisse donc l'essentiel à payer. La phrase affichée dit
maintenant ce qui est vrai : *« relancer la MEME commande reprend où vous en
étiez, sans repayer ce qui est fait »*. `tests/test_pannes.py` refait la mesure
et refuse le mot « gratuit ».

## Réseau coupé

Le téléphone sort du wifi au milieu d'une fabrication de quinze minutes. Ce
n'est pas un cas rare : c'est le cas normal d'un appareil qu'on met dans sa
poche.

Ce que l'usine affichait alors : la liste des fournisseurs qui ont échoué, puis
**« Nouvelle clé : usine cles »** — un conseil absurde quand le problème est le
wifi, et qui envoie créer des comptes chez quatre fournisseurs pour rien.

Le geste dépend de la cause, et la cause se **mesure** : `http.en_ligne()` est
interrogé une fois avant de conseiller (HTTPS d'abord, DNS en repli — c'est le
seul test qui reste valable derrière un proxy ou un réseau mobile filtré).
Hors ligne, on parle du wifi. En ligne, on renvoie au diagnostic.

Au passage : `http.en_ligne()` n'avait **aucun appelant**. Voir plus bas.

### Le produit interrompu ne se fait pas passer pour fini

Après une coupure, le dossier du produit reste sur le disque — c'est voulu, il
porte le travail déjà payé. Ce qui ne doit pas rester, c'est l'idée qu'il est
fini. `usine liste` affichait `en_cours` comme n'importe quel autre mot, sous un
titre « Produits fabriqués ». Il affiche maintenant **inachevé**, et rappelle en
bas de liste que relancer reprend le travail.

## Base de l'atelier illisible

Une carte SD fatiguée rend des octets nuls ; un processus tué en pleine écriture
laisse un fichier tronqué. Mesure du 13/09/2026 (Python 3.11) :

| ce qui arrive au fichier | ce que SQLite dit |
|---|---|
| en-tête détruite, ou remplacée par du texte | `file is not a database`, dès la première lecture |
| fichier tronqué | `database disk image is malformed`, dès la première lecture |
| page intérieure écrasée | **rien** — le défaut ne sort que le jour où l'on lit cette page |
| fichier vide | **rien**, et c'est normal : SQLite y écrit son schéma |

La troisième ligne est la coûteuse, et c'est elle qui a dicté la forme du
contrôle : `store.diagnostic_base()` rouvre le fichier et lance
`PRAGMA integrity_check`. Un contrôle qui se contenterait d'ouvrir la base
déclarerait sain un fichier à moitié détruit.

### On mesure, on ne déduit pas

`sqlite3.DatabaseError` couvre aussi bien un fichier illisible qu'une colonne
mal nommée. Conseiller une restauration de sauvegarde à qui vient de croiser un
défaut de requête lui ferait détruire son atelier pour rien. La CLI ne croit
donc pas l'exception sur parole : elle rouvre le fichier et demande à SQLite.
Base saine ⇒ message générique.

### Ce que l'utilisateur doit savoir, et qu'il ignorait

L'usine devenait **entièrement muette** : toutes les commandes passent par la
base, `usine docteur` et `usine sauvegarde` compris. Chacune répondait
`DatabaseError : file is not a database`, sans nommer le fichier ni le remède.

Le message dit maintenant, dans cet ordre :

1. quel fichier ;
2. **que les produits sont intacts** — ce sont des fichiers dans `produits/`,
   et les réglages un JSON à côté. C'est le seul point qui évite une
   réinstallation de panique ;
3. ce que la base contient et qu'on perdrait vraiment : l'historique, les
   ventes, **les bibles de série** et le cache. On ne rassure pas à tort — une
   bible de série perdue, c'est du contenu perdu ;
4. les deux remèdes, vérifiés l'un et l'autre :
   `usine sauvegarde --restaurer archive.zip --oui` (la restauration met
   l'ancienne base de côté au lieu de l'écraser), ou déplacer `usine.db` à la
   main — l'usine en recrée une vide au démarrage suivant.

**On n'efface rien.** Déplacer soi-même la base de quelqu'un serait décider à sa
place que son historique ne vaut rien.

### `usine docteur` survit

C'est la commande qu'on lance quand plus rien ne marche ; elle mourait comme les
autres, et sur la même ligne — elle lit les compteurs du jour, qui sont dans la
base. Elle rend maintenant un rapport complet, la base marquée illisible, et un
verdict qui **prime sur les fournisseurs** : dix clés valides ne servent à rien
si l'usine ne peut rien enregistrer.

Le tableau de bord aussi. `/api/etat` est la toute première requête de la page,
et tout ce qu'elle assemble passe par la base : elle levait, la page restait
vide — **bouton « docteur » compris**, c'est-à-dire le seul écran qui aurait su
expliquer la panne. Elle rend maintenant la panne et le geste, et la page les
affiche au lieu d'une moitié de tableau de bord.

Les compteurs du jour deviennent alors `None`, jamais `0`. « 0 appel
aujourd'hui » se lit « quota intact », et c'est précisément la conclusion qu'on
ne peut pas tirer. La CLI, le menu et le tableau de bord affichent `?`.

Le remède, lui, ne se déduit plus de l'état : tout verdict « bloqué » affichait
`usine cles`. Une base cassée ne se répare pas en ajoutant une clé.

## Deux défauts trouvés en chemin

**`usine docteur` plantait chez tous les vrais utilisateurs, et chez eux seuls.**
La boucle d'affichage du pool de clés écrasait le dictionnaire de diagnostic par
une chaîne de couleur (`etat = ...`), et la section suivante mourait sur
`string indices must be integers`. Le pool est vide sans clé : la boucle ne
tournait donc jamais dans la suite de tests. Posséder une clé API — c'est-à-dire
être un utilisateur — suffisait à déclencher le défaut.

**Le détecteur de fonctions orphelines se laissait tromper par une homonymie.**
Il cherchait le nom dans le *texte* du dépôt. `http.en_ligne()` n'avait aucun
appelant, mais le mot apparaissait ailleurs comme nom de paramètre
(`en_ligne=not ctx.hors_ligne`), et cela suffisait à le déclarer employé. Il lit
maintenant l'arbre syntaxique : un appel, un attribut, un nom chargé **hors de
sa propre portée**. Les chaînes de caractères continuent de compter — une
fonction atteinte par `getattr(module, "nom")` a un appelant bien réel, et
l'accuser serait crier à tort.

Mesure après réécriture : une seule orpheline sur tout le dépôt — celle qu'on
cherchait — et **aucune fausse alerte**. C'est la condition pour l'adopter.

## Où c'est

| | |
|---|---|
| `usine/cli.py` | `_expliquer_ecriture`, `_expliquer_base`, `_explique_le_cache`, et les trois branches de `principal()` |
| `usine/core/store.py` | `diagnostic_base()` — `PRAGMA integrity_check` sur une connexion à part |
| `usine/core/diagnostic.py` | `espace_libre()`, la clé `base`, le verdict et son `remede` |
| `tests/test_pannes.py` | les trois pannes, provoquées pour de vrai |

Voir aussi `docs/TERMUX.md` (processus tué, batterie, binaires absents) et
`docs/SAUVEGARDE.md` (créer et restaurer une archive).
