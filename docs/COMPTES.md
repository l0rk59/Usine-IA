# La couverture annonçait sept prompts, le pack en contenait douze

## Le défaut

Mesure du 15/09/2026, en fabriquant un pack de prompts et en **comptant ce
qu'il contient** :

| | |
|---|---|
| titre annoncé | *7 prompts pour l'écriture de fiches produit* |
| pack livré | 12 prompts |

Le titre était fixé à la ligne qui suit le plan :

```python
categories = _categories(ctx, nombre)
titre = "{} prompts pour {}".format(nombre, ctx.sujet.lower())
```

`nombre`, c'est ce qu'on a **demandé** — avant qu'un seul prompt ne soit
rédigé. Le nombre réellement livré était calculé soixante lignes plus bas,
pour le résumé, et personne ne confrontait les deux.

Deux chaînes du dépôt se nomment par un chiffre : le pack de prompts et le
calendrier éditorial (`30 posts LinkedIn — …`). Les deux avaient le défaut.
Partout ailleurs le titre vient d'un `len(...)` déjà mesuré — `3 nouvelles`,
`8 sections, 2 fins`, `21 repère(s) en 7 bloc(s)`.

## Pourquoi douze, et pourquoi c'est pire que le chiffre

La rédaction publiait **tout ce que le modèle rendait**. Le plan avait prévu
deux prompts pour la catégorie « Stratégie » ; la réponse en contenait six.
Les quatre en trop étaient des morceaux de la consigne elle-même, promus au
rang de produit vendu :

```markdown
## titre' : l'intitulé, reformulé pour être vendeur et clair.

**Quand l'utiliser :** Au démarrage d'un projet.
```

L'acheteur payait donc pour quatre fragments du prompt système, présentés
comme des prompts professionnels, dans un pack dont la couverture annonçait
un compte faux.

## La correction

**Le plan est le contrat.** `_rediger_lot` ne retient plus que le nombre de
prompts que le plan a demandés pour cette catégorie.

On coupe sur le **nombre** et non sur les intitulés : la consigne demande
précisément de reformuler le titre (« l'intitulé, reformulé pour être vendeur
et clair »), donc comparer les libellés écarterait les bonnes reformulations
en même temps que les mauvaises. Un garde-fou qui crie à tort finit ignoré.

**Le titre compte ce qui est écrit.** Il est construit à partir du plan, puis
recalculé après la rédaction si le compte a bougé. Le dossier, lui, garde son
nom : il est créé avant la rédaction — il le faut, `usine reprendre` s'appuie
dessus — et le renommer casserait une reprise en cours. C'est le titre **vu**
par l'acheteur et par le tableau de bord qu'on remet d'aplomb, via
`base.renommer()`.

**Un plan court est signalé.** `ctx.etape(…, "anomalie")` plutôt que
`"echec"` : le pack *est* complet — chaque prompt planifié est rédigé — c'est
la commande qui n'est pas honorée. `"en_cours"` aurait fait croire à une
reprise possible ; le silence aurait laissé la différence dans le défilement
du terminal, c'est-à-dire nulle part sur un téléphone.

Aucun seuil : les deux nombres sont rendus, un humain juge si quatre prompts
sur cinquante valent d'être vendus. Et on signale le **manque**, pas l'écart —
un plan qui rend cinquante-deux prompts pour cinquante n'a lésé personne.

## Ce qui garde la correction

`tests/test_compte_annonce.py`, treize tests. Campagne de mutation : onze
mutations.

La première campagne en a laissé passer **trois**, toutes sur la même branche
— la correction du titre *après* rédaction. Aucun test ne l'atteignait : avec
le plafond, le plan et le total sont toujours égaux, et la branche ne
s'exécutait jamais. Pour écrire moins que le plan il faut que le modèle rende
des entrées **sans champ `prompt`** ; ce cas n'existait dans aucun test. On
pouvait donc supprimer d'un coup la correction du titre, sa remise à jour en
base et son passage aux fichiers livrés sans qu'un seul test bronche.

Trois corrections que rien ne gardait, dans un module de neuf tests verts.

## Le balayage qui a suivi

Les dix-huit types ont été refabriqués, et tout nombre lisible sur le titre ou
le sous-titre du markdown livré confronté à ce que la chaîne déclare avoir
produit :

```
interactive  8 sections, 2 fins      → sections 8, fins 2
recueil      3 nouvelles             → recits 3
feuilleton   3 episodes              → episodes 3
conte        6 doubles-pages         → pages 6
social       7 posts                 → posts 7
emails       7 messages              → messages 7
memo         21 repere(s), 7 bloc(s) → entrees 21, blocs 7
quiz         7 questions             → questions 7
prompts      4 prompts               → prompts 4   (corrigé)
```

Deux nombres qui ne sont pas des comptes et qu'il ne faut pas confondre avec
eux : le `en 30 jours` d'une mini-formation est la **promesse** écrite par le
modèle, et le `un tous les 7 jour(s)` d'une séquence e-mail est un
**intervalle**. Un détecteur qui les compterait crierait à tort sur deux
chaînes saines.
