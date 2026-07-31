"""Tests for the AgentThought widget.

Verifies:
- Markdown rendering of the content area (bold, italic, code, lists).
- Header state transitions (running / completed expanded / collapsed).
- Ctrl+X toggle action.
- Click on header toggle.
- Sizing inside a VerticalScroll parent.
"""

from __future__ import annotations

import asyncio



class TestAgentThoughtMarkdownRendering:
    """Content area must render as Markdown, not raw text."""

    def test_content_uses_markdown_widget(self):
        """The composed content child must be a Markdown widget."""
        from tui.widgets.agent_thought import AgentThought

        # Inspect the compose output without mounting (faster than app boot)
        widget = AgentThought("**bold** _italic_ `code`", replay=True)
        from textual.app import App
        from textual.containers import Container

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Find the content widget inside AgentThought
                content = widget.query_one("#thought-content")
                return type(content).__name__

        result = asyncio.run(_run())
        assert result == "Markdown"

    def test_initial_content_is_preserved(self):
        """The Markdown widget receives the initial content as-is."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import Container

        widget = AgentThought("## header\n\n- item 1\n- item 2", replay=True)

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                md = widget.query_one("#thought-content")
                # The Markdown widget stores its source document
                return md.source

        src = asyncio.run(_run())
        assert "## header" in src
        assert "- item 1" in src

    def test_replay_thought_starts_completed_collapsed(self):
        """A replay-mode thought must start collapsed with '+ Thought'."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import Container

        widget = AgentThought("any content", replay=True)

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                header = widget.query_one("#thought-header")
                content = widget.query_one("#thought-content")
                return (
                    str(header.render()),
                    content.display,
                    widget._completed,
                    widget._collapsed,
                )

        header_text, content_display, completed, collapsed = asyncio.run(_run())
        assert header_text == "+ Thought"
        assert content_display is False
        assert completed is True
        assert collapsed is True

    def test_running_thought_starts_with_thinking_header(self):
        """A non-replay thought must show '⏳ thinking:' until completed."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import Container

        widget = AgentThought("analyzing...")  # replay=False default

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                return str(widget.query_one("#thought-header").render())

        assert asyncio.run(_run()) == "⏳ thinking:"

    def test_mark_completed_removes_widget(self):
        """After mark_completed, the widget is removed from the DOM."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import Container

        widget = AgentThought("reasoning…")

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                parent = widget.parent
                assert widget in parent.children
                widget.mark_completed()
                await pilot.pause()
                return widget not in parent.children

        assert asyncio.run(_run())

    def test_ctrl_x_toggle_before_completion(self):
        """Ctrl+X only works before completion; after mark_completed widget is removed."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import Container

        widget = AgentThought("body")

        class _ProbeApp(App):
            def compose(self):
                with Container():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Before completion: starts expanded with "⏳ thinking:"
                h0 = str(widget.query_one("#thought-header").render())
                d0 = widget.query_one("#thought-content").display
                widget.action_toggle()  # collapse
                await pilot.pause()
                h1 = str(widget.query_one("#thought-header").render())
                d1 = widget.query_one("#thought-content").display
                return (h0, d0, h1, d1)

        h0, d0, h1, d1 = asyncio.run(_run())
        assert h0 == "⏳ thinking:"
        assert d0 is True
        assert h1 == "⏳ thinking:"
        assert d1 is False

    def test_agent_thought_has_min_height_inside_verticalscroll(self):
        """The widget must enforce height: auto + min-height: 3 so it
        doesn't collapse to 0 inside a VerticalScroll parent."""
        from tui.widgets.agent_thought import AgentThought
        from textual.app import App
        from textual.containers import VerticalScroll

        widget = AgentThought("x")

        class _ProbeApp(App):
            def compose(self):
                with VerticalScroll():
                    yield widget

        app = _ProbeApp()
        async def _run():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Read the inline styles we set in on_mount
                return (
                    widget.styles.height,
                    widget.styles.min_height,
                )

        height, min_height = asyncio.run(_run())
        # height should be 'auto' (SymbolicTextual value)
        assert "auto" in str(height)
        # min-height should be 3 (SymbolicTextual value of 3)
        assert "3" in str(min_height)
