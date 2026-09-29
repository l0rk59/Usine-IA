"""Ce que l'acheteur trouve dans l'archive, et ce qu'il ne doit pas y trouver.

Mesure du 14/09/2026, sur les neuf chaines : TOUTES laissaient partir au moins
un fichier de travail.

```
ebook       carnet.json, rapport-qualite.json
nouvelle    bible.json, carnet.json, continuite.json, rapport-qualite.json
modeles     carnet.json, systeme.json
impression  cahier.json, carnet.json
logiciel    carnet.json, verification.json
les autres  carnet.json
```

L'acheteur ouvrait l'archive et y trouvait `rapport-qualite.json`, qui porte la
note interne de son propre produit — 3,79/10 dans la mesure — et la liste de
ses defauts ; et `carnet.json`, qui contient le texte de chaque section et la
ligne de commande exacte qui a fabrique le produit.

La cause n'est pas un oubli, c'est une FORME : une liste de noms tenue a la
main, ecrite une fois, que chaque fichier ajoute ensuite contourne sans que
rien ne le dise. Or chaque chaine declare deja ce qu'elle livre. L'archive se
construit desormais a partir de cette declaration ; la liste noire n'est plus
qu'un filet pour les appels qui n'ont pas la declaration sous la main.
"""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, store  # noqa: E402
from usine.packaging.livraison import (FICHIERS_AJOUTES,  # noqa: E402
                                       FICHIERS_INTERNES, empaqueter)


def setUpModule():
    atelier.isoler("archive-livree")


def _fabriquer_avec_zip(commande, extra=None):
    atelier.isoler("archive-" + commande)
    llm.definir_simulateur(simulateur)
    from usine import cli

    sortie = io.StringIO()
    try:
        with redirect_stdout(sortie), redirect_stderr(sortie):
            cli.principal([commande, "la gestion du temps en {}".format(commande),
                           "--sans-image", "-q", "rapide", "--zip"]
                          + (extra or []))
    finally:
        llm.definir_simulateur(None)
    produit = store.lister_produits(2)[0]
    dossier = Path(produit["dossier"])
    archive = next((f for f in dossier.glob("*.zip")), None)
    dans = set()
    if archive:
        with zipfile.ZipFile(archive) as contenu:
            dans = {Path(nom).name for nom in contenu.namelist()
                    if not nom.endswith("/")}
    return (produit.get("meta") or {}), dans, dossier


class L_AcheteurNeRecoitQueSonProduit(unittest.TestCase):

    CHAINES = ["ebook", "formation", "prompts", "outils", "social",
               "modeles", "impression", "logiciel", "nouvelle"]

    def test_aucune_chaine_ne_livre_de_fichier_de_travail(self):
        for commande in self.CHAINES:
            with self.subTest(chaine=commande):
                meta, dans, _dossier = _fabriquer_avec_zip(commande)
                declares = set(meta.get("fichiers") or [])
                self.assertTrue(declares, "la chaine ne declare rien")
                surplus = sorted(dans - declares - set(FICHIERS_AJOUTES))
                self.assertEqual(
                    surplus, [],
                    "« {} » livre a l'acheteur : {}".format(
                        commande, ", ".join(surplus)))

    def test_le_rapport_qualite_ne_part_jamais(self):
        """Le plus couteux des fichiers qui fuyaient : il porte la note du
        produit et la liste de ses defauts. Un acheteur qui l'ouvre lit
        « 3.79 / 10 » a propos de ce qu'il vient de payer."""
        _meta, dans, dossier = _fabriquer_avec_zip("ebook")
        self.assertTrue((dossier / "rapport-qualite.json").exists(),
                        "le rapport n'est plus produit : le test ne mesure "
                        "plus rien")
        self.assertNotIn("rapport-qualite.json", dans)

    def test_le_carnet_de_reprise_ne_part_jamais(self):
        """Il contient le texte de chaque section et la ligne de commande
        exacte qui a fabrique le produit."""
        _meta, dans, dossier = _fabriquer_avec_zip("ebook")
        self.assertTrue((dossier / "carnet.json").exists())
        self.assertNotIn("carnet.json", dans)

    def test_l_acheteur_recoit_bien_son_produit(self):
        """L'autre sens, et il compte autant : un filtre qui ne laisse rien
        passer livrerait une archive vide.

        Les deux noms sont ECRITS ICI, pas lus de « FICHIERS_AJOUTES ». Une
        premiere version bouclait sur cette constante — et vider la constante
        vidait la boucle : le test passait sur zero tour pendant que la notice
        et la licence disparaissaient de l'archive. Un test qui tire son
        attente de la chose qu'il controle ne controle rien.
        """
        meta, dans, _dossier = _fabriquer_avec_zip("ebook")
        declares = meta.get("fichiers") or []
        self.assertTrue(declares)
        for nom in declares:
            with self.subTest(fichier=nom):
                self.assertIn(nom, dans)
        for nom in ("LISEZ-MOI.md", "LICENCE.txt"):
            with self.subTest(fichier=nom):
                self.assertIn(nom, dans, "la notice et la licence sont "
                                         "ecrites par l'empaquetage et "
                                         "doivent partir avec le produit")

    def test_un_fichier_au_nom_imprevu_ne_part_pas(self):
        """Le coeur du sujet, et le seul cas que la liste noire ne peut pas
        couvrir.

        Une liste de noms ne connait que le passe : chaque fichier de travail
        ajoute plus tard la contourne. C'est ainsi que « carnet.json » et
        « rapport-qualite.json », tous deux posterieurs a la liste, sont
        partis chez des acheteurs. Le controle porte donc sur un nom que
        PERSONNE n'a prevu.
        """
        _meta, _dans, dossier = _fabriquer_avec_zip("ebook")
        intrus = dossier / "brouillon-interne-2026.json"
        intrus.write_text('{"note_reelle": 2.1}', encoding="utf-8")
        from usine.packaging.livraison import empaqueter

        produit = store.lister_produits(2)[0]
        archive = empaqueter(
            dossier, "essai-intrus", produit["titre"], "Auteur",
            livres=(produit.get("meta") or {}).get("fichiers"))
        with zipfile.ZipFile(archive) as contenu:
            dans = {Path(nom).name for nom in contenu.namelist()}
        self.assertNotIn("brouillon-interne-2026.json", dans,
                         "un fichier que la liste noire ne connait pas part "
                         "chez l'acheteur")
        self.assertIn("livre.md", dans, "le produit lui-meme doit passer")

    def test_la_couverture_dessinee_part_avec_le_livre(self):
        """Elle est declaree par la chaine, donc elle doit passer : un livre
        livre sans sa couverture serait le defaut inverse."""
        atelier.isoler("archive-couverture")
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["ebook", "un livre avec sa couverture",
                               "--chapitres", "2", "-q", "rapide", "--zip"])
        finally:
            llm.definir_simulateur(None)
        produit = store.lister_produits(2)[0]
        dossier = Path(produit["dossier"])
        images = [f.name for f in dossier.rglob("*") if f.suffix == ".png"]
        self.assertTrue(images, "aucune couverture : le test ne mesure rien")
        archive = next(f for f in dossier.glob("*.zip"))
        with zipfile.ZipFile(archive) as contenu:
            dans = {Path(nom).name for nom in contenu.namelist()}
        for image in images:
            with self.subTest(image=image):
                self.assertIn(image, dans)


class LesTroisCheminsFiltrentPareil(unittest.TestCase):
    """Une archive se fabrique a trois endroits : a la fin d'une chaine, par
    « usine livrer », et depuis le tableau de bord. Trois filtres differents
    finiraient par diverger, et c'est celui qu'on regarde le moins qui
    fuirait."""

    def _intrus_part_il(self, faire_l_archive):
        atelier.isoler("archive-chemin-" + str(id(faire_l_archive))[-6:])
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["ebook", "un livre a trois chemins",
                               "--chapitres", "2", "--sans-image", "-q",
                               "rapide"])
        finally:
            llm.definir_simulateur(None)
        produit = store.lister_produits(2)[0]
        dossier = Path(produit["dossier"])
        (dossier / "brouillon-interne-2026.json").write_text(
            "{}", encoding="utf-8")
        archive = faire_l_archive(produit, dossier)
        with zipfile.ZipFile(archive) as contenu:
            return {Path(nom).name for nom in contenu.namelist()}

    def test_la_fabrication_avec_zip_filtre(self):
        """Le troisieme chemin, et le plus emprunte : « --zip » a la fin
        d'une fabrication. On refabrique dans le MEME dossier — c'est ce que
        fait « usine reprendre » — apres y avoir depose un intrus, sinon le
        dossier est neuf et il n'y a rien a filtrer.
        """
        atelier.isoler("archive-zip-fabrication")
        llm.definir_simulateur(simulateur)
        from usine import cli

        sortie = io.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["ebook", "un livre refabrique sur place",
                               "--chapitres", "2", "--sans-image",
                               "-q", "rapide"])
            produit = store.lister_produits(2)[0]
            dossier = Path(produit["dossier"])
            (dossier / "brouillon-interne-2026.json").write_text(
                '{"note_reelle": 2.1}', encoding="utf-8")
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["ebook", "un livre refabrique sur place",
                               "--chapitres", "2", "--sans-image",
                               "-q", "rapide", "--zip",
                               "--reprendre-id", produit["id"]])
        finally:
            llm.definir_simulateur(None)
        archive = next(f for f in dossier.glob("*.zip"))
        with zipfile.ZipFile(archive) as contenu:
            dans = {Path(nom).name for nom in contenu.namelist()}
        self.assertNotIn("brouillon-interne-2026.json", dans,
                         "la fabrication avec « --zip » livre un fichier que "
                         "la liste noire ne connait pas")
        self.assertIn("livre.md", dans)

    def test_usine_livrer_filtre(self):
        def par_la_commande(produit, _dossier):
            from usine import cli

            sortie = io.StringIO()
            with redirect_stdout(sortie), redirect_stderr(sortie):
                cli.principal(["livrer", produit["id"]])
            dossier = Path(produit["dossier"])
            return next(f for f in dossier.glob("*.zip"))

        dans = self._intrus_part_il(par_la_commande)
        self.assertNotIn("brouillon-interne-2026.json", dans)
        self.assertIn("livre.md", dans)

    def test_le_tableau_de_bord_filtre(self):
        def par_le_serveur(produit, _dossier):
            from usine.web import serveur

            reponse, code = serveur.Gestionnaire._gerer_produit(
                None, {"action": "livrer", "id": produit["id"]})
            self.assertEqual(code, 200, reponse)
            dossier = Path(produit["dossier"])
            return next(f for f in dossier.glob("*.zip"))

        dans = self._intrus_part_il(par_le_serveur)
        self.assertNotIn("brouillon-interne-2026.json", dans)
        self.assertIn("livre.md", dans)


class LeFiletTientQuandLaDeclarationManque(unittest.TestCase):
    """« usine livrer » sur un produit d'avant, dont la fiche ne porte aucune
    liste de fichiers, doit encore filtrer."""

    def test_sans_liste_declaree_la_liste_noire_reprend_la_main(self):
        atelier.isoler("archive-filet")
        dossier = Path(store.__file__).parent  # un dossier quelconque
        with self.subTest(cas="fichiers internes couverts"):
            for nom in ("carnet.json", "rapport-qualite.json", "bible.json",
                        "continuite.json", "systeme.json", "cahier.json",
                        "verification.json"):
                self.assertIn(nom, FICHIERS_INTERNES,
                              "« {} » fuirait sur un produit sans "
                              "declaration".format(nom))
        self.assertTrue(dossier.exists())

    def test_le_filet_exclut_vraiment(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp) / "produit"
            dossier.mkdir()
            (dossier / "livre.md").write_text("# Titre\n", encoding="utf-8")
            (dossier / "carnet.json").write_text("{}", encoding="utf-8")
            archive = empaqueter(dossier, "essai", "Titre", "Auteur")
            with zipfile.ZipFile(archive) as contenu:
                dans = {Path(nom).name for nom in contenu.namelist()}
        self.assertIn("livre.md", dans)
        self.assertNotIn("carnet.json", dans)


class LArchiveEstRangeeAvecSonProduit(unittest.TestCase):
    """L'archive etait ecrite A COTE du dossier du produit, nommee d'apres le
    seul titre, dans un dossier commun a tous les produits.

    Mesure du 24/09/2026 : deux memos de meme titre — la meme niche
    refabriquee, que le cache resert avec le meme titre — et une seule
    archive sur le disque, celle du second. Le vendeur envoyait au client du
    premier le produit du second. Et le menu du telephone cherchait l'archive
    DANS le dossier : le partage ne la trouvait jamais.
    """

    def _memo(self, sujet, *extra):
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(sortie):
            from usine import cli

            cli.principal(["memo", sujet] + list(extra))

    def test_deux_produits_de_meme_titre_ont_chacun_leur_archive(self):
        atelier.isoler("archive-homonymes")
        llm.definir_simulateur(simulateur)
        try:
            self._memo("la tva des coiffeurs", "--zip")
            self._memo("la tva des coiffeurs", "--zip")
        finally:
            llm.definir_simulateur(None)
        produits = store.lister_produits(2)
        self.assertEqual(len({p["titre"] for p in produits}), 1,
                         "le cas exige deux titres identiques")
        archives = [sorted(Path(p["dossier"]).glob("*.zip")) for p in produits]
        self.assertEqual([len(a) for a in archives], [1, 1])
        self.assertNotEqual(archives[0][0], archives[1][0])

    def test_le_menu_partage_l_archive_que_livrer_a_ecrite(self):
        """Sans archive fabriquee a la main : c'est le vrai « livrer » qui
        l'ecrit, et le vrai menu qui la cherche."""
        from unittest import mock

        from usine import cli, menu

        atelier.isoler("archive-menu")
        llm.definir_simulateur(simulateur)
        try:
            self._memo("la paie des fleuristes")
            partagees = []
            entrees = iter(["1", "5", "o", ""])
            sortie = io.StringIO()
            with mock.patch("usine.core.telephone.partager",
                            lambda chemin, titre="": partagees.append(chemin)
                            or True), \
                    mock.patch("builtins.input",
                               lambda invite="": next(entrees)), \
                    redirect_stdout(sortie), redirect_stderr(sortie):
                menu.menu_produits(lambda arguments: cli.principal(list(arguments)))
        finally:
            llm.definir_simulateur(None)
        self.assertEqual(len(partagees), 1, sortie.getvalue()[-600:])
        self.assertTrue(zipfile.is_zipfile(partagees[0]))


if __name__ == "__main__":
    unittest.main()
