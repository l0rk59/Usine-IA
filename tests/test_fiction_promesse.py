"""Pour la fiction, on ne cherche pas une niche.

Une niche, ailleurs dans l'usine, c'est un PROBLEME que quelqu'un paie pour
resoudre. Toute la prospection est batie la-dessus : probleme, acheteur,
promesse de resultat, concurrence, canal d'acquisition.

Applique a un roman, ce vocabulaire n'a pas de reponse honnete — et un modele
a qui l'on pose une question sans reponse en fabrique une. On obtenait des
fictions habillees en produits pratiques.

Ce que ce module garde, c'est que la fiction a son propre vocabulaire, que ce
vocabulaire arrive JUSQU'AUX INVITES, et que le controle de genre se tait
quand il ne sait pas.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("fiction_promesse")


from usine.pipelines import base, catalogue, fiction  # noqa: E402


class LeVocabulaireDeLaFiction(unittest.TestCase):

    def test_le_genre_se_deduit_du_sous_genre(self):
        self.assertEqual(fiction.genre_du_sous_genre("cozy mystery"), "policier")
        # « fantasy romance » est le nom du rayon ; « romantasy » est le mot
        # de la conversation. Le second n'est pas dans la liste : les listes
        # de ce module ne portent que ce qu'une source nomme.
        self.assertEqual(fiction.genre_du_sous_genre("Fantasy Romance"),
                         "romance")

    def test_un_sous_genre_inconnu_ne_rend_pas_de_genre(self):
        """Le marche invente des sous-genres plus vite qu'on ne met a jour
        une liste. Deviner ferait declencher des controles de convention au
        hasard — et un controle qui signale a tort finit ignore."""
        self.assertEqual(fiction.genre_du_sous_genre("biopunk lacustre"), "")
        self.assertEqual(fiction.genre_du_sous_genre(""), "")

    def test_la_longueur_est_situee_pas_jugee(self):
        texte = fiction.situer_la_longueur(27000, "contemporary romance")
        self.assertIn("27000", texte)
        self.assertIn("50000", texte)
        # Une MESURE, pas un verdict : l'usine n'a pas de quoi trancher si
        # un format court est un choix ou un accident.
        for mot in ("trop court", "insuffisant", "mauvais"):
            self.assertNotIn(mot, texte.lower())

    def test_une_longueur_inconnue_ne_rend_rien(self):
        self.assertEqual(fiction.situer_la_longueur(27000, "biopunk"), "")
        self.assertEqual(fiction.situer_la_longueur(0, "cozy mystery"), "")


class LeContratDeGenre(unittest.TestCase):
    """Deterministe, zero appel de modele : il compare deux reglages entre
    eux, ce qui se verifie sans lire une ligne du livre."""

    def test_une_romance_a_fin_tragique_est_signalee(self):
        alertes = fiction.contrat_de_genre(
            {"genre": "romance", "fin": "tragique"})
        self.assertTrue(alertes)
        self.assertIn("contrat", alertes[0].lower())

    def test_une_romance_a_fin_heureuse_ne_l_est_pas(self):
        for fin in fiction.FINS_EXIGEES_EN_ROMANCE:
            self.assertEqual(
                fiction.contrat_de_genre({"genre": "romance", "fin": fin}), [])

    def test_un_polar_a_fin_tragique_ne_l_est_pas(self):
        """La regle est propre a la romance. L'appliquer partout ferait un
        garde-fou qui crie a tort huit fois sur dix."""
        self.assertEqual(
            fiction.contrat_de_genre({"genre": "policier", "fin": "tragique"}),
            [])

    def test_un_genre_inconnu_ne_declenche_rien(self):
        self.assertEqual(
            fiction.contrat_de_genre({"genre": "", "fin": "tragique"}), [])

    def test_la_chaleur_adulte_sur_un_livre_jeunesse_est_signalee(self):
        alertes = fiction.contrat_de_genre(
            {"genre": "jeunesse", "chaleur": "explicite"})
        self.assertTrue(alertes)


class LaPromesseArriveJusquAuxInvites(unittest.TestCase):
    """Le point qui separe un reglage d'un reglage orphelin.

    Les neuf champs de fiction etaient saisissables et enregistrables. S'ils
    n'entrent pas dans l'invite, ils sont un mensonge fait a l'utilisateur —
    et c'est un test de ce depot qui garde ce point ailleurs.
    """

    def _contexte(self, **reglages):
        ctx = base.Contexte(sujet="Un phare en Bretagne")
        fiction.poser_la_promesse(ctx, reglages)
        return ctx

    def test_l_invite_de_la_bible_porte_le_sous_genre_et_la_fin(self):
        from usine.core import llm

        vues = []

        def simulateur(messages, role):
            vues.append(messages[-1]["content"])
            return json.dumps({
                "titre": "Le phare", "genre": "policier",
                "premisse": "p", "cadre": {"lieu": "l", "epoque": "e",
                                           "regles": ["r"]},
                "personnages": [{"nom": "Anne", "role": "protagoniste",
                                 "desir": "d", "defaut": "f", "voix": "v"}],
                "enjeu": "e", "fin_visee": "f"})

        from usine.pipelines import nouvelle
        llm.definir_simulateur(simulateur)
        try:
            ctx = self._contexte(sous_genre="cozy mystery", fin="heureuse",
                                 chaleur="porte fermee")
            nouvelle.construire_bible(ctx)
        finally:
            llm.definir_simulateur(None)
        self.assertIn("cozy mystery", vues[0])
        self.assertIn("heureuse", vues[0])
        self.assertIn("porte fermee", vues[0])

    def test_les_consignes_de_scene_portent_le_temps_et_la_chaleur(self):
        """Ce sont les trois reglages qui se perdent phrase apres phrase :
        un modele qui tient le passe pendant huit scenes glisse a la
        neuvieme, et rien ne le rattrape."""
        ctx = self._contexte(temps="present", chaleur="tendre",
                             point_de_vue="premiere personne")
        texte = fiction.consignes_de_scene(ctx)
        self.assertIn("present", texte)
        self.assertIn("premiere personne", texte)
        self.assertIn("baisers", texte)

    def _rediger_une_scene(self, **reglages):
        """Appelle la VRAIE redaction de scene et rend l'invite envoyee.

        Verifier « consignes_de_scene » toute seule ne prouve rien : une
        campagne de mutation a montre que supprimer son injection dans
        « rediger_scene » ne faisait echouer aucun test. L'ingredient etait
        garde, le cablage non — exactement le defaut que ce depot retrouve a
        chaque audit.
        """
        from usine.core import llm
        from usine.pipelines import nouvelle

        vues = []
        scene = {"titre": "Le phare s'eteint", "beat": "declencheur",
                 "lieu": "le phare", "personnages": ["Anne"],
                 "point_de_vue": "Anne", "objectif": "comprendre",
                 "obstacle": "la tempete", "pivot": "elle trouve la lettre"}
        grille = {"scenes": [scene], "beats": [{"nom": "declencheur",
                                                "evenement": "la lettre"}]}
        bible = {"titre": "Le phare", "genre": "policier", "premisse": "p",
                 "cadre": {"lieu": "l", "epoque": "e", "regles": ["r"]},
                 "personnages": [{"nom": "Anne", "role": "protagoniste",
                                  "desir": "d", "defaut": "f", "voix": "v"}],
                 "enjeu": "e", "fin_visee": "f"}

        def simulateur(messages, role):
            vues.append(messages[-1]["content"])
            return "Anne poussa la porte. Le vent entra avec elle."

        llm.definir_simulateur(simulateur)
        try:
            nouvelle.rediger_scene(self._contexte(**reglages), bible, grille,
                                   0, scene, memoire="")
        finally:
            llm.definir_simulateur(None)
        return vues[0]

    def test_la_vraie_redaction_de_scene_porte_les_consignes(self):
        invite = self._rediger_une_scene(temps="present", chaleur="tendre",
                                         ambiance="melancolique")
        self.assertIn("present", invite)
        self.assertIn("baisers", invite)
        self.assertIn("melancolique", invite)

    def test_la_vraie_redaction_de_scene_ne_repete_pas_le_bloc_entier(self):
        invite = self._rediger_une_scene(sous_genre="cozy mystery",
                                         temps="passe")
        self.assertNotIn("cozy mystery", invite)
        self.assertIn("passe", invite)

    def test_la_scene_ne_repete_pas_le_bloc_entier(self):
        """Le repeter trente fois couterait son volume multiplie par trente
        sans rien ajouter — une depense qui ne se voit que sur la facture."""
        ctx = self._contexte(sous_genre="cozy mystery", temps="passe")
        self.assertIn("cozy mystery", fiction.consignes(ctx))
        self.assertNotIn("cozy mystery", fiction.consignes_de_scene(ctx))

    def test_sans_reglage_aucune_consigne_n_est_ajoutee(self):
        """Une invite qui enumere neuf champs vides apprend au modele que
        ces champs ne comptent pas."""
        ctx = self._contexte()
        self.assertEqual(fiction.consignes(ctx), "")
        self.assertEqual(fiction.consignes_de_scene(ctx), "")


class LesDeuxCheminsDeposentLaPromesse(unittest.TestCase):
    """La ligne de commande pose ses reglages sur un « Namespace », la file
    de production dans un dictionnaire. Les deux doivent arriver au meme
    endroit, sinon une promesse trouvee par l'exploration se perd entre la
    file et la fabrication."""

    def test_depuis_un_dictionnaire_d_options(self):
        ctx = base.Contexte(sujet="x")
        fiction.poser_la_promesse(ctx, {"sous_genre": "cozy mystery"})
        self.assertEqual(fiction.promesse_du_contexte(ctx)["genre"], "policier")

    def test_depuis_un_namespace_de_ligne_de_commande(self):
        import argparse

        ctx = base.Contexte(sujet="x")
        fiction.poser_la_promesse(
            ctx, argparse.Namespace(sous_genre="fantasy romance",
                                    fin="heureuse"))
        lu = fiction.promesse_du_contexte(ctx)
        self.assertEqual(lu["genre"], "romance")
        self.assertEqual(lu["fin"], "heureuse")

    def test_les_trois_portes_appellent_bien_le_meme_depot(self):
        """Garde-fou de structure : une porte qui oublierait l'appel
        laisserait la promesse se perdre sans qu'aucun test d'unite ne le
        voie, parce que chacune fonctionne isolement.

        Ce garde-fou ne regardait que DEUX portes, la ligne de commande et
        la file. La troisieme, le tableau de bord, ne posait pas la
        promesse — mesure du 23/09/2026 : un reglage de fiction choisi dans
        le formulaire atteignait une invite sur vingt-huit. Les trois
        passent maintenant par « brief.completer », qui pose la promesse.
        """
        def appelle(chemin, nom):
            arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"))
            return any(isinstance(n, ast.Call)
                       and isinstance(n.func, ast.Attribute)
                       and n.func.attr == nom
                       for n in ast.walk(arbre))

        for chemin in ("usine/cli.py", "usine/production.py",
                       "usine/web/serveur.py"):
            self.assertTrue(appelle(chemin, "completer"), chemin)
        self.assertTrue(appelle("usine/pipelines/brief.py", "poser_la_promesse"))


class LaFictionNeReprendPasLesReglagesDuPratique(unittest.TestCase):

    def test_chaque_type_de_fiction_recoit_les_champs_de_fiction(self):
        """Tous les champs pour la fiction adulte ; pas pour un album.

        Ce test exigeait la liste COMPLETE sur les six types, conte compris.
        C'est ainsi qu'un album pour trois a cinq ans en est venu a proposer
        « niveau de chaleur : explicite » — et la valeur partait reellement
        dans l'invite qui ecrit l'album.

        Le partage d'une liste unique reste la bonne idee entre un roman et
        un feuilleton. Il ne vaut pas entre un roman et un album illustre.
        « catalogue.SANS_OBJET_EN_JEUNESSE » nomme la difference, et
        « tests/test_reglages_fiction.py » la garde.
        """
        from usine.pipelines import catalogue

        attendus = {c.nom for c in catalogue.champs_de_fiction()}
        for produit in catalogue.TYPES:
            if produit.famille != "fiction":
                continue
            noms = {c.nom for c in produit.champs}
            with self.subTest(type=produit.cle):
                if produit.cle == "conte":
                    self.assertEqual(
                        noms & set(catalogue.SANS_OBJET_EN_JEUNESSE), set())
                    self.assertIn("tranche", noms)
                else:
                    # « serie » n'existe que la ou des tomes s'enchainent.
                    exiges = attendus - (
                        set() if produit.cle in catalogue.TYPES_A_TOMES
                        else {"serie"})
                    self.assertTrue(exiges <= noms, exiges - noms)


    def test_aucun_type_pratique_ne_recoit_ces_champs(self):
        """« sous-genre » ou « niveau de chaleur » sur un guide de fiscalite
        est un champ que personne ne lira, et qui fait douter des autres."""
        propres = {"sous_genre", "tropes", "chaleur", "fin", "ambiance",
                   "point_de_vue"}
        for fiche in catalogue.TYPES:
            if fiche.famille == "fiction":
                continue
            self.assertEqual(propres & {c.nom for c in fiche.champs}, set(),
                             fiche.cle)

    def test_la_liste_des_types_de_fiction_est_lue_dans_le_catalogue(self):
        """Une liste recopiee oublierait le prochain type ajoute, et l'oubli
        ne se verrait qu'a l'usage : un roman a qui l'on demande quel
        probleme il resout."""
        attendu = tuple(f.cle for f in catalogue.TYPES
                        if f.famille == "fiction")
        self.assertEqual(fiction.types_de_fiction(), attendu)
        self.assertTrue(attendu)

    def test_est_fiction_distingue_bien_les_deux_familles(self):
        self.assertTrue(fiction.est_fiction("roman"))
        self.assertFalse(fiction.est_fiction("ebook"))
        self.assertFalse(fiction.est_fiction(""))


class LExplorationDePromessesNEstPasUneProspectionDeNiches(unittest.TestCase):

    def tearDown(self):
        from usine.core import llm

        llm.definir_simulateur(None)

    def test_l_invite_demande_des_tropes_et_non_un_probleme(self):
        from usine.core import llm

        vues = []

        def simulateur(messages, role):
            vues.append(messages[-1]["content"])
            return json.dumps({"promesses": []})

        llm.definir_simulateur(simulateur)
        fiction.explorer_promesses(base.Contexte(sujet="Bretagne"), nombre=3)
        invite = vues[0]
        self.assertIn("TROPES", invite)
        self.assertIn("FIN", invite)
        # Le vocabulaire des niches n'a rien a faire ici : c'est lui qui
        # faisait fabriquer des reponses a des questions sans reponse.
        for mot in ("probleme precis resolu", "premier_canal",
                    "angle_differenciant", "concurrence"):
            self.assertNotIn(mot, invite)

    def test_une_promesse_garde_un_sous_genre_inconnu(self):
        """« romantasy » n'existait pas quand ces listes ont commence."""
        propre = fiction._nettoyer_promesse(
            {"titre": "T", "type": "roman", "sous_genre": "biopunk lacustre"})
        self.assertEqual(propre["sous_genre"], "biopunk lacustre")
        self.assertEqual(propre["genre"], "")

    def test_un_type_pratique_propose_bascule_vers_la_fiction(self):
        """Ce que le modele a trouve reste bon ; c'est l'etiquette qui a
        glisse. Jeter la proposition perdrait le travail."""
        propre = fiction._nettoyer_promesse(
            {"titre": "T", "type": "ebook", "sous_genre": "cozy mystery"})
        self.assertTrue(fiction.est_fiction(propre["type"]))

    def test_l_exploration_refuse_le_cache(self):
        arbre = ast.parse((RACINE / "usine" / "pipelines" / "fiction.py")
                          .read_text(encoding="utf-8"))
        fonction = next(n for n in ast.walk(arbre)
                        if isinstance(n, ast.FunctionDef)
                        and n.name == "explorer_promesses")
        appels = [n for n in ast.walk(fonction) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "travailler_json"]
        self.assertEqual(len(appels), 1)
        self.assertTrue([m for m in appels[0].keywords if m.arg == "cache"
                         and m.value.value is False])


class LeVocabulaireDuGenreEstProposeQuandRienNEstImpose(unittest.TestCase):
    """Le cas le plus courant : un sous-genre choisi, et rien d'autre.

    C'est par le TROPE qu'un lecteur cherche un livre — il ne tape pas
    « romance contemporaine », il tape « ennemis puis amants ». Laisser le
    modele en inventer hors du genre produit un livre que personne ne
    cherche.
    """

    def test_le_genre_connu_apporte_ses_tropes(self):
        texte = fiction.promesse_pour_ia({"sous_genre": "dark romance"})
        self.assertIn("ennemis puis amants", texte)

    def test_des_tropes_imposes_ne_sont_pas_completes(self):
        """Proposer une liste a qui a deja choisi, c'est l'inviter a
        s'ecarter de son choix."""
        texte = fiction.promesse_pour_ia(
            {"sous_genre": "dark romance", "tropes": "one bed"})
        self.assertNotIn("ennemis puis amants", texte)

    def test_un_genre_sans_trope_recense_n_en_propose_aucun(self):
        """Le cozy mystery a bien un genre — mais aucune source consultee ne
        recense les tropes du policier. Le modele n'en recoit donc pas, au
        lieu d'en recevoir d'inventes."""
        texte = fiction.promesse_pour_ia({"sous_genre": "cozy mystery"})
        self.assertIn("cozy mystery", texte)
        self.assertNotIn("Aucun trope impose", texte)

    def test_un_genre_inconnu_n_apporte_aucune_liste(self):
        texte = fiction.promesse_pour_ia({"sous_genre": "biopunk lacustre"})
        self.assertNotIn("Aucun trope impose", texte)
