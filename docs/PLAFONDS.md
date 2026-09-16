# Les plafonds de jetons sont les nôtres, et une coupure n'est pas une erreur

La question posée le 16/09/2026, devant `reponse coupee au plafond (700 jetons)` :

> C'est nous qui avons fixé des limites dans les réponses des agents ? On
> devrait pas plutôt attendre l'erreur du provider pour être sûr du maximum ?

La première moitié est exacte. La seconde ne peut pas marcher, et c'est
instructif.

## Oui, ce sont les nôtres

Une quarantaine de plafonds sont écrits à la main dans le dépôt. Le 700 du
journal vient de `brief.py`, sur la décision des réglages. Une poignée d'appels
seulement dérivent leur plafond de ce qu'ils demandent (`jetons_pour()` à
partir du nombre de mots, `_plafond_reecriture()` à partir de la longueur du
texte). Le reste est un chiffre choisi un jour.

## Mais il n'y a pas d'erreur à attendre

Une réponse coupée au plafond ne lève rien. Le fournisseur rend **HTTP 200**,
un `usage` renseigné, et `finish_reason: "length"`. Tous les signaux disent
« réponse valide ». C'est la deuxième des trois règles de ce dépôt — *ne pas
croire le code de retour, lire le contenu* — et c'est exactement le cas qu'elle
décrit.

Attendre l'erreur ne marche pas mieux dans l'autre sens : demander plus que ce
qu'un fournisseur accepte fait lever un 400 chez certains, et se fait
silencieusement ramener au maximum chez d'autres. Il n'y a pas de limite
découvrable par l'échec.

Et pour les quotas par minute, l'erreur coûte : un 429 **consomme** du quota.
Le dépôt le documente déjà à propos des attentes.

## Ce que fait l'usine à la place

Le bon geste existait déjà, dans `nouvelle._grille_ou_retente`, et son
docstring le formule :

> *Un chiffre choisi à la main finit toujours par être trop petit pour un cas
> qu'on n'avait pas vu. Plutôt que d'en inventer un plus gros et d'espérer, on
> lit le fait que le routeur mesure DÉJÀ — `finish_reason: length` — et on
> redemande.*

Il n'était appelé qu'à **un seul endroit**, sur les quarante appels JSON du
dépôt.

## Le défaut que la généralisation a révélé

`generer_json` faisait pire que rien. Un JSON coupé est illisible, donc il en
concluait que **le fournisseur** ne savait pas tenir un format : il l'écartait,
et recommençait **au même plafond** chez le suivant.

Trois fournisseurs brûlés pour une limite que nous avions posée nous-mêmes.

Désormais, quand le décodage échoue :

- **la réponse était coupée** → la faute est à nous. Le plafond double, le
  fournisseur garde sa chance ;
- **la réponse était complète mais illisible** → la faute est à lui. Le
  traitement d'avant s'applique, il est écarté.

Le plafond ne grandit pas sans fin : il s'arrête au plus large que le catalogue
des fournisseurs déclare accepter (`max(p.max_sortie)`). Monter plus haut ne
produirait pas plus — cela produirait une erreur chez certains et un silence
chez d'autres. Le chiffre est **dérivé** de données déclarées, pas écrit.

## Le second défaut, trouvé en mesurant le premier

En rejouant le journal réel, le compte ne tombait pas juste :

```
L'usine decide 9 reglage(s) : genre, sous_genre, tropes, ambiance...
  sous_genre : roman d'apprentissage créatif
  ... huit valeurs ...
```

Neuf annoncés, huit listés. Le manquant était **`genre`** — le plus structurant
de tous — auquel le modèle avait répondu « drame contemporain », qui n'est pas
dans la liste fermée (`horreur, imaginaire, jeunesse, litterature, policier…`).

La coupure n'y était pour rien. Un filtre écartait la valeur, et se taisait.

Écarter reste juste : accepter « drame contemporain » ferait entrer dans la
fiche une valeur que rien d'autre ne sait relire. C'est le **silence** qui était
le défaut — le roman est parti sans contrat de genre, et il fallait compter les
lignes du journal pour s'en apercevoir. Sur un écran de téléphone, personne ne
compte.

```
  [!] non retenu — genre : « drame contemporain » hors de la liste
      (horreur, imaginaire, jeunesse, litterature, policier)
  1 reglage(s) sur 9 restent a la charge de la chaine.
```

## Ce qui garde la correction

`tests/test_plafonds.py`, sept tests, aucun sur le réseau : le fournisseur
simulé rend un JSON tronqué tant que le plafond demandé est trop bas, ce qui est
la forme exacte du défaut — rien ne lève, le texte revient simplement coupé.

Campagne de mutation : huit mutations, toutes vues.

Un de ces tests a d'abord échoué, et pour la raison que ce dépôt documente :
trois cas partageaient un sujet, donc une entrée de cache, donc le cas « tout
passe » recevait la réponse fautive du cas précédent. Chaque cas a maintenant
son sujet.

---

# Ce qu'un journal de roman a montré le lendemain

Dix-huit scènes, sur un téléphone. Trois défauts de plus, dont un de la pire
famille : celle où tous les signaux disent « valide ».

## Le 7,5 fabriqué — l'éditeur n'a relu aucune scène

```
relecture « L'atelier qui tousse » : 7.5/10, 0 correction(s)
relecture « L'inspection qui tombe » : 7.5/10, 0 correction(s)
... six fois de plus, identiques au dixième près ...
```

Huit scènes, huit notes rigoureusement égales. Ce n'était pas un éditeur
indulgent : c'était la branche d'erreur.

```python
except Exception:
    return Critique(note=7.5, verdict="relecture indisponible")
```

Sa réponse revenait coupée au plafond, donc illisible, donc l'exception. Le
journal affichait alors une note qui n'avait été mesurée sur rien, avec zéro
correction, exactement comme une relecture réussie sans reproche.

Et **7,5 ≥ 7,5** rend la critique `acceptable` — ce qui arrête la boucle
d'amélioration en annonçant que le texte est assez bon. La relecture ratée ne
se contentait pas de mentir : elle empêchait la correction.

`Critique` porte maintenant `mesuree`. Non mesurée n'est pas acceptable — c'est
inconnu. Le résumé le dit, et le rapport qualité ne moyenne plus ce qui n'a pas
été mesuré.

*(Le plafond lui-même est réparé par la correction de la veille : `2600 →
5200`, vérifié — la relecture passe.)*

## Le plafond de 320, coupé dix-huit fois sur dix-huit

La mémoire hiérarchique demande un état **« en 90 mots maximum »**. Quatre-vingt-dix
mots français font environ 234 jetons. Le plafond en laissait **320** — 86 de
marge. Coupé à chaque scène, sans une exception.

`jetons_pour()` existe pour cette conversion et porte déjà la marge :
`jetons_pour(90)` rend 634. L'oublier ici revenait à recopier le calcul de
travers — exactement ce que le docstring de cette fonction raconte avoir déjà
coûté une fois.

## Le service retiré, réinterrogé à chaque bascule

```
github : le service a ete retire par son editeur. [...]
         Retirez-le de usine/core/config.py
```

Le dépôt **savait déjà** : ce message et son commentaire datent du 15/09, et
le journal du 16/09 le montre encore. Pourtant aucun repos n'était posé pour
ce cas. Une clé refusée se repose une heure, un quota une minute, un crédit
épuisé une demi-heure — et le seul échec vraiment définitif du lot était le
seul réinterrogé à chaque bascule, sur chaque scène, indéfiniment.

Vingt-quatre heures, et non « pour toujours » : une fermeture progressive peut
se rouvrir, et l'usine n'a pas à trancher à la place de l'éditeur. Ce qu'elle
peut trancher, c'est qu'un service qui se déclare retiré ne reviendra pas dans
l'heure.

## Ce qui garde ces corrections

`tests/test_journal_roman.py`, dix tests, aucun sur le réseau. Campagne de
mutation : huit mutations, toutes vues.

Deux `[RATE]` au premier tour, tous deux dans mes tests. Le pire était celui-ci :
`Critique(note=0.0, mesuree=False).acceptable` est faux **avec ou sans la
correction**, puisque zéro est déjà sous le seuil. Le test ne mesurait rien. Le
défaut d'origine rendait justement **7,5** — il fallait une note haute pour que
la vérification ait un sens.
