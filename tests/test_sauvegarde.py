"""Sauvegarde et restauration de l'atelier.

Ce qui se perd avec `usine.db` n'est pas remplacable. Les produits se
refabriquent ; une annee de ventes importees, non. Et l'usine tourne sur un
telephone, dont le dossier de travail est souvent sous /sdcard.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import sys
import unittest
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, reglages, sauvegarde, store, ventes  # noqa: E402
from usine.core import file as file_prod  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("sauvegarde")


def _peupler():
    store.creer_produit("sauve-p1", "ebook", "Un livre", sujet="un sujet",
                        dossier=str(config.PRODUITS_DIR / "sauve-p1"))
    ventes.enregistrer({"date": "2026-08-01", "reference": "Un livre",
                        "unites": 2, "brut": 58.0, "net": 50.0,
                        "devise": "EUR", "remboursement": 0,
                        "plateforme": "gumroad", "empreinte": "sauve-v1"},
                       produit_id="sauve-p1")


def _archive_ancienne(nettoyer):
    """Une archive dont la base n'a QUE le schema de base de store.

    C'est l'etat d'une sauvegarde ecrite avant que la file de production
    n'existe : les tables creees a la demande n'y sont pas.
    """
    dossier = Path(tempfile.mkdtemp(prefix="usine-archive-"))
    nettoyer(shutil.rmtree, str(dossier), True)
    base = dossier / "ancienne.db"
    connexion = sqlite3.connect(str(base))
    try:
        connexion.executescript(store.SCHEMA)
        connexion.execute("PRAGMA user_version = {}".format(
            store.VERSION_SCHEMA))
        connexion.commit()
    finally:
        connexion.close()

    archive = dossier / "ancienne.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.write(base, sauvegarde.NOM_BASE)
        zip_.writestr(sauvegarde.NOM_FICHE, json.dumps(
            {"version": sauvegarde.VERSION, "cree_le": "2026-01-01T00:00:00Z",
             "avec_produits": False, "fichiers_produits": 0,
             "schema": store.VERSION_SCHEMA}))
    return archive


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

    def test_restaurer_une_archive_d_avant_la_file_la_recree(self):
        """Les tables nees a la demande doivent renaitre apres restauration.

        « _schema_pret » n'etait pas le seul drapeau de ce genre : la file,
        les experiences et l'apprentissage creent leurs tables au premier
        usage et retenaient « c'est fait » chacun de leur cote. Restaurer
        une archive anterieure a l'ajout de la file laissait donc le
        processus convaincu que « file_production » existait, et la
        premiere requete levait « no such table ».
        """
        file_prod.ajouter("un sujet de la file", "ebook")   # drapeau leve
        archive = _archive_ancienne(self.addCleanup)

        sauvegarde.restaurer(archive, avec_produits=False)

        self.assertEqual(file_prod.lister(), [])
        self.assertEqual(file_prod.compter()["en_attente"], 0)
        identifiant = file_prod.ajouter("apres restauration", "ebook")
        self.assertTrue(identifiant)

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


class TestArchiveHostile(unittest.TestCase):
    """Une archive passe par un ordinateur ou un nuage. Elle peut revenir
    modifiee."""

    def _piegee(self, entrees):
        archive = sauvegarde.creer()
        piege = Path(tempfile.mkdtemp()) / "piege.zip"
        with zipfile.ZipFile(archive) as source:
            contenu = {n: source.read(n) for n in source.namelist()}
        with zipfile.ZipFile(piege, "w") as cible:
            for nom, octets in contenu.items():
                cible.writestr(nom, octets)
            for nom, octets in entrees:
                cible.writestr(nom, octets)
        return piege

    def test_une_entree_qui_remonte_les_dossiers_est_refusee(self):
        temoin = config.PRODUITS_DIR.parent.parent / "evade.txt"
        temoin.unlink(missing_ok=True)
        piege = self._piegee([
            ("produits/../../evade.txt", b"sorti"),
            ("produits/legitime/ok.md", b"normal"),
        ])
        resultat = sauvegarde.restaurer(piege)
        self.assertTrue(resultat["valide"])
        self.assertFalse(temoin.exists(), "rien ne doit sortir de l'atelier")
        self.assertIn("produits/../../evade.txt", resultat["refuses"])
        self.assertTrue((config.PRODUITS_DIR / "legitime" / "ok.md").exists(),
                        "une entree normale doit passer")

    def test_un_chemin_absolu_est_refuse(self):
        piege = self._piegee([("produits//tmp/absolu.txt", b"x")])
        resultat = sauvegarde.restaurer(piege)
        self.assertTrue(resultat["refuses"])
        self.assertFalse(Path("/tmp/absolu.txt").exists())


if __name__ == "__main__":
    unittest.main()
