"""La memoire de ce que l'usine a deja ecrit.

Le defaut vise ne se voit qu'au volume : quatre produits par jour sur des
niches voisines donnent trois fois le meme livre. Ni le modele ni le controle
qualite ne peuvent le reperer — chacun ne regarde qu'un produit a la fois, et
chacun le trouve bon.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("USINE_HOME", tempfile.mkdtemp(prefix="usine-empreinte-"))

from usine.core import empreinte  # noqa: E402

TEXTE = (
    "Prospecter demande une regularite que peu de freelances tiennent. "
    "Bloquez une heure chaque lundi matin, avant toute autre tache. "
    "Ecrivez a cinq personnes precises plutot qu'a cinquante inconnues. "
    "Relancez une fois au bout de huit jours, puis passez a autre chose."
)
REMANIE = (
    "Prospecter demande une regularite que bien peu de freelances tiennent. "
    "Bloquez donc une heure chaque lundi matin, avant toute autre tache. "
    "Ecrivez a cinq personnes precises plutot qu'a cinquante inconnues. "
    "Relancez une fois au bout de huit jours, puis passez a autre chose."
)
ETRANGER = (
    "La photosynthese convertit la lumiere solaire en energie chimique. "
    "Les chloroplastes abritent la chlorophylle, pigment vert des feuilles. "
    "Le dioxyde de carbone entre par les stomates de la face inferieure. "
    "L'oxygene produit repart dans l'atmosphere par le meme chemin."
)


class TestSignature(unittest.TestCase):

    def test_l_estimation_suit_le_calcul_exact(self):
        """MinHash approche Jaccard : le verifier sur des cas connus."""
        for un, autre in ((TEXTE, REMANIE), (TEXTE, ETRANGER),
                          (TEXTE, TEXTE), (REMANIE, ETRANGER)):
            exact = empreinte.jaccard(empreinte.groupes(un),
                                      empreinte.groupes(autre))
            estime = empreinte.ressemblance(empreinte.signature(un),
                                            empreinte.signature(autre))
            self.assertAlmostEqual(estime, exact, delta=0.12,
                                   msg="{:.2f} contre {:.2f}".format(estime, exact))

    def test_un_texte_est_identique_a_lui_meme(self):
        self.assertEqual(
            empreinte.ressemblance(empreinte.signature(TEXTE),
                                   empreinte.signature(TEXTE)), 1.0)

    def test_deux_textes_etrangers_ne_se_ressemblent_pas(self):
        self.assertLess(
            empreinte.ressemblance(empreinte.signature(TEXTE),
                                   empreinte.signature(ETRANGER)), 0.05)

    def test_un_remaniement_leger_reste_detecte(self):
        """Changer quelques mots ne suffit pas a faire un autre produit."""
        self.assertGreater(
            empreinte.ressemblance(empreinte.signature(TEXTE),
                                   empreinte.signature(REMANIE)), 0.55)

    def test_la_signature_a_une_taille_fixe(self):
        """Un texte long et un texte court doivent rester comparables."""
        court = empreinte.signature("Trois mots seulement ici pour voir.")
        long = empreinte.signature(TEXTE * 40)
        self.assertEqual(len(court), empreinte.EMPREINTES)
        self.assertEqual(len(long), empreinte.EMPREINTES)

    def test_un_texte_vide_ne_ressemble_a_rien(self):
        self.assertEqual(empreinte.signature(""), [])
        self.assertEqual(empreinte.ressemblance([], empreinte.signature(TEXTE)), 0.0)

    def test_les_fonctions_de_hachage_ne_bougent_pas(self):
        """Deux signatures ne sont comparables que si elles viennent des memes.

        Un tirage aleatoire a chaque demarrage rendrait incomparables les
        produits d'avant et d'apres un redemarrage — le module serait
        silencieusement inutile.
        """
        premier = empreinte.signature(TEXTE)
        import importlib

        importlib.reload(empreinte)
        self.assertEqual(premier, empreinte.signature(TEXTE))


class TestPlan(unittest.TestCase):
    """Le cas que la comparaison de texte seule laisse passer."""

    UN = ["Chapitre 1 — Pourquoi vous n'avez pas assez de clients",
          "Chapitre 2 — Trouver vos premiers prospects",
          "Chapitre 3 — Ecrire un message qui obtient une reponse",
          "Chapitre 4 — Relancer sans harceler"]
    AUTRE = ["Etape 1 : pourquoi les clients manquent",
             "Etape 2 : trouver ses premiers prospects",
             "Etape 3 : ecrire le message qui obtient une reponse",
             "Etape 4 : relancer sans harceler"]
    AILLEURS = ["Chapitre 1 — Choisir ses semences",
                "Chapitre 2 — Preparer la terre du balcon",
                "Chapitre 3 — Arroser selon la saison"]

    def test_deux_charpentes_equivalentes_se_reconnaissent(self):
        self.assertGreaterEqual(
            empreinte.ressemblance_plan(empreinte.plan(self.UN),
                                        empreinte.plan(self.AUTRE)), 0.75)

    def test_deux_charpentes_differentes_ne_se_confondent_pas(self):
        self.assertLess(
            empreinte.ressemblance_plan(empreinte.plan(self.UN),
                                        empreinte.plan(self.AILLEURS)), 0.2)

    def test_le_meme_livre_sous_d_autres_mots_est_detecte(self):
        """Le cas frequent : plan identique, pas une phrase en commun."""
        texte_faible = empreinte.ressemblance(
            empreinte.signature(" ".join(self.UN)),
            empreinte.signature(" ".join(self.AUTRE)))
        voisins = empreinte.comparer(
            " ".join(self.UN), self.UN,
            [{"produit_id": "p1", "titre": "L'autre", "sujet": "x",
              "signature": empreinte.signature(" ".join(self.AUTRE)),
              "plan": empreinte.plan(self.AUTRE)}])
        self.assertLess(texte_faible, 0.30,
                        "le texte seul ne doit PAS suffire ici")
        self.assertTrue(voisins[0].doublon,
                        "le plan doit rattraper ce que le texte rate")
        self.assertEqual(voisins[0].motif, "plan")

    def test_un_livre_entierement_contenu_dans_un_autre(self):
        """Six chapitres inclus dans douze : c'est un doublon, pas une moitie."""
        court = empreinte.plan(self.UN[:2])
        long = empreinte.plan(self.UN + self.AILLEURS)
        self.assertEqual(empreinte.ressemblance_plan(court, long), 1.0)


class TestSujets(unittest.TestCase):

    def test_deux_intitules_de_meme_niche_se_recouvrent(self):
        self.assertGreaterEqual(empreinte.ressemblance_sujet(
            "La prospection pour freelances", "Prospection freelance"), 0.75)

    def test_deux_niches_distinctes_ne_se_recouvrent_pas(self):
        self.assertLess(empreinte.ressemblance_sujet(
            "La prospection pour freelances", "Le jardinage sur balcon"), 0.2)

    def test_les_mots_outils_ne_comptent_pas(self):
        """Sinon « le guide de la X » et « le guide de la Y » se ressembleraient."""
        self.assertLess(empreinte.ressemblance_sujet(
            "Le guide complet de la couture", "Le guide complet de la peche"), 0.4)


class TestChaine(unittest.TestCase):
    """Bout en bout : la chaine de fabrication pose et compare les empreintes."""

    def _contexte(self, dossier, sujet):
        from usine.pipelines.base import Contexte, preparer

        contexte = Contexte(sujet=sujet, journal=lambda m: None)
        preparer(contexte, "ebook", sujet)
        return contexte

    def test_un_second_produit_identique_est_signale(self):
        from usine.core import store
        from usine.pipelines import base

        journal = []
        dossier = Path(tempfile.mkdtemp())
        for tour in range(2):
            contexte = self._contexte(dossier, "la prospection tour {}".format(tour))
            contexte.journal = journal.append
            chemin = contexte.dossier / "livre.md"
            chemin.write_text("# Titre\n\n## Chapitre un\n\n" + TEXTE,
                              encoding="utf-8")
            base.terminer(contexte, [chemin], {}, type_produit="ebook")

        self.assertTrue(any("Deja fabrique" in ligne for ligne in journal),
                        "le second produit doit etre signale")
        self.assertEqual(len(store.lister_empreintes("ebook")) >= 2, True)

    def test_un_produit_etranger_ne_declenche_rien(self):
        from usine.pipelines import base

        journal = []
        contexte = self._contexte(Path(tempfile.mkdtemp()), "la photosynthese")
        contexte.journal = journal.append
        chemin = contexte.dossier / "livre.md"
        chemin.write_text("# Plantes\n\n## Les feuilles\n\n" + ETRANGER,
                          encoding="utf-8")
        base.terminer(contexte, [chemin], {}, type_produit="ebook")
        self.assertFalse(any("Deja fabrique" in ligne for ligne in journal))

    def test_deux_types_differents_ne_sont_pas_des_doublons(self):
        """Un ebook et un cahier sur le meme sujet sont complementaires."""
        from usine.pipelines import base

        journal = []
        for genre in ("formation", "impression"):
            contexte = self._contexte(Path(tempfile.mkdtemp()), "le meme sujet")
            contexte.journal = journal.append
            chemin = contexte.dossier / "notes.md"
            chemin.write_text("# T\n\n## S\n\n" + TEXTE, encoding="utf-8")
            base.terminer(contexte, [chemin], {}, type_produit=genre)
        self.assertFalse(any("Deja fabrique" in ligne for ligne in journal))


class TestFicheProduit(unittest.TestCase):
    """Le meta d'un produit arrive decode, ou la fonctionnalite se tait.

    Il etait rendu en JSON brut et chaque appelant le decodait de son cote.
    Le bilan de session, lui, s'est protege par un « isinstance(meta, dict) »
    toujours faux : le signalement des doublons en fin de lot n'a jamais
    affiche une ligne, sans qu'aucun test ne s'en apercoive.
    """

    def test_le_meta_est_un_dictionnaire(self):
        from usine.core import store

        store.creer_produit("m1", "ebook", "Titre", sujet="s", dossier="/tmp")
        store.maj_produit("m1", statut="pret",
                          meta={"doublon": {"motif": "plan"}, "mots": 12})
        fiche = store.lire_produit("m1")
        self.assertIsInstance(fiche["meta"], dict)
        self.assertEqual(fiche["meta"]["doublon"]["motif"], "plan")
        self.assertEqual(store.lister_produits(1)[0]["meta"]["mots"], 12)

    def test_un_meta_illisible_ne_fait_pas_tomber_la_lecture(self):
        from usine.core import store

        store.creer_produit("m2", "ebook", "Titre", sujet="s", dossier="/tmp")
        with store.cursor() as cur:
            cur.execute("UPDATE produits SET meta = ? WHERE id = ?",
                        ("{ceci n est pas du json", "m2"))
        self.assertEqual(store.lire_produit("m2")["meta"], {})


if __name__ == "__main__":
    unittest.main()
