#!/bin/bash
# Registers ai-dlc-skill for OneCode via symlink

set -euo pipefail

CANONICAL_SKILL_DIR="${HOME}/.cdh/skills/ai-dlc-skill"
DEV_SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

if [ -d "$CANONICAL_SKILL_DIR" ]; then
    SKILL_DIR="$CANONICAL_SKILL_DIR"
else
    SKILL_DIR="$DEV_SKILL_DIR"
fi

ONECODE_SKILLS_DIR="${HOME}/.onecode/skills"
SYMLINK_TARGET="$ONECODE_SKILLS_DIR/ai-dlc-skill"

mkdir -p "$ONECODE_SKILLS_DIR"

if [ ! -L "$SYMLINK_TARGET" ]; then
  ln -s "$SKILL_DIR" "$SYMLINK_TARGET"
  echo "Created symlink: $SYMLINK_TARGET -> $SKILL_DIR"
else
  echo "Symlink already exists: $SYMLINK_TARGET"
fi

echo "ai-dlc-skill registered for OneCode"