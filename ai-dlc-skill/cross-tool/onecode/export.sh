#!/usr/bin/env bash
# onecode/export.sh — Export AI-DLC rules to onecode format
set -euo pipefail

# Project root: first arg or current working directory
PROJECT_ROOT="${1:-$PWD}"
# Skill dir: CDH platform skill pool or AI_DLC_SKILL_DIR env var
SKILL_DIR="${AI_DLC_SKILL_DIR:-$HOME/.cdh/skills/ai-dlc-skill}"

if [ ! -d "$SKILL_DIR" ]; then
  echo "  ✗ ai-dlc-skill not found at $SKILL_DIR" >&2
  echo "  Run: cdh skill install ai-dlc-skill" >&2
  exit 1
fi

echo "  Exporting onecode configs for project: $(basename "$PROJECT_ROOT")"

CDH_DIR="$PROJECT_ROOT/.cdh"
CROSS_TOOL_DIR="$SKILL_DIR/cross-tool/onecode"

# 1. Generate .cdh/config.yaml if not exists
if [ ! -f "$CDH_DIR/config.yaml" ]; then
  mkdir -p "$CDH_DIR"
  sed "s/{{project_name}}/$(basename "$PROJECT_ROOT")/g; s/{{cloud_provider}}/tcb/g; s/{{current_phase}}/understand/g; s/{{compute_mode}}/cloudbase-functions/g" \
    "$CROSS_TOOL_DIR/config.yaml.tpl" > "$CDH_DIR/config.yaml"
  echo "  ✓ $CDH_DIR/config.yaml created"
else
  echo "  - $CDH_DIR/config.yaml exists, skipping"
fi

# 2. Generate .cdh/state.json if not exists
if [ ! -f "$CDH_DIR/state.json" ]; then
  mkdir -p "$CDH_DIR"
  cat > "$CDH_DIR/state.json" <<-EOF
{
  "current_phase": "understand",
  "completed_phases": [],
  "gate_results": {}
}
EOF
  echo "  ✓ $CDH_DIR/state.json created"
else
  echo "  - $CDH_DIR/state.json exists, skipping"
fi

# 3. Generate .cdh/SKILL.md from the master skill (always refresh)
mkdir -p "$CDH_DIR"
cp "$SKILL_DIR/SKILL.md" "$CDH_DIR/SKILL.md"
echo "  ✓ $CDH_DIR/SKILL.md updated"

# 4. Generate component skills into apps/*/.skill/
bash "$CROSS_TOOL_DIR/export-skills.sh" "$PROJECT_ROOT" "$SKILL_DIR"

echo "  onecode export complete."
