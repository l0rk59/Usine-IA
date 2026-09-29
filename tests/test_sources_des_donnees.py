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


from usine.pipelines import conte, fiction, prose, social  # noqa: E402


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

    MODULES = (fiction, conte, social, prose)

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


class LesChiffresVerifiesUneSecondeFois(unittest.TestCase):
    """Seconde passe du 15/09/2026, a la demande : « creuse ce point, et
    verifie aussi les autres donnees ».

    Elle a trouve trois erreurs, dont une que la PREMIERE correction avait
    introduite.
    """

    def test_le_conte_ne_pretend_plus_savoir_faire_du_9_12_ans(self):
        """L'erreur de ma correction precedente.

        J'avais adosse la tranche 9-12 aux « premiers lecteurs » (1 000 a
        5 000 mots) — qui s'adressent aux 5-7 ans. A neuf ans on lit un livre
        en CHAPITRES : 10 000 a 20 000 mots pour les 7-10, 25 000 a 50 000
        pour les 8-12. Ce n'est pas un album plus long, c'est un autre objet.
        """
        self.assertNotIn("9-12 ans", conte.TRANCHES)
        self.assertEqual(sorted(conte.TRANCHES), ["3-5 ans", "6-8 ans"])
        # Et l'absence est documentee, pas seulement effective.
        self.assertIn("au_dela_de_huit_ans", conte.SOURCES)
        self.assertIn("chapitres", conte.SOURCES["au_dela_de_huit_ans"])

    def test_ce_que_l_usine_sait_faire_pour_cet_age_porte_ses_longueurs(self):
        """Retirer une tranche sans dire ou aller laisserait un trou."""
        self.assertEqual(fiction.MOTS_ATTENDUS["chapter books"], (10000, 20000))
        self.assertEqual(fiction.MOTS_ATTENDUS["middle grade"], (25000, 50000))

    def test_la_fantasy_epique_porte_la_fourchette_la_plus_large(self):
        """Les sources divergent la, et seulement la : de 100 000 a 200 000
        selon qu'on lit « ce que le lecteur attend » ou « ce qu'un premier
        roman fait ». La regle du module est de retenir la plus large."""
        self.assertEqual(fiction.MOTS_ATTENDUS["epic fantasy"], (100000, 200000))
        self.assertIn("200 000", fiction.SOURCES["MOTS_ATTENDUS"])

    def test_la_source_des_categories_cite_amazon_lui_meme(self):
        """« Thousands of book categories in each Amazon marketplace, and
        they can change over time » — c'est Amazon qui le dit sur sa propre
        page d'aide, et qui renvoie a la navigation du magasin plutot qu'a
        une liste."""
        self.assertIn("thousands of book categories",
                      fiction.SOURCES["CATEGORIES"])


class LesLimitesDesReseauxSontCellesDuMoment(unittest.TestCase):
    """Donnee la plus perissable de la chaine sociale, et elle n'avait aucune
    source. Le plafond des legendes TikTok est passe de 2 200 a 4 000 en
    2024 : rien dans l'usine ne l'aurait su."""

    def test_les_plafonds_releves_sont_ceux_de_2026(self):
        self.assertEqual(social.LIMITES["x"]["maximum"], 280)
        self.assertEqual(social.LIMITES["linkedin"]["maximum"], 3000)
        self.assertEqual(social.LIMITES["instagram"]["maximum"], 2200)
        self.assertEqual(social.LIMITES["tiktok"]["maximum"], 4000)

    def test_le_repli_est_rendu_car_c_est_lui_qui_decide(self):
        """Un post LinkedIn peut faire 3 000 caracteres, mais seuls les 210
        premiers s'affichent. Ce qui fait cliquer tient la."""
        self.assertEqual(social.LIMITES["linkedin"]["avant_repli"], 210)
        self.assertEqual(social.LIMITES["instagram"]["avant_repli"], 125)

    def test_les_consignes_sont_baties_sur_les_limites(self):
        """Deux endroits pour le meme chiffre divergent, et c'est celui de
        l'invite qui ferait ecrire des posts tronques."""
        for cle, limites in social.LIMITES.items():
            self.assertIn(str(limites["maximum"]), social.RESEAUX[cle], cle)

    def test_le_cout_d_un_lien_chez_x_est_rendu(self):
        """Vingt-trois caracteres quelle que soit la longueur de l'adresse :
        un fil qui colle un lien par message en perd vingt-trois a chaque
        fois, sans que personne ne les voie partir."""
        self.assertEqual(social.CARACTERES_PAR_LIEN_X, 23)
        self.assertIn("23", social.RESEAUX["x"])

    def test_chaque_reseau_declare_a_ses_limites(self):
        """Un reseau propose sans plafond connu ferait ecrire a l'aveugle."""
        from usine.pipelines import catalogue

        self.assertEqual(set(catalogue.reseaux_sociaux()), set(social.LIMITES))
