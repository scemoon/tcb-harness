import pytest
import tempfile
import os
from pathlib import Path

from cdh.agent.session import AgentSession, SessionData
from cdh.agent.hooks import HookManager, HookContext, HookResult, HookEvent
from cdh.agent.permissions import (
    PermissionChecker, PermissionSet, PermissionResult,
    PathRule, CommandRule, create_safe_permission_set
)
from cdh.agent.attachments import AttachmentSet, Attachment


class TestSessionData:
    def test_create_empty(self):
        sd = SessionData()
        assert sd.name == "Untitled"
        assert sd.messages == []

    def test_to_from_dict(self):
        sd = SessionData(name="test", mode="agent", messages=[{"role": "user", "content": "hello"}])
        d = sd.to_dict()
        assert d["name"] == "test"
        assert d["messages"][0]["content"] == "hello"
        sd2 = SessionData.from_dict(d)
        assert sd2.name == sd.name
        assert sd2.messages[0]["content"] == "hello"


class TestAgentSession:
    def test_create_and_save(self, tmp_path):
        session = AgentSession(storage_path=tmp_path)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")
        session.save()
        assert (tmp_path / f"{session.id}.json").exists()

    def test_load_session(self, tmp_path):
        session1 = AgentSession(storage_path=tmp_path)
        session1.add_message("user", "Test")
        session1.save()
        session2 = AgentSession(session_id=session1.id, storage_path=tmp_path)
        assert session2.load()
        assert len(session2.messages) == 1

    def test_compact_messages(self, tmp_path):
        session = AgentSession(storage_path=tmp_path)
        for i in range(5):
            session.add_message("user", f"Message {i}")
        # compact_messages replaces all non-system messages with a single summarized message
        session.compact_messages("Summarized content")
        # After compaction: system message with summarized content
        assert len(session.messages) == 1
        assert "Summarized content" in session.messages[0]["content"]


class TestPermissionSet:
    def test_path_rule_matches_exact(self):
        rule = PathRule("*.py", PermissionResult.ALLOW)
        assert rule.matches("foo.py")
        assert not rule.matches("src/foo.py")

    def test_path_rule_matches_glob(self):
        rule = PathRule("**/*.py", PermissionResult.ALLOW)
        assert rule.matches("foo.py")
        assert rule.matches("src/foo.py")

    def test_command_rule_matches(self):
        rule = CommandRule("rm *", PermissionResult.DENY)
        assert rule.matches("rm file.txt")
        assert not rule.matches("ls")
        s1 = AgentSession(storage_path=tmp_path)
        s1.save()
        s2 = AgentSession(storage_path=tmp_path)
        s2.save()
        sessions = AgentSession.list_sessions(storage_path=tmp_path)
        assert len(sessions) == 2


class TestHookManager:
    def test_register_pre_tool_hook(self):
        manager = HookManager()
        called = []

        def my_hook(ctx):
            called.append(ctx.tool_name)
            return HookResult(allowed=True)

        manager.register_pre_tool(my_hook)
        ctx = HookContext(agent_name="build", tool_name="Bash", args={"command": "ls"})
        result = manager.run_pre_tool(ctx)
        assert result.allowed
        assert called == ["Bash"]

    def test_pre_tool_hook_blocks(self):
        manager = HookManager()

        def block_hook(ctx):
            return HookResult(allowed=False, error="Blocked")

        manager.register_pre_tool(block_hook)
        ctx = HookContext(agent_name="build", tool_name="Bash", args={"command": "ls"})
        result = manager.run_pre_tool(ctx)
        assert not result.allowed
        assert result.error == "Blocked"

    def test_post_tool_hook_modifies_result(self):
        manager = HookManager()

        def modify_hook(ctx, tool_result):
            return HookResult(data="modified")

        manager.register_post_tool(modify_hook)
        ctx = HookContext(agent_name="build", tool_name="Bash", args={"command": "ls"})
        result = manager.run_post_tool(ctx, "original")
        assert result == "modified"

    def test_hook_clear(self):
        manager = HookManager()
        manager.register_pre_tool(lambda ctx: HookResult())
        manager.clear()
        assert len(manager._pre_tool_hooks) == 0


class TestPermissionSet:
    def test_path_rule_matches_glob(self):
        rule = PathRule("*.py", PermissionResult.ALLOW)
        assert rule.matches("foo.py")
        assert not rule.matches("foo.txt")

    def test_path_rule_matches_nested(self):
        rule = PathRule("src/*.py", PermissionResult.ALLOW)
        assert rule.matches("src/foo.py")
        assert not rule.matches("foo.py")

    def test_command_rule_matches(self):
        rule = CommandRule("rm *", PermissionResult.DENY)
        assert rule.matches("rm file.txt")
        assert not rule.matches("ls")

    def test_check_path_default(self):
        ps = PermissionSet()
        assert ps.check_path("anything") == PermissionResult.ALLOW

    def test_check_command_with_rule(self):
        ps = PermissionSet()
        ps.deny_command("rm -rf /*")
        assert ps.check_command("rm -rf /") == PermissionResult.DENY
        assert ps.check_command("ls") == PermissionResult.ALLOW


class TestPermissionChecker:
    def test_safe_permission_set_blocks_dangerous(self):
        ps = create_safe_permission_set()
        checker = PermissionChecker(ps)
        result = checker.check_command("rm -rf /*")
        assert result == PermissionResult.DENY

    def test_ask_requires_approval(self):
        ps = PermissionSet()
        ps.ask_command("sudo *")
        checker = PermissionChecker(ps)
        result = checker.check_command("sudo rm file")
        assert result == PermissionResult.ASK

    def test_is_allowed_helper(self):
        ps = PermissionSet()
        ps.deny_path("**/secrets/**")
        checker = PermissionChecker(ps)
        assert checker.is_allowed(ps.check_path("foo.py"))
        assert not checker.is_allowed(ps.check_path("src/secrets/config"))
        assert checker.is_denied(ps.check_path("src/secrets/config"))
        assert not checker.is_denied(ps.check_path("foo.py"))


class TestAttachmentSet:
    def test_attach_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        aset = AttachmentSet()
        att = aset.attach(str(f))
        assert att.content == "hello world"
        assert att.error is None

    def test_attach_nonexistent(self):
        aset = AttachmentSet()
        att = aset.attach("/nonexistent/file.txt")
        assert att.error == "File not found"

    def test_attach_file_too_large(self, tmp_path):
        f = tmp_path / "large.bin"
        f.write_bytes(b"x" * (11 * 1024 * 1024))
        aset = AttachmentSet()
        att = aset.attach(str(f))
        assert "too large" in att.error

    def test_attach_with_alias(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        aset = AttachmentSet()
        att = aset.attach(str(f), alias="My File")
        assert att.name == "My File"

    def test_get_context_text(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        aset = AttachmentSet()
        aset.attach(str(f))
        ctx = aset.get_context_text()
        assert "Attachment 1" in ctx
        assert "test.txt" in ctx

    def test_remove(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        aset = AttachmentSet()
        aset.attach(str(f))
        assert len(aset.list()) == 1
        aset.remove(0)
        assert len(aset.list()) == 0

    def test_clear(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        aset = AttachmentSet()
        aset.attach(str(f))
        aset.clear()
        assert len(aset.list()) == 0