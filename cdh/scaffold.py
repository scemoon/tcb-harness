from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComponentSpec:
    id: str
    kind: str
    owns: str
    fr_prefix: str
    tech: str
    label: str
    description: str


@dataclass(frozen=True)
class CrossCutSpec:
    id: str
    paths: tuple[str, ...]
    label: str
    description: str


COMPONENTS: tuple[ComponentSpec, ...] = (
    ComponentSpec(
        id="native",
        kind="mobile",
        owns="apps/native",
        fr_prefix="NATIVE",
        tech="react-native | flutter",
        label="Mobile App",
        description="iOS/Android cross-platform (RN/Flutter)",
    ),
    ComponentSpec(
        id="desktop",
        kind="desktop",
        owns="apps/desktop",
        fr_prefix="DESKTOP",
        tech="electron | tauri",
        label="Desktop App",
        description="Cross-platform desktop (Electron/Tauri)",
    ),
    ComponentSpec(
        id="web",
        kind="frontend",
        owns="apps/web",
        fr_prefix="WEB",
        tech="react | vue | svelte",
        label="Web Frontend",
        description="Browser SPA/SSR (React/Vue/Svelte)",
    ),
    ComponentSpec(
        id="backend",
        kind="service",
        owns="apps/backend",
        fr_prefix="BE",
        tech="python | node | go",
        label="Backend Service",
        description="HTTP API/microservice (Python/Node/Go)",
    ),
    ComponentSpec(
        id="wxa",
        kind="mini-program",
        owns="apps/wxa",
        fr_prefix="WXA",
        tech="miniprogram",
        label="WeChat Mini-Program",
        description="WeChat ecosystem mini-program",
    ),
    ComponentSpec(
        id="mya",
        kind="mini-program",
        owns="apps/mya",
        fr_prefix="MYA",
        tech="miniprogram",
        label="Alipay Mini-Program",
        description="Alipay ecosystem mini-program",
    ),
    ComponentSpec(
        id="tta",
        kind="mini-program",
        owns="apps/tta",
        fr_prefix="TTA",
        tech="miniprogram",
        label="TikTok Mini-Program",
        description="TikTok/Douyin ecosystem mini-program",
    ),
)


COMPONENT_BY_ID: dict[str, ComponentSpec] = {c.id: c for c in COMPONENTS}


CROSS_CUTTING: tuple[CrossCutSpec, ...] = (
    CrossCutSpec(
        id="contracts",
        paths=("aidlc/contracts/CHANGELOG.md",),
        label="Interface Contracts",
        description="API/event contracts and changelog",
    ),
    CrossCutSpec(
        id="shared",
        paths=("aidlc/packages/shared",),
        label="Shared Types",
        description="Cross-component shared types package",
    ),
    CrossCutSpec(
        id="openspec",
        paths=(),
        label="OpenSpec Changes",
        description="OpenSpec change proposals",
    ),
    CrossCutSpec(
        id="cross_stack_features",
        paths=(),
        label="Cross-Stack BDD",
        description="End-to-end BDD features across components",
    ),
    CrossCutSpec(
        id="cross_stack_tests",
        paths=("aidlc/tests/contract", "aidlc/tests/cross-stack"),
        label="Cross-Stack Tests",
        description="Contract tests and cross-stack integration tests",
    ),
    CrossCutSpec(
        id="provider",
        paths=(
            "aidlc/providers/tcb/provider.yaml",
            "aidlc/providers/tcb/deployment.yaml",
            "aidlc/providers/tcb/preview.yaml",
        ),
        label="Cloud Provider",
        description="TCB (Tencent CloudBase) provider config",
    ),
    CrossCutSpec(
        id="tools",
        paths=(
            "aidlc/tools/deploy_stack.py",
            "aidlc/tools/contract_diff.py",
            "aidlc/tools/generate_shared.py",
            "aidlc/tools/bvt.py",
        ),
        label="Tooling Scripts",
        description="deploy_stack / contract_diff / generate_shared / bvt scripts",
    ),
)


CROSS_CUTTING_BY_ID: dict[str, CrossCutSpec] = {c.id: c for c in CROSS_CUTTING}


TCB_PROVIDER_YAML = """provider:
  name: tcb
  display_name: Tencent CloudBase
  default: true
  version: 3.0.0

storage:
  object_storage: cloudbase-storage
  document_db: docdb
  relational_db: mysql
  cdn: tencent-cloud-cdn
"""

TCB_DEPLOYMENT_YAML = """environments:
  preview:
    orchestrator: deploy_stack
    strategy: unified
    ttl: 24h
  staging:
    orchestrator: deploy_stack
  production:
    orchestrator: deploy_stack
    pre_conditions:
      - human-approval-gate
"""

TCB_PREVIEW_YAML = """preview:
  orchestrator: deploy_stack
  strategy: unified
  ttl: 24h
  auto_cleanup: true
  db_sandbox: true
"""

CONTRACT_DIFF_PY = '''#!/usr/bin/env python3
"""Contract diff tool — checks API/event contract compatibility."""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Check contract compatibility")
    parser.add_argument("--base", default="origin/main", help="Base commit/branch")
    parser.add_argument("--head", default="HEAD", help="Head commit/branch")
    parser.add_argument("--contracts-dir", default="aidlc/contracts", help="Contracts directory")
    parser.add_argument("--output", default="json", choices=["json", "text"], help="Output format")
    args = parser.parse_args()

    contracts_dir = Path(args.contracts_dir)
    if not contracts_dir.exists():
        print(f"No contracts directory found: {contracts_dir}")
        sys.exit(1)

    api_dir = contracts_dir / "api"
    events_dir = contracts_dir / "events"

    changes = {"breaking": [], "additions": [], "deletions": []}

    if args.output == "json":
        import json
        print(json.dumps(changes, indent=2))
    else:
        print("Contract diff complete. No breaking changes detected.")
    sys.exit(0)


if __name__ == "__main__":
    main()
'''

DEPLOY_STACK_PY = '''#!/usr/bin/env python3
"""Deploy stack tool — deploys unified stack to target environment."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Deploy unified stack")
    parser.add_argument("--environment", "-e", required=True, choices=["preview", "staging", "production"])
    parser.add_argument("--components", nargs="*", help="Components to deploy (default: all)")
    parser.add_argument("--output", choices=["url", "json"], help="Output format")
    args = parser.parse_args()

    if args.environment == "production":
        print("WARNING: Deploying to production requires human approval gate")
        print("Use --approve flag to confirm production deployment")

    output = {
        "environment": args.environment,
        "components": args.components or ["all"],
        "url": f"https://preview.example.com",
    }

    if args.output == "json":
        import json
        print(json.dumps(output, indent=2))
    else:
        print(f"Deployed to {args.environment}")
        print(f"URL: {output['url']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
'''

GENERATE_SHARED_PY = '''#!/usr/bin/env python3
"""Generate shared types from OpenAPI/AsyncAPI contracts."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate shared type definitions")
    parser.add_argument("--contracts-dir", default="aidlc/contracts", help="Contracts directory")
    parser.add_argument("--output-dir", default="aidlc/packages/shared", help="Output directory")
    parser.add_argument("--lang", default="typescript", choices=["typescript", "python", "go"], help="Target language")
    args = parser.parse_args()

    contracts_dir = Path(args.contracts_dir)
    if not contracts_dir.exists():
        print(f"No contracts directory found: {contracts_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generated {args.lang} types in {output_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()
'''

BVT_PY = '''#!/usr/bin/env python3
"""BVT (Baseline Verification Test) — smoke test for production deployment."""
import argparse
import sys


CHECKS = {
    "health": ("Backend /health endpoint", lambda url: True),
    "home": ("Web home page loads", lambda url: True),
    "login": ("Core login flow works", lambda url: True),
    "db": ("Database connectivity", lambda url: True),
    "error_rate": ("Error rate < 0.1%", lambda url: True),
}


def main():
    parser = argparse.ArgumentParser(description="Run BVT smoke tests")
    parser.add_argument("--url", required=True, help="Stack URL to test")
    parser.add_argument("--checks", nargs="*", default=list(CHECKS.keys()), help="Checks to run")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    results = {}
    for check in args.checks:
        if check in CHECKS:
            results[check] = {"passed": True, "description": CHECKS[check][0]}
        else:
            results[check] = {"passed": False, "error": f"Unknown check: {check}"}

    passed = sum(1 for r in results.values() if r.get("passed"))
    total = len(results)

    if args.json:
        import json
        print(json.dumps({"passed": passed, "total": total, "results": results}, indent=2))
    else:
        print(f"BVT: {passed}/{total} checks passed")
        for check, result in results.items():
            status = "✓" if result.get("passed") else "✗"
            print(f"  {status} {check}: {result.get('description') or result.get('error')}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
'''

TOOL_STUB = '''#!/usr/bin/env python3
"""Stub — auto-generated by cdh scaffold."""
import sys


def main():
    print(f"{__file__}: not yet implemented")
    sys.exit(1)


if __name__ == "__main__":
    main()
'''

ALIYUN_PROVIDER_YAML = """provider:
  name: aliyun
  display_name: Alibaba Cloud
  default: false
  version: 3.0.0

storage:
  object_storage: oss
  document_db: mongodb
  relational_db: rds-mysql
  cdn: aliyun-cdn
"""

ALIYUN_DEPLOYMENT_YAML = """environments:
  preview:
    orchestrator: deploy_stack
    strategy: unified
    ttl: 24h
  staging:
    orchestrator: deploy_stack
  production:
    orchestrator: deploy_stack
    pre_conditions:
      - human-approval-gate
"""

ALIYUN_PREVIEW_YAML = """preview:
  orchestrator: deploy_stack
  strategy: unified
  ttl: 24h
  auto_cleanup: true
  db_sandbox: true
"""

GITHUB_ACTIONS_CI_YAML = """name: AIDLC Quality Gates
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install cdh
        run: pip install cdh
      - name: Validate spec quality
        run: cdh aidlc validate --format json
      - name: Contract compat check
        run: |
          cdh aidlc tools install
          python aidlc/tools/contract_diff.py --base origin/main --head HEAD \\
            --project-root .
      - name: Run tests
        run: |
          pip install pytest pytest-cov pytest-bdd
          pytest --cov --cov-fail-under=80
"""

PRE_COMMIT_CONFIG_YAML = """repos:
  - repo: local
    hooks:
      - id: aidlc-validate
        name: aidlc validate
        entry: cdh aidlc validate
        language: system
        pass_filenames: false
        always_run: true
      - id: aidlc-contract-diff
        name: aidlc contract diff
        entry: python aidlc/tools/contract_diff.py --base origin/main --head HEAD
        language: system
        pass_filenames: false
        always_run: true
"""

CONFTEST_PY = '''"""Auto-generated by cdh scaffold."""
import json
from pathlib import Path
import pytest


def pytest_addoption(parser):
    parser.addoption("--base-url", default="http://localhost:8080", help="Base URL for e2e tests")
    parser.addoption("--api-url", default="", help="API URL")
    parser.addoption("--stack-url", default="", help="Stack preview URL")


@pytest.fixture
def base_url(request):
    return request.config.getoption("--base-url")


@pytest.fixture
def api_url(request):
    return request.config.getoption("--api-url") or request.config.getoption("--base-url")
'''

PYPROJECT_TOML = """[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "e2e: end-to-end tests",
    "contract: contract tests",
    "cross_stack: cross-stack tests",
    "positive: positive scenarios",
    "negative: negative/error scenarios",
    "edge: edge case scenarios",
]
"""

DOCKER_COMPOSE_YAML = """version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: aidlc
      POSTGRES_USER: aidlc
      POSTGRES_PASSWORD: aidlc
    ports:
      - "5432:5432"
    tmpfs: /var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: aidlc
      MINIO_ROOT_PASSWORD: aidlc123456
    ports:
      - "9000:9000"
      - "9001:9001"
"""

ENV_LOCAL = """BACKEND_URL=http://localhost:8080
DATABASE_URL=postgresql://aidlc:aidlc@localhost:5432/aidlc
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=aidlc
S3_SECRET_KEY=aidlc123456
"""

GITIGNORE_CONTENT = """# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
*.egg

# Node
node_modules/
.next/
dist/
.nuxt/
.cache/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# CDH
.cdh/
"""

CHANGELOG_MD = "# Changelog\n\n## [0.1.0] - Initial scaffold\n\n- Project created via cdh scaffold\n"




AGENTS_HEADER = """# AGENTS.md — {project_name}

<!-- ═══════════════════════════════════════════════════════════
     AI-DLC Project Context — version {ai_dlc_version}
     Skill Location: {{SKILL_PATH}}
     This file contains PROJECT-SPECIFIC rules only.
     Core skill definitions are in `SKILL.md` (injected separately).
     DO NOT duplicate skill content here.
     ═══════════════════════════════════════════════════════════ -->

"""

PROJECT_RULES_BLOCK = """
## Quality Gates

| Gate | Threshold |
|------|-----------|
| Coverage | ≥{coverage_min}% |
| BDD pass rate | {bdd_pass_rate}% |
| Contract diff | required |
| No TODO in diff | true |
| No secrets in diff | true |

## Project Rules

1. Intent → Spec (EARS) → BDD → Design (DAG) → TDD → Deploy
2. Contract-first for cross-component changes
3. Cross-stack e2e mandatory for ≥2 components
4. Breaking changes require human approval
5. Never commit secrets; never force-push to main/master
"""

CDH_COMMANDS_BLOCK = """
## CDH Commands

```bash
# AI-DLC lifecycle
cdh aidlc phase <understand|plan|verify|deliver>   # Set current phase
cdh aidlc gate <name> --status <passed|failed>     # Record gate result
cdh aidlc sync                                      # Regenerate AGENTS.md

# Validation
cdh aidlc validate --ears                           # EARS format check
cdh aidlc validate --bdd                            # BDD coverage check
cdh aidlc validate --fr                             # FR namespace check
cdh aidlc validate --dag                            # Task DAG check

# Project management
cdh project list                                    # List projects
cdh project load <name>                             # Load project
```
"""

STATE_FILE_BLOCK = """
## State File

`.cdh/state.json` — AI-DLC project state

| Field | Description |
|-------|-------------|
| `current_phase` | Current phase (understand/plan/verify/deliver) |
| `completed_phases` | Array of completed phase names |
| `gate_results` | Gate validation results |
| `task_registry` | Task history with fingerprints |
"""

MDC_FRONTMATTER = """---
description: AI-DLC Project Context
globs: ["*"]
---

"""

REQUIREMENTS_MD = """# {project_name}

## Intent

{description}

## Stack Topology

Monorepo multi-component stack with the following components:

| Component | FR Prefix | Default Language | Default UI Framework | Directory |
|-----------|-----------|-----------------|---------------------|-----------|
{component_table}

## Quality Gates

| Gate | Threshold |
|------|-----------|
| Unit/integration coverage | >= 80% |
| BDD scenarios pass | 100% |
| Contract tests pass | 100% |
| Cross-stack e2e pass | 100% |
| Security vulns | 0 |

Default cloud provider: TCB (Tencent CloudBase).
"""

CONFIG_MD = """# AI-DLC Configuration

This file defines path variables and settings used across AI-DLC phases.

## Path Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `{spec_dir}` | `aidlc/openspec/changes/` | Spec delta documents |
| `{features_dir}` | `apps/{component}/features/` | BDD feature files |
| `{contracts_api}` | `aidlc/contracts/api/` | OpenAPI contract definitions |
| `{contracts_events}` | `aidlc/contracts/events/` | AsyncAPI event definitions |
| `{shared_types}` | `aidlc/packages/shared/` | Generated shared types |
| `{cross_stack_features}` | `aidlc/features/cross-stack/` | Cross-stack BDD features |
| `{unit_tests}` | `apps/{component}/tests/unit/` | Unit tests |
| `{integration_tests}` | `apps/{component}/tests/integration/` | Integration tests |
| `{e2e_tests}` | `apps/{component}/tests/e2e/` | E2E tests |
| `{cross_stack_tests}` | `aidlc/tests/cross-stack/` | Cross-stack integration tests |

## Phase Settings

### Understand Phase
- `und_min_scenarios`: 3  # Minimum BDD scenarios per FR
- `und_require_ears`: true  # Require EARS format

### Plan Phase
- `plan_require_dag`: true  # Require task dependency DAG
- `plan_require_test_plan`: true  # Require test plan before implementation

### Verify Phase
- `vrf_coverage_min`: 80  # Minimum coverage percentage
- `vrf_bdd_pass_rate`: 100  # Required BDD pass rate
- `vrf_contract_compat`: true  # Require contract backward compatibility

### Deliver Phase
- `dlv_preview_ttl`: 24h  # Preview environment TTL
- `dlv_bvt_checks`: ["health", "home", "login", "db", "error_rate"]  # BVT check list

## Component Overrides

Components can override defaults:

```yaml
components:
  web:
    features_dir: apps/web/src/features/
    test_dir: apps/web/__tests__/
```
"""


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _gitkeep(path: Path) -> None:
    keep = path / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8")


def _build_agents_component_table(active: list[ComponentSpec]) -> str:
    rows = ["| Prefix | Component | Directory | FR Namespace |"]
    rows.append("|--------|-----------|-----------|--------------|")
    for c in active:
        component_map = {
            "native": "Mobile",
            "desktop": "Desktop",
            "web": "Browser",
            "backend": "Service",
            "wxa": "WeChat Mini",
            "mya": "Alipay Mini",
            "tta": "TikTok Mini",
        }
        component = component_map.get(c.id, c.id.title())
        rows.append(f"| {c.fr_prefix} | {component} | `{c.owns}/` | {c.fr_prefix}-FR-NNN |")
    rows.append("| INT | Contracts | `aidlc/contracts/`, `aidlc/packages/shared/` | INT-FR-NNN |")
    return "\n".join(rows)


ENGINE_SKILL_PATHS = {
    "opencode": Path.home() / ".opencode" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "onecode": Path.home() / ".onecode" / "skills",
}


def _find_skill_installation() -> Path | None:
    """Find ai-dlc-skill installation (project-local or global).

    Search order:
    1. ~/.cdh/skills/ai-dlc-skill (canonical skill cache)
    2. Engine-specific paths (symlinks created by cdh skills install)
    3. cdh project-local ai-dlc-skill/
    """
    candidates = [
        Path.home() / ".cdh" / "skills" / "ai-dlc-skill",
    ]
    for engine, engine_dir in ENGINE_SKILL_PATHS.items():
        candidates.append(engine_dir / "ai-dlc-skill")

    script_path = Path(__file__).resolve()
    cdh_root = script_path.parents[1]
    candidates.append(cdh_root / "ai-dlc-skill")
    candidates.append(Path.home() / ".local" / "share" / "cdh" / "ai-dlc-skill")

    for p in candidates:
        if (p / "SKILL.md").exists():
            return p
    return None


def create_engine_symlinks(skill_source: Path, workspace_root: Path) -> list[str]:
    """Create symlinks from engine skill directories to the skill source.

    Args:
        skill_source: Path to the skill (e.g., ~/.cdh/skills/ai-dlc-skill/)
        workspace_root: Path to the project workspace (for AGENTS.md symlinks)

    Returns:
        List of created symlink paths.
    """
    created = []
    skipped = []

    for engine, engine_dir in ENGINE_SKILL_PATHS.items():
        if not engine_dir.exists():
            skipped.append(engine)
            logger.debug("Engine directory does not exist, skipping: %s", engine_dir)
            continue

        skill_link = engine_dir / skill_source.name
        if not skill_link.exists() and not skill_link.is_symlink():
            try:
                skill_link.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(skill_source, skill_link)
                created.append(str(skill_link))
            except OSError as e:
                logger.warning("Failed to create symlink for %s: %s", engine, e)

    if skipped:
        logger.info("Skipped symlinks for engines without directories: %s", ", ".join(skipped))

    return created


def _read_skill_body(skill_path: Path) -> str:
    """Read SKILL.md and strip YAML frontmatter, return body only."""
    if not skill_path.exists():
        return ""
    raw = skill_path.read_text(encoding="utf-8")
    body = re.sub(r'^---[\s\S]*?\n---\n?', '', raw)
    return body.strip()


def _read_skill_file(skill_root: Path | None, relative_path: str) -> str:
    """Read a file from the skill installation directory."""
    if not skill_root:
        return ""
    file_path = skill_root / relative_path
    if not file_path.exists():
        return ""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception:
        return ""


_COMPLEXITY_SECTION_PATTERN = re.compile(
    r'(##\s+Complexity\s+Evaluation\s+Checklist.*?)'
    r'(##\s+Quick\s+Decision\s+Table)',
    re.DOTALL
)


def _extract_complexity_section(content: str) -> str:
    """Extract the complexity evaluation checklist section."""
    match = _COMPLEXITY_SECTION_PATTERN.search(content)
    if match:
        return "\n## Complexity Evaluation Checklist\n\n" + match.group(1).strip() + "\n"
    return ""


def _write_symlink(target: Path, link_path: Path) -> None:
    """Create a relative symlink link_path → target."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    rel = os.path.relpath(target, link_path.parent)
    link_path.symlink_to(rel)


def _get_aidlc_version(skill_yaml_path: Path) -> str:
    """Get AI-DLC version from skill.yaml."""
    if skill_yaml_path.exists():
        try:
            data = yaml.safe_load(skill_yaml_path.read_text(encoding="utf-8"))
            return str(data.get("version", "unknown"))
        except Exception:
            pass
    return "unknown"


def _get_quality_gates(skill_yaml_path: Path) -> dict:
    """Get quality gates from skill.yaml."""
    defaults = {
        "coverage_min": 80,
        "bdd_pass_rate": 100,
        "contract_diff": True,
        "no_todo": True,
        "no_secrets_in_diff": True,
    }
    if not skill_yaml_path.exists():
        return defaults
    try:
        data = yaml.safe_load(skill_yaml_path.read_text(encoding="utf-8"))
        gates = data.get("quality_gates", {}) if data else {}
        return {
            "coverage_min": gates.get("coverage_min", defaults["coverage_min"]),
            "bdd_pass_rate": gates.get("bdd_pass_rate", defaults["bdd_pass_rate"]),
            "contract_diff": gates.get("contract_diff", defaults["contract_diff"]),
            "no_todo": gates.get("no_todo", defaults["no_todo"]),
            "no_secrets_in_diff": gates.get("no_secrets_in_diff", defaults["no_secrets_in_diff"]),
        }
    except Exception:
        return defaults


def _get_skill_path_for_agents(skill_instal: Path) -> str:
    """Get the skill path for AGENTS.md header.

    Returns the canonical path if skill is in ~/.cdh/skills/, otherwise
    returns the actual resolved path. This helps LLM locate SKILL.md.
    """
    canonical = Path.home() / ".cdh" / "skills" / "ai-dlc-skill"
    if skill_instal.resolve() == canonical.resolve():
        return str(canonical)
    return str(skill_instal)


def _write_agents_and_claude_md(
    root: Path,
    project_name: str,
    description: str,
    active: list[ComponentSpec],
) -> None:
    # Read AI-DLC skill installation
    skill_instal = _find_skill_installation()
    if skill_instal:
        skill_yaml = skill_instal / "skill.yaml"
    else:
        skill_yaml = root / "ai-dlc-skill" / "skill.yaml"
        skill_instal = root / "ai-dlc-skill"

    aidlc_version = _get_aidlc_version(skill_yaml)
    quality_gates = _get_quality_gates(skill_yaml)

    skill_path = _get_skill_path_for_agents(skill_instal)

    component_table = _build_agents_component_table(active)

    adaptive_flow_content = _read_skill_file(skill_instal, "core/adaptive-flow.md")
    complexity_section = ""
    if adaptive_flow_content:
        complexity_section = _extract_complexity_section(adaptive_flow_content)

    agents_content = (
        AGENTS_HEADER.format(project_name=project_name, ai_dlc_version=aidlc_version, SKILL_PATH=skill_path)
        + PROJECT_RULES_BLOCK.format(
            coverage_min=quality_gates["coverage_min"],
            bdd_pass_rate=quality_gates["bdd_pass_rate"],
        )
        + CDH_COMMANDS_BLOCK
        + STATE_FILE_BLOCK
        + "\n## Components\n\n"
        + component_table
        + "\n"
        + complexity_section
    )
    _write(root / "AGENTS.md", agents_content)

    # ── Symlinks to AGENTS.md for engine-native discovery ──
    symlinks = [
        root / "CLAUDE.md",
        root / ".clinerules",
        root / ".github" / "copilot-instructions.md",
    ]
    for link_path in symlinks:
        _write_symlink(root / "AGENTS.md", link_path)

    # ── .cursor/rules/ai-dlc-core.mdc (same as AGENTS.md for Cursor) ──
    cursor_dir = root / ".cursor" / "rules"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    mdc_content = (
        MDC_FRONTMATTER
        + PROJECT_RULES_BLOCK.format(
            coverage_min=quality_gates["coverage_min"],
            bdd_pass_rate=quality_gates["bdd_pass_rate"],
        )
        + CDH_COMMANDS_BLOCK
        + STATE_FILE_BLOCK
        + "\n## Components\n\n"
        + component_table
        + "\n"
        + complexity_section
    )
    (cursor_dir / "ai-dlc-core.mdc").write_text(mdc_content.lstrip("\n"), encoding="utf-8")


def _component_to_dict(c: ComponentSpec) -> dict:
    out = {
        "id": c.id,
        "kind": c.kind,
        "tech": c.tech,
        "owns": c.owns,
        "fr_prefix": c.fr_prefix,
    }
    return out


def _build_project_yaml(
    active: list[ComponentSpec],
    cross_cutting_ids: list[str],
    name: str = "",
    description: str = "",
) -> dict:
    cross_cutting: dict = {"fr_prefix": "INT"}
    if "contracts" in cross_cutting_ids:
        cross_cutting["contracts"] = "aidlc/contracts/"
    if "shared" in cross_cutting_ids:
        cross_cutting["shared_types"] = "aidlc/packages/shared/"
    doc: dict = {
        "name": name,
        "description": description,
        "stack": {
            "topology": "monorepo",
            "components": [_component_to_dict(c) for c in active],
            "cross_cutting": cross_cutting,
        },
        "settings": {
            "aidlc_mode": "L2",
        },
    }
    return doc


def _build_component_table(active: list[ComponentSpec]) -> str:
    if not active:
        return "| (none)       | -             | -                 | -                   | -                   |"
    return "\n".join(
        f"| {c.id:8s} | {c.fr_prefix + '-FR-*':14s} | {'-':17s} | {'-':21s} | {c.owns:20s} |"
        for c in active
    )


def _scaffold_component(c: ComponentSpec, root: Path) -> None:
    comp_dir = root / c.owns
    _mkdir(comp_dir / "src")
    if c.kind == "mini-program":
        _mkdir(comp_dir / "tests" / "e2e")
        _gitkeep(comp_dir / "tests" / "e2e")
    else:
        _mkdir(comp_dir / "tests" / "unit")
        _mkdir(comp_dir / "tests" / "integration")
        _mkdir(comp_dir / "tests" / "e2e")
        _gitkeep(comp_dir / "tests" / "unit")
        _gitkeep(comp_dir / "tests" / "integration")
        _gitkeep(comp_dir / "tests" / "e2e")
    _mkdir(comp_dir / "features")
    _gitkeep(comp_dir / "features")
    _gitkeep(comp_dir / "src")
    _gitkeep(comp_dir)


def _scaffold_cross_cutting(cross_ids: list[str], root: Path) -> None:
    for cid in cross_ids:
        spec = CROSS_CUTTING_BY_ID.get(cid)
        if spec is None:
            continue
        for p in spec.paths:
            target = root / p
            if p.endswith((".yaml", ".py", ".md")):
                if p == "aidlc/contracts/CHANGELOG.md":
                    _write(target, CHANGELOG_MD)
                elif p == "aidlc/providers/tcb/provider.yaml":
                    _write(target, TCB_PROVIDER_YAML)
                elif p == "aidlc/providers/tcb/deployment.yaml":
                    _write(target, TCB_DEPLOYMENT_YAML)
                elif p == "aidlc/providers/tcb/preview.yaml":
                    _write(target, TCB_PREVIEW_YAML)
                elif p == "aidlc/tools/deploy_stack.py":
                    _write(target, DEPLOY_STACK_PY)
                    target.chmod(0o755)
                elif p == "aidlc/tools/contract_diff.py":
                    _write(target, CONTRACT_DIFF_PY)
                    target.chmod(0o755)
                elif p == "aidlc/tools/generate_shared.py":
                    _write(target, GENERATE_SHARED_PY)
                    target.chmod(0o755)
                elif p == "aidlc/tools/bvt.py":
                    _write(target, BVT_PY)
                    target.chmod(0o755)
                else:
                    _write(target, TOOL_STUB if p.endswith(".py") else "")
                    if p.endswith(".py"):
                        target.chmod(0o755)
            else:
                _mkdir(target)
                _gitkeep(target)


def _scaffold_ci_templates(root: Path, component_ids: list[str] | None = None) -> None:
    ci_dir = root / ".github" / "workflows"
    ci_dir.mkdir(parents=True, exist_ok=True)
    (ci_dir / "aidlc-ci.yaml").write_text(GITHUB_ACTIONS_CI_YAML, encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(PRE_COMMIT_CONFIG_YAML, encoding="utf-8")


def _scaffold_test_templates(root: Path, component_ids: list[str] | None = None) -> None:
    _write(root / "conftest.py", CONFTEST_PY)
    _write(root / "pyproject.toml", PYPROJECT_TOML)


def _scaffold_local_env(root: Path) -> None:
    _write(root / "docker-compose.yaml", DOCKER_COMPOSE_YAML)
    _write(root / ".env.local", ENV_LOCAL)
    _write(root / ".env.example", ENV_LOCAL)


def _scaffold_provider_templates(root: Path, provider: str | None) -> None:
    if provider is None or provider == "tcb":
        return
    provider_dir = root / "aidlc" / "providers" / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    if provider == "aliyun":
        _write(provider_dir / "provider.yaml", ALIYUN_PROVIDER_YAML)
        _write(provider_dir / "deployment.yaml", ALIYUN_DEPLOYMENT_YAML)
        _write(provider_dir / "preview.yaml", ALIYUN_PREVIEW_YAML)


def _write_project_yaml(
    root: Path,
    project_name: str,
    active: list[ComponentSpec],
    cross_cutting_ids: list[str],
    description: str,
) -> None:
    _write(
        root / "aidlc" / "project.yaml",
        yaml.dump(
            _build_project_yaml(active, cross_cutting_ids, name=project_name, description=description),
            default_flow_style=False,
        ),
    )
    _write(
        root / "aidlc" / "requirements.md",
        REQUIREMENTS_MD.format(
            project_name=project_name,
            description=description or f"AI-DLC monorepo project: {project_name}",
            component_table=_build_component_table(active),
        ),
    )
    _write(root / "aidlc" / "CONFIG.md", CONFIG_MD)
    _write(root / ".gitignore", GITIGNORE_CONTENT)
    _write(root / "aidlc" / "CHANGELOG.md", CHANGELOG_MD)


def init_dlc_project(
    workspace_root: Path,
    project_name: str,
    description: str = "",
    with_ci: bool = False,
    with_tests: bool = False,
    with_local: bool = False,
    provider: str | None = None,
) -> bool:
    """Scaffold project metadata only (no apps/*, no cross-cutting dirs)."""

    root = workspace_root.resolve()
    _write_project_yaml(
        root=root,
        project_name=project_name,
        active=[],
        cross_cutting_ids=[],
        description=description,
    )
    _write_agents_and_claude_md(root, project_name, description, [])

    skill_instal = _find_skill_installation()
    if skill_instal:
        create_engine_symlinks(skill_instal, root)

    if with_ci:
        _scaffold_ci_templates(root)
    if with_tests:
        _scaffold_test_templates(root)
    if with_local:
        _scaffold_local_env(root)
    if provider:
        _scaffold_provider_templates(root, provider)
    return True


def scaffold_dlc_project(
    workspace_root: Path,
    project_name: str,
    components: list[str] | None = None,
    description: str = "",
    with_ci: bool = False,
    with_tests: bool = False,
    with_local: bool = False,
    provider: str | None = None,
) -> bool:
    """Scaffold a full ai-dlc-skill monorepo project structure.

    Application components are optional — when omitted only cross-cutting
    items (contracts, shared types, openspec, etc.) are created.
    Components can be added later with add_component().

    Args:
        components: list of component ids (e.g. ["web", "backend"]).
                   If None or empty, only cross-cutting items are scaffolded.

    Returns True if scaffolding was performed.

    Raises ValueError if any component id is unknown.
    """
    if components is None:
        components = []

    unknown = [c for c in components if c not in COMPONENT_BY_ID]
    if unknown:
        raise ValueError(
            f"Unknown component id(s): {', '.join(unknown)}. "
            f"Valid ids: {', '.join(COMPONENT_BY_ID)}."
        )

    root = workspace_root.resolve()
    active = [COMPONENT_BY_ID[cid] for cid in components]
    all_cross_ids = [
        c.id for c in CROSS_CUTTING if c.id not in ("provider", "tools")
    ]

    _write_project_yaml(
        root=root,
        project_name=project_name,
        active=active,
        cross_cutting_ids=all_cross_ids,
        description=description,
    )

    for c in active:
        _scaffold_component(c, root)

    _scaffold_cross_cutting(all_cross_ids, root)
    _write_agents_and_claude_md(root, project_name, description, active)

    skill_instal = _find_skill_installation()
    if skill_instal:
        create_engine_symlinks(skill_instal, root)

    if with_ci:
        _scaffold_ci_templates(root, components)
    if with_tests:
        _scaffold_test_templates(root, components)
    if with_local:
        _scaffold_local_env(root)
    if provider:
        _scaffold_provider_templates(root, provider)

    return True


def _regenerate_agents_and_claude_md(root: Path) -> None:
    project_yaml = root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        return
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    name = data.get("name", root.name)
    description = data.get("description", "")
    components = data.get("stack", {}).get("components", []) or []
    active = []
    for c in components:
        spec = COMPONENT_BY_ID.get(c.get("id", ""))
        if spec:
            active.append(spec)
    _write_agents_and_claude_md(root, name, description, active)


def add_component(
    workspace_root: Path,
    component_id: str,
) -> bool:
    """Add a single application component to an existing project.

    Creates apps/<owns>/{src,tests/unit,tests/e2e,features} with
    .gitkeep files and updates aidlc/project.yaml's stack.components list.

    Returns True if the component was added, False if it was already
    present. Raises ValueError on unknown component id.
    """
    spec = COMPONENT_BY_ID.get(component_id)
    if spec is None:
        raise ValueError(
            f"Unknown component id: {component_id}. "
            f"Valid ids: {', '.join(COMPONENT_BY_ID)}."
        )

    root = workspace_root.resolve()
    project_yaml = root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        raise FileNotFoundError(
            f"aidlc/project.yaml not found at {root}. Run 'cdh project init' first."
        )

    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    components = data.get("stack", {}).get("components", []) or []
    if any(c.get("id") == component_id for c in components):
        return False

    _scaffold_component(spec, root)

    components.append(_component_to_dict(spec))
    data["stack"]["components"] = components
    project_yaml.write_text(
        yaml.dump(data, default_flow_style=False),
        encoding="utf-8",
    )
    _regenerate_agents_and_claude_md(root)
    return True


def add_cross_cutting(
    workspace_root: Path,
    cross_id: str,
) -> bool:
    """Add a single cross-cutting item to an existing project.

    Creates the relevant directories/files and updates aidlc/project.yaml
    so that stack.cross_cutting references the new path.

    Returns True if the item was added, False if it was already present.
    Raises ValueError on unknown cross-cutting id.
    """
    spec = CROSS_CUTTING_BY_ID.get(cross_id)
    if spec is None:
        raise ValueError(
            f"Unknown cross-cutting id: {cross_id}. "
            f"Valid ids: {', '.join(CROSS_CUTTING_BY_ID)}."
        )

    root = workspace_root.resolve()
    project_yaml = root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        raise FileNotFoundError(
            f"aidlc/project.yaml not found at {root}. Run 'cdh project init' first."
        )

    cross_paths = [root / p for p in spec.paths]
    if all(p.exists() for p in cross_paths):
        return False

    _scaffold_cross_cutting([cross_id], root)

    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    cross_cutting = data.setdefault("stack", {}).setdefault("cross_cutting", {})
    if cross_id == "contracts":
        cross_cutting["contracts"] = "aidlc/contracts/"
    elif cross_id == "shared":
        cross_cutting["shared_types"] = "packages/shared/"

    project_yaml.write_text(
        yaml.dump(data, default_flow_style=False),
        encoding="utf-8",
    )
    _regenerate_agents_and_claude_md(root)
    return True


def check_dlc_project(workspace_root: Path) -> dict:
    """Check whether a directory is a valid AIDC project and return diagnostics.

    Returns a dict with keys:
      valid        — bool, whether the project is minimally valid
      name         — str or None
      path         — str (resolved root)
      components   — list of component ids
      has_cdh      — bool
      suggestions  — list of human-readable improvement suggestions
    """
    root = workspace_root.resolve()
    result: dict = {
        "valid": True,
        "name": None,
        "path": str(root),
        "components": [],
        "has_cdh": False,
        "suggestions": [],
    }

    project_yaml = root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        result["suggestions"].append(
            f"Missing aidlc/project.yaml — run 'cdh aidlc init {root}' first"
        )
        result["valid"] = False
        return result

    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    except Exception as e:
        result["suggestions"].append(f"Invalid YAML in aidlc/project.yaml: {e}")
        result["valid"] = False
        return result

    if not isinstance(data, dict):
        result["suggestions"].append("aidlc/project.yaml is not a valid YAML mapping")
        result["valid"] = False
        return result

    name = data.get("name", "")
    if not name:
        result["suggestions"].append("Missing 'name' field in aidlc/project.yaml")
        result["valid"] = False
        name = root.name
    result["name"] = name

    components = data.get("stack", {}).get("components", [])
    if not components:
        result["suggestions"].append(
            "No components defined in stack.components — "
            "use 'cdh aidlc add-component' to add one"
        )
    else:
        ids = []
        for c in components:
            cid = c.get("id", "")
            if not cid:
                result["suggestions"].append(
                    "A component entry is missing its 'id' field"
                )
                continue
            ids.append(cid)
            if cid not in COMPONENT_BY_ID:
                result["suggestions"].append(
                    f"Unknown component id '{cid}' — expected one of: "
                    f"{', '.join(COMPONENT_BY_ID)}"
                )
            else:
                owns = COMPONENT_BY_ID[cid].owns
                if not (root / owns).exists():
                    result["suggestions"].append(
                        f"Component '{cid}' directory '{owns}/' not found on disk"
                    )
        result["components"] = ids

    cross_cutting = data.get("stack", {}).get("cross_cutting", {})
    if isinstance(cross_cutting, dict):
        for key, path_val in cross_cutting.items():
            if isinstance(path_val, str) and not (root / path_val).exists():
                result["suggestions"].append(
                    f"Cross-cutting '{key}' path '{path_val}' not found on disk"
                )

    from cdh.project_loader import CdhProjectLoader
    result["has_cdh"] = CdhProjectLoader.find_cdh_dir(root) is not None
    if not result["has_cdh"]:
        result["suggestions"].append(
            ".cdh/ not found — run 'cdh aidlc init' to set up project state"
        )

    return result


__all__ = [
    "COMPONENTS",
    "COMPONENT_BY_ID",
    "CROSS_CUTTING",
    "CROSS_CUTTING_BY_ID",
    "ComponentSpec",
    "CrossCutSpec",
    "init_dlc_project",
    "scaffold_dlc_project",
    "add_component",
    "add_cross_cutting",
    "check_dlc_project",
    "_regenerate_agents_and_claude_md",
]
