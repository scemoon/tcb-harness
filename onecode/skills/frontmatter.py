from __future__ import annotations

import re
from typing import Any

import yaml


_FRONTMATTER_RE = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n?',
    re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown text.

    Returns (frontmatter_dict, body_text). If no frontmatter,
    frontmatter_dict is empty and body_text is the full text.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    yaml_block = match.group(1)
    body = text[match.end():]

    try:
        frontmatter = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, body
