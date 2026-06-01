from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from cdha.agent.tools.protocol import ToolResult
from cdha.agent.tools.registry import ToolSpec


class LSPServer:
    """Minimal LSP client using stdio JSON-RPC (Clawd-Code pattern)."""

    def __init__(self, command: list[str], root_uri: str):
        self._command = command
        self._root_uri = root_uri
        self._process: subprocess.Popen | None = None
        self._request_id = 0

    def start(self) -> bool:
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._send("initialize", {
                "processId": None,
                "rootUri": self._root_uri,
                "capabilities": {},
            })
            self._send("initialized", {})
            return True
        except Exception:
            self.stop()
            return False

    def _send(self, method: str, params: dict) -> dict | None:
        if not self._process or not self._process.stdin:
            return None
        self._request_id += 1
        msg = json.dumps({"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params})
        self._process.stdin.write((msg + "\n").encode())
        self._process.stdin.flush()
        # Read response
        line = self._process.stdout.readline() if self._process.stdout else b""
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
        return None

    def get_diagnostics(self, uri: str, text: str) -> list[dict]:
        self._send("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": text},
        })
        result = self._send("textDocument/diagnostic", {
            "textDocument": {"uri": uri},
        })
        return (result or {}).get("result", {}).get("diagnostics", [])

    def stop(self):
        if self._process:
            self._process.terminate()
            self._process.wait()


class LSPTool:
    """Query a language server for code intelligence (diagnostics, completions, etc.)."""

    def __init__(self):
        self._servers: dict[str, LSPServer] = {}

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="LSP",
            description="Get code diagnostics and intelligence from a Language Server. Requires lsp server command and file path.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "LSP server command and args (e.g. ['pyright-langserver', '--stdio'])",
                    },
                    "file_path": {"type": "string", "description": "Path to the file to analyze"},
                    "action": {
                        "type": "string",
                        "enum": ["diagnostics"],
                        "description": "What to get from the LSP server",
                    },
                },
                "required": ["command", "file_path", "action"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        command = tool_input.get("command", [])
        file_path = tool_input.get("file_path", "")
        action = tool_input.get("action", "diagnostics")
        if not command or not file_path:
            return ToolResult(name="LSP", output={"error": "command and file_path required"}, is_error=True)

        server_key = "|".join(command)
        if server_key not in self._servers:
            root_uri = Path(file_path).parent.as_uri()
            server = LSPServer(command, root_uri)
            if not server.start():
                return ToolResult(
                    name="LSP",
                    output={"error": f"failed to start LSP server: {command}"},
                    is_error=True,
                )
            self._servers[server_key] = server

        server = self._servers[server_key]
        file_uri = Path(file_path).absolute().as_uri()
        text = ""
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(name="LSP", output={"error": f"cannot read file: {e}"}, is_error=True)

        try:
            if action == "diagnostics":
                diags = server.get_diagnostics(file_uri, text)
                return ToolResult(
                    name="LSP",
                    output={"diagnostics": diags, "count": len(diags)},
                )
            return ToolResult(name="LSP", output={"error": f"unknown action: {action}"}, is_error=True)
        except Exception as e:
            return ToolResult(name="LSP", output={"error": str(e)}, is_error=True)
