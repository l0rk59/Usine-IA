#!/usr/bin/env bash
# Bout en bout de USR Universel SANS Windows ni carte graphique : compile la
# bibliotheque + tests/wine/usr_universal_run.cpp avec MinGW, et l'execute
# sous Wine avec vkd3d-proton (Direct3D 12 -> Vulkan, llvmpipe).
#
#   VKD3D_PROTON=/chemin/build-vkd3d-proton DXC=/chemin/dxc \
#       tests/wine/universel_wine.sh entree.bin sortie.bin [poids.bin]
#
# L'entree est produite par tests/test_universel_bout_en_bout.py.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/../.." && pwd)"
IN="$(realpath "$1")"
OUT="$(realpath -m "$2")"
WEIGHTS="${3:+$(realpath "$3")}"
: "${VKD3D_PROTON:?definir VKD3D_PROTON (dossier de construction de vkd3d-proton)}"
: "${DXC:=dxc}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASSES="usr_prepare usr_accumulate usr_sharpen"
UPASSES="usr_u_luma usr_u_down usr_u_grad usr_u_flow usr_u_median usr_u_finalize usr_u_residual usr_u_accumulate usr_u_output"
for p in $PASSES $UPASSES; do
    "$DXC" -T cs_6_0 -E main -O3 -WX ${USR_DXC_FLAGS:-} -Fh "$WORK/$p.h" -Vn "g_$p" \
        "$HERE/shaders/$p.hlsl"
done
{ echo '#pragma once'; for p in $PASSES; do echo "#include \"$p.h\""; done; } > "$WORK/usr_shaders.h"
{ echo '#pragma once'; for p in $UPASSES; do echo "#include \"$p.h\""; done; } > "$WORK/usr_universal_shaders.h"

x86_64-w64-mingw32-g++ -std=c++17 -O2 -Wall -Wextra -Werror \
    -DWIDL_EXPLICIT_AGGREGATE_RETURNS -DUNICODE -D_UNICODE \
    -I "$HERE/include" -I "$HERE/src" -I "$WORK" \
    "$HERE/src/usr_dx12.cpp" "$HERE/src/usr_universal_dx12.cpp" \
    "$HERE/tests/wine/usr_universal_run.cpp" \
    -o "$WORK/usr_universal_run.exe" -static -ld3d12 -ldxgi -ldxguid

cp "$VKD3D_PROTON/libs/d3d12/d3d12.dll" "$VKD3D_PROTON/libs/d3d12core/d3d12core.dll" "$WORK/"
export WINEPREFIX="${WINEPREFIX:-$WORK/prefix}" WINEDEBUG=-all
export WINEDLLOVERRIDES="d3d12,d3d12core=n,b"
WINE="$(command -v wine64 || echo /usr/lib/wine/wine64)"
cp "$IN" "$WORK/entree.bin"
[ -n "$WEIGHTS" ] && cp "$WEIGHTS" "$WORK/poids.bin"
(cd "$WORK" && xvfb-run -a "$WINE" usr_universal_run.exe entree.bin sortie.bin ${WEIGHTS:+poids.bin})
cp "$WORK/sortie.bin" "$OUT"
"$(dirname "$WINE")/wineserver" -w 2>/dev/null || wineserver -w 2>/dev/null || true
echo "Sortie : $OUT"
