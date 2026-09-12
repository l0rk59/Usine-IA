"""Le tableau de bord : veille, empreintes et sauvegarde, cote serveur.

Trois choses n'existaient qu'en ligne de commande et dans le menu Termux.
Sur un telephone, le navigateur est souvent l'interface la plus confortable
— et pour la sauvegarde, la seule qui permette de sortir l'archive de
l'appareil.

Ce que ces tests gardent surtout : les titres et les liens affiches ici
viennent d'un flux exterieur, que n'importe qui peut alimenter. Le rendu
dans un vrai navigateur est verifie a la main (Termux n'a pas de Chromium,
et l'usine n'installe aucune dependance) ; le filtrage, lui, se teste.
"""

from __future__ import annotations

import io
import json
import re
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, llm, store, veille  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.web import serveur  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("tableau")


FLUX_SUBS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Meal Prep Sunday</title>
<link href="https://www.reddit.com/r/MealPrepSunday/"/></entry>
</feed>"""

# Le troisieme titre est hostile : une balise dans le titre, un lien en
# « javascript: ». Reddit ne les produit pas — mais le flux n'est pas signe,
# et le tableau de bord est la page qui pilote l'usine.
FLUX_POSTS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Why does meal prep always go wrong on Wednesday</title>
<link href="https://www.reddit.com/r/MealPrepSunday/comments/a/"/>
<updated>2026-01-02T10:00:00+00:00</updated></entry>
<entry><title>Tired of throwing away half my vegetables</title>
<link href="http://www.reddit.com/r/MealPrepSunday/comments/b/"/>
<updated>2026-01-03T10:00:00+00:00</updated></entry>
<entry><title>My &lt;script&gt;alert(1)&lt;/script&gt; routine</title>
<link href="javascript:alert(document.cookie)"/>
<updated>2026-01-04T10:00:00+00:00</updated></entry>
<entry><title>Batch cooking on a real budget</title>
<link href="https://evil.example.test/r/MealPrepSunday/comments/d/"/>
<updated>2026-01-05T10:00:00+00:00</updated></entry>
<entry><title>Meal prep containers that survive a whole week</title>
<link href="https://www.reddit.com/r/MealPrepSunday/comments/e/"/>
<updated>2026-01-06T10:00:00+00:00</updated></entry>
</feed>"""


def _faux_flux(chemin, timeout=15, patience=20.0):
    brut = FLUX_SUBS if "subreddits" in chemin else FLUX_POSTS
    return (veille._ENTREE.findall(brut), "")


class BaseServeur(unittest.TestCase):
    """Un vrai serveur HTTP : les routes se testent par le reseau."""

    @classmethod
    def setUpClass(cls):
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.serveur.daemon_threads = True
        cls.base = "http://127.0.0.1:{}".format(cls.serveur.server_address[1])
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def appeler(self, chemin, corps=None):
        donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
        requete = urllib.request.Request(
            self.base + chemin, data=donnees,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(requete, timeout=20) as reponse:
                return reponse.status, reponse.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, chemin, corps=None):
        statut, brut = self.appeler(chemin, corps)
        return statut, json.loads(brut)


class TestVeille(BaseServeur):

    def _consulter(self, sujet="meal planning", periode="year"):
        with mock.patch.object(veille, "_flux", _faux_flux), \
                mock.patch.object(veille.time, "sleep", lambda s: None):
            statut, lance = self.json("/api/veille",
                                      {"sujet": sujet, "periode": periode})
            self.assertEqual(statut, 200, lance)
            for _ in range(100):
                _, etat = self.json("/api/veille/" + lance["veille"])
                if etat["statut"] != "en_cours":
                    return etat
                threading.Event().wait(0.05)
        self.fail("la veille ne s'est jamais terminee")

    def test_un_sujet_vide_est_refuse(self):
        statut, corps = self.json("/api/veille", {"sujet": "  "})
        self.assertEqual(statut, 400)
        self.assertIn("sujet", corps["erreur"])

    def test_une_periode_inventee_est_refusee(self):
        statut, _ = self.json("/api/veille",
                              {"sujet": "x", "periode": "depuis toujours"})
        self.assertEqual(statut, 400)

    def test_une_veille_inconnue_repond_404(self):
        statut, _ = self.json("/api/veille/nexistepas")
        self.assertEqual(statut, 404)

    def test_la_consultation_rapporte_communautes_et_douleurs(self):
        etat = self._consulter()
        self.assertEqual(etat["statut"], "termine")
        rapport = etat["resultat"]
        self.assertEqual([c["nom"] for c in rapport["communautes"]],
                         ["MealPrepSunday"])
        # Le vocabulaire ne retient que ce qui revient : un mot vu une fois
        # dans un titre n'est pas le vocabulaire d'une communaute.
        self.assertIn("meal", [mot for mot, _ in rapport["mots"]])
        self.assertTrue(all(n > 1 for _, n in rapport["mots"]))
        titres = [d["titre"] for d in rapport["douleurs"]]
        self.assertIn("Why does meal prep always go wrong on Wednesday", titres)
        self.assertNotIn("Batch cooking on a real budget", titres)

    def test_seuls_les_liens_reddit_en_https_passent(self):
        """Un « javascript: » rendu dans une ancre serait une execution de
        script dans la page qui pilote l'usine.

        Le filtrage est cote serveur, et non dans le script : ce qui n'est
        jamais envoye ne peut pas etre affiche par erreur plus tard.
        """
        rapport = self._consulter()["resultat"]
        liens = {d["titre"]: d["lien"] for d in rapport["discussions"]}
        self.assertEqual(liens["My <script>alert(1)</script> routine"], "")
        self.assertEqual(liens["Tired of throwing away half my vegetables"], "",
                         "http simple accepte")
        self.assertEqual(liens["Batch cooking on a real budget"], "",
                         "un hote qui imite reddit accepte")
        self.assertTrue(
            liens["Why does meal prep always go wrong on Wednesday"]
            .startswith("https://www.reddit.com/"))

    def test_le_titre_hostile_est_transmis_tel_quel(self):
        """Le serveur ne nettoie pas le texte : c'est la page qui l'echappe.

        Le nettoyer ici mentirait sur ce que les gens ont ecrit, et laisserait
        croire que l'affichage est sur alors qu'il ne le serait que pour les
        cas prevus.
        """
        rapport = self._consulter()["resultat"]
        titres = [d["titre"] for d in rapport["discussions"]]
        self.assertIn("My <script>alert(1)</script> routine", titres)

    def test_deux_veilles_simultanees_sont_refusees(self):
        """Reddit compte par adresse, pas par onglet : elles se prendraient
        mutuellement le 429."""
        with mock.patch.object(serveur, "VEILLES",
                               {"x": {"id": "x", "statut": "en_cours"}}):
            statut, corps = self.json("/api/veille", {"sujet": "autre chose"})
        self.assertEqual(statut, 429)
        self.assertIn("deja en cours", corps["erreur"])


class TestEmpreintesManquantes(BaseServeur):

    def test_le_commerce_compte_les_produits_sans_empreinte(self):
        """« Aucun recouvrement » et « rien n'a ete compare » se ressemblent."""
        dossier = config.PRODUITS_DIR / "tab-vide"
        dossier.mkdir(parents=True, exist_ok=True)
        store.creer_produit("tab-vide", "ebook", "Sans matiere", sujet="s",
                            dossier=str(dossier))
        _, donnees = self.json("/api/commerce")
        self.assertGreaterEqual(donnees["sans_empreinte"], 1)

    def test_la_reconstruction_pose_les_empreintes_manquantes(self):
        dossier = config.PRODUITS_DIR / "tab-plein"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "livre.md").write_text(
            "# La prospection\n\n"
            "Prospecter demande une regularite que peu de freelances tiennent. "
            "Bloquez une heure chaque lundi matin, avant toute autre tache. "
            "Ecrivez a cinq personnes precises plutot qu'a cinquante inconnues.\n",
            encoding="utf-8")
        store.creer_produit("tab-plein", "ebook", "La prospection",
                            sujet="prospection", dossier=str(dossier))

        avant = {e["produit_id"] for e in store.lister_empreintes(limite=500)}
        self.assertNotIn("tab-plein", avant)

        _, resultat = self.json("/api/doublons", {"action": "reconstruire"})
        self.assertGreaterEqual(resultat["reconstruites"], 1)
        apres = {e["produit_id"] for e in store.lister_empreintes(limite=500)}
        self.assertIn("tab-plein", apres)

    def test_une_action_inconnue_ne_touche_a_rien(self):
        _, resultat = self.json("/api/doublons", {"action": "tout effacer"})
        self.assertIn("erreur", resultat)


class TestSauvegarde(BaseServeur):

    def test_creer_puis_lister_puis_telecharger(self):
        _, cree = self.json("/api/sauvegarde", {"action": "creer"})
        self.assertIn("archive", cree)
        nom = cree["archive"]["nom"]
        self.assertTrue(nom.endswith(".zip"))

        _, liste = self.json("/api/sauvegardes")
        self.assertIn(nom, [a["nom"] for a in liste["archives"]])

        statut, corps = self.appeler("/archive/" + nom)
        self.assertEqual(statut, 200)
        self.assertEqual(corps[:2], b"PK", "ce n'est pas une archive zip")
        import io
        with zipfile.ZipFile(io.BytesIO(corps)) as zip_:
            self.assertIn("usine.db", zip_.namelist())

    def test_la_base_ne_sort_pas_par_la_route_des_archives(self):
        """Le dossier des sauvegardes est a cote de la base et des reglages.

        Une sortie de dossier livrerait « usine.db » en clair, avec les
        ventes et l'historique, a qui a atteint le tableau de bord.
        """
        for tentative in ("../usine.db", "..%2Fusine.db", "%2e%2e/usine.db",
                          "sauvegardes/../../usine.db", "usine.db",
                          "../reglages.json"):
            statut, corps = self.appeler("/archive/" + tentative)
            self.assertIn(statut, (400, 403, 404), tentative)
            self.assertNotIn(b"SQLite format", corps, tentative)

    def test_seules_les_archives_zip_sont_servies(self):
        dossier = config.WORKDIR / "sauvegardes"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "note.txt").write_text("un secret", encoding="utf-8")
        statut, corps = self.appeler("/archive/note.txt")
        self.assertEqual(statut, 404)
        self.assertNotIn(b"un secret", corps)

    def test_une_action_inconnue_n_ecrit_aucune_archive(self):
        _, resultat = self.json("/api/sauvegarde", {"action": "tout effacer"})
        self.assertIn("erreur", resultat)


class TestRestauration(BaseServeur):
    """Remplacer l'atelier depuis la page, sans pouvoir le faire par megarde."""

    def _archive_et_produit_neuf(self):
        """Une archive, puis un produit fabrique APRES elle.

        Le produit d'apres est le temoin : une restauration reussie le fait
        disparaitre, une restauration refusee le laisse en place.
        """
        _, cree = self.json("/api/sauvegarde", {"action": "creer"})
        nom = cree["archive"]["nom"]
        temoin = "temoin-" + nom.replace(".", "-")
        store.creer_produit(temoin, "ebook", "Fabrique apres l'archive",
                            sujet="s", dossier="/tmp")
        return nom, temoin

    def _existe(self, produit_id):
        return store.lire_produit(produit_id) is not None

    def test_inspecter_dit_ce_que_contient_l_archive(self):
        _, cree = self.json("/api/sauvegarde", {"action": "creer"})
        _, fiche = self.json("/api/sauvegarde",
                             {"action": "inspecter",
                              "nom": cree["archive"]["nom"]})
        self.assertTrue(fiche["valide"])
        self.assertEqual(fiche["schema"], store.VERSION_SCHEMA)
        self.assertEqual(fiche["schema_courant"], store.VERSION_SCHEMA)
        self.assertIn("cree_le", fiche)

    def test_inspecter_ne_sort_pas_du_dossier_des_sauvegardes(self):
        for nom in ("../usine.db", "..%2Fusine.db", "usine.db",
                    "sauvegardes/x.zip", "../reglages.json", "", "x.zip"):
            _, fiche = self.json("/api/sauvegarde",
                                 {"action": "inspecter", "nom": nom})
            self.assertIn("erreur", fiche, nom)

    def test_sans_confirmation_rien_n_est_remplace(self):
        """La confirmation voyage avec la requete, pas avec la page.

        Une page rechargee, un rejeu de requete ou un script tiers n'herite
        pas d'une case cochee dans un navigateur que le serveur ne voit pas.
        """
        nom, temoin = self._archive_et_produit_neuf()
        _, refus = self.json("/api/sauvegarde",
                             {"action": "restaurer", "nom": nom})
        self.assertIn("non confirmee", refus["erreur"])
        self.assertTrue(self._existe(temoin), "l'atelier a ete touche")

    def test_une_confirmation_approximative_ne_suffit_pas(self):
        """« oui », 1, « true » sont vrais en JavaScript. Pas ici."""
        nom, temoin = self._archive_et_produit_neuf()
        for valeur in ("oui", "true", 1, [1], {"ok": 1}):
            with self.subTest(confirme=valeur):
                _, refus = self.json("/api/sauvegarde",
                                     {"action": "restaurer", "nom": nom,
                                      "confirme": valeur})
                self.assertIn("erreur", refus)
                self.assertTrue(self._existe(temoin))

    def test_une_archive_inconnue_est_refusee(self):
        _, refus = self.json("/api/sauvegarde",
                             {"action": "restaurer", "nom": "../usine.db",
                              "confirme": True})
        self.assertIn("introuvable", refus["erreur"])

    def test_la_restauration_confirmee_remet_l_atelier_d_avant(self):
        nom, temoin = self._archive_et_produit_neuf()
        self.assertTrue(self._existe(temoin))
        _, fait = self.json("/api/sauvegarde",
                            {"action": "restaurer", "nom": nom,
                             "confirme": True})
        self.assertTrue(fait["restaure"])
        self.assertFalse(self._existe(temoin))
        self.assertTrue(fait["ancienne_base"],
                        "l'ancienne base doit etre mise de cote, pas supprimee")
        self.assertNotIn("/", fait["ancienne_base"],
                         "un chemin d'atelier n'a rien a faire dans la page")

    def test_on_ne_restaure_pas_sous_une_fabrication_en_cours(self):
        """Remplacer la base sous un produit en cours le ferait ecrire dans
        un atelier qui n'existe plus."""
        nom, temoin = self._archive_et_produit_neuf()
        occupe = {"x": {"id": "x", "statut": "en_cours", "debut": 0,
                        "journal": [], "resultat": None, "erreur": ""}}
        with mock.patch.object(serveur, "TRAVAUX", occupe):
            _, refus = self.json("/api/sauvegarde",
                                 {"action": "restaurer", "nom": nom,
                                  "confirme": True})
        self.assertIn("fabrication est en cours", refus["erreur"])
        self.assertTrue(self._existe(temoin))

    def test_on_ne_restaure_pas_sous_une_veille_en_cours(self):
        nom, temoin = self._archive_et_produit_neuf()
        with mock.patch.object(serveur, "VEILLES",
                               {"v": {"id": "v", "statut": "en_cours"}}):
            _, refus = self.json("/api/sauvegarde",
                                 {"action": "restaurer", "nom": nom,
                                  "confirme": True})
        self.assertIn("veille est en cours", refus["erreur"])
        self.assertTrue(self._existe(temoin))

    def test_on_ne_restaure_pas_sous_l_usine_continue(self):
        from usine import production

        nom, temoin = self._archive_et_produit_neuf()
        with mock.patch.object(production, "verrou_actif", lambda: 4242):
            _, refus = self.json("/api/sauvegarde",
                                 {"action": "restaurer", "nom": nom,
                                  "confirme": True})
        self.assertIn("4242", refus["erreur"])
        self.assertTrue(self._existe(temoin))

    def test_la_page_demande_deux_gestes(self):
        """Garde-fou : la case et le bouton sont ce qui separe « je consulte
        mes sauvegardes » de « j'efface aujourd'hui »."""
        _, corps = self.appeler("/")
        page = corps.decode("utf-8")
        for marqueur in ("restauration", "restauration-compris",
                         "restauration-faire", "restauration-annuler"):
            self.assertIn('id="{}"'.format(marqueur), page, marqueur)
        self.assertIn("disabled", page.split('id="restauration-faire"')[1][:40],
                      "le bouton doit naitre inactif")


class TestTeleversement(BaseServeur):
    """Faire revenir une archive qui n'est pas sur l'appareil.

    C'est le cas de la reinstallation : le telephone a ete efface, et la
    sauvegarde est sur un ordinateur ou dans un nuage. Ni la page ni la
    ligne de commande ne savaient la faire revenir — toutes deux veulent un
    fichier deja la.
    """

    def _dossier(self):
        return config.WORKDIR / "sauvegardes"

    def _archives(self):
        dossier = self._dossier()
        return sorted(f.name for f in dossier.iterdir()) if dossier.is_dir() else []

    def _envoyer(self, octets, nom="sauvegarde.zip"):
        requete = urllib.request.Request(
            self.base + "/api/televerser?nom=" + urllib.parse.quote(nom),
            data=octets, headers={"Content-Type": "application/zip"})
        try:
            with urllib.request.urlopen(requete, timeout=30) as reponse:
                return reponse.status, json.loads(reponse.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _vraie_archive(self):
        """Une archive valide, retiree du dossier : elle « vient d'ailleurs »."""
        from usine.core import sauvegarde

        archive = sauvegarde.creer()
        octets = archive.read_bytes()
        archive.unlink()
        return octets

    def test_une_archive_venue_d_ailleurs_rejoint_les_autres(self):
        octets = self._vraie_archive()
        statut, recu = self._envoyer(octets, "ma sauvegarde du 3 mars.zip")
        self.assertEqual(statut, 200, recu)
        self.assertEqual(recu["archive"]["nom"], "ma-sauvegarde-du-3-mars.zip")
        self.assertEqual(recu["fiche"]["schema"], store.VERSION_SCHEMA)
        self.assertIn("ma-sauvegarde-du-3-mars.zip",
                      [a["nom"] for a in recu["sauvegardes"]])

    def test_un_nom_qui_contient_un_chemin_est_reduit(self):
        """Le nom vient de la machine d'en face : c'est un nom, pas un chemin."""
        octets = self._vraie_archive()
        for propose, attendu in (
                ("../../etc/passwd", "passwd.zip"),
                ("/tmp/evade.zip", "evade.zip"),
                ("C:\\Users\\moi\\sauve.zip", "sauve.zip")):
            with self.subTest(nom=propose):
                _, recu = self._envoyer(octets, propose)
                self.assertEqual(recu["archive"]["nom"], attendu)
        self.assertFalse(
            (config.WORKDIR / "passwd.zip").exists(),
            "une archive est sortie du dossier des sauvegardes")

    def test_deux_envois_du_meme_nom_n_ecrasent_rien(self):
        """Remplacer l'archive qui protege par celle qu'on teste serait la
        pire facon de recevoir une sauvegarde."""
        octets = self._vraie_archive()
        _, premier = self._envoyer(octets, "collision.zip")
        _, second = self._envoyer(octets, "collision.zip")
        self.assertEqual(premier["archive"]["nom"], "collision.zip")
        self.assertEqual(second["archive"]["nom"], "collision-2.zip")
        self.assertIn("collision.zip", self._archives())

    def test_ce_qui_n_est_pas_une_archive_est_refuse_et_ne_reste_pas(self):
        avant = self._archives()
        statut, refus = self._envoyer(b"je ne suis pas un zip" * 60, "faux.zip")
        self.assertEqual(statut, 400)
        self.assertIn("illisible", refus["erreur"])
        self.assertEqual(self._archives(), avant,
                         "un fichier refuse est reste dans le dossier")

    def test_une_archive_sans_base_est_refusee(self):
        creux = io.BytesIO()
        with zipfile.ZipFile(creux, "w") as zip_:
            zip_.writestr("lisez-moi.txt", "rien dedans")
        avant = self._archives()
        statut, refus = self._envoyer(creux.getvalue(), "creux.zip")
        self.assertEqual(statut, 400)
        self.assertIn("sans base", refus["erreur"])
        self.assertEqual(self._archives(), avant)

    def test_une_archive_qui_annonce_une_base_enorme_est_refusee(self):
        """Restaurer lit « usine.db » d'un seul bloc en memoire.

        Six cents kilo-octets compresses annoncant six cents mega-octets
        suffiraient a faire tomber le telephone.
        """
        from usine.core import sauvegarde

        bombe = io.BytesIO()
        with zipfile.ZipFile(bombe, "w", zipfile.ZIP_DEFLATED) as zip_:
            zip_.writestr("usine.db", b"\0" * (sauvegarde.BASE_MAX + 1024))
        octets = bombe.getvalue()
        self.assertLess(len(octets), 2 * 1024 * 1024,
                        "le temoin doit rester petit une fois compresse")

        avant = self._archives()
        statut, refus = self._envoyer(octets, "bombe.zip")
        self.assertEqual(statut, 400)
        self.assertIn("refuse de la charger en memoire", refus["erreur"])
        self.assertEqual(self._archives(), avant)

    def test_un_corps_vide_est_refuse(self):
        statut, refus = self._envoyer(b"", "vide.zip")
        self.assertEqual(statut, 400)
        self.assertIn("vide", refus["erreur"])

    @staticmethod
    def _lire_reponse(prise) -> str:
        """Lit la reponse ENTIERE, corps compris.

        Un seul recv() rend ce que la pile TCP a sous la main : souvent les
        en-tetes seuls, le corps arrivant dans le segment suivant. Le test
        qui affirmait sur le corps passait donc la plupart du temps et
        echouait au hasard — le pire des tests, parce qu'on finit par le
        croire casse alors qu'il dit vrai.
        """
        prise.settimeout(5)
        donnees = b""
        while True:
            try:
                morceau = prise.recv(4096)
            except socket.timeout:
                break
            if not morceau:
                break
            donnees += morceau
            entetes, separateur, corps = donnees.partition(b"\r\n\r\n")
            if not separateur:
                continue
            annonce = re.search(rb"[Cc]ontent-[Ll]ength:\s*(\d+)", entetes)
            if annonce is None or len(corps) >= int(annonce.group(1)):
                break
        return donnees.decode("utf-8", "replace")

    def test_une_taille_annoncee_hors_limite_est_refusee_sans_rien_lire(self):
        """Le plafond est verifie AVANT de lire le corps.

        Sinon un envoi annonce a dix giga-octets remplirait le disque du
        telephone avant d'etre refuse.
        """
        annonce = serveur.TELEVERSEMENT_MAX + 1
        prise = socket.create_connection(self.serveur.server_address, timeout=10)
        try:
            prise.sendall((
                "POST /api/televerser?nom=enorme.zip HTTP/1.1\r\n"
                "Host: 127.0.0.1\r\n"
                "Content-Type: application/zip\r\n"
                "Content-Length: {}\r\n\r\n".format(annonce)).encode())
            # Pas un seul octet de corps : la reponse doit venir quand meme.
            reponse = self._lire_reponse(prise)
        finally:
            prise.close()
        self.assertIn("413", reponse.splitlines()[0])
        self.assertIn("limite", reponse)

    def test_un_transfert_interrompu_ne_laisse_pas_de_fichier(self):
        octets = self._vraie_archive()
        avant = self._archives()
        prise = socket.create_connection(self.serveur.server_address, timeout=10)
        try:
            prise.sendall((
                "POST /api/televerser?nom=coupee.zip HTTP/1.1\r\n"
                "Host: 127.0.0.1\r\n"
                "Content-Type: application/zip\r\n"
                "Content-Length: {}\r\n\r\n".format(len(octets)).encode()))
            prise.sendall(octets[:len(octets) // 3])
            prise.shutdown(socket.SHUT_WR)
            reponse = self._lire_reponse(prise)
        finally:
            prise.close()
        self.assertIn("400", reponse.splitlines()[0])
        self.assertEqual(self._archives(), avant)

    def test_une_archive_televersee_est_restaurable(self):
        """Le parcours complet : atelier efface, archive renvoyee, catalogue
        de retour."""
        store.creer_produit("tv-ancien", "ebook", "Le catalogue d'avant",
                            sujet="s", dossier="/tmp")
        octets = self._vraie_archive()
        store.creer_produit("tv-apres", "ebook", "Fabrique apres l'archive",
                            sujet="s", dossier="/tmp")

        _, recu = self._envoyer(octets, "retour.zip")
        _, fait = self.json("/api/sauvegarde",
                            {"action": "restaurer",
                             "nom": recu["archive"]["nom"], "confirme": True})
        self.assertTrue(fait["restaure"])
        self.assertIsNotNone(store.lire_produit("tv-ancien"))
        self.assertIsNone(store.lire_produit("tv-apres"))


class TestAb(BaseServeur):
    """L'A/B dans le navigateur : la seule interface qui puisse MONTRER
    les couvertures.

    Comparer quatre directions visuelles en lisant des chemins de fichiers
    dans une console n'a aucun sens. C'est le trou le plus voyant qu'avait
    le tableau de bord.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        llm.definir_simulateur(simulateur)
        cls.dossier = config.PRODUITS_DIR / "tab-ab"
        cls.dossier.mkdir(parents=True, exist_ok=True)
        store.creer_produit("tab-ab", "ebook", "Le systeme du freelance",
                            sujet="freelance", dossier=str(cls.dossier))

    def _creer(self, sur="titre", **extra):
        charge = dict(action="creer", sur=sur, nombre=3, **extra)
        charge.setdefault("produit", "tab-ab")
        statut, lance = self.json("/api/ab", charge)
        self.assertEqual(statut, 200, lance)
        for _ in range(400):
            _, travail = self.json("/api/travaux/" + lance["travail"])
            if travail["statut"] != "en_cours":
                break
            threading.Event().wait(0.1)
        self.assertEqual(travail["statut"], "termine", travail.get("erreur"))
        return travail["resultat"]["experience_id"]

    def test_creer_sans_produit_ni_titre_est_refuse(self):
        statut, refus = self.json("/api/ab", {"action": "creer"})
        self.assertEqual(statut, 400)
        self.assertIn("produit", refus["erreur"])

    def test_un_sujet_de_test_invente_est_refuse(self):
        statut, _ = self.json("/api/ab", {"action": "creer", "titre": "x",
                                          "sur": "la couleur du bouton"})
        self.assertEqual(statut, 400)

    def test_un_produit_inconnu_est_refuse(self):
        statut, _ = self.json("/api/ab", {"action": "creer",
                                          "produit": "nexistepas"})
        self.assertEqual(statut, 400)

    def test_un_test_inconnu_repond_404(self):
        self.assertEqual(self.json("/api/ab/999999")[0], 404)
        self.assertEqual(self.json("/api/ab/pas-un-nombre")[0], 400)

    def test_les_couvertures_arrivent_avec_une_image_servie(self):
        """Le chemin stocke est un NOM de fichier, pas un chemin.

        Il ne vaut que rapporte au dossier du test — regle qui vivait en
        deux exemplaires divergents, dans la ligne de commande et ici.
        """
        identifiant = self._creer(sur="couverture")
        _, detail = self.json("/api/ab/{}".format(identifiant))
        self.assertTrue(detail["variantes"])
        for variante in detail["variantes"]:
            self.assertTrue(variante["image"], variante["contenu"])
            statut, corps = self.appeler(variante["image"])
            self.assertEqual(statut, 200)
            self.assertEqual(corps[:4], b"\x89PNG", "ce n'est pas une image")

    def test_un_test_de_titres_n_a_pas_d_image(self):
        identifiant = self._creer(sur="titre")
        _, detail = self.json("/api/ab/{}".format(identifiant))
        self.assertTrue(all(not v["image"] for v in detail["variantes"]))
        self.assertTrue(all(v["contenu"] for v in detail["variantes"]))

    def test_reporter_des_chiffres_change_le_verdict(self):
        identifiant = self._creer()
        _, avant = self.json("/api/ab/{}".format(identifiant))
        self.assertEqual(avant["verdict"]["etat"], "sans_donnees")
        for variante, (vues, actions) in zip(avant["variantes"],
                                             ((900, 120), (900, 20), (900, 18))):
            statut, _ = self.json("/api/ab", {"action": "observer",
                                              "variante": variante["id"],
                                              "vues": vues, "actions": actions})
            self.assertEqual(statut, 200)
        _, apres = self.json("/api/ab/{}".format(identifiant))
        self.assertEqual(apres["verdict"]["etat"], "gagnant")
        self.assertEqual(apres["variantes"][0]["vues"], 900)

    def test_une_saisie_impossible_est_refusee_a_l_ecran(self):
        """Plus d'actions que de vues est une erreur de saisie, pas une panne."""
        identifiant = self._creer()
        _, detail = self.json("/api/ab/{}".format(identifiant))
        statut, refus = self.json("/api/ab", {
            "action": "observer", "variante": detail["variantes"][0]["id"],
            "vues": 1, "actions": 50})
        self.assertEqual(statut, 400)
        self.assertIn("actions", refus["erreur"])

    def test_dater_une_variante_la_rend_mesurable(self):
        identifiant = self._creer()
        _, detail = self.json("/api/ab/{}".format(identifiant))
        self.assertEqual(detail["sans_periode"], len(detail["variantes"]))
        statut, _ = self.json("/api/ab", {
            "action": "periode", "variante": detail["variantes"][0]["id"],
            "du": "2026-01-01", "au": "2026-01-31"})
        self.assertEqual(statut, 200)
        _, apres = self.json("/api/ab/{}".format(identifiant))
        self.assertEqual(apres["variantes"][0]["debut"], "2026-01-01")
        self.assertEqual(apres["sans_periode"], len(apres["variantes"]) - 1)

    def test_une_date_illisible_est_refusee(self):
        identifiant = self._creer()
        _, detail = self.json("/api/ab/{}".format(identifiant))
        statut, refus = self.json("/api/ab", {
            "action": "periode", "variante": detail["variantes"][0]["id"],
            "du": "le 3 janvier"})
        self.assertEqual(statut, 400)
        self.assertIn("AAAA-MM-JJ", refus["erreur"])

    def test_clore_retient_la_gagnante(self):
        identifiant = self._creer()
        _, detail = self.json("/api/ab/{}".format(identifiant))
        retenue = detail["variantes"][0]["id"]
        statut, _ = self.json("/api/ab", {"action": "clore", "id": identifiant,
                                          "gagnante": retenue, "note": "retenue"})
        self.assertEqual(statut, 200)
        _, apres = self.json("/api/ab/{}".format(identifiant))
        self.assertEqual(apres["statut"], "close")
        self.assertEqual(apres["gagnante"], retenue)

    def test_supprimer_efface_le_test(self):
        identifiant = self._creer()
        self.json("/api/ab", {"action": "supprimer", "id": identifiant})
        self.assertEqual(self.json("/api/ab/{}".format(identifiant))[0], 404)

    def test_une_action_inconnue_est_refusee(self):
        statut, _ = self.json("/api/ab", {"action": "tout effacer"})
        self.assertEqual(statut, 400)


class TestBilanEtMarche(BaseServeur):
    """Deux mesures qui n'existaient qu'en console."""

    def test_le_bilan_tient_sans_aucune_production(self):
        """C'est l'etat que voit un nouvel utilisateur."""
        _, bilan = self.json("/api/bilan")
        self.assertIn("productions", bilan)

    def test_le_bilan_rend_ce_que_l_usine_a_appris(self):
        from usine.core import apprentissage

        # Deux productions par ton : en dessous, « _grouper » ne rend rien,
        # et c'est voulu — une seule note ne mesure pas un ton.
        notes = (("pro", 9.0), ("pro", 8.0), ("amical", 5.0), ("amical", 4.0))
        for rang, (ton, note) in enumerate(notes):
            apprentissage.enregistrer("tab-b{}".format(rang), "ebook",
                                      sujet="s", ton=ton, qualite="standard",
                                      note=note, mots=3000, appels=10, duree=42)
        _, bilan = self.json("/api/bilan")
        self.assertGreaterEqual(bilan["productions"], 4)
        tons = {g["valeur"]: g["note_moyenne"] for g in bilan["par_ton"]}
        self.assertGreater(tons["pro"], tons["amical"])

    def test_la_page_lit_le_bon_champ_de_note(self):
        """Le bilan porte « note_moyenne ». Le script lisait « note ».

        Rien n'aurait echoue : chaque barre se serait affichee vide, a zero,
        et le classement par ton aurait eu l'air de dire que rien ne compte.
        """
        _, corps = self.appeler("/statique/app.js")
        script = corps.decode("utf-8")
        self.assertIn("g.note_moyenne", script)
        self.assertNotIn("g.note ", script)

    def test_un_sondage_de_marche_sans_sujet_est_refuse(self):
        self.assertEqual(self.json("/api/marche", {"sujet": " "})[0], 400)

    def test_le_sondage_rapporte_ce_qu_il_a_mesure(self):
        from usine.core import marche as module_marche

        fige = {"sujet": "x", "date": "2026-09-12", "sources": {},
                "sources_disponibles": ["hacker_news"],
                "sources_indisponibles": ["wikipedia"],
                "lecture": {"demande": "moyenne", "concurrence": "faible",
                            "tendance": "stable", "signaux": ["820 discussions"]}}
        with mock.patch.object(module_marche, "sonder", lambda *a, **k: fige):
            _, lance = self.json("/api/marche", {"sujet": "la prospection"})
            for _ in range(200):
                _, etat = self.json("/api/marche/" + lance["marche"])
                if etat["statut"] != "en_cours":
                    break
                threading.Event().wait(0.05)
        self.assertEqual(etat["statut"], "termine")
        self.assertEqual(etat["resultat"]["lecture"]["demande"], "moyenne")
        # Une source muette n'est pas un marche absent : la page doit pouvoir
        # le dire, donc l'etat doit le porter.
        self.assertEqual(etat["resultat"]["sources_indisponibles"], ["wikipedia"])

    def test_un_sondage_inconnu_repond_404(self):
        self.assertEqual(self.json("/api/marche/nexistepas")[0], 404)


class TestActionsProduit(BaseServeur):
    """La carte Produits savait lister, pas agir.

    « usine marketing » et « usine livrer » sont les deux commandes qu'on
    lance APRES avoir regarde un produit — donc exactement la ou la page
    s'arretait.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        llm.definir_simulateur(simulateur)

    def _un_produit(self):
        dossier = config.PRODUITS_DIR / "tab-act"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "livre.md").write_text(
            "# Un livre\n\nDu texte suffisant pour empaqueter quelque chose.\n",
            encoding="utf-8")
        store.creer_produit("tab-act", "ebook", "Un livre a empaqueter",
                            sujet="un sujet", dossier=str(dossier))
        return "tab-act"

    def test_un_produit_inconnu_est_refuse(self):
        statut, refus = self.json("/api/produit",
                                  {"action": "livrer", "id": "nexistepas"})
        self.assertEqual(statut, 404)
        self.assertIn("inconnu", refus["erreur"])

    def test_une_action_inconnue_est_refusee(self):
        identifiant = self._un_produit()
        statut, _ = self.json("/api/produit",
                              {"action": "detruire", "id": identifiant})
        self.assertEqual(statut, 400)

    def test_livrer_ecrit_une_archive_telechargeable(self):
        """L'archive est ecrite A COTE du dossier du produit, pas dedans.

        La liste de fichiers ne la voit donc jamais : c'est la reponse qui
        doit porter son lien, sinon elle est introuvable depuis la page.
        """
        identifiant = self._un_produit()
        statut, fait = self.json("/api/produit",
                                 {"action": "livrer", "id": identifiant})
        self.assertEqual(statut, 200, fait)
        self.assertTrue(fait["archive"].startswith("/fichier/"))
        self.assertGreater(fait["ko"], 0)

        code, corps = self.appeler(fait["archive"])
        self.assertEqual(code, 200)
        self.assertEqual(corps[:2], b"PK")

        _, produits = self.json("/api/produits")
        fichiers = [f["nom"] for p in produits["produits"]
                    if p["id"] == identifiant for f in p["fichiers"]]
        self.assertFalse([f for f in fichiers if f.endswith(".zip")],
                         "l'archive n'est pas dans le dossier du produit")

    def test_le_kit_de_vente_part_en_tache_de_fond(self):
        identifiant = self._un_produit()
        statut, lance = self.json("/api/produit",
                                  {"action": "marketing", "id": identifiant})
        self.assertEqual(statut, 200, lance)
        for _ in range(600):
            _, travail = self.json("/api/travaux/" + lance["travail"])
            if travail["statut"] != "en_cours":
                break
            threading.Event().wait(0.1)
        self.assertEqual(travail["statut"], "termine", travail.get("erreur"))
        liens = travail["resultat"]["fichiers"]
        self.assertTrue(liens)
        self.assertTrue(any("page-de-vente" in lien for lien in liens), liens)
        for lien in liens:
            self.assertEqual(self.appeler(lien)[0], 200, lien)


class TestDocteur(BaseServeur):
    """Le bouton « pourquoi ca ne marche pas », dans le navigateur."""

    def test_le_diagnostic_rend_des_faits_et_un_verdict(self):
        from usine.core import diagnostic

        # Les deux controles reseau sont neutralises : la suite ne doit
        # dependre d'aucune connexion.
        with mock.patch.object(diagnostic, "_reseau", lambda: True), \
                mock.patch.object(diagnostic, "locaux_actifs", lambda **k: []):
            _, etat = self.json("/api/docteur")
        for cle in ("python", "workdir", "env_present", "node", "espace",
                    "fournisseurs", "verdict", "reseau", "locaux"):
            self.assertIn(cle, etat)
        self.assertIn(etat["verdict"]["etat"], ("pret", "local", "bloque"))
        self.assertTrue(etat["verdict"]["message"])

    def test_le_verdict_dit_quoi_faire_quand_rien_n_est_pret(self):
        from usine.core import diagnostic

        verdict = diagnostic._verdict(
            {"distants_prets": 0, "locaux": []})
        self.assertEqual(verdict["etat"], "bloque")
        self.assertIn("usine cles", verdict["message"])
        verdict = diagnostic._verdict({"distants_prets": 0, "locaux": ["ollama"]})
        self.assertEqual(verdict["etat"], "local")

    def test_les_memes_controles_servent_les_deux_interfaces(self):
        """Recopier les controles cote web en aurait fait deux jeux qui
        divergent : « docteur » lit desormais le meme module."""
        source = (RACINE / "usine" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("module_diagnostic.etat_installation(", source)
        # Ce que le garde-fou surveille vraiment : que « docteur » n'aille pas
        # refaire lui-meme un controle que le module porte deja.
        for refait in ("shutil.disk_usage", "def _reseau", "locaux_actifs()"):
            self.assertNotIn(refait, source)

    def _faux_catalogue(self, servis, statut=200):
        """Remplace la reponse de /models par un catalogue choisi."""
        from unittest import mock

        charge = json.dumps({"data": [{"id": m} for m in servis]}).encode()
        return mock.patch("usine.core.http.requete",
                          return_value=(statut, charge))

    def _fournisseur(self, modeles):
        from usine.core import config

        return config.Provider(
            name="essai", base_url="https://exemple.invalide/v1",
            api_key_env="", models=modeles, keyless=True)

    def test_un_modele_retire_du_catalogue_est_signale(self):
        """La panne reelle : Groq a retire ses modeles Llama du palier
        gratuit, chaque appel a repondu 404, et rien ne l'a jamais dit."""
        from unittest import mock
        from usine.core import config, diagnostic

        faux = self._fournisseur({"rapide": "vivant", "standard": "mort"})
        with mock.patch.object(config, "active_providers", return_value=[faux]):
            with self._faux_catalogue(["vivant", "autre"]):
                rapport = diagnostic.modeles_disparus()
        self.assertEqual(len(rapport["ecarts"]), 1)
        self.assertEqual(rapport["ecarts"][0]["manquants"], ["mort"])
        self.assertIn("autre", rapport["ecarts"][0]["proposes"])
        self.assertEqual(rapport["consultes"], ["essai"])

    def test_un_catalogue_complet_ne_signale_rien(self):
        from unittest import mock
        from usine.core import config, diagnostic

        faux = self._fournisseur({"rapide": "a", "standard": "b"})
        with mock.patch.object(config, "active_providers", return_value=[faux]):
            with self._faux_catalogue(["a", "b", "c"]):
                rapport = diagnostic.modeles_disparus()
        self.assertEqual(rapport["ecarts"], [])
        self.assertEqual(rapport["consultes"], ["essai"])

    def test_un_service_injoignable_n_accuse_personne(self):
        """« Je ne sais pas » ne doit pas se lire « aucun modele » : un reseau
        coupe declarerait toute la configuration morte."""
        from unittest import mock
        from usine.core import config, diagnostic

        faux = self._fournisseur({"standard": "mort"})
        with mock.patch.object(config, "active_providers", return_value=[faux]):
            with mock.patch("usine.core.http.requete", side_effect=OSError("hs")):
                rapport = diagnostic.modeles_disparus()
            self.assertEqual(rapport["ecarts"], [])
            # Et surtout : le rapport dit que personne n'a repondu. Une liste
            # d'ecarts vide ne doit pas pouvoir se lire « tout va bien ».
            self.assertEqual(rapport["consultes"], [])
            self.assertEqual(rapport["injoignables"], ["essai"])
            with self._faux_catalogue([], statut=403):
                rapport = diagnostic.modeles_disparus()
            self.assertEqual(rapport["injoignables"], ["essai"])

    def test_l_etat_annonce_les_series_connues(self):
        """Le tableau de bord doit proposer les suites en cours plutot que de
        faire retaper leur nom : une faute de frappe cree une seconde serie
        vide, et le tome repartirait de zero sans rien dire."""
        from usine.core import serie as module_serie

        module_serie.enregistrer_tome(
            "Les rails", {"cadre": {}, "personnages": []}, "T1", "...")
        _, corps = self.appeler("/api/etat")
        etat = json.loads(corps)
        self.assertIn("series", etat)
        self.assertIn("Les rails", etat["series"])

    def test_les_reglages_peuvent_etre_enregistres_depuis_la_page(self):
        """La route existait et personne ne l'appelait : le tableau de bord
        affichait les reglages sans pouvoir les changer, et il fallait
        ressortir vers la ligne de commande pour retaper un nom d'auteur."""
        _, corps = self.appeler(
            "/api/reglages",
            corps={"auteur": "Une autrice", "qualite": "exigeant"})
        retour = json.loads(corps)
        self.assertEqual(retour["reglages"]["auteur"], "Une autrice")
        self.assertEqual(retour["reglages"]["qualite"], "exigeant")

        page = self.appeler("/")[1].decode("utf-8")
        self.assertIn('id="retenir"', page)
        script = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        self.assertIn("'/api/reglages'", script)

    def test_le_formulaire_porte_le_champ_serie(self):
        """Une option qui n'est pas dans la page n'existe pas pour qui
        produit depuis un navigateur."""
        _, corps = self.appeler("/")
        page = corps.decode("utf-8")
        self.assertIn('id="serie"', page)
        self.assertIn("series-connues", page)
        script = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
            encoding="utf-8")
        self.assertIn("serie: $('serie')", script)
        self.assertIn("bloc-serie", script)

    def test_le_controle_des_modeles_ne_sort_que_si_on_le_demande(self):
        """Une requete par fournisseur : trop lent pour un rafraichissement.

        Mais le defaut inverse est pire — un modele retire du catalogue tue
        un fournisseur en silence — donc le controle existe, sous un drapeau.
        """
        from usine.core import diagnostic

        etat = diagnostic.etat_installation(avec_reseau=False, avec_locaux=False)
        self.assertIsNone(etat["modeles"])
        source = (RACINE / "usine" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("--modeles", source)


class TestPageServie(BaseServeur):
    """Garde-fou sur ce que la page declare.

    Le rendu est verifie dans un vrai navigateur, ce que la suite ne peut
    pas faire. Ces controles ne disent donc pas que l'interface marche — ils
    disent que les trois cartes n'ont pas disparu d'une refonte.
    """

    def test_les_trois_cartes_sont_dans_la_page(self):
        _, corps = self.appeler("/")
        page = corps.decode("utf-8")
        for marqueur in ("veille-lancer", "doublons-reconstruire",
                         "sauvegarde-creer", "veille-douleurs", "sauvegardes",
                         "archive-fichier", "ab-creer", "ab-liste", "bilan",
                         "marche-lancer", "docteur-lancer", "docteur",
                         "fond-cyber"):
            self.assertIn('id="{}"'.format(marqueur), page, marqueur)

    def test_chaque_champ_de_saisie_porte_une_etiquette(self):
        """Un champ sans etiquette n'a pas de nom pour un lecteur d'ecran.

        Verifie sur la source : les deux listes de la carte A/B sont
        arrivees sans etiquette, et rien ne l'a signale — un audit dans un
        vrai navigateur les a trouvees.
        """
        _, corps = self.appeler("/")
        page = corps.decode("utf-8")
        etiquettes = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', page))
        # Une case a cocher est souvent ENTOURÉE de son etiquette plutot que
        # nommee par « for » : les deux sont valides.
        entourees = [(m.start(), m.end())
                     for m in re.finditer(r"<label\b.*?</label>", page, re.S)]
        sans = []
        for balise in re.finditer(r'<(?:input|select|textarea)\b[^>]*>', page):
            texte = balise.group(0)
            if 'type="hidden"' in texte or " hidden" in texte:
                continue
            if "placeholder=" in texte or "aria-label=" in texte:
                continue
            if any(debut <= balise.start() < fin for debut, fin in entourees):
                continue
            trouve = re.search(r'\bid="([^"]+)"', texte)
            if not trouve or trouve.group(1) not in etiquettes:
                sans.append(texte[:60])
        self.assertEqual(sans, [], "champs sans etiquette")

    def test_la_page_a_une_region_principale_et_des_zones_vivantes(self):
        """Ce qui change pendant qu'on regarde doit pouvoir etre annonce."""
        _, corps = self.appeler("/")
        page = corps.decode("utf-8")
        self.assertIn("<main>", page)
        self.assertGreaterEqual(page.count('role="status"'), 5)
        self.assertIn('role="log"', page)
        # La scene 3D repete ce que le journal dit deja en toutes lettres.
        self.assertIn('aria-hidden="true"', page)

    def test_le_script_echappe_ce_qui_vient_du_flux(self):
        _, corps = self.appeler("/statique/app.js")
        script = corps.decode("utf-8")
        self.assertIn("function ligneDite", script)
        self.assertIn("echapper(d.titre)", script)


if __name__ == "__main__":
    unittest.main()
