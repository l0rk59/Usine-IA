"""Chaque type de produit declare ses reglages une fois, et trois lecteurs.

Mesure du 14/09/2026 : sur les dix-sept options propres aux types fabricables,
HUIT etaient inatteignables depuis le tableau de bord.

    formation   MANQUE narration, modules
    impression  MANQUE reliure
    social      MANQUE visuels
    logiciel    MANQUE cible, sans_essai
    idees       MANQUE sans_veille, sans_marche

On ne pouvait donc pas choisir, depuis le navigateur, si un outil logiciel
devait etre une ligne de commande ou une application web — ni combien de
modules comptait une formation.

La cause n'etait pas un oubli mais une FORME. Le formulaire etait du HTML
ecrit a la main, avec des blocs caches et montres par le script : un
« bloc-reseau » pour les posts, un « bloc-serie » pour la fiction, et rien pour
le reste. Ajouter un type demandait d'editer le gabarit, le script ET le
serveur — et les options tombaient entre les mailles, une par une.

Les champs se declarent maintenant dans le catalogue. L'analyseur d'arguments
les transforme en « add_argument », le serveur les sert, le tableau de bord en
fait la section du type. Un champ ajoute la-bas apparait partout.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402

HTML = (RACINE / "usine" / "web" / "statique" / "tableau.html").read_text(
    encoding="utf-8")
JS = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
    encoding="utf-8")

# Ce que « _options_communes » ajoute a TOUS les types : ces options ne sont
# pas propres a un type et n'ont rien a faire dans sa declaration.
COMMUNES = {
    "help", "sujet", "audience", "ton", "taille", "chapitres", "mots",
    "auteur", "langue", "marque", "prix", "dedicace", "contact", "qualite",
    "sans_marketing", "sans_zip", "marketing", "extrait", "plateforme",
    "zip", "hors_ligne", "sans_image", "relecture_ensemble", "reprendre_id",
    "commande", "fonction",
}


def setUpModule():
    atelier.isoler("champs-par-type")


def _options_recues(cle):
    """Ce que l'analyseur d'arguments accepte reellement pour ce type."""
    from usine import cli

    parseur = cli.construire_parseur()
    sous = [a for a in parseur._actions if getattr(a, "choices", None)][0]
    return sorted(a.dest for a in sous.choices[cle]._actions
                  if a.dest not in COMMUNES)


class UneDeclarationTroisLecteurs(unittest.TestCase):

    def test_l_analyseur_recoit_exactement_ce_qui_est_declare(self):
        """Mesure sur l'ANALYSEUR, pas sur le texte du fichier : une option
        ecrite et jamais ajoutee passerait une recherche de chaine."""
        for type_produit in catalogue.tous():
            with self.subTest(type=type_produit.cle):
                declares = sorted(c.nom for c in type_produit.champs)
                self.assertEqual(
                    _options_recues(type_produit.cle), declares,
                    "« {} » : le catalogue et la ligne de commande ne disent "
                    "pas la meme chose".format(type_produit.cle))

    def test_le_serveur_sert_les_champs_de_chaque_type(self):
        from usine.web import serveur

        servis = {t["cle"]: t for t in serveur._catalogue()}
        for type_produit in catalogue.tous(fabricables=True):
            with self.subTest(type=type_produit.cle):
                recus = [c["nom"] for c in servis[type_produit.cle]["champs"]]
                self.assertEqual(recus, [c.nom for c in type_produit.champs])

    def test_le_navigateur_ne_connait_aucun_type_en_dur(self):
        """C'est le defaut d'origine : « if type === 'social' » dans le
        script. Chaque type nomme la-bas est un type qui vieillira seul."""
        for type_produit in catalogue.tous():
            with self.subTest(type=type_produit.cle):
                self.assertNotIn("'{}'".format(type_produit.cle), JS,
                                 "le script nomme « {} » en dur"
                                 .format(type_produit.cle))

    def test_le_gabarit_ne_contient_aucun_champ_propre_a_un_type(self):
        """Ils sont batis depuis le catalogue. Un champ laisse dans le
        gabarit serait servi pour TOUS les types, y compris ceux qui ne
        savent pas quoi en faire."""
        propres = {c.nom for t in catalogue.tous() for c in t.champs}
        for nom in sorted(propres):
            with self.subTest(champ=nom):
                self.assertNotIn('id="{}"'.format(nom), HTML)

    def test_les_champs_declares_sont_reellement_rendus(self):
        """La declaration peut etre juste, le serveur peut la servir, et la
        carte rester vide : rien ne relie les deux si personne ne dessine.

        Une premiere version des controles s'arretait au serveur. Vider le
        rendu — « innerHTML = '' » — laissait tout passer, et le formulaire
        n'affichait plus un seul reglage de type.
        """
        bloc = JS[JS.index("function dessinerChampsDuType"):]
        bloc = bloc[:bloc.index("\n}")]
        self.assertIn("champs-type", bloc)
        self.assertIn("champDuType", bloc,
                      "les champs ne sont pas transformes en HTML")
        self.assertIn("type.champs", bloc,
                      "le rendu ne lit pas la declaration du type")
        # Et « champDuType » doit vraiment produire un champ de saisie.
        fabrique = JS[JS.index("function champDuType"):]
        fabrique = fabrique[:fabrique.index("\nfunction ")]
        for genre in ("checkbox", "select", "input"):
            with self.subTest(genre=genre):
                self.assertIn(genre, fabrique)
        self.assertIn("data-champ", fabrique,
                      "les champs rendus ne portent pas leur nom : l'envoi "
                      "ne saura pas les relire")

    def test_ce_qui_est_rendu_est_relu_a_l_envoi(self):
        """Un champ affiche et jamais envoye est un mensonge fait a
        l'utilisateur : il le remplit, et rien n'en tient compte."""
        bloc = JS[JS.index("function valeursDuType"):]
        bloc = bloc[:bloc.index("\n}")]
        self.assertIn("data-champ", bloc)
        self.assertIn("champs-type", bloc)
        envoi = JS[JS.index("$('lancer').addEventListener"):]
        envoi = envoi[:envoi.index("\n});")]
        self.assertIn("valeursDuType()", envoi,
                      "la fabrication n'envoie pas les reglages du type")

    def test_la_carte_du_type_existe_et_part_vide(self):
        self.assertIn('id="champs-type"', HTML)
        bloc = HTML[HTML.index('id="champs-type"'):]
        self.assertTrue(bloc.startswith('id="champs-type"></div>'),
                        "la carte du type contient du HTML ecrit a la main")


class ChaqueChampSaitCeQuIlEst(unittest.TestCase):

    GENRES = {"texte", "entier", "decimal", "booleen", "choix"}

    def test_chaque_champ_a_un_genre_connu(self):
        """Un genre invente se rendrait en champ texte, en silence : un
        nombre de modules saisi comme une phrase, et la chaine recevrait
        « douze » la ou elle attend 12."""
        for type_produit in catalogue.tous():
            for champ in type_produit.champs:
                with self.subTest(type=type_produit.cle, champ=champ.nom):
                    self.assertIn(champ.genre, self.GENRES)

    def test_un_champ_de_choix_propose_des_choix(self):
        for type_produit in catalogue.tous():
            for champ in type_produit.champs:
                if champ.genre != "choix":
                    continue
                with self.subTest(type=type_produit.cle, champ=champ.nom):
                    self.assertTrue(champ.choix,
                                    "liste deroulante sans aucune option")

    def test_les_choix_sont_lus_la_ou_ils_sont_decides(self):
        """Recopier la liste des reseaux ici en ferait deux listes, et c'est
        celle du formulaire qui proposerait un reseau retire."""
        from usine.pipelines import logiciel, social

        reseaux = next(c for c in catalogue.obtenir("social").champs
                       if c.nom == "reseau")
        self.assertEqual(set(reseaux.choix), set(social.RESEAUX))
        cibles = next(c for c in catalogue.obtenir("logiciel").champs
                      if c.nom == "cible")
        self.assertEqual(set(cibles.choix), set(logiciel.CIBLES))

    def test_chaque_champ_a_un_libelle_lisible(self):
        """Le nom technique — « sans_essai » — ne se montre pas a
        l'utilisateur."""
        for type_produit in catalogue.tous():
            for champ in type_produit.champs:
                with self.subTest(type=type_produit.cle, champ=champ.nom):
                    self.assertTrue(champ.libelle.strip())
                    self.assertNotEqual(champ.libelle, champ.nom)

    def test_chaque_drapeau_commence_par_un_tiret(self):
        for type_produit in catalogue.tous():
            for champ in type_produit.champs:
                for drapeau in champ.drapeaux:
                    with self.subTest(champ=champ.nom, drapeau=drapeau):
                        self.assertTrue(drapeau.startswith("-"))


class LesCinqTypesOrphelinsSontReglables(unittest.TestCase):
    """Les cinq qu'on ne pouvait pas regler depuis le navigateur."""

    MANQUAIENT = {
        "formation": ("modules", "narration"),
        "impression": ("reliure",),
        "social": ("visuels",),
        "logiciel": ("cible", "sans_essai"),
        "idees": ("sans_marche", "sans_veille"),
    }

    def test_chacun_des_huit_reglages_perdus_est_revenu(self):
        from usine.web import serveur

        servis = {t["cle"]: [c["nom"] for c in t["champs"]]
                  for t in serveur._catalogue()}
        for cle, noms in sorted(self.MANQUAIENT.items()):
            for nom in noms:
                with self.subTest(type=cle, champ=nom):
                    self.assertIn(nom, servis.get(cle, []),
                                  "« {} » reste inatteignable depuis le "
                                  "tableau de bord".format(nom))


if __name__ == "__main__":
    unittest.main()
