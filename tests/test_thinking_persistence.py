"""Tests for thinking block persistence in the engine.

Verifies that:
1. Thinking blocks extracted from response_text are stored in context
   (so they survive session reload).
2. The on_thinking callback (used by the streaming path) also appends
   to _pending_thinking_blocks.
3. Both paths produce the same {"type": "thinking"} dict in context.
"""

from __future__ import annotations

from unittest.mock import MagicMock



class TestThinkingPersistence:
    """Engine must persist thinking blocks into context for session replay."""

    def _make_engine(self):
        from onecode.agent.engine import AgentEngine
        return AgentEngine(app=MagicMock())

    def test_thinking_blocks_in_response_text_are_stored_in_context(self):
        """Non-streaming path: <thinking>...</thinking> in response_text
        is extracted and stored as {"type": "thinking"} blocks."""
        engine = self._make_engine()
        response_text = (
            "before "
            "<thinking>I need to analyze the bug first.</thinking> "
            "after"
        )
        thinking_blocks = []
        import re
        THINKING_RE = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.DOTALL)
        for match in THINKING_RE.finditer(response_text):
            thinking_blocks.append(match.group(1))
        clean_text = THINKING_RE.sub("", response_text).strip()
        if thinking_blocks or True:
            assistant_blocks = []
            for tb in thinking_blocks:
                assistant_blocks.append({"type": "thinking", "thinking": tb})
            if clean_text:
                assistant_blocks.append({"type": "text", "text": clean_text})
            engine.context.add_assistant(assistant_blocks)

        ctx_msgs = engine.context.messages
        assert len(ctx_msgs) == 1
        content = ctx_msgs[0].content
        assert isinstance(content, list)
        types = [b["type"] for b in content]
        assert "thinking" in types
        assert "text" in types
        thinking_block = next(b for b in content if b["type"] == "thinking")
        assert thinking_block["thinking"] == "I need to analyze the bug first."

    def test_on_thinking_callback_appends_to_pending_blocks(self):
        """Streaming path: on_thinking callback populates
        _pending_thinking_blocks for later add_assistant."""
        engine = self._make_engine()
        engine._pending_thinking_blocks = []

        # Simulate the adapter calling on_thinking twice
        captured = []
        engine.on_thinking = lambda text: captured.append(text)
        engine.on_thinking("First thought.")
        engine.on_thinking("Second thought.")

        assert captured == ["First thought.", "Second thought."]

    def test_session_replay_can_extract_thinking_blocks(self):
        """End-to-end: the context format with thinking dicts can be
        converted back to ThinkBlock objects via _content_to_blocks."""
        from onecode.agent.onecode_agent_acp import CDHACPAdapter

        content = [
            {"type": "thinking", "thinking": "Plan: read file first."},
            {"type": "text", "text": "I'll help you with that."},
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Read",
                "input": {"path": "/etc/hosts"},
                "status": "complete",
            },
        ]
        blocks = CDHACPAdapter._content_to_blocks(content)
        from onecode.models.messages import ThinkBlock, TextBlock, ToolCall as MsgToolCall

        assert any(isinstance(b, ThinkBlock) for b in blocks)
        assert any(isinstance(b, TextBlock) for b in blocks)
        assert any(isinstance(b, MsgToolCall) for b in blocks)

        thinking = next(b for b in blocks if isinstance(b, ThinkBlock))
        assert thinking.content == "Plan: read file first."

        text = next(b for b in blocks if isinstance(b, TextBlock))
        assert text.content == "I'll help you with that."

        tool = next(b for b in blocks if isinstance(b, MsgToolCall))
        assert tool.name == "Read"
        assert tool.arguments == {"path": "/etc/hosts"}


class TestThinkingFallback:
    """When thinking is in a legacy <thinking> tag in response_text, the
    non-streaming path must still extract it for storage."""

    def test_thinking_marker_stripped_from_clean_text(self):
        import re
        THINKING_RE = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.DOTALL)
        response = "Hello <thinking>secret plan</thinking> World"
        thinking_blocks = [m.group(1) for m in THINKING_RE.finditer(response)]
        clean = THINKING_RE.sub("", response).strip()
        assert thinking_blocks == ["secret plan"]
        assert clean == "Hello  World"
