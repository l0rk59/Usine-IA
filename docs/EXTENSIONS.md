# Ce que l'usine pourrait faire de plus

Revue complète, menée en septembre 2026 : état réel du câblage, ce que
chaque type de produit sait faire, ce qu'il ne sait pas, et ce qu'on peut y
ajouter. Les affirmations ci-dessous ont été **mesurées sur le code**, pas
supposées.

---

## 1. Câblage : ce qui est branché, ce qui ne l'est pas

Audit automatique du catalogue contre les trois interfaces.

| | Résultat |
|---|---|
| Types de produits au catalogue | 9, **tous fabricables** |
| Types absents du menu Termux | aucun |
| Types absents du tableau de bord | aucun |
| Commandes CLI | 29, toutes dans le menu |

Le catalogue est donc la source unique, et les trois interfaces la suivent.
C'est l'invariant le plus important du projet et il tient.

### Trois trous réels, tous dans le tableau de bord

La carte **Produits** liste les produits et sert leurs fichiers. Elle ne sait
rien en faire :

| Commande | Ce qu'elle fait | Menu | Tableau de bord |
|---|---|:-:|:-:|
| `usine marketing <id>` | kit de vente d'un produit existant | ✅ | ❌ |
| `usine livrer <id>` | archive ZIP livrable | ✅ | ❌ |
| `usine docteur` | diagnostic complet de l'installation | ✅ | ❌ |

Les deux premières sont les actions qu'on fait **après** avoir regardé un
produit — donc exactement là où la page s'arrête. La troisième est le bouton
« pourquoi ça ne marche pas », et c'est dans le navigateur qu'on le cherche.

### Un angle mort dans le garde-fou des sujets

`securite.analyser_sujet()` couvre cinq domaines : santé, finance, juridique,
nutrition, mineurs. **Rien sur la sécurité informatique.** Un sujet comme
« guide de test d'intrusion » passe sans un mot d'avertissement, alors que
c'est précisément le domaine où la frontière entre pédagogie et outillage
d'attaque compte le plus — pour le lecteur comme pour le vendeur.

---

## 2. Les ebooks : romans, nouvelles ?

**Non, et ce n'est pas qu'une affaire d'invite.** Il faut le dire clairement
parce que la réponse a l'air d'être oui.

La chaîne `ebook` produit des **guides pratiques**, et sa mécanique est celle
d'un guide :

- chaque chapitre est rédigé **indépendamment**, sans rien savoir de ce que
  les chapitres précédents ont écrit — il ne reçoit que la liste des *titres*
  des autres, pour éviter les redites ;
- l'invite impose « un exemple chiffré réaliste », « une liste numérotée
  d'étapes applicables aujourd'hui », et termine chaque chapitre par
  **« À retenir : »**.

Pour un guide, l'indépendance des chapitres est une qualité : ils sont
modulaires, et on peut les fabriquer dans n'importe quel ordre. Pour un
roman, c'est rédhibitoire. Une fiction a besoin d'une **continuité** que
cette architecture ne porte pas : qui est présent, ce que le lecteur sait
déjà, où en est l'arc, ce qui a été promis au chapitre 3 et doit être payé au
chapitre 11.

### Ce qu'il faudrait vraiment

Une chaîne distincte (`roman`, `nouvelle`), avec trois pièces que l'ebook n'a
pas :

1. **Une bible** produite avant le premier chapitre : personnages (nom, désir,
   défaut, voix), lieux, règles du monde, chronologie. Elle est passée à
   chaque chapitre et ne change plus.
2. **Un résumé roulant** : chaque chapitre reçoit ce qui s'est passé jusque-là,
   en quelques lignes, et le met à jour en sortant. C'est la mémoire que la
   chaîne actuelle n'a pas.
3. **Une grille de structure** au lieu d'un plan de chapitres. Les
   [beat sheets](https://savethecat.com/about-the-beats/a-writers-guide-to-beats-and-beat-sheets)
   séparent le *beat* (un tournant) du *chapitre* (une unité de manuscrit) :
   on planifie en beats, puis on regroupe les scènes qui les livrent.

### Longueurs réelles du marché

Le sur-mesure actuel (2 à 60 sections × 300 à 4 000 mots) couvre
techniquement ces volumes, mais les paliers n'ont aucun sens pour la fiction.
Les repères 2026 :

| Format | Mots |
|---|---|
| Nouvelle | 1 000 – 10 000 |
| Novelette | 7 500 – 17 000 |
| Novella | 17 500 – 40 000 |
| Roman (seuil) | 40 000 |
| Romance | 50 000 – 90 000 |
| Thriller / policier | 70 000 – 90 000 |
| Fantasy | 90 000 – 130 000 |
| Fantasy épique | 100 000 – 180 000 |

Un premier roman se vise à **80 000 – 90 000 mots** dans la plupart des
genres. À 4 000 mots par section, c'est une vingtaine de chapitres — donc
dans les clous du moteur, si la continuité suivait.

### Ce que la fiction exige en plus côté fichier

Amazon KDP attend un EPUB avec un **appareil liminaire** dans l'ordre : page
de titre, page de copyright, dédicace éventuelle, table des matières. Les
titres de chapitres doivent être de **vrais styles de titre** — c'est ce qui
engendre la table des matières de l'ebook — et chaque chapitre commence par
un saut de page, jamais par des paragraphes vides.

**Fait.** L'EPUB porte maintenant l'appareil liminaire complet, dans l'ordre
attendu : couverture, page de titre, **page de copyright**, dédicace
(`--dedicace`), table des matières, puis le texte. La page de copyright porte
l'année, l'auteur, l'éditeur quand il diffère, la date d'édition,
l'identifiant unique de la publication et la mention d'assistance IA quand le
réglage `signature_ia` est actif.

La validation avant livraison est faite, mais **pas par EPUBCheck** : c'est un
programme Java, qui ne tournera jamais sur Termux. Les contrôles structurels
qu'il applique sont refaits en Python dans `render/epub_conformite.py`, et le
rapport dit lui-même ce qu'il ne couvre pas (schémas XSD, vocabulaire complet
des propriétés, liens internes) plutôt que de laisser croire à une validation
complète.

---

## 3. La sécurité : jusqu'où, et où s'arrête-t-on

> **Décision (mise à jour).** Un outil de reconnaissance passive (`usine
> recon`) avait été construit puis **entièrement retiré à la demande du
> propriétaire** : l'usine ne fournit plus aucun outil qui teste ou audite un
> site, même passivement. Elle reste sur le **contenu** de sécurité (guides,
> checklists, sensibilisation), que les chaînes existantes savent déjà
> fabriquer. La section ci-dessous garde la trace du raisonnement, mais le
> profil « audit local » et l'outil de recon ne sont pas au programme.

Le sujet est vendeur et la demande est réelle. Il faut poser la ligne une
fois, clairement, parce qu'elle décide de tout le reste.

### La ligne

L'usine peut fabriquer des produits qui **apprennent à se défendre**, qui
**expliquent** comment une attaque fonctionne, et qui **auditent votre
propre** matériel. Elle ne fabrique pas d'outil qui attaque ce qui ne vous
appartient pas — ni scanner de cibles tierces, ni collecteur
d'identifiants, ni exploit prêt à l'emploi, même « pour apprendre ».

Ce n'est pas de la frilosité : un produit vendu sur une place de marché est
utilisé par des gens qu'on ne connaît pas, et la responsabilité du vendeur
est engagée. C'est la même raison qui fait que la chaîne `logiciel` **refuse
d'exécuter** `os.system`, `subprocess`, `socket` et l'écriture hors dossier.

### Ce qui tient largement du bon côté, et qui se vend

Le marché existe et il est documenté — les
[CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks) couvrent plus de
25 familles de produits, et les
[modèles de politique NIST CSF](https://www.cisecurity.org/-/media/project/cisecurity/cisecurity/data/media/files/uploads/2024/08/cis-ms-isac-nist-cybersecurity-framework-policy-template-guide-2024.pdf)
font correspondre 49 sous-catégories à des documents prêts à adapter.

| Produit | Chaîne existante | Ce qu'il faudrait |
|---|---|---|
| Guide « sécuriser son activité en 7 jours » | `ebook` | rien, ça marche déjà |
| Checklist de durcissement (Android, Windows, routeur) | `outils` | un cadre de référence pour ne pas inventer |
| Politique de sécurité type pour TPE (RGPD, mots de passe, sauvegarde) | `modeles` | correspondance NIST CSF / CIS |
| Cahier d'exercices « repérer un hameçonnage » | `impression` | rien |
| Mini-formation sensibilisation employés | `formation` | rien |
| Plan de réponse à incident à remplir | `outils` | trame IR |
| Audit de **sa propre** installation | `logiciel` | voir ci-dessous |

### Le seul qui demande du travail : l'outil d'audit

Un script qui inspecte **la machine de l'acheteur** est le produit le plus
proche de « l'outil » que la sécurité permette honnêtement. Il est réalisable
dans les contraintes actuelles — bibliothèque standard, sans réseau — mais
la chaîne `logiciel` l'interdit aujourd'hui : lire des permissions de
fichiers ou l'état d'un pare-feu suppose exactement les appels que le bac à
sable refuse.

Deux façons de s'en sortir, à trancher :

- **un profil « audit local »** pour la chaîne `logiciel`, qui autorise la
  lecture de `/etc`, des permissions et de la configuration réseau, en
  refusant toujours l'écriture et toute connexion sortante ;
- ou **produire un script qu'on ne fait pas tourner** : livré avec sa
  vérification syntaxique et son mode `--dry-run`, mais jamais exécuté par
  l'usine. Plus sûr, moins convaincant.

Recommandation : le profil « lecture seule, sans réseau ». Il garde la
promesse de la chaîne — *« un outil qui démarre, vérifié avant livraison »* —
qui est ce qui la distingue.

### Et le garde-fou

Un domaine `securite` dans `DOMAINES_SENSIBLES`, qui reconnaît « intrusion »,
« pentest », « exploit », « mot de passe », « faille » et prévient sur deux
points : ce qui est légal chez soi ne l'est pas ailleurs, et une place de
marché retire ce qu'elle juge être de l'outillage offensif.

---

## 4. Ce qu'on peut ajouter, type par type

Classé par rapport entre ce que ça apporte et ce que ça coûte.

### `ebook` — guides
- ~~**Page de copyright et appareil liminaire**~~ **Fait.** Voir §2.
- ~~**Validation EPUBCheck** avant livraison~~ **Fait**, en Python : voir §2.
- **Éditions déclinées** : le même livre en « version courte » offerte pour
  capter des adresses, et en version complète payante.

### `roman` / `nouvelle` — fiction *(chaîne nouvelle)*
**Fait pour la nouvelle.** `usine nouvelle` livre les trois pièces décrites au
§2 — bible, résumé roulant, grille de beats — plus un contrôle de continuité
déterministe. Voir [FICTION.md](FICTION.md).

**La mémoire du roman est faite.** Elle a commencé par la mesure annoncée :
un résumé de taille fixe porte douze scènes, la treizième chasse la première,
et c'est de l'arithmétique — sept mots par événement, quatre-vingt-dix mots
de résumé. La mémoire hiérarchique (parties closes figées + état courant)
s'active seule au-delà, et retient 24 faits sur 24 là où la plate en retenait
12. Chiffres et méthode dans [FICTION.md](FICTION.md) ; la mesure tourne dans
`tests/test_memoire.py`.

**Ce qui reste au roman n'est plus la mémoire, c'est la structure** :
intrigues secondaires, arc par personnage, promesse posée en partie 1 et payée
en partie 4. La grille est une liste plate de tournants ; elle ne sait pas
noter ce qui est en suspens.

### `prompts` — packs de prompts
- **Variantes par modèle** : ce qui marche sur un modèle échoue sur un autre.
- **Fichier importable** dans les outils qui acceptent des bibliothèques.

### `formation` — mini-formations
- **Quiz auto-corrigés** en HTML autonome (la chaîne produit déjà du HTML).
- **Script de narration** par module, pour qui veut enregistrer une voix.

### `outils` — boîtes à outils
- **Cadres de référence** : la valeur d'une checklist vient de ce sur quoi
  elle s'appuie. CIS et NIST CSF sont publics et faits pour ça.

### `modeles` — Notion / tableur
- **Formules réellement calculées** plutôt que des colonnes vides.
- **Deux versions** : vide à remplir, et pré-remplie en exemple.

### `impression` — cahiers
- **Format A5 et Letter** en plus de A4 : le marché anglophone imprime en
  Letter.
- **Marge de reliure** pour l'impression à la demande.

### `social` — packs de publications
- **Découpage par réseau** avec les limites réelles de caractères.
- **Visuels de citation** : le moteur de couverture sait déjà composer texte
  et fond, il suffit d'un autre format.

### `logiciel` — outils vérifiés
- **Profil « audit local »** (voir §3).
- **Autres langages** : la vérification est spécifique à Python ; du
  JavaScript demanderait un vérificateur à part.

### `idees` — études de niche
- La veille Reddit et le sondage de marché l'alimentent déjà. Rien d'urgent.

---

## 5. Termux et le navigateur local

L'intégration Termux était **documentaire** : `termux-open` et
`termux-wake-lock` étaient *conseillés dans le texte*, jamais appelés. Elle
est maintenant branchée, dans `core/telephone.py`.

| Appel | Ce que ça change | État |
|---|---|:-:|
| `termux-notification` | savoir qu'un produit est prêt sans regarder le terminal | ✅ |
| `termux-battery-status` | l'usine continue s'arrête sous X % au lieu de vider le téléphone | ✅ |
| `termux-wake-lock` | pris automatiquement pendant une fabrication, relâché après | ✅ |
| `termux-open` | ouvrir le PDF produit, au lieu d'afficher son chemin | ✅ *(notification, et menu)* |
| `termux-share` | envoyer le ZIP vers Drive, un courriel ou Telegram | ✅ *(menu)* |

Tous se comportent pareil quand `termux-api` n'est pas installé : le binaire
est absent, on l'ignore. Aucune dépendance ajoutée — ce qui est la contrainte
fondatrice.

Deux choix méritent d'être notés, parce qu'ils ne se devinent pas :

- **la batterie se lit entre deux produits**, jamais pendant. C'est le seul
  point d'arrêt propre : couper au milieu d'un chapitre laisserait un dossier
  à moitié écrit, ce que le reste de la conception s'acharne à éviter ;
- **un délai d'attente sur chaque appel**. Le paquet `termux-api` installe les
  commandes, mais elles dialoguent avec l'application Termux:API, à installer
  séparément. Paquet sans application, `termux-battery-status` ne rend jamais
  la main : sans délai, l'usine se figerait avant son premier produit, sans
  rien dire. C'est le pire mode de panne, et il coûtait une ligne à éviter.

L'écran **Mes produits** du menu porte les deux derniers : *Ouvrir sur le
téléphone* (le PDF principal — celui qui pèse le plus lourd, car l'annexe
`guide-annexe.pdf` trie *avant* `guide.pdf`) et *Partager l'archive*. Sans
archive, le menu propose de la créer plutôt que de renvoyer l'utilisateur vers
`usine livrer`.

Les deux entrées existent **partout**, y compris là où `termux-api` est
absent : une numérotation qui change selon la machine est un piège pour les
tests comme pour l'utilisateur. Quand l'outil manque, le menu le dit, donne la
commande d'installation et affiche le chemin du fichier.

### Côté navigateur

Le tableau de bord tourne sur `127.0.0.1`, donc sans HTTPS — ce qui **ferme**
une partie des API du navigateur (service workers, notifications sur
certains moteurs). Ce qui reste ouvert et utile :

- **glisser-déposer** un export de ventes ou une archive sur la page, au lieu
  de passer par le sélecteur de fichiers ;
- **impression** de la fiche produit ou de la planche A/B avec une feuille de
  style dédiée ;
- **lecture hors-ligne** des produits déjà fabriqués.

---

## 6. Ordre proposé

1. ~~**Brancher les trois trous** : `marketing`, `livrer` et `docteur` dans le
   tableau de bord.~~ **Fait.** Les contrôles de `usine docteur` vivent
   maintenant dans `core/diagnostic.py`, lus par les deux interfaces — les
   recopier côté web en aurait fait deux jeux qui divergent. Au passage, le
   diagnostic gagne l'**espace disque libre** : un téléphone se remplit, et
   une fabrication qui s'arrête faute de place ne dit pas pourquoi.
2. ~~**Le domaine `securite`** dans le garde-fou des sujets.~~ **Fait.**
3. ~~**Les notifications Termux**, plus la coupure sur batterie faible.~~
   **Fait.** Voir §5 : `core/telephone.py`, trois réglages (`notifications`,
   `batterie_minimum`, `verrou_veille`), et l'état de `termux-api` remonté
   dans `usine docteur` comme au tableau de bord.
4. ~~**L'appareil liminaire des ebooks** et la validation EPUBCheck.~~
   **Fait.** Page de copyright et dédicace dans l'EPUB ; contrôle structurel
   en Python plutôt qu'EPUBCheck, qui demanderait Java. 16 des tests du
   contrôle cassent volontairement un EPUB valide — un contrôle qui ne sait
   rien refuser ne prouve rien.
5. ~~**La chaîne `nouvelle`** — la fiction par le format le plus court, pour
   éprouver la continuité avant d'attaquer le roman.~~ **Fait.**
   `usine/pipelines/nouvelle.py` : bible, résumé roulant, grille de beats,
   contrôle de continuité déterministe. Le test de fumée refuse désormais de
   passer si un type du catalogue n'est fabriqué par aucun de ses scénarios —
   c'est ainsi que l'oubli d'une chaîne se voit.

### Ce qui vient ensuite

Le backlog n'est pas vide pour autant. Par ordre de rapport entre ce que ça
apporte et ce que ça coûte :

1. ~~**La mémoire hiérarchique**, sans laquelle le roman reste hors de portée.~~
   **Fait**, et mesuré avant d'être écrite (voir §4). La suite pour le roman
   est la **structure** : une grille qui sache noter une promesse en suspens
   et l'arc de chaque personnage.
2. ~~**`termux-share`** : envoyer une archive livrable vers Drive ou un
   courriel depuis l'écran « Mes produits » du menu.~~ **Fait**, avec
   *Ouvrir sur le téléphone* dans le même écran (voir §5).
3. **Éditions déclinées** d'un ebook : version courte offerte pour capter des
   adresses, version complète payante.
4. **Quiz auto-corrigés** en HTML autonome pour les mini-formations : la
   chaîne produit déjà du HTML.
*(L'ancien item « profil audit local » est retiré : la direction outillage de
sécurité a été abandonnée.)*
