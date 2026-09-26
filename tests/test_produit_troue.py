"""Un produit livre avec un trou doit le dire.

Mesure du 14/09/2026, faite en coupant le reseau au milieu de chaque chaine :
sept types de produits sur neuf etaient livres marques « pret » alors qu'il
leur manquait une partie. `usine reprendre` repondait « aucun produit
inacheve », et le PDF partait chez l'acheteur avec le plan a la place du
chapitre.

Le garde-fou etait pourtant deja ecrit, et juste : `terminer()` lit
« manquants » et laisse le produit « en_cours » s'il y en a. Mais seules deux
chaines sur neuf prenaient la peine de remplir « manquants ». Le mecanisme
etait bon, c'est son alimentation qui manquait — `terminer()` relit maintenant
le journal d'etapes, pour les dix chaines a la fois.

Trois chaines cachaient en plus le meme defaut, ecrit trois fois de la meme
facon :

```python
except Exception as exc:
    ctx.etape("module-1", "echec", str(exc))   # note l'echec
    corps = plan_de_repli()
ctx.etape("module-1", "ok")                    # ... puis l'efface
```

Le second appel est HORS du « except » : il s'execute toujours, et le dernier
statut gagne. L'echec etait donc note puis immediatement recouvert.
"""

from __future__ import annotations

import ast
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import config, llm, store  # noqa: E402

PIPELINES = sorted((RACINE / "usine" / "pipelines").glob("*.py"))


def setUpModule():
    atelier.isoler("produit-troue")


def _echecs_recouverts(source: str):
    """Les etapes notees en echec puis reecrites « ok » juste apres.

    Lit la STRUCTURE : un « try » dont un gestionnaire note une etape, puis,
    dans le MEME bloc et apres lui, un second appel qui note la meme etape en
    dur. Chercher les deux chaines dans le fichier n'aurait rien prouve —
    elles s'y trouvent legitimement des dizaines de fois.

    Deux precautions, chacune apprise d'une erreur du detecteur lui-meme :

    **Un gestionnaire qui sort ne recouvre rien.** Trois des quatre cas de
    « ebook » finissent par « continue » : la ligne d'apres est inatteignable
    depuis eux. Les compter aurait accuse le seul fichier qui traitait le cas
    correctement — et un garde-fou qui crie a tort finit ignore.

    **Un alias cache le defaut.** Le quatrieme cas de « ebook » notait
    l'echec sous « "chapitre-{}".format(index + 1) » et la reussite sous
    « repere » — deux ecritures du meme nom. Comparees telles quelles, elles
    ne se ressemblent pas, et le defaut passait. Les variables locales
    affectees UNE SEULE fois sont donc remplacees par leur valeur avant
    comparaison. Celles affectees plusieurs fois ne le sont pas : le
    detecteur rate alors un defaut plutot que d'en inventer un.
    """
    trouves = []

    def appel_etape(noeud):
        return (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "etape"
                and noeud.args)

    def statut(noeud):
        if len(noeud.args) > 1 and isinstance(noeud.args[1], ast.Constant):
            return noeud.args[1].value
        for mot in noeud.keywords:
            if mot.arg == "statut" and isinstance(mot.value, ast.Constant):
                return mot.value.value
        return "ok" if len(noeud.args) == 1 else None

    arbre = ast.parse(source)
    alias = _alias_uniques(arbre)

    def nom_de(noeud):
        """Le nom de l'etape, alias resolus."""
        brut = ast.unparse(noeud.args[0])
        return alias.get(brut, brut)

    for corps in _blocs(arbre):
        for rang, noeud in enumerate(corps):
            if not isinstance(noeud, ast.Try):
                continue
            notes = {}
            for handler in noeud.handlers:
                if _sort_du_bloc(handler):
                    continue  # la suite du bloc lui est inatteignable
                for inner in ast.walk(handler):
                    if appel_etape(inner) and statut(inner) == "echec":
                        notes[nom_de(inner)] = inner.lineno
            if not notes:
                continue
            for suivant in corps[rang + 1:]:
                for inner in ast.walk(suivant):
                    if not appel_etape(inner):
                        continue
                    nom = nom_de(inner)
                    if nom in notes and statut(inner) == "ok":
                        trouves.append((nom, notes[nom], inner.lineno))
    return trouves


def _sort_du_bloc(handler) -> bool:
    """Le gestionnaire se termine-t-il par continue, break, return ou raise ?"""
    if not handler.body:
        return False
    return isinstance(handler.body[-1],
                      (ast.Continue, ast.Break, ast.Return, ast.Raise))


def _alias_uniques(arbre):
    """Variables locales affectees une seule fois, et leur expression.

    Une seule affectation : la substitution est sure. Plusieurs, et la valeur
    depend du chemin — on s'abstient.
    """
    comptes, valeurs = {}, {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign) and len(noeud.targets) == 1:
            cible = noeud.targets[0]
            if isinstance(cible, ast.Name):
                comptes[cible.id] = comptes.get(cible.id, 0) + 1
                valeurs[cible.id] = ast.unparse(noeud.value)
    return {nom: valeurs[nom] for nom, n in comptes.items() if n == 1}


def _blocs(arbre):
    """Tous les corps de bloc du module, chacun comme une liste d'instructions."""
    for noeud in ast.walk(arbre):
        for champ in ("body", "orelse", "finalbody"):
            valeur = getattr(noeud, champ, None)
            if isinstance(valeur, list) and valeur:
                yield valeur


class UnEchecNoteNeDoitPasEtreRecouvert(unittest.TestCase):

    def test_aucune_chaine_ne_reecrit_son_echec_en_ok(self):
        for chemin in PIPELINES:
            with self.subTest(chaine=chemin.stem):
                recouverts = _echecs_recouverts(
                    chemin.read_text(encoding="utf-8"))
                self.assertEqual(
                    recouverts, [],
                    "« {} » note un echec puis l'efface : {}".format(
                        chemin.stem,
                        "; ".join("{} (ligne {} puis {})".format(*r)
                                  for r in recouverts)))

    def test_le_detecteur_verrait_le_defaut_d_origine(self):
        """Sans ce cas, le controle ci-dessus pourrait passer parce qu'il ne
        trouve jamais rien, et non parce qu'il n'y a plus rien a trouver."""
        fautif = (
            "def f(ctx, i):\n"
            "    try:\n"
            "        corps = ecrire()\n"
            "    except Exception as exc:\n"
            "        ctx.etape('module-%d' % i, 'echec', str(exc))\n"
            "        corps = repli()\n"
            "    ctx.etape('module-%d' % i, 'ok')\n")
        self.assertTrue(_echecs_recouverts(fautif))

    def test_le_detecteur_laisse_tranquille_la_forme_correcte(self):
        """Un seul appel, apres coup, qui regarde ce qui s'est passe."""
        correct = (
            "def f(ctx, i):\n"
            "    perdu = ''\n"
            "    try:\n"
            "        corps = ecrire()\n"
            "    except Exception as exc:\n"
            "        perdu = str(exc)\n"
            "        corps = repli()\n"
            "    ctx.etape('module-%d' % i, 'echec' if perdu else 'ok', perdu)\n")
        self.assertEqual(_echecs_recouverts(correct), [])

    def test_un_gestionnaire_qui_sort_ne_recouvre_rien(self):
        """Le faux positif d'origine : trois cas de « ebook » finissent par
        « continue », donc la ligne d'apres leur est inatteignable."""
        sortant = (
            "def f(ctx, i):\n"
            "    for c in tout:\n"
            "        try:\n"
            "            corps = ecrire()\n"
            "        except Exception as exc:\n"
            "            ctx.etape('chapitre-%d' % i, 'echec', str(exc))\n"
            "            continue\n"
            "        ctx.etape('chapitre-%d' % i, 'ok')\n")
        self.assertEqual(_echecs_recouverts(sortant), [])

    def test_un_alias_ne_cache_pas_le_defaut(self):
        """Le vrai defaut d'origine : l'echec note sous une expression, la
        reussite sous la variable qui vaut la meme chose."""
        alias = (
            "def f(ctx, i):\n"
            "    repere = 'chapitre-%d' % i\n"
            "    try:\n"
            "        corps = ecrire()\n"
            "    except Exception as exc:\n"
            "        ctx.etape('chapitre-%d' % i, 'echec', str(exc))\n"
            "        corps = repli()\n"
            "    ctx.etape(repere, 'ok')\n")
        self.assertTrue(_echecs_recouverts(alias),
                        "l'alias cache encore le defaut")

    def test_le_detecteur_ne_confond_pas_deux_etapes_differentes(self):
        """Noter l'echec d'une etape puis la reussite d'une AUTRE est normal."""
        voisin = (
            "def f(ctx):\n"
            "    try:\n"
            "        a = ecrire()\n"
            "    except Exception as exc:\n"
            "        ctx.etape('quiz', 'echec', str(exc))\n"
            "    ctx.etape('emails', 'ok')\n")
        self.assertEqual(_echecs_recouverts(voisin), [])


class UneChaineQuiPerdUneEtapeLeDit(unittest.TestCase):
    """La mesure qui a ouvert le sujet, rejouee sur les chaines a boucle.

    Celles qui n'ont pas de boucle meurent franchement quand le reseau tombe —
    elles ne livrent rien, donc elles ne mentent pas. Ce sont celles qui
    CONTINUENT avec un repli qu'il fallait faire parler.
    """

    CHAINES = {"formation": "module-", "prompts": "categorie-",
               "outils": "outil-", "social": "lot-"}

    def _couper_a(self, commande, plafond):
        atelier.isoler("troue-" + commande)
        compte = {"n": 0}

        def coupe(messages, role="standard", **kw):
            compte["n"] += 1
            if compte["n"] > plafond:
                raise OSError("[Errno 101] Network is unreachable")
            return simulateur(messages, role)

        llm.definir_simulateur(coupe)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal([commande,
                               "coupure {} du quatorze".format(commande),
                               "--sans-image", "-q", "rapide"])
        except Exception:
            pass
        finally:
            llm.definir_simulateur(None)
        produits = store.lister_produits(3)
        return produits[0] if produits else None

    def test_un_produit_ampute_n_est_jamais_marque_pret(self):
        for commande, prefixe in sorted(self.CHAINES.items()):
            with self.subTest(chaine=commande):
                produit = self._couper_a(commande, 3)
                self.assertIsNotNone(produit, "rien n'a ete enregistre")
                self.assertEqual(
                    produit["statut"], "en_cours",
                    "« {} » livre un produit troue en le disant pret"
                    .format(commande))
                manquants = (produit.get("meta") or {}).get("manquants") or []
                self.assertTrue(
                    any(str(m).startswith(prefixe) for m in manquants),
                    "« {} » ne nomme pas ce qui manque : {}"
                    .format(commande, manquants))

    def _couper_sur(self, commande, marqueur, extra=None):
        """Fait echouer l'appel qui contient ce marqueur, et lui seul.

        Un compteur mesure la LONGUEUR de la chaine, pas sa solidite : couper
        au sixieme appel n'exercait rien pour les chaines courtes, qui avaient
        deja fini. Viser l'invite nomme exactement l'etape qu'on veut perdre.
        """
        atelier.isoler("troue-cible-" + commande + marqueur[:12])

        def coupe(messages, role="standard", **kw):
            texte = (messages[-1]["content"] if isinstance(messages, list)
                     else str(messages))
            if marqueur in texte:
                raise OSError("[Errno 101] Network is unreachable")
            return simulateur(messages, role)

        llm.definir_simulateur(coupe)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal([commande,
                               "coupure ciblee {} {}".format(commande, marqueur[:10]),
                               "--sans-image", "-q", "rapide"] + (extra or []))
        except Exception:
            pass
        finally:
            llm.definir_simulateur(None)
        produits = store.lister_produits(3)
        return produits[0] if produits else None

    def test_une_etape_facultative_perdue_laisse_le_produit_vendable(self):
        """L'autre moitie de la regle, et la plus facile a oublier : une
        formation sans son quiz reste une formation. La marquer inachevee
        enverrait « usine reprendre » refaire dix modules pour un quiz."""
        produit = self._couper_sur("formation",
                                   "Redige le quiz d'auto-evaluation")
        self.assertIsNotNone(produit)
        self.assertEqual(produit["statut"], "pret",
                         "un quiz manquant ne rend pas la formation invendable")
        meta = produit.get("meta") or {}
        self.assertIn("quiz", meta.get("incomplets") or [],
                      "le quiz perdu n'est dit nulle part : il est perdu "
                      "ET invisible")

    def test_le_guide_perdu_d_un_systeme_de_modeles_est_dit(self):
        """La chaine « modeles » remplace son guide par une liste de puces.
        Elle notait ensuite « ctx.etape(\"guide\") » tout court — c'est-a-dire
        « ok », quoi qu'il soit arrive."""
        produit = self._couper_sur("modeles",
                                   "Redige le guide d'installation")
        self.assertIsNotNone(produit)
        self.assertEqual(produit["statut"], "en_cours")
        self.assertIn("guide", (produit.get("meta") or {}).get("manquants") or [])

    def test_un_controle_qui_trouve_quelque_chose_le_dit_sur_la_fiche(self):
        """Une anomalie de continuite ne vivait que dans le defilement du
        terminal — c'est-a-dire nulle part, sur un telephone."""
        atelier.isoler("troue-anomalie")

        # La panne est provoquee sur la redaction d'une scene precise : c'est
        # ce qui fait diverger le manuscrit, donc ce qui donne au controle de
        # continuite quelque chose a trouver. Sans trou, il ne signale rien —
        # et un test qui passe faute d'avoir rien a voir ne garde rien.
        def coupure(messages, role="standard", **kw):
            texte = (messages[-1]["content"] if isinstance(messages, list)
                     else str(messages))
            if "Ecris la scene 4 " in texte:
                raise llm.PlusDeFournisseur("coupe pendant la redaction")
            return simulateur(messages, role)

        llm.definir_simulateur(coupure)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["roman", "un huis clos dans un phare ancien",
                               "--chapitres", "8", "--sans-image"])
        finally:
            llm.definir_simulateur(None)
        produit = store.lister_produits(3)[0]
        meta = produit.get("meta") or {}
        self.assertIn("continuite", meta.get("anomalies") or [],
                      "le controle de continuite a trouve quelque chose et "
                      "la fiche du produit n'en garde rien")
        self.assertNotIn("continuite",
                         meta.get("manquants") or [],
                         "une anomalie n'est pas une scene a reecrire : "
                         "aucune reecriture ne la corrige")

    def test_une_etape_rattrapee_n_est_plus_un_trou(self):
        """Le dernier statut gagne, et c'est le point.

        Une etape qui echoue puis reussit a la reprise n'est pas un trou.
        Compter n'importe quel echec aurait marque inacheve tout produit
        ayant connu une seule erreur rattrapee — donc, a terme, tous.
        """
        atelier.isoler("troue-rattrape")
        etat = {"coupe": True}

        def intermittent(messages, role="standard", **kw):
            texte = (messages[-1]["content"] if isinstance(messages, list)
                     else str(messages))
            if etat["coupe"] and "Redige le guide d'installation" in texte:
                raise OSError("[Errno 101] Network is unreachable")
            return simulateur(messages, role)

        llm.definir_simulateur(intermittent)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["modeles", "un tableau de suivi de chantier",
                               "--sans-image", "-q", "rapide"])
            abime = store.lister_produits(3)[0]
            self.assertEqual(abime["statut"], "en_cours")
            # Le reseau revient, et l'on refait la MEME etape.
            etat["coupe"] = False
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["reprendre", abime["id"]])
        finally:
            llm.definir_simulateur(None)
        repris = store.lire_produit(abime["id"]) or {}
        self.assertEqual(repris.get("statut"), "pret",
                         "le guide a ete refait et le produit reste inacheve : "
                         "« usine reprendre » ne sert alors a rien")

    def test_une_fabrication_entiere_reste_prete(self):
        """L'autre sens, et il compte autant : un garde-fou qui declare
        inacheve un produit complet rendrait « usine reprendre » inutile a
        force de crier."""
        atelier.isoler("troue-complet")
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["prompts", "un pack entier sans coupure",
                               "--sans-image", "-q", "rapide"])
        finally:
            llm.definir_simulateur(None)
        produit = store.lister_produits(3)[0]
        self.assertEqual(produit["statut"], "pret")
        self.assertFalse((produit.get("meta") or {}).get("manquants"))



class LaLigneDeCommandeNeLeDitPasPret(unittest.TestCase):
    """La fiche disait « inacheve » ; la console, la notification et le code
    de sortie disaient le contraire.

    Mesure du 25/09/2026, sans cle, par le vrai routeur : sept sections sur
    sept non ecrites, et « Produit livre », « Produit pret » sur le
    telephone, code 0. Le tableau de bord et l'usine continue, eux, le
    confiaient deja a la boucle.
    """

    def _fabriquer(self, plafond):
        from unittest import mock

        from usine import cli
        from usine.core import telephone

        compte = {"n": 0}

        def coupe(messages, role="standard", **kw):
            compte["n"] += 1
            if plafond and compte["n"] > plafond:
                raise OSError("[Errno 101] Network is unreachable")
            return simulateur(messages, role)

        notifications = []
        llm.definir_simulateur(coupe)
        sortie = io.StringIO()
        try:
            with mock.patch.object(telephone, "notifier",
                                   lambda titre, *a, **k: notifications.append(titre)), \
                    redirect_stdout(sortie), redirect_stderr(sortie):
                code = cli.principal(["prompts", "une coupure annoncee {}".format(
                    plafond), "--sans-image", "-q", "rapide"])
        finally:
            llm.definir_simulateur(None)
        return code, sortie.getvalue(), notifications

    def test_un_produit_coupe_s_annonce_inacheve(self):
        atelier.isoler("troue-annonce")
        code, texte, notifications = self._fabriquer(3)
        self.assertEqual(store.lister_produits(1)[0]["statut"], "en_cours")
        self.assertEqual(code, 3)
        self.assertIn("Produit inacheve", texte)
        self.assertNotIn("Produit livré", texte)
        self.assertIn("usine reprendre", texte)
        self.assertNotIn("Produit prêt", notifications)

    def test_l_annonce_du_tableau_de_bord_suit_le_statut(self):
        """Le tableau de bord recharge sa liste a l'annonce « produit ». Elle
        partait avant que la fiche soit posee : un livre fini s'y affichait
        « inacheve ». Et seize chaines sur dix-huit ne l'envoyaient pas."""
        from unittest import mock

        from usine.core import evenements

        vus = []
        vrai = evenements.publier

        def espion(genre, **donnees):
            if genre == "produit":
                fiche = store.lister_produits(1)[0]
                vus.append((donnees.get("statut"), fiche["statut"]))
            return vrai(genre, **donnees)

        for plafond, attendu in ((3, "en_cours"), (0, "pret")):
            with self.subTest(coupe=plafond):
                atelier.isoler("troue-evenement-{}".format(plafond))
                vus.clear()
                with mock.patch.object(evenements, "publier", espion):
                    self._fabriquer(plafond)
                self.assertEqual(vus, [(attendu, attendu)])

    def test_un_produit_entier_reste_annonce_pret(self):
        """L'autre sens : sans lui, un « Produit inacheve » fige passerait."""
        atelier.isoler("troue-annonce-complet")
        code, texte, notifications = self._fabriquer(0)
        self.assertEqual(code, 0)
        self.assertIn("Produit livré", texte)
        self.assertIn("Produit prêt", notifications)


class UnProduitTroueNeSePrepareEtreVendu(unittest.TestCase):
    """Le kit de vente et l'archive sortaient aussi pour un produit inacheve.

    Mesure du 24/09/2026 : l'archive destinee a l'acheteur livrait le
    chapitre perdu reduit a son plan — « Point A, Point B, Point C » — et une
    page de vente promettait le livre entier. Le produit etait marque
    inacheve ; le paquet pret a mettre en ligne ne le disait nulle part.
    """

    def test_ni_kit_ni_archive_avant_la_fin_puis_les_deux(self):
        from usine.core import reglages
        from usine.pipelines import porte, reprise

        atelier.isoler("troue-vente")
        reglages.ecrire(dict(images=False, qualite="rapide",
                             marketing_auto=True, archive_auto=True))
        etat = {"panne": True}

        def modele(messages, role="standard", **kw):
            if etat["panne"] and "Redige le chapitre 2 sur" in messages[-1]["content"]:
                raise ValueError("reponse illisible")
            return simulateur(messages, role)

        journal = []
        llm.definir_simulateur(modele)
        try:
            ctx = porte.contexte("la paie des fleuristes", {"chapitres": 5},
                                 journal.append)
            coupe = porte.fabriquer("ebook", ctx, {"chapitres": 5},
                                    journal.append)
            self.assertEqual(store.lire_produit(ctx.produit_id)["statut"],
                             "en_cours")
            self.assertFalse(list(config.PRODUITS_DIR.rglob("*.zip")),
                             "une archive d'acheteur pour un livre troue")
            self.assertFalse(coupe.get("marketing"))
            self.assertTrue(any("pas pour un produit inachevé" in l
                                for l in journal), "le refus doit se dire")
            # Les commandes explicites refusent de meme, et disent comment
            # finir le produit.
            from usine import cli

            for commande in ("livrer", "marketing"):
                sortie = io.StringIO()
                with redirect_stdout(sortie), redirect_stderr(sortie):
                    code = cli.principal([commande, ctx.produit_id])
                with self.subTest(commande=commande):
                    self.assertEqual(code, 1, sortie.getvalue())
                    self.assertIn("usine reprendre " + ctx.produit_id,
                                  sortie.getvalue())
            self.assertFalse(list(config.PRODUITS_DIR.rglob("*.zip")))
            etat["panne"] = False
            fini = reprise.reprendre(ctx.produit_id, journal=journal.append)
        finally:
            llm.definir_simulateur(None)
        self.assertEqual(store.lire_produit(ctx.produit_id)["statut"], "pret")
        self.assertTrue(fini.get("archive"))
        self.assertTrue(fini.get("marketing"))


if __name__ == "__main__":
    unittest.main()
