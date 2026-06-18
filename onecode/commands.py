from __future__ import annotations

from typing import TYPE_CHECKING

from tui import platform_commands

if TYPE_CHECKING:
    from tui.widgets.conversation import Conversation


async def _mode(conversation: Conversation, parameters: str) -> None:
    from onecode.config import load_config, save_config

    mode = parameters.strip().lower()
    if mode not in ("build", "plan", "solo"):
        conversation.notify("Mode must be: build, plan, or solo", title="/mode", severity="error")
        return
    cfg = load_config()
    cfg.default_mode = mode
    save_config(cfg)
    conversation.app.settings.set("mode", mode)
    await conversation.set_mode(mode)
    conversation.flash(f"onecode mode set to [b]{mode}")


async def _provider(conversation: Conversation, parameters: str) -> None:
    from onecode.config import load_config, save_config

    provider = parameters.strip()
    if not provider:
        conversation.notify("Provider name required", title="/provider", severity="error")
        return
    cfg = load_config()
    cfg.default_provider = provider
    save_config(cfg)
    conversation.app.settings.set("provider", provider)
    conversation.flash(f"onecode provider set to [b]{provider}")


async def _model(conversation: Conversation, parameters: str) -> None:
    from onecode.config import load_config, save_config

    model = parameters.strip()
    if not model:
        conversation.notify("Model name required", title="/model", severity="error")
        return
    cfg = load_config()
    cfg.default_model = model
    save_config(cfg)
    conversation.app.settings.set("model", model)
    conversation.flash(f"onecode model set to [b]{model}")


async def _skill(conversation: Conversation, parameters: str) -> None:
    from tui.widgets.markdown_note import MarkdownNote
    from onecode.skills.manager import SkillManager
    from onecode.skills.loader import SkillLoader
    from onecode.skills.create import create_skill_scaffold

    parts = parameters.strip().split()
    subcmd = parts[0].lower() if parts else ""
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if subcmd == "list":
        loader = SkillLoader()
        all_skills = loader.get_all()
        if not all_skills:
            await conversation.post(MarkdownNote("**No skills found.**\n\nUse `/skill add <name>` to create a new skill."))
            return

        lines = ["**Available Skills**\n"]
        for name, skill in sorted(all_skills.items()):
            enabled = skill.enabled
            status = "✓" if enabled else "✗"
            lines.append(f"- {status} **{name}**: {skill.description}")
            if skill.path:
                lines.append(f"  - Path: `{skill.path}`")
        await conversation.post(MarkdownNote("\n".join(lines)))

    elif subcmd == "add":
        name = rest.strip()
        if not name:
            conversation.notify("Skill name required", title="/skill add", severity="error")
            return

        mgr = SkillManager()
        if mgr.get(name):
            conversation.notify(f"Skill '{name}' already exists", title="/skill add", severity="error")
            return

        err = create_skill_scaffold(mgr.skills_dir, name, f"A skill for {name}")
        if err:
            conversation.notify(f"Error: {err}", title="/skill add", severity="error")
            return

        await conversation.post(MarkdownNote(
            f"**Skill '{name}' created**\n\n"
            f"Location: `{mgr.skills_dir / name}`\n\n"
            f"Edit the SKILL.md file to add instructions, then use `/skill list` to see it."
        ))

    elif subcmd == "remove":
        name = rest.strip()
        if not name:
            conversation.notify("Skill name required", title="/skill remove", severity="error")
            return

        mgr = SkillManager()
        err = mgr.remove(name)
        if err:
            conversation.notify(f"Error: {err}", title="/skill remove", severity="error")
            return

        await conversation.post(MarkdownNote(f"**Skill '{name}' removed.**"))

    elif subcmd == "enable":
        name = rest.strip()
        if not name:
            conversation.notify("Skill name required", title="/skill enable", severity="error")
            return

        mgr = SkillManager()
        skill_data = mgr.get(name)
        if not skill_data:
            conversation.notify(f"Skill '{name}' not found", title="/skill enable", severity="error")
            return

        mgr.enable(name, True)
        await conversation.post(MarkdownNote(f"**Skill '{name}' enabled.**"))

    elif subcmd == "disable":
        name = rest.strip()
        if not name:
            conversation.notify("Skill name required", title="/skill disable", severity="error")
            return

        mgr = SkillManager()
        skill_data = mgr.get(name)
        if not skill_data:
            conversation.notify(f"Skill '{name}' not found", title="/skill disable", severity="error")
            return

        mgr.enable(name, False)
        await conversation.post(MarkdownNote(f"**Skill '{name}' disabled.**"))

    else:
        await conversation.post(MarkdownNote(
            "**Skill Management**\n\n"
            "Usage:\n"
            "- `/skill list` - List all skills\n"
            "- `/skill add <name>` - Create a new skill\n"
            "- `/skill remove <name>` - Remove a skill\n"
            "- `/skill enable <name>` - Enable a skill\n"
            "- `/skill disable <name>` - Disable a skill"
        ))


async def _mcp(conversation: Conversation, parameters: str) -> None:
    from tui.widgets.markdown_note import MarkdownNote
    from onecode.mcp.manager import MCPManager

    parts = parameters.strip().split()
    subcmd = parts[0].lower() if parts else ""
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if subcmd == "list":
        mgr = MCPManager()
        servers = mgr.list()
        if not servers:
            await conversation.post(MarkdownNote(
                "**No MCP Servers**\n\n"
                "Use `/mcp add <name> <url>` to add an MCP server."
            ))
            return

        lines = ["**Configured MCP Servers**\n"]
        for s in servers:
            name = s.get("name", "unknown")
            transport = s.get("transport", "sse")
            enabled = s.get("enabled", True)
            status = "✓" if enabled else "✗"
            if transport == "sse":
                url = s.get("url", "")
                lines.append(f"- {status} **{name}** (SSE)")
                if url:
                    lines.append(f"  - URL: `{url}`")
            else:
                cmd = s.get("command", "")
                args = " ".join(s.get("args", []))
                lines.append(f"- {status} **{name}** (stdio)")
                if cmd:
                    lines.append(f"  - Command: `{cmd} {args}`")
        await conversation.post(MarkdownNote("\n".join(lines)))

    elif subcmd == "add":
        args_parts = rest.split()
        if len(args_parts) < 2:
            conversation.notify("Usage: /mcp add <name> <url> [--type stdio]", title="/mcp add", severity="error")
            return

        name = args_parts[0]
        url = args_parts[1]
        transport = "sse"

        mgr = MCPManager()
        if mgr.get(name):
            conversation.notify(f"MCP server '{name}' already exists", title="/mcp add", severity="error")
            return

        mgr.add(name, url, transport="sse")
        await conversation.post(MarkdownNote(
            f"**MCP Server '{name}' added**\n\n"
            f"URL: `{url}`\n"
            f"Transport: SSE\n\n"
            f"Use `/mcp list` to see all servers."
        ))

    elif subcmd == "remove":
        name = rest.strip()
        if not name:
            conversation.notify("Server name required", title="/mcp remove", severity="error")
            return

        mgr = MCPManager()
        if not mgr.get(name):
            conversation.notify(f"MCP server '{name}' not found", title="/mcp remove", severity="error")
            return

        mgr.remove(name)
        await conversation.post(MarkdownNote(f"**MCP Server '{name}' removed.**"))

    elif subcmd == "enable":
        name = rest.strip()
        if not name:
            conversation.notify("Server name required", title="/mcp enable", severity="error")
            return

        mgr = MCPManager()
        err = mgr.enable(name, True)
        if err:
            conversation.notify(f"Error: {err}", title="/mcp enable", severity="error")
            return

        await conversation.post(MarkdownNote(f"**MCP Server '{name}' enabled.**"))

    elif subcmd == "disable":
        name = rest.strip()
        if not name:
            conversation.notify("Server name required", title="/mcp disable", severity="error")
            return

        mgr = MCPManager()
        err = mgr.enable(name, False)
        if err:
            conversation.notify(f"Error: {err}", title="/mcp disable", severity="error")
            return

        await conversation.post(MarkdownNote(f"**MCP Server '{name}' disabled.**"))

    else:
        await conversation.post(MarkdownNote(
            "**MCP Server Management**\n\n"
            "Usage:\n"
            "- `/mcp list` - List all MCP servers\n"
            "- `/mcp add <name> <url>` - Add an SSE MCP server\n"
            "- `/mcp remove <name>` - Remove an MCP server\n"
            "- `/mcp enable <name>` - Enable an MCP server\n"
            "- `/mcp disable <name>` - Disable an MCP server"
        ))


def register_commands() -> None:
    platform_commands.register("model", "Set onecode LLM model", _model, "<model name>")
    platform_commands.register("provider", "Set onecode LLM provider", _provider, "<provider name>")
    platform_commands.register("skill", "Manage skills (list, add, remove, enable, disable)", _skill, "list|add|remove [name]")
    platform_commands.register("mcp", "Manage MCP servers (list, add, remove, enable, disable)", _mcp, "list|add|remove [name]")
