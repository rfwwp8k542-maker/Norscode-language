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
exec python3 -m http.server --bind "$HOST" "$PORT" -d docs
