from __future__ import annotations

from typing import TYPE_CHECKING

from tui import platform_commands

if TYPE_CHECKING:
    from tui.widgets.conversation import Conversation


_KNOWN_PROVIDERS = {
    "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
    "openai": ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "minimax": ["MiniMax-M2.7", "MiniMax-M2.5"],
    "minimaxi": ["MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M3"],
    "glm": ["glm-4-plus", "glm-4-flash"],
    "ollama": [],
}


# ── small helpers ──────────────────────────────────────────────────────


def _load_cfg():
    from onecode.config import load_config
    return load_config()


def _save_cfg(cfg):
    from onecode.config import save_config
    save_config(cfg)


def _post_note(conversation, text):
    from tui.widgets.markdown_note import MarkdownNote
    return conversation.post(MarkdownNote(text))


async def _post(conversation, text):
    await _post_note(conversation, text)


# ── status: one-shot snapshot of every onecode: setting ───────────────


async def _status(conversation: "Conversation", parameters: str) -> None:
    """Render a single capability panel: provider, model, mode, skills, MCP."""
    cfg = _load_cfg()
    from onecode.skills.loader import SkillLoader
    from onecode.mcp.manager import MCPManager

    skills = SkillLoader().get_all()
    enabled_skills = sorted(n for n, s in skills.items() if s.enabled)
    disabled_skills = sorted(n for n, s in skills.items() if not s.enabled)

    servers = MCPManager().list()
    enabled_mcps = sorted(s["name"] for s in servers if s.get("enabled", True))
    disabled_mcps = sorted(s["name"] for s in servers if not s.get("enabled", True))

    lines = [
        "**onecode — current state**\n",
        f"- **provider**: `{cfg.default_provider}`",
        f"- **model**: `{cfg.default_model}`",
        f"- **mode**: `{cfg.default_mode}`  (build | plan | solo)",
        f"- **log level**: `{cfg.log_level}`",
        f"- **skills**: {len(enabled_skills)} enabled, {len(disabled_skills)} disabled",
    ]
    if enabled_skills:
        lines.append(f"  - enabled: {', '.join(f'`{n}`' for n in enabled_skills)}")
    if disabled_skills:
        lines.append(f"  - disabled: {', '.join(f'`{n}`' for n in disabled_skills)}")
    lines.append(f"- **mcp servers**: {len(enabled_mcps)} enabled, {len(disabled_mcps)} disabled")
    if enabled_mcps:
        lines.append(f"  - enabled: {', '.join(f'`{n}`' for n in enabled_mcps)}")
    if disabled_mcps:
        lines.append(f"  - disabled: {', '.join(f'`{n}`' for n in disabled_mcps)}")

    lines += [
        "\n**What can I do here?**",
        "- `/onecode:provider [set <name|n>]` — show / change LLM provider",
        "- `/onecode:model [set <name|n>]` — show / change LLM model",
        "- `/onecode:skill list|enable|disable|add|remove [name]`",
        "- `/onecode:mcp list|enable|disable|add|remove [name|url]`",
        "- `/onecode:help` — show this overview",
    ]
    await _post(conversation, "\n".join(lines))


# ── provider ───────────────────────────────────────────────────────────


async def _provider(conversation: "Conversation", parameters: str) -> None:
    cfg = _load_cfg()
    args = parameters.strip().split()
    sub = args[0].lower() if args else ""

    if sub in ("", "show", "list"):
        registered = sorted(_KNOWN_PROVIDERS.keys())
        lines = [
            "**LLM Provider**\n",
            f"- current: `{cfg.default_provider}`",
            f"- available ({len(registered)}):",
        ]
        for i, name in enumerate(registered, 1):
            marker = " ← active" if name == cfg.default_provider else ""
            models = _KNOWN_PROVIDERS[name]
            model_hint = f"  models: {', '.join(models)}" if models else "  models: (any local)"
            lines.append(f"  `{i}) {name}`{marker}{model_hint}")
        lines += [
            "\n**How to switch**",
            "- `/onecode:provider set <name>` — e.g. `set minimaxi`",
            "- `/onecode:provider set <n>` — by number from the list above",
            "\n*Tip:* the provider change applies to new sessions; the current session keeps the active model until you start a new conversation.",
        ]
        await _post(conversation, "\n".join(lines))
        return

    if sub == "set":
        if len(args) < 2:
            conversation.notify("Usage: /onecode:provider set <name|n>", title="/onecode:provider", severity="error")
            return
        target = args[1].strip()
        registered = sorted(_KNOWN_PROVIDERS.keys())
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(registered):
                target = registered[idx - 1]
        if target not in registered:
            conversation.notify(
                f"Unknown provider '{target}'. Use /onecode:provider to list available ones.",
                title="/onecode:provider",
                severity="error",
            )
            return
        cfg.default_provider = target
        _save_cfg(cfg)
        try:
            conversation.app.settings.set("provider", target)
        except Exception:
            pass
        conversation.flash(f"onecode provider set to [b]{target}")
        await _status(conversation, "")
        return

    await _post(conversation, _HELP_PROVIDER)


_HELP_PROVIDER = (
    "**/onecode:provider** — show / switch the LLM provider\n\n"
    "**Sub-commands**\n"
    "- `(none)` or `show` — list registered providers with current marker\n"
    "- `set <name>` — switch provider (name or list-number)\n\n"
    "**Examples**\n"
    "- `/onecode:provider` — show the picker\n"
    "- `/onecode:provider set minimaxi` — switch by name\n"
    "- `/onecode:provider set 3` — switch by list number"
)


# ── model ──────────────────────────────────────────────────────────────


async def _model(conversation: "Conversation", parameters: str) -> None:
    cfg = _load_cfg()
    args = parameters.strip().split()
    sub = args[0].lower() if args else ""

    provider = cfg.default_provider
    known = _KNOWN_PROVIDERS.get(provider, [])

    if sub in ("", "show", "list"):
        lines = [
            "**LLM Model**\n",
            f"- provider: `{provider}`",
            f"- current:  `{cfg.default_model}`",
        ]
        if known:
            lines.append(f"- known models for `{provider}` ({len(known)}):")
            for i, name in enumerate(known, 1):
                marker = " ← active" if name == cfg.default_model else ""
                lines.append(f"  `{i}) {name}`{marker}")
        else:
            lines.append("- *(no preset list — type any model name)*")
        lines += [
            "\n**How to switch**",
            "- `/onecode:model set <name>` — e.g. `set MiniMax-M2.7`",
            "- `/onecode:model set <n>` — by number from the list above",
            "- `/onecode:model set <any-string>` — for providers without a preset",
            "\n*Tip:* changing the model mid-session does not retroactively update the active request; new turns will use the new model.",
        ]
        await _post(conversation, "\n".join(lines))
        return

    if sub == "set":
        if len(args) < 2:
            conversation.notify("Usage: /onecode:model set <name|n>", title="/onecode:model", severity="error")
            return
        target = args[1].strip()
        if target.isdigit() and known:
            idx = int(target)
            if 1 <= idx <= len(known):
                target = known[idx - 1]
        if not target:
            conversation.notify("Model name required", title="/onecode:model", severity="error")
            return
        cfg.default_model = target
        _save_cfg(cfg)
        try:
            conversation.app.settings.set("model", target)
        except Exception:
            pass
        conversation.flash(f"onecode model set to [b]{target}")
        await _status(conversation, "")
        return

    await _post(conversation, _HELP_MODEL)


_HELP_MODEL = (
    "**/onecode:model** — show / switch the LLM model\n\n"
    "**Sub-commands**\n"
    "- `(none)` or `show` — list known models for the current provider\n"
    "- `set <name>` — switch model (name or list-number)\n\n"
    "**Examples**\n"
    "- `/onecode:model` — show the picker for the current provider\n"
    "- `/onecode:model set MiniMax-M2.7` — switch by name\n"
    "- `/onecode:model set 1` — switch by list number"
)


# ── skill ──────────────────────────────────────────────────────────────


async def _skill(conversation: "Conversation", parameters: str) -> None:
    from onecode.skills.manager import SkillManager
    from onecode.skills.loader import SkillLoader
    from onecode.skills.create import create_skill_scaffold

    parts = parameters.strip().split()
    sub = parts[0].lower() if parts else ""
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if sub in ("", "list", "show"):
        skills = SkillLoader().get_all()
        if not skills:
            await _post(conversation, "**Skills**\n\n_No skills installed._\n\nUse `/onecode:skill add <name>` to scaffold a new one.")
            return
        lines = ["**Skills**\n"]
        names = sorted(skills.keys())
        for i, name in enumerate(names, 1):
            s = skills[name]
            marker = "✓" if s.enabled else "✗"
            desc = s.description or "(no description)"
            lines.append(f"- `{i}) {marker}` **{name}** — {desc}")
        lines += [
            "\n**How to manage**",
            "- `/onecode:skill enable <name|n>` — turn on",
            "- `/onecode:skill disable <name|n>` — turn off",
            "- `/onecode:skill add <name>` — scaffold a new skill",
            "- `/onecode:skill remove <name|n>` — delete a skill",
        ]
        await _post(conversation, "\n".join(lines))
        return

    if sub == "enable" or sub == "disable":
        if not rest.strip():
            conversation.notify(f"Usage: /onecode:skill {sub} <name|n>", title=f"/onecode:skill {sub}", severity="error")
            return
        target = _resolve_indexed_name(conversation, rest.strip(), SkillLoader().get_all(), sub)
        if target is None:
            return
        mgr = SkillManager()
        mgr.enable(target, sub == "enable")
        conversation.flash(f"skill [b]{target}[/b] {sub}d")
        await _skill(conversation, "list")
        return

    if sub == "add":
        name = rest.strip()
        if not name:
            conversation.notify("Usage: /onecode:skill add <name>", title="/onecode:skill add", severity="error")
            return
        mgr = SkillManager()
        if mgr.get(name):
            conversation.notify(f"Skill '{name}' already exists", title="/onecode:skill add", severity="error")
            return
        err = create_skill_scaffold(mgr.skills_dir, name, f"A skill for {name}")
        if err:
            conversation.notify(f"Error: {err}", title="/onecode:skill add", severity="error")
            return
        await _post(
            conversation,
            f"**Skill '{name}' created**\n\n"
            f"- location: `{mgr.skills_dir / name}`\n"
            f"- edit `SKILL.md` to add instructions\n"
            f"- then `/onecode:skill list` to confirm it shows up",
        )
        return

    if sub == "remove":
        if not rest.strip():
            conversation.notify("Usage: /onecode:skill remove <name|n>", title="/onecode:skill remove", severity="error")
            return
        target = _resolve_indexed_name(conversation, rest.strip(), SkillLoader().get_all(), sub)
        if target is None:
            return
        SkillManager().remove(target)
        conversation.flash(f"skill [b]{target}[/b] removed")
        await _skill(conversation, "list")
        return

    await _post(conversation, _HELP_SKILL)


_HELP_SKILL = (
    "**/onecode:skill** — manage installed skills\n\n"
    "**Sub-commands**\n"
    "- `(none)` or `list` — show all skills with status\n"
    "- `enable <name|n>` — turn a skill on\n"
    "- `disable <name|n>` — turn a skill off\n"
    "- `add <name>` — scaffold a new skill\n"
    "- `remove <name|n>` — delete a skill\n\n"
    "**Examples**\n"
    "- `/onecode:skill` — list\n"
    "- `/onecode:skill enable 2` — enable the skill at index 2 from the list\n"
    "- `/onecode:skill add my-skill` — scaffold a new skill named `my-skill`"
)


# ── mcp ────────────────────────────────────────────────────────────────


async def _mcp(conversation: "Conversation", parameters: str) -> None:
    from onecode.mcp.manager import MCPManager

    parts = parameters.strip().split()
    sub = parts[0].lower() if parts else ""
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if sub in ("", "list", "show"):
        servers = MCPManager().list()
        if not servers:
            await _post(
                conversation,
                "**MCP Servers**\n\n_None configured._\n\n"
                "Use `/onecode:mcp add <name> <url>` for an SSE server, or "
                "`/onecode:mcp add <name> --type stdio --command <cmd>` for stdio.",
            )
            return
        lines = ["**MCP Servers**\n"]
        for i, s in enumerate(servers, 1):
            name = s.get("name", "?")
            transport = s.get("transport", "sse")
            enabled = s.get("enabled", True)
            marker = "✓" if enabled else "✗"
            if transport == "sse":
                lines.append(f"- `{i}) {marker}` **{name}** (SSE) — `{s.get('url', '')}`")
            else:
                cmd = s.get("command", "")
                args = " ".join(s.get("args") or [])
                lines.append(f"- `{i}) {marker}` **{name}** (stdio) — `{cmd} {args}`".rstrip())
        lines += [
            "\n**How to manage**",
            "- `/onecode:mcp enable <name|n>`",
            "- `/onecode:mcp disable <name|n>`",
            "- `/onecode:mcp remove <name|n>`",
        ]
        await _post(conversation, "\n".join(lines))
        return

    if sub == "enable" or sub == "disable":
        if not rest.strip():
            conversation.notify(f"Usage: /onecode:mcp {sub} <name|n>", title=f"/onecode:mcp {sub}", severity="error")
            return
        mgr = MCPManager()
        target = _resolve_indexed_name(conversation, rest.strip(), {s["name"]: s for s in mgr.list()}, sub)
        if target is None:
            return
        err = mgr.enable(target, sub == "enable")
        if err:
            conversation.notify(f"Error: {err}", title=f"/onecode:mcp {sub}", severity="error")
            return
        conversation.flash(f"mcp server [b]{target}[/b] {sub}d")
        await _mcp(conversation, "list")
        return

    if sub == "add":
        args_parts = rest.split()
        if len(args_parts) < 2:
            await _post(
                conversation,
                "**/onecode:mcp add** — register a new MCP server\n\n"
                "- **SSE** (default): `/onecode:mcp add <name> <url>`\n"
                "- **stdio**: `/onecode:mcp add <name> --type stdio --command <cmd> --args a,b`",
            )
            return
        name = args_parts[0]
        url = args_parts[1]
        mgr = MCPManager()
        if mgr.get(name):
            conversation.notify(f"MCP server '{name}' already exists", title="/onecode:mcp add", severity="error")
            return
        mgr.add(name, url, transport="sse")
        await _post(
            conversation,
            f"**MCP Server '{name}' added**\n\n- transport: SSE\n- URL: `{url}`\n\nUse `/onecode:mcp list` to confirm.",
        )
        return

    if sub == "remove":
        if not rest.strip():
            conversation.notify("Usage: /onecode:mcp remove <name|n>", title="/onecode:mcp remove", severity="error")
            return
        mgr = MCPManager()
        target = _resolve_indexed_name(conversation, rest.strip(), {s["name"]: s for s in mgr.list()}, sub)
        if target is None:
            return
        mgr.remove(target)
        conversation.flash(f"mcp server [b]{target}[/b] removed")
        await _mcp(conversation, "list")
        return

    await _post(conversation, _HELP_MCP)


_HELP_MCP = (
    "**/onecode:mcp** — manage MCP (Model Context Protocol) servers\n\n"
    "**Sub-commands**\n"
    "- `(none)` or `list` — show configured servers\n"
    "- `add <name> <url>` — add an SSE server\n"
    "- `enable <name|n>` / `disable <name|n>`\n"
    "- `remove <name|n>`\n\n"
    "**Examples**\n"
    "- `/onecode:mcp` — list servers\n"
    "- `/onecode:mcp add my-server https://example.com/mcp`\n"
    "- `/onecode:mcp disable 1` — disable the first server in the list"
)


# ── helpers ────────────────────────────────────────────────────────────


def _resolve_indexed_name(conversation, raw, items, sub_label):
    """Accept either a literal name or a 1-based index from the most recent list.

    ``items`` is either a ``dict[name, ...]`` (skills) or already indexed
    by name (MCP). Returns the resolved name or ``None`` after notifying
    the user on error.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    keys = list(items.keys())
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(keys):
            return keys[idx - 1]
        conversation.notify(
            f"Index {idx} out of range (1..{len(keys)}). Run `/onecode:{sub_label}` first to see numbers.",
            title=f"/onecode:{sub_label}",
            severity="error",
        )
        return None
    if raw in items:
        return raw
    conversation.notify(
        f"Unknown name '{raw}'. Run `/onecode:{sub_label}` first to see available names.",
        title=f"/onecode:{sub_label}",
        severity="error",
    )
    return None


# ── clear-todos ──────────────────────────────────────────────────────────


async def _clear_todos(conversation: "Conversation", parameters: str) -> None:
    """Clear all todos via the agent's session/clear_todos RPC."""
    agent = conversation.agent
    if agent is None:
        conversation.notify("No active agent session", title="/clear-todos", severity="error")
        return
    if not hasattr(agent, "acp_session_clear_todos"):
        conversation.notify("Agent does not support clear-todos", title="/clear-todos", severity="error")
        return
    try:
        result = await agent.acp_session_clear_todos()
        if result and result.get("cleared"):
            conversation.notify("All todos cleared", title="/clear-todos")
        else:
            conversation.notify("Failed to clear todos", title="/clear-todos", severity="error")
    except Exception as e:
        conversation.notify(f"Failed to clear todos: {e}", title="/clear-todos", severity="error")


# ── registration ──────────────────────────────────────────────────────


def register_commands() -> None:
    """Register the slash commands exposed to the TUI prompt.

    The help text intentionally covers both **what** the command does and
    **how** to invoke it (sub-command + index syntax), so the
    autocomplete panel is self-documenting.
    """
    platform_commands.register(
        "help",
        "Show onecode: command overview and current state",
        _status,
        "(no args)",
    )
    platform_commands.register(
        "status",
        "Show current provider, model, mode, skills, and MCP servers",
        _status,
        "(no args)",
    )
    platform_commands.register(
        "provider",
        "Show / switch the LLM provider (current + numbered list)",
        _provider,
        "[set <name|n>]",
    )
    platform_commands.register(
        "model",
        "Show / switch the LLM model for the current provider",
        _model,
        "[set <name|n>]",
    )
    platform_commands.register(
        "skill",
        "Manage skills: list, enable, disable, add, remove (accepts name or list number)",
        _skill,
        "list|enable|disable|add|remove [name|n]",
    )
    platform_commands.register(
        "mcp",
        "Manage MCP servers: list, add, enable, disable, remove (accepts name or list number)",
        _mcp,
        "list|add|enable|disable|remove [name|n]",
    )
    platform_commands.register(
        "clear-todos",
        "Clear all plan todos — starts a fresh blank plan",
        _clear_todos,
        "(no args)",
    )