"""Six peaux pour le tableau de bord, et ce qu'une peau doit changer.

« nuit » et « jour » etaient deux nuances de la meme interface : meme police,
meme densite, memes animations. Une peau qui ne change que la teinte ne sert
qu'a soi-meme.

Or trois situations demandent trois interfaces differentes, pas trois
nuances : un ecran de telephone en plein soleil, un vieil appareil que la 3D
fait ramer, et quelqu'un qui ne distingue pas un cyan sur du noir. « papier »,
« console » et « contraste » repondent a ces trois-la — elles changent la
police, la densite, la taille de base, et coupent les animations.

Les peaux sont declarees dans « core/reglages.py » et nulle part ailleurs :
la CLI, le menu Termux et la page les lisent toutes les trois. Une liste
recopiee dans le CSS et une autre dans le menu finiraient par ne plus proposer
les memes.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import reglages  # noqa: E402

CSS = (RACINE / "usine" / "web" / "statique" / "tableau.css").read_text(
    encoding="utf-8")
JS = (RACINE / "usine" / "web" / "statique" / "app.js").read_text(
    encoding="utf-8")


def setUpModule():
    atelier.isoler("peaux")


class LaListeEstUnique(unittest.TestCase):

    def test_chaque_peau_declaree_a_son_bloc_css(self):
        """Une peau proposee sans regles CSS laisse la page sans couleurs :
        le navigateur ne trouve rien et affiche du noir sur du noir."""
        for peau in reglages.THEMES:
            with self.subTest(peau=peau["cle"]):
                if peau["cle"] == "nuit":
                    continue  # la peau d'origine vit sur « :root »
                self.assertIn('[data-theme="{}"]'.format(peau["cle"]), CSS)

    def test_aucun_bloc_css_ne_propose_une_peau_inconnue(self):
        """L'autre sens : une peau dans le CSS que personne ne peut choisir
        est du style mort, et celui qui la trouve croit a une regression."""
        declarees = {t["cle"] for t in reglages.THEMES}
        dans_le_css = set(re.findall(r'\[data-theme="(\w+)"\]', CSS))
        self.assertEqual(dans_le_css - declarees, set())

    def test_le_navigateur_ne_recopie_pas_la_liste(self):
        """Elle arrive par « /api/etat ». Une seconde liste dans le script
        vieillirait sans que rien ne le dise."""
        for peau in reglages.THEMES:
            if peau["cle"] in ("nuit", "jour"):
                continue  # citees comme valeurs de repli, ce qui est normal
            with self.subTest(peau=peau["cle"]):
                self.assertNotIn("'{}'".format(peau["cle"]), JS)

    def test_le_serveur_les_sert_toutes(self):
        from usine.web import serveur

        peaux = serveur._etat()["peaux"]
        self.assertEqual([p["cle"] for p in peaux],
                         [t["cle"] for t in reglages.THEMES])
        for peau in peaux:
            with self.subTest(peau=peau["cle"]):
                self.assertTrue(peau["nom"] and peau["description"])

    def test_une_peau_inconnue_retombe_sur_nuit(self):
        """Un reglage recopie a la main, ou une peau retiree entre deux
        versions, ne doit pas rendre la page illisible."""
        self.assertEqual(reglages.theme("nexistepas")["cle"], "nuit")

    def test_le_reglage_refuse_une_peau_inventee(self):
        valeurs = reglages.ecrire({"theme": "arc-en-ciel"})
        self.assertIn(valeurs["theme"], {t["cle"] for t in reglages.THEMES})
        reglages.reinitialiser()


class UnePeauChangePlusQueLaCouleur(unittest.TestCase):

    def _bloc(self, cle):
        """Le bloc CSS d'une peau, tel qu'il est ecrit."""
        debut = CSS.index(':root[data-theme="{}"] {{'.format(cle))
        return CSS[debut:CSS.index("}", debut)]

    def test_les_peaux_calmes_coupent_les_animations(self):
        """Un vieux telephone qui rame n'a pas besoin d'une autre teinte :
        il a besoin qu'on arrete ce qui tourne.

        Quatre choses tournent en meme temps sur la peau d'origine, et une
        premiere version du test se contentait de chercher « data-anime »
        quelque part dans la feuille : retirer la regle qui eteint le canvas
        laissait le test vert, parce que la regle qui coupe les transitions
        contenait le meme mot. On verifie donc chaque cible, une par une.
        """
        calmes = [t["cle"] for t in reglages.THEMES if not t["anime"]]
        self.assertTrue(calmes, "aucune peau calme : le sujet a disparu")
        for cle in calmes:
            with self.subTest(peau=cle):
                self.assertFalse(reglages.THEMES_PAR_CLE[cle]["anime"])

        # Chaque selecteur pris SEUL. Les regroupes par virgule partagent une
        # accolade : lire le groupe entier faisait passer « data-inerte » pour
        # « data-anime » des lors qu'un voisin de la meme liste portait le bon
        # attribut. Le test etait vert, la peau calme laissait tourner le
        # canvas.
        eteints = set()
        for groupe in re.findall(r"([^{}]*)\{[^{}]*\}", CSS):
            for selecteur in groupe.split(","):
                if '[data-anime="non"]' in selecteur:
                    eteints.add(selecteur.split('[data-anime="non"]')[-1].strip())
        for cible in ("#fond-cyber", "body:after", ".scene"):
            with self.subTest(cible=cible):
                self.assertIn(cible, eteints,
                              "une peau calme laisse « {} » tourner"
                              .format(cible))
        coupe = re.search(
            r'\[data-anime="non"\][^{}]*\{[^{}]*animation:\s*none', CSS)
        self.assertTrue(coupe, "une peau calme laisse les animations CSS")

    def test_trois_familles_de_police_au_moins(self):
        """Serif, chasse fixe et sans : trois lectures differentes, pas trois
        nuances de la meme."""
        familles = {t["police"] for t in reglages.THEMES}
        self.assertGreaterEqual(len(familles), 3)

    def test_chaque_peau_qui_change_de_police_le_fait_vraiment(self):
        for peau in reglages.THEMES:
            if peau["police"] == "sans" or peau["cle"] == "contraste":
                continue
            with self.subTest(peau=peau["cle"]):
                bloc = self._bloc(peau["cle"])
                self.assertIn("--police-corps", bloc,
                              "« {} » se dit « {} » et garde la police par "
                              "defaut".format(peau["cle"], peau["police"]))

    def test_la_peau_contraste_grossit_le_texte(self):
        """Ce n'est pas une variante esthetique : c'est la peau qui rend le
        tableau de bord utilisable a qui voit mal."""
        bloc = self._bloc("contraste")
        trouve = re.search(r"--taille-base:\s*(\d+)px", bloc)
        self.assertTrue(trouve, "« contraste » ne change pas la taille du texte")
        self.assertGreaterEqual(int(trouve.group(1)), 17)

    def test_la_peau_console_densifie(self):
        """Sur un telephone, elle doit faire tenir plus de lignes a l'ecran."""
        bloc = self._bloc("console")
        trouve = re.search(r"--densite:\s*([\d.]+)", bloc)
        self.assertTrue(trouve)
        self.assertLess(float(trouve.group(1)), 1.0)

    def test_la_densite_et_la_police_sont_vraiment_employees(self):
        """Des variables declarees et jamais lues seraient six peaux qui se
        ressemblent malgre leurs declarations."""
        self.assertIn("var(--police-corps)", CSS)
        self.assertIn("var(--police-titre)", CSS)
        self.assertIn("var(--densite)", CSS)
        self.assertIn("var(--taille-base)", CSS)


class LeChoixSeFaitPartout(unittest.TestCase):

    def test_le_menu_termux_propose_la_meme_liste(self):
        """On fait tourner le menu et on regarde ce qu'il AFFICHE.

        Chercher « reglages.THEMES » dans le fichier ne prouvait rien : le
        nom y figure deux fois, et remplacer la liste des cles par deux peaux
        en dur laissait le second appel — donc le mot — en place. Le menu ne
        proposait plus que « nuit » et « jour », et le test restait vert.
        """
        from usine import menu

        self.assertIn("theme", menu._A_CHOISIR)
        propose = {}

        def espion(titre, options, defaut=1, retour="Retour"):
            propose["options"] = options
            return len(options)  # la derniere peau de la liste

        vrai = menu.choisir
        menu.choisir = espion
        try:
            rendu = menu._A_CHOISIR["theme"]("nuit")
        finally:
            menu.choisir = vrai

        self.assertEqual([nom for nom, _detail in propose["options"]],
                         [t["nom"] for t in reglages.THEMES])
        self.assertEqual(rendu, reglages.THEMES[-1]["cle"],
                         "le menu enregistre une autre peau que celle choisie")

    def test_le_systeme_a_le_dernier_mot_sur_les_animations(self):
        """Quelqu'un qui a demande moins d'animations ne doit pas en recevoir
        parce qu'une peau en prevoit."""
        self.assertIn("prefers-reduced-motion", JS)

    def test_la_scene_se_recalcule_au_lieu_de_se_cacher(self):
        """Une premiere version ne faisait que CACHER : revenir d'une peau
        calme a « nuit » laissait la scene 3D eteinte jusqu'au rechargement,
        et on croyait la peau cassee.

        On ne cherche plus une ligne precise — elle a deja bouge une fois —
        mais le point unique qui decide, et le fait que les deux entrees
        (changer de peau, changer d'onglet) y passent toutes les deux. Deux
        calculs separes divergeraient, et c'est exactement le defaut d'origine.
        """
        self.assertIn("function majVisibiliteScene", JS)
        for fonction in ("appliquerPeau", "montrerSection"):
            with self.subTest(entree=fonction):
                bloc = JS[JS.index("function {}(".format(fonction)):]
                bloc = bloc[:bloc.index("\n}")]
                self.assertIn("majVisibiliteScene()", bloc,
                              "« {} » decide de la scene dans son coin"
                              .format(fonction))

    def test_les_quatre_conditions_pesent_sur_la_scene(self):
        """La peau, le reglage « effets_3d », le support WebGL et la section.

        Chacune a son motif : une peau calme sur un vieil appareil, quelqu'un
        qui a coupe la 3D, un navigateur sans WebGL, et un onglet ou
        l'avancement d'une fabrication ne veut rien dire. En oublier une
        rallume la scene chez quelqu'un qui l'avait eteinte.
        """
        bloc = JS[JS.index("function majVisibiliteScene"):]
        bloc = bloc[:bloc.index("\n}")]
        for condition in ("anime", "scene.actif", "effets3dActifs()",
                          "sceneAttendue()"):
            with self.subTest(condition=condition):
                self.assertIn(condition, bloc)


if __name__ == "__main__":
    unittest.main()
