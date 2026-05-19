TOOLS_SCHEMA = [
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
            "description": "Replace exact string in file. Must read file first to know current content.",
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
            "name": "Glob",
            "description": "Find files matching a glob pattern (e.g. **/*.py).",
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
                    "include": {"type": "string", "description": "File pattern to filter (e.g. *.py)", "default": None}
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
            "description": "Execute a shell command and return stdout/stderr.",
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
                    "prompt": {"type": "string", "description": "What to extract from the page", "default": None}
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
            "name": "Task",
            "description": "Spawn a subagent to handle a subtask asynchronously.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string", "description": "Subagent type (general|explore|scout)", "default": "general"},
                    "prompt": {"type": "string", "description": "Task description for the subagent"}
                },
                "required": ["prompt"]
            }
        }
    },
]
