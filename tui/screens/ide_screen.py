from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Static, TextArea

from onecode.agent.tools.file_ops import FileOps
from tui.widgets.project_directory_tree import ProjectDirectoryTree


_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".rs": "rust",
    ".go": "go",
    ".toml": "toml",
    ".sql": "sql",
    ".xml": "xml",
    ".svg": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".scala": "scala",
    ".r": "r",
    ".lua": "lua",
    ".vim": "vim",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".proto": "protobuf",
    ".dockerfile": "dockerfile",
}

_TREE_WIDTH = 32


class IdeScreen(ModalScreen[None]):
    """Built-in minimal code editor for project file browsing and editing."""

    BINDINGS = [
        Binding("escape,q", "dismiss", "Close", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "new_file", "New File"),
        Binding("ctrl+d", "delete_file", "Delete"),
        Binding("f2", "rename", "Rename"),
        Binding("ctrl+b", "toggle_focus", "Toggle Focus"),
        Binding("ctrl+r", "refresh", "Refresh Tree"),
    ]

    DEFAULT_CSS = f"""
    IdeScreen {{
        background: $surface;
    }}

    #ide-header {{
        dock: top;
        width: 100%;
        padding: 0 2;
        background: $panel;
        color: $text-primary;
        text-style: bold;
        height: 3;
    }}

    #ide-body {{
        width: 100%;
        height: 1fr;
    }}

    #ide-tree {{
        width: {_TREE_WIDTH};
        height: 100%;
        border-right: solid $panel;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }}

    #ide-editor {{
        width: 1fr;
        height: 100%;
    }}

    #ide-editor > TextArea {{
        height: 100%;
    }}

    #ide-editor-placeholder {{
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }}

    #ide-prompt {{
        dock: bottom;
        width: 100%;
        height: 3;
        background: $panel;
        padding: 0 2;
        layout: horizontal;
    }}

    #ide-prompt.hidden {{
        display: none;
    }}

    #ide-prompt-label {{
        width: auto;
        padding: 1 1 1 0;
        color: $text-muted;
    }}

    #ide-prompt-input {{
        width: 1fr;
    }}

    #ide-footer {{
        dock: bottom;
        width: 100%;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
        height: 1;
    }}
    """

    current_file = reactive[Path | None](None)
    _modified = reactive(False)

    def __init__(
        self,
        project_dir: Path | None = None,
        filepath: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._project_dir = (project_dir or Path.cwd()).resolve()
        self._file_ops = FileOps(self._project_dir)
        self._initial_file = filepath
        self._delete_pending: Path | None = None
        self._prompt_action: str = ""
        self._loading_file: bool = False

    def compose(self) -> ComposeResult:
        yield Static("", id="ide-header")
        with Horizontal(id="ide-body"):
            yield ProjectDirectoryTree(self._project_dir, id="ide-tree")
            with VerticalScroll(id="ide-editor"):
                yield Static(
                    "Select a file from the tree to edit\n\n"
                    "ctrl+s: Save  ctrl+n: New  ctrl+d: Delete  F2: Rename  ctrl+b: Toggle  esc/q: Close",
                    id="ide-editor-placeholder",
                )
        with Horizontal(id="ide-prompt", classes="hidden"):
            yield Static("> ", id="ide-prompt-label")
            yield Input(placeholder="filename...", id="ide-prompt-input")
        yield Static("", id="ide-footer")

    def on_mount(self) -> None:
        self.title = f"IDE: {self._project_dir.name}"
        self._update_header()
        self._update_footer()
        self.query_one("#ide-tree").focus()

        if self._initial_file:
            fp = (self._project_dir / self._initial_file).resolve()
            if fp.is_file():
                self.call_after_refresh(lambda: self._open_file(fp))

    # ── header / footer ──────────────────────────────────────────

    def _update_header(self) -> None:
        if self.current_file:
            try:
                display = str(self.current_file.relative_to(self._project_dir))
            except ValueError:
                display = str(self.current_file)
            marker = " [+]" if self._modified else ""
            self.query_one("#ide-header", Static).update(
                f"[b]IDE: {self._project_dir.name}[/b]  "
                f"[#888888]{display}{marker}[/]"
            )
        else:
            self.query_one("#ide-header", Static).update(
                f"[b]IDE: {self._project_dir.name}[/b]"
            )

    def _update_footer(self) -> None:
        self.query_one("#ide-footer", Static).update(
            "ctrl+s: Save  ctrl+n: New  ctrl+d: Delete  F2: Rename  "
            "ctrl+b: Toggle  esc/q: Close"
        )

    # ── directory tree ────────────────────────────────────────────

    @on(ProjectDirectoryTree.FileSelected)
    def on_file_selected(self, event: ProjectDirectoryTree.FileSelected) -> None:
        event.stop()
        if event.path.is_file():
            self._open_file(event.path.resolve())

    @work
    async def action_refresh(self) -> None:
        tree = self.query_one("#ide-tree", ProjectDirectoryTree)
        await tree.reload()
        self.notify("Directory tree refreshed")

    # ── file open ─────────────────────────────────────────────────

    @on(TextArea.Changed, "#ide-editor TextArea")
    def on_editor_changed(self) -> None:
        if self._loading_file:
            return
        self._modified = True

    def _open_file(self, filepath: Path) -> None:
        content = self._file_ops.read(str(filepath))
        if content.startswith("Error") or content.startswith("File not found"):
            self.notify(f"Cannot open: {filepath.name}", severity="error")
            return

        self.current_file = filepath
        self._modified = False
        self._delete_pending = None
        self._loading_file = True

        lang = _LANGUAGE_MAP.get(filepath.suffix.lower(), "")

        editor_panel = self.query_one("#ide-editor", VerticalScroll)
        for child in list(editor_panel.children):
            child.remove()

        text_area = TextArea(
            content,
            language=lang,
            show_line_numbers=True,
            soft_wrap=False,
        )
        editor_panel.mount(text_area)
        text_area.focus()
        self._update_header()
        self.call_after_refresh(lambda: setattr(self, "_loading_file", False))

    def _get_textarea(self) -> TextArea | None:
        try:
            return self.query_one("#ide-editor TextArea", TextArea)
        except Exception:
            return None

    # ── actions ───────────────────────────────────────────────────

    def action_save(self) -> None:
        if self.current_file is None:
            self.notify("No file open", severity="warning")
            return

        text_area = self._get_textarea()
        if text_area is None:
            return

        result = self._file_ops.write(str(self.current_file), text_area.text)
        if result.get("success"):
            self._modified = False
            self.notify(f"Saved: {self.current_file.name}")
        else:
            self.notify(
                f"Save failed: {result.get('error', 'Unknown error')}",
                severity="error",
            )

    def action_new_file(self) -> None:
        self._prompt_action = "new"
        self._show_prompt("New file path (relative):")

    def action_delete_file(self) -> None:
        if self.current_file is None:
            self.notify("No file selected", severity="warning")
            return

        if self._delete_pending != self.current_file:
            self._delete_pending = self.current_file
            self.notify(
                f"Press ctrl+d again to confirm delete: {self.current_file.name}",
                timeout=5,
            )
            return

        filepath = self._delete_pending
        self._delete_pending = None
        try:
            filepath.unlink()
            self.notify(f"Deleted: {filepath.name}")
        except OSError as e:
            self.notify(f"Delete failed: {e}", severity="error")
            return

        if self.current_file == filepath:
            self._clear_editor()
        self.action_refresh()

    def action_rename(self) -> None:
        if self.current_file is None:
            self.notify("No file selected", severity="warning")
            return
        self._prompt_action = "rename"
        self._show_prompt(
            "New name:",
            prefill=self.current_file.name,
        )

    def action_toggle_focus(self) -> None:
        text_area = self._get_textarea()
        if text_area is not None and text_area.has_focus:
            self.query_one("#ide-tree").focus()
        else:
            if text_area is not None:
                text_area.focus()
            else:
                self.query_one("#ide-tree").focus()

    # ── prompt overlay (new / rename input) ───────────────────────

    def _show_prompt(self, label: str, prefill: str = "") -> None:
        prompt_label = self.query_one("#ide-prompt-label", Static)
        prompt_input = self.query_one("#ide-prompt-input", Input)
        prompt_panel = self.query_one("#ide-prompt", Horizontal)

        prompt_label.update(label)
        prompt_input.value = prefill
        prompt_panel.remove_class("hidden")
        prompt_input.focus()

    def _hide_prompt(self) -> None:
        prompt_panel = self.query_one("#ide-prompt", Horizontal)
        prompt_input = self.query_one("#ide-prompt-input", Input)
        prompt_input.value = ""
        prompt_panel.add_class("hidden")

    @on(Input.Submitted, "#ide-prompt-input")
    def on_prompt_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self._hide_prompt()

        if not value:
            self.query_one("#ide-tree").focus()
            return

        if self._prompt_action == "new":
            self._do_create_file(value)
        elif self._prompt_action == "rename":
            self._do_rename_file(value)

        self._prompt_action = ""

    def _do_create_file(self, filename: str) -> None:
        result = self._file_ops.write(filename, "")
        if not result.get("success"):
            self.notify(f"Create failed: {result.get('error')}", severity="error")
            self.query_one("#ide-tree").focus()
            return

        filepath = (self._project_dir / filename).resolve()
        self.notify(f"Created: {filename}")
        self.action_refresh()
        self._open_file(filepath)

    def _do_rename_file(self, new_name: str) -> None:
        if self.current_file is None:
            return

        new_path = self.current_file.parent / new_name

        if not self._file_ops._is_within_workspace(new_path.resolve()):
            self.notify("Cannot rename outside workspace", severity="error")
            self.query_one("#ide-tree").focus()
            return

        try:
            self.current_file.rename(new_path)
        except OSError as e:
            self.notify(f"Rename failed: {e}", severity="error")
            self.query_one("#ide-tree").focus()
            return

        self.notify(f"Renamed to: {new_name}")
        self.current_file = new_path
        self._update_header()
        self.action_refresh()

    # ── editor management ─────────────────────────────────────────

    def _clear_editor(self) -> None:
        self.current_file = None
        self._modified = False
        editor_panel = self.query_one("#ide-editor", VerticalScroll)
        for child in list(editor_panel.children):
            child.remove()
        editor_panel.mount(
            Static(
                "Select a file from the tree to edit\n\n"
                "ctrl+s: Save  ctrl+n: New  ctrl+d: Delete  F2: Rename  ctrl+t: Toggle  esc/q: Close",
                id="ide-editor-placeholder",
            )
        )
        self._update_header()

    def watch_modified(self, old: bool, new: bool) -> None:
        self._update_header()

    # ── dismiss ───────────────────────────────────────────────────

    def action_dismiss(self) -> None:
        prompt_panel = self.query_one("#ide-prompt", Horizontal)
        if not prompt_panel.has_class("hidden"):
            self._hide_prompt()
            self.query_one("#ide-tree").focus()
            return
        if self._modified:
            self.notify(
                "Unsaved changes! Save with ctrl+s before closing",
                severity="warning",
            )
            return
        self.dismiss(None)
