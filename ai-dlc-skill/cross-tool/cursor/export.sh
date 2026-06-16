#!/usr/bin/env bash
# cursor/export.sh — Export AI-DLC rules to Cursor format (.cursor/rules/*.mdc)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
CURSOR_DIR="$PROJECT_ROOT/.cursor/rules"

mkdir -p "$CURSOR_DIR"

# Core rules
cat > "$CURSOR_DIR/ai-dlc-core.mdc" << 'EOF'
---
description: AI-DLC Core Lifecycle Rules
globs: ["*"]
---
# AI-DLC Core Rules

See `.opencode/skills/ai-dlc-skill/SKILL.md` for full methodology.

Key rules:
1. Intent → Spec → BDD → Code pipeline
2. Contract-first for cross-component changes
3. 3-phase minimum (L1 bug fix: Verify only; L2 feature: Understand→Verify)
4. All tests must fail before code (TDD Red phase)
5. Coverage ≥80%, BDD 100%, 0 vulns, no TODO

FR namespaces: NATIVE-*, DESKTOP-*, WEB-*, BE-*, WXA-*, MYA-*, TTA-*, INT-*
EOF

echo "  ✓ $CURSOR_DIR/ai-dlc-core.mdc"
