import re
from pathlib import Path

_EARS_PATTERNS = [
    ("ubiquitous", r"the\s+system\s+SHALL"),
    ("event-driven", r"When\s+.+,\s+(the\s+)?\w+\s+SHALL"),
    ("state-driven", r"While\s+.+,\s+(the\s+)?\w+\s+SHALL"),
    ("unwanted", r"If\s+.+,\s+(the\s+)?\w+\s+SHALL"),
    ("optional", r"Where\s+.+,\s+(the\s+)?\w+\s+SHALL"),
]

_FR_ID_RE = re.compile(r"(\b[A-Z]{2,8}-FR-\d{3}\b)")

_AMBIGUOUS_WORDS = ["should", "may", "might", "could", "would", "perhaps", "maybe"]

_SHALL_RE = re.compile(r"\bSHALL\b", re.IGNORECASE)
_AMBIGUOUS_RE = re.compile(
    r"\b(" + "|".join(_AMBIGUOUS_WORDS) + r")\b", re.IGNORECASE
)


def _parse_yaml_frontmatter(text: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from markdown. Returns (parsed_dict, body_text)."""
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end == -1:
        return None, text
    fm_text = text[3:end].strip()
    body = text[end + 3:].lstrip("\n")
    fm: dict = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body


def _find_spec_deltas(root: Path) -> list[Path]:
    changes_dir = root / "aidlc" / "openspec" / "changes"
    if not changes_dir.exists():
        return []
    return sorted(changes_dir.rglob("spec-delta.md"))


def _check_file(path: Path) -> list[dict]:
    checks = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [{"name": "read-error", "status": "fail", "message": str(e), "file": str(path)}]

    lines = text.split("\n")
    seen_shall = False
    seen_pattern = set()
    ambiguous_lines = []
    fr_ids = []

    fm, body_text = _parse_yaml_frontmatter(text)
    body_lines = body_text.split("\n")

    # ── Frontmatter validation ──
    if fm is not None:
        fid = fm.get("id", "")
        if _FR_ID_RE.match(fid):
            fr_ids.append(fid)
            checks.append({
                "name": "ears-frontmatter-id",
                "status": "pass",
                "message": f"Frontmatter declares FR id: {fid}",
                "file": str(path),
            })
        else:
            checks.append({
                "name": "ears-frontmatter-id",
                "status": "warn",
                "message": f"Frontmatter id '{fid}' does not match FR id pattern (e.g. WEB-FR-001)" if fid else "No 'id' field in frontmatter",
                "file": str(path),
            })
        for req_field in ["title", "status"]:
            if req_field not in fm:
                checks.append({
                    "name": "ears-frontmatter-field",
                    "status": "warn",
                    "message": f"Missing frontmatter field: '{req_field}'",
                    "file": str(path),
                })
        if fm.get("status") not in ("draft", "review", "approved", "implemented"):
            checks.append({
                "name": "ears-frontmatter-status",
                "status": "warn",
                "message": f"Frontmatter status '{fm.get('status', '')}' should be one of: draft, review, approved, implemented",
                "file": str(path),
            })
    else:
        checks.append({
            "name": "ears-frontmatter",
            "status": "warn",
            "message": "No YAML frontmatter found — FR metadata should be declared at the top of the spec-delta",
            "file": str(path),
        })

    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _FR_ID_RE.search(stripped)
        if match:
            fr_ids.append(match.group(1))

        if _SHALL_RE.search(stripped):
            seen_shall = True

        for pname, p_re in _EARS_PATTERNS:
            if re.search(p_re, stripped, re.IGNORECASE):
                seen_pattern.add(pname)

        if _AMBIGUOUS_RE.search(stripped):
            for w in _AMBIGUOUS_WORDS:
                if re.search(rf"\b{w}\b", stripped, re.IGNORECASE):
                    ambiguous_lines.append((i, w, stripped[:80]))

    if not fm and not seen_shall:
        checks.append({
            "name": "ears-shall-keyword",
            "status": "fail",
            "message": "No requirement uses SHALL keyword — EARS requires SHALL for all functional requirements",
            "file": str(path),
        })
    elif seen_shall:
        checks.append({
            "name": "ears-shall-keyword",
            "status": "pass",
            "message": "SHALL keyword found in spec delta",
            "file": str(path),
        })

    if not seen_pattern:
        if fm:
            checks.append({
                "name": "ears-pattern",
                "status": "warn",
                "message": "No recognized EARS pattern (ubiquitous/event-driven/state-driven/unwanted/optional) detected in body",
                "file": str(path),
            })
    else:
        checks.append({
            "name": "ears-pattern",
            "status": "pass",
            "message": f"Detected EARS patterns: {', '.join(sorted(seen_pattern))}",
            "file": str(path),
        })

    # ── FR ID cross-reference check ──
    if len(fr_ids) >= 2:
        checks.append({
            "name": "ears-fr-reference",
            "status": "pass",
            "message": f"Cross-references FRs: {', '.join(sorted(set(fr_ids)))}",
            "file": str(path),
        })

    if ambiguous_lines:
        for line_no, word, snippet in ambiguous_lines:
            checks.append({
                "name": "ears-ambiguous-word",
                "status": "warn",
                "message": f"Line {line_no}: ambiguous word '{word}' in: \"{snippet}\"",
                "file": str(path),
                "line": line_no,
            })
    else:
        checks.append({
            "name": "ears-ambiguous-word",
            "status": "pass",
            "message": "No ambiguous terms found",
        })

    return checks


def run_ears_check(root: Path) -> dict:
    spec_deltas = _find_spec_deltas(root)
    if not spec_deltas:
        return {
            "passed": False,
            "checks": [{
                "name": "ears-spec-found",
                "status": "fail",
                "message": "No spec-delta.md found under aidlc/openspec/changes/",
            }],
        }

    all_checks = []
    for sd in spec_deltas:
        all_checks.extend(_check_file(sd))

    passed = all(c["status"] == "pass" for c in all_checks)
    return {"passed": passed, "checks": all_checks}
