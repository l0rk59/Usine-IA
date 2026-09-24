"""La fiche technique de l'appareil, et la mise a jour depuis le depot.

Deux commandes qui manquaient au bout de la boucle Termux.

« usine docteur » dit si l'usine peut produire MAINTENANT. Il ne dit pas ce
qui devrait etre dans install.sh pour que cet appareil-la marche sans
bricolage — et c'est cette question-la qu'on se pose quand on veut corriger
l'installation pour tout le monde, pas seulement pour soi.

Quant a la mise a jour : sur Termux, git n'est pas installe par defaut, et
l'usine a justement ete ecrite pour ne rien exiger. Il faut donc que la
commande marche sans lui.
"""

from __future__ import annotations

import io
import sys
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import cli  # noqa: E402
from usine.core import config, maj, specs  # noqa: E402


def setUpModule():
    atelier.isoler("machine")


def _muet(argv):
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = cli.principal(argv)
    return code, sortie.getvalue()


class FicheTechnique(unittest.TestCase):

    def setUp(self):
        self.releve = specs.relever()

    def test_aucune_cle_api_n_entre_dans_la_fiche(self):
        """La fiche est faite pour etre poussee sur un depot public.

        C'est la seule contrainte absolue de ce module : tout le reste peut
        etre approximatif, une cle recopiee ne se rattrape pas.
        """
        import os

        os.environ["GROQ_API_KEY"] = "gsk_secret_a_ne_jamais_ecrire_00000000"
        try:
            from usine.core import cles as pool_cles

            pool_cles.oublier()
            releve_avec_cle = specs.relever()
            texte = specs.en_markdown(releve_avec_cle)
        finally:
            os.environ.pop("GROQ_API_KEY", None)
            from usine.core import cles as pool_cles

            pool_cles.oublier()
        self.assertNotIn("gsk_secret", texte)
        self.assertNotIn("secret_a_ne_jamais_ecrire", texte)
        # Et pas davantage dans le RELEVE : la fiche n'est qu'une mise en
        # forme, et un releve qui porte les cles finira tot ou tard ecrit
        # quelque part — dans un rapport, dans un journal, dans un ticket.
        self.assertNotIn("secret_a_ne_jamais_ecrire", repr(releve_avec_cle))
        # Le NOMBRE de cles, lui, a sa place : c'est ce qui dit si l'appareil
        # est configure, sans rien reveler.
        self.assertIn("| Fournisseur | Variable | Cles | Genre |", texte)

    def test_un_binaire_absent_dit_ce_que_son_absence_coute(self):
        """« installez nodejs » sans dire pourquoi ne fait installer personne."""
        for binaire in self.releve["binaires"]:
            with self.subTest(binaire=binaire["nom"]):
                self.assertTrue(binaire["cout_si_absent"].strip())

    def test_la_fiche_commence_par_ce_qui_manque(self):
        """Une fiche qui enumere trente lignes vertes et cache la seule rouge
        ne sert a personne."""
        texte = specs.en_markdown(self.releve)
        self.assertLess(texte.index("## Ce qui manque"),
                        texte.index("## L'appareil"))

    def test_chaque_manque_porte_la_commande_qui_le_pose(self):
        for manque in specs._manques(self.releve):
            with self.subTest(manque=manque["quoi"]):
                self.assertTrue(manque["commande"].strip())
                self.assertIn(manque["gravite"],
                              ("bloquant", "recommande", "optionnel"))

    def test_hors_termux_on_ne_reclame_pas_les_outils_termux(self):
        """Un garde-fou qui crie a tort finit ignore.

        Sur un ordinateur, « termux-notification » n'existe pas et n'a aucune
        raison d'exister : le reclamer ferait trente lignes de bruit a chaque
        fiche, et la seule ligne utile se perdrait dedans.
        """
        faux = dict(self.releve)
        faux["termux"] = {"termux": False, "api": False, "batterie": None}
        manques = specs._manques(faux)
        self.assertFalse([m for m in manques if m["quoi"].startswith("termux-")])

    def test_la_commande_ecrit_le_fichier_et_le_dit(self):
        cible = config.WORKDIR / "fiche-essai.md"
        code, texte = _muet(["specs", "--vers", str(cible)])
        self.assertIn(code, (0, 1))     # 1 quand il manque quelque chose de bloquant
        self.assertTrue(cible.exists())
        self.assertIn("Fiche ecrite", texte)
        self.assertIn("# Fiche technique de l'appareil",
                      cible.read_text(encoding="utf-8"))

    def test_hors_du_telephone_la_fiche_du_depot_reste_intacte(self):
        """Elle decrit le telephone. Lancee dans un conteneur, la commande la
        remplacait par la fiche de la machine du moment — deux fois deja."""
        from unittest import mock

        from usine.core import maj

        racine = Path(tempfile.mkdtemp(prefix="usine-racine-"))
        self.addCleanup(shutil.rmtree, str(racine), True)
        fiche = racine / "SPECS-APPAREIL.md"
        fiche.write_text("la fiche du telephone", encoding="utf-8")
        releve = dict(specs.relever())
        releve["termux"] = {"termux": False, "api": False, "batterie": None}
        with mock.patch.object(maj, "racine", return_value=racine), \
                mock.patch.object(specs, "relever", return_value=releve):
            code, texte = _muet(["specs"])
        self.assertEqual(fiche.read_text(encoding="utf-8"), "la fiche du telephone")
        self.assertTrue((config.WORKDIR / "SPECS-APPAREIL.md").exists())
        self.assertIn("n'est pas un telephone", texte)

    def test_sur_le_telephone_elle_part_a_la_racine(self):
        from unittest import mock

        from usine.core import maj

        racine = Path(tempfile.mkdtemp(prefix="usine-racine-"))
        self.addCleanup(shutil.rmtree, str(racine), True)
        releve = dict(specs.relever())
        releve["termux"] = {"termux": True, "api": True, "batterie": None}
        with mock.patch.object(maj, "racine", return_value=racine), \
                mock.patch.object(specs, "relever", return_value=releve):
            _muet(["specs"])
        self.assertIn("# Fiche technique de l'appareil",
                      (racine / "SPECS-APPAREIL.md").read_text(encoding="utf-8"))

    def test_un_manque_bloquant_donne_un_code_de_sortie_non_nul(self):
        """Pour qu'un script d'installation puisse s'en servir."""
        code, _ = _muet(["specs", "--vers",
                         str(config.WORKDIR / "fiche-code.md")])
        bloquants = [m for m in specs._manques(specs.relever())
                     if m["gravite"] == "bloquant"]
        self.assertEqual(code, 1 if bloquants else 0)


class MiseAJour(unittest.TestCase):

    def test_l_atelier_et_la_cle_ne_sont_jamais_remplaces(self):
        """Les ecraser en mettant a jour serait la pire facon de perdre
        quelqu'un : il ne se sert plus jamais de la commande, et il a raison.
        """
        self.assertNotIn("atelier", maj.DOSSIERS_CODE)
        self.assertNotIn(".env", maj.FICHIERS_CODE)
        for nom in maj.DOSSIERS_CODE + maj.FICHIERS_CODE:
            with self.subTest(nom=nom):
                self.assertFalse(nom.startswith("atelier"))

    def test_la_racine_est_bien_le_dossier_d_installation(self):
        self.assertTrue((maj.racine() / "usine").is_dir())

    def test_une_archive_qui_sort_du_dossier_est_refusee(self):
        """Un nom de membre vient du reseau.

        « ../../.bashrc » dans une archive est le moyen le plus simple de
        faire ecrire un fichier ou l'on veut. Le refus est total : on ne
        deballe rien du tout, plutot que de sauter le membre fautif.
        """
        import zipfile
        from unittest import mock

        faux = io.BytesIO()
        with zipfile.ZipFile(faux, "w") as archive:
            archive.writestr("Usine-IA-main/usine/__init__.py", "x = 1")
            archive.writestr("../evade.txt", "je sors")
        with mock.patch("usine.core.http.get_bytes", return_value=faux.getvalue()):
            resultat = maj.par_archive("main", dossier=config.WORKDIR)
        self.assertFalse(resultat["ok"])
        self.assertIn("sortait", str(resultat["erreur"]))
        self.assertFalse((config.WORKDIR / "evade.txt").exists())

    def test_une_archive_sans_usine_est_refusee(self):
        """Avoir a moitie deballe n'importe quoi sur l'installation serait
        pire que de ne pas avoir essaye."""
        import zipfile
        from unittest import mock

        faux = io.BytesIO()
        with zipfile.ZipFile(faux, "w") as archive:
            archive.writestr("autre-chose/lisezmoi.txt", "ce n'est pas l'usine")
        with mock.patch("usine.core.http.get_bytes", return_value=faux.getvalue()):
            resultat = maj.par_archive("main", dossier=config.WORKDIR)
        self.assertFalse(resultat["ok"])
        self.assertIn("attendue", str(resultat["erreur"]))

    def test_un_fichier_qui_n_est_pas_une_archive_est_refuse(self):
        from unittest import mock

        with mock.patch("usine.core.http.get_bytes",
                        return_value=b"<html>404 not found</html>"):
            resultat = maj.par_archive("main", dossier=config.WORKDIR)
        self.assertFalse(resultat["ok"])
        self.assertIn("archive", str(resultat["erreur"]))

    def test_une_archive_valide_remplace_le_code_et_rien_d_autre(self):
        import zipfile
        from unittest import mock

        cible = config.WORKDIR / "installation-essai"
        (cible / "atelier").mkdir(parents=True, exist_ok=True)
        (cible / "atelier" / "temoin.txt").write_text("mon travail",
                                                      encoding="utf-8")
        (cible / ".env").write_text("CLE=secrete", encoding="utf-8")

        faux = io.BytesIO()
        with zipfile.ZipFile(faux, "w") as archive:
            archive.writestr("Usine-IA-main/usine/__init__.py",
                             '__version__ = "9.9.9"')
            archive.writestr("Usine-IA-main/README.md", "# nouvelle version")
        with mock.patch("usine.core.http.get_bytes", return_value=faux.getvalue()):
            resultat = maj.par_archive("main", dossier=cible)

        self.assertTrue(resultat["ok"], resultat.get("erreur"))
        self.assertIn("usine/", resultat["remplaces"])
        self.assertEqual((cible / "atelier" / "temoin.txt").read_text(
            encoding="utf-8"), "mon travail")
        self.assertEqual((cible / ".env").read_text(encoding="utf-8"),
                         "CLE=secrete")
        self.assertIn("9.9.9", (cible / "usine" / "__init__.py").read_text(
            encoding="utf-8"))

    def test_une_archive_demesuree_est_refusee_sans_etre_ouverte(self):
        """Sur un telephone, deballer cent megaoctets pour rien coute la place
        qu'on n'a pas."""
        from unittest import mock

        enorme = b"0" * (maj.TAILLE_MAX + 1)
        with mock.patch("usine.core.http.get_bytes", return_value=enorme):
            resultat = maj.par_archive("main", dossier=config.WORKDIR)
        self.assertFalse(resultat["ok"])
        self.assertIn("inattendue", str(resultat["erreur"]))

    def test_la_verification_relance_un_processus_neuf(self):
        """Les modules deja charges ICI sont l'ancienne version.

        Reimporter apres une mise a jour repondrait « tout va bien » quoi
        qu'on ait installe — c'est-a-dire exactement quand il ne faut pas.
        """
        source = Path(maj.__file__).read_text(encoding="utf-8")
        self.assertIn("subprocess.run", source.split("def verifier")[1])

    def test_un_depot_prive_est_nomme_comme_cause_possible(self):
        """Un depot prive repond 404 sans jeton, comme une branche inconnue.

        On ne peut pas distinguer les deux depuis l'appareil. Nommer les deux
        evite de chercher une panne de reseau pendant une heure parce que le
        depot est simplement prive — ce qui est le cas du depot de
        l'utilisateur.
        """
        from unittest import mock

        with mock.patch("usine.core.http.get_bytes",
                        side_effect=Exception("HTTP 404")):
            resultat = maj.par_archive("main", dossier=config.WORKDIR)
        self.assertFalse(resultat["ok"])
        message = str(resultat["erreur"])
        self.assertIn("prive", message)
        self.assertIn("git", message)

    def test_les_modifications_locales_sont_signalees_avant_d_ecraser(self):
        from unittest import mock

        with mock.patch("usine.core.maj.modifications_locales",
                        return_value=["usine/cli.py"]), \
             mock.patch("usine.core.maj.est_un_clone", return_value=True), \
             mock.patch("usine.core.maj.git_disponible", return_value=True):
            code, texte = _muet(["maj"])
        self.assertEqual(code, 1)
        self.assertIn("usine/cli.py", texte)
        self.assertIn("--oui", texte)


if __name__ == "__main__":
    unittest.main()
