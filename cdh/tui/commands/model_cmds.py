from __future__ import annotations

from cdh.models.registry import ModelRegistry
from cdh.tui.commands.registry import command


@command("model list", "List all available models grouped by provider")
def cmd_model_list(app, *args):
    from cdh.models.provider import ProviderRegistry
    providers = ProviderRegistry.list()
    current_model = app.current_model
    items = []
    for p in sorted(providers):
        models = ModelRegistry.list_by_provider(p)
        if not models:
            continue
        for m in models:
            active = "[active] " if m.id == current_model else ""
            caps = ", ".join(m.capabilities[:2]) if m.capabilities else ""
            ctx = f"{m.context_window:,}"
            items.append((f"{active}{p:>10} | {m.id:<28} ctx:{ctx:>8}  {caps}", m.id))
    app.show_config_panel("Models", items, "model switch ", execute=True)
    return ""


@command("model switch", "Switch active model")
def cmd_model_switch(app, *args):
    if not args:
        from cdh.models.provider import ProviderRegistry
        providers = ProviderRegistry.list()
        items = []
        for p in sorted(providers):
            models = ModelRegistry.list_by_provider(p)
            for m in models:
                items.append((f"{p:<10} | {m.id:<28}", m.id))
        app.show_config_panel("Select Model", items, "model switch ", execute=True)
        return ""
    model_id = args[0]
    info = ModelRegistry.get(model_id)
    if not info:
        return f"Unknown model: {model_id}. Use /model list to see available models."
    app.current_model = model_id
    app.current_provider = info.provider
    return f"Switched to {model_id} ({info.provider})"


@command("model show", "Show current model info")
def cmd_model_show(app, *args):
    info = ModelRegistry.get(app.current_model)
    if info:
        text = (
            f"Model:        {app.current_model}\n"
            f"Provider:     {app.current_provider}\n"
            f"Context:      {info.context_window:,} tokens\n"
            f"Max output:   {info.max_output:,} tokens\n"
            f"Input cost:   ${info.cost_per_1k_input:.5f}/1k\n"
            f"Output cost:  ${info.cost_per_1k_output:.5f}/1k\n"
            f"Capabilities: {', '.join(info.capabilities)}"
        )
        app.show_config_info("Model Info", text)
        return ""
    return f"Current model: {app.current_model}"


@command("model temperature", "Set or show temperature")
def cmd_model_temperature(app, *args):
    text = f"Temperature setting (placeholder).\nCurrent model: {app.current_model}"
    app.show_config_info("Temperature", text)
    return ""


@command("model auto", "Auto-select model by complexity")
def cmd_model_auto(app, *args):
    m = app.config.model_auto
    text = (
        f"Auto model selection:\n"
        f"  Simple tasks:   {m.simple_tasks}\n"
        f"  Medium tasks:   {m.medium_tasks}\n"
        f"  Complex tasks:  {m.complex_tasks}"
    )
    app.show_config_info("Model Auto", text)
    return ""
