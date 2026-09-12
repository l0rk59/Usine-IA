# Le routeur IA et les agents : ce qui a été corrigé

Audit de `core/llm.py`, `core/config.py`, `core/cles.py`, `core/http.py`,
`core/budget.py`, `agents/base.py` et `agents/equipe.py`. Chaque constat a été
**mesuré sur le code**, corrigé, et gardé par un test qui échoue quand on
remet le défaut.

Point commun aux neuf : **aucun ne provoque d'erreur**. Ils font perdre
quelque chose en silence — une fin de chapitre, un quota, une attente, un
repos, une entrée de cache.

---

## 1. Une réponse tronquée passait pour complète

`finish_reason` n'apparaissait nulle part dans le dépôt. Or le plafond de
jetons était figé à **4096** dans neuf appels, et le calcul recopié à chaque
fois (`min(4096, mots × 2.6)`).

Mesuré avec le ratio que le code lui-même applique :

| Section | Jetons demandés | Servis | |
|---|---:|---:|---|
| `mini` → `long` | 1 820 – 3 380 | tous | ✅ |
| `--mots 1600` | 4 160 | 4 096 | ❌ |
| `--mots 4000` *(le maximum documenté)* | 10 400 | 4 096 | ❌ **40 %** |

Les quatre paliers y échappaient ; le sur-mesure, non. Et comme rien ne lisait
`finish_reason`, un chapitre tranché au milieu d'une phrase traversait tout le
contrôle qualité sans que rien ne le signale.

**Corrigé en trois endroits.** Le calcul vit maintenant dans
`pipelines/base.jetons_pour()`, avec un plafond de 8192. Chaque fournisseur
déclare ce qu'il sait réellement émettre (`Provider.max_sortie`) et le routeur
y ramène la demande. Et `Reponse.tronquee` dit la vérité : une réponse coupée
n'entre **pas** au cache — la resservir indéfiniment fixerait la coupure pour
toujours.

Même défaut dans la boucle de correction : `min(4096, len(texte) // 2 + marge)`
coupait toute réécriture d'un texte de plus de huit mille caractères, et le
garde-fou « texte tronqué » d'en face rejetait alors la correction. Une boucle
qui corrigeait sans jamais rien appliquer.

## 2. Les pannes consommaient le quota

`compteur_jour` comptait **toutes** les lignes, échecs compris. Cinquante
coupures réseau brûlaient donc 50 des 500 requêtes du jour d'un fournisseur
qui n'avait rien servi — le scénario courant sur un réseau mobile.

La règle est maintenant explicite : un appel consomme le quota d'un
fournisseur s'il l'a **réellement traité** — une réponse servie, ou un refus
pour cause de débit (429), que tous les services décomptent. Une coupure
réseau ou un 500 ne consomment rien chez eux.

Le compteur **par minute**, lui, compte toujours tout : une requête refusée a
bien été envoyée, et elle pèse sur le débit.

## 3. `Retry-After` était ignoré

`HttpErreur` ne portait pas les en-têtes de la réponse. Sur un 429, le routeur
dormait 90 s (fournisseur) ou 120 s (clé) — quel que soit le délai demandé par
le service, parfois cinq secondes, parfois dix minutes.

L'en-tête est lu sous ses deux formes légales (un nombre de secondes, ou une
date HTTP), borné à une heure, et le repli d'origine reste quand le service se
tait.

## 4. Le repos ne survivait pas à un redémarrage

`_REPOS` et `Cle.repos_jusqu_a` vivaient dans des dictionnaires de module.
Android tue le processus sans préavis : au redémarrage, un fournisseur qui
venait de répondre 429 était resollicité dans la seconde — et répondait 429,
ce qui, lui, consomme du quota.

La donnée était pourtant déjà en base, dans `cles_journal`. Il ne manquait que
de la relire. C'est fait, pour les fournisseurs comme pour les clés.

## 5. Le cache confondait deux appels différents

La clé portait les messages, le rôle et la température — pas le **plafond de
jetons** ni le **mode JSON**. Deux appels ne différant que par eux
partageaient une entrée, donc un texte : parfois un texte coupé plus court que
ce que le second demandait.

## 6. Un budget en jetons, pas seulement en appels

Plusieurs paliers gratuits comptent en **jetons** — Cerebras et Gemini
l'annoncent dans leurs propres notes de `config.py`. Un budget qui ne compte
que les requêtes laisse donc passer le plafond qui compte vraiment.

```bash
usine reglages --definir budget_jetons_jour=200000
usine usine demarrer --budget jetons_jour=200000
```

La colonne `tokens` était déjà remplie depuis toujours ; seul le plafond
manquait.

## 7. Un rôle « long contexte »

Il y avait `rapide | standard | costaud`. Le million de jetons de contexte de
Gemini était noté dans la configuration et jamais exploité.

Le rôle `long` existe maintenant, et il a **un appelant réel** : la fermeture
d'une partie de roman, qui condense plusieurs scènes d'un coup. C'est le seul
appel de l'usine qui y gagne vraiment — et le seul où tronquer la matière à
six mille caractères perdait des scènes entières (vingt-quatre mille
désormais). Les fournisseurs sans modèle dédié retombent sur `standard` :
déclarer le rôle ne coûte rien là où il n'apporte rien.

## 8. La relecture croisée était annoncée, pas mesurée

La chaîne fait relire par un **autre** modèle que celui qui a écrit — c'est
son mécanisme central, et `eviter` le met en œuvre. Mais `eviter` se désactive
quand un seul fournisseur reste disponible : mieux vaut une relecture par le
même modèle que pas de relecture du tout. Ce repli est le bon ; il n'était
simplement écrit nulle part.

`Critique` retient désormais qui a écrit et qui a relu, et le rapport qualité
porte la part réellement croisée :

```json
"relecture_croisee": {"relectures": 12, "sur_un_autre_modele": 12, "part": 1.0}
```

## 9. Personne ne lisait le produit entier

Chaque agent travaille section par section. Une promesse faite dans
l'avant-propos et jamais tenue, deux chapitres qui donnent des conseils
opposés, un terme défini deux fois différemment : aucun de ces défauts n'est
visible depuis une section seule, et aucun ne se mesure en Python.

```bash
usine ebook "mon sujet" --relecture-ensemble
```

**Ce n'est pas la résurrection de `equipe.controler()`**, retiré lors d'un
audit précédent. Celle-là rendait un *verdict* — une note avant-vente, que le
contrôle déterministe donne gratuitement et mieux. Celle-ci ne juge ni le
style ni la qualité : elle cherche uniquement ce qui **se contredit**. Et elle
est en option, parce que c'est un appel de modèle par produit sur un long
texte.

Une section citée par le modèle mais absente du produit est retirée de la
référence — le problème peut être vrai, la référence fausse ne doit pas l'être.

---

## Ce qui a été écarté, et pourquoi

- **Un agent vérificateur de faits.** Sans accès web, il ne peut que confirmer
  les croyances du modèle. Pire que rien, parce qu'il rassure.
- **Un fournisseur de plus.** La contrainte est le quota, pas le choix.
- **Le parallélisme.** Les limites par minute sont ce qui borne la production
  sur téléphone : paralléliser accélère surtout l'arrivée des 429.
- **Le streaming.** La CLI journalise déjà section par section, et cela
  compliquerait la bascule de fournisseur pour un gain cosmétique.
- **Une expiration du cache.** Il est là pour ne pas redépenser de quota ;
  une péremption le ferait redépenser en silence. `usine cache --vider` existe.

## Comment ces corrections sont gardées

`tests/test_routeur.py` et `tests/test_agents.py`. Chacun des neuf défauts a
été **remis dans son état d'avant** pour vérifier que la suite tombe — les
neuf tombent. Deux ne tombaient pas au premier essai, et c'étaient de vrais
trous de couverture : le `Retry-After` n'était testé qu'en isolation, jamais
dans le routeur ; et le filtre des sections inventées n'était jamais exercé,
parce que le simulateur renvoyait un cas que l'autre filtre écartait avant.
