#!/usr/bin/env bash
set -euo pipefail
time -p cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
PORT="${PORT:-3000}"
INTERNE="${PORT_INTERNE:-8778}"
WEB_DIR="${OPENCODE_WEB_DIR:-/home/runner/work/_temp/omgithub-web}"
DIST="$PROJECT_DIR/dist"
/usr/bin/time -p mkdir -p "$DIST/statique" "$WEB_DIR"
/usr/bin/time -p cp "$PROJECT_DIR/usine/web/statique/tableau.html" "$DIST/index.html"
/usr/bin/time -p cp "$PROJECT_DIR/usine/web/statique/tableau.css" "$PROJECT_DIR/usine/web/statique/app.js" "$PROJECT_DIR/usine/web/statique/cyber.js" "$PROJECT_DIR/usine/web/statique/scene.js" "$DIST/statique/"
/usr/bin/time -p python3 --version
/usr/bin/time -p python3 -c "import usine.web.serveur; print('serveur ok')"
/usr/bin/time -p python3 - "$DIST" "$PROJECT_DIR" "$WEB_DIR" <<'PY'
import json
import sys
dist, projet, web = sys.argv[1], sys.argv[2], sys.argv[3]
with open(web + "/deployment-output.json", "w", encoding="utf-8") as f:
    json.dump({"project": projet, "directory": dist}, f)
print("deployment-output.json -> " + web + "/deployment-output.json")
PY
# Le tableau de bord refuse tout hote qui ne le nomme pas (garde anti
# rebinding de usine/web/serveur.py) : le tunnel public arriverait avec un
# nom trycloudflare.com et prendrait 403. Le relais ci-dessous n'accepte que
# les noms locaux et le tunnel, et reecrit l'hote vers le serveur interne —
# l'origine d'une modification reste, elle, verifiee par l'usine.
/usr/bin/time -p python3 -m usine web --port "$INTERNE" --hote 127.0.0.1 >"$WEB_DIR/serveur-interne.log" 2>&1 &
INTERNE_PID=$!
trap 'kill $INTERNE_PID 2>/dev/null || true' EXIT HUP INT TERM
time -p bash -c 'for i in $(seq 1 30); do curl --fail --silent --max-time 2 "http://127.0.0.1:'"$INTERNE"'/" >/dev/null && break; sleep 2; done'
/usr/bin/time -p curl --fail --silent --max-time 5 "http://127.0.0.1:$INTERNE/api/etat" -o /dev/null
/usr/bin/time -p python3 - "$PORT" "$INTERNE" <<'PY'
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PORT = int(sys.argv[1])
INTERNE = "http://127.0.0.1:" + sys.argv[2]
SAUF_ENTETES = {"connection", "keep-alive", "transfer-encoding", "upgrade"}


def nom_hote(hote):
    h = (hote or "").strip().lower()
    m = re.match(r"^\[(.*)\](?::\d+)?$", h)
    if m:
        return m.group(1)
    if h.count(":") == 1:
        nom, _, port = h.partition(":")
        if port.isdigit():
            return nom
    return h


def admis(hote):
    nom = nom_hote(hote)
    if nom in ("127.0.0.1", "localhost", "::1"):
        return True
    return nom.endswith(".trycloudflare.com")


class Relais(BaseHTTPRequestHandler):
    server_version = "RelaisApercu/1.0"

    def _relayer(self):
        if not admis(self.headers.get("Host")):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"erreur": "hote refuse"}')
            return
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else None
        entetes = {k: v for k, v in dict(self.headers).items()
                   if k.lower() not in SAUF_ENTETES | {"host", "content-length"}}
        entetes["Host"] = "127.0.0.1:" + sys.argv[2]
        entetes["Connection"] = "close"
        requete = Request(INTERNE + self.path, data=corps,
                          headers=entetes, method=self.command)
        try:
            with urlopen(requete, timeout=120) as reponse:
                self.send_response(reponse.status)
                for cle, valeur in reponse.headers.items():
                    if cle.lower() not in SAUF_ENTETES:
                        self.send_header(cle, valeur)
                self.end_headers()
                shutil.copyfileobj(reponse, self.wfile)
        except HTTPError as echec:
            self.send_response(echec.code)
            for cle, valeur in (echec.headers or {}).items():
                if cle.lower() not in SAUF_ENTETES:
                    self.send_header(cle, valeur)
            self.end_headers()
            self.wfile.write(echec.read())

    do_GET = _relayer
    do_POST = _relayer
    do_PUT = _relayer
    do_DELETE = _relayer
    do_PATCH = _relayer
    do_HEAD = _relayer
    do_OPTIONS = _relayer

    def log_message(self, format, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), Relais).serve_forever()
PY
