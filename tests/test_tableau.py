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

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, store, veille  # noqa: E402
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
                         "sauvegarde-creer", "veille-douleurs", "sauvegardes"):
            self.assertIn('id="{}"'.format(marqueur), page, marqueur)

    def test_le_script_echappe_ce_qui_vient_du_flux(self):
        _, corps = self.appeler("/statique/app.js")
        script = corps.decode("utf-8")
        self.assertIn("function ligneDite", script)
        self.assertIn("echapper(d.titre)", script)


if __name__ == "__main__":
    unittest.main()
