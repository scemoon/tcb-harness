from __future__ import annotations

from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import ToolSpec
from onecode.skills.loader import SkillLoader
from onecode.skills.argument_substitution import substitute_arguments


class SkillTool:
    """Run a SKILL.md skill (Clawd-Code pattern)."""

    def __init__(self, loader: SkillLoader):
        self._loader = loader

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Skill",
            description="Run a registered skill by name with optional arguments. Skills are markdown-based instruction sets with YAML frontmatter.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name to run"},
                    "arguments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional positional arguments ($0, $1, $path, $ARGUMENTS)",
                    },
                },
                "required": ["name"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        name = tool_input.get("name", "")
        args = tool_input.get("arguments") or []
        skill = self._loader.get(name)
        if not skill:
            return ToolResult(
                name="Skill",
                output={"error": f"skill '{name}' not found"},
                is_error=True,
            )
        content = skill.content
        if args:
            content = substitute_arguments(content, args)
        return ToolResult(
            name="Skill",
            output={"name": name, "content": content, "description": skill.description},
        )

