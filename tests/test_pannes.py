"""Ce que l'usine dit quand la machine lache.

Trois pannes qu'un telephone produit vraiment, et qu'aucun test ne provoquait :
le disque se remplit au milieu d'une fabrication, la base est ecrasee par une
carte SD fatiguee, le reseau tombe. Elles ont ceci de commun que le message
brut de Python n'aide personne : « [Errno 28] No space left on device » ne dit
ni ou, ni quoi faire, ni — le plus important — que le travail deja paye n'est
pas perdu.

Ces tests portent donc sur le MESSAGE autant que sur le code de sortie. Un
message est ici une piece de l'usine : c'est lui qui decide si l'utilisateur
repare ou abandonne.

Ils portent aussi sur le silence : un message de disque plein devant un port
deja pris serait pire que le message brut, parce qu'il enverrait chercher au
mauvais endroit.
"""

from __future__ import annotations

import errno
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import cli  # noqa: E402
from usine.core import config, store  # noqa: E402


def setUpModule():
    atelier.isoler("pannes")


class DisquePlein(unittest.TestCase):
    """Traduire un echec d'ecriture en geste a faire."""

    def test_le_disque_plein_dit_combien_il_reste(self):
        message = cli._expliquer_ecriture(
            OSError(errno.ENOSPC, "No space left on device"))
        self.assertIn("Plus de place", message)
        # Le chiffre vient de shutil, pas d'une estimation : sans lui,
        # « faites de la place » ne dit pas combien.
        self.assertRegex(message, r"Il reste \d+ Mo")

    def test_chaque_message_d_ecriture_dit_que_relancer_est_gratuit(self):
        """La phrase qui evite d'abandonner une fabrication a moitie faite.

        Les appels deja payes sont en cache. Sans cette phrase, l'utilisateur
        croit avoir brule son quota du jour et ne relance pas.
        """
        for code in (errno.ENOSPC, errno.EACCES, errno.EPERM, errno.EROFS):
            with self.subTest(code=code):
                message = cli._expliquer_ecriture(OSError(code, "peu importe"))
                self.assertIn("cache", message)
                self.assertIn("MEME commande", message)
                # Ne PAS promettre la gratuite : mesure faite, une relance
                # apres coupure precoce coute encore 21 appels sur 27.
                self.assertNotIn("aucun quota", message)

    def test_la_permission_refusee_renvoie_a_termux_setup_storage(self):
        message = cli._expliquer_ecriture(OSError(errno.EACCES, "refuse"))
        self.assertIn("termux-setup-storage", message)
        self.assertIn(str(config.WORKDIR), message)

    def test_la_lecture_seule_propose_un_autre_dossier(self):
        message = cli._expliquer_ecriture(OSError(errno.EROFS, "read-only"))
        self.assertIn("USINE_HOME", message)

    def test_un_port_occupe_n_est_pas_un_disque_plein(self):
        """Le garde-fou se tait quand il ne sait pas.

        « usine web » lance deux fois leve OSError, comme le disque plein.
        Repondre « plus de place » enverrait chercher a l'oppose du defaut.
        On rend "" et l'appelant retombe sur le message brut, qui, lui, est
        juste.
        """
        self.assertEqual(
            cli._expliquer_ecriture(OSError(errno.EADDRINUSE, "Address already in use")),
            "")
        self.assertEqual(cli._expliquer_ecriture(OSError(errno.ENOENT, "absent")), "")


class BaseIllisible(unittest.TestCase):
    """Une base cassee ne doit pas rendre l'usine muette."""

    @staticmethod
    def _casser(forme: str = "entete") -> None:
        store.connect()
        store.close()
        brut = config.DB_PATH.read_bytes()
        if forme == "entete":
            # Ce que rend une carte SD qui a laché : des octets nuls.
            config.DB_PATH.write_bytes(b"\x00" * 200 + brut[200:])
        else:
            # Processus tue en pleine ecriture : le fichier s'arrete net.
            config.DB_PATH.write_bytes(brut[:1500])

    def tearDown(self):
        # Repartir d'une base saine : les autres cas de ce module, et les
        # autres modules, n'ont pas a heriter d'un fichier casse.
        store.close()
        if config.DB_PATH.exists():
            config.DB_PATH.unlink()
        store.connect()

    def test_une_base_saine_ne_declenche_rien(self):
        store.connect()
        self.assertEqual(store.diagnostic_base(), "")

    def test_l_entete_detruite_est_vue(self):
        self._casser("entete")
        self.assertIn("not a database", store.diagnostic_base())

    def test_la_base_tronquee_est_vue(self):
        self._casser("tronquee")
        self.assertIn("malformed", store.diagnostic_base())

    def test_une_page_interieure_ecrasee_est_vue(self):
        """La forme silencieuse, et la raison d'etre de « integrity_check ».

        Une page interieure abimee ne leve rien a l'ouverture : SQLite lit
        l'entete, trouve tout normal, et n'echoue que le jour ou une requete
        touche cette page-la. Un controle qui se contenterait d'ouvrir la base
        declarerait ce fichier sain.
        """
        store.connect()
        store.close()
        for _ in range(400):
            store.enregistrer_empreinte("p{}".format(_), "ebook", "t", "s",
                                        "x" * 200, "plan", 100)
        store.close()
        brut = bytearray(config.DB_PATH.read_bytes())
        self.assertGreater(len(brut), 12288, "base trop petite pour ce test")
        brut[8192:12288] = b"\xff" * 4096
        config.DB_PATH.write_bytes(bytes(brut))
        self.assertNotEqual(store.diagnostic_base(), "")

    def test_une_base_absente_n_est_pas_une_base_cassee(self):
        """Premiere installation : il n'y a pas encore de fichier."""
        store.close()
        config.DB_PATH.unlink()
        self.assertEqual(store.diagnostic_base(), "")

    def test_le_message_nomme_le_fichier_et_les_deux_remedes(self):
        message = cli._expliquer_base("file is not a database")
        self.assertIn(str(config.DB_PATH), message)
        self.assertIn("--restaurer", message)
        self.assertIn("mv ", message)

    def test_le_message_dit_que_les_produits_survivent(self):
        """Le seul point qui evite une reinstallation de panique.

        Les produits sont des fichiers dans produits/ ; la base ne porte que
        l'historique. Qui l'ignore efface tout et recommence.
        """
        message = cli._expliquer_base("file is not a database")
        self.assertIn(str(config.PRODUITS_DIR), message)
        self.assertIn("intacts", message)

    def test_docteur_survit_a_une_base_illisible(self):
        """La commande qu'on lance quand plus rien ne marche.

        Elle mourait comme les autres, sur la meme ligne et pour la meme
        raison : elle lit les compteurs du jour, qui sont dans la base.
        """
        from usine.core import diagnostic as module_diagnostic

        self._casser("entete")
        etat = module_diagnostic.etat_installation(avec_reseau=False,
                                                   avec_locaux=False)
        self.assertIn("not a database", etat["base"])
        self.assertEqual(etat["verdict"]["etat"], "bloque")
        self.assertIn("sauvegarde", etat["verdict"]["remede"])

    def test_les_compteurs_inconnus_ne_deviennent_pas_zero(self):
        """Un chiffre sans source est pire que pas de chiffre.

        « 0 appel aujourd'hui » se lit « quota intact ». C'est justement la
        conclusion qu'on ne peut pas tirer quand la base ne se lit plus.
        """
        from usine.core import llm

        lignes = llm.diagnostic(compteurs=False)
        self.assertTrue(lignes)
        for ligne in lignes:
            self.assertIsNone(ligne["aujourdhui"])
            self.assertIsNone(ligne["jetons_aujourdhui"])
        self.assertEqual(cli._compte(None), "?")
        self.assertEqual(cli._compte(0), "0")

    def test_le_tableau_de_bord_ne_meurt_pas_sur_sa_premiere_requete(self):
        """Sinon la page reste vide, bouton « docteur » compris.

        « /api/etat » est la toute premiere requete de la page, et tout ce
        qu'elle assemble passe par la base. Elle levait donc, et le seul
        ecran qui aurait su expliquer la panne n'etait jamais atteint.
        """
        from usine.web import serveur

        self._casser("entete")
        etat = serveur._etat()
        self.assertIn("not a database", etat["base"])
        self.assertIn("--restaurer", etat["remede"])

    def test_le_tableau_de_bord_repond_normalement_sur_une_base_saine(self):
        """L'autre branche, sans quoi un « return » trop tot passerait."""
        from usine.web import serveur

        store.connect()
        etat = serveur._etat()
        self.assertEqual(etat["base"], "")
        self.assertIn("fournisseurs", etat)

    def test_le_verdict_ne_conseille_pas_une_cle_pour_une_base_cassee(self):
        """« bloque » ne suffit pas a choisir le geste.

        Le remede etait deduit de l'etat : tout « bloque » affichait
        « usine cles ». Ajouter une cle ne repare aucune base.
        """
        from usine.core import diagnostic as module_diagnostic

        self._casser("entete")
        etat = module_diagnostic.etat_installation(avec_reseau=False,
                                                   avec_locaux=False)
        self.assertNotIn("usine cles", etat["verdict"]["remede"])


class ReseauCoupe(unittest.TestCase):
    """Le telephone sort du wifi au milieu d'une fabrication de quinze minutes.

    Ce n'est pas un cas rare : c'est le cas normal d'un appareil qu'on met
    dans sa poche. Ce que l'utilisateur voyait alors : la liste des
    fournisseurs qui ont echoue, puis « Nouvelle cle : usine cles » — un
    conseil absurde quand le probleme est le wifi, et qui envoie creer des
    comptes chez quatre fournisseurs pour rien.
    """

    def setUp(self):
        from usine.core import llm

        self.llm = llm
        llm.definir_simulateur(None)

    def tearDown(self):
        self.llm.definir_simulateur(None)

    def _principal(self, en_ligne, argv):
        """Lance la CLI avec un reseau decide d'avance et aucun fournisseur.

        On capte aussi stderr : « erreur() » y ecrit, et c'est justement la
        que se trouve le message qu'on veut lire.
        """
        import io as flux
        from contextlib import redirect_stderr, redirect_stdout

        from usine.core import http

        vrai = http.en_ligne
        http.en_ligne = lambda timeout=6: en_ligne
        sortie = flux.StringIO()
        try:
            with redirect_stdout(sortie), redirect_stderr(sortie):
                code = cli.principal(argv)
        finally:
            http.en_ligne = vrai
        return code, sortie.getvalue()

    def _sans_fournisseur(self):
        """Un routeur qui n'a plus personne : l'etat d'un telephone hors ligne."""
        def tombe(*_a, **_kw):
            raise self.llm.PlusDeFournisseur(
                "Tous les fournisseurs ont echoue :\n  - groq : reseau indisponible")
        self.llm.definir_simulateur(tombe)

    def test_hors_ligne_on_parle_du_wifi_et_pas_des_cles(self):
        self._sans_fournisseur()
        code, texte = self._principal(False, ["ebook", "un sujet quelconque"])
        self.assertEqual(code, 3)
        self.assertIn("Le reseau est coupe", texte)
        self.assertNotIn("usine cles", texte)

    def test_en_ligne_on_renvoie_bien_au_diagnostic(self):
        """L'autre branche : le reseau marche, donc le defaut est ailleurs.

        Sans ce cas, le test precedent passerait aussi avec un message fige.
        """
        self._sans_fournisseur()
        code, texte = self._principal(True, ["ebook", "un sujet quelconque"])
        self.assertEqual(code, 3)
        self.assertIn("usine cles", texte)
        self.assertNotIn("Le reseau est coupe", texte)

    def test_les_deux_branches_disent_que_la_relance_reprend_le_travail(self):
        self._sans_fournisseur()
        for en_ligne in (True, False):
            with self.subTest(en_ligne=en_ligne):
                _, texte = self._principal(en_ligne, ["ebook", "un sujet"])
                self.assertIn("sans repayer ce qui est fait", texte)

    def test_une_coupure_ne_fait_pas_passer_un_produit_pour_livre(self):
        """Le defaut le plus couteux serait le silencieux.

        Un dossier de produit reste sur le disque apres la coupure. Il ne doit
        ni s'annoncer livre, ni apparaitre au catalogue comme un produit fini.
        """
        from tests.simulateur import simulateur

        appels = {"n": 0}

        def coupure(invite, role="standard", **kw):
            appels["n"] += 1
            if appels["n"] > 6:
                raise self.llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
            return simulateur(invite, role=role, **kw)

        self.llm.definir_simulateur(coupure)
        # Atelier neuf : le cache des reponses IA est partage par tout le
        # module, et un cas qui herite du cache d'un autre n'exerce plus la
        # coupure — le compteur n'atteint jamais son seuil.
        atelier.isoler("pannes-coupure")
        try:
            code, texte = self._principal(
                False, ["ebook", "la coupure de reseau", "--chapitres", "8"])
            produits = store.lister_produits()
            _, liste = self._principal(False, ["liste"])
        finally:
            atelier.isoler("pannes")
        self.assertEqual(code, 3)
        self.assertNotIn("Produit livre", texte)
        # Le dossier reste : c'est voulu, il porte le travail deja paye. Ce
        # qui ne doit pas rester, c'est l'idee qu'il est fini.
        self.assertEqual([p["statut"] for p in produits], ["en_cours"])
        self.assertIn("inacheve", liste)
        self.assertIn("sans repayer ce qui est fait", liste)

    def test_la_relance_ne_repaie_pas_les_appels_deja_faits(self):
        """La mesure qui autorise la phrase affichee a l'utilisateur.

        On promet « reprend ou vous en etiez, sans repayer ce qui est fait ».
        La promesse tient au cache, et le cache est ce qui se casse le plus
        discretement : une invite qui change d'un espace, et la relance repaie
        tout sans que rien ne le signale.

        On ne promet PAS la gratuite : ici la relance coute encore les appels
        jamais faits. C'est la difference entre les deux phrases, et elle est
        exactement ce que le cache a rendu.
        """
        from tests.simulateur import simulateur

        appels = {"n": 0}
        COUPE_A = 6

        def coupure(invite, role="standard", **kw):
            appels["n"] += 1
            if appels["n"] > COUPE_A:
                raise self.llm.PlusDeFournisseur("Tous les fournisseurs ont echoue")
            return simulateur(invite, role=role, **kw)

        self.llm.definir_simulateur(coupure)
        atelier.isoler("pannes-relance")
        self._principal(False, ["ebook", "la relance apres coupure",
                                "--chapitres", "8"])

        relance = {"n": 0}

        def compte(invite, role="standard", **kw):
            # Le simulateur n'est appele que si le cache s'est tu : ce
            # compteur mesure donc ce que la relance coute vraiment.
            relance["n"] += 1
            return simulateur(invite, role=role, **kw)

        self.llm.definir_simulateur(compte)
        code, _ = self._principal(True, ["ebook", "la relance apres coupure",
                                         "--chapitres", "8"])
        self.assertEqual(code, 0, "la relance doit aller au bout")

        # Combien coute la meme fabrication d'un seul trait, cache vide ?
        atelier.isoler("pannes-neuf")
        try:
            dun_trait = {"n": 0}

            def compte_neuf(invite, role="standard", **kw):
                dun_trait["n"] += 1
                return simulateur(invite, role=role, **kw)

            self.llm.definir_simulateur(compte_neuf)
            self._principal(True, ["ebook", "la relance apres coupure",
                                   "--chapitres", "8"])
        finally:
            atelier.isoler("pannes")

        self.assertEqual(relance["n"], dun_trait["n"] - COUPE_A,
                         "le cache doit rendre exactement les appels deja payes")
        self.assertGreater(relance["n"], 0,
                           "sans quoi le test ne distinguerait pas cache et gratuite")


class DocteurAvecUneCle(unittest.TestCase):
    """Le pool de cles n'est rempli que chez qui possede une cle.

    D'ou un defaut qui ne pouvait pas sortir en test : la boucle d'affichage
    du pool ecrasait le dictionnaire de diagnostic par une chaine de couleur,
    et la section suivante mourait. Sans cle, la boucle ne tourne jamais.
    Autrement dit, « usine docteur » plantait chez tous les vrais
    utilisateurs, et chez eux seuls.
    """

    def test_docteur_affiche_le_pool_sans_ecraser_son_diagnostic(self):
        import io
        import os
        from contextlib import redirect_stdout

        from usine.core import cles as pool_cles
        from usine.core import diagnostic as module_diagnostic

        # « cmd_docteur » sonde le reseau et les serveurs locaux. On coupe les
        # deux plutot que d'appeler etat_installation nous-memes : c'est
        # justement le chemin reel de la commande qu'on veut voir tourner.
        reseau, locaux = module_diagnostic._reseau, module_diagnostic.locaux_actifs
        module_diagnostic._reseau = lambda: False
        module_diagnostic.locaux_actifs = lambda timeout=3: []
        os.environ["GROQ_API_KEY"] = "gsk_" + "0" * 32
        try:
            pool_cles.oublier()
            sortie = io.StringIO()
            with redirect_stdout(sortie):
                code = cli.cmd_docteur(_Sansargument())
            texte = sortie.getvalue()
        finally:
            module_diagnostic._reseau, module_diagnostic.locaux_actifs = reseau, locaux
            os.environ.pop("GROQ_API_KEY", None)
            pool_cles.oublier()
        self.assertEqual(code, 0)
        self.assertIn("Pool de cles", texte)


class _Sansargument:
    """Le strict necessaire pour appeler cmd_docteur sans argparse."""

    modeles = False


if __name__ == "__main__":
    unittest.main()
