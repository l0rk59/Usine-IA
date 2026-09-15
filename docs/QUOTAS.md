# Ce que les paliers gratuits autorisent vraiment

Audit du 12 septembre 2026, mené contre la documentation des fournisseurs
eux-mêmes. Point de départ : l'usine appelait **deux modèles qui n'existaient
plus**, et ne s'en apercevait pas.

---

## 1. Groq était mort depuis le 16 août 2026

`console.groq.com/docs/deprecations` :

| Modèle retiré | Arrêt | Remplacement recommandé |
|---|---|---|
| `llama-3.1-8b-instant` | 16/08/2026 | `openai/gpt-oss-20b` |
| `llama-3.3-70b-versatile` | 16/08/2026 | `openai/gpt-oss-120b` |

Ce sont exactement les deux modèles que `core/config.py` configurait pour
Groq. Depuis le 16 août, chaque appel répondait **404**, le routeur mettait
Groq au repos une demi-heure et passait au suivant.

Le comportement était correct — c'est celui prévu pour une panne passagère.
Appliqué à une panne définitive, il rend le fournisseur le plus rapide de la
liste inutilisable **sans que rien, nulle part, ne le dise** : pas d'erreur,
pas d'alerte, pas de ligne dans `usine docteur`. Juste des produits fabriqués
plus lentement, par des services moins bons.

Cerebras avait glissé de la même façon : son catalogue gratuit s'est réduit à
deux modèles (`gpt-oss-120b`, `qwen-3.8-27b`) et les Llama configurés n'y
figurent plus.

**Deux corrections, pas une.** Les identifiants sont à jour — c'est le
rattrapage. Et `usine docteur --modeles` interroge le `/models` de chaque
fournisseur pour comparer au configuré — c'est ce qui empêche la prochaine
disparition de passer inaperçue :

```
== Catalogues des fournisseurs
  [!] groq ne sert plus : llama-3.3-70b-versatile
      propose a la place : openai/gpt-oss-120b, openai/gpt-oss-20b, ...
      Corrigez les identifiants dans usine/core/config.py.
  [ok] Modeles confirmes chez : gemini, mistral
  [!] Non verifie (pas de cle, ou service injoignable) : nvidia
```

Et quand le 404 tombe quand même, le routeur ne dit plus `HTTP 404` mais :
*« le modèle « … » n'existe plus chez groq […] vérifiez avec usine docteur
--modeles »*.

**Le rapport nomme qui a répondu.** Un service injoignable, une clé absente ou
un endpoint muet rendent « je ne sais pas », jamais « aucun modèle » — un
réseau coupé déclarerait sinon toute la configuration morte. Mais l'inverse
est un piège symétrique : un contrôle qui n'a pu interroger personne rendait
une liste d'écarts vide, **indistinguable d'un contrôle où tout va bien**.
C'est exactement la confusion qui a laissé Groq mourir en silence, et elle
avait été réintroduite dans le contrôle censé la supprimer. Le rapport dit
donc les trois états : ce qui est confirmé, ce qui a disparu, ce qui n'a pas
pu être vérifié.

## 2. Le quota qui compte n'est pas celui qu'on comptait

Le routeur ne modélisait que les requêtes — par minute et par jour. Or les
paliers gratuits s'épuisent en **jetons** bien avant de s'épuiser en requêtes.

| Fournisseur | Ce que l'usine croyait | Ce que le fournisseur publie |
|---|---|---|
| groq | 28 req/min · 900 req/jour | 30 req/min · 1 000 req/jour · **8 000 jetons/min** · **200 000 jetons/jour** |
| cerebras | 25 req/min · 800 req/jour | **5 req/min** · 30 000 jetons/min · 1 000 000 jetons/jour |
| gemini | 12 req/min · 400 req/jour | par modèle — voir §3 |

Deux conséquences, mesurables :

**Groq ne peut pas écrire un chapitre.** Une demande de chapitre — trois mille
jetons d'invite, huit mille de sortie — en pèse onze mille. Le budget d'une
minute entière en autorise huit mille. Aucune attente n'y change rien : le
routeur **écarte Groq pour cette demande** et la confie au suivant, au lieu
d'aller chercher un 429 à la main. Les appels courts (titres, plans, contrôles
JSON) continuent d'y aller, et c'est là que sa vitesse sert.

**Cerebras acceptait cinq fois trop d'appels.** 5 requêtes par minute, pas 25 :
l'enchaînement des chapitres s'attirait un 429 sur quatre appels sur cinq.

`Provider.max_sortie` réduit déjà la sortie demandée à ce qu'un service sait
émettre. Ce qui manquait, c'est le budget de la **minute** et de la **journée**,
entrée comprise. Les deux sont comptés en base (`store.jetons_minute`,
`store.jetons_jour`), à partir des `usage.total_tokens` réellement renvoyés.

La fenêtre par minute est **glissante** : la place se libère quand le plus vieil
appel en sort, pas à la minute ronde. Le routeur attend donc ce qu'il faut, et
pas une minute entière à chaque fois.

Un plafond à zéro signifie « non publié par le fournisseur », donc non
modélisé. On ne l'invente pas.

## 3. Google compte par modèle, l'usine comptait par fournisseur

| Modèle | req/min | req/jour |
|---|---:|---:|
| `gemini-2.5-flash` | 10 | 250 |
| `gemini-2.5-flash-lite` | 15 | 1 000 |

Un seul couple `rpm`/`rpd` pour tout le fournisseur produisait le défaut
inverse dans les deux sens : les mille requêtes de flash-lite fermaient flash
quatre fois trop tôt, et le rôle `costaud` devenait indisponible pour une
raison qui ne le concernait pas.

`Provider.quotas` associe donc un `Quota` à un identifiant de modèle, et
`Quota.portee` dit s'il vaut pour le modèle ou pour le service. Le comptage
suit, jusqu'au pool de clés : une clé qui a épuisé les requêtes de flash garde
entières celles de flash-lite.

Google ne publie plus ces chiffres dans sa documentation — la page *rate
limits* renvoie vers AI Studio, derrière une authentification. Les valeurs
retenues sont **les plus basses rapportées** : sous-estimer coûte une attente,
surestimer coûte un 429.

## 4bis. Deux estimateurs de jetons qui se contredisaient

Trouvé en confrontant deux constantes qui n'avaient jamais été mises côte à
côte, parce qu'elles vivaient dans des modules différents :

| | Pour 1 000 mots de français |
|---|---:|
| `jetons_pour` — fixe le plafond de sortie | 2 600 jetons |
| `_cout_estime` — pèse une demande avant de l'envoyer | 1 598 jetons |

**Un facteur 1,63.** Les deux convertissent du français en jetons ; ils ne
peuvent pas avoir raison ensemble.

**Mesuré** : 5,59 caractères par mot, espace compris, sur les 27 375 mots de
français de `docs/`. C'est le seul des deux chiffres qu'on puisse mesurer ici
— le second demanderait le tokeniseur du modèle, qu'on n'a pas.

**Choisi** : le ratio jetons-par-mot fait foi, et le ratio par caractère en
découle (2,15 caractères par jeton). Aligner dans l'autre sens ferait demander
*moins* de jetons de sortie, donc des textes coupés ; aligner dans ce sens-ci
ne fait qu'écarter un fournisseur un peu plus tôt. Surestimer coûte une
bascule, sous-estimer coûte un 429 ou une phrase tranchée.

Un test vérifie désormais que les deux estimateurs s'accordent à 5 % près.

## 4. Estimer le coût avant d'appeler

Pour savoir si une demande tient dans le budget de la minute, il faut la peser
avant de l'envoyer. Deux approximations, toutes deux documentées dans le code :

- **3,5 caractères par jeton** en français. Les tokeniseurs BPE découpent
  l'anglais autour de quatre ; le français un peu plus finement (accents,
  élisions, terminaisons). L'estimation surévalue donc légèrement — le bon
  sens de l'erreur, puisque sous-estimer fait tenter un appel qui sera refusé.
- **La sortie demandée, pas celle qui sera produite.** C'est ce que les
  fournisseurs réservent : Groq comme Cerebras demandent explicitement
  d'ajuster `max_tokens` pour cette raison.

---

## Ce que cela change à l'usage

Rien à faire. Les identifiants et les quotas sont dans `core/config.py`, le
routeur s'y conforme seul. Trois habitudes utiles quand même :

- `usine docteur --modeles` après quelques semaines sans produire. Une requête
  par fournisseur, et la réponse à la seule question que personne ne pense à
  poser : *est-ce que les modèles que je demande existent encore ?*
- `usine docteur` affiche désormais la consommation en jetons à côté de celle
  en requêtes, quand le fournisseur publie un plafond.
- Plusieurs clés chez un même fournisseur multiplient les requêtes **et** les
  jetons — sauf si elles appartiennent au même projet : chez Google, les
  quotas se comptent par projet, pas par clé. Voir ci-dessous.

## 5. Le pool de clés ne multipliait rien

Le pool existe pour une seule raison : **ne jamais s'arrêter pour cause de
quota.** Il ne l'obtenait pas.

Les plafonds d'un fournisseur s'appliquent à un **compte**, donc à une clé. Le
routeur, lui, les comptait pour tout le fournisseur — il additionnait les
consommations de clés indépendantes. Mesuré :

```
quota d'UNE cle : 1000 requetes/jour
cle A a consomme : 1000
cle B a consomme : 0
le routeur declare groq utilisable ? -> False
```

Deux clés donnaient un seul quota. Le même défaut valait pour les jetons par
jour et pour le débit par minute — là, deux clés se **freinaient l'une
l'autre** : le pool ralentissait la production au lieu de l'accélérer.

Le décompte se fait désormais par clé (`compteur_jour`, `jetons_jour`,
`compteur_minute` et `jetons_minute` acceptent un `cle_id`). Une clé épuisée
est sautée, la suivante essayée ; c'est seulement le **repos** d'un
fournisseur — un modèle retiré, un service en panne — qui vaut pour toutes ses
clés à la fois, parce qu'il ne regarde aucune clé en particulier.

**Le cas qui va dans l'autre sens**, et il est assumé : Google compte par
projet. Deux clés d'un même projet partagent leur quota, et compter par clé y
est optimiste. Le prix en est un 429, que le routeur sait déjà traiter en
mettant la clé au repos pour la durée que le service demande. Un décompte
trop prudent, lui, rend le pool entièrement inutile — ce qui est pire.

## Comment ces corrections sont gardées

Dix mutations, une par correction. Chacune remet le défaut dans le code, lance
`tests/test_routeur.py` et `tests/test_tableau.py`, et vérifie que la suite
**échoue**. Un test qui passe encore alors que le défaut est revenu ne garde
rien — c'est ainsi qu'une première version du test de quota par modèle a été
prise en défaut : elle saturait flash (250 requêtes), un chiffre trop bas pour
faire la différence avec le comptage global. Elle sature maintenant flash-lite
(1 000) et vérifie que flash reste ouvert.

---

# Vingt modèles sur vingt-sept ne répondaient pas

*`usine docteur --essai` sur un vrai téléphone, huit clés valides, 15/09/2026.*

C'est la première fois que la question « est-ce que ce modèle marche ? » recevait
une réponse mesurée plutôt que déduite d'un catalogue. Elle a trouvé trois
choses, et **deux étaient des défauts de la sonde elle-même**.

## Le plus coûteux : un fournisseur payé, jamais appelé

Le rapport listait 27 modèles essayés. Aucun n'était ceux d'`opencode` — six
modèles, six cents requêtes par jour, un abonnement payé.

`opencode` était **déclaré**, doté d'une clé, et affiché « disponible » par le
diagnostic. Mais `active_providers()` se construit sur `DEFAULT_ORDER`, et ce
nom n'y figurait pas. Un fournisseur absent de cette liste est invisible pour
toujours — au routeur comme à la sonde.

C'est le **réglage orphelin** du dépôt, déplacé d'un cran : une chose déclarée,
visible, et que rien ne lit.

La correction ne se contente pas d'ajouter le nom : l'ordre est désormais
**dérivé** du catalogue, et tout fournisseur non listé est ajouté à la fin
plutôt que perdu. Corriger l'oubli une fois ne suffit pas ; il faut le rendre
impossible.

## Un diagnostic qui accuse à tort est pire que pas de diagnostic

```
x groq  openai/gpt-oss-120b   vide   0.48s
x groq  openai/gpt-oss-20b    vide   0.40s
```

Groq venait de servir **14 399 jetons le jour même**, avec succès.

La sonde accordait seize jetons — assez pour « OK ». Mais les `gpt-oss` sont
des modèles de **raisonnement** : ils rédigent leur brouillon entre `<think>`
et `</think>` avant de répondre. `core.texte` retire ce brouillon, et il ne
restait rien.

Deux corrections : la sonde accorde 256 jetons, et le cas « le modèle a parlé,
et tout ce qu'il a dit était du brouillon » porte son propre nom —
`raisonnement seul` — parce que le geste à faire n'est pas celui d'un modèle
mort.

## Listé ne veut pas dire appelable

NVIDIA **liste** `writer/palmyra-creative-122b` dans son catalogue public — je
l'ai vérifié, parmi 81. Et cette clé-là reçoit 404 en le demandant, deux fois,
à un jour d'intervalle.

Ce n'est donc ni transitoire ni une erreur de recopie : **le catalogue public
et ce qu'un compte peut appeler sont deux choses différentes.** Un identifiant
copié d'un catalogue public répare la panne d'un compte, pas celle du compte
voisin.

D'où `usine docteur --reparer` : pour chaque identifiant que le fournisseur ne
connaît plus, l'usine cherche un remplaçant dans le catalogue, **l'appelle**, et
ne le retient que s'il répond. Sans cet appel, on remplacerait un identifiant
mort par un autre — et cela ne se verrait qu'à la fabrication suivante.

Ce qui n'est **pas** réparé, et c'est volontaire : un quota atteint, un crédit
épuisé, une panne du service. Changer de modèle n'y peut rien, et le faire
masquerait la vraie cause — c'est le compte qui est à sec, pas l'identifiant.

## Ce que le rapport disait d'autre, et qui n'est pas réparable

| fournisseur | état | ce qu'il faut faire |
|---|---|---|
| `cerebras` | HTTP 402 | crédit épuisé |
| `mistral` | HTTP 429 | quota du jour atteint |
| `pollinations` | HTTP 402 | budget de la clé épuisé |
| `github` | HTTP 410 | **le service ferme** — rien à corriger |
| `ollama` | HTTP 500 / 404 | serveur local, modèle non téléchargé |
| `llamacpp` | injoignable | serveur local non lancé |

## Trois rôles « sans recours » qui en avaient un

Le rapport de réparation, même jour :

```
[ok] gemini / long     : « gemini-2.5-flash » -> « models/gemini-3.5-flash »
[ok] gemini / standard : « gemini-2.5-flash » -> « models/gemini-3.5-flash »
[!]  gemini / costaud  : « gemini-2.5-flash » ne repond pas,
                         et rien dans son catalogue ne le remplace.
```

Les trois partent du **même identifiant mort**. Deux trouvent un remplaçant
qui répond ; le troisième déclare qu'il n'y en a pas.

Deux causes, et la seconde était invisible sans la première :

1. **Le classement par rôle met les gros modèles en tête.** `costaud` veut le
   plus fort ; le palier gratuit n'en sert aucun. Les quatre essais partaient
   tous dessus sans jamais atteindre le petit modèle qui, lui, répond. La
   borne passe à huit — chaque essai est un vrai appel, donc elle reste, mais
   elle doit laisser sortir du haut du classement.

2. **L'ordre des rôles décidait du sort.** `costaud` passe avant `long` et
   `standard` dans l'ordre alphabétique : quand son tour est venu, rien
   n'avait encore répondu. Un repli lu au fil de l'eau ne l'aurait pas sauvé.
   D'où une **seconde passe**, une fois le fournisseur entier essayé : un rôle
   sans solution reprend un modèle qui a déjà répondu ici même — y compris un
   modèle déjà configuré pour un autre rôle et qui, lui, marchait.

Ce n'est pas le meilleur modèle pour ce rôle — c'en est un qui **marche**, ce
qui vaut mieux qu'un mort. Le rapport le dit : `(repli : aucun modèle de ce
rang ne répond)`.

## Les identifiants par défaut, corrigés sur mesure

| fournisseur | rôle | avant (404) | après |
|---|---|---|---|
| gemini | standard, costaud, long | `gemini-2.5-flash` | `models/gemini-3.5-flash` |
| gemini | rapide | `gemini-2.5-flash-lite` | `models/gemini-3.1-flash-lite` |
| nvidia | rapide | `nvidia/nemotron-nano-3-30b-a3b` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| nvidia | creatif | `writer/palmyra-creative-122b` | `meta/muse-glimmer-30b` |
| nvidia | code | `mistralai/codestral-22b-instruct-v0.1` | `nvidia/nemotron-3-super-120b-a12b` |

**Source : un seul compte, une seule date (15/09/2026).** Chaque remplaçant a
été appelé sur ce compte-là et a répondu. Un autre palier peut ne pas servir
les mêmes — c'est `usine docteur --reparer` qui tranche pour chaque
installation, et ces valeurs ne sont qu'un point de départ moins faux que le
précédent.

Les identifiants retirés sont inscrits dans `MODELES_RETIRES`
(`tests/test_routeur.py`) : un test refuse qu'ils reviennent.

> Deux cas de ce même fichier recopiaient `gemini-2.5-flash` pour tester le
> comptage par modèle. La même donnée périssable à un deuxième endroit : ils
> ont cassé le jour où Google a retiré ses « 2.5 ». Ils lisent désormais la
> configuration — ce qui est testé, c'est le comptage, pas un identifiant.

## « Rien à réparer » ne veut pas dire « tout va bien »

Après correction des identifiants, le rapport donnait :

```
[ok] Aucun identifiant mort : rien a reparer.
```

C'était **exact**, et trompeur. Au même instant : GitHub Models retiré (410),
Cerebras à crédit épuisé (402), Mistral et OpenRouter à quota atteint (429),
Pollinations à budget épuisé.

La réparation avait raison — aucune de ces pannes ne se corrige en changeant
de modèle. Mais elle les écartait **en silence**, et son verdict se lisait
comme un feu vert.

C'est exactement la confusion que ce dépôt passe son temps à supprimer, et
qu'il avait déjà nommée pour `modeles_disparus` : *« personne n'a répondu » ne
doit pas se lire « tout va bien »*. Écrite une fois, la règle n'a pas suivi
jusqu'au contrôle suivant.

Le rapport distingue désormais quatre états :

| état | ce que ça veut dire | le geste |
|---|---|---|
| **réparé** | identifiant mort, remplaçant appelé et retenu | rien |
| **repli** | aucun modèle de ce rang ne répond, un autre a été pris | vérifier que ce rôle reste acceptable |
| **écarté** | quota, crédit, service retiré | un quota se recharge, un crédit s'achète, un service retiré ne revient pas |
| **vivant** | le modèle configuré répond | rien |

Et le cas qui ne doit surtout pas passer pour un succès a désormais sa propre
phrase : *« Aucun identifiant mort — mais aucun modèle n'a répondu non plus.
Ce contrôle ne dit rien. »*

---

# Vérifier les quotas, pas seulement les modèles

*Ajouté le 15/09/2026, à la demande : « on pourrait faire en sorte que l'usine
teste les requêtes, les jetons, pour être sûr qu'on a bien paramétré ? »*

`config.py` le dit de lui-même : *fournisseurs, modèles, quotas — données
recopiées, donc périssables.* Les modèles savent désormais se vérifier
(`--essai`, `--reparer`). Les quotas, eux, étaient recopiés d'une page de
documentation et **rien ne les avait jamais confrontés à quoi que ce soit**.

Or la plupart des services les annoncent dans les en-têtes de **chaque**
réponse. L'usine les jetait : `requete()` ne rendait que le statut et le
corps. Un appel minimal par fournisseur suffit donc — pas un par modèle,
puisque ces limites valent pour le compte.

```bash
usine docteur --quotas
```

## La fenêtre ne se lit pas dans la remise à zéro — corrigé au premier essai

Aucun en-tête ne dit « par jour ». `x-ratelimit-limit-requests: 1000` ne veut
rien dire seul : mille par minute et mille par jour sont deux mondes, et s'y
tromper se trompe d'un facteur **1 440**.

La première version déduisait la fenêtre du temps de remise à zéro : `7.2s`
donc par minute, `23h14m56s` donc par jour. Le premier passage sur un vrai
compte l'a mise en défaut immédiatement :

```
groq  ! requetes  par minute : ecrit        30   annonce      1000
```

Or **1 000 est exactement le `rpd` écrit**, et il est juste. L'audit venait
d'accuser une configuration correcte.

La cause : chez un service à seau de jetons, la remise à zéro est le temps de
**recharge de ce qui vient d'être consommé**, pas la longueur de la fenêtre.
Un appel sur mille d'un quota journalier se recharge en quelques secondes, ce
qui se lit « par minute » et ne l'est pas.

**On ne déduit donc plus rien.** Le chiffre annoncé est confronté aux quatre
chiffres écrits — `rpm`, `rpd`, `tpm`, `tpd` — et l'audit dit auquel il
correspond. La durée de remise à zéro reste affichée, parce qu'elle renseigne
le lecteur ; elle ne rend plus de verdict.

```
groq  v requetes  :      1000 annonce — c'est le quota « requetes par jour » ecrit
```

## Trois verdicts, et les deux derniers comptent autant que le premier

| verdict | ce que ça veut dire |
|---|---|
| **accordé** | le chiffre publié est l'un des quatre qui sont écrits |
| **inconnu** | il n'est aucun des quatre. L'audit **ne conclut pas « faux »** : un service peut publier une limite qu'on n'a pas recopiée. Il rend la mesure, sans verdict |
| **non publié** | il n'en publie aucun. Ce n'est **pas** « tout va bien », c'est « on ne sait pas » |

La distinction n'est pas de la pédanterie : confondre « non publié » et
« conforme » ferait passer un quota jamais vérifié pour un quota vérifié —
exactement la fausse assurance que ce dépôt supprime partout ailleurs. Et
`inconnu` plutôt que `différent` applique l'autre règle du dépôt : **rater un
défaut plutôt qu'en inventer un.** C'est le « différent » de la première
version qui a accusé Groq à tort.

## Le compteur de l'usine, confronté à celui du service

Un `rpd` exact ne protège de rien si le compteur qui s'y compare dérive. Le
service dit combien il en reste ; l'usine dit combien elle en a consommé. Les
deux répondent à la même question.

L'écart est **rendu, pas jugé** : l'usine ne connaît pas les appels faits
depuis une autre machine avec la même clé, et accuser sur cette base serait
crier à tort.

### La sonde doit se retirer de sa propre mesure

Le premier rapport réel disait aussi :

```
consomme : 333 selon le service, 0 selon l'usine  — ECART
```

Les 333 jetons étaient **ceux de la sonde elle-même**. Elle passe
volontairement hors du routeur — c'est tout l'intérêt : mesurer sans que le
routeur bascule à sa place — donc elle n'apparaît dans aucun compteur de
l'usine. L'audit criait à l'écart sur sa propre requête, et il l'aurait fait à
chaque exécution.

`essai_direct` rend donc ce que son appel vient de coûter (les
`usage.total_tokens` du service, et la requête), et l'audit le soustrait avant
de comparer. Un instrument qui se mesure lui-même ne mesure rien.

Le résultat est **planché à zéro** : selon les services, `remaining` est
calculé avant ou après le décompte de notre propre appel. Sur un compte neuf,
la première convention donne « −1 consommé », un chiffre qui se lit comme un
défaut du service alors qu'il n'est qu'une convention d'en-tête.

### Le compteur comparé doit être celui de la bonne fenêtre

Défaut trouvé en relisant la correction elle-même, pas par un test. Quand la
fonction de fenêtre a cessé de répondre `"minute"` pour répondre `"moins d'une
minute"`, le comparateur qui lisait cette valeur **n'a rien cassé** : il est
simplement tombé toujours dans la branche « jour ». Le chiffre par minute du
service se comparait au compteur du jour de l'usine — un écart inventé à
chaque appel.

Rien n'échouait, parce que le résultat restait un entier plausible. C'est la
forme de défaut la plus chère de ce dépôt : **une mesure fausse a l'air d'une
mesure.** Le comparateur lit désormais la correspondance, qui nomme sa
fenêtre, et un test distingue les quatre compteurs.

## Ce qu'on ne sait pas lire est montré tel quel

Les en-têtes de quota non reconnus sont affichés bruts plutôt que jetés. Aucun
standard ne fixe leur nom, et chaque service a sa forme. Les jeter
garantirait de ne jamais apprendre celles qu'on ignore ; les montrer, c'est
les coder demain.

## Le fournisseur payé ne recevait pas un seul appel

C'est le message rendu par la correction ci-dessus qui l'a nommé, dès la
première exécution :

```
opencode : HTTP 400
  Error from provider (Console Go): Request is missing
  x-opencode-session and cannot be routed
```

Six modèles, six cents requêtes par jour, un abonnement payé — et **aucun
appel n'aboutissait**. Le code seul (`400`) n'en disait rien ; il aura fallu
afficher le corps de la réponse pour que le défaut se nomme lui-même. C'est
la démonstration la plus directe de la règle du dépôt : *ne pas croire le
code de retour, lire le contenu.*

### Un identifiant de session dérivé de la clé

Il fallait une valeur **stable** — une session qui change à chaque appel n'est
pas une session — et **propre au compte**. Elle est dérivée de la clé par
condensat :

- deux installations du même compte partagent la même session, ce qui est le
  comportement attendu ;
- il n'y a rien à persister, donc rien à migrer ni à perdre ;
- une clé changée change la session sans qu'on ait à y penser ;
- le condensat ne laisse pas remonter à la clé, ce qui compte : cet
  identifiant part sur le réseau à chaque appel.

La **forme** retenue est celle d'un UUID. Aucun service n'a dit l'exiger —
l'authentification d'OpenCode passe avant le contrôle de session, donc le
format n'a pas pu être mesuré sans clé. C'est la forme la plus courante, donc
la moins susceptible d'être refusée. Si elle l'est quand même, le corps du
refus le dira maintenant, en toutes lettres.

### Quatre endroits construisaient ces en-têtes

Le corriger à un seul endroit aurait donné le défaut favori de ce dépôt : la
chose marche ici, échoue là, et l'écart ne se voit qu'à l'usage. Le routeur,
la sonde directe et les deux lecteurs de catalogue passent désormais tous par
`config.entetes_appel`.

Le garde-fou lit la **structure**, pas un nom : il cherche toute fonction qui
pose elle-même son `Authorization` **et** qui parle de `base_url`. Chercher la
chaîne « entetes_appel » quelque part dans le fichier aurait été satisfait par
un commentaire — c'est l'homonymie qui a déjà laissé passer une fonction sans
appelant et deux réglages orphelins. Un test montre le détecteur en train
d'accuser un cas fabriqué, parce qu'un détecteur écrit après la correction ne
peut pas avoir été vu échouer sur le vrai défaut.

## L'écart de 217 jetons : une dérive, ou une convention ?

Toujours au premier passage, chez Groq :

```
jetons : 8000 annoncé — c'est le quota « jetons par minute » écrit
         il en reste 7667 pour cette fenêtre
         consommé : 217 selon le service, 0 selon l'usine — ÉCART
```

Le service dit avoir décompté **333** jetons ; la sonde n'en avait produit que
**116**. Deux lectures, et elles n'appellent pas le même geste :

1. le compteur de l'usine dérive ;
2. le service décompte la sortie **demandée** (`max_tokens`) et non celle
   produite.

La seconde n'est pas académique : `max_sortie` vaut 8192 chez Groq, pour un
plafond de 8 000 jetons **par minute**. Si la réservation est décomptée, un
seul appel épuise la minute entière — et l'usine, qui compte les
`usage.total_tokens` réellement rendus, croirait avoir de la marge.

**On ne tranche pas à la place de la mesure.** La sonde rend désormais ce
qu'elle a demandé (`max_tokens`) et ce qu'elle a produit
(`completion_tokens`), et le rapport constate l'égalité **quand elle a lieu** :

```
consommé : 217 selon le service, 0 selon l'usine — ÉCART
l'écart vaut exactement la réservation non consommée (217) :
ce service décompte la sortie DEMANDÉE, pas celle produite.
```

**Confirmé le 15/09/2026**, à l'exécution suivante : la ligne s'est affichée.
Et relue avec les chiffres complets, elle dit plus que prévu — le seau était
**plein** avant l'appel (8000 − 7667 = 333, soit exactement la réservation).
Les 333 étaient donc *entièrement* ceux de la sonde, et les 217 restants
n'étaient rien d'autre que la mauvaise soustraction.

La sonde se retire désormais de sa mesure **au bon tarif** : la réservation
quand le service en applique une, la consommation réelle sinon. C'est la même
faute que la première fois, d'un cran plus fin — l'audit se retirait de sa
propre mesure, mais pas au prix que le service facture.

L'écart disparu, la ligne qui l'expliquait n'avait plus de cas où s'afficher :
elle a servi à trancher l'hypothèse, elle est retirée. Un test garde qu'une
consommation venue d'ailleurs, elle, reste visible — le but n'est pas de faire
disparaître tout écart.

> **Conséquence ouverte, non traitée ici.** Si Groq débite la réservation,
> alors le compteur de l'usine — qui enregistre les `usage.total_tokens`
> rendus — sous-estime ce que le service décompte. Avec `max_sortie` à 8192
> pour 8 000 jetons par minute, un seul appel peut épuiser la minute pendant
> que l'usine se croit à 3 000. Une seule mesure, sur un seul service : pas
> de quoi changer le comptage du routeur. À vérifier sur un second service
> qui publie ses en-têtes.

## Un code HTTP ne dit pas quoi faire, le message du service si

Le premier rapport réel contenait aussi cette ligne, sur un fournisseur
**payé** :

```
opencode : HTTP 400 — rien n'a pu etre lu.
```

« 400 » ne permet ni de réparer, ni de constater qu'il n'y a rien à réparer.
Le corps de la réponse le permet presque toujours — c'est lui qui distingue
« ce modèle n'est pas ouvert à votre offre » d'un paramètre mal formé.

Le rapport rend donc le message du service, passé par `securite.expurger` :
une clé peut se trouver dans un message d'erreur, et un diagnostic ne doit
jamais être l'endroit où elle sort.

**Défait de son enveloppe, et plié plutôt que tranché.** Les cinq corps relevés
n'ont aucune forme commune — `message` à la racine chez Cerebras et Mistral,
`error.message` chez OpenCode et GitHub, du texte brut chez Pollinations.
Tronqués à cent cinquante signes, quatre sur cinq perdaient leur fin :

```
{"message":"Payment required to access this resource. Visit your
billing tab.","type":"payment_required_error","param":"quota","code":
"payment_require
```

Quarante signes d'enveloppe avant la phrase utile, et la coupe qui tombe dans
le code d'erreur. Chez Pollinations, elle emportait le **lien** qui permet de
relever le budget — c'est-à-dire le seul geste à faire.

Ce qui ne se reconnaît pas est rendu tel quel : une enveloppe lisible vaut
mieux qu'une phrase perdue en voulant faire mieux. Et le pliage ne coupe ni
sur un trait d'union ni au milieu d'un mot — la première version tranchait
`edit-key?id=…` en deux et rendait le lien inutilisable, le défaut qu'on
corrigeait déplacé d'un cran.

## Ce que le premier passage sur un vrai compte a publié

*15/09/2026, huit clés.*

| fournisseur | ce qu'il publie |
|---|---|
| `groq` | requêtes **et** jetons, avec restes et remises à zéro |
| `gemini`, `openrouter` | aucun chiffre — `non publié`, donc « on ne sait pas » |
| `opencode` | HTTP 400 : en-tête de session manquant — **corrigé** |
| `cerebras` | HTTP 402 : crédit épuisé — *Visit your billing tab* |
| `mistral` | HTTP 429 : quota du jour atteint |
| `github` | HTTP 410 : *scheduled retirement brownout* — le service ferme |
| `pollinations` | HTTP 402 : budget de la clé épuisé, avec le lien pour le relever |

Trois services sur huit publient des en-têtes de quota, et il n'existe aucun
standard sur leur nom. Ceux qu'on ne sait pas lire sont montrés bruts.
