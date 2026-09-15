"""Un recueil, c'est sept histoires qui ne doivent pas etre la meme.

Fabriquer sept nouvelles et les agrafer ne fait pas un recueil : cela fait
sept nouvelles dans le meme fichier. Et c'est precisement la ou la fiction
generee est la plus faible — personnages archetypaux, resolutions trop nettes.
Sur une nouvelle isolee cela passe ; sur sept d'affilee, le lecteur reconnait
la meme histoire a la troisieme et repose le livre.

Ce que ce module garde, c'est la mesure de l'ECART entre les recits. Elle est
deterministe — elle compare des chaines et compte des mots — et elle ne juge
jamais la qualite d'un texte : « ce recit est banal » n'est pas verifiable,
« deux recits portent le meme protagoniste » l'est.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("recueil")


from usine.core import llm, store  # noqa: E402
from usine.pipelines import base, recueil  # noqa: E402
from tests import simulateur  # noqa: E402


class DeuxPremissesJumellesSeVoientAvantDEcrire(unittest.TestCase):
    """Detectee ici, une premisse jumelle coute un appel a corriger.
    Detectee a la lecture, elle coute le recueil."""

    def test_deux_premisses_tres_proches_sont_signalees(self):
        doubles = recueil.premisses_jumelles([
            {"titre": "A", "premisse": "Un pecheur perd son bateau",
             "qui": "un pecheur"},
            {"titre": "B", "premisse": "Un pecheur perd son bateau",
             "qui": "un pecheur"},
            {"titre": "C", "premisse": "Une archiviste brule des registres",
             "qui": "une archiviste"},
        ])
        self.assertEqual([(g, d) for g, d, _s in doubles], [(0, 1)])

    def test_des_premisses_distinctes_ne_declenchent_rien(self):
        self.assertEqual(recueil.premisses_jumelles([
            {"titre": "A", "premisse": "Un cheminot cache une lettre",
             "qui": "un cheminot"},
            {"titre": "B", "premisse": "Une archiviste brule des registres",
             "qui": "une archiviste"},
        ]), [])

    def test_le_controle_compare_les_premisses_et_non_les_titres(self):
        """Deux titres peuvent differer entierement et couvrir la meme
        histoire — c'est meme le cas le plus frequent : un modele varie le
        vocabulaire bien avant de varier le fond."""
        doubles = recueil.premisses_jumelles([
            {"titre": "Le quai numero deux",
             "premisse": "Un cheminot cache une lettre a sa fille",
             "qui": "un cheminot"},
            {"titre": "Ce que la mer rend",
             "premisse": "Un cheminot cache une lettre a sa fille",
             "qui": "un cheminot"},
        ])
        self.assertTrue(doubles)


class CeQuiPasseSousLeSeuilResteVisible(unittest.TestCase):
    """Le seuil est volontairement haut — rater un defaut plutot qu'en
    inventer un. Ce qui compense, c'est que la proximite maximale est rendue
    dans tous les cas, avec son chiffre."""

    JUMEAUX = [
        {"titre": "Le phare",
         "premisse": "Une libraire herite du phare de son pere et y trouve "
                     "une lettre", "qui": "une libraire"},
        {"titre": "La lettre",
         "premisse": "Une libraire recoit le phare de son pere et decouvre "
                     "une lettre", "qui": "une libraire"},
        {"titre": "La tempete",
         "premisse": "Un pecheur perd son bateau dans la tempete de janvier",
         "qui": "un pecheur"},
    ]

    def test_ce_couple_passe_le_seuil_et_c_est_assume(self):
        """Mesure du 15/09/2026 : deux fois la meme histoire, a 0,67."""
        self.assertEqual(recueil.premisses_jumelles(self.JUMEAUX), [])

    def test_mais_sa_proximite_est_rendue_avec_son_chiffre(self):
        proche = recueil.proximite_maximale(self.JUMEAUX)
        self.assertEqual(proche["couple"], (0, 1))
        self.assertGreater(proche["score"], 0.5)
        self.assertEqual(proche["titres"], ("Le phare", "La lettre"))

    def test_sans_couple_a_comparer_la_mesure_ne_ment_pas(self):
        self.assertEqual(recueil.proximite_maximale([])["score"], 0.0)


class LaVarieteSeMesureEtNeSeJugePas(unittest.TestCase):

    def test_les_protagonistes_repetes_sont_comptes(self):
        mesure = recueil.mesurer_la_variete([
            {"protagoniste": "Anne", "fin": "amere", "mots": 1200},
            {"protagoniste": "Anne", "fin": "heureuse", "mots": 1100},
            {"protagoniste": "Luc", "fin": "ouverte", "mots": 900},
        ])
        self.assertEqual(mesure["protagonistes_distincts"], 2)
        self.assertEqual(mesure["fins_distinctes"], 3)

    def test_deux_recits_sur_le_meme_personnage_sont_dits(self):
        lectures = recueil.lire_la_variete(recueil.mesurer_la_variete([
            {"protagoniste": "Anne", "fin": "amere", "mots": 1200},
            {"protagoniste": "Anne", "fin": "heureuse", "mots": 1100},
        ]))
        self.assertTrue(any("meme personnage" in l for l in lectures))

    def test_des_fins_toutes_identiques_sont_dites_sans_etre_condamnees(self):
        """Un recueil de Noel finit bien sept fois, et c'est un choix.
        L'usine n'a pas de quoi trancher — elle le signale, elle ne
        l'interdit pas."""
        lectures = recueil.lire_la_variete(recueil.mesurer_la_variete([
            {"protagoniste": "A", "fin": "heureuse", "mots": 1000},
            {"protagoniste": "B", "fin": "heureuse", "mots": 1000},
            {"protagoniste": "C", "fin": "heureuse", "mots": 1000},
        ]))
        self.assertTrue(any("meme facon" in l for l in lectures))
        for lecture in lectures:
            for verdict in ("mauvais", "rate", "a refaire", "trop"):
                self.assertNotIn(verdict, lecture.lower())

    def test_un_recueil_varie_ne_declenche_aucune_lecture(self):
        """Un controle qui signale a tort finit ignore."""
        self.assertEqual(recueil.lire_la_variete(recueil.mesurer_la_variete([
            {"protagoniste": "Anne", "fin": "amere", "mots": 1200},
            {"protagoniste": "Luc", "fin": "heureuse", "mots": 900},
            {"protagoniste": "Zoe", "fin": "ouverte", "mots": 1400},
        ])), [])

    def test_un_recit_seul_ne_declenche_rien(self):
        """Un recueil d'un texte n'a pas de variete a mesurer, et le dire
        serait un faux positif garanti."""
        self.assertEqual(recueil.lire_la_variete(recueil.mesurer_la_variete([
            {"protagoniste": "Anne", "fin": "amere", "mots": 1200}])), [])

    def test_l_ecart_de_longueur_se_compte(self):
        mesure = recueil.mesurer_la_variete([
            {"protagoniste": "A", "fin": "x", "mots": 2000},
            {"protagoniste": "B", "fin": "y", "mots": 1000}])
        self.assertEqual(mesure["ecart_de_longueur"], 0.5)


class LaChaineCompleteViaLeSimulateur(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _produire(self, combien, sujet="une ville du nord"):
        ctx = base.Contexte(sujet=sujet, sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = combien, 120
        return recueil.produire(ctx)

    def test_le_nombre_demande_fait_foi(self):
        """Un modele qui rend douze premisses quand on en demande trois
        ferait fabriquer douze recits — quatre fois le temps et le quota
        annonces, et l'utilisateur ne l'apprendrait qu'a la fin."""
        self.assertEqual(self._produire(3)["recits"], 3)

    def test_la_mesure_de_variete_est_livree_avec_le_recueil(self):
        import json

        resume = self._produire(3, sujet="un port de la Manche")
        donnees = json.loads((Path(resume["dossier"]) / "recueil.json")
                             .read_text(encoding="utf-8"))
        self.assertIn("variete", donnees)
        self.assertEqual(donnees["variete"]["recits"], 3)

    def test_chaque_recit_a_son_propre_texte(self):
        """Le contexte de chaque recit porte SA premisse, pas le sujet du
        recueil : sept bibles identiques donneraient sept fois la meme
        histoire, ce que toute cette chaine existe pour eviter."""
        import json

        resume = self._produire(3, sujet="une vallee des Alpes")
        donnees = json.loads((Path(resume["dossier"]) / "recueil.json")
                             .read_text(encoding="utf-8"))
        titres = {r["titre"] for r in donnees["recits"]}
        self.assertEqual(len(titres), 3)
        for recit in donnees["recits"]:
            self.assertTrue(recit["texte"].strip(), recit["titre"])


def _fil_json(titres, premisses=None, qui=None, fins=None):
    import json

    premisses = premisses or ["premisse de {}".format(t) for t in titres]
    qui = qui or ["personne {}".format(i) for i in range(len(titres))]
    fins = fins or ["amere", "heureuse", "ouverte", "tragique", "ironique"]
    return json.dumps({
        "titre": "Le recueil", "fil": "un fil",
        "recits": [{"titre": t, "premisse": premisses[i], "qui": qui[i],
                    "registre": "sobre", "fin": fins[i % len(fins)],
                    "place": str(i)}
                   for i, t in enumerate(titres)]}, ensure_ascii=False)


class CeQuiEstDemandeFaitFoi(unittest.TestCase):
    """Un modele qui rend douze premisses quand on en demande trois ferait
    fabriquer douze recits — quatre fois le temps et le quota annonces, et
    l'utilisateur ne l'apprendrait qu'a la fin.

    Une mutation a montre que ce plafond n'etait garde par rien : le
    simulateur rend exactement ce qu'on lui demande, donc le cas ou il en
    rend trop ne s'executait jamais.
    """

    def tearDown(self):
        llm.definir_simulateur(None)
        store.cache_vider()

    def test_un_modele_trop_genereux_est_ramene_a_la_demande(self):
        def trop(messages, role):
            invite = messages[-1]["content"]
            if '"premisse"' in invite and '"registre"' in invite:
                return _fil_json(["A", "B", "C", "D", "E", "F", "G"])
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(trop)
        ctx = base.Contexte(sujet="un modele trop genereux", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 120
        self.assertEqual(recueil.produire(ctx)["recits"], 3)


class ChaqueRecitPartDeSaProprePremisse(unittest.TestCase):
    """Sept bibles identiques donneraient sept fois la meme histoire — ce que
    toute cette chaine existe pour eviter. Le contexte de chaque recit doit
    donc porter SA premisse, pas le sujet du recueil."""

    def tearDown(self):
        llm.definir_simulateur(None)
        store.cache_vider()

    def test_la_bible_de_chaque_recit_recoit_sa_premisse(self):
        bibles = []

        def espion(messages, role):
            invite = messages[-1]["content"]
            if '"premisse"' in invite and '"registre"' in invite:
                return _fil_json(
                    ["Le quai", "La couturiere", "La mer"],
                    premisses=["un cheminot cache une lettre",
                               "une couturiere retrouve une robe",
                               "un adolescent trouve un carnet"])
            if '"personnages"' in invite and '"premisse"' in invite:
                bibles.append(invite)
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(espion)
        ctx = base.Contexte(sujet="une ville a trois recits", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 120
        recueil.produire(ctx)
        self.assertEqual(len(bibles), 3)
        for attendu in ("un cheminot cache une lettre",
                        "une couturiere retrouve une robe",
                        "un adolescent trouve un carnet"):
            self.assertTrue(any(attendu in b for b in bibles), attendu)


class LesJumellesDeclenchentUneReprise(unittest.TestCase):
    """Redemander « varie davantage » ne change rien. Dire « les recits 2 et
    5 racontent la meme chose » change ce point-la."""

    def tearDown(self):
        llm.definir_simulateur(None)
        store.cache_vider()

    def test_la_seconde_demande_nomme_les_couples(self):
        fils = []

        def deux_fils(messages, role):
            invite = messages[-1]["content"]
            if '"premisse"' in invite and '"registre"' in invite:
                fils.append(invite)
                if len(fils) == 1:
                    return _fil_json(
                        ["Le phare", "La lanterne", "La mer"],
                        premisses=["un pecheur perd son bateau",
                                   "un pecheur perd son bateau",
                                   "une archiviste brule des registres"],
                        qui=["un pecheur", "un pecheur", "une archiviste"])
                return _fil_json(
                    ["Le quai", "La couturiere", "La mer"],
                    premisses=["un cheminot cache une lettre",
                               "une couturiere retrouve une robe",
                               "un adolescent trouve un carnet"])
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(deux_fils)
        ctx = base.Contexte(sujet="une ville aux jumelles", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 120
        resume = recueil.produire(ctx)

        self.assertEqual(len(fils), 2, "le fil jumele n'a pas ete repris")
        self.assertIn("Le phare", fils[1])
        self.assertIn("La lanterne", fils[1])
        self.assertEqual(resume["premisses_jumelles"], [])

    def test_un_fil_deja_varie_ne_declenche_pas_de_reprise(self):
        """Redemander a un modele qui a bien repondu coute un appel pour
        rien — et sur un telephone, un appel est une minute."""
        fils = []

        def compter(messages, role):
            invite = messages[-1]["content"]
            if '"premisse"' in invite and '"registre"' in invite:
                fils.append(invite)
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(compter)
        ctx = base.Contexte(sujet="une ville deja variee", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 3, 120
        recueil.produire(ctx)
        self.assertEqual(len(fils), 1)
