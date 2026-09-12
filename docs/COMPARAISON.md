# L'usine face à ce qui existe ailleurs

Audit du 12 septembre 2026. Deux questions, une par partie. **Où en est
l'usine ?** — mesuré sur le dépôt. **Que font les autres ?** — mesuré sur
leurs dépôts et leur documentation, pas sur leur communication.

L'audit interne du code, lui, est dans [AUDIT.md](AUDIT.md) ; celui du routeur
et des agents dans [ROUTEUR.md](ROUTEUR.md).

---

## 1. Ce que pèse l'usine

| | |
|---|---:|
| Code | 23 029 lignes, 71 modules |
| Tests | 11 730 lignes, 819 tests |
| Documentation | 4 452 lignes |
| Chaînes de production | 10 |
| Commandes `usine` | 30 |
| Fournisseurs IA | 10 |
| Dépendances hors bibliothèque standard | **0** |

Le rapport tests/code est de 0,51. Ce n'est pas un objectif, c'est une
conséquence : chaque correction est gardée par un test qui échoue quand on
remet le défaut (méthode décrite en fin de [ROUTEUR.md](ROUTEUR.md)).

---

## 2. Ce que la recherche a trouvé de cassé

Le plus grave n'était pas une idée manquante, c'était une panne :

> **Groq ne fonctionnait plus depuis le 16 août 2026.** Les deux modèles
> configurés avaient été retirés du palier gratuit. Chaque appel répondait
> 404, le routeur mettait le fournisseur au repos et passait au suivant —
> sans erreur, sans alerte, sans une ligne dans `usine docteur`.

Corrigé, avec le contrôle qui empêche la récidive. Cerebras avait glissé de la
même façon, les quotas de trois fournisseurs étaient faux, et le plafond
d'upload KDP avait changé fin 2025. Détail et chiffres :
[QUOTAS.md](QUOTAS.md).

**La leçon est structurelle, pas ponctuelle.** Toute donnée recopiée d'un
service tiers pourrit : identifiants de modèles, quotas, règles de
plateforme. Une usine qui tourne sur un téléphone pendant des mois sans qu'on
la regarde doit pouvoir *relire* ces données, pas seulement les porter.
`usine docteur --modeles` le fait pour les modèles. Les quotas et les règles
KDP restent datés à la main, dans les commentaires du code — c'est moins bien,
et c'est assumé : il n'existe pas d'endpoint qui les publie.

---

## 3. Comparaison avec les projets équivalents

Quatre projets actifs couvrent le même besoin — fabriquer un livre complet
avec des agents IA. Comparés sur ce qu'ils exigent pour tourner, et sur ce
qu'ils vérifient.

### Ce qu'il faut installer

| Projet | Runtime exigé |
|---|---|
| **Usine-IA** | Python 3.8+. **Rien d'autre.** |
| `Ckokoski/AuthorAgent` | Node.js 22+ |
| `agruai/ai-book-writer` | Python 3.12 + Node 20 + Docker + PostgreSQL 16 + Redis 7 |
| `wesleyscholl/book-generator` | Pandoc + LaTeX + ImageMagick + jq |
| `guerra2fernando/libriscribe` | Python + dépendances pip |

C'est la différence qui décide, et elle n'est pas idéologique. **Aucun de ces
quatre ne s'installe sur un téléphone Android.** Docker et PostgreSQL ne
tournent pas sous Termux ; une distribution LaTeX complète y pèse plus que la
mémoire disponible ; Pandoc n'y est pas empaqueté. L'usine produit PDF et EPUB
parce que ses moteurs sont écrits à la main, en Python — ce qui coûte cher en
lignes et ne rapporte rien sur un ordinateur de bureau. Sur le seul appareil
que tout le monde possède, cela rapporte tout.

### Ce que chacun vérifie

| Contrôle | Usine-IA | Autres |
|---|---|---|
| Tics d'écriture des modèles | 32 motifs français mesurés | AuthorAgent : passe « anti-AI-slop » par modèle |
| Rythme des phrases (écart-type) | mesuré | — |
| Diversité lexicale par fenêtres | mesurée | — |
| Chiffres avancés sans source | détectés | — |
| Promesses de résultat (risque juridique) | détectées | — |
| Continuité structurelle (beats, fils, arcs, intrigues) | 12 contrôles déterministes | AuthorAgent : par modèle ; ai-book-writer : agent dédié, critères non documentés |
| Contradictions de faits avec citations | 3 attributs, déterministe | AuthorAgent : base d'entités, par modèle |
| Conformité EPUB 3 | 7 contrôles structurels | — |
| Contraste WCAG déclaré et vérifié | oui | — |
| Doublons entre produits | empreintes en base | — |

**Le partage est net et il tient en une phrase :** là où les autres font
relire par un modèle, l'usine mesure. Un modèle qui se relit confirme ses
propres erreurs ; une mesure ne coûte rien, ne s'épuise pas, et donne le même
verdict deux fois de suite.

Le prix de ce choix est réel. AuthorAgent détecte des contradictions que le
registre des faits ne verra jamais — un métier, un lieu de naissance, un
nombre d'enfants n'ont pas de vocabulaire fermé. Notre registre suit trois
attributs. Il ne se trompe pas, et il en rate.

### Ce que les autres ont et que nous n'avons pas

Trois choses, honnêtement :

1. **Bible de série** (AuthorAgent) — continuité entre plusieurs tomes. Nous
   avons une bible par livre et des empreintes qui détectent les doublons
   entre produits. Rien qui tienne un univers commun. C'est une vraie absence,
   et une vraie opportunité commerciale : le tome 2 se vend au lecteur du
   tome 1.
2. **Préparation audiobook** avec attribution des voix (AuthorAgent). Nous
   avons le script de narration (`render/narration.py`) et sa durée mesurée,
   pas l'attribution par personnage ni la synthèse.
3. **Agents-personnages critiques** — un critique par personnage majeur, qui
   signale les répliques hors voix. Notre bible déclare une « voix » par
   personnage, et rien ne vérifie qu'elle est tenue. Mesurable en partie
   (longueur des répliques, vocabulaire, tics déclarés) : candidat sérieux.

### Ce qu'ils ont et que nous avons déjà en mieux

- **Suivi des coûts** (`ai-book-writer` : « real-time cost tracking, budget
  controls ») — `core/budget.py` arrête la production au plafond, et l'usine
  compte désormais requêtes *et* jetons, par minute et par jour, par modèle
  quand le fournisseur compte ainsi.
- **Chaînes de repli entre fournisseurs** (libriscribe) — dix fournisseurs,
  rotation de clés, repos persisté en base, cache des réponses, repli sur IA
  locale.
- **Anti-AI-slop** — 32 motifs français compilés, mesurés phrase par phrase,
  sans appel de modèle.

---

## 4. Ce qui a été fait à la suite de cet audit

| Constat | Action |
|---|---|
| Groq et Cerebras appelaient des modèles retirés | identifiants corrigés |
| Rien ne détectait une disparition de modèle | `usine docteur --modeles` |
| Un 404 distant ne disait pas sa cause | message qui nomme le modèle et le remède |
| Les quotas en jetons n'étaient pas modélisés | `Quota.tpm` / `tpd`, fenêtre glissante, estimation du coût avant l'appel |
| Gemini compté par fournisseur au lieu de par modèle | `Quota.portee`, comptage par modèle jusqu'au pool de clés |
| Cerebras : 25 req/min supposées, 5 réelles | corrigé |
| KDP : « trois titres par jour » | « dix par format et par semaine », vérifié sur la page d'aide d'Amazon |
| Aucun contrôle des faits affirmés par la prose | `pipelines/faits.py`, branché dans le contrôle de continuité |

## 5. Ce qui reste ouvert

- **La bible de série.** L'absence la plus nette. Demande un modèle de données
  partagé entre produits, et une décision sur ce qu'on fait des empreintes
  existantes.
- **Le contrôle de voix par personnage.** Mesurable en partie, et le premier
  candidat parce qu'il ne demande aucun appel de modèle : la bible déclare
  déjà une voix, rien ne vérifie qu'elle est tenue.
- **Les quotas datés à la main.** Aucun fournisseur ne les publie sous une
  forme lisible par un programme. Ils porteront donc toujours une date de
  vérification dans le commentaire, et ils vieilliront.
