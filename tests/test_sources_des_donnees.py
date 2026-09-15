"""Aucune donnee de marche sans provenance.

Ce module est ne d'un reproche juste : « tu as invente beaucoup, je voulais
du reel, tu aurais pu chercher ».

C'etait exact. Les listes de genres, de sous-genres, de tropes et les
tranches d'age d'un album sortaient de ma tete, avec en commentaire
« donnees recopiees, donc perissables » — recopiees de personne. Le depot
refuse un pourcentage enonce sans marqueur de source ; il n'avait rien pour
refuser une LISTE enoncee sans source, et c'est le meme defaut a plus grande
echelle : un sous-genre invente envoie fabriquer pour un rayon qui n'existe
pas.

Ce controle lit la STRUCTURE du module — les affectations de premier niveau —
et exige que chaque donnee ait son entree dans « SOURCES ». Une donnee sans
source connue reste possible : elle doit alors le DIRE, et son entree
commence par « SANS SOURCE ».
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("sources_des_donnees")


from usine.pipelines import conte, fiction  # noqa: E402


def _donnees_de(module) -> list:
    """Les tables de donnees declarees au premier niveau d'un module.

    Lit l'arbre syntaxique plutot que le module charge : on veut les noms
    ECRITS dans le fichier, pas ce qui a pu etre ajoute a l'execution — c'est
    la difference entre « cette donnee est declaree ici » et « cette cle
    existe quelque part ».
    """
    chemin = Path(module.__file__)
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms = []
    for noeud in arbre.body:
        cibles = []
        if isinstance(noeud, ast.Assign):
            cibles = [c.id for c in noeud.targets if isinstance(c, ast.Name)]
        elif isinstance(noeud, ast.AnnAssign) and isinstance(noeud.target, ast.Name):
            cibles = [noeud.target.id]
        for nom in cibles:
            if not nom.isupper() or nom in ("SOURCES",):
                continue
            # Un nom prive (« _ETIQUETTES ») n'est pas une donnee de marche :
            # c'est de la mise en forme d'invite. Exiger sa provenance ferait
            # crier a tort sur chaque detail interne — et un controle qui
            # signale a tort finit ignore.
            if nom.startswith("_"):
                continue
            valeur = getattr(module, nom, None)
            # Seules les TABLES sont des donnees de marche. Un entier de
            # reglage (« PAGES_MIN ») n'est pas un releve : l'exiger source
            # ferait crier a tort a chaque constante technique.
            if isinstance(valeur, (dict, tuple, list)) and valeur:
                noms.append(nom)
    return noms


class ChaqueTableDeDonneesPorteSaSource(unittest.TestCase):

    MODULES = (fiction, conte)

    def _orphelines(self, modules):
        """La detection, appelee PAR le test et PAR son temoin.

        La reecrire dans le temoin laisserait neutraliser celle du test sans
        que personne ne bronche : une campagne de mutation l'a montre deux
        fois de suite sur d'autres detecteurs de ce depot.
        """
        manquantes = []
        for module in modules:
            sources = getattr(module, "SOURCES", {})
            for nom in _donnees_de(module):
                if nom not in sources:
                    manquantes.append("{}.{}".format(
                        module.__name__.rsplit(".", 1)[-1], nom))
        return manquantes

    def test_aucune_donnee_n_est_orpheline(self):
        manquantes = self._orphelines(self.MODULES)
        self.assertEqual(manquantes, [], "\n".join([
            "Ces donnees n'ont pas d'entree dans SOURCES :",
            ", ".join(manquantes),
            "Une donnee sans source connue reste possible — elle doit le "
            "dire, et son entree commence par « SANS SOURCE »."]))

    def _source_valable(self, texte):
        """Trois formes valables, et une seule regle : dire d'ou ca vient.

        Un releve porte sa date ; ce qui n'a pas de source le declare ; ce
        qui n'est pas une donnee de marche le declare aussi. Tout le reste
        est une affirmation de plus.
        """
        if len(texte) <= 40:
            return False
        return ("2026" in texte or "2025" in texte
                or texte.startswith("SANS SOURCE")
                or "pas une donnee de marche" in texte)

    def test_chaque_source_dit_d_ou_elle_vient_et_quand(self):
        for module in self.MODULES:
            for nom, texte in getattr(module, "SOURCES", {}).items():
                with self.subTest(donnee=nom):
                    self.assertTrue(self._source_valable(texte), nom)

    def test_le_detecteur_de_source_refuse_vraiment_une_affirmation(self):
        self.assertFalse(self._source_valable(
            "Les sous-genres les plus vendeurs du moment, c'est bien connu "
            "et tout le monde le sait depuis toujours."))
        self.assertFalse(self._source_valable("trop court"))
        self.assertTrue(self._source_valable(
            "Releve le 15/09/2026 sur les guides de categories, partiel "
            "parce qu'aucune taxinomie complete n'est publiee."))

    def test_ce_qui_n_a_pas_de_source_le_dit(self):
        """Le cas honnete : les ambiances ne sont recensees nulle part. Les
        garder est un choix ; les presenter comme un releve serait un
        mensonge."""
        self.assertTrue(fiction.SOURCES["AMBIANCES"].startswith("SANS SOURCE"))

    def test_le_detecteur_voit_vraiment_une_donnee_sans_source(self):
        """Ecrit apres la correction : on lui montre le defaut, et on le lui
        montre PAR la meme fonction que celle du test."""
        faux = type("Faux", (), {})()
        faux.__file__ = str(RACINE / "usine" / "_temoin_donnees.py")
        faux.__name__ = "usine.pipelines._temoin"
        Path(faux.__file__).write_text(
            "UNE_LISTE = ('a', 'b')\nSOURCES = {}\n", encoding="utf-8")
        faux.UNE_LISTE = ("a", "b")
        faux.SOURCES = {}
        try:
            self.assertEqual(self._orphelines([faux]), ["_temoin.UNE_LISTE"])
        finally:
            Path(faux.__file__).unlink()


class LesDonneesSourceesSontCellesQuiOntEteMesurees(unittest.TestCase):
    """Les valeurs elles-memes, pas seulement leur etiquette.

    Un test qui verifie l'existence d'une source et laisse la valeur libre
    permettrait de changer le chiffre sans changer la source — c'est-a-dire
    de reinventer sous couvert de provenance.
    """

    def test_la_fin_exigee_en_romance_suit_la_definition_du_genre(self):
        """« A central love story and an emotionally satisfying and
        optimistic ending » : HEA ou HFN, rien d'autre."""
        self.assertEqual(fiction.FINS_EXIGEES_EN_ROMANCE,
                         ("heureuse", "heureuse pour l'instant"))
        self.assertIn("Romance Writers of America",
                      fiction.SOURCES["FINS_EXIGEES_EN_ROMANCE"])

    def test_l_album_standard_fait_quatorze_doubles_pages(self):
        """32 pages liminaires comprises, soit ~14 doubles-pages."""
        for tranche in ("3-5 ans", "6-8 ans"):
            self.assertEqual(conte.TRANCHES[tranche]["pages"], 14, tranche)
        self.assertIn("32 pages", conte.SOURCES["pages"])

    def test_les_mots_par_page_decoulent_du_total(self):
        """Ils ne sont pas poses : c'est le total divise par le nombre de
        doubles-pages. Les poser separement les ferait diverger."""
        for tranche, regle in conte.TRANCHES.items():
            attendu = round(regle["mots_total"] / regle["pages"])
            self.assertAlmostEqual(regle["mots_page"], attendu, delta=1,
                                   msg=tranche)

    def test_le_plafond_de_phrase_suit_un_repere_de_lisibilite(self):
        """Huit mots (compris a ~100 %) ou quatorze (a plus de 90 %). Aucun
        autre chiffre n'a de source ici."""
        for tranche, regle in conte.TRANCHES.items():
            self.assertIn(regle["mots_phrase"], (8, 14), tranche)

    def test_les_tropes_recenses_sont_ceux_des_releves(self):
        romance = fiction.TROPES["romance"]
        for trope in ("enemies to lovers", "fake dating", "second chance",
                      "slow burn", "grumpy x sunshine"):
            self.assertIn(trope, romance)

    def test_les_genres_sans_trope_recense_n_en_inventent_pas(self):
        """Aucune source consultee ne recense les tropes du policier ou de
        l'imaginaire avec la regularite de ceux de la romance. Combler le
        trou serait retomber dans le defaut que ce module corrige."""
        for genre in ("policier", "imaginaire", "litterature"):
            self.assertEqual(fiction.tropes_du_genre(genre), (), genre)

    def test_les_categories_sont_celles_du_rayon_reel(self):
        for categorie in ("Romance", "Mystery, Thriller & Suspense",
                          "Science Fiction & Fantasy", "Children's eBooks"):
            self.assertIn(categorie, fiction.CATEGORIES)

    def test_la_source_dit_que_la_liste_est_partielle(self):
        """Amazon ne publie aucune taxinomie complete. Le taire laisserait
        croire que ce qui manque n'existe pas."""
        self.assertIn("partielle", fiction.SOURCES["CATEGORIES"])
