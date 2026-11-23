#!/usr/bin/env bash
# Instala kp9 en ~/.local (sin sudo). Uso: ./install.sh [PREFIJO]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
prefix="${1:-$HOME/.local}"
app_dir="$prefix/share/kp9"
bin_dir="$prefix/bin"

rm -rf "$app_dir"
mkdir -p "$app_dir" "$bin_dir"
cp -R "$here/kp9/." "$app_dir/"
# los archivos descargados traen la marca de cuarentena de Gatekeeper
xattr -dr com.apple.quarantine "$app_dir" 2>/dev/null || true
ln -sf "$app_dir/kp9" "$bin_dir/kp9"

echo "kp9 instalado en $app_dir"
echo "comando: $bin_dir/kp9"
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "agrega a tu PATH (p. ej. en ~/.zshrc): export PATH=\"$bin_dir:\$PATH\"" ;;
esac
