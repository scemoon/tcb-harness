from __future__ import annotations

from cdh.skill.manager import SkillManager
from cdh.mcp.manager import MCPManager
from cdh.tui.commands.registry import command


@command("skill list", "List installed skills")
def cmd_skill_list(app, *args):
    mgr = SkillManager()
    skills = mgr.list()
    if not skills:
        return "No skills installed. Use /skill install <path>"
    items = []
    for s in skills:
        name = s.get('name', '?')
        enabled = "on" if s.get('enabled', True) else "off"
        items.append((f"{name:<24}  enabled: {enabled}", name))
    app.show_config_panel("Skills", items, "skill toggle ", execute=True)
    return ""


@command("skill toggle", "Toggle a skill on/off")
def cmd_skill_toggle(app, *args):
    if not args:
        return "Usage: /skill toggle <name>"
    mgr = SkillManager()
    skills = mgr.list()
    name = args[0]
    for s in skills:
        if s.get('name') == name:
            current = s.get('enabled', True)
            mgr.enable(name, not current)
            state = "enabled" if not current else "disabled"
            return f"Skill '{name}' {state}."
    return f"Skill not found: {name}"


@command("skill install", "Install a skill from path")
def cmd_skill_install(app, *args):
    if not args:
        return "Usage: /skill install <path>"
    from pathlib import Path
    mgr = SkillManager()
    err = mgr.install(Path(args[0]))
    return f"Skill installed from {args[0]}" if not err else f"Error: {err}"


@command("mcp list", "List MCP connections")
def cmd_mcp_list(app, *args):
    mgr = MCPManager()
    mcps = mgr.list()
    if not mcps:
        return "No MCP connections configured."
    items = []
    for m in mcps:
        name = m.get('name', '?')
        url = m.get('url', '')[:30]
        transport = m.get('transport', 'stdio')
        items.append((f"{name:<20} {url:<32} [{transport}]", name))
    app.show_config_panel("MCP Connections", items, "mcp connect ", execute=True)
    return ""


@command("mcp connect", "Connect to an MCP server")
def cmd_mcp_connect(app, *args):
    if not args:
        return "Usage: /mcp connect <name>"
    mgr = MCPManager()
    mcps = mgr.list()
    name = args[0]
    for m in mcps:
        if m.get('name') == name:
            mgr.connect(name)
            return f"Connected to MCP server: {name}"
    return f"MCP server not found: {name}"


@command("mcp add", "Add MCP connection")
def cmd_mcp_add(app, *args):
    if len(args) < 2:
        return "Usage: /mcp add <name> <url|command>"
    mgr = MCPManager()
    mgr.add(args[0], args[1])
    return f"MCP connection added: {args[0]}"


@command("provider list", "List available providers")
def cmd_provider_list(app, *args):
    from cdh.models.provider import ProviderRegistry
    from cdh.models.registry import ModelRegistry
    providers = ProviderRegistry.list()
    current = app.current_provider
    items = []
    for p in sorted(providers):
        models = ModelRegistry.list_by_provider(p)
        model_names = ", ".join(m.id for m in models)
        active = "[active] " if p == current else ""
        items.append((f"{active}{p:<14} models: {model_names}", p))
    app.show_config_panel("Providers", items, "provider switch ", execute=True)
    return ""


@command("provider switch", "Switch active provider")
def cmd_provider_switch(app, *args):
    if not args:
        return cmd_provider_list(app)
    from cdh.models.provider import ProviderRegistry
    providers = ProviderRegistry.list()
    if args[0] not in providers:
        return f"Unknown provider: {args[0]}. Available: {', '.join(providers)}"
    app.current_provider = args[0]
    return f"Switched to provider: {args[0]}"


@command("provider config show", "Show full config for a provider")
def cmd_provider_config_show(app, *args):
    if not args:
        return "Usage: /provider config show <provider_name>"
    name = args[0]
    cfg = app.config.providers.get(name)
    if not cfg:
        from cdh.models.provider import ProviderRegistry
        available = ", ".join(ProviderRegistry.list())
        return f"No config for provider: {name}. Available: {available}"
    key = cfg.api_key or "(not set)"
    if key and key != "(not set)":
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    else:
        masked = key
    return (
        f"Provider: {name}\n"
        f"  API Key: {masked}\n"
        f"  Endpoint: {cfg.endpoint or 'default'}\n"
        f"  Models: {', '.join(cfg.models) if cfg.models else 'use registry'}"
    )


@command("provider config apikey", "Show or set API key for a provider")
def cmd_provider_config_apikey(app, *args):
    if not args:
        return "Usage: /provider config apikey <provider_name> [api_key]"
    name = args[0]
    if len(args) >= 2:
        key = args[1]
        cfg = app.config.providers.get(name)
        if cfg is None:
            from cdh.config import ProviderConfig
            cfg = ProviderConfig()
            app.config.providers[name] = cfg
        cfg.api_key = key
        from cdh.config import save_config
        save_config(app.config)
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return f"API key for {name} set to: {masked}"
    else:
        cfg = app.config.providers.get(name)
        if not cfg or not cfg.api_key:
            return f"No API key configured for {name}."
        key = cfg.api_key
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return f"Provider {name} API key: {masked}"


@command("provider config baseurl", "Show or set base URL for a provider")
def cmd_provider_config_baseurl(app, *args):
    if not args:
        return "Usage: /provider config baseurl <provider_name> [url]"
    name = args[0]
    if len(args) >= 2:
        url = args[1]
        cfg = app.config.providers.get(name)
        if cfg is None:
            from cdh.config import ProviderConfig
            cfg = ProviderConfig()
            app.config.providers[name] = cfg
        cfg.endpoint = url
        from cdh.config import save_config
        save_config(app.config)
        return f"Base URL for {name} set to: {url}"
    else:
        cfg = app.config.providers.get(name)
        if not cfg:
            return f"No config for provider: {name}"
        return f"Provider {name} base URL: {cfg.endpoint or 'default'}"


@command("cloud list", "List cloud configurations")
def cmd_cloud_list(app, *args):
    clouds = app.config.clouds
    if not clouds:
        return "No cloud configs."
    current = app.current_cloud
    items = []
    for name, cfg in clouds.items():
        active = "[active] " if name == current else ""
        items.append((f"{active}{name:<14} region: {cfg.region:<16} env: {cfg.env_id}", name))
    app.show_config_panel("Clouds", items, "cloud switch ", execute=True)
    return ""


@command("cloud switch", "Switch active cloud")
def cmd_cloud_switch(app, *args):
    if not args:
        return cmd_cloud_list(app)
    name = args[0]
    if name not in app.config.clouds:
        available = ", ".join(app.config.clouds.keys())
        return f"Unknown cloud: {name}. Available: {available}"
    app.current_cloud = name
    from cdh.tui.widgets.header import HeaderBar
    app.query_one(HeaderBar).sync(app)
    return f"Switched to cloud: {name}"


@command("cloud add", "Add cloud configuration")
def cmd_cloud_add(app, *args):
    return "Usage: /cloud add <name> [options]. Currently supports: tcb"
