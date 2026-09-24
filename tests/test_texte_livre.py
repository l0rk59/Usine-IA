"""Ce que le modele ecrit arrive propre chez l'acheteur.

Balayage du 24/09/2026, avec un modele simule qui fait ce que font couramment
les vrais : du « **gras** » dans ses reponses, et des gabarits du genre
« <VOTRE NOM> ». Resultat :

- des « ** » en clair dans les PDF de douze types sur dix-huit, et dans les
  pages HTML de huit — le PDF imprimait le texte tel quel ;
- dans les posts sociaux et le CSV des e-mails, qui partent tels quels sur
  LinkedIn ou dans la boite des abonnes ;
- « <VOTRE NOM> » avale comme une balise, donc invisible, dans les pages des
  outils, des modeles, des prompts et du pack social : leur texte entrait
  dans le HTML sans echappement.

AUCUN test de ce module ne sort sur le reseau.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
import zlib
from html.parser import HTMLParser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402


def setUpModule():
    atelier.isoler("texte-livre")


from usine.core import llm, reglages, store  # noqa: E402
from usine.render import document as D  # noqa: E402
from usine.render.pdf import DocumentPDF  # noqa: E402
from usine.web import serveur  # noqa: E402

GRAS = "TEMOINGRAS"
CHEVRONS = "<VOTRE NOM>"


# Les champs courts qu'une chaine affiche tels quels : un nom d'outil, une
# colonne de base. Un premier jet du test ne piquait que les textes de plus
# de vingt-cinq caracteres — ils passaient au travers, et deux defauts avec.
_COURTS = ("nom", "role", "description", "titre")


def _piquer(valeur, cle=""):
    """Ajoute du gras et un gabarit en chevrons a chaque texte du modele —
    sauf au code, qui doit rester litteral et n'est pas ce qu'on mesure."""
    if isinstance(valeur, dict):
        return {k: _piquer(v, k) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_piquer(v, cle) for v in valeur]
    if not isinstance(valeur, str) or cle in ("code", "fichier", "prompt",
                                                "commande", "usage"):
        return valeur
    if len(valeur) > 25 and " " in valeur:
        return "**{}** {} {}".format(GRAS, valeur, CHEVRONS)
    if cle in _COURTS and len(valeur) > 2:
        return "{} {}".format(valeur, CHEVRONS)
    return valeur


def _simulateur_bavard(messages, role):
    rendu = simulateur(messages, role)
    try:
        return json.dumps(_piquer(json.loads(rendu)), ensure_ascii=False)
    except ValueError:
        return rendu


def _texte_pdf(chemin: Path) -> str:
    brut = chemin.read_bytes()
    morceaux = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", brut, re.S):
        flux = m.group(1)
        try:
            flux = zlib.decompress(flux)
        except zlib.error:
            pass
        morceaux += [x.decode("latin-1") for x in re.findall(rb"\((.*?)\)\s*Tj", flux)]
    return "\n".join(morceaux)


class _Visible(HTMLParser):
    """Le texte qu'un navigateur affiche, hors scripts et blocs de code."""

    def __init__(self):
        super().__init__()
        self.morceaux, self._cache = [], 0

    def handle_starttag(self, balise, attributs):
        if balise in ("script", "pre", "code", "style"):
            self._cache += 1

    def handle_endtag(self, balise):
        if balise in ("script", "pre", "code", "style") and self._cache:
            self._cache -= 1

    def handle_data(self, donnees):
        if not self._cache:
            self.morceaux.append(donnees)


class LesFichiersLivres(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        atelier.isoler("texte-livre-fichiers")
        reglages.ecrire(dict(images=False, qualite="rapide"))
        llm.definir_simulateur(_simulateur_bavard)
        cls._boucle = serveur._lancer_la_boucle
        serveur._lancer_la_boucle = lambda **_kw: None
        cls.dossiers = {}
        for i, cle in enumerate(("ebook", "emails", "social", "quiz", "outils",
                                 "modeles", "prompts", "impression", "memo")):
            store.cache_vider()
            serveur.TRAVAUX["tl"] = {"statut": "en_cours", "journal": []}
            try:
                serveur._lancer("tl", cle, {"sujet": "la tresorerie des artisans {}".format(i)})
            finally:
                serveur.TRAVAUX.pop("tl", None)
            cls.dossiers[cle] = Path(store.lister_produits(1)[0]["dossier"])

    @classmethod
    def tearDownClass(cls):
        serveur._lancer_la_boucle = cls._boucle
        llm.definir_simulateur(None)

    def test_aucun_gras_en_clair_dans_les_pdf(self):
        for cle, dossier in self.dossiers.items():
            for pdf in dossier.rglob("*.pdf"):
                with self.subTest(type=cle, fichier=pdf.name):
                    texte = _texte_pdf(pdf)
                    self.assertIn(GRAS, texte, "le temoin doit etre arrive")
                    self.assertNotIn("*" + GRAS, texte)

    def test_aucun_gras_ni_chevron_perdu_dans_les_pages(self):
        for cle, dossier in self.dossiers.items():
            for page in dossier.rglob("*.html"):
                with self.subTest(type=cle, fichier=page.name):
                    brut = page.read_text(encoding="utf-8")
                    lecteur = _Visible()
                    lecteur.feed(brut)
                    visible = " ".join(lecteur.morceaux)
                    self.assertNotIn("*" + GRAS, visible)
                    hors_script = re.sub(r"(?s)<script.*?</script>", "", brut)
                    # Un « <VOTRE NOM> » brut dans le HTML est une balise
                    # inconnue : le navigateur ne l'affiche pas.
                    self.assertNotIn(CHEVRONS, hors_script)

    def test_ce_qui_part_tel_quel_ailleurs_est_du_texte_brut(self):
        """Un reseau social et un outil d'e-mailing n'interpretent pas le
        markdown : les etoiles partaient avec le post et avec le message."""
        for cle, motif in (("social", "*.csv"), ("emails", "*.csv")):
            for fichier in self.dossiers[cle].rglob(motif):
                with self.subTest(type=cle, fichier=fichier.name):
                    contenu = fichier.read_text(encoding="utf-8-sig")
                    self.assertIn(GRAS, contenu)
                    self.assertNotIn("**", contenu)


class LeRenduPdf(unittest.TestCase):

    def test_le_paragraphe_retire_le_balisage_mais_pas_le_code(self):
        doc = DocumentPDF()
        doc.paragraphe("un **mot** fort")
        doc.paragraphe("ls *.txt *.md", brut=True)
        flux = "\n".join(doc._flux)
        self.assertNotIn("**mot**", flux)
        self.assertIn("*.txt *.md", flux)

    def test_un_bloc_de_code_markdown_reste_litteral(self):
        """« 2**3**2 » est du Python, pas du gras : nettoye, il devenait
        « 232 » dans la notice d'un outil logiciel."""
        doc = DocumentPDF()
        D.vers_pdf(D.analyser("```\nprint(2**3**2)\n```"), doc)
        self.assertIn("2**3**2", "\n".join(doc._flux))

    def test_une_multiplication_n_est_pas_de_l_italique(self):
        """Le nettoyage ne doit pas manger ce qui n'est pas du balisage : sans
        la condition d'espace, « 5 * 3 * 2 » devenait « 5  3  2 »."""
        self.assertEqual(D.nettoyer_inline("5 * 3 * 2"), "5 * 3 * 2")
        self.assertEqual(D.nettoyer_inline("un *mot* ici"), "un mot ici")


if __name__ == "__main__":
    unittest.main()
