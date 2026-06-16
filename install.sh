#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-scemoon/cloud-dev-harness}"
VERSION="${VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.cdha}"

if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
  log() { echo -e "${GREEN}==>${NC} $*"; }
  warn() { echo -e "${YELLOW}==>${NC} $*"; }
  info() { echo -e "${CYAN}==>${NC} $*"; }
else
  log() { echo "==> $*"; }
  warn() { echo "==> $*"; }
  info() { echo "==> $*"; }
fi

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

detect_downloader() {
  if command -v curl &>/dev/null; then
    download() { curl -sSL "$1" -o "$2"; }
  elif command -v wget &>/dev/null; then
    download() { wget -q "$1" -O "$2"; }
  else
    echo "Error: need curl or wget" >&2; exit 1
  fi
}

install_package() {
  local src="$1"
  if command -v pip3 &>/dev/null; then
    pip3 install "$src" "${PIP_FLAGS:-}"
  elif command -v pip &>/dev/null; then
    pip install "$src" "${PIP_FLAGS:-}"
  else
    warn "pip not found; installing inplace at $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    cp -a "$src/." "$INSTALL_DIR/"
    return
  fi
  INSTALL_DIR=$(python3 -c "import site; print(site.USER_SITE)" 2>/dev/null || echo "$INSTALL_DIR")
}

TMPDIR=$(mktemp -d)

if [ "$VERSION" = "latest" ]; then
  API_URL="https://api.github.com/repos/$REPO/releases/latest"
  tmp=$(mktemp) && download "$API_URL" "$tmp"
  TAG=$(python3 -c "import json; print(json.load(open('$tmp'))['tag_name'])" 2>/dev/null || grep -o '"tag_name": *"[^"]*"' "$tmp" | head -1 | sed 's/.*: *"//;s/"//')
  rm -f "$tmp"
  [ -z "$TAG" ] && { echo "Error: could not determine latest version" >&2; exit 1; }
  VERSION="${TAG#v}"
  log "Latest release: $TAG"
fi

ARCHIVE_URL="https://github.com/$REPO/archive/refs/tags/v${VERSION}.tar.gz"
log "Downloading $REPO v$VERSION ..."
download "$ARCHIVE_URL" "$TMPDIR/release.tar.gz"

log "Extracting ..."
tar xzf "$TMPDIR/release.tar.gz" -C "$TMPDIR"
SRC_DIR="$TMPDIR/cloud-dev-harness-${VERSION}"
[ ! -d "$SRC_DIR" ] && SRC_DIR=$(find "$TMPDIR" -maxdepth 1 -name "cloud-dev-harness-*" -type d | head -1)
[ -z "$SRC_DIR" ] && { echo "Error: could not find source directory" >&2; exit 1; }

log "Installing cloud-dev-harness v$VERSION ..."
install_package "$SRC_DIR"

SHIM="$HOME/.local/bin/cdh"
if [ ! -f "$SHIM" ] && ! command -v cdh &>/dev/null; then
  mkdir -p "$HOME/.local/bin"
  cat > "$SHIM" << 'SHIMEOF'
#!/usr/bin/env bash
exec python3 -m cdh "$@"
SHIMEOF
  chmod +x "$SHIM"
  info "Created shim at $SHIM"
  info "Add to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

log "cloud-dev-harness v$VERSION installed!"
