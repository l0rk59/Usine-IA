"""Cartes de revision : une chose a retenir par carte, recto et verso.

Ce n'est ni le quiz ni le memo. Le quiz mesure avec des propositions et une
explication ; le memo tient sur une page qu'on consulte. Une carte sert a
se tester SEUL, cent fois, en espacant les passages — et ce que l'acheteur
paie, c'est de pouvoir l'imprimer recto-verso, la decouper, ou la charger
dans Anki sans rien retaper. Trois livrables que les autres chaines ne
savent pas faire : voir « render/cartes.py ».

Les cartes s'ecrivent par lots. Un lot est une section au sens de
« Redaction » : il va au carnet des qu'il est ecrit, une reprise ne le
repaie pas, et un lot perdu est note en echec — le paquet sort alors
inacheve, et « usine reprendre » n'ecrit que ce qui manque. Chaque lot
recoit les rectos deja ecrits, pour ne pas les redemander.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..agents import equipe
from ..render import cartes as rendu
from ..render import document as D
from ..render import libelles, livraison
from ..render.page import ecrire_page
from ..render.pdf import DocumentPDF
from .base import Contexte, Redaction, preparer, renommer, slug, terminer
from .quiz import NIVEAUX

LOT = 12
NOMBRE_MIN, NOMBRE_MAX = 8, 120
NIVEAU_PAR_DEFAUT = "intermediaire"


def _rediger_lot(ctx: Contexte, combien: int, niveau: str,
                 deja: List[str]) -> List[Dict[str, str]]:
    invite = (
        "Ecris {n} cartes de revision sur : {sujet}\n"
        "PUBLIC : {audience}\nNIVEAU : {niveau}\n{deja}\n"
        "Une carte = UNE chose a retenir.\n"
        "- 'recto' : une question precise, ou un terme a definir. 15 mots au "
        "plus. Jamais une question qui se repond par oui ou par non.\n"
        "- 'verso' : la reponse, juste et complete, qui se comprend sans "
        "relire le recto. 45 mots au plus : elle doit tenir sur une carte "
        "imprimee.\n"
        "- 'theme' : deux ou trois mots, pour regrouper les cartes.\n"
        "Deux cartes ne portent jamais sur la meme chose.\n\n"
        "Schema JSON exact :\n"
        '{{"cartes": [{{"recto": "...", "verso": "...", "theme": "..."}}]}}'
    ).format(n=combien, sujet=ctx.sujet, audience=ctx.audience, niveau=niveau,
             deja=("DEJA ECRITES, ne les reprends pas : " + " | ".join(deja[-40:])
                   if deja else ""))
    donnees = equipe.FORMATEUR.travailler_json(
        ctx, invite, role_modele="standard", temperature=0.6,
        max_tokens=150 * combien + 400)
    brutes = donnees.get("cartes") if isinstance(donnees, dict) else donnees
    return [c for c in (_valider(b) for b in (brutes or [])) if c]


def _valider(brute: Any) -> Any:
    """Une carte dont une face est vide, ou dont le verso repete le recto,
    n'apprend rien : elle est ecartee plutot qu'imprimee."""
    if not isinstance(brute, dict):
        return None
    recto = D.nettoyer_inline(str(brute.get("recto") or "")).strip()
    verso = D.nettoyer_inline(str(brute.get("verso") or "")).strip()
    if not recto or not verso or recto.lower() == verso.lower():
        return None
    return {"recto": recto, "verso": verso,
            "theme": D.nettoyer_inline(str(brute.get("theme") or "")).strip()}


def _cle(carte: Dict[str, str]) -> str:
    return " ".join(carte["recto"].lower().split()).strip(" ?.!")


def produire(ctx: Contexte, nombre: int = 40, niveau: str = "") -> Dict[str, Any]:
    nombre = max(NOMBRE_MIN, min(int(nombre or 40), NOMBRE_MAX))
    if niveau not in NIVEAUX:
        ctx.journal("  niveau : {} (personne ne l'a choisi)".format(
            NIVEAU_PAR_DEFAUT))
        niveau = NIVEAU_PAR_DEFAUT
    t = libelles.textes(ctx.langue_iso)
    titre = t["cartes_titre"].format(nombre=nombre, sujet=ctx.sujet)
    dossier = preparer(ctx, "cartes", titre)

    lots = (nombre + LOT - 1) // LOT
    ctx.journal("Étape 1/2 — rédaction de {} cartes, en {} lot(s)...".format(
        nombre, lots))
    redaction = Redaction(ctx, dossier)
    cartes: List[Dict[str, str]] = []
    vues = set()
    ecartees = 0
    for rang in range(1, lots + 1):
        combien = min(LOT, nombre - (rang - 1) * LOT)
        deja = [c["recto"] for c in cartes]
        texte = redaction.ecrire(
            "lot-{}".format(rang), "{} carte(s)".format(combien),
            lambda: json.dumps(_rediger_lot(ctx, combien, niveau, deja),
                               ensure_ascii=False))
        if texte is None:
            continue
        for carte in json.loads(texte):
            if _cle(carte) in vues:
                ecartees += 1
                continue
            vues.add(_cle(carte))
            cartes.append(carte)
        ctx.journal("  lot {}/{} : {} carte(s) au total".format(
            rang, lots, len(cartes)))
    if not cartes:
        if redaction.cause is not None:
            raise redaction.cause
        raise ValueError("Aucune carte exploitable")
    if ecartees:
        ctx.journal("  {} carte(s) écartées : elles répétaient une carte "
                    "déjà écrite.".format(ecartees))
    # Le manque est dit, pas corrige : un paquet de trente-deux cartes vendu
    # pour quarante est un paquet troue, et c'est a l'etape de le porter.
    if not redaction.manquants:
        ctx.etape("cartes", "anomalie" if len(cartes) < nombre else "ok",
                  "{} carte(s) sur {} demandées".format(len(cartes), nombre))
    if len(cartes) != nombre:
        titre = renommer(ctx, t["cartes_titre"].format(
            nombre=len(cartes), sujet=ctx.sujet))

    ctx.journal("Étape 2/2 — planches, fichier Anki et page...")
    fichiers = _exporter(ctx, titre, cartes, t)
    resume = {
        "produit_id": ctx.produit_id,
        "titre": titre,
        "dossier": str(dossier),
        "cartes": len(cartes),
        "themes": sorted({c["theme"] for c in cartes if c["theme"]}),
        "fichiers": [f.name for f in fichiers],
        "budget_epuise": redaction.budget_epuise,
    }
    terminer(ctx, fichiers, {"cartes": len(cartes), "niveau": niveau,
                             "manquants": redaction.manquants})
    (dossier / "produit.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume


def _exporter(ctx: Contexte, titre: str, cartes: List[Dict[str, str]],
              t: Dict[str, Any]) -> List[Path]:
    dossier = ctx.dossier
    nom_anki = t["fichier_anki"]
    mode_emploi = "\n\n".join([
        t["cartes_impression"],
        t["cartes_anki"].format(fichier=nom_anki),
        t["cartes_methode"]])
    liste = "\n".join("{}. **{}** — {}".format(rang, c["recto"], c["verso"])
                      for rang, c in enumerate(cartes, 1))
    mesure: Dict[str, int] = {}

    def planches(_couverture) -> DocumentPDF:
        doc = DocumentPDF(titre_document=titre, auteur=ctx.auteur,
                          police_corps="Helvetica", langue=ctx.langue_iso)
        mesure.update(rendu.planches(doc, cartes))
        return doc

    produit = livraison.Produit(
        type="cartes", sommaire=False, titre=titre,
        sous_titre=t["cartes_sous_titre"], promesse=t["cartes_promesse"],
        blocs=[livraison.Bloc(titre=t["cartes_mode_emploi_titre"],
                              corps=mode_emploi),
               livraison.Bloc(titre=t["cartes_liste_titre"], corps=liste)],
        tableaux=[livraison.Tableau(
            nom="cartes", colonnes=list(t["cartes_colonnes"]),
            lignes=[[c["recto"], c["verso"], c["theme"]] for c in cartes],
            bom=True)],
        donnees={"titre": titre, "cartes": cartes},
        nom_donnees="cartes",
        formats=("md", "pdf", "html"),
        police_corps="Helvetica",
        style_couverture="flashcards spread on a desk, study cards, clean",
        nom_fichier=slug(titre, 48),
        documents=[(t["fichier_planches"], planches)],
    )
    fichiers = livraison.livrer(ctx, produit)
    # Une face coupee sur la planche est une carte qu'on ne peut plus lire
    # imprimee. Le produit reste entier — la page et Anki ont le texte
    # complet — mais c'est au vendeur de le savoir avant de vendre.
    if mesure.get("coupees"):
        ctx.journal("  [!] {} face(s) trop longue(s) pour la planche : texte "
                    "coupé à l'impression.".format(mesure["coupees"]))
        ctx.etape("planches", "anomalie",
                  "{} face(s) coupée(s)".format(mesure["coupees"]))

    fichiers.append(rendu.fichier_anki(dossier / nom_anki, cartes,
                                       tuple(t["cartes_colonnes"])))
    chemin = dossier / t["fichier_page_cartes"]
    ecrire_page(chemin, titre,
                rendu.corps(cartes, t["cartes_script"], t["cartes_intro_page"]),
                t["cartes_sous_titre"], ctx.auteur, langue=ctx.langue_iso,
                style=rendu.STYLE, script=rendu.SCRIPT)
    fichiers.append(chemin)
    return fichiers
