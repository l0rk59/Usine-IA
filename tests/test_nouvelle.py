"""La chaine de fiction : bible, memoire roulante, continuite.

Ce que cette chaine ajoute a l'ebook tient en un mot : la MEMOIRE. Une scene
doit savoir ce qui s'est passe avant elle. Les tests portent donc moins sur
« un fichier est produit » — le catalogue le verifie deja pour tous les
types — que sur les trois pieces qui justifient une chaine a part :

  1. la bible existe avant la premiere scene et contraint ce qui suit ;
  2. le resume roulant entre reellement dans l'invite de la scene suivante ;
  3. le controle de continuite sait REFUSER. La moitie de ces tests lui
     donnent des histoires cassees : un controle qui ne detecte rien serait
     vert sur n'importe quoi.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import llm, reglages  # noqa: E402
from usine.pipelines import catalogue, nouvelle  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402


def setUpModule():
    atelier.isoler("nouvelle")
    llm.definir_simulateur(simulateur)
    reglages.ecrire({"images": False, "qualite": "rapide", "auteur": "Tests"})


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(**kwargs) -> Contexte:
    base = dict(sujet="un cheminot et la fermeture de sa ligne",
                audience="lecteurs de fiction", taille="mini", qualite="rapide",
                hors_ligne=True, sans_image=True, journal=lambda message: None)
    base.update(kwargs)
    return Contexte(**base)


BIBLE = {
    "titre": "Le dernier train",
    "genre": "drame",
    "premisse": "Une cheminote apprend que sa ligne ferme.",
    "cadre": {"lieu": "Roubaix", "epoque": "aujourd'hui", "regles": []},
    "personnages": [
        {"nom": "Camille Renard", "role": "protagoniste", "desir": "sauver la ligne",
         "defaut": "ne demande jamais d'aide", "voix": "breve"},
        {"nom": "Hakim Oussaid", "role": "antagoniste", "desir": "fermer",
         "defaut": "rigide", "voix": "polie"},
    ],
    "enjeu": "Elle perd le depot.",
    "fin_visee": "Elle conduit le dernier train.",
}

GRILLE_COMPLETE = {
    "beats": [{"nom": n, "evenement": "..."} for n, _ in nouvelle.BEATS],
    "scenes": [
        {"titre": "Le depot", "beat": "situation", "personnages": ["Camille Renard"]},
        {"titre": "La lettre", "beat": "declencheur", "personnages": ["Camille Renard"]},
        {"titre": "Le quai", "beat": "climax", "personnages": ["Hakim Oussaid"]},
        {"titre": "Apres", "beat": "resolution", "personnages": ["Camille Renard"]},
    ],
}


def _histoire(*textes: str) -> List[Tuple[str, str]]:
    return [("Scene {}".format(i + 1), t) for i, t in enumerate(textes)]


# --------------------------------------------------------------------------
# Le controle de continuite doit savoir refuser
# --------------------------------------------------------------------------


class TestControleContinuite(unittest.TestCase):
    def _controler(self, scenes, memoires=None, bible=None, grille=None):
        return nouvelle.controler_continuite(
            bible or BIBLE, grille or GRILLE_COMPLETE, scenes,
            memoires if memoires is not None
            else ["etat numero {} distinct".format(i) for i in range(len(scenes))])

    def test_une_histoire_saine_ne_declenche_rien(self):
        rapport = self._controler(_histoire(
            "Camille Renard entre dans le depot et regarde la motrice.",
            "Hakim Oussaid tend le dossier a Camille Renard sans s'asseoir.",
            "Camille Renard conduit le dernier convoi ; Hakim Oussaid regarde.",
        ), memoires=["Camille arrive au depot glace",
                     "Hakim refuse le sursis demande",
                     "Camille conduit le convoi final"])
        self.assertEqual(rapport["anomalies"], [], rapport["anomalies"])
        self.assertEqual(rapport["resume"], "continuite tenue")

    def test_un_personnage_de_la_bible_jamais_apparu(self):
        rapport = self._controler(_histoire(
            "Camille Renard verrouille le hangar, seule, et compte les rails.",
            "Camille Renard rentre a pied sous la pluie et ne dit rien.",
        ))
        genres = [a["genre"] for a in rapport["anomalies"]]
        self.assertIn("personnage_absent", genres)
        self.assertIn("Hakim", " ".join(a["detail"] for a in rapport["anomalies"]))

    def test_le_protagoniste_efface_est_une_anomalie_majeure(self):
        rapport = self._controler(_histoire(
            "Hakim Oussaid classe les dossiers du depot.",
            "Hakim Oussaid signe l'arrete et ferme le bureau.",
            "Hakim Oussaid rend les cles au service.",
            "Camille Renard passe une derniere fois.",
        ))
        graves = [a for a in rapport["anomalies"] if a["gravite"] == "majeur"]
        self.assertTrue(any(a["genre"] == "protagoniste_efface" for a in graves),
                        rapport["anomalies"])
        self.assertGreaterEqual(rapport["majeures"], 1)

    def test_une_scene_ou_personne_n_est_nomme(self):
        rapport = self._controler(_histoire(
            "Camille Renard ouvre le depot. Hakim Oussaid la suit.",
            "La pluie tombait sur les rails. Le vent poussait les portes.",
        ))
        detail = " ".join(a["detail"] for a in rapport["anomalies"]
                          if a["genre"] == "scene_hors_distribution")
        self.assertIn("Scene 2", detail)

    def test_un_etat_qui_n_avance_plus(self):
        """Deux resumes identiques : la scene n'a rien fait avancer."""
        fige = "Camille attend au depot, le sursis reste incertain."
        rapport = self._controler(
            _histoire("Camille Renard attend. Hakim Oussaid aussi.",
                      "Camille Renard attend encore, Hakim Oussaid patiente."),
            memoires=[fige, fige])
        self.assertTrue(any(a["genre"] == "scene_sans_pivot"
                            for a in rapport["anomalies"]), rapport["anomalies"])

    def test_une_scene_non_redigee_est_dite_telle_quelle(self):
        """Un plafond de budget n'est pas un defaut du recit.

        Les scenes reduites a leur fiche gardent une memoire de secours qui
        accumule les pivots : leur vocabulaire se recouvre, et le controle du
        pivot les signalerait toutes comme « l'histoire n'avance plus ». Ce
        serait blamer le recit pour notre propre degradation.
        """
        fige = "Camille attend au depot, le sursis reste incertain."
        rapport = nouvelle.controler_continuite(
            BIBLE, GRILLE_COMPLETE,
            _histoire("Camille Renard et Hakim Oussaid au depot.",
                      "Camille Renard, Hakim Oussaid : fiche de scene.",
                      "Camille Renard, Hakim Oussaid : fiche de scene."),
            memoires=[fige, fige, fige],
            redigees=[True, False, False])
        genres = [a["genre"] for a in rapport["anomalies"]]
        self.assertNotIn("scene_sans_pivot", genres)
        self.assertIn("scene_non_redigee", genres)
        detail = " ".join(a["detail"] for a in rapport["anomalies"])
        self.assertIn("2 scene(s)", detail)

    def test_un_tournant_indispensable_que_rien_ne_livre(self):
        grille = {"beats": GRILLE_COMPLETE["beats"],
                  "scenes": [{"titre": "x", "beat": "situation",
                              "personnages": ["Camille Renard"]}]}
        rapport = self._controler(_histoire(
            "Camille Renard et Hakim Oussaid se croisent au depot."),
            grille=grille)
        manquants = " ".join(a["detail"] for a in rapport["anomalies"]
                             if a["genre"] == "beat_non_livre")
        for essentiel in ("declencheur", "climax", "resolution"):
            self.assertIn(essentiel, manquants)

    def test_les_beats_facultatifs_ne_sont_pas_exiges(self):
        """Six scenes ne peuvent pas livrer sept tournants separement.

        Le reprocher serait faux : seuls le declencheur, le climax et la
        resolution sont indispensables.
        """
        rapport = self._controler(_histoire(
            "Camille Renard parle a Hakim Oussaid une derniere fois."))
        genres = [a["genre"] for a in rapport["anomalies"]]
        self.assertNotIn("beat_non_livre", genres)

    def test_un_personnage_reconnu_par_son_nom_seul(self):
        """La bible dit « Camille Renard », le texte ecrit « Camille »."""
        rapport = self._controler(_histoire(
            "Camille poussa la porte. Hakim l'attendait sur le quai."))
        self.assertNotIn("personnage_absent",
                         [a["genre"] for a in rapport["anomalies"]])


# --------------------------------------------------------------------------
# La memoire roulante
# --------------------------------------------------------------------------


class TestMemoire(unittest.TestCase):
    def test_la_memoire_de_secours_garde_le_pivot(self):
        """Quand le budget tombe, la memoire ne doit pas disparaitre."""
        scene = {"titre": "La lettre", "pivot": "Camille apprend la fermeture"}
        memoire = nouvelle._memoire_de_secours("", scene)
        self.assertIn("Camille apprend la fermeture", memoire)
        suivante = nouvelle._memoire_de_secours(memoire, {
            "titre": "Le quai", "pivot": "Hakim signe l'arrete"})
        self.assertIn("Camille apprend la fermeture", suivante)
        self.assertIn("Hakim signe l'arrete", suivante)

    def test_un_resume_vide_ne_detruit_pas_la_memoire(self):
        """Un modele qui repond trois mots ferait perdre tout le passe."""
        llm.definir_simulateur(lambda messages, role: "ok")
        try:
            memoire = nouvelle.mettre_a_jour_resume(
                _contexte(), "Camille est au depot depuis l'aube.",
                {"titre": "Le quai", "pivot": "Hakim signe"}, "du texte")
        finally:
            llm.definir_simulateur(simulateur)
        self.assertIn("Camille est au depot", memoire)
        self.assertIn("Hakim signe", memoire)


# --------------------------------------------------------------------------
# La chaine, de bout en bout
# --------------------------------------------------------------------------


class TestChaine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resume = nouvelle.produire(_contexte())
        cls.dossier = Path(cls.resume["dossier"])

    def test_la_bible_est_ecrite_avant_le_texte(self):
        donnees = json.loads((self.dossier / "bible.json").read_text(
            encoding="utf-8"))
        self.assertTrue(donnees["bible"]["personnages"])
        self.assertTrue(donnees["grille"]["scenes"])
        self.assertTrue(donnees["bible"]["enjeu"])

    def test_la_memoire_est_conservee_scene_par_scene(self):
        donnees = json.loads((self.dossier / "continuite.json").read_text(
            encoding="utf-8"))
        self.assertEqual(len(donnees["memoires"]), self.resume["scenes"])
        # Elle doit AVANCER : deux etats successifs identiques signifient que
        # la chaine n'a pas de memoire, seulement l'illusion d'en avoir une.
        self.assertNotEqual(donnees["memoires"][0], donnees["memoires"][-1])

    def test_la_continuite_est_tenue_et_rapportee(self):
        donnees = json.loads((self.dossier / "continuite.json").read_text(
            encoding="utf-8"))
        self.assertEqual(donnees["continuite"]["majeures"], 0,
                         donnees["continuite"]["anomalies"])

    def test_le_texte_livre_est_de_la_prose_pas_un_guide(self):
        texte = (self.dossier / "nouvelle.md").read_text(encoding="utf-8")
        self.assertNotIn("A retenir", texte)
        # Les titres de niveau 1 sont ceux des scenes, poses par la mise en
        # page. Aucun sous-titre ni liste ne doit apparaitre dans une scene.
        for ligne in texte.splitlines():
            self.assertFalse(ligne.startswith("## "), ligne)

    def test_le_catalogue_connait_la_chaine(self):
        self.assertIn("nouvelle", catalogue.cles())
        self.assertIsNotNone(catalogue.obtenir("nouvelle").fabriquer)

    def test_les_formats_annonces_sont_produits(self):
        extensions = {f.suffix.lstrip(".") for f in self.dossier.iterdir()}
        for attendu in catalogue.obtenir("nouvelle").formats:
            self.assertIn(attendu, extensions)


class TestBudgetEpuise(unittest.TestCase):
    """Un plafond atteint ne detruit pas le travail fait — comme pour l'ebook."""

    def setUp(self):
        from usine.core import budget

        reglages.ecrire({"images": False, "qualite": "rapide",
                         "budget_appels_produit": 6, "budget_appels_jour": 0,
                         "budget_produits_jour": 0, "budget_minutes_produit": 0})
        self.compteur = budget.Compteur()
        self.compteur.demarrer_produit()
        budget.brancher(self.compteur)

    def tearDown(self):
        from usine.core import budget

        budget.brancher(None)
        reglages.ecrire({"budget_appels_produit": 0, "qualite": "rapide",
                         "images": False})

    def test_l_histoire_sort_quand_meme_et_le_dit(self):
        resume = nouvelle.produire(_contexte())
        self.assertTrue(resume["budget_epuise"])
        dossier = Path(resume["dossier"])
        # Toutes les scenes sont la, les dernieres reduites a leur fiche.
        self.assertEqual(resume["scenes"], 6)
        for extension in (".pdf", ".epub", ".md"):
            self.assertTrue(any(f.suffix == extension for f in dossier.iterdir()),
                            "aucun fichier {}".format(extension))
        donnees = json.loads((dossier / "continuite.json").read_text(
            encoding="utf-8"))
        genres = [a["genre"] for a in donnees["continuite"]["anomalies"]]
        self.assertIn("scene_non_redigee", genres)
        # La memoire de secours ne doit pas etre prise pour une histoire figee.
        self.assertNotIn("scene_sans_pivot", genres)


class TestFormatsDeFiction(unittest.TestCase):
    """Les paliers de l'usine sont penses pour des guides ; la fiction a les
    siens, et la chaine doit dire lequel elle vise plutot que l'imposer."""

    def test_les_reperes_du_marche(self):
        self.assertEqual(nouvelle.format_fiction(600), "texte tres court")
        self.assertEqual(nouvelle.format_fiction(7600), "nouvelle")
        self.assertEqual(nouvelle.format_fiction(13200), "novelette")
        self.assertEqual(nouvelle.format_fiction(25000), "novella")
        self.assertEqual(nouvelle.format_fiction(90000), "roman")


class TestBible(unittest.TestCase):
    def test_un_personnage_hors_bible_est_ecarte_de_la_grille(self):
        """La bible est la source de verite : la grille ne peut pas la completer.

        Le modele repond ici une grille qui introduit un inconnu — c'est ce
        qu'il fait en vrai quand la scene lui semble manquer de monde. S'en
        remettre au simulateur habituel ne prouverait rien : sa distribution
        est justement celle de sa bible.
        """
        intruse = json.dumps({
            "beats": [{"nom": "situation", "evenement": "..."}],
            "scenes": [{"titre": "Le depot", "beat": "situation",
                        "lieu": "Roubaix",
                        "personnages": ["Camille Renard", "Le controleur Vasseur"],
                        "point_de_vue": "Camille Renard", "objectif": "...",
                        "obstacle": "...", "pivot": "..."}],
        }, ensure_ascii=False)
        llm.definir_simulateur(lambda messages, role: intruse)
        try:
            grille = nouvelle.construire_grille(_contexte(), BIBLE)
        finally:
            llm.definir_simulateur(simulateur)
        presents = grille["scenes"][0]["personnages"]
        self.assertIn("Camille Renard", presents)
        self.assertNotIn("Le controleur Vasseur", presents,
                         "un personnage absent de la bible doit etre ecarte")

    def test_un_nom_proche_n_est_pas_le_meme_personnage(self):
        self.assertTrue(nouvelle._reconnu("Renard", ["Camille Renard"]))
        self.assertTrue(nouvelle._reconnu("Camille", ["Camille Renard"]))
        self.assertFalse(nouvelle._reconnu("Alexandra", ["Alex Dubois"]))
        self.assertFalse(nouvelle._reconnu("", ["Camille Renard"]))

    def test_le_protagoniste_est_trouve_meme_sans_role_declare(self):
        sans_role = dict(BIBLE, personnages=[
            {"nom": "Alex", "role": "secondaire", "desir": "", "defaut": "",
             "voix": ""}])
        self.assertEqual(nouvelle.protagoniste(sans_role), "Alex")

    def test_la_bible_entre_dans_chaque_invite(self):
        texte = nouvelle.resumer_bible(BIBLE)
        for attendu in ("Camille Renard", "Hakim Oussaid", "ENJEU", "veut :",
                        "defaut :", "voix :"):
            self.assertIn(attendu, texte)


if __name__ == "__main__":
    unittest.main()
