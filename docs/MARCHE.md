# Mesurer un marché

```bash
usine marche "productivity"
usine idees "productivity"      # les idées s'appuient sur ces mesures
```

Demander à un modèle « ce sujet se vend-il ? » produit une réponse fluide et
sans valeur : il n'a pas accès au marché, il produit du plausible. Ce module va
chercher des mesures vérifiables, puis les donne au modèle comme matière.

## Les quatre sources

Toutes publiques, **aucune inscription**, vérifiées en fonctionnement.

| Source | Ce qu'elle mesure |
|---|---|
| **Hacker News** (Algolia) | volume et intensité des discussions |
| **Wikipedia pageviews** | intérêt réel dans le temps, par langue |
| **Stack Exchange** | questions sans réponse = douleurs non résolues |
| **Open Library** | ouvrages existants = concurrence éditoriale |

Chaque source est facultative. Si l'une tombe, le rapport le dit
(`fiabilité : 3/4 sources`) au lieu d'inventer un chiffre.

## Trois pièges évités

**Wikipedia ne renvoie pas le premier résultat.** Chercher « productivity »
propose « Productivity software » avant « Productivity ». Mais prendre le plus
consulté est pire : « freelance » renverrait *Freelance (2023 film)*. Les
candidats sont donc classés d'abord sur la proximité du titre — les pages
homonymes entre parenthèses sont écartées — et la fréquentation ne sert qu'à
départager à proximité égale.

**Une fréquentation faible n'est pas un signal.** Sous 200 vues par mois,
l'article est trop confidentiel : la tendance devient du bruit statistique. Le
rapport l'annonce et ne la retient pas dans le verdict.

**Un échantillon ne s'extrapole pas.** Open Library renvoie 20 résultats sur
2 491 trouvés. Le rapport écrit « 2 des 20 premiers résultats datent des
5 dernières années », jamais « 2 sur 2 491 ».

## La limite à connaître

**Ces sources sont anglophones.** « la prospection pour freelances » renvoie
zéro résultat — ce qui ne dit rien du marché francophone, seulement de la
langue de la requête. Le module détecte les requêtes françaises et le signale
explicitement dans le verdict au lieu de conclure « niche trop étroite ».

Pour un sujet francophone : mesurez avec le mot-clé anglais équivalent
(`freelancing`, `productivity`, `meditation`), puis produisez en français.

## Ce qui ne fonctionne plus

Ces sources sont souvent citées ; elles sont mortes ou fermées, vérifié :

| Source | État |
|---|---|
| Reddit JSON public | renvoie du HTML — API verrouillée pour le trafic non authentifié |
| Google Trends `dailytrends` | HTTP 404, endpoint supprimé |
| GitHub Search sans token | HTTP 403 depuis une IP de centre de données |

Les remplacer par « Wikipedia pageviews » (tendance) et « Hacker News »
(discussions) donne un signal comparable, sans clé et sans blocage.

## Depuis le menu et le tableau de bord

`usine marche` n'existait qu'en ligne de commande. Le menu Termux propose
maintenant **Mesurer un marché**, et le tableau de bord le lance depuis la
carte de veille — même champ, deux gestes distincts : la veille dit ce que les
gens *disent*, le marché dit combien ils sont.

La page affiche les trois signaux (demande, concurrence, tendance), les
mesures qui les fondent, et surtout **les sources qui n'ont pas répondu**. Un
silence de source n'est pas un marché absent : ne pas le dire laisserait lire
un verdict là où il n'y a qu'une mesure manquante.

