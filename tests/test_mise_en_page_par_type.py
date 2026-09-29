"""Un sommaire coute une page pleine. Tous les produits la payaient.

Mesure du 15/09/2026, en fabriquant les dix-huit types et en COMPTANT les
pages des PDF livres :

    memo     6 pages, dont une de sommaire — pour un type dont la docstring
             dit « l'antiseche d'une ou deux pages » et « un memo de neuf
             pages n'est plus un memo, c'est un ebook rate »
    social   4 pages, dont une de sommaire : un quart du document, pour
             lister « Mode d'emploi » et quatre jours numerotes
    quiz     5 pages, sommaire de trois entrees — Consignes, Questions,
             Corrige — qu'on trouve en tournant la page
    interactive  sommaire de deux entrees sur sept pages, alors qu'un
             livre-jeu se navigue par NUMEROS de section

Le sommaire vaut sa page dans un livre, ou l'on cherche le chapitre neuf. Il
ne la vaut pas dans une fiche. C'est la chaine qui declare, parce qu'elle
seule sait si son produit est un livre ou une carte — un seuil en nombre de
pages serait un chiffre invente, et il se tromperait sur un ebook court comme
sur un memo long.

Et le memo composait un bloc par PAGE : le moteur commun ouvre une nouvelle
page a chaque titre de niveau 1. Quatre blocs faisaient quatre pages.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("mise-en-page")


from usine.core import llm  # noqa: E402
from usine.pipelines import base, catalogue  # noqa: E402
from tests import simulateur  # noqa: E402

# Les objets qui ne sont pas des livres. Le reste garde son sommaire.
SANS_SOMMAIRE = ("memo", "quiz", "social", "interactive")


def _pages(chemin):
    return len(re.findall(rb"/Type\s*/Page[^s]", chemin.read_bytes()))


def _fabriquer(cle, sujet, **options):
    llm.definir_simulateur(simulateur.simulateur)
    try:
        contexte = base.Contexte(sujet=sujet, sans_image=True,
                                 journal=lambda m: None)
        contexte.chapitres = 3
        resume = catalogue.executer(cle, contexte, options)
    finally:
        llm.definir_simulateur(None)
    return Path(resume["dossier"]), resume


class UneFicheNePaiePasUnePageDeSommaire(unittest.TestCase):

    def _contenu(self, pdf):
        import zlib

        morceaux = []
        for flux in re.findall(rb"stream\r?\n(.*?)\r?\nendstream",
                               pdf.read_bytes(), re.DOTALL):
            try:
                morceaux.append(zlib.decompress(flux).decode("latin-1"))
            except zlib.error:
                pass
        return "\n".join(morceaux)

    def test_les_fiches_n_ont_pas_de_page_de_sommaire(self):
        for cle, sujet in (("memo", "les raccourcis du terminal"),
                           ("quiz", "le droit du travail"),
                           ("social", "la facturation"),
                           ("interactive", "une gare abandonnee")):
            with self.subTest(type=cle):
                dossier, _ = _fabriquer(cle, sujet, nombre=4)
                pdf = next(dossier.glob("*.pdf"))
                self.assertNotIn("Sommaire", self._contenu(pdf))

    def test_un_livre_garde_le_sien(self):
        """La correction retire une page a QUATRE types. La retirer a tous
        serait la deuxieme facon de se tromper : dans un ebook, on cherche le
        chapitre neuf."""
        dossier, _ = _fabriquer("ebook", "la facturation des independants")
        pdf = next(dossier.glob("*.pdf"))
        self.assertIn("Sommaire", self._contenu(pdf))

    def test_les_types_qui_declinent_sont_nommes_et_pas_devines(self):
        for cle in SANS_SOMMAIRE:
            with self.subTest(type=cle):
                self.assertIsNotNone(catalogue.obtenir(cle))


class UnMemoTientSurUneFeuille(unittest.TestCase):
    """Le type dont la docstring dit « une ou deux pages » en faisait six."""

    def test_les_blocs_se_suivent_au_lieu_d_ouvrir_chacun_sa_page(self):
        dossier, resume = _fabriquer("memo", "les raccourcis du clavier",
                                     nombre=4)
        pdf = next(dossier.glob("*.pdf"))
        # Couverture + le contenu. Quatre blocs ne font plus quatre pages.
        self.assertLessEqual(_pages(pdf), 3, (
            "un memo de {} pages n'est plus un memo".format(_pages(pdf))))
        self.assertEqual(resume["blocs"], 4)

    def test_le_contenu_ne_s_imprime_pas_par_dessus_la_couverture(self):
        """La premiere correction supprimait TOUS les sauts de page, et le
        memo tombait a une seule page — le compte exact que la docstring
        reclame. Il a fallu ouvrir le PDF pour voir le texte sombre imprime
        sur la couverture sombre. Compter les pages ne suffisait pas.
        """
        dossier, _ = _fabriquer("memo", "les commandes git", nombre=4)
        pdf = next(dossier.glob("*.pdf"))
        self.assertGreaterEqual(_pages(pdf), 2, (
            "une seule page : le contenu est dessine sur la couverture"))

    def test_la_couverture_n_annonce_plus_une_page_qui_n_existe_pas(self):
        """Elle imprimait « sur une page » sur un PDF de six pages."""
        dossier, _ = _fabriquer("memo", "les raccourcis du navigateur",
                                nombre=4)
        markdown = (dossier / "memo.md").read_text(encoding="utf-8")
        self.assertNotIn("sur une page", markdown)
        self.assertIn("4 blocs", markdown)


class UneNoticeTechniqueNEstPasUnLivre(unittest.TestCase):
    """Un titre de niveau 1 ouvre une page neuve — juste dans un livre.

    Mesure du 15/09/2026 sur la notice d'un outil logiciel : trois sections,
    trois pages, et les deux tiers bas de chacune blancs. Cinq pages dont
    trois quasi vides, pour un document qu'on lit a l'ecran comme un fichier
    « LISEZ-MOI ».
    """

    def test_les_sections_d_une_notice_s_enchainent(self):
        dossier, _ = _fabriquer("logiciel", "un convertisseur de devises")
        pdf = next(dossier.glob("*.pdf"))
        self.assertLessEqual(_pages(pdf), 3, (
            "{} pages pour trois sections courtes".format(_pages(pdf))))

    def test_le_contenu_ne_s_imprime_pas_sur_la_couverture(self):
        """Compter les pages ne suffit pas : un document assez long deborde
        de la couverture sur une deuxieme page, et le compte parait juste
        pendant que la premiere page est illisible. On regarde donc ce que la
        page de couverture PORTE."""
        import zlib

        dossier, _ = _fabriquer("logiciel", "un verificateur de liens")
        pdf = next(dossier.glob("*.pdf"))
        flux = re.findall(rb"stream\r?\n(.*?)\r?\nendstream",
                          pdf.read_bytes(), re.DOTALL)
        premiere = ""
        for brut in flux:
            try:
                contenu = zlib.decompress(brut).decode("latin-1")
            except zlib.error:
                continue
            if " Tm " in contenu:
                premiere = contenu
                break
        self.assertNotIn("Ce que fait cet outil", premiere, (
            "le contenu est dessine sur la couverture"))

    def test_une_notice_garde_une_couverture_a_elle(self):
        dossier, _ = _fabriquer("logiciel", "un renommeur de fichiers")
        self.assertGreaterEqual(_pages(next(dossier.glob("*.pdf"))), 2)

    def test_un_livre_garde_une_page_par_chapitre(self):
        """La correction vise UNE chaine. Le defaut par defaut doit rester
        « une page par chapitre », sinon les chapitres d'un roman coulent les
        uns dans les autres.

        Mesure sur le MECANISME et non sur un produit : le texte d'un ebook
        reel remplit ses pages de toute facon, et le compte ne distingue alors
        plus les deux mises en page. Une campagne de mutation l'a montre —
        basculer le defaut ne faisait echouer aucun test.

        Et il faut une mesure qui NE PASSE PAS le reglage : les chaines qui ne
        declarent rien sont justement celles que le defaut protege. Tant que
        les deux mesures le passaient toutes les deux, basculer le defaut a
        « enchainees » restait invisible — les dix-sept autres chaines
        auraient coule leurs chapitres les uns dans les autres sans qu'un seul
        test bronche.
        """
        from usine.render import livraison

        blocs = [livraison.Bloc(titre="Chapitre {}".format(rang),
                                corps="Une ligne.") for rang in range(1, 6)]
        contexte = base.Contexte(sujet="essai", sans_image=True,
                                 journal=lambda m: None)
        contexte.dossier = Path(atelier.isoler("mise-en-page")) / "livre"
        contexte.dossier.mkdir(parents=True, exist_ok=True)

        def pages_pour(enchainees, nom):
            reglage = {} if enchainees is None else {
                "sections_enchainees": enchainees}
            produit = livraison.Produit(
                type="ebook", titre="Essai", blocs=blocs, formats=("pdf",),
                sommaire=False, nom_fichier=nom, **reglage)
            fichiers = livraison.livrer(contexte, produit)
            return _pages(next(f for f in fichiers if f.suffix == ".pdf"))

        separees = pages_pour(False, "separe")
        enchainees = pages_pour(True, "enchaine")
        self.assertGreater(separees, enchainees, (
            "cinq chapitres d'une ligne tiennent en {} page(s) enchainees et "
            "{} separees : les deux mises en page ne se distinguent pas"
            .format(enchainees, separees)))
        self.assertGreaterEqual(separees, 5)

        # Sans rien declarer : c'est ce que recoivent les dix-sept chaines qui
        # ne parlent pas de mise en page.
        self.assertEqual(pages_pour(None, "defaut"), separees, (
            "une chaine qui ne declare rien n'a plus une page par chapitre"))


if __name__ == "__main__":
    unittest.main()
