"""Les CSV livres a l'acheteur ne doivent pas s'executer chez lui.

Un CSV produit par l'usine n'est pas un fichier de travail : les modeles
Notion, le calendrier editorial et les tableaux de la boite a outils partent
tels quels chez l'acheteur. Excel, LibreOffice et Google Sheets interpretent
comme une FORMULE toute cellule commencant par « = », « + », « - » ou « @ ».

Le contenu vient d'un modele de langage, nourri entre autres de titres Hacker
News et de questions Stack Exchange recuperes sur internet.
"""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("USINE_HOME", tempfile.mkdtemp(prefix="usine-tableur-"))

from usine.render import tableur  # noqa: E402

HOSTILES = [
    '=HYPERLINK("http://exemple.test/vol","Cliquez ici")',
    '=cmd|\'/c calc\'!A1',
    "+1+1",
    "-2+3",
    "@SUM(1:10)",
    "\t=1+1",
    "\r=1+1",
]

LEGITIMES = [
    "-50 % de temps passe",      # devient #NAME? sans protection
    "+33 6 12 34 56 78",
    "@ retenir",
]


class TestEchappement(unittest.TestCase):

    def test_toute_amorce_de_formule_est_neutralisee(self):
        for valeur in HOSTILES + LEGITIMES:
            self.assertTrue(tableur.cellule(valeur).startswith("'"),
                            "non neutralise : {!r}".format(valeur))

    def test_le_contenu_reste_entier(self):
        """L'apostrophe marque le texte, elle ne tronque rien."""
        for valeur in HOSTILES + LEGITIMES:
            self.assertEqual(tableur.cellule(valeur)[1:], valeur)

    def test_un_texte_ordinaire_n_est_pas_touche(self):
        for valeur in ("Texte normal", "1-2-3", "Prix : 29 EUR", "", "a=b"):
            self.assertEqual(tableur.cellule(valeur), valeur)

    def test_les_nombres_et_les_vides_passent(self):
        self.assertEqual(tableur.cellule(29), "29")
        self.assertEqual(tableur.cellule(None), "")
        self.assertEqual(tableur.cellule(12.5), "12.5")

    def test_un_csv_ecrit_se_relit_a_l_identique(self):
        chemin = Path(tempfile.mkdtemp()) / "t.csv"
        tableur.ecrire(chemin, ["Colonne", "Valeur"],
                       [["=danger", "-50 %"], ["ok", "normal"]])
        with chemin.open(encoding="utf-8", newline="") as flux:
            lignes = list(csv.reader(flux))
        self.assertEqual(lignes[0], ["Colonne", "Valeur"])
        self.assertEqual(lignes[1], ["'=danger", "'-50 %"])
        self.assertEqual(lignes[2], ["ok", "normal"])


class TestLivrables(unittest.TestCase):
    """Le vrai test : une charge hostile traversee par les chaines reelles."""

    CHARGE = '=HYPERLINK("http://exemple.test","clic")'

    def _contexte(self):
        from usine.pipelines.base import Contexte, preparer

        contexte = Contexte(sujet="essai", sans_image=True, hors_ligne=True,
                            journal=lambda message: None)
        preparer(contexte, "outils", "Essai")
        return contexte

    def test_un_tableau_livre_neutralise_la_charge(self):
        from usine.render import livraison

        contexte = self._contexte()
        produit = livraison.Produit(
            type="outils", titre="Essai", formats=("md",),
            tableaux=[livraison.Tableau(
                nom="tableau", colonnes=["Colonne", self.CHARGE],
                lignes=[[self.CHARGE, "normal"], ["-10 %", "+5"]])])
        livraison.livrer(contexte, produit)
        brut = (contexte.dossier / "tableau.csv").read_text(encoding="utf-8")
        self.assertNotIn("\n=HYPERLINK", brut)
        self.assertNotIn(",=HYPERLINK", brut)
        with (contexte.dossier / "tableau.csv").open(encoding="utf-8",
                                                     newline="") as flux:
            lignes = list(csv.reader(flux))
        for ligne in lignes:
            for cellule in ligne:
                self.assertFalse(
                    cellule.startswith(tableur.AMORCES),
                    "cellule executable livree : {!r}".format(cellule))

    def test_aucune_chaine_n_ecrit_de_csv_sans_passer_par_le_module(self):
        """Verrou : une chaine qui ecrirait son CSV en direct echapperait au filtre."""
        import re

        racine = Path(__file__).resolve().parent.parent / "usine"
        coupables = []
        for fichier in racine.rglob("*.py"):
            if fichier.name == "tableur.py":
                continue
            texte = fichier.read_text(encoding="utf-8")
            for numero, ligne in enumerate(texte.splitlines(), 1):
                if re.search(r"\.writerows?\(", ligne) and "tableur." not in ligne:
                    # writerow(tableur.ligne(...)) est sur ; writerow([...]) ne l'est pas.
                    suite = "\n".join(texte.splitlines()[numero - 1:numero + 4])
                    if "tableur." not in suite:
                        coupables.append("{}:{}".format(
                            fichier.relative_to(racine), numero))
        self.assertFalse(
            coupables,
            "ecriture CSV sans echappement : " + ", ".join(coupables))


if __name__ == "__main__":
    unittest.main()
