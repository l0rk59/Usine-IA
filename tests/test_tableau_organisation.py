"""Ce que le tableau de bord fait tenir sur un ecran de telephone.

Mesure faite au navigateur le 14/09/2026, en 412px de large — la largeur d'un
telephone courant :

| | avant | apres |
|---|---|---|
| barre d'onglets | ~190px, cinq lignes | 56px, une ligne |
| onglet « Reglages » | 3077px, 29 champs deroules | 997px, groupes replies |
| scene 3D | sur les cinq onglets | sur les deux ou elle informe |

La cause de la barre empilee n'etait ni « flex-wrap » ni « min-width » : une
regle groupee donne « width: 100% » a TOUT bouton de la page, donc chaque
onglet occupait la largeur entiere et passait a la ligne. Trois reglages de
flexbox successifs n'y ont rien change avant qu'on mesure la largeur reelle
des boutons dans un navigateur.

Ces tests lisent la STRUCTURE des fichiers, pas leur apparence : ils gardent
ce qui a ete corrige, pas les pixels, qui dependent du navigateur.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402

STATIQUE = RACINE / "usine" / "web" / "statique"
HTML = (STATIQUE / "tableau.html").read_text(encoding="utf-8")
CSS = (STATIQUE / "tableau.css").read_text(encoding="utf-8")
JS = (STATIQUE / "app.js").read_text(encoding="utf-8")


def setUpModule():
    atelier.isoler("tableau-organisation")


class ChaqueOngletExiste(unittest.TestCase):

    def _cles_onglets(self):
        return re.findall(r'data-onglet="(\w+)"', HTML)

    def test_chaque_bouton_a_sa_section(self):
        """Un onglet sans section affiche une page vide et laisse croire que
        le tableau de bord est casse."""
        sections = set(re.findall(r'data-section="(\w+)"', HTML))
        for cle in self._cles_onglets():
            with self.subTest(onglet=cle):
                self.assertIn(cle, sections)

    def test_chaque_section_a_son_bouton(self):
        """L'autre sens : une section sans bouton est inatteignable — c'est
        exactement ce qui rendait « produire en boucle » introuvable."""
        boutons = set(self._cles_onglets())
        for cle in re.findall(r'data-section="(\w+)"', HTML):
            with self.subTest(section=cle):
                self.assertIn(cle, boutons)

    def test_produire_en_boucle_a_son_propre_onglet(self):
        """Elle vivait en quatrieme bloc de « Fabriquer », sous le formulaire,
        l'equipe et le journal — 1770px plus bas. La fonction qui fabrique
        sans qu'on dicte quoi que ce soit etait la moins visible de la page.
        """
        self.assertIn("continue", self._cles_onglets())


class LaBarreTientSurUneLigne(unittest.TestCase):

    def _regle(self, selecteur):
        debut = CSS.index(selecteur + " {")
        return CSS[debut:CSS.index("}", debut)]

    def test_les_onglets_ne_s_empilent_plus(self):
        regle = self._regle(".onglets")
        self.assertIn("nowrap", regle)
        self.assertIn("overflow-x: auto", regle)

    def test_un_onglet_ne_prend_pas_toute_la_largeur(self):
        """La vraie cause, et la seule qui comptait : « input, select,
        textarea, button » impose « width: 100% ». Sans la contredire ici,
        « flex-wrap: nowrap » ne fait que remplacer six lignes par six
        boutons pleine largeur qui debordent.
        """
        regle = self._regle(".onglets button")
        self.assertIn("width: auto", regle,
                      "la regle groupee des champs reprend la main : chaque "
                      "onglet occupe la largeur entiere")

    def test_la_regle_groupee_impose_toujours_la_largeur(self):
        """Sans ce cas, le test precedent passerait encore le jour ou la
        regle groupee disparaitrait — en gardant une ligne devenue inutile
        que quelqu'un finirait par supprimer, ramenant le defaut."""
        groupee = self._regle("input, select, textarea, button")
        self.assertIn("width: 100%", groupee)

    def test_l_onglet_actif_est_ramene_dans_le_cadre(self):
        """Une barre qui defile peut garder l'onglet choisi hors du cadre :
        actif et invisible, ce qui se lit comme une page vide."""
        self.assertIn("scrollIntoView", JS)


class LesReglagesNeSontPlusUnMur(unittest.TestCase):

    def test_les_groupes_se_replient(self):
        """Les six groupes existaient deja — mais tous deroules d'un coup.
        Un titre qui ne replie rien n'est pas une section, c'est du gras."""
        self.assertIn("<details class=\"groupe-reglages\"", JS)
        self.assertIn("<summary>", JS)

    def test_un_seul_groupe_est_ouvert_au_depart(self):
        bloc = JS[JS.index("function dessinerReglages"):]
        bloc = bloc[:bloc.index("\n}")]
        self.assertIn("groupes[0]", bloc,
                      "aucun groupe ouvert, ou tous : les deux sont mauvais")

    def test_ce_que_l_utilisateur_a_ouvert_survit_au_rafraichissement(self):
        """La liste se redessine a chaque chargement d'etat. Refermer sous
        les doigts de quelqu'un le groupe qu'il remplissait serait pire que
        le mur qu'on vient d'enlever."""
        bloc = JS[JS.index("function dessinerReglages"):]
        bloc = bloc[:bloc.index("\n}")]
        self.assertIn("[open]", bloc)

    def test_enregistrer_reste_atteignable(self):
        self.assertIn("barre-enregistrer", HTML)
        regle = CSS[CSS.index(".barre-enregistrer {"):]
        regle = regle[:regle.index("}")]
        self.assertIn("sticky", regle)

    def test_la_barre_d_enregistrement_est_opaque(self):
        """« --carte » est translucide : la barre laissait lire le groupe qui
        defilait dessous, et on croyait a un defaut d'affichage."""
        regle = CSS[CSS.index(".barre-enregistrer {"):]
        regle = regle[:regle.index("}")]
        self.assertNotIn("var(--carte)", regle)


class LaSceneNeSAfficheQueLaOuElleInforme(unittest.TestCase):

    def test_elle_ne_paraphrase_pas_les_reglages(self):
        """Elle ne dit qu'une chose : l'avancement d'une fabrication. Sur
        « Reglages » ou « La machine » elle ne dit rien, et prenait 370px du
        haut de chaque onglet — avant le premier champ."""
        bloc = JS[JS.index("const SECTIONS_AVEC_SCENE"):]
        bloc = bloc[:bloc.index(";")]
        for section in ("reglages", "machine", "produits", "marche"):
            with self.subTest(section=section):
                self.assertNotIn("'{}'".format(section), bloc)

    def test_elle_reste_la_ou_une_fabrication_avance(self):
        bloc = JS[JS.index("const SECTIONS_AVEC_SCENE"):]
        bloc = bloc[:bloc.index(";")]
        for section in ("fabriquer", "continue"):
            with self.subTest(section=section):
                self.assertIn("'{}'".format(section), bloc)


if __name__ == "__main__":
    unittest.main()
