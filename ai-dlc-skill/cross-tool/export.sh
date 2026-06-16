#!/usr/bin/env bash
# export.sh — One-click export AI-DLC rules to all supported tool formats
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "AI-DLC Cross-Tool Export"
echo "========================"
echo ""

for tool in cdha cursor cline copilot; do
  export_script="$SCRIPT_DIR/$tool/export.sh"
  if [ -f "$export_script" ]; then
    echo "[$tool] Running $export_script..."
    bash "$export_script"
  else
    echo "[$tool] No export script found at $export_script"
  fi
  echo ""
done

echo "Done. All supported tool configs generated."
