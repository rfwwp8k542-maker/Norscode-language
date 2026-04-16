#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-}"
if [[ -z "$HOST" ]]; then
  if [[ -n "${PORT:-}" ]]; then
    HOST="0.0.0.0"
  else
    HOST="127.0.0.1"
  fi
fi
PORT="${PORT:-4000}"
cd docs
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "No Python interpreter found on PATH" >&2
    exit 127
  fi
fi
exec "$PYTHON_BIN" -m http.server --bind "$HOST" "$PORT"
