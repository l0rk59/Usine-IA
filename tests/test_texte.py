"""Ce que le modele ajoute au texte, et le refus qui se fait passer pour une reponse.

Les deux defauts gardes ici ont la meme forme : rien n'echoue. Le texte arrive,
le controle qualite le note, le PDF le met en page, et le defaut n'apparait que
dans le produit fini — c'est-a-dire chez l'acheteur.

La mesure qui a ouvert le sujet, le 13/09/2026, sur un vrai appel :

    HTTP 200, finish_reason « stop », usage renseigne, et pour tout contenu
    « The API key used for this request has reached its budget. »

Un quota epuise qui ne ressemble pas a un quota epuise. Le routeur ne
basculait pas — puisque rien n'avait echoue — et le message de facturation
partait dans un chapitre.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import texte  # noqa: E402

# Le message reel, recopie tel qu'il est arrive.
MESSAGE_REEL = (
    "The API key used for this request has reached its budget. Please "
    "[raise the key budget](https://enter.pollinations.ai/edit-key?id=89idjaT"
    "Sg2hI4YwZDuO8ZME5Ma6GrFps&ref=agent_key_budget), then try again.\n\n"
    "Topping up the wallet does not raise this limit."
)


def setUpModule():
    atelier.isoler("texte")


class RestesDeFabrication(unittest.TestCase):

    def test_le_brouillon_de_raisonnement_ne_passe_pas(self):
        for balise in ("think", "thinking", "reasoning", "scratchpad"):
            with self.subTest(balise=balise):
                brut = "<{0}>je pese le pour et le contre</{0}>Le chapitre.".format(balise)
                self.assertEqual(texte.assainir(brut), "Le chapitre.")

    def test_une_ouverture_sans_fermeture_vide_la_reponse(self):
        """Coupe au plafond au milieu du brouillon : il n'y a pas de reponse.

        Rendre le brouillon serait pire que rendre rien : une reponse vide
        fait redemander, un brouillon fait un chapitre de reflexions a voix
        haute que personne ne relit.
        """
        self.assertEqual(texte.assainir("<think>je commence a peine"), "")

    def test_les_jetons_de_dialogue_disparaissent(self):
        for jeton in ("<|im_end|>", "<|endoftext|>", "<|eot_id|>", "[INST]"):
            with self.subTest(jeton=jeton):
                self.assertEqual(texte.assainir("Bonjour" + jeton), "Bonjour")

    def test_une_balise_html_legitime_survit(self):
        """« <s> » barre un prix dans une page de vente.

        Le retirer partout aurait casse les pages de vente, qui barrent le
        prix d'origine a cote du prix remise. On ne l'enleve donc qu'aux
        bords, la ou il ne peut etre qu'un jeton de modele.
        """
        garde = "Le <s>99 EUR</s> devient 29 EUR"
        self.assertEqual(texte.assainir(garde), garde)
        self.assertEqual(texte.assainir("<s>Bonjour"), "Bonjour")

    def test_les_caracteres_invisibles_sont_retires(self):
        sale = "Bon​jour﻿ le­ monde�"
        self.assertEqual(texte.assainir(sale), "Bonjour le monde")

    def test_le_mojibake_est_repare(self):
        # « l'ete a ete reussi » ecrit en UTF-8 puis relu comme du latin-1.
        casse = "l'été a été réussi".encode(
            "utf-8").decode("latin-1")
        self.assertEqual(texte.reparer_encodage(casse), "l'été a été réussi")

    def test_un_texte_a_moitie_abime_sort_intact(self):
        """Le garde-fou principal, et il ne se voit pas.

        Un accent francais reel donne un octet isole qui n'est jamais un
        debut de sequence UTF-8 valide. Un texte ou cohabitent une signature
        de mojibake et de vrais accents echoue donc au redecodage, et sort
        tel quel plutot qu'a moitie converti.
        """
        casse = "l'été".encode("utf-8").decode("latin-1")
        mixte = casse + " et déjà"
        self.assertEqual(texte.reparer_encodage(mixte), mixte)

    def test_sans_signature_on_ne_touche_a_rien(self):
        """« é«» » se reencode en un ideogramme chinois parfaitement valide.

        Sans l'exigence d'une signature, un texte francais ordinaire pouvait
        donc etre transforme en silence — la conversion reussit, et rien ne
        le signale.
        """
        # Sans accent francais isole apres : c'est bien la PREMIERE condition
        # qu'on exerce ici, pas le decodage qui echoue par ailleurs.
        self.assertEqual(texte.reparer_encodage("é«»"), "é«»")

    def test_un_texte_sain_n_est_jamais_touche_par_la_reparation(self):
        """La conversion est brutale : elle doit rester inerte sur du bon texte.

        C'est la condition pour l'adopter. Un correcteur qui abime un texte
        sain une fois sur cent est pire que pas de correcteur du tout.
        """
        for sain in ("l'été a été réussi", "Ça coûte 29 EUR", "naïve où", "",
                     "Voici « un exemple » — avec tirets cadratins"):
            with self.subTest(sain=sain):
                self.assertEqual(texte.reparer_encodage(sain), sain)


class RefusDeguise(unittest.TestCase):

    def test_le_message_reel_est_reconnu(self):
        raison = texte.refus_deguise(MESSAGE_REEL)
        self.assertTrue(raison)
        self.assertIn("service", raison)

    def test_il_est_classe_comme_un_quota(self):
        """La duree du repos en depend.

        Revenir dans dix secondes chez un service qui n'a plus de credit
        rebrule un appel pour rien.
        """
        self.assertTrue(texte.ressemble_a_un_quota(MESSAGE_REEL))
        self.assertFalse(texte.ressemble_a_un_quota(
            "Internal server error, please try again later."))

    def test_un_seul_signal_ne_suffit_pas(self):
        """La regle qui empeche d'accuser un vrai chapitre.

        Un manuel sur les API parle legitimement de « rate limit ». Un
        chapitre peut citer une phrase anglaise. Les deux a la fois, avec en
        plus un lien vers une console de facturation, n'arrivent pas.
        """
        chapitre = ("Votre API doit gerer le rate limit : au-dela de trente "
                    "appels par minute, le service repond 429 et il faut "
                    "attendre. Voici comment le prevoir dans votre code.")
        self.assertEqual(texte.refus_deguise(chapitre), "")

    def test_un_texte_long_n_est_jamais_accuse(self):
        """Les messages de service sont courts ; un chapitre ne l'est pas."""
        long = (MESSAGE_REEL + " ") * 6
        self.assertGreater(len(long), texte.LONGUEUR_MAX_MESSAGE)
        self.assertEqual(texte.refus_deguise(long), "")

    def test_le_mode_json_ne_reclame_pas_de_francais(self):
        """Un JSON a des cles anglaises, et c'est normal.

        Sans ce drapeau, « aucun mot francais » se serait declenche sur
        chaque reponse structuree courte.
        """
        reponse = '{"titre": "Ok", "sections": 8}'
        self.assertEqual(texte.refus_deguise(reponse, attend_francais=False), "")


class LeRouteurApplique(unittest.TestCase):
    """Le module peut etre parfait et n'etre branche nulle part.

    Ces deux cas passent par « _appel », c'est-a-dire par le vrai chemin
    d'une reponse de fournisseur : une reponse HTTP complete, fabriquee ici.
    Sans eux, les tests du module auraient continue de passer alors que le
    routeur, lui, ne l'appelait plus.
    """

    @staticmethod
    def _reponse(contenu):
        import json
        from unittest import mock

        charge = json.dumps({
            "choices": [{"message": {"content": contenu},
                         "finish_reason": "stop"}],
            "usage": {"total_tokens": 42},
        })
        return mock.patch("usine.core.llm.post_json",
                          return_value=json.loads(charge))

    def _appeler(self, contenu):
        from usine.core import config, llm

        fournisseur = config.PROVIDERS_BY_NAME["pollinations"]
        with self._reponse(contenu):
            return llm._appel(fournisseur, [{"role": "user", "content": "x"}],
                              "standard", 0.7, 500, False, 30, None)

    def test_le_brouillon_ne_traverse_pas_le_routeur(self):
        reponse = self._appeler("<think>je pese le pour</think>Le chapitre.")
        self.assertEqual(reponse.texte, "Le chapitre.")

    def test_le_refus_deguise_fait_echouer_l_appel(self):
        """C'est ce qui fait basculer le routeur sur un autre fournisseur.

        Tant que l'appel « reussissait », rien ne basculait : le message de
        facturation etait mis en cache et ecrit dans un chapitre.
        """
        from usine.core.http import HttpErreur

        with self.assertRaises(HttpErreur) as leve:
            self._appeler(MESSAGE_REEL)
        # 402 et non 503 : « plus de credit » ne se retente pas dans dix
        # secondes, contrairement a un hoquet de service.
        self.assertEqual(leve.exception.statut, 402)

    def test_une_panne_de_service_n_est_pas_classee_comme_un_quota(self):
        from usine.core.http import HttpErreur

        panne = ("Internal server error from the upstream provider. "
                 "The service is temporarily unavailable, please try again "
                 "later. No endpoints found for this request.")
        with self.assertRaises(HttpErreur) as leve:
            self._appeler(panne)
        self.assertEqual(leve.exception.statut, 503)


class AucuneFausseAlerteSurDuVraiTexte(unittest.TestCase):
    """Mesure sur des produits reellement fabriques, pas sur des exemples.

    Un detecteur qui signale a tort finit ignore, ce qui est pire que se
    taire. La condition d'adoption etait : zero accusation sur un corpus
    entier. Elle a ete verifiee sur 354 000 caracteres de produits fabriques,
    et ce test la refait a chaque passage de la suite sur ce que la suite
    fabrique elle-meme.
    """

    @classmethod
    def setUpClass(cls):
        import io
        from contextlib import redirect_stdout

        from tests.simulateur import simulateur
        from usine.core import llm

        llm.definir_simulateur(simulateur)
        from usine import cli

        with redirect_stdout(io.StringIO()):
            cli.principal(["ebook", "la facturation des independants",
                           "--chapitres", "4"])
        llm.definir_simulateur(None)
        from usine.core import config

        cls.textes = [f.read_text(encoding="utf-8")
                      for f in config.PRODUITS_DIR.rglob("*")
                      if f.is_file() and f.suffix in (".md", ".txt")]

    def test_le_corpus_existe(self):
        """Sans quoi les deux tests suivants passeraient a vide."""
        self.assertTrue(self.textes)
        self.assertGreater(sum(len(t) for t in self.textes), 5000)

    def test_aucun_paragraphe_n_est_pris_pour_un_refus(self):
        for contenu in self.textes:
            for bloc in contenu.split("\n\n"):
                raison = texte.refus_deguise(bloc)
                self.assertEqual(raison, "", "accuse a tort : " + bloc[:80])

    def test_assainir_ne_touche_pas_au_fond(self):
        """Il peut retirer des blancs ; il ne doit pas retirer des mots."""
        for contenu in self.textes:
            mots_avant = len(contenu.split())
            mots_apres = len(texte.assainir(contenu).split())
            self.assertEqual(mots_avant, mots_apres)


if __name__ == "__main__":
    unittest.main()
