---
name: rendu
description: Toucher aux moteurs de fichiers ecrits a la main — PDF, EPUB, couverture, typographie, tableur — dans usine/render/. A utiliser quand un PDF s'ouvre mal ou pas du tout, quand un distributeur refuse un EPUB, quand il faut ajouter un element de mise en page (titre, encadre, image, pied de page), changer une police ou une marge, ou quand quelqu'un propose d'installer reportlab, ebooklib, WeasyPrint ou Pandoc. A utiliser aussi devant un fichier livre qui s'ouvre chez soi mais que personne d'autre ne peut lire.
allowed-tools: Bash, Read, Edit, Grep, Glob
---

# Les moteurs ecrits a la main

`usine/render/` contient un generateur PDF (772 lignes), un generateur EPUB 3
et son controleur de conformite, un moteur de couverture, un metreur de
largeur de texte et un tableur CSV/XLSX. Tout en Python standard.

Ce n'est pas de l'entetement. Un telephone sous Termux ne compile pas de roue
native : `reportlab` demande un compilateur C, `WeasyPrint` demande Cairo et
Pango, `EPUBCheck` est un programme Java. Aucun ne s'installe la ou l'usine
doit tourner. Avant de proposer une bibliotheque, verifier qu'elle n'est pas
deja ecrite ici — c'est souvent le cas.

## Le danger propre a ces formats

**Un fichier casse s'ouvre quand meme.** Les lecteurs PDF reparent
silencieusement une table de references fausse ; l'archive d'un EPUB invalide
s'ouvre sans broncher. Le fichier a l'air bon chez soi, et c'est le
distributeur qui le refuse trois semaines plus tard, ou le liseuse de
l'acheteur qui affiche une page blanche.

D'ou la regle : **ne jamais juger un fichier genere en l'ouvrant.** Le
controler.

```bash
python3 -c "
import json, sys
from usine.render.epub_conformite import verifier_epub
print(json.dumps(verifier_epub(sys.argv[1]).en_donnees(), ensure_ascii=False, indent=1))
" atelier/produits/<dossier>/<livre>.epub
```

`epub_conformite.py` refait les controles structurels d'EPUBCheck : `mimetype`
en premiere entree non compressee, conteneur designant un OPF present, chaque
fichier du manifeste present dans l'archive, chaque entree du dos declaree,
document de navigation portant `epub:type="toc"`, XML bien forme partout. Sa
docstring dit aussi ce qu'il **ne** fait pas — schemas XSD, vocabulaire
complet des proprietes, liens internes.

## PDF : ce qui casse le fichier

Le format est une suite d'objets numerotes, suivie d'une table `xref` qui
donne **le decalage en octets de chaque objet depuis le debut du fichier**,
puis d'un `trailer` et d'un `startxref` qui pointe vers cette table.

Consequence : **toute modification de ce qui precede un objet decale tout ce
qui suit.** Les decalages ne se calculent donc qu'a l'ecriture, dans la boucle
finale de `DocumentPDF`, jamais a l'avance.

Trois pieges reels, chacun deja rencontre :

- **Les chaines litterales s'echappent.** Une parenthese non echappee dans un
  titre casse la structure du fichier sans qu'aucun lecteur ne dise pourquoi.
  Tout texte qui entre dans un dictionnaire passe par `_chaine_pdf()`.
- **`/Info` et `/Lang` ne sont pas decoratifs.** Sans dictionnaire `/Info`, le
  fichier s'affiche « Untitled » dans les lecteurs et arrive sans auteur chez
  les distributeurs. Sans `/Lang`, un lecteur d'ecran doit deviner la langue —
  il devine l'anglais.
- **Le texte est mesure, pas devine.** `render/metriques.py` porte les largeurs
  des polices de base ; c'est ce qui permet de couper une ligne au bon endroit
  et de centrer un titre. Une mise en page qui calcule en « nombre de
  caracteres » deborde des le premier mot large.

Verification minimale apres toute modification du moteur :

```bash
python3 tests/fumee.py      # fabrique un produit complet de chaque type
python3 -m unittest tests.test_reliure tests.test_epub tests.test_accessibilite -q
```

## Couleurs et lisibilite

Toute couleur posee dans un document passe par `render/lisibilite.py`, qui
declare les paires et **verifie leur contraste WCAG**. Une couleur choisie a
l'oeil passe le regard de son auteur et echoue chez un lecteur malvoyant, sur
un ecran au soleil, ou a l'impression en niveaux de gris. Ajouter la paire au
module plutot que la valeur au document.

## Ce qui compte a l'autre bout

Le fichier n'est pas l'objectif : la vente l'est. Deux details qui se voient
seulement chez l'acheteur, et que les tests gardent :

- **La marge de reliure.** Un interieur broche dont la marge interne est egale
  a l'externe perd ses premiers caracteres dans la pliure.
- **Le fichier montre a l'utilisateur.** Trier les fichiers par nom fait
  remonter `guide-annexe.pdf` avant `guide.pdf` — le tiret precede le point.
  Prendre l'ordre du resume de fabrication, ou le plus gros fichier.

## Si un format manque vraiment

Ecrire le moteur ici, en lisant la specification, et lui ecrire son
controleur de conformite dans la foulee. Un generateur sans controleur produit
des fichiers dont personne ne sait s'ils sont valides — et on ne l'apprend que
par un refus de distributeur.
