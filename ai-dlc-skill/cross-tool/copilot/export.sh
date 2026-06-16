#!/usr/bin/env bash
# copilot/export.sh — Export AI-DLC rules to GitHub Copilot format (.github/copilot-instructions.md)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"

mkdir -p "$PROJECT_ROOT/.github"

cat > "$PROJECT_ROOT/.github/copilot-instructions.md" << 'EOF'
# AI-DLC Copilot Instructions

## Development Workflow
Follow the AI-Driven Development Lifecycle:
1. Understand (SDD+BDD): Intent → EARS Spec → BDD Features
2. Plan (SDD+TDD): Design Doc → Task DAG → Test Plan
3. Verify (BDD+TDD): TDD Red→Green→Refactor per scenario
4. Deliver (SDD+Cloud): Stack Preview → e2e → Production + BVT

## Component FR Mapping
- NATIVE-FR-* → apps/native/
- DESKTOP-FR-* → apps/desktop/
- WEB-FR-* → apps/web/
- BE-FR-* → apps/backend/
- WXA-FR-* → apps/wxa/
- MYA-FR-* → apps/mya/
- TTA-FR-* → apps/tta/
- INT-FR-* → contracts/ + packages/shared/

## Quality Gates
- Coverage ≥80%
- BDD 100% pass
- 0 security violations
- No TODO/FIXME in src/
- Contract backward-compatible
- Cross-stack e2e for multi-component changes

## Security
- Secrets: secure storage, no hardcoding
- Input: validate type/length/format/range
- SQL: parameterized queries only
- CORS: explicit origins, no wildcard in prod
- HTTPS only in production
EOF

echo "  ✓ $PROJECT_ROOT/.github/copilot-instructions.md"
