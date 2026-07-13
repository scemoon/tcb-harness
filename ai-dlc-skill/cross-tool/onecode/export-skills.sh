#!/usr/bin/env bash
# export-skills.sh — Generate per-component .skill/SKILL.md from components/*.md
set -euo pipefail

PROJECT_ROOT="${1:-$PWD}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="${2:-${AI_DLC_SKILL_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}}"

if [ ! -d "$SKILL_DIR" ]; then
  echo "  ✗ ai-dlc-skill not found at $SKILL_DIR" >&2
  exit 1
fi

echo "Generating component skills in $PROJECT_ROOT/apps/*/.skill/"

for component in native desktop web backend wxa mya tta; do
  component_dir="$PROJECT_ROOT/apps/$component"
  skill_dir="$component_dir/.skill"
  src="$SKILL_DIR/components/$component.md"

  if [ ! -d "$component_dir" ]; then
    echo "  ⚠ $component_dir not found, skipping"
    continue
  fi

  if [ ! -f "$src" ]; then
    echo "  ⚠ $src not found, skipping"
    continue
  fi

  mkdir -p "$skill_dir"
  cp "$src" "$skill_dir/SKILL.md"
  echo "  ✓ $component → $skill_dir/SKILL.md"
done

echo "Done."
