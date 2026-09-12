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

### 4. Les fils tendus, et les arcs

Une grille plate de tournants suffit à une nouvelle. Elle ne suffit pas à un
récit long, et la raison est précise : **elle ne sait pas noter qu'un objet
montré à la scène 2 doit servir à la scène 11.** Chaque scène est alors
juste, et l'ensemble ne tient pas — c'est exactement ce qu'on reproche à la
fiction générée.

Un **fil tendu** est une promesse faite au lecteur. Il dit où il est *posé*,
où il est *payé*, et par quoi :

```json
{"nom": "la lettre non ouverte", "pose": 2, "paye": 11,
 "quoi": "une enveloppe qu'elle ne décachette pas",
 "paiement": "c'était la mutation qu'elle refusait"}
```

Un fusil accroché au mur au premier acte doit tirer au dernier. Chaque scène
reçoit donc trois choses : ce qu'elle doit **poser**, ce qu'elle doit
**payer**, et ce qui reste **en suspens** — qu'elle ne doit pas résoudre,
mais pas oublier non plus. Le nombre de fils suit la longueur : un tous les
quatre scènes environ, jamais plus de dix.

Un **arc** dit d'où part un personnage, dans quelle scène il *bascule*, et où
il arrive. Un personnage qui finit comme il a commencé n'a pas d'arc, et un
tel « arc » est écarté plutôt que noté — le noter ferait mentir le contrôle.

Tout cela vient dans **le même appel** que la grille : la structure ne coûte
pas un appel de plus.

### 5. Les intrigues secondaires

Un fil tendu est un **point** : posé ici, payé là. Une intrigue secondaire est
une **ligne** — un début, une complication, une fin — portée par un
personnage *autre que le protagoniste*, entrelacée avec l'histoire principale.

```json
{"nom": "le départ de Lucie", "personnage": "Lucie Renard",
 "enjeu": "elle a un train à prendre et personne ne le sait",
 "scenes": [3, 9, 16, 21], "resolution": "elle part sans prévenir"}
```

Une nouvelle n'en reçoit **aucune**, et ce n'est pas un manque : sa force est
de n'avoir qu'une ligne. Le seuil est à dix scènes — une intrigue demande au
moins trois scènes pour exister, et chaque scène qu'elle prend, elle la prend
à l'histoire principale.

Trois refus à l'entrée, et chacun dit ce qu'une intrigue *est* :

| Refusé | Pourquoi |
|---|---|
| moins de trois scènes | c'est une digression, pas une ligne |
| portée par le protagoniste | c'est l'histoire, pas une ligne à côté |
| sans résolution déclarée | la laisser entrer la déclarerait surveillée alors qu'elle est déjà perdue |

Chaque scène concernée sait deux choses : qu'elle porte cette ligne, et si
c'est **ici** qu'elle se termine. Une résolution qui arrive sans que la scène
le sache est une résolution qui n'arrive pas.

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
| un fil que la scène payeuse ne mentionne pas | le JSON promettait ce que la prose n'a pas fait |
| un fil que la scène où il est posé ne mentionne pas | le lecteur ne peut pas remarquer ce qui n'est pas là |
| un protagoniste sans arc | il traverse l'histoire sans changer |
| une bascule dans une scène où le personnage n'apparaît pas | il change hors champ |
| une intrigue secondaire dont la scène de résolution ne parle pas | **ouverte, suivie, puis laissée tomber** — le défaut le plus fréquent d'un récit long |
| une scène annoncée comme portant une intrigue et qui n'en dit rien | elle ne l'a pas tuée, elle ne l'a pas fait avancer *(mineur)* |

Le contrôle des fils mérite d'être décrit, parce qu'il va plus loin que les
autres : il ne se contente pas de relire la grille, il **relit la prose**. Un
fil déclaré payé à la scène 11 est cherché dans le texte de la scène 11, par
les mots porteurs de son nom (« lettre » pour « la lettre non ouverte »). Le
modèle peut promettre dans le JSON ce qu'il n'a pas écrit ; c'est là qu'on
s'en aperçoit.

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

### Le registre des faits

Les douze contrôles ci-dessus lisent la **charpente**. Aucun ne lit ce que les
phrases affirment — et une héroïne aux yeux verts scène 2 puis aux yeux bleus
scène 9 ne casse aucune structure. C'est pourtant l'erreur de continuité que
les lecteurs relèvent le plus, et celle qui échappe le plus sûrement à une
relecture d'auteur : à plus forte raison quand le texte est écrit scène par
scène par un modèle dont la mémoire est un résumé de quatre-vingt-dix mots.

`pipelines/faits.py` relève ce que le texte affirme, et signale ce qu'il
affirme de deux façons incompatibles. Trois attributs, tous à vocabulaire
fermé :

| Attribut | Peut changer ? | Gravité d'une divergence |
|---|---|---|
| couleur des yeux | non | **majeure** |
| couleur des cheveux | oui — teinture, âge | mineure, « peut être voulu » |
| âge | non, au-delà d'une dizaine d'écart | majeure |

Chaque constat cite **les deux passages**. Sans eux, vérifier une
contradiction demande de rouvrir le manuscrit ; personne ne le fait, et
l'alerte est ignorée.

```
[majeur] Camille : la couleur des yeux passe de « vert » a « bleu »
    Scene 2 : « Camille leva ses yeux verts vers le ciel. »
    Scene 9 : « Les yeux bleus de Camille ne cillaient plus. »
```

Trois décisions méritent d'être dites, parce qu'elles limitent volontairement
ce que le registre trouve :

- **Une phrase qui nomme deux personnages n'attribue rien.** À qui
  appartiennent « ses yeux verts » dans *« Camille regarda Lucie »* ? Deviner
  serait pire que se taire.
- **Les homonymes sont départagés au score.** Une mère et sa fille partagent
  un nom de famille : « Camille Renard » retrouve deux de ses mots dans
  *« Camille poussa la porte »*, « Lucie Renard » un seul. À égalité, la
  phrase reste ambiguë et n'est pas retenue. C'est le même départage que
  `personnage_officiel` — et le même bug d'homonyme, trouvé deux fois.
- **L'âge s'écrit en lettres.** La fiction dit « quarante-cinq ans », pas
  « 45 ans ». Ne lire que les chiffres revenait à ne rien lire. Le lecteur de
  nombres s'arrête à cent vingt : *« trois cents ans de solitude »* n'est
  l'âge de personne, et se rabattre sur son dernier mot en aurait fait un
  centenaire.

Un seul constat par personnage et par attribut : signaler chaque paire d'un
attribut cité dix fois noierait le constat dans sa propre répétition.

### Qui prend la parole

La bible donne à chaque personnage une **voix** — « registre, tic de langage,
ce qu'il ne dit jamais » — et cette voix part dans l'invite de chaque scène :
*« Chaque personnage parle avec la voix que lui donne la bible. »* Rien ne
vérifiait qu'elle avait été tenue. C'est exactement le défaut que l'usine
traque partout ailleurs : **une consigne émise, jamais relue.**

`pipelines/voix.py` relève les répliques et les rattache à qui les prononce.
Trois formes de dialogue, toutes trois produites par les modèles :

| Forme | Où est l'incise |
|---|---|
| `— Non, dit Camille.` | après la réplique, ouverte par la virgule |
| `— Vraiment ? demanda Lucie.` | après la réplique, sans virgule |
| `« Non », dit Camille.` | tout ce qui entoure les guillemets |

Deux conditions pour attribuer, toutes deux nécessaires : un **verbe de
parole** dans l'incise, et **un seul personnage nommé**. Sans le verbe,
*« Non. » Camille recula* attribuerait à Camille une réplique qui peut être de
l'autre. Sans l'unicité, *« Assez, dit Camille en regardant Lucie »* ferait
deviner lequel parle.

Le verbe retenu est le **dernier** de la ligne : une réplique peut contenir
*« il m'a dit »* sans que ce soit l'incise.

#### Ce que le contrôle affirme

Deux constats, parce que deux seulement se tiennent sans seuil inventé :

- **un personnage présent dans la prose et qui ne prend jamais la parole** —
  majeur pour le protagoniste, mineur sinon. Le constat ne tombe que s'il y a
  du dialogue ailleurs : une nouvelle entièrement narrative est un choix, pas
  un défaut ;
- **un personnage qui confisque la parole** — 80 % des répliques à lui seul.
  Le seuil est volontairement haut : dans une nouvelle à deux personnages,
  soixante pour cent des répliques pour l'un des deux est un équilibre normal.

#### Ce que le contrôle n'affirme pas

*« Les personnages parlent tous de la même voix »* est le défaut le plus
courant de la fiction générée, et ce module **ne le déclare pas**. Le déclarer
demanderait un seuil sur la distance entre deux profils, et ce seuil n'a pas
été mesuré sur de la fiction réelle. L'inventer produirait un garde-fou qui
crie à tort, donc un garde-fou que personne ne lit.

Les profils sont donc **rendus**, pas jugés — longueur moyenne des répliques
et son écart-type, part de questions, part d'exclamations, diversité du
vocabulaire — et c'est un humain qui les regarde. En dessous de quatre
répliques, une moyenne ne veut rien dire : le rapport dit sur combien de
personnages la comparaison aurait un sens.

Une mesure honnête vaut mieux qu'un verdict fabriqué. Un test garde cette
abstention, pour que personne n'ajoute le verdict sans la mesure.

### Ce qu'il ne sait pas faire

Il compte les noms propres. Deux personnages qui partagent un nom de famille
se reconnaissent donc l'un l'autre, et une mère citée seule marque sa fille
comme présente. Même biais pour les fils : une scène qui paie « la lettre »
en parlant de « l'enveloppe » passera pour muette.

Dans les deux cas, le contrôle **rate un manque au lieu d'en inventer un** —
c'est le bon sens de l'erreur pour un garde-fou qui doit être cru quand il
parle. Un garde-fou qui crie à tort finit ignoré, ce qui est pire que de se
taire.

Le registre des faits obéit à la même règle, et paie le même prix : il ne suit
que trois attributs, et seulement quand la phrase ne nomme qu'un personnage.
Une contradiction sur un métier, un lieu de naissance ou un nombre d'enfants
lui échappe entièrement. Ces faits-là n'ont pas de vocabulaire fermé, et les
reconnaître demanderait de comprendre le récit — ce qu'un contrôle
déterministe ne fait pas, et ce qu'un modèle relisant sa propre prose fait
mal.

## Les séries : ce qu'un tome transmet au suivant

L'usine fabriquait des produits isolés. Une nouvelle écrite hier et une
nouvelle écrite aujourd'hui ne se connaissaient pas, même si l'auteur voulait
la même héroïne dans le même village.

Deux conséquences, et **c'est la commerciale qui pèse le plus** : le tome 2 se
vend au lecteur du tome 1. C'est le seul levier de vente qu'une fabrique de
fiction possède vraiment, et rien ne l'exploitait. La seconde est littéraire :
un tome qui contredit le précédent perd ce lecteur-là pour de bon.

```bash
usine nouvelle "la ligne qui ferme"   --serie "Les rails"
usine nouvelle "dix ans plus tard"    --serie "Les rails"
usine series "Les rails"
```

Une série inconnue **n'est pas une erreur** : c'est un premier tome. Rien à
déclarer d'avance.

### Ce que la série accumule

| | |
|---|---|
| le cadre | lieu, époque, règles du monde |
| la distribution | jusqu'à 12 personnages, dans l'ordre d'apparition |
| les faits acquis | un par personnage et par attribut — yeux, cheveux, âge |
| le résumé de chaque tome | l'état final de la mémoire roulante, abrégé à 220 mots |

**Aucun appel de modèle.** Ce qui entre vient du texte produit ou de la bible
du tome, jamais d'une interprétation : un résumé de résumé dérive à chaque
génération, et au tome 4 le village aurait changé de nom sans que personne
l'ait décidé.

### Trois règles, et pourquoi

**Le premier tome qui affirme a raison.** Si le tome 3 donne des yeux bleus à
une héroïne que le tome 1 a faite aux yeux verts, ce n'est pas la série qui a
changé d'avis — c'est le tome 3 qui se trompe. Un canon qui se réécrirait
ferait du tome le plus récent l'arbitre de tout ce qui précède, et le tome 4
serait alors comparé à l'erreur du tome 3.

**Le cadre se complète, il ne se réécrit pas.** Réécrire le lieu au tome 2
déplacerait rétroactivement une histoire que le lecteur a déjà lue. Une règle
du monde que le tome 2 pose pour la première fois, elle, s'ajoute.

**Une fiche de personnage déjà connu reste celle du tome où il est apparu.**
C'est celle que le lecteur a lue.

### Le contrôle de continuité entre tomes

`pipelines/faits.py` savait déjà repérer une contradiction **dans** un texte.
Il suffisait de lui donner deux textes : le canon de la série d'un côté, ce
que le tome courant affirme de l'autre.

```
[majeur] « Camille Renard » : yeux vaut « vert » dans la serie, « bleu » ici
```

Rien n'est signalé quand la série est neuve — il n'y a pas de canon à
contredire — ni pour un attribut que la série ne connaît pas : c'est le tome
courant qui l'établit.

### La dernière page, qui est la vente

La continuité retient le lecteur. **La dernière page est ce qui lui vend le
tome suivant** — il vient de finir, c'est l'instant précis où il est le plus
disponible qu'il sera jamais, et c'est le seul endroit où on le tient encore.

Chaque tome d'une série reçoit donc un bloc « La suite » : les autres tomes,
avec leur titre et leur résumé, et une demande d'avis — c'est l'avis qui décide
si quelqu'un d'autre trouvera le livre. Zéro appel de modèle : tout vient de la
bible de série.

Une page « La suite » qui n'annonce rien n'est pas écrite. Décevoir à la
dernière page est le pire service à rendre à qui vous a lu jusqu'au bout. Et
rien n'y promet un tome à venir : ce qui est annoncé existe.

#### Le problème du tome 1, et ce qui le règle

Le tome 1 est fabriqué quand le tome 2 n'existe pas. Sa dernière page ne peut
donc annoncer personne — alors que son lecteur est **exactement celui qui
compte** : il a payé en premier, il a fini, il en veut un autre.

```bash
usine series "Les rails"              # dit combien de tomes sont à refaire
usine series "Les rails" --rafraichir
```

Sur un téléphone, tout cela est dans **« Mes séries »** au menu principal :
la liste des suites, le nombre de tomes à rafraîchir, et les deux actions —
rafraîchir, ou écrire le tome suivant. Une option qui n'existe que dans la
ligne de commande n'existe pas pour qui produit depuis son canapé.

Le rafraîchissement relit le markdown déjà livré, **remplace** sa page de fin —
ne l'empile pas, deux pages « La suite » qui se suivent se contrediraient — et
réécrit les fichiers. Le récit lui-même n'est pas touché.

Un détail compte plus qu'il n'en a l'air : **la couverture est reprise, pas
regénérée.** Celle d'un modèle d'images ne se reproduit pas à l'identique, et
un acheteur ne doit pas retrouver un livre dont la couverture a changé depuis
qu'il l'a vu. `Produit.reutiliser_couverture` existe pour cela, et n'est levé
que par une refabrication.

Il reste à redéposer les fichiers chez le distributeur — la commande le dit.

### Ce que le tome suivant reçoit

Le rappel entre dans l'invite de la bible, avant l'idée. Il nomme la série, le
cadre établi, les règles déjà posées, les personnages **avec leurs faits
acquis**, et les tomes précédents avec leur résumé. Il finit par la consigne
qui compte :

> Écris la SUITE : ne réexplique pas ce que le lecteur a déjà lu, ne contredis
> aucun fait ci-dessus, et n'oublie pas qu'un tome doit se tenir seul pour qui
> commence par lui.

Le dernier membre de phrase n'est pas une politesse. Un tome qui suppose le
précédent lu est invendable seul, et c'est pourtant ainsi que la moitié des
lecteurs arrivent.

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

**La structure.** Les deux tiers en sont faits : la grille sait maintenant
noter une promesse posée en partie 1 et payée en partie 4 (les **fils
tendus**), et un **arc par personnage** avec sa scène de bascule — voir §4.
Les deux entrent dans l'invite de chaque scène et sont vérifiés contre la
prose produite.

Les **intrigues secondaires** suivent (§5) : la grille porte des lignes
parallèles, les scènes savent laquelle elles avancent, et le contrôle sait
dire qu'une a été abandonnée en route.

Reste donc, pour un roman, ce qui n'est plus un problème de structure mais de
**jugement** : savoir si l'histoire vaut la peine d'être lue. Le contrôle
vérifie qu'un récit se tient, jamais qu'il touche — et aucun outil ne sait
faire la seconde chose. Un roman qui sort d'ici est un premier jet structuré,
avec sa continuité tenue et ses promesses payées. Il demande la même
relecture humaine qu'un manuscrit.

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
