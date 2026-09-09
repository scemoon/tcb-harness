from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec


class LSPClient:
    def __init__(self, command: list[str], root_uri: str, workspace_root: Path | None = None):
        self._command = command
        self._root_uri = root_uri
        self._workspace_root = workspace_root or Path(root_uri.replace("file://", "")) if root_uri else Path.cwd()
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._pending: dict[int, Any] = {}

    def start(self) -> bool:
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            resp = self._send("initialize", {
                "processId": None,
                "rootUri": self._root_uri,
                "capabilities": {
                    "textDocument": {
                        "definition": {"dynamicRegistration": True},
                        "references": {"dynamicRegistration": True},
                        "hover": {"dynamicRegistration": True},
                        "documentSymbol": {"dynamicRegistration": True},
                        "callHierarchy": {"dynamicRegistration": True},
                    },
                    "workspace": {
                        "symbol": {"dynamicRegistration": True},
                    },
                },
            })
            self._send("initialized", {"parameters": {}})
            return resp is not None
        except Exception:
            self.stop()
            return False

    def _send(self, method: str, params: dict) -> dict | None:
        if not self._process or not self._process.stdin:
            return None
        self._request_id += 1
        msg_id = self._request_id
        msg = json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        self._process.stdin.write((msg + "\n").encode())
        self._process.stdin.flush()

        line = self._process.stdout.readline() if self._process.stdout else b""
        if line:
            try:
                resp = json.loads(line)
                if resp.get("id") == msg_id:
                    if "error" in resp:
                        return {"error": resp["error"]}
                    return resp.get("result")
                return None
            except json.JSONDecodeError:
                pass
        return None

    def _read_notification(self) -> dict | None:
        if not self._process or not self._process.stdout:
            return None
        import select
        if select.select([self._process.stdout], [], [], 0.1)[0]:
            line = self._process.stdout.readline()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        return None

    def _position_params(self, file_uri: str, line: int, character: int) -> dict:
        return {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        }

    def goto_definition(self, file_uri: str, line: int, character: int) -> list[dict]:
        result = self._send("textDocument/definition", self._position_params(file_uri, line, character))
        if result is None:
            return []
        if isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            result = [result] if result else []
        return [self._location_to_dict(loc) for loc in result if loc]

    def find_references(self, file_uri: str, line: int, character: int, include_declaration: bool = True) -> list[dict]:
        params = self._position_params(file_uri, line, character)
        params["context"] = {"includeDeclaration": include_declaration}
        result = self._send("textDocument/references", params)
        if result is None:
            return []
        if isinstance(result, dict) and "error" in result:
            return []
        return [self._location_to_dict(loc) for loc in result if loc]

    def hover(self, file_uri: str, line: int, character: int) -> dict | None:
        result = self._send("textDocument/hover", self._position_params(file_uri, line, character))
        if result is None or isinstance(result, dict) and "error" in result:
            return None
        if not result:
            return None
        return {
            "contents": result.get("contents", ""),
            "range": result.get("range"),
        }

    def document_symbol(self, file_uri: str) -> list[dict]:
        result = self._send("textDocument/documentSymbol", {"textDocument": {"uri": file_uri}})
        if result is None or isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            return []
        symbols = []
        for item in result:
            if isinstance(item, dict):
                symbols.append({
                    "name": item.get("name", ""),
                    "kind": item.get("kind", ""),
                    "location": self._location_to_dict(item.get("location")),
                    "containerName": item.get("containerName", ""),
                })
        return symbols

    def workspace_symbol(self, query: str) -> list[dict]:
        result = self._send("workspace/symbol", {"query": query})
        if result is None or isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            return []
        symbols = []
        for item in result:
            if isinstance(item, dict):
                symbols.append({
                    "name": item.get("name", ""),
                    "kind": item.get("kind", ""),
                    "location": self._location_to_dict(item.get("location")),
                    "containerName": item.get("containerName", ""),
                })
        return symbols

    def goto_implementation(self, file_uri: str, line: int, character: int) -> list[dict]:
        result = self._send("textDocument/implementation", self._position_params(file_uri, line, character))
        if result is None or isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            result = [result] if result else []
        return [self._location_to_dict(loc) for loc in result if loc]

    def call_hierarchy(self, file_uri: str, line: int, character: int) -> dict:
        result = self._send("textDocument/prepareCallHierarchy", self._position_params(file_uri, line, character))
        if result is None or isinstance(result, dict) and "error" in result:
            return {"incomingCalls": [], "outgoingCalls": []}

        if not isinstance(result, list) or not result:
            return {"incomingCalls": [], "outgoingCalls": []}

        item = result[0] if result else {}
        call_hierarchy = {"incomingCalls": [], "outgoingCalls": []}

        if item.get("from"):
            incoming = self._send("callHierarchy/incomingCalls", {"item": item})
            if incoming and isinstance(incoming, list):
                call_hierarchy["incomingCalls"] = [
                    {"from": c.get("from", {}).get("name", ""), "locations": [self._location_to_dict(loc) for loc in c.get("from", {}).get("locations", [])]}
                    for c in incoming if isinstance(c, dict)
                ]

        if item.get("to"):
            outgoing = self._send("callHierarchy/outgoingCalls", {"item": item})
            if outgoing and isinstance(outgoing, list):
                call_hierarchy["outgoingCalls"] = [
                    {"to": c.get("to", {}).get("name", ""), "locations": [self._location_to_dict(loc) for loc in c.get("to", {}).get("locations", [])]}
                    for c in outgoing if isinstance(c, dict)
                ]

        return call_hierarchy

    def incoming_calls(self, file_uri: str, line: int, character: int) -> list[dict]:
        result = self._send("callHierarchy/incomingCalls", {
            "item": {
                "name": "",
                "uri": file_uri,
                "range": {"start": {"line": line, "character": character}, "end": {"line": line, "character": character}},
            }
        })
        if result is None or isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            return []
        return [
            {"from": c.get("from", {}).get("name", ""), "locations": [self._location_to_dict(loc) for loc in c.get("from", {}).get("locations", [])]}
            for c in result if isinstance(c, dict)
        ]

    def outgoing_calls(self, file_uri: str, line: int, character: int) -> list[dict]:
        result = self._send("callHierarchy/outgoingCalls", {
            "item": {
                "name": "",
                "uri": file_uri,
                "range": {"start": {"line": line, "character": character}, "end": {"line": line, "character": character}},
            }
        })
        if result is None or isinstance(result, dict) and "error" in result:
            return []
        if not isinstance(result, list):
            return []
        return [
            {"to": c.get("to", {}).get("name", ""), "locations": [self._location_to_dict(loc) for loc in c.get("to", {}).get("locations", [])]}
            for c in result if isinstance(c, dict)
        ]

    def diagnostics(self, file_uri: str, text: str) -> list[dict]:
        self._send("textDocument/didOpen", {
            "textDocument": {"uri": file_uri, "languageId": "python", "version": 1, "text": text},
        })
        result = self._send("textDocument/diagnostic", {"textDocument": {"uri": file_uri}})
        if result is None:
            return []
        if isinstance(result, dict) and "error" in result:
            return []
        return result.get("diagnostics", []) if isinstance(result, dict) else []

    def _location_to_dict(self, loc: Any) -> dict | None:
        if not isinstance(loc, dict):
            return None
        uri = loc.get("uri", "")
        range_data = loc.get("range", {})
        if not range_data:
            return {"uri": uri, "line": 0, "endLine": 0, "column": 0, "endColumn": 0}
        start = range_data.get("start", {})
        end = range_data.get("end", {})
        return {
            "uri": uri,
            "line": start.get("line", 0) + 1,
            "endLine": end.get("line", 0) + 1,
            "column": start.get("character", 0) + 1,
            "endColumn": end.get("character", 0) + 1,
        }

    def stop(self):
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None


class LSPTool(Tool):
    def __init__(self):
        self._servers: dict[str, LSPClient] = {}

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="LSP",
            description="Get code intelligence from a Language Server. Supports: diagnostics, gotoDefinition, findReferences, hover, documentSymbol, workspaceSymbol, gotoImplementation, callHierarchy, incomingCalls, outgoingCalls.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "LSP server command (e.g. ['pyright-langserver', '--stdio'])",
                    },
                    "file_path": {"type": "string", "description": "Path to the file to analyze"},
                    "action": {
                        "type": "string",
                        "enum": [
                            "diagnostics",
                            "gotoDefinition",
                            "findReferences",
                            "hover",
                            "documentSymbol",
                            "workspaceSymbol",
                            "gotoImplementation",
                            "callHierarchy",
                            "incomingCalls",
                            "outgoingCalls",
                        ],
                        "description": "LSP action to perform",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-based) for position-based actions (gotoDefinition, findReferences, hover, gotoImplementation, callHierarchy, incomingCalls, outgoingCalls)",
                    },
                    "character": {
                        "type": "integer",
                        "description": "Character position (1-based) for position-based actions",
                    },
                    "query": {
                        "type": "string",
                        "description": "Query string for workspaceSymbol action",
                    },
                    "include_declaration": {
                        "type": "boolean",
                        "description": "Include declaration in references (default: true)",
                        "default": True,
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
            workspace_root = Path(file_path).parent if file_path else Path.cwd()
            root_uri = workspace_root.as_uri()
            server = LSPClient(command, root_uri, workspace_root)
            if not server.start():
                return ToolResult(name="LSP", output={"error": f"failed to start LSP server: {command}"}, is_error=True)
            self._servers[server_key] = server

        server = self._servers[server_key]
        file_uri = Path(file_path).absolute().as_uri()
        text = ""
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(name="LSP", output={"error": f"cannot read file: {e}"}, is_error=True)

        line = tool_input.get("line", 1) - 1
        character = tool_input.get("character", 1) - 1

        try:
            if action == "diagnostics":
                diags = server.diagnostics(file_uri, text)
                return ToolResult(name="LSP", output={"diagnostics": diags, "count": len(diags)})

            elif action == "gotoDefinition":
                results = server.goto_definition(file_uri, line, character)
                return ToolResult(name="LSP", output={"definitions": results, "count": len(results)})

            elif action == "findReferences":
                include_decl = tool_input.get("include_declaration", True)
                results = server.find_references(file_uri, line, character, include_decl)
                return ToolResult(name="LSP", output={"references": results, "count": len(results)})

            elif action == "hover":
                result = server.hover(file_uri, line, character)
                if result:
                    return ToolResult(name="LSP", output=result)
                return ToolResult(name="LSP", output={"error": "no hover info available"})

            elif action == "documentSymbol":
                symbols = server.document_symbol(file_uri)
                return ToolResult(name="LSP", output={"symbols": symbols, "count": len(symbols)})

            elif action == "workspaceSymbol":
                query = tool_input.get("query", "")
                symbols = server.workspace_symbol(query)
                return ToolResult(name="LSP", output={"symbols": symbols, "count": len(symbols)})

            elif action == "gotoImplementation":
                results = server.goto_implementation(file_uri, line, character)
                return ToolResult(name="LSP", output={"implementations": results, "count": len(results)})

            elif action == "callHierarchy":
                result = server.call_hierarchy(file_uri, line, character)
                return ToolResult(name="LSP", output=result)

            elif action == "incomingCalls":
                results = server.incoming_calls(file_uri, line, character)
                return ToolResult(name="LSP", output={"incomingCalls": results, "count": len(results)})

            elif action == "outgoingCalls":
                results = server.outgoing_calls(file_uri, line, character)
                return ToolResult(name="LSP", output={"outgoingCalls": results, "count": len(results)})

            else:
                return ToolResult(name="LSP", output={"error": f"unknown action: {action}"}, is_error=True)

        except Exception as e:
            return ToolResult(name="LSP", output={"error": str(e)}, is_error=True)


    def stop_all(self):
        for server in self._servers.values():
            server.stop()
        self._servers.clear()
