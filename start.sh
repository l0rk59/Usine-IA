#!/usr/bin/env bash
# Vitrine statique de l'Usine-IA : le depot est Python pur (zero dependance,
# pas de Node, pas de paquet a compiler), donc il n'y a rien a installer ni a
# compiler ici. On verifie la page prete dans dist/, on publie le descripteur
# attendu par le controleur, puis on sert dist/ au premier plan sur PORT.
set -euo pipefail
time -p cd "$(dirname "$0")"
time -p python3 --version
time -p mkdir -p dist
# « Build when needed » : le site est un HTML statique sans etape de build ;
# on verifie seulement qu'il existe et qu'il n'est pas vide (defaut de script = sortie 1).
time -p test -s dist/index.html
time -p python3 -c "from pathlib import Path; racine = Path('.').resolve(); dist = racine / 'dist'; assert (dist / 'index.html').stat().st_size > 0; print('vitrine:', dist)"
# Descripteur pour le controleur : projet + repertoire statique absolu DANS le depot.
# OPENCODE_WEB_DIR = metadonnees du worker ; la page servie reste dist/ sous PROJECT_DIR.
time -p python3 - "$PWD" "${OPENCODE_WEB_DIR:-/home/runner/work/_temp/omgithub-web}" <<'PY'
import json, sys
from pathlib import Path
racine = Path(sys.argv[1]).resolve()
web = Path(sys.argv[2]); web.mkdir(parents=True, exist_ok=True)
dist = racine / "dist"
assert (dist / "index.html").is_file(), "dist/index.html manquant"
(web / "deployment-output.json").write_text(json.dumps({"project": str(racine), "directory": str(dist)}), encoding="utf-8")
print("descripteur:", web / "deployment-output.json")
PY
# Serveur au premier plan (pas d'arriere-plan : le controleur possede le tmux).
# Le PORT impose par le lanceur prime, 3000 par defaut.
PORT="${PORT:-3000}"
echo "vitrine Usine-IA sur http://0.0.0.0:${PORT}/ (dist/)"
exec python3 -m http.server "${PORT}" --directory dist --bind 0.0.0.0
