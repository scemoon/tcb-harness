def make_tools_schema(register_dynamic: bool = True) -> list[dict]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Read",
                "description": "Read file contents with optional line range. Returns content with line numbers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "offset": {"type": "integer", "description": "Starting line offset (0-based)", "default": 0},
                        "limit": {"type": "integer", "description": "Max lines to read (0 = all)", "default": 0}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Write",
                "description": "Create or overwrite a file with content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "content": {"type": "string", "description": "Full file content to write"}
                    },
                    "required": ["path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Edit",
                "description": "Replace exact string in file. Must read file first. old_string MUST be unique.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "old_string": {"type": "string", "description": "Exact text to replace"},
                        "new_string": {"type": "string", "description": "Replacement text"}
                    },
                    "required": ["path", "old_string", "new_string"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Insert",
                "description": "Insert text at a specific line in a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "line": {"type": "integer", "description": "Line number to insert after (-1 for beginning)"},
                        "text": {"type": "string", "description": "Text to insert"}
                    },
                    "required": ["path", "line", "text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "UndoEdit",
                "description": "Undo the most recent Edit/Insert operation on a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to undo last edit on"}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Glob",
                "description": "Find files matching a glob pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern to match"}
                    },
                    "required": ["pattern"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Grep",
                "description": "Search for regex pattern in files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search"},
                        "include": {"type": "string", "description": "File pattern filter"}
                    },
                    "required": ["pattern"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "List",
                "description": "List directory contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path", "default": "."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "description": "Execute a shell command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60}
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "WebFetch",
                "description": "Fetch a URL and extract information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch"},
                        "prompt": {"type": "string", "description": "What to extract"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "WebSearch",
                "description": "Search the web and return results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "SendMessage",
                "description": "Send a user-visible message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to show"},
                        "attachments": {"type": "array", "items": {"type": "string"}, "description": "File paths to attach"}
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Task",
                "description": "Spawn a subagent.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_type": {"type": "string", "default": "general"},
                        "prompt": {"type": "string", "description": "Task description"}
                    },
                    "required": ["prompt"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskCreate",
                "description": "Create a task with dependency tracking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "Task subject"},
                        "description": {"type": "string", "description": "Task description"},
                        "activeForm": {"type": "string"},
                        "metadata": {"type": "object"}
                    },
                    "required": ["subject", "description"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskGet",
                "description": "Retrieve a task by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "taskId": {"type": "string"}
                    },
                    "required": ["taskId"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskList",
                "description": "List all tasks.",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskUpdate",
                "description": "Update a task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "taskId": {"type": "string"},
                        "subject": {"type": "string"},
                        "description": {"type": "string"},
                        "activeForm": {"type": "string"},
                        "status": {"type": "string"},
                        "owner": {"type": "string"},
                        "addBlocks": {"type": "array", "items": {"type": "string"}},
                        "addBlockedBy": {"type": "array", "items": {"type": "string"}},
                        "metadata": {"type": "object"},
                        "output": {"type": "string"}
                    },
                    "required": ["taskId"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskOutput",
                "description": "Get output for a task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"}
                    },
                    "required": ["task_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TaskStop",
                "description": "Stop a running task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"}
                    },
                    "required": ["task_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TodoCreate",
                "description": "Create a todo item.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TodoList",
                "description": "List all todos.",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TodoComplete",
                "description": "Mark a todo as done.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todo_id": {"type": "string"}
                    },
                    "required": ["todo_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "AskUser",
                "description": "Ask the user a question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "context": {"type": "string"}
                    },
                    "required": ["question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Agent",
                "description": "Execute a batch of tool calls as an atomic step.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "calls": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "input": {"type": "object"}
                                },
                                "required": ["name", "input"]
                            }
                        },
                        "stop_on_error": {"type": "boolean"}
                    },
                    "required": ["calls"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ToolSearch",
                "description": "Search for available tools by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "Skill",
                "description": "Run a registered skill by name with optional arguments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Skill name"},
                        "arguments": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Positional arguments ($0, $1, $path, $ARGUMENTS)",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "MCPTool",
                "description": "Call a tool on a connected MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string"},
                        "tool": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["server", "tool"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "MCPResources",
                "description": "List or read resources from an MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string"},
                        "action": {"type": "string", "enum": ["list", "read"]},
                        "uri": {"type": "string"},
                    },
                    "required": ["server", "action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "LSP",
                "description": "Get code diagnostics from a Language Server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "array", "items": {"type": "string"},
                            "description": "LSP server command",
                        },
                        "file_path": {"type": "string"},
                        "action": {"type": "string", "enum": ["diagnostics"]},
                    },
                    "required": ["command", "file_path", "action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "CronCreate",
                "description": "Create a scheduled cron job.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "interval_seconds": {"type": "integer"},
                        "command": {"type": "string"},
                    },
                    "required": ["name", "interval_seconds", "command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "CronList",
                "description": "List all cron jobs.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "CronRemove",
                "description": "Remove a cron job.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "Worktree",
                "description": "Manage git worktrees.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "add", "prune"]},
                        "path": {"type": "string"},
                        "branch": {"type": "string"},
                    },
                    "required": ["action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ConfigRead",
                "description": "Read configuration values.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Config key path"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ConfigWrite",
                "description": "Set configuration values (no secrets).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
        },
    ]
    return tools


TOOLS_SCHEMA = make_tools_schema()
