# Les agents et la boucle qualité

## Pourquoi treize rôles plutôt qu'un seul prompt

Un prompt unique qui demande « écris un chapitre utile, concret, bien écrit,
sans risque juridique et qui tienne la promesse du titre » produit un texte
moyen sur tous ces axes. Chaque agent n'a qu'un objectif à tenir, et le tient
mieux.

Le signe est celui qui apparaît dans le journal du tableau de bord pendant une
fabrication — c'est tout ce qu'on voit d'un agent qui travaille, et c'est
pourquoi un test vérifie que deux agents n'en partagent jamais un.

| Agent | Signe | Rôle | Modèle | Température |
|---|---|---|---|---|
| `architecte` | `#` | conçoit les plans | costaud | 0.65 |
| `redacteur` | `~` | écrit le contenu | standard | 0.80 |
| `editeur` | `!` | critique sans complaisance | costaud | 0.35 |
| `reviseur` | `+` | applique les corrections | standard | 0.55 |
| `styliste` | `/` | retire les tics d'IA | standard | 0.60 |
| `marketeur` | `$` | écrit la page de vente | costaud | 0.78 |
| `formateur` | `^` | découpe une méthode en modules qu'on finit | standard | 0.70 |
| `animateur` | `@` | écrit pour les réseaux sociaux | standard | 0.82 |
| `bibliothecaire` | `&` | classe et teste les packs de prompts | standard | 0.60 |
| `outilleur` | `=` | transforme une méthode en gabarit utilisable | standard | 0.62 |
| `prospecteur` | `?` | juge une niche | raisonnement | 0.55 |
| `lecteur` | `o` | lit le produit fini, en acheteur | standard | 0.50 |
| `controleur` | `v` | valide la mise en vente | costaud | 0.30 |

### Les six derniers venus, et ce qui manquait sans eux

Les sept premiers ne servaient qu'aux ebooks et aux pages de vente. **Cinq
chaînes sur dix n'avaient aucune équipe** : la formation, les publications
sociales, les packs de prompts, les boîtes à outils et l'étude de niche
appelaient le routeur directement, avec une personnalité écrite en dur dans
chaque fichier — quinze appels au total.

Ce qu'elles y perdaient ne se voyait nulle part :

- aucune règle de métier, donc le prompt de chaque fichier vieillissait seul ;
- **aucune relecture croisée** : le même modèle écrivait et se relisait ;
- aucun événement `agent`, donc un panneau éteint dans le tableau de bord
  pour la moitié du catalogue ;
- et surtout **aucun signalement de réponse tronquée**, qui est pourtant « le
  défaut le plus coûteux du routeur, parce qu'il est invisible partout en
  aval ».

`formateur`, `animateur`, `bibliothecaire`, `outilleur` et `prospecteur`
couvrent ces cinq chaînes. Un test les mesure par les **événements réellement
publiés** pendant une fabrication, et non en cherchant leur nom dans le code :
un agent importé et jamais appelé passerait une recherche de texte.

Le treizième, `lecteur`, répond à un manque d'une autre nature.

## Le lecteur : la seule voix qui ne juge pas le métier

Tous les autres contrôles jugent le **texte**. Un chapitre techniquement
excellent et incompréhensible pour son public reste un chapitre raté, et rien
ne le signalait.

`lecteur` reçoit le produit **entier** et une seule consigne : être l'acheteur.
Il rend ce qu'aucun relecteur ne rend — ce qu'il n'a pas compris, où il a
décroché, les sigles employés avant d'être expliqués, et si la promesse du
titre est tenue.

```bash
usine ebook "sujet" --relecture-ensemble
```

Il ne s'impose pas : un appel par produit, sur le texte complet, quand la
chaîne le demande. Et il **refuse de juger une section seule** — ce qu'il
cherche (un sigle expliqué trop tard, une promesse non tenue) n'existe qu'à
l'échelle du produit. Trois tests gardent ces trois points.

## La boucle : écrire → critiquer → corriger

```
   rédacteur  ──►  texte v1
                     │
              éditeur (AUTRE fournisseur)
                     │
            note /10 + problèmes datés
                     │
         note ≥ 7,5 et rien de bloquant ? ──oui──►  texte retenu
                     │ non
                  réviseur
                     │
                  texte v2  ──►  (2 passes maximum)
```

Deux points viennent directement de la recherche publiée sur les boucles de
réflexion, et expliquent des choix qui pourraient sembler arbitraires :

**Le relecteur n'est jamais le modèle qui a écrit.** Un modèle qui se relit
lui-même a tendance à confirmer ses propres erreurs plutôt qu'à les voir —
c'est la « dégénérescence de la pensée ». Le routeur accepte un paramètre
`eviter` qui écarte le fournisseur ayant produit le texte. S'il ne reste aucun
autre fournisseur, la relecture a quand même lieu : une relecture imparfaite
vaut mieux que pas de relecture.

**La boucle est bornée à deux passes.** Le gain s'épuise après deux ou trois
itérations ; au-delà, on consomme du quota sans améliorer le texte.

## Un garde-fou concret

Un réviseur qui renvoie un texte deux fois plus court a tronqué au lieu de
corriger. Dans ce cas le texte d'origine est conservé et l'événement
`revision_rejetee` est publié. Sans cette vérification, un chapitre pouvait
arriver amputé dans le PDF final.

## Quand deux moitiés de l'usine se contredisent

Le rédacteur avait pour règle « toute affirmation est suivie d'un exemple ou
d'un chiffre illustratif ». Le contrôle déterministe, lui, signale tout chiffre
dont la phrase ne porte aucun marqueur de source — c'est une règle du dépôt :
*pas de chiffre sans source*.

Les deux étaient justes séparément. Ensemble, elles coûtaient **trois appels
par chapitre** : le texte sortait fautif, le contrôle le voyait, le réviseur le
corrigeait. Personne ne pouvait le remarquer, parce que le résultat final était
correct.

La règle du rédacteur nomme désormais les marqueurs que le contrôle accepte :

> Un chiffre précis s'introduit TOUJOURS par « par exemple », « imaginons »,
> « supposons » ou « selon \<source nommée\> ». Sans cette marque, il passe
> pour une statistique inventée — et il en est une.

Un test relit chaque fiche d'agent et vérifie qu'aucune ne prescrit un tic que
le contrôle pénalise, ni ne cite un marqueur que le contrôle ne reconnaît pas.
Il a fallu l'écrire avec précaution : le styliste a pour métier de supprimer
« en conclusion », donc il **cite** le tic pour l'interdire. Un détecteur qui
compte cette citation accuserait la seule fiche qui fait exactement ce qu'il
faut — et *un garde-fou qui crie à tort finit ignoré*. Le détecteur retire donc
ce qui est entre guillemets avant de chercher.

## Choisir le niveau

```bash
usine ebook "sujet" --qualite rapide     # 0 relecture — le plus économe
usine ebook "sujet" --qualite standard   # 1 relecture  (défaut)
usine ebook "sujet" --qualite exigeant   # 2 relectures — 2 à 3 fois plus long
```

Chaque produit relu reçoit un `rapport-qualite.json` qui donne, section par
section, la note avant et après, le nombre de corrections appliquées et ce qui
reste signalé. C'est une mesure, pas une affirmation.

## Personnaliser les agents

```bash
usine prompts-systeme --exporter     # écrit atelier/prompts/
nano atelier/prompts/agents.json     # changez mission, règles, température
usine prompts-systeme                # montre ce qui est personnalisé
usine prompts-systeme --reinitialiser
```

Un fichier `agents.json` mal formé est ignoré et les valeurs d'origine
reprennent la main : une faute de frappe dans un prompt ne doit jamais empêcher
de produire.


## Ce que la chaîne mesure sur elle-même

La relecture par un **autre** modèle que l'auteur est le mécanisme central de
cette équipe. Elle a un repli : quand un seul fournisseur est disponible, la
relecture a lieu sur le modèle qui a écrit — mieux vaut cela que pas de
relecture du tout.

Ce repli est le bon, mais il était invisible. Le rapport qualité porte
désormais la part **réellement** croisée :

```json
"relecture_croisee": {"relectures": 12, "sur_un_autre_modele": 12, "part": 1.0}
```

Et `usine ebook --relecture-ensemble` ajoute une lecture du livre entier à la
recherche des contradictions entre chapitres — ce qu'aucun agent ne voyait,
chacun travaillant section par section. Voir [ROUTEUR.md](ROUTEUR.md).
