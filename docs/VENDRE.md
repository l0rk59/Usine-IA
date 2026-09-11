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

## 5. Trouver les dix premiers acheteurs

Le dossier `bonus-publications/` contient un calendrier prêt à publier.

Ne lancez pas sur une audience inexistante. L'ordre qui fonctionne :

1. Publiez pendant deux semaines sur le sujet, gratuitement, là où se trouve
   votre audience.
2. Proposez un extrait gratuit (le chapitre 1 en PDF) contre une adresse e-mail.
3. Seulement ensuite, envoyez la séquence de lancement à cette liste.

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
