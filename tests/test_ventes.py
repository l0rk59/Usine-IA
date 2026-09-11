"""Les ventes reelles, et ce qu'elles changent aux decisions de l'usine.

L'usine mesurait la qualite, la duree, les appels consommes. Elle ne savait
rien de ce qui rapporte : « usine bilan » pouvait repondre « quel ton donne
vos meilleures notes » et jamais « quelle niche a paye ». Les deux questions
n'ont aucune raison d'avoir la meme reponse.
"""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("USINE_HOME", tempfile.mkdtemp(prefix="usine-ventes-"))

from usine.core import store, ventes  # noqa: E402

GUMROAD = """Sale ID,Purchase Date,Product Name,Quantity,Price,Net Amount,Currency,Refunded
S1,2026-08-03,Le systeme du freelance (PDF + EPUB),1,"29.00","25.13",EUR,false
S2,2026-08-05,Le systeme du freelance (PDF + EPUB),2,"58.00","50.26",EUR,false
S3,2026-08-11,Le systeme du freelance (PDF + EPUB),1,"29.00","25.13",EUR,true
"""

# Tableur francais : point-virgule, virgule decimale, dates jj/mm/aaaa,
# symbole monetaire colle au nombre, et une colonne d'etat en clair.
FRANCAIS = """Numero de commande;Date de vente;Article;Quantite;Montant;Devise;Statut
1001;03/08/2026;Cahier du freelance;1;12,50 €;EUR;Termine
1002;14/08/2026;Cahier du freelance;2;25,00 €;EUR;Rembourse
1003;19/08/2026;Cahier du freelance;1;12,50 €;EUR;Termine
"""


def _vider():
    with store.cursor() as cur:
        cur.execute("DELETE FROM ventes")
        cur.execute("DELETE FROM produits")


class TestLectureDesExports(unittest.TestCase):

    def setUp(self):
        _vider()

    def test_un_export_anglophone_est_lu(self):
        lecture = ventes.lire_export(GUMROAD, "gumroad")
        self.assertTrue(lecture.exploitable)
        self.assertEqual(len(lecture.lignes), 3)
        self.assertEqual(lecture.ignorees, 0)
        premiere = lecture.lignes[0]
        self.assertEqual(premiere["date"], "2026-08-03")
        self.assertEqual(premiere["brut"], 29.0)
        self.assertEqual(premiere["net"], 25.13)

    def test_un_export_francais_est_lu_aussi(self):
        """Point-virgule, virgule decimale, jj/mm/aaaa, euro colle au nombre."""
        lecture = ventes.lire_export(FRANCAIS, "etsy")
        self.assertTrue(lecture.exploitable)
        self.assertEqual([l["date"] for l in lecture.lignes],
                         ["2026-08-03", "2026-08-14", "2026-08-19"])
        self.assertEqual([l["brut"] for l in lecture.lignes], [12.5, 25.0, 12.5])
        self.assertEqual([l["unites"] for l in lecture.lignes], [1, 2, 1])

    def test_une_colonne_absente_est_nommee_plutot_que_devinee(self):
        lecture = ventes.lire_export("Colonne A,Colonne B\n1,2\n", "x")
        self.assertFalse(lecture.exploitable)
        self.assertEqual(sorted(lecture.manquants), ["brut", "date"])
        self.assertEqual(lecture.colonnes, ["Colonne A", "Colonne B"])

    def test_une_ligne_illisible_est_comptee_pas_inventee(self):
        texte = GUMROAD + "S4,pas une date,Truc,1,pas un montant,,EUR,false\n"
        lecture = ventes.lire_export(texte, "gumroad")
        self.assertEqual(len(lecture.lignes), 3)
        self.assertEqual(lecture.ignorees, 1)

    def test_le_net_absent_reste_absent(self):
        """Deduire une commission « habituelle » donnerait un revenu fictif."""
        lecture = ventes.lire_export(FRANCAIS, "etsy")
        self.assertTrue(all(l["net"] is None for l in lecture.lignes))

    def test_un_etat_en_clair_distingue_le_remboursement(self):
        lecture = ventes.lire_export(FRANCAIS, "etsy")
        self.assertEqual([l["remboursement"] for l in lecture.lignes], [0, 1, 0])

    def test_une_colonne_statut_valant_1_n_est_pas_un_remboursement(self):
        """Le nom de la colonne compte : « Statut = 1 » n'est pas un remboursement."""
        texte = ("Date,Montant,Statut\n2026-08-03,10,1\n")
        self.assertEqual(ventes.lire_export(texte, "x").lignes[0]["remboursement"], 0)
        texte = ("Date,Montant,Refunded\n2026-08-03,10,1\n")
        self.assertEqual(ventes.lire_export(texte, "x").lignes[0]["remboursement"], 1)

    def test_une_date_americaine_donne_une_vraie_date(self):
        """« 12/31/2024 » devenait « 2024-31-12 » : un mois numero 31.

        Tout le filtrage par date compare des chaines : une date impossible
        ne ressortait d'aucune requete, donc la vente disparaissait sans
        qu'aucun message ne le dise.
        """
        from usine.core.ventes import _date

        self.assertEqual(_date("12/31/2024", "mja"), "2024-12-31")
        self.assertEqual(_date("31/12/2024", "jma"), "2024-12-31")
        self.assertEqual(_date("2024-12-31"), "2024-12-31")

    def test_une_date_impossible_est_refusee_pas_rangee(self):
        from usine.core.ventes import _date

        self.assertEqual(_date("13/13/2024", "jma"), "")
        self.assertEqual(_date("00/05/2024", "jma"), "")

    def test_la_convention_se_decide_sur_tout_le_fichier(self):
        """« 03/08 » est indecidable seul ; « 31/12 » ailleurs tranche."""
        from usine.core.ventes import convention_dates

        self.assertEqual(convention_dates(["03/08/2026", "31/12/2024"]), "jma")
        self.assertEqual(convention_dates(["03/08/2026", "12/31/2024"]), "mja")
        self.assertEqual(convention_dates(["03/08/2026"]), "jma")

    def test_un_export_americain_est_lu_entierement(self):
        texte = ("Date,Product,Price\n"
                 "12/31/2024,Un livre,29\n"
                 "01/15/2025,Un livre,29\n")
        lecture = ventes.lire_export(texte, "gumroad")
        self.assertEqual(lecture.convention, "mja")
        self.assertEqual([l["date"] for l in lecture.lignes],
                         ["2024-12-31", "2025-01-15"])
        self.assertEqual(lecture.ignorees, 0)

    def test_une_colonne_paid_n_est_pas_un_identifiant_de_commande(self):
        """L'alias « id » se trouvait comme SOUS-CHAINE dans « Paid ».

        Toutes les ventes recevaient alors la meme empreinte, et l'index
        unique les jetait toutes sauf une, en annoncant « deja connue(s) ».
        """
        correspondance = ventes.reconnaitre(
            ["Date", "Product", "Price", "Paid", "Country"])
        self.assertNotIn("identifiant", correspondance)
        self.assertEqual(correspondance["date"], "Date")

    def test_toutes_les_lignes_d_un_export_sans_identifiant_sont_gardees(self):
        _vider()
        texte = ("Date,Product,Price,Paid\n"
                 "2026-08-01,Un livre,29,yes\n"
                 "2026-08-02,Un livre,19,yes\n"
                 "2026-08-03,Un livre,39,yes\n")
        lecture = ventes.lire_export(texte, "gumroad")
        ajoutees = sum(1 for ligne in lecture.lignes if ventes.enregistrer(ligne))
        self.assertEqual(ajoutees, 3, "aucune vente ne doit etre confondue")

    def test_une_colonne_n_est_retenue_que_pour_un_champ(self):
        correspondance = ventes.reconnaitre(["Date", "Total", "Order ID"])
        retenues = list(correspondance.values())
        self.assertEqual(len(retenues), len(set(retenues)))

    def test_les_montants_s_ecrivent_de_plusieurs_facons(self):
        from usine.core.ventes import _nombre

        for texte, attendu in (("1 234,56 €", 1234.56), ("$1,234.56", 1234.56),
                               ("1234.56", 1234.56), ("29", 29.0),
                               ("-12,50", -12.5), ("", None), ("abc", None)):
            self.assertEqual(_nombre(texte), attendu, texte)


class TestEnregistrement(unittest.TestCase):

    def setUp(self):
        _vider()

    def test_reimporter_le_meme_export_n_ajoute_rien(self):
        lecture = ventes.lire_export(GUMROAD, "gumroad")
        premier = sum(1 for l in lecture.lignes if ventes.enregistrer(l))
        second = sum(1 for l in ventes.lire_export(GUMROAD, "gumroad").lignes
                     if ventes.enregistrer(l))
        self.assertEqual((premier, second), (3, 0))

    def test_les_remboursements_sont_deduits_pas_ignores(self):
        for ligne in ventes.lire_export(GUMROAD, "gumroad").lignes:
            ventes.enregistrer(ligne)
        total = ventes.total_par_devise()[0]
        self.assertEqual(total["devise"], "EUR")
        self.assertEqual(total["unites"], 3)          # 1 + 2, le rembourse exclu
        self.assertAlmostEqual(total["brut"], 58.0)   # 29 + 58 - 29
        self.assertEqual(total["rembourses"], 1)

    def test_deux_devises_ne_sont_jamais_additionnees(self):
        """Convertir sans source de taux reviendrait a fabriquer le resultat."""
        for index, devise in enumerate(("EUR", "USD", "USD")):
            ventes.enregistrer({"date": "2026-08-01", "reference": "x",
                                "unites": 1, "brut": 10.0, "net": None,
                                "devise": devise, "remboursement": 0,
                                "plateforme": "p",
                                "empreinte": "d{}".format(index)})
        totaux = {t["devise"]: t for t in ventes.total_par_devise()}
        self.assertEqual(sorted(totaux), ["EUR", "USD"])
        self.assertAlmostEqual(totaux["USD"]["brut"], 20.0)
        self.assertAlmostEqual(totaux["EUR"]["brut"], 10.0)

    def test_le_net_inconnu_est_signale_et_non_compte_comme_zero(self):
        for ligne in ventes.lire_export(FRANCAIS, "etsy").lignes:
            ventes.enregistrer(ligne)
        total = ventes.total_par_devise()[0]
        self.assertEqual(total["net_inconnu"], 3)


class TestRattachement(unittest.TestCase):

    def setUp(self):
        _vider()
        store.creer_produit("ebook-le-systeme-du-freelance", "ebook",
                            "Le systeme du freelance rentable",
                            sujet="la prospection", dossier="/tmp")
        store.creer_produit("impression-cahier", "impression",
                            "Le cahier du freelance organise",
                            sujet="l organisation", dossier="/tmp")

    def test_le_nom_affiche_sur_la_plateforme_retrouve_son_produit(self):
        """« Le systeme du freelance (PDF + EPUB) » n'est pas le titre interne."""
        for ligne in ventes.lire_export(GUMROAD, "gumroad").lignes:
            ventes.enregistrer(ligne)
        propositions = ventes.rattacher_automatiquement()
        self.assertEqual(len(propositions), 1)
        reference, produit_id, score = propositions[0]
        self.assertEqual(produit_id, "ebook-le-systeme-du-freelance")
        self.assertGreaterEqual(score, 0.75)

    def test_chaque_reference_va_vers_SON_produit(self):
        """Le type de produit fait la difference, et doit donc etre compte.

        Comparer deux niches demande d'ignorer « cahier » et « systeme » :
        c'est de l'emballage. Comparer deux noms de produits demande
        l'inverse — c'est exactement ce qui les distingue. Les ecarter
        rattachait la vente du cahier a l'ebook voisin.
        """
        from usine.core import empreinte

        ebook = "Le systeme du freelance rentable"
        cahier = "Le cahier du freelance organise"
        self.assertEqual(
            empreinte.ressemblance_reference("Cahier du freelance [download]",
                                             cahier), 1.0)
        self.assertLess(
            empreinte.ressemblance_reference("Cahier du freelance [download]",
                                             ebook), 0.75)

    def test_les_mentions_de_format_ne_comptent_pas(self):
        from usine.core import empreinte

        self.assertEqual(
            empreinte.nettoyer_reference("Le systeme du freelance (PDF + EPUB)"),
            "le systeme du freelance")

    def test_une_reference_etrangere_n_est_pas_rattachee_au_hasard(self):
        ventes.enregistrer({"date": "2026-08-01", "reference": "Cours de guitare",
                            "unites": 1, "brut": 10.0, "net": None,
                            "devise": "EUR", "remboursement": 0,
                            "plateforme": "p", "empreinte": "zz"})
        self.assertEqual(ventes.rattacher_automatiquement(), [])

    def test_le_chiffre_d_affaires_se_groupe_par_type(self):
        for ligne in ventes.lire_export(GUMROAD, "gumroad").lignes:
            ventes.enregistrer(ligne)
        for reference, produit_id, _ in ventes.rattacher_automatiquement():
            ventes.lier(reference, produit_id)
        types = {t["valeur"]: t for t in ventes.par_champ("type")}
        self.assertIn("ebook", types)
        self.assertAlmostEqual(types["ebook"]["brut"], 58.0)


class TestPrix(unittest.TestCase):
    """Le nombre qui determine le revenu etait le moins fonde du systeme."""

    def setUp(self):
        _vider()
        store.creer_produit("p1", "impression", "Cahier", sujet="s",
                            dossier="/tmp")

    def _vendre(self, montants):
        for index, montant in enumerate(montants):
            ventes.enregistrer({"date": "2026-08-01", "reference": "Cahier",
                                "unites": 1, "brut": montant, "net": None,
                                "devise": "EUR", "remboursement": 0,
                                "plateforme": "etsy",
                                "empreinte": "p{}".format(index)},
                               produit_id="p1")

    def test_le_prix_median_vient_des_ventes(self):
        self._vendre([9.0, 12.0, 12.0, 15.0, 19.0])
        observe = ventes.prix_observes("impression")[0]
        self.assertEqual(observe["median"], 12.0)
        self.assertEqual(observe["ventes"], 5)

    def test_une_idee_recoit_le_prix_constate_quand_il_existe(self):
        from usine.pipelines import idees

        self._vendre([14.0, 14.0, 16.0, 12.0])
        lot = [self._idee("ebook"), self._idee("impression")]
        idees._ancrer_les_prix(lot)
        self.assertEqual(lot[0]["prix_source"], "modele")
        self.assertEqual(lot[0]["prix_eur"], 19)
        self.assertIn("ventes constatees", lot[1]["prix_source"])
        self.assertEqual(lot[1]["prix_eur"], 14)

    def test_deux_ventes_ne_suffisent_pas_a_fonder_un_prix(self):
        from usine.pipelines import idees

        self._vendre([40.0, 42.0])
        lot = [self._idee("impression")]
        idees._ancrer_les_prix(lot)
        self.assertEqual(lot[0]["prix_source"], "modele")

    def test_toutes_les_idees_portent_les_memes_cles(self):
        """Le CSV s'ecrit avec les cles de la PREMIERE idee.

        Une cle qui n'apparaitrait que sur la troisieme ferait echouer
        l'export, et seulement chez qui a deja vendu — donc jamais en test.
        """
        from usine.pipelines import idees

        self._vendre([14.0, 14.0, 16.0])
        lot = [self._idee("ebook"), self._idee("impression")]
        idees._ancrer_les_prix(lot)
        self.assertEqual(set(lot[0]), set(lot[1]))

    @staticmethod
    def _idee(type_produit):
        return {"titre": "T", "type": type_produit, "probleme": "",
                "acheteur": "", "promesse": "", "prix_eur": 19,
                "prix_source": "modele", "prix_fourchette": "",
                "difficulte": "moyenne", "concurrence": "moyenne",
                "angle_differenciant": "", "premier_canal": ""}


class TestResumePourIA(unittest.TestCase):

    def setUp(self):
        _vider()

    def test_sans_vente_le_resume_est_vide(self):
        """Mieux vaut ne rien dire au modele que lui dire zero."""
        self.assertEqual(ventes.resume_pour_ia(), "")

    def test_avec_des_ventes_le_resume_les_cite(self):
        store.creer_produit("p1", "ebook", "Le systeme", sujet="s", dossier="/tmp")
        ventes.enregistrer({"date": "2026-08-01", "reference": "Le systeme",
                            "unites": 2, "brut": 58.0, "net": None,
                            "devise": "EUR", "remboursement": 0,
                            "plateforme": "gumroad", "empreinte": "r1"},
                           produit_id="p1")
        resume = ventes.resume_pour_ia()
        self.assertIn("Le systeme", resume)
        self.assertIn("58", resume)


if __name__ == "__main__":
    unittest.main()
