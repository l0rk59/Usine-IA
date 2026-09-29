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

## Recueil de nouvelles — `usine recueil`

*Ajouté le 15/09/2026.*

**Ce que l'acheteur reçoit** : plusieurs nouvelles liées par un fil, dans un
ordre voulu — PDF, EPUB, HTML, Markdown, et la mesure de variété en JSON.

**Pourquoi une chaîne à part.** Fabriquer sept nouvelles et les agrafer ne fait
pas un recueil : cela fait sept nouvelles dans le même fichier. Ce qui fait la
valeur d'un recueil, c'est qu'il se lise d'un bout à l'autre — donc que les
textes se répondent sans se répéter.

Et c'est précisément là que la fiction générée est la plus faible. Les études
publiques sur les textes de modèles le disent toutes de la même façon :
personnages archétypaux, tensions désamorcées, résolutions trop nettes. Sur
une nouvelle isolée, cela passe. **Sur sept d'affilée, cela se voit** — le
lecteur reconnaît la même histoire à la troisième, et repose le livre.

### Mesurer que les récits ne sont pas le même

C'est ce qui donne son intérêt à cette chaîne. En deux temps, et le premier
est le moins cher :

**Avant d'écrire** — les prémisses proposées se ressemblent-elles ? Deux
prémisses jumelles coûtent deux récits à découvrir. Quand il y en a, on
redemande le fil en **nommant les couples** : redemander « varie davantage »
ne change rien, dire « *Le phare* et *La lanterne* racontent la même chose »
change ce point-là.

**Après avoir écrit** — combien de protagonistes distincts, combien de formes
de fin, de combien les longueurs s'écartent.

Les deux sont déterministes : ils comparent des chaînes et comptent des mots.
Aucun n'appelle un modèle, et aucun ne juge la qualité d'un texte — ils
mesurent un **écart**, ce qui est vérifiable, là où « ce récit est banal » ne
l'est pas.

### Le seuil est volontairement haut, et ce qui passe dessous reste visible

Mesure du 15/09/2026 : « une libraire hérite du phare de son père et y trouve
une lettre » contre « une libraire reçoit le phare de son père et découvre une
lettre » donne **0,67**. Deux fois la même histoire — et le contrôle la laisse
passer.

C'est assumé, et c'est la règle du dépôt : *rater un défaut plutôt qu'en
inventer un*. Un recueil où deux textes se répondent volontairement — deux
versions d'un même événement, un diptyque — est un procédé, pas une faute, et
un contrôle qui le refuserait finirait ignoré.

Ce qui compense : **la proximité maximale est rendue dans tous les cas**, avec
son chiffre.

```
3 protagoniste(s) distinct(s), 3 forme(s) de fin.
Les deux recits les plus proches : « Le phare » et « La lettre » (0.67).
```

Le 0,67 se voit, et c'est un humain qui tranche.

### Ce qui est dit, et ce qui ne l'est pas

Une seule chose est affirmée, parce qu'une seule est certaine : deux récits qui
portent le même protagoniste, ou sept qui finissent de la même façon, sont un
**fait**. Tout le reste est rendu en chiffres.

Et même ces faits ne sont pas des condamnations. Un recueil de Noël finit bien
sept fois, et c'est un choix :

> *Les 7 récits finissent tous de la même façon (heureuse). C'est peut-être
> voulu ; lu d'affilée, cela s'entend.*

Un test vérifie que les mots « mauvais », « raté », « à refaire » n'y
apparaissent pas.

### Un défaut trouvé en regardant le produit

La première version livrait **sept récits pour trois demandés**, sans un mot :
le modèle rendait plus de prémisses que demandé et la chaîne les fabriquait
toutes. Quatre fois le temps et le quota annoncés, découverts à la fin. Ce qui
est demandé fait foi maintenant.

## Feuilleton — `usine feuilleton`

*Ajouté le 15/09/2026.*

**Ce que l'acheteur reçoit** : une saison d'épisodes, chacun précédé de son
« Précédemment » et refermé sur une question ouverte.

**Pourquoi une chaîne à part.** Couper un roman en morceaux ne fait pas un
feuilleton : cela fait un roman vendu en tranches. Le format tient deux
promesses que le roman n'a pas à tenir — chaque épisode **se lit sans avoir
relu le précédent**, et **donne envie du suivant**.

Trois contrôles, tous déterministes :

| ce qu'il voit | pourquoi ça compte |
|---|---|
| un épisode sans suspens déclaré | le lecteur n'a aucune raison de revenir |
| un rappel qui ne nomme personne de la distribution | il ne rappelle rien, il meuble |
| un rappel qui dépasse le quart de l'épisode | ce n'est plus un rappel, c'est un résumé qui prend la place du récit |

Le **dernier** épisode est exclu du premier contrôle par construction, pas par
tolérance : il referme l'arc, et lui réclamer un suspens serait lui réclamer
une saison de plus. Le **premier** est exclu du second : il n'a rien à
rappeler.

La part se compte sur l'épisode, pas sur un absolu — cinquante mots de rappel
sont longs devant deux cents mots d'épisode, et courts devant deux mille.

**Le « Précédemment » n'est pas le résumé roulant de la chaîne.** Celui-là sert
au modèle à ne pas se contredire, il est écrit en notes, et personne ne doit le
lire. Les confondre livrerait au lecteur une fiche technique — *« Camille :
veut sauver la ligne ; obstacle : Hakim »* — au lieu d'un rappel.

## Conte jeunesse illustré — `usine conte`

*Ajouté le 15/09/2026.*

**Ce que l'acheteur reçoit** : un album en doubles-pages, avec ses
illustrations quand le service d'images répond, et ses notes d'illustration
sinon.

**Pourquoi une chaîne à part.** Un album se compose en doubles-pages : deux ou
trois phrases par page, une image par page. Le faire passer par la chaîne de
fiction donnerait un roman court avec des titres de scènes — c'est-à-dire tout
ce qu'un album n'est pas.

### Le contrôle qui n'invente pas de seuil

La chaîne vérifie que le texte produit correspond à la **tranche d'âge**
demandée. Et c'est là qu'elle se distingue d'un contrôle fabriqué :

> Le plafond de mots par phrase n'est pas une vérité sur la lecture enfantine.
> C'est ce que l'usine a **demandé** au modèle.

Il est écrit dans `TRANCHES`, il se modifie, et le contrôle mesure si la
réponse s'y tient. Comparer une sortie à la consigne qui l'a produite est
vérifiable ; affirmer « une phrase de plus de douze mots est trop longue pour
un enfant de cinq ans » demanderait une étude qu'on n'a pas.

| tranche | pages | mots/page | mots/phrase demandés |
|---|---:|---:|---:|
| 3-5 ans | 12 | 35 | 10 |
| 6-8 ans | 16 | 70 | 14 |
| 9-12 ans | 20 | 140 | 20 |

Conséquence directe, et voulue : **la même phrase passe pour 9-12 ans et est
signalée pour 3-5 ans.** Le contrôle ne juge pas la phrase, il la compare à ce
qu'on a demandé. Un test garde ce point.

La **phrase la plus longue** est rendue à côté de la moyenne : une moyenne
cache une phrase de trente mots au milieu de vingt phrases de trois.

### Les images peuvent manquer, pas les notes

Une illustration qui ne vient pas ne fait pas échouer l'album : la note reste
dans le livre, et l'acheteur peut la faire dessiner. Un album sans images se
vend mal ; un album dont l'acheteur ne sait pas quoi faire dessiner ne se vend
pas du tout.


# L'ebook avait une seule forme

*Mesuré le 26/09/2026.*

Le type phare de l'usine n'avait **aucun réglage propre** — contre neuf pour un
roman, trois pour une séquence e-mail. Sa charpente était écrite en dur dans
l'invite de chaque chapitre : « au moins une liste numérotée d'étapes
applicables aujourd'hui », un exemple chiffré, et une dernière page intitulée
« votre plan des 30 prochains jours ». Un manuel qu'on consulte sur le droit
des baux, un recueil de cas de négociation et un programme de remise en forme
sur quatre semaines sortaient avec la même charpente et la même fin. Rien
n'échouait : un réglage par défaut n'est pas neutre, il est juste invisible.

Trois réglages, déclarés au catalogue, donc présents dans la ligne de commande,
le menu Termux et le tableau de bord :

| Réglage | Valeurs | Ce qu'il change |
|---|---|---|
| `--forme` | `methode`, `reference`, `programme`, `cas`, `questions` | le plan, l'ouverture et la structure de chaque chapitre, l'avant-propos (comment lire), la dernière page et son titre |
| `--niveau` | `debutant`, `intermediaire`, `avance` | ce qu'on explique et ce qu'on saute |
| `--exercices` | `avec`, `sans` | un encadré « Exercice » par chapitre, que le rendu met en valeur |

Laissés vides, ils sont **décidés par l'usine d'après le sujet**, comme les
réglages des autres types. L'invite de décision montre l'étiquette à côté de
la clé (« cas (Études de cas) ») : une clé seule ne dit pas ce qu'elle
fabrique. Si le modèle ne peut pas décider, l'ebook retombe sur la méthode pas
à pas, et le journal le dit.

Deux détails qui ne se voient qu'à l'usage :

- la forme **prime** sur les habitudes des agents. Le rédacteur a pour règle
  générale « donner des étapes numérotées exécutables aujourd'hui » ; l'invite
  le dit en toutes lettres, sans quoi un manuel de référence recevait deux
  consignes contradictoires ;
- les valeurs restent des clés sans accent — on les tape en ligne de
  commande — mais chaque liste affiche une **étiquette** (`Champ.etiquettes`),
  et la ligne vide se lit « L'usine décide » au lieu d'une case blanche.

`tests/test_ebook_formes.py` suit chaque réglage jusqu'à l'invite qui part au
modèle ; quatorze mutations, toutes vues.

# Le pack de prompts ne savait écrire que pour ChatGPT

*Mesuré le 26/09/2026.*

Chaque prompt était rédigé pour un assistant de texte — « assigner un rôle,
préciser le format de sortie » — et le mode d'emploi disait de le coller
« dans Claude ou ChatGPT ». Or les packs de prompts **d'image** (Midjourney,
Stable Diffusion) forment un rayon à part des places de marche. Un prompt
d'image n'a ni rôle ni format de sortie : il décrit un sujet, un style, une
lumière, un cadrage, une palette. Écrit comme un prompt de texte, il ne
produit rien d'utilisable — et l'acheteur ne le découvre qu'en l'essayant.

`--cible texte|image` (« Outil visé » dans le menu et le tableau de bord)
change le plan des catégories, la consigne de rédaction, le mode d'emploi et
le conseil livrés, et le style de couverture. Les prompts d'image sont écrits
en anglais, la langue que ces outils comprennent le mieux ; le mode d'emploi
le dit, et précise que « --ar 3:2 » est propre à Midjourney. Laissée vide, la
cible est décidée d'après le sujet.

# La boîte à outils et les modèles : une forme choisie pour tous

*Mesuré le 26/09/2026.*

**La boîte à outils** imposait toujours un mélange de checklists, de modèles à
compléter et de tableaux de suivi. Or un pack de trente checklists, un pack de
modèles et un classeur de suivi sont trois produits distincts, cherchés avec
des mots différents (« checklist pack », « templates », « tracker »).
`--composition melange|checklists|modeles|tableaux` fixe ce qu'on vend ; et
quand la composition impose un genre, chaque outil le prend, même si le modèle
a dérivé : ce qui a été choisi est ce qui est livré.

**Les modèles** visaient « Notion ou un tableur » à la fois, et le guide livré
expliquait les deux à chaque acheteur. `--outil notion|tableur|les-deux` change
la conception (relations, rollups et vues pour Notion ; onglets reliés par un
identifiant, formules exactes et listes déroulantes pour un tableur) et le
guide d'installation.

Les deux se décident d'après le sujet quand personne ne les choisit, et le
journal dit quand l'usine a dû retomber sur le mélange ou sur « les deux ».

# Cartes de révision — `usine cartes`

*Ajoutées le 27/09/2026.*

Ni le quiz ni le mémo. Le quiz mesure, avec des propositions et une
explication ; le mémo se consulte. Une carte sert à **se tester seul**, cent
fois, en espaçant les passages. Ce que l'acheteur paie, c'est de pouvoir la
réviser comme il en a l'habitude, sans rien retaper — d'où trois livrables
que les autres chaînes ne savent pas faire (`usine/render/cartes.py`) :

| Livrable | Ce qui le fait rater en silence |
|---|---|
| **Planches à découper** (PDF, huit cartes par feuille) | Imprimée en recto-verso, la feuille se retourne sur son bord long et inverse la gauche et la droite. Sans versos **en miroir**, la réponse de la carte 1 tombe au dos de la carte 2 — et le PDF paraît parfait à l'écran. |
| **Fichier Anki** (texte à tabulations) | Une tabulation ou un retour à la ligne dans un champ décale toutes les colonnes suivantes. Les en-têtes `#separator`, `#columns`, `#tags column` sont ceux que lit Anki depuis sa version 2.1.54 (manuel d'Anki, vérifié le 27/09/2026) ; le thème devient une étiquette, donc ses espaces deviennent des tirets bas. |
| **Page qui retourne les cartes** (HTML, hors ligne) | Même principe que le quiz auto-corrigé : un script écrit à la main, jamais par un modèle, et la liste complète des cartes sous le paquet pour qui n'a pas de script. |

Le réglage `--niveau` (« Niveau visé ») est celui du quiz. Laissé vide, l'usine
en juge d'après le sujet.

**Les lots.** Les cartes s'écrivent par douze. Chaque lot va au carnet dès
qu'il est écrit : une coupure au deuxième lot ne perd pas le premier, et
`usine reprendre` ne repaie que les lots manquants. Chaque lot reçoit les
rectos déjà écrits pour ne pas les redemander ; ceux qui reviennent quand
même sont écartés, et le paquet plus mince **le dit** — titre recompté,
journal, étape en anomalie. Un paquet de trente-deux cartes vendu pour
quarante est un paquet troué.

**Une face trop longue.** Elle est d'abord composée plus petite, jusqu'à un
plancher lisible (9 points au recto, 8 au verso). Au-delà, elle est coupée
avec « … » et **comptée** : l'étape « planches » passe en anomalie. Le produit
reste entier — la page et Anki ont le texte complet — mais c'est au vendeur de
le savoir avant de vendre.

`tests/test_cartes.py` : vingt-deux tests, et vingt et une mutations toutes
vues, du miroir des versos au lot relu du carnet. Le test de reprise ne
compte pas les appels pour prouver la relecture — le simulateur est
déterministe, et un lot refait retomberait sur le cache sans se voir au
compteur. Il **marque** le lot gardé au carnet, et cherche la marque dans le
fichier Anki final.

# Cahier de mots mêlés — `usine mots-meles`

*Ajouté le 27/09/2026.*

Un rayon entier de l'impression à la demande, et le seul produit de l'usine
où le modèle n'écrit presque rien : une liste de mots par sous-thème. Placer,
remplir, vérifier, dessiner, résoudre : tout le reste est du calcul, donc
déterministe, instantané (moins d'une seconde pour dix grilles difficiles) et
gratuit. Une grille « écrite » par un modèle contiendrait des mots
introuvables, et l'acheteur le découvrirait en jouant.

Trois défauts qu'un cahier de jeux ne pardonne pas, et que le code empêche au
lieu de les espérer absents :

| Défaut | Ce qui l'empêche |
|---|---|
| un mot de la liste absent de la grille | un mot n'est listé **que s'il a été placé** ; celui que la grille refuse sort de la liste, et c'est compté |
| un mot présent deux fois | le remplissage au hasard recrée parfois un mot court ailleurs. Chaque grille est relue après remplissage, dans les huit directions, et refaite tant qu'un mot s'y lit deux fois |
| un mot contenu dans un autre (« rat », « râteau ») | le plus court est écarté avant de placer quoi que ce soit : sinon le défaut précédent est inévitable |

Les cases vides se remplissent avec les lettres des mots eux-mêmes : une
lettre rare au milieu d'un bruit uniforme se repère d'un coup d'œil. Les
accents, espaces et tirets disparaissent dans la grille (« crème brûlée »
s'y écrit CREMEBRULEE) mais restent dans la liste, et la règle du cahier le
dit.

| Réglage | Valeurs | Ce qu'il change |
|---|---|---|
| `--difficulte` | `facile`, `moyen`, `difficile` | grille de 12, 15 ou 18 ; directions : à l'endroit seulement, puis les diagonales, puis les huit directions, à l'envers compris |
| `--caracteres` | `standard`, `gros` | les gros caractères sont un rayon à part : grille plus petite, lettres plus grandes, liste sur deux colonnes |

Laissés vides, ils sont décidés d'après le sujet et le public.

Le cahier sort en **A4 et en Lettre US**, composés par le même code : la
composition du PDF a été extraite de la livraison commune (`composer_pdf`),
pour qu'un second format de page ne soit pas une copie qui divergerait. Les
solutions, quatre par page, sont surlignées en couleurs pâles — lisibles
imprimées en niveaux de gris — et les lettres qui ne servent à aucun mot
passent en gris clair.

Les listes s'écrivent par lots de huit grilles, au carnet : une coupure ne
perd pas les lots écrits, et un sous-thème répété ou une liste trop pauvre est
écarté, compté, et fait passer l'étape « grilles » en anomalie.
`tests/test_mots_meles.py` relit chaque grille comme un joueur.
