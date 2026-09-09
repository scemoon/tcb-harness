from __future__ import annotations

import asyncio
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static, ProgressBar


class OllamaModelStatus(Static):
    class DownloadStarted(Message):
        def __init__(self, model_id: str) -> None:
            self.model_id = model_id
            super().__init__()

    class DownloadCompleted(Message):
        def __init__(self, model_id: str, success: bool) -> None:
            self.model_id = model_id
            self.success = success
            super().__init__()

    downloading: reactive[bool] = reactive(False)
    progress: reactive[float] = reactive(0.0)

    def __init__(self, model_id: str, ollama_name: str, description: str = ""):
        super().__init__()
        self.model_id = model_id
        self.ollama_name = ollama_name
        self.description = description
        self._installed = False

    def set_installed(self, installed: bool) -> None:
        self._installed = installed
        self.refresh()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="model-row"):
            yield Static(self._status_icon(), id=f"icon-{self.model_id}")
            yield Static(self.model_id, classes="model-name")
            if self.description:
                yield Static(f"({self.description})", classes="model-desc")
            if self._installed:
                yield Static("已安装", classes="status-ready")
            elif self.downloading:
                yield ProgressBar(
                    total=100,
                    show_eta=False,
                    id=f"progress-{self.model_id}",
                )
                yield Static(
                    f"{self.progress:.0f}%",
                    id=f"pct-{self.model_id}",
                    classes="progress-text",
                )
            else:
                yield Button(
                    "下载",
                    id=f"dl-{self.model_id}",
                    classes="dl-btn small",
                )

    def _status_icon(self) -> str:
        if self._installed:
            return "[green]✓[/green]"
        elif self.downloading:
            return "[yellow]⏬[/yellow]"
        return "[dim]○[/dim]"

    def watch_downloading(self, value: bool) -> None:
        self.refresh()

    def watch_progress(self, value: float) -> None:
        if self.downloading:
            try:
                bar = self.query_one(f"#progress-{self.model_id}", ProgressBar)
                bar.update(progress=min(value, 100))
                pct = self.query_one(f"#pct-{self.model_id}", Static)
                pct.update(f"{value:.0f}%")
            except Exception:
                pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith(f"dl-{self.model_id}"):
            self.post_message(self.DownloadStarted(self.model_id))


class OllamaStatusPanel(Static):
    DEFAULT_CSS = """
    OllamaStatusPanel {
        height: auto;
        padding: 1 2;
        border: solid $secondary-muted;
        margin: 1 0;
        background: $surface;
    }

    .panel-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .model-row {
        height: auto;
        layout: horizontal;
        spacing: 1;
        padding: 0 1;
    }

    .model-name {
        color: $text;
    }

    .model-desc {
        color: $text-muted;
    }

    .status-ready {
        color: green;
    }

    .dl-btn {
        max-width: 8;
    }

    .progress-text {
        color: $text-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self._model_widgets: dict[str, OllamaModelStatus] = {}
        self._manager = None

    def set_manager(self, manager) -> None:
        self._manager = manager

    def add_model(self, model_id: str, ollama_name: str, description: str = "") -> OllamaModelStatus:
        widget = OllamaModelStatus(model_id, ollama_name, description)
        self._model_widgets[model_id] = widget
        return widget

    def compose(self) -> ComposeResult:
        yield Static("本地模型", classes="panel-title")
        yield Static("检测 Ollama 服务中...", id="ollama-status")
        yield Horizontal(
            id="models-container",
            classes="models-container",
        )

    async def refresh_status(self) -> None:
        if not self._manager:
            return

        status_text = self.query_one("#ollama-status", Static)
        container = self.query_one("#models-container", Horizontal)

        if not await self._manager.check_running():
            status_text.update("[red]✗ Ollama 服务未运行[/red]")
            status_text.update("请先安装并启动 Ollama\n安装: curl -fsSL https://ollama.com/install.sh | sh\n启动: ollama serve")
            container.display = False
            return

        status_text.update("[green]✓ Ollama 正常[/green]")
        container.display = True

        hardware = self._manager.detect_hardware()
        hardware_info = self._manager.get_hardware_info(hardware)
        recommended = self._manager.recommend(hardware)

        status_text.update(
            f"[green]✓ Ollama 正常[/green] | {hardware_info} | "
            f"推荐: [bold]{recommended or '无'}[/bold]"
        )

        installed = await self._manager.list_installed()

        if not self._model_widgets:
            for model_id, spec in self._manager.MODEL_SPECS.items():
                widget = self.add_model(
                    model_id,
                    spec["ollama_name"],
                    spec.get("description", ""),
                )
                await container.mount(widget)

        for model_id, widget in self._model_widgets.items():
            widget.set_installed(model_id in installed)

    async def on_download_started(self, event: OllamaModelStatus.DownloadStarted) -> None:
        model_id = event.model_id
        widget = self._model_widgets.get(model_id)
        if not widget or not self._manager:
            return

        widget.downloading = True
        widget.progress = 0.0

        try:

            async def progress_callback(data: dict) -> None:
                status = data.get("status", "")
                if "downloading" in status:
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)
                    if total > 0:
                        pct = (completed / total) * 100
                    else:
                        pct = 50.0
                elif "verifying" in status:
                    pct = 90.0
                elif "success" in data:
                    pct = 100.0
                else:
                    pct = 30.0
                widget.progress = pct

            await self._manager.pull_model(model_id, progress_callback=progress_callback)
            widget.downloading = False
            widget.set_installed(True)
            self.post_message(OllamaModelStatus.DownloadCompleted(model_id, True))
        except Exception as e:
            widget.downloading = False
            widget.set_installed(False)
            self.post_message(OllamaModelStatus.DownloadCompleted(model_id, False))
