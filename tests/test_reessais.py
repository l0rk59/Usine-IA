"""Ce que l'usine fait quand une API echoue : reessayer, et attendre entre deux.

Mesure du 15/09/2026, avant correction. Le routeur IA rejouait un appel deux
fois avec attente et basculait de fournisseur — c'etait la partie solide. Tout
le reste du reseau tentait UNE fois, sans attendre :

    images.generer_visuel        1 tentative,  0.0 s
    marche.sonder                1 tentative par source, 0.0 s
    modeles.catalogue            1 tentative,  0.0 s
    maj (telechargement)         1 tentative,  0.0 s

Et le routeur lui-meme avait un angle mort : une exception qui n'est pas une
« HttpErreur » — un JSON tronque, un corps vide, une structure inattendue —
abandonnait le fournisseur en UN essai et ZERO seconde, la ou une HttpErreur
temporaire valait deux essais et six secondes.

Une coupure d'une seconde sur un forfait mobile perdait donc une illustration
pour de bon, et le journal annoncait « 0 image(s) sur 14 » sans dire pourquoi.

AUCUN test de ce module ne sort sur le reseau : la panne est injectee.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("reessais")


from usine.core import config, http, images, llm, maj, marche, modeles  # noqa: E402


class Panne:
    """Echoue « fois » fois, puis rend « valeur ». Compte les appels."""

    def __init__(self, exception, fois=99, valeur=None):
        self.exception, self.fois, self.valeur = exception, fois, valeur
        self.appels = 0

    def __call__(self, *args, **kwargs):
        self.appels += 1
        if self.appels <= self.fois:
            raise self.exception
        return self.valeur


class SansAttendreVraiment:
    """Remplace « http.patienter » et compte les secondes demandees.

    On patche « patienter » et non « time.sleep » : patienter dort par
    tranches d'une seconde, et neutraliser time.sleep la ferait tourner a
    vide en accumulant des millions de secondes fictives. L'instrument
    mesurait alors n'importe quoi — verifie le 15/09/2026.
    """

    def __init__(self):
        self.secondes = 0.0

    def __enter__(self):
        self._vrai = http.patienter
        self._vrai_llm = llm._patienter
        http.patienter = self._noter
        llm._patienter = lambda s: self._noter(s)
        return self

    def _noter(self, secondes, arret=None):
        self.secondes += secondes
        return True

    def __exit__(self, *exc):
        http.patienter = self._vrai
        llm._patienter = self._vrai_llm
        return False


class InsisterRejoueCeQuiPeutChangerDAvis(unittest.TestCase):

    def test_une_panne_temporaire_est_rejouee_puis_levee(self):
        panne = Panne(http.HttpErreur(503, "indisponible"))
        with SansAttendreVraiment() as horloge:
            with self.assertRaises(http.HttpErreur):
                http.insister(panne)
        self.assertEqual(panne.appels, http.TENTATIVES)
        self.assertGreater(horloge.secondes, 0.0)

    def test_un_succes_au_deuxieme_essai_rend_la_valeur(self):
        panne = Panne(http.HttpErreur(503, "x"), fois=1, valeur="enfin")
        with SansAttendreVraiment():
            self.assertEqual(http.insister(panne), "enfin")
        self.assertEqual(panne.appels, 2)

    def test_l_attente_grandit_entre_deux_essais(self):
        """Revenir toutes les demi-secondes sur un service en panne ne fait
        que consommer du forfait et de la batterie."""
        attentes = []
        vrai = http.patienter
        http.patienter = lambda s, arret=None: (attentes.append(s), True)[1]
        try:
            with self.assertRaises(http.HttpErreur):
                http.insister(Panne(http.HttpErreur(503, "x")), tentatives=4)
        finally:
            http.patienter = vrai
        self.assertEqual(len(attentes), 3)
        for avant, apres in zip(attentes, attentes[1:]):
            self.assertGreater(apres, avant)

    def test_une_panne_definitive_n_est_jamais_rejouee(self):
        # Une cle refusee, un acces interdit, un modele qui n'existe pas, un
        # credit epuise : aucun ne changera d'avis en deux secondes, et
        # insister ne fait que retarder le message utile.
        for statut in (400, 401, 403, 404, 402):
            with self.subTest(statut=statut):
                panne = Panne(http.HttpErreur(statut, "non"))
                with SansAttendreVraiment() as horloge:
                    with self.assertRaises(http.HttpErreur):
                        http.insister(panne)
                self.assertEqual(panne.appels, 1)
                self.assertEqual(horloge.secondes, 0.0)

    def test_une_reponse_illisible_est_rejouee_comme_une_panne_reseau(self):
        # Un JSON tronque par une coupure n'est pas une HttpErreur, et c'est
        # pourtant la meme panne du point de vue de l'usine : le service n'a
        # rien donne d'exploitable.
        for exception in (ValueError("illisible"),
                          json.JSONDecodeError("x", "y", 0),
                          TimeoutError("delai"),
                          ConnectionResetError("reset")):
            with self.subTest(panne=type(exception).__name__):
                panne = Panne(exception)
                with SansAttendreVraiment():
                    with self.assertRaises(type(exception)):
                        http.insister(panne)
                self.assertEqual(panne.appels, http.TENTATIVES)

    def test_le_delai_demande_par_le_service_prime_sur_le_calcul(self):
        """« Retry-After » evite d'attendre dix minutes pour cinq secondes,
        et de revenir trop tot pour reprendre un 429 — qui, lui, consomme du
        quota."""
        erreur = http.HttpErreur(429, "trop vite", entetes={"Retry-After": "7"})
        attentes = []
        vrai = http.patienter
        http.patienter = lambda s, arret=None: (attentes.append(s), True)[1]
        try:
            with self.assertRaises(http.HttpErreur):
                http.insister(Panne(erreur), tentatives=2)
        finally:
            http.patienter = vrai
        self.assertEqual(len(attentes), 1)
        self.assertGreaterEqual(attentes[0], 7.0)
        self.assertLess(attentes[0], 9.0)


class LAttenteResteInterruptible(unittest.TestCase):
    """« Une boucle qui dort doit rester interruptible » — skill termux.

    Un « time.sleep(20) » d'un seul bloc fait attendre vingt secondes a un
    Ctrl+C. L'utilisateur tue alors le processus a la main, en laissant la
    base dans l'etat qu'on imagine.
    """

    def test_patienter_dort_par_tranches_d_une_seconde_au_plus(self):
        tranches = []
        vrai = time.sleep
        time.sleep = lambda s: (tranches.append(s), vrai(0))[1]
        try:
            http.patienter(3.0)
        finally:
            time.sleep = vrai
        self.assertGreater(len(tranches), 1)
        for tranche in tranches:
            self.assertLessEqual(tranche, 1.0)

    def test_une_demande_d_arret_coupe_l_attente(self):
        vrai = time.sleep
        time.sleep = lambda s: None
        try:
            self.assertFalse(http.patienter(30.0, arret=lambda: True))
        finally:
            time.sleep = vrai

    def test_le_routeur_dort_aussi_par_tranches(self):
        tranches = []
        vrai = time.sleep
        time.sleep = lambda s: (tranches.append(s), vrai(0))[1]
        try:
            llm._patienter(3.0)
        finally:
            time.sleep = vrai
        self.assertGreater(len(tranches), 1)
        for tranche in tranches:
            self.assertLessEqual(tranche, 1.0)


class ChaqueCheminReseauReessaie(unittest.TestCase):
    """Un point unique de reessai ne sert a rien si personne ne l'appelle."""

    def _compter(self, module, attribut, lancer, exception=None):
        # Le constat « le service d'images est muet » survit a l'appel qui l'a
        # pose : c'est tout son interet. Il traverse donc aussi les tests, et
        # le premier qui echoue rendait le suivant complaisant — il mesurait
        # une tentative la ou il en attendait trois, et il l'a dit.
        images._SERVICE_MUET = False
        panne = Panne(exception or http.HttpErreur(503, "indisponible"))
        vrai = getattr(module, attribut)
        setattr(module, attribut, panne)
        try:
            with SansAttendreVraiment() as horloge:
                try:
                    lancer()
                except Exception:
                    pass
        finally:
            setattr(module, attribut, vrai)
        return panne.appels, horloge.secondes

    def test_une_illustration_ne_se_perd_pas_sur_une_coupure(self):
        """Il n'y a AUCUN repli pour une illustration d'album : celle qui ne
        vient pas ne vient pas du tout, et le livre sort avec une note
        « a dessiner » a sa place."""
        import tempfile

        appels, attente = self._compter(
            images, "image_pollinations",
            lambda: images.generer_visuel(
                Path(tempfile.mkdtemp()), "p1", "un ourson"))
        self.assertEqual(appels, http.TENTATIVES)
        self.assertGreater(attente, 0.0)

    def test_la_couverture_insiste_avant_de_replier_sur_l_atelier(self):
        import tempfile

        import os

        from usine.core import reglages

        # Sans jeton, l'usine sait d'avance que l'image sortira filigranee et
        # ne la demande meme pas : le reseau n'est jamais touche, et le test
        # mesurerait zero pour une raison qui n'a rien a voir.
        reglages.ecrire({"couverture": "ia"})
        os.environ["POLLINATIONS_TOKEN"] = "jeton-de-test"
        try:
            appels, _ = self._compter(
                images, "image_pollinations",
                lambda: images.generer_couverture(
                    Path(tempfile.mkdtemp()), "Un titre", en_ligne=True))
        finally:
            os.environ.pop("POLLINATIONS_TOKEN", None)
            reglages.ecrire({"couverture": "atelier"})
        self.assertEqual(appels, http.TENTATIVES)

    def test_un_service_d_images_muet_ne_se_constate_qu_une_fois(self):
        """Quinze illustrations, une seule lecon.

        Mesure du 15/09/2026 par le chemin reel du tableau de bord, sans
        fournisseur d'images joignable : un conte prenait 83 secondes, dont
        77,5 en images. Quinze appels, chacun rejouant trois tentatives avec
        attente — les quatorze derniers rapprenaient a cinq secondes piece ce
        que le premier avait etabli.

        Les reessais restent justes pour un hoquet. C'est de les payer quinze
        fois qui ne l'est pas.
        """
        import tempfile

        images._SERVICE_MUET = False
        panne = Panne(http.HttpErreur(503, "indisponible"))
        vrai = images.image_pollinations
        images.image_pollinations = panne
        dossier = Path(tempfile.mkdtemp())
        try:
            with SansAttendreVraiment():
                for page in range(15):
                    images.generer_visuel(dossier, "p{}".format(page), "un ourson")
        finally:
            images.image_pollinations = vrai
        # Le premier appel mesure (trois tentatives), les quatorze suivants
        # tentent leur chance une fois.
        self.assertEqual(panne.appels, http.TENTATIVES + 14, (
            "{} appels pour quinze illustrations : la panne est reapprise a "
            "chaque page".format(panne.appels)))

    def test_le_service_qui_revient_est_repris_au_vol(self):
        """Le constat s'efface au premier succes : sans cela, une coupure au
        debut d'un album condamnait les treize illustrations suivantes a une
        seule tentative chacune, pour toute la duree du processus."""
        import tempfile

        images._SERVICE_MUET = False
        etat = {"appels": 0}

        def service(*a, **k):
            etat["appels"] += 1
            if etat["appels"] <= http.TENTATIVES:      # la panne du debut
                raise http.HttpErreur(503, "indisponible")
            if etat["appels"] == http.TENTATIVES + 1:  # le service revient
                return b"x" * 2048
            raise http.HttpErreur(503, "rechute")      # et retombe

        vrai = images.image_pollinations
        images.image_pollinations = service
        dossier = Path(tempfile.mkdtemp())
        try:
            with SansAttendreVraiment():
                for page in range(3):
                    images.generer_visuel(dossier, "p{}".format(page), "un ourson")
        finally:
            images.image_pollinations = vrai
        # 3 (panne) + 1 (succes, qui efface le constat) + 3 (l'insistance a
        # repris). Sans l'effacement, la derniere page n'en ferait qu'une.
        self.assertEqual(etat["appels"], http.TENTATIVES * 2 + 1)

    def test_chaque_source_du_sondage_est_rejouee(self):
        appels, attente = self._compter(
            marche, "requete", lambda: marche.sonder("la facturation"))
        # Quatre sources, deux essais chacune. Deux et non trois : un sondage
        # interroge quatre services de suite et l'utilisateur attend devant
        # son telephone.
        self.assertEqual(appels, 8)
        self.assertGreater(attente, 0.0)

    def test_le_catalogue_de_modeles_est_rejoue(self):
        """Sans catalogue, le routeur ne sait pas par quoi remplacer un modele
        disparu, et met le fournisseur au repos une demi-heure."""
        import os

        fournisseur = config.PROVIDERS_BY_NAME["groq"]
        # Sans cle, la question ne peut meme pas etre posee : « interroger »
        # rend None avant tout appel, et le test mesurerait zero pour une
        # raison qui n'a rien a voir avec les reessais.
        os.environ[fournisseur.api_key_env] = "cle-de-test"
        try:
            appels, _ = self._compter(
                http, "requete",
                lambda: modeles.catalogue(fournisseur, forcer=True))
        finally:
            os.environ.pop(fournisseur.api_key_env, None)
        self.assertEqual(appels, 2)

    def test_le_telechargement_de_mise_a_jour_est_rejoue(self):
        """Le telechargement le plus long de l'usine, donc celui qui a le plus
        de chances d'etre coupe en route."""
        appels, _ = self._compter(
            http, "get_bytes", lambda: maj.par_archive(branche="main"))
        self.assertEqual(appels, http.TENTATIVES)


def _essais_du_routeur(exception, fournisseur="ollama"):
    """Combien d'appels et combien de secondes d'attente le routeur depense
    sur un fournisseur qui leve toujours « exception »."""
    panne = Panne(exception)
    vrai_appel, vrai_ordre = llm._appel, config.provider_order
    llm._appel = panne
    # Un fournisseur LOCAL par defaut : son budget par minute est infini, donc
    # les cas s'enchainent sans que le precedent ait consomme le debit du
    # suivant. Une premiere version mesurait « 0 essai » sur les derniers cas
    # pour cette seule raison.
    config.provider_order = lambda: [fournisseur]
    llm._REPOS.clear()
    try:
        with SansAttendreVraiment() as horloge:
            try:
                llm.generer([{"role": "user", "content": "test"}],
                            cache=False)
            except Exception:
                pass
    finally:
        llm._appel, config.provider_order = vrai_appel, vrai_ordre
    return panne.appels, horloge.secondes


class LeRouteurNAbandonnePasSurUneReponseIllisible(unittest.TestCase):
    """L'angle mort mesure : deux essais pour un 503, un seul pour un JSON
    tronque — alors que du point de vue de l'usine c'est la meme panne."""

    def _essais(self, exception):
        return _essais_du_routeur(exception)

    def test_une_reponse_illisible_vaut_autant_d_essais_qu_un_503(self):
        for exception in (ValueError("illisible"),
                          json.JSONDecodeError("x", "y", 0),
                          TimeoutError("delai"),
                          ConnectionResetError("reset")):
            with self.subTest(panne=type(exception).__name__):
                essais, attente = self._essais(exception)
                self.assertEqual(essais, 2)
                self.assertGreater(attente, 0.0)

    def test_un_429_n_est_pas_rejoue_mais_met_le_fournisseur_au_repos(self):
        """Rejouer un 429 consomme du quota pour reprendre un 429. Le bon
        geste est de laisser le fournisseur tranquille et de basculer."""
        essais, _ = self._essais(http.HttpErreur(429, "trop de requetes"))
        self.assertEqual(essais, 1)


def _enveloppe_par_http(cause: BaseException) -> http.HttpErreur:
    """L'erreur exactement telle que « http » la fabrique quand urllib echoue.

    On passe par le vrai code d'enveloppe plutot que d'en construire une a la
    main : c'est lui qui accroche la cause, et c'est cette chaine que le
    routeur lit. Une imitation pourrait la porter la ou le vrai code ne la
    porte pas, et le test passerait sur une situation qui n'existe pas.
    """
    import urllib.error
    import urllib.request

    def refuser(*args, **kwargs):
        raise urllib.error.URLError(cause)

    vrai = urllib.request.urlopen
    urllib.request.urlopen = refuser
    try:
        http.requete_complete("http://127.0.0.1:11434/v1/chat/completions")
    except http.HttpErreur as exc:
        return exc
    finally:
        urllib.request.urlopen = vrai
    raise AssertionError("l'appel refuse n'a pas leve d'HttpErreur")


class UnServeurLocalEteintNeCoutePasOnzeSecondes(unittest.TestCase):
    """Mesure du 23/09/2026 : ollama eteint, chaque appel du routeur perdait
    onze secondes — deux essais par serveur local, attente entre les deux —
    parce que le refus de connexion devient « HTTP 0 », marque temporaire.

    Or c'est quand les services distants sont epuises que le routeur descend
    jusqu'au repli local : donc a chaque appel d'une fin de roman.
    """

    def test_un_refus_de_connexion_local_n_est_pas_rejoue(self):
        refus = _enveloppe_par_http(ConnectionRefusedError(111, "Connection refused"))
        self.assertEqual(refus.statut, 0)
        essais, attente = _essais_du_routeur(refus)
        self.assertEqual(essais, 1)
        self.assertEqual(attente, 0.0)

    def test_un_delai_depasse_en_local_reste_rejoue(self):
        """Le pendant : un serveur local LENT (modele en cours de chargement)
        repond peut-etre au second essai. Seul le refus est definitif."""
        lent = _enveloppe_par_http(TimeoutError("timed out"))
        self.assertEqual(lent.statut, 0)
        essais, attente = _essais_du_routeur(lent)
        self.assertEqual(essais, 2)
        self.assertGreater(attente, 0.0)

    def test_un_refus_chez_un_service_distant_reste_rejoue(self):
        """Pour un service distant, « connexion refusee » est souvent un
        telephone qui change de reseau : la seconde suivante, ca passe."""
        import os

        from usine.core import cles as pool_cles

        os.environ["GROQ_API_KEY"] = "gsk_" + "0" * 32
        pool_cles.oublier()
        try:
            refus = _enveloppe_par_http(ConnectionRefusedError(111, "Connection refused"))
            essais, attente = _essais_du_routeur(refus, fournisseur="groq")
        finally:
            os.environ.pop("GROQ_API_KEY", None)
            pool_cles.oublier()
        self.assertEqual(essais, 2)
        self.assertGreater(attente, 0.0)


if __name__ == "__main__":
    unittest.main()
