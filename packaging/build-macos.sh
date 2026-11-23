#!/usr/bin/env bash
# Construye un binario autónomo de kp9 para macOS (no requiere Python en el Mac destino).
# Resultado: dist/kp9-<versión>-macos-<arch>.tar.gz con la carpeta kp9/ e install.sh.
# La arquitectura es la de la máquina donde se construye (arm64 o x86_64).
set -euo pipefail

cd "$(dirname "$0")/.."
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
arch=$(uname -m)
name="kp9-${version}-macos-${arch}"
work="build/pyinstaller"
# caché de PyInstaller dentro del repo (no en ~/Library)
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/build/pyinstaller-cache}"

uv sync --quiet
rm -rf "$work/kp9" "dist/kp9" "dist/${name}" "dist/${name}.tar.gz"

uv run pyinstaller packaging/kp9_entry.py \
  --name kp9 \
  --onedir \
  --noconfirm \
  --clean \
  --log-level WARN \
  --workpath "$work" \
  --specpath "$work" \
  --distpath dist \
  --collect-data kp9 \
  --collect-all textual \
  --collect-submodules pygments \
  --collect-submodules rich

# prueba rápida: el binario arranca e inicializa un workspace
tmp="build/smoke"; rm -rf "$tmp"
dist/kp9/kp9 --help >/dev/null
dist/kp9/kp9 init "$tmp/ws" >/dev/null
rm -rf "$tmp"

mkdir -p "dist/${name}"
mv dist/kp9 "dist/${name}/kp9"
cp packaging/install.sh "dist/${name}/install.sh"
tar -C dist -czf "dist/${name}.tar.gz" "${name}"
rm -rf "dist/${name}"
echo "listo: dist/${name}.tar.gz"
