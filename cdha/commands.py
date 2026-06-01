from __future__ import annotations

from typing import TYPE_CHECKING

from tui import platform_commands

if TYPE_CHECKING:
    from tui.widgets.conversation import Conversation


async def _harness(conversation: Conversation, parameters: str) -> None:
    from tui.widgets.markdown_note import MarkdownNote
    from cdha.config import load_config

    cfg = load_config()
    info = f"""CDH Harness Info:
Provider: {cfg.default_provider}
Model: {cfg.default_model}
Mode: {cfg.default_mode}
Cloud: {cfg.default_cloud}"""
    await conversation.post(MarkdownNote(info))


async def _spec(conversation: Conversation, parameters: str) -> None:
    from tui.widgets.markdown_note import MarkdownNote
    from cdha.lifecycle.manager import (
        LifecycleManager,
        PHASE_DESCRIPTIONS,
        PIPELINE_ORDER,
    )

    mgr = LifecycleManager()
    lines = ["**CDHA Spec Phase**\n"]
    lines.append(f"Current stage: **{mgr.current.value}**")
    lines.append("")

    for stage in PIPELINE_ORDER:
        status = mgr.stages.get(stage, None)
        icon = {None: "○", "pending": "○", "in_progress": "◉", "completed": "✓", "failed": "✗"}.get(
            status.value if status else None, "○"
        )
        desc = PHASE_DESCRIPTIONS.get(stage, "")
        lines.append(f"{icon} **{stage.value}**: {desc}")

    await conversation.post(MarkdownNote("\n".join(lines)))


async def _mode(conversation: Conversation, parameters: str) -> None:
    from cdha.config import load_config, save_config

    mode = parameters.strip().lower()
    if mode not in ("agent", "plan", "solo"):
        conversation.notify("Mode must be: agent, plan, or solo", title="/cdha:mode", severity="error")
        return
    cfg = load_config()
    cfg.default_mode = mode
    save_config(cfg)
    conversation.app.settings.set("mode", mode)
    conversation.flash(f"CDHA mode set to [b]{mode}")


async def _provider(conversation: Conversation, parameters: str) -> None:
    from cdha.config import load_config, save_config

    provider = parameters.strip()
    if not provider:
        conversation.notify("Provider name required", title="/cdha:provider", severity="error")
        return
    cfg = load_config()
    cfg.default_provider = provider
    save_config(cfg)
    conversation.app.settings.set("provider", provider)
    conversation.flash(f"CDHA provider set to [b]{provider}")


async def _model(conversation: Conversation, parameters: str) -> None:
    from cdha.config import load_config, save_config

    model = parameters.strip()
    if not model:
        conversation.notify("Model name required", title="/cdha:model", severity="error")
        return
    cfg = load_config()
    cfg.default_model = model
    save_config(cfg)
    conversation.app.settings.set("model", model)
    conversation.flash(f"CDHA model set to [b]{model}")


async def _cloud(conversation: Conversation, parameters: str) -> None:
    from cdha.config import load_config, save_config

    cloud = parameters.strip()
    if not cloud:
        conversation.notify("Cloud name required", title="/cdha:cloud", severity="error")
        return
    cfg = load_config()
    cfg.default_cloud = cloud
    save_config(cfg)
    conversation.app.settings.set("cloud", cloud)
    conversation.flash(f"CDHA cloud set to [b]{cloud}")


def register_commands() -> None:
    platform_commands.register("cdha:harness", "Show CDHA harness configuration", _harness)
    platform_commands.register("cdha:spec", "Show CDHA spec pipeline phase info", _spec)
    platform_commands.register("cdha:mode", "Set CDHA mode (agent|plan|solo)", _mode, "<agent|plan|solo>")
    platform_commands.register("cdha:provider", "Set CDHA LLM provider", _provider, "<provider name>")
    platform_commands.register("cdha:model", "Set CDHA LLM model", _model, "<model name>")
    platform_commands.register("cdha:cloud", "Set CDHA cloud platform", _cloud, "<cloud name>")
