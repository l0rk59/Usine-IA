#!/usr/bin/env bash
# Verifications de « Xenia + USR » possibles sans Windows (integration
# continue) :
#   1. les 7 correctifs s'appliquent sur un clone neuf de xenia-canary-uwp ;
#   2. les tests du menu de reglages passent (C++20 strict) ;
#   3. la cible CMake third_party/usr se construit : shaders par dxc,
#      bibliotheque par g++ avec les en-tetes DirectX ouverts de Microsoft.
#
#   DXC=/chemin/dxc DIRECTX_HEADERS=/chemin/DirectX-Headers \
#       xenia/tests/verifier_linux.sh [dossier]
#
# XENIA_SOURCE (depot a cloner) est transmis a appliquer.sh.
set -euo pipefail

ICI="$(cd "$(dirname "$0")/.." && pwd)"
CIBLE="$(realpath -m "${1:-$PWD/xenia-usr-verif}")"
: "${DXC:?definir DXC (dxc Linux)}"
: "${DIRECTX_HEADERS:?definir DIRECTX_HEADERS (depot microsoft/DirectX-Headers)}"

rm -rf "$CIBLE"
SANS_SOUS_MODULES=1 "$ICI/appliquer.sh" "$CIBLE"

echo "== tests du menu USR"
g++ -std=c++20 -Wall -Wextra -Werror -I "$CIBLE/src" \
    "$ICI/tests/usr_menu_test.cc" -o "$CIBLE/usr_menu_test"
"$CIBLE/usr_menu_test"

echo "== cible CMake third_party/usr"
W="$CIBLE/verif-cmake"
mkdir -p "$W"
cat > "$W/CMakeLists.txt" <<FIN
cmake_minimum_required(VERSION 3.20)
project(usr_verif CXX)
add_subdirectory("$CIBLE/third_party/usr" usr)
FIN
DXH="$DIRECTX_HEADERS/include"
cmake -S "$W" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DUSR_DXC="$DXC" \
    -DCMAKE_CXX_FLAGS="-Wall -Wextra -Werror -include wsl/winadapter.h \
-include directx/d3d12.h -include dxguids/dxguids.h -I$DXH -I$DXH/directx \
-I$DXH/wsl/stubs"
cmake --build "$W/build" -j "$(nproc)"
test -f "$W/build/usr/libusr.a"
echo "Xenia + USR : correctifs, menu et bibliotheque verifies ($CIBLE)"
