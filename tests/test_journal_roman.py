"""Ce qu'un journal de fabrication reel a montre, le 16/09/2026.

Un roman de dix-huit scenes, sur un telephone. Trois defauts, dont un qui est
la pire forme que connaisse ce depot : tous les signaux disaient « valide ».

1. LE 7,5 FABRIQUE. Huit scenes, huit lignes identiques :

       relecture « L'atelier qui tousse » : 7.5/10, 0 correction(s)
       relecture « L'inspection qui tombe » : 7.5/10, 0 correction(s)
       ... six fois de plus, au dixieme pres ...

   L'editeur n'avait relu AUCUNE scene. Sa reponse revenait coupee au plafond,
   donc illisible, et la branche d'erreur rendait « Critique(note=7.5) » —
   pile le seuil d'acceptation. Le journal montrait une relecture qui n'avait
   pas eu lieu, avec une note qui n'avait ete mesuree sur rien.

   Pire : 7,5 >= 7,5 rend la critique « acceptable », ce qui ARRETE la boucle
   d'amelioration en annoncant que le texte est assez bon.

2. LE PLAFOND DE 320. La memoire hierarchique demande un etat « en 90 mots
   maximum ». Quatre-vingt-dix mots francais font environ 234 jetons ; le
   plafond en laissait 320, soit 86 de marge. Coupe a chaque scene, dix-huit
   fois de suite. « jetons_pour » existe pour cette conversion et porte deja
   la marge.

3. LE SERVICE RETIRE. GitHub Models repondait « le service a ete retire par
   son editeur » — un fait que le depot avait deja constate le 15/09 et ecrit
   dans son propre code. Aucun repos n'etait pose pour ce cas : le seul echec
   vraiment definitif du lot etait le seul reinterroge a chaque bascule.

Aucun test ici ne sort sur le reseau.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("journal-roman")


from usine.agents import equipe  # noqa: E402
from usine.agents.base import Critique  # noqa: E402
from usine.core import llm  # noqa: E402
from usine.pipelines import base, nouvelle  # noqa: E402


class UneRelectureQuiNAPasEuLieuNEnEstPasUne(unittest.TestCase):

    def test_elle_ne_porte_pas_de_note(self):
        perdue = Critique(note=0.0, mesuree=False, verdict="HTTP 502")
        self.assertIn("indisponible", perdue.resume())
        self.assertNotIn("7.5", perdue.resume())

    def test_elle_n_est_pas_acceptable_meme_avec_une_bonne_note(self):
        """Le vrai degat : « acceptable » arrete la boucle d'amelioration.

        La note doit etre HAUTE pour que ce test mesure quelque chose. Avec
        zero, il passait avec ou sans la correction — une campagne de mutation
        l'a montre. Le defaut d'origine rendait justement 7,5, pile le seuil.
        """
        self.assertFalse(Critique(note=7.5, mesuree=False).acceptable, (
            "une relecture qui n'a pas eu lieu est jugee acceptable"))
        self.assertFalse(Critique(note=10.0, mesuree=False).acceptable)

    def test_une_vraie_note_reste_acceptable(self):
        """Le pendant : sans lui, tout refuser passerait le test precedent
        sans rien distinguer."""
        self.assertTrue(Critique(note=7.5).acceptable)
        self.assertIn("7.5", Critique(note=7.5).resume())

    def test_l_editeur_injoignable_rend_une_critique_non_mesuree(self):
        def tombe(*a, **k):
            raise llm.PlusDeFournisseur("tous les fournisseurs ont echoue")

        vrai = equipe.EDITEUR.travailler_json
        equipe.EDITEUR.travailler_json = tombe
        try:
            ctx = base.Contexte(sujet="un phare", journal=lambda m: None)
            critique = equipe.critiquer(ctx, "un texte", "une scene")
        finally:
            equipe.EDITEUR.travailler_json = vrai
        self.assertFalse(critique.mesuree, (
            "une relecture impossible rend une note comme si elle avait eu "
            "lieu : {}".format(critique.resume())))
        self.assertFalse(critique.acceptable)

    def test_une_reponse_qui_n_est_pas_un_objet_n_est_pas_une_note(self):
        """L'autre porte de sortie : le modele a repondu, mais pas un objet.
        Elle rendait elle aussi 7,5."""
        vrai = equipe.EDITEUR.travailler_json
        equipe.EDITEUR.travailler_json = lambda *a, **k: (["une liste"], "faux")
        try:
            ctx = base.Contexte(sujet="un port", journal=lambda m: None)
            critique = equipe.critiquer(ctx, "un texte", "une scene")
        finally:
            equipe.EDITEUR.travailler_json = vrai
        self.assertFalse(critique.mesuree, (
            "une relecture illisible passe pour mesuree : {}".format(
                critique.resume())))
        self.assertFalse(critique.acceptable)

    def test_le_rapport_ne_moyenne_pas_ce_qui_n_a_pas_ete_mesure(self):
        rapport = equipe.rapport_qualite({
            "scene 1": [Critique(note=6.0)],
            "scene 2": [Critique(note=0.0, mesuree=False)],
        })
        # Seule la vraie note compte : une moyenne de 3,0 ferait croire a une
        # mesure, et une de 6,75 ferait croire a deux.
        self.assertEqual(rapport.get("note_moyenne_finale"), 6.0)


class LePlafondVientDuNombreDeMots(unittest.TestCase):

    def test_la_memoire_demande_de_quoi_ecrire_ce_qu_elle_demande(self):
        """90 mots ~ 234 jetons de contenu ; le plafond en laissait 320."""
        from usine.pipelines.base import jetons_pour

        vus = []

        def espion(self, ctx, invite, max_tokens=4000, **k):
            vus.append(max_tokens)
            return llm.Reponse(texte="Un etat factuel de l'histoire. " * 6,
                               fournisseur="faux", modele="m")

        vrai = equipe.SCENARISTE.__class__.travailler
        equipe.SCENARISTE.__class__.travailler = espion
        try:
            ctx = base.Contexte(sujet="un phare", journal=lambda m: None)
            nouvelle.mettre_a_jour_resume(ctx, "", "une scene", "du texte")
        finally:
            equipe.SCENARISTE.__class__.travailler = vrai
        self.assertEqual(vus, [jetons_pour(nouvelle.MOTS_RESUME)])
        self.assertGreater(vus[0], 320, (
            "le plafond ne laisse pas de quoi ecrire les {} mots demandes"
            .format(nouvelle.MOTS_RESUME)))


class UnServiceRetireSeRepose(unittest.TestCase):
    """Le seul echec definitif du lot, et le seul sans repos."""

    def test_le_cas_est_reconnu(self):
        erreur = llm.HttpErreur(
            410, "github_models_retirement_brownout")
        self.assertTrue(llm._service_ferme(erreur))

    def test_il_est_mis_au_repos_longtemps(self):
        llm._REPOS.pop("github", None)
        llm._reposer("github", 86400, "service retire")
        self.assertGreater(llm._REPOS.get("github", 0) - __import__("time").time(),
                           3600, (
            "un service retire se repose moins longtemps qu'une cle refusee"))
        llm._REPOS.pop("github", None)

    def test_un_410_met_reellement_le_fournisseur_au_repos(self):
        """Mesure sur le ROUTEUR, et non sur le texte du fichier : chercher
        « 86400 » dans la source passerait meme si plus rien ne l'appelait.

        Sans repos, le fournisseur retire etait reinterroge a chaque bascule —
        une fois par scene, sur chaque produit, indefiniment.
        """
        import time

        # On ne vise pas un fournisseur nomme : sans cle d'API, la plupart
        # sont sautes avant l'appel, et le test mesurerait un fournisseur
        # qu'on n'a jamais interroge. On regarde CEUX QUI ONT REPONDU.
        llm._REPOS.clear()
        appeles = []

        def ferme(p, *a, **k):
            appeles.append(p.name)
            raise llm.HttpErreur(410, "github_models_retirement_brownout")

        vrai_appel, vrai_quota = llm._appel, llm._quota_ok
        llm._appel = ferme
        llm._quota_ok = lambda *a, **k: True
        try:
            try:
                llm.generer("bonjour", cache=False)
            except llm.PlusDeFournisseur:
                pass
        finally:
            llm._appel, llm._quota_ok = vrai_appel, vrai_quota
        self.assertTrue(appeles, "le routeur n'a interroge personne")
        for nom in set(appeles):
            with self.subTest(fournisseur=nom):
                reste = llm._REPOS.get(nom, 0.0) - time.time()
                self.assertGreater(reste, 3600, (
                    "« {} » s'est declare retire et se repose {:.0f} s — "
                    "moins qu'une cle refusee, alors qu'il est le seul echec "
                    "definitif du lot".format(nom, max(reste, 0))))
        llm._REPOS.clear()


if __name__ == "__main__":
    unittest.main()
