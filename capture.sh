#!/usr/bin/env bash
set -euo pipefail
time -p cd "$(dirname "$0")"
if [[ -z "${CAPTURE_URL:-}" || -z "${CAPTURE_DIR:-}" ]]; then
  echo "Set CAPTURE_URL and CAPTURE_DIR." >&2
  exit 1
fi
/usr/bin/time -p mkdir -p "$CAPTURE_DIR"
/usr/bin/time -p node --version
RUNTIME="${RUNTIME_DIR:?RUNTIME_DIR manquant}"
/usr/bin/time -p test -f "$RUNTIME/scripts/default-capture.mjs"
/usr/bin/time -p env CAPTURE_URL="$CAPTURE_URL" CAPTURE_DIR="$CAPTURE_DIR" node "$RUNTIME/scripts/default-capture.mjs"
