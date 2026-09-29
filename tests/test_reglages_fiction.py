"""Un album jeunesse portait les reglages d'une romance adulte.

Ce que la mesure du 15/09/2026 a trouve dans le tableau de bord. Les six
types de fiction — nouvelle, roman, recueil, feuilleton, livre-jeu, conte —
declaraient les MEMES dix reglages. Le conte proposait donc :

    Niveau de chaleur : sans romance | tendre | porte fermee |
                        sensuelle | EXPLICITE

sur un album pour trois a cinq ans. Et ce n'etait pas un champ inerte : la
valeur choisie partait reellement dans l'invite qui ecrit l'album, via
« fiction.consignes » —

    NIVEAU DE CHALEUR : explicite
    Les scenes d'intimite sont detaillees. [...]

S'y ajoutaient les tropes de romance (« ennemis puis amants »), un point de
vue de roman, un temps du recit, une charpente en voyage du heros sur
quatorze doubles-pages, et une serie.

La cause n'est pas une etourderie sur un champ. Le partage d'une liste
unique a un bon argument — il evite qu'un type ajoute plus tard oublie la
moitie des reglages — et cet argument vaut entre un roman et un feuilleton.
Il ne vaut pas entre un roman et un album illustre : ce sont deux objets, pas
deux longueurs du meme objet.

Second defaut du meme panneau : les suggestions etaient en ANGLAIS dans une
interface francaise — « chapter books, clean & wholesome romance, coming of
age, cozy mystery, dark romance, dystopian, early readers... ».
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("reglages-fiction")


from usine.pipelines import base, catalogue, fiction  # noqa: E402

JEUNESSE = ("conte",)


def _type(cle):
    for produit in catalogue.TYPES:
        if produit.cle == cle:
            return produit
    raise AssertionError("type inconnu : " + cle)


def _champs(cle):
    return {c.nom for c in _type(cle).champs}


class UnAlbumNePorteAucunReglageDAdulte(unittest.TestCase):

    def test_le_conte_ne_propose_plus_de_niveau_de_chaleur(self):
        self.assertNotIn("chaleur", _champs("conte"))

    def test_le_conte_ne_propose_aucun_reglage_sans_objet_pour_lui(self):
        interdits = _champs("conte") & set(catalogue.SANS_OBJET_EN_JEUNESSE)
        self.assertEqual(interdits, set(), (
            "un album jeunesse declare des reglages de fiction adulte : "
            "{}".format(sorted(interdits))))

    def test_la_ligne_de_commande_suit_le_catalogue(self):
        """Le catalogue est la source unique : ce qu'il retire disparait de
        la CLI, du menu et du tableau de bord sans qu'on y touche."""
        drapeaux = {c.drapeau for c in _type("conte").champs}
        self.assertNotIn("--chaleur", drapeaux)
        self.assertNotIn("--tropes", drapeaux)

    def test_l_album_garde_ce_qui_le_regle_vraiment(self):
        garde = _champs("conte")
        self.assertIn("tranche", garde)
        self.assertIn("ambiance", garde)
        self.assertIn("sous_genre", garde)

    def test_seuls_les_sous_genres_jeunesse_sont_suggeres(self):
        aide = next(c.aide for c in _type("conte").champs
                    if c.nom == "sous_genre")
        for adulte in ("dark romance", "romance contemporaine", "polar noir",
                       "horreur occulte"):
            self.assertNotIn(adulte, aide, adulte)
        self.assertIn("album illustré", aide)

    def test_les_types_de_fiction_adulte_gardent_leurs_reglages(self):
        # La correction retire des champs a UN type. Les retirer a tous
        # serait la deuxieme facon de se tromper.
        for cle in ("nouvelle", "roman", "recueil", "feuilleton",
                    "interactive"):
            with self.subTest(type=cle):
                for champ in catalogue.SANS_OBJET_EN_JEUNESSE:
                    if (champ == "serie"
                            and cle not in catalogue.TYPES_A_TOMES):
                        continue   # voir « TYPES_A_TOMES »
                    self.assertIn(champ, _champs(cle))


class LaChaleurNArrivePlusDansUneInviteDAlbum(unittest.TestCase):
    """Le champ retire ne suffit pas : c'est l'invite qu'il faut mesurer."""

    def test_l_invite_d_un_conte_ne_porte_pas_de_consigne_d_intimite(self):
        contexte = base.Contexte(sujet="un ourson qui perd son doudou",
                                 journal=lambda m: None)
        # On pose la promesse par le chemin REEL, avec les seuls reglages
        # qu'un conte peut encore porter.
        fiction.poser_la_promesse(contexte, {
            cle: "valeur" for cle in _champs("conte") if cle in fiction.CLES})
        consignes = fiction.consignes(contexte)
        for interdit in ("CHALEUR", "intimite", "TROPES"):
            self.assertNotIn(interdit, consignes, interdit)

    def test_le_temoin_montre_que_la_mesure_sait_voir_la_consigne(self):
        """Sans ce temoin, le test precedent passerait meme si « consignes »
        ne rendait plus jamais rien."""
        contexte = base.Contexte(sujet="deux rivaux", journal=lambda m: None)
        fiction.poser_la_promesse(contexte, {"chaleur": "explicite"})
        self.assertIn("CHALEUR", fiction.consignes(contexte))


class LesReglagesDeFictionSontEnFrancais(unittest.TestCase):
    """« Tout est en francais », y compris ce qui s'affiche."""

    ANGLAIS = ("chapter books", "early readers", "cozy mystery",
               "coming of age", "dystopian", "clean & wholesome",
               "enemies to lovers", "slow burn", "picture books",
               "middle grade", "epic fantasy", "hard-boiled")

    def test_aucune_suggestion_de_sous_genre_n_est_en_anglais(self):
        for produit in catalogue.TYPES:
            if produit.famille != "fiction":
                continue
            for champ in produit.champs:
                texte = " ".join([champ.aide or ""] + list(champ.choix or ()))
                for mot in self.ANGLAIS:
                    with self.subTest(type=produit.cle, terme=mot):
                        self.assertNotIn(mot, texte.lower())

    def test_les_tropes_proposes_sont_en_francais(self):
        tropes = fiction.tropes_du_genre("romance")
        self.assertIn("ennemis puis amants", tropes)
        self.assertNotIn("enemies to lovers", tropes)

    def test_un_libelle_francais_retrouve_le_releve_du_marche(self):
        """Sans le chemin inverse, le reglage serait affiche, choisi, et sans
        effet : les longueurs attendues sont rangees sous le terme source."""
        self.assertEqual(fiction.mots_attendus("romance contemporaine"),
                         fiction.mots_attendus("contemporary romance"))
        self.assertNotEqual(fiction.mots_attendus("romance contemporaine"),
                            (0, 0))

    def test_le_libelle_accentue_et_la_saisie_sans_accent_se_rejoignent(self):
        """Le libelle s'affiche « fantasy épique » ; au clavier d'un
        telephone on tape souvent « fantasy epique ». Les deux doivent
        retrouver le releve, sinon le reglage est choisi et sans effet."""
        self.assertEqual(fiction.libelle("epic fantasy"), "fantasy épique")
        for saisie in ("fantasy épique", "fantasy epique", "Fantasy Épique"):
            with self.subTest(saisie=saisie):
                self.assertEqual(fiction.terme_source(saisie), "epic fantasy")
        self.assertNotEqual(fiction.mots_attendus("fantasy epique"), (0, 0))

    def test_un_terme_inconnu_ressort_intact(self):
        # Ces listes proposent, elles n'interdisent pas : un sous-genre
        # saisi a la main doit ressortir tel quel, pas efface.
        self.assertEqual(fiction.libelle("polar solarpunk"), "polar solarpunk")

    def test_les_termes_que_le_marche_francophone_emploie_restent(self):
        # Les traduire inventerait un vocabulaire que personne ne tape dans
        # une barre de recherche.
        for terme in ("dark romance", "space opera", "steampunk", "thriller"):
            self.assertEqual(fiction.libelle(terme), terme)


if __name__ == "__main__":
    unittest.main()
