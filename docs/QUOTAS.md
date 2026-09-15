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

## La fenêtre ne se lit pas dans le nom, mais dans la remise à zéro

Aucun en-tête ne dit « par jour ». `x-ratelimit-limit-requests: 1000` ne veut
rien dire seul : mille par minute et mille par jour sont deux mondes.

C'est `x-ratelimit-reset-requests` qui tranche — `7.2s` désigne une limite par
minute, `23h14m56s` une limite par jour. Comparer un chiffre à `rpm` plutôt
qu'à `rpd` se trompe d'un facteur **1 440**.

Entre trois et trente minutes, l'audit **ne tranche pas**. Un quota comparé à
la mauvaise fenêtre est pire qu'un quota non vérifié : il produit un
« conforme » ou un « différent » tiré à pile ou face, sur un chiffre que
personne n'ira revérifier.

## Trois verdicts, et le troisième compte autant

| verdict | ce que ça veut dire |
|---|---|
| **accordé** | le service publie un chiffre, et c'est celui qui est écrit |
| **différent** | il en publie un autre — **c'est lui qui a raison**, c'est lui qui applique |
| **non publié** | il n'en publie aucun. Ce n'est **pas** « tout va bien », c'est « on ne sait pas » |

La distinction n'est pas de la pédanterie : confondre « non publié » et
« conforme » ferait passer un quota jamais vérifié pour un quota vérifié —
exactement la fausse assurance que ce dépôt supprime partout ailleurs.

## Le compteur de l'usine, confronté à celui du service

Un `rpd` exact ne protège de rien si le compteur qui s'y compare dérive. Le
service dit combien il en reste ; l'usine dit combien elle en a consommé. Les
deux répondent à la même question.

L'écart est **rendu, pas jugé** : l'usine ne connaît pas les appels faits
depuis une autre machine avec la même clé, et accuser sur cette base serait
crier à tort.

## Ce qu'on ne sait pas lire est montré tel quel

Les en-têtes de quota non reconnus sont affichés bruts plutôt que jetés. Aucun
standard ne fixe leur nom, et chaque service a sa forme. Les jeter
garantirait de ne jamais apprendre celles qu'on ignore ; les montrer, c'est
les coder demain.

> Ces en-têtes n'apparaissent que sur l'endpoint facturé. Ils n'ont donc pas
> pu être vérifiés depuis un poste sans clé : la première exécution sur un
> vrai compte est celle qui nous apprendra quels services publient quoi.
