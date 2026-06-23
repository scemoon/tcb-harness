#!/usr/bin/env bash
set -euo pipefail

# cloud-dev-harness installer — supports npm and PyPI
# Usage: bash <(curl -sSL https://raw.githubusercontent.com/scemoon/cloud-dev-harness/main/install.sh)
#   --method npm|pip    force a specific installer
#   --version <ver>     install a specific version (PyPI only; npm always fetches latest)
#   --help              show this help

REPO="${REPO:-scemoon/cloud-dev-harness}"
VERSION="${VERSION:-latest}"
METHOD="${METHOD:-auto}"

# ── colours ──────────────────────────────────────────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
  log()  { echo -e "${GREEN}==>${NC} $*"; }
  warn() { echo -e "${YELLOW}==>${NC} $*"; }
  info() { echo -e "${CYAN}==>${NC} $*"; }
else
  log()  { echo "==> $*"; }
  warn() { echo "==> $*"; }
  info() { echo "==> $*"; }
fi

usage() {
  sed -n '3,7p' "$0" | sed 's/^# //; s/^#$//'
  exit 0
}

# ── parse args ───────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --method)  METHOD="$2";  shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --help)    usage ;;
    *)         warn "unknown arg: $1"; shift ;;
  esac
done

# ── detect tools ─────────────────────────────────────────────────────
has_npm()  { command -v npm  &>/dev/null; }
has_pip()  { command -v pip3 &>/dev/null || command -v pip &>/dev/null; }
has_uv()   { command -v uv   &>/dev/null; }

install_npm() {
  log "Installing via npm …"
  local tag="latest"
  npm install -g "@${REPO}"@"${tag}"
  log "Done! Run 'cdh' to start."
}

install_pip() {
  log "Installing via pip …"
  local ver="${VERSION}"
  local spec="cloud-dev-harness"

  if [ "$ver" != "latest" ]; then
    spec="cloud-dev-harness==${ver}"
  fi

  if has_uv; then
    log "Using uv to install …"
    uv pip install --system "$spec" ${PIP_FLAGS:-}
  else
    local pip_cmd
    pip_cmd=$(command -v pip3 || command -v pip)
    log "Using $pip_cmd …"
    "$pip_cmd" install "$spec" --upgrade ${PIP_FLAGS:-} 2>/dev/null \
      || "$pip_cmd" install "$spec" ${PIP_FLAGS:-}
  fi

  # ensure CLI shim
  local shim_dir="${HOME}/.local/bin"
  mkdir -p "$shim_dir"
  local shim="$shim_dir/cdh"
  if [ ! -f "$shim" ]; then
    cat > "$shim" << 'SHIMEOF'
#!/usr/bin/env bash
exec python3 -m cdh "$@"
SHIMEOF
    chmod +x "$shim"
    info "Created shim at $shim"
    info "Add to PATH: export PATH=\"$shim_dir:\$PATH\""
  fi

  log "Done! Run 'cdh' to start."
}

# ── main ─────────────────────────────────────────────────────────────
case "$METHOD" in
  npm)  install_npm ;;
  pip)  install_pip ;;
  auto)
    if has_npm; then
      install_npm
    elif has_pip; then
      install_pip
    else
      echo "Error: need npm or pip. Install Node.js (npm) or Python (pip) first." >&2
      exit 1
    fi
    ;;
  *)
    echo "Error: unknown method '$METHOD'. Use npm or pip." >&2
    exit 1
    ;;
esac
