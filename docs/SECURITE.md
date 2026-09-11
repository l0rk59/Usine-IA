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
