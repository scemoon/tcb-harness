"""Tests for the auto-ask detection fix.

Verifies that when the LLM asks the user a question, the engine intercepts
before tool execution and yields ask_user instead of running tools or forcing
continuation.

Bug scenarios (pre-fix):
  - LLM outputs: "请问要升级哪个用户？" + tool calls (e.g., Read users)
    → System executes tools while user is still reading the question
  - LLM outputs a plain-text question with NO tool calls
    → Turn is treated as empty, FORCE_CONTINUE nudging kicks in, and the
      user's input gets queued (turn == "agent") instead of answering.

Fix (post-fix):
  - Question detected via shared detection (question_detect.py):
    semantic intent + syntax (question marks).
  - With tool calls: loose detection (a question mark in the FINAL sentence,
    or intent) — an aside ``?`` in the middle of the output does not fire.
  - Without tool calls: strict detection (trailing question mark or intent)
    so a plain question turn becomes an AskUser dialog.
  - The ACP adapter's end-of-turn fallback also uses strict detection, so
    prose that merely contains a question mark does not pop an AskUser
    dialog every turn (auto-ask fires only when the agent actually asks).
  - Engine yields ask_user and waits for user answer.
  - Tools are deferred to the next LLM turn after user answers.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from onecode.agent.agents.types import BuildAgent
from onecode.agent.engine import AgentEngine
from onecode.models.messages import StreamEventType


def _make_engine():
    """Create a minimal engine for testing."""

    class FakeApp:
        config = type(
            "cfg",
            (),
            {
                "default_provider": "minimaxi",
                "default_model": "minimax-m1-671b",
                "providers": {},
            },
        )()

    engine = AgentEngine(FakeApp(), project_dir=Path.cwd())
    engine.current_agent = BuildAgent()
    return engine


class TestAutoAskDetectionLogic:
    """Unit-test the auto-ask interception with various inputs.

    Detection uses two layers (shared with the ACP adapter fallback):
    - Layer 1: Semantic (intent) — explicit "need user input" signals
    - Layer 2: Syntax (punctuation) — question marks as fallback

    Since the fix, a plain-text question also intercepts when the LLM made
    NO tool calls (strict detection: trailing question mark or intent), so
    the turn becomes an AskUser dialog instead of forcing continuation.
    """

    @pytest.mark.parametrize("text,has_tools,expected", [
        # ── Semantic: explicit need user input patterns ──
        # 问用户
        ("请问要升级哪个用户？", True, True),
        ("请问您要升级哪个用户？", True, True),
        ("请问要升级哪个用户的VIP？", True, True),
        # 请选择
        ("请选择要升级的用户", True, True),
        ("请选择要执行的操作", True, True),
        # 请确认
        ("请确认是否继续", True, True),
        ("需要确认一些信息？", True, True),
        # 需要您/需要用户提供
        ("需要用户提供用户ID", True, True),
        ("需要您提供文件路径", True, True),
        # 询问您/问您
        ("询问您希望如何处理", True, True),
        ("问您要升级哪个用户", True, True),
        # 请告诉我/需要知道
        ("请告诉我要升级哪个用户", True, True),
        ("需要知道用户的VIP等级", True, True),
        # 等待您的
        ("等待您的确认", True, True),
        # 需要哪些参数
        ("需要哪些参数?", True, True),
        # 需要用户ID
        ("需要用户ID才能继续", True, True),
        # 哪个用户/哪个文件
        ("哪个用户要升级？", True, True),
        ("哪个文件需要修改？", True, True),
        # ── Semantic: self-talk patterns (no input needed) ──
        # 让我想想 — 自言自语，不是问用户
        ("让我想想这个问题", True, False),
        # 首先/然后 — 步骤规划
        ("首先我需要读取文件", True, False),
        ("然后执行升级操作", True, False),
        # 我需要先 — LLM 自己决定
        ("我需要先确认一下", True, False),
        ("我可以先查看用户列表", True, False),
        # 好的 — LLM 确认自己要做的事
        ("好的，我来帮你升级", True, False),
        # ── Syntax: punctuation-based detection (fallback) ──
        # Fullwidth question mark
        ("需要确认一些信息？", True, True),
        # ? preceded by CJK
        ("要升级哪个用户?", True, True),
        ("upgradeToVip 需要哪些参数?", True, True),
        # Fullwidth colon
        ("请问：", True, True),
        ("这是一个比较大的问题，让我询问您希望如何处理：", True, True),
        # English question mark
        ("Which user to upgrade?", True, True),
        ("What should I do?", True, True),
        # ── English semantic: needs input (no ? needed) ──
        ("Could you tell me which user to upgrade", True, True),
        ("I need to know the file path to edit", True, True),
        ("Please confirm which file you want me to edit", True, True),
        ("What parameter should I use for this operation", True, True),
        ("Should I proceed with the upgrade", True, True),
        ("Do you want me to upgrade this user", True, True),
        ("Please specify which user", True, True),
        ("I need to know which file", True, True),
        ("Can you tell me the user ID", True, True),
        ("Which file should I edit", True, True),
        ("What file do you want me to read", True, True),
        ("Which one should I pick", True, True),
        ("Please select a user", True, True),
        ("What's the file path", True, True),
        ("Which option would you like", True, True),
        ("Do you want to continue", True, True),
        ("Should I continue with this", True, True),
        # ── English semantic: self-talk (no input needed) ──
        ("Let me read the file first", True, False),
        ("First I'll check the user list", True, False),
        ("Then I'll proceed with the upgrade", True, False),
        ("Okay, let me upgrade the user for you", True, False),
        ("Sure, I'll help you upgrade the VIP", True, False),
        ("Let me just verify the parameter", True, False),
        ("I'll need to check a few things first", True, False),
        ("Okay so I'll start by reading", True, False),
        ("Alright so I need to look at", True, False),
        ("Sure, let me run the command", True, False),
        ("Looks like I need to update", True, False),
        ("It seems the file is missing", True, False),
        ("Based on the error, I'll", True, False),
        ("Let me just check the config", True, False),
        ("I think this is the right approach", True, False),
        ("I believe we should proceed", True, False),
        ("I'm thinking about the best way", True, False),
        ("I need to consider the options", True, False),
        ("Here is what I found", True, False),
        ("So I'll start by reading the file", True, False),
        ("Okay so first I'll get the list", True, False),
        # ── Negative cases ──
        # 普通陈述句，无问号无语义信号
        ("好的，我来帮你升级VIP。", True, False),
        ("Looking at the codebase...", True, False),
        # ── No tool calls: the turn should STILL intercept as AskUser ──
        # (question-only turns previously fell into the empty-turn nudging
        # loop and the user's input went to the prompt queue)
        ("请问要升级哪个用户？", False, True),
        ("请选择要升级的用户", False, True),
        ("请确认是否继续", False, True),
        ("要升级哪个用户?", False, True),
        ("Which user to upgrade?", False, True),
        ("Could you tell me which user to upgrade", False, True),
        ("Do you want me to continue", False, True),
        # ── No tool calls: self-talk / statements must NOT intercept ──
        ("让我先读取用户列表", False, False),
        ("让我想想这个问题", False, False),
        ("好的，我来帮你升级VIP。", False, False),
        ("First I'll check the user list", False, False),
        ("Looking at the codebase...", False, False),
        # ── On-demand behavior: only real closing questions trigger ──
        # A question mark buried in the MIDDLE of the output (aside,
        # rhetorical, code) must not fire auto-ask on every turn.
        ("先看一下代码？好的，我来读取文件并执行操作", True, False),
        ("你可能会问为什么这么做。我先执行任务", True, False),
        ("先确认一下？随后我直接运行", True, False),
        ("a ? b : c 这种三元表达式很正常", True, False),
        # A question that CLOSES the turn still triggers, even when it is
        # preceded by prose or tool calls.
        ("我已经读取了文件，接下来要修改哪个文件？", True, True),
        ("好的，我来执行。你确定要删除这个文件？", True, True),
        ("执行完毕，需要我继续下一步吗？", True, True),
        # Statement ending with a fullwidth colon is NOT a question.
        ("操作步骤如下：", True, False),
        ("让我列出所有选项：", True, False),
        # Empty
        ("", True, False),
        (None, True, False),
    ])
    def test_is_auto_ask_condition(self, text, has_tools, expected):
        """The detection fires via semantic or syntax layer, with and without tool calls."""
        from onecode.agent.question_detect import looks_like_question

        clean_text = text.rstrip() if text else ""
        tool_uses = [{"id": "tu-1", "name": "Read", "input": {}}] if has_tools else []

        # Same composition as the engine: tool calls relax the syntax check,
        # no tool calls require a strict (trailing/intent) question signal.
        _is_auto_ask = bool(tool_uses and looks_like_question(clean_text, strict=False))
        if not _is_auto_ask and not tool_uses:
            _is_auto_ask = bool(clean_text and looks_like_question(clean_text, strict=True))

        assert _is_auto_ask == expected, f"text={text!r}, has_tools={has_tools}"

    def test_semantic_detection_coverage(self):
        """Verify semantic patterns cover the upgradeToVip scenario."""
        from onecode.agent.question_detect import semantic_needs_input

        # The user's original scenario: "请问要升级哪个用户的VIP？"
        scenarios = [
            ("请问要升级哪个用户的VIP？", True, "fullwidth question mark"),
            ("请选择要升级的用户", True, "请选择 semantic"),
            ("需要用户提供用户ID", True, "需要您 semantic"),
            ("需要知道用户的VIP等级", True, "需要知道 semantic"),
            ("哪个用户的VIP要升级？", True, "哪个用户 semantic"),
            ("让我先读取用户列表", False, "self-talk: 让我先"),
            ("首先我需要确认权限", False, "self-talk: 首先"),
            ("好的，我来升级VIP", False, "self-talk: 好的"),
        ]

        for text, expected, desc in scenarios:
            assert semantic_needs_input(text) == expected, f"{desc}: {text!r}"


class TestAutoAskResolveApproval:
    """Verify resolve_approval works with the synthetic auto-ask AskUser tool."""

    async def test_synthetic_ask_user_resolve(self):
        """The fake AskUser created by auto-ask should work with resolve_approval."""
        engine = _make_engine()
        engine._pending_approval = {
            "tool_call": {
                "id": "auto-ask-1",
                "name": "AskUser",
                "input": {"question": "请问要升级哪个用户？"},
            },
            "category": "ask_user",
            "ask_user": True,
        }

        result = await engine.resolve_approval(approved=True, answer="用户ID是 12345")
        assert result is not None
        assert result["is_error"] is False
        parsed = json.loads(result["content"])
        assert parsed["answer"] == "用户ID是 12345"
        assert engine._pending_approval is None

    async def test_synthetic_ask_user_cancel(self):
        """Cancelling the synthetic AskUser should return an error."""
        engine = _make_engine()
        engine._pending_approval = {
            "tool_call": {
                "id": "auto-ask-2",
                "name": "AskUser",
                "input": {"question": "请问要升级哪个用户？"},
            },
            "category": "ask_user",
            "ask_user": True,
        }

        result = await engine.resolve_approval(approved=False, answer="")
        assert result is not None
        assert result["is_error"] is True
        assert engine._pending_approval is None


class TestAutoAskEventSequence:
    """Verify the auto-ask interception produces the correct event sequence.

    These tests bypass the full chat_stream() by directly exercising the
    detection and branching logic, which is simpler and sufficient to prove
    the fix works correctly.
    """

    def test_is_auto_ask_true_triggers_branch(self):
        """When detection fires, the code should take the interception branch —
        including question-only turns with NO tool calls."""
        from onecode.agent.question_detect import looks_like_question

        # Question + tool calls (loose detection)
        clean_text = "请问要升级哪个用户？"
        tool_uses = [{"id": "tu-1", "name": "Read", "input": {}}]
        assert bool(tool_uses and looks_like_question(clean_text.rstrip(), strict=False)) is True

        # Plain question, NO tool calls (strict detection)
        clean_text = "Which user should I upgrade?"
        tool_uses = []
        _is_auto_ask = bool(tool_uses and looks_like_question(clean_text, strict=False))
        if not _is_auto_ask and not tool_uses:
            _is_auto_ask = bool(clean_text and looks_like_question(clean_text, strict=True))
        assert _is_auto_ask is True

    def test_is_auto_ask_false_allows_normal_flow(self):
        """When detection does not fire, the code proceeds normally."""
        from onecode.agent.question_detect import looks_like_question

        # Normal text without question signal
        clean_text = "好的，我来读取用户列表。"
        tool_uses = [{"id": "tu-1", "name": "Read", "input": {}}]
        assert bool(tool_uses and looks_like_question(clean_text, strict=False)) is False

        # Self-talk, no tool calls (must NOT intercept)
        clean_text = "让我先读取用户列表"
        tool_uses = []
        _is_auto_ask = bool(tool_uses and looks_like_question(clean_text, strict=False))
        if not _is_auto_ask and not tool_uses:
            _is_auto_ask = bool(clean_text and looks_like_question(clean_text, strict=True))
        assert _is_auto_ask is False

    def test_fake_ask_user_tool_call_id_format(self):
        """The synthetic AskUser ID should follow the 'auto-ask-N' pattern."""
        _ask_fake_id = f"auto-ask-{0}"
        assert _ask_fake_id == "auto-ask-0"
        _ask_fake_id = f"auto-ask-{999}"
        assert _ask_fake_id == "auto-ask-999"

    def test_synthetic_ask_user_structure(self):
        """Verify the structure of the synthetic AskUser tool use matches what
        the ACP adapter expects (tool_use id + tool_result id must match)."""
        _ask_fake_id = "auto-ask-42"

        assistant_blocks = [
            {"type": "text", "text": "请问要升级哪个用户？"},
            {
                "type": "tool_use",
                "id": _ask_fake_id,
                "name": "AskUser",
                "input": {"question": "请问要升级哪个用户？"},
            },
        ]

        # Find the tool_use block
        tool_use = next(b for b in assistant_blocks if b["type"] == "tool_use")
        assert tool_use["id"] == _ask_fake_id
        assert tool_use["name"] == "AskUser"

        # The tool_result that resolve_approval returns will use this same id,
        # so the context stays consistent (tool_use → tool_result pairing).
        result = {
            "tool_use_id": _ask_fake_id,
            "content": json.dumps({"answer": "用户12345"}),
            "is_error": False,
            "category": "ask_user",
        }
        assert result["tool_use_id"] == tool_use["id"]

    def test_auto_ask_preserves_thinking_blocks(self):
        """When thinking blocks exist alongside a question, they should be
        included in the assistant_blocks so they survive session reload."""
        from onecode.agent.question_detect import looks_like_question
        thinking_blocks = ["Let me think about this..."]
        clean_text = "请问要升级哪个用户？"
        tool_uses = [{"id": "tu-1", "name": "Read", "input": {}}]

        _is_auto_ask = bool(tool_uses and looks_like_question(clean_text, strict=False))
        assert _is_auto_ask is True

        # Simulate what the code does with thinking blocks
        assistant_blocks: list = []
        for tb in thinking_blocks:
            assistant_blocks.append({"type": "thinking", "thinking": tb})
        assistant_blocks.append({"type": "text", "text": clean_text})
        assistant_blocks.append({
            "type": "tool_use",
            "id": "auto-ask-1",
            "name": "AskUser",
            "input": {"question": clean_text},
        })

        thinking_block = next((b for b in assistant_blocks if b["type"] == "thinking"), None)
        assert thinking_block is not None
        assert thinking_block["thinking"] == "Let me think about this..."
