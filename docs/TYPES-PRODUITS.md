# Les types de produits

## Un seul endroit où ils sont déclarés

`usine/pipelines/catalogue.py` est la source unique. La CLI, le moteur continu,
le serveur web, le menu et l'explorateur de niches le lisent — aucun ne
redéfinit sa propre liste.

Ce n'était pas le cas avant : la liste était recopiée dans **sept fichiers**, et
deux avaient déjà divergé, avec une conséquence concrète — l'explorateur de
niches ne connaissait ni `impression` ni `modeles`, les deux types les plus
vendus. Les idées correspondantes étaient silencieusement converties en ebooks.

## Ce qui est déclaré

```python
TypeProduit(
    cle="impression", nom="Cahier imprimable",
    resume="Des fiches à remplir à la main",
    detail="PDF aux formats A4 et Lettre US",
    formats=("pdf", "html"),
    minutes=(5, 12),
    quantite=("pages", "Combien de fiches", "12"),
    mots_cles=("planner", "imprimable", "cahier", "agenda", "fiche"),
)
```

Les `mots_cles` servent à `normaliser()` : un modèle écrit « planner »,
« Notion » ou « e-book » plutôt que nos clés internes. Sans cette tolérance,
ces propositions retombaient sur `ebook` par défaut.

Ils doivent rester **sans accent** — ils sont comparés à du texte normalisé. Un
mot-clé accentué ne correspondrait jamais à rien : une assertion à l'import le
refuse bruyamment plutôt que de le laisser silencieusement inopérant.

## Les huit types réels

| Clé | Produit | Formats livrés |
|---|---|---|
| `ebook` | Guide structuré | PDF, EPUB, HTML, MD, TXT |
| `prompts` | Bibliothèque de prompts | PDF, CSV, JSON, HTML, MD |
| `formation` | Modules + cahier d'exercices | PDF ×2, HTML, MD |
| `outils` | Checklists et tableaux | PDF, CSV, HTML, MD |
| `modeles` | Bases Notion / tableur | CSV, PDF, HTML, MD |
| `impression` | Fiches à remplir | PDF A4 + Lettre US, HTML |
| `social` | Calendrier éditorial | CSV, PDF, JSON, HTML, MD |
| `idees` | Étude de niche | CSV, JSON, HTML, MD |

**« Vrai type » signifie : une chaîne de fabrication qui lui est propre.** Un
type qui produirait le même fichier qu'un autre sous un nom différent n'a pas sa
place ici — c'est la différence entre huit types et une énumération de soixante.

## L'assemblage commun

`usine/render/livraison.py` fait le travail identique pour tous : couverture,
markdown, PDF avec page de titre et sommaire, EPUB, HTML, texte, CSV, JSON.

```python
produit = livraison.Produit(
    type="ebook", titre=plan["titre"], sous_titre=plan["sous_titre"],
    blocs=livraison.blocs_depuis_sections(sections),
    formats=("md", "pdf", "epub", "html", "txt"),
    libelle_sections="chapitres",
)
return livraison.livrer(ctx, produit)
```

Ce qui reste propre à un type passe par des **fonctions de rappel**, pas par des
drapeaux : `rendu_pdf` pour une mise en page particulière (cases à cocher,
grille, tableau), `rendu_html` pour une structure HTML spécifique, `documents`
pour un second PDF. Une abstraction qui se contorsionne pour couvrir tous les
cas particuliers coûte plus cher que la duplication qu'elle remplace.

### Ce que le moteur fait payer, et ce qu'il ne fait pas payer

Mesuré, pas supposé :

| Chaîne | Avant | Après | Gain |
|---|---|---|---|
| `ebook` — prose, mise en page standard | 445 | 365 | **80 lignes** |
| `formation` — prose + un second document | 262 | 241 | **21 lignes** |
| `prompts` — mise en page PDF et HTML propres | 239 | 227 | 12 lignes |

Le moteur paie quand la mise en page est standard. Quand elle est spécifique,
les deux rappels sont nécessaires de toute façon et le gain devient marginal.
**`outils`, `modeles`, `impression` et `social` n'ont donc pas été migrés** :
changer leurs sorties pour économiser une douzaine de lignes n'en vaut pas la
peine. Ils gardent leur exportateur.

### Le bilan net, sans arrangement

| | Lignes |
|---|---|
| Économisées sur les trois chaînes migrées | −113 |
| Code mort supprimé (`web/modele.py`) | −223 |
| Infrastructure ajoutée (`catalogue` + `livraison`) | +500 |
| **Total** | **+173** |

Le refactor n'a pas réduit le volume de code. Ce qu'il apporte est ailleurs :
deux bugs réels corrigés, une liste déclarée une fois au lieu de sept, un
nouveau type dont l'export coûte dix lignes au lieu de soixante, et un test qui
exécute chaque type. Si le seul objectif avait été de compter moins de lignes,
il ne fallait pas le faire.

## Ajouter un type

1. Écrire `usine/pipelines/<nom>.py` avec une fonction `produire(ctx, ...)` qui
   construit un `livraison.Produit` et appelle `livraison.livrer()`.
2. L'inscrire dans `TYPES` et dans `_chaines()` de `catalogue.py`.

C'est tout. La CLI, le menu, la file de production, le tableau de bord et
l'explorateur de niches le proposent aussitôt.

Le test `test_chaque_type_produit_ses_fichiers` l'exécutera automatiquement et
vérifiera que chaque format annoncé est réellement produit, et qu'aucun fichier
n'est vide.

## Pourquoi ce test compte

Pendant ce refactor, une erreur d'import a cassé la chaîne `formation`. **Les
157 tests d'alors sont tous passés au vert** : aucun n'exécutait cette chaîne de
bout en bout. Le bug n'a été vu qu'en comparant manuellement les fichiers
produits avant et après.

Le test parcourt désormais chaque type déclaré. Retirer l'import à nouveau fait
échouer la suite, en nommant le type fautif.
