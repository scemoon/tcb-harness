from pathlib import Path

from cdh.models.provider import Message


WORKSPACE = Path(__file__).parent.parent.parent.parent
SKILLS_DIR = WORKSPACE / "skills"


def get_all_skills() -> dict[str, dict]:
    skills = {}
    for d in SKILLS_DIR.iterdir():
        if d.is_dir():
            skill_yaml = d / "skill.yaml"
            if skill_yaml.exists():
                import yaml
                try:
                    data = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
                    data["name"] = data.get("name", d.name)
                    data["enabled"] = data.get("enabled", True)
                    data["path"] = d
                    skills[data["name"]] = data
                except Exception:
                    pass
    return skills


def get_skill_content(name: str) -> str:
    skill = get_all_skills().get(name)
    if not skill or not skill.get("enabled"):
        return ""
    skill_path = skill.get("path")
    if not skill_path:
        return ""
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        return skill_md.read_text(encoding="utf-8")
    return ""


def load_all_enabled_skills() -> list[tuple[str, str]]:
    loaded = []
    for name, skill in get_all_skills().items():
        if skill.get("enabled"):
            content = get_skill_content(name)
            if content:
                loaded.append((name, content))
    return loaded