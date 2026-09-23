# Sécurité et quotas

## Ce que l'usine ne fait pas, et pourquoi

**Elle ne crée pas de comptes automatiquement pour contourner les quotas.**
C'est explicitement interdit par les conditions d'utilisation de Groq, Google
AI Studio, Mistral, OpenRouter et Cerebras. Ces services détectent la création
en série (même empreinte d'appareil, même adresse IP, même schéma d'e-mails) et
la sanction est le bannissement de l'IP et de l'appareil — vous perdriez
l'accès à *tous* les fournisseurs d'un coup, y compris ceux utilisés
légitimement.

La méthode qui donne le même résultat sans le risque est l'addition :
**sept services gratuits cumulés** offrent plus de quota qu'un seul service
multiplié par sept comptes, et rien n'y est fragile.

| Fournisseur | Requêtes/jour (ordre de grandeur) |
|---|---|
| Groq | ~900 |
| Cerebras | ~800 |
| NVIDIA NIM | ~800 |
| Gemini | ~400 |
| Mistral | ~500 |
| GitHub Models | ~140 |
| OpenRouter | ~45 |

Un ebook de 12 chapitres en qualité standard consomme environ 40 appels. Le
cumul ci-dessus laisse largement la place à plusieurs produits par jour.

## La rotation de clés

Vous pouvez légitimement détenir plusieurs clés : personnelle, professionnelle,
celle d'un associé. Déclarez-les toutes.

```
GROQ_API_KEY=cle_une,cle_deux
GEMINI_API_KEY_2=une_autre_cle
```

Le pool :

- **répartit la charge** sur la clé la moins sollicitée de la journée, au lieu
  d'épuiser la première (ce qui déclencherait la limite par minute) ;
- **met une clé au repos** selon la raison du refus : 2 minutes sur un 429,
  1 heure sur un 401 (clé révoquée) ou un 402 (crédit épuisé) ;
- **ne fait jamais tomber le fournisseur entier** pour une clé fautive ;
- **ne stocke jamais la clé**. Seule une empreinte SHA-256 tronquée sert
  d'identifiant en base, et l'affichage est toujours masqué (`gsk_ab***xyz`).

```bash
usine docteur     # état des fournisseurs et du pool
```

## Les secrets dans les journaux

Toute chaîne ressemblant à une clé (`gsk_`, `sk-or-v1-`, `AIza`, `nvapi-`,
`ghp_`, `Bearer …`) est remplacée par `[CLE MASQUEE]` avant d'atteindre la
console, le fichier de log, le tableau de bord ou un message d'erreur. C'est
ce qui évite qu'une capture d'écran du tableau de bord publie votre clé.

Les mêmes motifs gardent le dépôt : `scripts/fuites.py`, lancé par la CI,
cherche une clé dans les fichiers suivis par git. Ils exigent la **longueur**
d'une clé après le préfixe. Le contrôle précédent cherchait `gsk_` seul : il
signalait cette page, l'aide de la ligne de commande et les clés factices des
tests, et fut rouge du 12 au 23/09/2026 sans une seule vraie clé — assez
longtemps pour qu'on cesse de le lire, et qu'il cache un échec réel sous
Python 3.9. Il affichait aussi ce qu'il trouvait : sur une vraie fuite, il
aurait recopié la clé dans le journal public de la CI. Le nouveau ne donne que
le fichier et la ligne.

## Le tableau de bord

Par défaut il écoute sur `127.0.0.1` : inaccessible depuis le réseau.

Si vous l'ouvrez au réseau local (`usine web --hote 0.0.0.0`), un jeton d'accès
est **généré automatiquement** et devient obligatoire — sinon n'importe qui sur
le même Wi-Fi pourrait lire vos produits et lancer des fabrications à votre
place. La comparaison du jeton se fait à temps constant.

```bash
usine reglages --definir jeton_web=votre-mot-de-passe   # jeton fixe
```

Les chemins de fichiers sont résolus puis vérifiés comme descendant du dossier
des produits : les formes `..`, `%2e%2e` et les chemins absolus sont refusées.

### `127.0.0.1` n'est pas une protection

C'était tenu pour une. Mais le navigateur du téléphone, lui, **est** sur
`127.0.0.1`. Mesure du 23/09/2026 : un `POST` en `text/plain` envoyé depuis
une page quelconque (`https://evil.example`) — une requête « simple », que le
navigateur émet sans demander la permission à personne — a réécrit `marque` et
`site` dans les réglages. Le jeton ne protégeait que le mode réseau local.

Deux défenses, parce qu'il y a deux attaques :

- **L'origine.** Une requête qui modifie doit venir du tableau de bord lui-même :
  `Sec-Fetch-Site: cross-site`, un `Origin` étranger et `Origin: null` (iframe
  isolée, fichier local) sont refusés. Une requête sans `Origin` passe : c'est
  `curl` ou un script sur le téléphone, qui a déjà la main sur l'atelier.
- **Le nom d'hôte.** Un domaine qu'on contrôle peut se faire résoudre vers
  `127.0.0.1` (*DNS rebinding*) ; la page est alors de même origine pour le
  navigateur, et le contrôle précédent ne voit rien. Seul l'en-tête `Host` la
  trahit : il porte le nom de l'attaquant. Il doit être `127.0.0.1`,
  `localhost`, `::1` ou l'adresse d'écoute.

`tests/test_tableau_origine.py`, sept mutations vues.

## Les domaines sensibles

Certains sujets exposent le vendeur plus que le lecteur. L'usine les détecte
(insensible aux accents) et **avertit sans bloquer** :

| Domaine | Pourquoi |
|---|---|
| santé | responsabilité, préjudice direct au lecteur |
| finance | cadre AMF en France pour le conseil en investissement |
| juridique | rédaction d'actes réservée aux professionnels |
| nutrition | dangereux sans suivi individuel |
| mineurs | obligations de protection propres aux plateformes |

Un produit sur un domaine détecté reçoit un fichier `AVERTISSEMENT.txt` avec
une clause de non-responsabilité renforcée. C'est vous qui décidez de publier.

## Ce qui ne part pas chez l'acheteur

L'archive ZIP exclut le dossier `marketing/` (votre page de vente, vos e-mails
de lancement, le prix plancher que vous étiez prêt à accepter) et les fichiers
de travail (`plan.json`, `systeme.json`, `cahier.json`…). Un test de
non-régression le vérifie à chaque exécution.

## Revue de septembre 2026

Quatre points relevés sur ce que la session venait d'ajouter — un journal sur
disque, une table, des appels HTTP, une refabrication de fichiers.

### Un identifiant ne se change pas par la surface qu'il garde

`jeton_web` est le mot de passe du tableau de bord. `POST /api/reglages`
acceptait tout réglage déclaré dans `DEFAUTS`, **y compris celui-là**. Qui
atteignait la page pouvait donc s'y enfermer en posant un jeton, ou l'ouvrir à
tous en l'effaçant.

Le défaut préexistait ; le rendre appelable depuis la page l'a mis en lumière.
`REGLAGES_HORS_WEB` l'écarte désormais. Le jeton se change depuis la machine —
`usine reglages`, ou le menu.

### Un jour est une date, pas une chaîne libre

`usine journal <jour>` posait son argument directement dans un nom de
fichier : `../../quelque-chose` désignait un fichier **hors** du dossier des
journaux — que `nettoyer()` aurait ensuite pu effacer. Le format est vérifié,
et tout le reste retombe sur aujourd'hui.

### Un journal ne remplit pas le téléphone

Quatorze fichiers gardés bornaient leur *nombre*, pas leur *taille*. Une
production de plusieurs heures écrivait sans limite. Au-delà de 2 Mo, le
fichier repart de zéro — et de zéro plutôt que coupé par le début : relire un
fichier amputé en tête donnerait un journal qui commence au milieu d'une
phrase, alors que c'est la fin qui intéresse.

### Une refabrication n'écrit que dans l'atelier

`usine series --rafraichir` **réécrit des fichiers déjà livrés**, dans un
dossier lu en base. Le dossier est maintenant vérifié comme étant sous
`PRODUITS_DIR` avant tout écrasement : une erreur ici détruirait des fichiers
que l'utilisateur a peut-être déjà mis en vente.

### Ce qui a été vérifié et n'a rien donné

- Les requêtes SQL de `core/serie.py` sont toutes paramétrées, et le nom d'une
  série est réduit à `[a-z0-9-]`.
- `expurger` couvre les deux seuls endroits où un message quitte le processus.
  La console n'y passe pas, et c'est un constat : le corps d'une réponse HTTP
  en erreur — seul endroit où un service renverrait une clé — est porté par
  `HttpErreur.corps` et n'est affiché nulle part.

