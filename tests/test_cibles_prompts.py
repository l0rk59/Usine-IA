"""Un pack de prompts d'image n'est pas un pack de prompts de texte.

Mesure du 26/09/2026 : le pack ne savait ecrire que pour un assistant de
texte — « assigner un role, preciser le format de sortie » — et son mode
d'emploi disait de coller le texte « dans Claude ou ChatGPT ». Les packs de
prompts d'image (Midjourney, Stable Diffusion) forment un rayon a part des
places de marche ; ecrits comme des prompts de texte, ils ne produisent rien
d'utilisable, et l'acheteur ne le decouvre qu'en les essayant.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from tests import simulateur as sim  # noqa: E402
from usine.core import llm  # noqa: E402
from usine.pipelines import catalogue, pack_prompts  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402
from usine.render import libelles  # noqa: E402

INVITES: List[str] = []


def _espion(messages, role):
    INVITES.append(messages[-1]["content"])
    return sim.simulateur(messages, role)


def setUpModule():
    atelier.isoler("cibles-prompts")
    llm.definir_simulateur(_espion)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet: str, journal=None) -> Contexte:
    # Une audience par cas : elle entre dans la consigne systeme, donc dans
    # la cle du cache. Deux cas au meme plan simule liraient sinon le cache
    # l'un de l'autre, et l'espion ne verrait rien passer.
    return Contexte(sujet=sujet, audience="des acheteurs de " + sujet,
                    sans_image=True, journal=journal or (lambda _m: None))


def _textes_livres(resume) -> str:
    dossier = Path(resume["dossier"])
    return "\n".join(f.read_text(encoding="utf-8")
                     for f in sorted(dossier.glob("*.md")))


class LaCibleChangeLeProduit(unittest.TestCase):

    def test_un_pack_d_images_s_ecrit_pour_un_generateur_d_images(self):
        INVITES.clear()
        resume = catalogue.executer("prompts", _contexte("affiches vintage"),
                                    {"nombre": 6, "cible": "image"})
        redaction = [i for i in INVITES if i.startswith("Theme du pack")]
        self.assertTrue(redaction)
        for invite in redaction:
            self.assertIn(pack_prompts.CIBLES["image"]["prompt"], invite)
            self.assertNotIn("assigner un role", invite)
        livre = _textes_livres(resume)
        self.assertIn(libelles.FR["prompts_mode_emploi_image"], livre)
        self.assertNotIn(libelles.FR["prompts_mode_emploi"], livre)

    def test_un_pack_de_texte_garde_sa_consigne(self):
        INVITES.clear()
        resume = catalogue.executer("prompts", _contexte("relances clients"),
                                    {"nombre": 6, "cible": "texte"})
        redaction = [i for i in INVITES if i.startswith("Theme du pack")]
        self.assertTrue(redaction)
        for invite in redaction:
            self.assertIn("assigner un role", invite)
        self.assertIn(libelles.FR["prompts_mode_emploi"], _textes_livres(resume))

    def test_le_plan_sait_quel_outil_il_sert(self):
        INVITES.clear()
        catalogue.executer("prompts", _contexte("portraits de chiens"),
                           {"nombre": 6, "cible": "image"})
        plan = next(i for i in INVITES if i.startswith("Organise un pack"))
        self.assertIn(pack_prompts.CIBLES["image"]["nom"], plan)
        self.assertIn(pack_prompts.CIBLES["image"]["categories"], plan)

    def test_la_cible_par_defaut_se_dit(self):
        lignes: List[str] = []
        pack_prompts.produire(_contexte("scripts de prospection",
                                        journal=lignes.append), nombre=6)
        self.assertTrue(any("personne ne l'a choisi" in l for l in lignes),
                        lignes[:4])


class LesPortesLaProposent(unittest.TestCase):

    def test_le_menu_montre_l_outil_et_rend_la_cle(self):
        from usine import menu

        sortie = io.StringIO()
        reponses = iter(["3"])
        with redirect_stdout(sortie), mock.patch(
                "builtins.input", lambda invite="": next(reponses, "")):
            options = menu._options_du_type("prompts")
        self.assertEqual(options, {"cible": "image"})
        self.assertIn("Midjourney", sortie.getvalue())

    def test_l_usine_la_decide_quand_personne_ne_la_choisit(self):
        INVITES.clear()
        ctx = _contexte("prompts pour restaurateurs")
        catalogue.executer("prompts", ctx, {"nombre": 6})
        self.assertIn("cible", ctx.meta.get("reglages_decides", {}))
        decision = next(i for i in INVITES
                        if i.startswith("Tu prepares la fabrication"))
        self.assertIn("image (Générateurs d'images", decision)


if __name__ == "__main__":
    unittest.main()
