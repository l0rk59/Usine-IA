"""L'EPUB livre : appareil liminaire et conformite structurelle.

Deux sujets, une meme raison d'etre. Un EPUB casse ne se voit pas : l'archive
s'ouvre, le fichier a l'air normal, et c'est le distributeur qui le refuse
des semaines plus tard. Et un livre sans page de copyright se repere au
premier coup d'oeil — c'est la premiere chose qu'un lecteur habitue regarde
apres le titre.

La moitie de ces tests CASSENT volontairement un EPUB valide : un controle
qui ne sait rien refuser ne prouve rien.
"""

from __future__ import annotations

import html
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.render.epub import construire_epub  # noqa: E402
from usine.render.epub_conformite import verifier_epub  # noqa: E402

CHAPITRES = [("Le premier chapitre", "<p>Du texte.</p>"),
             ("Le second chapitre", "<p>Encore du texte.</p>")]

OPF = "{http://www.idpf.org/2007/opf}"


def setUpModule():
    atelier.isoler("epub")


def _construire(dossier: Path, **kwargs) -> Path:
    return construire_epub(dossier / "livre.epub", "Le systeme du freelance",
                           "Zoe Martin", CHAPITRES, sous_titre="Un sous-titre",
                           description="La promesse du livre.", **kwargs)


def _reecrire(source: Path, cible: Path,
              transformer: Callable[[str, bytes], Optional[bytes]],
              premier: str = "mimetype",
              compresser_mimetype: bool = False) -> Path:
    """Recopie un EPUB en modifiant, supprimant ou reordonnant ses entrees.

    C'est ainsi qu'un EPUB se casse dans la vraie vie : quelqu'un dezippe,
    corrige une coquille, rezippe — et perd la regle du « mimetype » en
    premiere position non compressee.
    """
    with zipfile.ZipFile(source) as entree:
        contenus: Dict[str, bytes] = {n: entree.read(n) for n in entree.namelist()}
    noms = sorted(contenus, key=lambda n: (n != premier, n))
    with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as sortie:
        for nom in noms:
            octets = transformer(nom, contenus[nom])
            if octets is None:
                continue
            if nom == "mimetype" and not compresser_mimetype:
                sortie.writestr(zipfile.ZipInfo("mimetype"), octets,
                                compress_type=zipfile.ZIP_STORED)
            else:
                sortie.writestr(nom, octets)
    return cible


class BaseEpub(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="usine-epub-"))
        self.livre = _construire(self.dossier)

    def casser(self, transformer, **kwargs) -> object:
        abime = _reecrire(self.livre, self.dossier / "abime.epub",
                          transformer, **kwargs)
        return verifier_epub(abime)


# --------------------------------------------------------------------------
# Ce que l'usine produit doit passer
# --------------------------------------------------------------------------


class TestEpubValide(BaseEpub):
    def test_l_epub_de_l_usine_est_conforme(self):
        rapport = verifier_epub(self.livre)
        self.assertTrue(rapport.conforme, rapport.erreurs)
        self.assertEqual(rapport.avertissements, [])
        self.assertGreater(rapport.controles, 20,
                           "un controle qui ne controle rien serait vert aussi")

    def test_la_recopie_a_l_identique_reste_conforme(self):
        """Le banc d'essai lui-meme ne doit rien casser par accident."""
        rapport = self.casser(lambda nom, octets: octets)
        self.assertTrue(rapport.conforme, rapport.erreurs)

    def test_un_fichier_absent(self):
        rapport = verifier_epub(self.dossier / "jamais-ecrit.epub")
        self.assertFalse(rapport.conforme)
        self.assertIn("absent", rapport.erreurs[0])

    def test_un_fichier_qui_n_est_pas_une_archive(self):
        faux = self.dossier / "faux.epub"
        faux.write_bytes(b"ceci n'est pas un ZIP")
        rapport = verifier_epub(faux)
        self.assertFalse(rapport.conforme)
        self.assertIn("illisible", rapport.erreurs[0])


# --------------------------------------------------------------------------
# Le mimetype : la regle la plus mecanique, et la plus souvent perdue
# --------------------------------------------------------------------------


class TestMimetype(BaseEpub):
    def test_mimetype_pas_en_premier(self):
        rapport = self.casser(lambda nom, octets: octets, premier="OEBPS/style.css")
        self.assertFalse(rapport.conforme)
        self.assertIn("premiere entree", rapport.erreurs[0])

    def test_mimetype_compresse(self):
        rapport = self.casser(lambda nom, octets: octets, compresser_mimetype=True)
        self.assertFalse(rapport.conforme)
        self.assertIn("non compresse", " ".join(rapport.erreurs))

    def test_mimetype_au_mauvais_contenu(self):
        rapport = self.casser(
            lambda nom, octets: b"application/zip" if nom == "mimetype" else octets)
        self.assertFalse(rapport.conforme)
        self.assertIn("application/epub+zip", " ".join(rapport.erreurs))

    def test_mimetype_absent(self):
        rapport = self.casser(
            lambda nom, octets: None if nom == "mimetype" else octets)
        self.assertFalse(rapport.conforme)


# --------------------------------------------------------------------------
# Conteneur, manifeste, dos, navigation
# --------------------------------------------------------------------------


class TestStructure(BaseEpub):
    def test_conteneur_absent(self):
        rapport = self.casser(
            lambda n, o: None if n == "META-INF/container.xml" else o)
        self.assertIn("META-INF/container.xml", " ".join(rapport.erreurs))

    def test_conteneur_mal_forme(self):
        rapport = self.casser(
            lambda n, o: b"<container" if n == "META-INF/container.xml" else o)
        self.assertIn("mal forme", " ".join(rapport.erreurs))

    def test_conteneur_qui_designe_un_opf_absent(self):
        rapport = self.casser(
            lambda n, o: o.replace(b"OEBPS/content.opf", b"OEBPS/ailleurs.opf")
            if n == "META-INF/container.xml" else o)
        self.assertIn("OEBPS/ailleurs.opf", " ".join(rapport.erreurs))

    def test_fichier_declare_mais_absent_de_l_archive(self):
        rapport = self.casser(lambda n, o: None if n == "OEBPS/ch002.xhtml" else o)
        self.assertFalse(rapport.conforme)
        self.assertIn("ch002.xhtml", " ".join(rapport.erreurs))

    def test_fichier_present_mais_non_declare(self):
        """Un orphelin gonfle l'archive : c'est un avertissement, pas un refus."""
        def ajouter(nom, octets):
            return octets

        abime = _reecrire(self.livre, self.dossier / "orphelin.epub", ajouter)
        with zipfile.ZipFile(abime, "a") as z:
            z.writestr("OEBPS/brouillon.txt", "oublie la")
        rapport = verifier_epub(abime)
        self.assertTrue(rapport.conforme, "un orphelin ne doit pas faire echouer")
        self.assertIn("brouillon.txt", " ".join(rapport.avertissements))

    def test_le_dos_renvoie_a_un_identifiant_inconnu(self):
        rapport = self.casser(
            lambda n, o: o.replace(b'<itemref idref="ch001"/>',
                                   b'<itemref idref="fantome"/>')
            if n.endswith("content.opf") else o)
        self.assertIn("fantome", " ".join(rapport.erreurs))

    def test_sans_document_de_navigation(self):
        rapport = self.casser(
            lambda n, o: o.replace(b' properties="nav"', b"")
            if n.endswith("content.opf") else o)
        self.assertIn("navigation", " ".join(rapport.erreurs))

    def test_navigation_sans_epub_type_toc(self):
        rapport = self.casser(
            lambda n, o: o.replace(b'epub:type="toc" ', b"")
            if n.endswith("nav.xhtml") else o)
        self.assertIn("toc", " ".join(rapport.erreurs))

    def test_table_des_matieres_vide(self):
        rapport = self.casser(
            lambda n, o: o.replace(b"<ol>", b"<ol>x</ol><ol>").replace(
                b'<li><a href="ch001.xhtml">Le premier chapitre</a></li>'
                b'<li><a href="ch002.xhtml">Le second chapitre</a></li>', b"")
            if n.endswith("nav.xhtml") else o)
        self.assertIn("aucun lien", " ".join(rapport.erreurs))

    def test_xhtml_mal_forme(self):
        rapport = self.casser(
            lambda n, o: o.replace(b"</p>", b"") if n.endswith("ch001.xhtml") else o)
        self.assertFalse(rapport.conforme)
        self.assertIn("ch001.xhtml", " ".join(rapport.erreurs))


class TestMetadonneesObligatoires(BaseEpub):
    def _sans(self, motif: bytes, remplacement: bytes = b""):
        return self.casser(lambda n, o: o.replace(motif, remplacement)
                           if n.endswith("content.opf") else o)

    def test_sans_langue(self):
        rapport = self._sans(b"<dc:language>fr</dc:language>")
        self.assertIn("dc:language", " ".join(rapport.erreurs))

    def test_sans_date_de_modification(self):
        rapport = self.casser(
            lambda n, o: o.replace(b'property="dcterms:modified"',
                                   b'property="dcterms:autre"')
            if n.endswith("content.opf") else o)
        self.assertIn("dcterms:modified", " ".join(rapport.erreurs))

    def test_identifiant_unique_qui_ne_designe_rien(self):
        rapport = self._sans(b'id="pub-id"', b'id="autre-id"')
        self.assertIn("unique-identifier", " ".join(rapport.erreurs))


# --------------------------------------------------------------------------
# Appareil liminaire
# --------------------------------------------------------------------------


class TestAppareilLiminaire(BaseEpub):
    def _dos(self, chemin: Path):
        with zipfile.ZipFile(chemin) as z:
            paquet = ET.fromstring(z.read("OEBPS/content.opf"))
        return [n.get("idref") for n in paquet.findall(".//{}itemref".format(OPF))]

    def _page(self, chemin: Path, nom: str) -> str:
        with zipfile.ZipFile(chemin) as z:
            return z.read("OEBPS/" + nom).decode("utf-8")

    def test_l_ordre_attendu_par_les_plateformes(self):
        """Titre, copyright, puis table des matieres — dans cet ordre."""
        dos = self._dos(self.livre)
        self.assertLess(dos.index("titre"), dos.index("droits"))
        self.assertLess(dos.index("droits"), dos.index("nav"))
        self.assertLess(dos.index("nav"), dos.index("ch001"))

    def test_la_page_de_copyright_porte_l_essentiel(self):
        page = self._page(self.livre, "droits.xhtml")
        self.assertIn("Zoe Martin", page)
        self.assertIn("&#169;", page)
        self.assertIn("Tous droits réservés", page)
        self.assertIn("urn:uuid:", page, "l'identifiant unique doit y figurer")

    def test_la_dedicace_n_existe_que_si_on_en_donne_une(self):
        with zipfile.ZipFile(self.livre) as z:
            self.assertNotIn("OEBPS/dedicace.xhtml", z.namelist())
        self.assertNotIn("dedicace", self._dos(self.livre))

        avec = construire_epub(self.dossier / "avec.epub", "T", "Zoe", CHAPITRES,
                               dedicace="Pour celles et ceux qui commencent.")
        self.assertIn("Pour celles et ceux qui commencent",
                      self._page(avec, "dedicace.xhtml"))
        dos = self._dos(avec)
        self.assertLess(dos.index("droits"), dos.index("dedicace"))
        self.assertLess(dos.index("dedicace"), dos.index("nav"))

    def test_les_mentions_s_ajoutent_a_la_page_de_droits(self):
        avec = construire_epub(self.dossier / "mention.epub", "T", "Zoe",
                               CHAPITRES, mentions=["Elabore avec une IA."])
        self.assertIn("Elabore avec une IA.", self._page(avec, "droits.xhtml"))

    def test_l_editeur_n_est_cite_que_s_il_differe_de_l_auteur(self):
        seul = construire_epub(self.dossier / "seul.epub", "T", "Zoe", CHAPITRES,
                               editeur="Zoe")
        self.assertNotIn("Édité par", self._page(seul, "droits.xhtml"))
        marque = construire_epub(self.dossier / "marque.epub", "T", "Zoe",
                                 CHAPITRES, editeur="Les Editions du Coin")
        self.assertIn("Les Editions du Coin", self._page(marque, "droits.xhtml"))

    def test_les_pages_liminaires_sont_du_xml_bien_forme(self):
        avec = construire_epub(self.dossier / "complet.epub", "T & Co", "Zoe",
                               CHAPITRES, dedicace="Pour \"Julie\" & les autres",
                               mentions=["Mention <avec> des chevrons"])
        for nom in ("droits.xhtml", "dedicace.xhtml"):
            ET.fromstring(self._page(avec, nom))
        self.assertTrue(verifier_epub(avec).conforme)


class TestBranchementDansLaLivraison(unittest.TestCase):
    """Le controle et l'appareil liminaire doivent servir en vrai.

    Un verificateur que la chaine de fabrication n'appelle pas ne protege
    personne, et une page de copyright qui n'atteint pas le fichier livre
    n'existe pas.
    """

    def setUp(self):
        from usine.core import reglages
        from usine.pipelines.base import Contexte

        reglages.reinitialiser()
        self.dossier = Path(tempfile.mkdtemp(prefix="usine-livraison-"))
        self.contexte = Contexte(sujet="x", auteur="Zoe", hors_ligne=True,
                                 sans_image=True, journal=lambda message: None)
        self.contexte.dossier = self.dossier

    def _livrer(self, **kwargs):
        from usine.render import livraison

        for nom, valeur in kwargs.items():
            setattr(self.contexte, nom, valeur)
        produit = livraison.Produit(
            type="ebook", titre="Le systeme du freelance",
            blocs=[livraison.Bloc("Un chapitre", "Du contenu suffisant.")],
            formats=("epub",))
        return livraison.livrer(self.contexte, produit)[0]

    def _page_droits(self, chemin: Path) -> str:
        with zipfile.ZipFile(chemin) as z:
            page = z.read("OEBPS/droits.xhtml").decode("utf-8")
        # Le generateur echappe tout, apostrophes comprises (« l&#x27;IA ») :
        # on compare le texte tel que le lecteur le verra.
        return html.unescape(page)

    def test_l_epub_livre_est_controle_et_le_resultat_conserve(self):
        chemin = self._livrer()
        rapport = self.contexte.meta.get("epub")
        self.assertIsNotNone(rapport, "le controle doit laisser sa trace")
        self.assertTrue(rapport["conforme"], rapport["erreurs"])
        self.assertTrue(verifier_epub(chemin).conforme)

    def test_la_mention_ia_suit_son_reglage(self):
        """Le meme reglage commande la licence et la page de copyright."""
        from usine.core import reglages
        from usine.render import libelles

        MENTION_IA_COURTE = libelles.libelle("fr", "mention_ia_courte")

        reglages.ecrire({"signature_ia": True})
        self.assertIn(MENTION_IA_COURTE, self._page_droits(self._livrer()))

        reglages.ecrire({"signature_ia": False})
        self.assertNotIn(MENTION_IA_COURTE, self._page_droits(self._livrer()))

    def test_la_dedicace_du_contexte_atteint_le_fichier(self):
        chemin = self._livrer(dedicace="Pour Julie, qui a commence.")
        with zipfile.ZipFile(chemin) as z:
            self.assertIn("Pour Julie, qui a commence",
                          z.read("OEBPS/dedicace.xhtml").decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
