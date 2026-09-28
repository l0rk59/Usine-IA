#!/usr/bin/env bash
# Construit l'arbre source de « Xenia + USR » : clone xenia-canary-uwp au
# commit sur lequel les correctifs ont ete ecrits, copie la bibliotheque USR
# dans third_party/usr et applique les 4 correctifs (git am).
#
#   xenia/appliquer.sh [dossier]          (defaut : ./xenia-usr)
#
# Variables : XENIA_SOURCE (depot a cloner, defaut GitHub), XENIA_COMMIT,
# SANS_SOUS_MODULES=1 (ne pas recuperer les sous-modules de Xenia : pratique
# pour verifier les correctifs, insuffisant pour compiler).
# Sous Windows : xenia\appliquer.ps1 fait la meme chose.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
USR="$(cd "$ICI/.." && pwd)"
CIBLE="${1:-$PWD/xenia-usr}"
SOURCE="${XENIA_SOURCE:-https://github.com/amitamit99/xenia-canary-uwp.git}"
COMMIT="${XENIA_COMMIT:-3e236f08245f8f98b6813a6c249b6896dbfbd400}"

if [ -e "$CIBLE" ]; then
    echo "Le dossier $CIBLE existe deja : choisir un autre dossier." >&2
    exit 1
fi

echo "== Xenia : $SOURCE @ ${COMMIT:0:7}"
git clone --quiet "$SOURCE" "$CIBLE"
git -C "$CIBLE" -c advice.detachedHead=false checkout --quiet -b usr "$COMMIT"
if [ "${SANS_SOUS_MODULES:-0}" != "1" ]; then
    echo "== sous-modules de Xenia (quelques minutes)"
    # comme « xb setup » : profondeur 1, sans xbyak_aarch64 (processeurs ARM)
    mapfile -t SOUS_MODULES < <(grep -oP \
        '(?<=path = )(?!third_party/xbyak_aarch64).+' "$CIBLE/.gitmodules")
    git -C "$CIBLE" -c fetch.recurseSubmodules=on-demand submodule update \
        --init --depth=1 -j "$(nproc)" "${SOUS_MODULES[@]}"
fi

echo "== bibliotheque USR -> third_party/usr"
mkdir -p "$CIBLE/third_party/usr"
cp -r "$USR/include" "$USR/src" "$USR/shaders" "$CIBLE/third_party/usr/"
cp "$ICI/third_party_usr/CMakeLists.txt" "$CIBLE/third_party/usr/"
cp "$USR/../LICENSE" "$CIBLE/third_party/usr/LICENSE"   # MIT, suit le code

echo "== correctifs"
git -C "$CIBLE" -c user.name="Usine-IA" -c user.email="usr@usine-ia.local" \
    -c core.autocrlf=false am --keep-cr --quiet "$ICI"/patches/*.patch
git -C "$CIBLE" log --oneline -4

cat <<FIN

Arbre pret : $CIBLE (branche « usr »).
Compilation (Windows, Visual Studio 2022 + charge « Developpement UWP ») :
  cd $CIBLE
  cmake --preset vs
  puis ouvrir build\\xenia.sln et compiler xenia-canary-uwp (Release | x64).
Pas a pas, paquet et installation sur Xbox : super-resolution/docs/XENIA.md.
FIN
