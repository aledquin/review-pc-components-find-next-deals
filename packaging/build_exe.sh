#!/usr/bin/env bash
# Build a standalone `pca` executable on Linux or macOS.
#
#   $ ./packaging/build_exe.sh
#
# Run from the repo root. Produces dist/pca (single-file).

set -euo pipefail

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Creating .venv ..."
    python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/python -m pip install -e ".[packaging,web,gui]" >/dev/null

echo "Building pca (CLI) ..."
./.venv/bin/python -m PyInstaller packaging/pca.spec --clean --noconfirm

echo "Building pca-gui (native GUI) ..."
./.venv/bin/python -m PyInstaller packaging/pca-gui.spec --clean --noconfirm

echo ""
echo "Built:"
printf "  CLI: %s (%.1f MB)\n" "$(realpath dist/pca)" "$(du -m dist/pca | cut -f1)"
printf "  GUI: %s (%.1f MB)\n" "$(realpath dist/pca-gui)" "$(du -m dist/pca-gui | cut -f1)"
echo ""
echo "Smoke: pca --help"
./dist/pca --help | head -n 3
