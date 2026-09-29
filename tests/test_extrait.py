"""L'edition courte offerte : ce qu'elle contient, et ou elle ne va pas.

Deux proprietes portent tout : l'extrait est DECOUPE dans le livre produit
(aucun appel au modele, donc reproductible et fidele), et il vit dans
« marketing/ », qui ne part jamais chez l'acheteur. Un extrait livre a
quelqu'un qui vient de payer le livre entier serait au mieux ridicule.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, reglages  # noqa: E402
from usine.marketing import extrait  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402

MARKDOWN = """# Le systeme du freelance

*Facturer mieux en travaillant moins*

_Zoe Martin_

# Avant-propos : pourquoi ce livre

Le probleme que vit le lecteur, expose en quelques paragraphes.

# Trouver ses premiers clients

Du contenu de chapitre, avec des phrases entieres.

# Fixer ses tarifs

Encore du contenu, differemment tourne.

# Tenir ses delais

Un troisieme chapitre de contenu.

# Conclusion : les trente prochains jours

Le plan d'action final.
"""


def setUpModule():
    atelier.isoler("extrait")
    llm.definir_simulateur(simulateur)
    reglages.ecrire({"images": False, "qualite": "rapide", "auteur": "Zoe Martin",
                     "site": "https://exemple.fr/le-livre",
                     "contact": "zoe@exemple.fr"})


def tearDownModule():
    llm.definir_simulateur(None)


class TestDecoupe(unittest.TestCase):
    def test_l_entete_et_les_chapitres_sont_separes(self):
        entete, chapitres = extrait.decouper(MARKDOWN)
        self.assertIn("Le systeme du freelance", entete)
        self.assertIn("Zoe Martin", entete)
        self.assertEqual(len(chapitres), 5)
        self.assertEqual(chapitres[0][0], "Avant-propos : pourquoi ce livre")
        self.assertIn("Le probleme que vit le lecteur", chapitres[0][1])

    def test_le_titre_du_livre_n_est_pas_compte_comme_un_chapitre(self):
        _, chapitres = extrait.decouper(MARKDOWN)
        self.assertNotIn("Le systeme du freelance",
                         [titre for titre, _ in chapitres])

    def test_un_markdown_sans_titre_ne_casse_pas(self):
        entete, chapitres = extrait.decouper("juste du texte, sans titre")
        self.assertEqual(chapitres, [])
        self.assertIn("juste du texte", entete)


class TestQuantiteOfferte(unittest.TestCase):
    def test_jamais_tout_le_livre(self):
        """Un extrait complet n'est plus un extrait."""
        for total in range(2, 30):
            self.assertLess(extrait.nombre_offert(total), total,
                            "{} chapitres".format(total))

    def test_toujours_au_moins_un_chapitre(self):
        for total in range(2, 30):
            self.assertGreaterEqual(extrait.nombre_offert(total), 1)

    def test_un_quart_par_defaut(self):
        self.assertEqual(extrait.nombre_offert(8), 2)
        self.assertEqual(extrait.nombre_offert(12), 3)
        self.assertEqual(extrait.nombre_offert(20), 5)

    def test_une_demande_explicite_est_suivie_mais_bornee(self):
        self.assertEqual(extrait.nombre_offert(12, 5), 5)
        self.assertEqual(extrait.nombre_offert(12, 99), 11, "jamais tout")
        self.assertEqual(extrait.nombre_offert(12, -3), 3, "retombe au defaut")


class TestProduction(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="usine-extrait-"))
        (self.dossier / "livre.md").write_text(MARKDOWN, encoding="utf-8")
        from usine.pipelines.base import Contexte

        self.contexte = Contexte(sujet="le freelancing", auteur="Zoe Martin",
                                 hors_ligne=True, journal=lambda message: None)

    def _produire(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return extrait.produire(self.contexte, self.dossier,
                                    "Le systeme du freelance", "ebook", **kwargs)

    def test_les_fichiers_sont_ecrits_dans_marketing(self):
        resultat = self._produire()
        self.assertIsNotNone(resultat)
        cible = self.dossier / "marketing" / "extrait"
        self.assertTrue(cible.is_dir())
        extensions = {f.suffix for f in cible.iterdir()}
        self.assertIn(".pdf", extensions)
        self.assertIn(".epub", extensions)

    def test_l_epub_de_l_extrait_est_conforme(self):
        """Il est envoye a des prospects : un fichier casse se voit tout autant."""
        from usine.render.epub_conformite import verifier_epub

        self._produire()
        epub = next((self.dossier / "marketing" / "extrait").glob("*.epub"))
        rapport = verifier_epub(epub)
        self.assertTrue(rapport.conforme, rapport.erreurs)

    def test_il_ne_contient_que_les_chapitres_offerts(self):
        """La promesse d'un extrait est de s'arreter."""
        self._produire(chapitres_offerts=2)
        texte = self._texte_epub()
        self.assertIn("Avant-propos", texte)
        self.assertIn("Trouver ses premiers clients", texte)
        self.assertNotIn("Un troisieme chapitre de contenu", texte,
                         "le corps d'un chapitre non offert a fui")

    def test_la_derniere_page_dit_ce_qui_manque_et_ou_l_obtenir(self):
        self._produire(chapitres_offerts=2)
        texte = self._texte_epub()
        self.assertIn("Fixer ses tarifs", texte, "les titres restants servent "
                                                 "d'appat, pas leur contenu")
        self.assertIn("https://exemple.fr/le-livre", texte)
        self.assertIn("zoe@exemple.fr", texte)

    def test_sans_site_ni_contact_l_appel_a_l_action_reste(self):
        reglages.ecrire({"site": "", "contact": ""})
        try:
            self._produire()
            self.assertIn("Répondez à cet e-mail", self._texte_epub())
        finally:
            reglages.ecrire({"site": "https://exemple.fr/le-livre",
                             "contact": "zoe@exemple.fr"})

    def test_un_livre_trop_court_n_a_pas_d_extrait(self):
        court = Path(tempfile.mkdtemp(prefix="usine-court-"))
        (court / "livre.md").write_text(
            "# Titre\n\n_Zoe_\n\n# Un chapitre\n\nDu texte.\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(extrait.produire(self.contexte, court, "Titre"))

    def test_un_dossier_sans_markdown_ne_casse_pas(self):
        vide = Path(tempfile.mkdtemp(prefix="usine-vide-"))
        self.assertIsNone(extrait.produire(self.contexte, vide, "Titre"))

    def _texte_epub(self) -> str:
        import html
        import re

        epub = next((self.dossier / "marketing" / "extrait").glob("*.epub"))
        with zipfile.ZipFile(epub) as archive:
            pages = [n for n in archive.namelist() if n.endswith(".xhtml")]
            brut = " ".join(archive.read(n).decode("utf-8") for n in sorted(pages))
        return html.unescape(re.sub(r"<[^>]+>", " ", brut))


class TestDeclarationAuCatalogue(unittest.TestCase):
    """Quels produits se pretent a un extrait est declare UNE fois."""

    def test_les_produits_qu_on_lit_en_ont_un(self):
        for cle in ("ebook", "nouvelle", "prompts", "formation"):
            self.assertTrue(catalogue.accepte_extrait(cle), cle)

    def test_un_outil_logiciel_n_en_a_pas(self):
        """« Les deux premiers chapitres » ne veut rien dire pour un programme."""
        self.assertFalse(catalogue.accepte_extrait("logiciel"))

    def test_un_type_inconnu_n_en_a_pas(self):
        self.assertFalse(catalogue.accepte_extrait("inexistant"))


if __name__ == "__main__":
    unittest.main()
