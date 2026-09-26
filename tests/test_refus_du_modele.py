"""Le modele qui refuse la demande, et le texte qu'on vendait a sa place.

Mesure du 24/09/2026, un ebook dont un modele refuse le chapitre 2 :
« Je suis desole, mais je ne peux pas vous aider a rediger ce contenu. »
etait imprime a la place du chapitre, et le produit marque « pret ». Rien
n'echouait : HTTP 200, une reponse non vide, un chapitre de plus.

Ces tests passent par le VRAI routeur — « generer », « _appel » — avec deux
faux fournisseurs dont le contenu vient du simulateur. Le simulateur seul ne
suffirait pas : il court-circuite « _appel », la ou la reponse est lue.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine.core import cles as pool_cles  # noqa: E402
from usine.core import llm, store, texte  # noqa: E402

REFUS = "Je suis desole, mais je ne peux pas vous aider a rediger ce contenu."
REFUS_ANGLAIS = "I'm sorry, but I can't help with that request."


def setUpModule():
    atelier.isoler("refus-du-modele")


class LeDetecteur(unittest.TestCase):
    """Deux signaux, tous deux necessaires, dans une reponse courte : elle
    s'ouvre sur un refus, et elle nomme ce qu'elle refuse."""

    REFUSES = (
        REFUS, REFUS_ANGLAIS,
        "I’m sorry, but I can’t assist with this.",
        "As an AI, I cannot write explicit content.",
        "Désolé, je ne peux pas écrire ce type de contenu.",
    )
    PAS_DES_REFUS = (
        # Une replique : elle s'ouvre sur un guillemet ou un tiret.
        '"I\'m sorry, but I can\'t stay," Mara said. The ferry left without '
        'her, and this request was her last.',
        "— Desole, je ne peux pas rester, dit Camille. Elle partit avant "
        "votre demande.",
        # Des textes qui commencent comme un refus sans en etre un.
        "I can't believe how many freelancers undercharge. Here is how to "
        "fix it.",
        "Je ne peux pas vous dire combien de devis j'ai vus trop bas.",
        "Sorry to interrupt your week: here are three ways to raise prices.",
        # Un refus noye dans un long texte n'est plus un refus.
        REFUS + " " + "Voici neanmoins le chapitre complet. " * 30,
    )

    def test_les_refus_sont_reconnus(self):
        for contenu in self.REFUSES:
            with self.subTest(contenu=contenu[:40]):
                self.assertTrue(texte.refus_du_modele(contenu))

    def test_rien_d_autre(self):
        for contenu in self.PAS_DES_REFUS:
            with self.subTest(contenu=contenu[:40]):
                self.assertEqual(texte.refus_du_modele(contenu), "")

    def test_aucune_fausse_alerte_sur_un_livre_fabrique(self):
        """Le meme critere que pour les messages de service : zero accusation
        sur tout ce que la suite fabrique, paragraphe par paragraphe."""
        from usine import cli
        from usine.core import config

        llm.definir_simulateur(simulateur)
        try:
            with redirect_stdout(io.StringIO()):
                cli.principal(["nouvelle", "le phare des excuses",
                               "--sans-image", "-q", "rapide"])
                cli.principal(["ebook", "dire non a un client",
                               "--sans-image", "-q", "rapide",
                               "--chapitres", "4"])
        finally:
            llm.definir_simulateur(None)
        blocs = [bloc for f in config.PRODUITS_DIR.rglob("*.md")
                 for bloc in f.read_text(encoding="utf-8").split("\n\n")]
        self.assertGreater(len(blocs), 50)
        for bloc in blocs:
            self.assertEqual(texte.refus_du_modele(bloc), "",
                             "accuse a tort : " + bloc[:80])


class _DeuxFournisseurs(unittest.TestCase):
    """Deux faux fournisseurs, groq puis cerebras, dont le contenu vient du
    simulateur — sauf quand « refuse » dit qu'un modele decline."""

    def setUp(self):
        self.refuse = lambda fournisseur, invite: False
        self.vus = []
        anciens = {k: os.environ.get(k) for k in (
            "GROQ_API_KEY", "CEREBRAS_API_KEY", "USINE_PROVIDERS")}
        self.addCleanup(self._restaurer, anciens)
        os.environ.update(GROQ_API_KEY="gsk_" + "A" * 32,
                          CEREBRAS_API_KEY="csk-" + "B" * 32,
                          USINE_PROVIDERS="groq,cerebras")
        pool_cles.oublier()
        llm._REPOS.clear()
        store.cache_vider()
        for nom, valeur in (("post_json", self._post),
                            ("_quota_ok", lambda *a, **k: True),
                            ("_laisser_passer", lambda *a, **k: True),
                            ("_patienter", lambda *a, **k: None)):
            rustine = mock.patch.object(llm, nom, valeur)
            rustine.start()
            self.addCleanup(rustine.stop)

    @staticmethod
    def _restaurer(anciens):
        for cle, valeur in anciens.items():
            if valeur is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = valeur
        pool_cles.oublier()
        llm._REPOS.clear()

    def _post(self, url, charge, entetes=None, timeout=120):
        fournisseur = "groq" if "groq" in url else "cerebras"
        invite = charge["messages"][-1]["content"]
        self.vus.append(fournisseur)
        if self.refuse(fournisseur, invite):
            contenu = REFUS
        else:
            contenu = simulateur(charge["messages"], "standard")
        return {"choices": [{"message": {"content": contenu},
                             "finish_reason": "stop"}],
                "usage": {"total_tokens": 100}}


class LeRouteur(_DeuxFournisseurs):

    def test_un_refus_passe_au_modele_suivant(self):
        self.refuse = lambda fournisseur, invite: fournisseur == "groq"
        rep = llm.generer("Ecris le chapitre sur la cuisson.", cache=False)
        self.assertEqual(rep.fournisseur, "cerebras")
        self.assertNotIn("desole", rep.texte.lower())

    def test_tous_refusent_n_est_pas_un_silence(self):
        """Attendre les quotas n'y changerait rien : c'est la demande qui est
        declinee. Une erreur ordinaire, que la section et la niche comptent."""
        self.refuse = lambda fournisseur, invite: True
        with self.assertRaises(llm.DemandeRefusee) as leve:
            llm.generer("Ecris la scene interdite.", cache=False)
        self.assertNotIsInstance(leve.exception, llm.PlusDeFournisseur)
        self.assertIn("refusé", str(leve.exception))

    def test_un_fournisseur_absent_laisse_le_doute(self):
        """Cerebras au repos n'a rien dit : il aurait peut-etre accepte. Le
        routeur ne tranche pas a sa place — c'est un silence, on attend."""
        self.refuse = lambda fournisseur, invite: True
        llm._reposer("cerebras", 3600, "essai")
        with self.assertRaises(llm.PlusDeFournisseur):
            llm.generer("Ecris la scene interdite.", cache=False)

    def test_un_refus_n_entre_pas_au_cache(self):
        self.refuse = lambda fournisseur, invite: fournisseur == "groq"
        llm.generer("Ecris le chapitre sur le repos.")
        self.refuse = lambda fournisseur, invite: False
        rep = llm.generer("Ecris le chapitre sur le repos.")
        self.assertNotIn("desole", rep.texte.lower())


class UnLivreDontUnChapitreEstRefuse(_DeuxFournisseurs):
    """De bout en bout : le refus n'est plus vendu comme un chapitre."""

    def test_le_chapitre_manque_et_le_dit(self):
        from usine import cli

        # Tous les modeles refusent le chapitre 2, et seulement lui.
        self.refuse = lambda fournisseur, invite: (
            "CHAPITRE 2" in invite.upper() and "PLAN" not in invite.upper()[:40])
        with redirect_stdout(io.StringIO()):
            cli.principal(["ebook", "la gestion du temps des infirmieres",
                           "--sans-image", "-q", "rapide", "--chapitres", "4"])
        produit = store.lister_produits(1)[0]
        dossier = Path(produit["dossier"])
        livre = "\n".join(f.read_text(encoding="utf-8")
                          for f in dossier.glob("*.md"))
        self.assertNotIn(REFUS[:30], livre)
        self.assertEqual(produit["statut"], "en_cours",
                         "un livre avec un chapitre manquant n'est pas pret")


class UneReecritureRefuseeGardeLeTexte(unittest.TestCase):
    """Corriger un chapitre qui existe ne doit pas le faire perdre."""

    def test_reviser_et_corriger(self):
        from usine.agents import equipe
        from usine.agents.base import Critique
        from usine.core import controle
        from usine.pipelines.base import Contexte

        texte_original = "Un chapitre deja ecrit. " * 40
        ctx = Contexte(sujet="x", journal=lambda _m: None)
        critique = Critique(note=5.0, problemes=[{
            "gravite": "majeur", "probleme": "p", "passage": "Un chapitre",
            "correction": "c"}])
        rapport = controle.controler("87% des freelances echouent. " * 5, 400)
        with mock.patch.object(equipe.REVISEUR, "travailler",
                               side_effect=llm.DemandeRefusee("refus")):
            self.assertEqual(equipe.reviser(ctx, texte_original, critique, "t"),
                             texte_original)
            self.assertEqual(equipe.corriger_defauts(ctx, texte_original,
                                                     rapport, "t"),
                             texte_original)


if __name__ == "__main__":
    unittest.main()
