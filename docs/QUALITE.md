# Mesurer la qualité plutôt que la déclarer

## Deux contrôles, deux natures

L'usine ne demande pas à un modèle de juger ce qu'on peut compter.

| | Contrôle local | Relecture IA |
|---|---|---|
| Ce qu'il détecte | tics, répétitions, rythme, chiffres sans source, promesses, volume, structure | pertinence, progression, tenue de la promesse |
| Coût en quota | **zéro** | 1 à 2 appels |
| Durée | instantanée | 30 à 120 s |
| Reproductible | oui, au centième | non |

Le contrôle local tourne **d'abord**. Il produit des consignes de correction
déjà précises, que le réviseur applique en un seul appel. Le relecteur IA
n'intervient qu'ensuite, sur ce qui demande un jugement.

Conséquence directe : un défaut mesurable ne consomme plus deux appels (un pour
le détecter, un pour le corriger) mais un seul.

## Ce qui est mesuré

| Mesure | Ce qu'elle révèle | Seuil |
|---|---|---|
| **Tics** | 30 tournures d'IA en français | ≥ 3 occurrences ou 2,5 ‰ |
| **Promesses** | « garanti », « sans risque », « du jour au lendemain » | 1 suffit, bloquant |
| **Chiffres sans source** | un `%` ou un « 3× plus » sans « par exemple » ni « selon » | 1 → mineur, 2 → majeur |
| **Répétition** | n-grammes de 4 et 6 mots réapparaissant | > 6 % / > 2 % |
| **Diversité lexicale** | vocabulaire pauvre, normalisé par fenêtres de 300 mots | < 0,42 |
| **Rythme** | coefficient de variation des longueurs de phrases | < 0,35 |
| **Continuité** | recouvrement du vocabulaire avec les sections précédentes | < 0,35 |
| **Volume** | mots produits / mots visés | < 60 % |
| **Structure** | sous-titres et listes présents | aucun `##` au-delà de 400 mots |

### Trois choix expliqués

**Le rythme se juge en relatif, pas en absolu.** Un écart-type de 4 mots est
faible sur des phrases de 25 mots et large sur des phrases de 7. Le coefficient
de variation (écart-type ÷ moyenne) rend le critère indépendant du style choisi :
un texte volontairement sec n'est pas pénalisé, un texte robotique l'est.

**La diversité lexicale se mesure par fenêtres.** Le rapport brut mots uniques
÷ mots totaux chute mécaniquement quand le texte s'allonge. Par fenêtres de
300 mots, un chapitre court et un chapitre long deviennent comparables.

**La note reflète l'ampleur, pas seulement la catégorie.** Un texte à 170 tics
pour 1000 mots et un texte à 6 tics sont tous deux « bloquants », mais le
premier perd bien plus de points. Chaque anomalie porte un poids calculé.

## Lire le rapport

Chaque produit reçoit un `rapport-qualite.json` :

```json
{
  "controle_local":  { "note_moyenne_initiale": 4.5, "note_moyenne_finale": 7.8 },
  "note_moyenne_initiale": 6.0,          // relecture IA, avant
  "note_moyenne_finale":   8.5,          // relecture IA, après
  "mesure_finale": { "note_moyenne": 7.8, "note_min": 6.5,
                     "sections_bloquantes": [] }
}
```

`mesure_finale` est calculée sur le texte **réellement exporté**, pas sur un
état intermédiaire. C'est la seule note à citer.

## Étalonnage observé

| Texte | Note |
|---|---|
| Rédigé avec exemples chiffrés, rythme varié, structure | **10 / 10** |
| Correct mais générique : 3 tics, phrases uniformes, trop court | **2 / 10** |
| Sortie brute typique d'un modèle non guidé | **0 à 2 / 10** |

L'échelle est volontairement sévère : elle sert à décider s'il faut relancer,
pas à rassurer.

## Personnaliser les seuils

Les motifs sont dans `usine/core/controle.py` — `TICS` et `PROMESSES` sont deux
listes d'expressions régulières que vous pouvez étendre. Un défaut qui revient
dans vos productions apparaît dans `usine bilan` sous « défauts fréquents » :
c'est le signal qu'il faut soit ajouter une règle à l'agent rédacteur
(`usine prompts-systeme --exporter`), soit ajouter le motif ici.
