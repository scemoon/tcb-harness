"""Tests for the structured ``<minimax:tool_call>`` parser added in step 1
and the daily-rotation logging added in step 5.

These complement the existing ``test_streaming.py`` and ``test_session.py``
suites — they pin behaviour that the legacy / bare-markdown parsers cannot
cover.
"""

from __future__ import annotations

import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────
# <minimax:tool_call> parser
# ─────────────────────────────────────────────────────────────────────


class TestMinimaxToolCallParser:
    def test_single_invoke(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text = (
            "before <minimax:tool_call>"
            '<invoke name="Read">'
            '<parameter name="path">SPEC.md</parameter>'
            "</invoke>"
            "</minimax:tool_call> after"
        )
        uses, cleaned, next_id = _extract_minimax_tool_uses(text)
        assert uses == [
            {"id": "minimax-1", "name": "Read", "input": {"path": "SPEC.md"}},
        ]
        assert "<minimax:tool_call>" not in cleaned
        assert "Read" not in cleaned
        assert "before " in cleaned and "after" in cleaned
        assert next_id == 1

    def test_multiple_invokes(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text = (
            "<minimax:tool_call>"
            '<invoke name="List">'
            '<parameter name="path">.</parameter>'
            "</invoke>"
            '<invoke name="Read">'
            '<parameter name="path">SPEC.md</parameter>'
            "</invoke>"
            "</minimax:tool_call>"
        )
        uses, _, next_id = _extract_minimax_tool_uses(text)
        assert [u["name"] for u in uses] == ["List", "Read"]
        assert [u["id"] for u in uses] == ["minimax-1", "minimax-2"]
        assert uses[1]["input"] == {"path": "SPEC.md"}
        assert next_id == 2

    def test_multiline_parameter_value(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text = (
            "<minimax:tool_call>"
            '<invoke name="Write">'
            '<parameter name="content">line1\nline2\nline3</parameter>'
            '<parameter name="path">/tmp/x</parameter>'
            "</invoke>"
            "</minimax:tool_call>"
        )
        uses, _, _ = _extract_minimax_tool_uses(text)
        assert len(uses) == 1
        assert uses[0]["input"]["content"] == "line1\nline2\nline3"
        assert uses[0]["input"]["path"] == "/tmp/x"

    def test_xml_unescape(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text = (
            "<minimax:tool_call>"
            '<invoke name="Bash">'
            '<parameter name="command">echo &lt;tag&gt; &amp; &quot;hi&quot;</parameter>'
            "</invoke>"
            "</minimax:tool_call>"
        )
        uses, _, _ = _extract_minimax_tool_uses(text)
        assert uses[0]["input"]["command"] == 'echo <tag> & "hi"'

    def test_id_counter_continues(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text1 = (
            "<minimax:tool_call>"
            '<invoke name="A"><parameter name="x">1</parameter></invoke>'
            "</minimax:tool_call>"
        )
        text2 = (
            "<minimax:tool_call>"
            '<invoke name="B"><parameter name="x">2</parameter></invoke>'
            "</minimax:tool_call>"
        )
        uses1, _, next1 = _extract_minimax_tool_uses(text1, id_start=10)
        uses2, _, next2 = _extract_minimax_tool_uses(text2, id_start=next1)
        assert uses1[0]["id"] == "minimax-11"
        assert uses2[0]["id"] == "minimax-12"
        assert next2 == 12

    def test_no_minimax_block_returns_empty(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        uses, cleaned, next_id = _extract_minimax_tool_uses("plain text only")
        assert uses == []
        assert cleaned == "plain text only"
        assert next_id == 0

    def test_unclosed_block_left_in_place(self):
        from cdha.agent.engine import _extract_minimax_tool_uses
        text = "<minimax:tool_call><invoke name=\"X\"/></invoke>"  # no close
        uses, cleaned, _ = _extract_minimax_tool_uses(text)
        assert uses == []  # regex requires both tags
        assert text in cleaned  # left in buffer for the next pass


# ─────────────────────────────────────────────────────────────────────
# Instance tool_id_counter — pins the P0-2 fix
# ─────────────────────────────────────────────────────────────────────


class TestInstanceToolIdCounter:
    def test_counter_initialized_to_zero(self):
        from cdha.agent.engine import AgentEngine
        e = AgentEngine(app=MagicMock())
        assert e._tool_id_counter == 0

    def test_counter_persists_across_legacy_extractions(self):
        from cdha.agent.engine import AgentEngine, _extract_legacy_tool_uses

        e = AgentEngine(app=MagicMock())
        text1 = '[TOOL_CALL]{tool => "Read", args => {--path "/a"}}[/TOOL_CALL]'
        text2 = '[TOOL_CALL]{tool => "Write", args => {--path "/b"}}[/TOOL_CALL]'

        uses1, _, _ = _extract_legacy_tool_uses(text1, id_start=e._tool_id_counter)
        e._tool_id_counter += len(uses1)
        uses2, _, _ = _extract_legacy_tool_uses(text2, id_start=e._tool_id_counter)
        e._tool_id_counter += len(uses2)

        assert uses1[0]["id"] == "legacy-1"
        assert uses2[0]["id"] == "legacy-2"
        assert e._tool_id_counter == 2

    def test_minimax_then_legacy_no_collision(self):
        from cdha.agent.engine import (
            AgentEngine, _extract_minimax_tool_uses, _extract_legacy_tool_uses,
        )

        e = AgentEngine(app=MagicMock())

        minimax_text = (
            "<minimax:tool_call>"
            '<invoke name="Read"><parameter name="path">/a</parameter></invoke>'
            "</minimax:tool_call>"
        )
        legacy_text = '[TOOL_CALL]{tool => "Bash", args => {--command "ls"}}[/TOOL_CALL]'

        uses1, _, _ = _extract_minimax_tool_uses(minimax_text, id_start=e._tool_id_counter)
        e._tool_id_counter += len(uses1)
        uses2, _, _ = _extract_legacy_tool_uses(legacy_text, id_start=e._tool_id_counter)
        e._tool_id_counter += len(uses2)

        assert uses1[0]["id"] == "minimax-1"
        assert uses2[0]["id"] == "legacy-2"
        assert e._tool_id_counter == 2


# ─────────────────────────────────────────────────────────────────────
# Filter / stream callback — confirm both formats stripped
# ─────────────────────────────────────────────────────────────────────


class TestFilterAndStreamBothFormats:
    def test_filter_strips_minimax_block(self):
        from cdha.agent.cdh_agent_acp import _filter_tool_call_text
        text = (
            'hello <minimax:tool_call>'
            '<invoke name="Read"><parameter name="path">/f</parameter></invoke>'
            '</minimax:tool_call> world'
        )
        out = _filter_tool_call_text(text)
        assert "<minimax:tool_call>" not in out
        assert "Read" not in out
        assert "hello " in out and "world" in out

    def test_filter_strips_mixed_formats(self):
        from cdha.agent.cdh_agent_acp import _filter_tool_call_text
        text = (
            'a <minimax:tool_call><invoke name="X">'
            '<parameter name="p">v</parameter></invoke></minimax:tool_call>'
            'b [TOOL_CALL]{tool => "Y"}[/TOOL_CALL] c'
        )
        out = _filter_tool_call_text(text)
        assert "minimax" not in out
        assert "TOOL_CALL" not in out
        assert "a b c" == out.replace("  ", " ").strip() or out.strip() == "a b c"

    def test_stream_callback_strips_minimax_across_chunks(self):
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        a = CDHACPAdapter()
        sent = []
        a.send_session_update = lambda u: sent.append(u)
        cb = a._make_stream_callback()

        cb("hi <minimax:tool_call>")
        cb('<invoke name="Read"><parameter name="path">SPEC</parameter>')
        cb("</invoke></minimax:tool_call> bye")

        emitted = "".join(
            u["content"]["text"]
            for u in sent
            if u.get("sessionUpdate") == "agent_message_chunk"
        )
        assert "minimax" not in emitted
        assert "hi" in emitted and "bye" in emitted


# ─────────────────────────────────────────────────────────────────────
# ProviderError hierarchy
# ─────────────────────────────────────────────────────────────────────


class TestProviderErrorClassification:
    def test_429_is_rate_limit(self):
        from cdha.models.errors import RateLimitError
        from cdha.models.provider import Provider
        err = Provider.classify_http_error(429, "rate limit", retry_after=60.0)
        assert isinstance(err, RateLimitError)
        assert err.retry_after == 60.0
        assert "60" in err.to_user_message()

    def test_401_is_auth_error(self):
        from cdha.models.errors import AuthError
        from cdha.models.provider import Provider
        err = Provider.classify_http_error(401, "invalid api key")
        assert isinstance(err, AuthError)

    def test_5xx_is_transient(self):
        from cdha.models.errors import TransientProviderError
        from cdha.models.provider import Provider
        for code in (500, 502, 503, 504):
            assert isinstance(
                Provider.classify_http_error(code, "boom"),
                TransientProviderError,
            )

    def test_400_with_context_length(self):
        from cdha.models.errors import ContextLengthError
        from cdha.models.provider import Provider
        err = Provider.classify_http_error(
            400, "context length exceeded for model"
        )
        assert isinstance(err, ContextLengthError)

    def test_400_without_context_length_is_generic(self):
        from cdha.models.errors import ProviderError
        from cdha.models.provider import Provider
        err = Provider.classify_http_error(400, "bad request")
        assert type(err) is ProviderError

    def test_body_truncated(self):
        from cdha.models.provider import Provider
        err = Provider.classify_http_error(500, "x" * 10_000)
        assert len(err.body) == 4096  # 4 KiB cap


# ─────────────────────────────────────────────────────────────────────
# Daily log rotation
# ─────────────────────────────────────────────────────────────────────


class TestDailyLogRotation:
    def test_handler_attached_with_midnight_when(self, tmp_path: Path, monkeypatch):
        from cdha.cli import setup_logging, LOG_DIR

        # Redirect LOG_DIR to a temp path so we don't pollute ~/.cdha.
        monkeypatch.setattr("cdha.cli.LOG_DIR", tmp_path)
        monkeypatch.setattr("cdha.cli.LOG_FILE", tmp_path / "cdh.log")

        root = setup_logging("INFO")
        try:
            rotating = [
                h for h in root.handlers
                if isinstance(h, TimedRotatingFileHandler)
            ]
            assert len(rotating) == 1
            # ``TimedRotatingFileHandler`` upper-cases ``when`` internally.
            assert rotating[0].when.upper() == "MIDNIGHT"
            assert rotating[0].backupCount == 7
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
                h.close()

    def test_log_writes_appear_in_file(self, tmp_path: Path, monkeypatch):
        from cdha.cli import setup_logging

        log_file = tmp_path / "cdh.log"
        monkeypatch.setattr("cdha.cli.LOG_DIR", tmp_path)
        monkeypatch.setattr("cdha.cli.LOG_FILE", log_file)

        root = setup_logging("INFO")
        try:
            logging.getLogger("cdha.agent.engine").info("engine log line")
            # Force a flush — TimedRotatingFileHandler buffers.
            for h in root.handlers:
                h.flush()
            contents = log_file.read_text(encoding="utf-8")
            assert "engine log line" in contents
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
                h.close()

    def test_default_level_is_info_not_warning(self, tmp_path: Path, monkeypatch):
        """Regression test for the original empty-cdh.log bug."""
        from cdha.cli import setup_logging

        log_file = tmp_path / "cdh.log"
        monkeypatch.setattr("cdha.cli.LOG_DIR", tmp_path)
        monkeypatch.setattr("cdha.cli.LOG_FILE", log_file)

        root = setup_logging("INFO")
        try:
            assert root.level == logging.INFO
            # The cdha namespace should now also be at INFO, not WARNING.
            assert logging.getLogger("cdha").level <= logging.INFO
            assert logging.getLogger("cdha.agent.engine").level <= logging.INFO
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
                h.close()


# ─────────────────────────────────────────────────────────────────────
# Sandbox rlimit — regression test for the "tools don't execute" bug
# ─────────────────────────────────────────────────────────────────────


class TestSandboxResourceLimits:
    """The sandbox was calling ``setrlimit(RLIMIT_AS, 512MB)`` on the
    parent Python process, which then prevented ``subprocess.run`` from
    forking the shell (it returned ``EAGAIN`` / ``Resource temporarily
    unavailable``), so every Bash invocation silently failed.

    The fix is to apply rlimits in a ``preexec_fn`` that runs only in
    the child process.  These tests pin that behaviour.
    """

    def test_sandbox_has_public_exec_method(self):
        """Regression: the edit accidentally dropped ``Sandbox.exec``."""
        from cdha.agent.tools.sandbox import Sandbox, SandboxConfig, SandboxMode
        from pathlib import Path

        sb = Sandbox(SandboxConfig(workspace_root=Path("/tmp"), mode=SandboxMode.NONE))
        assert hasattr(sb, "exec"), "Sandbox.exec is the public entry point"
        assert callable(sb.exec)

    def test_shell_exec_returns_success_for_simple_command(self, tmp_path):
        """A trivial ``echo`` should return ``success=True`` with stdout."""
        from cdha.agent.tools.file_ops import ShellTool

        sh = ShellTool(tmp_path)
        result = sh.exec("echo hello-from-cdh-sandbox-test", timeout=10)
        assert result.get("success") is True, (
            f"Shell tool failed: {result!r} — this is the regression where "
            "RLIMIT_AS=512MB was being applied to the parent process and "
            "broke subprocess.run."
        )
        assert "hello-from-cdh-sandbox-test" in result.get("stdout", "")

    def test_shell_exec_does_not_apply_rlimit_to_parent(self, tmp_path):
        """Verify the parent's address space is left alone.

        If the parent process is given a 512 MB RLIMIT_AS, the cdha import
        machinery (which already uses more than that) starts failing with
        ``BlockingIOError: [Errno 35] Resource temporarily unavailable``
        on the very next ``subprocess.run`` call.
        """
        import resource

        from cdha.agent.tools.file_ops import ShellTool

        before = resource.getrlimit(resource.RLIMIT_AS)
        sh = ShellTool(tmp_path)
        sh.exec("true", timeout=5)
        after = resource.getrlimit(resource.RLIMIT_AS)
        assert before == after, (
            f"ShellTool.exec shrank the parent RLIMIT_AS from {before} "
            f"to {after} — limits must be applied in the child only."
        )
