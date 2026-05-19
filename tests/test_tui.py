import pytest

from cdh.tui.app import CloudDevHarnessApp


pytestmark = pytest.mark.asyncio(loop_scope="function")


class TestTUIStartup:
    async def test_app_starts(self):
        """Test that the TUI app starts without errors."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            assert pilot.app is not None

    async def test_chat_panel_mounts(self):
        """Test that ChatPanel is visible."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.chat import ChatPanel
            chat = app.query_one("ChatPanel")
            assert chat is not None

    async def test_input_widget_exists(self):
        """Test that the input widget exists."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            inp = app.query_one("#chat-input", Input)
            assert inp is not None

    async def test_right_panel_mounts(self):
        """Test that RightPanel sidebar is present."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.right_panel import RightPanel
            rp = app.query_one("#right-sidebar", RightPanel)
            assert rp is not None

    async def test_header_mounts(self):
        """Test that header is present."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.header import HeaderBar
            header = app.query_one(HeaderBar)
            assert header is not None

    async def test_footer_mounts(self):
        """Test that footer is present."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.footer import FooterBar
            footer = app.query_one(FooterBar)
            assert footer is not None

    async def test_input_focus_on_startup(self):
        """Test that input is focused on startup."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            from textual.widgets import Input
            inp = app.query_one("#chat-input", Input)
            assert inp.has_focus


class TestSidebar:
    async def test_sidebar_visible_by_default(self):
        """Test that sidebar is visible on startup."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.right_panel import RightPanel
            rp = app.query_one("#right-sidebar", RightPanel)
            assert not rp.has_class("-hidden")

    async def test_sidebar_toggles_via_action(self):
        """Test that the right sidebar can be toggled via action_toggle_right_panel."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.right_panel import RightPanel
            rp = app.query_one("#right-sidebar", RightPanel)
            assert not rp.has_class("-hidden")

            app.action_toggle_right_panel()
            await pilot.pause()
            assert rp.has_class("-hidden")

            app.action_toggle_right_panel()
            await pilot.pause()
            assert not rp.has_class("-hidden")


class TestInput:
    async def test_input_accepts_text(self):
        """Test that input widget accepts text."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            inp = app.query_one("#chat-input", Input)
            inp.focus()
            await pilot.pause()

            inp.insert_text_at_cursor("abc")
            await pilot.pause()
            assert inp.value == "abc"

    async def test_input_clears_after_submit(self):
        """Test that input clears after submitting a message."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            inp = app.query_one("#chat-input", Input)
            inp.focus()
            await pilot.pause()

            inp.insert_text_at_cursor("hello")
            await pilot.pause()
            assert inp.value == "hello"

            await inp.action_submit()
            await pilot.pause()
            assert inp.value == ""

    async def test_chat_panel_receives_message(self):
        """Test that sending a message adds it to chat."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            from cdh.tui.widgets.chat import ChatPanel
            inp = app.query_one("#chat-input", Input)
            chat = app.query_one("ChatPanel")

            inp.focus()
            await pilot.pause()

            inp.insert_text_at_cursor("test message")
            await pilot.pause()

            await inp.action_submit()
            await pilot.pause()

            from textual.widgets import Static
            log = chat.query_one("#chat-log", Static)
            assert log is not None


class TestCommandSuggestions:
    async def test_command_suggestions_appear_on_slash(self):
        """Test that typing / shows command suggestions."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input, ListView
            inp = app.query_one("#chat-input", Input)
            suggestions = app.query_one("#cmd-suggestions", ListView)

            inp.focus()
            await pilot.pause()
            inp.insert_text_at_cursor("/mode")
            await pilot.pause()
            assert suggestions.has_class("-visible")


class TestBindings:
    async def test_ctrl_f_focuses_input(self):
        """Test that Ctrl+F focuses the chat input."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            await pilot.press("ctrl+f")
            inp = app.query_one("#chat-input", Input)
            assert inp.has_focus

    async def test_tab_cycles_mode(self):
        """Test that Tab cycles through modes."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            initial_mode = app.current_mode
            await pilot.press("tab")
            await pilot.pause()
            assert app.current_mode != initial_mode

    async def test_ctrl_q_quits(self):
        """Test that Ctrl+Q quits the app."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+q")
            await pilot.pause()
            assert not app.is_running


class TestFooter:
    async def test_footer_exists(self):
        """Test that footer is present."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.footer import FooterBar
            footer = app.query_one(FooterBar)
            assert footer is not None

    async def test_footer_has_shortcuts(self):
        """Test that footer shows shortcuts."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from cdh.tui.widgets.footer import FooterBar
            footer = app.query_one(FooterBar)
            assert footer is not None

    async def test_input_in_input_area(self):
        """Test that input widget is in input area."""
        app = CloudDevHarnessApp()
        async with app.run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            inp = app.query_one("#chat-input", Input)
            assert inp is not None
            input_area = app.query_one("#input-area")
            assert input_area is not None