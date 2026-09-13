"""L'equipe : qui existe, qui est appele, et qui se contredit.

Trois mesures ont ouvert ce sujet, le 13/09/2026.

**Cinq chaines sur dix n'avaient aucune equipe.** La formation, les
publications, les packs de prompts, les boites a outils et l'etude de niche
appelaient le modele directement, avec une personnalite ecrite en dur dans
chaque fichier. Elles y perdaient quatre choses, toutes invisibles : aucune
regle de metier, aucune relecture croisee — le meme modele ecrivait et se
relisait —, aucun evenement « agent », donc un panneau eteint dans le tableau
de bord pour la moitie du catalogue, et surtout aucun signalement de reponse
tronquee, qui est pourtant « le defaut le plus couteux du routeur ».

**Personne ne lisait le produit comme son acheteur.** Tous les controles
jugent le TEXTE. Un chapitre techniquement excellent et incomprehensible pour
son public est un chapitre rate, et rien ne le signalait.

**Deux moities de l'usine se contredisaient.** Le redacteur avait pour regle
« toute affirmation est suivie d'un exemple ou d'un chiffre illustratif », et
le controle deterministe signale precisement tout chiffre dont la phrase ne
porte aucun marqueur de source. La boucle de correction payait la difference a
chaque chapitre.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402
from usine import cli  # noqa: E402
from usine.agents import equipe  # noqa: E402
from usine.core import controle, evenements, llm, prompts  # noqa: E402


def setUpModule():
    atelier.isoler("equipe")


def _fabriquer(argv):
    """Lance une chaine et rend les agents que l'usine a REELLEMENT allumes."""
    vus = set()
    vrai = evenements.publier

    def espion(genre, **kw):
        if genre == "agent" and kw.get("etat") == "debut":
            vus.add(kw.get("agent"))
        return vrai(genre, **kw)

    evenements.publier = espion
    llm.definir_simulateur(simulateur)
    sortie = io.StringIO()
    try:
        with redirect_stdout(sortie), redirect_stderr(sortie):
            cli.principal(argv)
    finally:
        evenements.publier = vrai
        llm.definir_simulateur(None)
    return vus, sortie.getvalue()


class ChaqueChaineAUneEquipe(unittest.TestCase):
    """Le defaut se voyait dans le tableau de bord : panneau eteint.

    On mesure par les EVENEMENTS, pas en lisant le code : un agent importe et
    jamais appele publierait quand meme son nom dans une recherche de texte.
    """

    CHAINES = {
        "formation": "formateur",
        "social": "animateur",
        "prompts": "bibliothecaire",
        "outils": "outilleur",
        "idees": "prospecteur",
    }

    def setUp(self):
        atelier.isoler("equipe-{}".format(self.id().rsplit(".", 1)[-1]))

    def test_les_cinq_chaines_orphelines_ont_leur_agent(self):
        for commande, agent in sorted(self.CHAINES.items()):
            with self.subTest(chaine=commande):
                atelier.isoler("equipe-chaine-" + commande)
                vus, _ = _fabriquer([commande, "la facturation des independants",
                                     "--sans-image"])
                self.assertIn(agent, vus,
                              "la chaine « {} » n'allume aucun agent"
                              .format(commande))

    def test_plus_aucun_appel_ne_contourne_l_equipe(self):
        """Un appel direct au routeur perd la troncature, la relecture croisee
        et l'evenement. Le brief est la seule exception nommee : il tourne
        AVANT qu'un contexte de fabrication existe.
        """
        import re

        coupables = []
        for chemin in (RACINE / "usine").rglob("*.py"):
            if chemin.name in ("llm.py", "base.py", "brief.py"):
                continue
            texte = chemin.read_text(encoding="utf-8")
            if re.search(r"\bllm\.generer(_json)?\(", texte):
                coupables.append(str(chemin.relative_to(RACINE)))
        self.assertEqual(coupables, [],
                         "ces chaines appellent le routeur sans passer par un "
                         "agent : ni troncature signalee, ni relecture croisee")


class LesAgentsEtLeControleNeSeContredisentPas(unittest.TestCase):
    """Deux moities de l'usine qui se contredisent coutent a chaque chapitre.

    Le redacteur reclamait un chiffre illustratif ; le controle signale tout
    chiffre sans marqueur de source. Le texte sortait fautif, le controle le
    voyait, le reviseur le corrigeait — trois appels pour une instruction mal
    ecrite.
    """

    @staticmethod
    def _prescriptions(fiche):
        """Le texte d'une fiche, SANS ce qu'elle cite entre guillemets.

        Le styliste a pour regle de supprimer « en conclusion » : il cite le
        tic pour l'interdire. Un detecteur qui compte cette citation comme une
        prescription accuserait la seule fiche qui fait exactement ce qu'il
        faut — et un garde-fou qui crie a tort finit ignore.
        """
        import re

        texte = " ".join([fiche.get("metier", ""), fiche.get("mission", "")]
                         + list(fiche.get("regles", [])))
        return re.sub(r"«[^»]*»", " ", texte)

    def test_aucune_fiche_ne_prescrit_un_tic_que_le_controle_penalise(self):
        for nom, fiche in prompts.AGENTS_DEFAUT.items():
            texte = controle._sans_accent(self._prescriptions(fiche))
            for motif in controle._COMPILES_TICS:
                with self.subTest(agent=nom, tic=motif.pattern):
                    self.assertIsNone(motif.search(texte))

    def test_le_detecteur_verrait_une_fiche_fautive(self):
        """Sans ce cas, le controle ci-dessus pourrait passer parce qu'il ne
        trouve jamais rien, et non parce qu'il n'y a rien a trouver."""
        fautive = {"metier": "x", "mission": "y",
                   "regles": ["Terminer chaque section par en conclusion."]}
        texte = controle._sans_accent(self._prescriptions(fautive))
        self.assertTrue(any(m.search(texte) for m in controle._COMPILES_TICS))

    def test_le_detecteur_laisse_tranquille_une_fiche_qui_cite_le_tic(self):
        """Le styliste a pour metier de les retirer : il doit pouvoir les nommer."""
        citante = {"metier": "x", "mission": "y",
                   "regles": ["Supprimer les transitions mecaniques "
                              "(« en conclusion », « par ailleurs »)."]}
        texte = controle._sans_accent(self._prescriptions(citante))
        self.assertFalse(any(m.search(texte) for m in controle._COMPILES_TICS))

    def test_le_redacteur_nomme_les_marqueurs_que_le_controle_accepte(self):
        """Lui demander « un chiffre illustratif » sans dire comment le marquer
        garantit que le controle le refusera."""
        regles = " ".join(prompts.AGENTS_DEFAUT["redacteur"]["regles"]).lower()
        self.assertIn("chiffre", regles)
        marques = [m for m in ("par exemple", "imaginons", "supposons", "selon")
                   if m in regles]
        self.assertTrue(marques, "aucun marqueur de source nomme au redacteur")
        for marque in marques:
            with self.subTest(marqueur=marque):
                self.assertTrue(controle.MARQUEUR_SOURCE.search(marque),
                                "le redacteur cite un marqueur que le controle "
                                "ne reconnait pas")


class ChaqueAgentEstUtilise(unittest.TestCase):
    """Un agent declare et jamais appele est un mensonge de plus dans une
    interface qui affiche « l'equipe »."""

    def test_tous_les_agents_de_l_equipe_ont_un_appelant(self):
        import re

        sources = "\n".join(
            chemin.read_text(encoding="utf-8")
            for chemin in (RACINE / "usine").rglob("*.py")
            if chemin.name != "prompts.py")
        for nom, agent in sorted(equipe.EQUIPE.items()):
            constante = nom.upper()
            with self.subTest(agent=nom):
                appels = re.findall(
                    r"\b{}\.(travailler|travailler_json)\(".format(constante),
                    sources)
                self.assertTrue(appels,
                                "l'agent « {} » n'est appele nulle part"
                                .format(nom))

    def test_chaque_agent_a_un_emoji_distinct(self):
        """Le journal du tableau de bord ne montre que ce signe : deux agents
        qui le partagent sont indiscernables pendant une fabrication."""
        signes = [f["emoji"] for f in prompts.AGENTS_DEFAUT.values()]
        self.assertEqual(len(signes), len(set(signes)))

    def test_chaque_agent_a_un_role_de_modele_connu(self):
        """Un role invente se resout en silence sur « standard » : le modele
        special qu'on croyait avoir choisi n'est jamais appele."""
        from usine.core import config

        connus = {r for f in config.PROVIDERS for r in f.models}
        for nom, fiche in prompts.AGENTS_DEFAUT.items():
            with self.subTest(agent=nom):
                self.assertIn(fiche["role_modele"], connus)


class LeLecteur(unittest.TestCase):
    """La seule voix qui ne juge pas le metier."""

    def setUp(self):
        atelier.isoler("equipe-lecteur")

    def test_il_lit_le_produit_entier_et_dit_ce_qu_il_n_a_pas_compris(self):
        vus, texte = _fabriquer(["ebook", "la facturation", "--chapitres", "3",
                                 "--sans-image", "--relecture-ensemble"])
        self.assertIn("lecteur", vus)
        self.assertIn("clarte", texte)
        self.assertIn("jamais expliques", texte)

    def test_il_ne_tourne_pas_sans_relecture_d_ensemble(self):
        """Un appel par produit sur le texte entier : la chaine le demande,
        il ne s'impose pas."""
        atelier.isoler("equipe-lecteur-sans")
        vus, _ = _fabriquer(["ebook", "la facturation", "--chapitres", "3",
                             "--sans-image"])
        self.assertNotIn("lecteur", vus)

    def test_une_section_seule_ne_se_lit_pas(self):
        """Ce qu'il cherche — un sigle explique trop tard, une promesse non
        tenue — n'est visible qu'a la lecture complete."""
        from usine.pipelines.base import Contexte

        ctx = Contexte(sujet="x", journal=lambda _m: None)
        self.assertEqual(
            equipe.lire_comme_l_audience(ctx, [("Titre", "Un texte.")]), {})


if __name__ == "__main__":
    unittest.main()
