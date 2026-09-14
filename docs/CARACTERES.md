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
