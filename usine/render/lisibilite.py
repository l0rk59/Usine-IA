"""Le contraste des documents livres, declare une fois et verifie.

Depuis le 28 juin 2025, l'European Accessibility Act s'applique aux livres
numeriques vendus dans l'Union. Un EPUB mis en vente doit porter ses
metadonnees d'accessibilite, et ce qu'elles annoncent doit etre vrai.

Ce module tient la liste des couples encre/fond des feuilles de style
livrees. Ce n'est pas de la documentation : un test parcourt les feuilles de
style reelles, releve chaque couleur qui y apparait, et refuse celle qui ne
figure pas dans ce tableau. Ajouter une couleur oblige donc a dire a quoi
elle sert et sur quoi elle se pose — faute de quoi la suite echoue.

Sans ce verrou, la declaration de conformite se serait desynchronisee de la
feuille de style au premier changement de teinte, et l'usine aurait continue
d'affirmer une conformite qu'elle n'avait plus.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# Seuil WCAG 2.1 AA pour du texte de taille normale.
SEUIL_TEXTE = 4.5
# Seuil pour les elements non textuels : filets, bordures, traits de titre.
SEUIL_OBJET = 3.0

Couple = Tuple[str, str, str, float]   # (role, encre, fond, seuil)

# --- EPUB : fond blanc impose par la liseuse -------------------------------
BLANC = "#ffffff"

EPUB: List[Couple] = [
    ("corps", "#16181d", BLANC, SEUIL_TEXTE),
    ("titre h1", "#0f172a", BLANC, SEUIL_TEXTE),
    ("titre h2", "#1e293b", BLANC, SEUIL_TEXTE),
    ("titre h3", "#334155", BLANC, SEUIL_TEXTE),
    ("citation", "#3f4653", BLANC, SEUIL_TEXTE),
    ("sous-titre", "#475569", BLANC, SEUIL_TEXTE),
    ("auteur", "#64748b", BLANC, SEUIL_TEXTE),
    ("titre d'encadre", "#1d4ed8", "#f1f6fe", SEUIL_TEXTE),
    ("texte d'encadre", "#16181d", "#f1f6fe", SEUIL_TEXTE),
    ("code", "#16181d", "#f4f5f7", SEUIL_TEXTE),
    ("filet de titre", "#2563eb", BLANC, SEUIL_OBJET),
    ("separateur", "#cbd5e1", BLANC, 1.0),        # decoratif
]

# --- HTML livre : deux themes, donc deux jeux ------------------------------
HTML_CLAIR: List[Couple] = [
    ("corps", "#16181d", "#ffffff", SEUIL_TEXTE),
    ("texte doux", "#5b6472", "#ffffff", SEUIL_TEXTE),
    ("accent", "#2563eb", "#ffffff", SEUIL_TEXTE),
    ("texte d'encadre", "#16181d", "#f1f6fe", SEUIL_TEXTE),
    ("accent sur encadre", "#2563eb", "#f1f6fe", SEUIL_TEXTE),
    ("bordure", "#e2e8f0", "#ffffff", 1.0),       # decoratif
    # Quiz auto-corrige : les deux verdicts, et le bouton.
    ("verdict juste", "#14663f", "#e9f6ef", SEUIL_TEXTE),
    ("verdict faux", "#9b1c1c", "#fdecec", SEUIL_TEXTE),
    ("bouton", "#ffffff", "#2563eb", SEUIL_TEXTE),
    ("bouton survole", "#ffffff", "#1d4ed8", SEUIL_TEXTE),
]

HTML_SOMBRE: List[Couple] = [
    ("corps", "#e8eaee", "#0f1218", SEUIL_TEXTE),
    ("texte doux", "#9aa3b2", "#0f1218", SEUIL_TEXTE),
    ("accent", "#60a5fa", "#0f1218", SEUIL_TEXTE),
    ("texte d'encadre", "#e8eaee", "#151c28", SEUIL_TEXTE),
    ("accent sur encadre", "#60a5fa", "#151c28", SEUIL_TEXTE),
    ("bordure", "#262c38", "#0f1218", 1.0),       # decoratif
    ("verdict juste", "#6ee7a8", "#12211a", SEUIL_TEXTE),
    ("verdict faux", "#fca5a5", "#24161a", SEUIL_TEXTE),
    ("bouton", "#0f1218", "#60a5fa", SEUIL_TEXTE),
]

JEUX: Dict[str, List[Couple]] = {
    "epub": EPUB, "html clair": HTML_CLAIR, "html sombre": HTML_SOMBRE,
}


def couleurs_declarees() -> set:
    """Toutes les teintes citees ici, encre et fond confondus."""
    connues = set()
    for couples in JEUX.values():
        for _, encre, fond, _ in couples:
            connues.add(encre.lower())
            connues.add(fond.lower())
    return connues


def verifier() -> List[str]:
    """Les couples qui n'atteignent pas leur seuil. Vide = tout va bien."""
    from .couverture import contraste
    from .raster import couleur_hex

    manques = []
    for nom_jeu, couples in JEUX.items():
        for role, encre, fond, seuil in couples:
            mesure = contraste(couleur_hex(encre), couleur_hex(fond))
            if mesure < seuil:
                manques.append("{} / {} : {:.2f}:1 (exige {:.1f})".format(
                    nom_jeu, role, mesure, seuil))
    return manques
