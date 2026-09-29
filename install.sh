#!/usr/bin/env bash
# Installation de l'Usine-IA sur Termux (et sur un Linux classique).
# Usage :  bash install.sh
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERT=$'\033[32m'; JAUNE=$'\033[33m'; BLEU=$'\033[1;36m'; GRIS=$'\033[2m'; FIN=$'\033[0m'

info()   { printf '%s==>%s %s\n' "$BLEU" "$FIN" "$1"; }
succes() { printf '  %s[ok]%s %s\n' "$VERT" "$FIN" "$1"; }
avertir(){ printf '  %s[!]%s %s\n' "$JAUNE" "$FIN" "$1"; }

cat <<'BANNIERE'

  _   _     _              ___    _
 | | | |___(_)_ _  ___ ___|_ _|  /_\
 | |_| (_-< | ' \/ -_)___ | |  / _ \
  \___//__/_|_||_\___|    |___/_/ \_\

  Fabrique de produits digitaux — installation

BANNIERE

# --------------------------------------------------------------------------
# 1. Detection de l'environnement
# --------------------------------------------------------------------------
info "Detection de l'environnement"
if [ -n "${PREFIX:-}" ] && [ -d "/data/data/com.termux" ]; then
  TERMUX=1
  DOSSIER_BIN="$PREFIX/bin"
  succes "Termux detecte (Android)"
else
  TERMUX=0
  DOSSIER_BIN="$HOME/.local/bin"
  succes "Linux / macOS"
fi

# --------------------------------------------------------------------------
# 2. Dependances systeme
# --------------------------------------------------------------------------
if [ "$TERMUX" = "1" ]; then
  info "Installation des paquets Termux"
  yes | pkg update >/dev/null 2>&1 || avertir "mise a jour des depots ignoree"
  for paquet in python openssl ca-certificates; do
    if pkg list-installed 2>/dev/null | grep -q "^$paquet/"; then
      succes "$paquet deja installe"
    else
      yes | pkg install -y "$paquet" >/dev/null 2>&1 && succes "$paquet installe" \
        || avertir "echec de l'installation de $paquet"
    fi
  done
  # git (recommande) : c'est lui qui fait marcher « usine maj ». Sans lui, la
  # mise a jour telecharge une archive, ce qui ne fonctionne que sur un depot
  # public — et ce depot-ci peut etre prive.
  if command -v git >/dev/null 2>&1; then
    succes "git present : « usine maj » mettra a jour sans retelecharger"
  else
    yes | pkg install -y git >/dev/null 2>&1 && succes "git installe" \
      || avertir "git absent : « usine maj » ne marchera que sur un depot public"
  fi
  # Node.js (optionnel) : sans lui, le JavaScript genere par la chaine
  # « logiciel » n'est verifie qu'en mode degrade. L'usine produit sans.
  if command -v node >/dev/null 2>&1; then
    succes "Node.js present : verification complete du JavaScript genere"
  else
    avertir "Node.js absent (optionnel) : pkg install nodejs-lts"
  fi
  # termux-api (optionnel) : notifications de fin, ouverture des fichiers.
  if ! command -v termux-notification >/dev/null 2>&1; then
    avertir "termux-api absent (optionnel) : pkg install termux-api"
  fi
  # Acces au stockage partage : permet de deposer les produits dans /sdcard
  if [ ! -d "$HOME/storage" ]; then
    avertir "Pour enregistrer vos produits dans la memoire du telephone, lancez ensuite :"
    printf '      %stermux-setup-storage%s\n' "$GRIS" "$FIN"
  fi
fi

# --------------------------------------------------------------------------
# 3. Python
# --------------------------------------------------------------------------
info "Verification de Python"
if ! command -v python3 >/dev/null 2>&1; then
  printf '  Python 3 est introuvable. Sur Termux : pkg install python\n'
  exit 1
fi
VERSION_PY="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
succes "Python $VERSION_PY"
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    sys.exit("  Python 3.9 minimum est requis.")
PY
# L'usine n'utilise que la bibliotheque standard : rien a installer via pip.
python3 -c "import sqlite3, ssl, zlib, zipfile, urllib.request" \
  && succes "Modules standard requis presents (sqlite3, ssl, zlib, zipfile)"

# --------------------------------------------------------------------------
# 4. Configuration
# --------------------------------------------------------------------------
info "Configuration"
if [ ! -f "$RACINE/.env" ]; then
  cp "$RACINE/.env.exemple" "$RACINE/.env"
  succes "Fichier .env cree a partir du modele"
  avertir "Ajoutez-y au moins une cle API : nano $RACINE/.env"
else
  succes "Fichier .env deja present"
fi
mkdir -p "$RACINE/atelier/produits" "$RACINE/atelier/logs"
succes "Dossier de travail : $RACINE/atelier"

# --------------------------------------------------------------------------
# 5. Commande « usine »
# --------------------------------------------------------------------------
info "Installation de la commande « usine »"
mkdir -p "$DOSSIER_BIN"
# PYTHONPATH fige la racine : la commande marche depuis n'importe quel dossier.
cat > "$DOSSIER_BIN/usine" <<LANCEUR
#!/usr/bin/env bash
export PYTHONPATH="$RACINE\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m usine.cli "\$@"
LANCEUR
chmod +x "$DOSSIER_BIN/usine"
succes "Commande installee : $DOSSIER_BIN/usine"

case ":$PATH:" in
  *":$DOSSIER_BIN:"*) ;;
  *) avertir "Ajoutez ceci a votre ~/.bashrc :"
     printf '      %sexport PATH="%s:$PATH"%s\n' "$GRIS" "$DOSSIER_BIN" "$FIN" ;;
esac

# --------------------------------------------------------------------------
# 6. Verification
# --------------------------------------------------------------------------
info "Verification de l'installation"
if PYTHONPATH="$RACINE" python3 -m usine.cli --version >/dev/null 2>&1; then
  succes "L'usine repond"
else
  avertir "L'usine ne demarre pas — lancez : PYTHONPATH=$RACINE python3 -m usine.cli docteur"
  exit 1
fi

# --------------------------------------------------------------------------
# 7. Ce qui manque encore sur CET appareil
# --------------------------------------------------------------------------
# La liste des outils utiles vit dans usine/core/specs.py, pas ici : deux
# listes divergeraient, et c'est celle du script d'installation qui vieillit
# le plus vite. On lui demande.
info "Ce qui manque sur cet appareil"
PYTHONPATH="$RACINE" python3 -m usine.cli specs --vers "$RACINE/SPECS-APPAREIL.md" \
  >/dev/null 2>&1 || true
if [ -f "$RACINE/SPECS-APPAREIL.md" ]; then
  succes "Fiche ecrite : SPECS-APPAREIL.md"
  printf '      %sLa pousser sur le depot aide a corriger install.sh pour tout le monde.%s\n' \
    "$GRIS" "$FIN"
fi

cat <<FIN_MESSAGE

  ${VERT}Installation terminee.${FIN}

  Prochaines etapes :

    ${BLEU}usine cles${FIN}        obtenir une cle API gratuite (2 minutes)
    ${BLEU}usine docteur${FIN}     verifier que tout repond
    ${BLEU}usine idees "votre niche"${FIN}
    ${BLEU}usine ebook "votre sujet" --marketing --zip${FIN}
    ${BLEU}usine web${FIN}         tableau de bord dans le navigateur

FIN_MESSAGE
