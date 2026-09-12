# Audit complet — septembre 2026

Revue de bout en bout après le retrait du chercheur de failles : agents,
connexions, paramétrages, installation, dépendances. Chaque constat a été
**vérifié sur le code**, corrigé, puis gardé par un test.

## Agents : deux étaient déclarés mais ne travaillaient jamais

Un agent ne s'allume dans l'interface que lorsqu'une chaîne l'appelle
(`base.py` publie l'événement `agent`). Or deux des sept ne recevaient
aucun appel :

| Agent | Avant | Après |
|---|---|---|
| **styliste** | `polir()` défini, jamais appelé | passe de style finale au niveau **exigeant** de l'ebook |
| **contrôleur** | pastille affichée, jamais allumée | s'allume pendant le contrôle déterministe, dont il est le visage |

La fonction LLM `equipe.controler()` (un verdict avant-vente jamais branché,
un appel modèle par produit) a été **retirée** : elle faisait double emploi
avec le contrôle déterministe gratuit, et l'usine tient à ne pas gaspiller de
quota. Le contrôleur reste, personnifiant le vrai garde-fou.

La chaîne éditoriale est maintenant complète et **testée** : rédacteur →
contrôle déterministe (contrôleur) → relecture croisée (éditeur critique,
réviseur corrige, jamais le modèle qui a écrit) → style (styliste). C'est le
motif *planner–writer–critic* recommandé pour la production 2026, avec
relecture par un **autre modèle** que l'auteur.

## Paramétrages : trois réglages ne pilotaient rien

| Réglage | Symptôme | Branchement ajouté |
|---|---|---|
| `theme` | le tableau de bord l'ignorait (localStorage seul) | thème par défaut de la page, le choix manuel primant |
| `effets_3d` | jamais lu : la 3D tournait toujours | coupe la scène 3D **et** le fond animé (vieux téléphone) |
| `signature_ia` | la mention IA de la licence était figée | active/retire le bloc TRANSPARENCE de la licence livrée |

## Installation & dépendances

- **Plancher Python** : `install.sh` exigeait 3.8, l'intégration continue
  n'atteste que 3.9. Aligné sur 3.9 — ce que la CI prouve réellement.
- **Node.js** (optionnel) et **termux-api** (optionnel) : `install.sh` les
  signale désormais, avec la commande d'installation. L'usine produit sans.
- **Zéro dépendance** confirmé par `scripts/dependances.py` : rien à
  installer via pip, la contrainte fondatrice tient.

## Ce qui reste sciemment de côté

- **Limite par minute et par clé** : le pool applique une limite *par jour*
  par clé ; le débit par minute est géré en réaction (rotation sur 429 +
  backoff), pas en prévention. Suffisant, non repris pour ne pas toucher au
  throttling à l'aveugle.
- **Quelques utilitaires sans appelant** (`inventaire`, `env_int`,
  `nb_abonnes`…) : du code mort inoffensif, laissé pour éviter du brassage.
- **Types de produits manquants** : la fiction (roman, nouvelle) reste le
  grand chantier documenté dans [EXTENSIONS.md](EXTENSIONS.md) — une chaîne
  distincte, pas une variante d'ebook.
- **Thèmes** : le tableau de bord a nuit + jour (cyberpunk). D'autres palettes
  seraient un simple jeu de variables CSS si le besoin vient.
