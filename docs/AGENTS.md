# Les agents et la boucle qualité

## Pourquoi sept rôles plutôt qu'un seul prompt

Un prompt unique qui demande « écris un chapitre utile, concret, bien écrit,
sans risque juridique et qui tienne la promesse du titre » produit un texte
moyen sur tous ces axes. Chaque agent n'a qu'un objectif à tenir, et le tient
mieux.

| Agent | Rôle | Modèle | Température |
|---|---|---|---|
| `architecte` | conçoit les plans | costaud | 0.65 |
| `redacteur` | écrit le contenu | standard | 0.80 |
| `editeur` | critique sans complaisance | costaud | 0.35 |
| `reviseur` | applique les corrections | standard | 0.55 |
| `styliste` | retire les tics d'IA | standard | 0.60 |
| `marketeur` | écrit la page de vente | costaud | 0.78 |
| `controleur` | valide la mise en vente | costaud | 0.30 |

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
