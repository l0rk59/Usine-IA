"""Les plafonds de jetons sont les NOTRES, et une coupure n'est pas une erreur.

Deux constats du 16/09/2026, sur un journal reel.

1. « reponse coupee au plafond (700 jetons) ». Ce 700 etait ecrit a la main
   dans brief.py — une quarantaine de chiffres du meme genre vivent dans le
   depot. Le fournisseur n'y est pour rien.

2. Une reponse coupee ne leve AUCUNE erreur : HTTP 200, « finish_reason:
   length », un « usage » renseigne. Il n'y a donc pas d'erreur a attendre
   pour decouvrir la vraie limite — c'est la premiere des trois regles de ce
   depot : ne pas croire le code de retour, lire le contenu.

Ce que faisait « generer_json » : le JSON coupe est illisible, donc il en
concluait que le fournisseur ne savait pas tenir un format, l'ECARTAIT, et
recommencait AU MEME PLAFOND chez le suivant. Trois fournisseurs brules pour
une limite que nous avions posee nous-memes.

« nouvelle._grille_ou_retente » avait deja trouve la bonne reponse pour un
seul appel, et son docstring la dit : ne pas inventer un plafond plus gros et
esperer, mais lire ce que le routeur mesure deja, et redemander avec de la
place. Ce qui valait pour la grille de beats vaut pour les quarante autres
appels JSON.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("plafonds")


from usine.core import llm  # noqa: E402


class _Fournisseur:
    """Rend un JSON COUPE tant que le plafond demande est trop bas.

    C'est la forme exacte du defaut : rien ne leve, le texte revient
    simplement tronque, et « tronquee » est le seul signal.
    """

    def __init__(self, il_faut=2000):
        self.il_faut = il_faut
        self.plafonds = []
        self.fournisseurs = []

    def __call__(self, invite, systeme="", role="standard", temperature=0.4,
                 max_tokens=4000, json_mode=False, cache=True, eviter=None,
                 **_k):
        self.plafonds.append(max_tokens)
        nom = "fournisseur-{}".format(len(self.fournisseurs) + 1)
        self.fournisseurs.append(nom)
        complet = json.dumps({"genre": "policier", "detail": "x" * 40})
        if max_tokens < self.il_faut:
            return llm.Reponse(texte=complet[:20], fournisseur=nom,
                               modele="m", tronquee=True)
        return llm.Reponse(texte=complet, fournisseur=nom, modele="m",
                           tronquee=False)


def _avec(faux):
    vrai = llm.generer
    llm.generer = faux
    return vrai


class UneCoupureFaitGrandirLePlafondPasChangerDeFournisseur(unittest.TestCase):

    def test_le_plafond_double_au_lieu_d_ecarter_le_fournisseur(self):
        faux = _Fournisseur(il_faut=2000)
        vrai = _avec(faux)
        try:
            resultat = llm.generer_json("une invite", max_tokens=1000)
        finally:
            llm.generer = vrai
        self.assertEqual(resultat["genre"], "policier")
        self.assertEqual(faux.plafonds, [1000, 2000], (
            "plafonds demandes : {} — une coupure doit donner de la place, "
            "pas relancer au meme plafond".format(faux.plafonds)))

    def test_aucun_fournisseur_n_est_ecarte_pour_notre_propre_plafond(self):
        """Le coeur du defaut : la faute etait a nous, la punition au
        fournisseur."""
        faux = _Fournisseur(il_faut=2000)
        vrai = _avec(faux)
        ecartes = []
        vraie_generer = faux.__call__

        def espion(invite, **k):
            ecartes.append(list(k.get("eviter") or []))
            return vraie_generer(invite, **k)

        llm.generer = espion
        try:
            llm.generer_json("une autre invite", max_tokens=1000)
        finally:
            llm.generer = vrai
        self.assertEqual(ecartes[-1], [], (
            "le fournisseur a ete ecarte alors qu'il repondait bien : {}"
            .format(ecartes)))

    def test_le_plafond_ne_grandit_pas_sans_fin(self):
        """Il s'arrete au plus large que le catalogue de fournisseurs
        accepte : monter plus haut ne produit pas plus, cela produit une
        erreur chez certains et un silence chez d'autres."""
        faux = _Fournisseur(il_faut=10**9)   # jamais assez
        vrai = _avec(faux)
        try:
            with self.assertRaises(ValueError):
                llm.generer_json("invite sans fin", max_tokens=1000, essais=6)
        finally:
            llm.generer = vrai
        self.assertLessEqual(max(faux.plafonds), llm.PLAFOND_RELANCE)
        self.assertEqual(llm.PLAFOND_RELANCE,
                         max(p.max_sortie for p in llm.config.PROVIDERS))

    def test_un_modele_qui_ne_sait_pas_le_json_est_toujours_ecarte(self):
        """Le garde-fou qui crie a tort : une reponse ILLISIBLE mais NON
        coupee reste la faute du fournisseur, et le traitement d'avant doit
        continuer de s'appliquer."""
        vus = []

        def bavard(invite, **k):
            nom = "bavard-{}".format(len(vus) + 1)
            vus.append(list(k.get("eviter") or []))
            return llm.Reponse(texte="Bien sur ! Voici la reponse.",
                               fournisseur=nom, modele="m", tronquee=False)

        vrai = _avec(bavard)
        try:
            with self.assertRaises(ValueError):
                llm.generer_json("invite", max_tokens=1000, essais=3)
        finally:
            llm.generer = vrai
        self.assertTrue(vus[-1], (
            "aucun fournisseur ecarte alors qu'ils repondent en prose : {}"
            .format(vus)))


if __name__ == "__main__":
    unittest.main()


class UnReglageEcarteNeDisparaitPlusEnSilence(unittest.TestCase):
    """Journal reel du 16/09/2026, roman : « L'usine decide 9 reglage(s) »
    puis HUIT valeurs. Le neuvieme etait « genre » — le plus structurant —
    auquel le modele avait repondu « drame contemporain », hors de la liste
    fermee. Le roman est parti sans contrat de genre, et il fallait compter
    les lignes du journal pour s'en apercevoir.

    Ecarter reste la bonne decision : accepter « drame contemporain » ferait
    entrer dans la fiche une valeur que rien d'autre ne sait relire. C'est le
    SILENCE qui etait le defaut.
    """

    REPONSE = {
        "genre": "drame contemporain",          # hors liste
        "sous_genre": "roman d'apprentissage",  # champ libre
        "tropes": "mentor", "ambiance": "intime",
        "point_de_vue": "premiere personne", "temps": "present",
        "chaleur": "tendre", "fin": "heureuse", "structure": "voyage du heros",
    }

    def _journal(self, reponse, sujet):
        """Un SUJET different par cas : l'invite entre dans la cle de cache,
        et deux cas qui la partagent partagent la reponse — le second
        n'exercerait alors rien. Le piege que le depot signale, retombe ici au
        premier essai : le cas « tout passe » recevait la reponse fautive du
        cas precedent."""
        from usine.pipelines import base, brief, catalogue

        lignes = []
        llm.definir_simulateur(lambda m, r: json.dumps(reponse))
        try:
            ctx = base.Contexte(sujet=sujet, sans_image=True,
                                journal=lignes.append)
            decides = brief.decider_les_reglages(
                ctx, catalogue.obtenir("roman"), {})
        finally:
            llm.definir_simulateur(None)
        return decides, " | ".join(lignes)

    def test_le_reglage_perdu_est_nomme_avec_sa_raison(self):
        decides, journal = self._journal(self.REPONSE,
                                         "la restauration de meubles")
        self.assertNotIn("genre", decides)
        self.assertIn("genre", journal)
        self.assertIn("drame contemporain", journal)
        self.assertIn("hors de la liste", journal, (
            "le journal ne dit pas pourquoi le reglage a ete perdu : {}"
            .format(journal)))

    def test_le_compte_des_perdus_est_donne(self):
        """Huit lignes sous une annonce de neuf ne se remarquent pas sur un
        ecran de telephone."""
        _, journal = self._journal(self.REPONSE,
                                   "la plongee en apnee")
        self.assertIn("1 reglage(s) sur 9", journal)

    def test_rien_n_est_annonce_quand_tout_passe(self):
        """Le garde-fou qui crie a tort : une reponse entierement valide ne
        doit produire aucune ligne d'avertissement."""
        bonne = dict(self.REPONSE, genre="policier")
        decides, journal = self._journal(bonne, "la taille des bonsais")
        self.assertEqual(decides.get("genre"), "policier")
        self.assertNotIn("non retenu", journal)
        self.assertNotIn("restent a la charge", journal)
