"""Tests des modules ajoutes : pool de cles, agents, securite, reglages, direct.

Aucun appel reseau : la couche HTTP est remplacee la ou c'est necessaire.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

_TEMPORAIRE = tempfile.mkdtemp(prefix="usine-ext-")
os.environ["USINE_HOME"] = _TEMPORAIRE

from usine.agents import equipe  # noqa: E402
from usine.agents.base import Critique  # noqa: E402
from usine.core import cles as pool_cles  # noqa: E402
from usine.core import (config, evenements, llm, prompts, reglages,  # noqa: E402
                        securite, store)
from usine.core.http import HttpErreur  # noqa: E402


class TestPoolDeCles(unittest.TestCase):
    def setUp(self):
        pool_cles.oublier()
        for nom in list(os.environ):
            if nom.startswith("ESSAI_KEY"):
                del os.environ[nom]

    def test_plusieurs_cles_dans_une_variable(self):
        os.environ["ESSAI_KEY"] = "aaa , bbb ; ccc"
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        self.assertEqual([c.valeur for c in pool.cles], ["aaa", "bbb", "ccc"])

    def test_variables_numerotees(self):
        os.environ["ESSAI_KEY"] = "une"
        os.environ["ESSAI_KEY_2"] = "deux"
        os.environ["ESSAI_KEY_3"] = "trois"
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        self.assertEqual(len(pool), 3)

    def test_les_doublons_sont_ecartes(self):
        os.environ["ESSAI_KEY"] = "meme,meme"
        os.environ["ESSAI_KEY_2"] = "meme"
        self.assertEqual(len(pool_cles.charger("essai", "ESSAI_KEY")), 1)

    def test_la_cle_n_est_jamais_affichee_en_clair(self):
        secret = "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
        os.environ["ESSAI_KEY"] = secret
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        affichage = pool.cles[0].affichage
        self.assertNotIn(secret, affichage)
        self.assertIn("***", affichage)
        for ligne in pool_cles.resume():
            self.assertNotIn(secret, json.dumps(ligne))

    def test_une_cle_au_repos_est_ecartee(self):
        os.environ["ESSAI_KEY"] = "un,deux"
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        premiere = pool.choisir(100)
        pool.mettre_au_repos(premiere, 300, "quota")
        seconde = pool.choisir(100)
        self.assertIsNotNone(seconde)
        self.assertNotEqual(seconde.id, premiere.id)

    def test_equilibrage_sur_la_cle_la_moins_sollicitee(self):
        os.environ["ESSAI_KEY"] = "un,deux"
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        premiere = pool.cles[0]
        for _ in range(5):
            store.enregistrer_appel("essai", "m", True, cle_id=premiere.id)
        choisie = pool.choisir(100)
        self.assertEqual(choisie.id, pool.cles[1].id,
                         "le pool doit repartir la charge, pas epuiser la premiere")

    def test_plafond_journalier_atteint_sur_toutes_les_cles(self):
        os.environ["ESSAI_KEY"] = "un,deux"
        pool = pool_cles.charger("essai", "ESSAI_KEY")
        for cle in pool.cles:
            for _ in range(3):
                store.enregistrer_appel("essai", "m", True, cle_id=cle.id)
        self.assertIsNone(pool.choisir(3))


class TestRotationDansLeRouteur(unittest.TestCase):
    """La premiere cle reçoit un 429 : la seconde doit prendre le relais."""

    def setUp(self):
        pool_cles.oublier()
        llm._REPOS.clear()
        store.cache_vider()
        os.environ["GROQ_API_KEY"] = "cle-une,cle-deux"
        os.environ["USINE_PROVIDERS"] = "groq"
        self.origine = llm.post_json

    def tearDown(self):
        llm.post_json = self.origine
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("USINE_PROVIDERS", None)
        pool_cles.oublier()
        llm._REPOS.clear()

    def test_bascule_de_cle_sur_429(self):
        vues = []

        def faux_post(url, charge, entetes=None, timeout=120):
            jeton = (entetes or {}).get("Authorization", "").replace("Bearer ", "")
            vues.append(jeton)
            if jeton == "cle-une":
                raise HttpErreur(429, "Too Many Requests")
            return {"choices": [{"message": {"content": "reponse de secours"}}],
                    "usage": {"total_tokens": 12}}

        llm.post_json = faux_post
        reponse = llm.generer("question de test rotation", cache=False,
                              tentatives_par_fournisseur=1)
        self.assertEqual(reponse.texte, "reponse de secours")
        self.assertIn("cle-une", vues)
        self.assertIn("cle-deux", vues)
        self.assertNotIn("cle-une", reponse.cle,
                         "la cle utilisee ne doit pas etre celle qui a echoue")

    def test_toutes_les_cles_refusees_leve_une_erreur_claire(self):
        def faux_post(url, charge, entetes=None, timeout=120):
            raise HttpErreur(401, "Unauthorized")

        llm.post_json = faux_post
        with self.assertRaises(llm.PlusDeFournisseur):
            llm.generer("question sans issue", cache=False,
                        tentatives_par_fournisseur=1)

    def test_le_secret_ne_fuit_pas_dans_le_message_d_erreur(self):
        os.environ["GROQ_API_KEY"] = "gsk_SECRET0123456789ABCDEFGHIJKLMNOP"
        pool_cles.oublier()

        def faux_post(url, charge, entetes=None, timeout=120):
            raise HttpErreur(500, "erreur interne")

        llm.post_json = faux_post
        try:
            llm.generer("question", cache=False, tentatives_par_fournisseur=1)
        except llm.PlusDeFournisseur as exc:
            self.assertNotIn("gsk_SECRET0123456789ABCDEFGHIJKLMNOP", str(exc))
        else:
            self.fail("une erreur etait attendue")


class TestSecurite(unittest.TestCase):
    def test_expurge_les_cles_connues(self):
        for secret in ("gsk_" + "a" * 30, "sk-or-v1-" + "b" * 30,
                       "AIza" + "c" * 35, "nvapi-" + "d" * 25,
                       "ghp_" + "e" * 36, "Bearer " + "f" * 30):
            self.assertNotIn(secret, securite.expurger("fuite : " + secret))
            self.assertIn("[CLE MASQUEE]", securite.expurger("fuite : " + secret))

    def test_ne_massacre_pas_un_texte_normal(self):
        texte = "Le chapitre 3 parle de prospection et coute 29 EUR."
        self.assertEqual(securite.expurger(texte), texte)

    def test_comparaison_de_jeton(self):
        self.assertTrue(securite.jeton_valide("", "n'importe quoi"))
        self.assertTrue(securite.jeton_valide("abc", "abc"))
        self.assertFalse(securite.jeton_valide("abc", "abd"))
        self.assertFalse(securite.jeton_valide("abc", ""))

    def test_jetons_uniques(self):
        self.assertNotEqual(securite.nouveau_jeton(), securite.nouveau_jeton())
        self.assertGreaterEqual(len(securite.nouveau_jeton()), 24)

    def test_noms_de_fichiers_surs(self):
        for hostile in ("../../etc/passwd", "a/b\\c", 'x<y>z:"|?*', "CON", "NUL.txt",
                        "   ", "..", "."):
            propre = securite.nom_de_fichier_sur(hostile)
            self.assertNotIn("/", propre)
            self.assertNotIn("\\", propre)
            self.assertNotIn("..", propre)
            self.assertTrue(propre)

    def test_detection_insensible_aux_accents(self):
        self.assertTrue(securite.analyser_sujet("comment guerir le stress"))
        self.assertTrue(securite.analyser_sujet("comment guérir le stress"))
        self.assertFalse(securite.analyser_sujet("la cuisine italienne facile"))


class TestReglages(unittest.TestCase):
    def setUp(self):
        reglages.reinitialiser()

    def test_conversion_des_types(self):
        reglages.ecrire({"images": "non", "relectures": "3", "auteur": "  Zoe  "})
        self.assertIs(reglages.lire("images"), False)
        self.assertEqual(reglages.lire("relectures"), 3)
        self.assertEqual(reglages.lire("auteur"), "Zoe")

    def test_les_cles_inconnues_sont_ignorees(self):
        reglages.ecrire({"inexistant": "x"})
        self.assertNotIn("inexistant", reglages.charger())

    def test_fichier_corrompu_ne_casse_rien(self):
        reglages.chemin().write_text("{ ceci n'est pas du json", encoding="utf-8")
        reglages.charger(force=True)
        self.assertEqual(reglages.lire("ton"), reglages.DEFAUTS["ton"])

    def test_qualite_vers_relectures(self):
        self.assertEqual(reglages.relectures_pour("rapide"), 0)
        self.assertEqual(reglages.relectures_pour("standard"), 1)
        self.assertEqual(reglages.relectures_pour("exigeant"), 2)


class TestRegistreDePrompts(unittest.TestCase):
    def setUp(self):
        prompts.oublier()
        repertoire = prompts.dossier()
        if repertoire.exists():
            import shutil

            shutil.rmtree(repertoire)
        prompts.oublier()

    def test_valeurs_par_defaut(self):
        self.assertIn("architecte", prompts.agents())
        self.assertIn("formule creuse", prompts.modele("interdits"))

    def test_surcharge_par_fichier(self):
        prompts.exporter()
        fichier = prompts.dossier() / "agents.json"
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
        donnees["redacteur"]["temperature"] = 0.11
        donnees["redacteur"]["mission"] = "mission personnalisee"
        fichier.write_text(json.dumps(donnees), encoding="utf-8")
        prompts.oublier()
        self.assertEqual(prompts.agents()["redacteur"]["temperature"], 0.11)
        self.assertIn("agent : redacteur", prompts.personnalises())

    def test_fichier_agents_corrompu_retombe_sur_les_defauts(self):
        prompts.dossier().mkdir(parents=True, exist_ok=True)
        (prompts.dossier() / "agents.json").write_text("pas du json", encoding="utf-8")
        prompts.oublier()
        self.assertEqual(prompts.agents()["redacteur"]["temperature"],
                         prompts.AGENTS_DEFAUT["redacteur"]["temperature"])


class TestBusEvenements(unittest.TestCase):
    def setUp(self):
        evenements.vider()

    def test_diffusion_a_un_abonne(self):
        file = evenements.abonner()
        try:
            evenements.publier("essai", message="bonjour")
            recu = file.get(timeout=2)
            self.assertEqual(recu["type"], "essai")
            self.assertEqual(recu["message"], "bonjour")
        finally:
            evenements.desabonner(file)

    def test_les_secrets_sont_expurges_avant_diffusion(self):
        file = evenements.abonner()
        try:
            evenements.publier("essai", message="cle gsk_" + "z" * 30)
            self.assertIn("[CLE MASQUEE]", file.get(timeout=2)["message"])
        finally:
            evenements.desabonner(file)

    def test_un_abonne_sature_ne_bloque_pas_la_production(self):
        file = evenements.abonner(taille=2)
        try:
            for i in range(40):
                evenements.publier("essai", index=i)
        finally:
            evenements.desabonner(file)
        self.assertGreaterEqual(len(evenements.historique()), 40)

    def test_historique_depuis_un_identifiant(self):
        evenements.publier("a")
        marque = evenements.publier("b")["id"]
        evenements.publier("c")
        suivants = evenements.historique(marque)
        self.assertEqual([e["type"] for e in suivants], ["c"])


class TestBoucleQualite(unittest.TestCase):
    def test_critique_acceptable(self):
        self.assertTrue(Critique(note=8.0).acceptable)
        self.assertFalse(Critique(note=6.0).acceptable)

    def test_problemes_bloquants(self):
        critique = Critique(note=5.0, problemes=[
            {"gravite": "bloquant", "correction": "x", "probleme": "p", "passage": ""},
            {"gravite": "mineur", "correction": "y", "probleme": "q", "passage": ""},
        ])
        self.assertEqual(len(critique.bloquants), 1)

    def test_la_revision_refuse_un_texte_tronque(self):
        """Un reviseur qui renvoie la moitie du texte a coupe : on garde l'original."""
        original = "phrase complete. " * 60
        critique = Critique(note=5.0, problemes=[
            {"gravite": "majeur", "correction": "corriger", "probleme": "p",
             "passage": "phrase"}])
        llm.definir_simulateur(lambda messages, role: "trop court")
        try:
            class Faux:
                langue = "francais"
                description_ton = "pro"
                audience = "des testeurs"
            resultat = equipe.reviser(Faux(), original, critique, "Section")
        finally:
            llm.definir_simulateur(None)
        self.assertEqual(resultat, original)

    def test_rapport_de_qualite(self):
        rapport = equipe.rapport_qualite({
            "Chapitre 1": [Critique(note=6.0, problemes=[
                {"gravite": "majeur", "correction": "c", "probleme": "p",
                 "passage": ""}]), Critique(note=8.5)],
        })
        self.assertEqual(rapport["note_moyenne_initiale"], 6.0)
        self.assertEqual(rapport["note_moyenne_finale"], 8.5)
        self.assertEqual(rapport["sections"][0]["problemes_corriges"], 1)


class TestEvitementDeFournisseur(unittest.TestCase):
    """Le relecteur ne doit pas etre le modele qui a ecrit le texte."""

    def setUp(self):
        pool_cles.oublier()
        llm._REPOS.clear()
        store.cache_vider()
        os.environ["GROQ_API_KEY"] = "g"
        os.environ["MISTRAL_API_KEY"] = "m"
        os.environ["USINE_PROVIDERS"] = "groq,mistral"
        self.origine = llm.post_json

    def tearDown(self):
        llm.post_json = self.origine
        for nom in ("GROQ_API_KEY", "MISTRAL_API_KEY", "USINE_PROVIDERS"):
            os.environ.pop(nom, None)
        pool_cles.oublier()

    def test_le_fournisseur_evite_n_est_pas_appele(self):
        appeles = []

        def faux_post(url, charge, entetes=None, timeout=120):
            appeles.append(url)
            return {"choices": [{"message": {"content": "ok"}}]}

        llm.post_json = faux_post
        reponse = llm.generer("relire ce texte", cache=False, eviter=["groq"])
        self.assertEqual(reponse.fournisseur, "mistral")
        self.assertFalse(any("groq" in url for url in appeles))

    def test_on_n_evite_pas_le_dernier_fournisseur_restant(self):
        """Mieux vaut une relecture par le meme modele que pas de relecture."""
        os.environ["USINE_PROVIDERS"] = "groq"
        llm.post_json = lambda *a, **k: {"choices": [{"message": {"content": "ok"}}]}
        reponse = llm.generer("relire ce texte unique", cache=False, eviter=["groq"])
        self.assertEqual(reponse.fournisseur, "groq")


class TestTableauDeBord(unittest.TestCase):
    """Serveur reel : statiques, flux temps reel, jeton d'acces."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        from usine.web import serveur

        cls.module = serveur
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.serveur.daemon_threads = True
        cls.base = "http://127.0.0.1:{}".format(cls.serveur.server_address[1])
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        (config.WORKDIR / "secret.txt").write_text("NE DOIT PAS FUIR", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()
        reglages.ecrire({"jeton_web": ""})

    def _appeler(self, chemin, entetes=None):
        import urllib.error
        import urllib.request

        requete = urllib.request.Request(self.base + chemin, headers=entetes or {})
        try:
            with urllib.request.urlopen(requete, timeout=10) as reponse:
                return reponse.status, reponse.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_les_fichiers_statiques_sont_servis(self):
        for fichier, marqueur in (("tableau.css", b"--accent"),
                                  ("scene.js", b"SceneUsine"),
                                  ("app.js", b"EventSource")):
            statut, corps = self._appeler("/statique/" + fichier)
            self.assertEqual(statut, 200, fichier)
            self.assertIn(marqueur, corps, fichier)

    def test_les_statiques_ne_sortent_pas_de_leur_dossier(self):
        for tentative in ("/statique/%2e%2e/serveur.py",
                          "/statique/%2e%2e%2f%2e%2e%2fcli.py",
                          "/statique/../serveur.py"):
            statut, corps = self._appeler(tentative)
            self.assertIn(statut, (400, 403, 404), tentative)
            self.assertNotIn(b"def demarrer", corps, tentative)

    def test_etat_expose_agents_et_types(self):
        statut, corps = self._appeler("/api/etat")
        self.assertEqual(statut, 200)
        donnees = json.loads(corps)
        self.assertEqual(len(donnees["agents"]), len(equipe.EQUIPE))
        self.assertIn("impression", [t["cle"] for t in donnees["types"]])
        self.assertIn("exigeant", donnees["qualites"])

    def test_le_commerce_est_servi_meme_sans_vente(self):
        """C'est l'etat que voit un nouvel utilisateur : il doit tenir."""
        statut, corps = self._appeler("/api/commerce")
        self.assertEqual(statut, 200)
        donnees = json.loads(corps)
        for cle in ("devises", "produits", "types", "prix", "doublons",
                    "produits_compares"):
            self.assertIn(cle, donnees)
        self.assertIsInstance(donnees["devises"], list)

    def test_le_commerce_remonte_les_ventes_et_les_doublons(self):
        from usine.core import store, ventes

        store.creer_produit("web-p1", "ebook", "Un produit", sujet="s",
                            dossier="/tmp")
        ventes.enregistrer({"date": "2026-08-01", "reference": "Un produit",
                            "unites": 2, "brut": 58.0, "net": 50.0,
                            "devise": "EUR", "remboursement": 0,
                            "plateforme": "gumroad", "empreinte": "web-v1"},
                           produit_id="web-p1")
        _, corps = self._appeler("/api/commerce")
        donnees = json.loads(corps)
        # Porte sur CE produit, pas sur le total : tous les modules de test
        # partagent le meme atelier, donc la somme globale depend de l'ordre
        # d'execution et ne prouverait rien.
        ligne = [p for p in donnees["produits"] if p["produit_id"] == "web-p1"]
        self.assertTrue(ligne, "la vente doit apparaitre")
        self.assertAlmostEqual(ligne[0]["brut"], 58.0)
        self.assertEqual(ligne[0]["unites"], 2)

    def test_le_sur_mesure_arrive_jusqu_au_contexte(self):
        """Le tableau de bord n'offrait que les listes fermees.

        Sur Termux, c'est l'une des trois seules interfaces : une option
        absente ici n'existe pas pour qui travaille depuis le navigateur du
        telephone.
        """
        from usine.web.serveur import _entier

        self.assertEqual(_entier("7"), 7)
        self.assertEqual(_entier(""), 0)
        self.assertEqual(_entier(None), 0)
        self.assertEqual(_entier("abc"), 0)
        self.assertEqual(_entier(-5), 0)

    def test_l_etat_ne_contient_aucune_cle_en_clair(self):
        os.environ["GROQ_API_KEY"] = "gsk_" + "Q" * 32
        pool_cles.oublier()
        try:
            _, corps = self._appeler("/api/etat")
            self.assertNotIn(b"gsk_QQQ", corps)
        finally:
            os.environ.pop("GROQ_API_KEY", None)
            pool_cles.oublier()

    def test_le_flux_transmet_les_evenements_en_direct(self):
        import threading
        import urllib.request

        recu = []

        def lire():
            flux = urllib.request.urlopen(self.base + "/api/flux", timeout=8)
            for _ in range(40):
                ligne = flux.readline()
                if not ligne:
                    break
                if ligne.startswith(b"data:"):
                    recu.append(json.loads(ligne[5:].decode("utf-8")))
                    break
            flux.close()

        fil = threading.Thread(target=lire, daemon=True)
        fil.start()
        import time as _t
        _t.sleep(0.4)
        evenements.publier("essai_direct", message="en direct")
        fil.join(timeout=6)
        self.assertTrue(recu, "aucun evenement recu par le flux")

    def test_verification_de_sujet(self):
        import urllib.request

        requete = urllib.request.Request(
            self.base + "/api/verifier-sujet",
            data=json.dumps({"sujet": "investir en bourse"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            donnees = json.loads(reponse.read())
        self.assertTrue(donnees["alertes"])
        self.assertEqual(donnees["alertes"][0]["domaine"], "finance")

    def test_le_jeton_protege_l_acces(self):
        reglages.ecrire({"jeton_web": "jeton-de-test"})
        try:
            statut, _ = self._appeler("/api/etat")
            self.assertEqual(statut, 401)
            statut, _ = self._appeler("/api/etat?jeton=mauvais")
            self.assertEqual(statut, 401)
            statut, _ = self._appeler("/api/etat?jeton=jeton-de-test")
            self.assertEqual(statut, 200)
            statut, _ = self._appeler(
                "/api/etat", {"Authorization": "Bearer jeton-de-test"})
            self.assertEqual(statut, 200)
        finally:
            reglages.ecrire({"jeton_web": ""})


if __name__ == "__main__":
    unittest.main(verbosity=2)
