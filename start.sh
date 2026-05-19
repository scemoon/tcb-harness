#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required" >&2
    exit 1
fi

echo "Starting Cloud Dev Harness (cdh)..."
if [ $# -eq 0 ]; then
    exec python3 -m cdh tui
else
    exec python3 -m cdh "$@"
fi
