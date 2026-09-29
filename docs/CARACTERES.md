# Ce que le PDF ne sait pas écrire

## La mesure

Les caractères passés directement dans les deux moteurs, le 14/09/2026 :

```
PDF  — remplacés par « ? » : cyrillique, arabe, japonais, grec, emoji
PDF  — conservés           : « » — et tous les accents français
EPUB — perdus              : aucun
```

Un livre intitulé *« la cuisine japonaise 和食 pour débutants »* sortait donc
avec **« ?? » sur sa couverture et sa page de titre**, livré marqué « prêt »,
alors que l'EPUB du même produit était parfait. Rien ne disait lequel des deux
fichiers croire.

C'est la plainte d'origine — *« des caractères buggés qui s'introduisent dans
des produits générés »* — sur un chemin qui n'avait pas été regardé : celui du
**clavier vers le PDF**, et non celui du modèle vers le texte. Le second était
corrigé depuis longtemps ; `core/texte.py` assainit chaque réponse, en un seul
point, dans le routeur.

## Pourquoi le moteur ne peut pas tout écrire

C'est la contrainte fondatrice du dépôt. Termux ne sait pas compiler de roue
native, donc pas de `reportlab` : le moteur PDF est écrit à la main. Il
n'embarque aucune police et utilise les **quatorze polices standard** du
format, en `WinAnsiEncoding`.

WinAnsi couvre le français entier — accents, `«` `»`, tiret cadratin, ligature
`œ` — et rien au-delà de l'alphabet latin. Embarquer une police capable du
japonais demanderait un fichier de plusieurs mégaoctets et une table CID : la
dépense est hors de proportion avec le besoin, et ce dépôt ne peut compter sur
aucune police présente sur le téléphone.

Le choix n'est donc pas *« tout écrire »* contre *« écrire du latin »*. Il est
entre **le dire** et **le taire**.

## Deux pertes, deux traitements

Elles se ressemblent à l'encodage et n'ont rien à voir pour le lecteur.

| | |
|---|---|
| **un symbole** (emoji, flèche) | retiré proprement, sans laisser de trace |
| **une lettre** (и, 和, م, α) | laissée en `?`, et **signalée** |

Un emoji encodé en WinAnsi devient `?`. Dans un titre de couverture, ce point
d'interrogation se lit comme un défaut du fichier — alors qu'une absence se lit
comme un choix. Et un emoji ne porte aucune information textuelle : le retirer
ne perd rien.

Une lettre, au contraire, **ne doit pas** être effacée : un mot russe supprimé
en silence serait pire qu'un mot illisible, parce que personne ne saurait qu'il
manque quelque chose. Elle reste en `?`, ce qui se remarque, et la chaîne le
dit :

```
[!] Le PDF ne sait pas ecrire 2 caractere(s) : 和 食. Ils y apparaissent
    en « ? » — l'EPUB et le HTML, eux, les gardent.
```

Et la fiche du produit le garde : `pdf_caracteres_absents: ["和", "食"]`.

## Le détecteur ne crie pas sur du français

C'est la moitié du travail. Un dépôt entièrement français dont le contrôle
signalerait les accents serait ignoré dès le deuxième produit. Le détecteur ne
regarde que les catégories Unicode **lettre** et **nombre**, et seulement
celles que cp1252 ne porte pas :

```
L'elevage bio : « cout reel », marge — a 12 % pres, ca depend de l'oeuf.
  → perdus : aucun
```

Les symboles ne sont pas signalés, puisqu'ils sont retirés proprement. Les
signaler ferait crier le contrôle sur n'importe quel texte contenant une
flèche.

## Le titre autant que le corps

Une première version ne lisait que le texte du livre — et le cas qui a ouvert
le sujet passait inaperçu, parce que les idéogrammes étaient **dans le titre**.

Or le titre est précisément ce qui va sur la couverture et sur la page de
titre : les deux pages qu'on regarde. Le détecteur lit donc le corps, le titre,
le sujet et le nom de l'auteur.

## Et là où il n'y a pas de PDF

`usine idees` ne livre que du CSV, du JSON et du HTML. Signaler ce que « le
PDF » ne sait pas écrire à propos d'un produit qui n'en livre aucun serait un
message sur un fichier inexistant — le genre d'avertissement qui apprend à
ignorer les avertissements.

Les huit mutations de la campagne sont vues.

## Ce que le PDF écrivait bien, mais coupait mal

*Mesuré le 27/09/2026.*

Le français sépare « », :, ; ! et ? du mot par une espace, et le modèle
l'écrit ordinaire. Le moteur PDF coupait les lignes à toute espace : un « » »
ou un « : » ouvrait la ligne suivante, un « « » fermait la précédente. Sur le
texte des notes de `docs/`, composé à 330 points de large, **1,5 % des
retours à la ligne** tombaient ainsi — environ une fois toutes les deux pages
de livre. Rien n'échouait : le texte était juste, seule sa mise en page ne
l'était pas. Le défaut est apparu en regardant une planche de cartes de
révision, où une ligne commençait par « » : ».

- **PDF** : `couper` colle ces signes à leur mot avant de couper
  (`_mots_insecables` dans `usine/render/pdf.py`). Mesure après correction :
  0 % sur le même texte. L'anglais, qui ne met pas d'espace avant les
  deux-points, n'est pas touché.
- **HTML et EPUB** : le navigateur et la liseuse font la même coupure.
  L'espace devient insécable (U+00A0) dans le texte courant, le gras,
  l'italique et le texte des liens — **pas dans le code en ligne** : une
  espace insécable copiée dans un terminal n'est plus une espace, et la
  commande ne marche plus.

`tests/test_typographie.py` compose la même phrase à toutes les largeurs de
90 à 400 points ; sept mutations, toutes vues.

## Ce que le PDF savait écrire, et remplaçait quand même

*Mesuré le 27/09/2026, contre les fichiers AFM d'Adobe (la copie livrée avec
matplotlib).*

Trois défauts du même moteur, trouvés en regardant la page d'une grille de
mots mêlés dont le titre s'imprimait « Grille 1 - Les épices » :

- **des signes dégradés pour rien.** La table de remplacement disait « ce
  que WinAnsi ne sait pas écrire », mais WinAnsi a le tiret cadratin, le
  demi-cadratin, les apostrophes et guillemets courbes, les points de
  suspension, la puce, ×, ÷, ± et ™. Ils sortaient en « - », « ... », « ' » —
  et les tirets de dialogue d'un roman en traits d'union. La table ne garde
  plus que ce qui manque vraiment (flèches, ≥, ≠…), et elle a gagné ce que les
  modèles écrivent en français : l'**espace fine insécable** (U+202F, avant
  « ; ! ? » et dans les guillemets) sortait en « ? », et le **signe moins**
  (U+2212) disparaissait — « −5 °C » s'imprimait « 5 °C » ;
- **des largeurs empruntées.** Hors ASCII, chaque signe prenait la largeur
  d'un autre : « « » celle de « " », « œ » celle de « o ». Un guillemet
  français était compté 36 % trop étroit en Helvetica, « œ » 41 %, et une
  ligne justifiée qui en contenait dépassait la marge de droite d'autant.
  Les 123 signes supérieurs de WinAnsi ont désormais leur largeur AFM, dans
  les cinq polices ; les tables ASCII, vérifiées au passage, concordaient à
  l'unité près. La table de remplacement vit à côté des largeurs, pour que
  la mesure compte ce qui sera dessiné (« → » s'imprime « -> ») ;
- **le titre du fichier.** Les métadonnées étaient encodées en latin-1, qui
  n'a pas « — » : tout titre qui en porte un s'affichait « Quiz ? la paie »
  dans la barre de la visionneuse et dans la bibliothèque de la liseuse. Hors
  ASCII, elles partent maintenant en UTF-16, comme la norme le prévoit.

Aucun de ces défauts ne faisait échouer quoi que ce soit : le fichier restait
valide, et le texte, lisible. `tests/test_pdf_caracteres.py` garde les trois.
