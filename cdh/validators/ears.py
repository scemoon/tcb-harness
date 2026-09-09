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

# ── MUSUBI axiom patterns ──

# 1. Atomicity: detect "and" / "or" in the condition clause of event/state/unwanted/optional forms.
#    Captures the trigger clause between the keyword and the SHALL.
_ATOMIC_EVENT_RE = re.compile(
    r"\bWhen\s+(?P<trigger>.+?),\s+(?:the\s+)?\w+\s+SHALL", re.IGNORECASE
)
_ATOMIC_STATE_RE = re.compile(
    r"\bWhile\s+(?P<trigger>.+?),\s+(?:the\s+)?\w+\s+SHALL", re.IGNORECASE
)
_ATOMIC_UNWANTED_RE = re.compile(
    r"\bIf\s+(?P<trigger>.+?),\s+(?:the\s+)?\w+\s+SHALL", re.IGNORECASE
)
_ATOMIC_OPTIONAL_RE = re.compile(
    r"\bWhere\s+(?P<trigger>.+?),\s+(?:the\s+)?\w+\s+SHALL", re.IGNORECASE
)
_ATOMIC_CONJUNCTION_RE = re.compile(
    r"\s+(?:and|or)\s+", re.IGNORECASE
)

# 2. Observability: unverifiable internal-only verbs.
_OBSERVABILITY_VERBS = ["think about", "know that", "intend to", "believe", "feel", "understand that"]
_OBSERVABILITY_RE = re.compile(
    r"\bthe\s+system\s+SHALL\s+(?:" + "|".join(_OBSERVABILITY_VERBS) + r")\b",
    re.IGNORECASE,
)

# 3. Modal clarity: SHALL mixed with weaker modality.
_MODAL_CLARITY_PATTERNS = [
    (r"\bthe\s+system\s+SHALL\s+try\s+to\b", "try to"),
    (r"\bthe\s+system\s+SHALL\s+attempt\s+to\b", "attempt to"),
    (r"\bthe\s+system\s+SHALL\s+be\s+able\s+to\b", "be able to"),
    (r"\bthe\s+system\s+SHOULD\s+ensure\b", "SHOULD ensure"),
    (r"\bSHALL\s+(?:try|attempt|strive)\b", "weaker verb after SHALL"),
]

# 4. Quantifier: ubiquitous "the system SHALL <verb>" without explicit scope.
#    Catches bare action verbs without "all/each/every/for" quantifier or clear object.
_QUANTIFIER_BARE_VERBS = [
    "respond",
    "validate",
    "process",
    "handle",
    "manage",
    "support",
    "provide",
    "perform",
    "execute",
    "send",
    "receive",
]
_QUANTIFIER_BARE_RE = re.compile(
    r"\bthe\s+system\s+SHALL\s+(" + "|".join(_QUANTIFIER_BARE_VERBS) + r")\b(?!\s+(?:all|each|every|for|to|from|with|that|which|when|where|if))",
    re.IGNORECASE,
)

# 5. Negative capability: bare "SHALL NOT" is non-EARS — use "If <unwanted>, the system SHALL ...".
_SHALL_NOT_RE = re.compile(r"\bSHALL\s+NOT\b", re.IGNORECASE)


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


def _check_atomicity(body_lines: list[str], path: Path) -> list[dict]:
    """MUSUBI axiom: detect compound conditions using and/or in EARS triggers."""
    checks: list[dict] = []
    flagged = False
    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for label, regex in (
            ("event-driven", _ATOMIC_EVENT_RE),
            ("state-driven", _ATOMIC_STATE_RE),
            ("unwanted", _ATOMIC_UNWANTED_RE),
            ("optional", _ATOMIC_OPTIONAL_RE),
        ):
            m = regex.search(stripped)
            if not m:
                continue
            trigger = m.group("trigger")
            # Only flag when the conjunction is inside the trigger clause, not the
            # response clause (we already split on the first comma before SHALL).
            if _ATOMIC_CONJUNCTION_RE.search(trigger):
                flagged = True
                conjunction = re.search(_ATOMIC_CONJUNCTION_RE, trigger).group(0).strip()
                checks.append({
                    "name": "ears-axiom-atomicity",
                    "status": "warn",
                    "message": (
                        f"Line {i}: non-atomic {label} condition — '{conjunction}' joins multiple "
                        f"triggers in \"{stripped[:100]}\". Split into separate FRs."
                    ),
                    "file": str(path),
                    "line": i,
                })
    if not flagged:
        checks.append({
            "name": "ears-axiom-atomicity",
            "status": "pass",
            "message": "All EARS triggers are atomic (no 'and'/'or' in condition clauses)",
            "file": str(path),
        })
    return checks


def _check_observability(body_lines: list[str], path: Path) -> list[dict]:
    """MUSUBI axiom: detect unverifiable internal-state verbs."""
    checks: list[dict] = []
    flagged = False
    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _OBSERVABILITY_RE.search(stripped)
        if m:
            flagged = True
            verb = m.group(0).split("SHALL", 1)[1].strip()
            checks.append({
                "name": "ears-axiom-observability",
                "status": "warn",
                "message": (
                    f"Line {i}: unverifiable requirement — 'SHALL {verb}' is an internal state "
                    f"that cannot be empirically tested. Rephrase as an externally observable action "
                    f"in: \"{stripped[:100]}\""
                ),
                "file": str(path),
                "line": i,
            })
    if not flagged:
        checks.append({
            "name": "ears-axiom-observability",
            "status": "pass",
            "message": "All SHALL statements describe externally observable behaviour",
            "file": str(path),
        })
    return checks


def _check_modal_clarity(body_lines: list[str], path: Path) -> list[dict]:
    """MUSUBI axiom: detect SHALL combined with weaker modality."""
    checks: list[dict] = []
    flagged = False
    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pattern, label in _MODAL_CLARITY_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                flagged = True
                checks.append({
                    "name": "ears-axiom-modal-clarity",
                    "status": "warn",
                    "message": (
                        f"Line {i}: ambiguous modality — '{label}' mixed with SHALL in: "
                        f"\"{stripped[:100]}\". Use SHALL alone or replace with a weaker keyword "
                        f"throughout."
                    ),
                    "file": str(path),
                    "line": i,
                })
    if not flagged:
        checks.append({
            "name": "ears-axiom-modal-clarity",
            "status": "pass",
            "message": "No SHALL/weaker-modality mixing detected",
            "file": str(path),
        })
    return checks


def _check_quantifier(body_lines: list[str], path: Path) -> list[dict]:
    """MUSUBI axiom: detect ubiquitous SHALL statements missing scope/quantifier."""
    checks: list[dict] = []
    flagged = False
    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Only apply to ubiquitous form ("the system SHALL <bare-verb>") so we
        # don't flag condition-bearing forms (event/state/unwanted/optional)
        # which already imply scope via their trigger.
        if not re.match(r"^\s*the\s+system\s+SHALL\b", stripped, re.IGNORECASE):
            continue
        if _QUANTIFIER_BARE_RE.search(stripped):
            flagged = True
            verb_match = re.search(
                r"\bthe\s+system\s+SHALL\s+(\w+)", stripped, re.IGNORECASE
            )
            verb = verb_match.group(1) if verb_match else "<verb>"
            checks.append({
                "name": "ears-axiom-quantifier",
                "status": "warn",
                "message": (
                    f"Line {i}: missing quantifier/scope — 'SHALL {verb}' does not specify "
                    f"what/who/each/all. Add explicit scope (e.g. 'SHALL {verb} each <object>') "
                    f"in: \"{stripped[:100]}\""
                ),
                "file": str(path),
                "line": i,
            })
    if not flagged:
        checks.append({
            "name": "ears-axiom-quantifier",
            "status": "pass",
            "message": "Ubiquitous SHALL statements declare explicit scope",
            "file": str(path),
        })
    return checks


def _check_negative_capability(body_lines: list[str], path: Path) -> list[dict]:
    """MUSUBI axiom: detect bare 'SHALL NOT' (non-EARS)."""
    checks: list[dict] = []
    flagged = False
    for i, line in enumerate(body_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _SHALL_NOT_RE.search(stripped):
            # EARS allows "If <unwanted>, the system SHALL <response>" — only
            # flag when the line does not also contain that wanted-shape.
            has_unwanted_shape = re.search(
                r"\bIf\s+.+,\s+(?:the\s+)?\w+\s+SHALL\b", stripped, re.IGNORECASE
            )
            if not has_unwanted_shape:
                flagged = True
                checks.append({
                    "name": "ears-axiom-negative-capability",
                    "status": "warn",
                    "message": (
                        f"Line {i}: bare 'SHALL NOT' is non-EARS — rephrase as "
                        f"'If <unwanted condition>, the system SHALL <response>' in: "
                        f"\"{stripped[:100]}\""
                    ),
                    "file": str(path),
                    "line": i,
                })
    if not flagged:
        checks.append({
            "name": "ears-axiom-negative-capability",
            "status": "pass",
            "message": "Negatives expressed via EARS unwanted-form (no bare SHALL NOT)",
            "file": str(path),
        })
    return checks


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

    # ── MUSUBI axiom checks (warn-level) ──
    checks.extend(_check_atomicity(body_lines, path))
    checks.extend(_check_observability(body_lines, path))
    checks.extend(_check_modal_clarity(body_lines, path))
    checks.extend(_check_quantifier(body_lines, path))
    checks.extend(_check_negative_capability(body_lines, path))

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