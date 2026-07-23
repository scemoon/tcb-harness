#!/bin/bash
# Registers ai-dlc-skill for OpenCode via symlink + config check

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
OPENCODE_DIR="$PROJECT_ROOT/.opencode"
SYMLINK_TARGET="$OPENCODE_DIR/skills/ai-dlc-skill"

mkdir -p "$OPENCODE_DIR/skills"

if [ ! -L "$SYMLINK_TARGET" ]; then
  ln -s ../../ai-dlc-skill "$SYMLINK_TARGET"
  echo "Created symlink: $SYMLINK_TARGET -> ../../ai-dlc-skill"
else
  echo "Symlink already exists: $SYMLINK_TARGET"
fi

# Verify skills.paths in config.json
CONFIG="$OPENCODE_DIR/config.json"
if [ -f "$CONFIG" ]; then
  if grep -q '"skills"' "$CONFIG" 2>/dev/null; then
    echo "skills.paths already configured in $CONFIG"
  else
    echo "WARNING: config.json missing skills.paths. Add:"
    echo '  "skills": { "paths": [".opencode/skills"] }'
  fi
fi

echo "✅ ai-dlc-skill registered for OpenCode"
