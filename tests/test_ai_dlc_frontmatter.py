import re
from pathlib import Path

import pytest
import yaml

SKILL_DIR = Path(__file__).resolve().parents[1] / "ai-dlc-skill"
SKILL_MD = SKILL_DIR / "SKILL.md"

REQUIRED = {
    "name", "description", "triggers", "phases",
    "allowed_tools", "compatibility", "license",
}

REPO_ROOT = SKILL_DIR.parent
SYMLINK_TARGETS = {
    SKILL_DIR / ".claude" / "skills" / "ai-dlc-skill",
    SKILL_DIR / ".agents" / "skills" / "ai-dlc-skill",
}


def test_frontmatter_present():
    text = SKILL_MD.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert m, "SKILL.md is missing YAML frontmatter at the top"
    fm = yaml.safe_load(m.group(1))

    missing = REQUIRED - fm.keys()
    assert not missing, f"frontmatter missing fields: {missing}"

    assert fm["name"] == "ai-dlc-skill"
    assert "Understand" in fm["description"]
    assert set(fm["phases"]) == {"understand", "plan", "verify", "deliver", "brownfield"}

    for trigger in ("ai-dlc", "lifecycle", "BDD", "INT-FR"):
        assert trigger in fm["triggers"], \
            f"expected trigger {trigger!r} not found in frontmatter"

    compat = fm["compatibility"]
    for key in ("cdh", "opencode", "claude-code", "openai-codex"):
        assert key in compat, \
            f"compatibility entry {key!r} missing"


@pytest.mark.parametrize("link", sorted(SYMLINK_TARGETS))
def test_symlink_broadcasts(link):
    assert link.is_symlink(), f"{link} is not a symlink"
    assert link.resolve() == SKILL_DIR.resolve(), \
        f"{link} does not point to {SKILL_DIR}"
