import base64
import re
from pathlib import Path

from tui.acp import protocol
from tui.prompt.extract import extract_paths_from_prompt
from tui.prompt.resource import load_resource, ResourceError


CDH_SKILL_MARKER_RE = re.compile(r"<!--\s*CDH_SKILL\s+(\S+)\s*-->")


def _load_from_cdh_marker(project_path: Path) -> str:
    """If AGENTS.md contains ``<!-- CDH_SKILL <path> -->``, load that file."""
    agents_md = project_path / "AGENTS.md"
    if not agents_md.exists():
        return ""
    try:
        text = agents_md.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = CDH_SKILL_MARKER_RE.search(text)
    if not m:
        return ""
    skill_path = Path(m.group(1)).expanduser()
    if not skill_path.exists():
        return ""
    try:
        return skill_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def build(project_path: Path, prompt: str) -> list[protocol.ContentBlock]:
    """Build the prompt structure and extract paths with the @ syntax.

    Args:
        project_path: The project root.
        prompt: The prompt text.

    Returns:
        A list of content blocks.
    """
    prompt_content: list[protocol.ContentBlock] = []

    skill_content = _load_from_cdh_marker(project_path)
    if skill_content:
        prompt_content.append({
            "type": "text",
            "text": f"[Development Standards - AI-DLC]\n\n{skill_content}\n\n---\n\n"
        })

    prompt_content.append({"type": "text", "text": prompt})
    for path, _, _ in extract_paths_from_prompt(prompt):
        if path.endswith("/"):
            continue
        try:
            resource = load_resource(project_path, Path(path))
        except ResourceError:
            continue
        uri = f"file://{resource.path.absolute().resolve()}"
        if resource.text is not None:
            prompt_content.append(
                {
                    "type": "resource",
                    "resource": {
                        "uri": uri,
                        "text": resource.text,
                        "mimeType": resource.mime_type,
                    },
                }
            )
        elif resource.data is not None:
            prompt_content.append(
                {
                    "type": "resource",
                    "resource": {
                        "uri": uri,
                        "blob": base64.b64encode(resource.data).decode("utf-8"),
                        "mimeType": resource.mime_type,
                    },
                }
            )

    return prompt_content
