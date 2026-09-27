"""Cahier de mots meles : ce qu'une grille ne pardonne pas.

Un mot de la liste introuvable dans la grille, ou present deux fois, ou
contenu dans un autre : l'acheteur le decouvre en jouant, et rien, a la
fabrication, ne l'aurait signale — le PDF est valide, la page est belle.
Ces tests relisent donc chaque grille comme un joueur : chaque mot de la
liste s'y lit, une fois, a l'endroit que la solution indique.
"""

from __future__ import annotations

import io
import json
import random
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests import simulateur as sim  # noqa: E402
from usine import cli  # noqa: E402
from usine.core import llm, store  # noqa: E402
from usine.pipelines import carnet, catalogue  # noqa: E402
from usine.pipelines import mots_meles as meles  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402

INVITES: List[str] = []
FRUITS = list(sim._FRUITS)


def _espion(messages, role):
    INVITES.append(messages[-1]["content"])
    return sim.simulateur(messages, role)


def setUpModule():
    atelier.isoler("mots-meles")
    llm.definir_simulateur(_espion)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet: str, journal=None, langue: str = "") -> Contexte:
    # Une audience par cas : elle entre dans la consigne systeme, donc dans
    # la cle du cache, et deux cas au meme sujet ne se liraient pas.
    ctx = Contexte(sujet=sujet, audience="des amateurs de " + sujet,
                   sans_image=True, journal=journal or (lambda _m: None))
    if langue:
        ctx.langue = langue
    return ctx


def _lu_a_sa_place(grille, mot) -> str:
    ligne, colonne, dl, dc = mot["position"]
    return "".join(grille["lettres"][ligne + dl * i][colonne + dc * i]
                   for i in range(len(mot["forme"])))


def _en_liste(grille):
    return [list(rangee) for rangee in grille["lettres"]]


class LesMots(unittest.TestCase):

    def test_un_mot_devient_des_lettres(self):
        self.assertEqual(meles.lettres("crème brûlée"), "CREMEBRULEE")
        self.assertEqual(meles.lettres("Œuf"), "OEUF")
        self.assertEqual(meles.lettres("l'été"), "LETE")
        self.assertEqual(meles.lettres("porte-clés"), "PORTECLES")
        self.assertEqual(meles.lettres("R2D2"), "")
        self.assertEqual(meles.lettres("東京"), "")

    def test_ce_qui_ne_tient_pas_est_ecarte_et_compte(self):
        mots, ecartes = meles.preparer_mots(
            ["pomme", "Pomme", "ab", "anticonstitutionnellement", "R2D2",
             "poire", "cerise"], taille=12, combien=10)
        self.assertEqual([f for _, f in mots], ["POMME", "POIRE", "CERISE"])
        self.assertEqual(ecartes, 4)

    def test_un_mot_contenu_dans_un_autre_est_ecarte(self):
        """« RAT » se lit toujours dans « RATEAU » : il y serait deux fois."""
        mots, ecartes = meles.preparer_mots(["rat", "râteau", "pelle"], 12, 10)
        self.assertEqual([f for _, f in mots], ["RATEAU", "PELLE"])
        self.assertEqual(ecartes, 1)

    def test_la_liste_est_ramenee_au_nombre_demande(self):
        mots, ecartes = meles.preparer_mots(FRUITS, 18, 5)
        self.assertEqual(len(mots), 5)
        self.assertEqual(ecartes, len(FRUITS) - 5)


class LaGrille(unittest.TestCase):

    def _grilles(self, difficulte, caracteres="standard", combien=6):
        taille = meles.DIFFICULTES[difficulte]["taille"]
        for n in range(combien):
            debut = (7 * n) % len(FRUITS)
            mots, _ = meles.preparer_mots(FRUITS[debut:] + FRUITS[:debut],
                                          taille, meles.DIFFICULTES[difficulte]["mots"])
            grille = meles.fabriquer_grille(mots, difficulte, caracteres,
                                            "essai|{}|{}".format(difficulte, n))
            self.assertIsNotNone(grille)
            yield grille

    def test_chaque_mot_se_lit_une_fois_a_l_endroit_indique(self):
        for difficulte in meles.DIFFICULTES:
            for grille in self._grilles(difficulte):
                self.assertGreaterEqual(len(grille["mots"]), meles.MOTS_MIN)
                for mot in grille["mots"]:
                    with self.subTest(difficulte=difficulte, mot=mot["forme"]):
                        self.assertEqual(_lu_a_sa_place(grille, mot), mot["forme"])
                        self.assertEqual(
                            meles.occurrences(_en_liste(grille), mot["forme"]), 1)

    def test_les_directions_suivent_la_difficulte(self):
        vues = {}
        for difficulte in meles.DIFFICULTES:
            vues[difficulte] = {tuple(m["position"][2:])
                                for g in self._grilles(difficulte, combien=10)
                                for m in g["mots"]}
            permises = set(meles.DIFFICULTES[difficulte]["directions"])
            self.assertLessEqual(vues[difficulte], permises, difficulte)
        # Seul « difficile » fait lire a l'envers, et il le fait vraiment.
        a_l_envers = {(0, -1), (-1, 0), (-1, -1), (1, -1)}
        self.assertFalse(vues["moyen"] & a_l_envers)
        self.assertTrue(vues["difficile"] & a_l_envers)

    def test_les_gros_caracteres_font_une_grille_plus_petite(self):
        for difficulte, fiche in meles.DIFFICULTES.items():
            grille = next(self._grilles(difficulte, "gros", combien=1))
            self.assertEqual(len(grille["lettres"]), fiche["gros"])
            self.assertLess(fiche["gros"], fiche["taille"])

    def test_la_meme_liste_redonne_la_meme_grille(self):
        mots, _ = meles.preparer_mots(FRUITS, 15, 15)
        une = meles.fabriquer_grille(mots, "moyen", "standard", "graine")
        deux = meles.fabriquer_grille(mots, "moyen", "standard", "graine")
        self.assertEqual(une, deux)

    def test_un_mot_que_la_grille_refuse_sort_de_la_liste(self):
        """Liste et grille ne font qu'un : un mot liste mais absent de la
        grille est introuvable, et le joueur cherche pour rien."""
        vrai_placer = meles.placer

        def sans_le_premier(formes, *args):
            return vrai_placer([f for f in formes if f != "POMME"], *args)

        mots, _ = meles.preparer_mots(FRUITS, 15, 15)
        with mock.patch.object(meles, "placer", sans_le_premier):
            grille = meles.fabriquer_grille(mots, "moyen", "standard", "g")
        self.assertIsNotNone(grille)
        self.assertNotIn("POMME", [m["forme"] for m in grille["mots"]])
        self.assertEqual(len(grille["mots"]), 14)
        self.assertEqual(grille["perdus"], 1)

    def test_trop_peu_de_mots_ne_fait_pas_de_grille(self):
        mots, _ = meles.preparer_mots(FRUITS[:3], 15, 15)
        self.assertIsNone(meles.fabriquer_grille(mots, "moyen", "standard", "g"))

    def test_un_mot_recree_par_le_remplissage_est_vu(self):
        """Le defaut que la relecture empeche : « RAT » pose une fois, et le
        hasard le recree ailleurs."""
        grille = [list("RATXX"), list("XXXXX"), list("XXRAT"), list("XXXXX"),
                  list("TARXX")]
        self.assertEqual(meles.occurrences(grille, "RAT"), 3)
        # Un palindrome se lit dans les deux sens au meme endroit : une fois.
        self.assertEqual(meles.occurrences([list("RADAR")], "RADAR"), 1)

    def test_le_remplissage_refait_ce_qui_recree_un_mot(self):
        """Un remplissage force a recreer le mot est refuse, pas livre."""
        vide = [[None] * 4 for _ in range(4)]
        for i, lettre in enumerate("RAT"):
            vide[0][i] = lettre
        alea = random.Random("x")
        with mock.patch.object(meles, "_ESSAIS_REMPLISSAGE", 3), \
                mock.patch.object(alea, "choice", lambda _r: "A"):
            # Que des « A » : aucun second « RAT » possible, la grille passe.
            self.assertIsNotNone(meles.remplir(vide, ["RAT"], alea))
        lettres = iter("RAT" * 200)
        with mock.patch.object(meles, "_ESSAIS_REMPLISSAGE", 3), \
                mock.patch.object(alea, "choice", lambda _r: next(lettres)):
            self.assertIsNone(meles.remplir(vide, ["RAT"], alea))


class LaChaine(unittest.TestCase):

    def test_le_cahier_sort_en_a4_et_en_lettre_us(self):
        resume = catalogue.executer(
            "mots-meles", _contexte("le verger"),
            {"nombre": 10, "difficulte": "difficile", "caracteres": "standard"})
        dossier = Path(resume["dossier"])
        self.assertEqual(resume["grilles"], 10)
        a4 = next(dossier.glob("*-A4.pdf"))
        lettre = next(dossier.glob("*-Lettre-US.pdf"))
        # Couverture, regle, dix grilles, trois pages de solutions.
        for pdf, format_page in ((a4, b"595.28 841.89"), (lettre, b"612.00 792.00")):
            brut = pdf.read_bytes()
            self.assertEqual(brut.count(b"/Type /Page "), 15, pdf.name)
            self.assertEqual(brut.count(b"/MediaBox [0 0 " + format_page), 15,
                             pdf.name)
        grilles = json.loads((dossier / "grilles.json").read_text(encoding="utf-8"))
        for grille in grilles["grilles"]:
            for mot in grille["mots"]:
                self.assertEqual(_lu_a_sa_place(grille, mot), mot["forme"])
        texte = (dossier / "mots-meles.md").read_text(encoding="utf-8")
        self.assertIn("```text", texte)
        self.assertIn("CRÈME BRÛLÉE", texte)

    def test_en_anglais_le_cahier_suit(self):
        resume = catalogue.executer(
            "mots-meles", _contexte("the orchard", langue="anglais"),
            {"nombre": 4, "difficulte": "facile", "caracteres": "standard"})
        dossier = Path(resume["dossier"])
        self.assertTrue(list(dossier.glob("*-US-Letter.pdf")))
        self.assertIn("Words to find", (dossier / "lire.html").read_text(
            encoding="utf-8"))

    def test_les_reglages_par_defaut_se_disent(self):
        lignes: List[str] = []
        resume = meles.produire(_contexte("la mer", journal=lignes.append),
                                nombre=4)
        self.assertEqual((resume["difficulte"], resume["caracteres"]),
                         ("moyen", "standard"))
        self.assertEqual(sum("personne ne l'a choisi" in l for l in lignes), 2)

    def test_le_second_lot_connait_les_sous_themes_deja_pris(self):
        INVITES.clear()
        catalogue.executer("mots-meles", _contexte("les oiseaux"),
                           {"nombre": 12, "difficulte": "moyen",
                            "caracteres": "standard"})
        lots = [i for i in INVITES if "grilles de mots meles" in i]
        self.assertEqual(len(lots), 2)
        self.assertNotIn("DEJA PRIS", lots[0])
        self.assertIn("Sous-thème 1", lots[1])

    def test_la_taille_des_mots_demandes_suit_la_grille(self):
        INVITES.clear()
        catalogue.executer("mots-meles", _contexte("les outils"),
                           {"nombre": 4, "difficulte": "facile",
                            "caracteres": "gros"})
        lot = next(i for i in INVITES if "grilles de mots meles" in i)
        self.assertIn("de 3 a 11 lettres", lot)

    def test_une_liste_inutilisable_est_ecartee_et_le_manque_se_dit(self):
        lignes: List[str] = []
        ctx = _contexte("les volcans", journal=lignes.append)

        def listes(_ctx, combien, par_grille, _taille, _deja):
            bonnes = [{"theme": "Thème {}".format(n), "mots": FRUITS[:par_grille]}
                      for n in range(combien - 2)]
            return bonnes + [{"theme": "Trop court", "mots": ["pomme", "poire"]},
                             {"theme": "Thème 0", "mots": FRUITS[:par_grille]}]

        with mock.patch.object(meles, "_rediger_lot", listes):
            resume = catalogue.executer("mots-meles", ctx,
                                        {"nombre": 8, "difficulte": "moyen",
                                         "caracteres": "standard"})
        self.assertEqual(resume["grilles"], 6)
        self.assertIn("6 grilles", resume["titre"])
        self.assertTrue(any("2 liste(s) écartée(s)" in l for l in lignes), lignes)
        etapes = {e["nom"]: e["statut"]
                  for e in store.etapes_produit(ctx.produit_id)}
        self.assertEqual(etapes.get("grilles"), "anomalie")


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class LaReprise(unittest.TestCase):

    def setUp(self):
        atelier.isoler("mots-meles-reprise")

    def tearDown(self):
        llm.definir_simulateur(_espion)

    def test_un_lot_perdu_se_reprend_sans_repayer_le_premier(self):
        lots = {"n": 0}

        def coupe(messages, role):
            if "grilles de mots meles" in messages[-1]["content"]:
                lots["n"] += 1
                if lots["n"] >= 2:
                    raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
            return sim.simulateur(messages, role)

        llm.definir_simulateur(coupe)
        code, _ = _muet(["mots-meles", "les arbres", "-n", "12",
                         "--difficulte", "moyen", "--caracteres", "standard"])
        self.assertEqual(code, 3)
        produit = store.lister_produits()[0]
        dossier = Path(produit["dossier"])
        # Le simulateur est deterministe : un lot refait retomberait sur le
        # cache sans se voir au compteur. Le lot garde est donc marque.
        titre, corps = carnet.section(dossier, "lot-1")
        listes = json.loads(corps)
        listes[0]["theme"] = "Relu du carnet"
        carnet.noter_section(dossier, "lot-1", titre,
                             json.dumps(listes, ensure_ascii=False))

        payes = {"n": 0}

        def compter(messages, role):
            if "grilles de mots meles" in messages[-1]["content"]:
                payes["n"] += 1
            return sim.simulateur(messages, role)

        llm.definir_simulateur(compter)
        code, journal = _muet(["reprendre"])
        self.assertEqual(code, 0, journal[-800:])
        self.assertEqual(payes["n"], 1)
        apres = store.lister_produits()[0]
        self.assertEqual(apres["statut"], "pret")
        grilles = json.loads((Path(apres["dossier"]) / "grilles.json").read_text(
            encoding="utf-8"))["grilles"]
        self.assertEqual(len(grilles), 12)
        self.assertEqual(grilles[0]["theme"], "Relu du carnet")


class LesPortes(unittest.TestCase):

    def test_la_ligne_de_commande(self):
        args = cli.construire_parseur().parse_args(
            ["mots-meles", "la mer", "-n", "20", "--difficulte", "facile",
             "--caracteres", "gros"])
        self.assertEqual((args.nombre, args.difficulte, args.caracteres, args._type),
                         (20, "facile", "gros", "mots-meles"))

    def test_le_menu_propose_les_deux_reglages(self):
        from usine import menu

        reponses = iter(["4", "3"])
        with redirect_stdout(io.StringIO()), mock.patch(
                "builtins.input", lambda invite="": next(reponses, "")):
            self.assertEqual(menu._options_du_type("mots-meles"),
                             {"difficulte": "difficile", "caracteres": "gros"})

    def test_l_usine_les_decide_quand_personne_ne_les_choisit(self):
        ctx = _contexte("les jardins")
        catalogue.executer("mots-meles", ctx, {"nombre": 4})
        decides = ctx.meta.get("reglages_decides", {})
        self.assertIn("difficulte", decides)
        self.assertIn("caracteres", decides)


if __name__ == "__main__":
    unittest.main()
