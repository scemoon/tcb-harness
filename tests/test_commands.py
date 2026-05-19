import pytest
from cdh.tui.commands.registry import CommandRegistry


def test_command_registry():
    assert CommandRegistry.get_handler("help") is not None
    assert CommandRegistry.get_handler("mode") is not None
    assert CommandRegistry.get_handler("nonexistent") is None


def test_dispatch_unknown():
    result = CommandRegistry.dispatch(None, "/foobar")
    assert "Unknown command" in result


def test_dispatch_empty():
    result = CommandRegistry.dispatch(None, "")
    assert "Empty" in result


class FakeApp:
    current_mode = "agent"
    current_model = "claude-3-opus-20240229"
    current_provider = "anthropic"
    current_cloud = "tcb"
    current_project = None
    config = None
    lifecycle = None
    tracer = None
    session_store = None
    _session = None
    agent = None

    def query_one(self, *args, **kwargs):
        return self

    def sync(self, *args, **kwargs):
        pass


def test_dispatch_mode():
    app = FakeApp()
    from cdh.config import GlobalConfig
    from cdh.lifecycle.manager import LifecycleManager
    from cdh.storage.session import SessionStore
    from cdh.trace.tracer import Tracer
    from cdh.agent.engine import AgentEngine
    app.config = GlobalConfig()
    app.lifecycle = LifecycleManager()
    app.tracer = Tracer()
    app.session_store = SessionStore()
    app.agent = AgentEngine(app)

    # Fake show_config_panel for commands that display panels
    app.show_config_panel = lambda *a, **kw: None

    result = CommandRegistry.dispatch(app, "/mode")
    assert result == ""

    result = CommandRegistry.dispatch(app, "/mode plan")
    assert "plan" in result
    assert app.current_mode == "plan"


def test_dispatch_help():
    result = CommandRegistry.dispatch(None, "/help")
    assert "Available commands" in result
