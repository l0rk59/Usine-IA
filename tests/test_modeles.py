"""Choisir un modele dans le catalogue que le fournisseur sert vraiment.

Le defaut garde ici etait entierement silencieux, et il touchait un vrai
utilisateur avec une vraie cle. Releve du 13/09/2026 sur « GET /v1/models » :

    NVIDIA     configure meta/llama-3.1-8b et meta/llama-3.3-70b ;
               sert 82 modeles, dont aucun des deux.
    OpenRouter configure llama-3.3-70b:free et deepseek-chat-v3:free ;
               sert 19 modeles « :free », dont aucun des deux.

Chaque appel rendait 404. Le routeur en tirait « modele inconnu » et mettait
le fournisseur au repos une demi-heure : une cle valide ne servait a rien, et
rien ne disait pourquoi.

Recopier les bons identifiants aurait repare la panne du jour et pas celle du
mois suivant. Les catalogues de ce fichier sont donc des RELEVES REELS, gardes
tels quels dans « tests/donnees », et les tests portent sur la capacite a
choisir dedans — pas sur les identifiants eux-memes.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config, modeles  # noqa: E402

DONNEES = json.loads(
    (RACINE / "tests" / "donnees" / "catalogues-fournisseurs.json")
    .read_text(encoding="utf-8"))
CATALOGUES = DONNEES["catalogues"]

ROLES = ("rapide", "standard", "costaud", "long", "creatif", "code",
         "raisonnement")


def setUpModule():
    atelier.isoler("modeles")


class ChoisirDansUnCatalogueReel(unittest.TestCase):

    def test_chaque_role_trouve_un_modele_chez_chaque_fournisseur(self):
        for nom, liste in CATALOGUES.items():
            for role in ROLES:
                with self.subTest(fournisseur=nom, role=role):
                    self.assertIn(modeles.choisir(liste, role), liste)

    def test_un_modele_qui_ne_sait_pas_ecrire_n_est_jamais_choisi(self):
        """Le pire cas de substitution, parce qu'il ne leve rien.

        Un modele d'embeddings ou un classificateur de securite appele en
        redaction ne rend pas d'erreur : il rend un vecteur, une phrase vide
        ou du bruit. Le chapitre est incomprehensible et tout le reste de la
        chaine le traite comme du texte.
        """
        for nom, liste in CATALOGUES.items():
            for role in ROLES:
                with self.subTest(fournisseur=nom, role=role):
                    choisi = modeles.choisir(liste, role).lower()
                    for interdit in ("embed", "guard", "safety", "rerank",
                                     "parse", "translate", "clip", "reward",
                                     "detector", "diffusion"):
                        self.assertNotIn(interdit, choisi)

    def test_la_fiction_va_sur_un_modele_qui_ecrit(self):
        """NVIDIA sert « writer/palmyra-creative-122b », qui existe pour cela.

        Sans le role, le roman partait sur le modele de redaction generale,
        et aucun test ne pouvait faire la difference.
        """
        self.assertIn("creative",
                      modeles.choisir(CATALOGUES["nvidia"], "creatif").lower())

    def test_le_code_va_sur_un_modele_de_code(self):
        choisi = modeles.choisir(CATALOGUES["nvidia"], "code").lower()
        self.assertTrue("codestral" in choisi or "code" in choisi, choisi)

    def test_un_raisonneur_ne_prend_pas_le_role_rapide(self):
        """Un « rapide » qui reflechit trois cents jetons avant de rendre un
        titre n'a de rapide que le nom — et c'est le plafond de jetons par
        minute qui est la vraie contrainte de l'usine.

        Le cas se produit reellement : chez OpenRouter, le seul modele dont le
        nom contient « nano » est un modele de raisonnement.
        """
        rapide = modeles.choisir(CATALOGUES["openrouter"], "rapide").lower()
        self.assertNotIn("reasoning", rapide)
        self.assertIn("reasoning",
                      modeles.choisir(CATALOGUES["openrouter"],
                                      "raisonnement").lower())

    def test_un_modele_encore_servi_n_est_jamais_remplace(self):
        """On ne change pas un modele qui marche."""
        liste = CATALOGUES["nvidia"]
        self.assertEqual(
            modeles.choisir(liste, "standard", prefere="google/gemma-4-31b-it"),
            "google/gemma-4-31b-it")

    def test_un_catalogue_vide_ne_rend_rien_plutot_que_n_importe_quoi(self):
        """Mieux vaut une panne nommee qu'un chapitre ecrit par un hasard."""
        self.assertEqual(modeles.choisir([], "standard"), "")
        self.assertEqual(modeles.choisir(["nvidia/embed-qa-4"], "standard"), "")


class ConfigurationAJour(unittest.TestCase):
    """Ce que le depot configure doit exister chez le fournisseur.

    Ce test ne sort pas sur le reseau : il compare a un releve date. Il
    vieillira — c'est voulu, et c'est le but. Le jour ou il echoue, le releve
    est a refaire, ce qui est exactement le moment ou il faut le refaire.
    """

    def test_les_modeles_configures_sont_servis(self):
        for nom, liste in CATALOGUES.items():
            fournisseur = config.PROVIDERS_BY_NAME[nom]
            for role, modele in fournisseur.models.items():
                with self.subTest(fournisseur=nom, role=role):
                    self.assertIn(
                        modele, liste,
                        "« {} » n'est plus servi par {} (releve du {}). "
                        "Refaites le releve : skill « fournisseurs »."
                        .format(modele, nom, DONNEES["releve_le"]))

    def test_chaque_role_declare_est_un_role_connu(self):
        """Un role invente se resout en silence sur « standard ».

        Il n'echoue nulle part : « model_for » retombe sur standard, et le
        modele special qu'on croyait avoir configure n'est jamais appele.
        """
        for fournisseur in config.PROVIDERS:
            for role in fournisseur.models:
                with self.subTest(fournisseur=fournisseur.name, role=role):
                    self.assertIn(role, ROLES)

    def test_chaque_role_declare_est_demande_quelque_part(self):
        """Un modele configure que personne ne demande est un reglage orphelin.

        La regle du depot vaut aussi pour les roles : declarer « creatif »
        sans qu'aucune chaine ne le demande revient a promettre un modele
        special pour la fiction et a ne jamais l'appeler.
        """
        code = "\n".join(f.read_text(encoding="utf-8")
                         for f in (RACINE / "usine").rglob("*.py"))
        declares = {r for f in config.PROVIDERS for r in f.models}
        for role in sorted(declares):
            with self.subTest(role=role):
                self.assertIn('"{}"'.format(role), code,
                              "le role « {} » est configure et jamais demande"
                              .format(role))


class Substitution(unittest.TestCase):

    def setUp(self):
        modeles.oublier()

    def tearDown(self):
        modeles.oublier()

    def _fournisseur(self):
        return config.PROVIDERS_BY_NAME["nvidia"]

    def test_sans_catalogue_lisible_on_ne_substitue_pas(self):
        """« je ne sais pas » n'est pas « n'importe lequel ».

        Sans reseau ni cle, substituer a l'aveugle ferait appeler un modele au
        hasard. On rend "" et le routeur signale le 404, ce qui est la bonne
        reponse.
        """
        vrai = modeles.interroger
        modeles.interroger = lambda f, timeout=10: None
        try:
            self.assertEqual(
                modeles.substituer(self._fournisseur(), "standard", "x"), "")
        finally:
            modeles.interroger = vrai

    def test_la_substitution_exclut_le_modele_refuse(self):
        """Sinon on retombe dessus indefiniment.

        Un fournisseur peut lister un modele et ne plus le servir : le
        catalogue dit oui, l'appel dit 404, et sans exclusion la boucle est
        infinie.
        """
        liste = list(CATALOGUES["nvidia"])
        refuse = modeles.choisir(liste, "standard")
        vrai = modeles.interroger
        modeles.interroger = lambda f, timeout=10: liste
        try:
            remplacant = modeles.substituer(self._fournisseur(), "standard", refuse)
        finally:
            modeles.interroger = vrai
        self.assertTrue(remplacant)
        self.assertNotEqual(remplacant, refuse)

    def test_la_substitution_est_retenue_pour_les_appels_suivants(self):
        """Sans memoire, chaque appel refait le meme 404, la meme
        interrogation du catalogue et le meme choix — trois fois par chapitre.
        """
        fournisseur = self._fournisseur()
        modeles.retenir(fournisseur.name, "standard", "un/modele-de-secours")
        self.assertEqual(modeles.modele_effectif(fournisseur, "standard"),
                         "un/modele-de-secours")
        self.assertIn("nvidia / standard", modeles.substitutions())

    def test_sans_substitution_on_appelle_ce_qui_est_configure(self):
        fournisseur = self._fournisseur()
        self.assertEqual(modeles.modele_effectif(fournisseur, "creatif"),
                         fournisseur.models["creatif"])


class LeRouteurEtLesChainesDemandentBienCesRoles(unittest.TestCase):
    """Un module de choix parfait qui n'est branche nulle part ne choisit rien.

    Ces cas passent par le vrai chemin : une reponse HTTP fabriquee ici pour
    le routeur, une fabrication complete pour les chaines.
    """

    def setUp(self):
        atelier.isoler("modeles-branchement")
        modeles.oublier()

    def tearDown(self):
        from usine.core import llm

        llm.definir_simulateur(None)
        modeles.oublier()

    @staticmethod
    def _reponse_ok(contenu="Un paragraphe en francais avec de la matiere."):
        return {"choices": [{"message": {"content": contenu},
                             "finish_reason": "stop"}],
                "usage": {"total_tokens": 10}}

    def test_l_appel_utilise_la_substitution_retenue(self):
        from unittest import mock

        from usine.core import llm

        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        modeles.retenir("nvidia", "standard", "un/remplacant")
        with mock.patch("usine.core.llm.post_json",
                        return_value=self._reponse_ok()) as poste:
            llm._appel(fournisseur, [{"role": "user", "content": "x"}],
                       "standard", 0.7, 200, False, 30, None)
        envoye = poste.call_args[0][1]
        self.assertEqual(envoye["model"], "un/remplacant")

    def test_un_404_fait_changer_de_modele_au_lieu_d_ecarter_le_fournisseur(self):
        """Le defaut vecu par un utilisateur avec une vraie cle NVIDIA.

        Les deux modeles configures n'etaient plus servis : chaque appel
        rendait 404, le routeur mettait NVIDIA au repos une demi-heure, et la
        cle ne servait a rien.
        """
        from unittest import mock

        from usine.core import llm
        from usine.core.http import HttpErreur

        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        servis = list(CATALOGUES["nvidia"])
        vrai_interroger = modeles.interroger
        modeles.interroger = lambda f, timeout=10: servis

        appels = {"n": 0}

        def poster(url, charge, entetes=None, timeout=60):
            appels["n"] += 1
            if charge["model"] == fournisseur.models["standard"]:
                raise HttpErreur(404, "model not found")
            return self._reponse_ok()

        # Un seul fournisseur en jeu : sinon le routeur bascule sur le suivant
        # et le test ne dit plus rien sur la substitution. On remplace
        # « active_providers », pas la liste : c'est cette fonction que le
        # routeur appelle, et elle filtre selon les cles presentes.
        try:
            with mock.patch("usine.core.config.active_providers",
                            return_value=[fournisseur]), \
                 mock.patch("usine.core.llm.post_json", side_effect=poster):
                reponse = llm.generer("Ecris un paragraphe.", role="standard",
                                      cache=False)
        finally:
            modeles.interroger = vrai_interroger

        self.assertTrue(reponse.texte)
        self.assertGreaterEqual(appels["n"], 2, "il doit y avoir eu un second essai")
        self.assertNotEqual(reponse.modele, fournisseur.models["standard"])
        # Et la substitution est retenue : sans memoire, chaque appel refait
        # le meme 404, la meme interrogation et le meme choix.
        self.assertEqual(modeles.modele_effectif(fournisseur, "standard"),
                         reponse.modele)

    def _roles_demandes(self, argv):
        """Les roles que la chaine demande reellement, en la faisant tourner."""
        from tests.simulateur import simulateur
        from usine import cli
        from usine.core import llm

        vus = []

        def espion(invite, role="standard", **kw):
            vus.append(role)
            return simulateur(invite, role=role, **kw)

        llm.definir_simulateur(espion)
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(sortie):
            cli.principal(argv)
        return vus

    def test_la_fiction_demande_un_modele_qui_ecrit(self):
        roles = self._roles_demandes(["nouvelle", "un secret de famille",
                                      "--chapitres", "3"])
        self.assertIn("creatif", roles)

    def test_la_chaine_logicielle_demande_un_modele_de_code(self):
        roles = self._roles_demandes(["logiciel", "un convertisseur de devises"])
        self.assertIn("code", roles)


class ComptageDuCache(unittest.TestCase):

    def setUp(self):
        atelier.isoler("modeles-comptage")

    def test_un_catalogue_garde_n_est_pas_une_reponse_en_cache(self):
        """Sinon l'usine annonce un cache non vide a qui n'a rien fabrique —
        et « usine cache --vider » promet de liberer des reponses qui
        n'existent pas."""
        from usine.core import store

        depart = store.compter_reponses_cachees()
        store.cache_set("catalogue-modeles:essai", "[]", "catalogue", "modeles")
        store.cache_set("substitution:essai:standard", "x", "substitution", "s")
        self.assertEqual(store.compter_reponses_cachees(), depart)
        store.cache_set("une-vraie-reponse", "du texte", "essai", "modele")
        self.assertEqual(store.compter_reponses_cachees(), depart + 1)


if __name__ == "__main__":
    unittest.main()


class ModeleInconnuAutrementQueParUn404(unittest.TestCase):
    """Un identifiant perime ne s'annonce pas partout par 404.

    Le routeur savait deja remplacer un modele disparu — mais seulement quand
    le fournisseur repondait 404. Or aucun ne s'accorde sur le code :

        NVIDIA, OpenRouter   404
        Groq                 400  {"code": "model_not_found"}
        Mistral              400  {"type": "invalid_model"}
        Cerebras             422  {"detail": [{"msg": "model not found"}]}

    Mesure du 14/09/2026, en rejouant ces quatre formes contre le routeur :
    seul le 404 declenchait la substitution. Pour les trois autres, le
    fournisseur partait au repos une demi-heure, sans substitution et sans un
    mot — alors que la cle etait bonne et que le catalogue contenait de quoi
    remplacer. Trois fournisseurs sur onze ne pouvaient donc pas se remettre
    d'un identifiant vieilli, ce qui est exactement ce que decrit quelqu'un
    qui dit « beaucoup de modeles ne fonctionnent pas ».

    C'est la deuxieme des trois regles du depot, dans sa forme la plus nue :
    ne pas croire le code de retour, lire le contenu.
    """

    @staticmethod
    def _reponse_ok(contenu="Un paragraphe en francais avec de la matiere."):
        return {"choices": [{"message": {"content": contenu},
                             "finish_reason": "stop"}],
                "usage": {"total_tokens": 10}}

    FORMES = [
        (404, '{"error":{"message":"The model does not exist"}}'),
        (400, '{"error":{"message":"The model `x` does not exist",'
              '"code":"model_not_found"}}'),
        (400, '{"message":"Invalid model: x","type":"invalid_model"}'),
        (422, '{"detail":[{"msg":"model not found"}]}'),
    ]

    def test_les_quatre_formes_connues_sont_reconnues(self):
        from usine.core import llm
        from usine.core.http import HttpErreur

        for statut, corps in self.FORMES:
            self.assertTrue(
                llm._modele_inconnu(HttpErreur(statut, "refus", corps=corps)),
                "statut {} non reconnu : {}".format(statut, corps[:50]))

    def test_les_quatre_formes_font_changer_de_modele(self):
        from unittest import mock

        from usine.core import llm
        from usine.core.http import HttpErreur

        # Le fournisseur importe peu : ce qui est teste, c'est la forme de
        # la reponse. On prend celui dont le catalogue reel est en fixture.
        fournisseur = config.PROVIDERS_BY_NAME["nvidia"]
        servis = list(CATALOGUES["nvidia"])
        for statut, corps in self.FORMES:
            modeles.oublier()
            vrai = modeles.interroger
            modeles.interroger = lambda f, timeout=10: list(servis)

            def poster(url, charge, entetes=None, timeout=60, _s=statut, _c=corps):
                if charge["model"] == fournisseur.models["standard"]:
                    raise HttpErreur(_s, "refus", corps=_c)
                return self._reponse_ok()

            try:
                with mock.patch("usine.core.config.active_providers",
                                return_value=[fournisseur]), \
                     mock.patch("usine.core.llm.post_json", side_effect=poster):
                    reponse = llm.generer("Ecris.", role="standard", cache=False)
            finally:
                modeles.interroger = vrai
            self.assertNotEqual(
                reponse.modele, fournisseur.models["standard"],
                "statut {} : le routeur n'a pas substitue".format(statut))

    def test_une_panne_du_service_ne_fait_pas_changer_de_modele(self):
        """Le controle doit rater un defaut plutot que d'en inventer un.

        Un 500 ou un 503 qui contiendrait ces mots par accident parle d'une
        panne du service, pas d'un identifiant. Substituer alors changerait de
        modele pour rien et masquerait l'incident — et le remplacant tomberait
        sur la meme panne.
        """
        from usine.core import llm
        from usine.core.http import HttpErreur

        for statut in (500, 502, 503):
            self.assertFalse(
                llm._modele_inconnu(HttpErreur(
                    statut, "panne", corps='{"error":"model not found"}')),
                "un {} ne doit pas passer pour un identifiant perime".format(
                    statut))

    def test_un_refus_muet_ne_declenche_rien(self):
        """Un 400 qui ne dit pas pourquoi n'est pas un modele inconnu."""
        from usine.core import llm
        from usine.core.http import HttpErreur

        self.assertFalse(llm._modele_inconnu(
            HttpErreur(400, "Bad Request", corps='{"error":"bad temperature"}')))
        self.assertFalse(llm._modele_inconnu(HttpErreur(429, "trop vite")))
