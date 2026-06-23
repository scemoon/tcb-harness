import base64
from pathlib import Path

from tui.acp import protocol
from tui.prompt.extract import extract_paths_from_prompt
from tui.prompt.resource import load_resource, ResourceError


CLOUD_SPEC_SKILL_PATH = Path(__file__).resolve().parent.parent.parent / "cloud-spec-skill" / "SKILL.md"


def _get_cloud_spec_content() -> str:
    """Load cloud-spec-skill content."""
    if CLOUD_SPEC_SKILL_PATH.exists():
        return CLOUD_SPEC_SKILL_PATH.read_text(encoding="utf-8")
    return ""


def cloud_spec_skill_loaded() -> bool:
    """Check if cloud-spec-skill SKILL.md exists."""
    return CLOUD_SPEC_SKILL_PATH.exists()


def ensure_cloud_spec_skill_installed() -> str | None:
    """Ensure cloud-spec-skill is accessible to agents.

    Checks if SKILL.md exists in repo and copies it to ~/.cdh/skills/ if needed,
    or updates if the repo version is newer.
    Returns error message if installation fails, None on success.
    """
    from onecode.skills.loader import USER_SKILLS_DIR

    if not CLOUD_SPEC_SKILL_PATH.exists():
        return None

    skill_dest = USER_SKILLS_DIR / "cloud-spec-skill"
    dest_skills_md = skill_dest / "SKILL.md"

    if skill_dest.exists() and dest_skills_md.exists():
        repo_mtime = CLOUD_SPEC_SKILL_PATH.stat().st_mtime
        dest_mtime = dest_skills_md.stat().st_mtime
        if dest_mtime >= repo_mtime:
            return None

    try:
        import shutil

        if skill_dest.exists():
            shutil.rmtree(skill_dest)
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(CLOUD_SPEC_SKILL_PATH.parent, skill_dest)
        return None
    except Exception as e:
        return str(e)


def build(project_path: Path, prompt: str) -> list[protocol.ContentBlock]:
    """Build the prompt structure and extract paths with the @ syntax.

    Args:
        project_path: The project root.
        prompt: The prompt text.

    Returns:
        A list of content blocks.
    """
    prompt_content: list[protocol.ContentBlock] = []

    # Prepend cloud-spec-skill as system guidance
    cloud_spec_content = _get_cloud_spec_content()
    if cloud_spec_content:
        prompt_content.append({
            "type": "text",
            "text": f"[System Guidance - Always follow these development standards]\n\n{cloud_spec_content}\n\n---\n\n"
        })

    prompt_content.append({"type": "text", "text": prompt})
    for path, _, _ in extract_paths_from_prompt(prompt):
        if path.endswith("/"):
            continue
        try:
            resource = load_resource(project_path, Path(path))
        except ResourceError:
            # TODO: How should this be handled?
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
