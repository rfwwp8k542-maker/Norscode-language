#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$ROOT_DIR/build/pyinstaller/config}"

if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller mangler i .venv. Kjør: python3 -m pip install --target .venv/lib/python3.14/site-packages pyinstaller" >&2
    exit 1
fi

cd "$ROOT_DIR"
rm -rf build dist/norscode dist/norcode

"$PYTHON_BIN" -m PyInstaller \
    --onefile \
    --name norscode \
    --clean \
    --distpath dist \
    --workpath build/pyinstaller \
    --specpath build/pyinstaller \
    main.py

if [ -x dist/norscode ]; then
    echo "Bygget binær: dist/norscode"
else
    echo "Bygg ferdig, men fant ikke dist/norscode" >&2
    exit 1
fi
