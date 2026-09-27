"""Cartes de revision : trois livrables, et trois facons de rater en silence.

Aucune ne fait echouer quoi que ce soit ; chacune ne se voit qu'a l'usage,
chez l'acheteur :

- **la planche** s'imprime en recto-verso. Sans le miroir des versos, la
  feuille retournee sur son bord long pose la reponse de la carte 1 au dos
  de la carte 2 — et le PDF a l'ecran parait parfait ;
- **le fichier Anki** : une tabulation ou un retour a la ligne dans un champ
  decale toutes les colonnes suivantes, et l'import range les reponses
  dans les etiquettes ;
- **une face trop longue** deborde de son rectangle, ou se coupe au milieu
  d'une phrase. La chaine doit le COMPTER et le dire, pas livrer une carte
  illisible marquee « prete ».
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
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
from usine.pipelines import cartes as chaine  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402
from usine.render import cartes as rendu  # noqa: E402
from usine.render import libelles  # noqa: E402
from usine.render.pdf import DocumentPDF  # noqa: E402

INVITES: List[str] = []


def _espion(messages, role):
    INVITES.append(messages[-1]["content"])
    return sim.simulateur(messages, role)


def setUpModule():
    atelier.isoler("cartes")
    llm.definir_simulateur(_espion)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet: str, journal=None, langue: str = "") -> Contexte:
    # Une audience par cas : elle entre dans la consigne systeme, donc dans
    # la cle du cache. Deux cas au meme sujet simule liraient sinon le cache
    # l'un de l'autre, et l'espion ne verrait rien passer.
    ctx = Contexte(sujet=sujet, audience="des eleves de " + sujet,
                   sans_image=True, journal=journal or (lambda _m: None))
    if langue:
        ctx.langue = langue
    return ctx


def _carte(n: int, verso: str = "", theme: str = "Bases"):
    return {"recto": "Question numero {} ?".format(n),
            "verso": verso or "Reponse numero {}.".format(n), "theme": theme}


class _Planche(DocumentPDF):
    """Retient ou chaque carte a ete dessinee, et sur quelle page."""

    def __init__(self):
        super().__init__(titre_document="t", auteur="a",
                         police_corps="Helvetica")
        self.page = 0
        self.cadres = []
        self.textes = []

    def nouvelle_page(self, numeroter: bool = True) -> None:
        self.page += 1
        super().nouvelle_page(numeroter=numeroter)

    def rectangle(self, x, y, largeur, hauteur, *a, **k):
        self.cadres.append((self.page, x, y, largeur))
        super().rectangle(x, y, largeur, hauteur, *a, **k)

    def texte_a(self, contenu, x, y, police, taille, couleur=(0, 0, 0)):
        self.textes.append((self.page, contenu, taille))
        super().texte_a(contenu, x, y, police, taille, couleur)


def _textes(resume) -> str:
    dossier = Path(resume["dossier"])
    return "\n".join(f.read_text(encoding="utf-8")
                     for f in sorted(dossier.glob("*.md")))


# --------------------------------------------------------------------------


class LaPlanche(unittest.TestCase):

    def test_le_verso_est_le_miroir_du_recto(self):
        """Retournee sur son bord long, la feuille inverse gauche et droite :
        la carte de gauche au recto doit etre a droite au verso, a la meme
        hauteur."""
        doc = _Planche()
        rendu.planches(doc, [_carte(n) for n in range(1, 9)])
        rectos = [c for c in doc.cadres if c[0] == 1]
        versos = [c for c in doc.cadres if c[0] == 2]
        self.assertEqual((len(rectos), len(versos)), (8, 8))
        self.assertLess(rectos[0][1], rectos[1][1],
                        "au recto, la carte 1 est a gauche de la carte 2")
        for (_, x_r, y_r, larg), (_, x_v, y_v, _l) in zip(rectos, versos):
            self.assertAlmostEqual(x_r + larg + x_v, doc.largeur, places=3)
            self.assertAlmostEqual(y_r, y_v, places=3)

    def test_chaque_planche_porte_ses_versos_juste_apres(self):
        """Neuf cartes : deux planches, donc quatre pages, dans l'ordre
        recto, verso, recto, verso — et aucune numerotee, un numero de
        page au milieu d'une ligne de coupe tombe sur une carte."""
        doc = _Planche()
        rendu.planches(doc, [_carte(n) for n in range(1, 10)])
        self.assertEqual(doc.page, 4)
        self.assertEqual(sum(1 for c in doc.cadres if c[0] == 3), 1)
        verso_seul = [t for t in doc.textes if t[0] == 4]
        self.assertIn("Reponse numero 9.", [t[1] for t in verso_seul])
        doc._fermer_page()
        self.assertFalse(any(numeroter for _flux, numeroter in doc._pages))

    def test_une_face_longue_rapetisse_avant_d_etre_coupee(self):
        doc = _Planche()
        largeur = (doc.largeur - 2 * rendu.MARGE_PAGE) / rendu.COLONNES \
            - 2 * rendu.MARGE_CARTE
        hauteur = (doc.hauteur - 2 * rendu.MARGE_PAGE) / rendu.RANGEES \
            - 2 * rendu.MARGE_CARTE - 14
        moyen = " ".join(["phrase"] * 70)
        taille, _lignes, coupe = rendu._ajuster(
            doc, moyen, "Helvetica", rendu.TAILLES_VERSO, largeur, hauteur)
        self.assertFalse(coupe)
        self.assertLess(taille, rendu.TAILLES_VERSO[0])

    def test_une_face_qui_ne_tient_pas_est_coupee_et_comptee(self):
        doc = _Planche()
        fleuve = " ".join("phrase{}".format(n) for n in range(300))
        mesure = rendu.planches(doc, [_carte(1, verso=fleuve), _carte(2)])
        self.assertEqual(mesure, {"coupees": 1})
        derniere = [t[1] for t in doc.textes
                    if t[0] == 2 and t[1].startswith("phrase")][-1]
        self.assertTrue(derniere.endswith("…"), derniere)

    def test_une_planche_ordinaire_ne_coupe_rien(self):
        self.assertEqual(rendu.planches(_Planche(), [_carte(1), _carte(2)]),
                         {"coupees": 0})


class LeFichierAnki(unittest.TestCase):

    def test_les_en_tetes_et_une_ligne_par_carte(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = rendu.fichier_anki(
                Path(dossier) / "a.txt",
                [_carte(1, theme="Verbes courants"), _carte(2, theme="")],
                ("Recto", "Verso", "Thème"))
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lignes[:4], ["#separator:Tab", "#html:false",
                                      "#columns:Recto\tVerso\tThème",
                                      "#tags column:3"])
        self.assertEqual(len(lignes), 6)
        self.assertEqual(lignes[4].split("\t"),
                         ["Question numero 1 ?", "Reponse numero 1.",
                          "Verbes_courants"])
        self.assertEqual(lignes[5].split("\t")[2], "")

    def test_une_tabulation_dans_un_champ_ne_decale_pas_les_colonnes(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = rendu.fichier_anki(
                Path(dossier) / "a.txt",
                [{"recto": "Deux\tcolonnes ?", "verso": "Ligne un\nligne deux",
                  "theme": "a\tb"}], ("R", "V", "T"))
            ligne = chemin.read_text(encoding="utf-8").splitlines()[4]
        self.assertEqual(ligne.split("\t"),
                         ["Deux colonnes ?", "Ligne un ligne deux", "a_b"])


class LaPage(unittest.TestCase):

    def test_le_texte_d_une_carte_ne_ferme_pas_le_script(self):
        piege = "</script><script>alert(1)</script>"
        page = rendu.corps([_carte(1, verso=piege)],
                           libelles.FR["cartes_script"], "intro")
        # Deux fermetures : celles des deux blocs de donnees, pas une de plus.
        self.assertEqual(page.count("</script>"), 2)
        self.assertIn("&lt;script&gt;alert", page)

    def test_la_typographie_francaise_ne_se_coupe_pas(self):
        """Le navigateur coupe a toute espace ordinaire : sans espace
        insecable, le « » » d'une reponse tombait seul en tete de ligne."""
        page = rendu.corps([_carte(1, verso="On dit « went » : toujours.")],
                           libelles.FR["cartes_script"], "intro")
        self.assertIn("«\u00a0went\u00a0»\u00a0:", page)

    def test_le_script_se_lit(self):
        if not shutil.which("node"):
            self.skipTest("node absent : le script ne peut pas etre verifie")
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "cartes.js"
            chemin.write_text(rendu.SCRIPT, encoding="utf-8")
            rendu_node = subprocess.run(["node", "--check", str(chemin)],
                                        capture_output=True, text=True)
        self.assertEqual(rendu_node.returncode, 0, rendu_node.stderr)


class LaChaine(unittest.TestCase):

    def test_les_trois_livrables_sortent(self):
        resume = catalogue.executer("cartes", _contexte("la photosynthese"),
                                    {"nombre": 10, "niveau": "debutant"})
        dossier = Path(resume["dossier"])
        self.assertEqual(resume["cartes"], 10)
        self.assertTrue(list(dossier.glob("*planches-a-decouper.pdf")))
        anki = (dossier / "cartes-anki.txt").read_text(encoding="utf-8")
        self.assertEqual(len(anki.splitlines()), 4 + 10)
        page = (dossier / "cartes.html").read_text(encoding="utf-8")
        donnees = page.split('id="cartes">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(len(json.loads(donnees)), 10)
        self.assertIn(libelles.FR["cartes_script"]["retourner"], page)
        for nom in resume["fichiers"]:
            self.assertTrue((dossier / nom).exists(), nom)

    def test_en_anglais_les_noms_de_fichiers_suivent(self):
        resume = catalogue.executer(
            "cartes", _contexte("the water cycle", langue="anglais"),
            {"nombre": 8, "niveau": "debutant"})
        dossier = Path(resume["dossier"])
        self.assertTrue((dossier / "flashcards-anki.txt").exists())
        self.assertTrue((dossier / "flashcards.html").exists())
        self.assertTrue(list(dossier.glob("*cut-out-sheets.pdf")))
        self.assertFalse((dossier / "cartes.html").exists())

    def test_le_niveau_arrive_a_l_invite(self):
        INVITES.clear()
        catalogue.executer("cartes", _contexte("la mecanique quantique"),
                           {"nombre": 8, "niveau": "avance"})
        lots = [i for i in INVITES if "cartes de revision" in i]
        self.assertTrue(lots)
        self.assertIn("NIVEAU : avance", lots[0])

    def test_le_niveau_par_defaut_se_dit(self):
        lignes: List[str] = []
        chaine.produire(_contexte("les fractions", journal=lignes.append),
                        nombre=8)
        self.assertTrue(any("personne ne l'a choisi" in l for l in lignes))

    def test_le_deuxieme_lot_connait_les_rectos_deja_ecrits(self):
        INVITES.clear()
        resume = catalogue.executer("cartes", _contexte("la revolution"),
                                    {"nombre": 20, "niveau": "intermediaire"})
        lots = [i for i in INVITES if "cartes de revision" in i]
        self.assertEqual(len(lots), 2)
        self.assertNotIn("DEJA ECRITES", lots[0])
        self.assertIn("DEJA ECRITES", lots[1])
        self.assertIn("Que veut dire la notion numero 1 ?", lots[1])
        self.assertEqual(resume["cartes"], 20)

    def test_un_doublon_est_ecarte_et_le_manque_se_dit(self):
        """Un modele repete volontiers une carte d'un lot a l'autre. Le
        paquet sort plus mince, et il le dit : titre, journal, etape."""
        lignes: List[str] = []
        ctx = _contexte("les capitales", journal=lignes.append)
        with mock.patch.object(chaine, "_rediger_lot",
                               lambda _c, combien, _n, _d: [
                                   _carte(n) for n in range(1, combien + 1)]):
            resume = catalogue.executer("cartes", ctx,
                                        {"nombre": 20, "niveau": "debutant"})
        self.assertEqual(resume["cartes"], 12)
        self.assertIn("12 cartes", resume["titre"])
        self.assertTrue(any("écartées" in l for l in lignes))
        etapes = {e["nom"]: e["statut"]
                  for e in store.etapes_produit(ctx.produit_id)}
        self.assertEqual(etapes.get("cartes"), "anomalie")

    def test_une_face_coupee_a_l_impression_se_dit(self):
        fleuve = " ".join("phrase{}".format(n) for n in range(300))
        ctx = _contexte("les volcans")
        with mock.patch.object(chaine, "_rediger_lot",
                               lambda _c, combien, _n, _d: [
                                   _carte(n, verso=fleuve if n == 1 else "")
                                   for n in range(1, combien + 1)]):
            resume = catalogue.executer("cartes", ctx,
                                        {"nombre": 8, "niveau": "debutant"})
        etapes = {e["nom"]: e["statut"]
                  for e in store.etapes_produit(ctx.produit_id)}
        self.assertEqual(etapes.get("planches"), "anomalie")
        # La page et Anki gardent le texte entier : seule la planche coupe.
        anki = (Path(resume["dossier"]) / "cartes-anki.txt").read_text(
            encoding="utf-8")
        self.assertIn("phrase299", anki)

    def test_une_carte_vide_ou_qui_se_repete_est_ecartee(self):
        self.assertIsNone(chaine._valider({"recto": "Quoi ?", "verso": ""}))
        self.assertIsNone(chaine._valider({"recto": "", "verso": "Ceci."}))
        self.assertIsNone(chaine._valider({"recto": "Paris", "verso": "paris"}))
        self.assertIsNone(chaine._valider("pas une carte"))
        self.assertEqual(chaine._valider({"recto": "**Quoi** ?", "verso": "Ceci."}),
                         {"recto": "Quoi ?", "verso": "Ceci.", "theme": ""})


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class LaReprise(unittest.TestCase):

    def setUp(self):
        atelier.isoler("cartes-reprise")

    def tearDown(self):
        llm.definir_simulateur(_espion)

    def test_un_lot_perdu_se_reprend_sans_repayer_les_autres(self):
        lots = {"n": 0}

        def coupe_au_deuxieme_lot(messages, role):
            if "cartes de revision" in messages[-1]["content"]:
                lots["n"] += 1
                if lots["n"] >= 2:
                    raise llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
            return sim.simulateur(messages, role)

        llm.definir_simulateur(coupe_au_deuxieme_lot)
        code, _texte = _muet(["cartes", "la cellule vegetale", "-n", "30",
                              "--niveau", "debutant"])
        self.assertEqual(code, 3)
        produit = store.lister_produits()[0]
        self.assertEqual(produit["statut"], "en_cours")
        dossier = Path(produit["dossier"])
        self.assertEqual(carnet.compte(dossier), 1)
        # Le simulateur est deterministe : un lot refait retomberait sur le
        # cache et ne se verrait pas au compteur. On marque donc le lot garde
        # au carnet, et c'est la marque qu'on cherche dans le produit fini.
        titre, corps = carnet.section(dossier, "lot-1")
        cartes = json.loads(corps)
        cartes[0]["recto"] = "Carte relue du carnet ?"
        carnet.noter_section(dossier, "lot-1", titre,
                             json.dumps(cartes, ensure_ascii=False))

        payes = {"n": 0}

        def compter(messages, role):
            if "cartes de revision" in messages[-1]["content"]:
                payes["n"] += 1
            return sim.simulateur(messages, role)

        llm.definir_simulateur(compter)
        code, journal = _muet(["reprendre"])
        self.assertEqual(code, 0, journal[-800:])
        self.assertEqual(payes["n"], 2, "seuls les deux lots perdus se repaient")
        apres = store.lister_produits()[0]
        self.assertEqual(apres["statut"], "pret")
        anki = (Path(apres["dossier"]) / "cartes-anki.txt").read_text(
            encoding="utf-8")
        self.assertIn("Carte relue du carnet ?", anki)
        self.assertEqual(len(anki.splitlines()), 4 + 30)


class LesPortes(unittest.TestCase):

    def test_la_ligne_de_commande_connait_le_type(self):
        args = cli.construire_parseur().parse_args(
            ["cartes", "la chimie", "-n", "16", "--niveau", "avance"])
        self.assertEqual((args.nombre, args.niveau, args._type),
                         (16, "avance", "cartes"))

    def test_le_menu_propose_le_niveau(self):
        from usine import menu

        reponses = iter(["2"])
        with redirect_stdout(io.StringIO()), mock.patch(
                "builtins.input", lambda invite="": next(reponses, "")):
            self.assertEqual(menu._options_du_type("cartes"),
                             {"niveau": "debutant"})

    def test_l_usine_decide_le_niveau_quand_personne_ne_le_choisit(self):
        ctx = _contexte("le code de la route")
        catalogue.executer("cartes", ctx, {"nombre": 8})
        self.assertIn("niveau", ctx.meta.get("reglages_decides", {}))


if __name__ == "__main__":
    unittest.main()
