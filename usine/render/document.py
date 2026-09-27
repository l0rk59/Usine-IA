"""Modele de document intermediaire.

L'IA produit du Markdown. On le convertit une seule fois en blocs, puis chaque
format (PDF, EPUB, HTML, TXT) consomme ces blocs. Un seul analyseur a maintenir.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Bloc:
    type: str      # h1 h2 h3 p ul ol quote callout hr code image table
    texte: str = ""
    elements: List[str] = field(default_factory=list)
    titre: str = ""                 # utilise par 'callout'
    url: str = ""                   # utilise par 'image'
    # utilises par 'table' : la ligne d'en-tete, puis les lignes de donnees
    entetes: List[str] = field(default_factory=list)
    rangees: List[List[str]] = field(default_factory=list)


_TITRE = re.compile(r"^(#{1,6})\s+(.*)$")
_PUCE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMERO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_CITATION = re.compile(r"^>\s?(.*)$")
_REGLE = re.compile(r"^\s*([-*_])\s*\1\s*\1[\s\-*_]*$")
_ENCADRE = re.compile(r"^\s*(?:>\s*)?\*\*(À retenir|A retenir|Astuce|Exercice|Action|"
                      r"En pratique|Attention|Resume|Résumé)\s*:?\*\*\s*(.*)$", re.IGNORECASE)

_GRAS = re.compile(r"\*\*(.+?)\*\*")
# Pas d'espace juste apres l'etoile ouvrante ni juste avant la fermante,
# comme en markdown : « 5 * 3 * 2 » est une multiplication, pas de l'italique.
# Sans cette condition, le nettoyage du PDF rendait « 5  3  2 ».
_ITALIQUE = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
_CODE_INLINE = re.compile(r"`([^`]+)`")
_LIEN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Une image SEULE sur sa ligne. Le modele de document ignorait cette forme :
# elle tombait dans « paragraphe », et « ![](images/page-01.png) » sortait
# imprime tel quel, crochets et parentheses compris, dans le PDF, le HTML,
# l'EPUB et le texte brut. Un conte de quatorze doubles-pages livrait ainsi
# quatorze illustrations produites, enregistrees sur le disque, et visibles
# nulle part. Le defaut ne se voyait qu'en OUVRANT le produit : le markdown,
# lui, etait correct depuis le debut.
_IMAGE_SEULE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
# Un tableau markdown : une ligne d'en-tete, une ligne de separation faite de
# tirets, puis les rangees. Le modele de document l'ignorait, et trois chaines
# en produisent — la notice d'un outil logiciel, la boite a outils, les
# modeles. Le tableau sortait donc en TUYAUX ET TIRETS BRUTS :
#
#     | Fichier | Verification | Resultat | | --- | --- | --- | | outil.py |
#
# dans le PDF, dans le HTML et dans le texte brut. Le markdown, lui, etait
# correct — le defaut ne se voyait qu'en ouvrant le produit.
_LIGNE_TABLEAU = re.compile(r"^\s*\|(.+)\|\s*$")
_SEPARATEUR_TABLEAU = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


# Le navigateur et la liseuse coupent a toute espace ordinaire : le « » »
# d'une citation tombait seul en tete de ligne, comme dans le PDF (voir
# « _mots_insecables » dans render/pdf.py). L'espace insecable le colle a
# son mot. Le code en ligne n'y passe pas : une espace insecable copiee
# dans un terminal n'est plus une espace.
_AVANT_INSECABLE = re.compile(r"(?<=«)[ \t]+|[ \t]+(?=[»:;!?])")


def insecables(texte: str) -> str:
    return _AVANT_INSECABLE.sub("\u00a0", texte)


def _cellules(ligne: str) -> List[str]:
    corps = _LIGNE_TABLEAU.match(ligne)
    return [c.strip() for c in corps.group(1).split("|")] if corps else []


def nettoyer_inline(texte: str) -> str:
    """Retire le balisage inline (pour le PDF et le texte brut)."""
    texte = _LIEN.sub(r"\1 (\2)", texte)
    texte = _GRAS.sub(r"\1", texte)
    texte = _ITALIQUE.sub(r"\1", texte)
    texte = _CODE_INLINE.sub(r"\1", texte)
    return texte.strip()


def inline_html(texte: str) -> str:
    """Convertit le balisage inline en HTML, en echappant le reste."""
    jetons: Dict[str, str] = {}

    def reserver(rendu: str) -> str:
        cle = "\x00{}\x00".format(len(jetons))
        jetons[cle] = rendu
        return cle

    texte = _LIEN.sub(
        lambda m: reserver('<a href="{}">{}</a>'.format(
            html.escape(m.group(2), quote=True), html.escape(insecables(m.group(1))))),
        texte,
    )
    texte = _GRAS.sub(lambda m: reserver("<strong>{}</strong>".format(html.escape(insecables(m.group(1))))), texte)
    texte = _ITALIQUE.sub(lambda m: reserver("<em>{}</em>".format(html.escape(insecables(m.group(1))))), texte)
    texte = _CODE_INLINE.sub(lambda m: reserver("<code>{}</code>".format(html.escape(m.group(1)))), texte)
    texte = html.escape(insecables(texte))
    for cle, rendu in jetons.items():
        texte = texte.replace(html.escape(cle), rendu).replace(cle, rendu)
    return texte


def analyser(markdown: str) -> List[Bloc]:
    """Markdown -> liste de blocs."""
    blocs: List[Bloc] = []
    lignes = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    paragraphe: List[str] = []

    def vider() -> None:
        if paragraphe:
            texte = " ".join(paragraphe).strip()
            if texte:
                blocs.append(Bloc("p", texte))
            paragraphe.clear()

    while i < len(lignes):
        ligne = lignes[i]
        nu = ligne.strip()

        if not nu:
            vider()
            i += 1
            continue

        if nu.startswith("```"):
            vider()
            i += 1
            tampon: List[str] = []
            while i < len(lignes) and not lignes[i].strip().startswith("```"):
                tampon.append(lignes[i])
                i += 1
            i += 1
            blocs.append(Bloc("code", "\n".join(tampon)))
            continue

        if _REGLE.match(nu):
            vider()
            blocs.append(Bloc("hr"))
            i += 1
            continue

        titre = _TITRE.match(nu)
        if titre:
            vider()
            niveau = min(len(titre.group(1)), 3)
            blocs.append(Bloc("h{}".format(niveau), nettoyer_inline(titre.group(2))))
            i += 1
            continue

        encadre = _ENCADRE.match(nu)
        if encadre:
            vider()
            corps = [encadre.group(2).strip()]
            i += 1
            while i < len(lignes) and lignes[i].strip() and not _TITRE.match(lignes[i].strip()) \
                    and not _PUCE.match(lignes[i]) and not _ENCADRE.match(lignes[i].strip()):
                corps.append(lignes[i].strip().lstrip("> ").strip())
                i += 1
            blocs.append(Bloc("callout", " ".join(c for c in corps if c),
                              titre=encadre.group(1).strip()))
            continue

        if _PUCE.match(ligne) or _NUMERO.match(ligne):
            vider()
            ordonnee = bool(_NUMERO.match(ligne)) and not _PUCE.match(ligne)
            elements: List[str] = []
            while i < len(lignes):
                courante = lignes[i]
                puce = _PUCE.match(courante) or _NUMERO.match(courante)
                if puce:
                    elements.append(puce.group(1).strip())
                    i += 1
                elif courante.strip() and courante.startswith(("  ", "\t")) and elements:
                    elements[-1] += " " + courante.strip()
                    i += 1
                else:
                    break
            blocs.append(Bloc("ol" if ordonnee else "ul", elements=elements))
            continue

        citation = _CITATION.match(nu)
        if citation:
            vider()
            morceaux = [citation.group(1).strip()]
            i += 1
            while i < len(lignes) and _CITATION.match(lignes[i].strip()):
                morceaux.append(_CITATION.match(lignes[i].strip()).group(1).strip())
                i += 1
            blocs.append(Bloc("quote", " ".join(morceaux).strip()))
            continue

        if _LIGNE_TABLEAU.match(nu) and i + 1 < len(lignes) \
                and _SEPARATEUR_TABLEAU.match(lignes[i + 1].strip()):
            vider()
            entetes = [nettoyer_inline(c) for c in _cellules(nu)]
            i += 2
            rangees = []
            while i < len(lignes) and _LIGNE_TABLEAU.match(lignes[i].strip()):
                rangees.append([nettoyer_inline(c)
                                for c in _cellules(lignes[i].strip())])
                i += 1
            blocs.append(Bloc("table", entetes=entetes, rangees=rangees))
            continue

        image = _IMAGE_SEULE.match(nu)
        if image:
            vider()
            blocs.append(Bloc("image", image.group(1).strip(),
                              url=image.group(2).strip()))
            i += 1
            continue

        paragraphe.append(nu)
        i += 1

    vider()
    return blocs


def vers_texte(blocs: List[Bloc]) -> str:
    """Rendu texte brut (lisible partout, y compris dans un terminal Termux)."""
    sortie: List[str] = []
    for bloc in blocs:
        if bloc.type == "h1":
            sortie.append("\n" + bloc.texte.upper())
            sortie.append("=" * min(len(bloc.texte), 70))
        elif bloc.type == "h2":
            sortie.append("\n" + bloc.texte)
            sortie.append("-" * min(len(bloc.texte), 70))
        elif bloc.type == "h3":
            sortie.append("\n" + bloc.texte)
        elif bloc.type in ("ul", "ol"):
            for index, element in enumerate(bloc.elements, 1):
                puce = "{}.".format(index) if bloc.type == "ol" else "-"
                sortie.append("  {} {}".format(puce, nettoyer_inline(element)))
        elif bloc.type == "quote":
            sortie.append("  | " + nettoyer_inline(bloc.texte))
        elif bloc.type == "callout":
            sortie.append("\n[{}] {}".format(bloc.titre.upper(), nettoyer_inline(bloc.texte)))
        elif bloc.type == "hr":
            sortie.append("\n" + "* * *")
        elif bloc.type == "code":
            sortie.extend("    " + l for l in bloc.texte.split("\n"))
        elif bloc.type == "table":
            # En texte brut, les tuyaux sont la forme la plus lisible qui
            # existe : on les garde, alignes sur la largeur de chaque colonne.
            colonnes = [bloc.entetes] + bloc.rangees
            largeurs = [max(len(str(r[i])) if i < len(r) else 0 for r in colonnes)
                        for i in range(len(bloc.entetes))]
            def _ligne(valeurs):
                return "  " + " | ".join(
                    str(valeurs[i] if i < len(valeurs) else "").ljust(largeurs[i])
                    for i in range(len(largeurs)))
            sortie.append(_ligne(bloc.entetes))
            sortie.append("  " + "-+-".join("-" * l for l in largeurs))
            sortie.extend(_ligne(r) for r in bloc.rangees)
        elif bloc.type == "image":
            # Le texte brut ne montre pas d'image : il dit qu'il y en a une,
            # et ce qu'elle represente quand le texte de remplacement le dit.
            sortie.append("[Illustration{}]".format(
                " : " + bloc.texte if bloc.texte else ""))
        else:
            sortie.append(nettoyer_inline(bloc.texte))
        sortie.append("")
    return "\n".join(sortie).strip() + "\n"


def vers_html(blocs: List[Bloc], niveau_depart: int = 1) -> str:
    """Fragment HTML (sans <html>), reutilise par l'EPUB et la page web."""
    sortie: List[str] = []
    for bloc in blocs:
        if bloc.type in ("h1", "h2", "h3"):
            niveau = min(int(bloc.type[1]) + niveau_depart - 1, 6)
            sortie.append("<h{n}>{t}</h{n}>".format(n=niveau, t=inline_html(bloc.texte)))
        elif bloc.type in ("ul", "ol"):
            items = "".join("<li>{}</li>".format(inline_html(e)) for e in bloc.elements)
            sortie.append("<{t}>{i}</{t}>".format(t=bloc.type, i=items))
        elif bloc.type == "quote":
            sortie.append("<blockquote><p>{}</p></blockquote>".format(inline_html(bloc.texte)))
        elif bloc.type == "callout":
            sortie.append(
                '<aside class="encadre"><p class="encadre-titre">{}</p><p>{}</p></aside>'.format(
                    html.escape(bloc.titre), inline_html(bloc.texte)
                )
            )
        elif bloc.type == "hr":
            sortie.append("<hr/>")
        elif bloc.type == "code":
            sortie.append("<pre><code>{}</code></pre>".format(html.escape(bloc.texte)))
        elif bloc.type == "table":
            entete = "".join("<th>{}</th>".format(inline_html(c))
                             for c in bloc.entetes)
            corps = "".join(
                "<tr>{}</tr>".format("".join(
                    "<td>{}</td>".format(inline_html(str(c))) for c in rangee))
                for rangee in bloc.rangees)
            sortie.append("<table><thead><tr>{}</tr></thead>"
                          "<tbody>{}</tbody></table>".format(entete, corps))
        elif bloc.type == "image":
            sortie.append(
                '<p class="illustration"><img src="{}" alt="{}"/></p>'.format(
                    html.escape(bloc.url, quote=True), html.escape(bloc.texte)))
        else:
            sortie.append("<p>{}</p>".format(inline_html(bloc.texte)))
    return "\n".join(sortie)


def vers_pdf(blocs: List[Bloc], doc, sauter_h1: bool = False) -> None:
    """Ecrit les blocs dans un DocumentPDF."""
    for bloc in blocs:
        if bloc.type == "h1":
            if sauter_h1:
                continue
            doc.titre(bloc.texte, 1)
        elif bloc.type == "h2":
            doc.titre(bloc.texte, 2)
        elif bloc.type == "h3":
            doc.titre(bloc.texte, 3)
        elif bloc.type == "ul":
            doc.liste([nettoyer_inline(e) for e in bloc.elements])
        elif bloc.type == "ol":
            doc.liste(
                ["{}. {}".format(i, nettoyer_inline(e)) for i, e in enumerate(bloc.elements, 1)],
                puce=" ",
            )
        elif bloc.type == "quote":
            doc.citation(nettoyer_inline(bloc.texte))
        elif bloc.type == "callout":
            doc.encadre(bloc.titre, nettoyer_inline(bloc.texte))
        elif bloc.type == "hr":
            doc.separateur()
        elif bloc.type == "code":
            doc.paragraphe(bloc.texte, taille=9.5, police="Helvetica", justifier=False,
                           brut=True)
        elif bloc.type == "table":
            # « doc.tableau » existait depuis le debut, avec ses colonnes
            # egales et son en-tete colore. Rien ne l'appelait depuis le
            # markdown : le tableau passait par « paragraphe » et sortait en
            # tuyaux.
            doc.tableau(bloc.entetes, bloc.rangees)
        elif bloc.type == "image":
            # Le modele de document ne porte qu'un CHEMIN, pas les octets : il
            # ne sait pas ou est le dossier du produit et n'ouvre aucun
            # fichier. Une chaine qui veut l'image dans son PDF la place
            # elle-meme, par « rendu_pdf », ou elle a les octets. Ici, on dit
            # qu'il y a une image plutot que d'imprimer son chemin.
            if bloc.texte:
                doc.encadre("Illustration", bloc.texte)
        else:
            doc.paragraphe(nettoyer_inline(bloc.texte), justifier=True)


def compter_mots(markdown: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", markdown, re.UNICODE))
