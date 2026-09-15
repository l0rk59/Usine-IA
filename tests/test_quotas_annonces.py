"""Les quotas ecrits, confrontes a ceux que le service annonce.

« config.py » le dit de lui-meme : fournisseurs, modeles, quotas — donnees
recopiees, donc perissables. Les modeles savent desormais se verifier ; les
quotas, non. Ils sont recopies d'une page de documentation, et rien ne les
avait jamais confrontes a quoi que ce soit.

Or la plupart des services les annoncent dans les en-tetes de CHAQUE reponse.
Un appel minimal par fournisseur suffit — pas un par modele, puisque ces
limites valent pour le compte.

Ce que ce module garde, c'est surtout ce que l'audit doit REFUSER de dire :
deviner une fenetre qu'il ne connait pas, et prendre un silence pour un
accord.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("quotas_annonces")


from usine.core import config, diagnostic  # noqa: E402
from usine.core.http import HttpErreur  # noqa: E402


class LaRemiseAZeroNEstPasLaFenetre(unittest.TestCase):
    """Le defaut que le premier passage sur un vrai compte a revele.

    On deduisait la fenetre du temps de remise a zero : « 7.2s » donc par
    minute, « 23h » donc par jour. Groq annonce 1000 requetes avec une remise
    a zero de quelques dizaines de secondes, et l'audit a conclu « 1000 par
    minute, alors que 30 est ecrit : different ». Or 1000 est exactement le
    « rpd » ecrit, et il est juste.

    La cause : chez un service a seau de jetons, la remise a zero est le temps
    de RECHARGE de ce qui vient d'etre consomme, pas la longueur de la
    fenetre. Un appel sur mille d'un quota journalier recharge en une poignee
    de secondes, ce qui se lit « par minute » et ne l'est pas.

    On ne deduit donc plus rien : on regarde a quel chiffre ECRIT le chiffre
    annonce correspond.
    """

    def test_un_millier_annonce_se_reconnait_comme_le_quota_du_jour(self):
        groq = config.PROVIDERS_BY_NAME["groq"]
        quota = groq.quota("standard")
        self.assertEqual(diagnostic._correspondance(quota.rpd, quota),
                         "requetes par jour")
        self.assertEqual(diagnostic._correspondance(quota.rpm, quota),
                         "requetes par minute")
        self.assertEqual(diagnostic._correspondance(quota.tpm, quota),
                         "jetons par minute")

    def test_un_chiffre_inconnu_ne_se_range_nulle_part(self):
        """Et c'est une reponse : « je ne sais pas » vaut mieux qu'un
        verdict tire au sort sur un chiffre que personne n'ira revoir."""
        groq = config.PROVIDERS_BY_NAME["groq"]
        self.assertEqual(
            diagnostic._correspondance(123456789, groq.quota("standard")), "")

    def test_les_formes_connues_se_lisent(self):
        for brut, attendu in (("7.2s", 7.2), ("60", 60.0), ("2m", 120.0),
                              ("1m30s", 90.0), ("23h14m56s", 83696.0),
                              ("500ms", 0.5)):
            self.assertAlmostEqual(diagnostic._secondes(brut), attendu, places=2,
                                   msg=brut)

    def test_ce_qui_ne_se_lit_pas_rend_rien(self):
        for brut in ("", "bientot", None):
            self.assertIsNone(diagnostic._secondes(brut))

    def test_la_duree_reste_affichee_mais_ne_decide_plus(self):
        """Elle renseigne le lecteur ; elle ne rend plus de verdict."""
        self.assertIn("minute", diagnostic._fenetre(7.2))
        self.assertIn("demi-heure", diagnostic._fenetre(83696.0))
        self.assertEqual(diagnostic._fenetre(900.0), "")
        self.assertEqual(diagnostic._fenetre(None), "")


class LesTroisVerdicts(unittest.TestCase):

    def _auditer(self, entetes, fournisseur="mistral"):
        p = config.PROVIDERS_BY_NAME[fournisseur]

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                observe["entetes"] = dict(entetes)
                observe["jetons"] = 0
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            return diagnostic.auditer_quotas()["lignes"][0]

    def test_un_chiffre_ecrit_est_reconnu_quelle_que_soit_la_remise_a_zero(self):
        """Le coeur de la correction : une remise a zero courte ne doit plus
        faire prendre un quota journalier pour un quota par minute."""
        p = config.PROVIDERS_BY_NAME["mistral"]
        ligne = self._auditer({
            "x-ratelimit-limit-requests": str(p.quota("standard").rpd),
            "x-ratelimit-reset-requests": "12s",
        })
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["verdict"], "accorde")
        self.assertEqual(requetes["correspond"], "requetes par jour")

    def test_un_chiffre_inconnu_rend_la_mesure_sans_verdict(self):
        ligne = self._auditer({
            "x-ratelimit-limit-requests": "987654",
            "x-ratelimit-reset-requests": "30s",
        })
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["verdict"], "inconnu")
        self.assertEqual(requetes["correspond"], "")
        self.assertEqual(requetes["annonce"], 987654)

    def test_un_silence_n_est_pas_un_accord(self):
        """« Non publie » veut dire « on ne sait pas ».

        Le confondre avec « conforme » ferait passer un quota jamais verifie
        pour un quota verifie — la meme fausse assurance que ce depot
        supprime partout ailleurs.
        """
        ligne = self._auditer({})
        for mesure in ligne["mesures"]:
            self.assertEqual(mesure["verdict"], "non publie")
            self.assertNotIn("annonce", mesure)

    def test_ce_qu_on_ne_sait_pas_lire_est_rendu_tel_quel(self):
        """Ce qu'on ne comprend pas aujourd'hui se lit a l'oeil, et se code
        demain. Le jeter garantirait de ne jamais l'apprendre."""
        ligne = self._auditer({"x-ratelimit-limit-audio-seconds": "3600"})
        self.assertIn("x-ratelimit-limit-audio-seconds", ligne["inconnus"])

    def test_les_jetons_se_mesurent_aussi(self):
        p = config.PROVIDERS_BY_NAME["groq"]
        ligne = self._auditer({
            "x-ratelimit-limit-tokens": str(p.quota("standard").tpm),
            "x-ratelimit-reset-tokens": "45s",
        }, fournisseur="groq")
        jetons = next(m for m in ligne["mesures"] if m["genre"] == "jetons")
        self.assertEqual(jetons["verdict"], "accorde")
        self.assertEqual(jetons["correspond"], "jetons par minute")

    def test_l_audit_se_retire_de_sa_propre_mesure(self):
        """Il consomme ce qu'il mesure.

        Premier passage sur un vrai compte : « 333 jetons selon le service,
        0 selon l'usine — ECART ». Les 333 etaient ceux de la sonde
        elle-meme, qui ne passe volontairement pas par le compteur du
        routeur. L'audit criait a l'ecart sur sa propre requete.
        """
        p = config.PROVIDERS_BY_NAME["groq"]
        quota = p.quota("standard")

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                observe["entetes"] = {
                    "x-ratelimit-limit-tokens": str(quota.tpm),
                    "x-ratelimit-remaining-tokens": str(quota.tpm - 333),
                }
                observe["jetons"] = 333
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        jetons = next(m for m in ligne["mesures"] if m["genre"] == "jetons")
        self.assertEqual(jetons["consomme_service"], 0,
                         "l'audit se compte lui-meme comme un ecart")

    def test_le_corps_d_un_refus_est_rendu(self):
        """« HTTP 400 » ne dit pas quoi faire ; le message du service, si.

        Un fournisseur paye rendait 400, et le rapport n'en disait rien de
        plus : ni reparable, ni constatable comme irreparable.
        """
        p = config.PROVIDERS_BY_NAME["opencode"]

        def essai(prov, modele, timeout=30, observe=None):
            raise HttpErreur(400, "Bad Request",
                             corps='{"error":"model not enabled for this plan"}')

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        self.assertIn("model not enabled", ligne["detail"])


class UnRefusPorteLesEntetes(unittest.TestCase):
    """Un 429 porte justement les en-tetes les plus interessants.

    Les jeter au motif que l'appel a echoue reviendrait a ne jamais pouvoir
    verifier un quota au moment precis ou il est atteint.
    """

    def test_un_429_livre_quand_meme_ses_chiffres(self):
        p = config.PROVIDERS_BY_NAME["mistral"]

        def essai(prov, modele, timeout=30, observe=None):
            raise HttpErreur(429, "Too Many Requests", entetes={
                "x-ratelimit-limit-requests": "500",
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "12h",
            })

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["annonce"], 500)
        self.assertEqual(requetes["reste"], 0)
        # La sonde a echoue : elle n'a rien consomme a retirer.
        self.assertEqual(requetes["consomme_service"], 500)


if __name__ == "__main__":
    unittest.main()


class LeCompteurCompareDoitEtreCeluiDeLaBonneFenetre(unittest.TestCase):
    """Comparer le chiffre du service au mauvais compteur invente un ecart.

    Ce garde-fou est ne d'un defaut que la suite n'avait pas vu. Quand
    « _fenetre » a cesse de repondre « minute » pour repondre « moins d'une
    minute », le comparateur qui lisait cette valeur n'a rien casse : il est
    simplement tombe TOUJOURS dans la branche « jour ». Le chiffre par minute
    du service se comparait alors au compteur du jour de l'usine.

    Rien n'echouait, parce que le resultat restait un entier plausible — et
    c'est exactement la forme de defaut que ce depot paie le plus cher : une
    mesure fausse a l'air d'une mesure.
    """

    def _compteurs(self, correspond):
        """Quatre compteurs distincts : celui qui remonte nomme sa fenetre."""
        with mock.patch.object(diagnostic.store, "compteur_minute",
                               return_value=11), \
             mock.patch.object(diagnostic.store, "compteur_jour",
                               return_value=22), \
             mock.patch.object(diagnostic.store, "jetons_minute",
                               return_value=(33, 0)), \
             mock.patch.object(diagnostic.store, "jetons_jour",
                               return_value=44):
            return diagnostic._compte_usine(
                config.PROVIDERS_BY_NAME["groq"], "m", correspond)

    def test_chaque_fenetre_lit_son_propre_compteur(self):
        self.assertEqual(self._compteurs("requetes par minute"), 11)
        self.assertEqual(self._compteurs("requetes par jour"), 22)
        self.assertEqual(self._compteurs("jetons par minute"), 33)
        self.assertEqual(self._compteurs("jetons par jour"), 44)

    def test_sans_correspondance_on_ne_compare_a_rien(self):
        """Un chiffre annonce qu'on ne sait pas nommer n'a pas de compteur.

        Rendre un zero ici ferait passer « je ne sais pas quelle fenetre »
        pour « l'usine n'a rien consomme », donc pour un ecart maximal.
        """
        self.assertIsNone(self._compteurs(""))

    def test_l_audit_compare_bien_a_la_minute_quand_c_est_la_minute(self):
        """Le defaut se voyait de bout en bout, pas seulement en unitaire."""
        p = config.PROVIDERS_BY_NAME["groq"]
        quota = p.quota("standard")

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                observe["entetes"] = {
                    "x-ratelimit-limit-requests": str(quota.rpm),
                    "x-ratelimit-reset-requests": "7.2s",
                }
                observe["jetons"] = 0
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai), \
             mock.patch.object(diagnostic.store, "compteur_minute",
                               return_value=11), \
             mock.patch.object(diagnostic.store, "compteur_jour",
                               return_value=22):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["correspond"], "requetes par minute")
        self.assertEqual(requetes["compte_usine"], 11,
                         "le chiffre par minute a ete compare au compteur "
                         "du jour")


class UneMesureNeSeCompteJamaisNegative(unittest.TestCase):
    """Le service peut calculer « reste » avant ou apres notre propre sonde.

    Les deux conventions existent. Sur un compte neuf, la premiere donne
    « -1 consomme » une fois la sonde retiree — un chiffre qui se lit comme
    un defaut du service alors qu'il n'est qu'une convention d'en-tete.
    """

    def test_un_compte_neuf_ne_rend_pas_un_consomme_negatif(self):
        p = config.PROVIDERS_BY_NAME["groq"]
        quota = p.quota("standard")

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                # « reste » calcule AVANT notre appel : rien n'est consomme.
                observe["entetes"] = {
                    "x-ratelimit-limit-requests": str(quota.rpm),
                    "x-ratelimit-remaining-requests": str(quota.rpm),
                }
                observe["jetons"] = 0
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["consomme_service"], 0)


class LaSondeRapporteCeQuElleAConsomme(unittest.TestCase):
    """La soustraction ne vaut que si le chiffre soustrait est le bon.

    Deux mutations sont passees inapercues quand ce module s'est teste
    lui-meme : remettre « jetons = 0 » dans la sonde, et remettre le cout
    d'une requete a zero. Les deux rendaient l'audit de nouveau capable de
    crier a l'ecart sur sa propre mesure, et rien ne le disait — parce que
    tous les cas de test posaient le chiffre a la main au lieu de le faire
    produire par le code qui le lit.
    """

    def _sonder(self, charge_utile):
        p = config.PROVIDERS_BY_NAME["groq"]
        observe = {}
        import json as _json
        from usine.core import llm as module_llm
        with mock.patch("usine.core.http.requete_complete",
                        return_value=(200,
                                      _json.dumps(charge_utile).encode("utf-8"),
                                      {"x-ratelimit-limit-tokens": "6000"})):
            module_llm.essai_direct(p, "m", observe=observe)
        return observe

    def test_les_jetons_viennent_de_la_reponse_du_service(self):
        observe = self._sonder({
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 333},
        })
        self.assertEqual(observe["jetons"], 333)
        self.assertEqual(observe["entetes"]["x-ratelimit-limit-tokens"], "6000")

    def test_un_service_qui_ne_compte_pas_ne_fait_pas_tomber_la_sonde(self):
        """Certains n'envoient pas « usage ». Zero est alors la verite."""
        observe = self._sonder({"choices": [{"message": {"content": "OK"}}]})
        self.assertEqual(observe["jetons"], 0)

    def test_une_sonde_reussie_retire_sa_propre_requete(self):
        p = config.PROVIDERS_BY_NAME["groq"]
        quota = p.quota("standard")

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                # Le service a deja decompte notre appel : il en reste un de
                # moins. C'est le notre, pas un ecart a signaler.
                observe["entetes"] = {
                    "x-ratelimit-limit-requests": str(quota.rpm),
                    "x-ratelimit-remaining-requests": str(quota.rpm - 1),
                }
                observe["jetons"] = 0
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        requetes = next(m for m in ligne["mesures"] if m["genre"] == "requetes")
        self.assertEqual(requetes["consomme_service"], 0,
                         "l'audit compte sa propre requete comme un ecart")


class LeMessageDuServiceEstExtraitDeSonEnveloppe(unittest.TestCase):
    """Cinq corps d'erreur RELEVES sur un vrai compte le 15/09/2026.

    Ils n'ont aucune forme commune : « message » a la racine chez Cerebras et
    Mistral, « error.message » chez OpenCode et GitHub, du texte brut chez
    Pollinations. Tronques a cent cinquante signes, quatre sur cinq perdaient
    leur fin — et chez Pollinations, la fin etait le LIEN qui permet de
    relever le budget, donc le seul geste a faire.
    """

    CAS = (
        ('{"message":"Payment required to access this resource. Visit your '
         'billing tab.","type":"payment_required_error","param":"quota"}',
         "Payment required to access this resource. Visit your billing tab."),
        ('{"object":"error","message":"Rate limit exceeded",'
         '"type":"rate_limited","code":"1300"}', "Rate limit exceeded"),
        ('{"type":"error","error":{"type":"MissingSessionID","message":'
         '"Request is missing x-opencode-session and cannot be routed"}}',
         "Request is missing x-opencode-session and cannot be routed"),
        ('{"error":{"code":"github_models_retirement_brownout","message":'
         '"GitHub Models is temporarily unavailable."}}',
         "GitHub Models is temporarily unavailable."),
    )

    def test_les_quatre_enveloppes_rencontrees_se_defont(self):
        for corps, attendu in self.CAS:
            self.assertEqual(diagnostic._message_lisible(corps), attendu)

    def test_ce_qui_n_est_pas_du_json_est_rendu_tel_quel(self):
        """Pollinations repond en texte. Vouloir faire mieux le perdrait."""
        brut = ("The API key used for this request has reached its budget. "
                "Please [raise the key budget](https://enter.pollinations.ai"
                "/edit-key?id=89idjaTSg2hI4YwZDuO8)")
        self.assertEqual(diagnostic._message_lisible(brut), brut)

    def test_un_json_sans_message_connu_est_rendu_tel_quel(self):
        """Rater une extraction plutot que rendre une chaine vide : une
        enveloppe lisible vaut mieux qu'un silence."""
        corps = '{"statut":"refuse","raison_interne":42}'
        self.assertEqual(diagnostic._message_lisible(corps), corps)

    def test_le_lien_survit_a_la_mise_en_page(self):
        """Coupe sur son trait d'union, il n'est plus cliquable — et c'est
        exactement ce qu'a fait la premiere version du pliage."""
        import textwrap
        brut = ("Please [raise the key budget](https://enter.pollinations.ai"
                "/edit-key?id=89idjaTSg2hI4YwZDuO8)")
        lignes = textwrap.wrap(brut, 68, break_on_hyphens=False,
                               break_long_words=False)
        self.assertTrue(any("edit-key?id=89idjaTSg2hI4YwZDuO8" in l
                            for l in lignes), lignes)


class LaSondeSeCompteEnReservation(unittest.TestCase):
    """Un service qui RESERVE debite plus que ce qu'il produit.

    Mesure du 15/09/2026 sur un vrai compte Groq : seau plein a 8000,
    « remaining » a 7667 juste apres la sonde, soit 333 debites — alors que
    la reponse annoncait 116 jetons produits. 333 est exactement l'invite
    (77) plus le plafond demande (256).

    Soustraire les 116 laissait donc 217 « consommes par quelqu'un d'autre »,
    et le rapport criait a l'ecart sur sa propre requete, a chaque execution.
    C'est la meme faute que la premiere fois, d'un cran plus fin : l'audit se
    retirait de sa mesure, mais pas au bon tarif.
    """

    def _mesurer(self, produit, sortie, plafond, reste):
        p = config.PROVIDERS_BY_NAME["groq"]
        quota = p.quota("standard")

        def essai(prov, modele, timeout=30, observe=None):
            if observe is not None:
                observe["entetes"] = {
                    "x-ratelimit-limit-tokens": str(quota.tpm),
                    "x-ratelimit-remaining-tokens": str(reste),
                }
                observe["jetons"] = produit
                observe["jetons_sortie"] = sortie
                observe["plafond_demande"] = plafond
            return "OK"

        with mock.patch.object(diagnostic.config, "active_providers",
                               return_value=[p]), \
             mock.patch("usine.core.llm.essai_direct", side_effect=essai):
            ligne = diagnostic.auditer_quotas()["lignes"][0]
        return next(m for m in ligne["mesures"] if m["genre"] == "jetons")

    def test_les_chiffres_reels_du_15_09_ne_rendent_plus_d_ecart(self):
        mesure = self._mesurer(produit=116, sortie=39, plafond=256, reste=7667)
        self.assertEqual(mesure["consomme_service"], 0)

    def test_un_service_qui_ne_reserve_pas_est_compte_au_reel(self):
        """Tous ne reservent pas. Facturer la reservation partout inventerait
        un ecart en sens inverse, ce qui ne vaut pas mieux."""
        mesure = self._mesurer(produit=116, sortie=39, plafond=0, reste=7884)
        self.assertEqual(mesure["consomme_service"], 0)

    def test_une_consommation_venue_d_ailleurs_reste_visible(self):
        """Le but n'est pas de faire disparaitre tout ecart : un appel fait
        depuis une autre machine avec la meme cle doit encore se voir."""
        mesure = self._mesurer(produit=116, sortie=39, plafond=256,
                               reste=7667 - 500)
        self.assertEqual(mesure["consomme_service"], 500)

    def test_la_sonde_releve_vraiment_ces_deux_chiffres(self):
        """Poses a la main, ils ne prouveraient rien : ils doivent venir de
        la reponse du service et du plafond reellement demande."""
        import json as _json
        from usine.core import llm as module_llm
        p = config.PROVIDERS_BY_NAME["groq"]
        observe = {}
        with mock.patch("usine.core.http.requete_complete",
                        return_value=(200, _json.dumps({
                            "choices": [{"message": {"content": "OK"}}],
                            "usage": {"prompt_tokens": 77,
                                      "completion_tokens": 39,
                                      "total_tokens": 116},
                        }).encode("utf-8"), {})):
            module_llm.essai_direct(p, "m", observe=observe)
        self.assertEqual(observe["jetons"], 116)
        self.assertEqual(observe["jetons_sortie"], 39)
        self.assertEqual(observe["plafond_demande"], min(256, p.max_sortie))
