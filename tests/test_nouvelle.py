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
from usine.agents import equipe  # noqa: E402
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
    # Les scenes portent TOUS les champs que « construire_grille » garantit :
    # un jeu d'essai ampute ferait passer des tests que la vraie grille
    # ferait echouer, ce qui est pire que pas de test du tout.
    "scenes": [
        dict(titre=titre, beat=beat, lieu="le depot", personnages=presents,
             point_de_vue=presents[0], objectif="obtenir un sursis",
             obstacle="le reglement", pivot="le sursis est refuse")
        for titre, beat, presents in (
            ("Le depot", "situation", ["Camille Renard"]),
            ("La lettre", "declencheur", ["Camille Renard"]),
            ("Le quai", "climax", ["Hakim Oussaid"]),
            ("Apres", "resolution", ["Camille Renard"]),
        )
    ],
    "fils": [],
    "arcs": [{"personnage": "Camille Renard", "depart": "refuse l'aide",
              "bascule": 3, "arrivee": "accepte l'aide"}],
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


class TestFilsTendus(unittest.TestCase):
    """Ce qui separe un recit long d'une suite de scenes justes.

    Une grille plate de tournants ne sait pas noter qu'un objet montre a la
    scene 2 doit servir a la scene 11. Chaque scene est alors juste, et
    l'ensemble ne tient pas : c'est exactement ce qu'on reproche a la
    fiction generee.
    """

    def test_un_fil_qui_pointe_hors_du_recit_est_ecarte(self):
        """Un fil paye a la scene 40 d'un recit de 6 ne serait jamais servi."""
        fils = nouvelle._normaliser_fils([
            {"nom": "la lettre", "pose": 1, "paye": 40},
            {"nom": "le quai", "pose": 0, "paye": 3},
            {"nom": "bon", "pose": 1, "paye": 4},
        ], total=6)
        self.assertEqual([f["nom"] for f in fils], ["bon"])

    def test_un_fil_paye_avant_d_etre_pose_est_ecarte(self):
        """Il demanderait a la scene 3 de reveler ce que la scene 9 n'a pas
        encore montre."""
        fils = nouvelle._normaliser_fils(
            [{"nom": "a rebours", "pose": 9, "paye": 3}], total=12)
        self.assertEqual(fils, [])

    def test_un_fil_paye_dans_la_scene_ou_il_est_pose_est_ecarte(self):
        fils = nouvelle._normaliser_fils(
            [{"nom": "instantane", "pose": 4, "paye": 4}], total=12)
        self.assertEqual(fils, [])

    def test_un_fil_sans_nom_est_ecarte(self):
        """Le nom sert a reconnaitre le fil dans le texte : sans lui, rien
        n'est verifiable."""
        fils = nouvelle._normaliser_fils(
            [{"nom": "  ", "pose": 1, "paye": 3}], total=6)
        self.assertEqual(fils, [])

    def test_un_numero_ecrit_en_toutes_lettres_est_lu(self):
        fils = nouvelle._normaliser_fils(
            [{"nom": "la lettre", "pose": "scene 2", "paye": "scene 5"}], total=8)
        self.assertEqual((fils[0]["pose"], fils[0]["paye"]), (2, 5))

    def test_le_nombre_de_fils_suit_la_longueur(self):
        """Six scenes ne tiennent pas huit promesses ; vingt-quatre scenes
        qui n'en tiennent qu'une sont une suite d'evenements."""
        self.assertEqual(nouvelle._fils_a_demander(6), 2)
        self.assertEqual(nouvelle._fils_a_demander(24), 6)
        self.assertLessEqual(nouvelle._fils_a_demander(200), 10)
        self.assertGreaterEqual(nouvelle._fils_a_demander(1), 1)

    def test_chaque_scene_sait_ce_qu_elle_doit_poser_payer_et_porter(self):
        grille = {"fils": [
            {"nom": "A", "pose": 1, "paye": 4, "quoi": "", "paiement": ""},
            {"nom": "B", "pose": 2, "paye": 3, "quoi": "", "paiement": ""},
        ]}
        premiere = nouvelle.fils_de_la_scene(grille, 0)
        self.assertEqual([f["nom"] for f in premiere["poser"]], ["A"])
        self.assertEqual(premiere["payer"], [])
        troisieme = nouvelle.fils_de_la_scene(grille, 2)
        self.assertEqual([f["nom"] for f in troisieme["payer"]], ["B"])
        self.assertEqual([f["nom"] for f in troisieme["suspens"]], ["A"],
                         "un fil pose et pas encore paye doit rester present")

    def test_un_fil_non_paye_dans_le_texte_est_signale(self):
        """Le JSON peut promettre ce que la prose n'a pas fait."""
        scenes = [("S1", "Camille Renard trouve une lettre chez Hakim Oussaid."),
                  ("S2", "Camille Renard marche seule avec Hakim Oussaid."),
                  ("S3", "Camille Renard et Hakim Oussaid attendent."),
                  ("S4", "Camille Renard et Hakim Oussaid se taisent.")]
        grille = dict(GRILLE_COMPLETE, fils=[
            {"nom": "le revolver", "pose": 1, "paye": 4, "quoi": "", "paiement": ""}])
        rapport = nouvelle.controler_continuite(
            BIBLE, grille, scenes,
            ["un etat", "deux etats", "trois etats", "quatre etats"])
        genres = [a["genre"] for a in rapport["anomalies"]]
        self.assertIn("fil_non_paye", genres)
        self.assertIn("fil_non_pose", genres)

    def test_un_fil_reellement_paye_ne_declenche_rien(self):
        scenes = [("S1", "Camille Renard trouve une lettre chez Hakim Oussaid."),
                  ("S2", "Camille Renard marche seule avec Hakim Oussaid."),
                  ("S3", "Camille Renard et Hakim Oussaid attendent."),
                  ("S4", "Camille Renard ouvre la lettre devant Hakim Oussaid.")]
        grille = dict(GRILLE_COMPLETE, fils=[
            {"nom": "la lettre", "pose": 1, "paye": 4, "quoi": "", "paiement": ""}])
        rapport = nouvelle.controler_continuite(
            BIBLE, grille, scenes,
            ["un etat", "deux etats", "trois etats", "quatre etats"])
        self.assertNotIn("fil_non_paye",
                         [a["genre"] for a in rapport["anomalies"]])

    def test_une_scene_non_redigee_ne_se_voit_pas_reprocher_son_fil(self):
        """Le budget est tombe : ce n'est pas au recit d'en repondre."""
        scenes = [("S1", "Camille Renard et Hakim Oussaid."),
                  ("S2", "fiche de scene"), ("S3", "fiche"), ("S4", "fiche")]
        grille = dict(GRILLE_COMPLETE, fils=[
            {"nom": "le revolver", "pose": 1, "paye": 4, "quoi": "", "paiement": ""}])
        rapport = nouvelle.controler_continuite(
            BIBLE, grille, scenes, ["a", "b b", "c c c", "d d d d"],
            redigees=[True, False, False, False])
        self.assertNotIn("fil_non_paye",
                         [a["genre"] for a in rapport["anomalies"]])


class TestFilsDansLInvite(unittest.TestCase):
    """Un fil qui n'atteint pas la scene n'est qu'un JSON de plus.

    C'est le point ou ce chantier peut echouer en silence : la grille serait
    parfaite, le controle passerait, et le modele n'aurait jamais rien su des
    promesses qu'il devait tenir.
    """

    def _invite(self, grille, index):
        recues = []
        origine = equipe.REDACTEUR.travailler

        def espion(contexte, invite, **kwargs):
            recues.append(invite)
            return origine(contexte, invite, **kwargs)

        equipe.REDACTEUR.travailler = espion
        try:
            nouvelle.rediger_scene(_contexte(), BIBLE, grille, index,
                                   grille["scenes"][index], "memoire")
        finally:
            equipe.REDACTEUR.travailler = origine
        return recues[0]

    def test_la_scene_sait_ce_qu_elle_pose_et_ce_qu_elle_paie(self):
        grille = dict(GRILLE_COMPLETE, fils=[
            {"nom": "la lettre non ouverte", "pose": 1, "paye": 4,
             "quoi": "une enveloppe qu'elle ne decachette pas",
             "paiement": "c'etait sa mutation"}])
        pose = self._invite(grille, 0)
        self.assertIn("A POSER", pose)
        self.assertIn("la lettre non ouverte", pose)
        self.assertIn("une enveloppe qu'elle ne decachette pas", pose)
        self.assertNotIn("A PAYER", pose)

        paiement = self._invite(grille, 3)
        self.assertIn("A PAYER", paiement)
        self.assertIn("c'etait sa mutation", paiement)

    def test_un_fil_en_cours_reste_sous_les_yeux(self):
        grille = dict(GRILLE_COMPLETE, fils=[
            {"nom": "la lettre", "pose": 1, "paye": 4, "quoi": "", "paiement": ""}])
        milieu = self._invite(grille, 1)
        self.assertIn("EN SUSPENS", milieu)
        self.assertIn("ne les oublie pas", milieu)

    def test_la_bascule_est_annoncee_a_la_bonne_scene(self):
        grille = dict(GRILLE_COMPLETE, arcs=[
            {"personnage": "Camille Renard", "depart": "refuse l'aide",
             "bascule": 3, "arrivee": "accepte l'aide"}])
        self.assertIn("BASCULE de Camille Renard", self._invite(grille, 2))
        self.assertNotIn("BASCULE", self._invite(grille, 0))

    def test_sans_fil_aucune_rubrique_vide_n_apparait(self):
        """Une rubrique vide n'est pas neutre : le modele la remplit."""
        grille = dict(GRILLE_COMPLETE, fils=[], arcs=[])
        invite = self._invite(grille, 0)
        for mot in ("A POSER", "A PAYER", "EN SUSPENS", "BASCULE"):
            self.assertNotIn(mot, invite)


class TestArcs(unittest.TestCase):
    """Un personnage qui finit comme il a commence n'a pas d'arc."""

    def test_un_personnage_hors_bible_n_a_pas_d_arc(self):
        arcs = nouvelle._normaliser_arcs(
            [{"personnage": "Le controleur Vasseur", "depart": "a",
              "bascule": 2, "arrivee": "b"}], BIBLE, total=6)
        self.assertEqual(arcs, [])

    def test_un_depart_egal_a_l_arrivee_n_est_pas_un_arc(self):
        arcs = nouvelle._normaliser_arcs(
            [{"personnage": "Camille Renard", "depart": "seule",
              "bascule": 2, "arrivee": "Seule"}], BIBLE, total=6)
        self.assertEqual(arcs, [])

    def test_un_seul_arc_par_personnage(self):
        arcs = nouvelle._normaliser_arcs([
            {"personnage": "Camille Renard", "depart": "a", "bascule": 2,
             "arrivee": "b"},
            {"personnage": "Camille Renard", "depart": "c", "bascule": 4,
             "arrivee": "d"},
        ], BIBLE, total=6)
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0]["arrivee"], "b")

    def test_un_protagoniste_sans_arc_est_signale(self):
        scenes = [("S{}".format(i), "Camille Renard et Hakim Oussaid parlent.")
                  for i in range(1, 5)]
        grille = dict(GRILLE_COMPLETE, arcs=[
            {"personnage": "Hakim Oussaid", "depart": "a", "bascule": 2,
             "arrivee": "b"}])
        rapport = nouvelle.controler_continuite(
            BIBLE, grille, scenes, ["un", "deux x", "trois y", "quatre z"])
        self.assertIn("protagoniste_sans_arc",
                      [a["genre"] for a in rapport["anomalies"]])

    def test_une_bascule_sans_le_personnage_est_signalee(self):
        scenes = [("S1", "Camille Renard seule."),
                  ("S2", "Camille Renard encore seule, sous la pluie."),
                  ("S3", "Camille Renard et Hakim Oussaid."),
                  ("S4", "Camille Renard et Hakim Oussaid se quittent.")]
        grille = dict(GRILLE_COMPLETE, arcs=[
            {"personnage": "Camille Renard", "depart": "a", "bascule": 1,
             "arrivee": "b"},
            {"personnage": "Hakim Oussaid", "depart": "a", "bascule": 2,
             "arrivee": "b"}])
        rapport = nouvelle.controler_continuite(
            BIBLE, grille, scenes, ["un", "deux x", "trois y", "quatre z"])
        detail = " ".join(a["detail"] for a in rapport["anomalies"]
                          if a["genre"] == "bascule_sans_le_personnage")
        self.assertIn("Hakim Oussaid", detail)

    def test_une_bascule_hors_du_recit_est_signalee(self):
        scenes = [("S1", "Camille Renard et Hakim Oussaid.")]
        grille = dict(GRILLE_COMPLETE, arcs=[
            {"personnage": "Camille Renard", "depart": "a", "bascule": 0,
             "arrivee": "b"}])
        rapport = nouvelle.controler_continuite(BIBLE, grille, scenes, ["un"])
        self.assertIn("bascule_hors_recit",
                      [a["genre"] for a in rapport["anomalies"]])


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
        scene = {"titre": "Le quai", "pivot": "Hakim signe"}
        llm.definir_simulateur(lambda messages, role: "ok")
        try:
            redacteur = nouvelle.redacteur_pour(_contexte(), scene)
            memoire = redacteur("Camille est au depot depuis l'aube.",
                                "du texte", "Le quai")
        finally:
            llm.definir_simulateur(simulateur)
        self.assertIn("Camille est au depot", memoire)
        self.assertIn("Hakim signe", memoire)

    def test_un_resume_exploitable_est_garde_tel_quel(self):
        redacteur = nouvelle.redacteur_pour(
            _contexte(), {"titre": "Le quai", "pivot": "Hakim signe"})
        etat = redacteur("", "du texte de scene", "Scene modele 1")
        self.assertNotIn("Hakim signe", etat, "le repli n'avait pas lieu d'etre")
        self.assertGreater(len(etat), 40)


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


class TestMemoireSurUnLongTexte(unittest.TestCase):
    """Au-dela d'une douzaine de scenes, un resume plat ne suffit plus.

    La mesure est dans tests/test_memoire.py ; ce qui est verifie ici est le
    BRANCHEMENT : la chaine choisit bien la memoire hierarchique, et ce que
    recoit la vingtieme scene contient reellement le debut du livre.
    """

    def setUp(self):
        self.recues = []
        self.origine = nouvelle.rediger_scene

        def espion(ctx, bible, grille, index, scene, memoire, fin_precedente=""):
            self.recues.append(memoire)
            return self.origine(ctx, bible, grille, index, scene, memoire,
                                fin_precedente)

        nouvelle.rediger_scene = espion

    def tearDown(self):
        nouvelle.rediger_scene = self.origine

    def test_la_vingtieme_scene_sait_ce_qui_s_est_passe_au_debut(self):
        nouvelle.produire(_contexte(chapitres=20, mots_section=1200))
        derniere = self.recues[-1]
        self.assertIn("Partie 1 :", derniere,
                      "le debut du livre doit encore etre la")
        self.assertIn("Partie en cours :", derniere)
        # Les parties closes doivent porter des contenus DIFFERENTS : trois
        # resumes identiques ne diraient rien de plus qu'un seul.
        parties = [ligne for ligne in derniere.splitlines()
                   if ligne.startswith("Partie ") and "en cours" not in ligne]
        self.assertEqual(len(parties), 3)
        self.assertEqual(len(set(parties)), 3)

    def test_une_nouvelle_courte_garde_la_memoire_plate(self):
        """Pas de frais de structure quand un seul etat suffit."""
        nouvelle.produire(_contexte(taille="mini"))
        self.assertNotIn("Partie 1 :", "".join(self.recues))


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

    def test_un_texte_long_degrade_aussi_proprement(self):
        """Memoire hierarchique ET repli : la combinaison la plus risquee.

        Les parties doivent continuer de se fermer aux bons endroits meme
        quand plus aucune scene n'est redigee, sinon la structure de la
        memoire dependrait de la reussite des appels.
        """
        resume = nouvelle.produire(_contexte(chapitres=20, mots_section=1200))
        self.assertTrue(resume["budget_epuise"])
        self.assertEqual(resume["scenes"], 20)
        dossier = Path(resume["dossier"])
        for extension in (".pdf", ".epub", ".md"):
            self.assertTrue(any(f.suffix == extension for f in dossier.iterdir()))
        donnees = json.loads((dossier / "continuite.json").read_text(
            encoding="utf-8"))
        genres = [a["genre"] for a in donnees["continuite"]["anomalies"]]
        self.assertIn("scene_non_redigee", genres)
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
