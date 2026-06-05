"""Test session loading: verifies that stored messages are replayed as
the correct ACP session update types, including tool_call notifications
for MsgToolCall blocks in legacy [TOOL_CALL] format."""

from unittest.mock import Mock, patch, MagicMock

import pytest

from cdha.agent.cdh_agent_acp import CDHACPAdapter


def _collect_updates(adapter: CDHACPAdapter) -> list[dict]:
    return [call[0][0] for call in adapter.send_session_update.call_args_list]


@pytest.fixture
def adapter():
    a = CDHACPAdapter()
    a.send_session_update = Mock()
    return a


@patch("cdha.agent.cdh_agent_acp.load_config")
@patch("cdha.agent.cdh_agent_acp._create_engine")
async def test_session_load_legacy_tool_call(mock_create_engine, mock_load_config, adapter):
    """Session load with legacy [TOOL_CALL] format produces tool_call updates."""
    mock_engine = MagicMock()
    mock_engine.load_session.return_value = True
    mock_engine._session.messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content":
            "before [TOOL_CALL]{tool => \"Read\", args => {--path \"/f\"}}[/TOOL_CALL] after"},
    ]
    mock_create_engine.return_value = mock_engine
    mock_load_config.return_value.default_mode = "agent"

    await adapter.session_load("/tmp", [], "sess-1")

    updates = _collect_updates(adapter)
    assert any(u["sessionUpdate"] == "user_message_chunk" for u in updates)
    assert any(u["sessionUpdate"] == "tool_call" for u in updates)
    assert any(u["sessionUpdate"] == "agent_message_chunk" for u in updates)

    tool_calls = [u for u in updates if u["sessionUpdate"] == "tool_call"]
    assert len(tool_calls) > 0
    assert tool_calls[0]["toolCallId"] is not None
    assert len(tool_calls[0].get("content", [])) > 0


@patch("cdha.agent.cdh_agent_acp.load_config")
@patch("cdha.agent.cdh_agent_acp._create_engine")
async def test_session_load_agent_message_blocks(mock_create_engine, mock_load_config, adapter):
    """Session load with new AgentMessage block format."""
    mock_engine = MagicMock()
    mock_engine.load_session.return_value = True
    mock_engine._session.messages = [
        {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "blocks": [
                    {"type": "text", "text": "hello world"},
                ]
            },
    ]
    mock_create_engine.return_value = mock_engine
    mock_load_config.return_value.default_mode = "agent"

    await adapter.session_load("/tmp", [], "sess-2")

    updates = _collect_updates(adapter)
    chunks = [u for u in updates if u["sessionUpdate"] == "agent_message_chunk"]
    assert len(chunks) > 0
    assert "hello world" in chunks[0]["content"]["text"]


@patch("cdha.agent.cdh_agent_acp.load_config")
@patch("cdha.agent.cdh_agent_acp._create_engine")
async def test_session_load_multiple_tool_calls(mock_create_engine, mock_load_config, adapter):
    """Session with multiple tool calls sends a tool_call for each."""
    mock_engine = MagicMock()
    mock_engine.load_session.return_value = True
    mock_engine._session.messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content":
            "[TOOL_CALL]{tool => \"R\", args => {--path \"a\"}}[/TOOL_CALL]"
            "[TOOL_CALL]{tool => \"W\", args => {--path \"b\" --content \"c\"}}[/TOOL_CALL]"},
    ]
    mock_create_engine.return_value = mock_engine
    mock_load_config.return_value.default_mode = "agent"

    await adapter.session_load("/tmp", [], "sess-3")

    updates = _collect_updates(adapter)
    tool_calls = [u for u in updates if u["sessionUpdate"] == "tool_call"]
    assert len(tool_calls) == 2
    assert tool_calls[0]["toolCallId"] != tool_calls[1]["toolCallId"]


@patch("cdha.agent.cdh_agent_acp.load_config")
@patch("cdha.agent.cdh_agent_acp._create_engine")
async def test_session_load_tool_result_role(mock_create_engine, mock_load_config, adapter):
    """Session with separate 'tool' role messages emits tool_call_update."""
    mock_engine = MagicMock()
    mock_engine.load_session.return_value = True
    mock_engine._session.messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content":
            "[TOOL_CALL]{tool => \"Read\", args => {--path \"/f\"}}[/TOOL_CALL]"},
        {"role": "tool", "name": "legacy-0", "content": [
            {"type": "tool_result", "tool_use_id": "legacy-0",
             "content": "file content", "is_error": False}
        ]},
    ]
    mock_create_engine.return_value = mock_engine
    mock_load_config.return_value.default_mode = "agent"

    await adapter.session_load("/tmp", [], "sess-4")

    updates = _collect_updates(adapter)
    tool_call_updates = [u for u in updates if u["sessionUpdate"] == "tool_call_update"]
    assert len(tool_call_updates) > 0
    assert any("file content" in str(u) for u in tool_call_updates)
