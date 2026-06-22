#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-scemoon/cloud-dev-harness}"
VERSION="${VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.onecode}"

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

check_python() {
  for cmd in python3 python; do
    command -v "$cmd" &>/dev/null || continue
    local ver; ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0")
    local major="${ver%.*}" minor="${ver#*.}"
    if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 14 ]; }; then
      PYTHON="$cmd"; return 0
    fi
  done
  return 1
}

install_package() {
  local src="$1"
  if command -v uv &>/dev/null; then
    uv pip install "$src" --system "${PIP_FLAGS:-}"
  elif command -v pip3 &>/dev/null; then
    pip3 install "$src" --upgrade "${PIP_FLAGS:-}" 2>/dev/null || pip3 install "$src" "${PIP_FLAGS:-}"
  elif command -v pip &>/dev/null; then
    pip install "$src" --upgrade "${PIP_FLAGS:-}" 2>/dev/null || pip install "$src" "${PIP_FLAGS:-}"
  else
    warn "pip not found; installing inplace at $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR" && cp -a "$src/." "$INSTALL_DIR/"
  fi
}

TMPDIR=$(mktemp -d)
detect_downloader

if ! check_python; then
  if command -v uv &>/dev/null; then
    warn "Python 3.14+ not found; will create venv with uv"
    USE_UV_VENV=1
  else
    echo "Error: Python 3.14+ is required. Install Python 3.14+ or uv (https://docs.astral.sh/uv/)" >&2
    exit 1
  fi
fi

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

if [ "${USE_UV_VENV:-0}" = "1" ]; then
  VENV_DIR="$HOME/.onecode/python"
  log "Creating Python venv with uv at $VENV_DIR ..."
  uv venv "$VENV_DIR" && uv pip install "$SRC_DIR" --python "$VENV_DIR/bin/python" "${PIP_FLAGS:-}"
else
  log "Installing cloud-dev-harness v$VERSION ..."
  install_package "$SRC_DIR"
fi

SHIM_DIR="${HOME}/.local/bin"
SHIM="${SHIM_DIR}/cdh"
if ! command -v cdh &>/dev/null; then
  mkdir -p "$SHIM_DIR"
  if [ "${USE_UV_VENV:-0}" = "1" ]; then
    cat > "$SHIM" << SHIMEOF
#!/usr/bin/env bash
exec ${VENV_DIR}/bin/python -m cdh "\$@"
SHIMEOF
  else
    cat > "$SHIM" << 'SHIMEOF'
#!/usr/bin/env bash
exec python3 -m cdh "$@"
SHIMEOF
  fi
  chmod +x "$SHIM"
  info "Created shim at $SHIM"
  info "Add to PATH: export PATH=\"$SHIM_DIR:\$PATH\""
fi

log "cloud-dev-harness v$VERSION installed!"
