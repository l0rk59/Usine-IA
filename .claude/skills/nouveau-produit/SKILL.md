---
name: nouveau-produit
description: Ajouter un nouveau type de produit fabricable a l'usine (une chaine de production complete, de l'invite au fichier livre). A utiliser des que quelqu'un propose de fabriquer un genre de produit que l'usine ne sait pas encore faire — un nouveau format de livre, un type de document, un pack a vendre — ou demande « est-ce qu'on pourrait aussi produire des ... ». A utiliser aussi pour comprendre pourquoi un type existant n'apparait pas dans le menu, la CLI ou le tableau de bord : la reponse est presque toujours le catalogue.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Ajouter une chaine de production

## Le catalogue est la source unique

`usine/pipelines/catalogue.py` declare les types de produits **une fois**. La
CLI, le menu Termux, le moteur continu, le serveur web, son gabarit HTML et
l'explorateur de niches le lisent ; aucun ne tient sa propre liste.

Cette regle vient d'un defaut concret : la liste avait ete recopiee dans sept
fichiers, deux avaient diverge, et l'etude de niche ne pouvait plus proposer
`impression` ni `modeles` — les deux types les plus vendus. Les idees
correspondantes etaient silencieusement converties en ebooks.

Donc : **ecrire la chaine, l'inscrire au catalogue, et ne toucher a rien
d'autre.** Si un ajout oblige a modifier la CLI ou le menu, c'est le signe
qu'on est en train de recreer une liste parallele.

## D'abord : est-ce un vrai type ?

Un vrai type a **une chaine de fabrication qui lui est propre**. Un type qui
produirait le meme fichier qu'un autre sous un nom different n'en est pas un —
c'est une etiquette, et elle appartient au sujet, pas au catalogue.

Le test : si la chaine se resume a appeler `ebook.produire()` avec un ton
different, ce n'est pas un type. Un reglage suffit.

## Les quatre etapes

**1. La chaine** — `usine/pipelines/<nom>.py`, exposant
`produire(ctx: Contexte) -> Dict[str, Any]`.

Regarder `pipelines/ebook.py` pour le cas general et `pipelines/nouvelle.py`
pour un cas ou la chaine ajoute ses propres controles. Points communs :

- `preparer(ctx, "<cle>", titre)` cree le dossier de sortie ;
- `ctx.journal(...)` parle a l'utilisateur, `ctx.etape(...)` alimente la base ;
- `jetons_pour(mots)` calcule le plafond de jetons — ne pas le figer ;
- l'export passe par `render/document.py` et `packaging/livraison.py` ;
- toute degradation (budget atteint, modele indisponible) doit **produire
  quand meme**, en moins bien, et le dire. Un chapitre qui echoue n'arrete pas
  le livre : il est remplace par son plan detaille.

**2. L'inscription** — une entree `TypeProduit` dans `catalogue.py` :

```python
TypeProduit(
    cle="nouvelle", nom="Nouvelle (fiction)",
    resume="Une histoire courte, avec bible et continuite tenue",
    detail="PDF + EPUB + HTML + Markdown + couverture",
    formats=("pdf", "epub", "html", "md", "txt"),
    minutes=(12, 30),
    # Volontairement etroits : « nouvelle » designe aussi bien un recit
    # qu'une nouvelle methode. Un mot-cle trop large enverrait des guides
    # a la fiction.
    mots_cles=("fiction", "recit", "roman", "conte", "intrigue"),
),
```

Les champs qui se decident vraiment :

| Champ | Ce qu'il commande |
|---|---|
| `mots_cles` | ce que l'explorateur de niches enverra ici. Trop large = des produits mal aiguilles |
| `vendable` | `False` pour un outil d'analyse : il sort du kit de vente |
| `file` | `False` s'il n'a pas de sens dans la file de production continue |
| `extrait` | `False` quand « les deux premiers chapitres » ne veut rien dire — un logiciel se juge en marchant, pas en se goutant |
| `quantite` | `(argument, question, defaut)` si l'utilisateur doit choisir un nombre |

**3. Les tests** — `tests/test_<nom>.py`, commencant par :

```python
def setUpModule():
    atelier.isoler("<nom>")
```

Cette ligne n'est pas decorative. `config` resout ses chemins au premier
import, et `unittest discover` importe tous les modules avant d'en executer
un : sans `setUpModule`, le premier gagne pour toute la suite et les modules
partagent une base. Rien n'echoue — c'est ce qui rend le defaut durable.

Les tests du catalogue verifient ensuite d'eux-memes que chaque type a une
chaine, des champs remplis, des mots-cles sans accent, et qu'il produit
vraiment les formats qu'il annonce.

**4. La documentation** — `docs/TYPES-PRODUITS.md`, et une ligne dans
`README.md` si le type change ce que l'usine sait faire. Dire ce que
l'acheteur recoit, pas comment le code est organise.

## Verifier

```bash
python3 -m unittest tests.test_catalogue tests.test_<nom> -q
python3 tests/fumee.py     # exerce toutes les chaines via la vraie CLI
```

Le test de fumee est celui qui compte : il passe par la CLI reelle, avec le
simulateur a la place du routeur, et fabrique le produit de bout en bout. Une
chaine qui marche en test unitaire et casse en fumee a un probleme de cablage,
presque toujours dans le catalogue.
