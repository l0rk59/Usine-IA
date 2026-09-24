"""Quiz auto-corrige : une page HTML autonome, sans reseau ni bibliotheque.

Une mini-formation sans exercice corrige laisse l'apprenant sans moyen de
savoir s'il a compris. Le cahier d'exercices demande de produire un livrable
— c'est le coeur de la formation — mais il ne dit jamais « vous vous etes
trompe ici, et voila pourquoi ».

Trois contraintes ont dicte la forme :

  1. **un seul fichier**, ouvrable hors ligne depuis un telephone ou un
     ordinateur, sans serveur. Le HTML porte donc ses styles et son script ;
  2. **zero bibliotheque**, comme partout ailleurs dans ce projet. Une
     quarantaine de lignes de JavaScript suffisent a corriger un QCM ;
  3. **utilisable au clavier et au lecteur d'ecran** : chaque question est un
     « fieldset » avec sa « legend », chaque proposition une vraie
     « radio » etiquetee, et le resultat est annonce par une region « live ».

Les bonnes reponses sont dans le fichier. Elles y sont forcement : une page
qui se corrige seule, sans serveur, les porte. C'est une auto-evaluation,
pas un examen — le dire dans la page evite le malentendu.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

from . import libelles
from .document import nettoyer_inline

# Teintes propres au quiz. Elles sont declarees dans render/lisibilite.py et
# verifiees par la suite de tests : une teinte ajoutee ici doit y etre classee.
STYLE = """
.quiz-intro { color:var(--doux); font-size:.95rem; }
.question { border:1px solid var(--bordure); border-radius:10px;
            padding:1rem 1.15rem; margin:1.4em 0; }
.question > legend { font-family:Helvetica,Arial,sans-serif; font-weight:700;
                     padding:0 .4em; font-size:.95rem; }
.question ol { list-style:none; padding:0; margin:.6em 0 0; }
.question li { margin:0 0 .55em; }
.question label { display:flex; gap:.6rem; align-items:flex-start;
                  cursor:pointer; padding:.35em .5em; border-radius:8px; }
.question label:hover { background:var(--encadre); }
.question input { margin-top:.35em; }
.verdict { margin:.8em 0 0; font-size:.92rem; font-family:Helvetica,Arial,sans-serif; }
.juste { color:#14663f; background:#e9f6ef; border-radius:8px; padding:.5em .7em; }
.faux { color:#9b1c1c; background:#fdecec; border-radius:8px; padding:.5em .7em; }
.score { font-family:Helvetica,Arial,sans-serif; font-size:1.05rem;
         font-weight:700; margin:1.6em 0 0; }
button.corriger { font:600 1rem Helvetica,Arial,sans-serif; color:#ffffff;
                  background:#2563eb; border:0; border-radius:9px;
                  padding:.7em 1.4em; cursor:pointer; }
button.corriger:hover { background:#1d4ed8; }
@media (prefers-color-scheme: dark) {
  .juste { color:#6ee7a8; background:#12211a; }
  .faux { color:#fca5a5; background:#24161a; }
  button.corriger { background:#60a5fa; color:#0f1218; }
  button.corriger:hover { background:#2563eb; color:#ffffff; }
}
@media print { button.corriger { display:none; } }
"""

# Le script est ecrit a la main et fige : il ne vient jamais d'un modele.
# C'est pourquoi il n'est pas soumis au verificateur de la chaine
# « logiciel » — un test le passe a « node --check » quand node est la.
SCRIPT = """
(function () {
  var donnees = JSON.parse(document.getElementById('reponses').textContent);
  var textes = JSON.parse(document.getElementById('textes-quiz').textContent);
  var formulaire = document.getElementById('quiz');

  function corriger(evenement) {
    evenement.preventDefault();
    var justes = 0;
    var sansReponse = 0;
    donnees.forEach(function (question, index) {
      var choisi = formulaire.querySelector('input[name="q' + index + '"]:checked');
      var verdict = document.getElementById('verdict-' + index);
      if (!choisi) {
        sansReponse += 1;
        verdict.className = 'verdict';
        verdict.textContent = textes.sans_reponse;
        return;
      }
      var bonne = Number(choisi.value) === question.reponse;
      if (bonne) { justes += 1; }
      verdict.className = 'verdict ' + (bonne ? 'juste' : 'faux');
      verdict.textContent = (bonne ? textes.juste : textes.faux_avant
        + question.propositions[question.reponse] + textes.faux_apres)
        + question.explication;
    });
    var score = document.getElementById('score');
    score.textContent = justes + textes.score_sur + donnees.length
      + (sansReponse ? ' — ' + sansReponse + textes.sans_reponse_nombre : '.');
  }

  formulaire.addEventListener('submit', corriger);
})();
"""


def _echapper(texte: str) -> str:
    return html.escape(str(texte), quote=True)


def corps(questions: List[Dict[str, Any]], promesse: str = "",
          langue: str = "fr") -> str:
    """Le HTML du quiz : un formulaire, une question par « fieldset ».

    Ses textes fixes suivent la langue du produit, jusqu'a ceux que le script
    affiche en corrigeant : ils arrivent par un bloc JSON, et non ecrits dans
    le script, qui reste le meme pour toutes les langues.
    """
    t = libelles.textes(langue)
    morceaux = []
    if promesse:
        morceaux.append('<p class="quiz-intro">{}</p>'.format(
            _echapper(nettoyer_inline(promesse))))
    morceaux.append('<p class="quiz-intro">{}</p>'.format(
        _echapper(t["quiz_intro"])))
    morceaux.append('<form id="quiz">')

    module_courant = ""
    for index, question in enumerate(questions):
        if question.get("module") and question["module"] != module_courant:
            module_courant = question["module"]
            morceaux.append("<h2>{}</h2>".format(_echapper(module_courant)))
        morceaux.append('<fieldset class="question">')
        morceaux.append("<legend>{}. {}</legend>".format(
            index + 1, _echapper(question["question"])))
        morceaux.append("<ol>")
        for rang, proposition in enumerate(question["propositions"]):
            identifiant = "q{}-{}".format(index, rang)
            morceaux.append(
                '<li><label for="{id}">'
                '<input type="radio" id="{id}" name="q{index}" value="{rang}"/>'
                "<span>{texte}</span></label></li>".format(
                    id=identifiant, index=index, rang=rang,
                    texte=_echapper(proposition)))
        morceaux.append("</ol>")
        # « aria-live » : le lecteur d'ecran annonce le verdict au moment ou
        # il apparait, sans que l'utilisateur ait a le chercher.
        morceaux.append(
            '<p class="verdict" id="verdict-{}" role="status" '
            'aria-live="polite"></p>'.format(index))
        morceaux.append("</fieldset>")

    morceaux.append('<p><button type="submit" class="corriger">'
                    "{}</button></p>".format(_echapper(t["quiz_corriger"])))
    morceaux.append('<p class="score" id="score" role="status" '
                    'aria-live="polite"></p>')
    morceaux.append("</form>")
    morceaux.append(
        '<script type="application/json" id="reponses">{}</script>'.format(
            json.dumps(questions, ensure_ascii=False).replace("</", "<\\/")))
    morceaux.append(
        '<script type="application/json" id="textes-quiz">{}</script>'.format(
            json.dumps(t["quiz_script"], ensure_ascii=False).replace("</", "<\\/")))
    return "\n".join(morceaux)


def ecrire(chemin: Path, titre: str, questions: List[Dict[str, Any]],
           promesse: str = "", langue: str = "fr") -> Path:
    """Ecrit la page complete, dans le style des autres pages livrees."""
    from .page import ecrire_page

    return ecrire_page(
        chemin, libelles.libelle(langue, "quiz_titre", titre=titre),
        corps(questions, promesse, langue),
        sous_titre=libelles.libelle(langue, "quiz_sous_titre",
                                    nombre=len(questions)),
        langue=langue, style=STYLE, script=SCRIPT)
