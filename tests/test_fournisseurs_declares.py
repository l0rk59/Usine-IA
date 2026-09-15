"""Ce qu'une fiche de fournisseur doit tenir pour ne pas mentir.

Les fiches de « core/config.py » sont de la donnee RECOPIEE : identifiants de
modeles, plafonds, adresses. C'est la donnee la plus perissable du depot, et
son pourrissement est silencieux — une cle valide qui ne sert a rien.

Le cas d'ecole est arrive le 13/09/2026 : NVIDIA servait 82 modeles, et aucun
des deux configures. Chaque appel rendait 404, le routeur mettait le
fournisseur au repos une demi-heure, et rien ne disait pourquoi.

Deux garde-fous en sont sortis. « core/modeles.py » relit le catalogue vivant
et substitue. Et ces controles-ci, qui verifient ce qu'une fiche PROMET —
pas ce qu'elle contient.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import config  # noqa: E402

SOURCE = (RACINE / "usine" / "core" / "config.py").read_text(encoding="utf-8")


def setUpModule():
    atelier.isoler("fournisseurs-declares")


class ChaqueFicheEstUtilisable(unittest.TestCase):

    def test_chaque_fournisseur_a_une_adresse_et_un_role_standard(self):
        """Sans « standard », le routeur n'a rien a demander : c'est le role
        que prennent les chaines qui ne precisent rien."""
        for fournisseur in config.PROVIDERS:
            with self.subTest(fournisseur=fournisseur.name):
                self.assertTrue(fournisseur.base_url.startswith("http")
                                or fournisseur.local,
                                "adresse absente ou invalide")
                self.assertIn("standard", fournisseur.models)

    def test_aucun_role_invente(self):
        """Un role qu'aucun agent ne demande est du reglage mort ; un role
        qu'un agent demande et qu'aucun fournisseur ne sert se resout en
        silence sur « standard », et le modele special n'est jamais appele."""
        from usine.core import prompts

        demandes = {fiche["role_modele"] for fiche in prompts.AGENTS_DEFAUT.values()}
        servis = {role for f in config.PROVIDERS for role in f.models}
        self.assertEqual(demandes - servis, set(),
                         "des agents demandent un role que personne ne sert")

    def test_chaque_fournisseur_distant_dit_ou_obtenir_une_cle(self):
        """« usine docteur » affiche ce lien quand la cle manque. Sans lui, le
        message dit « definir X_API_KEY » et laisse chercher."""
        for fournisseur in config.PROVIDERS:
            if fournisseur.local or fournisseur.keyless:
                continue
            with self.subTest(fournisseur=fournisseur.name):
                self.assertTrue(fournisseur.signup,
                                "aucune adresse pour obtenir une cle")

    def test_les_noms_de_variables_d_environnement_sont_dans_le_modele(self):
        """Une cle qu'on ne sait pas ou coller n'existe pas. « .env.exemple »
        est le seul endroit ou l'utilisateur les voit toutes."""
        modele = (RACINE / ".env.exemple").read_text(encoding="utf-8")
        for fournisseur in config.PROVIDERS:
            if fournisseur.local or not fournisseur.api_key_env:
                continue
            with self.subTest(fournisseur=fournisseur.name):
                self.assertIn(fournisseur.api_key_env, modele,
                              "« {} » n'apparait pas dans .env.exemple"
                              .format(fournisseur.api_key_env))


class LaDonneeRecopiePorteSaDate(unittest.TestCase):
    """« Un quota recopie d'un fournisseur porte sa date de verification en
    commentaire. » C'est une regle du depot, et elle ne vaut que si on la
    verifie."""

    DATE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

    @staticmethod
    def _bloc(nom):
        """La fiche d'un fournisseur, du « name= » au « Provider( » suivant."""
        debut = SOURCE.index('name="{}"'.format(nom))
        suite = SOURCE.find("    Provider(", debut)
        return SOURCE[debut:suite if suite != -1 else len(SOURCE)]

    def test_chaque_fiche_relevee_porte_sa_propre_date(self):
        """Dans SA fiche, pas quelque part dans le fichier.

        Une premiere version cherchait une date n'importe ou dans
        « config.py ». Elle passait donc tant qu'UNE seule fiche en portait
        une — et les autres pouvaient vieillir sans que rien ne le dise,
        abritees par la date de leur voisine. C'est la meme erreur que
        chercher un nom « quelque part dans le code ».

        La deuxieme version ne regardait que DEUX fiches, nommees en dur, sur
        onze. Audit du 15/09/2026 : quatre fournisseurs distants portaient des
        quotas sans aucune date — mistral, github et pollinations n'avaient
        meme pas de source, et cerebras citait la sienne sans dire quand. Un
        garde-fou dont la portee est une liste ecrite a la main vieillit des
        qu'on ajoute une ligne ailleurs. Il lit donc la liste des
        fournisseurs, qui est la seule source.
        """
        verifiees = 0
        for fournisseur in config.PROVIDERS:
            # Un fournisseur LOCAL ne recopie rien : « 600 par minute » sur
            # ollama veut dire « autant que le telephone en supporte ». Ce
            # n'est pas un chiffre pris chez quelqu'un, et exiger une date la
            # serait un garde-fou qui crie a tort.
            if fournisseur.local:
                continue
            verifiees += 1
            with self.subTest(fournisseur=fournisseur.name):
                self.assertTrue(
                    self.DATE.search(self._bloc(fournisseur.name)),
                    "la fiche « {} » recopie des identifiants et des quotas "
                    "sans dire quand ils ont ete releves".format(
                        fournisseur.name))
        # Le compte, parce qu'un detecteur vert ne se garde pas lui-meme.
        # Une campagne de mutation a montre qu'on pouvait reduire la boucle
        # ci-dessus a deux fournisseurs sans qu'un seul test bronche : c'est
        # exactement la panne d'origine, et elle survivait a sa propre
        # correction. Les deux comptes viennent de la meme liste mais pas du
        # meme chemin — restreindre la boucle fait diverger l'un sans l'autre.
        self.assertEqual(
            verifiees, sum(1 for p in config.PROVIDERS if not p.local),
            "le controle n'a regarde que {} fiche(s) distante(s) : sa portee "
            "a ete retrecie".format(verifiees))

    def test_opencode_dit_qu_il_n_a_pas_de_catalogue(self):
        """Le seul fournisseur de la liste sans endpoint « /v1/models ».

        Cela change le comportement du depot : « core/modeles.py » ne pourra
        pas rattraper un identifiant renomme chez lui. Ce n'est pas un defaut
        — le routeur signalera un 404 nomme, ce qui vaut mieux qu'un chapitre
        ecrit par un modele d'embeddings — mais quelqu'un qui l'ignore
        cherchera longtemps pourquoi la substitution automatique ne joue pas.
        """
        fiche = next((f for f in config.PROVIDERS if f.name == "opencode"), None)
        self.assertIsNotNone(fiche, "le fournisseur opencode a disparu")
        bloc = SOURCE[SOURCE.index('name="opencode"'):]
        bloc = bloc[:bloc.index("    Provider(", 10)] if "    Provider(" in bloc[10:] else bloc
        self.assertIn("/v1/models", bloc,
                      "rien ne dit que ce fournisseur n'a pas de catalogue")


if __name__ == "__main__":
    unittest.main()
