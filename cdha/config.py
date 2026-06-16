import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


CLOUD_DEV_HARNESS_DIR = Path.home() / ".cdha"
GLOBAL_CONFIG_PATH = CLOUD_DEV_HARNESS_DIR / "cdh.config.yaml"


@dataclass
class ProviderConfig:
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    models: list[str] = field(default_factory=list)


@dataclass
class ObservabilityConfig:
    trace_enabled: bool = True
    trace_exporter: str = "file"
    otlp_endpoint: str = "http://localhost:4317"
    trace_dir: str = "~/.cdha/traces"


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
    max_iterations: int = 20
    timeout_seconds: int = 300
    allow_shell_commands: bool = True
    shell_command_whitelist: list[str] = field(default_factory=list)


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
    dirs = [
        CLOUD_DEV_HARNESS_DIR,
        CLOUD_DEV_HARNESS_DIR / "sessions",
        CLOUD_DEV_HARNESS_DIR / "skills",
        CLOUD_DEV_HARNESS_DIR / "mcps",
        CLOUD_DEV_HARNESS_DIR / "traces",
        CLOUD_DEV_HARNESS_DIR / "logs",
        CLOUD_DEV_HARNESS_DIR / "models",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> GlobalConfig:
    ensure_dirs()
    if not GLOBAL_CONFIG_PATH.exists():
        _write_default_config()
    raw = yaml.safe_load(GLOBAL_CONFIG_PATH.read_text()) or {}
    return _dict_to_dataclass(GlobalConfig, raw)


def _write_default_config():
    default = {
        "default_mode": "build",
        "default_provider": "minimaxi",
        "default_model": "MiniMax-M2.7",
        "providers": {
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
                "models": ["llama2", "codellama"],
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
                "models": ["MiniMax-M2.7", "MiniMax-M2.5"],
            },
            "glm": {
                "api_key": "${GLM_API_KEY}",
                "endpoint": "https://open.bigmodel.cn/api/paas/v4",
                "models": ["glm-5.1", "glm-5"],
            },
        },
        "observability": {
            "trace_enabled": True,
            "trace_exporter": "file",
            "otlp_endpoint": "http://localhost:4317",
            "trace_dir": "~/.cdha/traces",
        },
        "attachments": {
            "max_size_mb": 10,
            "allowed_extensions": [".txt", ".md", ".py", ".json", ".yaml", ".sql"],
            "sandbox_read": True,
        },
        "agent": {
            "max_iterations": 20,
            "timeout_seconds": 300,
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
    }
    GLOBAL_CONFIG_PATH.write_text(yaml.dump(default, default_flow_style=False))


def save_config(cfg: GlobalConfig):
    GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = _dataclass_to_dict(cfg)
    GLOBAL_CONFIG_PATH.write_text(yaml.dump(raw, default_flow_style=False))


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
