#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BINARY="$ROOT_DIR/dist/norscode"

if [ ! -x "$BINARY" ]; then
    echo "Norscode binary not found at: $BINARY" >&2
    echo "Build it with: sh scripts/build-standalone.sh" >&2
    exit 1
fi

exec "$BINARY" "$@"
