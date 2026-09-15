"""Un reglage affiche, enregistre, et jamais lu est un mensonge fait a l'utilisateur.

La regle est dans CLAUDE.md. Un test la gardait deja — mais il verifiait
qu'un reglage est ATTEIGNABLE depuis les trois interfaces, pas qu'il ARRIVE
jusqu'a la chaine qui fabrique. Les deux questions se ressemblent et n'ont
pas la meme reponse.

Mesure du 15/09/2026, en suivant chaque champ jusqu'a « fabriquer » :

    logiciel     « Ne pas executer le code »      sans effet
    idees        « Ne pas mesurer le marche »     sans effet
    idees        « Ne pas lire les discussions »  sans effet
    social       « Visuels a generer »            sans effet
    interactive  « Serie »                        sans effet
    recueil      « Serie »                        sans effet
    feuilleton   « Serie »                        sans effet

Deux causes distinctes.

Les cinq premieres : la case s'appelle « sans_marche », la chaine attend
« avec_marche ». Seule la ligne de commande faisait la traduction —
« avec_marche=not args.sans_marche ». Le serveur passait les options telles
quelles a « executer », qui ne transmet que les cles declarees dans
« options ». La case etait donc affichee, cochee, enregistree, et sans effet.
Verifie en comptant les sondages de marche : un avec la case, un sans.

Les trois dernieres : « produire » n'accepte tout simplement pas d'argument
« serie » dans ces trois chaines. Seules « nouvelle » et « roman » portent la
machinerie de tomes.
"""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402


def setUpModule():
    atelier.isoler("reglages-arrivent")


from usine.core import llm, marche  # noqa: E402
from usine.pipelines import base, catalogue, fiction  # noqa: E402
from tests import simulateur  # noqa: E402

# Le module de chaine de chaque type. Ecrit ici plutot que devine : deviner
# par le nom aurait rate « prompts » -> « pack_prompts ».
CHAINE = {"ebook": "ebook", "nouvelle": "nouvelle", "roman": "nouvelle",
          "interactive": "interactive", "recueil": "recueil",
          "feuilleton": "feuilleton", "conte": "conte",
          "prompts": "pack_prompts", "formation": "formation",
          "outils": "boite_outils", "modeles": "modeles",
          "impression": "impression", "social": "social",
          "logiciel": "logiciel", "emails": "emails", "memo": "memo",
          "quiz": "quiz", "idees": "idees"}


def _lus_sur_le_contexte(module, vus=None):
    """Les noms lus sur un contexte dans ce module et ceux qu'il importe.

    On lit l'ARBRE, et on reste dans la chaine du type. Chercher un nom
    « quelque part dans usine/ » est precisement le detecteur satisfait par
    une homonymie qui a deja laisse passer deux reglages orphelins ici.
    """
    vus = vus if vus is not None else set()
    if not module or module in vus:
        return set()
    vus.add(module)
    chemin = RACINE / "usine" / "pipelines" / (module + ".py")
    if not chemin.is_file():
        return set()
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms, imports = set(), set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Attribute) and isinstance(noeud.value, ast.Name) \
                and noeud.value.id in ("ctx", "contexte"):
            noms.add(noeud.attr)
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) \
                and noeud.func.id == "getattr" and len(noeud.args) >= 2 \
                and isinstance(noeud.args[1], ast.Constant):
            noms.add(noeud.args[1].value)
        if isinstance(noeud, ast.ImportFrom) and not (noeud.module or ""):
            imports.update(a.name for a in noeud.names)
    for suivant in imports:
        noms |= _lus_sur_le_contexte(suivant, vus)
    return noms


def _sans_chemin(type_produit):
    # « fabriquer » est cable paresseusement : sans cet appel, la signature
    # est vide et TOUT champ traduit passe pour perdu. Le detecteur criait
    # alors a tort sur quatre reglages parfaitement branches.
    catalogue._cabler()
    """Les champs de ce type qu'aucun chemin ne porte jusqu'a sa chaine.

    La detection, appelee PAR le test et PAR son temoin. La recopier dans le
    temoin laisserait neutraliser celle du test sans que personne ne bronche.
    """
    lus = _lus_sur_le_contexte(CHAINE.get(type_produit.cle))
    signature = (inspect.signature(type_produit.fabriquer).parameters
                 if type_produit.fabriquer else {})
    perdus = []
    for champ in (type_produit.champs or ()):
        nom = champ.nom
        if type_produit.quantite and nom in (type_produit.quantite[0], "nombre"):
            continue
        if nom in (type_produit.options or {}):
            continue
        if champ.argument and champ.argument in signature:
            continue
        if nom in fiction.CLES and type_produit.famille == "fiction":
            continue          # depose dans ctx.meta par « poser_la_promesse »
        if nom in lus:
            continue
        perdus.append(nom)
    return perdus


class ChaqueReglageArriveJusquASaChaine(unittest.TestCase):

    def test_aucun_champ_ne_se_perd_en_chemin(self):
        perdus = {t.cle: _sans_chemin(t) for t in catalogue.TYPES
                  if _sans_chemin(t)}
        self.assertEqual(perdus, {}, (
            "Ces reglages sont affiches, saisis, enregistres — et jetes avant "
            "d'arriver a la chaine : {}".format(perdus)))

    def test_le_temoin_verrait_un_champ_se_perdre(self):
        """Le detecteur applique a un champ qu'aucune chaine n'attend.

        Il appelle la MEME fonction que le test. Sans ce temoin, neutraliser
        la detection ne ferait echouer personne.
        """
        faux = catalogue.obtenir("quiz")
        invente = catalogue.Champ("reglage_invente", "--invente", "Invente")
        temoin = catalogue.TypeProduit(
            cle="quiz", nom=faux.nom, resume="", detail="",
            formats=faux.formats, minutes=faux.minutes,
            quantite=faux.quantite, fabriquer=faux.fabriquer,
            options=dict(faux.options), champs=faux.champs + (invente,))
        self.assertIn("reglage_invente", _sans_chemin(temoin))

    def test_aucun_argument_de_chaine_n_est_impossible_a_regler(self):
        """Le sens inverse : une chaine qui accepte un argument que rien
        n'expose est une fonctionnalite invisible — c'est le defaut qui avait
        cache « --reliure » et « --cible » au tableau de bord."""
        commun = {"ctx", "contexte", "serie", "relecture_ensemble"}
        for produit in catalogue.TYPES:
            if produit.fabriquer is None:
                continue
            reglables = {c.nom for c in (produit.champs or ())}
            reglables |= {c.argument for c in (produit.champs or ())
                          if c.argument}
            reglables |= set(produit.options or {})
            if produit.quantite:
                reglables.add(produit.quantite[0])
            manquants = [p for p in inspect.signature(produit.fabriquer).parameters
                         if p not in reglables and p not in commun]
            with self.subTest(type=produit.cle):
                self.assertEqual(manquants, [], produit.cle)


class UneCaseCocheeChangeVraimentQuelqueChose(unittest.TestCase):
    """Le compte, pas la lecture du code : c'est le seul qui ne triche pas."""

    def setUp(self):
        llm.definir_simulateur(simulateur.simulateur)
        self._vrai_sonder = marche.sonder
        self.sondages = []

        def espion(sujet, **_kw):
            self.sondages.append(sujet)
            return {"sujet": sujet, "date": "2026-09-15", "sources": {},
                    "sources_disponibles": [], "sources_indisponibles": [],
                    "lecture": {"demande": None, "fiabilite": "0/4",
                                "verdict": "", "signaux": [],
                                "concurrence": None, "tendance": None,
                                "requete_francophone": True}}

        marche.sonder = espion

    def tearDown(self):
        marche.sonder = self._vrai_sonder
        llm.definir_simulateur(None)

    def _produire(self, options):
        # Pas « hors_ligne » : il coupe le sondage a lui seul, et le test
        # mesurerait alors l'effet du mode hors ligne, pas celui de la case.
        contexte = base.Contexte(sujet="la facturation", sans_image=True,
                                 journal=lambda m: None)
        try:
            catalogue.executer("idees", contexte, {**options, "nombre": 3})
        except Exception:
            pass
        return len(self.sondages)

    def test_sans_la_case_le_marche_est_sonde(self):
        self.assertGreater(self._produire({}), 0)

    def test_avec_la_case_le_marche_ne_l_est_plus(self):
        self.assertEqual(self._produire({"sans_marche": True}), 0)

    def test_la_case_du_formulaire_html_compte_autant_qu_un_booleen(self):
        # Le navigateur envoie « on », la ligne de commande un vrai booleen,
        # la file relit du JSON. Les trois doivent vouloir dire la meme chose.
        self.assertEqual(self._produire({"sans_marche": "on"}), 0)

    def test_une_case_decochee_ne_coupe_rien(self):
        # « 0 » et « » sont ce qu'un formulaire envoie pour une case vide :
        # les prendre pour un oui couperait le sondage a chaque fabrication.
        self.assertGreater(self._produire({"sans_marche": "0"}), 0)
        self.sondages.clear()
        self.assertGreater(self._produire({"sans_marche": ""}), 0)


if __name__ == "__main__":
    unittest.main()
