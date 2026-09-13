# Ce qu'un utilisateur a trouvé en dix minutes

Un passage de dix minutes sur un vrai téléphone, avec de vraies clés, a fait
remonter plus de défauts que l'audit de la veille. Cette note dit lesquels, et
ce qu'ils ont en commun.

Ils ont ceci en commun : **aucun ne faisait échouer quoi que ce soit.** La
suite de tests était verte, la fumée passait, les dix chaînes produisaient.

## 1. Un quota épuisé qui ne ressemblait pas à un quota épuisé

Premier appel réel à un fournisseur, 13/09/2026 :

```
HTTP 200 · finish_reason: "stop" · usage renseigné
contenu : « The API key used for this request has reached its budget. »
```

Tous les signaux disent « réponse valide ». Le routeur l'a donc acceptée, mise
en cache, et écrite dans un chapitre. Deux plaintes de l'utilisateur n'en
faisaient qu'une : *« des caractères buggés dans les produits »* et *« quand un
quota est dépassé, l'usine ne continue pas »*.

La règle qui en sort : **ne pas croire le code HTTP, lire le texte**. Détail
dans `usine/core/texte.py`.

Le même passage retire ce que le modèle ajoute à sa réponse : le brouillon des
modèles de raisonnement entre `<think>` et `</think>`, les jetons de dialogue,
les accents abîmés par un décodage raté. Rien de tout cela n'échouait non plus.

## 2. Deux fournisseurs sur deux ne servaient aucun des modèles configurés

Relevé sur `GET /v1/models`, le même jour :

| | configuré | servi |
|---|---|---|
| NVIDIA | `meta/llama-3.1-8b`, `meta/llama-3.3-70b` | 82 modèles, **aucun des deux** |
| OpenRouter | `llama-3.3-70b:free`, `deepseek-chat-v3:free` | 19 modèles `:free`, **aucun des deux** |

Chaque appel rendait 404, le routeur mettait le fournisseur au repos une
demi-heure, et une clé valide ne servait à rien sans que rien ne le dise.

Recopier les bons identifiants aurait réparé la panne du jour et pas celle du
mois prochain. Le fournisseur, lui, sait ce qu'il sert : on le lui demande, et
on choisit **par rôle** plutôt que par nom.

## 3. Le produit se coupait et ne reprenait pas

Le pipeline n'attrapait que `BudgetEpuise`. `PlusDeFournisseur` — quota atteint
partout, réseau coupé, clés refusées — remontait jusqu'à la CLI et emportait la
fabrication entière.

Mesure : réseau coupé au sixième appel d'un ebook de huit chapitres, il restait
sur le disque **un** fichier, `plan.json`. Le plan, l'avant-propos et le premier
chapitre — relu, contrôlé, corrigé — avaient été produits, payés, puis perdus.

Le cache n'y suffisait pas : une section passe par plusieurs appels enchaînés,
et chaque passe forge une invite qui dépend de la précédente. Ce qu'il faut
garder n'est pas l'appel, c'est **la section finie**.

## 4. Ce qui existait sans avoir de nom

Le roman était fabricable depuis toujours — `usine nouvelle --chapitres 40` — et
ne figurait ni au catalogue, ni au menu, ni au tableau de bord. *Personne ne
devine une fonctionnalité qui n'a pas de nom.*

Même forme pour les réglages : **dix-huit sur vingt-six** ne se changeaient
qu'en ouvrant un fichier JSON à la main.

## 5. Sept agents qui ne se parlaient pas

L'éditeur critiquait, le réviseur appliquait. Une file d'attente où chacun
corrige le précédent sans jamais lui répondre.

Le défaut est mesurable : une critique d'éditeur peut être **fausse**. « Ajoute
un chiffre » fait inventer une statistique ; « donne un exemple concret » fait
fabriquer un témoignage. Le réviseur appliquait tout, et le contrôle qualité
signalait ensuite un chiffre sans source que personne n'avait demandé.

## 6. Le menu et la page, tous deux à plat

Dix-sept entrées sur un niveau dans le menu Termux, quatorze cartes empilées
dans le tableau de bord. Il fallait faire défiler toute la veille de niche pour
atteindre ses produits, et rien ne disait ce qui allait avec quoi.

Les deux sont rangés maintenant, avec **les mêmes sections dans le même
ordre** : deux interfaces qui rangent les mêmes choses différemment obligent à
apprendre deux fois.

---

## Ce que les garde-fous n'avaient pas vu, et pourquoi

Trois contrôles existaient déjà pour attraper exactement ces défauts. Ils
étaient verts. Tous les trois échouaient de la même façon : **ils cherchaient un
nom quelque part dans le code**, et un nom se trouve partout.

| Contrôle | Ce qu'il a laissé passer | Pourquoi |
|---|---|---|
| fonction sans appelant | `http.en_ligne` | le mot servait ailleurs de nom de paramètre |
| réglage orphelin | `plateforme`, `devise` | les mots apparaissent dans toute ligne parlant de vente |
| réglage orphelin | `couverture` | classe CSS du moteur EPUB, sujet de test A/B |

Un détecteur qui se satisfait d'une homonymie ne garde rien — et il est pire
que pas de détecteur, parce qu'il fait croire que le point est couvert. Ils
lisent maintenant la structure : l'arbre syntaxique pour les fonctions, la
ligne et son contexte pour les réglages.

## Où c'est

| | |
|---|---|
| `usine/core/texte.py` | brouillons de modèle, encodage, refus déguisés |
| `usine/core/modeles.py` | catalogue vivant, choix par rôle, substitution |
| `usine/pipelines/carnet.py` | ce qui est déjà écrit ; la reprise |
| `usine/pipelines/brief.py` | ce que l'usine décide quand on ne lui dit rien |
| `usine/agents/equipe.py` | `contester`, `arbitrer`, `deliberer` |
| `usine/core/specs.py` | ce qui manque à cet appareil, en Markdown |
| `usine/core/maj.py` | mise à jour sans toucher à l'atelier |

Voir aussi `docs/PANNES.md` (disque, base, réseau) et
`docs/AUDIT-INVARIANTS.md` (la méthode : mesurer un invariant sur tout le code,
corriger, puis poser le garde-fou).
