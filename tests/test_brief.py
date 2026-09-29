"""Ce que l'usine decide quand on ne lui dit rien, et le roman qu'elle cachait.

Deux defauts d'ergonomie, et le meme mecanisme derriere : une capacite reelle
que rien ne rendait visible.

**Les reglages par defaut.** Taper un sujet et rien d'autre etait possible, et
trompeur : « pro », douze chapitres, « un public francophone motive »
s'appliquaient quel que soit le sujet. Un guide de fiscalite pour
experts-comptables et un carnet de recettes pour debutants sortaient avec la
meme voix, la meme longueur et la meme audience imaginaire. Un reglage par
defaut n'est pas neutre ; il est juste invisible.

**Le roman.** Il etait deja fabricable — « usine nouvelle --chapitres 40 » —
et ne figurait ni au catalogue, ni au menu, ni au tableau de bord. Personne ne
devine une fonctionnalite qui n'a pas de nom.
"""

from __future__ import annotations

import io
import sys
import unittest
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine import cli  # noqa: E402
from usine.core import llm, reglages, store  # noqa: E402
from usine.pipelines import brief, catalogue, nouvelle  # noqa: E402


def setUpModule():
    atelier.isoler("brief")


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class CeQuiResteADecider(unittest.TestCase):

    def _contexte(self, **remplace):
        from usine.pipelines.base import Contexte

        valeurs = {"sujet": "un sujet", "ton": brief.AUTO,
                   "audience": brief.AUTO, "taille": brief.AUTO}
        valeurs.update(remplace)
        return Contexte(**valeurs)

    def test_tout_est_a_decider_quand_rien_n_est_choisi(self):
        self.assertEqual(brief.a_decider(self._contexte()),
                         ["audience", "ton", "taille"])

    def test_un_choix_explicite_n_est_jamais_repris(self):
        """La regle qui rend le brief acceptable.

        Un brief qui ecrase « --ton punchy » ne serait pas une aide, ce serait
        une commande qui n'obeit pas.
        """
        ctx = self._contexte(ton="punchy")
        self.assertNotIn("ton", brief.a_decider(ctx))

    def test_un_nombre_de_chapitres_impose_ferme_la_taille(self):
        """« --chapitres 4 » dit la longueur aussi clairement que « -T court »."""
        ctx = self._contexte(chapitres=4)
        self.assertNotIn("taille", brief.a_decider(ctx))

    def test_le_volume_ne_se_decide_que_pour_une_chaine_qui_le_lit(self):
        """Vraie fabrication du 27/09/2026 : « volume : 5 sections de ~400
        mots » annonce pour un memo, qui compte des blocs."""
        for cle in ("memo", "quiz", "cartes", "mots-meles", "prompts"):
            with self.subTest(type=cle):
                self.assertEqual(brief.a_decider(self._contexte(), cle),
                                 ["audience", "ton"])
        for cle in ("ebook", "roman", "conte", "formation"):
            with self.subTest(type=cle):
                self.assertIn("taille", brief.a_decider(self._contexte(), cle))

    def test_l_aide_ne_nomme_que_ce_qui_a_ete_decide(self):
        from usine.pipelines.base import Contexte

        lignes = []
        ctx = Contexte(sujet="le compost en appartement", ton=brief.AUTO,
                       audience=brief.AUTO, taille=brief.AUTO,
                       journal=lignes.append)
        with mock.patch.object(brief, "demander", lambda *a, **k: {
                "audience": "des citadins", "ton": "pedagogue", "sections": 5,
                "mots_par_section": 400, "niche": "", "promesse": "",
                "pourquoi": ""}):
            brief.appliquer(ctx, "memo")
        self.assertFalse(any("volume" in l for l in lignes), lignes)
        self.assertIn("  (pour imposer les vôtres : les champs Ton et Audience, "
                      "ou --ton, --audience)", lignes)

    def test_une_case_vide_vaut_auto(self):
        """Les deux veulent dire la meme chose, et c'est le point : ne pas
        choisir est un choix."""
        self.assertEqual(brief.a_decider(self._contexte(ton="", audience="",
                                                        taille="")),
                         ["audience", "ton", "taille"])


class LeBriefEstApplique(unittest.TestCase):

    def setUp(self):
        atelier.isoler("brief-application")
        llm.definir_simulateur(simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_le_reglage_par_defaut_est_auto(self):
        """Sinon le brief ne se declenche jamais et tout ce module est mort."""
        profil = reglages.charger()
        for champ in ("ton", "taille", "audience"):
            with self.subTest(champ=champ):
                self.assertEqual(profil[champ], brief.AUTO)

    def test_sans_option_l_usine_annonce_ce_qu_elle_a_decide(self):
        """Une decision prise en silence ne se corrige pas."""
        _, texte = _muet(["ebook", "la facturation des independants"])
        self.assertIn("Brief automatique", texte)
        self.assertIn("niche :", texte)
        self.assertIn("--ton", texte, "il faut dire comment imposer le sien")
        # Le meme journal s'affiche dans le tableau de bord, ou il n'y a pas
        # d'option a taper : il nomme aussi les champs du formulaire.
        self.assertIn("Ton, Audience et Volume", texte)

    def test_le_brief_change_vraiment_le_produit(self):
        """Sans cette mesure, le brief pourrait n'etre qu'un affichage."""
        _muet(["ebook", "la facturation des independants"])
        produit = store.lister_produits()[0]
        # Le simulateur rend 9 sections et une audience precise : ce ne sont
        # ni les 12 du palier « standard », ni « un public francophone motive ».
        self.assertEqual((produit.get("meta") or {}).get("chapitres"), 9)
        self.assertIn("portage", produit["audience"])

    def test_une_option_explicite_gagne_sur_le_brief(self):
        code, texte = _muet(["ebook", "les servitudes de passage",
                             "--ton", "punchy", "--chapitres", "4",
                             "-a", "des notaires"])
        self.assertEqual(code, 0)
        self.assertNotIn("Brief automatique", texte)
        produit = store.lister_produits()[0]
        self.assertEqual((produit.get("meta") or {}).get("chapitres"), 4)
        self.assertEqual(produit["audience"], "des notaires")

    def test_un_choix_partiel_ne_laisse_decider_que_le_reste(self):
        """Le cas courant, et le seul ou la regle se verifie vraiment.

        Quand TOUT est impose, le brief ne tourne pas et n'ecrase donc rien :
        un test qui ne regarde que ce cas-la ne prouve rien. Ici le ton est
        impose et l'audience ne l'est pas.
        """
        from usine.pipelines.base import Contexte

        ctx = Contexte(sujet="la facturation", ton="punchy",
                       audience=brief.AUTO, taille=brief.AUTO,
                       journal=lambda _m: None)
        applique = brief.appliquer(ctx)
        self.assertEqual(ctx.ton, "punchy", "le ton impose doit survivre")
        self.assertNotIn("ton", applique)
        self.assertIn("audience", applique)
        self.assertNotEqual(ctx.audience, brief.AUTO)

    def test_sans_modele_le_brief_renonce_au_lieu_de_bloquer(self):
        """Personne n'attend cinq minutes pour se voir proposer un ton.

        Sans fournisseur, la fabrication continue — le brief est un confort,
        pas un passage oblige. Mais « auto » ne part pas dans les invites :
        la decision est confiee au redacteur, en toutes lettres.

        Mesure du 23/09/2026 : ce test exigeait qu'on « garde les valeurs
        par defaut ». Elles valent « auto » depuis que l'usine decide tout,
        et le modele de redaction recevait « TON : auto ».
        """
        def tombe(*_a, **_kw):
            raise llm.PlusDeFournisseur("aucun fournisseur")

        llm.definir_simulateur(tombe)
        from usine.pipelines.base import Contexte

        journal = []
        ctx = Contexte(sujet="un sujet", ton=brief.AUTO, audience=brief.AUTO,
                       taille=brief.AUTO, journal=journal.append)
        applique = brief.appliquer(ctx)
        self.assertTrue(any("indisponible" in ligne for ligne in journal))
        self.assertEqual(applique.get("confie_au_redacteur"), ["audience", "ton"])
        self.assertNotEqual(ctx.ton, brief.AUTO)
        self.assertNotEqual(ctx.audience, brief.AUTO)
        self.assertNotIn(brief.AUTO, ctx.description_ton.split())
        # Ce que l'utilisateur a choisi n'est jamais remplace, meme sans brief.
        ctx = Contexte(sujet="un sujet", ton="punchy", audience=brief.AUTO,
                       taille=brief.AUTO, journal=journal.append)
        brief.appliquer(ctx)
        self.assertEqual(ctx.ton, "punchy")


class LeRomanExiste(unittest.TestCase):

    def setUp(self):
        # Un atelier par cas : le cache des reponses est partage par tout un
        # atelier, et les cas qui coupent la fabrication a un nombre d'appels
        # donne n'atteindraient jamais leur seuil si le cache repondait a
        # leur place.
        atelier.isoler("brief-roman-{}".format(self.id().rsplit(".", 1)[-1]))
        llm.definir_simulateur(simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_il_est_au_catalogue(self):
        """Le catalogue est la source unique : la CLI, le menu et le tableau
        de bord le lisent. Y figurer, c'est exister partout."""
        self.assertIn("roman", catalogue.cles())
        type_produit = catalogue.obtenir("roman")
        self.assertTrue(type_produit.fabriquer)
        self.assertIn("epub", type_produit.formats)

    def test_il_annonce_une_duree_honnete(self):
        """Trente scenes relues prennent des heures. Annoncer « 12 a 30 min »
        comme la nouvelle ferait croire l'usine bloquee."""
        self.assertGreaterEqual(catalogue.obtenir("roman").minutes[0], 45)

    def test_le_produit_fabrique_porte_le_nom_de_roman(self):
        """Ce qu'on demande et ce qu'on retrouve doivent porter le meme nom.

        Sans cela le roman s'enregistrait comme une nouvelle, s'affichait
        comme une nouvelle, et son dossier s'appelait « nouvelle-... ».
        """
        _muet(["roman", "un meurtre en station de ski", "--chapitres", "6"])
        produit = store.lister_produits()[0]
        self.assertEqual(produit["type"], "roman")
        self.assertTrue(Path(produit["dossier"]).name.startswith("roman-"))

    def test_sans_precision_il_prend_l_echelle_d_un_roman(self):
        """En dessous de 40 000 mots, le marche ne parle plus de roman."""
        from usine.pipelines.base import Contexte

        ctx = Contexte(sujet="x")
        self.assertEqual(ctx.nb_chapitres * ctx.mots_par_chapitre < 40000, True)
        ctx_roman = Contexte(sujet="x")
        ctx_roman.chapitres = nouvelle.ROMAN_SCENES
        ctx_roman.mots_section = nouvelle.ROMAN_MOTS
        self.assertGreaterEqual(
            ctx_roman.nb_chapitres * ctx_roman.mots_par_chapitre, 40000)
        self.assertEqual(
            nouvelle.format_fiction(ctx_roman.nb_chapitres
                                    * ctx_roman.mots_par_chapitre),
            "roman")

    def test_la_reprise_garde_la_bible_d_origine(self):
        """Reconstruire la bible changerait le monde sous les scenes ecrites.

        C'est exactement la continuite que cette chaine existe pour tenir :
        meme distribution, meme cadre, meme ordre des beats.
        """
        from usine.pipelines import carnet

        appels = {"n": 0}

        def coupure(invite, role="standard", **kw):
            appels["n"] += 1
            if appels["n"] > 12:
                raise llm.PlusDeFournisseur("coupe")
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(coupure)
        _muet(["roman", "une disparition en Ardeche", "--chapitres", "8"])
        produit = store.lister_produits()[0]
        dossier = Path(produit["dossier"])
        plan = carnet.plan(dossier)
        plan["bible"]["titre"] = "Bible marquee pour la reprise"
        carnet.noter_plan(dossier, plan)

        llm.definir_simulateur(simulateur)
        _, texte = _muet(["reprendre", produit["id"]])
        self.assertIn("Bible marquee pour la reprise", texte)
        # Et une reprise ne rebriefe pas : redecider le ton donnerait au
        # second tiers du livre une autre voix que le premier.
        self.assertNotIn("Brief automatique", texte)

    def test_une_scene_de_repli_n_entre_pas_au_carnet(self):
        """Une fiche de repli n'est pas une scene.

        Si elle entrait au carnet, la reprise la sauterait et le roman
        garderait un trou definitif : un resume de trois lignes a la place
        d'une scene, et plus aucun moyen de savoir laquelle.

        La panne est provoquee sur la REDACTION d'une scene precise, et pas
        au bout de N appels. La difference compte : une panne survenue
        ailleurs — pendant un resume, pendant une relecture — fait sauter les
        scenes suivantes avant meme qu'on tente de les ecrire, et ce chemin-la
        n'exerce pas le cas qu'on veut garder.
        """
        from usine.pipelines import carnet

        def coupure(invite, role="standard", **kw):
            texte = invite[-1]["content"] if isinstance(invite, list) else str(invite)
            if "Ecris la scene 4 " in texte:
                raise llm.PlusDeFournisseur("coupe pendant la redaction")
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(coupure)
        _muet(["roman", "un huis clos dans un phare", "--chapitres", "8"])
        produit = store.lister_produits()[0]
        dossier = Path(produit["dossier"])
        manquants = (produit.get("meta") or {}).get("manquants") or []
        self.assertIn("scene-4", manquants,
                      "la scene dont la redaction a echoue doit etre a refaire")
        au_carnet = carnet.compte(dossier)
        self.assertIsNone(carnet.section(dossier, "scene-4"),
                          "une fiche de repli n'est pas une scene ecrite")
        self.assertEqual(au_carnet + len(manquants), 8,
                         "chaque scene est soit au carnet, soit a refaire")

    def test_une_coupure_laisse_un_roman_reprenable(self):
        """C'est le produit le plus long de l'usine, donc celui qui a le plus
        besoin de reprise : une a trois heures de fabrication."""
        from usine.pipelines import carnet

        appels = {"n": 0}

        def coupure(invite, role="standard", **kw):
            appels["n"] += 1
            if appels["n"] > 12:
                raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(coupure)
        code, texte = _muet(["roman", "un naufrage en mer du Nord",
                             "--chapitres", "8"])
        # Inacheve, donc 3 ; exporte quand meme, donc le bandeau.
        self.assertEqual(code, 3)
        self.assertIn("Produit inachevé", texte)
        produit = store.lister_produits()[0]
        self.assertEqual(produit["statut"], "en_cours")
        self.assertTrue((produit.get("meta") or {}).get("manquants"))
        dossier = Path(produit["dossier"])
        # La bible et la grille sont au carnet : une reprise qui les
        # reconstruirait changerait le monde sous les scenes deja ecrites.
        plan = carnet.plan(dossier)
        self.assertTrue(plan.get("bible"))
        self.assertTrue(plan.get("grille"))


if __name__ == "__main__":
    unittest.main()
