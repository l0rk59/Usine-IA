# Un livre anglais habillé en français

Le réglage « langue » fait écrire le modèle dans la langue choisie. Tout le
reste — ce que l'usine écrit elle-même autour du contenu — était en dur, en
français.

## Ce que la mesure a montré

Mesure du 24/09/2026 : langue réglée sur « anglais », dix-sept types fabriqués
(tous sauf `idees`, qui ne livre rien à un acheteur), kit de vente et archive
compris. Le simulateur remplaçait chaque mot du modèle par « zz… » : tout mot
restant dans les fichiers livrés avait donc été écrit par l'usine.

Les dix-sept types livraient un contenu anglais dans un mobilier français :

- la licence, le `LISEZ-MOI.md`, la page de copyright de l'EPUB, le sommaire ;
- les mots fixes de chaque genre : « Chapitre », « Précédemment », « À suivre »,
  « rendez-vous au », « Jour », « Objet » ;
- les colonnes des tableurs, les consignes et le barème du quiz, le script
  qui corrige le quiz dans le navigateur ;
- la page de fin d'un tome de série (« Vous venez de lire le tome 2… ») ;
- le diagnostic d'un outil logiciel (« erreur de syntaxe : invalid syntax »).

Rien n'échouait. Le modèle écrivait bien en anglais, les fichiers étaient bien
là, et chaque test lisait des chaînes françaises parce que c'est la langue par
défaut. Le défaut n'existait que dans la langue que personne ne testait — et
c'est le premier que voit un acheteur anglophone, à la première page.

## La correction

Tout le texte fixe destiné à l'acheteur vit dans une table,
`usine/render/libelles.py`, en deux langues :

- **le français**, recopié tel qu'il sortait : un produit français ne change
  pas, à deux retouches près — l'objet d'un e-mail s'écrit « **Objet** : … »
  au lieu de « **Objet :** … », pour que le gras ne dépende plus de la
  typographie de la langue ; et la notice d'un outil ne renvoie plus
  l'acheteur à `verification.json`, un fichier interne qu'il ne reçoit
  jamais ;
- **l'anglais**, écrit à la main — pas traduit par un modèle, parce que c'est
  le texte que l'usine signe.

Les chaînes demandent `libelles.textes(ctx.langue_iso)` et n'écrivent plus un
mot fixe elles-mêmes.

**Les autres langues du réglage** (espagnol, allemand, italien, portugais,
néerlandais) reçoivent le mobilier anglais : un livre espagnol au mobilier
anglais n'est pas juste, mais l'acheteur le lit. La fabrication le dit, avant
la première ligne écrite (`base.avertir_habillage`, appelé par `preparer`, par
où passent les dix-sept chaînes). Une langue que l'usine ne reconnaît pas
garde le mobilier français, et la fabrication le dit aussi.

**Ce qui reste en français, par décision** : ce qui s'adresse au vendeur — la
fiche produit, la séquence de lancement, le journal de fabrication. C'est la
langue de celui qui fabrique.

### Les noms de fichiers

Un acheteur anglophone cherche `README`, pas `LISEZ-MOI`. Suivent la langue :

| | français | anglais |
|---|---|---|
| notice de l'archive | `LISEZ-MOI.md` | `README.md` |
| licence | `LICENCE.txt` | `LICENSE.txt` |
| manuel d'une formation | `…-manuel.pdf` | `…-manual.pdf` |
| cahier d'exercices | `…-cahier-exercices.pdf` | `…-workbook.pdf` |
| extrait gratuit | `…-extrait.pdf` | `…-excerpt.pdf` |
| tableurs de la boîte à outils | `tableau-03-….csv` | `table-03-….csv` |

Un produit empaqueté une première fois dans une autre langue garde l'ancienne
notice dans son dossier : seule celle de la langue courante part dans
l'archive, sinon l'acheteur recevrait deux modes d'emploi dont un périmé.

Les noms **fixes** d'un type — `livre.md`, `nouvelle.md`, `lire.html`,
`couverture.png` — ne changent pas. L'usine les relit (reprise, extrait,
rafraîchissement de série) et la notice les cite ; les rendre variables aurait
exposé chaque relecture à un fichier introuvable, pour un nom que l'acheteur
lit sans le comprendre de travers.

### La série

La page de fin d'un tome est refaite des mois après sa fabrication
(`usine serie rafraichir`). Le contexte de ce rafraîchissement était construit
sans langue : un tome anglais repartait en français. Il lit maintenant la
langue sur la fiche du produit.

Pour remplacer l'ancienne page sans l'empiler, le rafraîchissement la
reconnaît sous **tous** les titres qu'elle a pu porter — un tome anglais
fabriqué avant cette correction finit sur « La suite » — mais seulement en
**dernière** position, là où l'export la pose. Une scène que le modèle aurait
intitulée « What comes next » fait partie du récit, et la retirer amputerait
le livre.

### Le diagnostic du logiciel

L'analyse statique refuse de lancer un script pour quatre motifs (syntaxe,
import sensible, appel interdit, écriture hors du dossier). Le message était
composé en français et recopié tel quel dans la notice. Le souci porte
maintenant son motif et sa valeur ; la notice redit le motif dans la langue du
produit et garde la valeur (un nom de module, le message de Python). Les
messages français de la vérification sont composés à partir de la même table :
une seule source.

### Le kit de vente demandé après coup

Le kit de vente et l'archive se refont des jours après la fabrication, quand
les réglages ont pu changer : c'est la langue du **produit** qui compte. Le
carnet la porte. Un produit fabriqué avant le carnet repartait des valeurs de
repli, et aucun appelant n'y mettait la langue, pourtant inscrite sur sa
fiche : sa page de vente sortait en français. `porte.contexte_existant` la lit
maintenant sur la fiche, pour toutes les portes à la fois.

## Ce que les contrôles supposaient

Trois contrôles lisaient le texte du modèle comme s'il était forcément
français. En anglais, deux criaient à tort et un se trompait de mesure.

**Le routeur jetait des réponses valides.** Un « refus déguisé » — un message
de facturation rendu avec HTTP 200 — se reconnaît à deux signaux sur trois :
vocabulaire de service, lien vers une console, **aucun mot français**. Pour un
livre anglais, le troisième est acquis d'avance : un seul mot comme
« billing », « quota », « API key » ou « try again later » suffisait. Mesure
du 24/09/2026 : quatre textes anglais courts sur quatre (un post sur la
facturation, un « Previously » où passe le mot « quota ») étaient jetés.
Ceux qui disaient « billing » ou « credit » étaient même classés *quota
épuisé* : fournisseur mis au repos, puis le suivant, puis une boucle qui
attend des quotas pleins. L'agent dit maintenant au routeur la langue qu'il
vient de demander, et « aucun mot français » ne compte que si l'on attendait
du français. Le vrai message de facturation reste reconnu en anglais par ses
deux autres signaux.

**Un chiffre anglais sourcé passait pour inventé.** `chiffres_sans_source` ne
connaissait que « selon », « étude », « par exemple ». « According to a 2023
Gallup survey », « For example », « A McKinsey report », « Imagine » : quatre
sur quatre signalés, la note du texte baissée, et chaque correction demandait
au modèle de retirer des chiffres correctement sourcés. Les
marqueurs anglais sont ajoutés — ce qui ne peut que taire le contrôle, jamais
le faire crier.

**Le contrôle des voix est réservé au français, et le dit.** Une réplique n'est
rattachée à un personnage que par un verbe de parole de sa liste, qui est
française. Dans un livre anglais, rien n'était rattaché — sauf quand un mot
anglais s'écrit comme un verbe de la liste (« fit », « admit ») : une seule
réplique rattachée ainsi suffisait à déclarer muets tous les autres
personnages. Hors du français, il ne juge plus rien et l'écrit dans son
résumé. Les guillemets anglais “ ” comptent en revanche comme du dialogue
dans les deux langues : la part de dialogue d'un livre anglais s'annonçait
nulle, et certains modèles les posent aussi dans un texte français.

Ce qui reste français sans crier : les tics d'écriture, les promesses de
résultat, les faits relevés dans une fiction. En anglais, ces contrôles ne
trouvent rien — ils ratent, ils n'accusent pas.

## Comment c'est gardé

`tests/test_langue_livree.py` :

- **les deux tables disent la même chose** : mêmes clés, mêmes champs à
  remplir (`{titre}`…), mêmes longueurs pour les listes. Une clé absente d'un
  côté lève une `KeyError` à la livraison — dans la langue que personne ne
  teste ;
- **les tables d'affichage couvrent leurs valeurs** : chaque niveau de quiz,
  disposition d'imprimable, objectif d'e-mails, genre de mémo a son libellé
  anglais. Une valeur ajoutée sans libellé s'afficherait en français sans rien
  casser ;
- **le catalogue entier en anglais** : tiré de `catalogue.tous`, pas d'une
  liste recopiée — une chaîne ajoutée demain est lue sans qu'on y pense. Le
  test lit tout ce que l'acheteur ouvre : markdown, texte, HTML, CSV, PDF,
  chapitres de l'EPUB, archive, extrait gratuit. Il cherche quatre signes : un
  mot français qui n'est pas aussi un mot anglais, une lettre accentuée,
  l'espace avant les deux-points, les guillemets français.

Deux précautions dans ce test, chacune apprise en le voyant rater :

- le simulateur neutre donne à chaque mot un suffixe **unique** : avec
  « zz » partout, les quatre propositions d'une question se valaient, le quiz
  les écartait toutes comme insolubles, et le type sortait du test sans le
  dire ;
- les blocs qui n'existent **que dans le PDF** (barème du quiz, consignes des
  fiches imprimables) ne se voient qu'en lisant le PDF.

Les contrôles sont gardés à côté de ceux qu'ils corrigent : `tests/test_texte.py`
(le routeur, jusqu'au trajet complet avec un faux fournisseur),
`tests/test_controle.py`, `tests/test_voix.py`.

Le test ne vaut que si on l'a vu échouer : 33 mutations, chacune remettant un
morceau de mobilier en français ou défaisant une des corrections ci-dessus —
toutes détectées.
