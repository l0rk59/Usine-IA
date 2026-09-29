"""Couper les fournisseurs en pleine fabrication, pour chaque type du catalogue.

Mesure du 24/09/2026, par le tableau de bord, fournisseurs coupes au tiers puis
aux deux tiers de chaque fabrication : le feuilleton, le recueil et le
livre-jeu sortaient « prets » avec des scenes en moins — six coupes sur six.
« scene indisponible » au journal, et rien sur la fiche. La boucle ne les
reprenait pas, « usine reprendre » n'avait rien a reprendre, et le fichier
partait avec des episodes de deux scenes sur trois.

Un test gardait deja ce defaut, sur une liste ECRITE A LA MAIN de quatre
chaines ; ces trois-la sont arrivees apres elle. Celui-ci lit le catalogue.

AUCUN test de ce module ne sort sur le reseau.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


def setUpModule():
    atelier.isoler("trous-fiction")


from usine.core import config, llm, reglages, store  # noqa: E402
from usine.pipelines import carnet, catalogue, porte, reprise  # noqa: E402
from usine.pipelines import memoire as M  # noqa: E402
from usine.pipelines import nouvelle  # noqa: E402
from usine.pipelines.base import Contexte, Redaction, preparer  # noqa: E402
from usine.pipelines.nouvelle import memoriser  # noqa: E402

REPERES = {"feuilleton": "episode-", "recueil": "recit-",
           "interactive": "section-"}


def _muet(_message):
    return None


class Fournisseurs:
    """Le simulateur, coupe apres N appels, et qui garde les invites vues.

    Il donne a chaque recit sa premisse et une bible a son nom. Le
    simulateur rend le meme fil et la meme bible quoi qu'on lui demande : les
    recits d'un recueil y partageaient leurs invites, et le cache repondait a
    la place du carnet — une reprise qui repayait tout aurait eu l'air de ne
    rien repayer.
    """

    def __init__(self, coupe_apres=None, echec_si="", coupe_des=""):
        self.coupe_apres = coupe_apres
        self.echec_si = echec_si
        self.coupe_des = coupe_des
        self.appels = 0
        self.refuses = 0
        self.reussies = []

    def __call__(self, messages, role):
        self.appels += 1
        invite = messages[-1]["content"]
        if self.coupe_des and self.coupe_des in invite:
            self.coupe_apres = self.appels - 1
        if self.coupe_apres is not None and self.appels > self.coupe_apres:
            self.refuses += 1
            raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
        if self.echec_si and self.echec_si in invite:
            raise ValueError("reponse illisible")
        rendu = simulateur(messages, role)
        idee = re.search(r"IDEE : (.+)", invite)
        if invite.startswith("Concois la bible") and idee:
            bible = json.loads(rendu)
            bible["titre"] = "Bible de " + idee.group(1)
            rendu = json.dumps(bible, ensure_ascii=False)
        if invite.startswith("Concois un RECUEIL"):
            fil = json.loads(rendu)
            for rang, recit in enumerate(fil.get("recits") or [], 1):
                recit["premisse"] = "{} Recit {}.".format(recit.get("premisse", ""),
                                                          rang)
            rendu = json.dumps(fil, ensure_ascii=False)
        self.reussies.append(invite)
        return rendu


class _Cas(unittest.TestCase):

    def setUp(self):
        atelier.isoler("trous-fiction-{}".format(self.id().rsplit(".", 1)[-1]))
        reglages.ecrire(dict(images=False, qualite="rapide"))

    def tearDown(self):
        llm.definir_simulateur(None)

    def _fabriquer(self, genre, sujet, fournisseurs, **options):
        llm.definir_simulateur(fournisseurs)
        store.cache_vider()
        ctx = porte.contexte(sujet, dict(options), _muet)
        try:
            resultat = porte.fabriquer(genre, ctx, dict(options), _muet)
        except llm.PlusDeFournisseur:
            resultat = None
        return ctx, resultat


class AucuneChaineCoupeeNeSeDitPrete(_Cas):

    def test_chaque_type_du_catalogue(self):
        for rang, fiche in enumerate(catalogue.tous(fabricables=True)):
            complet = Fournisseurs()
            self._fabriquer(fiche.cle, "la caisse des artisans {}".format(rang),
                            complet)
            for part in (3, 2):
                seuil = max(2, complet.appels // part)
                coupe = Fournisseurs(coupe_apres=seuil)
                ctx, _ = self._fabriquer(
                    fiche.cle, "la caisse coupee {} {}".format(rang, part), coupe)
                if not coupe.refuses or not ctx.produit_id:
                    continue        # fini avant la coupe, ou rien d'enregistre
                produit = store.lire_produit(ctx.produit_id) or {}
                meta = produit.get("meta") or {}
                with self.subTest(type=fiche.cle, coupe=seuil):
                    self.assertTrue(
                        produit.get("statut") == "en_cours" or meta.get("incomplets"),
                        "« {} » coupe a {} appels sur {} se dit pret".format(
                            fiche.cle, seuil, complet.appels))

    def test_les_trois_chaines_nomment_ce_qui_manque(self):
        """Le cas mesure, et plus que le statut : ce qui manque est NOMME, et
        la boucle apprend que ce sont les fournisseurs qui se sont tus —
        c'est ce qui la fait attendre au lieu de renoncer."""
        for genre, prefixe in sorted(REPERES.items()):
            complet = Fournisseurs()
            self._fabriquer(genre, "le phare des Glenan", complet)
            coupe = Fournisseurs(coupe_apres=complet.appels // 2)
            ctx, resultat = self._fabriquer(genre, "le phare des Glenan coupe",
                                            coupe)
            with self.subTest(type=genre):
                # Une fois les fournisseurs muets, on cesse de demander :
                # chaque appel suivant serait refuse apres ses propres
                # attentes, pour chaque scene restante.
                self.assertEqual(coupe.refuses, 1)
                produit = store.lire_produit(ctx.produit_id) or {}
                manquants = (produit.get("meta") or {}).get("manquants") or []
                self.assertEqual(produit.get("statut"), "en_cours")
                self.assertTrue(manquants)
                self.assertTrue(all(m.startswith(prefixe) for m in manquants),
                                manquants)
                self.assertTrue(resultat["budget_epuise"])


class LaSectionCoupeeEstNommee(_Cas):
    """La section en cours d'ecriture au moment de la coupe est un trou comme
    les autres. Ne nommer que les suivantes laissait sortir « pret » un livre
    coupe sur sa DERNIERE section : il n'y en avait pas de suivante."""

    def setUp(self):
        super().setUp()
        self.ctx = Contexte(sujet="un quai", journal=_muet)
        self.dossier = preparer(self.ctx, "feuilleton", "Un quai")
        self.redaction = Redaction(self.ctx, self.dossier)

    def _lever(self, panne):
        def rediger():
            raise panne
        return rediger

    def _perdues(self):
        return {e["nom"] for e in store.etapes_produit(self.ctx.produit_id)
                if e["statut"] == "echec"}

    def test_un_quota_vide_nomme_la_section_et_arrete_les_demandes(self):
        self.assertIsNone(self.redaction.ecrire(
            "scene-1", "Le quai", self._lever(llm.PlusDeFournisseur("muets"))))
        demandes = []
        self.redaction.ecrire("scene-2", "La gare",
                              lambda: demandes.append(1) or "texte")
        self.assertEqual(self.redaction.manquants, ["scene-1", "scene-2"])
        self.assertEqual(self._perdues(), {"scene-1", "scene-2"})
        self.assertEqual(demandes, [], "la scene 2 a ete demandee pour rien")

    def test_une_reponse_illisible_nomme_la_section_et_continue(self):
        self.redaction.ecrire("scene-1", "Le quai",
                              self._lever(ValueError("illisible")))
        self.assertEqual(self.redaction.ecrire("scene-2", "La gare",
                                               lambda: "texte"), "texte")
        self.assertEqual(self.redaction.manquants, ["scene-1"])
        self.assertFalse(self.redaction.budget_epuise)

    def test_le_carnet_fait_foi_a_la_reprise(self):
        self.redaction.ecrire("scene-1", "Le quai", lambda: "le texte ecrit")
        reprise_ = Redaction(self.ctx, self.dossier)
        self.assertEqual(reprise_.ecrire("scene-1", "Le quai",
                                         self._lever(AssertionError("repaye"))),
                         "le texte ecrit")
        self.assertTrue(reprise_.relue)

    def test_un_recit_coupe_a_sa_bible_est_nomme(self):
        for panne, fournisseurs in (
                ("quota", Fournisseurs(coupe_des="Recit 2.")),
                ("illisible", Fournisseurs(echec_si="Recit 2."))):
            with self.subTest(panne=panne):
                ctx, _ = self._fabriquer("recueil", "les halles " + panne,
                                         fournisseurs)
                manquants = ((store.lire_produit(ctx.produit_id) or {})
                             .get("meta") or {}).get("manquants") or []
                self.assertIn("recit-2", manquants)


    def test_un_recit_deja_ecrit_ne_disparait_pas_au_silence(self):
        """Premiere fabrication : le recit 2 illisible, les autres ecrits. A
        la reprise, les fournisseurs se taisent sur ce meme recit 2. Les
        recits suivants sont au carnet : ils doivent rester dans le livre, et
        seul le recit 2 manquer."""
        ctx, _ = self._fabriquer("recueil", "les dockers du Havre",
                                 Fournisseurs(echec_si="Recit 2."))
        llm.definir_simulateur(Fournisseurs(coupe_des="Recit 2."))
        store.cache_vider()
        fini = reprise.reprendre(ctx.produit_id, journal=_muet)
        manquants = ((store.lire_produit(ctx.produit_id) or {})
                     .get("meta") or {}).get("manquants")
        self.assertEqual(manquants, ["recit-2"])
        self.assertEqual(fini["recits"], len(carnet.plan(ctx.dossier)["chapitres"]) - 1)


class UnRecueilSansRecit(_Cas):

    def test_le_silence_remonte_tel_quel(self):
        """Coupe apres le fil, avant le premier recit : rien a livrer. C'est
        le silence des fournisseurs qui doit remonter — la boucle attend
        alors qu'ils rouvrent — et non « aucun recit n'a pu etre ecrit », que
        la boucle compterait comme une faute de la niche."""
        llm.definir_simulateur(Fournisseurs(coupe_des="Concois la bible"))
        store.cache_vider()
        ctx = porte.contexte("les fanfares du Nord", {}, _muet)
        with self.assertRaises(llm.PlusDeFournisseur):
            porte.fabriquer("recueil", ctx, {}, _muet)
        self.assertTrue(carnet.plan(ctx.dossier),
                        "le fil doit etre au carnet pour la reprise")


class LaRepriseFinitSansRepayer(_Cas):

    # Les invites qui construisent le plan : bible, arc, fil, carte, grille.
    PLAN = ("Concois", "Construis la grille")

    def test_la_reprise_relit_le_carnet(self):
        """Deux choses, et pas « aucune invite ne revient » : le simulateur
        rend le meme texte a toutes les scenes, donc deux scenes differentes
        y produisent parfois la meme invite. Ce qu'on garde est exact : la
        reprise n'ecrit aucune section deja au carnet, et ne redemande rien
        du plan. Le cache est vide a la reprise : ce n'est pas lui qui
        repond a la place du carnet."""
        for genre in sorted(REPERES):
            complet = Fournisseurs()
            self._fabriquer(genre, "la gare de Morlaix", complet)
            premiere = Fournisseurs(coupe_apres=complet.appels // 2)
            ctx, resultat = self._fabriquer(genre, "la gare de Morlaix coupee",
                                            premiere)
            deja = set(carnet.lire(ctx.dossier)["sections"])
            store.cache_vider()
            seconde = Fournisseurs()
            llm.definir_simulateur(seconde)
            notees, resumes = [], []
            noter = carnet.noter_section
            carnet.noter_section = lambda d, cle, *a, **k: (
                notees.append(cle), noter(d, cle, *a, **k))[1]
            # Les resumes DEMANDES, et non ceux que le simulateur a vus : il
            # rend le meme texte a toutes les scenes, et le cache en servait
            # la plupart — une memoire repayee pour chaque scene relue passait
            # alors inapercue. La fermeture d'une partie, dans une memoire
            # hierarchique, est un resume de plus, et legitime.
            resumer = nouvelle.mettre_a_jour_resume

            def compter(ctx_, etat, intitule, *a, **k):
                if not intitule.startswith("Partie "):
                    resumes.append(intitule)
                return resumer(ctx_, etat, intitule, *a, **k)

            nouvelle.mettre_a_jour_resume = compter
            try:
                fini = reprise.reprendre(ctx.produit_id, journal=_muet)
            finally:
                carnet.noter_section = noter
                nouvelle.mettre_a_jour_resume = resumer
            with self.subTest(type=genre):
                self.assertTrue(deja, "rien au carnet : la coupe est trop tot")
                produit = store.lire_produit(ctx.produit_id) or {}
                self.assertEqual(produit.get("statut"), "pret")
                self.assertFalse((produit.get("meta") or {}).get("manquants"))
                self.assertEqual(fini["titre"], resultat["titre"])
                self.assertTrue(notees, "la reprise n'a rien ecrit")
                self.assertEqual(deja & set(notees), set(),
                                 "« {} » reecrit ce qui etait au carnet".format(genre))
                # Une scene relue du carnet ne repaye pas son resume : au plus
                # un resume par section ecrite maintenant.
                self.assertLessEqual(len(resumes), len([c for c in notees
                                                        if "-scene-" in c]))
                plan = {i for i in premiere.reussies if i.startswith(self.PLAN)}
                self.assertEqual(plan & set(seconde.reussies), set(),
                                 "« {} » redemande son plan a la reprise".format(genre))

    def test_le_livre_jeu_garde_sa_carte(self):
        """Une carte redemandee renumerote les sections sous les textes deja
        ecrits : la section 7 du carnet n'est plus celle ou menent les
        choix."""
        complet = Fournisseurs()
        self._fabriquer("interactive", "le labyrinthe de Chartres", complet)
        ctx, _ = self._fabriquer("interactive", "le labyrinthe de Chartres bis",
                                 Fournisseurs(coupe_apres=complet.appels // 2))
        carte = carnet.plan(ctx.dossier)["chapitres"]
        llm.definir_simulateur(Fournisseurs())
        store.cache_vider()
        reprise.reprendre(ctx.produit_id, journal=_muet)
        livree = json.loads((ctx.dossier / "carte.json").read_text(
            encoding="utf-8"))["carte"]
        self.assertEqual([(s["numero"], s["choix"]) for s in livree],
                         [(s["numero"], s["choix"]) for s in carte])


class UnRappelNeSEcritPasSurUneFiche(_Cas):

    def test_le_rappel_attend_l_episode_complet(self):
        """Une scene de l'episode 1 perdue — pas un quota, une reponse
        illisible. Ecrit sur la fiche qui tient sa place, le « Precedemment »
        de l'episode 2 serait reste au carnet apres la reprise, et aurait
        raconte au lecteur un episode qui n'est pas celui qu'il a lu."""
        ctx, resultat = self._fabriquer(
            "feuilleton", "la criee de Douarnenez",
            Fournisseurs(echec_si="Ecris la scene 2 sur"), chapitres=3)
        produit = store.lire_produit(ctx.produit_id) or {}
        manquants = (produit.get("meta") or {}).get("manquants") or []
        self.assertIn("episode-1-scene-2", manquants)
        self.assertIn("episode-2-rappel", manquants)
        self.assertFalse(resultat["budget_epuise"],
                         "une reponse illisible n'est pas un quota")
        llm.definir_simulateur(Fournisseurs())
        store.cache_vider()
        fini = reprise.reprendre(ctx.produit_id, journal=_muet)
        self.assertEqual((store.lire_produit(ctx.produit_id) or {})["statut"],
                         "pret")
        self.assertTrue(fini["recaps"][0]["mots"],
                        "le rappel de l'episode 2 n'a pas ete ecrit a la reprise")


class LaMemoireAvanceQuandElleEchoue(_Cas):

    SCENE = {"titre": "Le quai", "pivot": "Yann rend la cle",
             "objectif": "", "personnages": ["Yann"]}

    def _memoriser(self, panne):
        def simulateur_en_panne(messages, role):
            raise panne

        llm.definir_simulateur(simulateur_en_panne)
        ctx = Contexte(sujet="un quai", journal=_muet)
        # Le dossier n'est pas lu : la memoire ne passe pas par le carnet.
        redaction = Redaction(ctx, config.WORKDIR)
        memoire = M.choisir(4, 90)
        memoriser(memoire, redaction, ctx, self.SCENE, "Le texte de la scene.",
                  0, 4)
        return memoire, redaction

    def test_une_memoire_perdue_avance_sur_la_fiche(self):
        """Le feuilleton avalait cet echec par un « pass » : la memoire
        restait en arriere d'une scene, sans rien pour la faire avancer."""
        memoire, redaction = self._memoriser(ValueError("illisible"))
        self.assertIn("Yann rend la cle", memoire.etat_courant())
        self.assertFalse(redaction.budget_epuise)

    def test_un_quota_vide_arrete_les_demandes(self):
        memoire, redaction = self._memoriser(
            llm.PlusDeFournisseur("Tous les fournisseurs ont echoue"))
        self.assertIn("Yann rend la cle", memoire.etat_courant())
        self.assertTrue(redaction.budget_epuise,
                        "la scene suivante serait demandee pour rien")


if __name__ == "__main__":
    unittest.main()
