#!/usr/bin/env bash
# cdha/export.sh — Export AI-DLC rules to CDHA (Cloud Dev Harness Agent) format
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# ai-dlc-skill root: cdha/.. → cross-tool/.. → ai-dlc-skill
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# project root: ai-dlc-skill → skills → .opencode → project
PROJECT_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

echo "  Exporting CDHA configs..."

CDH_DIR="$PROJECT_ROOT/.cdh"

# 1. Generate .cdh/config.yaml if not exists
if [ ! -f "$CDH_DIR/config.yaml" ]; then
  mkdir -p "$CDH_DIR"
  sed "s/{{project_name}}/$(basename "$PROJECT_ROOT")/g; s/{{cloud_provider}}/tcb/g; s/{{current_phase}}/understand/g; s/{{compute_mode}}/cloudbase-functions/g" \
    "$SCRIPT_DIR/config.yaml.tpl" > "$CDH_DIR/config.yaml"
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
bash "$SCRIPT_DIR/export-skills.sh"

echo "  CDHA export complete."
