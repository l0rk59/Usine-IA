"""Six chaines de fiction, deux agents, tous deux ecrits pour les guides.

La mesure d'ou part ce module. Les six chaines de fiction du depot —
nouvelle, roman, recueil, feuilleton, livre-jeu, conte — n'employaient que
DEUX agents sur treize : « architecte » et « redacteur ». Et pas des agents
neutres qu'on aurait pu reutiliser :

  l'architecte concoit « une structure qui mene le lecteur d'un probleme
  precis a un resultat verifiable », en « diagnostic, methode, mise en
  oeuvre, suivi », et sa derniere partie « dit quoi faire ensuite » ;

  le redacteur ecrit « comme on explique a un ami competent mais presse »,
  doit « ouvrir sur une situation que le lecteur reconnait, jamais sur une
  definition », et « donner des etapes numerotees executables aujourd'hui ».

C'est sous ces regles que l'usine ecrivait ses romans. Rien n'echouait : un
modele a qui l'on demande une scene en ecrit une, meme si sa personnalite lui
parle d'etapes numerotees. Le defaut sort a la lecture.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("agents-fiction")


from usine.agents import equipe  # noqa: E402
from usine.core import llm, prompts  # noqa: E402
from usine.pipelines import base  # noqa: E402
from tests import simulateur  # noqa: E402

CHAINES_DE_FICTION = ("nouvelle", "conte", "interactive", "recueil",
                      "feuilleton")
AGENTS_DE_GUIDE = ("ARCHITECTE", "REDACTEUR", "FORMATEUR", "OUTILLEUR")


def _agents_appeles(module: str):
    """Les agents qu'un module appelle REELLEMENT, lus dans l'arbre.

    Lire la structure et non le texte : « equipe.REDACTEUR » cite dans un
    commentaire ou dans une docstring d'explication ne serait pas un appel,
    et un detecteur satisfait par une homonymie ne garde rien — ce depot en
    a deja fait deux fois les frais.
    """
    arbre = ast.parse((RACINE / "usine" / "pipelines" / "{}.py".format(module))
                      .read_text(encoding="utf-8"))
    trouves = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Attribute):
            continue
        cible = noeud.value
        # « equipe.X.travailler(...) » : l'attribut cherche est le MILIEU.
        if isinstance(cible, ast.Attribute) and isinstance(cible.value, ast.Name) \
                and cible.value.id == "equipe" and cible.attr.isupper():
            trouves.add(cible.attr)
        elif isinstance(cible, ast.Name) and cible.id == "equipe" \
                and noeud.attr.isupper():
            trouves.add(noeud.attr)
    return trouves


class AucuneChaineDeFictionNAppelleUnAgentDeGuide(unittest.TestCase):

    def test_les_cinq_chaines_n_emploient_plus_l_architecte_ni_le_redacteur(self):
        fautives = {}
        for module in CHAINES_DE_FICTION:
            appeles = _agents_appeles(module)
            intrus = sorted(appeles & set(AGENTS_DE_GUIDE))
            if intrus:
                fautives[module] = intrus
        self.assertEqual(fautives, {}, (
            "Ces chaines de fiction appellent un agent ecrit pour le "
            "non-fictionnel : {}. Le redacteur doit « donner des etapes "
            "numerotees executables aujourd'hui ».".format(fautives)))

    def test_chaque_chaine_de_fiction_appelle_au_moins_un_agent_de_fiction(self):
        fiction = {"SCENARISTE", "ROMANCIER", "CONTEUR", "LECTEUR_DE_FICTION"}
        for module in CHAINES_DE_FICTION:
            with self.subTest(chaine=module):
                self.assertTrue(_agents_appeles(module) & fiction,
                                "{} n'appelle aucun agent de fiction".format(module))

    def test_le_temoin_verrait_le_defaut_revenir(self):
        """Le detecteur, applique a une chaine qui EST du non-fictionnel.

        Il appelle la meme fonction que le test, et non une copie : une
        campagne de mutation de ce depot a montre deux fois qu'un temoin qui
        recopie le calcul laisse neutraliser le vrai detecteur sans que
        personne ne bronche.
        """
        self.assertTrue(_agents_appeles("ebook") & set(AGENTS_DE_GUIDE))


class LesQuatreMetiersDeLaFictionSontDeclares(unittest.TestCase):

    NOMS = ("scenariste", "romancier", "conteur", "lecteur_de_fiction")

    def test_ils_existent_dans_le_registre_de_prompts(self):
        for nom in self.NOMS:
            self.assertIn(nom, prompts.AGENTS_DEFAUT, nom)
            self.assertIn(nom, equipe.EQUIPE, nom)

    def test_le_conteur_autorise_la_repetition_que_le_romancier_interdit(self):
        """Une contradiction VOULUE, et c'est pourquoi ce sont deux agents.

        Un album se construit sur le retour d'une formule, que l'enfant
        attend et finit par dire avec l'adulte. Donner au conte les regles
        d'un romancier lui interdirait son procede principal.
        """
        conteur = " ".join(prompts.AGENTS_DEFAUT["conteur"]["regles"]).lower()
        self.assertIn("repetition est un outil", conteur)

    def test_le_romancier_reprend_ce_que_les_releves_de_prose_comptent(self):
        """Les deux moities doivent dire la meme chose.

        Le depot a deja paye la contradiction inverse : le redacteur demandait
        « un exemple ou un chiffre illustratif » pendant que le controle
        deterministe signalait tout chiffre sans marqueur de source, et la
        boucle de correction payait la difference a chaque chapitre.
        """
        regles = " ".join(prompts.AGENTS_DEFAUT["romancier"]["regles"]).lower()
        self.assertIn("montrer, ne pas dire", regles)     # emotions_nommees
        self.assertIn("conscience entre la scene", regles)  # mots_filtres
        self.assertIn("dit", regles)                      # incises
        self.assertIn("adverbe", regles)                  # mots_en_ment

    def test_chaque_agent_de_fiction_porte_un_signe_libre(self):
        """Le journal du tableau de bord ne montre que ce signe."""
        signes = [f["emoji"] for f in prompts.AGENTS_DEFAUT.values()]
        self.assertEqual(len(signes), len(set(signes)))


class LeLecteurDeFictionNePosePasLesQuestionsDUnGuide(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    SECTIONS = [("Scene 1", "Camille poussa la porte du depot." * 12),
                ("Scene 2", "Hakim l'attendait pres du quai deux." * 12)]

    def test_la_lecture_rend_ce_qu_un_lecteur_de_roman_repond(self):
        lecture = equipe.lire_comme_un_lecteur_de_fiction(
            base.Contexte(sujet="un depot ferroviaire",
                          journal=lambda m: None),
            self.SECTIONS, "une releve qui tourne mal")
        self.assertTrue(lecture["disponible"])
        self.assertTrue(lecture["decrochages"])
        self.assertEqual(lecture["personnages_confondus"], ["Camille et Lucie"])
        self.assertIn("scene 2", lecture["fin_devinee"])
        self.assertTrue(lecture["promesses_non_payees"])

    def test_elle_ne_demande_pas_ce_qu_on_saura_faire_apres_avoir_lu(self):
        """La question de « lire_comme_l_audience », inutile sur un roman.

        Un roman ne promet aucun savoir-faire, et un lecteur de fiction ne
        decroche pas sur un sigle non explique.
        """
        recues = []
        origine = equipe.LECTEUR_DE_FICTION.travailler_json

        def espion(contexte, invite, **kwargs):
            recues.append(invite)
            return origine(contexte, invite, **kwargs)

        equipe.LECTEUR_DE_FICTION.travailler_json = espion
        try:
            equipe.lire_comme_un_lecteur_de_fiction(
                base.Contexte(sujet="un depot", journal=lambda m: None),
                self.SECTIONS, "une releve")
        finally:
            equipe.LECTEUR_DE_FICTION.travailler_json = origine
        invite = recues[0].lower()
        self.assertNotIn("sauras toujours pas faire", invite)
        self.assertNotIn("sigle", invite)
        self.assertIn("cesse d'y croire", invite)
        self.assertIn("devine la fin", invite)

    def test_un_texte_trop_court_ne_paie_pas_un_appel_de_modele(self):
        self.assertEqual(equipe.lire_comme_un_lecteur_de_fiction(
            base.Contexte(sujet="x", journal=lambda m: None),
            [("Scene 1", "Une seule scene.")]), {})

    def test_la_chaine_nouvelle_range_la_lecture_dans_son_rapport(self):
        from usine.pipelines import nouvelle

        ctx = base.Contexte(sujet="un phare et sa releve", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres = 4
        resume = nouvelle.produire(ctx)
        lecture = resume["qualite"].get("lecteur") or {}
        self.assertTrue(lecture.get("disponible"), lecture)
        self.assertTrue(lecture["decrochages"])


if __name__ == "__main__":
    unittest.main()
