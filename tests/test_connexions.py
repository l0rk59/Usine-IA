"""Les branchements que cet audit a rétablis restent branchés.

Trois choses étaient déclarées mais reliées à rien : deux agents (styliste,
contrôleur) qui n'entraient jamais en action, et le réglage « signature_ia »
que la licence ignorait. Ces tests échouent si l'une redevient orpheline.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import evenements, llm, reglages  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("connexions")
    llm.definir_simulateur(simulateur)


class TestAgentsRelies(unittest.TestCase):
    """Un agent affiché dans l'équipe doit réellement travailler.

    Les deux étaient déclarés, montrés dans l'interface et la scène 3D, mais
    aucune chaîne ne les appelait : leur pastille ne s'allumait jamais.
    """

    def _agents_allumes(self, qualite):
        from usine.pipelines import ebook
        from usine.pipelines.base import Contexte

        vus = set()
        origine = evenements.publier

        def espion(type_, **kw):
            if type_ == "agent" and kw.get("etat") == "debut":
                vus.add(kw.get("agent"))
            return origine(type_, **kw)

        evenements.publier = espion
        try:
            ctx = Contexte(sujet="la prospection pour freelances",
                           audience="freelances", qualite=qualite,
                           chapitres=2, mots_section=300, sans_image=True,
                           journal=lambda m: None)
            ebook.produire(ctx)
        finally:
            evenements.publier = origine
        return vus

    def test_le_controleur_s_allume_meme_en_qualite_rapide(self):
        """Le contrôle déterministe EST le travail du contrôleur."""
        self.assertIn("controleur", self._agents_allumes("rapide"))

    def test_le_styliste_s_allume_en_qualite_exigeante(self):
        """La passe de style finale n'existe qu'au niveau exigeant."""
        vus = self._agents_allumes("exigeant")
        self.assertIn("styliste", vus)
        self.assertIn("editeur", vus)     # la relecture éditoriale aussi

    def test_le_styliste_ne_tourne_pas_en_qualite_rapide(self):
        """Rapide = aucune relecture : le styliste doit rester au repos."""
        self.assertNotIn("styliste", self._agents_allumes("rapide"))

    def test_plus_aucun_agent_declare_n_est_orphelin(self):
        """Chaque agent de l'équipe doit être invocable par du code réel.

        On lit le code plutôt que de tout exécuter : un agent dont le nom
        n'apparaît qu'à sa déclaration est un agent mort.
        """
        from usine.agents import equipe

        sources = "\n".join(
            f.read_text(encoding="utf-8")
            for f in (RACINE / "usine").rglob("*.py"))
        for nom, agent in equipe.EQUIPE.items():
            variable = nom.upper()
            # Nombre d'occurrences de la CONSTANTE agent (ARCHITECTE, ...) :
            # au moins une hors de sa définition dans equipe.py.
            occurrences = sources.count(variable)
            with self.subTest(agent=nom):
                self.assertGreater(
                    occurrences, 2,
                    "l'agent {} n'est presque jamais reference".format(nom))


class TestSignatureIA(unittest.TestCase):
    """Le réglage « signature_ia » doit décider de la mention dans la licence."""

    def tearDown(self):
        reglages.reinitialiser()

    def _licence(self):
        from usine.packaging import livraison

        dossier = reglages.chemin().parent
        chemin = livraison.ecrire_licence(dossier, "Un produit", "Moi")
        return chemin.read_text(encoding="utf-8")

    def test_activee_la_mention_ia_est_dans_la_licence(self):
        reglages.ecrire({"signature_ia": True})
        self.assertIn("TRANSPARENCE", self._licence())

    def test_desactivee_la_mention_disparait(self):
        reglages.ecrire({"signature_ia": False})
        texte = self._licence()
        self.assertNotIn("TRANSPARENCE", texte)
        # Le reste de la licence tient toujours.
        self.assertIn("LICENCE D'UTILISATION", texte)


if __name__ == "__main__":
    unittest.main()
