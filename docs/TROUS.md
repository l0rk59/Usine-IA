# Un produit livré avec un trou doit le dire

## Ce qui a été mesuré

Le 14/09/2026, en coupant le réseau au milieu de chaque chaîne. Pas en lisant
le code : en provoquant la panne.

```
chaine       statut    trous  ce qui manque
--------------------------------------------------------
formation    pret          0  —
prompts      pret          0  —
modeles      pret          0  —
outils       pret          0  —
social       pret          0  —
```

Une formation dont quatre modules sur dix ont été remplacés par leur plan
était livrée **marquée « prêt »**. `usine reprendre` répondait « aucun produit
inachevé ». Le PDF partait chez l'acheteur avec des puces à la place des
leçons, et rien, nulle part, ne le disait.

C'est le défaut que ce dépôt craint le plus : *invisible partout en aval*.

## Le garde-fou existait, et il était juste

`terminer()` — le point de sortie commun aux dix chaînes — fait exactement ce
qu'il faut :

```python
manquants = [str(m) for m in (infos.get("manquants") or [])]
store.maj_produit(..., statut="en_cours" if manquants else "pret")
```

Le commentaire au-dessus dit même pourquoi : « *« pret » veut dire vendable.
Un produit dont des sections ont été remplacées par leur plan ne l'est pas.* »

**Mais seules deux chaînes sur neuf remplissaient `manquants`.** `terminer()`
voyait donc toujours une liste vide, et marquait toujours « prêt ».

Le mécanisme était bon. C'est son alimentation qui manquait.

## Ce que les chaînes notaient déjà

Toutes les chaînes notent leurs étapes : `ctx.etape("module-4", "echec", ...)`.
Ces lignes partaient dans une table SQLite que **personne ne relisait** au
moment de conclure.

`terminer()` relit maintenant ce journal, pour les dix chaînes à la fois. Une
seule correction, à un seul endroit, plutôt que neuf corrections à recopier —
et la dixième chaîne écrite dans six mois en héritera sans rien faire.

**Le dernier statut de chaque étape gagne.** Une étape qui a échoué puis réussi
à la reprise n'est pas un trou. Compter n'importe quel échec aurait marqué
inachevé tout produit ayant connu une seule erreur rattrapée — donc, à terme,
tous, et `usine reprendre` serait devenu du bruit.

## Trois statuts, parce que deux ne suffisaient pas

Le premier jet confondait deux choses sous le mot « echec ». Le contrôle de
continuité d'un roman s'est retrouvé dans les sections à refaire — or aucune
réécriture ne corrige une contradiction : `usine reprendre` serait allé
réécrire une scène qui existe.

| | |
|---|---|
| `ok` | l'étape a tourné, rien à signaler |
| `echec` | l'étape **n'a pas pu** tourner : il manque son résultat |
| `anomalie` | l'étape a tourné et a **trouvé** quelque chose |

Et un quatrième cas, orthogonal : `essentiel=False`. Un quiz manquant, une
séquence e-mail indisponible, une relecture d'ensemble qui n'a pas pu tourner
ne rendent pas le produit invendable. Ils sont notés, ils sont dits, et le
produit reste « prêt » — parce qu'*un garde-fou qui crie à tort finit ignoré*,
et que `usine reprendre` n'aurait bientôt plus signalé que du bruit.

`essentiel` vaut **True** par défaut : une chaîne qui oublie d'y penser fait du
bruit plutôt que du silence. Le silence est le défaut qu'on corrigeait.

## Le même défaut, écrit quatre fois

```python
except Exception as exc:
    ctx.etape("module-1", "echec", str(exc))   # note l'échec
    corps = plan_de_repli()
ctx.etape("module-1", "ok")                    # ... puis l'efface
```

Le second appel est **hors** du `except` : il s'exécute toujours. Le dernier
statut gagne, donc l'échec était noté puis immédiatement recouvert.

`formation`, `pack_prompts` et `modeles` portaient cette forme. La quatrième
était plus coûteuse : dans `ebook`, le chapitre de repli descendait jusqu'au
**carnet** et s'y inscrivait comme un chapitre écrit. `usine reprendre` ne le
refaisait donc jamais — le plan partait chez l'acheteur à sa place,
définitivement.

## Le détecteur, et ses deux erreurs

Un contrôle garde ce motif. Il lit la structure : un `try` dont un gestionnaire
note une étape, puis, dans le **même bloc** et après lui, un appel qui note la
même étape « ok » en dur.

Il s'est trompé deux fois avant d'être juste, et les deux erreurs sont
instructives.

**Il accusait à tort.** Trois des quatre cas d'`ebook` finissent par
`continue` : la ligne d'après leur est inatteignable. Le détecteur signalait
donc le seul fichier qui traitait le cas correctement. Il regarde maintenant si
le gestionnaire sort par `continue`, `break`, `return` ou `raise`.

**Il était aveuglé par un alias.** Le quatrième cas notait l'échec sous
`"chapitre-{}".format(index + 1)` et la réussite sous `repere` — deux écritures
du même nom. Comparées telles quelles, elles ne se ressemblent pas, et le vrai
défaut passait pendant que le faux était signalé. Les variables locales
affectées **une seule fois** sont désormais remplacées par leur valeur avant
comparaison ; celles affectées plusieurs fois ne le sont pas, et le détecteur
rate alors un défaut plutôt que d'en inventer un.

## Ce que ça donne

```
chaine       statut     trous  ce qui manque
------------------------------------------------------------------------
formation    en_cours       6  module-4, module-5, module-6, module-7
                               [facultatif: emails, quiz]
prompts      en_cours       2  categorie-1, categorie-2
outils       en_cours       4  outil-3, outil-4, outil-5, outil-6
social       en_cours       4  lot-3, lot-4, lot-5, lot-6
nouvelle     en_cours       3  scene-2, scene-3, scene-4
                               [anomalie: continuite]
```

```
$ usine reprendre
== Reprise — Formation : le systeme complet
  5 section(s) a refaire : module-5, module-6, module-7, module-8, module-9
  Commande : usine formation ... -q rapide
```

Les chaînes sans boucle (`modeles`, `impression`, `logiciel`) meurent
franchement quand le réseau tombe au mauvais moment : elles ne livrent rien,
donc elles ne mentent pas. Ce sont celles qui **continuent** avec un repli
qu'il fallait faire parler.

Les douze mutations de la campagne sont vues.

## Trois chaînes arrivées après la liste

Le 24/09/2026, même mesure, mais par le tableau de bord et sur **tous** les
types du catalogue : fournisseurs coupés au tiers, puis aux deux tiers de
chaque fabrication.

```
interactive   13 appels, coupe a  4 : statut=pret   manquants=0
interactive   13 appels, coupe a  9 : statut=pret   manquants=0
recueil       19 appels, coupe a  6 : statut=pret   manquants=0
recueil       19 appels, coupe a 13 : statut=pret   manquants=0
feuilleton    46 appels, coupe a 16 : statut=pret   manquants=0
feuilleton    46 appels, coupe a 32 : statut=pret   manquants=0
```

Six coupes sur six : le livre-jeu, le recueil et le feuilleton sortaient
**« prêts »** avec des scènes en moins. Les quinze autres types disaient la
vérité. Ces trois-là écrivaient « scène indisponible » au journal, puis
`continue` — sans rien noter. `terminer()` ne pouvait donc rien relire, la
boucle ne les reprenait pas, et un épisode de deux scènes sur trois partait
chez l'acheteur.

Le test qui gardait ce défaut existait. Il portait sur une liste **écrite à la
main** de quatre chaînes, et ces trois-là sont arrivées après elle. Celui qui
le remplace (`tests/test_trous_fiction.py`) lit le catalogue : une dix-neuvième
chaîne y passera sans que personne n'y pense. Il tourne en quelques secondes.

### Une boucle, écrite une fois

`ebook` et `nouvelle` savaient déjà le faire, chacune dans sa boucle.
`base.Redaction` en sort la règle, pour les chaînes qui ne la suivaient pas :

- ce qui est au carnet n'est pas repayé : une reprise relit ;
- quand plus rien ne répond, on cesse de demander — chaque appel suivant
  serait refusé, après ses propres attentes ;
- ce qui n'a pas pu être écrit est noté en échec, et **pas** au carnet : un
  repli n'est pas une section, une reprise doit encore l'écrire.

La section en cours d'écriture au moment de la coupe est un trou comme les
autres. Le premier jet ne nommait que les suivantes — un livre coupé sur sa
*dernière* section serait sorti « prêt ». La campagne de mutation l'a vu.

### Reprendre sans tout refaire

Les trois chaînes gardent maintenant leur plan au carnet — la bible, l'arc du
feuilleton, le fil du recueil et la bible de chaque récit, la carte du
livre-jeu. Sans lui, la reprise redemandait une carte, qui **renumérotait** les
sections sous les textes déjà écrits : la section 7 du carnet n'était plus
celle vers laquelle renvoient les choix.

Le test le vérifie le cache vidé : une invite déjà payée qui revient est alors
une invite repayée, pas une réponse du cache. Il a fallu pour cela donner à
chaque récit du simulateur sa propre prémisse — le simulateur rend la même à
tous, les récits y partageaient leurs invites, et le cache répondait à la
place du carnet.

Deux défauts plus petits, trouvés en chemin :

- **Le « Précédemment » écrit sur une fiche.** Une scène de l'épisode 1
  perdue, le rappel de l'épisode 2 se rédigeait sur la fiche qui tenait sa
  place, restait au carnet après la reprise, et racontait au lecteur un
  épisode qui n'était pas celui qu'il avait lu. Il attend maintenant l'épisode
  complet.
- **La mémoire du feuilleton avalée par un `pass`.** Un résumé qui échouait
  laissait la mémoire en arrière d'une scène, sans rien pour la faire
  avancer. Elle avance maintenant sur la fiche, comme dans `nouvelle`.
