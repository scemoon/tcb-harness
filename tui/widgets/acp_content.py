from textual import containers
from textual.app import ComposeResult
from textual import widgets
from tui.acp.protocol import ToolCallContent


_WRITE_ICON = "✏️ "


def _header_path(content_blocks: list[ToolCallContent]) -> str:
    """Extract filename from content blocks for use in the permission header."""
    for block in content_blocks:
        text = ""
        match block:
            case {"type": "content", "content": {"type": "text", "text": t}}:
                text = t
            case {"type": "resource", "resource": {"uri": uri}}:
                return uri.rsplit("/", 1)[-1] if "/" in uri else uri
            case {"type": "diff", "path": path}:
                return path
        if text:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("📄 "):
                    return line[2:].strip()
    return ""


class ACPToolCallContent(containers.VerticalGroup):

    def __init__(
        self,
        content: list[ToolCallContent],
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._content = content
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        for content in self._content:
            match content:
                case {
                    "type": "content",
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                }:
                    yield widgets.Markdown(text)
                case {
                    "type": "diff",
                    "oldText": old_text,
                    "newText": new_text,
                    "path": path,
                }:
                    from tui.widgets.diff_view import make_diff

                    yield make_diff(path, path, old_text, new_text)
                case {"type": "resource", "resource": res}:
                    text = res.get("text", "") or res.get("blob", "") or ""
                    mime = res.get("mimeType", "")
                    if text:
                        yield widgets.Markdown(f"```\n{text}\n```")
                case {"type": "text", "text": text}:
                    yield widgets.Markdown(text)
                case _:
                    import json
                    yield widgets.Static(json.dumps(content, indent=2, ensure_ascii=False))
