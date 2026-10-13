#!/usr/bin/env bash
# Capture de la vitrine : ouvre exactement CAPTURE_URL, attend le rendu,
# saisit final-desktop.png (1440x900) et final-mobile.png (390x844) dans
# CAPTURE_DIR, ferme son propre navigateur, laisse l'appli tourner.
# Sortie 75 = infra volatile (navigation, navigateur, tunnel) ; 1 = defaut de script ou de rendu.
set -euo pipefail
time -p cd "$(dirname "$0")"
if [[ -z "${CAPTURE_URL:-}" ]]; then echo "capture: CAPTURE_URL manquante" >&2; exit 1; fi
if [[ -z "${CAPTURE_DIR:-}" ]]; then echo "capture: CAPTURE_DIR manquant" >&2; exit 1; fi
if [[ -z "${RUNTIME_DIR:-}" ]]; then echo "capture: RUNTIME_DIR manquant" >&2; exit 1; fi
time -p mkdir -p "${CAPTURE_DIR}"
# Le capteur mutualise delivre exactement le contrat ci-dessus (attente body
# visible + fontes chargees, 1 s de repos, PNG bureau + mobile, fermeture dans
# finally, 75 pour le transitoire, 1 sinon) ; on le garde pour ne pas
# reimplementer un navigateur a cote. Sorties hors sources, appli inchangee.
time -p node "${RUNTIME_DIR}/scripts/default-capture.mjs"
status=$?
time -p ls -l "${CAPTURE_DIR}/final-desktop.png" "${CAPTURE_DIR}/final-mobile.png"
exit "$status"
