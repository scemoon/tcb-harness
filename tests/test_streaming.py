"""Test streaming callback: after fix, [TOOL_CALL] text is stripped from
buffer without emitting duplicate tool_call notifications.

Tool calls are handled by TOOL_CALL_START/TOOL_CALL_COMPLETE events from
the engine — the text parser must NOT emit its own notifications."""

from unittest.mock import Mock


from onecode.agent.onecode_agent_acp import CDHACPAdapter


def _make_spy_adapter() -> tuple[CDHACPAdapter, Mock]:
    """Create a CDHACPAdapter with send_session_update mocked."""
    adapter = CDHACPAdapter()
    adapter.send_session_update = Mock()
    return adapter, adapter.send_session_update


def _collect_updates(spy: Mock) -> list[dict]:
    """Return list of session update dicts from all spy calls."""
    return [call[0][0] for call in spy.call_args_list]


class TestStreamingCallback:
    """Verify the streaming callback never emits tool_call from text parsing."""

    def test_strips_tool_call_block_in_single_chunk(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("before [TOOL_CALL]{tool => \"Read\", args => {--path \"/f\"}}[/TOOL_CALL] after")

        updates = _collect_updates(spy)
        assert len(updates) == 2
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "before "
        assert updates[1]["sessionUpdate"] == "agent_message_chunk"
        assert updates[1]["content"]["text"] == " after"
        # No tool_call should be emitted from text parsing
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)

    def test_strips_tool_call_across_multiple_chunks(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("start ")
        callback("[TOOL_CALL]{tool => \"Write\", args => {--path \"x\" --content \"y\"}}")
        callback("[/TOOL_CALL] end")

        updates = _collect_updates(spy)
        assert len(updates) == 2
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "start "
        assert updates[1]["sessionUpdate"] == "agent_message_chunk"
        assert updates[1]["content"]["text"] == " end"
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)

    def test_strips_tool_call_open_close_separate(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("prefix [TOOL_CALL]{tool => \"Read\", args => {--path \"x\"}}")
        callback("[/TOOL_CALL] suffix")

        updates = _collect_updates(spy)
        assert len(updates) == 2
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "prefix "
        assert updates[1]["sessionUpdate"] == "agent_message_chunk"
        assert updates[1]["content"]["text"] == " suffix"
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)

    def test_emits_thinking_blocks(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("before <thinking>I think</thinking> after")

        updates = _collect_updates(spy)
        assert len(updates) == 3
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "before "
        assert updates[1]["sessionUpdate"] == "agent_thought_chunk"
        assert "I think" in updates[1]["content"]["text"]
        assert updates[2]["sessionUpdate"] == "agent_message_chunk"
        assert updates[2]["content"]["text"] == " after"
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)

    def test_handles_plain_text_with_no_markers(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("Just some regular text without any markers.")

        updates = _collect_updates(spy)
        assert len(updates) == 1
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "Just some regular text without any markers."

    def test_handles_thinking_tool_call_interleaved(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("<thinking>Step 1</thinking>")
        callback("text [TOOL_CALL]{tool => \"Read\", args => {--path \"a\"}}[/TOOL_CALL]")
        callback("<thinking>Step 2</thinking> done")

        updates = _collect_updates(spy)
        tool_calls = [u for u in updates if u["sessionUpdate"] == "tool_call"]
        assert len(tool_calls) == 0
        thought_chunks = [u for u in updates if u["sessionUpdate"] == "agent_thought_chunk"]
        assert len(thought_chunks) == 2

    def test_partial_tool_call_open_held_in_buffer(self):
        """If [TOOL_CALL] is at end of buffer with no close marker, hold it."""
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("start [TOOL_CALL]{tool => \"Read\"")
        # At this point the open marker is found, text_buffer is
        # "{tool => \"Read\"", no close marker → held
        updates = _collect_updates(spy)
        assert len(updates) == 1
        assert updates[0]["sessionUpdate"] == "agent_message_chunk"
        assert updates[0]["content"]["text"] == "start "

        # Now provide the close
        callback("}[/TOOL_CALL] end")
        updates = _collect_updates(spy)
        assert updates[-1]["sessionUpdate"] == "agent_message_chunk"
        assert updates[-1]["content"]["text"] == " end"

    def test_bare_tool_call_no_emit(self):
        """Bare {tool => ...} without [TOOL_CALL] markers is also stripped."""
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback("before {tool => \"Read\", args => {--path \"/f\"}} after")

        updates = _collect_updates(spy)
        assert len(updates) == 2
        assert updates[0]["content"]["text"] == "before "
        assert updates[1]["content"]["text"] == " after"
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)

    def test_multiple_tool_calls(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()

        callback(
            "a [TOOL_CALL]{tool => \"Read\", args => {--path \"1\"}}[/TOOL_CALL]"
            " b [TOOL_CALL]{tool => \"Write\", args => {--path \"2\" --content \"c\"}}[/TOOL_CALL]"
            " c"
        )

        updates = _collect_updates(spy)
        assert len(updates) == 3
        assert updates[0]["content"]["text"] == "a "
        assert updates[1]["content"]["text"] == " b "
        assert updates[2]["content"]["text"] == " c"
        assert not any(u["sessionUpdate"] == "tool_call" for u in updates)


class TestBuildToolCallContent:
    """_build_tool_call_content produces correct content blocks."""

    def test_write_emits_code_fence(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Write", {"path": "/tmp/test.py", "content": "print(1)"})
        assert len(result) == 1
        block = result[0]
        assert block["type"] == "content"
        text = block["content"]["text"]
        assert "```python" in text
        assert "print(1)" in text

    def test_read_returns_empty(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Read", {"path": "/tmp/file.txt"})
        assert result == []

    def test_edit_emits_diff_block(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Edit", {
            "path": "/tmp/file.py",
            "old_string": "print(1)",
            "new_string": "print(2)",
        })
        assert len(result) == 1
        assert result[0]["type"] == "diff"
        assert result[0]["path"] == "/tmp/file.py"
        assert "print(1)" in result[0]["oldText"]
        assert "print(2)" in result[0]["newText"]

    def test_bash_emits_bash_fence(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Bash", {"command": "ls -la"})
        assert len(result) == 1
        text = result[0]["content"]["text"]
        assert "```bash" in text
        assert "$ ls -la" in text

    def test_list_is_header_only(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("List", {"path": "/tmp"})
        assert result == []

    def test_grep_emits_pattern_block(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Grep", {"pattern": "def run"})
        assert len(result) == 1
        text = result[0]["content"]["text"]
        assert "🔍 Pattern" in text
        assert "def run" in text
        assert "📁 Filter" not in text

    def test_grep_with_include_shows_filter(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content(
            "Grep", {"pattern": "TODO", "include": "*.py"}
        )
        assert len(result) == 1
        text = result[0]["content"]["text"]
        assert "🔍 Pattern" in text
        assert "TODO" in text
        assert "📁 Filter" in text
        assert "*.py" in text

    def test_grep_empty_pattern_falls_back_to_json(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Grep", {"pattern": ""})
        assert len(result) == 1
        text = result[0]["content"]["text"]
        assert "```json" in text

    def test_unknown_tool_falls_back_to_json(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("FooBar", {"key": "val"})
        assert len(result) == 1
        text = result[0]["content"]["text"]
        assert "```json" in text
        assert "key" in text
        assert "val" in text

    def test_empty_args_returns_empty(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content("Read", {})
        assert result == []

    def test_none_name_returns_empty(self):
        from onecode.agent.onecode_agent_acp import _build_tool_call_content

        result = _build_tool_call_content(None, {"a": "b"})
        assert len(result) == 1
        assert "```json" in result[0]["content"]["text"]


class TestFilterToolCallText:
    """_filter_tool_call_text removes tool call markers from agent text."""

    def test_removes_complete_tool_call(self):
        from onecode.agent.onecode_agent_acp import _filter_tool_call_text

        text = "before [TOOL_CALL]{tool => \"Read\"}[/TOOL_CALL] after"
        result = _filter_tool_call_text(text)
        assert result == "before  after"

    def test_keeps_text_without_markers(self):
        from onecode.agent.onecode_agent_acp import _filter_tool_call_text

        text = "just plain text"
        result = _filter_tool_call_text(text)
        assert result == "just plain text"

    def test_handles_incomplete_tool_call(self):
        from onecode.agent.onecode_agent_acp import _filter_tool_call_text

        text = "before [TOOL_CALL]{tool => \"Read\""
        result = _filter_tool_call_text(text)
        # Incomplete block (no [/TOOL_CALL]) is left in place
        assert result == text

    def test_multiple_tool_calls(self):
        from onecode.agent.onecode_agent_acp import _filter_tool_call_text

        text = ("a[TOOL_CALL]{tool => \"R\"}[/TOOL_CALL]b"
                "[TOOL_CALL]{tool => \"W\"}[/TOOL_CALL]c")
        result = _filter_tool_call_text(text)
        assert result == "abc"


class TestExtractLegacyToolCall:
    """_extract_legacy_tool_call parses tool call blocks correctly."""

    def test_extracts_name_and_path_arg(self):
        from onecode.agent.onecode_agent_acp import _extract_legacy_tool_call

        text = ("prefix [TOOL_CALL]{tool => \"Read\", args => {--path \"/a\"}}"
                "[/TOOL_CALL] suffix")
        result = _extract_legacy_tool_call(text)
        assert result is not None
        assert result["name"] == "Read"
        assert result["arguments"]["path"] == "/a"

    def test_extracts_write_with_content(self):
        from onecode.agent.onecode_agent_acp import _extract_legacy_tool_call

        text = ("[TOOL_CALL]{tool => \"Write\", args => {"
                "--path \"f.py\" --content \"print('hi')\"}}[/TOOL_CALL]")
        result = _extract_legacy_tool_call(text)
        assert result is not None
        assert result["name"] == "Write"
        assert result["arguments"]["path"] == "f.py"
        assert result["arguments"]["content"] == "print('hi')"

    def test_no_tool_call_returns_none(self):
        from onecode.agent.onecode_agent_acp import _extract_legacy_tool_call

        result = _extract_legacy_tool_call("just text")
        assert result is None

    def test_incomplete_no_close_marker_returns_none(self):
        from onecode.agent.onecode_agent_acp import _extract_legacy_tool_call

        result = _extract_legacy_tool_call("[TOOL_CALL]{tool => \"Read\"")
        assert result is None

    def test_returns_span_positions(self):
        from onecode.agent.onecode_agent_acp import _extract_legacy_tool_call

        text = "x[TOOL_CALL]{tool=>\"R\"}[/TOOL_CALL]y"
        result = _extract_legacy_tool_call(text)
        assert result is not None
        start, end = result["span"]
        assert text[start:end] == "[TOOL_CALL]{tool=>\"R\"}[/TOOL_CALL]"


class TestContentToBlocks:
    """_content_to_blocks converts stored message content to blocks."""

    def _convert(self, content):
        from onecode.agent.onecode_agent_acp import CDHACPAdapter
        return CDHACPAdapter._content_to_blocks(content)

    def test_string_with_tool_call_produces_tool_call(self):
        blocks = self._convert(
            "[TOOL_CALL]{tool => \"Read\", args => {--path \"/f\"}}[/TOOL_CALL]"
        )
        assert len(blocks) == 1
        assert type(blocks[0]).__name__ == "ToolCall"
        assert blocks[0].name == "Read"
        assert blocks[0].arguments["path"] == "/f"

    def test_string_with_thinking_produces_think_block(self):
        blocks = self._convert("<thinking>I think</thinking>")
        assert len(blocks) == 1
        assert type(blocks[0]).__name__ == "ThinkBlock"
        assert "I think" in blocks[0].content

    def test_plain_text_produces_text_block(self):
        blocks = self._convert("Hello world")
        assert len(blocks) == 1
        assert type(blocks[0]).__name__ == "TextBlock"
        assert blocks[0].content == "Hello world"

    def test_mixed_content_produces_correct_order(self):
        blocks = self._convert(
            "a <thinking>think</thinking> b "
            "[TOOL_CALL]{tool => \"R\", args => {--path \"x\"}}[/TOOL_CALL] c"
        )
        # Text before think, think, text before tool, tool, text after tool
        assert len(blocks) == 5
        assert type(blocks[0]).__name__ == "TextBlock"
        assert blocks[0].content == "a "
        assert type(blocks[1]).__name__ == "ThinkBlock"
        assert "think" in blocks[1].content
        assert type(blocks[2]).__name__ == "TextBlock"
        assert " b " in blocks[2].content
        assert type(blocks[3]).__name__ == "ToolCall"
        assert blocks[3].name == "R"
        assert type(blocks[4]).__name__ == "TextBlock"

    def test_list_format_with_tool_use(self):
        blocks = self._convert([
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "call_1", "name": "Read", "input": {"path": "/f"}},
            {"type": "tool_result", "tool_use_id": "call_1", "content": "result"},
        ])
        assert len(blocks) == 3
        assert type(blocks[0]).__name__ == "TextBlock"
        assert type(blocks[1]).__name__ == "ToolCall"
        assert blocks[1].id == "call_1"
        assert type(blocks[2]).__name__ == "ToolResult"
        assert blocks[2].content == "result"


class TestStreamingWatchdog:
    """When a stream is truncated mid-marker (``<thinking>``,
    ``[TOOL_CALL]``, ``<minimax:tool_call>``, or bare ``{tool => ...}``)
    the held buffer would otherwise grow without limit and every
    subsequent chunk is silently swallowed.  The watchdog forces a
    flush once the buffer exceeds a safety cap, so the user at least
    sees the held text as a plain message."""

    def test_unclosed_thinking_block_is_flushed(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()
        # Open a <thinking> tag, then push 80 KB of body with no close.
        callback("<thinking>")
        callback("x" * (80 * 1024))
        updates = _collect_updates(spy)
        # The watchdog should have emitted the held text as a plain
        # message rather than silently holding it.
        assert any(
            u["sessionUpdate"] == "agent_message_chunk"
            and "x" * 100 in u["content"]["text"]
            for u in updates
        ), f"watchdog did not flush; got {updates!r}"

    def test_unclosed_minimax_tool_call_is_flushed(self):
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()
        callback("<minimax:tool_call>")
        callback("y" * (80 * 1024))
        updates = _collect_updates(spy)
        assert any(
            u["sessionUpdate"] == "agent_message_chunk"
            and "y" * 100 in u["content"]["text"]
            for u in updates
        )

    def test_normal_thinking_block_below_cap_not_flushed(self):
        """A well-formed small thinking block must NOT be force-flushed
        as a plain message — it should still go through the
        ``agent_thought_chunk`` path (which the streaming callback
        strips from the text buffer)."""
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()
        callback("<thinking>short</thinking>")
        updates = _collect_updates(spy)
        # No agent_message_chunk containing the held text should be
        # emitted; the only chunk for the thinking body goes through
        # the agent_thought_chunk path.
        assert not any(
            u["sessionUpdate"] == "agent_message_chunk"
            and "short" in u["content"]["text"]
            for u in updates
        )
        assert any(
            u["sessionUpdate"] == "agent_thought_chunk" for u in updates
        )

    def test_subsequent_chunks_after_watchdog_emit_normally(self):
        """Once the watchdog has flushed, the callback must continue
        processing later chunks as plain text rather than staying
        stuck in the "held" state."""
        adapter, spy = _make_spy_adapter()
        callback = adapter._make_stream_callback()
        callback("<thinking>")
        callback("z" * (80 * 1024))     # trips the watchdog
        callback("after-flush text")
        updates = _collect_updates(spy)
        # The "after-flush text" should be visible as a message.
        assert any(
            u["sessionUpdate"] == "agent_message_chunk"
            and "after-flush text" in u["content"]["text"]
            for u in updates
        )


class TestBashOutputFormat:
    """_format_bash_output produces a single fenced code block with bash lang."""

    def test_stdout_only(self):
        from onecode.agent.tools.bash_tool import BashTool

        out = BashTool._format_bash_output("hello\nworld", "", "", False)
        assert out.startswith("```bash\n")
        assert out.endswith("\n```")
        assert "hello" in out
        assert "world" in out

    def test_stderr_only(self):
        from onecode.agent.tools.bash_tool import BashTool

        out = BashTool._format_bash_output("", "warn: oops", "", False)
        assert out.startswith("```bash\n")
        assert "[stderr]" in out
        assert "warn: oops" in out

    def test_error_only(self):
        from onecode.agent.tools.bash_tool import BashTool

        out = BashTool._format_bash_output("", "", "boom", True)
        assert "[error] boom" in out

    def test_no_output_marker(self):
        from onecode.agent.tools.bash_tool import BashTool

        assert BashTool._format_bash_output("", "", "", False) == "(no output)"
        assert BashTool._format_bash_output("", "", "", True) == "(failed with no output)"
