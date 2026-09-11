# L'usine continue

Vous remplissez une file de niches, vous fixez un budget, vous lancez. L'usine
produit en boucle et s'arrête toute seule — sur la fin de la file, sur le
budget, ou sur votre demande.

```bash
usine file --ajouter "la prospection pour freelances" "la gestion du temps"
usine file --ajouter "50 prompts pour community managers" --type prompts -n 50 --priorite 1
usine usine demarrer --budget appels_jour=250 produits_jour=3
```

## La file

Persistée en base, pas en mémoire — et c'est la décision qui compte le plus
sur Android : le système tue les processus en arrière-plan sans préavis. Une
file en mémoire disparaîtrait avec le processus. Ici, relancer reprend
exactement où l'usine s'était arrêtée, et une entrée laissée « en cours » par
une coupure est remise en attente au démarrage suivant.

```bash
usine file                          # voir la file
usine file --ajouter "niche" --type impression --priorite 1
usine file --retirer 3
usine file --rejouer                # remettre les échecs en file
usine file --vider                  # nettoyer les entrées livrées
```

| Comportement | Pourquoi |
|---|---|
| Priorité 1 passe avant priorité 9 | vous décidez de l'ordre, pas l'ordre d'ajout |
| Un doublon en attente est refusé | relancer la même commande ne produit pas deux fois le même livre |
| Un sujet **déjà livré** peut être relancé | refaire un produit est légitime |
| 2 tentatives avant condamnation | une coupure réseau ne doit pas condamner une niche |

## Le budget

C'est lui qui empêche l'usine de vider vos quotas pendant la nuit.

```bash
usine reglages --definir budget_appels_jour=250 budget_appels_produit=80 \
                        budget_produits_jour=4 budget_minutes_produit=45
usine usine demarrer --budget appels_jour=120     # ou à la volée
```

`0` signifie « pas de limite ». Trois niveaux de contrôle :

**Avant chaque produit.** L'usine refuse d'en démarrer un qu'elle ne pourra
pas finir. Entamer un ebook avec 5 appels restants gaspille le budget *et*
laisse un dossier incomplet — mieux vaut s'arrêter proprement et garder la
niche en file.

**Avant chaque appel.** Une garde est consultée par le routeur IA. Une réponse
servie par le cache n'est jamais refusée : elle ne coûte rien.

**Pendant un produit.** Si un plafond tombe au dixième chapitre, **le livre
sort quand même** : les chapitres déjà rédigés sont conservés, les suivants
sont réduits à leur plan, le PDF et l'EPUB sont générés. Perdre neuf chapitres
parce que le dixième a dépassé n'aurait aucun sens. L'usine s'arrête ensuite.

## Piloter

```bash
usine usine statut      # depuis n'importe quel terminal, même pendant la production
usine usine arreter     # termine le produit en cours, puis s'arrête
```

`Ctrl+C` fait la même chose : le produit en cours est terminé et exporté. Un
second `Ctrl+C` coupe immédiatement — le travail non exporté est alors perdu,
mais la niche reste en file.

Un seul processus à la fois : un verrou PID l'empêche. Si Android a tué
l'usine, le verrou est détecté comme orphelin et nettoyé automatiquement au
lancement suivant.

## Le mode automatique

```bash
usine usine demarrer --auto
```

Quand la file se vide, l'usine explore de nouvelles niches à partir des sujets
qui ont donné vos **meilleures notes** — c'est la seule base dont elle dispose,
et elle vaut mieux qu'un tirage au hasard. Sans historique, elle vous le dit et
s'arrête plutôt que d'inventer.

## Sur Termux

Android suspend les applications en arrière-plan. Pour une session longue :

```bash
termux-wake-lock
nohup usine usine demarrer --max 5 > ~/usine.log 2>&1 &
usine usine statut          # suivre depuis un autre onglet
tail -f ~/usine.log
termux-wake-unlock          # une fois terminé
```

Ajoutez aussi Termux aux applications non optimisées :
*Paramètres → Applications → Termux → Batterie → Sans restriction*.

Si l'usine est tuée malgré tout, relancez la même commande : la file reprend,
et le cache restitue ce qui avait déjà été généré sans reconsommer un appel.

## Réglages utiles

| Réglage | Défaut | Effet |
|---|---|---|
| `budget_appels_jour` | 250 | plafond global sur 24 h |
| `budget_appels_produit` | 80 | plafond par produit |
| `budget_produits_jour` | 4 | nombre de produits par jour |
| `budget_minutes_produit` | 45 | durée maximum d'un produit |
| `pause_entre_produits` | 60 | secondes entre deux produits, pour laisser respirer les quotas par minute |

## Depuis le téléphone

Le menu (`usine`, sans argument) expose tout cela sans une seule option à
taper : **Usine continue** → ajouter une niche, voir la file, démarrer,
arrêter, régler le budget.

Le tableau de bord (`usine web`) affiche la file en direct, permet d'ajouter
ou retirer une niche, et de démarrer ou arrêter l'usine depuis le navigateur.
