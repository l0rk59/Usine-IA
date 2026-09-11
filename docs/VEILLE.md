# Aller voir ce que les gens disent

## Ce que les quatre sources de marché ne disaient pas

Hacker News, Wikipedia, Stack Exchange et Open Library mesurent des
**volumes** : combien de discussions, combien de pages vues, combien de
livres. Elles répondent à « cette niche existe-t-elle ? ».

Elles ne répondent pas à « qu'est-ce qui y fait mal, et avec quels mots ? ».
Or un titre de produit qui reprend le vocabulaire des gens se trouve ; un
titre écrit en langue de brochure ne se cherche pas.

```bash
usine veille "freelance invoicing"
usine idees "freelance invoicing"     # s'en sert déjà
```

## La recherche globale de Reddit ne marche pas — vérifié

Le premier essai est passé par `/search.rss?q=...`. Sur
`meal planning for busy parents`, elle a rendu :

```
[cats     ] Kittens in storm drain successfully rescued. Thanks, everyone!
[meirl    ] Meirl
[travel   ] 4 days in Slovenia completely exceeded my expectations
```

Elle élargit la requête jusqu'à rendre du populaire hors sujet. Nourrir le
modèle avec ça aurait été **pire que de ne rien lui donner** — c'est le piège
exact que ce dépôt a déjà rencontré avec trois sources de marché mortes.

## Le chemin qui marche : en deux temps

On demande d'abord **qui** parle du sujet, puis on lit **ce qui s'y dit**. Les
titres sont alors sur le sujet par construction.

```
/subreddits/search.rss?q=<niche>   →  les communautés
/r/<communauté>/top.rss?t=year     →  ce qui s'y dit vraiment
```

Sur `freelance invoicing`, cela donne :

```
Leurs mots
  freelancers (5), built (3), invoicing (2), tool (2), tracking (2)

Discussions les plus suivies
  Which is best invoicing platform for freelancers?
  The tool I built after 10 years of chasing late payments
```

« chasing late payments » est une promesse produit écrite par quelqu'un qui a
le problème. Aucun modèle de langage ne l'aurait formulée ainsi.

## Reddit limite le débit, fermement

Le deuxième appel rapproché reçoit un `429` sans prévenir. Deux conséquences
assumées :

- **une seule nouvelle tentative**, après une vraie attente. Insister
  prolonge le blocage au lieu de le lever, et l'usine a mieux à faire que
  d'attendre un site gratuit ;
- **deux communautés par défaut**, espacées. Cela donne une cinquantaine de
  titres, largement assez pour dégager un vocabulaire.

Un refus est rapporté comme tel. **« Aucune discussion » et « on n'a pas pu
regarder » ne se confondent pas** — c'est la distinction qui empêche de
conclure qu'une niche est vide alors qu'on s'est simplement fait éconduire.

## S'en passer

`usine idees` consulte la veille par défaut : deux appels espacés, parfois une
attente de vingt secondes si Reddit répond `429`. Quand ce n'est pas le moment :

```bash
usine idees "une niche" --sans-veille    # garde les mesures de marché
usine idees "une niche" --hors-ligne     # coupe tout
```

## Ce que ce module n'est pas

| | |
|---|---|
| **Pas une mesure de demande commerciale** | un sujet très discuté peut n'avoir aucun acheteur. On se plaint gratuitement. C'est un signal de **douleur**, pas d'intention d'achat. |
| **Pas représentatif** | Reddit est anglophone, jeune, technophile et américain. Une niche française de retraités jardiniers n'y laissera aucune trace, ce qui ne dit **rien** de son marché. |
| **Pas exhaustif** | la recherche de communautés dérive : sur « meal planning », elle propose `r/canoecamping`. On lit les deux premières, pas les six. |

Ces trois limites sont affichées à chaque exécution, et le résumé transmis au
modèle les rappelle lui aussi. Un signal dont on ignore la portée vaut moins
qu'un signal dont on la connaît.

## Un défaut corrigé en chemin

Le repérage des formulations de problème (« how do I », « struggling »,
« tired of ») n'en trouvait qu'une sur cinquante discussions — et le résumé
n'envoyait **que** celle-là, cachant les quarante-neuf autres derrière un
filtre approximatif.

Les douleurs passent maintenant en premier, puis le reste complète. Un filtre
qui trie ne doit pas jeter.

## Depuis le tableau de bord

La carte **Veille de niche** fait la même consultation dans le navigateur, et
ajoute ce que la console ne peut pas offrir : chaque titre trouvé porte un
bouton **→ sujet** qui l'écrit dans le champ de fabrication, et le passe au
contrôle des domaines sensibles comme s'il avait été tapé à la main. Une
formulation de problème lue chez les gens devient un produit sans recopie —
c'est tout l'intérêt d'aller les lire.

La consultation tourne **en tâche de fond** : `scouter` s'impose trois
secondes entre deux communautés, parce que Reddit répond 429 dès le deuxième
appel rapproché. La page interroge l'avancement au lieu d'attendre une
réponse qui mettrait une demi-minute à venir. Deux consultations simultanées
sont refusées : Reddit compte par adresse, pas par onglet — elles se
prendraient mutuellement le 429.

### Les titres viennent de l'extérieur

Le flux n'est pas signé, et le tableau de bord est la page qui pilote
l'usine. Deux barrières, toutes deux testées :

- **Côté serveur**, seul un lien `https` vers `reddit.com` est transmis. Un
  `javascript:` ou un hôte qui imite Reddit arrive à la page comme une chaîne
  vide, et le titre s'affiche alors sans lien. Filtrer ici plutôt que dans le
  script : ce qui n'est jamais envoyé ne peut pas être affiché par erreur
  plus tard.
- **Côté page**, le texte du titre est échappé. Le serveur, lui, ne le nettoie
  pas : le nettoyer mentirait sur ce que les gens ont écrit.

