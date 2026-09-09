import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("onecode.config")


# NOTE: ``ONECODE_DIR`` and ``GLOBAL_CONFIG_PATH`` are resolved at
# *import time* using ``Path.home()``. They are kept as module-level
# constants for backward compatibility, but code that runs inside tests
# with a patched ``$HOME`` should prefer the ``onecode_dir()`` and
# ``global_config_path()`` helpers below so the values are re-evaluated
# at call time.
ONECODE_DIR = Path.home() / ".onecode"
GLOBAL_CONFIG_PATH = ONECODE_DIR / "onecode.config.yaml"


def onecode_dir() -> Path:
    """Return ``~/.onecode`` resolved at call time (test-friendly)."""
    return Path.home() / ".onecode"


def global_config_path() -> Path:
    """Return the path to the onecode global config at call time."""
    return Path.home() / ".onecode" / "onecode.config.yaml"


@dataclass
class ProviderConfig:
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    models: list[str] = field(default_factory=list)
    auto_download: bool = True
    auto_select: bool = True


@dataclass
class ObservabilityConfig:
    trace_enabled: bool = True
    trace_exporter: str = "file"
    otlp_endpoint: str = "http://localhost:4317"
    trace_dir: str = "~/.onecode/traces"


@dataclass
class TuiConfig:
    theme: str = "auto"
    show_right_panel: bool = True
    command_history_size: int = 100


@dataclass
class AttachmentsConfig:
    max_size_mb: int = 10
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".txt", ".md", ".py", ".json", ".yaml", ".sql",
    ])
    sandbox_read: bool = True


@dataclass
class AgentConfig:
    max_iterations: int = 500
    timeout_seconds: int = 600
    allow_shell_commands: bool = True
    shell_command_whitelist: list[str] = field(default_factory=list)
    temperature: float = 0.7
    max_subagent_depth: int = 1
    max_subagent_timeout: int = 600
    max_empty_turns: int = 10


@dataclass
class ModelAutoConfig:
    simple_tasks: str = "minimax-2.7"
    medium_tasks: str = "minimax-2.7"
    complex_tasks: str = "minimax-2.7"


@dataclass
class CodebaseConfig:
    enabled: bool = True
    auto_retrieve: bool = True
    chunk_strategy: str = "line"
    chunk_lines: int = 50
    chunk_overlap: int = 10
    retriever: str = "bm25"
    embedding_provider: str = ""
    embedding_model: str = ""
    top_k: int = 5
    max_chunk_tokens: int = 500
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "node_modules/**", "__pycache__/**", ".git/**",
        ".venv/**", "venv/**", "dist/**", "build/**",
        "*.min.*", "*.pyc", "*.egg-info/**", ".cdh/**",
        ".opencode/**", ".claude/**", ".agents/**",
        ".idea/**", ".vscode/**", ".DS_Store",
    ])
    include_extensions: list[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
        ".java", ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
        ".swift", ".kt", ".scala",
        ".sql", ".yaml", ".yml", ".json", ".toml",
        ".md", ".css", ".scss", ".html", ".svelte", ".vue",
        ".sh", ".bash", ".zsh", ".fish",
        ".tf", ".tfvars",
    ])


@dataclass
class MemoryConfig:
    enabled: bool = True
    auto_recall: bool = True
    top_k: int = 5


@dataclass
class PerAgentVerificationConfig:
    enabled: bool = True
    gates: list[str] = field(default_factory=lambda: ["lint", "type", "test"])
    policy: str = "conditional"


@dataclass
class VerificationConfig:
    enabled: bool = True
    policy: str = "conditional"
    gates: list[str] = field(default_factory=lambda: ["lint", "type", "test"])
    plan_gate_mode: str = "adaptive"
    per_agent: dict[str, PerAgentVerificationConfig] = field(default_factory=dict)

    def for_agent(self, agent_type: str) -> PerAgentVerificationConfig:
        return self.per_agent.get(agent_type, PerAgentVerificationConfig(
            enabled=self.enabled,
            gates=self.gates,
            policy=self.policy,
        ))


@dataclass
class EventLoopConfig:
    enabled: bool = False
    sources: list[str] = field(default_factory=lambda: ["cron", "filewatch"])


@dataclass
class MCPConfig:
    timeout: float = 60.0
    heartbeat_interval: float = 15.0
    reconnect_enabled: bool = True
    disabled: list[str] = field(default_factory=list)  # glob patterns of MCP server names to skip


@dataclass
class RetryConfig:
    max_attempts: int = 5
    backoff_max: float = 60.0
    backoff_jitter: float = 0.5


@dataclass
class HillclimbConfig:
    enabled: bool = False
    min_sessions: int = 10


@dataclass
class AskUserConfig:
    timeout_seconds: int = 10
    timeout_behavior: str = "use_default"
    unsupported_behavior: str = "use_default"


@dataclass
class LoopConfig:
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    event: EventLoopConfig = field(default_factory=EventLoopConfig)
    hillclimb: HillclimbConfig = field(default_factory=HillclimbConfig)


@dataclass
class GlobalConfig:
    default_mode: str = "build"
    default_provider: str = "minimaxi"
    default_model: str = "MiniMax-M2.7"

    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    attachments: AttachmentsConfig = field(default_factory=AttachmentsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    model_auto: ModelAutoConfig = field(default_factory=ModelAutoConfig)
    current_project: str = ""
    current_project_path: str = ""
    log_level: str = "info"
    session_auto_save: bool = True
    codebase: CodebaseConfig = field(default_factory=CodebaseConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    loops: LoopConfig = field(default_factory=LoopConfig)
    ask_user: AskUserConfig = field(default_factory=AskUserConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)


def _dict_to_dataclass(cls, data: dict):
    if data is None:
        return cls()
    field_types = cls.__dataclass_fields__
    kwargs = {}
    for name, field_def in field_types.items():
        if name in data:
            val = data[name]
            ftype = field_def.type
            origin = getattr(ftype, "__origin__", None)
            if origin is dict:
                args = getattr(ftype, "__args__", ())
                if len(args) == 2:
                    _, val_type = args
                    if hasattr(val_type, "__dataclass_fields__"):
                        kwargs[name] = {k: _dict_to_dataclass(val_type, v) for k, v in val.items()}
                    else:
                        kwargs[name] = val
                else:
                    kwargs[name] = val
            elif hasattr(ftype, "__dataclass_fields__"):
                kwargs[name] = _dict_to_dataclass(ftype, val) if isinstance(val, dict) else ftype()
            else:
                kwargs[name] = val
    return cls(**kwargs)


def ensure_dirs():
    base = onecode_dir()
    dirs = [
        base,
        base / "sessions",
        base / "skills",
        base / "mcps",
        base / "traces",
        base / "logs",
        base / "models",
        base / "codebase" / "indexes",
        base / "memory",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # One-time migration from legacy ~/.cdh/ to ~/.onecode/
    try:
        from onecode.migrate import migrate_legacy_cdh_to_onecode
        result = migrate_legacy_cdh_to_onecode()
        if result:
            logger.warning("Legacy migration: %s", result)
    except Exception as exc:
        logger.warning("Legacy migration failed: %s", exc)


def load_config() -> GlobalConfig:
    ensure_dirs()
    config_path = global_config_path()
    if not config_path.exists():
        _write_default_config()
    try:
        from onecode.skills.bootstrap import ensure_onecode_default_skills
        ensure_onecode_default_skills()
    except Exception:
        pass
    raw = yaml.safe_load(config_path.read_text()) or {}
    cfg = _dict_to_dataclass(GlobalConfig, raw)
    # If the on-disk config has no provider entries (e.g. an older
    # install or a hand-edited file with ``providers: {}``), populate
    # the dict from the registered provider classes plus the built-in
    # default templates so the config editor can show and edit them.
    if not cfg.providers:
        cfg.providers = _default_providers()
    # Make sure every provider entry is a proper ``ProviderConfig``
    # instance — the on-disk YAML may have been hand-edited or
    # produced by a version that skipped dataclass conversion for
    # nested dicts, and the UI relies on attribute access.
    cfg.providers = {
        name: pcfg if isinstance(pcfg, ProviderConfig) else _dict_to_dataclass(ProviderConfig, pcfg)
        for name, pcfg in cfg.providers.items()
    }
    return cfg


def _default_providers() -> dict:
    """Return the default provider config templates.

    Combines the default YAML block (kept for backwards-compat) with
    any providers that the ``ProviderRegistry`` knows about but that
    are missing from the default block.
    """
    from onecode.models.provider import ProviderRegistry

    # Trigger provider registration side-effects.
    try:
        from onecode.models import providers as _providers_mod  # noqa: F401
    except ImportError:
        pass

    # Pull the default block out of _write_default_config's literal so
    # we keep a single source of truth.
    default: dict = {}
    try:
        # We re-derive the default dict by inlining the same templates
        # used in _write_default_config; this keeps both paths aligned
        # without exposing the literal as a module attribute.
        from onecode.config import _PROVIDER_DEFAULT_TEMPLATES  # type: ignore
        import copy as _copy
        default = {k: _copy.deepcopy(v) for k, v in _PROVIDER_DEFAULT_TEMPLATES.items()}
    except ImportError:
        # Fall back to an empty seed; the registry merge below will
        # still produce a useful result.
        default = {}

    # Merge in any registered provider that isn't in the default block,
    # so newly added providers (e.g. aliyun) show up automatically.
    for name in ProviderRegistry.list():
        if name not in default:
            default[name] = {
                "api_key": "${" + name.upper() + "_API_KEY}",
                "endpoint": "",
                "models": [],
            }
    return default


_PROVIDER_DEFAULT_TEMPLATES: dict = {
    "anthropic": {
        "api_key": "${ANTHROPIC_API_KEY}",
        "endpoint": "https://api.anthropic.com/v1",
        "models": [
            "claude-opus-4.7",
            "claude-opus-4.7-fast"
        ],
    },
    "openai": {
        "api_key": "${OPENAI_API_KEY}",
        "endpoint": "https://api.openai.com/v1",
        "models": ["gpt-5.5-pro", "gpt-5.5"],
    },
    "ollama": {
        "endpoint": "http://localhost:11434",
        "models": ["llama2", "codellama", "qwen3.5-2b", "qwen3.5-4b"],
        "auto_download": True,
        "auto_select": True,
    },
    "deepseek": {
        "api_key": "${DEEPSEEK_API_KEY}",
        "endpoint": "https://api.deepseek.com/v1",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
    },
    "minimax": {
        "api_key": "${MINIMAX_API_KEY}",
        "endpoint": "https://api.minimax.com/v1",
        "models": ["MiniMax-M2.7", "MiniMax-M2.5"],
    },
    "minimaxi": {
        "api_key": "${MINMAXI_API_KEY}",
        "endpoint": "https://api.minimaxi.com/v1",
        "models": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5"],
    },
    "glm": {
        "api_key": "${GLM_API_KEY}",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.1", "glm-5"],
    },
}


def _write_default_config():
    default = {
        "default_mode": "build",
        "default_provider": "minimaxi",
        "default_model": "MiniMax-M2.7",
        "providers": _PROVIDER_DEFAULT_TEMPLATES,
        "observability": {
            "trace_enabled": True,
            "trace_exporter": "file",
            "otlp_endpoint": "http://localhost:4317",
            "trace_dir": "~/.onecode/traces",
        },
        "attachments": {
            "max_size_mb": 10,
            "allowed_extensions": [".txt", ".md", ".py", ".json", ".yaml", ".sql"],
            "sandbox_read": True,
        },
        "agent": {
            "max_iterations": 100,
            "timeout_seconds": 600,
            "allow_shell_commands": True,
            "shell_command_whitelist": [],
        },
        "model_auto": {
            "simple_tasks": "minimax-2.7",
            "medium_tasks": "minimax-2.7",
            "complex_tasks": "minimax-2.7"
        },
        "current_project": "",
        "current_project_path": "",
        "log_level": "info",
        "session_auto_save": True,
        "codebase": {
            "enabled": True,
            "auto_retrieve": True,
            "chunk_strategy": "line",
            "chunk_lines": 50,
            "chunk_overlap": 10,
            "retriever": "bm25",
            "top_k": 5,
            "max_chunk_tokens": 500,
            "exclude_patterns": [
                "node_modules/**", "__pycache__/**", ".git/**",
                ".venv/**", "venv/**", "dist/**", "build/**",
                "*.min.*", "*.pyc", "*.egg-info/**", ".cdh/**",
                ".opencode/**", ".claude/**", ".agents/**",
                ".idea/**", ".vscode/**", ".DS_Store",
            ],
            "include_extensions": [
                ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                ".java", ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
                ".swift", ".kt", ".scala",
                ".sql", ".yaml", ".yml", ".json", ".toml",
                ".md", ".css", ".scss", ".html", ".svelte", ".vue",
                ".sh", ".bash", ".zsh", ".fish",
                ".tf", ".tfvars",
            ],
        },
        "mcp": {
            "timeout": 60.0,
            "heartbeat_interval": 15.0,
            "reconnect_enabled": True,
            "disabled": [],
        },
        "retry": {
            "max_attempts": 5,
            "backoff_max": 60.0,
            "backoff_jitter": 0.5,
        },
    }
    global_config_path().write_text(yaml.dump(default, default_flow_style=False))


def save_config(cfg: GlobalConfig):
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _dataclass_to_dict(cfg)
    path.write_text(yaml.dump(raw, default_flow_style=False))


def _dataclass_to_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for name, field_def in obj.__dataclass_fields__.items():
            val = getattr(obj, name)
            if hasattr(val, "__dataclass_fields__"):
                result[name] = _dataclass_to_dict(val)
            elif isinstance(val, dict) and val:
                first_val = next(iter(val.values()), None)
                if hasattr(first_val, "__dataclass_fields__"):
                    result[name] = {k: _dataclass_to_dict(v) for k, v in val.items()}
                else:
                    result[name] = val
            else:
                result[name] = val
        return result
    return obj


def resolve_env(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.environ.get(env_var, "")
    return value


CDH_AGENT_CONFIG_PATH = Path.home() / ".cdh" / "agent_config.yaml"


def sync_agent_config() -> None:
    """Read ``~/.cdh/agent_config.yaml`` and sync applicable params to ``onecode.config.yaml``.

    Maps optimizer-evolved params to ``GlobalConfig`` fields:
      - ``engine.onecode.max_iterations`` → ``agent.max_iterations``
      - ``engine.onecode.temperature``    → ``agent.temperature``
      - ``engine.onecode.plan_gate_mode`` → ``loops.verification.plan_gate_mode``
      - ``platform.verification.policy``  → ``loops.verification.policy``
      - ``platform.verification.gates``   → ``loops.verification.gates``

    Silently no-ops if the agent config does not exist.
    """
    if not CDH_AGENT_CONFIG_PATH.exists():
        return
    try:
        raw = yaml.safe_load(CDH_AGENT_CONFIG_PATH.read_text()) or {}
    except Exception:
        logger.warning("Failed to read %s", CDH_AGENT_CONFIG_PATH)
        return

    cfg = load_config()
    changed = False

    # Platform-level params → loops.verification
    platform = raw.get("platform", {})
    if "verification.policy" in platform:
        cfg.loops.verification.policy = str(platform["verification.policy"])
        changed = True
    if "verification.gates" in platform:
        gates = platform["verification.gates"]
        if isinstance(gates, list):
            cfg.loops.verification.gates = [str(g) for g in gates]
            changed = True

    # Engine-level params (onecode-specific)
    engine = raw.get("engine", {})
    onecode_params = engine.get("onecode", {})
    if "max_iterations" in onecode_params:
        val = int(onecode_params["max_iterations"])
        if val >= 5:
            cfg.agent.max_iterations = val
            changed = True
    if "temperature" in onecode_params:
        val = float(onecode_params["temperature"])
        if 0.0 <= val <= 2.0:
            cfg.agent.temperature = val
            changed = True
    if "plan_gate_mode" in onecode_params:
        val = str(onecode_params["plan_gate_mode"])
        if val in ("strict", "adaptive", "relaxed"):
            cfg.loops.verification.plan_gate_mode = val
            changed = True

    if changed:
        save_config(cfg)
        logger.info("Synced %s → onecode.config.yaml", CDH_AGENT_CONFIG_PATH)
