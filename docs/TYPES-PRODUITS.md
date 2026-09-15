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

## Les dix types réels

| Clé | Produit | Formats livrés |
|---|---|---|
| `ebook` | Guide structuré | PDF, EPUB, HTML, MD, TXT |
| `nouvelle` | Fiction courte, avec bible et continuité | PDF, EPUB, HTML, MD, TXT |
| `prompts` | Bibliothèque de prompts | PDF, CSV, JSON, HTML, MD |
| `formation` | Modules + cahier d'exercices | PDF ×2, HTML, MD |
| `outils` | Checklists et tableaux | PDF, CSV, HTML, MD |
| `modeles` | Bases Notion / tableur | CSV, PDF, HTML, MD |
| `impression` | Fiches à remplir | PDF A4 + Lettre US, HTML |
| `social` | Calendrier éditorial | CSV, PDF, JSON, HTML, MD |
| `logiciel` | Outil CLI, web ou extension | code source + PDF, HTML, MD |
| `idees` | Étude de niche | CSV, JSON, HTML, MD |

**« Vrai type » signifie : une chaîne de fabrication qui lui est propre.** Un
type qui produirait le même fichier qu'un autre sous un nom différent n'a pas sa
place ici — c'est la différence entre dix types et une énumération de soixante.

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

## Le type qui ne ressemble pas aux autres

`logiciel` est le seul dont le livrable peut être **faux plutôt que médiocre**.
Un ebook maladroit se vend ; un script qui ne démarre pas se fait rembourser.
Sa chaîne ajoute donc une étape que les huit autres n'ont pas : analyse du code
généré, réparation par le modèle à partir de l'erreur exacte, puis exécution
réelle en bac à sable pour la cible `cli`. Voir `docs/LOGICIEL.md`.

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

---

# Trois produits que l'usine ne savait pas fabriquer

*Ajoutés le 14/09/2026.*

Elle écrivait un livre de deux cents pages et trente posts LinkedIn, mais pas
les sept messages qui séparent une inscription d'un premier achat, pas la page
qu'on garde à côté de soi, pas le quiz qui dit **pourquoi** on s'est trompé.

| Type | Ce qu'il est, et ce qu'il n'est pas |
|---|---|
| `emails` | Une **séquence**, pas une suite d'articles : elle se lit dans l'ordre, à jours d'intervalle, par quelqu'un qui a oublié le message précédent |
| `memo` | L'**inverse de l'ebook** : un ebook se lit une fois, un mémo se consulte vingt fois, debout, en cherchant une ligne |
| `quiz` | Ce qui a de la valeur n'est pas la question, c'est l'**explication** |

## Ce que chacun a demandé au code, et pourquoi

**La séquence e-mail.** Le plan est établi en un seul appel, puis les messages
sont rédigés un par un. Ce n'est pas une économie d'appels : la progression
*est* le produit. Demander les messages indépendamment donnerait sept bons
messages qui ne vont nulle part. Chaque rédaction reçoit donc l'objet du
message précédent et celui du suivant.

Le plan peut répondre `"aucune"` à la question « que demande ce message ? », et
c'est le cas de la plupart des messages d'accueil. Cette réponse est gardée
telle quelle : la transformer en appel à l'action fabriquerait une demande que
personne n'a voulue.

Le CSV livré porte un marqueur d'encodage (`utf-8-sig`). Les outils d'emailing
français l'ouvrent dans Excel avant de l'importer, et sans ce marqueur les
accents des lignes d'objet arrivent cassés **jusque dans la boîte du
destinataire**.

**Le mémo.** Deux conséquences dans le code, toutes deux dictées par ce qu'un
mémo est :

- le contrôle qualité de prose est coupé (`prose=False` au catalogue). Il
  mesure le rythme des phrases et la diversité lexicale ; sur des lignes de
  trois mots il rend un chiffre qui n'a aucun sens, et un chiffre sans sens est
  pire que pas de chiffre parce qu'on le croit ;
- la longueur est une **contrainte**, pas une conséquence. Deux bornes, et ce
  ne sont pas les mêmes : la **demande** est ramenée à quatorze blocs, et la
  **réponse** l'est aussi. Un modèle répond volontiers dix-neuf blocs quand on
  en demande huit. Une première version du test demandait quarante blocs en
  croyant exercer la coupe ; la demande était ramenée à quatorze avant l'appel,
  et la ligne qui tranche ne s'exécutait jamais. La mutation l'a montré.

**Le quiz.** La validation est plus sévère que pour les autres chaînes, parce
qu'un corrigé faux se découvre après la vente, par l'acheteur, et qu'il n'a
aucun moyen de savoir si c'est lui ou le quiz. Sont écartées : une réponse dont
l'indice sort du tableau, un indice écrit en toutes lettres, et deux
propositions identiques — deux réponses justes pour un seul indice.

Il **réutilise** `usine/render/quiz.py`, écrit pour la formation : une page qui
se corrige seule, hors ligne. D'où le nom `reponse` pour l'indice de la bonne
proposition, et non `bonne` : deux formes pour la même chose auraient rendu la
page muette. C'est la règle du dépôt — avant d'écrire, vérifier que ce n'est
pas déjà là.

Le barème compte en **nombre de bonnes réponses sur les questions retenues**,
pas sur celles demandées. Un barème sur vingt annoncerait des seuils
inatteignables quand huit questions ont été écartées.

## Un bloc sans corps ne rend rien, et ne le dit pas

Trouvé en écrivant ces chaînes, et présent avant elles.

Un `Bloc` livré porte trois rendus possibles : `corps` (markdown, qui sert
**tous** les formats), `rendu_pdf` (mise en page fine) et `rendu_html`. Trois
chaînes ne donnaient que le rendu PDF, en passant `rendu_html=""` — et un bloc
sans corps ni rendu HTML ne rend **rien du tout**, en silence.

Mesure du 14/09/2026, en relisant `lire.html` : le mode d'emploi du pack de
prompts, les consignes et le barème du quiz, le calendrier d'envoi de la
séquence e-mail manquaient tous les trois pour qui ouvre la page — c'est-à-dire
pour la plupart des acheteurs sur téléphone.

Le garde-fou (`tests/test_types_neufs.py`) ne cherche pas `rendu_html=""` dans
le source : il **intercepte l'assemblage** et regarde les blocs réellement
remis à la livraison. La même faute écrite autrement serait passée.

## Quand on ne sait pas encore quoi fabriquer

Les quatorze commandes de fabrication demandent le type d'abord. Or le choisir
suppose de savoir ce qui se vend dans une niche qu'on n'a pas encore cherchée :
c'est l'ordre inverse de celui dans lequel la question se pose.

```bash
usine auto                      # l'usine choisit la niche ET le type
usine auto "votre sujet"        # vous donnez le sujet, elle choisit le type
```

Le tableau de bord propose le même choix, en tête de la liste des types. Il ne
porte aucun réglage, et c'est normal : les réglages d'un type ne peuvent pas
être demandés avant que le type soit connu.

## Livre dont le lecteur est le héros — `usine interactive`

*Ajouté le 15/09/2026.*

**Ce que l'acheteur reçoit** : un récit à embranchements, en sections
numérotées, avec plusieurs fins — PDF, EPUB, HTML, Markdown, et la carte du
livre en JSON.

**Pourquoi une chaîne à part, et pas une option de `nouvelle`.** Toute la
machinerie de fiction du dépôt suppose une **suite** : des scènes numérotées,
un résumé roulant qui avance, une grille de beats où la scène 11 paie ce que
la scène 3 a promis. Un récit à embranchements n'a rien de tout cela. La
section qui suit la 4 dépend du lecteur, le « résumé de ce qui précède » n'a
pas de valeur unique, et deux lecteurs n'auront pas lu le même livre.

### La carte est le produit, et elle se vérifie avant d'écrire

C'est le cœur de cette chaîne. Les défauts d'un livre-jeu ne sont pas des
défauts de texte : une section peut être magnifiquement écrite et le livre
injouable. Quatre défauts, qu'un lecteur découvre sinon à votre place :

| | |
|---|---|
| **le choix mort** | « rendez-vous à la section 12 », et la 12 n'existe pas |
| **la section orpheline** | écrite, payée, et qu'aucun chemin n'atteint |
| **le piège** | on y entre, on n'en sort plus, aucune fin n'est joignable |
| **la fin unique** | un livre à choix qui n'a qu'une issue n'en est pas un |

Aucun ne demande un appel de modèle pour être vu : **ils se comptent**. Et ils
se comptent *avant* la rédaction, donc un livre troué ne coûte pas un livre
entier à découvrir.

Le troisième est le plus intéressant : rien n'y cloche localement. Les
sections sont atteignables, elles ont des choix, chaque choix mène quelque
part. Il faut parcourir le graphe **à l'envers depuis les fins** pour le voir.

### Quand la carte est fausse

Deux tentatives, et la seconde **nomme les défauts** de la première :

```
carte incoherente, 2 defaut(s) — on les nomme et on redemande :
  Section 7 : « fuir par la cave » renvoie vers la section 31, qui n'existe pas.
  Aucun chemin ne mene aux sections 12, 13 : elles seraient ecrites, payees,
  et jamais lues.
```

Un modèle à qui l'on dit « recommence » refait la même carte. Un modèle à qui
l'on dit « la section 7 renvoie vers 31, qui n'existe pas » corrige ce
point-là.

Si la seconde échoue encore, la carte est **élaguée** pour rester jouable —
les choix vers le vide disparaissent, un piège devient une fin, ce qu'aucun
chemin n'atteint n'est pas écrit. C'est une dégradation, elle est annoncée à
l'écran et dans `produit.json`, et elle vaut mieux qu'un livre qui bloque à la
section 7.

### Deux détails qui coûtent cher

**Les choix ne sont pas demandés au rédacteur.** Ils sont déjà dans la carte,
déjà vérifiés, déjà numérotés. Les faire réécrire les ferait dériver du graphe
— le texte proposerait trois portes là où la carte en connaît deux, et la
vérification qu'on vient de payer ne garderait plus rien.

**Les titres sont retirés du corps des sections.** Le numéro de section *est*
un titre de niveau 2 dans le document rendu : un « ## Le principe de base »
laissé dans le corps fabrique une section fantôme au sommaire, et le lecteur à
qui l'on dit « rendez-vous au 7 » trouve deux entrées entre le 6 et le 8.
Mesuré le 15/09/2026 : avant correction, un livre de douze sections en
déclarait vingt-quatre.

### Ce que le test de fumée a appris

Au premier passage, il a déclaré « abouti » un livre de **zéro section**. Le
simulateur ne savait pas répondre à la demande de carte, la carte était vide,
l'élagage n'a rien laissé, et la chaîne a livré en silence.

Un simulateur qui ne sait pas répondre ne rend pas un test moins bon : **il le
rend faux.** Il connaît maintenant ce cas, et rend une carte volontairement
simple et juste — ce que le test doit exercer, c'est la chaîne, pas la
capacité du simulateur à se tromper. Les cartes fausses sont fabriquées à la
main par les tests d'unité.

