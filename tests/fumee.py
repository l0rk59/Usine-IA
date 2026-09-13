"""Test de fumee : exerce toutes les chaines de production via la vraie CLI.

Aucun appel reseau : le routeur IA est remplace par le simulateur.
Lancement :  python3 tests/fumee.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

ATELIER = tempfile.mkdtemp(prefix="usine-fumee-")
os.environ["USINE_HOME"] = ATELIER
os.environ["USINE_PROVIDERS"] = "pollinations"  # jamais appele : le simulateur intercepte

from usine import cli  # noqa: E402
from usine.core import llm, store  # noqa: E402
from tests.simulateur import simulateur  # noqa: E402

llm.definir_simulateur(simulateur)

SCENARIOS = [
    ("idees", ["idees", "le jardinage urbain", "-n", "6", "--sans-image",
               "--sans-marche", "--hors-ligne"]),
    # Sur-mesure : sept sections de neuf cents mots, ton libre.
    ("sur-mesure", ["ebook", "la menuiserie du dimanche", "--chapitres", "7",
                    "--mots", "900", "-t", "comme un menuisier a son apprenti",
                    "--sans-image"]),
    ("ebook", ["ebook", "la prospection pour freelances", "-T", "mini",
               "--sans-image", "--marketing", "--zip"]),
    # La fiction : la seule chaine qui porte une memoire d'une section a la
    # suivante. Le scenario verifie que la bible et la continuite sortent.
    ("nouvelle", ["nouvelle", "un gardien de phare et le dernier hiver",
                  "-T", "mini", "--sans-image",
                  "--dedicace", "Pour ceux qui restent"]),
    # Le roman partage la chaine de la nouvelle, mais pas son echelle : c'est
    # la seule qui declenche la memoire hierarchique (des parties closes, pas
    # un resume plat). Huit scenes suffisent a la faire basculer sans que le
    # test de fumee dure une heure.
    ("roman", ["roman", "une disparition dans les Cevennes", "--chapitres", "8",
               "--mots", "400", "--sans-image"]),
    ("prompts", ["prompts", "la gestion de projet", "-n", "8", "--sans-image"]),
    ("formation", ["formation", "le copywriting", "-m", "4", "--sans-image"]),
    ("outils", ["outils", "la facturation", "-n", "5", "--sans-image"]),
    ("social", ["social", "le freelancing", "-n", "6", "-r", "linkedin",
                "--sans-image"]),
    ("modeles", ["modeles", "le suivi client", "-n", "3", "--sans-image"]),
    ("impression", ["impression", "la planification hebdomadaire", "-n", "6",
                    "--sans-image"]),
    ("complet", ["complet", "la meditation au bureau", "-T", "mini", "--sans-image"]),
    ("logiciel-cli", ["logiciel", "le nettoyage de fichiers en double", "-c", "cli",
                      "--sans-image"]),
    ("logiciel-web", ["logiciel", "le calcul de tarif pour freelances", "-c", "web",
                      "--sans-image"]),
    ("logiciel-extension", ["logiciel", "la lecture sans distraction",
                            "-c", "extension", "--sans-image"]),
    ("qualite", ["ebook", "la negociation", "-T", "mini", "--sans-image",
                 "--qualite", "exigeant"]),
    # Les seuls scenarios AVEC couverture : tout le reste passe --sans-image,
    # si bien que la chaine graphique n'etait exercee nulle part.
    ("couverture-ebook", ["ebook", "la negociation commerciale", "-T", "mini",
                          "--auteur", "Claire Fontaine", "--marque", "Atelier"]),
    ("couverture-outils", ["outils", "le suivi de tresorerie", "-n", "4"]),
    ("file-ajout", ["file", "--ajouter", "une niche de test", "--type", "ebook"]),
    ("file-liste", ["file"]),
    # Prospection : l'usine choisit une niche voisine a partir de ce qui a
    # le mieux marche, sans refaire ce qu'elle a deja fabrique.
    ("file-explorer", ["file", "--explorer", "--sans-veille", "-n", "5"]),
    ("usine-statut", ["usine", "statut"]),
    ("usine-demarrer", ["usine", "demarrer", "--max", "1", "--pause", "0"]),
    ("file-nettoyage", ["file", "--vider"]),
    ("ab-creer", ["ab", "creer", "--titre", "Un titre a tester", "--sur", "titre",
                  "-n", "4", "--hors-ligne", "--sans-image"]),
    ("ab-observer", ["ab", "observer", "1", "--vues", "200", "--actions", "9"]),
    ("ab-verdict", ["ab", "verdict", "1"]),
    # Sans periode renseignee, la comparaison des rythmes doit refuser de
    # conclure plutot que de compter zero pour tout le monde.
    ("ab-rythme", ["ab", "rythme", "1"], 1),
    ("ab-liste", ["ab", "liste"]),
    # Tous les produits du test viennent du meme simulateur : ils SONT des
    # doublons. La commande sort en 1 quand elle en trouve — c'est ce qui
    # permet de la mettre dans une tache planifiee.
    ("doublons", ["doublons"], 1),
    ("ventes-vide", ["ventes"]),
    ("ventes-import", ["ventes", "--importer", str(RACINE / "tests" / "ventes.csv"),
                       "--sur", "gumroad"]),
    ("ventes-rattacher", ["ventes", "--rattacher"]),
    ("ventes-resume", ["ventes"]),
    ("doublons-reconstruire", ["doublons", "--reconstruire"]),
    ("sauvegarde", ["sauvegarde"]),
    ("sauvegarde-inspecter", ["sauvegarde", "--inspecter",
                              "{atelier}/sauvegardes"]),
    ("bilan", ["bilan"]),
    ("reglages", ["reglages"]),
    ("prompts-systeme", ["prompts-systeme"]),
    ("liste", ["liste"]),
    ("cache", ["cache"]),
    ("docteur", ["docteur"]),
]

ATTENDUS = {
    "ebook": [".pdf", ".epub", "lire.html", "livre.md", "livre.txt"],
    "nouvelle": [".pdf", ".epub", "bible.json", "continuite.json",
                 "nouvelle.md", "lire.html"],
    "prompts": [".pdf", "prompts.csv", "prompts.json", "lire.html"],
    "formation": ["-manuel.pdf", "-cahier-exercices.pdf", "formation.md",
                  "quiz.html"],
    "outils": [".pdf", "boite-outils.md", "lire.html"],
    "social": [".pdf", "calendrier.csv", "posts.md"],
    "complet": [".pdf", ".epub", "marketing", "bonus-boite-outils",
                "bonus-publications"],
    "modeles": [".pdf", "a-importer", "modeles.md", "systeme.json"],
    "impression": ["-A4.pdf", "-Lettre-US.pdf", "cahier.json"],
    "qualite": ["rapport-qualite.json", ".pdf", ".epub"],
    "sur-mesure": [".pdf", ".epub", "livre.md"],
    "couverture-ebook": ["couverture.png", "couverture.svg", ".pdf", ".epub"],
    "couverture-outils": ["couverture.png", "couverture.svg", ".pdf"],
    "logiciel-cli": ["source/outil.py", "source/test_outil.py", "verification.json",
                     "notice.md", "lire.html", ".pdf"],
    "logiciel-web": ["source/index.html", "verification.json", "notice.md", ".pdf"],
    "logiciel-extension": ["source/manifest.json", "source/popup.html",
                           "source/popup.js", "source/contenu.js",
                           "verification.json"],
}


def verifier_sorties(nom: str) -> str:
    """Confirme que les fichiers attendus existent reellement sur le disque."""
    attendus = ATTENDUS.get(nom)
    if not attendus:
        return ""
    produits = [p for p in store.lister_produits(10)
                if p["statut"] != "bonus_integre"]
    if not produits:
        return "aucun produit enregistre"
    dossier = Path(produits[0]["dossier"])
    if not dossier.exists():
        return "dossier absent : {}".format(dossier)
    presents = [str(p.relative_to(dossier)) for p in dossier.rglob("*")]
    manquants = [a for a in attendus if not any(a in p for p in presents)]
    if manquants:
        return "fichiers manquants : {}".format(", ".join(manquants))
    vides = [p for p in dossier.rglob("*") if p.is_file() and p.stat().st_size == 0]
    if vides:
        return "fichiers vides : {}".format(", ".join(v.name for v in vides))
    png = dossier / "couverture.png"
    if png.exists() and not png.read_bytes().startswith(b"\x89PNG"):
        return "couverture.png n'est pas un PNG"
    return ""


def _resoudre(argument: str) -> str:
    """Remplace « {atelier} » par le dossier de test, et un dossier de
    sauvegardes par l'archive la plus recente qu'il contient."""
    if "{atelier}" not in argument:
        return argument
    chemin = Path(argument.format(atelier=ATELIER))
    if chemin.is_dir():
        archives = sorted(chemin.glob("*.zip"))
        return str(archives[-1]) if archives else str(chemin)
    return str(chemin)


def types_non_exerces() -> list:
    """Types du catalogue qu'aucun scenario ne fabrique.

    Le catalogue est la source unique de verite ; cette liste-ci est ecrite a
    la main. Sans ce controle, ajouter une chaine de fabrication la laisserait
    hors du seul test qui passe par la VRAIE CLI, et personne ne le verrait.
    """
    from usine.pipelines import catalogue

    lances = {scenario[1][0] for scenario in SCENARIOS}
    return [cle for cle in catalogue.cles(fabricables=True)
            if cle not in lances]


def principal() -> int:
    echecs = []
    oublies = types_non_exerces()
    if oublies:
        echecs.append(("catalogue", "type(s) jamais fabrique(s) par ce test : "
                       + ", ".join(oublies)))
    for scenario in SCENARIOS:
        nom, arguments = scenario[0], list(scenario[1])
        arguments = [_resoudre(a) for a in arguments]
        attendu = scenario[2] if len(scenario) > 2 else 0
        print("\n" + "=" * 66)
        print(">>> usine " + " ".join(arguments))
        print("=" * 66)
        try:
            code = cli.principal(arguments)
        except Exception:
            traceback.print_exc()
            echecs.append((nom, "exception"))
            continue
        if code != attendu:
            echecs.append((nom, "code de sortie {} (attendu {})".format(
                code, attendu)))
            continue
        probleme = verifier_sorties(nom)
        if probleme:
            echecs.append((nom, probleme))

    print("\n" + "=" * 66)
    if echecs:
        print("ECHECS :")
        for nom, raison in echecs:
            print("  - {} : {}".format(nom, raison))
    else:
        print("Toutes les chaines de production ont abouti.")
    print("Atelier de test : {}".format(ATELIER))
    total = sum(f.stat().st_size for f in Path(ATELIER).rglob("*") if f.is_file())
    nombre = sum(1 for f in Path(ATELIER).rglob("*") if f.is_file())
    print("{} fichiers produits, {} Ko au total".format(nombre, total // 1024))
    return 1 if echecs else 0


if __name__ == "__main__":
    code = principal()
    shutil.rmtree(ATELIER, ignore_errors=True)
    sys.exit(code)
