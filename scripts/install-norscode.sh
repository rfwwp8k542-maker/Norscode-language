#!/usr/bin/env sh
set -eu

REPO="rfwwp8k542-maker/Norscode-language"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
VERSION="${NORSCODE_VERSION:-latest}"

case "$(uname -s)" in
    Linux*) ASSET="norscode-linux" ;;
    Darwin*) ASSET="norscode-macos" ;;
    MINGW* | MSYS* | CYGWIN*) ASSET="norscode-windows.exe" ;;
    *)
        echo "Ustøttet operativsystem for automatisk installasjon." >&2
        exit 1
        ;;
esac

if [ "$VERSION" = "latest" ]; then
    DOWNLOAD_URL="https://github.com/$REPO/releases/latest/download/$ASSET"
else
    DOWNLOAD_URL="https://github.com/$REPO/releases/download/$VERSION/$ASSET"
fi

mkdir -p "$INSTALL_DIR"

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

TMP_FILE="$TMP_DIR/$ASSET"

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$DOWNLOAD_URL" -o "$TMP_FILE"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_FILE" "$DOWNLOAD_URL"
else
    echo "Mangler både curl og wget. Installer én av dem og prøv igjen." >&2
    exit 1
fi

chmod +x "$TMP_FILE"
cp "$TMP_FILE" "$INSTALL_DIR/$ASSET"

echo "Norscode ble installert i: $INSTALL_DIR/$ASSET"
echo "Legg $INSTALL_DIR i PATH hvis det ikke allerede er gjort."
