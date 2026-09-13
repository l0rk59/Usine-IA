# Usine-IA — conventions du depot

Fabrique de produits digitaux qui tourne **sur un telephone Android, sous
Termux**. Cette phrase n'est pas une anecdote : elle explique presque toutes
les contraintes ci-dessous.

## La contrainte fondatrice : zero dependance

Rien hors de la bibliotheque standard de Python. Pas de `pip install`, pas de
CDN, pas de Node, pas de Java.

Termux ne sait pas compiler de roue native, et une dependance ajoutee par
megarde ne se voit qu'au moment ou quelqu'un installe sur un telephone neuf —
c'est-a-dire trop tard. C'est pourquoi les moteurs PDF et EPUB sont ecrits a
la main, et pourquoi la conformite EPUB 3 est refaite en Python au lieu
d'appeler EPUBCheck, qui est un programme Java.

`python3 scripts/dependances.py` le verifie en lisant l'arbre syntaxique.

Corollaire pratique : avant de proposer une bibliotheque, verifier qu'elle
n'est pas deja ecrite ici. `render/`, `packaging/` et `core/http.py`
contiennent beaucoup de roues deja inventees pour cette raison.

## Langue

**Tout est en francais** : noms de fonctions, de variables, de fichiers,
commentaires, docstrings, messages a l'utilisateur, messages de commit. Sans
accent dans le code (`controler`, `fenetre`) ; avec accents dans la
documentation Markdown et dans les textes montres a l'utilisateur.

## Ce qu'un commentaire doit dire

**Pourquoi, pas quoi.** Le code dit deja ce qu'il fait.

Les commentaires de ce depot racontent le defaut qu'ils empechent de revenir.
C'est leur fonction : sans l'histoire, la ligne suivante ressemble a une
complication gratuite et quelqu'un la simplifiera.

```python
# « length » signifie : le modele n'avait pas fini, il a ete coupe au
# plafond. Ne pas le lire faisait passer un chapitre tranche au milieu
# d'une phrase pour un chapitre termine — le defaut le plus couteux du
# routeur, parce qu'il est invisible partout en aval.
```

Meme regle pour les messages de commit : ils expliquent **ce qui allait mal et
pourquoi c'etait invisible**, pas la liste des fichiers touches.

## Ce qu'on ne fait pas

- **Pas de code sans appelant.** Une fonction que personne n'appelle ne
  protege personne. Si une chaine ne l'utilise pas, elle n'existe pas.
- **Pas de reglage orphelin.** Un parametre affiche, sauvegarde et jamais lu
  est un mensonge fait a l'utilisateur. Un test garde ce point.
- **Pas de chiffre sans source.** Le controle qualite refuse un pourcentage
  enonce sans marqueur de source — la meme regle vaut pour le code et pour la
  documentation. Un quota recopie d'un fournisseur porte sa date de
  verification en commentaire.
- **Pas de garde-fou qui crie a tort.** Un controle qui signale a tort finit
  ignore, ce qui est pire que se taire. Quand l'attribution est ambigue, les
  controles de ce depot **ratent un defaut plutot que d'en inventer un**, et
  le disent dans leur docstring.
- **Pas de verdict non mesure.** S'il faut un seuil pour trancher et que ce
  seuil n'a pas ete mesure, rendre la mesure et laisser un humain juger. Une
  mesure honnete vaut mieux qu'un verdict fabrique.

## Tests

- Un module de test par sujet, commencant par `setUpModule()` qui appelle
  `atelier.isoler("<nom>")`. Sans cette ligne, tous les modules partagent une
  base de donnees et un dossier de produits — sans qu'aucun test n'echoue.
- **Un test ne vaut que si on l'a vu echouer.** Apres une correction, remettre
  le defaut et verifier que la suite le remarque : skill `mutation`.
- Le simulateur (`tests/simulateur.py`) remplace le routeur IA. **Aucun test
  ne sort sur le reseau.**
- Attention au cache des reponses IA : deux cas de test qui partagent une
  invite partagent une entree de cache, et le second n'exerce rien.

## Ou regarder

| | |
|---|---|
| `usine/pipelines/catalogue.py` | source unique des types de produits ; la CLI, le menu et le web le lisent |
| `usine/core/llm.py` | routeur multi-fournisseurs : quotas, bascule, cache, repli local |
| `usine/core/config.py` | fournisseurs, modeles, quotas — donnees recopiees, donc perissables |
| `usine/core/controle.py` | controle qualite deterministe, sans appel de modele |
| `usine/core/texte.py` | ce que le modele ajoute et qu'on retire ; refus deguises en reponse |
| `usine/core/modeles.py` | le catalogue vivant d'un fournisseur, et le choix par role |
| `usine/pipelines/carnet.py` | ce qui est deja ecrit, sur le disque : la reprise |
| `usine/pipelines/brief.py` | ce que l'usine decide quand on ne lui dit rien |
| `usine/agents/equipe.py` | les treize agents, la relecture croisee, la deliberation et la lecture en acheteur |
| `usine/core/reglages.py` | les reglages, leurs groupes, et les six peaux du tableau de bord |
| `docs/` | une note par sujet, chacune expliquant un defaut mesure et sa correction |

## Trois regles qui reviennent

Elles ne sont pas nouvelles, mais chaque audit les retrouve, et toujours sous
la meme forme.

**Un garde-fou satisfait par une homonymie ne garde rien.** Chercher un nom
« quelque part dans le code » a laisse passer une fonction sans appelant
(`http.en_ligne`, dont le nom servait ailleurs de parametre) puis deux
reglages orphelins (`plateforme`, `devise`, dont les noms servent partout ou
l'on parle de vente). Un detecteur lit la STRUCTURE — l'arbre syntaxique, ou
au minimum la ligne et son contexte.

**Ne pas croire le code de retour, lire le contenu.** Un fournisseur peut
rendre HTTP 200, `finish_reason: stop`, un `usage` renseigne, et pour tout
contenu « votre cle a epuise son budget ». Tous les signaux disent « reponse
valide ».

**Un reglage par defaut n'est pas neutre, il est juste invisible.** « pro,
douze chapitres, un public motive » donnait la meme voix a un guide de
fiscalite et a un carnet de recettes, sans que rien n'echoue.

## Skills du projet

`.claude/skills/` — chacune encode un enchainement que ce depot refait
regulierement et ou l'on se trompe de la meme facon.

| | |
|---|---|
| `mutation` | remettre le defaut et verifier que la suite le remarque ; outil livre |
| `avant-de-pousser` | rejouer en local les cinq controles de la CI |
| `fournisseurs` | modeles et quotas : la donnee la plus perissable du depot |
| `nouveau-produit` | ajouter une chaine de fabrication, via le catalogue |
| `migration-base` | changer le schema SQLite sans detruire l'atelier d'un utilisateur |
| `rendu` | les moteurs PDF / EPUB ecrits a la main, et pourquoi |
| `controle-qualite` | ajouter une mesure deterministe sans creer de faux positif |
| `termux` | ecrire pour un telephone : processus tue, batterie, binaires absents |

`tests/test_skills.py` verifie que chaque skill dit la verite : entete
lisible, chemins cites existants, fonctions citees reelles. Une skill qui
cite une fonction renommee est un piege — elle n'echoue nulle part, elle fait
perdre une heure a qui la suit.

## Avant de pousser

```bash
python3 -m unittest discover -s tests -t . -q
python3 tests/fumee.py
python3 scripts/dependances.py
```

Le detail et le pourquoi : skill `avant-de-pousser`.
