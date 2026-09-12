# La fiction : pourquoi une chaîne à part

`usine nouvelle "un gardien de phare et le dernier hiver"`

La question revient souvent : puisque la chaîne `ebook` sait écrire un livre
de douze chapitres, pourquoi ne saurait-elle pas écrire un roman ? La réponse
n'est pas une affaire de consigne, et elle mérite d'être dite précisément.

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

### 2. Le résumé roulant

C'est la mémoire, et c'est ce que la chaîne `ebook` n'a pas. Chaque scène
reçoit l'état de l'histoire jusque-là ; en sortant, elle le met à jour.

Cela coûte **un appel court par scène** — environ quatre-vingt-dix mots, au
présent, purement factuel : qui est où, ce qui a changé, ce qui reste en
suspens. C'est le surcoût de cette chaîne par rapport à un ebook de même
longueur, et c'est exactement ce qu'on achète.

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
| Roman | 40 000 et plus | hors de portée d'une session : voir ci-dessous |

Le sur-mesure fonctionne (`--chapitres 24 --mots 3500` vise 84 000 mots), mais
un roman n'est pas qu'une nouvelle plus longue : à cette échelle, un résumé
roulant de quatre-vingt-dix mots ne suffit plus à porter vingt-quatre scènes,
et il faudrait une mémoire hiérarchique — un résumé par partie, plus un état
courant. C'est le chantier suivant, et il commence par mesurer où la mémoire
actuelle lâche.

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
