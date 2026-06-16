#!/usr/bin/env bash
# cdha/export.sh — Export AI-DLC rules to CDHA (Cloud Dev Harness Agent) format
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# ai-dlc-skill root: cdha/.. → cross-tool/.. → ai-dlc-skill
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# project root: ai-dlc-skill → skills → .opencode → project
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"

echo "  Exporting CDHA agent configs..."

# 1. Generate .cdh/config.yaml if not exists
CDH_DIR="$PROJECT_ROOT/.cdh"
if [ ! -f "$CDH_DIR/config.yaml" ]; then
  mkdir -p "$CDH_DIR"
  sed "s/{{project_name}}/$(basename "$PROJECT_ROOT")/g; s/{{cloud_provider}}/tcb/g; s/{{current_phase}}/init/g; s/{{compute_mode}}/cloudbase-functions/g" \
    "$SCRIPT_DIR/config.yaml.tpl" > "$CDH_DIR/config.yaml"
  echo "  ✓ $CDH_DIR/config.yaml created"
else
  echo "  - $CDH_DIR/config.yaml exists, skipping"
fi

# 2. Copy Master Agent config
AGENT_CONFIG_DIR="$CDH_DIR/agents"
mkdir -p "$AGENT_CONFIG_DIR"
cp "$SCRIPT_DIR/agents/ai-dlc-master.yaml" "$AGENT_CONFIG_DIR/"
echo "  ✓ $AGENT_CONFIG_DIR/ai-dlc-master.yaml"

# 3. Generate component skills
bash "$SCRIPT_DIR/export-skills.sh"

echo "  CDHA export complete."
