"""La ponctuation francaise ne tombe plus seule en debut de ligne.

Le francais separe « », :, ; ! et ? du mot par une espace, et le modele
l'ecrit ordinaire. Le moteur PDF coupait a toute espace : un « » » ou un
« : » ouvrait la ligne suivante, un « « » fermait la precedente. Mesure du
27/09/2026 sur les notes de docs/ composees a 330 points : 1,5 % des retours
a la ligne, environ une fois toutes les deux pages de livre. Le navigateur et
la liseuse faisaient la meme chose au HTML et a l'EPUB.

Rien n'echouait : le texte etait juste, seule sa mise en page l'etait moins.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.render.document import inline_html  # noqa: E402
from usine.render.pdf import DocumentPDF, _mots_insecables  # noqa: E402

PHRASE = ("Le verbe « went » se dit : il est irregulier ; vraiment ? Oui ! "
          "Et « thought », « bought » se confondent (« taught » aussi).")
ORPHELINS_EN_TETE = ("»", ":", ";", "!", "?")


def setUpModule():
    atelier.isoler("typographie")


class LaCoupureDuPDF(unittest.TestCase):

    def test_aucun_signe_seul_en_debut_ou_en_fin_de_ligne(self):
        doc = DocumentPDF(titre_document="t", auteur="a",
                          police_corps="Times-Roman")
        vues = 0
        # Toutes les largeurs d'un mot a l'autre : chaque espace de la
        # phrase finit par tomber en fin de ligne au moins une fois. Pas en
        # dessous de 90 points : un groupe colle qui ne tient plus sur une
        # ligne est coupe lettre a lettre, comme tout mot trop long.
        for largeur in range(90, 400, 2):
            lignes = doc.couper(PHRASE, "Times-Roman", 11, largeur)
            vues += len(lignes) - 1
            for ligne in lignes:
                with self.subTest(largeur=largeur, ligne=ligne):
                    self.assertNotIn(ligne.split()[0], ORPHELINS_EN_TETE)
                    self.assertFalse(ligne.rstrip().endswith("«"))
        self.assertGreater(vues, 300, "le test doit avoir coupe souvent")

    def test_le_texte_n_est_pas_change(self):
        doc = DocumentPDF(titre_document="t", auteur="a",
                          police_corps="Times-Roman")
        lignes = doc.couper(PHRASE, "Times-Roman", 11, 120)
        self.assertEqual(" ".join(lignes), PHRASE)

    def test_l_anglais_se_coupe_comme_avant(self):
        """Pas d'espace avant les deux-points en anglais : rien a coller."""
        anglais = "Note: this is fine; really? Yes!"
        self.assertEqual(_mots_insecables(anglais), anglais.split())


class LeHTML(unittest.TestCase):

    def test_une_espace_insecable_colle_les_signes_a_leur_mot(self):
        rendu = inline_html("Il dit « **went** » : voilà ! Pourquoi ?")
        self.assertEqual(rendu, "Il dit «\u00a0<strong>went</strong>\u00a0»"
                                "\u00a0: voilà\u00a0! Pourquoi\u00a0?")

    def test_le_code_en_ligne_garde_ses_espaces(self):
        """Une espace insecable copiee dans un terminal n'est plus une
        espace : la commande ne marche plus."""
        self.assertIn("<code>a : b ?</code>", inline_html("`a : b ?`"))

    def test_le_texte_d_un_lien_suit_la_regle(self):
        self.assertIn(">«\u00a0lien\u00a0»</a>",
                      inline_html("[« lien »](https://exemple.fr/?a=1)"))


if __name__ == "__main__":
    unittest.main()
