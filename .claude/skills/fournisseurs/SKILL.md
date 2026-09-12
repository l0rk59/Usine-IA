---
name: fournisseurs
description: Verifier et mettre a jour les identifiants de modeles et les quotas gratuits des fournisseurs IA dans usine/core/config.py. A utiliser quand un fournisseur repond 404 ou 429 sans raison apparente, quand la production est brusquement plus lente, quand on ajoute un fournisseur, quand on veut savoir si un modele configure existe encore, ou apres quelques semaines sans avoir produit. A utiliser aussi des que le mot « quota », « rate limit », « modele deprecie » ou « le routeur ne prend plus tel fournisseur » apparait : c'est presque toujours une donnee recopiee qui a pourri.
allowed-tools: Bash, Read, Edit, WebFetch, WebSearch, Grep
---

# Les fournisseurs pourrissent en silence

Les identifiants de modeles et les quotas gratuits sont recopies d'un service
tiers. Ils changent sans annonce, et leur changement ne produit aucune erreur
visible : un modele retire fait repondre 404, le routeur met le fournisseur au
repos une demi-heure et passe au suivant — exactement ce qu'il ferait pour une
panne passagere.

C'est arrive. Groq a retire ses deux modeles Llama du palier gratuit le
16 aout 2026 ; l'usine a continue de les demander pendant trois semaines. Rien
ne l'a dit : ni erreur, ni alerte, ni ligne dans `usine docteur`. Seulement des
produits fabriques plus lentement, par des services moins bons.

## Par ou commencer

```bash
python3 .claude/skills/fournisseurs/scripts/etat.py
```

Affiche, fournisseur par fournisseur : les modeles configures par role, le
quota qui s'y applique, sa portee, et **les pages qui font foi**. Utiliser ces
pages-la — les tableaux de quotas bougent sans annonce, et les blogs
d'agregateurs recopient des chiffres perimes avec aplomb.

Puis, pour les identifiants uniquement :

```bash
python3 -m usine.cli docteur --modeles
```

Interroge le `/models` de chaque fournisseur et compare au configure. Le
rapport distingue trois etats — confirme, disparu, **non verifie**. Ce
troisieme etat compte autant que les autres : une liste d'ecarts vide parce
que personne n'a pu etre interroge ne veut pas dire que tout va bien.

## Corriger

Tout est dans `usine/core/config.py`, dans la liste `PROVIDERS`.

- **Un identifiant de modele** se remplace dans `models`. Un commentaire dit
  ce qui a ete retire et quand : le prochain lecteur saura que ce n'etait pas
  un choix esthetique.
- **Un quota** s'ecrit dans `rpm`/`rpd` quand il vaut pour tout le service,
  ou dans `quotas` — un `Quota` par identifiant de modele — quand le
  fournisseur compte par modele. C'est le cas de Google : `flash` et
  `flash-lite` ont chacun le sien, et `portee="modele"` le dit au routeur.
- **Un plafond en jetons** (`tpm`, `tpd`) est souvent celui qui s'epuise le
  premier. Groq accorde mille requetes par jour et deux cent mille jetons,
  soit environ un livre. Le laisser a zero ne signifie pas « pas de limite »
  mais « non publie par le fournisseur ».

Les tests refusent qu'un identifiant connu pour avoir ete retire revienne :
`MODELES_RETIRES` dans `tests/test_routeur.py`. Y ajouter ceux qu'on retire.

## Deux regles apprises a nos depens

**Prendre le chiffre le plus bas quand les sources divergent.** Google ne
publie plus ses quotas gratuits en clair — la page renvoie vers AI Studio,
derriere une authentification — et les sources secondaires se contredisent.
Sous-estimer coute une attente ; surestimer coute un 429, qui lui consomme du
quota.

**Dater la verification dans le commentaire.** Personne ne peut deviner si un
chiffre a ete lu la semaine derniere ou il y a deux ans. La date est la seule
chose qui rende la donnee jugeable plus tard.

## Ce que le routeur en fait

Utile a savoir avant de toucher un chiffre, parce que le comportement change :

- `_quota_ok` ecarte le fournisseur pour la journee quand `rpd` ou `tpd` est
  atteint ;
- `_attente` fait patienter sous `rpm` et `tpm`, en fenetre glissante ;
- `_attente` rend `None` — « ce fournisseur ne peut pas servir cette
  demande » — quand la demande pese a elle seule plus que le budget d'une
  minute. Le routeur passe alors au suivant sans appeler. C'est ce qui evite
  d'envoyer une demande de chapitre de onze mille jetons a un service qui en
  accorde huit mille par minute.

Apres toute modification : `python3 -m unittest tests.test_routeur -q`.
