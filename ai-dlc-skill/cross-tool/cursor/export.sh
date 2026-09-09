#!/bin/bash
# Generates .cursor/rules/ai-dlc-core.mdc from ai-dlc-skill/SKILL.md

set -euo pipefail

CANONICAL_SKILL_DIR="${HOME}/.cdh/skills/ai-dlc-skill"
DEV_SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="$(cd "$DEV_SKILL_DIR/.." && pwd)"

if [ -d "$CANONICAL_SKILL_DIR" ]; then
    SKILL_DIR="$CANONICAL_SKILL_DIR"
else
    SKILL_DIR="$DEV_SKILL_DIR"
fi

SKILL_FILE="$SKILL_DIR/SKILL.md"
OUTPUT_DIR="$PROJECT_ROOT/.cursor/rules"
OUTPUT_FILE="$OUTPUT_DIR/ai-dlc-core.mdc"

mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_FILE" << 'MDCFRONT'
---
description: AI-DLC Core Lifecycle Rules
globs: ["*"]
---

MDCFRONT

awk '
  BEGIN { found=0; count=0; }
  /^---$/ { count++; if (count == 1) next; if (count == 2) { found=1; next; } }
  found { print }
' "$SKILL_FILE" >> "$OUTPUT_FILE"

cat >> "$OUTPUT_FILE" << 'RULES'
<!-- ═══════════════════════════════════════════════════════════
     Project Rules
     ═══════════════════════════════════════════════════════════ -->

## Project Rules

1. Intent → Spec (EARS) → BDD → Design (DAG) → TDD Red-Green-Refactor → Deploy
2. Contract-first for cross-component changes (`aidlc/contracts/`)
3. FR namespaces: NATIVE|DESKTOP|WEB|BE|WXA|MYA|TTA (apps/) + INT (aidlc/contracts/)
4. Quality gates: coverage ≥80%, BDD 100%, 0 vulns, no TODO, backward-compat contracts
5. Cross-stack e2e mandatory for changes affecting ≥2 components
6. Never commit secrets; never force-push to main/master
7. Chinese for user communication, English for code
8. Run lint/typecheck/test after non-trivial edits
RULES

echo "Generated $OUTPUT_FILE from $SKILL_DIR/SKILL.md"