"""« --hors-ligne » : aucune connexion ne sort de l'appareil.

L'option promettait « ne rien telecharger (IA locale) ». Elle etait lue par
les images, le marche et la veille ; le routeur IA n'en savait rien. Mesure du
25/09/2026 : « usine ebook ... --hors-ligne » avec une cle Groq a envoye ses
invites a Groq.

L'audit du 14/09/2026 avait pourtant compte « zero connexion ». Il tournait
avec le simulateur, qui REMPLACE le routeur : exactement la ou la fuite se
produisait, il n'y avait plus rien a mesurer. Ces tests font donc passer la
fabrication par le vrai routeur et le vrai client HTTP, jusqu'a de vrais
serveurs : un faux ollama qui repond comme le simulateur, et un faux
fournisseur distant qui compte ce qu'il recoit.
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import config, http, llm  # noqa: E402


def setUpModule():
    atelier.isoler("hors-ligne")


class Serveur:
    """Un serveur compatible OpenAI. « simule » : il repond comme le
    simulateur de la suite ; sinon, une phrase fixe."""

    def __init__(self, simule: bool):
        self.recus = 0
        serveur_ref = self

        class Poignee(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self._repondre({"object": "list",
                                "data": [{"id": "qwen2.5:3b"},
                                         {"id": "llama-3.3-70b-versatile"}]})

            def do_POST(self):
                taille = int(self.headers.get("Content-Length") or 0)
                charge = json.loads(self.rfile.read(taille) or b"{}")
                serveur_ref.recus += 1
                texte = (simulateur(charge.get("messages", []), "standard")
                         if simule else "Une reponse du service distant.")
                self._repondre({"choices": [{"message": {"content": texte},
                                             "finish_reason": "stop"}],
                                "usage": {"total_tokens": 10}})

            def _repondre(self, charge):
                corps = json.dumps(charge).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Poignee)
        self.url = "http://127.0.0.1:{}/v1".format(self._http.server_port)

    def __enter__(self):
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self._http.shutdown()
        self._http.server_close()


class Montage:
    """Groq est « distant » (un faux serveur qui compte), ollama est local.

    Les deux ecoutent sur la boucle locale : pour savoir ce qui serait parti
    sur le reseau, on regarde QUI a recu, pas l'adresse de connexion.
    """

    def __init__(self, distant: Serveur, local: Serveur):
        self.distant, self.local = distant, local

    def __enter__(self):
        self._urls = {n: config.PROVIDERS_BY_NAME[n].base_url
                      for n in ("groq", "ollama")}
        self._env = {n: os.environ.get(n)
                     for n in ("USINE_PROVIDERS", "GROQ_API_KEY")}
        config.PROVIDERS_BY_NAME["groq"].base_url = self.distant.url
        config.PROVIDERS_BY_NAME["ollama"].base_url = self.local.url
        os.environ["USINE_PROVIDERS"] = "groq,ollama"
        os.environ["GROQ_API_KEY"] = "gsk_" + "A" * 32
        from usine.core import cles as pool_cles

        pool_cles.oublier()
        llm._REPOS.clear()
        llm.definir_simulateur(None)
        return self

    def __exit__(self, *args):
        from usine.core import cles as pool_cles

        for nom, url in self._urls.items():
            config.PROVIDERS_BY_NAME[nom].base_url = url
        for nom, valeur in self._env.items():
            if valeur is None:
                os.environ.pop(nom, None)
            else:
                os.environ[nom] = valeur
        pool_cles.oublier()
        llm._REPOS.clear()


class EspionDeSockets:
    """Toute connexion ouverte, avec son hote. Rien ne passe inapercu : urllib
    ouvre ses connexions par « socket.create_connection »."""

    def __init__(self):
        self.hotes = []

    def __enter__(self):
        self._vrai = socket.create_connection

        def espion(adresse, *args, **kwargs):
            self.hotes.append(adresse[0])
            return self._vrai(adresse, *args, **kwargs)

        socket.create_connection = espion
        return self

    def __exit__(self, *args):
        socket.create_connection = self._vrai

    def hors_de_l_appareil(self):
        return [h for h in self.hotes if h not in ("127.0.0.1", "localhost", "::1")]


def _commande(argv):
    from usine import cli

    sortie = io.StringIO()
    with redirect_stdout(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class UneFabricationHorsLigne(unittest.TestCase):

    def test_aucune_invite_ne_part_vers_un_distant(self):
        with Serveur(simule=True) as distant, Serveur(simule=True) as local, \
                Montage(distant, local), EspionDeSockets() as espion:
            code, texte = _commande(["ebook", "la prospection pour freelances",
                                     "-T", "mini", "--hors-ligne",
                                     "--sans-image"])
        self.assertEqual(code, 0, texte[-1500:])
        self.assertEqual(distant.recus, 0)
        self.assertGreater(local.recus, 0)
        self.assertEqual(espion.hors_de_l_appareil(), [])

    def test_sans_l_option_le_distant_ecrit(self):
        """Le temoin : sans lui, le test ci-dessus passerait aussi avec un
        montage ou le distant n'est jamais joignable."""
        with Serveur(simule=True) as distant, Serveur(simule=True) as local, \
                Montage(distant, local):
            reponse = llm.generer("Ecris une phrase.", cache=False)
        self.assertEqual(reponse.fournisseur, "groq")
        self.assertEqual(distant.recus, 1)

    def test_le_choix_de_niche_ne_sonde_pas_le_marche(self):
        """Sans sujet, l'usine choisit une niche et mesure chaque piste sur
        des sources publiques. Hors ligne, elle ne mesure rien, et le dit.

        Un atelier vide : avec un produit deja fabrique, l'usine explore
        autour de lui et ne sonde pas le marche — le test ne mesurerait rien.
        """
        atelier.isoler("hors-ligne-vide")
        try:
            with Serveur(simule=True) as distant, Serveur(simule=True) as local, \
                    Montage(distant, local), EspionDeSockets() as espion:
                code, texte = _commande(["ebook", "-T", "mini", "--hors-ligne",
                                         "--sans-image"])
        finally:
            atelier.isoler("hors-ligne")
        self.assertEqual(code, 0, texte[-1500:])
        self.assertEqual(distant.recus, 0)
        self.assertEqual(espion.hors_de_l_appareil(), [])
        self.assertIn("proposee, pas mesuree", texte)


class LaSortieEstFermee(unittest.TestCase):

    def test_une_connexion_distante_est_refusee_sans_etre_rejouee(self):
        essais = []

        def action():
            essais.append(1)
            return http.requete("https://exemple.invalide/", timeout=2)

        debut = time.time()
        with http.hors_ligne(), EspionDeSockets() as espion:
            with self.assertRaises(http.HorsLigne):
                http.insister(action, tentatives=3)
        self.assertEqual(len(essais), 1)
        self.assertLess(time.time() - debut, 1.0)
        self.assertEqual(espion.hotes, [])

    def test_un_ollama_du_reseau_domestique_reste_permis(self):
        """L'utilisateur l'a configure pour cela : c'est son IA locale."""
        ollama = config.PROVIDERS_BY_NAME["ollama"]
        ancienne = ollama.base_url
        ollama.base_url = "http://192.168.1.20:11434/v1"
        try:
            with http.hors_ligne():
                http._verifier_sortie("http://192.168.1.20:11434/v1/models")
                with self.assertRaises(http.HorsLigne):
                    http._verifier_sortie("http://192.168.1.21/")
        finally:
            ollama.base_url = ancienne

    def test_savoir_si_l_on_est_en_ligne_n_ouvre_rien(self):
        with http.hors_ligne(), EspionDeSockets() as espion:
            self.assertFalse(http.en_ligne(timeout=1))
        self.assertEqual(espion.hotes, [])

    def test_le_mode_est_propre_au_fil(self):
        """Le tableau de bord fabrique plusieurs produits dans un processus."""
        vu = []
        with http.hors_ligne():
            fil = threading.Thread(target=lambda: vu.append(http.hors_ligne_actif()))
            fil.start()
            fil.join()
            self.assertTrue(http.hors_ligne_actif())
        self.assertEqual(vu, [False])
        self.assertFalse(http.hors_ligne_actif())


if __name__ == "__main__":
    unittest.main()
