#!/bin/bash
# Registers ai-dlc-skill for OpenCode via symlink + config check

set -euo pipefail

CANONICAL_SKILL_DIR="${HOME}/.cdh/skills/ai-dlc-skill"
DEV_SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="$(cd "$DEV_SKILL_DIR/.." && pwd)"

if [ -d "$CANONICAL_SKILL_DIR" ]; then
    SKILL_DIR="$CANONICAL_SKILL_DIR"
else
    SKILL_DIR="$DEV_SKILL_DIR"
fi

OPENCODE_DIR="$PROJECT_ROOT/.opencode"
SYMLINK_TARGET="$OPENCODE_DIR/skills/ai-dlc-skill"

mkdir -p "$OPENCODE_DIR/skills"

if [ ! -L "$SYMLINK_TARGET" ]; then
  ln -s "$SKILL_DIR" "$SYMLINK_TARGET"
  echo "Created symlink: $SYMLINK_TARGET -> $SKILL_DIR"
else
  echo "Symlink already exists: $SYMLINK_TARGET"
fi

CONFIG="$OPENCODE_DIR/config.json"
if [ -f "$CONFIG" ]; then
  if grep -q '"skills"' "$CONFIG" 2>/dev/null; then
    echo "skills.paths already configured in $CONFIG"
  else
    echo "WARNING: config.json missing skills.paths. Add:"
    echo '  "skills": { "paths": [".opencode/skills"] }'
  fi
fi

echo "ai-dlc-skill registered for OpenCode"