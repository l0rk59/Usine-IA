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
- Plusieurs clés chez un même fournisseur multiplient les requêtes, **pas** les
  jetons si elles appartiennent au même projet : chez Google, les quotas se
  comptent par projet, pas par clé.

## Comment ces corrections sont gardées

Dix mutations, une par correction. Chacune remet le défaut dans le code, lance
`tests/test_routeur.py` et `tests/test_tableau.py`, et vérifie que la suite
**échoue**. Un test qui passe encore alors que le défaut est revenu ne garde
rien — c'est ainsi qu'une première version du test de quota par modèle a été
prise en défaut : elle saturait flash (250 requêtes), un chiffre trop bas pour
faire la différence avec le comptage global. Elle sature maintenant flash-lite
(1 000) et vérifie que flash reste ouvert.
