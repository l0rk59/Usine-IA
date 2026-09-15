"""Un livre dont le lecteur est le heros : c'est le GRAPHE qui est le produit.

Les defauts d'un livre-jeu ne sont pas des defauts de texte. Une section peut
etre magnifiquement ecrite et le livre injouable : « rendez-vous a la section
31 » quand la 31 n'existe pas, une section qu'aucun chemin n'atteint, une
boucle d'ou aucune fin n'est joignable.

Aucun de ces defauts ne demande un appel de modele pour etre vu. Ils se
comptent — et se comptent AVANT la redaction, donc un livre troue ne coute
pas un livre entier a decouvrir.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("interactive")


from usine.core import llm, store  # noqa: E402
from usine.pipelines import base, interactive  # noqa: E402
from tests import simulateur  # noqa: E402


def _carte(*entrees):
    """Fabrique une carte a partir de (numero, [cibles]) ; [] = une fin."""
    return interactive.normaliser_carte({"sections": [
        {"numero": n, "intitule": "s{}".format(n), "fin": not cibles,
         "issue": "heureuse" if not cibles else "",
         "choix": [{"texte": "aller en {}".format(c), "vers": c}
                   for c in cibles]}
        for n, cibles in entrees]}, 99)


class LesQuatreDefautsQuiRendentUnLivreInjouable(unittest.TestCase):

    def test_un_choix_vers_une_section_qui_n_existe_pas(self):
        fautes = interactive.verifier_carte(
            _carte((1, [2, 31]), (2, []), (3, [])), 99)
        self.assertTrue(any("31" in f and "n'existe pas" in f for f in fautes),
                        fautes)

    def test_une_section_qu_aucun_chemin_n_atteint(self):
        """Ecrite, payee, et jamais lue."""
        fautes = interactive.verifier_carte(
            _carte((1, [2, 3]), (2, []), (3, []), (7, [2, 3])), 99)
        self.assertTrue(any("7" in f and "Aucun chemin" in f for f in fautes),
                        fautes)

    def test_un_piege_dont_aucune_fin_n_est_joignable(self):
        """Le lecteur y tourne en rond jusqu'a fermer le livre.

        Le cas est subtil : les sections 4 et 5 sont atteignables, elles ont
        des choix, chacun mene quelque part. Rien ne cloche localement — il
        faut parcourir le graphe a l'envers depuis les fins pour le voir.
        """
        fautes = interactive.verifier_carte(
            _carte((1, [2, 4]), (2, []), (4, [5]), (5, [4])), 99)
        self.assertTrue(any("aucune fin n'est joignable" in f for f in fautes),
                        fautes)

    def test_une_seule_fin_n_est_pas_un_livre_a_choix(self):
        fautes = interactive.verifier_carte(
            _carte((1, [2, 3]), (2, [3]), (3, [])), 99)
        self.assertTrue(any("livre a choix" in f for f in fautes), fautes)

    def test_une_carte_saine_ne_declenche_rien(self):
        """Le garde-fou doit se taire quand tout va bien : un controle qui
        signale a tort finit ignore."""
        carte = _carte((1, [2, 3]), (2, [4, 5]), (3, [4, 5]),
                       (4, []), (5, []))
        self.assertEqual(interactive.verifier_carte(carte, 99), [])

    def test_une_section_a_un_seul_choix_est_signalee(self):
        fautes = interactive.verifier_carte(
            _carte((1, [2]), (2, []), (3, [])), 99)
        self.assertTrue(any("au moins deux choix" in f for f in fautes), fautes)

    def test_les_defauts_nomment_la_section_en_cause(self):
        """« La carte semble incoherente » se relit trois fois sans rien
        trouver. Un defaut nomme se corrige — et c'est ce qu'on renvoie au
        modele pour qu'il reprenne CE point-la."""
        fautes = interactive.verifier_carte(
            _carte((1, [2, 31]), (2, []), (3, [])), 99)
        self.assertTrue(all(any(car.isdigit() for car in f) for f in fautes),
                        fautes)


class LaLectureDuGraphe(unittest.TestCase):

    def test_les_sections_atteignables_se_comptent_depuis_la_premiere(self):
        carte = _carte((1, [2]), (2, []), (9, [1]))
        self.assertEqual(interactive.atteignables(carte), {1, 2})

    def test_une_boucle_ne_fait_pas_tourner_le_parcours_sans_fin(self):
        carte = _carte((1, [2]), (2, [1, 3]), (3, []))
        self.assertEqual(interactive.atteignables(carte), {1, 2, 3})

    def test_sans_section_de_depart_rien_n_est_atteignable(self):
        self.assertEqual(interactive.atteignables(_carte((2, []), (3, []))),
                         set())


class LaNormalisationNeRepareRien(unittest.TestCase):
    """Reparer en silence ferait passer une carte trouee pour une carte
    juste — et c'est justement ce qu'on veut pouvoir compter."""

    def test_un_choix_sans_cible_lisible_est_jete(self):
        carte = interactive.normaliser_carte({"sections": [
            {"numero": 1, "choix": [{"texte": "a", "vers": "plus loin"},
                                    {"texte": "b", "vers": 2}]},
            {"numero": 2, "fin": True, "choix": []}]}, 9)
        self.assertEqual([c["vers"] for c in carte[0]["choix"]], [2])

    def test_une_section_hors_bornes_est_jetee(self):
        carte = interactive.normaliser_carte({"sections": [
            {"numero": 1, "choix": [{"texte": "a", "vers": 2}]},
            {"numero": 400, "fin": True, "choix": []}]}, 9)
        self.assertEqual([s["numero"] for s in carte], [1])

    def test_une_section_sans_choix_devient_une_fin(self):
        carte = interactive.normaliser_carte(
            {"sections": [{"numero": 1, "choix": []}]}, 9)
        self.assertTrue(carte[0]["fin"])

    def test_un_numero_en_double_ne_fait_pas_deux_sections(self):
        carte = interactive.normaliser_carte({"sections": [
            {"numero": 1, "intitule": "premiere", "choix": []},
            {"numero": 1, "intitule": "seconde", "choix": []}]}, 9)
        self.assertEqual(len(carte), 1)
        self.assertEqual(carte[0]["intitule"], "premiere")


class LElagageRendJouableEtLeDit(unittest.TestCase):
    """Le dernier recours, quand le modele n'a pas su corriger. Il ne repare
    pas l'histoire : il coupe ce qui la rend injouable."""

    def test_apres_elagage_la_carte_ne_porte_plus_de_defaut_bloquant(self):
        carte = _carte((1, [2, 31]), (2, [4]), (4, [5]), (5, [4]), (9, [1]))
        elaguee = interactive.elaguer(carte)
        fautes = interactive.verifier_carte(elaguee, 99)
        for interdit in ("n'existe pas", "Aucun chemin", "aucune fin n'est"):
            self.assertFalse(any(interdit in f for f in fautes), fautes)

    def test_un_piege_devient_une_fin_plutot_qu_une_impasse(self):
        carte = interactive.elaguer(_carte((1, [2, 4]), (2, []), (4, [5]),
                                           (5, [4])))
        par_numero = {s["numero"]: s for s in carte}
        self.assertTrue(par_numero[4]["fin"] or 4 not in par_numero)

    def test_ce_qu_aucun_chemin_n_atteint_n_est_pas_ecrit(self):
        carte = interactive.elaguer(_carte((1, [2, 3]), (2, []), (3, []),
                                           (8, [2, 3])))
        self.assertNotIn(8, {s["numero"] for s in carte})

    def test_un_choix_vers_soi_meme_disparait(self):
        """Il ne mene nulle part : le lecteur relit la meme page."""
        carte = interactive.elaguer(_carte((1, [1, 2]), (2, [])))
        self.assertEqual([c["vers"] for c in carte[0]["choix"]], [2])


class LeTexteDUneSectionNeFabriquePasDeSectionFantome(unittest.TestCase):
    """Le numero de section EST un titre dans le document rendu.

    Un « ## Le principe de base » laisse dans le corps fabrique une entree de
    plus au sommaire, et le lecteur a qui l'on dit « rendez-vous au 7 »
    trouve deux entrees entre le 6 et le 8. Mesure du 15/09/2026 : avant
    correction, un livre de douze sections en declarait vingt-quatre.
    """

    def test_les_titres_sont_retires_du_corps(self):
        # La fonction a demenage dans « base » le jour ou le feuilleton a
        # eu le meme besoin : deux copies auraient diverge.
        propre = base.sans_titres(
            "Un couloir.\n\n## Le principe de base\n\nUne porte.")
        self.assertNotIn("##", propre)
        self.assertIn("Un couloir.", propre)
        self.assertIn("Une porte.", propre)


class LaChaineCompleteViaLeSimulateur(unittest.TestCase):

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)

    def tearDown(self):
        llm.definir_simulateur(None)

    def _produire(self, sections=12):
        ctx = base.Contexte(sujet="un manoir sur la lande", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = sections, 150
        return ctx, interactive.produire(ctx)

    def test_un_livre_jouable_sort_de_bout_en_bout(self):
        _ctx, resume = self._produire()
        self.assertEqual(resume["sections"], 12)
        self.assertGreaterEqual(resume["fins"], interactive.FINS_MINIMUM)
        self.assertEqual(resume["defauts_restants"], [])
        self.assertFalse(resume["carte_elaguee"])

    def test_la_carte_verifiee_est_livree_avec_le_livre(self):
        """Sans elle, on ne peut pas rouvrir le livre pour corriger un
        chemin : il faudrait relire trente sections pour redessiner le
        graphe a la main."""
        import json

        _ctx, resume = self._produire()
        carte = json.loads((Path(resume["dossier"]) / "carte.json")
                           .read_text(encoding="utf-8"))["carte"]
        self.assertEqual(interactive.verifier_carte(carte, 12), [])

    def test_le_texte_ne_contient_aucun_titre_parasite(self):
        _ctx, resume = self._produire()
        texte = (Path(resume["dossier"]) / "interactive.md").read_text(
            encoding="utf-8")
        # Les seuls titres de niveau 2 doivent etre des numeros de section.
        titres = [l[3:].strip() for l in texte.split("\n")
                  if l.startswith("## ")]
        self.assertTrue(titres)
        for titre in titres:
            self.assertTrue(titre.isdigit(), titre)


class LeChoixEstEcritCommeLeGenreLEcrit(unittest.TestCase):
    """« Pousser la porte → 4 » ne survit pas au PDF.

    Le moteur PDF n'embarque aucune police : les quatorze polices standard du
    format, en WinAnsi, ou « → » n'existe pas. Le symbole etait RETIRE en
    silence — a raison, un « ? » a sa place se lirait comme un defaut du
    fichier — et la page montrait « Pousser la porte 4 », ou rien ne dit que
    4 est une destination. Vu en ouvrant le PDF, pas en lisant le markdown.
    """

    def test_l_infinitif_prend_la_formule_du_genre(self):
        self.assertEqual(
            interactive.formuler_choix("Pousser la porte", 4),
            "Si vous voulez pousser la porte, rendez-vous au **4**.")

    def test_la_deuxieme_personne_ne_donne_pas_une_phrase_fautive(self):
        # « Si vous voulez vous reculez » reviendrait a CHAQUE section.
        formule = interactive.formuler_choix("Vous reculez", 12)
        self.assertNotIn("Si vous voulez vous", formule)
        self.assertIn("rendez-vous au **12**", formule)

    def test_aucun_symbole_absent_des_polices_du_pdf(self):
        from usine.render import pdf as moteur

        for texte in ("Pousser la porte", "Vous reculez", "ACCEPTER"):
            formule = interactive.formuler_choix(texte, 7)
            # Ce que le PDF ecrira vraiment : le balisage inline retire, les
            # symboles absents des polices retires aussi. Le numero doit
            # survivre aux deux.
            ecrit = moteur._sans_symbole(formule.replace("**", ""))
            self.assertIn("rendez-vous au 7", ecrit)

    def test_le_livre_livre_ne_porte_aucune_fleche(self):
        llm.definir_simulateur(simulateur.simulateur)
        try:
            ctx = base.Contexte(sujet="une gare abandonnee", sans_image=True,
                                journal=lambda m: None)
            ctx.chapitres, ctx.mots_section = 12, 150
            resume = interactive.produire(ctx)
        finally:
            llm.definir_simulateur(None)
        texte = (Path(resume["dossier"]) / "interactive.md").read_text(
            encoding="utf-8")
        self.assertNotIn("\u2192", texte)
        self.assertIn("rendez-vous au", texte)


class LaSecondeDemandeNommeLesDefautsDeLaPremiere(unittest.TestCase):
    """Un modele a qui l'on dit « recommence » refait la meme carte.

    Ce mecanisme n'etait garde par aucun test : le simulateur rend toujours
    une carte valide, donc la reprise ne s'executait jamais. Une campagne de
    mutation l'a montre — retirer les defauts de la seconde invite ne faisait
    echouer personne.
    """

    def setUp(self):
        # Le cache des reponses est indexe sur l'invite, et l'invite de la
        # carte ne depend que de la BIBLE — que le simulateur rend identique
        # quel que soit le sujet. Deux cas de ce module partagent donc leur
        # entree de cache, et le second comptait zero appel : il ne mesurait
        # plus la reprise, il mesurait le cache. Changer de sujet ne suffit
        # pas ; il faut vider.
        store.cache_vider()

    def tearDown(self):
        llm.definir_simulateur(None)

    def test_les_defauts_precis_sont_renvoyes_au_modele(self):
        import json

        invites = []

        def deux_cartes(messages, role):
            invite = messages[-1]["content"]
            if '"vers"' not in invite or '"fin"' not in invite:
                return simulateur.simulateur(messages, role)
            invites.append(invite)
            if len(invites) == 1:
                # Premiere carte : un choix vers le vide, et une seule fin.
                return json.dumps({"sections": [
                    {"numero": 1, "intitule": "depart", "fin": False,
                     "choix": [{"texte": "aller", "vers": 2},
                               {"texte": "fuir", "vers": 31}]},
                    {"numero": 2, "intitule": "la fin", "fin": True,
                     "issue": "heureuse", "choix": []}]})
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(deux_cartes)
        # Un sujet PROPRE a ce cas. Deux cas de test qui partagent une invite
        # partagent une entree de cache, et le second n'exerce rien : la
        # premiere version de ce test comptait zero appel parce qu'un autre
        # cas avait deja fabrique la meme carte.
        ctx = base.Contexte(sujet="un manoir a deux cartes", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 12, 120
        resume = interactive.produire(ctx)

        self.assertEqual(len(invites), 2, "la carte fausse n'a pas ete reprise")
        seconde = invites[1]
        self.assertIn("31", seconde)
        self.assertIn("n'existe pas", seconde)
        # Et la premiere ne pouvait pas les contenir : elle les a causes.
        self.assertNotIn("n'existe pas", invites[0])
        # La reprise a abouti : pas d'elagage, pas de defaut restant.
        self.assertFalse(resume["carte_elaguee"])
        self.assertEqual(resume["defauts_restants"], [])

    def test_une_carte_juste_du_premier_coup_ne_declenche_pas_de_reprise(self):
        """Redemander a un modele qui a bien repondu coute un appel pour
        rien — et sur un telephone, un appel est une minute."""
        invites = []

        def compter(messages, role):
            invite = messages[-1]["content"]
            if '"vers"' in invite and '"fin"' in invite:
                invites.append(invite)
            return simulateur.simulateur(messages, role)

        llm.definir_simulateur(compter)
        ctx = base.Contexte(sujet="un manoir du premier coup", sans_image=True,
                            journal=lambda m: None)
        ctx.chapitres, ctx.mots_section = 12, 120
        interactive.produire(ctx)
        self.assertEqual(len(invites), 1)
