"""Le journal sur disque d'une production.

« config.LOG_DIR » etait cree a chaque demarrage et n'a jamais rien recu : le
dossier existait, la promesse aussi, et rien dedans. Ce que cela coutait :
l'usine continue tourne des heures sur un telephone dont Android reclame le
tampon du terminal, et une niche qui echoue a trois heures du matin ne
laissait aucune trace lisible.

Ces tests portent surtout sur les trois contraintes du telephone, parce que
ce sont elles qui ont dicte la forme du module : le processus meurt sans
preavis, le disque est fini, et une cle ne doit jamais toucher le disque.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, trace  # noqa: E402


def setUpModule():
    atelier.isoler("trace")


class BaseTrace(unittest.TestCase):
    def setUp(self):
        trace._secret_signale = False
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        for ancien in config.LOG_DIR.glob("usine-*.log"):
            ancien.unlink()


class TestEcriture(BaseTrace):
    def test_une_ligne_ecrite_se_relit(self):
        trace.ecrire("la niche a ete sautee")
        self.assertIn("la niche a ete sautee", "\n".join(trace.relire()))

    def test_la_categorie_apparait(self):
        trace.ecrire("demarrage", "usine")
        self.assertIn("[usine]", trace.relire()[0])

    def test_chaque_ligne_est_horodatee(self):
        """Un journal de plusieurs heures sans heure ne sert a rien."""
        trace.ecrire("quelque chose")
        self.assertRegex(trace.relire()[0], r"^\d{2}:\d{2}:\d{2} ")

    def test_une_ligne_vide_n_ecrit_rien(self):
        trace.ecrire("")
        trace.ecrire("   ")
        self.assertEqual(trace.relire(), [])

    def test_une_ligne_demesuree_est_coupee(self):
        trace.ecrire("x" * 5000)
        self.assertLess(len(trace.relire()[0]), trace.LIGNE_MAX + 40)

    def test_relire_rend_les_dernieres_lignes(self):
        for numero in range(50):
            trace.ecrire("ligne {}".format(numero))
        dernieres = trace.relire(5)
        self.assertEqual(len(dernieres), 5)
        self.assertIn("ligne 49", dernieres[-1])

    def test_relire_sans_journal_ne_leve_rien(self):
        self.assertEqual(trace.relire(), [])
        self.assertEqual(trace.jours_disponibles(), [])


class TestSecret(BaseTrace):
    """Une cle ne doit jamais toucher le disque — et le masquage doit se
    DIRE : masquer en silence laisse l'utilisateur avec une cle exposee
    quelque part et aucune raison de la renouveler."""

    CLE = "gsk_" + "a" * 40

    def test_la_cle_n_arrive_pas_sur_le_disque(self):
        trace.ecrire("echec avec " + self.CLE)
        contenu = trace.fichier().read_text(encoding="utf-8")
        self.assertNotIn(self.CLE, contenu)
        self.assertIn("[CLE MASQUEE]", contenu)

    def test_le_masquage_est_annonce(self):
        trace.ecrire("echec avec " + self.CLE)
        self.assertIn("renouvelez-la", trace.relire()[0])

    def test_l_alerte_ne_se_repete_pas(self):
        """Repetee a chaque ligne, elle deviendrait invisible — et c'est une
        alerte qu'il faut lire."""
        trace.ecrire("premier " + self.CLE)
        trace.ecrire("second " + self.CLE)
        lignes = trace.relire()
        self.assertIn("renouvelez-la", lignes[0])
        self.assertNotIn("renouvelez-la", lignes[1])

    def test_une_ligne_ordinaire_n_est_pas_alertee(self):
        trace.ecrire("tout va bien")
        self.assertNotIn("renouvelez-la", trace.relire()[0])


class TestDisque(BaseTrace):
    """Un journal qui remplit le telephone fait echouer la fabrication qu'il
    etait cense documenter."""

    def test_les_journaux_trop_anciens_sont_effaces(self):
        for jour in ("2020-01-{:02d}".format(n) for n in range(1, 21)):
            trace.fichier(jour).write_text("vieux\n", encoding="utf-8")
        supprimes = trace.nettoyer(jours_gardes=5)
        self.assertEqual(supprimes, 15)
        self.assertEqual(len(trace.jours_disponibles()), 5)

    def test_les_journaux_recents_survivent(self):
        trace.ecrire("aujourd'hui")
        trace.nettoyer(jours_gardes=14)
        self.assertTrue(trace.relire())

    def test_les_jours_sont_rendus_du_plus_recent_au_plus_ancien(self):
        for jour in ("2020-01-01", "2020-01-03", "2020-01-02"):
            trace.fichier(jour).write_text("x\n", encoding="utf-8")
        self.assertEqual(trace.jours_disponibles()[:3],
                         ["2020-01-03", "2020-01-02", "2020-01-01"])

    def test_un_disque_illisible_n_empeche_pas_de_produire(self):
        """Le journal est une trace, pas une fonction metier : il ne doit
        jamais faire echouer ce qu'il documente."""
        from unittest import mock

        with mock.patch("builtins.open", side_effect=OSError("disque plein")):
            trace.ecrire("une ligne")  # ne doit rien lever


class TestSurfaceDAttaque(BaseTrace):
    """Le jour vient d'un argument de ligne de commande, donc d'une chaine
    libre, et il finit dans un nom de fichier que « nettoyer » peut effacer."""

    def test_une_traversee_de_repertoire_retombe_sur_aujourd_hui(self):
        chemin = trace.fichier("../../etc/passwd")
        self.assertEqual(chemin.parent.resolve(), config.LOG_DIR.resolve())
        self.assertRegex(chemin.name, r"^usine-\d{4}-\d{2}-\d{2}\.log$")

    def test_une_date_valable_est_respectee(self):
        self.assertEqual(trace.fichier("2026-09-10").name, "usine-2026-09-10.log")

    def test_ce_qui_n_est_pas_une_date_retombe_sur_aujourd_hui(self):
        for brut in ("", "hier", "2026-9-1", "2026-09-10/../x", None):
            with self.subTest(jour=brut):
                self.assertEqual(trace.fichier(brut).name,
                                 trace.fichier().name)

    def test_relire_ne_sort_pas_du_dossier(self):
        ailleurs = config.LOG_DIR.parent / "secret.txt"
        ailleurs.write_text("ne doit pas etre lu\n", encoding="utf-8")
        try:
            self.assertNotIn("ne doit pas etre lu",
                             "\n".join(trace.relire(jour="../secret")))
        finally:
            ailleurs.unlink()

    def test_un_fichier_trop_gros_repart_de_zero(self):
        """Un journal qui remplit le telephone fait echouer la fabrication
        qu'il etait cense documenter."""
        trace.fichier().write_text("x" * (trace.TAILLE_MAX + 10), encoding="utf-8")
        trace.ecrire("apres la bascule")
        contenu = trace.fichier().read_text(encoding="utf-8")
        self.assertLess(len(contenu), 1000)
        self.assertIn("apres la bascule", contenu)

    def test_un_fichier_normal_continue_de_grossir(self):
        trace.ecrire("premiere")
        trace.ecrire("seconde")
        self.assertEqual(len(trace.relire()), 2)


class TestBrancheDansLaProduction(unittest.TestCase):
    """Du code sans appelant ne protege personne."""

    def test_le_journal_de_l_usine_continue_ecrit_sur_disque(self):
        from usine.production import UsineContinue

        for ancien in config.LOG_DIR.glob("usine-*.log"):
            ancien.unlink()
        usine = UsineContinue(journal=lambda _m: None)
        usine.journal("une niche a ete sautee")
        self.assertIn("une niche a ete sautee", "\n".join(trace.relire()))

    def test_ce_qui_est_dit_a_l_ecran_l_est_aussi(self):
        """Le journal double l'affichage, il ne le remplace pas."""
        from usine.production import UsineContinue

        vus = []
        usine = UsineContinue(journal=vus.append)
        usine.journal("visible")
        self.assertEqual(vus, ["visible"])


if __name__ == "__main__":
    unittest.main()
