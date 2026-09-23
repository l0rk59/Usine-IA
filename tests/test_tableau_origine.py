"""Une page web quelconque ne pilote plus le tableau de bord local.

Le tableau de bord n'a pas de mot de passe en mode local, parce que
« 127.0.0.1, c'est moi ». Sur un telephone c'est faux : toute page ouverte
dans le navigateur peut ecrire a 127.0.0.1:8777.

Mesure du 23/09/2026, serveur reel, requete identique a celle qu'envoie un
« fetch(..., {mode: 'no-cors'}) » depuis https://evil.example :

    POST /api/reglages  text/plain  {"marque": "PIRATE", "site": "https://evil.example"}
    -> HTTP 200, reglages reecrits

« site » part dans la notice et le kit de vente de chaque produit livre : une
page visitee au hasard signait les produits de quelqu'un d'autre. Le meme
essai sous un faux nom d'hote (« DNS rebinding ») passait aussi.

Ce qui n'envoie pas d'Origin — la ligne de commande, un script, curl — reste
admis : c'est un processus du telephone.
"""

from __future__ import annotations

import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("tableau-origine")


from usine.core import reglages  # noqa: E402
from usine.web import serveur  # noqa: E402


class _Serveur(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        reglages.ecrire({"marque": "", "site": ""})

    def _envoyer(self, chemin, corps=None, **entetes):
        req = urllib.request.Request(
            "http://127.0.0.1:{}{}".format(self.port, chemin),
            data=corps.encode() if corps is not None else None,
            method="POST" if corps is not None else "GET", headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def _marque(self):
        return reglages.charger(force=True).get("marque")


class UnSiteEtrangerNeModifiePlusRien(_Serveur):

    def test_la_requete_no_cors_d_un_autre_site_est_refusee(self):
        code = self._envoyer(
            "/api/reglages", '{"marque": "PIRATE"}',
            **{"Content-Type": "text/plain;charset=UTF-8",
               "Origin": "https://evil.example"})
        self.assertEqual(code, 403)
        self.assertEqual(self._marque(), "", "un site etranger a reecrit la marque")

    def test_sec_fetch_site_cross_site_est_refuse_meme_sans_origin(self):
        code = self._envoyer("/api/reglages", '{"marque": "PIRATE"}',
                             **{"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(code, 403)
        self.assertEqual(self._marque(), "")

    def test_une_origine_opaque_est_refusee(self):
        """Une page ouverte depuis un fichier ou un iframe isole envoie
        « Origin: null ». Rien de legitime ne modifie l'atelier depuis la."""
        code = self._envoyer("/api/reglages", '{"marque": "PIRATE"}',
                             Origin="null")
        self.assertEqual(code, 403)

    def test_le_rebinding_est_refuse_meme_en_lecture(self):
        """Sous un nom etranger, le site est « de meme origine » que le
        serveur et pourrait LIRE les reponses. Le nom d'hote le trahit."""
        self.assertEqual(self._envoyer("/api/etat", Host="evil.example:8777"), 403)
        code = self._envoyer("/api/reglages", '{"marque": "PIRATE"}',
                             Host="evil.example:{}".format(self.port))
        self.assertEqual(code, 403)
        self.assertEqual(self._marque(), "")


class LeTableauDeBordLuiMemeFonctionneToujours(_Serveur):
    """Le garde-fou qui crie a tort : un tableau de bord qui se refuse a
    lui-meme serait pire que la faille."""

    def test_le_navigateur_sur_la_page_du_tableau_de_bord_est_admis(self):
        code = self._envoyer(
            "/api/reglages", '{"marque": "Ma marque"}',
            **{"Content-Type": "application/json",
               "Origin": "http://127.0.0.1:{}".format(self.port),
               "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(code, 200)
        self.assertEqual(self._marque(), "Ma marque")

    def test_localhost_est_un_nom_admis(self):
        code = self._envoyer(
            "/api/reglages", '{"marque": "Par localhost"}',
            Host="localhost:{}".format(self.port),
            Origin="http://localhost:{}".format(self.port))
        self.assertEqual(code, 200)

    def test_un_script_sans_origin_reste_admis(self):
        """curl, la ligne de commande, un raccourci Termux : aucun n'envoie
        d'Origin. Ce sont des processus du telephone, la frontiere de
        confiance que ce tableau de bord a toujours eue."""
        code = self._envoyer("/api/reglages", '{"marque": "Par script"}',
                             **{"Content-Type": "application/json"})
        self.assertEqual(code, 200)
        self.assertEqual(self._marque(), "Par script")

    def test_la_lecture_ordinaire_passe(self):
        self.assertEqual(self._envoyer("/api/etat"), 200)


if __name__ == "__main__":
    unittest.main()
