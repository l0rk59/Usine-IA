"""La bible de serie : ce qu'un tome transmet au suivant.

L'usine fabriquait des produits isoles. Le tome 2 se vend au lecteur du tome
1 — c'est le seul levier de vente qu'une fabrique de fiction possede vraiment
— et un tome qui contredit le precedent perd ce lecteur pour de bon.

Ces tests portent sur les trois decisions qui font tenir le modele :

  1. le PREMIER tome qui affirme un fait a raison ; un tome ulterieur qui dit
     autre chose se trompe, et la serie ne change pas d'avis ;
  2. le cadre et la distribution s'ACCUMULENT sans se reecrire ;
  3. une serie inconnue n'est pas une erreur : c'est un premier tome.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import serie, store  # noqa: E402
from usine.pipelines import faits  # noqa: E402


def setUpModule():
    atelier.isoler("serie")


BIBLE_T1 = {
    "titre": "Le dernier train",
    "cadre": {"lieu": "Roubaix", "epoque": "aujourd'hui",
              "regles": ["les trains ne roulent plus la nuit"]},
    "personnages": [
        {"nom": "Camille Renard", "role": "protagoniste", "desir": "sauver la ligne",
         "defaut": "ne demande jamais d'aide", "voix": "breve"},
    ],
    "premisse": "Une cheminote apprend que sa ligne ferme.",
}

BIBLE_T2 = {
    "titre": "La voie de service",
    "cadre": {"lieu": "Lille", "epoque": "dix ans plus tard",
              "regles": ["les trains ne roulent plus la nuit",
                         "le depot est ferme le dimanche"]},
    "personnages": [
        {"nom": "Camille Renard", "role": "protagoniste", "desir": "autre chose",
         "defaut": "autre", "voix": "autre"},
        {"nom": "Hakim Oussaid", "role": "antagoniste", "desir": "fermer",
         "defaut": "rigide", "voix": "polie"},
    ],
}


def _vider():
    with store.cursor() as cur:
        cur.execute("DELETE FROM series")
        cur.execute("DELETE FROM produits")


class TestNommage(unittest.TestCase):
    """Une faute de casse creerait une seconde serie vide, et le tome 2
    repartirait de zero sans rien dire."""

    def test_la_casse_et_les_espaces_ne_comptent_pas(self):
        self.assertEqual(serie.normaliser("Les Ombres du Fleuve"),
                         serie.normaliser("les  ombres   du fleuve"))

    def test_les_accents_non_plus(self):
        self.assertEqual(serie.normaliser("L'Été perdu"),
                         serie.normaliser("l'ete perdu"))

    def test_un_nom_vide_ne_donne_pas_de_cle(self):
        self.assertEqual(serie.normaliser("   "), "")
        self.assertEqual(serie.normaliser(""), "")


class TestSerieNeuve(unittest.TestCase):
    """Une serie inconnue n'est pas une erreur : c'est un premier tome."""

    def setUp(self):
        _vider()

    def test_lire_une_serie_inconnue_rend_none(self):
        self.assertIsNone(serie.lire("jamais vue"))

    def test_le_premier_tome_porte_le_rang_1(self):
        self.assertEqual(serie.prochain_rang("jamais vue"), 1)

    def test_le_rappel_est_vide(self):
        """Une consigne qui parle d'un passe inexistant vaut moins que rien."""
        self.assertEqual(serie.rappel("jamais vue"), "")

    def test_aucune_contradiction_a_signaler(self):
        self.assertEqual(
            serie.contradictions("jamais vue", {"Camille": {"yeux": "vert"}}), [])

    def test_un_nom_vide_n_enregistre_rien(self):
        self.assertEqual(serie.enregistrer_tome("", BIBLE_T1, "T", ""), 0)
        self.assertEqual(serie.lister(), [])


class TestAccumulation(unittest.TestCase):
    def setUp(self):
        _vider()
        serie.enregistrer_tome("Les rails", BIBLE_T1, "Le dernier train",
                               resume="Camille perd sa ligne.",
                               faits={"Camille Renard": {"yeux": "vert",
                                                         "age": "32"}})

    def test_les_rangs_se_suivent(self):
        self.assertEqual(serie.prochain_rang("Les rails"), 2)
        rang = serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...")
        self.assertEqual(rang, 2)
        self.assertEqual(serie.prochain_rang("Les rails"), 3)

    def test_la_distribution_s_accumule_sans_doublon(self):
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...")
        noms = [p["nom"] for p in serie.lire("Les rails")["personnages"]]
        self.assertEqual(noms, ["Camille Renard", "Hakim Oussaid"])

    def test_une_fiche_de_personnage_deja_connu_n_est_pas_reecrite(self):
        """Le lecteur a lu la premiere. Un tome ulterieur qui redecrit le
        personnage ne doit pas reecrire le passe."""
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...")
        camille = serie.lire("Les rails")["personnages"][0]
        self.assertEqual(camille["desir"], "sauver la ligne")

    def test_le_cadre_du_premier_tome_fait_loi(self):
        """Reecrire le lieu au tome 2 deplacerait retroactivement une
        histoire que le lecteur a deja lue."""
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...")
        cadre = serie.lire("Les rails")["cadre"]
        self.assertEqual(cadre["lieu"], "Roubaix")
        self.assertEqual(cadre["epoque"], "aujourd'hui")

    def test_une_regle_nouvelle_s_ajoute_quand_meme(self):
        """Le cadre ne se reecrit pas, mais il se complete : un tome peut
        poser une regle que le precedent n'avait pas eu a poser."""
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...")
        regles = serie.lire("Les rails")["cadre"]["regles"]
        self.assertIn("les trains ne roulent plus la nuit", regles)
        self.assertIn("le depot est ferme le dimanche", regles)

    def test_un_resume_trop_long_est_abrege(self):
        long = " ".join("mot{}".format(i) for i in range(600))
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", long)
        dernier = serie.lire("Les rails")["tomes"][-1]["resume"]
        self.assertLessEqual(len(dernier.split()), serie.MOTS_RESUME_TOME + 1)
        self.assertTrue(dernier.endswith("..."))


class TestCanonDesFaits(unittest.TestCase):
    """Le premier tome qui affirme a raison. C'est tout le modele."""

    def setUp(self):
        _vider()
        serie.enregistrer_tome("Les rails", BIBLE_T1, "Le dernier train",
                               resume="...",
                               faits={"Camille Renard": {"yeux": "vert",
                                                         "age": "32"}})

    def test_un_fait_conforme_ne_dit_rien(self):
        self.assertEqual(
            serie.contradictions("Les rails",
                                 {"Camille Renard": {"yeux": "vert"}}), [])

    def test_un_fait_contredit_est_signale(self):
        trouvees = serie.contradictions(
            "Les rails", {"Camille Renard": {"yeux": "bleu"}})
        self.assertEqual(len(trouvees), 1)
        self.assertEqual(trouvees[0]["genre"], "fait_contredit_la_serie")
        self.assertEqual(trouvees[0]["gravite"], "majeur")
        self.assertIn("vert", trouvees[0]["detail"])
        self.assertIn("bleu", trouvees[0]["detail"])

    def test_un_attribut_inconnu_de_la_serie_n_est_pas_une_contradiction(self):
        """C'est le tome courant qui l'etablit : rien a contredire."""
        self.assertEqual(
            serie.contradictions("Les rails",
                                 {"Camille Renard": {"cheveux": "roux"}}), [])

    def test_un_personnage_inconnu_non_plus(self):
        self.assertEqual(
            serie.contradictions("Les rails", {"Nouveau": {"yeux": "bleu"}}), [])

    def test_le_canon_ne_se_reecrit_pas(self):
        """Un tome 2 qui se trompe ne doit pas devenir la nouvelle verite —
        sinon le tome 3 serait compare a l'erreur du tome 2."""
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...",
                               faits={"Camille Renard": {"yeux": "bleu"}})
        self.assertEqual(
            serie.lire("Les rails")["faits"]["Camille Renard"]["yeux"], "vert")
        self.assertTrue(serie.contradictions(
            "Les rails", {"Camille Renard": {"yeux": "bleu"}}))

    def test_un_fait_nouveau_entre_au_canon(self):
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie", "...",
                               faits={"Hakim Oussaid": {"yeux": "noir"}})
        acquis = serie.lire("Les rails")["faits"]
        self.assertEqual(acquis["Hakim Oussaid"]["yeux"], "noir")
        self.assertEqual(acquis["Camille Renard"]["age"], "32")


class TestRappel(unittest.TestCase):
    """Ce que le tome suivant recoit dans son invite."""

    def setUp(self):
        _vider()
        serie.enregistrer_tome("Les rails", BIBLE_T1, "Le dernier train",
                               resume="Camille perd sa ligne.",
                               faits={"Camille Renard": {"yeux": "vert"}})

    def test_il_nomme_la_serie_le_cadre_et_les_tomes(self):
        texte = serie.rappel("Les rails")
        self.assertIn("Les rails", texte)
        self.assertIn("Roubaix", texte)
        self.assertIn("Le dernier train", texte)
        self.assertIn("Camille perd sa ligne.", texte)

    def test_il_rappelle_les_faits_acquis(self):
        """Trois lignes qui evitent la contradiction que le lecteur, lui,
        remarquera."""
        self.assertIn("vert", serie.rappel("Les rails"))

    def test_il_demande_une_suite_qui_se_tienne_seule(self):
        texte = serie.rappel("Les rails")
        self.assertIn("SUITE", texte)
        self.assertIn("se tenir seul", texte)


class TestLienAvecLesProduits(unittest.TestCase):
    def setUp(self):
        _vider()

    def test_le_produit_porte_sa_serie_et_son_rang(self):
        store.creer_produit("p1", "nouvelle", "Le dernier train")
        serie.enregistrer_tome("Les rails", BIBLE_T1, "Le dernier train",
                               resume="...", produit_id="p1")
        fiche = store.lire_produit("p1")
        self.assertEqual(fiche["serie"], "les-rails")
        self.assertEqual(fiche["rang"], 1)
        self.assertEqual(serie.tomes_du_produit("p1"),
                         {"serie": "les-rails", "rang": 1})

    def test_un_produit_hors_serie_ne_ment_pas(self):
        store.creer_produit("p2", "ebook", "Un guide")
        self.assertIsNone(serie.tomes_du_produit("p2"))

    def test_lister_compte_les_tomes(self):
        serie.enregistrer_tome("Les rails", BIBLE_T1, "T1", "...")
        serie.enregistrer_tome("Les rails", BIBLE_T2, "T2", "...")
        listing = serie.lister()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["tomes"], 2)
        self.assertEqual(listing[0]["nom"], "Les rails")


class TestCanonDuTome(unittest.TestCase):
    """« faits.canon » reduit le registre a ce que la serie retient."""

    def test_le_premier_releve_fait_foi(self):
        registre = faits.relever(
            [("S1", "Camille avait les yeux verts."),
             ("S2", "Camille avait les yeux bleus.")],
            ["Camille"])
        self.assertEqual(faits.canon(registre)["Camille"]["yeux"], "vert")

    def test_un_registre_vide_donne_un_canon_vide(self):
        self.assertEqual(faits.canon({}), {})


if __name__ == "__main__":
    unittest.main()


class TestPageDeSuite(unittest.TestCase):
    """La derniere page : c'est la que la serie devient une vente.

    Un lecteur qui vient de finir un tome est, a cet instant precis, le plus
    disponible qu'il sera jamais pour en acheter un autre — et la derniere
    page est le seul endroit ou on le tient encore.
    """

    def setUp(self):
        _vider()
        serie.enregistrer_tome("Les rails", BIBLE_T1, "Le dernier train",
                               resume="Camille perd sa ligne.")
        serie.enregistrer_tome("Les rails", BIBLE_T2, "La voie de service",
                               resume="Dix ans plus tard, le depot rouvre.")

    def test_le_tome_1_annonce_le_tome_2(self):
        """Le cas qui rapporte : le lecteur du tome 1 est celui qui a paye en
        premier et qui reviendra."""
        page = serie.page_de_suite("Les rails", 1)
        self.assertIn("La voie de service", page)
        self.assertNotIn("Le dernier train", page)

    def test_le_tome_2_renvoie_au_tome_1(self):
        page = serie.page_de_suite("Les rails", 2)
        self.assertIn("Le dernier train", page)
        self.assertIn("tome 2", page)

    def test_un_tome_seul_n_a_pas_de_page_de_suite(self):
        """Une page « la suite » qui n'annonce rien decoit, et une deception
        a la derniere page est le pire service a rendre a qui vous a lu
        jusqu'au bout."""
        _vider()
        serie.enregistrer_tome("Solo", BIBLE_T1, "Unique", resume="...")
        self.assertEqual(serie.page_de_suite("Solo", 1), "")

    def test_une_serie_inconnue_ne_donne_rien(self):
        self.assertEqual(serie.page_de_suite("jamais vue", 1), "")

    def test_elle_demande_un_avis(self):
        """C'est ce qui decide si quelqu'un d'autre trouvera le livre."""
        self.assertIn("avis", serie.page_de_suite("Les rails", 1))


class TestTomesARafraichir(unittest.TestCase):
    def setUp(self):
        _vider()

    def test_le_dernier_tome_n_a_rien_a_rafraichir(self):
        store.creer_produit("p1", "nouvelle", "T1")
        serie.enregistrer_tome("Les rails", BIBLE_T1, "T1", "...", produit_id="p1")
        self.assertEqual(serie.tomes_a_rafraichir("Les rails"), [])

    def test_les_tomes_anterieurs_sont_signales(self):
        store.creer_produit("p1", "nouvelle", "T1")
        store.creer_produit("p2", "nouvelle", "T2")
        serie.enregistrer_tome("Les rails", BIBLE_T1, "T1", "...", produit_id="p1")
        serie.enregistrer_tome("Les rails", BIBLE_T2, "T2", "...", produit_id="p2")
        attente = serie.tomes_a_rafraichir("Les rails")
        self.assertEqual([t["rang"] for t in attente], [1])

    def test_un_tome_sans_produit_n_est_pas_propose(self):
        """Sans dossier de produit, il n'y a aucun fichier a refaire."""
        serie.enregistrer_tome("Les rails", BIBLE_T1, "T1", "...")
        serie.enregistrer_tome("Les rails", BIBLE_T2, "T2", "...")
        self.assertEqual(serie.tomes_a_rafraichir("Les rails"), [])
