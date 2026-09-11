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
               "--sans-marche"]),
    ("ebook", ["ebook", "la prospection pour freelances", "-T", "mini",
               "--sans-image", "--marketing", "--zip"]),
    ("prompts", ["prompts", "la gestion de projet", "-n", "8", "--sans-image"]),
    ("formation", ["formation", "le copywriting", "-m", "4", "--sans-image"]),
    ("outils", ["outils", "la facturation", "-n", "5", "--sans-image"]),
    ("social", ["social", "le freelancing", "-n", "6", "-r", "linkedin",
                "--sans-image"]),
    ("modeles", ["modeles", "le suivi client", "-n", "3", "--sans-image"]),
    ("impression", ["impression", "la planification hebdomadaire", "-n", "6",
                    "--sans-image"]),
    ("complet", ["complet", "la meditation au bureau", "-T", "mini", "--sans-image"]),
    ("qualite", ["ebook", "la negociation", "-T", "mini", "--sans-image",
                 "--qualite", "exigeant"]),
    ("bilan", ["bilan"]),
    ("reglages", ["reglages"]),
    ("prompts-systeme", ["prompts-systeme"]),
    ("liste", ["liste"]),
    ("cache", ["cache"]),
    ("docteur", ["docteur"]),
]

ATTENDUS = {
    "ebook": [".pdf", ".epub", "lire.html", "livre.md", "livre.txt"],
    "prompts": [".pdf", "prompts.csv", "prompts.json", "lire.html"],
    "formation": ["-manuel.pdf", "-cahier-exercices.pdf", "formation.md"],
    "outils": [".pdf", "boite-outils.md", "lire.html"],
    "social": [".pdf", "calendrier.csv", "posts.md"],
    "complet": [".pdf", ".epub", "marketing", "bonus-boite-outils",
                "bonus-publications"],
    "modeles": [".pdf", "a-importer", "modeles.md", "systeme.json"],
    "impression": ["-A4.pdf", "-Lettre-US.pdf", "cahier.json"],
    "qualite": ["rapport-qualite.json", ".pdf", ".epub"],
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
    return ""


def principal() -> int:
    echecs = []
    for nom, arguments in SCENARIOS:
        print("\n" + "=" * 66)
        print(">>> usine " + " ".join(arguments))
        print("=" * 66)
        try:
            code = cli.principal(arguments)
        except Exception:
            traceback.print_exc()
            echecs.append((nom, "exception"))
            continue
        if code != 0:
            echecs.append((nom, "code de sortie {}".format(code)))
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
