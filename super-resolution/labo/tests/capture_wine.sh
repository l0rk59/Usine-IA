#!/usr/bin/env bash
# Verification de bout en bout du Labo SANS Windows ni carte graphique :
# compile usr_labo.exe avec MinGW, l'execute sous Wine avec vkd3d-proton
# (Direct3D 12 -> Vulkan) sur le GPU logiciel de Mesa (llvmpipe), et
# ecrit des captures que tests/test_labo_bout_en_bout.py compare a la
# reference Python.
#
#   VKD3D_PROTON=/chemin/build-vkd3d-proton DXC=/chemin/dxc \
#       labo/tests/capture_wine.sh [dossier_de_sortie] [images]
#
# Prerequis (Ubuntu 24.04) : g++-mingw-w64-x86-64 wine64 xvfb
# mesa-vulkan-drivers, un dxc Linux, et vkd3d-proton compile pour win64
# (meson --cross-file build-win64.txt, voir .github/workflows).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$(realpath -m "${1:-$HERE/captures-wine}")"
FRAMES="${2:-24}"
: "${VKD3D_PROTON:?definir VKD3D_PROTON (dossier de construction de vkd3d-proton)}"
: "${DXC:=dxc}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== shaders (dxc)"
PASSES="usr_prepare usr_accumulate usr_sharpen"
UPASSES="usr_u_luma usr_u_down usr_u_grad usr_u_flow usr_u_median usr_u_finalize usr_u_residual usr_u_accumulate usr_u_output"
LPASSES="labo_scene labo_truth labo_upscale labo_compose labo_encode"
for p in $PASSES $UPASSES; do
    "$DXC" -T cs_6_0 -E main -O3 -WX -Fh "$WORK/$p.h" -Vn "g_$p" \
        "$HERE/shaders/$p.hlsl"
done
for p in $LPASSES; do
    "$DXC" -T cs_6_0 -E main -O3 -WX -Fh "$WORK/$p.h" -Vn "g_$p" \
        "$HERE/labo/shaders/$p.hlsl"
done
{ echo '#pragma once'; for p in $PASSES; do echo "#include \"$p.h\""; done; } > "$WORK/usr_shaders.h"
{ echo '#pragma once'; for p in $UPASSES; do echo "#include \"$p.h\""; done; } > "$WORK/usr_universal_shaders.h"
{ echo '#pragma once'; for p in $LPASSES; do echo "#include \"$p.h\""; done; } > "$WORK/labo_shaders.h"

echo "== usr_labo.exe (MinGW)"
# WIDL_EXPLICIT_AGGREGATE_RETURNS : ABI correcte des methodes COM qui
# renvoient une structure (GetDesc, GetCPUDescriptorHandleForHeapStart...).
x86_64-w64-mingw32-g++ -std=c++17 -O2 -Wall -Wextra -Werror \
    -DWIDL_EXPLICIT_AGGREGATE_RETURNS -DUNICODE -D_UNICODE \
    -I "$HERE/include" -I "$HERE/src" -I "$HERE/labo/src" -I "$WORK" \
    "$HERE/src/usr_dx12.cpp" "$HERE/src/usr_universal_dx12.cpp" \
    "$HERE"/labo/src/labo_core.cpp \
    "$HERE"/labo/src/labo_text.cpp "$HERE"/labo/src/labo_renderer.cpp \
    "$HERE"/labo/src/labo_frame.cpp "$HERE"/labo/src/labo_png.cpp \
    "$HERE"/labo/src/app_win32.cpp \
    -o "$WORK/usr_labo.exe" -static -ld3d12 -ldxgi -lxinput -ldxguid

cp "$VKD3D_PROTON/libs/d3d12/d3d12.dll" "$VKD3D_PROTON/libs/d3d12core/d3d12core.dll" "$WORK/"
export WINEPREFIX="${WINEPREFIX:-$WORK/prefix}" WINEDEBUG=-all
export WINEDLLOVERRIDES="d3d12,d3d12core=n,b"
WINE="$(command -v wine64 || echo /usr/lib/wine/wine64)"

echo "== execution sous Wine + vkd3d-proton ($FRAMES images)"
rm -rf "$OUT"
mkdir -p "$OUT"
# A gauche USR (vecteurs du jeu), a droite USR Universel (vue 2 : l'image
# seule, niveau 2) : les deux chemins sont captures et verifies.
(cd "$WORK" && xvfb-run -a "$WINE" usr_labo.exe --capture "$FRAMES" \
    --dossier sortie --largeur 640 --hauteur 360 --gauche 0 --droite 2)
cp "$WORK"/sortie/* "$OUT/"
"$(dirname "$WINE")/wineserver" -w 2>/dev/null || wineserver -w 2>/dev/null || true
ls "$OUT" | head
echo "Captures dans $OUT -- USR_LABO_CAPTURES=$OUT python -m unittest tests.test_labo_bout_en_bout"
