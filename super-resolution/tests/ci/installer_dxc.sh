#!/usr/bin/env bash
# Installe dxc (Linux x86-64) depuis les versions publiees par Microsoft :
# prend la plus recente qui fournit un binaire Linux (les noms de fichiers
# et le contenu des versions changent d'une publication a l'autre).
# Ecrit DXC, USR_DXC et LD_LIBRARY_PATH dans $GITHUB_ENV s'il existe.
#   GH_TOKEN=... tests/ci/installer_dxc.sh [dossier]
set -euo pipefail
DEST="${1:-/tmp/dxc}"
REPO=microsoft/DirectXShaderCompiler
mkdir -p "$DEST/x"
trouve=""
for tag in $(gh release list -R "$REPO" --limit 20 --json tagName -q '.[].tagName'); do
    for motif in 'linux_dxc_*x86_64*.tar.gz' 'linux_dxc_*.tar.gz' '*linux*x64*.tar.gz'; do
        if gh release download "$tag" -R "$REPO" --pattern "$motif" -D "$DEST" \
               --clobber >/dev/null 2>&1; then
            trouve="$tag"
            break 2
        fi
    done
done
[ -n "$trouve" ] || { echo "aucune version de dxc pour Linux trouvee" >&2; exit 1; }
archive=$(ls "$DEST"/*.tar.gz | head -n 1)
tar -xzf "$archive" -C "$DEST/x"
DXC=$(find "$DEST/x" -type f -name dxc | head -n 1)
LIB=$(dirname "$(find "$DEST/x" -name 'libdxcompiler.so*' | head -n 1)")
chmod +x "$DXC"
LD_LIBRARY_PATH="$LIB" "$DXC" --version
echo "dxc $trouve : $DXC"
if [ -n "${GITHUB_ENV:-}" ]; then
    { echo "DXC=$DXC"; echo "USR_DXC=$DXC"; echo "LD_LIBRARY_PATH=$LIB"; } >> "$GITHUB_ENV"
fi
