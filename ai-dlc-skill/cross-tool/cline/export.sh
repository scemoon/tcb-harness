#!/usr/bin/env bash
# cline/export.sh — Export AI-DLC rules to Cline format (.clinerules)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

cat > "$PROJECT_ROOT/.clinerules" << 'EOF'
# AI-DLC Development Rules (Cline)

## Core Methodology
AI-DLC: Intent → Spec (EARS) → BDD → Design → TDD → Deploy

## FR Namespaces
NATIVE apps/native | DESKTOP apps/desktop | WEB apps/web
BE apps/backend | WXA apps/wxa | MYA apps/mya | TTA apps/tta
INT aidlc/contracts/ + aidlc/packages/shared/

## Quality Gates
- Coverage >= 80%
- BDD scenarios 100% pass
- 0 vulns, no TODO in src/
- Contract backward-compat by default
- Cross-stack e2e mandatory for multi-component changes

## Reference
Full skill: .opencode/skills/ai-dlc-skill/
EOF

echo "  ✓ $PROJECT_ROOT/.clinerules"
