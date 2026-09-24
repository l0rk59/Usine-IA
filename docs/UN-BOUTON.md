# Un type, un bouton

## Ce qui était demandé

> « Je veux juste que tout fonctionne, une usine où je n'ai besoin de rien
> faire à part appuyer sur générer — en gardant quand même le choix du type
> de produit. »

## Ce que la mesure a dit

Le moteur y répondait déjà. Mesure du 15/09/2026, par le **chemin réel du
tableau de bord** (`serveur._lancer`), un type choisi et des options **vides**,
pour les dix-huit types : **dix-huit produits livrés, zéro échec**. Vérifié sur
le disque, pas sur le code de retour — entre 8 et 11 fichiers par produit, 149
à 365 Ko, statut `pret`.

Deux choses ne suivaient pas.

## Le conte mettait 83 secondes quand les autres en mettaient 6

Dont **77,5 en images**. Quinze appels — une couverture, quatorze
illustrations — et aucun fournisseur d'images joignable. Chaque appel rejouait
trois tentatives avec attente : les quatorze derniers réapprenaient, à cinq
secondes pièce, ce que le premier avait établi.

C'est un défaut **introduit par le travail sur les réessais** : avant lui, une
image ratée coûtait zéro seconde. Les réessais restent justes pour un
hoquet — c'est de les payer quinze fois qui ne l'est pas.

`images._demander_une_image` retient donc le constat. Après un `insister`
épuisé — trois tentatives sur cinq secondes, c'est déjà la mesure — les appels
suivants tentent leur chance **une fois**. Aucun délai, aucun seuil à
inventer : le premier succès efface le constat et l'insistance reprend, donc un
service qui revient au milieu d'un album est repris au vol.

**83 s → 12,8 s**, dont 6,1 en images.

Le test qui garde cela a d'abord fait tomber un test voisin, et il avait
raison : le constat traverse les appels — c'est tout son intérêt — donc il
traverse aussi les tests, et le premier qui échouait rendait le suivant
complaisant. Chaque mesure le remet à zéro.

## Le formulaire demandait sept choses avant le bouton

Type, sujet, audience, ton, volume, qualité, auteur — plus une carte entière
de réglages propres au type. Tous facultatifs depuis toujours : un champ vide
veut déjà dire « décide pour moi ». Mais **dépliés, ça ne se voit pas**. Sept
cases vides se lisent comme sept questions auxquelles il faut répondre, et on
cherche quoi écrire dans « Audience » au lieu d'appuyer.

L'onglet « Fabriquer » tient maintenant en trois éléments :

1. le type de produit — le choix qui reste ;
2. une phrase qui dit que le formulaire est fini ;
3. un repli « Choisir moi-même », fermé, qui contient tout le reste.

Rien n'est retiré. Le choix est à un clic, et il est complet.

Trois chemins renvoient le curseur dans le champ « sujet » — mettre le sujet
en file, reprendre un titre trouvé par la veille, signaler un sujet manquant.
Ils ouvrent le repli d'abord : sans cela, `focus()` viserait un champ dans un
bloc fermé et rien ne bougerait à l'écran — exactement le défaut déjà corrigé
quand ce champ vivait dans un onglet caché.

## La vérification qui compte

Pas une fonction appelée depuis un test : **le vrai navigateur, le vrai
serveur, le vrai bouton**, dans une fenêtre de téléphone (412 × 915).

Un geste — choisir « memo » dans la liste — puis un clic. Résultat :

```
L'usine choisit la niche...
3 domaines proposes — mesure sur les sources publiques...
Aucune source de marche n'a repondu : ces domaines sont PROPOSES, pas mesures.
Premiere niche, choisie par l'usine : « la facturation des independants ».
L'usine decide 1 reglage(s) : nombre...
  nombre : 7
Etape 1/2 — structure du memo...
Etape 2/2 — export...
```

Et sur le disque : `Memo — la facturation des independants`, statut `pret`,
huit fichiers — couverture PNG et SVG, PDF, page HTML, CSV, markdown, JSON.

Le journal reste honnête là où il pourrait se taire : aucune source de marché
n'ayant répondu, il dit que la niche est **proposée, pas mesurée**. Une usine
qui se tait sur ce qu'elle n'a pas pu vérifier est une usine qu'on cesse de
croire.

## Livré n'est pas bien fait : le bouton envoyait « auto » au rédacteur

La vérification ci-dessus regardait le disque et le statut. Elle ne regardait
pas **ce que le modèle avait reçu**. Mesure du 23/09/2026, en gardant chaque
invite envoyée par un ebook fabriqué à partir du seul sujet :

| Porte | Invites | « TON : auto » / « PUBLIC : auto » |
|---|---|---|
| ligne de commande | 13 | 0 |
| tableau de bord (`serveur._lancer`) | 15 | **15** |
| usine continue (`UsineContinue._fabriquer`) | 15 | **15** |

Seule la ligne de commande appelait le brief — l'appel qui décide, d'après le
sujet, à qui l'on parle, sur quel ton et en combien de sections. Or les
réglages par défaut valent `auto` depuis que l'usine décide tout
([DEPUIS-ZERO.md](DEPUIS-ZERO.md)). Par le bouton « Générer », c'est-à-dire
l'usage réel sur un téléphone, le modèle de rédaction lisait donc un mot sans
sens là où il attendait une consigne. Rien n'échouait : le livre s'écrivait,
d'une voix que personne n'avait choisie.

Même cause, second effet : un réglage de fiction choisi dans le formulaire
(« ambiance : brume et sel ») n'atteignait qu'**une invite sur vingt-huit** —
celle qui décide des *autres* réglages —, jamais celles qui écrivent. Un
garde-fou de structure vérifiait pourtant que la promesse de lecture était
posée… par deux portes sur trois. Il ignorait le tableau de bord.

Le kit de vente et le test A/B, lancés sur un produit déjà fabriqué, avaient
le même défaut par un autre chemin : ils reconstruisaient un contexte depuis
les réglages, donc « auto » — 2 invites sur 2 pour le kit, 1 sur 1 pour
l'A/B. La ligne de commande, elle, écrivait en dur « pro » et « un public
francophone motivé ». Ils reprennent désormais le contexte gardé au carnet du
produit, sans rien redemander (`porte.contexte_existant`).

Et la langue et la marque, par le même chemin : réglée sur « anglais »,
l'usine écrivait en français depuis le tableau de bord et la boucle — 0 invite
sur 7 demandait l'anglais, l'EPUB se déclarait `fr` —, et la marque
n'apparaissait dans aucun fichier (mesure du 24/09/2026). Un test compare
désormais les deux constructeurs de contexte champ par champ ; la liste des
champs est dérivée de la structure, pas écrite à la main.

Les trois portes passent maintenant par une seule préparation,
`brief.completer` : promesse de lecture, puis brief. Après : **0 « auto »**
sur les trois, et l'ambiance choisie dans **11 invites sur 23**.

Et quand le brief ne peut pas répondre, « auto » ne part pas non plus. La règle
d'échec disait « on garde les valeurs par défaut » — qui valent `auto`. Le
public et le ton deviennent alors une consigne en toutes lettres (« celui qui
sert le mieux ce sujet et ce public »), et le journal dit qu'ils ont été
laissés au rédacteur.

## Le bouton « Reprendre » ne reprenait rien

Un produit coupé par les quotas reste « inachevé » : c'est voulu, et c'est ce
qui le rend reprenable. La reprise rejouait la commande gardée au carnet. Mais
cette commande venait de `sys.argv`, donc de la ligne de commande — et les deux
autres portes n'en ont pas :

| Fabriqué par | Commande gardée | `usine reprendre` |
|---|---|---|
| usine continue | `usine demarrer` | `unrecognized arguments: --reprendre-id`, code 2 |
| tableau de bord | celle que le processus a vue en dernier : `web`, ou celle d'un **autre** produit | idem, et le travail restait « en cours » pour toujours : argparse sort par `SystemExit`, qu'un `except Exception` laisse passer |

Même par la ligne de commande, la reprise reconstruisait le contexte depuis les
arguments : les décisions du brief n'y figuraient pas, et les chapitres repris
partaient `auto`, d'une autre voix que les premiers. Un sujet laissé vide à
l'origine faisait même choisir une **nouvelle** niche, écrite dans le dossier
de l'ancienne.

Le carnet garde désormais, au premier instant où le dossier existe, le
**contexte résolu** — sujet, public, ton, volume, promesse de lecture,
décisions — et, pour ce qui passe par le catalogue, le type et les options une
fois décidées. À la reprise, c'est lui qui fait foi, quelle que soit la porte
(`pipelines/reprise.py`) ; rien n'est redemandé au modèle. Treize mutations,
treize vues (`tests/test_trois_portes.py`).

## Coupé par les quotas, fini sans qu'on revienne

Un produit lancé par « Générer » et coupé par les quotas restait inachevé,
avec un bouton « Reprendre » — qu'il fallait penser à presser, c'est-à-dire
s'apercevoir d'abord qu'il manquait dix scènes. L'usine continue sait déjà
attendre qu'un fournisseur rouvre et finir un produit depuis son carnet
([USINE-CONTINUE.md](USINE-CONTINUE.md)) : le tableau de bord le lui confie, et
la démarre pour ce seul produit si elle ne tourne pas — les autres niches de la
file attendent qu'on les demande. Seulement quand les fournisseurs se sont
tus : un trou d'une autre nature (une section illisible à chaque essai) ne se
répare pas en attendant, et reste à la main.

En l'écrivant, une course est apparue dans la suite de tests : la boucle et
une reprise manuelle finissaient le même produit en même temps, et l'une
mourait sur `carnet.json.tmp`, déplacé sous ses pieds par l'autre. Sur un
téléphone, c'est la boucle qui attend et l'utilisateur qui appuie quand même
sur « Reprendre ». Une reprise à la fois par produit, désormais
(`core/verrou.py`, le mécanisme du verrou de l'usine, sorti de
`production.py` plutôt que recopié) ; la boucle laisse faire celui qui finit
déjà. Et chaque écrivain du carnet a son propre fichier provisoire.
