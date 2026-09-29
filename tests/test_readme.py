"""Le README dit-il la verite sur ce que l'usine sait faire ?

« Une skill qui cite une fonction renommee est un piege — elle n'echoue nulle
part, elle fait perdre une heure a qui la suit. » La phrase est dans
CLAUDE.md, et elle vaut mot pour mot pour le README : c'est la premiere chose
qu'on lit, et la seule que beaucoup liront.

Le fichier a ete reecrit le 14/09/2026. Il etait passe de deux cents a **mille
deux cent quatre-vingt-dix-sept lignes** en une session, dont onze sections
consecutives racontant chacune un defaut corrige — un journal de bord deguise
en mode d'emploi. Les recits sont retournes dans « docs/ », ou ils etaient
deja, et le README ne garde qu'un index vers eux.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402

README = (RACINE / "README.md").read_text(encoding="utf-8")


def setUpModule():
    atelier.isoler("readme")


def _commandes_connues():
    from usine import cli

    parseur = cli.construire_parseur()
    sous = [a for a in parseur._actions if getattr(a, "choices", None)][0]
    return set(sous.choices), parseur


class ChaqueCommandeCiteeExiste(unittest.TestCase):

    def test_aucune_commande_inventee(self):
        connues, _ = _commandes_connues()
        # « usine » seul lance le menu ; « reglages », « menu » et « web » sont
        # des commandes comme les autres et figurent dans « connues ».
        citees = set(re.findall(r"`usine ([a-z][\w-]*)", README))
        citees |= set(re.findall(r"^usine ([a-z][\w-]*)", README, re.MULTILINE))
        inventees = sorted(citees - connues)
        self.assertEqual(inventees, [],
                         "le README promet des commandes qui n'existent pas : "
                         + ", ".join(inventees))

    def test_aucune_option_inventee(self):
        """Une option citee et disparue envoie droit dans un message
        d'erreur d'argparse, qui ne dit pas ou chercher."""
        _connues, parseur = _commandes_connues()
        aides = []
        for commande in ("ebook", "nouvelle", "usine", "sauvegarde",
                         "reglages", "maj", "specs", "ventes", "mots-meles"):
            sortie = io.StringIO()
            with contextlib.suppress(SystemExit), \
                    contextlib.redirect_stdout(sortie):
                parseur.parse_args([commande, "--help"])
            aides.append(sortie.getvalue())
        tout = "\n".join(aides)
        citees = set(re.findall(r"`(--[a-z][\w-]*)`", README))
        absentes = sorted(o for o in citees if o not in tout)
        self.assertEqual(absentes, [],
                         "options citees par le README et introuvables : "
                         + ", ".join(absentes))

    def test_les_types_de_produits_annonces_sont_ceux_du_catalogue(self):
        """Le catalogue est la source unique. Un tableau recopie a la main
        finirait par annoncer un produit retire, ou par en cacher un."""
        from usine.pipelines import catalogue

        for type_produit in catalogue.tous():
            with self.subTest(type=type_produit.cle):
                self.assertIn("usine {}".format(type_produit.cle), README,
                              "« {} » est fabricable et le README n'en parle "
                              "pas".format(type_produit.cle))


class LeReadmeResteLisible(unittest.TestCase):
    """Ce qui l'avait rendu illisible n'etait pas son contenu mais sa FORME :
    des recits de corrections empiles a la suite, chacun juste, ensemble
    incomprehensibles."""

    def test_il_tient_en_une_seance_de_lecture(self):
        lignes = README.count("\n")
        self.assertLess(lignes, 600,
                        "le README fait {} lignes : il redevient un journal "
                        "de bord".format(lignes))

    def test_chaque_note_de_docs_reste_atteignable_depuis_l_index(self):
        """La contrainte que la reecriture devait respecter : seize notes ne
        tenaient que par le README. Les couper les rendait introuvables."""
        notes = sorted((RACINE / "docs").glob("*.md"))
        self.assertGreater(len(notes), 20)
        absentes = [n.name for n in notes if n.name not in README]
        self.assertEqual(absentes, [],
                         "notes absentes de l'index : " + ", ".join(absentes))

    def test_la_contrainte_fondatrice_est_dite_des_le_debut(self):
        """Zero dependance explique presque tout le reste — les moteurs PDF et
        EPUB ecrits a la main, le tableau de bord sans bibliotheque. Ne pas le
        dire d'emblee fait passer ces choix pour des complications."""
        debut = README[:README.index("## Installation")]
        self.assertIn("bibliothèque standard", debut)


if __name__ == "__main__":
    unittest.main()
