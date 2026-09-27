# Quand une API échoue

## Ce qui existait

Mesure du 15/09/2026, en injectant une panne à la place du réseau et en
comptant les tentatives.

**Le routeur IA était la partie solide** — mais avec un angle mort :

| panne injectée | tentatives | attente |
|---|---|---|
| HTTP 503 / 500 | 2 par fournisseur, puis bascule | ~6 s |
| HTTP 0 (réseau coupé) | 2 par fournisseur, puis bascule | ~6 s |
| HTTP 429 | 1, puis mise au repos selon `Retry-After` | — |
| HTTP 404 | 1, puis substitution du modèle | — |
| **`ValueError` — réponse illisible** | **1** | **0 s** |
| **`TimeoutError`, `ConnectionResetError`** | **1** | **0 s** |
| **`JSONDecodeError` — JSON tronqué** | **1** | **0 s** |

Une `HttpErreur` temporaire valait deux essais et six secondes ; une réponse
qu'on n'avait pas su **lire** valait un essai et zéro seconde, et le
fournisseur était abandonné. Du point de vue de l'usine, ce sont pourtant les
deux mêmes pannes : le service n'a rien donné d'exploitable.

**Tout le reste du réseau n'avait aucun réessai :**

| chemin | avant | après |
|---|---|---|
| `images.generer_visuel` | 1 tentative, 0 s | 3 tentatives, ~5 s |
| `images.generer_couverture` | 1, puis repli local | 3, puis repli local |
| `marche.sonder` | 1 par source | 2 par source |
| `modeles.catalogue` | 1 | 2 |
| `maj` (téléchargement) | 1 | 3 |
| `veille` | 1 réessai réfléchi | inchangé |

Une coupure d'une seconde sur un forfait mobile perdait donc une illustration
pour de bon, et le journal annonçait « 0 image(s) sur 14 » sans dire pourquoi.

`veille` avait déjà un réessai, avec un commentaire expliquant pourquoi un
seul. Il n'a pas été touché.

## Un point unique : `http.insister`

**Ce qui est rejoué** : une `HttpErreur` temporaire (429, 5xx, et le statut 0
qui signifie « le réseau n'a pas répondu »), et **toute autre exception** —
parce qu'en pratique c'est une réponse qu'on n'a pas su lire. Le coût d'un
essai inutile est un appel ; le coût de ne pas réessayer est une illustration
perdue.

**Ce qui n'est pas rejoué** : une `HttpErreur` définitive. Une clé refusée
(401), un accès interdit (403), un modèle qui n'existe pas (404), un crédit
épuisé (402) ne changeront pas d'avis en deux secondes.

**`Retry-After` prime sur le calcul.** Quand le service dit lui-même combien
de temps attendre, deviner à sa place revient soit à patienter dix minutes
pour cinq secondes, soit à revenir trop tôt et reprendre un 429 — qui, lui,
consomme du quota.

**Trois essais, pas dix.** Sur un téléphone, une panne qui dure plus de
quelques secondes dure en général des minutes : le forfait est coupé, le
Wi-Fi a sauté, le service est en panne. Insister dix fois vide la batterie
pour arriver au même résultat, plus tard — et la bascule de fournisseur du
routeur, elle, répond en une seconde.

## L'attente reste interruptible

Un `time.sleep(20)` d'un seul bloc fait attendre vingt secondes à un Ctrl+C.
L'utilisateur tue alors le processus à la main, en laissant la base dans
l'état qu'on imagine. C'est la règle du skill `termux`, et elle a fait
découvrir un troisième trou : `_laisser_passer`, le respect du budget par
minute, pouvait dormir **jusqu'à soixante-deux secondes d'un bloc**. C'était
la plus longue attente de l'usine.

`http.patienter` et `llm._patienter` dorment par tranches d'une seconde.

## Ce que les réessais ont révélé

`test_equipe` est passé de 2,6 à 30,8 secondes. Pas une régression : la
**preuve** qu'un test sortait sur le réseau — cinq services publics réels,
`hn.algolia.com`, `fr.wikipedia.org`, `api.stackexchange.com`,
`openlibrary.org`, `www.reddit.com`, à chaque exécution de la suite.

Personne ne l'avait vu parce que l'échec coûtait zéro seconde : sans réseau,
les cinq appels rataient instantanément et le test passait quand même, en
exerçant un chemin dégradé qu'il ne prétendait pas tester.

`tests/atelier.py` refuse désormais tout appel sortant, à la dernière porte
(`urlopen`) et non à `http.requete` — un module qui appellerait `urllib`
directement passerait à côté d'un contrôle posé plus haut. La boucle locale
reste autorisée : les tests du tableau de bord parlent à leur propre serveur,
et les refuser ferait crier le garde-fou sur quarante tests légitimes.

La suite est passée de 108 à 80 secondes.

## Une panne passagère ne doit pas arrêter un produit

*Mesuré le 27/09/2026, première fabrication avec un vrai modèle, sans clé.*

Pollinations a répondu « 502, réponse vide » pendant au moins sept minutes
(de 14 h 45 à 14 h 52). Le routeur faisait deux essais à trois secondes
d'intervalle, puis abandonnait : trois produits sur quatre (quiz, cartes, mots
mêlés) se sont arrêtés au premier appel de rédaction. Le même appel passait
dix minutes plus tard. Sans clé, Pollinations est le seul fournisseur : c'est
le premier contact d'un utilisateur avec l'usine sur son téléphone.

Quand au moins un fournisseur **distant** a échoué d'une façon qui passe seule
(5xx, réseau coupé, réponse illisible) et que personne n'a répondu, le routeur
attend puis refait un tour complet, en repartant des fournisseurs d'origine —
pas du seul repli d'une relecture croisée. Quatre paliers, 30, 60, 90 et
120 secondes, cinq minutes au plus ; au-delà, le carnet garde ce qui est écrit
pour `usine reprendre`. Chaque attente se dit : dans le journal du tableau de
bord, et désormais aussi dans le terminal, qui restait muet pendant les
attentes du routeur — jusqu'à deux minutes, sur un téléphone où l'on tue un
processus muet.

Ce qui n'attend pas : un refus définitif (clé refusée, crédit épuisé, limite de
débit, qui a son propre repos) et un serveur **local**, qui dépend de
l'utilisateur et ne se réparera pas seul.

Dans les tests, l'isolation coupe ces paliers comme elle coupe le réseau :
treize tests simulent une panne, et la suite passait de deux minutes à douze.
Ceux de la patience les remettent eux-mêmes (`tests/test_reessais.py`, neuf
mutations vues).
