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

## 10. Un modèle qui ne sait pas répondre en JSON coûtait la production

Trouvé en provoquant la panne plutôt qu'en la supposant : un simulateur qui
répond en prose à chaque appel, et l'on regarde ce que l'utilisateur obtient.

`generer_json` réessayait trois fois **avec la même liste d'exclusions** — donc
chez le même fournisseur. Or un modèle qui répond en prose à une consigne
« JSON uniquement » recommencera : c'est presque toujours un modèle trop petit
pour tenir un format. Trois appels brûlés, puis la chaîne mourait sur son
premier pas, la construction du plan.

Le mécanisme pour l'éviter existait déjà — `generer(eviter=...)`, écrit pour la
relecture croisée. Le fournisseur qui échoue est maintenant écarté au fur et à
mesure, et il reste neuf candidats.

Quand tous ont échoué, `generer` refuse d'écarter tout le monde et le premier
revient, à température plus haute : mieux vaut un essai de plus que pas
d'essai du tout.

Le message d'échec a changé aussi. *« JSON introuvable dans la réponse du
modèle »* n'apprend rien à qui produit depuis un téléphone ; il nomme
désormais les fournisseurs tentés et dit quoi faire.

### La bonne réponse n'entrait jamais au cache

Seul le premier essai lit le cache, pour qu'une réponse illisible n'y soit pas
relue à chaque essai. Mais il y **écrit** aussi, et sa réponse illisible
comprise ; les essais suivants, hors cache, n'écrivaient rien. Le cache
gardait donc le texte inutilisable, jamais le JSON qui avait servi.

Mesure du 24/09/2026, avec un simulateur qui rend du texte au premier appel :
la même demande répétée coûtait **un appel à chaque fois**, et rendait chaque
fois une réponse différente. C'est exactement ce que fait une reprise : elle
rejoue les demandes du produit coupé, au moment où les quotas manquent, en
comptant sur le cache pour ne rien payer. Les onze chaînes qui n'ont pas de
carnet redemandaient ainsi leur plan, en recevaient un autre, et refaisaient
toutes les sections qui en dépendent.

Le JSON lisible est maintenant rangé sous la clé du premier essai. La même
demande ne coûte plus rien la seconde fois et rend la même réponse.

## 11. Le modèle qui refuse, imprimé à la place du chapitre

Mesure du 24/09/2026, un ebook dont un modèle refuse le chapitre 2 :
« Je suis désolé, mais je ne peux pas vous aider à rédiger ce contenu. »
était imprimé à la place du chapitre, et le produit marqué « prêt ». HTTP 200,
une réponse non vide : rien n'échouait. Le cas n'a rien d'exotique — une dark
romance ou un thriller violent sont des niches qui se vendent, et exactement
ce que certains modèles gratuits refusent.

`texte.refus_du_modele` reconnaît ce refus à deux signaux, tous deux
nécessaires, dans une réponse courte (600 caractères au plus) : elle **s'ouvre**
sur une formule de refus, et elle **nomme** ce qu'elle refuse (« cette
demande », « ce contenu », « help with », « guidelines »…). Une réplique qui
commence par des excuses s'ouvre sur un guillemet ou un tiret, et n'est pas
regardée. Comme pour les messages de service, zéro accusation sur tout ce que
la suite fabrique.

Le routeur passe alors au modèle suivant — un autre peut accepter — sans rien
mettre en cache. Quand **tous** ont refusé, il lève `DemandeRefusee` : ce
n'est pas un silence des fournisseurs, et l'attendre ne changerait rien.
Dans les chaînes qui écrivent section par section (ebook, formation, fiction),
la section manque et le dit, et le produit reste « en cours » ; ailleurs, le
produit échoue et le dit. Dans la boucle, la niche compte son essai au lieu
d'attendre. Il suffit qu'un seul fournisseur n'ait pas été essayé (au repos, quota
atteint) pour que le routeur ne tranche pas : il aurait peut-être accepté.

Une réécriture refusée — correction, révision — garde le texte d'avant.

Ce que le détecteur ne voit pas, et ne prétend pas voir : un refus long, ou
qui ne dit pas ce qu'il refuse, et un refus rendu comme une erreur HTTP de
modération, que le routeur ne distingue pas d'une panne.


---

# Ce qu'un journal de fabrication a révélé

*Nouvelle de cinq scènes, 15/09/2026. Une scène écrite sur cinq, note 4,33.*

Le journal disait tout ce qu'il fallait — à condition de le lire dans le bon
ordre. Les trois causes étaient à deux étapes de l'endroit où le défaut se
voyait.

## 1. Une substitution retenue sur un mensonge

```
nvidia : « writer/palmyra-creative-122b » n'est plus servi,
         l'usine passe a « meta/muse-glimmer-30b »
```

Le lendemain, le catalogue public de NVIDIA servait ce modèle — **parmi 81**.
Le 404 disait donc autre chose : un palier qui n'y donne pas droit, une panne
d'un instant, un routage interne.

Et la substitution était **retenue** : écrite en base, valable pour toutes les
sessions suivantes. `writer/palmyra-creative-122b` existe exactement pour
écrire de la fiction — toutes les nouvelles suivantes auraient été écrites par
un modèle plus petit, **définitivement**, sans que rien ne le dise.

La règle : *une substitution gardée pour toujours demande une preuve que le
modèle est parti, pas un code de retour qui le prétend.* Si le fournisseur
**liste encore** le modèle qu'il vient de refuser, il se contredit — on
substitue pour que la fabrication en cours aboutisse, mais **pour cette
session seulement**. Le lancement suivant redemande le modèle configuré.

C'est la deuxième règle du dépôt appliquée un cran plus loin : ne pas croire
le code de retour, et ne pas croire non plus ce qu'on en a déduit.

> Si votre atelier a déjà figé une substitution, `usine cache --catalogues`
> l'oublie sans toucher aux réponses payées.

## 2. Un service retiré n'est pas une panne

```
github/ghp_xN***Zj8 : HTTP 410 : Gone
```

Le corps disait `github_models_retirement_brownout` : **GitHub Models est en
cours de retrait**. Le message brut donnait à chercher une clé ou un
identifiant de modèle, alors qu'il n'y avait rien à corriger.

HTTP 410 est la seule réponse qui dise « parti, et ne reviendra pas ». La
distinguer d'un 404 ou d'un 503 change le geste : il n'y a rien à réparer, il
faut cesser de compter dessus.

## 3. Une grille de beats coupée, et la résolution perdue

```
01:44:04 reponse coupee au plafond (groq, 2250 jetons)
...
[majeur] aucune scene ne livre le beat « resolution »
```

Les deux lignes sont séparées par quatre minutes et trois étapes, et c'est la
même cause. Pour cinq scènes, la formule accordait `1600 + 5 × 130 = 2250`
jetons — exactement le chiffre du journal.

Le JSON tronqué **se relit en partie**, donc rien n'échouait : la grille
perdait ses derniers beats, et le contrôle de continuité signalait le manque
deux étapes plus loin.

La part fixe de cette grille — les huit beats, les intrigues, la charpente
JSON — ne dépend pas du nombre de scènes : c'était le **plancher** qui était
trop bas, pas la pente. Il passe à `2600 + n × 150`.

Mais un chiffre choisi à la main finit toujours par être trop petit pour un
cas qu'on n'avait pas vu — celui-ci l'a été. Le routeur **mesure déjà** la
coupe (`finish_reason: length`) : la chaîne la lit désormais et **redemande
une fois**, au double. Une seule : si le double ne suffit pas, insister
coûterait un troisième appel pour le même résultat.

## 4. Un serveur local éteint coûtait onze secondes par appel

Le refus de connexion devient, dans `core/http.py`, une `HttpErreur` de statut
0 marquée temporaire. C'est juste pour un service distant : sur un téléphone qui
passe du wifi à la 4G, la connexion revient vraiment une seconde plus tard.
C'est faux pour `127.0.0.1` : rien n'écoute sur ce port, et rien n'y écoutera
1,5 seconde plus tard — seul l'utilisateur peut lancer ollama.

Mesure du 23/09/2026, ollama et llama.cpp déclarés mais éteints : deux essais
par serveur, attente entre les deux, **onze secondes par appel**. Et le routeur
ne descend jusqu'au repli local que quand les services distants sont épuisés —
donc à chaque appel d'une fin de roman. Après : **0,04 s**, un essai par serveur.

Le routeur descend la chaîne des causes (`URLError.reason`, `__context__`)
plutôt que de lire le message, qui change selon le système et la langue. Pas de
repos pour autant : un refus est instantané, et c'est ce qui permet de
reprendre ollama à la seconde où on le lance. Un délai dépassé en local reste
rejoué — un modèle en cours de chargement répond parfois au second essai —, et
un refus chez un service distant aussi.

## 5. Le routeur sait quand un fournisseur rouvrira

`llm.prochaine_ouverture()` relit ce que le routeur a lui-même posé — repos par
fournisseur et par clé, quotas du jour qui repartent à minuit UTC — et rend le
délai avant qu'un fournisseur puisse servir, `0` s'il le peut déjà, `None` si
aucun ne le pourra sans geste humain. C'est ce qui permet à l'usine continue
d'attendre au lieu de s'arrêter ([USINE-CONTINUE.md](USINE-CONTINUE.md)). Ce
qu'il ne voit pas est écrit dans sa docstring : un réseau coupé, un crédit
épuisé sans repos posé. D'où le plancher d'attente côté boucle.

## 6. Le message qu'on lit quand plus rien ne répond

C'est le message qu'on lit au moment précis où il faut décider quoi faire.
Mesure du 24/09/2026, huit fournisseurs actifs, chacun en panne à sa façon —
avant :

```
Tous les fournisseurs ont echoue :
  - gemini/cle-fa***xxx : HTTP 401 : Unauthorized
  - mistral/cle-fa***xxx : HTTP 503 : Service Unavailable
  - mistral/cle-fa***xxx : HTTP 503 : Service Unavailable
  - openrouter/cle-fa***xxx : HTTP 0 : reseau indisponible : timed out
  - openrouter/cle-fa***xxx : HTTP 0 : reseau indisponible : timed out
  - cerebras : en repos
  - pollinations : HTTP 500 : Internal Server Error
  - pollinations : HTTP 500 : Internal Server Error
  - ollama : serveur injoignable [...]
  - llamacpp : serveur injoignable [...]
```

Il gardait les **dix dernières lignes** d'une liste qui en comptait onze — une
par essai. Groq, le premier essayé, avait disparu. Trois fournisseurs
apparaissaient deux fois ; « en repos » ne disait ni jusqu'à quand ni
pourquoi ; une clé refusée se lisait « HTTP 401 : Unauthorized » ; les trois
fournisseurs sans clé n'étaient nommés nulle part. Après :

```
Aucun fournisseur n'a pu repondre.
  Essayes :
    - groq : limite de debit atteinte (HTTP 429) — au repos jusqu'a 01:04
    - gemini : cle refusee (HTTP 401) : verifiez GEMINI_API_KEY dans .env — au repos jusqu'a 02:02
    - mistral : HTTP 503 : Service Unavailable (2 essais)
    - openrouter : HTTP 0 : reseau indisponible : timed out (2 essais)
    - pollinations : HTTP 500 : Internal Server Error (2 essais)
    - ollama : serveur injoignable [...]
    - llamacpp : serveur injoignable [...]
  Pas essayes :
    - cerebras : au repos jusqu'a 01:12
  Sans cle : nvidia, opencode, cloudflare
```

Une ligne par fournisseur, dans l'ordre où ils ont été essayés. La raison d'un
repos est relue en base (`store.raison_du_repos`), donc elle survit à un
redémarrage. Quand **tous** les fournisseurs distants sont au repos, une
dernière ligne dit l'heure du premier retour ; quand l'un d'eux vient
d'échouer pour une raison passagère (réseau, 503), elle n'apparaît pas —
annoncer une heure serait l'inventer. La clé masquée de chaque essai a disparu
du message : ce n'est pas elle qu'on cherche quand plus rien ne répond. Et le
message ne dit pas « usine cles » : quand le problème est le wifi, envoyer
créer des comptes serait absurde, et c'est la ligne de commande qui choisit le
conseil après avoir regardé le réseau ([PANNES.md](PANNES.md)).

## Deux tests qui ne gardaient rien

La campagne de mutation en a trouvé deux, et les deux pour la même raison —
un cas de test qui contient une **seconde façon de réussir** :

- le catalogue du test faisait choisir à `choisir()` le modèle déjà
  configuré : l'égalité finale tenait des deux côtés de la mutation, et
  supprimer la persistance ne changeait rien ;
- le corps de l'erreur portait le mot `retirement`, ce qui rattrapait la
  lecture du code : retirer la branche du 410 ne changeait rien. Un `Gone` nu
  est la forme minimale, et c'est elle qu'il faut garder.
