"""La fiction doit etre pilotable depuis le navigateur, pas seulement en CLI.

C'est l'usage normal de cette usine : elle tourne sur un telephone, et son
pilote est le tableau de bord. Une fonction qui n'existe qu'en ligne de
commande n'existe pas pour la plupart des sessions.

Defaut constate le 15/09/2026 : la recherche de promesses de lecture venait
d'etre ecrite, cablee a la CLI, documentee — et introuvable depuis le
navigateur. Le bouton « trouver des niches » y etait seul, et il pose la
mauvaise question a un roman.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("fiction_tableau")


from usine.pipelines import catalogue  # noqa: E402
from usine.web import serveur  # noqa: E402

STATIQUE = RACINE / "usine" / "web" / "statique"
GABARIT = (STATIQUE / "tableau.html").read_text(encoding="utf-8")
SCRIPT = (STATIQUE / "app.js").read_text(encoding="utf-8")


class LaRechercheDeFictionEstAtteignableDepuisLeNavigateur(unittest.TestCase):

    def test_le_bouton_existe_dans_le_gabarit(self):
        self.assertIn('id="file-prospecter-fiction"', GABARIT)

    def test_le_bouton_est_branche_dans_le_script(self):
        """Un bouton sans ecouteur est un bouton mort : il se clique, rien
        ne se passe, et l'utilisateur conclut que la fonction est cassee."""
        self.assertIn("$('file-prospecter-fiction').addEventListener", SCRIPT)

    def test_le_script_demande_bien_l_action_de_fiction(self):
        self.assertIn("prospecter-fiction", SCRIPT)

    def test_la_route_repond_vraiment_a_cette_action(self):
        """Par le RESEAU, pas par une recherche de chaine dans le fichier.

        La premiere version de ce test cherchait « prospecter-fiction » dans
        la source. Une mutation qui retirait l'action de la condition le
        laissait passer : le nom survivait ailleurs dans le fichier. C'est
        l'homonymie que ce depot retrouve a chaque audit — un garde-fou
        satisfait par un nom ne garde rien.
        """
        import json as _json
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer

        lance = []
        pret = threading.Event()

        def faux_lanceur(travail_id, fiction=False):
            # On remplace le LANCEUR, pas « threading.Thread » : le serveur
            # de test est lui-meme un serveur a fils, et le patcher
            # globalement l'empeche de repondre — la premiere version de ce
            # test expirait au bout de vingt secondes.
            lance.append((travail_id, fiction))
            pret.set()

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        httpd.daemon_threads = True
        base = "http://127.0.0.1:{}".format(httpd.server_address[1])
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with mock.patch.object(serveur, "_lancer_prospection",
                                   side_effect=faux_lanceur):
                requete = urllib.request.Request(
                    base + "/api/file",
                    data=_json.dumps({"action": "prospecter-fiction"})
                    .encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(requete, timeout=20) as reponse:
                    charge = _json.loads(reponse.read())
        finally:
            httpd.shutdown()
            httpd.server_close()

        self.assertIn("travail", charge)
        self.assertTrue(pret.wait(10), "le fil de prospection n'a pas demarre")
        # Et le fil lance doit bien demander la FICTION : router les deux
        # boutons vers la meme recherche aurait l'air de marcher.
        self.assertEqual(lance[0], (charge["travail"], True))
        travail = serveur.TRAVAUX.get(charge["travail"]) or {}
        self.assertIn("promesses", travail.get("sujet", ""))

    def test_l_action_appelle_la_recherche_de_promesses_et_non_de_niches(self):
        """Le coeur du cablage : les deux boutons doivent poser deux
        questions DIFFERENTES. Router les deux vers « prospecter » aurait
        l'air de marcher — et redemanderait a un roman quel probleme il
        resout."""
        appels = []

        def fausse_fiction(nombre=8, journal=None):
            appels.append("fiction")
            return {"ajoutees": 2, "en_file": 0, "ecartees": [], "pistes": 2}

        def fausse_niche(nombre=8, graine="", journal=None, avec_veille=True):
            appels.append("niche")
            return {"ajoutees": 2, "en_file": 0, "ecartees": [], "pistes": 2}

        # Les deux travaux doivent exister : le lanceur ecrit son resultat
        # dedans, et sans eux le test mesurerait la gestion d'erreur au lieu
        # du routage.
        for identifiant in ("t1", "t2"):
            serveur.TRAVAUX[identifiant] = {
                "id": identifiant, "type": "prospection", "sujet": "",
                "statut": "en_cours", "debut": 0.0, "journal": [],
                "resultat": None, "erreur": ""}
        try:
            with mock.patch("usine.production.prospecter_fiction",
                            side_effect=fausse_fiction), \
                 mock.patch("usine.production.prospecter",
                            side_effect=fausse_niche):
                serveur._lancer_prospection("t1", fiction=True)
                serveur._lancer_prospection("t2", fiction=False)
            self.assertEqual(serveur.TRAVAUX["t1"]["statut"], "termine")
        finally:
            serveur.TRAVAUX.pop("t1", None)
            serveur.TRAVAUX.pop("t2", None)
        self.assertEqual(appels, ["fiction", "niche"])


class LesTypesSontRangesParFamille(unittest.TestCase):
    """Melangees, « Roman » se cherchait entre « Pack de prompts » et
    « Sequence e-mail » — et les reglages qui suivent n'ont rien de commun
    d'une famille a l'autre."""

    def test_le_serveur_sert_la_famille_de_chaque_type(self):
        for fiche in serveur._catalogue():
            self.assertIn("famille", fiche)
            self.assertTrue(fiche["famille"], fiche["cle"])

    def test_le_script_range_VRAIMENT_les_types_en_groupes(self):
        """On execute le script, on ne le lit pas.

        La premiere version cherchait « optgroup » et « remplirTypes » dans
        le fichier. Une mutation qui remettait l'ancien appel la laissait
        passer : la fonction restait DEFINIE, simplement plus appelee. Un
        detecteur qui lit un nom ne voit pas qu'on a cesse de s'en servir.
        """
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node absent : le script ne peut pas etre execute")
        types = [{"cle": "auto", "nom": "L'usine decide", "famille": ""},
                 {"cle": "roman", "nom": "Roman", "famille": "fiction"},
                 {"cle": "ebook", "nom": "Ebook", "famille": "pratique"}]
        # On n'extrait QUE le bloc a tester : le reste du script touche au
        # DOM et a la scene 3D, qui n'existent pas sous node.
        bloc = SCRIPT[SCRIPT.index("const FAMILLES"):
                      SCRIPT.index("function echapper")]
        programme = (
            bloc
            + "function echapper(t){return String(t);}\n"
            + "const faux = {innerHTML: ''};\n"
            + "remplirTypes(faux, " + json.dumps(types) + ", 'roman');\n"
            + "console.log(faux.innerHTML);\n")
        rendu = subprocess.run(["node", "-e", programme], capture_output=True,
                               text=True, timeout=30)
        self.assertEqual(rendu.returncode, 0, rendu.stderr)
        sortie = rendu.stdout
        self.assertIn('<optgroup label="Fiction">', sortie)
        self.assertIn('<optgroup label="Pratique">', sortie)
        # « L'usine decide » sort AVANT les groupes, sans en-tete.
        self.assertLess(sortie.index("L'usine decide"), sortie.index("optgroup"))
        self.assertIn('value="roman" selected', sortie)

    def test_c_est_bien_ce_remplisseur_la_qui_remplit_la_liste_des_types(self):
        """Exercer la fonction ne suffit pas : encore faut-il qu'on l'appelle.

        Une mutation qui remettait l'ancien remplisseur plat laissait passer
        le test precedent — la fonction restait definie, simplement plus
        utilisee. On regarde donc QUI remplit « $('type') ».
        """
        import re

        appels = re.findall(r"(\w+)\(\$\('type'\)", SCRIPT)
        self.assertEqual(appels, ["remplirTypes"], appels)

    def test_le_choix_sans_famille_reste_hors_groupe(self):
        """« L'usine decide » n'appartient a aucune famille : le ranger dans
        l'une des deux le ferait disparaitre pour qui cherche l'autre."""
        premier = serveur._types_offerts()[0]
        self.assertEqual(premier["cle"], serveur.AUTO)
        self.assertEqual(premier["famille"], "")

    def test_chaque_type_de_fiction_du_catalogue_est_servi(self):
        servis = {f["cle"] for f in serveur._catalogue()
                  if f["famille"] == "fiction"}
        attendus = {f.cle for f in catalogue.TYPES
                    if f.famille == "fiction" and f.fabriquer is not None}
        self.assertEqual(servis, attendus)

    def test_les_reglages_de_fiction_partent_au_navigateur(self):
        """Un reglage declare au catalogue et absent du formulaire est un
        reglage qu'on ne peut pas regler : c'est le defaut que le tableau de
        bord a deja connu sur huit options."""
        for fiche in serveur._catalogue():
            if fiche["famille"] != "fiction":
                continue
            noms = {c["nom"] for c in fiche["champs"]}
            self.assertIn("sous_genre", noms, fiche["cle"])
            self.assertIn("chaleur", noms, fiche["cle"])

    def test_les_choix_d_un_champ_de_fiction_sont_servis(self):
        """Une liste vide cote navigateur donne un champ libre la ou le
        catalogue impose une liste fermee."""
        recueil = next(f for f in serveur._catalogue() if f["cle"] == "recueil")
        chaleur = next(c for c in recueil["champs"] if c["nom"] == "chaleur")
        self.assertIn("porte fermee", chaleur["choix"])
