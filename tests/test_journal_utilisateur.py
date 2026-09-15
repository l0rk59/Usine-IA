"""Trois defauts lus dans le journal d'une vraie fabrication.

Le 15/09/2026, une nouvelle de cinq scenes est sortie avec UNE scene ecrite
sur cinq et une note de 4,33. Le journal de cette fabrication disait tout ce
qu'il fallait, a condition de le lire dans le bon ordre — et les trois causes
etaient a deux etapes de l'endroit ou le defaut se voyait.

C'est la raison d'etre de ce module : garder ces trois-la, nommees par ce que
le journal montrait.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("journal_utilisateur")


from usine.core import config, llm, modeles  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402


class UneSubstitutionNeSeGardePasSurUnMensonge(unittest.TestCase):
    """« writer/palmyra-creative-122b » etait dans le catalogue de NVIDIA.

    Le journal disait « le modele n'existe plus chez nvidia » et l'usine est
    passee a « meta/muse-glimmer-30b ». Or le catalogue public de NVIDIA,
    relu le lendemain, servait bien ce modele — parmi 81. Le 404 disait donc
    autre chose : un palier qui n'y donne pas droit, une panne d'un instant,
    un routage interne.

    La substitution, elle, etait RETENUE — ecrite en base, valable pour
    toutes les sessions suivantes. Ce modele existe exactement pour ecrire de
    la fiction : toutes les nouvelles suivantes auraient ete ecrites par un
    modele plus petit, definitivement, sans que rien ne le dise.
    """

    # Le modele refuse est celui reellement configure pour « creatif » : c'est
    # la contradiction du fournisseur qu'on teste. Les deux autres sont
    # neutres — recopier de vrais identifiants ferait casser ce module le
    # jour ou la configuration les rattrape, ce qui est deja arrive.
    CATALOGUE: list = []

    @classmethod
    def setUpClass(cls):
        configure = config.PROVIDERS_BY_NAME["nvidia"].model_for("creatif")
        cls.CATALOGUE = [configure, "atelier/autre-un", "atelier/autre-deux"]

    def setUp(self):
        modeles.oublier()
        self.vrai = modeles.interroger
        modeles.interroger = lambda f, timeout=10: list(self.CATALOGUE)
        self.addCleanup(lambda: setattr(modeles, "interroger", self.vrai))

    def test_un_modele_encore_liste_ne_fige_pas_la_substitution(self):
        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        refuse = fournisseur.model_for("creatif")
        remplacant = modeles.substituer(fournisseur, "creatif", refuse)
        self.assertTrue(remplacant, "la fabrication en cours doit aboutir")
        self.assertNotEqual(remplacant, refuse)
        # Rien en base : la session suivante redemandera le modele configure.
        modeles.oublier_la_session()
        self.assertEqual(modeles.modele_effectif(fournisseur, "creatif"),
                         fournisseur.model_for("creatif"))

    def test_un_modele_vraiment_disparu_reste_remplace(self):
        """L'autre moitie : quand le catalogue ne le sert plus, la
        substitution doit survivre au redemarrage, sinon chaque lancement
        refait le meme 404 et la meme interrogation."""
        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        # Un catalogue qui ne sert PLUS le modele configure : sans cela,
        # « choisir » le reprenait, le remplacant valait le modele de depart,
        # et le cas ne distinguait plus rien.
        modeles.interroger = lambda f, timeout=10: [
            "atelier/remplacant-un", "atelier/remplacant-deux"]
        remplacant = modeles.substituer(fournisseur, "creatif",
                                        "writer/modele-retire-l-an-dernier")
        self.assertTrue(remplacant)
        # Sans cette ligne, le test passait des DEUX cotes de la mutation :
        # le remplacant choisi se trouvait etre le modele deja configure, et
        # l'egalite d'apres tenait sans qu'aucune substitution ne soit gardee.
        self.assertNotEqual(remplacant, fournisseur.model_for("creatif"),
                            "ce cas ne prouve rien si le remplacant est "
                            "deja le modele configure")
        modeles.oublier_la_session()
        self.assertEqual(modeles.modele_effectif(fournisseur, "creatif"),
                         remplacant)


class UnServiceRetireSeNommeAinsi(unittest.TestCase):
    """GitHub Models rendait « HTTP 410 : Gone ».

    Le corps disait « github_models_retirement_brownout » : le service est en
    cours de retrait. Le message brut donnait a chercher une cle ou un
    identifiant de modele, alors qu'il n'y avait rien a corriger.
    """

    def test_un_410_distant_dit_que_le_service_ferme(self):
        github = config.PROVIDERS_BY_NAME["github"]
        texte = llm._expliquer(github, HttpErreur(
            410, "Gone",
            corps='{"error":{"code":"github_models_retirement_brownout"}}'))
        self.assertIn("retire par son editeur", texte)
        self.assertIn("ni votre cle", texte)

    def test_un_410_sans_explication_suffit(self):
        """Tous les services retires ne le disent pas dans leur corps.

        Le premier cas de ce module portait « retirement » dans le corps, ce
        qui rattrapait la lecture du code : retirer la branche du 410 ne
        changeait rien, et la mutation l'a montre. Un « Gone » nu est la
        forme minimale, et c'est elle qu'il faut garder.
        """
        self.assertTrue(llm._service_ferme(HttpErreur(410, "Gone")))

    def test_un_service_retire_n_est_pas_un_modele_inconnu(self):
        """Les deux demandent des gestes opposes : corriger un identifiant,
        ou cesser de compter sur le service."""
        exc = HttpErreur(410, "Gone", corps="retirement brownout")
        self.assertTrue(llm._service_ferme(exc))
        self.assertFalse(llm._modele_inconnu(exc))

    def test_une_panne_ordinaire_n_est_pas_un_retrait(self):
        """Sinon l'usine dirait « ce service ferme » a chaque 503."""
        for statut in (500, 502, 503, 429, 404):
            self.assertFalse(
                llm._service_ferme(HttpErreur(statut, "panne")),
                "un {} ne doit pas passer pour un retrait".format(statut))


class UneGrilleCoupeeEstRedemandee(unittest.TestCase):
    """Cinq scenes, 2250 jetons accordes, reponse coupee.

    Le JSON tronque se relit en partie, donc rien n'echouait : la grille
    perdait ses derniers beats, et le controle de continuite signalait deux
    etapes plus loin « aucune scene ne livre le beat resolution ». La cause
    etait loin de l'endroit ou le defaut se voyait.
    """

    def test_le_plancher_couvre_le_cas_qui_a_echoue(self):
        from usine.pipelines import nouvelle

        source = (RACINE / "usine" / "pipelines" / "nouvelle.py").read_text(
            encoding="utf-8")
        self.assertIn("2600 + total * 150", source,
                      "le plancher est revenu sous le cas mesure")
        # Cinq scenes : 3350 jetons, la ou 2250 avait ete coupe.
        self.assertGreater(2600 + 5 * 150, 2250)
        self.assertTrue(hasattr(nouvelle, "_grille_ou_retente"))

    def test_une_grille_coupee_est_redemandee_plus_grande(self):
        """Un chiffre choisi a la main finit toujours par etre trop petit
        pour un cas qu'on n'avait pas vu. Le routeur MESURE deja la coupe."""
        from usine.pipelines import nouvelle

        class FauxContexte:
            def __init__(self):
                self.meta = {}
                self.lignes = []

            def journal(self, message):
                self.lignes.append(message)

        ctx = FauxContexte()
        budgets = []

        def repondre(_contexte, _invite, max_tokens=0, **_reste):
            budgets.append(max_tokens)
            if len(budgets) == 1:
                # Le routeur note la coupe comme il le fait en vrai.
                ctx.meta.setdefault("tronquees", []).append({"agent": "architecte"})
                return {"scenes": [{"titre": "coupee"}]}
            return {"scenes": [{"titre": "a"}, {"titre": "b"}], "beats": [1]}

        with mock.patch.object(nouvelle.equipe.SCENARISTE, "travailler_json",
                               side_effect=repondre):
            grille = nouvelle._grille_ou_retente(ctx, "invite", 2250)
        self.assertEqual(budgets, [2250, 4500], "la relance doit doubler")
        self.assertEqual(len(grille["scenes"]), 2, "la seconde grille gagne")
        self.assertTrue(any("redemande" in l for l in ctx.lignes),
                        "la relance doit se dire dans le journal")

    def test_une_grille_entiere_ne_coute_pas_un_second_appel(self):
        from usine.pipelines import nouvelle

        class FauxContexte:
            meta = {}

            def journal(self, message):
                pass

        appels = []

        def repondre(_contexte, _invite, max_tokens=0, **_reste):
            appels.append(max_tokens)
            return {"scenes": [{"titre": "a"}]}

        with mock.patch.object(nouvelle.equipe.SCENARISTE, "travailler_json",
                               side_effect=repondre):
            nouvelle._grille_ou_retente(FauxContexte(), "invite", 3350)
        self.assertEqual(appels, [3350], "un seul appel quand rien n'est coupe")


class UnFournisseurDeclareEtJamaisAppele(unittest.TestCase):
    """« opencode » etait declare, dote d'une cle, affiche « disponible »
    par le diagnostic — et l'ordre de bascule ne le nommait pas.

    Journal du 15/09/2026 : vingt-sept modeles essayes, aucun n'etait le
    sien. Six modeles payes, jamais appeles une seule fois. C'est le reglage
    orphelin du depot, deplace d'un cran : une chose declaree, visible, et
    que rien ne lit.
    """

    def test_tout_fournisseur_declare_entre_dans_l_ordre(self):
        declares = {p.name for p in config.PROVIDERS}
        ordonnes = set(config.provider_order())
        self.assertEqual(declares - ordonnes, set(),
                         "declares et jamais appeles")

    def test_un_fournisseur_absent_de_la_liste_est_ajoute_a_la_fin(self):
        """Le garde-fou structurel : corriger l'oubli une fois ne suffit
        pas, il faut le rendre impossible."""
        faux = config.Provider(name="atelier-fictif",
                               base_url="https://exemple.invalide/v1",
                               api_key_env="", models={"standard": "x"},
                               keyless=True)
        config.PROVIDERS.append(faux)
        config.PROVIDERS_BY_NAME[faux.name] = faux
        try:
            self.assertIn("atelier-fictif", config.provider_order())
            self.assertIn("atelier-fictif",
                          [p.name for p in
                           config.active_providers(include_unavailable=True)])
        finally:
            config.PROVIDERS.remove(faux)
            del config.PROVIDERS_BY_NAME[faux.name]

    def test_opencode_passe_avant_les_paliers_gratuits(self):
        """Il est paye : le laisser derriere les gratuits reviendrait a ne
        l'appeler qu'une fois ceux-ci epuises."""
        ordre = config.provider_order()
        self.assertLess(ordre.index("opencode"), ordre.index("pollinations"))


class LaSondeNAccusePasAtort(unittest.TestCase):
    """Un modele de RAISONNEMENT redige son brouillon avant de repondre.

    « core.texte » retire ce brouillon. Avec seize jetons accordes, il ne
    restait rien : la sonde declarait « vide » les deux modeles de Groq,
    alors que Groq venait de servir quatorze mille jetons le jour meme. Un
    diagnostic qui accuse a tort est pire que pas de diagnostic.
    """

    def test_la_sonde_laisse_de_la_place_au_brouillon(self):
        source = (RACINE / "usine" / "core" / "llm.py").read_text(
            encoding="utf-8")
        debut = source.index("def essai_direct(")
        corps = source[debut:source.index("\ndef ", debut + 10)]
        self.assertIn("min(256, p.max_sortie)", corps,
                      "seize jetons ne laissent pas conclure un modele de "
                      "raisonnement")

    def test_un_brouillon_seul_se_nomme_ainsi(self):
        """Et pas « vide » : le modele a parle, et il fonctionne."""
        from usine.core import diagnostic

        self.assertEqual(diagnostic._nommer_le_refus(
            HttpErreur(200, "raisonnement seul")), "raisonnement seul")

    def test_le_brouillon_seul_n_est_pas_un_modele_inconnu(self):
        """Sinon la reparation remplacerait un modele qui marche."""
        exc = HttpErreur(200, "raisonnement seul, pas de reponse")
        self.assertFalse(llm._modele_inconnu(exc))
        self.assertFalse(llm._service_ferme(exc))


class LaReparationEssaieAvantDeRetenir(unittest.TestCase):
    """Remplacer un identifiant mort par un autre identifiant mort ne se
    verrait qu'a la fabrication suivante."""

    def setUp(self):
        modeles.oublier()

    def test_un_remplacant_muet_n_est_pas_retenu(self):
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        catalogue = ["mort-un", "mort-deux", "vivant-standard"]
        appels = []

        def essai(p, modele, timeout=30):
            appels.append(modele)
            if modele.startswith("vivant"):
                return "OK"
            raise HttpErreur(404, "Not Found")

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai), \
             mock.patch.object(modeles, "catalogue", return_value=catalogue), \
             mock.patch.object(modeles, "choisir",
                               side_effect=lambda c, r: c[0] if c else ""):
            bilan = diagnostic.reparer_modeles()

        retenus = {(l["fournisseur"], l["role"]): l["apres"]
                   for l in bilan["repares"]}
        self.assertTrue(retenus, "rien n'a ete repare")
        for apres in retenus.values():
            self.assertTrue(apres.startswith("vivant"),
                            "un remplacant muet a ete retenu : " + apres)

    def test_un_role_sans_candidat_reprend_ce_qui_a_deja_repondu(self):
        """Rapport du 15/09/2026 : « gemini / costaud » repartait sans
        remplacant alors que « long » et « standard » — partis du MEME
        identifiant mort — venaient d'en trouver un qui repond.

        Le classement par role met les gros modeles en tete ; le palier
        gratuit ne les sert pas, et les quatre essais partaient tous dessus.
        Un modele deja appele et qui a repondu ne coute rien a reprendre.
        """
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["gemini"]
        # « costaud » passe avant « long » et « standard » dans l'ordre
        # alphabetique : c'est ce qui rendait le defaut visible.
        gros = ["gros-un", "gros-deux", "gros-trois", "gros-quatre"]
        catalogue = gros + ["petit-qui-repond"]

        def essai(p, modele, timeout=30):
            if modele == "petit-qui-repond":
                return "OK"
            raise HttpErreur(404, "Not Found")

        def classer(candidats, role):
            """Le classement reel : « costaud » ne veut que des gros.

            C'est exactement ce qui s'est passe — les autres roles
            acceptaient le petit modele et l'ont trouve, « costaud » non.
            """
            if role == "costaud":
                gros_restants = [m for m in gros if m in candidats]
                return gros_restants[0] if gros_restants else ""
            ordonnes = [m for m in gros if m in candidats]
            ordonnes += [m for m in candidats if m not in gros]
            return ordonnes[0] if ordonnes else ""

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai), \
             mock.patch.object(modeles, "catalogue", return_value=catalogue), \
             mock.patch.object(modeles, "choisir", side_effect=classer):
            bilan = diagnostic.reparer_modeles()

        roles = {l["role"] for l in bilan["repares"]}
        self.assertEqual(bilan["sans_recours"], [],
                         "un role repart sans remplacant alors qu'un modele "
                         "vient de repondre chez le meme fournisseur")
        self.assertEqual(roles, set(fournisseur.models),
                         "tous les roles doivent etre reparés")
        # Et le repli se DIT : ce n'est pas le meilleur modele pour ce role.
        self.assertTrue(any(l.get("repli") for l in bilan["repares"]))

    def test_un_modele_configure_qui_marche_sert_aussi_de_repli(self):
        """L'autre moitie du repli, et elle manquait.

        Un modele deja configure et qui REPOND n'a rien a reparer — mais il
        reste une solution prouvee pour un role qui, lui, n'en a pas. Sans
        le compter parmi les confirmes, la seconde passe repartait les mains
        vides alors qu'un modele du meme fournisseur venait de repondre.
        """
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["gemini"]
        vivant = fournisseur.model_for("rapide")

        def essai(p, modele, timeout=30):
            if modele == vivant:
                return "OK"
            raise HttpErreur(404, "Not Found")

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai), \
             mock.patch.object(modeles, "catalogue", return_value=[vivant]), \
             mock.patch.object(modeles, "choisir", return_value=""):
            bilan = diagnostic.reparer_modeles()

        self.assertEqual(bilan["sans_recours"], [],
                         "un modele du meme fournisseur repondait pourtant")
        for ligne in bilan["repares"]:
            self.assertEqual(ligne["apres"], vivant)
            self.assertTrue(ligne["repli"])

    def test_ce_qui_est_ecarte_est_dit(self):
        """« Rien a reparer » ne doit pas se lire « tout va bien ».

        Rapport du 15/09/2026, apres correction des identifiants : « Aucun
        identifiant mort : rien a reparer » — alors qu'un service etait
        ferme (410), un credit epuise et deux quotas atteints. La reparation
        avait raison, et le rapport donnait tort a la realite.

        C'est la confusion que ce depot passe son temps a supprimer :
        « personne n'a repondu » n'est pas « tout va bien ».
        """
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["mistral"]

        def essai(p, modele, timeout=30):
            raise HttpErreur(429, "Too Many Requests")

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            bilan = diagnostic.reparer_modeles()

        self.assertEqual(bilan["repares"], [])
        self.assertEqual(bilan["sans_recours"], [])
        self.assertTrue(bilan["ecartes"],
                        "un quota atteint doit etre DIT, pas tu")
        self.assertEqual({l["cause"] for l in bilan["ecartes"]},
                         {"quota atteint"})
        self.assertEqual(bilan["vivants"], [],
                         "aucun modele n'a repondu : ne pas le pretendre")

    def test_un_modele_qui_repond_est_compte_comme_vivant(self):
        """L'autre moitie : sans cette liste, on ne peut pas distinguer
        « tout repond » de « personne n'a pu etre interroge »."""
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["mistral"]
        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", return_value="OK"):
            bilan = diagnostic.reparer_modeles()
        self.assertEqual(bilan["ecartes"], [])
        self.assertEqual({l["fournisseur"] for l in bilan["vivants"]},
                         {"mistral"})

    def test_un_quota_atteint_ne_declenche_pas_de_remplacement(self):
        """Changer de modele n'y peut rien, et le faire masquerait la vraie
        cause : c'est le compte qui est a sec, pas l'identifiant."""
        from usine.core import diagnostic

        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]

        def essai(p, modele, timeout=30):
            raise HttpErreur(429, "Too Many Requests")

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[fournisseur]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            bilan = diagnostic.reparer_modeles()
        self.assertEqual(bilan["repares"], [])
        self.assertEqual(bilan["sans_recours"], [])


if __name__ == "__main__":
    unittest.main()
