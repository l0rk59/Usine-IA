"""L'usine choisit ses niches au lieu d'attendre qu'on les lui donne.

Le remplissage automatique existait, mais il partait du dernier produit
fabrique, explorait sans aucune mesure, et ne verifiait pas si la piste
avait deja ete traitee.
"""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("USINE_HOME", tempfile.mkdtemp(prefix="usine-prosp-"))

from usine import production  # noqa: E402
from usine.core import apprentissage, empreinte, file, store, ventes  # noqa: E402


def _vider():
    with store.cursor() as cur:
        for table in ("ventes", "produits", "empreintes", "file_production"):
            try:
                cur.execute("DELETE FROM {}".format(table))
            except Exception:
                pass
    try:
        with store.cursor() as cur:
            cur.execute("DELETE FROM productions")
    except Exception:
        pass


def _produire(sujet, note=5.0, produit_id=""):
    produit_id = produit_id or sujet.replace(" ", "-")
    store.creer_produit(produit_id, "ebook", sujet.title(), sujet=sujet,
                        dossier="/tmp")
    apprentissage.enregistrer(
        produit_id=produit_id, type_produit="ebook", sujet=sujet, audience="",
        ton="pro", taille="mini", qualite="standard", note=note,
        note_avant=note, mots=100, sections=2, duree=1.0, appels=1,
        fournisseurs="x", defauts=[])
    return produit_id


class TestGraine(unittest.TestCase):
    """« On part des sujets qui ont donne les meilleures notes », disait le
    commentaire. Le code prenait le plus RECENT."""

    def setUp(self):
        _vider()

    def test_la_meilleure_note_l_emporte_sur_la_plus_recente(self):
        _produire("la niche mediocre", note=3.0)
        _produire("la niche excellente", note=9.5)
        _produire("la niche recente", note=4.0)
        self.assertEqual(production.graine_de_depart(), "la niche excellente")

    def test_ce_qui_a_rapporte_l_emporte_sur_ce_qui_note_bien(self):
        """Le revenu mesure le marche, la note mesure l'usine."""
        _produire("la niche excellente", note=9.5)
        identifiant = _produire("la niche qui vend", note=3.0)
        ventes.enregistrer({"date": "2026-08-01", "reference": "x",
                            "unites": 4, "brut": 120.0, "net": None,
                            "devise": "EUR", "remboursement": 0,
                            "plateforme": "g", "empreinte": "pv1"},
                           produit_id=identifiant)
        self.assertEqual(production.graine_de_depart(), "la niche qui vend")

    def test_sans_historique_il_n_y_a_pas_de_graine(self):
        self.assertEqual(production.graine_de_depart(), "")


class TestProspection(unittest.TestCase):

    def setUp(self):
        _vider()
        self._ancien = production.idees.produire

    def tearDown(self):
        production.idees.produire = self._ancien

    def _pistes(self, titres, appels=None):
        def faux(contexte, nombre=12, avec_marche=True, avec_veille=True):
            if appels is not None:
                appels.append({"sujet": contexte.sujet,
                               "avec_marche": avec_marche,
                               "avec_veille": avec_veille})
            return {"idees": [{"titre": t, "type": "ebook", "acheteur": "x"}
                              for t in titres]}
        production.idees.produire = faux

    def test_sans_graine_rien_n_est_mis_en_file(self):
        self._pistes(["une piste"])
        journal = []
        rapport = production.prospecter(journal=journal.append)
        self.assertEqual(rapport["ajoutees"], 0)
        self.assertEqual(rapport["graine"], "")
        self.assertTrue(any("a la main" in ligne for ligne in journal))

    def test_les_pistes_nouvelles_entrent_en_file(self):
        _produire("la prospection pour freelances", note=8.0)
        self._pistes(["le jardinage sur balcon", "la couture pour debutants"])
        rapport = production.prospecter()
        self.assertEqual(rapport["ajoutees"], 2)
        self.assertEqual(file.compter()["en_attente"], 2)

    def test_une_piste_deja_fabriquee_est_ecartee_avant_la_file(self):
        """La file ne se dedoublonne que sur elle-meme.

        Sans ce filtre, l'usine refabriquait une niche deja traitee, et
        « usine doublons » ne le signalait qu'apres coup, le quota depense.
        """
        identifiant = _produire("la prospection pour freelances", note=8.0)
        empreinte_ok = store.enregistrer_empreinte(
            identifiant, "ebook", "Le systeme du freelance",
            "la prospection pour freelances", "[]", "[]", 100)
        self._pistes(["Prospection freelance", "le jardinage sur balcon"])
        rapport = production.prospecter()
        self.assertEqual(rapport["ajoutees"], 1)
        self.assertEqual(len(rapport["ecartees"]), 1)
        self.assertEqual(rapport["ecartees"][0][0], "Prospection freelance")
        self.assertEqual(file.compter()["en_attente"], 1)

    def test_l_exploration_s_appuie_sur_les_mesures_et_les_discussions(self):
        """Le remplissage automatique se passait des deux."""
        _produire("une niche", note=7.0)
        appels = []
        self._pistes(["une piste"], appels)
        production.prospecter()
        self.assertTrue(appels[0]["avec_marche"])
        self.assertTrue(appels[0]["avec_veille"])

    def test_la_veille_se_coupe_a_la_demande(self):
        _produire("une niche", note=7.0)
        appels = []
        self._pistes(["une piste"], appels)
        production.prospecter(avec_veille=False)
        self.assertFalse(appels[0]["avec_veille"])
        self.assertTrue(appels[0]["avec_marche"])

    def test_une_graine_imposee_court_circuite_le_classement(self):
        _produire("la niche la mieux notee", note=9.9)
        appels = []
        self._pistes(["une piste"], appels)
        production.prospecter(graine="une autre niche")
        self.assertEqual(appels[0]["sujet"], "une autre niche")

    def test_une_exploration_qui_echoue_ne_fait_pas_tomber_l_usine(self):
        _produire("une niche", note=7.0)

        def casse(*args, **kwargs):
            raise RuntimeError("plus de quota")

        production.idees.produire = casse
        journal = []
        rapport = production.prospecter(journal=journal.append)
        self.assertEqual(rapport["ajoutees"], 0)
        self.assertTrue(any("impossible" in ligne for ligne in journal))

    def test_deux_prospections_de_suite_n_empilent_pas_les_doublons(self):
        _produire("une niche", note=7.0)
        self._pistes(["le jardinage sur balcon"])
        production.prospecter()
        production.prospecter()
        self.assertEqual(file.compter()["en_attente"], 1)


if __name__ == "__main__":
    unittest.main()
