"""Trois produits que l'usine ne savait pas fabriquer.

Elle ecrivait un livre de deux cents pages et trente posts LinkedIn, mais pas
les sept messages qui separent une inscription d'un premier achat, pas la
page qu'on garde a cote de soi, pas le quiz qui dit POURQUOI on s'est trompe.

Ce qui est verifie ici n'est pas que les chaines produisent des fichiers — la
fumee s'en charge — mais les trois endroits ou chacune pouvait mentir sans
que rien n'echoue.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


from tests import simulateur as sim  # noqa: E402
from usine.core import llm, store  # noqa: E402
from usine.pipelines import catalogue, emails, memo, quiz  # noqa: E402
from usine.pipelines.base import Contexte  # noqa: E402
from usine.render import libelles  # noqa: E402


def setUpModule():
    atelier.isoler("types_neufs")
    # Le simulateur se pose ICI, pas a l'import. Pose a l'import, il tenait
    # jusqu'a ce qu'un autre module de test le retire dans son « finally » —
    # « definir_simulateur(None) » est global. Les treize tests de ce module
    # passaient donc seuls et echouaient dans la suite, en sortant sur le
    # RESEAU : deux cent trente secondes de delais d'attente, et la regle
    # « aucun test ne sort sur le reseau » violee sans que rien ne le dise.
    llm.definir_simulateur(sim.simulateur)


def tearDownModule():
    llm.definir_simulateur(None)


def _contexte(sujet="la facturation des independants"):
    return Contexte(sujet=sujet, journal=lambda _m: None, sans_image=True)


class LeCatalogueLesConnait(unittest.TestCase):

    def test_les_trois_types_sont_fabricables(self):
        cles = catalogue.cles(fabricables=True)
        for cle in ("emails", "memo", "quiz"):
            self.assertIn(cle, cles)
            self.assertIsNotNone(catalogue.obtenir(cle).fabriquer,
                                 "{} sans chaine de fabrication".format(cle))

    def test_chacun_declare_ses_reglages(self):
        attendus = {"emails": {"nombre", "intention", "rythme"},
                    "memo": {"nombre", "recto_verso"},
                    "quiz": {"nombre", "niveau", "sans_bareme"}}
        for cle, noms in attendus.items():
            with self.subTest(type=cle):
                self.assertEqual(
                    {c.nom for c in catalogue.obtenir(cle).champs}, noms)

    def test_les_listes_de_choix_sont_lues_et_non_recopiees(self):
        """Deux listes finissent par ne plus proposer la meme chose."""
        self.assertEqual(set(catalogue.objectifs_email()), set(emails.OBJECTIFS))
        self.assertEqual(set(catalogue.niveaux_quiz()), set(quiz.NIVEAUX))
        champ = next(c for c in catalogue.obtenir("quiz").champs
                     if c.nom == "niveau")
        # Le vide est l'option « que l'usine decide » : il ne vient pas
        # de la liste du module, et ne dit rien d'une recopie.
        self.assertEqual({c for c in champ.choix if c}, set(quiz.NIVEAUX))

    def test_le_memo_et_le_quiz_ne_sont_pas_notes_comme_de_la_prose(self):
        """Le controle deterministe mesure le rythme des phrases et la
        diversite lexicale. Sur des lignes de trois mots et sur quatre
        propositions, il rend un chiffre qui n'a pas de sens — et un chiffre
        sans sens est pire que pas de chiffre, parce qu'on le croit.
        """
        self.assertFalse(catalogue.obtenir("memo").prose)
        self.assertFalse(catalogue.obtenir("quiz").prose)
        # Une sequence e-mail, elle, EST de la prose : des paragraphes ecrits
        # a une personne. La noter a un sens.
        self.assertTrue(catalogue.obtenir("emails").prose)

    def test_le_memo_ne_promet_pas_d_extrait(self):
        """« Les deux premieres pages » d'un memo d'une page ne veut rien
        dire : ce serait le produit entier, offert."""
        self.assertFalse(catalogue.obtenir("memo").extrait)


class LaSequenceEmail(unittest.TestCase):

    def test_le_rythme_espace_vraiment_les_messages(self):
        """Le rythme est ecrit sur chaque message et sert au calendrier. Un
        reglage affiche, sauvegarde et jamais lu est un mensonge fait a
        l'utilisateur."""
        ctx = _contexte()
        resume = emails.produire(ctx, nombre=4, rythme=5)
        donnees = (ctx.dossier / "sequence.json").read_text(encoding="utf-8")
        import json

        messages = json.loads(donnees)["messages"]
        self.assertEqual([m["jour"] for m in messages], [0, 5, 10, 15])
        self.assertEqual(resume["jours"], 15)

    def test_une_intention_inconnue_retombe_sur_l_accueil(self):
        ctx = _contexte()
        emails.produire(ctx, nombre=3, intention="conquete-spatiale")
        fiche = store.lire_produit(ctx.produit_id) or {}
        self.assertEqual((fiche.get("meta") or {}).get("objectif"), "bienvenue")

    def test_aucune_action_reste_aucune_action(self):
        """Le plan dit « aucune » pour un message qui ne demande rien — et
        c'est le cas de la plupart des messages d'accueil. Transformer cela
        en appel a l'action fabriquerait une demande que personne n'a voulue.
        """
        ctx = _contexte()
        emails.produire(ctx, nombre=4)
        import json

        messages = json.loads(
            (ctx.dossier / "sequence.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(messages[0]["action"], "")
        self.assertTrue(messages[1]["action"])

    def test_le_csv_porte_le_marqueur_d_encodage(self):
        """Les outils d'emailing francais ouvrent ce fichier dans Excel avant
        de l'importer. Sans marqueur, les accents des objets arrivent casses
        jusque dans la boite du destinataire."""
        ctx = _contexte()
        emails.produire(ctx, nombre=3)
        brut = (ctx.dossier / "sequence.csv").read_bytes()
        self.assertTrue(brut.startswith(b"\xef\xbb\xbf"))


class LeMemo(unittest.TestCase):

    def test_on_ne_demande_jamais_plus_que_ce_qu_un_memo_supporte(self):
        """La DEMANDE est bornee : inutile de faire ecrire vingt blocs pour
        en jeter six."""
        ctx = _contexte()
        resume = memo.produire(ctx, nombre=40)
        self.assertLessEqual(resume["blocs"], memo.BLOCS_MAX)

    def test_un_modele_qui_deborde_est_tranche(self):
        """Et la REPONSE l'est aussi, ce qui n'est pas la meme chose.

        Borner la demande ne borne pas ce qui revient : un modele repond
        volontiers dix-neuf blocs quand on en demande huit. Une premiere
        version de ce test demandait quarante blocs et croyait exercer la
        coupe — la demande etait ramenee a quatorze avant l'appel, le
        simulateur en rendait quatorze, et la ligne qui tranche ne
        s'executait jamais. La mutation l'a montre : on pouvait la supprimer
        sans qu'aucun test ne bronche.
        """
        from unittest import mock

        trop = [{"titre": "Bloc {}".format(i), "genre": "liste",
                 "lignes": ["une ligne", "une autre"]} for i in range(25)]
        ctx = _contexte()
        with mock.patch.object(memo, "_structure", return_value=trop):
            resume = memo.produire(ctx, nombre=8)
        self.assertEqual(resume["blocs"], memo.BLOCS_MAX)

    def test_la_marge_de_reliure_suit_le_recto_verso(self):
        """Posee sur une impression simple face, elle decale le texte sans
        rien servir."""
        ctx = _contexte()
        memo.produire(ctx, nombre=4, recto_verso=False)
        simple = (ctx.dossier / "memo.md").read_text(encoding="utf-8")
        self.assertTrue(simple.strip())
        # La valeur elle-meme se lit sur le produit remis a la livraison.
        from usine.render import livraison

        vus = {}
        vrai = livraison.livrer

        def espion(contexte, produit):
            vus["reliure"] = produit.reliure
            return vrai(contexte, produit)

        livraison.livrer = espion
        try:
            memo.produire(_contexte("autre sujet"), nombre=4, recto_verso=True)
            self.assertGreater(vus["reliure"], 0)
            memo.produire(_contexte("troisieme sujet"), nombre=4,
                          recto_verso=False)
            self.assertEqual(vus["reliure"], 0)
        finally:
            livraison.livrer = vrai


class LeQuiz(unittest.TestCase):

    def test_une_question_au_corrige_faux_est_ecartee(self):
        """Un corrige faux se decouvre apres la vente, par l'acheteur, et il
        n'a aucun moyen de savoir si c'est lui ou le quiz. Le simulateur en
        glisse une dont l'indice sort du tableau."""
        self.assertIsNone(quiz._valider(
            {"question": "x", "propositions": ["a", "b"], "reponse": 7}))
        self.assertIsNone(quiz._valider(
            {"question": "x", "propositions": ["a", "b"], "reponse": "deux"}))
        # Deux propositions identiques : deux reponses justes, un seul indice.
        self.assertIsNone(quiz._valider(
            {"question": "x", "propositions": ["a", "A"], "reponse": 0}))
        self.assertIsNotNone(quiz._valider(
            {"question": "x", "propositions": ["a", "b"], "reponse": 1}))

    def test_la_chaine_ecarte_et_le_dit(self):
        ctx = _contexte()
        resume = quiz.produire(ctx, nombre=6)
        # Le simulateur rend six questions valables plus une incoherente.
        self.assertEqual(resume["questions"], 6)

    def test_le_quiz_parle_la_langue_du_rendu_deja_ecrit(self):
        """« render/quiz.py » existait pour la formation et attend
        « reponse ». Inventer « bonne » aurait fait deux formes pour la meme
        chose, et la page se serait affichee muette."""
        question = quiz._valider(
            {"question": "x", "propositions": ["a", "b"], "reponse": 1,
             "module": "Bases"})
        self.assertIn("reponse", question)
        self.assertNotIn("bonne", question)
        from usine.render import quiz as rendu

        html = rendu.corps([question])
        self.assertIn("type=\"radio\"", html)

    def test_la_page_qui_se_corrige_seule_est_livree(self):
        ctx = _contexte()
        resume = quiz.produire(ctx, nombre=5)
        self.assertIn("quiz.html", resume["fichiers"])
        page = (ctx.dossier / "quiz.html").read_text(encoding="utf-8")
        self.assertIn("Corriger mes reponses", page)

    def test_le_bareme_compte_les_questions_retenues(self):
        """Un bareme sur vingt ne veut rien dire quand huit questions ont ete
        ecartees : il annoncerait des seuils qu'on ne peut pas atteindre."""
        francais = libelles.textes("fr")
        self.assertIn("16 bonnes reponses", quiz._bareme(20, francais))
        self.assertIn("10 bonnes reponses", quiz._bareme(12, francais))

    def test_sans_bareme_le_retire_vraiment(self):
        ctx = _contexte()
        quiz.produire(ctx, nombre=5, sans_bareme=True)
        page = (ctx.dossier / "lire.html").read_text(encoding="utf-8")
        self.assertNotIn("Bareme", page)
        ctx2 = _contexte("un autre sujet de quiz")
        quiz.produire(ctx2, nombre=5, sans_bareme=False)
        self.assertIn("Bareme",
                      (ctx2.dossier / "lire.html").read_text(encoding="utf-8"))


class UnBlocSansCorpsNeRendRien(unittest.TestCase):
    """Le mode d'emploi n'existait que dans le PDF.

    Un « Bloc » livre peut porter trois rendus : « corps » (markdown, qui
    sert a tous les formats), « rendu_pdf » (mise en page fine) et
    « rendu_html ». Trois chaines ne donnaient que le rendu PDF, en passant
    « rendu_html="" » — et un bloc sans corps ni rendu HTML ne rend RIEN,
    sans se plaindre.

    Mesure du 14/09/2026, en relisant « lire.html » : le mode d'emploi du
    pack de prompts, les consignes et le bareme du quiz, le calendrier
    d'envoi de la sequence e-mail manquaient tous les trois pour qui ouvre
    la page — c'est-a-dire pour la plupart des acheteurs sur telephone.

    Ce controle lit la STRUCTURE plutot qu'un nom : il fabrique et relit la
    page. Chercher « rendu_html="" » dans le source aurait laisse passer la
    meme faute ecrite autrement.
    """

    CHERCHE = {
        # Des phrases SANS apostrophe : « lire.html » les echappe en
        # « &#x27; », et une phrase qui en contient se cherche en vain.
        "prompts": "Chaque prompt est autonome",
        "emails": "Le calendrier ci-dessous",
        "quiz": "Repondez a toutes les questions",
    }

    def test_le_mode_d_emploi_arrive_jusqu_a_la_page_html(self):
        for cle, phrase in sorted(self.CHERCHE.items()):
            with self.subTest(type=cle):
                ctx = _contexte("la facturation")
                catalogue.executer(cle, ctx, {"nombre": 4})
                page = (ctx.dossier / "lire.html").read_text(encoding="utf-8")
                self.assertIn(phrase, page,
                              "« {} » : le bloc d'introduction n'existe que "
                              "dans le PDF".format(cle))

    def test_aucun_bloc_livre_n_est_muet(self):
        """Le garde-fou general : un bloc sans aucun rendu ne sert a rien.

        Il ne lit pas le source des chaines mais les BLOCS qu'elles remettent
        a la livraison, en interceptant l'assemblage commun.
        """
        from usine.render import livraison

        muets = []
        vrai = livraison.livrer

        def espion(contexte, produit):
            for bloc in produit.blocs:
                if not bloc.corps.strip() and not bloc.rendu_html.strip():
                    muets.append("{} / {}".format(produit.type, bloc.titre))
            return vrai(contexte, produit)

        livraison.livrer = espion
        try:
            for cle in ("prompts", "emails", "memo", "quiz"):
                catalogue.executer(cle, _contexte("la facturation"),
                                   {"nombre": 4})
        finally:
            livraison.livrer = vrai
        self.assertEqual(muets, [], "\n".join(
            ["Ces blocs ne rendent rien hors du PDF :"] + muets))


if __name__ == "__main__":
    unittest.main()
