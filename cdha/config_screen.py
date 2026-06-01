from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from cdha.config import GlobalConfig, load_config, save_config


SECTIONS = [
    ("general",      "General",       "basic settings"),
    ("providers",    "Providers",     "LLM provider config"),
    ("cloud",        "Cloud",         "cloud platform settings"),
    ("agent",        "Agent",         "agent parameters"),
    ("observability","Observability", "tracing & monitoring"),
    ("shell",        "Shell",         "shell configuration"),
    ("tui",          "TUI",           "TUI settings"),
    ("attachments",  "Attachments",   "file attachment settings"),
    ("model_auto",   "Model Auto",    "model selection hints"),
]

PROVIDER_NAMES = {
    "anthropic": "Anthropic", "openai": "OpenAI", "deepseek": "DeepSeek",
    "minimax": "MiniMax", "minimaxi": "MiniMaxi", "glm": "GLM", "ollama": "Ollama",
}


class ConfigItem(Static, can_focus=True):
    def __init__(self, key: str, label: str, value: str = "", item_type: str = "field"):
        super().__init__()
        self.key = key
        self.label = label
        self.value = value
        self.item_type = item_type

    def render(self) -> str:
        if self.item_type == "section":
            return f"> {self.label}"
        if self.item_type == "back":
            return f"< {self.label}"
        return f"  {self.label:<18} {self.value}"


CSS = """
Screen {
    align: center middle;
}

ConfigScreen {
    background: #000;
}

#dialog {
    width: 60;
    height: 25;
    background: #000;
    border: solid #555;
}

#header {
    height: 2;
    background: #333;
    content-align: center middle;
    color: #fff;
    text-style: bold;
}

#breadcrumb {
    height: 1;
    background: #222;
    color: #aaa;
    padding: 0 1;
}

#content {
    width: 100%;
    height: 1fr;
    background: #000;
}

ConfigItem {
    width: 100%;
    height: 1;
    padding: 0 1;
    color: #fff;
    background: #000;
}

ConfigItem:hover, ConfigItem.-focus {
    background: #444;
}

#button-row {
    height: 3;
    background: #333;
    align: center middle;
}

Button {
    margin: 0 1;
}
"""


class ConfigScreen(App):
    TITLE = "CDH Configuration"
    CSS = CSS

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("left", "go_back", show=False),
        Binding("right", "go_enter", show=False),
        Binding("enter", "confirm", show=False),
        Binding("escape", "cancel", "Cancel"),
    ]

    cursor: var[int] = var(0)
    view: var[str] = var("menu")
    section_items: list[ConfigItem] = var(list)

    def __init__(self):
        super().__init__()
        self._cfg: GlobalConfig = load_config()
        self._breadcrumb = ["Menu"]
        self._current_section: str | None = None
        self._section_fields: list[ConfigItem] = []

    @property
    def current_items(self) -> list[ConfigItem]:
        return self._section_fields if self.view == "section" else list(self.section_items)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("CDH Configuration", id="header")
            yield Label("Menu", id="breadcrumb")
            with Widget(id="content"):
                pass
            with Horizontal(id="button-row"):
                yield Button("Save", id="save")
                yield Button("Reset", id="reset")
                yield Button("Quit", id="quit")

    def on_mount(self) -> None:
        self._build_menu()
        self._refresh_items()

    def _build_menu(self) -> None:
        self.section_items = [
            ConfigItem(sid, label, hint, item_type="section")
            for sid, label, hint in SECTIONS
        ]
        self.cursor = 0

    def _build_section(self, section_id: str) -> None:
        self._section_fields = [
            ConfigItem("__back__", "Back to Menu", item_type="back")
        ]

        cfg = self._cfg
        match section_id:
            case "general":
                self._section_fields.append(ConfigItem("default_mode", "Mode", cfg.default_mode))
                self._section_fields.append(ConfigItem("default_provider", "Provider", cfg.default_provider))
                self._section_fields.append(ConfigItem("default_model", "Model", cfg.default_model))
                self._section_fields.append(ConfigItem("default_cloud", "Cloud", cfg.default_cloud))
                self._section_fields.append(ConfigItem("log_level", "Log", cfg.log_level))
            case "providers":
                for pid, pcfg in cfg.providers.items():
                    self._section_fields.append(ConfigItem(f"providers.{pid}.api_key", PROVIDER_NAMES.get(pid, pid), pcfg.api_key and "set" or "unset"))
            case "cloud":
                for cid, ccfg in cfg.clouds.items():
                    self._section_fields.append(ConfigItem(f"clouds.{cid}.region", cid.upper(), ccfg.region))
            case "agent":
                self._section_fields.append(ConfigItem("agent.max_iterations", "Max Iter", str(cfg.agent.max_iterations)))
                self._section_fields.append(ConfigItem("agent.timeout_seconds", "Timeout", str(cfg.agent.timeout_seconds)))
            case "observability":
                self._section_fields.append(ConfigItem("observability.trace_dir", "Trace Dir", cfg.observability.trace_dir))
            case "shell":
                self._section_fields.append(ConfigItem("shell.default_shell", "Shell", cfg.shell.default_shell))
            case "tui":
                self._section_fields.append(ConfigItem("tui.theme", "Theme", cfg.tui.theme))
            case "attachments":
                self._section_fields.append(ConfigItem("attachments.max_size_mb", "Max Size", str(cfg.attachments.max_size_mb)))
            case "model_auto":
                self._section_fields.append(ConfigItem("model_auto.simple_tasks", "Simple", cfg.model_auto.simple_tasks))
        self.cursor = 0

    def _refresh_items(self) -> None:
        content = self.query_one("#content", Widget)
        content.remove_children()
        for item in self.current_items:
            content.mount(item)
        self.query_one("#breadcrumb", Label).update(" / ".join(self._breadcrumb))
        self._clamp_cursor()

    def _clamp_cursor(self) -> None:
        items = self.current_items
        if items:
            self.cursor = max(0, min(self.cursor, len(items) - 1))
            self._highlight_cursor()
            items[self.cursor].focus()

    def _highlight_cursor(self) -> None:
        for i, item in enumerate(self.current_items):
            item.set_class(i == self.cursor, "-focus")

    def action_cursor_up(self) -> None:
        items = self.current_items
        if not items:
            return
        self.cursor = max(0, self.cursor - 1)
        self._highlight_cursor()
        items[self.cursor].focus()

    def action_cursor_down(self) -> None:
        items = self.current_items
        if not items:
            return
        self.cursor = min(len(items) - 1, self.cursor + 1)
        self._highlight_cursor()
        items[self.cursor].focus()

    def action_go_back(self) -> None:
        if self.view == "section":
            self.view = "menu"
            self._breadcrumb = ["Menu"]
            self._current_section = None
            self.cursor = 0
            self._refresh_items()
        else:
            self.exit()

    def action_go_enter(self) -> None:
        self._activate_current()

    def action_confirm(self) -> None:
        self._activate_current()

    def _activate_current(self) -> None:
        items = self.current_items
        if not items or self.cursor >= len(items):
            return
        item = items[self.cursor]
        if item.item_type == "section":
            self.view = "section"
            self._current_section = item.key
            self._breadcrumb = ["Menu", item.label]
            self._build_section(item.key)
            self.cursor = 0
            self._refresh_items()
        elif item.item_type == "back":
            self.action_go_back()

    def action_cancel(self) -> None:
        self.exit()

    def _on_click(self, event) -> None:
        pass

    @on(Button.Pressed, "#save")
    def on_save(self) -> None:
        save_config(self._cfg)
        self.notify("Configuration saved")
        self.exit()

    @on(Button.Pressed, "#reset")
    def on_reset(self) -> None:
        self._cfg = load_config()
        self.cursor = 0
        if self.view == "menu":
            self._build_menu()
        elif self._current_section:
            self._build_section(self._current_section)
        self._refresh_items()

    @on(Button.Pressed, "#quit")
    def on_quit(self) -> None:
        self.exit()


def main() -> None:
    ConfigScreen().run()