"""Le menu doit lancer la commande qu'il annonce.

Un sous-menu est une table de correspondance entre un numero tape au clavier
et une branche de code. Rien ne la verifie a l'execution : inserer une entree
au milieu decale toutes les suivantes, et le menu se met a lancer
tranquillement la mauvaise commande. C'est exactement le defaut trouve dans
« _rythme_ab », ou un decalage d'indice faisait annoncer « variante B » pour
ce que le tableau juste au-dessus appelait C.

Ces tests pilotent donc le menu par son entree standard, comme un doigt sur
un ecran de telephone, et regardent ce qui en sort.
"""

from __future__ import annotations

import ast
import io
import itertools
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine import cli  # noqa: E402
from usine import menu  # noqa: E402
from usine.core import experience, reglages, store, ventes  # noqa: E402
from usine.core import file as file_prod  # noqa: E402
from usine.pipelines import catalogue  # noqa: E402


def setUpModule():
    """Un atelier a nous, rempli une fois pour toutes.

    Les sous-menus changent de branche selon ce que l'atelier contient :
    « Partir d'un produit existant ? » n'est posee que s'il y a des
    produits. Remplir depuis un test et pas depuis un autre ferait
    dependre chaque suite de l'ordre d'execution — ce qu'on vient
    justement de supprimer entre les modules.
    """
    atelier.isoler("menu")
    _atelier_rempli()


def _un_test(titre: str, contenus: List[str]) -> int:
    """Un test A/B avec ses variantes, sans passer par l'IA."""
    identifiant = experience.creer(titre, "titre")
    for contenu in contenus:
        experience.ajouter_variante(identifiant, contenu)
    return identifiant


def deroule(fonction, frappes: List[str], ensuite: str = "0",
            limite: int = 80):
    """Comme `piloter`, mais tolerant : les frappes epuisees, on repond
    toujours la meme chose.

    « 0 » ressort de n'importe quel sous-menu en boucle. Pour un ecran qui
    se deroule une fois — « Fabriquer un produit » — c'est la chaine vide
    qu'il faut : elle accepte chaque valeur par defaut jusqu'au bout.

    Sert a promener le menu partout sans avoir a compter chaque question.
    Le garde-fou est la limite : un menu qui ne rend pas la main est un
    menu qui bloque un telephone.
    """
    lancees: List[List[str]] = []
    restantes = list(frappes)
    posees = itertools.count(1)

    def faux_input(invite=""):
        if next(posees) > limite:
            raise AssertionError("le menu ne rend pas la main")
        return restantes.pop(0) if restantes else ensuite

    with redirect_stdout(io.StringIO()):
        with mock.patch("builtins.input", faux_input):
            if fonction in _SANS_EXECUTER:
                fonction()
            else:
                fonction(lambda args: lancees.append(list(args)) or 0)
    return lancees


def piloter(fonction, frappes: List[str]):
    """Deroule un sous-menu avec des frappes ecrites d'avance.

    Renvoie la liste des commandes que le menu a voulu lancer. La derniere
    frappe doit ramener au menu precedent, sinon la boucle ne rend pas la
    main — et un test qui ne rend pas la main est un test qui pend.
    """
    lancees: List[List[str]] = []

    def executer(arguments):
        lancees.append(list(arguments))
        return 0

    entrees = iter(frappes)

    def faux_input(invite=""):
        try:
            return next(entrees)
        except StopIteration:
            raise AssertionError(
                "le menu demande plus que les {} frappes prevues "
                "(invite : {!r})".format(len(frappes), invite))

    with redirect_stdout(io.StringIO()):
        with mock.patch("builtins.input", faux_input):
            fonction(executer)
    return lancees


class TestEcranProduits(unittest.TestCase):
    """Les deux gestes qu'on fait sur un telephone : ouvrir, et envoyer.

    Ils passent par termux-api, absent de toute machine d'integration
    continue. Les entrees doivent donc exister PARTOUT et se comporter
    proprement quand l'outil manque : pas d'exception, un message qui dit
    quoi installer, et le chemin du fichier a defaut.
    """

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="usine-menu-produit-"))
        (self.dossier / "guide.pdf").write_bytes(b"%PDF-1.4" + b"0" * 900)
        (self.dossier / "guide-annexe.pdf").write_bytes(b"%PDF-1.4" + b"0" * 20)
        store.creer_produit("menu-tel", "ebook", "Le systeme du freelance",
                            sujet="freelance", dossier=str(self.dossier))

    def _sortie(self, frappes, **faux):
        """Deroule l'ecran et rend ce qui a ete affiche."""
        sortie = io.StringIO()
        entrees = iter(frappes)
        with mock.patch.multiple("usine.core.telephone", **faux):
            with redirect_stdout(sortie):
                with mock.patch("builtins.input", lambda invite="": next(entrees)):
                    menu.menu_produits(lambda arguments: 0)
        return sortie.getvalue()

    def test_ouvrir_vise_le_document_principal(self):
        """« guide-annexe.pdf » trie avant « guide.pdf » : c'est la taille qui
        distingue le document principal de son annexe."""
        vus = []
        texte = self._sortie(["1", "4", ""],
                             ouvrir=lambda chemin: vus.append(chemin) or True)
        self.assertEqual(len(vus), 1)
        self.assertEqual(vus[0].name, "guide.pdf")
        self.assertIn("Ouverture", texte)

    def test_sans_termux_api_l_entree_explique_et_donne_le_chemin(self):
        texte = self._sortie(["1", "4", ""], ouvrir=lambda chemin: False)
        self.assertIn("termux-open", texte)
        self.assertIn("pkg install termux-api", texte)
        self.assertIn("guide.pdf", texte)

    def test_partager_sans_archive_propose_de_la_creer(self):
        lancees = []
        entrees = iter(["1", "5", "o", ""])
        with redirect_stdout(io.StringIO()):
            with mock.patch("builtins.input", lambda invite="": next(entrees)):
                menu.menu_produits(
                    lambda arguments: lancees.append(list(arguments)) or 0)
        self.assertIn(["livrer", "menu-tel"], lancees,
                      "repondre oui doit lancer la creation de l'archive")

    def test_partager_envoie_l_archive_la_plus_recente(self):
        (self.dossier / "ancienne.zip").write_bytes(b"PK" + b"0" * 10)
        recente = self.dossier / "recente.zip"
        recente.write_bytes(b"PK" + b"0" * 10)
        os.utime(recente, (2 ** 31, 2 ** 31))
        envoyees = []
        self._sortie(["1", "5", ""],
                     partager=lambda chemin, titre="": envoyees.append(chemin) or True)
        self.assertEqual(len(envoyees), 1)
        self.assertEqual(envoyees[0].name, "recente.zip")

    def test_partage_impossible_donne_le_chemin(self):
        (self.dossier / "livrable.zip").write_bytes(b"PK" + b"0" * 10)
        texte = self._sortie(["1", "5", ""],
                             partager=lambda chemin, titre="": False)
        self.assertIn("termux-share", texte)
        self.assertIn("livrable.zip", texte)


class TestSousMenuAB(unittest.TestCase):
    """Chaque entree du sous-menu A/B, verifiee par ce qu'elle lance."""

    def setUp(self):
        self.test_id = _un_test("La prospection pour freelances",
                                ["Trouver des clients sans se vendre",
                                 "Quinze minutes par jour suffisent"])

    def test_rythme_lance_bien_ab_rythme(self):
        lancees = piloter(menu.menu_ab,
                          ["5", str(self.test_id), "", "0"])
        self.assertEqual(lancees, [["ab", "rythme", str(self.test_id)]])

    def test_verdict_lance_bien_ab_verdict(self):
        lancees = piloter(menu.menu_ab,
                          ["6", str(self.test_id), "", "0"])
        self.assertEqual(lancees, [["ab", "verdict", str(self.test_id)]])

    def test_chaque_entree_atteint_une_branche(self):
        """Aucun numero affiche ne doit tomber dans le vide.

        Une entree ajoutee a la liste sans branche correspondante ne provoque
        rien du tout : le menu se reaffiche, et l'utilisateur croit que
        l'usine a fait quelque chose.
        """
        for numero in (3, 4, 5, 6):
            with self.subTest(entree=numero):
                # « zzz » n'est un numero de test pour personne : chaque
                # branche doit le refuser et revenir, sans rien lancer.
                lancees = piloter(menu.menu_ab, [str(numero), "zzz", "0"])
                self.assertEqual(
                    lancees, [],
                    "l'entree {} a lance {}".format(numero, lancees))
        for numero in (1, 2):
            with self.subTest(entree=numero):
                # Les deux premieres passent par « ab creer ». Refuser de
                # partir d'un produit, puis donner un titre et un nombre.
                lancees = piloter(
                    menu.menu_ab,
                    [str(numero), "n", "Un titre", "3", "", "0"])
                self.assertEqual(len(lancees), 1)
                self.assertEqual(lancees[0][:2], ["ab", "creer"])
                attendu = "titre" if numero == 1 else "couverture"
                self.assertIn(attendu, lancees[0])


class TestDatationDesVariantes(unittest.TestCase):
    """« Dater les variantes » ecrit reellement la periode en base."""

    def setUp(self):
        self.test_id = _un_test("Le systeme du freelance",
                                ["Facturer sans se justifier",
                                 "La semaine de quatre jours"])
        self.lot = experience.variantes(self.test_id)

    def test_les_dates_saisies_arrivent_en_base(self):
        frappes = [
            "4", str(self.test_id),
            "2026-01-01", "2026-02-15",   # variante A
            "2026-02-16", "",             # variante B : toujours en ligne
            "",                           # Appuyez sur Entree
            "0",
        ]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertEqual(apres[0]["debut"], "2026-01-01")
        self.assertEqual(apres[0]["fin"], "2026-02-15")
        self.assertEqual(apres[1]["debut"], "2026-02-16")
        self.assertIsNone(apres[1]["fin"])

    def test_une_variante_laissee_vide_reste_sans_periode(self):
        frappes = ["4", str(self.test_id), "", "", "", "0"]
        piloter(menu.menu_ab, frappes)
        for variante in experience.variantes(self.test_id):
            self.assertIsNone(variante["debut"])

    def test_une_date_illisible_est_refusee_sans_casser_le_menu(self):
        frappes = [
            "4", str(self.test_id),
            "le 3 janvier", "",           # variante A : format refuse
            "2026-03-01", "",             # variante B : acceptee
            "", "0",
        ]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertIsNone(apres[0]["debut"])
        self.assertEqual(apres[1]["debut"], "2026-03-01")

    def test_une_fin_avant_le_debut_est_refusee(self):
        frappes = [
            "4", str(self.test_id),
            "2026-05-01", "2026-04-01",   # variante A : fin avant debut
            "",                           # variante B : passee
            "", "0",
        ]
        piloter(menu.menu_ab, frappes)
        self.assertIsNone(experience.variantes(self.test_id)[0]["debut"])

    def test_la_periode_deja_posee_est_proposee_par_defaut(self):
        """Repasser sur une variante datee sans rien taper ne l'efface pas."""
        experience.fixer_periode(self.lot[0]["id"], "2026-01-10", "2026-01-20")
        frappes = ["4", str(self.test_id), "", "", "", "", "0"]
        piloter(menu.menu_ab, frappes)
        apres = experience.variantes(self.test_id)
        self.assertEqual(apres[0]["debut"], "2026-01-10")
        self.assertEqual(apres[0]["fin"], "2026-01-20")




_SANS_EXECUTER = (menu.menu_reglages, menu.menu_cles)

_SOUS_MENUS = (
    ("menu_fabriquer", menu.menu_fabriquer),
    ("menu_usine", menu.menu_usine),
    ("menu_ab", menu.menu_ab),
    ("menu_produits", menu.menu_produits),
    ("menu_ventes", menu.menu_ventes),
    ("menu_reglages", menu.menu_reglages),
    ("menu_cles", menu.menu_cles),
)


def _atelier_rempli():
    """De quoi faire changer les branches qui dependent des donnees."""
    store.creer_produit("menu-p1", "ebook", "Le systeme du freelance",
                        sujet="freelance", dossier="/tmp/menu-p1")
    store.creer_produit("menu-p2", "prompts", "80 prompts pour freelances",
                        sujet="prompts", dossier="/tmp/menu-p2")
    file_prod.ajouter("une niche en attente", "ebook")
    ventes.enregistrer({"date": "2026-08-01",
                        "reference": "Le systeme du freelance",
                        "unites": 2, "brut": 58.0, "net": 50.0,
                        "devise": "EUR", "remboursement": 0,
                        "plateforme": "gumroad", "empreinte": "menu-v1"},
                       produit_id="menu-p1")


class TestMenuSeries(unittest.TestCase):
    """L'ecran des series, et surtout l'action qui rapporte.

    Le rafraichissement n'a l'air de rien et c'est lui qui fait vendre : un
    tome fabrique quand il etait le dernier porte une derniere page qui
    n'annonce rien de ce qui est venu apres, et c'est le lecteur du tome 1 —
    celui qui a paye en premier et qui est revenu — qui ne voit rien.
    """

    def setUp(self):
        from usine.core import serie as module_serie

        with store.cursor() as cur:
            cur.execute("DELETE FROM series")
        self.module_serie = module_serie

    def _piloter(self, frappes):
        return deroule(menu.menu_series, frappes)

    def test_sans_serie_l_ecran_explique_ou_en_commencer_une(self):
        texte = io.StringIO()
        with redirect_stdout(texte):
            with mock.patch("builtins.input", lambda invite="": ""):
                menu.menu_series(lambda a: 0)
        self.assertIn("Aucune série", texte.getvalue())
        self.assertIn("Fabriquer un produit", texte.getvalue())

    def test_le_rafraichissement_lance_la_bonne_commande(self):
        self.module_serie.enregistrer_tome(
            "Les rails", {"cadre": {}, "personnages": []}, "T1", "...")
        lancees = self._piloter(["1", "1", "", "0", "0"])
        self.assertIn(["series", "Les rails", "--rafraichir"], lancees)

    def test_ecrire_le_tome_suivant_reprend_la_serie(self):
        self.module_serie.enregistrer_tome(
            "Les rails", {"cadre": {}, "personnages": []}, "T1", "...")
        lancees = self._piloter(["1", "2", "un nouveau depart", "", "0", "0"])
        self.assertIn(["nouvelle", "un nouveau depart", "--serie", "Les rails"],
                      lancees)

    def test_l_ecran_signale_les_tomes_a_rafraichir(self):
        store.creer_produit("s1", "nouvelle", "T1")
        store.creer_produit("s2", "nouvelle", "T2")
        base = {"cadre": {}, "personnages": []}
        self.module_serie.enregistrer_tome("Les rails", base, "T1", "...",
                                           produit_id="s1")
        self.module_serie.enregistrer_tome("Les rails", base, "T2", "...",
                                           produit_id="s2")
        texte = io.StringIO()
        entrees = iter(["0"])
        with redirect_stdout(texte):
            with mock.patch("builtins.input",
                            lambda invite="": next(entrees, "0")):
                menu.menu_series(lambda a: 0)
        self.assertIn("à rafraîchir", texte.getvalue())


class TestMenuPrincipal(unittest.TestCase):
    """Chaque entree, a tous les niveaux, ouvre vraiment quelque chose.

    Le menu principal a compte jusqu'a dix-sept entrees a plat, et c'etait la
    plus longue table numero -> branche du projet : y inserer une ligne
    decalait toutes les suivantes en silence. Il compte maintenant six
    sections, et le decalage est devenu possible a DEUX niveaux au lieu d'un.

    Ce test descend donc dans chaque section et verifie que chacune de ses
    entrees fait quelque chose d'observable : une commande partie, ou un
    ecran dont le texte ne peut venir que de lui. « Ne rien lancer » est vrai
    d'un sous-menu comme d'une branche vide, et c'est precisement ce que ce
    test existe pour distinguer.
    """

    # Pour chaque section : son numero, et par entree ce qui prouve qu'elle a
    # ouvert quelque chose — soit la commande attendue, soit un texte que
    # SEUL cet ecran imprime. L'etiquette du menu ne convient pas : elle
    # s'affiche que la branche soit cablee ou vide.
    # « Produire en boucle » est entree 2 depuis le 14/09/2026 : elle etait la
    # deuxieme ligne du sous-menu « Fabriquer », c'est-a-dire l'endroit le
    # moins visible pour la seule fonction qui produit sans qu'on dicte quoi
    # que ce soit. Le tableau de bord l'a sortie au meme moment, et les deux
    # interfaces doivent ranger pareil — un test le garde.
    SECTIONS = {
        1: {1: ("ecran", "Que voulez-vous fabriquer"),
            2: ("commande", "idees"),
            3: ("ecran", "Usine continue")},
        2: {},          # « Produire en boucle » ouvre directement son ecran
        3: {1: ("ecran", "Générer le kit de vente"),
            2: ("ecran", "Aucune série pour l'instant"),
            3: ("ecran", "Tests A/B")},
        4: {1: ("commande", "veille"),
            2: ("commande", "marche"),
            3: ("ecran", "Ventes"),
            4: ("commande", "doublons"),
            5: ("commande", "bilan")},
        5: {1: ("ecran", "Tout réinitialiser"),
            2: ("ecran", "pollinations"),
            3: ("ecran", "Prompts"),
            4: ("ecran", "Voir ce qu'il contient")},
        6: {1: ("commande", "docteur"),
            2: ("commande", "specs"),
            3: ("commande", "maj"),
            4: ("commande", "sauvegarde")},
        7: {},          # « Tableau de bord » lance directement une commande
    }

    def _derouler(self, frappes):
        """Lance le menu avec ces frappes, et rend (commandes, texte affiche)."""
        lancees = []
        entrees = iter(frappes)
        texte = io.StringIO()
        with redirect_stdout(texte):
            with mock.patch("builtins.input",
                            lambda invite="": next(entrees, "0")):
                menu.menu_principal(lambda a: lancees.append(a) or 0)
        return lancees, texte.getvalue()

    def test_le_tableau_de_bord_part_directement(self):
        lancees, _ = self._derouler(["7"])
        self.assertTrue(lancees)
        self.assertEqual(lancees[0][0], "web")

    def test_chaque_entree_de_chaque_section_ouvre_quelque_chose(self):
        for section, entrees in sorted(self.SECTIONS.items()):
            for numero, (genre, repere) in sorted(entrees.items()):
                with self.subTest(section=section, entree=numero, attendu=repere):
                    frappes = [str(section), str(numero),
                               "un sujet quelconque", "1", "", "0", "0", "0"]
                    lancees, texte = self._derouler(frappes)
                    if genre == "commande":
                        self.assertTrue(
                            lancees,
                            "section {} entree {} ne lance rien".format(
                                section, numero))
                        self.assertEqual(lancees[0][0], repere)
                    else:
                        self.assertIn(repere, texte)

    def test_aucune_entree_affichee_ne_tombe_dans_le_vide(self):
        """Une entree sans branche ne provoque rien : l'utilisateur croit que
        l'usine a fait quelque chose, et recommence."""
        for section, attendues in sorted(self.SECTIONS.items()):
            affichees = _entrees_de_section(section)
            with self.subTest(section=section):
                self.assertEqual(
                    affichees, len(attendues) or affichees,
                    "la section {} affiche {} entrees et ce test en verifie {}"
                    .format(section, affichees, len(attendues)))

    def test_le_menu_principal_reste_court(self):
        """Sur un ecran de telephone, dix-sept entrees font deux ecrans et
        demi a faire defiler pour trouver « Reglages »."""
        self.assertLessEqual(_entrees_du_menu(), 8)

    def test_produire_en_boucle_est_au_premier_niveau(self):
        """Elle etait la deuxieme ligne d'un sous-menu : pour l'atteindre il
        fallait deja savoir qu'elle existait, et qu'elle vivait sous
        « Fabriquer ». Le tableau de bord l'a sortie le meme jour."""
        source = Path(menu.__file__).read_text(encoding="utf-8")
        bloc = source.split('choisir("Menu principal", [')[1].split("], defaut=")[0]
        self.assertIn("Produire en boucle", bloc)


def _entrees_du_menu() -> int:
    """Combien d'entrees le menu principal affiche, lues dans sa source."""
    source = Path(menu.__file__).read_text(encoding="utf-8")
    bloc = source.split('choisir("Menu principal", [')[1].split("], defaut=")[0]
    return bloc.count('("')


def _entrees_de_section(numero: int) -> int:
    """Combien d'entrees une section affiche, lues dans sa source."""
    source = Path(menu.__file__).read_text(encoding="utf-8")
    titres = {1: "Fabriquer", 2: "", 3: "Mes produits",
              4: "Comprendre le marché", 5: "Réglages", 6: "La machine",
              7: ""}
    titre = titres[numero]
    if not titre:
        return 0
    bloc = source.split('choisir("{}", ['.format(titre))[1].split("])")[0]
    return bloc.count('("')


class TestAucunSousMenuNeLeve(unittest.TestCase):
    """Une trace Python en plein ecran de telephone n'est pas une reponse.

    Le menu n'avait aucun test : c'est du code de presentation, celui qu'on
    juge trop simple pour se tromper. Il l'etait assez pour rendre
    « Fabriquer un produit » inaccessible des qu'un ton sur mesure etait
    enregistre.
    """

    def _suites(self):
        yield []
        yield ["zzz"]
        yield ["99"]
        yield ["-1"]
        for numero in range(1, 13):
            yield [str(numero)]
            yield [str(numero), "zzz", "zzz"]
            yield [str(numero), "1", "1", "1"]

    def test_atelier_rempli(self):
        for nom, fonction in _SOUS_MENUS:
            for frappes in self._suites():
                with self.subTest(sous_menu=nom, frappes=frappes):
                    deroule(fonction, frappes)


class TestReglagesSurMesure(unittest.TestCase):
    """Un reglage hors liste ne doit rien casser, et ne pas etre perdu."""

    def tearDown(self):
        reglages.reinitialiser()

    def _fabriquer(self):
        lancees = deroule(menu.menu_fabriquer,
                          ["1", "un sujet", "des freelances", "o"],
                          ensuite="")
        self.assertTrue(lancees, "aucune commande lancee")
        return lancees[0]

    def test_un_ton_sur_mesure_n_empeche_pas_de_fabriquer(self):
        """Le defaut : « tons.index(valeurs["ton"]) » levait ValueError.

        Le menu propose la saisie libre du ton — et refusait ensuite de
        s'ouvrir tant que ce ton etait enregistre comme defaut.
        """
        libre = "comme un vieux menuisier a son apprenti"
        reglages.ecrire({"ton": libre})
        commande = self._fabriquer()
        self.assertIn("-t", commande)
        self.assertEqual(commande[commande.index("-t") + 1], libre)

    def test_un_volume_sur_mesure_devient_un_nombre_de_sections(self):
        reglages.ecrire({"taille": "15"})
        commande = self._fabriquer()
        self.assertIn("--chapitres", commande)
        self.assertEqual(commande[commande.index("--chapitres") + 1], "15")
        self.assertNotIn("-T", commande)

    def test_une_qualite_inventee_n_est_pas_enregistree(self):
        """« rapidos » vaut « standard » partout : autant le dire tout de suite."""
        reglages.ecrire({"qualite": "rapidos"})
        self.assertEqual(reglages.lire("qualite"), "standard")
        commande = self._fabriquer()
        self.assertEqual(commande[commande.index("--qualite") + 1], "standard")

    def test_les_trois_qualites_connues_restent_acceptees(self):
        for qualite in ("rapide", "standard", "exigeant"):
            with self.subTest(qualite=qualite):
                reglages.ecrire({"qualite": qualite})
                self.assertEqual(reglages.lire("qualite"), qualite)


class TestReglageParListe(unittest.TestCase):
    """Le menu des reglages propose les raccourcis au lieu du clavier."""

    def tearDown(self):
        reglages.reinitialiser()

    def _rang_de(self, nom):
        return [l["nom"] for l in reglages.lignes_affichables()].index(nom) + 1

    def test_choisir_un_ton_dans_la_liste(self):
        deroule(menu.menu_reglages, [str(self._rang_de("ton")), "1"])
        self.assertEqual(reglages.lire("ton"), sorted(menu.TONS)[0])

    def test_saisir_un_ton_libre(self):
        libre = "comme un guide de haute montagne"
        entree_libre = str(len(menu.TONS) + 1)
        deroule(menu.menu_reglages,
                [str(self._rang_de("ton")), entree_libre, libre])
        self.assertEqual(reglages.lire("ton"), libre)

    def test_une_qualite_ne_peut_plus_etre_tapee(self):
        """La liste fermee ne laisse aucun moyen d'ecrire n'importe quoi."""
        deroule(menu.menu_reglages, [str(self._rang_de("qualite")), "1"])
        self.assertEqual(reglages.lire("qualite"), "rapide")


def _repondre_a_tout(invite=""):
    """Une reponse par GENRE de question, lue sur l'invite affichee.

    Oui a chaque question fermee, la deuxieme entree de chaque liste (la
    premiere est « l'usine decide », qui ne fixe rien), une valeur a chaque
    champ qu'on peut laisser a l'usine. C'est le parcours qui fixe le plus
    de reglages possible — celui ou une traduction manquante se perd.
    """
    if "(o/N)" in invite or "(O/n)" in invite:
        return "o"
    if "Votre choix" in invite:
        return "2"
    if "l'usine décide)" in invite or "Marge" in invite:
        return "3"
    return ""


class ChaqueReponseDuMenuArriveALaCommande(unittest.TestCase):
    """Une reponse donnee dans le menu doit se retrouver dans la commande.

    Mesure du 26/09/2026 : la tranche d'age d'un conte etait demandee,
    rendue par « _options_du_type »... et absente de « _ARGUMENTS ». En
    fabrication directe, « _arguments_du_type » la jetait sans rien dire :
    l'album partait pour la tranche que l'usine choisissait, pas pour celle
    qu'on venait de choisir. Seule la file de production la gardait.
    """

    def tearDown(self):
        reglages.reinitialiser()

    def test_chaque_reglage_repondu_a_sa_traduction_et_parse(self):
        parseur = cli.construire_parseur()
        vus = 0
        for cle in catalogue.cles(fabricables=True):
            with redirect_stdout(io.StringIO()), mock.patch(
                    "builtins.input", _repondre_a_tout):
                options = menu._options_du_type(cle)
            champs = {c.nom for c in catalogue.obtenir(cle).champs}
            for nom, valeur in options.items():
                vus += 1
                with self.subTest(type=cle, reglage=nom):
                    self.assertIn(nom, menu._ARGUMENTS,
                                  "reponse jetee avant la commande")
                    arguments = menu._ARGUMENTS[nom](valeur)
                    with redirect_stderr(io.StringIO()):
                        espace = parseur.parse_args([cle] + arguments)
                    if nom in champs:
                        self.assertEqual(getattr(espace, nom), valeur)
        self.assertGreater(vus, 30, "le parcours ne fixe presque rien")

    def test_la_fiction_se_regle_depuis_le_telephone(self):
        """Neuf reglages de fiction, aucun atteignable depuis le menu : choisir
        « romance, fin heureuse » exigeait la ligne de commande."""
        for cle in ("nouvelle", "roman", "interactive", "recueil",
                    "feuilleton", "conte"):
            with self.subTest(type=cle):
                with redirect_stdout(io.StringIO()), mock.patch(
                        "builtins.input", _repondre_a_tout):
                    options = menu._options_du_type(cle)
                attendus = ({c.nom for c in catalogue.obtenir(cle).champs}
                            & set(menu.PROMESSE_DE_FICTION))
                self.assertTrue(attendus)
                self.assertLessEqual(attendus, set(options))

    def test_l_etiquette_s_affiche_et_la_cle_part(self):
        sortie = io.StringIO()
        with redirect_stdout(sortie), mock.patch(
                "builtins.input", _repondre_a_tout):
            options = menu._options_du_type("roman")
        self.assertIn("Mélancolique", sortie.getvalue())
        self.assertEqual(options["ambiance"], "reconfortante")


class ChaqueCommandeDuMenuParseDansLaCLI(unittest.TestCase):
    """Chaque ligne de commande que le menu fabrique doit parser dans le vrai
    parseur. Cette classe de defaut est deja arrivee : « Reprendre » lancait
    « unrecognized arguments », code 2, apres que l'utilisateur avait repondu
    a toutes les questions (AUDIT-AGENTS-FOURNISSEURS.md). Rien ne la
    surveillait : une option renommee dans la CLI casse le menu en silence.

    Le detecteur lit la STRUCTURE de menu.py : les « executer([...]) »
    litteraux, et les « arguments = [...] » completes par += et append puis
    passes a executer. Ce qu'il ne sait pas lire, il le rate plutot que
    d'inventer : un argv dont la sous-commande n'est pas un litteral (l'ecran
    de fabrication, qui part de produit["cle"]) n'est pas reconstruit.

    Les variables deviennent le bouche-trou « 1 » ; quand le parseur repond
    « invalid choice » sur ce bouche-trou precis, on rejoue avec un des choix
    offerts — la valeur reelle vient d'une liste equivalente a l'execution.
    Un refus sur un LITTERAL, lui, est un vrai defaut.
    """

    BOUCHE_TROU = "1"

    @staticmethod
    def _morceaux(noeud):
        """Les elements d'une expression de liste : litteraux, ou None."""
        if isinstance(noeud, ast.List):
            return [e.value if isinstance(e, ast.Constant)
                    and isinstance(e.value, str) else None
                    for e in noeud.elts]
        if isinstance(noeud, ast.BinOp) and isinstance(noeud.op, ast.Add):
            gauche = ChaqueCommandeDuMenuParseDansLaCLI._morceaux(noeud.left)
            droite = ChaqueCommandeDuMenuParseDansLaCLI._morceaux(noeud.right)
            if gauche is not None and droite is not None:
                return gauche + droite
        if isinstance(noeud, ast.IfExp):
            return ChaqueCommandeDuMenuParseDansLaCLI._morceaux(noeud.body)
        return None

    @classmethod
    def _reconstruire(cls, source):
        arbre = ast.parse(source)
        argvs = []
        for fonction in [n for n in ast.walk(arbre)
                         if isinstance(n, ast.FunctionDef)]:
            for n in ast.walk(fonction):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "executer" and n.args):
                    m = cls._morceaux(n.args[0])
                    if m is not None:
                        argvs.append((n.lineno, m))
            consomme = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "executer" and n.args
                and isinstance(n.args[0], ast.Name)
                and n.args[0].id == "arguments"
                for n in ast.walk(fonction))
            if not consomme:
                continue
            base, ajouts, depart = None, [], 0
            for n in ast.walk(fonction):
                if (isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == "arguments"):
                    base, depart = cls._morceaux(n.value), n.lineno
                elif (isinstance(n, ast.AugAssign)
                      and isinstance(n.target, ast.Name)
                      and n.target.id == "arguments"):
                    m = cls._morceaux(n.value)
                    if m:
                        ajouts += m
                elif (isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute)
                      and n.func.attr == "append"
                      and isinstance(n.func.value, ast.Name)
                      and n.func.value.id == "arguments" and n.args
                      and isinstance(n.args[0], ast.Constant)):
                    ajouts.append(n.args[0].value)
            # Toutes les branches sont concatenees : deux options posees deux
            # fois restent valides pour argparse (la derniere gagne).
            if base and isinstance(base[0], str):
                argvs.append((depart, base + ajouts))
        return argvs

    def _refus(self, argv, parseur):
        """Le message du parseur si cet argv est refuse, sinon ""."""
        import re

        for _ in range(6):  # au plus un choix a poser par option a choix
            try:
                with redirect_stdout(io.StringIO()):
                    with mock.patch.object(
                            type(parseur), "error",
                            lambda _s, message: (_ for _ in ()).throw(
                                ValueError(message))):
                        parseur.parse_args(argv)
                return ""
            except ValueError as exc:
                message = str(exc)
                trouve = re.search(
                    r"invalid choice: '?{}'?.*choose from (.+)".format(
                        self.BOUCHE_TROU), message)
                if not trouve or self.BOUCHE_TROU not in argv:
                    return message
                choix = trouve.group(1).strip(")").split(",")[0].strip(" '\"")
                argv[argv.index(self.BOUCHE_TROU)] = choix
            except SystemExit:
                return "sortie seche du parseur"
        return "les choix ne suffisent pas : " + " ".join(argv)

    def test_chaque_ligne_du_menu_parse(self):
        source = (RACINE / "usine" / "menu.py").read_text(encoding="utf-8")
        argvs = self._reconstruire(source)
        # Le jour ou le menu change de forme au point que le detecteur ne
        # reconstruit plus rien, ce test doit le dire au lieu de passer vide.
        self.assertGreaterEqual(len(argvs), 30, "le detecteur a perdu le menu")
        parseur = cli.construire_parseur()
        for ligne, brut in argvs:
            argv = [e if e is not None else self.BOUCHE_TROU for e in brut]
            with self.subTest(ligne=ligne, commande=" ".join(argv)):
                self.assertEqual(self._refus(list(argv), parseur), "")

    def test_le_detecteur_verrait_une_option_renommee(self):
        """Sans lui, le controle pourrait passer parce qu'il ne trouve rien.

        Les deux formes du menu sont plantees : l'appel direct, et la liste
        « arguments » completee puis passee a executer — la premiere campagne
        de mutation a montre que casser le collecteur dynamique seul ne
        faisait echouer aucun cas.
        """
        cas = {
            "directe": ("def ecran(executer):\n"
                        "    executer([\"ebook\", \"un sujet\","
                        " \"--sans-imagee\"])\n"),
            "dynamique": ("def ecran(executer):\n"
                          "    arguments = [\"usine\", \"demarrer\"]\n"
                          "    arguments.append(\"--maxx\")\n"
                          "    executer(arguments)\n"),
        }
        parseur = cli.construire_parseur()
        for forme, source in sorted(cas.items()):
            with self.subTest(forme=forme):
                argvs = self._reconstruire(source)
                self.assertEqual(len(argvs), 1, "le collecteur " + forme
                                 + " ne reconstruit plus")
                argv = [e if e is not None else self.BOUCHE_TROU
                        for e in argvs[0][1]]
                self.assertNotEqual(self._refus(argv, parseur), "")


if __name__ == "__main__":
    unittest.main()
