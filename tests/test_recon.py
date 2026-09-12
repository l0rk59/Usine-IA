"""Reconnaissance et audit de surface : ce qu'on lit, et ce qu'on refuse.

Aucun appel reseau reel : la couche HTTP est remplacee par des reponses
figees. L'enjeu de ces tests n'est pas seulement que l'outil trouve des
choses, mais qu'il tienne la ligne — rester passif sans autorisation, ne
jamais pretendre auditer une surface qu'il n'a pas touchee.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import recon  # noqa: E402


def setUpModule():
    """Cette suite travaille dans son propre atelier."""
    atelier.isoler("recon")


def _doh(reponses):
    """Fabrique un faux DNS-sur-HTTPS a partir d'un dictionnaire type->valeurs."""
    def faux(nom, type_):
        cle = (nom, type_)
        valeurs, ad = reponses.get(cle, ([], False))
        return valeurs, ad
    return faux


class TestNormalisation(unittest.TestCase):

    def test_une_url_devient_un_domaine_nu(self):
        self.assertEqual(
            recon.normaliser_domaine("https://www.Exemple.com/a/b?x=1"),
            "exemple.com")

    def test_le_port_et_le_www_sont_retires(self):
        self.assertEqual(recon.normaliser_domaine("Exemple.FR:8443"), "exemple.fr")

    def test_une_saisie_invalide_est_rejetee_sans_reseau(self):
        rapport = recon.auditer("ceci n'est pas un domaine")
        self.assertTrue(rapport.erreurs)
        self.assertEqual(rapport.constats, [])
        self.assertTrue(rapport.passif_seul)


class TestLigne(unittest.TestCase):
    """La distinction passif / surface EST la ligne legale."""

    def test_sans_autorisation_la_surface_n_est_jamais_touchee(self):
        appels = []

        def espion(*a, **k):
            appels.append(a)
            raise AssertionError("requete_complete appelee sans autorisation")

        with mock.patch.object(recon, "_doh", _doh({})), \
                mock.patch.object(recon, "sous_domaines", lambda d: ([], "")), \
                mock.patch.object(recon, "requete_complete", espion):
            rapport = recon.auditer("exemple.com", autorise=False)

        self.assertEqual(appels, [], "la cible a ete contactee sans accord")
        self.assertTrue(rapport.passif_seul)
        self.assertTrue(any(c.titre == "Surface non auditee"
                            for c in rapport.constats))

    def test_le_rapport_dit_quand_il_n_a_pas_regarde_la_surface(self):
        with mock.patch.object(recon, "_doh", _doh({})), \
                mock.patch.object(recon, "sous_domaines", lambda d: ([], "")):
            rapport = recon.auditer("exemple.com", autorise=False)
        constat = next(c for c in rapport.constats
                       if c.titre == "Surface non auditee")
        self.assertIn("bug bounty", constat.detail.lower())


class TestCourriel(unittest.TestCase):
    """Le constat qui rapporte le plus dans une divulgation."""

    def test_aucun_dmarc_est_grave_et_explique(self):
        reponses = {("exemple.com", "TXT"): (["v=spf1 include:_spf.exemple.com -all"], True),
                    ("_dmarc.exemple.com", "TXT"): ([], True)}
        with mock.patch.object(recon, "_doh", _doh(reponses)):
            constats = recon.courriel("exemple.com")
        dmarc = next(c for c in constats if "DMARC" in c.titre)
        self.assertEqual(dmarc.gravite, "grave")
        self.assertIn("usurpable", dmarc.detail)

    def test_un_domaine_bien_configure_ne_declenche_rien_de_grave(self):
        reponses = {
            ("exemple.com", "TXT"): (["v=spf1 -all"], True),
            ("_dmarc.exemple.com", "TXT"): (["v=DMARC1; p=reject"], True),
        }
        with mock.patch.object(recon, "_doh", _doh(reponses)):
            constats = recon.courriel("exemple.com")
        self.assertFalse([c for c in constats if c.gravite == "grave"])
        self.assertTrue([c for c in constats
                         if c.domaine == "courriel" and c.gravite == "ok"])

    def test_dnssec_absent_est_signale(self):
        reponses = {("exemple.com", "TXT"): (["v=spf1 -all"], False),
                    ("_dmarc.exemple.com", "TXT"): (["v=DMARC1; p=reject"], False)}
        with mock.patch.object(recon, "_doh", _doh(reponses)):
            constats = recon.courriel("exemple.com")
        self.assertTrue(any("DNSSEC" in c.titre for c in constats))


class TestSurface(unittest.TestCase):
    """Une seule requete, et ce qu'on lit dedans."""

    def _surface(self, entetes, git_head=b"", contact=b""):
        def faux(url, timeout=15):
            if url.endswith("/.git/HEAD"):
                return (200 if git_head else 404), {}, git_head
            if "security.txt" in url:
                return (200 if contact else 404), {}, contact
            return 200, entetes, b"<html></html>"
        return faux

    def test_les_entetes_manquants_sont_signales_avec_leur_gravite(self):
        entetes = {"server": "nginx"}          # aucun en-tete de securite
        with mock.patch.object(recon, "requete_complete", self._surface(entetes)), \
                mock.patch.object(recon, "_certificat", lambda d: ({}, "")):
            constats = recon.surface("exemple.com")
        titres = {c.titre for c in constats}
        self.assertIn("En-tete manquant : strict-transport-security", titres)
        self.assertIn("En-tete manquant : content-security-policy", titres)
        hsts = next(c for c in constats if "strict-transport" in c.titre)
        self.assertEqual(hsts.gravite, "grave")

    def test_csf_avec_frame_ancestors_couvre_x_frame_options(self):
        entetes = {"strict-transport-security": "max-age=63072000",
                   "content-security-policy": "frame-ancestors 'none'",
                   "x-content-type-options": "nosniff",
                   "referrer-policy": "no-referrer"}
        with mock.patch.object(recon, "requete_complete", self._surface(entetes)), \
                mock.patch.object(recon, "_certificat",
                                  lambda d: ({"version_tls": "TLSv1.3",
                                              "emetteur": "Test CA",
                                              "expire": ""}, "")):
            constats = recon.surface("exemple.com")
        self.assertFalse([c for c in constats
                          if "x-frame-options" in c.titre],
                         "frame-ancestors dans la CSP doit suffire")

    def test_un_depot_git_expose_est_grave(self):
        entetes = {"strict-transport-security": "x", "content-security-policy": "x",
                   "x-content-type-options": "x", "x-frame-options": "x",
                   "referrer-policy": "x"}
        surface = self._surface(entetes, git_head=b"ref: refs/heads/main\n")
        with mock.patch.object(recon, "requete_complete", surface), \
                mock.patch.object(recon, "_certificat",
                                  lambda d: ({"version_tls": "TLSv1.3"}, "")):
            constats = recon.surface("exemple.com")
        git = next(c for c in constats if ".git" in c.titre)
        self.assertEqual(git.gravite, "grave")

    def test_une_version_de_serveur_chiffree_est_signalee(self):
        entetes = {"strict-transport-security": "x", "content-security-policy": "x",
                   "x-content-type-options": "x", "x-frame-options": "x",
                   "referrer-policy": "x", "server": "Apache/2.4.29"}
        with mock.patch.object(recon, "requete_complete", self._surface(entetes)), \
                mock.patch.object(recon, "_certificat",
                                  lambda d: ({"version_tls": "TLSv1.3"}, "")):
            constats = recon.surface("exemple.com")
        self.assertTrue(any("Version du serveur" in c.titre for c in constats))


class TestRapportDivulgation(unittest.TestCase):
    """Le texte doit dire quoi corriger, jamais comment exploiter."""

    def _rapport(self):
        r = recon.Rapport(cible="exemple.com", passif_seul=False,
                          contact="mailto:security@exemple.com")
        r.constats = [
            recon.Constat("grave", "courriel", "Aucun DMARC",
                          "L'e-mail du domaine est usurpable."),
            recon.Constat("moyen", "entetes", "En-tete manquant : content-security-policy",
                          "Rien ne limite les scripts."),
            recon.Constat("ok", "tls", "TLS : TLSv1.3"),
        ]
        return r

    def test_le_rapport_est_adresse_au_bon_contact(self):
        texte = recon.rapport_divulgation(self._rapport(), chercheur="Alex")
        self.assertIn("security@exemple.com", texte)
        self.assertIn("Alex", texte)

    def test_le_rapport_classe_par_priorite_et_reste_courtois(self):
        texte = recon.rapport_divulgation(self._rapport())
        self.assertIn("Prioritaire", texte)
        self.assertIn("Aucun DMARC", texte)
        self.assertIn("divulgation responsable", texte)
        # Il ne doit jamais decrire une exploitation.
        for interdit in ("payload", "exploit", "curl -", "sqlmap"):
            self.assertNotIn(interdit, texte.lower())

    def test_un_domaine_sain_donne_une_bonne_nouvelle(self):
        r = recon.Rapport(cible="exemple.com")
        r.constats = [recon.Constat("ok", "courriel", "DMARC actif (p=reject)")]
        texte = recon.rapport_divulgation(r)
        self.assertIn("Bonne nouvelle", texte)


class TestScore(unittest.TestCase):

    def test_le_score_baisse_avec_la_gravite(self):
        r = recon.Rapport(cible="x")
        self.assertEqual(r.score, 100)
        r.constats = [recon.Constat("grave", "x", "a"),
                      recon.Constat("moyen", "x", "b")]
        self.assertEqual(r.score, 100 - 25 - 12)

    def test_le_score_ne_descend_jamais_sous_zero(self):
        r = recon.Rapport(cible="x")
        r.constats = [recon.Constat("grave", "x", str(i)) for i in range(10)]
        self.assertEqual(r.score, 0)


if __name__ == "__main__":
    unittest.main()
