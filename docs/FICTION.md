# La fiction : pourquoi une chaîne à part

`usine nouvelle "un gardien de phare et le dernier hiver"`

La question revient souvent : puisque la chaîne `ebook` sait écrire un livre
de douze chapitres, pourquoi ne saurait-elle pas écrire un roman ? La réponse
n'est pas une affaire de consigne, et elle mérite d'être dite précisément.
(Sur le roman en particulier, voir [Et le roman ?](#et-le-roman) plus bas :
la mémoire tient désormais à cette échelle, ce qui reste est la structure.)

## Le défaut qui rend l'ebook inapte

La chaîne `ebook` rédige chaque chapitre **indépendamment**. Il ne reçoit que
la liste des *titres* des autres, pour éviter les redites — rien de ce qu'ils
racontent.

Pour un guide pratique, c'est une **qualité** : les chapitres sont modulaires,
fabricables dans n'importe quel ordre, et un chapitre raté n'entraîne pas les
autres. C'est aussi ce qui permet à l'usine de livrer un livre amputé plutôt
que rien quand un plafond de budget tombe au dixième chapitre.

Pour une histoire, c'est rédhibitoire. Une fiction a besoin de savoir **qui
est présent**, **ce que le lecteur sait déjà**, **où en est l'arc**, et **ce
qui a été promis à la scène 3 et doit être payé à la scène 11**. Un chapitre
écrit sans mémoire produit un texte où un personnage mort revient, où une clé
trouvée est retrouvée deux fois, et où la dernière page ne referme rien.

## Les trois pièces que la chaîne `nouvelle` ajoute

### 1. La bible

Écrite **avant la première ligne de texte**, en un appel. Elle contient ce qui
ne changera plus :

- les **personnages** : nom, rôle, *désir* (ce qu'ils veulent, concrètement),
  *défaut* (ce qui les en empêche), *voix* (comment ils parlent) ;
- le **cadre** : lieu, époque, règles du monde ;
- l'**enjeu** : ce que le protagoniste perd s'il échoue — une chose précise,
  pas une abstraction ;
- la **fin visée**.

Un personnage dont le désir se décide au fil de l'eau n'a pas de désir. La
bible est passée **entière à chaque scène**, et elle est la source de vérité :
un personnage que la grille inventerait sans qu'il y figure est écarté.

### 2. La mémoire

C'est ce que la chaîne `ebook` n'a pas. Chaque scène reçoit l'état de
l'histoire jusque-là ; en sortant, elle le met à jour.

Cela coûte **un appel court par scène** — environ quatre-vingt-dix mots, au
présent, purement factuel : qui est où, ce qui a changé, ce qui reste en
suspens. C'est le surcoût de cette chaîne par rapport à un ebook de même
longueur, et c'est exactement ce qu'on achète.

#### Où un résumé plat lâche, mesuré

Un résumé de taille **fixe** réécrit à chaque scène est un tampon : il ne
grandit pas, et ce qu'on y ajoute chasse ce qui y était. La limite est
arithmétique avant d'être littéraire — énoncer un événement demande environ
sept mots (« Camille cache la convocation dans sa poche »), donc
quatre-vingt-dix mots portent **une douzaine d'événements**, pas davantage.

`tests/test_memoire.py` le mesure sur la vraie boucle, avec un résumeur
**idéal** : il ne paraphrase pas, ne se trompe pas, garde autant de faits que
la place le permet. Ce qui est mesuré est donc la limite de *capacité*, pas le
talent d'un modèle. Un vrai modèle fera moins bien ; il ne fera jamais mieux.

| Scènes | Faits retenus — résumé plat | Faits retenus — hiérarchique |
|---:|---:|---:|
| 6 | 6 | 6 |
| 12 | 12 | 12 |
| **13** | **12** *(la scène 1 disparaît)* | 13 |
| 18 | 12 | 18 |
| 24 | 12 | 24 |
| 40 | 12 | 40 |

La bascule est nette et tombe à la **treizième scène**. À l'échelle d'un
roman, un résumé plat a perdu la première moitié du livre.

S'y ajoute un second effet, invisible dans l'arithmétique : un fait posé à la
scène 1 traverse N-1 réécritures avant la scène N, et chaque réécriture est un
réencodage avec perte. Le tampon ne se contente pas de se remplir — il déforme
ce qu'il garde.

#### La mémoire hiérarchique

Agrandir le résumé ne résout rien : il faudrait sept mots de plus par scène,
donc un résumé proportionnel à la longueur du livre, qu'il faudrait relire
entièrement à chaque scène. C'est le coût qu'on voulait éviter.

La réponse repose sur **une seule propriété** : le résumé d'une partie close
est écrit **une fois** et n'est plus jamais réécrit. Il ne subit donc ni
troncature ni réencodage.

```
Partie 1 : …figée…          ┐
Partie 2 : …figée…          ├─ écrites une fois, jamais retouchées
Partie 3 : …figée…          ┘
Partie en cours : …roulante…   ← seule celle-ci est réécrite
```

La capacité devient « nombre de parties × taille d'un résumé » et croît avec
le livre, tandis que le coût par scène reste celui d'un seul résumé roulant.
Pour vingt-quatre scènes : 24 appels de scène + **3** fermetures de partie.

Elle s'active **seule**, au-delà de la capacité mesurée. En dessous, la
mémoire plate suffit et coûte moins : la hiérarchie n'apporterait que des
appels de fermeture pour rien.

Quand le budget tombe ou que le modèle répond n'importe quoi, la mémoire ne
disparaît pas : elle continue par les **pivots** annoncés dans la grille. Un
résumé dégradé vaut mieux qu'une amnésie, qui ferait repartir de zéro toutes
les scènes suivantes.

### 3. La grille de beats

Un **beat** est un tournant de l'histoire ; une **scène** est une unité de
manuscrit. Ce ne sont pas les mêmes objets, et les confondre est ce qui
produit des chapitres qui se ressemblent tous.

L'armature retenue tient en sept beats :

| Beat | Ce qu'il fait |
|---|---|
| situation | l'ordinaire du personnage, et ce qui lui manque |
| déclencheur | l'événement qui rend le retour en arrière impossible |
| engagement | le personnage choisit d'agir, et paie ce choix |
| complication | ce qui marchait ne marche plus ; l'enjeu monte |
| crise | le pire moment : il perd ce à quoi il tenait |
| climax | la confrontation, et la décision qui la tranche |
| résolution | le nouvel ordinaire, différent du premier |

On planifie en beats, puis on écrit les scènes qui les livrent. Plusieurs
scènes peuvent servir un même beat. Chaque scène porte un **pivot** : ce qui
est vrai à la fin et ne l'était pas au début. Une scène sans pivot est une
scène morte.

## Le contrôle de continuité

Déterministe, gratuit, instantané — comme le contrôle qualité des guides, et
pour la même raison : ces défauts-là se mesurent, ils ne demandent pas le
jugement d'un modèle.

| Ce qu'il cherche | Pourquoi |
|---|---|
| un personnage de la bible qui n'apparaît nulle part | le modèle l'a oublié en route |
| le protagoniste absent de plus de 40 % des scènes | ce n'est plus son histoire |
| une scène où personne de la distribution n'est nommé | la scène a dérivé |
| deux états successifs identiques | la scène n'a rien fait avancer |
| un déclencheur, un climax ou une résolution qu'aucune scène ne livre | il manque un tournant sans lequel il n'y a pas de récit |

Les quatre autres beats ne sont **pas** exigés : une nouvelle de six scènes ne
peut pas livrer sept tournants séparément, et le lui reprocher serait faux.

Le rapport est écrit dans `continuite.json`, à côté de `bible.json`. Les
anomalies majeures apparaissent dans le journal de fabrication et dans la
fiche du produit.

**Ce que le contrôle ne reproche pas au récit.** Quand un plafond de budget
tombe, les scènes restantes sont réduites à leur fiche et la mémoire passe en
secours — elle accumule les pivots au lieu d'être réécrite. Leur vocabulaire
se recouvre alors d'une scène à l'autre, ce que le contrôle du pivot
signalerait comme « l'histoire n'avance plus ». Ce serait blâmer le récit pour
notre propre dégradation : ces scènes sont exclues de ce contrôle-là, et le
rapport dit à la place, une fois, combien de scènes n'ont pas été rédigées.

### Ce qu'il ne sait pas faire

Il compte les noms propres. Deux personnages qui partagent un nom de famille
se reconnaissent donc l'un l'autre, et une mère citée seule marque sa fille
comme présente. Le contrôle **rate alors une absence au lieu d'en inventer
une** — c'est le bon sens de l'erreur pour un garde-fou qui doit être cru
quand il parle.

## Les longueurs

Les paliers de l'usine (`mini`, `court`, `standard`, `long`) sont pensés pour
des guides. La chaîne ne les remplace pas : elle **annonce** à quel format de
fiction correspond ce qu'on lui demande.

| Format | Mots | Réglage le plus proche |
|---|---|---|
| Nouvelle | 1 000 – 10 000 | `-T mini` (≈ 4 200) ou `-T court` (≈ 7 600) |
| Novelette | 7 500 – 17 000 | `-T standard` (≈ 13 200) |
| Novella | 17 500 – 40 000 | `--chapitres 20 --mots 1200` |
| Roman | 40 000 et plus | `--chapitres 24 --mots 3500` (≈ 84 000) |

### Et le roman ?

**Il n'y a pas de type `roman`, et c'est délibéré.** Le catalogue pose une
règle : « un type qui produirait le même fichier qu'un autre sous un nom
différent n'a pas sa place ici ». Un roman sort de la même chaîne, avec les
mêmes fichiers ; seule la longueur change, et elle est déjà un réglage.

La mémoire, elle, tient désormais à cette échelle : la hiérarchie s'active
seule dès la treizième scène, et une production de vingt-quatre scènes garde
la partie 1 sous les yeux de la scène 24. C'est mesuré, pas espéré.

Ce qui reste à faire est de deux ordres, et aucun n'est la mémoire.

**Le coût, qui est réel.** Vingt-quatre scènes en qualité `standard`
demandent une **centaine d'appels**. Deux plafonds par défaut s'y opposent :

```bash
usine reglages --definir budget_appels_produit=150 budget_minutes_produit=0
```

Sans cela, le livre sort tronqué — proprement, les scènes restantes réduites à
leur fiche, mais tronqué. Comptez plusieurs heures sur un téléphone : lancez-le
via l'usine continue, écran verrouillé, téléphone en charge. Le cache rend une
interruption sans conséquence : relancer reprend où l'on s'était arrêté.

**La structure, qui est le vrai chantier.** Un roman n'est pas une nouvelle
longue. Sept beats et une distribution de quatre personnages tiennent une
nouvelle ; un roman demande des **intrigues secondaires**, un **arc par
personnage** et des **retournements qui se préparent sur plusieurs parties**.
La grille actuelle est une liste plate de tournants — elle ne sait pas
représenter une promesse posée en partie 1 et payée en partie 4. C'est le
chantier suivant, et il ne commence pas par écrire plus : il commence par
donner à la grille de quoi noter ce qui est en suspens.

## Ce qui change pour le fichier livré

Une nouvelle sort avec l'appareil liminaire complet — page de titre, page de
copyright, dédicace (`--dedicace "Pour ceux qui restent"`), table des matières
— comme tout EPUB produit par l'usine. La couverture change de style :
`literary fiction`, pas `modern editorial book cover`. Une couverture de guide
pratique sur une fiction se repère immédiatement.

## Ce que la chaîne ne fait pas

- **Elle n'écrit pas à votre place.** Ce qui sort est un premier jet
  structuré, avec une continuité tenue. Une nouvelle publiable demande une
  relecture humaine, et le contrôle qualité mesure le texte, pas son intérêt.
- **Elle ne juge pas si l'histoire vaut la peine d'être lue.** Aucun outil ne
  sait le faire. Le contrôle de continuité vérifie que le récit se tient, pas
  qu'il touche.
- **Elle ne vous dispense pas des règles de la place de marché.** Vendre de la
  fiction générée demande d'annoncer l'usage de l'IA sur les plateformes qui
  l'exigent (KDP le demande explicitement depuis 2023). Le réglage
  `signature_ia` inscrit la mention dans la licence et dans la page de
  copyright ; le déclarer au dépôt reste votre geste.
