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

---

# La moitié du tableau de bord était invisible

*Mesure du 14/09/2026, sur un écran de 412 × 915 — un téléphone.*

L'utilisateur disait « je n'aime pas les menus, c'est mal organisé ». Il avait
raison, et la mesure dit pourquoi.

## Ce qui remplissait le premier écran

| | avant | après |
|---|---|---|
| en-tête | 78 px | 78 px |
| scène 3D | **420 px** | 238 px |
| décoration avant le premier réglage | **54 %** | 35 % |
| premier contrôle touchable | y = 658 | y = 548 |

On ouvrait le tableau de bord sur une animation, pas sur ce qu'on venait
faire. La scène **répète** ce que le journal et les compteurs disent en toutes
lettres — elle peut rétrécir sur un téléphone sans rien coûter à personne.

## Trois onglets sur six hors du cadre

La barre faisait **670 px de large dans une fenêtre de 412**. `Marché`,
`Réglages` et `La machine` tombaient hors du cadre, et une barre qui défile
horizontalement n'a ni ombre ni flèche : rien ne disait qu'ils existaient.

C'est un défaut **né de la correction du précédent**. La barre a connu les
deux excès :

1. six **lignes** empilées, 190 px de haut → corrigé en `nowrap` ;
2. une **ligne** qui défile, trois onglets invisibles.

Deux rangées de trois coûtent 44 px et suppriment le choix entre les deux.
Vérifié à huit largeurs, de 320 à 1024 px : **aucun onglet caché, aucun
débordement horizontal**. Le seuil de retour à la ligne unique est 700 px et
non 560 — les six onglets en demandent 670, et 560 recachait le dernier.

## Ce que la nouvelle mise en page a révélé

Des éléments jusque-là inatteignables le sont devenus, et la mesure de
contraste les a vus :

- **`jour` ne déclarait ni `--ambre` ni `--rouge`.** Elle héritait donc de
  ceux de `nuit`, conçus pour du texte lumineux sur du noir. Ils ne servent
  pas qu'aux jauges : `.journal .souci`, `.alerte` et l'étiquette d'une entrée
  en cours les emploient comme couleur de **texte**. Mesure : **1,41** pour
  l'ambre sur un fond clair. Du jaune vif sur du blanc, sur un avertissement —
  c'est-à-dire précisément la ligne qu'il faut pouvoir lire.
- Assombrir ce rouge pour qu'il se lise **en texte** a cassé son autre emploi :
  **fond** du bouton « supprimer », où l'encre sombre commune ne rendait plus
  que 2,90. Les deux emplois d'une même couleur tirent en sens inverse, et il
  faut déclarer les deux.

### Le garde-fou nommait sa liste

Il vérifiait `--encre`, `--doux` et `--accent`. C'était trois sur cinq. Une
liste tenue à la main garde jusqu'au jour où quelqu'un emploie une sixième
variable — et ce jour-là personne ne le sait.

Il **déduit** désormais la liste de la feuille de style : toute variable qui
apparaît dans un `color:` y entre d'office. Réécrit ainsi, il a trouvé
sur-le-champ `jour --vert` à **4,04**, que la relecture humaine avait laissé
passer.

## Ce que la chasse aux bugs a trouvé, et n'a pas trouvé

Soixante interactions pilotées dans un vrai navigateur — chaque bouton de
chaque onglet — puis trois fabrications complètes de bout en bout :
**zéro erreur JavaScript, zéro requête en échec**. Fabrication, liste des
produits, téléchargements, persistance des réglages, file d'attente, mode
« l'usine décide » : tout aboutit.

Deux alertes de cette chasse étaient des **erreurs de ma propre sonde**, et
elles méritent d'être nommées parce qu'elles se ressemblent : un bouton
déclaré « incliquable » parce que la sonde ne faisait pas défiler la page, et
une suppression déclarée sans effet parce que je comptais tous les boutons de
l'onglet au lieu de l'entrée visée. Une mesure qui accuse est aussi une mesure
à vérifier.

## Cinq cases qui ne faisaient rien

Audit du 15/09/2026, en suivant chaque réglage déclaré **jusqu'à la fonction
qui fabrique** — et non en vérifiant qu'il est atteignable, ce qu'un test
faisait déjà.

| type | réglage | effet réel |
|---|---|---|
| `logiciel` | Ne pas exécuter le code | aucun |
| `idees` | Ne pas mesurer le marché | aucun |
| `idees` | Ne pas lire les discussions | aucun |
| `social` | Visuels à générer | aucun |
| `interactive` | Série | aucun |
| `recueil` | Série | aucun |
| `feuilleton` | Série | aucun |

### Deux causes différentes

**La traduction de nom, faite à un seul endroit.** La case s'appelle
`sans_marche` ; la chaîne attend `avec_marche`. Seule la ligne de commande
faisait la conversion — `avec_marche=not args.sans_marche`. Le serveur, lui,
passe les options telles quelles à `executer`, qui ne transmet que les clés
déclarées dans `options`. La case était donc **affichée, cochée, enregistrée,
et jetée en chemin**.

Vérifié en comptant les sondages de marché, pas en lisant le code : un
sondage avec la case cochée, un sondage sans.

La traduction se déclare maintenant sur le champ lui-même —
`argument="avec_marche", inverse=True` — donc elle vaut pour les trois
chemins : ligne de commande, menu Termux, tableau de bord.

S'y ajoute une conversion que personne n'avait écrite : un navigateur envoie
`on`, la ligne de commande un vrai booléen, la file relit du JSON. Les trois
doivent vouloir dire la même chose, et `0` ou vide doivent vouloir dire non.

**Un argument que la chaîne n'accepte pas.** `produire` ne prend un paramètre
`serie` que dans `nouvelle` et `roman` — les seules à porter la machinerie de
tomes. Les trois autres affichaient le champ sans que rien ne puisse le lire.

### Pourquoi le garde-fou existant n'a rien vu

Il vérifiait qu'un réglage est **atteignable** depuis les trois interfaces.
C'est une autre question que « sert-il à quelque chose ». Les deux se
ressemblent, et une seule était posée.

`tests/test_reglages_arrivent.py` pose la seconde, de deux façons : en suivant
la déclaration jusqu'à la signature de `fabriquer`, et en **comptant** ce
qu'une case change réellement. Huit mutations, toutes vues.
