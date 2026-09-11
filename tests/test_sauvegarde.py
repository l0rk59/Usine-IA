"""Sauvegarde et restauration de l'atelier.

Ce qui se perd avec `usine.db` n'est pas remplacable. Les produits se
refabriquent ; une annee de ventes importees, non. Et l'usine tourne sur un
telephone, dont le dossier de travail est souvent sous /sdcard.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("USINE_HOME", tempfile.mkdtemp(prefix="usine-sauve-"))

from usine.core import config, reglages, sauvegarde, store, ventes  # noqa: E402


def _peupler():
    store.creer_produit("sauve-p1", "ebook", "Un livre", sujet="un sujet",
                        dossier=str(config.PRODUITS_DIR / "sauve-p1"))
    ventes.enregistrer({"date": "2026-08-01", "reference": "Un livre",
                        "unites": 2, "brut": 58.0, "net": 50.0,
                        "devise": "EUR", "remboursement": 0,
                        "plateforme": "gumroad", "empreinte": "sauve-v1"},
                       produit_id="sauve-p1")


def _sinistre():
    """Efface la base comme le ferait une application de nettoyage."""
    store.close()
    config.DB_PATH.unlink(missing_ok=True)
    for suffixe in ("-wal", "-shm"):
        Path(str(config.DB_PATH) + suffixe).unlink(missing_ok=True)


class TestArchive(unittest.TestCase):

    def test_l_archive_contient_la_base_et_les_reglages(self):
        reglages.ecrire({"auteur": "Claire Fontaine"})
        archive = sauvegarde.creer()
        with zipfile.ZipFile(archive) as zip_:
            noms = set(zip_.namelist())
        self.assertIn("usine.db", noms)
        self.assertIn("reglages.json", noms)
        self.assertIn("sauvegarde.json", noms)

    def test_les_cles_api_ne_sont_jamais_dans_l_archive(self):
        """Une archive se copie sur un ordinateur ou dans un nuage."""
        os.environ["GROQ_API_KEY"] = "gsk_" + "S" * 32
        try:
            archive = sauvegarde.creer()
            self.assertNotIn(b"gsk_SSS", archive.read_bytes())
        finally:
            os.environ.pop("GROQ_API_KEY", None)

    def test_les_produits_sont_exclus_par_defaut(self):
        dossier = config.PRODUITS_DIR / "sauve-p1"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "livre.md").write_text("du texte", encoding="utf-8")
        with zipfile.ZipFile(sauvegarde.creer()) as zip_:
            self.assertFalse([n for n in zip_.namelist()
                              if n.startswith("produits/")])
        with zipfile.ZipFile(sauvegarde.creer(avec_produits=True)) as zip_:
            self.assertTrue([n for n in zip_.namelist()
                             if n.startswith("produits/")])

    def test_la_base_copiee_est_lisible(self):
        """Copiee par l'API SQLite, pas par un copier-coller de fichier."""
        _peupler()
        archive = sauvegarde.creer()
        extrait = Path(tempfile.mkdtemp()) / "extrait.db"
        with zipfile.ZipFile(archive) as zip_:
            extrait.write_bytes(zip_.read("usine.db"))
        connexion = sqlite3.connect(str(extrait))
        try:
            self.assertEqual(
                connexion.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertGreaterEqual(
                connexion.execute("SELECT COUNT(*) FROM ventes").fetchone()[0], 1)
        finally:
            connexion.close()

    def test_inspecter_ne_change_rien_et_refuse_ce_qui_n_est_pas_une_archive(self):
        faux = Path(tempfile.mkdtemp()) / "faux.zip"
        faux.write_text("ceci n'est pas une archive", encoding="utf-8")
        self.assertFalse(sauvegarde.inspecter(faux)["valide"])
        self.assertFalse(sauvegarde.inspecter(faux / "absent")["valide"])

        vide = Path(tempfile.mkdtemp()) / "vide.zip"
        with zipfile.ZipFile(vide, "w") as zip_:
            zip_.writestr("autre.txt", "x")
        fiche = sauvegarde.inspecter(vide)
        self.assertFalse(fiche["valide"])
        self.assertIn("base de donnees", fiche["probleme"])


class TestRestauration(unittest.TestCase):

    def test_les_ventes_survivent_a_la_perte_de_la_base(self):
        _peupler()
        reglages.ecrire({"auteur": "Claire Fontaine", "marque": "Atelier Nord"})
        archive = sauvegarde.creer()

        _sinistre()
        reglages.reinitialiser()
        self.assertEqual(ventes.total_par_devise(), [])
        self.assertNotEqual(reglages.lire("auteur"), "Claire Fontaine")

        resultat = sauvegarde.restaurer(archive)
        self.assertTrue(resultat["valide"], resultat.get("probleme"))
        totaux = ventes.total_par_devise()
        self.assertTrue(totaux)
        self.assertEqual(reglages.lire("auteur"), "Claire Fontaine")
        self.assertEqual(reglages.lire("marque"), "Atelier Nord")
        self.assertEqual(store.lire_produit("sauve-p1")["titre"], "Un livre")

    def test_la_base_restauree_repasse_par_les_migrations(self):
        """« _schema_pret » survivait a la fermeture.

        Sans l'oubli du drapeau, la reconnexion sautait la creation des
        tables ET l'echelle de migrations : une archive plus ancienne
        revenait avec son schema d'origine, et la premiere requete sur une
        table recente echouait.
        """
        archive = sauvegarde.creer()
        _sinistre()
        sauvegarde.restaurer(archive)
        with store.cursor() as cur:
            version = cur.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, store.VERSION_SCHEMA)

    def test_l_ancienne_base_est_mise_de_cote_pas_supprimee(self):
        """Restaurer par erreur ne doit pas etre irreversible."""
        _peupler()
        archive = sauvegarde.creer()
        resultat = sauvegarde.restaurer(archive)
        ecarte = Path(resultat["ancienne_base"])
        self.assertTrue(ecarte.exists(), "l'ancienne base doit etre conservee")
        self.assertGreater(ecarte.stat().st_size, 0)

    def test_une_archive_d_une_version_plus_recente_est_refusee(self):
        """Mieux vaut refuser que d'ecrire un schema qu'on ne sait pas lire."""
        archive = sauvegarde.creer()
        futur = Path(tempfile.mkdtemp()) / "futur.zip"
        with zipfile.ZipFile(archive) as source:
            contenu = {n: source.read(n) for n in source.namelist()}
        import json

        fiche = json.loads(contenu["sauvegarde.json"].decode("utf-8"))
        fiche["schema"] = store.VERSION_SCHEMA + 5
        contenu["sauvegarde.json"] = json.dumps(fiche).encode("utf-8")
        with zipfile.ZipFile(futur, "w") as cible:
            for nom, octets in contenu.items():
                cible.writestr(nom, octets)
        resultat = sauvegarde.restaurer(futur)
        self.assertFalse(resultat["valide"])
        self.assertIn("plus recente", resultat["probleme"])

    def test_les_produits_reviennent_quand_ils_sont_dans_l_archive(self):
        dossier = config.PRODUITS_DIR / "sauve-p1"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "livre.md").write_text("contenu original", encoding="utf-8")
        archive = sauvegarde.creer(avec_produits=True)
        (dossier / "livre.md").unlink()

        resultat = sauvegarde.restaurer(archive)
        self.assertTrue(resultat["valide"])
        self.assertEqual((dossier / "livre.md").read_text(encoding="utf-8"),
                         "contenu original")


if __name__ == "__main__":
    unittest.main()
