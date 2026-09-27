"""Cartes de revision : planches a decouper, fichier Anki, page qui retourne.

Trois formes pour trois facons de reviser, et chacune a sa contrainte :

  1. **les planches** s'impriment en recto-verso. Chaque page de rectos est
     suivie de la page de ses versos, disposes EN MIROIR : une feuille qui
     se retourne sur son bord long inverse la gauche et la droite, et sans
     ce miroir la reponse de la carte 1 se retrouve au dos de la carte 2 ;
  2. **le fichier Anki** est un texte a tabulations avec les en-tetes que
     lit Anki depuis sa version 2.1.54 (« #separator », « #columns »,
     « #tags column » ; manuel d'Anki, « Importing > Text Files », verifie
     le 27/09/2026). Un CSV ordinaire s'importe aussi, mais sa ligne de
     titres devient une carte de plus ;
  3. **la page** retourne les cartes au toucher, hors ligne, sans
     bibliotheque — le meme principe que le quiz auto-corrige.

Une carte ne se lit que si son texte tient sur son rectangle. Le texte
trop long est d'abord compose plus petit, jusqu'a un plancher lisible ;
au-dela il est coupe, et c'est COMPTE : la chaine le note en anomalie au
lieu de livrer une carte illisible sans le dire.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .document import insecables
from .metriques import largeur_texte
from .pdf import DocumentPDF

COLONNES = 2
RANGEES = 4
PAR_PLANCHE = COLONNES * RANGEES
# Du plus confortable au plus petit encore lisible a bout de bras.
TAILLES_RECTO = (15.0, 13.5, 12.0, 11.0, 10.0, 9.0)
TAILLES_VERSO = (12.0, 11.0, 10.0, 9.0, 8.0)
MARGE_PAGE = 28.0        # environ un centimetre
MARGE_CARTE = 14.0
GRIS_TRAIT = (0.72, 0.74, 0.78)
GRIS_DOUX = (0.42, 0.45, 0.52)
ENCRE = (0.09, 0.10, 0.12)


def _ajuster(doc: DocumentPDF, texte: str, police: str,
             tailles: Tuple[float, ...], largeur: float,
             hauteur: float) -> Tuple[float, List[str], bool]:
    """La plus grande taille ou le texte tient ; coupe au plancher sinon."""
    for taille in tailles:
        lignes = doc.couper(texte, police, taille, largeur)
        if len(lignes) * taille * 1.3 <= hauteur:
            return taille, lignes, False
    taille = tailles[-1]
    lignes = doc.couper(texte, police, taille, largeur)
    tenues = max(1, int(hauteur // (taille * 1.3)))
    coupees = lignes[:tenues]
    coupees[-1] = coupees[-1].rstrip(" .,;:") + "…"
    return taille, coupees, True


def _poser_bloc(doc: DocumentPDF, lignes: List[str], police: str,
                taille: float, centre_x: float, centre_y: float,
                couleur: Tuple[float, float, float]) -> None:
    """Des lignes centrees, horizontalement et verticalement, sur un point."""
    hauteur_ligne = taille * 1.3
    total = len(lignes) * hauteur_ligne
    y = centre_y + total / 2 - taille
    for ligne in lignes:
        x = centre_x - largeur_texte(ligne, police, taille) / 2
        doc.texte_a(ligne, x, y, police, taille, couleur)
        y -= hauteur_ligne


def planches(doc: DocumentPDF, cartes: List[Dict[str, Any]]) -> Dict[str, int]:
    """Dessine toutes les planches ; rend combien de faces ont ete coupees.

    Le document recu ne doit avoir aucune page ouverte a lui : chaque
    planche ouvre la sienne, sans numero, parce qu'un numero de page au
    milieu d'une ligne de coupe tombe sur une carte.
    """
    largeur = (doc.largeur - 2 * MARGE_PAGE) / COLONNES
    hauteur = (doc.hauteur - 2 * MARGE_PAGE) / RANGEES
    utile_l = largeur - 2 * MARGE_CARTE
    utile_h = hauteur - 2 * MARGE_CARTE - 14
    coupees = 0
    for debut in range(0, len(cartes), PAR_PLANCHE):
        lot = cartes[debut:debut + PAR_PLANCHE]
        for face in ("recto", "verso"):
            doc.nouvelle_page(numeroter=False)
            for rang, carte in enumerate(lot):
                colonne, rangee = rang % COLONNES, rang // COLONNES
                if face == "verso":
                    colonne = COLONNES - 1 - colonne
                x = MARGE_PAGE + colonne * largeur
                y = doc.hauteur - MARGE_PAGE - (rangee + 1) * hauteur
                doc.rectangle(x, y, largeur, hauteur, GRIS_TRAIT,
                              plein=False, epaisseur=0.4)
                numero = str(debut + rang + 1)
                doc.texte_a(numero, x + largeur - MARGE_CARTE
                            - largeur_texte(numero, "Helvetica", 7),
                            y + 8, "Helvetica", 7, GRIS_DOUX)
                if face == "recto":
                    if carte.get("theme"):
                        doc.texte_a(str(carte["theme"])[:48], x + MARGE_CARTE,
                                    y + hauteur - MARGE_CARTE - 6,
                                    "Helvetica", 7.5, GRIS_DOUX)
                    police, tailles = "Helvetica-Bold", TAILLES_RECTO
                else:
                    police, tailles = "Helvetica", TAILLES_VERSO
                taille, lignes, coupe = _ajuster(
                    doc, str(carte[face]), police, tailles, utile_l, utile_h)
                if coupe:
                    coupees += 1
                _poser_bloc(doc, lignes, police, taille, x + largeur / 2,
                            y + hauteur / 2, ENCRE)
    return {"coupees": coupees}


def fichier_anki(chemin: Path, cartes: List[Dict[str, Any]],
                 colonnes: Tuple[str, str, str]) -> Path:
    """Le texte a tabulations qu'Anki importe tel quel (Fichier > Importer).

    Une tabulation ou un retour a la ligne DANS un champ decalerait toutes
    les colonnes suivantes : ils deviennent des espaces. Le theme devient
    une etiquette Anki, donc un seul mot : ses espaces deviennent des
    tirets bas, comme Anki le fait lui-meme.
    """
    def champ(texte: Any) -> str:
        return " ".join(str(texte or "").split())

    # « Tab » avec sa majuscule : c'est la valeur que le manuel ecrit.
    lignes = ["#separator:Tab", "#html:false",
              "#columns:{}".format("\t".join(colonnes)), "#tags column:3"]
    for carte in cartes:
        lignes.append("\t".join((champ(carte["recto"]), champ(carte["verso"]),
                                 champ(carte.get("theme")).replace(" ", "_"))))
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


STYLE = """
.paquet { max-width: 34rem; margin: 1.5rem auto; }
.carte { border:1px solid var(--bordure); border-radius:14px; min-height:14rem;
         padding:1.4rem 1.3rem; display:flex; flex-direction:column;
         justify-content:center; text-align:center; cursor:pointer;
         background:var(--encadre); }
.carte .theme { color:var(--doux); font-size:.8rem; margin:0 0 .6em;
                font-family:Helvetica,Arial,sans-serif; }
.carte .face { font-size:1.2rem; margin:0; }
.carte.retournee .face { font-size:1.02rem; }
.commandes { display:flex; gap:.6rem; justify-content:center; flex-wrap:wrap;
             margin:1rem 0 0; }
.commandes button { font:600 .95rem Helvetica,Arial,sans-serif;
                    color:var(--encre); background:var(--fond);
                    border:1px solid var(--bordure); border-radius:9px;
                    padding:.6em 1.1em; cursor:pointer; }
.compteur { text-align:center; color:var(--doux); font-size:.9rem;
            font-family:Helvetica,Arial,sans-serif; }
@media print { .commandes, .compteur { display:none; } }
"""

# Ecrit a la main et fige, comme celui du quiz : il ne vient jamais d'un
# modele, et un test le passe a « node --check » quand node est la.
SCRIPT = """
(function () {
  var cartes = JSON.parse(document.getElementById('cartes').textContent);
  var textes = JSON.parse(document.getElementById('textes-cartes').textContent);
  var ordre = cartes.map(function (_c, i) { return i; });
  var rang = 0;
  var retournee = false;
  var carte = document.getElementById('carte');
  var face = document.getElementById('face');
  var theme = document.getElementById('theme');
  var compteur = document.getElementById('compteur');

  function montrer() {
    var c = cartes[ordre[rang]];
    theme.textContent = c.theme || '';
    face.textContent = retournee ? c.verso : c.recto;
    carte.className = 'carte' + (retournee ? ' retournee' : '');
    compteur.textContent = textes.compteur
      .replace('{n}', String(rang + 1)).replace('{total}', String(cartes.length));
  }
  function retourner() { retournee = !retournee; montrer(); }
  function aller(pas) {
    rang = (rang + pas + cartes.length) % cartes.length;
    retournee = false;
    montrer();
  }
  function melanger() {
    for (var i = ordre.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = ordre[i]; ordre[i] = ordre[j]; ordre[j] = t;
    }
    rang = 0; retournee = false; montrer();
  }
  carte.addEventListener('click', retourner);
  carte.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); retourner(); }
  });
  document.getElementById('precedente').addEventListener('click', function () { aller(-1); });
  document.getElementById('suivante').addEventListener('click', function () { aller(1); });
  document.getElementById('retourner').addEventListener('click', retourner);
  document.getElementById('melanger').addEventListener('click', melanger);
  montrer();
})();
"""


def _echapper(texte: Any) -> str:
    return html.escape(str(texte), quote=True)


def corps(cartes: List[Dict[str, Any]], textes: Dict[str, str],
          intro: str) -> str:
    """Le HTML d'un paquet qu'on retourne au toucher.

    Sans script, la page reste utile : la liste complete des cartes suit le
    paquet, recto puis verso, et c'est elle qui s'imprime.
    """
    cartes = [dict(c, recto=insecables(c["recto"]), verso=insecables(c["verso"]))
              for c in cartes]
    morceaux = ['<p class="compteur">{}</p>'.format(_echapper(intro)),
                '<div class="paquet">',
                '<div class="carte" id="carte" role="button" tabindex="0" '
                'aria-live="polite">',
                '<p class="theme" id="theme"></p><p class="face" id="face">{}'
                '</p></div>'.format(_echapper(cartes[0]["recto"]) if cartes else ""),
                '<p class="compteur" id="compteur"></p>',
                '<p class="commandes">']
    for identifiant in ("precedente", "retourner", "suivante", "melanger"):
        morceaux.append('<button type="button" id="{}">{}</button>'.format(
            identifiant, _echapper(textes[identifiant])))
    morceaux.append("</p></div>")
    morceaux.append("<ol>")
    for carte in cartes:
        morceaux.append("<li><strong>{}</strong><br/>{}</li>".format(
            _echapper(carte["recto"]), _echapper(carte["verso"])))
    morceaux.append("</ol>")
    morceaux.append(
        '<script type="application/json" id="cartes">{}</script>'.format(
            json.dumps(cartes, ensure_ascii=False).replace("</", "<\\/")))
    morceaux.append(
        '<script type="application/json" id="textes-cartes">{}</script>'.format(
            json.dumps(textes, ensure_ascii=False).replace("</", "<\\/")))
    return "\n".join(morceaux)
