from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll, Horizontal
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from tui.diff_utils import (
    ModifiedFile,
    get_file_diff_content,
    get_modified_files,
    STATUS_COLORS,
    STATUS_ICONS,
    DIFF_COLORS,
)
from tui.widgets.diff_view import make_diff


def _tag_color(added: int, deleted: int) -> str:
    if added and deleted:
        return DIFF_COLORS["mix"]
    if added:
        return DIFF_COLORS["add"]
    if deleted:
        return DIFF_COLORS["del"]
    return DIFF_COLORS["dim"]


_FILE_LIST_DEFAULT_WIDTH = 42
_FILE_LIST_MIN_WIDTH = 20


def _build_file_tree(files: list[ModifiedFile]) -> list[dict]:
    tree: dict[str, dict] = {}
    for mf in files:
        parts = mf.filepath.split("/")
        node = tree
        for i, part in enumerate(parts[:-1]):
            if part not in node:
                node[part] = {"__type__": "dir", "__children__": {}}
            node = node[part]["__children__"]
        node[parts[-1]] = {"__type__": "file", "__mf__": mf}

    return tree


def _flatten_tree(tree: dict[str, dict], depth: int = 0) -> list[dict]:
    entries: list[dict] = []
    dirs = sorted(
        [(k, v) for k, v in tree.items() if v["__type__"] == "dir"],
        key=lambda x: x[0].casefold(),
    )
    files = sorted(
        [(k, v) for k, v in tree.items() if v["__type__"] == "file"],
        key=lambda x: x[0].casefold(),
    )
    for name, data in dirs:
        entries.append({
            "type": "dir",
            "name": name,
            "depth": depth,
            "display": f"{'  ' * depth}{name}/",
        })
        entries.extend(_flatten_tree(data["__children__"], depth + 1))
    for name, data in files:
        mf = data["__mf__"]
        entries.append({
            "type": "file",
            "name": name,
            "depth": depth,
            "display": f"{'  ' * depth}{name}",
            "mf": mf,
        })
    return entries


def _dirlen(path: str) -> int:
    return len(path) + 1 if not path.endswith("/") else len(path)


def _render_file_tree_lines(
    entries: list[dict],
    highlighted_filepath: str | None,
    panel_width: int,
) -> list[str]:
    out: list[str] = []
    max_label = panel_width - 4
    if max_label < 4:
        max_label = 4

    for entry in entries:
        match entry["type"]:
            case "dir":
                name = entry["name"]
                depth = entry["depth"]
                indent = "  " * depth
                disp = name
                if _dirlen(indent) + _dirlen(disp) > max_label:
                    disp = disp[:max_label - _dirlen(indent) - 1] + "…"
                line = f"{indent}[b][#888888]📁 {disp}[/][/b]"
                out.append(line)
            case "file":
                mf = entry["mf"]
                depth = entry["depth"]
                indent = "  " * depth
                icon = STATUS_ICONS.get(mf.status, "M")
                sc = STATUS_COLORS.get(mf.status, "yellow")
                tag = (
                    f"+{mf.added}/-{mf.deleted}"
                    if mf.added or mf.deleted
                    else ""
                )
                tc = _tag_color(mf.added, mf.deleted) if tag else ""

                disp = entry["name"]
                label_max = max_label - _dirlen(indent) - 2
                if tag:
                    label_max -= len(tag) + 2
                if label_max < 2:
                    label_max = 2
                if len(disp) > label_max:
                    disp = disp[:label_max - 1] + "…"

                line = f"{indent}[{sc}]{icon} {disp}[/]"
                if tag:
                    line += f"  [{tc}]{tag}[/]"

                if highlighted_filepath is not None and mf.filepath == highlighted_filepath:
                    line = f"[reverse]{line}[/]"
                out.append(line)
    return out


class DiffExplorerScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("j", "next_file", "", show=False),
        Binding("k", "prev_file", "", show=False),
        Binding("down", "next_file", "", show=False),
        Binding("up", "prev_file", "", show=False),
    ]

    DEFAULT_CSS = """
    DiffExplorerScreen {
        background: $surface;
    }

    #de-header {
        dock: top;
        width: 100%;
        padding: 0 2;
        background: $panel;
        color: $text-primary;
        text-style: bold;
        height: 3;
    }

    #de-body {
        width: 100%;
        height: 1fr;
    }

    #de-file-list {
        height: 100%;
        border-right: solid $panel;
        overflow-y: auto;
        padding: 0 0 0 1;
        scrollbar-size: 0 0;
    }

    #de-file-list-content {
        width: 100%;
        height: auto;
    }

    #de-diff-panel {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }

    #de-diff-panel #de-placeholder {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }

    #de-footer {
        dock: bottom;
        width: 100%;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
        height: 1;
    }
    """

    highlighted_index: reactive[int] = reactive(0)
    _file_list_width: reactive[int] = reactive(_FILE_LIST_DEFAULT_WIDTH)
    _modified_files: reactive[list[ModifiedFile]] = reactive(list)

    def __init__(
        self,
        project_dir: Path | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._project_dir = project_dir or Path.cwd()
        self._loading = True
        self._tree_entries: list[dict] = []
        self._file_entries: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="de-header")
        with Horizontal(id="de-body"):
            with VerticalScroll(id="de-file-list"):
                yield Static("", id="de-file-list-content")
            with VerticalScroll(id="de-diff-panel"):
                yield Static(
                    "Select a file to view diff\n\n"
                    "j/k: Select  ↑/↓: Scroll  Tab: Switch Panel  esc: Close",
                    id="de-placeholder",
                )
        yield Static("", id="de-footer")

    def on_mount(self) -> None:
        self.title = f"Diff: {self._project_dir.name}"
        panel = self.query_one("#de-file-list", VerticalScroll)
        panel.styles.width = self._file_list_width
        self._load_modified_files()

    @work(exclusive=True, thread=True)
    def _load_modified_files(self) -> None:
        files = get_modified_files(self._project_dir)
        self.app.call_from_thread(self._on_files_loaded, files)

    def _on_files_loaded(self, files: list[ModifiedFile]) -> None:
        self._modified_files = list(files)
        self._loading = False

        if not files:
            self.query_one("#de-header", Static).update(
                "[b]📝 Diff[/b]  [#888888]No changes in working tree[/]"
            )
            self.query_one("#de-footer", Static).update(" j/k: Select  ↑/↓: Scroll  Tab: Switch Panel  esc: Close")
            return

        tree = _build_file_tree(files)
        self._tree_entries = _flatten_tree(tree)
        self._file_entries = [e for e in self._tree_entries if e["type"] == "file"]

        self._update_header()
        self._update_footer()

        if self.highlighted_index >= len(self._file_entries):
            self.highlighted_index = 0
        self._render_file_list()
        self._scroll_to_highlighted()
        self._load_selected_diff()
        self.query_one("#de-file-list", VerticalScroll).focus()

    def _highlighted_filepath(self) -> str | None:
        idx = self.highlighted_index
        if 0 <= idx < len(self._file_entries):
            return self._file_entries[idx]["mf"].filepath
        return None

    def _update_header(self) -> None:
        files = self._modified_files
        count = len(files)
        total_added = sum(f.added for f in files)
        total_deleted = sum(f.deleted for f in files)
        self.query_one("#de-header", Static).update(
            f"[b]📝 Diff: {self._project_dir.name}[/b]  "
            f"[#888888]{count} file{'s' if count != 1 else ''}[/]  "
            f"[green]+{total_added}[/]/[red]-{total_deleted}[/]"
        )

    def _update_footer(self) -> None:
        files = self._file_entries
        if not files:
            return
        current = self.highlighted_index
        idx_display = f"{current + 1}/{len(files)}" if 0 <= current < len(files) else "?/?"
        self.query_one("#de-footer", Static).update(
            f" j/k: Select  ↑/↓: Scroll  "
            f"Tab: Switch Panel  esc: Close  [{idx_display}]"
        )

    def _render_file_list(self) -> None:
        hfp = self._highlighted_filepath()
        panel_width = max(self._file_list_width, _FILE_LIST_MIN_WIDTH)

        lines = _render_file_tree_lines(
            self._tree_entries, hfp, panel_width
        )
        content = self.query_one("#de-file-list-content", Static)
        content.update("\n".join(lines))

    def _scroll_to_highlighted(self) -> None:
        panel = self.query_one("#de-file-list", VerticalScroll)
        self.call_after_refresh(lambda: self._do_scroll_to_highlighted(panel))

    def _do_scroll_to_highlighted(self, panel: VerticalScroll) -> None:
        hfp = self._highlighted_filepath()
        if hfp is None:
            return

        for i, entry in enumerate(self._tree_entries):
            if entry["type"] == "file" and entry["mf"].filepath == hfp:
                target_y = i
                break
        else:
            return

        try:
            line_height = panel.virtual_size.height / max(
                len(self._tree_entries), 1
            )
        except ZeroDivisionError:
            line_height = 1

        target_scroll = target_y * line_height
        view_height = panel.size.height

        if target_scroll < panel.scroll_y:
            panel.scroll_to(y=max(0, target_scroll), animate=False)
        elif target_scroll + line_height > panel.scroll_y + view_height:
            panel.scroll_to(
                y=max(0, target_scroll - view_height + line_height),
                animate=False,
            )

    def watch_highlighted_index(self, old: int, new: int) -> None:
        if self._loading or not self._file_entries:
            return
        self._render_file_list()
        self._scroll_to_highlighted()
        self._update_footer()
        self._load_selected_diff()

    def watch__file_list_width(self, old: int, new: int) -> None:
        try:
            panel = self.query_one("#de-file-list", VerticalScroll)
        except Exception:
            return
        panel.styles.width = new
        self._render_file_list()

    @work(exclusive=True, group="diff-explorer-load-diff", thread=True)
    def _load_selected_diff(self) -> None:
        idx = self.highlighted_index
        if idx < 0 or idx >= len(self._file_entries):
            return
        mf = self._file_entries[idx]["mf"]
        before, after = get_file_diff_content(self._project_dir, mf.filepath)
        self.app.call_from_thread(self._render_diff, mf, before, after)

    def _render_diff(
        self, mf: ModifiedFile, before: str | None, after: str | None
    ) -> None:
        diff_panel = self.query_one("#de-diff-panel", VerticalScroll)
        for child in list(diff_panel.children):
            child.remove()

        if before is None and after is None:
            diff_panel.mount(
                Static(
                    "No diff content available\n"
                    "(file may be binary, empty, or unchanged)",
                    id="de-placeholder",
                )
            )
            return

        diff_view = make_diff(mf.filepath, mf.filepath, before, after or "")
        diff_view.styles.width = "100%"
        diff_view.styles.height = "auto"
        diff_panel.mount(diff_view)

    def action_next_file(self) -> None:
        files = self._file_entries
        if not files:
            return
        if self.highlighted_index < len(files) - 1:
            self.highlighted_index += 1

    def action_prev_file(self) -> None:
        if self.highlighted_index > 0:
            self.highlighted_index -= 1

    def action_scroll_down(self) -> None:
        try:
            diff_panel = self.query_one("#de-diff-panel", VerticalScroll)
            diff_panel.scroll_relative(y=1, animate=False)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        try:
            diff_panel = self.query_one("#de-diff-panel", VerticalScroll)
            diff_panel.scroll_relative(y=-1, animate=False)
        except Exception:
            pass

    def action_dismiss(self) -> None:
        self.dismiss(None)


