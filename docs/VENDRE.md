# Du fichier à la première vente

L'usine fabrique le produit. Ce document couvre ce qu'elle ne fait pas à votre
place.

## 1. Choisir un sujet qui se vend

```bash
usine idees "votre domaine" -n 15
```

La commande évalue chaque piste sur le problème résolu, l'acheteur, la
difficulté et la concurrence. Deux règles pour trier :

- **Un problème précis bat un thème large.** « Facturer ses premiers clients en
  freelance » se vend ; « réussir dans la vie » ne se vend pas.
- **Partez de ce que vous connaissez.** L'IA met en forme ; elle ne remplace
  pas votre expérience. Un guide générique est reconnaissable en trois pages.

## 2. Fabriquer

```bash
usine complet "votre sujet" --auteur "Votre Nom" --prix "29 EUR"
```

Vous obtenez l'ebook, une boîte à outils bonus, un pack de publications de
lancement, le kit de vente et l'archive ZIP.

## 3. Relire — l'étape non négociable

Ouvrez `livre.md` et vérifiez au minimum :

- **Les chiffres.** Les modèles inventent des statistiques crédibles. Supprimez
  ou sourcez tout nombre que vous ne pouvez pas justifier.
- **Les promesses.** Retirez toute formule qui garantit un résultat.
- **Les répétitions.** Deux chapitres disent parfois la même chose autrement.
- **Votre voix.** Ajoutez deux ou trois anecdotes personnelles : c'est ce qui
  distingue votre produit d'un fichier généré.

Comptez une à deux heures de relecture. C'est ce qui sépare un produit
remboursé d'un produit recommandé.

## 4. Mettre en vente

Le dossier `marketing/` contient déjà la description, les titres à tester, les
mots-clés et le prix conseillé.

| Plateforme | Commission | Pour qui |
|---|---|---|
| [Gumroad](https://gumroad.com) | ~10 % | le plus simple pour démarrer |
| [Payhip](https://payhip.com) | 0 % (offre gratuite) | gère la TVA européenne |
| [Etsy](https://etsy.com) | ~6,5 % + frais | trafic déjà présent, très concurrentiel |
| Votre site | frais de paiement | marge maximale, trafic à construire |

Sur la fiche produit : mettez la couverture en première image, listez les
formats livrés (PDF, EPUB, HTML), et indiquez le nombre de pages.

### Obligations légales (France / UE)

- Déclarez l'activité (micro-entreprise) avant de vendre régulièrement.
- La **TVA** sur les produits numériques est due dans le pays de l'acheteur.
  Payhip et Gumroad peuvent la collecter pour vous — vérifiez le réglage.
- Le droit de rétractation de 14 jours ne s'applique au contenu numérique que
  si l'acheteur a renoncé explicitement avant le téléchargement. Prévoyez la
  case à cocher.
- **Mentionnez l'usage de l'IA** si votre plateforme l'exige (Amazon KDP
  l'impose). La licence livrée avec chaque produit contient déjà cette mention.
- **Accessibilité — obligatoire depuis le 28 juin 2025.** L'European
  Accessibility Act s'applique aux livres numériques vendus dans l'Union.
  Les EPUB produits portent leurs métadonnées d'accessibilité et la notice
  livrée contient une déclaration. **Il vous reste deux choses à faire** :
  publier la déclaration d'accessibilité sur votre fiche produit (reprenez le
  texte de la section « Accessibilité » du `LISEZ-MOI.md`), et répondre aux
  demandes de format adapté. Les micro-entreprises de moins de 10 personnes
  et 2 M€ de chiffre d'affaires bénéficient d'une exemption partielle —
  vérifiez votre situation, la charge de la preuve vous incombe.

### La cadence de publication n'est pas la cadence de production

C'est le piège le plus coûteux, et il ne vient pas du logiciel.

`usine usine` sait fabriquer plusieurs produits par jour. **Les publier au
même rythme est le profil exact d'un compte qui se fait fermer.** Amazon KDP
plafonne à trois titres par jour et ferme les comptes de contenu IA déposé en
volume ; Etsy et Gumroad suspendent sur signalement de contenu dupliqué.

Produisez en lot, publiez lentement :

| | |
|---|---|
| Production | autant que votre budget d'appels le permet |
| Publication | **un à deux produits par semaine et par plateforme**, au début |
| Avant chaque dépôt | `usine doublons`, et une relecture humaine réelle |

Un compte fermé emporte tout l'historique de ventes et les avis accumulés.
Reconstituer cela prend des mois ; ralentir les dépôts ne coûte rien.

## 5. Trouver les dix premiers acheteurs

Le dossier `bonus-publications/` contient un calendrier prêt à publier.

Ne lancez pas sur une audience inexistante. L'ordre qui fonctionne :

1. Publiez pendant deux semaines sur le sujet, gratuitement, là où se trouve
   votre audience.
2. Proposez un **extrait gratuit** contre une adresse e-mail. L'usine le
   fabrique avec le kit de vente, dans `marketing/extrait/` : PDF et EPUB des
   premiers chapitres (un quart du livre par défaut), suivis d'une page qui
   liste les chapitres restants et renvoie vers votre site — celui de vos
   réglages `site` et `contact`.

   ```bash
   usine marketing <identifiant>              # un quart du livre
   usine marketing <identifiant> --extrait 1  # le seul premier chapitre
   ```

   Il est **découpé dans le livre déjà produit**, sans un seul appel d'IA :
   il ne consomme aucun quota, et c'est vraiment le début du livre que vous
   vendez — ce qu'un extrait promet.
3. Seulement ensuite, envoyez la séquence de lancement à cette liste.

> **L'extrait ne part jamais dans l'archive de l'acheteur.** Il vit dans
> `marketing/`, exclu de la mise en carton au même titre que votre page de
> vente. Livrer une version amputée à quelqu'un qui vient de payer le livre
> entier serait au mieux ridicule.

Un produit à 29 € vendu 20 fois rapporte plus qu'un produit à 9 € vendu deux
fois. Le prix bas n'accélère pas les ventes, il réduit la valeur perçue.

## 6. Itérer

```bash
usine liste                       # retrouve l'identifiant d'un produit
usine marketing <identifiant> --plateforme etsy --prix "39 EUR"
```

Testez une nouvelle description et un nouveau titre avant de conclure qu'un
produit ne marche pas. Dans la plupart des cas, c'est la page de vente qui
échoue, pas le produit.
