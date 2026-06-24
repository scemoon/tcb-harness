import asyncio
import logging
import sys

logger = logging.getLogger("tui.acp.agent")

import json
import os
from pathlib import Path
from typing import Any, cast, NamedTuple
from copy import deepcopy

import rich.repr

from textual.content import Content
from textual.message import Message
from textual.message_pump import MessagePump


from tui import jsonrpc
import tui
from tui.agent_schema import Agent as AgentData
from tui.agent import AgentBase, AgentReady, AgentFail
from tui.acp import protocol
from tui.acp import api
from tui.acp.api import API
from tui.acp import messages
from tui.acp.prompt import build as build_prompt
from tui import messages as tui_messages
from tui.db import DB
from tui import paths
from tui import constants
from tui.answer import Answer

PROTOCOL_VERSION = 1


class Mode(NamedTuple):
    """An agent mode."""

    id: str
    name: str
    description: str | None


@rich.repr.auto
class Agent(AgentBase):
    """An agent that speaks the APC (https://agentclientprotocol.com/overview/introduction) protocol."""

    def __init__(
        self,
        project_root: Path,
        agent: AgentData,
        session_id: str | None,
        session_pk: int | None = None,
    ) -> None:
        """

        Args:
            project_root: Project root path.
            command: Command to launch agent.
        """
        super().__init__(project_root)

        self._agent_data = agent
        self.session_id = session_id

        self.server = jsonrpc.Server()
        self.server.expose_instance(self)

        self._agent_task: asyncio.Task | None = None
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self.done_event = asyncio.Event()

        self.agent_capabilities: protocol.AgentCapabilities = {
            "loadSession": False,
            "promptCapabilities": {
                "audio": False,
                "embeddedContent": True,
                "image": True,
            },
        }
        self.auth_methods: list[protocol.AuthMethod] = []
        self.session_pk: int | None = session_pk
        self._pending_session_data: dict | None = None
        self.tool_calls: dict[str, protocol.ToolCall] = {}
        self._message_target: MessagePump | None = None

        self._terminal_count: int = 0

    @property
    def command(self) -> str | None:
        """The command used to launch the agent, or `None` if there isn't one."""
        acp_command = tui.get_os_matrix(self._agent_data["run_command"])
        return acp_command

    @property
    def supports_load_session(self) -> bool:
        """Does the agent support loading sessions?"""
        return self.agent_capabilities.get("loadSession", False)

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.project_root_path
        yield self.command

    def get_info(self) -> Content:
        agent_name = self._agent_data["name"]
        return Content(agent_name)

    async def start(self, message_target: MessagePump | None = None) -> None:
        """Start the agent."""
        self._message_target = message_target
        self._agent_task = asyncio.create_task(self._run_agent())

    def send(self, request: jsonrpc.Request) -> None:
        """Send a request to the agent.

        This is called automatically, if you go through `self.request`.

        Args:
            request: JSONRPC request object.

        """
        assert self._process is not None, "Process should be present here"

        logger.debug("[client] %s", request.body)
        if (stdin := self._process.stdin) is not None:
            stdin.write(b"%s\n" % request.body_json)

    def request(self) -> jsonrpc.Request:
        """Create a request object."""
        return API.request(self.send)

    def post_message(self, message: Message) -> bool:
        """Post a message to the message target (the Conversation).

        Args:
            message: Message object.

        Returns:
            `True` if the message was posted successfully, or `False` if it wasn't.
        """
        if (message_target := self._message_target) is None:
            return False
        return message_target.post_message(message)

    @jsonrpc.expose("session/update")
    def rpc_session_update(
        self,
        sessionId: str,
        update: protocol.SessionUpdate,
        _meta: dict[str, Any] | None = None,
    ):
        """Agent requests an update.

        https://agentclientprotocol.com/protocol/schema
        """
        status_line: str | None = None
        if _meta and (field_meta := _meta.get("field_meta")) is not None:
            if (
                open_hands_metrics := field_meta.get("openhands.dev/metrics")
            ) is not None:
                status_line = open_hands_metrics.get("status_line")

        match update:
            case {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": type, "text": text},
            }:
                if text:
                    self.post_message(messages.UserMessage(type, text))

            case {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": type, "text": text},
            }:
                self.post_message(messages.Update(type, text))

            case {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": type, "text": text},
            }:
                self.post_message(messages.Thinking(type, text))

            case {
                "sessionUpdate": "tool_call",
                "toolCallId": tool_call_id,
            }:
                logger.debug(
                    "session/update: tool_call id=%s title=%s kind=%s status=%s content_blocks=%d",
                    tool_call_id,
                    update.get('title','?'), update.get('kind','?'),
                    update.get('status','?'), len(update.get('content',[]) or []),
                )
                self.tool_calls[tool_call_id] = deepcopy(update)
                self.post_message(messages.ToolCall(deepcopy(update)))

            case {"sessionUpdate": "plan", "entries": entries}:
                self.post_message(messages.Plan(entries))

            case {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
            }:
                if tool_call_id in self.tool_calls:
                    current_tool_call = self.tool_calls[tool_call_id]
                    for key, value in update.items():
                        if value is not None:
                            current_tool_call[key] = value

                    logger.debug(
                        "session/update: tool_call_update id=%s status=%s content_blocks=%d",
                        tool_call_id,
                        update.get('status','?'),
                        len(update.get('content',[]) or []),
                    )

                    self.post_message(
                        messages.ToolCallUpdate(deepcopy(current_tool_call), update)
                    )
                else:
                    logger.debug(
                        "session/update: tool_call_update ORPHAN id=%s "
                        "(no prior tool_call, creating widget from update)",
                        tool_call_id,
                    )
                    current_tool_call: protocol.ToolCall = {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": "Tool call",
                    }
                    for key, value in update.items():
                        if value is not None:
                            current_tool_call[key] = value

                    self.tool_calls[tool_call_id] = current_tool_call
                    self.post_message(messages.ToolCall(deepcopy(current_tool_call)))

            case {
                "sessionUpdate": "usage_update",
            }:
                self.post_message(messages.ContextUpdate(
                    used=update.get("used", 0),
                    size=update.get("size", 0),
                ))

            case {
                "sessionUpdate": "ask_user",
                "question": question,
            }:
                self.post_message(messages.AskUser(
                    question=question,
                    context=update.get("context", ""),
                    options=update.get("options", []),
                    questions=update.get("questions", []),
                    tool_id=update.get("toolId", ""),
                ))

            case {
                "sessionUpdate": "ask_user",
                "questions": questions,
            } if questions:
                self.post_message(messages.AskUser(
                    questions=questions,
                    context=update.get("context", ""),
                    tool_id=update.get("toolId", ""),
                ))

            case {
                "sessionUpdate": "available_commands_update",
                "availableCommands": available_commands,
            }:
                self.post_message(messages.AvailableCommandsUpdate(available_commands))

            case {
                "sessionUpdate": "subagent_start",
                "subagentId": subagent_id,
                "agentType": agent_type,
                **rest,
            }:
                self.post_message(messages.SubAgentStart(
                    subagent_id, agent_type,
                    prompt=rest.get("prompt", ""),
                ))

            case {
                "sessionUpdate": "subagent_chunk",
                "subagentId": subagent_id,
                "text": text,
            }:
                self.post_message(messages.SubAgentChunk(subagent_id, text))

            case {
                "sessionUpdate": "subagent_end",
                "subagentId": subagent_id,
                "agentType": agent_type,
            }:
                self.post_message(messages.SubAgentEnd(subagent_id, agent_type))

        if status_line is not None:
            self.post_message(messages.UpdateStatusLine(status_line))

    @jsonrpc.expose("session/request_permission")
    async def rpc_request_permission(
        self,
        sessionId: str,
        options: list[protocol.PermissionOption],
        toolCall: protocol.ToolCallUpdatePermissionRequest,
        _meta: dict | None = None,
    ) -> protocol.RequestPermissionResponse:
        """Agent requests permission to make a tool call.

        Args:
            sessionId: The session ID.
            options: A list of permission options (potential replies).
            toolCall: The tool or tools the agent is requesting permission to call.
            _meta: Optional meta information.

        Returns:
            The response to the permission request.
        """
        result_future: asyncio.Future[Answer] = asyncio.Future()
        tool_call_id = toolCall["toolCallId"]

        permission_tool_call = toolCall.copy()
        permission_tool_call.pop("sessionUpdate", None)
        tool_call = cast(protocol.ToolCall, permission_tool_call)
        if tool_call_id in self.tool_calls:
            self.tool_calls[tool_call_id] |= tool_call
        else:
            self.tool_calls[tool_call_id] = deepcopy(tool_call)

        # Forward content to the ToolCall widget so the user can see what
        # the agent is requesting permission for (e.g. the bash command).
        merged = deepcopy(self.tool_calls[tool_call_id])
        self.post_message(messages.ToolCallUpdate(merged, tool_call))

        message = messages.RequestPermission(options, merged, result_future)
        self.post_message(message)
        await result_future
        ask_result = result_future.result()

        request_permission_outcome: protocol.OutcomeSelected = {
            "optionId": ask_result.id,
            "outcome": "selected",
        }
        result: protocol.RequestPermissionResponse = {
            "outcome": request_permission_outcome
        }
        return result

    def send_ask_user_answer(self, answer: str, cancelled: bool) -> None:
        """Send the user's answer back to the CDHA agent."""
        import uuid

        request = {
            "jsonrpc": "2.0",
            "method": "session/ask_user_answer",
            "params": {"answer": answer, "cancelled": cancelled},
            "id": str(uuid.uuid4()),
        }
        if self._process is not None and self._process.stdin is not None:
            self._process.stdin.write(b"%s\n" % json.dumps(request).encode("utf-8"))

    @jsonrpc.expose("fs/read_text_file")
    def rpc_read_text_file(
        self,
        sessionId: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
    ) -> dict[str, str]:
        """Read a file in the project."""
        # TODO: what if the read is outside of the project path?
        # https://agentclientprotocol.com/protocol/file-system#reading-files
        read_path = self.project_root_path / path
        try:
            text = read_path.read_text(encoding="utf-8", errors="ignore")
        except IOError:
            text = ""
        if line is not None:
            line = max(0, line - 1)
            if limit is None:
                text = "\n".join(text.splitlines()[line:])
            else:
                text = "\n".join(text.splitlines()[line : line + limit])
        return {"content": text}

    @jsonrpc.expose("fs/write_text_file")
    def rpc_write_text_file(self, sessionId: str, path: str, content: str) -> None:
        # TODO: What if the agent wants to write outside of the project path?
        # https://agentclientprotocol.com/protocol/file-system#writing-files

        write_path = self.project_root_path / path
        write_path.write_text(content, encoding="utf-8", errors="ignore")

    # https://agentclientprotocol.com/protocol/schema#createterminalrequest
    @jsonrpc.expose("terminal/create")
    async def rpc_terminal_create(
        self,
        command: str,
        _meta: dict | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[protocol.EnvVariable] | None = None,
        outputByteLimit: int | None = None,
        sessionId: str | None = None,
    ) -> protocol.CreateTerminalResponse:
        # Assign a terminal id
        self._terminal_count = self._terminal_count + 1
        terminal_id = f"terminal-{self._terminal_count}"

        terminal_env = (
            {variable["name"]: variable["value"] for variable in env} if env else {}
        )
        result_future: asyncio.Future[bool] = asyncio.Future()
        self.post_message(
            messages.CreateTerminal(
                terminal_id,
                command=command,
                args=args,
                cwd=cwd,
                env=terminal_env,
                output_byte_limit=outputByteLimit,
                result_future=result_future,
            )
        )
        await result_future
        if not result_future.result():
            raise jsonrpc.JSONRPCError("Failed to create a terminal.")
        return {"terminalId": terminal_id}

    # https://agentclientprotocol.com/protocol/schema#killterminalcommandrequest
    @jsonrpc.expose("terminal/kill")
    def rpc_terminal_kill(
        self, sessionID: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.KillTerminalCommandResponse:
        self.post_message(messages.KillTerminal(terminalId))
        return {}

    # https://agentclientprotocol.com/protocol/schema#terminal%2Foutput
    @jsonrpc.expose("terminal/output")
    async def rpc_terminal_output(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.TerminalOutputResponse:
        from tui.widgets.terminal_tool import ToolState

        result_future: asyncio.Future[ToolState] = asyncio.Future()

        if not self.post_message(messages.GetTerminalState(terminalId, result_future)):
            raise RuntimeError("Unable to get terminal output")

        await result_future
        terminal_state = result_future.result()

        result: protocol.TerminalOutputResponse = {
            "output": terminal_state.output,
            "truncated": terminal_state.truncated,
        }
        if (return_code := terminal_state.return_code) is not None:
            result["exitStatus"] = {"exitCode": return_code}
        return result

    # https://agentclientprotocol.com/protocol/schema#terminal%2Frelease
    @jsonrpc.expose("terminal/release")
    def rpc_terminal_release(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.ReleaseTerminalResponse:
        self.post_message(messages.ReleaseTerminal(terminalId))
        return {}

    # https://agentclientprotocol.com/protocol/schema#terminal%2Fwait-for-exit
    @jsonrpc.expose("terminal/wait_for_exit")
    async def rpc_terminal_wait_for_exit(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.WaitForTerminalExitResponse:
        result_future: asyncio.Future[tuple[int, str | None]] = asyncio.Future()
        if not self.post_message(
            messages.WaitForTerminalExit(terminalId, result_future)
        ):
            raise RuntimeError("Unable to wait for terminal exit; no terminal found")

        await result_future
        return_code, signal = result_future.result()
        return {"exitCode": return_code, "signal": signal}

    async def _run_agent(self) -> None:
        """Task to communicate with the agent subprocess."""

        PIPE = asyncio.subprocess.PIPE
        env = os.environ.copy()
        env["TOAD_CWD"] = str(self.project_root_path)
        python_bin = str(Path(sys.executable).parent)
        env["PATH"] = f"{python_bin}:{env.get('PATH', '')}"

        if (command := self.command) is None:
            self.post_message(
                AgentFail("Failed to start agent; no run command for this OS")
            )
            return
        try:
            process = self._process = await asyncio.create_subprocess_shell(
                command,
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                env=env,
                cwd=str(self.project_root_path),
                limit=10 * 1024 * 1024,
            )
        except Exception as error:
            self.post_message(AgentFail("Failed to start agent", details=str(error)))
            return

        self._task = asyncio.create_task(self.run())

        assert process.stdout is not None
        assert process.stdin is not None

        tasks: set[asyncio.Task] = set()

        async def call_jsonrpc(request: jsonrpc.JSONObject | jsonrpc.JSONList) -> None:
            try:
                if (result := await self.server.call(request)) is not None:
                    result_json = json.dumps(result).encode("utf-8")
                    if process.stdin is not None:
                        process.stdin.write(b"%s\n" % result_json)
            finally:
                if (task := asyncio.current_task()) is not None:
                    tasks.discard(task)

        while line := await process.stdout.readline():
            # This line should contain JSON, which may be:
            #   A) a JSONRPC request
            #   B) a JSONRPC response to a previous request
            if not line.strip():
                continue

            try:
                line_str = line.decode("utf-8")
            except Exception as error:
                logger.error("Unable to decode utf-8 from agent: %s", error)
                continue

            logger.debug("[agent] %s", line_str.rstrip())
            try:
                agent_data: jsonrpc.JSONType = json.loads(line_str)
            except Exception as error:
                logger.error("Failed to decode JSON from agent: %s", error)
                continue

            if isinstance(agent_data, dict):
                if "result" in agent_data or "error" in agent_data:
                    # Wait for pending notification dispatch tasks so all ACP
                    # messages are queued before the response future resolves.
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                        tasks.clear()
                    API.process_response(agent_data)
                    continue

            elif isinstance(agent_data, list):
                if not all(isinstance(datum, dict) for datum in agent_data):
                    logger.error("Agent sent invalid data: %r", agent_data)
                    continue

            if not isinstance(agent_data, dict):
                logger.error("Invalid JSON from agent: %r", agent_data)
                continue

            if not isinstance(agent_data, dict):
                logger.error("Invalid JSON from agent: %r", agent_data)
                continue

            # By this point we know it is a JSON RPC call
            assert isinstance(agent_data, dict)
            tasks.add(asyncio.create_task(call_jsonrpc(agent_data)))
            await asyncio.sleep(0)

        # Cancel all remaining tasks and wait for them to finish
        for task in tasks:
            task.cancel()

        # Wait for all tasks to complete cancellation
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if process.returncode:
            assert process.stderr is not None
            fail_details = (await process.stderr.read()).decode("utf-8", "replace")
            self.post_message(
                AgentFail(
                    f"Agent returned a failure code: [b]{process.returncode}",
                    details=fail_details,
                )
            )

        self._process = None

    async def stop(self) -> None:
        """Gracefully stop the process."""
        if self.session_pk is not None:
            db = DB()
            await db.session_update_last_used(self.session_pk)

        # Save session before terminating
        if self.session_id is not None:
            try:
                with self.request():
                    response = api.session_save(self.session_id)
                await asyncio.wait_for(response.wait(), timeout=3)
            except Exception:
                pass

        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass

    async def run(self) -> None:
        """The main logic of the Agent."""
        if constants.ACP_INITIALIZE:
            try:
                await self.acp_initialize()

                if self.session_id is None:
                    await self.acp_new_session()
                else:
                    if not self.agent_capabilities.get("loadSession", False):
                        self.post_message(
                            AgentFail(
                                "Resume not supported",
                                f"{self._agent_data['name']} does not currently support resuming sessions.",
                                help="no_resume",
                            )
                        )
                        return
                    await self.acp_load_session()
                    if self.session_pk is not None:
                        db = DB()
                        await db.session_update_last_used(self.session_pk)
            except jsonrpc.APIError as error:
                if isinstance(error.data, dict):
                    reason = str(
                        error.data.get("reason") or "Failed to initialize agent"
                    )
                    details = str(
                        error.data.get("details") or error.data.get("error") or ""
                    )
                else:
                    reason = "Failed to initialize agent"
                    details = ""
                self.post_message(AgentFail(reason, details))
        elif self.session_id is None:
            await self.acp_new_session()
            if self.session_pk is not None:
                db = DB()
                await db.session_update_last_used(self.session_pk)

        self.post_message(AgentReady())

    async def _ensure_db_session(self) -> None:
        if self.session_pk is not None:
            return
        if not self.supports_load_session:
            return
        data = getattr(self, "_pending_session_data", None)
        if data is None:
            return

        db = DB()
        self.session_pk = await db.session_new(
            data["session_name"],
            data["agent_name"],
            data["agent_identity"],
            data["session_id"],
            protocol=data["protocol"],
            meta=data["meta"],
        )
        self._pending_session_data = None
        await self._save_last_session_to_cdh()

    async def _save_last_session_to_cdh(self) -> None:
        if self.session_id is None:
            return
        try:
            from onecode.agent.cdh_loader import CdhProjectLoader

            cdh_dir = CdhProjectLoader.find_cdh_dir(self.project_root_path)
            if cdh_dir is None:
                return
            data: dict = {
                "agent_session_id": self.session_id,
                "agent_identity": self._agent_data["identity"],
            }
            if self.session_pk is not None:
                data["session_pk"] = self.session_pk
            CdhProjectLoader.save_last_session(cdh_dir, data)
        except Exception:
            pass

    async def send_prompt(self, prompt: str) -> str | None:
        """Send a prompt to the agent.

        !!! note
            This method blocks as it may defer to a thread to read resources.

        Args:
            prompt: Prompt text.
        """
        await self._ensure_db_session()
        prompt_content_blocks = await asyncio.to_thread(
            build_prompt, self.project_root_path, prompt
        )
        return await self.acp_session_prompt(prompt_content_blocks)

    async def acp_initialize(self):
        """Initialize agent."""
        with self.request():
            initialize_response = api.initialize(
                PROTOCOL_VERSION,
                {
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    },
                    "terminal": True,
                },
                {
                    "name": tui.NAME,
                    "title": tui.TITLE,
                    "version": tui.get_version(),
                },
            )

        response = await initialize_response.wait()
        assert response is not None

        # Store agents capabilities
        if agent_capabilities := response.get("agentCapabilities"):
            self.agent_capabilities = agent_capabilities
        if auth_methods := response.get("authMethods"):
            self.auth_methods = auth_methods

    async def acp_new_session(self) -> None:
        """Create a new session."""
        with self.request():
            session_new_response = api.session_new(
                str(self.project_root_path),
                [],
            )
        response = await session_new_response.wait()
        assert response is not None
        self.session_id = response["sessionId"]

        if self.supports_load_session:
            self._pending_session_data = {
                "session_name": "New Session",
                "agent_name": self._agent_data["name"],
                "agent_identity": self._agent_data["identity"],
                "session_id": self.session_id,
                "protocol": "acp",
                "meta": {
                    "cwd": str(self.project_root_path),
                    "agent_data": self._agent_data,
                },
            }

        if (modes := response.get("modes", None)) is not None:
            current_mode = modes["currentModeId"]
            available_modes = modes["availableModes"]
            modes_update = {
                mode["id"]: Mode(
                    mode["id"], mode["name"], mode.get("description", None)
                )
                for mode in available_modes
            }
            self.post_message(messages.SetModes(current_mode, modes_update))

    async def acp_load_session(self) -> None:
        assert self.session_id is not None, "Session id must be set"
        cwd = str(self.project_root_path)
        session_title = None
        if self.session_pk is not None:
            db = DB()
            if (session := await db.session_get(self.session_pk)) is not None:
                session_title = session.get("title") or "Untitled"
                if session["meta_json"]:
                    meta = json.loads(session["meta_json"])
                    if session_cwd := meta.get("cwd", None):
                        cwd = session_cwd
                    if agent_data := meta.get("agent_data"):
                        self._agent_data = agent_data
        else:
            db = DB()
            if (session := await db.session_get_by_agent_session_id(self.session_id)) is not None:
                self.session_pk = session["id"]
                session_title = session.get("title") or "Untitled"

        with self.request():
            session_load_response = api.session_load(cwd, [], self.session_id)
        self.post_message(messages.SessionReplay(active=True))
        try:
            response = await session_load_response.wait()
        finally:
            self.post_message(messages.SessionReplay(active=False))

        if (modes := response.get("modes", None)) is not None:
            current_mode = modes["currentModeId"]
            available_modes = modes["availableModes"]
            modes_update = {
                mode["id"]: Mode(
                    mode["id"], mode["name"], mode.get("description", None)
                )
                for mode in available_modes
            }
            self.post_message(messages.SetModes(current_mode, modes_update))

        if self.session_pk is None:
            self._pending_session_data = {
                "session_name": session_title or "Untitled",
                "agent_name": self._agent_data["name"],
                "agent_identity": self._agent_data["identity"],
                "session_id": self.session_id,
                "protocol": "acp",
                "meta": {
                    "cwd": str(self.project_root_path),
                    "agent_data": self._agent_data,
                },
            }
            await self._ensure_db_session()

        if session_title:
            self.post_message(tui_messages.SessionUpdate(name=session_title))

        await self._save_last_session_to_cdh()

    async def acp_session_prompt(
        self, prompt: list[protocol.ContentBlock]
    ) -> str | None:
        """Send the prompt to the agent.

        Returns:
            The stop reason.

        """
        with self.request():
            session_prompt = api.session_prompt(prompt, self.session_id)
        try:
            result = await session_prompt.wait()
        except jsonrpc.APIError as error:
            details = ""
            match error.data:
                case {"details": details}:
                    pass

            self.post_message(
                AgentFail(
                    "Failed to send prompt" or error.message,
                    (
                        str(details)
                        if details
                        else f"{self._agent_data['name']} returned an error"
                    ),
                )
            )
            return None
        except jsonrpc.JSONRPCError as error:
            self.post_message(
                AgentFail(
                    "Failed to send prompt" or error.message,
                    (error.message or f"{self._agent_data['name']} returned an error"),
                )
            )
            return None

        assert result is not None
        return result.get("stopReason")

    async def acp_session_set_mode(self, mode_id: str) -> str | None:
        """Update the current mode with the agent."""
        with self.request():
            response = api.session_set_mode(self.session_id, mode_id)
        try:
            await response.wait()
        except jsonrpc.APIError as error:
            match error.data:
                case {"details": details}:
                    return details if isinstance(details, str) else "Failed to set mode"
            return "Failed to set mode"
        else:
            return None

    async def set_mode(self, mode_id: str) -> str | None:
        return await self.acp_session_set_mode(mode_id)

    async def set_session_name(self, name: str) -> None:
        if self.session_pk is None:
            return
        db = DB()
        await db.session_update_title(self.session_pk, name)
        if self.session_id:
            from onecode.agent.session import AgentSession
            session = AgentSession(self.session_id)
            if session.load():
                session.name = name
                session.save()
        self.post_message(tui_messages.SessionUpdate(name=name))

    async def acp_session_cancel(self) -> bool:
        with self.request():
            response = api.session_cancel(self.session_id, {})
        try:
            await response.wait()
        except jsonrpc.APIError:
            # No-op if there is nothing to cancel
            return False
        return True

    async def cancel(self) -> bool:
        return await self.acp_session_cancel()
