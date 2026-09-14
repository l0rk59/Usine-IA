"""Les couleurs d'une peau : celles qu'elle declare, et celles qu'elle subit.

Une peau du tableau de bord ne redeclare que des variables. Tout ce qu'une
regle CSS peint EN DUR echappe donc aux six peaux a la fois — et le defaut
ne ressemble pas a un oubli de variable, il ressemble a une peau ratee. C'est
pour ca qu'il a tenu si longtemps :

  « papier » est une peau creme, faite pour travailler une heure. Elle portait
  une barre du haut bleu nuit, parce que « header.barre » ecrivait
  « rgba(5,6,13,0.92) » au lieu de lire le fond de la peau. Le titre brun sur
  ce bleu donnait 1.07 de contraste — illisible — et personne ne voyait la
  cause, parce que la barre EXISTAIT et avait l'air voulue.

  Le bouton « supprimer » ecrivait en blanc sur « --rouge ». Blanc sur le
  rouge vif de cinq peaux sur six : 2.80 a 3.45. Le seul bouton de la page
  qui detruit quelque chose etait le moins lisible.

  La scene 3D et le fond anime, eux, ne connaissaient que deux peaux : ils
  restaient cyan sous « ambre » et sous « console ».

Deux controles, donc. Le premier est structurel : aucune couleur ecrite hors
d'un bloc « :root ». Le second est numerique : le contraste WCAG de chaque
encre sur le fond que sa peau produit vraiment.

Ce que ces controles NE voient PAS, et le disent :
  - le contraste reel d'un texte pose sur un degrade, sur un canvas ou sur un
    halo ne se calcule pas depuis la feuille de style. Il a ete mesure au
    pixel dans un navigateur (674 textes, six peaux, six onglets) le
    14/09/2026 ; cette mesure ne tourne pas ici, parce qu'elle demande un
    navigateur et que rien dans ce depot n'en installe un ;
  - un gris translucide (une ombre portee, un voile) passe : il marche sous
    toutes les peaux. Seules la teinte et l'opacite dominante sont refusees.
    Le controle rate donc un defaut plutot que d'en inventer un.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests import atelier  # noqa: E402
from usine.core import reglages  # noqa: E402

STATIQUE = RACINE / "usine" / "web" / "statique"
CSS = (STATIQUE / "tableau.css").read_text(encoding="utf-8")

COULEUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
DECLARATION = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")

# WCAG 2.1, niveau AA, texte courant. Les titres de ce tableau de bord sont
# petits (0.72rem en majuscules) : aucun n'atteint la derogation « grand
# texte », on applique donc le meme seuil partout.
SEUIL = 4.5

# Les proprietes qui decident du clair et du sombre. Une couleur ecrite en dur
# dans l'une d'elles s'impose aux six peaux ; ailleurs — une ombre, une lueur —
# un gris discret reste acceptable partout.
PROPRIETES_DE_SURFACE = frozenset((
    "background", "background-color", "background-image",
    "color", "border", "border-color", "border-top", "border-bottom",
    "border-left", "border-right",
))


def setUpModule():
    atelier.isoler("peaux_couleurs")


def blocs_css(texte):
    """Chaque regle du fichier : (selecteur, corps). Sans dependance."""
    out, i = [], 0
    while True:
        j = texte.find("{", i)
        if j < 0:
            return out
        entete = texte[i:j].strip()
        k, prof = j, 0
        while k < len(texte):
            if texte[k] == "{":
                prof += 1
            elif texte[k] == "}":
                prof -= 1
                if prof == 0:
                    break
            k += 1
        selecteur = entete.splitlines()[-1].strip() if entete else ""
        out.append((selecteur, texte[j + 1:k]))
        i = k + 1


def rvba(valeur):
    """Une couleur CSS en (rouge, vert, bleu, alpha), ou None."""
    v = valeur.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16),
                int(h[6:8], 16) / 255 if len(h) == 8 else 1.0)
    if v.startswith("rgb"):
        m = re.findall(r"[\d.]+", v)
        if len(m) < 3:
            return None
        return (float(m[0]), float(m[1]), float(m[2]),
                float(m[3]) if len(m) > 3 else 1.0)
    return None


def _canal(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rouge, vert, bleu):
    return 0.2126 * _canal(rouge) + 0.7152 * _canal(vert) + 0.0722 * _canal(bleu)


def pose(avant, arriere):
    """Une couleur translucide posee sur son fond."""
    return tuple(c * avant[3] + f * (1 - avant[3])
                 for c, f in zip(avant[:3], arriere))


def contraste(encre, fond):
    a, b = luminance(*encre), luminance(*fond)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def palette(cle):
    """Les variables d'une peau, celles de « nuit » comblant les absentes."""
    base = CSS.index(":root {")
    fin_base = CSS.index("\n}", base)
    variables = dict(DECLARATION.findall(CSS[base:fin_base]))
    # « :root » est declare deux fois : couleurs, puis formes. On prend tout.
    for selecteur, corps in blocs_css(CSS):
        if selecteur == ":root":
            variables.update(DECLARATION.findall(corps))
    if cle != "nuit":
        ancre = ':root[data-theme="{}"]'.format(cle)
        for selecteur, corps in blocs_css(CSS):
            if selecteur == ancre:
                variables.update(DECLARATION.findall(corps))
    return {n: v.strip() for n, v in variables.items()}


def resoudre(variables, nom, vus=()):
    """La valeur d'une variable, « var(--autre) » suivi jusqu'au bout."""
    valeur = variables.get(nom, "")
    ref = re.match(r"var\(\s*(--[a-z0-9-]+)\s*\)$", valeur.strip())
    if ref and ref.group(1) not in vus:
        return resoudre(variables, ref.group(1), tuple(vus) + (nom,))
    return valeur


def _sans_commentaires(texte):
    """Le corps d'une regle, ses commentaires retires."""
    out, i = "", 0
    while True:
        j = texte.find("/*", i)
        if j < 0:
            return out + texte[i:]
        out += texte[i:j]
        k = texte.find("*/", j)
        if k < 0:
            return out
        i = k + 2


def _argument(corps, rang):
    """Le n-ieme argument d'un appel, virgules imbriquees respectees."""
    args, prof, courant = [], 0, ""
    for c in corps:
        if c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
        if c == "," and prof == 0:
            args.append(courant)
            courant = ""
            continue
        courant += c
    args.append(courant)
    return args[rang].strip() if len(args) > rang else None


class CouleursEnDur(unittest.TestCase):
    """Aucune regle ne peint une couleur que les six peaux subiront."""

    def test_aucune_couleur_teintee_hors_des_blocs_de_peau(self):
        coupables = []
        for selecteur, corps in blocs_css(CSS):
            if selecteur.startswith("@") or ":root" in selecteur:
                continue
            # On decoupe par DECLARATION, pas par ligne : le voile de
            # scanlines etale son degrade sur trois lignes, et un controle qui
            # ne regardait qu'une ligne a la fois ne voyait plus qu'il etait
            # dans un « gradient( ». Il signalait alors une etape de degrade
            # comme un aplat — un garde-fou qui crie a tort, et on l'ignore.
            for declaration in _sans_commentaires(corps).split(";"):
                if ":" not in declaration:
                    continue
                propriete, valeur = declaration.split(":", 1)
                propriete = propriete.strip().lower()
                for trouve in COULEUR.finditer(valeur):
                    couleur = rvba(trouve.group(0))
                    if couleur is None:
                        continue
                    rouge, vert, bleu, alpha = couleur
                    if alpha == 0:
                        continue  # transparent : ne peint rien, ne decide rien
                    teintee = max(rouge, vert, bleu) - min(rouge, vert, bleu) > 12
                    dans_degrade = "gradient(" in valeur[:trouve.start()]
                    # Ce n'est pas l'opacite qui tranche, c'est ce que la
                    # couleur REMPLIT. Un aplat de fond decide du clair et du
                    # sombre : « rgba(0,0,0,0.45) » derriere le journal est un
                    # gris discret sur une peau sombre, et un pave gris au
                    # milieu du creme de « papier ». Une etape de degrade ou
                    # une ombre, elles, se posent PAR-DESSUS ce que la peau a
                    # peint : un voile noir ou blanc y marche partout, et le
                    # refuser serait crier a tort.
                    if propriete in PROPRIETES_DE_SURFACE and not dans_degrade:
                        coupables.append("{} : {} ({})".format(
                            selecteur[:44], trouve.group(0), propriete))
                    elif teintee or alpha >= 0.5:
                        coupables.append("{} : {}".format(
                            selecteur[:48], trouve.group(0)))
        self.assertEqual(coupables, [], "\n".join(
            ["Ces regles peignent une couleur qui ne suit aucune peau :"]
            + coupables))

    def test_les_deux_canevas_lisent_la_peau_au_lieu_de_la_deviner(self):
        """La scene 3D et le fond anime prennent leurs couleurs du CSS.

        Ils tenaient chacun deux jeux de couleurs, « jour » et le reste : sous
        « ambre », une page entierement ambre affichait une grille cyan.
        """
        for nom in ("scene.js", "cyber.js"):
            source = (STATIQUE / nom).read_text(encoding="utf-8")
            self.assertIn("getPropertyValue", source,
                          "{} n'interroge jamais la peau".format(nom))
            self.assertIn("--accent", source,
                          "{} ne lit pas l'accent de la peau".format(nom))
            # La branche « si jour, sinon » etait la forme exacte du defaut.
            self.assertNotIn("dataset.theme === 'jour'", source,
                             "{} traite encore « jour » a part".format(nom))

    def test_chaque_dessin_de_la_scene_recoit_une_couleur_de_la_peau(self):
        """Le troisieme argument de « _dessiner » vient de la palette.

        La premiere version de ce controle cherchait « getPropertyValue »
        quelque part dans le fichier. Une mutation l'a mis en defaut : on
        peut lire la palette, la ranger dans une variable, et continuer a
        dessiner avec un triplet ecrit en dur juste a cote. Le fichier
        contenait le mot cherche, le controle etait vert, la scene restait
        bleue.

        Celui-ci lit la STRUCTURE : chaque appel de dessin, et l'argument
        qui porte sa couleur.
        """
        source = (STATIQUE / "scene.js").read_text(encoding="utf-8")
        appels, i = [], 0
        while True:
            i = source.find("this._dessiner(", i)
            if i < 0:
                break
            debut = source.index("(", i)
            prof, j = 0, debut
            while j < len(source):
                if source[j] == "(":
                    prof += 1
                elif source[j] == ")":
                    prof -= 1
                    if prof == 0:
                        break
                j += 1
            appels.append(source[debut + 1:j])
            i = j
        self.assertGreaterEqual(len(appels), 6,
                                "la scene ne dessine presque plus rien ?")
        sans_peau = []
        for corps in appels:
            couleur = _argument(corps, 2)
            if couleur is None or "teintes" not in couleur:
                sans_peau.append(" ".join(couleur.split())[:60]
                                 if couleur else "(argument absent)")
        self.assertEqual(sans_peau, [], "\n".join(
            ["Ces dessins n'utilisent pas la palette de la peau :"] + sans_peau))


class ContrasteDeclare(unittest.TestCase):
    """Chaque encre se lit sur le fond que sa peau produit vraiment.

    « vraiment » : « --carte » est translucide, donc le fond d'une carte n'est
    pas « --fond » mais la carte POSEE sur le fond. Comparer a « --fond » seul
    rendait un chiffre juste pour un fond qui n'existe nulle part.
    """

    def peaux(self):
        return [t["cle"] for t in reglages.THEMES]

    def fond_de_carte(self, variables):
        fond = rvba(resoudre(variables, "--fond"))
        carte = rvba(resoudre(variables, "--carte"))
        return pose(carte, fond[:3])

    def test_chaque_peau_declare_les_variables_mesurees(self):
        for cle in self.peaux():
            variables = palette(cle)
            for nom in ("--fond", "--carte", "--encre", "--doux", "--accent",
                        "--rouge", "--danger-encre"):
                self.assertIsNotNone(
                    rvba(resoudre(variables, nom)),
                    "{} : {} illisible ou absente".format(cle, nom))

    def test_encre_doux_et_accent_se_lisent_sur_une_carte(self):
        faibles = []
        for cle in self.peaux():
            variables = palette(cle)
            fond = self.fond_de_carte(variables)
            for nom in ("--encre", "--doux", "--accent"):
                encre = pose(rvba(resoudre(variables, nom)), fond)
                mesure = contraste(encre, fond)
                if mesure < SEUIL:
                    faibles.append("{} {} : {:.2f}".format(cle, nom, mesure))
        self.assertEqual(faibles, [], "\n".join(
            ["Sous le seuil WCAG AA de {} :".format(SEUIL)] + faibles))

    def test_le_bouton_qui_detruit_se_lit_sur_son_rouge(self):
        """Le seul bouton qui supprime quelque chose doit etre le plus clair.

        Il ecrivait « #fff » en dur : 2.80 sur console, 2.85 sur ambre, 3.22
        sur contraste, 3.45 sur nuit et jour. Cinq peaux sur six.
        """
        faibles = []
        for cle in self.peaux():
            variables = palette(cle)
            rouge = rvba(resoudre(variables, "--rouge"))
            encre = pose(rvba(resoudre(variables, "--danger-encre")), rouge[:3])
            mesure = contraste(encre, rouge[:3])
            if mesure < SEUIL:
                faibles.append("{} : {:.2f}".format(cle, mesure))
        self.assertEqual(faibles, [], "\n".join(
            ["Bouton « supprimer » illisible :"] + faibles))

    def test_un_titre_blanc_sur_un_pave_accent_tient_aussi(self):
        """L'accent sert DEUX fois : en texte, et en fond sous « --encre ».

        Les deux emplois tirent dans des sens opposes — un accent plus clair
        se lit mieux en texte sur fond sombre, et moins bien sous du texte
        clair. « jour » s'etait arrete au premier : 3.78 pour l'autre.
        """
        faibles = []
        for cle in self.peaux():
            variables = palette(cle)
            accent = rvba(resoudre(variables, "--accent"))
            fond = rvba(resoudre(variables, "--fond"))
            encre = pose(rvba(resoudre(variables, "--encre")), accent[:3])
            mesure = contraste(encre, accent[:3])
            autre = contraste(pose(fond, accent[:3]), accent[:3])
            if max(mesure, autre) < SEUIL:
                faibles.append("{} : {:.2f}".format(cle, max(mesure, autre)))
        self.assertEqual(faibles, [], "\n".join(
            ["Aucune encre ne se lit sur le pave d'accent :"] + faibles))


if __name__ == "__main__":
    unittest.main()
