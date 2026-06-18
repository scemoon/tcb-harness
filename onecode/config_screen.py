from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import var
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from onecode.config import GlobalConfig, load_config, resolve_env, save_config

def _display_val(v: str | None) -> str:
    if not v:
        return "default"
    resolved = resolve_env(v)
    return resolved if resolved else v

def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[:max_len-1] + "…"


SECTIONS = [
    ("general",      "General",       "basic settings"),
    ("providers",    "Providers",     "LLM provider config"),
    ("agent",        "Agent",         "agent parameters"),
    ("observability","Observability", "tracing & monitoring"),
    ("attachments",  "Attachments",   "file attachment settings"),
    ("model_auto",   "Model Auto",    "model selection hints"),
    ("skills",       "Skills",        "skill management"),
    ("mcps",         "MCPs",          "MCP server management"),
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
        if self.item_type in ("section", "provider", "skill", "mcp"):
            return f"> {self.label:<18} {self.value}"
        if self.item_type == "back":
            return f"< {self.label}"
        if self.item_type == "add_model":
            return f"  {self.label}"
        return f"  {self.label:<18} {_truncate(self.value, 36)}"


CSS = """
Screen {
    align: center middle;
}

ConfigScreen {
    background: #000;
}

#dialog {
    width: 64;
    height: 27;
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

#shortcuts {
    height: 1;
    background: #222;
    color: #888;
    padding: 0 1;
    content-align: left middle;
}

#button-row {
    height: 3;
    background: #333;
    align: center middle;
}

Button {
    margin: 0 1;
}

Button:disabled {
    color: #666;
}
"""


class EditFieldScreen(ModalScreen[str]):
    def __init__(self, field_label: str, current_value: str):
        super().__init__()
        self.field_label = field_label
        self.current_value = current_value

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
    ]

    CSS = """
    EditFieldScreen { background: rgba(0,0,0,0.7); align: center middle; }
    #edit-dialog { width: 50; height: 7; background: #111; border: solid #555; }
    #edit-label { height: 1; background: #333; color: #fff; padding: 0 1; }
    #edit-input { height: 3; padding: 0 1; }
    #edit-buttons { height: 3; background: #222; align: center middle; }
    Button { margin: 0 1; background: #444; color: #fff; }
    Button:hover { background: #666; }
    Button:focus { background: #555; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"  {self.field_label}", id="edit-label")
            yield Input(value=self.current_value, id="edit-input")
            with Horizontal(id="edit-buttons"):
                yield Button("Cancel", id="edit-cancel")
                yield Button("Save", id="edit-save")

    @on(Button.Pressed, "#edit-save")
    def on_save(self) -> None:
        self.dismiss(self.query_one("#edit-input", Input).value)

    @on(Button.Pressed, "#edit-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        self.dismiss(self.query_one("#edit-input", Input).value)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class OptionPickerScreen(ModalScreen[str]):
    def __init__(self, field_label: str, options: list[tuple[str, str]], current_value: str):
        super().__init__()
        self.field_label = field_label
        self.options = options
        self.current_value = current_value
        self._selected_index = 0

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
        Binding("up", "cursor_up", "Up"),
        Binding("down", "cursor_down", "Down"),
        Binding("enter", "confirm", "Confirm"),
    ]

    CSS = """
    OptionPickerScreen { background: rgba(0,0,0,0.7); align: center middle; }
    #picker-dialog { width: 50; height: auto; background: #111; border: solid #555; max-height: 20; }
    #picker-label { height: 1; background: #333; color: #fff; padding: 0 1; }
    #picker-list { height: auto; max-height: 15; background: #000; }
    .option-item { height: 1; padding: 0 1; color: #fff; background: #000; }
    .option-item:hover, .option-item.selected { background: #444; }
    #picker-buttons { height: 3; background: #222; align: center middle; }
    Button { margin: 0 1; background: #444; color: #fff; }
    Button:hover { background: #666; }
    Button:focus { background: #555; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Label(f"  {self.field_label}", id="picker-label")
            with Vertical(id="picker-list"):
                pass
            with Horizontal(id="picker-buttons"):
                yield Button("Cancel (ESC)", id="picker-cancel")
                yield Button("Confirm (ENTER)", id="picker-confirm")

    def on_mount(self) -> None:
        list_container = self.query_one("#picker-list", Vertical)
        for i, (label, val) in enumerate(self.options):
            is_selected = (val == self.current_value) or (self.current_value is None and i == 0)
            if is_selected:
                self._selected_index = i
            item = Static(f"  {'>' if is_selected else ' '}{label}", classes="option-item")
            item._option_index = i
            list_container.mount(item)
        self.query_one("#picker-confirm", Button).focus()

    def _refresh_list(self) -> None:
        list_container = self.query_one("#picker-list", Vertical)
        for i, item in enumerate(list_container.children):
            if isinstance(item, Static):
                label = self.options[i][0]
                marker = ">" if i == self._selected_index else " "
                item.update(f"  {marker}{label}")

    def action_cursor_up(self) -> None:
        if self._selected_index > 0:
            self._selected_index -= 1
            self._refresh_list()

    def action_cursor_down(self) -> None:
        if self._selected_index < len(self.options) - 1:
            self._selected_index += 1
            self._refresh_list()

    def action_confirm(self) -> None:
        _, val = self.options[self._selected_index]
        self.dismiss(val)

    @on(Button.Pressed, "#picker-confirm")
    def on_confirm_button(self) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#picker-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class ConfigScreen(App):
    TITLE = "CDH Configuration"
    CSS = CSS

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("left", "go_back", "Back"),
        Binding("right", "go_enter", "Select"),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+q", "quit_app", "Quit"),
    ]

    MODE_OPTIONS = [
        ("Build", "build"),
        ("Plan", "plan"),
        ("Solo", "solo"),
    ]

    LOG_LEVELS = ["debug", "info", "warn", "error"]

    cursor: var[int] = var(0)
    view: var[str] = var("menu")
    section_items: list[ConfigItem] = var(list)

    def __init__(self):
        super().__init__()
        self._cfg: GlobalConfig = load_config()
        self._breadcrumb = ["Menu"]
        self._current_section: str | None = None
        self._section_fields: list[ConfigItem] = []
        self._current_provider: str | None = None

    @property
    def current_items(self) -> list[ConfigItem]:
        return self._section_fields if self.view in ("section", "provider") else list(self.section_items)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("CDH Configuration", id="header")
            yield Label("Menu", id="breadcrumb")
            with Widget(id="content"):
                pass
            yield Label("", id="shortcuts")
            with Horizontal(id="button-row"):
                yield Button("Confirm (↵)", id="save")
                yield Button("Cancel (ESC)", id="cancel")
                yield Button("Quit (Ctrl+Q)", id="quit")

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
                self._section_fields.append(ConfigItem("log_level", "Log", cfg.log_level))
            case "providers":
                for pid, pcfg in cfg.providers.items():
                    n_models = len(pcfg.models)
                    ak = _truncate(_display_val(pcfg.api_key), 24)
                    ep = _truncate(_display_val(pcfg.endpoint), 20)
                    status = f"ep:{ep} ak:{ak}"
                    self._section_fields.append(ConfigItem(pid, PROVIDER_NAMES.get(pid, pid), status, item_type="provider"))
            case "agent":
                self._section_fields.append(ConfigItem("agent.max_iterations", "Max Iter", str(cfg.agent.max_iterations)))
                self._section_fields.append(ConfigItem("agent.timeout_seconds", "Timeout", str(cfg.agent.timeout_seconds)))
            case "observability":
                self._section_fields.append(ConfigItem("observability.trace_dir", "Trace Dir", cfg.observability.trace_dir))
            case "attachments":
                self._section_fields.append(ConfigItem("attachments.max_size_mb", "Max Size", str(cfg.attachments.max_size_mb)))
            case "model_auto":
                self._section_fields.append(ConfigItem("model_auto.simple_tasks", "Simple", cfg.model_auto.simple_tasks))
            case "skills":
                from onecode.skills.manager import SkillManager
                mgr = SkillManager()
                for s in mgr.list():
                    status = "[enabled]" if s.get("enabled", True) else "[disabled]"
                    self._section_fields.append(ConfigItem(f"skills.{s['name']}", s["name"], status, item_type="skill"))
            case "mcps":
                from onecode.mcp.manager import MCPManager
                mgr = MCPManager()
                for m in mgr.list():
                    status = "[enabled]" if m.get("enabled", True) else "[disabled]"
                    transport = m.get("transport", "sse")
                    self._section_fields.append(ConfigItem(f"mcps.{m['name']}", m["name"], f"{status} ({transport})", item_type="mcp"))
        self.cursor = 0

    def _build_provider(self, provider_id: str) -> None:
        self._section_fields = [
            ConfigItem("__back__", "Back to Providers", item_type="back")
        ]
        pcfg = self._cfg.providers.get(provider_id)
        if pcfg:
            self._section_fields.append(ConfigItem(f"{provider_id}.api_key", "API Key", _display_val(pcfg.api_key)))
            self._section_fields.append(ConfigItem(f"{provider_id}.endpoint", "Endpoint", _display_val(pcfg.endpoint)))
            for i, m in enumerate(pcfg.models):
                self._section_fields.append(ConfigItem(f"{provider_id}.models.{i}", "Model", m))
            self._section_fields.append(ConfigItem("__add_model__", "+ Add Model", item_type="add_model"))
        self.cursor = 0

    def _update_shortcuts(self) -> None:
        label = self.query_one("#shortcuts", Label)
        if self.view == "menu":
            label.update("")
        elif self.view == "provider":
            label.update("← Back to Providers  ↵ Confirm")
        else:
            label.update("← Back to Menu  → Select  ↵ Confirm")

    def _refresh_items(self) -> None:
        content = self.query_one("#content", Widget)
        content.remove_children()
        for item in self.current_items:
            content.mount(item)
        self.query_one("#breadcrumb", Label).update(" / ".join(self._breadcrumb))
        self._update_shortcuts()
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
        if self.view == "provider":
            self.view = "section"
            self._breadcrumb = ["Menu", "Providers"]
            self._current_provider = None
            self._build_section(self._current_section or "providers")
            self._refresh_items()
        elif self.view == "section":
            self.view = "menu"
            self._breadcrumb = ["Menu"]
            self._current_section = None
            self.cursor = 0
            self._build_menu()
            self._refresh_items()

    def action_go_enter(self) -> None:
        self._activate_current()

    def action_confirm(self) -> None:
        self._activate_current()

    def _edit_field(self, item: ConfigItem) -> None:
        key = item.key
        label = item.label
        options = self._get_enum_options(key)
        if options is not None:
            val = item.value if any(v == item.value for _, v in options) else options[0][1]
            self.push_screen(OptionPickerScreen(label, options, val), lambda v, k=key: self._on_field_edited(v, k))
        else:
            self.push_screen(EditFieldScreen(label, item.value), lambda v, k=key: self._on_field_edited(v, k))

    def _get_enum_options(self, key: str) -> list[tuple[str, str]] | None:
        if key == "default_mode":
            return self.MODE_OPTIONS
        if key == "log_level":
            return [(v, v) for v in self.LOG_LEVELS]
        if key == "default_provider":
            pids = list(self._cfg.providers.keys())
            return [(PROVIDER_NAMES.get(v, v), v) for v in pids]
        if key == "default_model":
            pcfg = self._cfg.providers.get(self._cfg.default_provider)
            if pcfg and pcfg.models:
                return [(m, m) for m in pcfg.models]
        return None

    def _apply_field_value(self, key: str, value: str) -> None:
        parts = key.split(".")
        if len(parts) == 1:
            setattr(self._cfg, parts[0], value)
        elif len(parts) == 2:
            parent = getattr(self._cfg, parts[0], None)
            if parent is not None:
                setattr(parent, parts[1], value)
            elif parts[0] in self._cfg.providers:
                setattr(self._cfg.providers[parts[0]], parts[1], value)
            elif parts[0] in self._cfg.clouds:
                setattr(self._cfg.clouds[parts[0]], parts[1], value)
        elif len(parts) == 3 and parts[0] == "providers":
            pcfg = self._cfg.providers.get(parts[1])
            if pcfg:
                setattr(pcfg, parts[2], value)
        elif len(parts) == 3 and parts[0] == "clouds":
            ccfg = self._cfg.clouds.get(parts[1])
            if ccfg:
                setattr(ccfg, parts[2], value)

    def _on_field_edited(self, value: str | None, key: str = "") -> None:
        if value is None:
            return
        self._apply_field_value(key, value)
        for item in self.current_items:
            if item.key == key:
                item.value = value
                if item.item_type == "field":
                    item.refresh()
                break
        save_config(self._cfg)

    def _on_model_added(self, value: str | None) -> None:
        if not value or not self._current_provider:
            return
        pcfg = self._cfg.providers.get(self._current_provider)
        if pcfg:
            pcfg.models.append(value)
            save_config(self._cfg)
            self._build_provider(self._current_provider)
            self.cursor = len(self._section_fields) - 1
            self._refresh_items()

    def _toggle_skill(self, item: ConfigItem) -> None:
        parts = item.key.split(".", 1)
        if len(parts) < 2:
            return
        name = parts[1]
        from onecode.skills.manager import SkillManager
        mgr = SkillManager()
        skill = mgr.get(name)
        if skill:
            new_enabled = not skill.get("enabled", True)
            mgr.enable(name, new_enabled)
            item.value = "[enabled]" if new_enabled else "[disabled]"
            item.refresh()

    def _toggle_mcp(self, item: ConfigItem) -> None:
        parts = item.key.split(".", 1)
        if len(parts) < 2:
            return
        name = parts[1]
        from onecode.mcp.manager import MCPManager
        mgr = MCPManager()
        mcp = mgr.get(name)
        if mcp:
            new_enabled = not mcp.get("enabled", True)
            mgr.enable(name, new_enabled)
            transport = mcp.get("transport", "sse")
            item.value = f"[{'enabled' if new_enabled else 'disabled'}] ({transport})"
            item.refresh()

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
        elif item.item_type == "provider":
            self.view = "provider"
            self._current_provider = item.key
            self._breadcrumb = ["Menu", "Providers", item.label]
            self._build_provider(item.key)
            self.cursor = 0
            self._refresh_items()
        elif item.item_type == "field":
            self._edit_field(item)
        elif item.item_type == "add_model":
            self.push_screen(EditFieldScreen("Model Name", ""), self._on_model_added)
        elif item.item_type == "back":
            self.action_go_back()
        elif item.item_type == "skill":
            self._toggle_skill(item)
        elif item.item_type == "mcp":
            self._toggle_mcp(item)

    def action_cancel(self) -> None:
        if self.view != "menu":
            self.action_go_back()

    def action_quit_app(self) -> None:
        self.exit()

    def _on_click(self, event) -> None:
        pass

    @on(Button.Pressed, "#save")
    def on_save(self) -> None:
        self.notify("Configuration saved")
        self.exit()

    @on(Button.Pressed, "#cancel")
    def on_cancel_button(self) -> None:
        self.exit()

    @on(Button.Pressed, "#quit")
    def on_quit(self) -> None:
        self.exit()


def main() -> None:
    ConfigScreen().run()