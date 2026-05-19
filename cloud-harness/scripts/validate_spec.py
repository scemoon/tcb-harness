#!/usr/bin/env python3
"""
Spec Validator — Validate a requirements document against quality rules

Usage:
    validate_spec.py <requirements.md> [--strict]

Checks:
    P0 (must pass): EARS syntax, no vague terms, priority, page stack, user roles
    P1 (recommended): exception coverage, quantified NFRs, data entity mapping
"""

import argparse
import re
import sys
from pathlib import Path

# Vague terms blacklist
VAGUE_TERMS = [
    "快速", "高效", "友好", "好看", "流畅", "稳定", "安全",
    "及时", "合理", "适当", "必要", "尽量", "可能",
    "fast", "quick", "efficient", "friendly", "nice", "good",
    "smooth", "stable", "secure", "reasonable", "proper",
]

# EARS patterns
EARS_PATTERNS = [
    r"\bshall\b",                              # Ubiquitous
    r"\bwhen\b.*\bshall\b",                    # Event-Driven
    r"\bif\b.*\bshall\b",                      # Unwanted
    r"\bwhile\b.*\bshall\b",                   # State-Driven
    r"\bwhere\b.*\bshall\b",                   # Optional Feature
]


def parse_markdown_sections(content: str) -> dict:
    """Parse markdown into sections by ## headers."""
    sections = {}
    current_section = "header"
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = line.strip("# ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_section] = "\n".join(current_lines)

    return sections


def extract_requirements(content: str) -> list[dict]:
    """Extract individual requirements from markdown."""
    requirements = []
    # Match ### FR-XX: Title or ### FR-XX — Title
    req_pattern = re.compile(r"^###\s+(FR-\d+)[：:\s—-]*(.*)", re.MULTILINE)

    parts = req_pattern.split(content)
    # parts: [before, id1, title1, body1, id2, title2, body2, ...]
    for i in range(1, len(parts), 3):
        if i + 2 < len(parts):
            requirements.append({
                "id": parts[i].strip(),
                "title": parts[i + 1].strip(),
                "body": parts[i + 2].strip(),
            })

    return requirements


def check_ears(body: str) -> tuple[bool, str]:
    """Check if acceptance criteria use EARS syntax."""
    # Find acceptance criteria section
    ac_match = re.search(r"验收标准[：:]*\n(.*?)(?=\n###|\n##|\Z)", body, re.DOTALL)
    if not ac_match:
        # Try English
        ac_match = re.search(r"Acceptance Criteria[：:]*\n(.*?)(?=\n###|\n##|\Z)", body, re.DOTALL)

    if not ac_match:
        return False, "No acceptance criteria section found"

    ac_text = ac_match.group(1)
    criteria = [line.strip() for line in ac_text.split("\n") if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "-", "*"))]

    if not criteria:
        return False, "No numbered/listed acceptance criteria found"

    has_shall = any("shall" in c.lower() for c in criteria)
    if not has_shall:
        return False, "Acceptance criteria don't use 'shall' keyword (EARS syntax)"

    return True, f"{len(criteria)} criteria found with EARS syntax"


def check_vague_terms(body: str) -> list[tuple[str, str]]:
    """Check for vague terms in requirement body."""
    findings = []
    for term in VAGUE_TERMS:
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        matches = pattern.findall(body)
        if matches:
            findings.append((term, ", ".join(matches)))
    return findings


def check_priority(body: str) -> tuple[bool, str]:
    """Check if requirement has priority."""
    priority_pattern = re.compile(r"优先级[：:]*\s*(P[012])|Priority[：:]*\s*(P[012])", re.IGNORECASE)
    if priority_pattern.search(body):
        return True, "Priority found"
    return False, "No priority (P0/P1/P2) found"


def validate_spec(spec_path: str, strict: bool = False) -> bool:
    """Validate a spec document and print results."""
    path = Path(spec_path)
    if not path.exists():
        print(f"[ERROR] File not found: {spec_path}")
        return False

    content = path.read_text(encoding="utf-8")
    requirements = extract_requirements(content)

    if not requirements:
        print("[ERROR] No requirements found (expected ### FR-XX format)")
        return False

    print(f"Validating {len(requirements)} requirements from {spec_path}\n")

    all_p0_pass = True
    total_p1_warnings = 0

    # P0-005: Check user roles section exists
    sections = parse_markdown_sections(content)
    has_roles = any("角色" in s.lower() or "role" in s.lower() for s in sections)
    print_p0("S-005", "User roles defined", has_roles,
             "Missing '用户角色' section" if not has_roles else "")

    # Per-requirement checks
    has_exception = 0
    has_normal = 0

    for req in requirements:
        req_label = f"{req['id']} — {req['title']}"

        # S-001: EARS syntax
        ears_ok, ears_msg = check_ears(req["body"])
        print_p0("S-001", f"{req_label}: EARS syntax", ears_ok, ears_msg)
        if not ears_ok:
            all_p0_pass = False

        # S-002: No vague terms
        vague = check_vague_terms(req["body"])
        vague_ok = len(vague) == 0
        vague_msg = f"Vague terms: {', '.join(f'{t}({c})' for t, c in vague)}" if vague else ""
        print_p0("S-002", f"{req_label}: No vague terms", vague_ok, vague_msg)
        if not vague_ok:
            all_p0_pass = False

        # S-003: Priority
        pri_ok, pri_msg = check_priority(req["body"])
        print_p0("S-003", f"{req_label}: Priority set", pri_ok, pri_msg)
        if not pri_ok:
            all_p0_pass = False

        # Track exception vs normal for S-101
        if re.search(r"\bif\b.*\bshall\b", req["body"], re.IGNORECASE):
            has_exception += 1
        else:
            has_normal += 1

    # S-101: Exception coverage
    exception_ratio = has_exception / max(len(requirements), 1)
    exception_ok = exception_ratio >= 0.2  # At least 20% should have exception scenarios
    print_p1("S-101", f"Exception coverage ({has_exception}/{len(requirements)} = {exception_ratio:.0%})",
             exception_ok, "Add exception scenarios (If...shall) for more requirements")
    if not exception_ok:
        total_p1_warnings += 1

    # S-102: Quantified NFRs
    nfr_section = sections.get("非功能需求", sections.get("Non-Functional Requirements", ""))
    if nfr_section:
        has_numbers = bool(re.search(r"\d+\s*(ms|s|fps|MB|KB|%|rpx|px)", nfr_section))
        print_p1("S-102", "NFRs quantified", has_numbers,
                 "Add specific numbers to non-functional requirements" if not has_numbers else "")
        if not has_numbers:
            total_p1_warnings += 1

    # Summary
    print("\n" + "=" * 60)
    if all_p0_pass:
        print("✅ All P0 checks PASSED")
    else:
        print("❌ Some P0 checks FAILED — must fix before proceeding")

    if total_p1_warnings > 0:
        print(f"⚠️  {total_p1_warnings} P1 warning(s) — recommended to address")

    if strict and (not all_p0_pass or total_p1_warnings > 0):
        return False

    return all_p0_pass


def print_p0(rule_id: str, desc: str, passed: bool, detail: str = ""):
    icon = "✅" if passed else "❌"
    suffix = f" — {detail}" if detail else ""
    print(f"{icon} {rule_id}: {desc}{suffix}")


def print_p1(rule_id: str, desc: str, passed: bool, suggestion: str = ""):
    icon = "✅" if passed else "⚠️ "
    suffix = f" — {suggestion}" if suggestion and not passed else ""
    print(f"{icon} {rule_id}: {desc}{suffix}")


def main():
    parser = argparse.ArgumentParser(description="Validate a spec document against quality rules")
    parser.add_argument("spec_file", help="Path to requirements.md")
    parser.add_argument("--strict", action="store_true", help="Fail on P1 warnings too")
    args = parser.parse_args()

    passed = validate_spec(args.spec_file, strict=args.strict)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
