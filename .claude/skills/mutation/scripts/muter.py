#!/usr/bin/env python3
"""Remet un defaut dans le code et verifie que la suite le remarque.

Un test qui passe ne prouve rien tant qu'on ne l'a pas vu echouer. C'est
particulierement vrai des garde-fous : un controle ecrit pour attraper un
defaut precis peut tres bien ne jamais s'executer — parce qu'un autre filtre
l'a devance, parce que le cache a servi la reponse d'avant, parce que le cas
choisi ne distinguait pas les deux comportements. Le test est vert, il ne
garde rien, et personne ne le saura avant que le defaut ne revienne.

La verification tient en une phrase : si je remets le defaut, est-ce que la
suite echoue ? Ce script la pose, mutation par mutation.

    python3 .claude/skills/mutation/scripts/muter.py campagne.json

Le fichier decrit chaque mutation :

    [
      {"titre": "le quota se compte par modele",
       "fichier": "usine/core/llm.py",
       "avant": "return p.model_for(role) if ... else \\"\\"",
       "apres": "return \\"\\"",
       "tests": ["tests.test_routeur"]}
    ]

« tests » est optionnel : sans lui, toute la suite tourne, ce qui est plus
lent mais ne rate rien.

Trois verdicts :
  [vu]    la suite echoue quand le defaut revient — le test garde vraiment
  [RATE]  la suite passe quand meme — le test est decoratif, a reecrire
  [?]     le motif n'est plus dans le fichier — la campagne a vieilli

La campagne refuse de demarrer si la suite est deja rouge : sur une suite
rouge, tout est « [vu] », et le rapport annonce que tout est garde au moment
precis ou plus rien ne l'est.

Le code est toujours restaure, y compris sur Ctrl+C : une campagne
interrompue ne doit pas laisser le depot mute.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

RACINE = Path(__file__).resolve().parents[4]


def _lancer(tests: List[str], timeout: int) -> bool:
    """Lance les tests demandes. Rend True si la suite ECHOUE.

    PYTHONDONTWRITEBYTECODE n'est pas une precaution de style : Python
    reutilise un .pyc quand la taille et la date du source n'ont pas change.
    Or une mutation remplace souvent un motif par un autre de MEME longueur,
    et l'ecriture puis la restauration tiennent dans la meme seconde. Le
    resultat est un verdict porte sur du code qui ne tournait plus — un faux
    « [vu] » ou un faux « [RATE] », impossible a distinguer d'un vrai.
    """
    commande = [sys.executable, "-m", "unittest"]
    commande += tests if tests else ["discover", "-s", "tests", "-t", "."]
    commande.append("-q")
    execution = subprocess.run(
        commande, cwd=str(RACINE), capture_output=True, text=True,
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return execution.returncode != 0


def _modules_de(mutations: List[Dict[str, Any]]) -> List[str]:
    """Les modules que la campagne va lancer. Vide = toute la suite."""
    modules: List[str] = []
    for mutation in mutations:
        tests = mutation.get("tests")
        if not tests:
            return []
        for module in tests:
            if module not in modules:
                modules.append(module)
    return modules


def _suite_deja_rouge(mutations: List[Dict[str, Any]], timeout: int) -> bool:
    """Lance les tests de la campagne SANS muter. Vrai s'ils echouent deja.

    Sans ce controle, une campagne jouee sur une suite deja rouge rend « [vu] »
    partout : chaque mutation est « detectee » par un test qui echouait avant
    qu'on ne touche a quoi que ce soit. Le rapport annonce alors que tout est
    garde au moment precis ou plus rien ne l'est — le pire verdict possible
    pour un outil dont le seul role est de ne pas se laisser rassurer.

    Vu le 15/09/2026 : une campagne de quinze mutations rendue entierement
    verte, dont deux ne tenaient qu'a un test casse par un changement de
    format de sortie. Les deux corrections qu'elles pretendaient garder
    n'etaient gardees par rien.
    """
    try:
        return _lancer(_modules_de(mutations), timeout)
    except subprocess.TimeoutExpired:
        print("La suite de reference depasse le delai : verdicts impossibles.")
        return True


def jouer(mutations: List[Dict[str, Any]], timeout: int = 900) -> int:
    """Joue toute la campagne. Rend le nombre de mutations non detectees."""
    survivantes = 0
    for mutation in mutations:
        titre = mutation.get("titre") or mutation["avant"][:40]
        chemin = RACINE / mutation["fichier"]
        original = chemin.read_text(encoding="utf-8")
        if mutation["avant"] not in original:
            print("[?]     {}".format(titre))
            print("        motif absent de {}".format(mutation["fichier"]))
            survivantes += 1
            continue
        if original.count(mutation["avant"]) > 1:
            # Muter la premiere des trois occurrences donne un verdict sur un
            # endroit qu'on n'a pas choisi.
            print("[?]     {}".format(titre))
            print("        motif present {} fois : precisez-le".format(
                original.count(mutation["avant"])))
            survivantes += 1
            continue

        chemin.write_text(
            original.replace(mutation["avant"], mutation["apres"], 1),
            encoding="utf-8")
        try:
            detectee = _lancer(mutation.get("tests") or [], timeout)
        except subprocess.TimeoutExpired:
            detectee = False
            print("        (delai depasse : compte comme non detectee)")
        finally:
            # Meme en cas de Ctrl+C ou d'exception : le depot est rendu propre.
            chemin.write_text(original, encoding="utf-8")

        print("{}  {}".format("[vu]   " if detectee else "[RATE] ", titre))
        if not detectee:
            survivantes += 1
    return survivantes


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    mutations = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    if isinstance(mutations, dict):
        mutations = mutations.get("mutations") or []
    if not mutations:
        print("Campagne vide.")
        return 2

    if _suite_deja_rouge(mutations, 900):
        print("La suite echoue AVANT toute mutation.")
        print("Sur une suite rouge, chaque mutation ressort « [vu] » : c'est le")
        print("test deja casse qui echoue, pas le defaut remis. Reparez d'abord.")
        return 2

    print("{} mutation(s) — le depot est restaure apres chacune.\n"
          .format(len(mutations)))
    survivantes = jouer(mutations)
    print()
    if survivantes:
        print("{} mutation(s) sur {} ne sont gardees par aucun test."
              .format(survivantes, len(mutations)))
        print("Un test qui passe alors que le defaut est revenu ne garde rien.")
        return 1
    print("Les {} mutations sont detectees : chaque correction est gardee."
          .format(len(mutations)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print("\nInterrompu. Verifiez « git status » : le fichier en cours de "
              "mutation a du etre restaure, mais confirmez-le.")
        sys.exit(130)
