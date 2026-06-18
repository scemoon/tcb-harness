# Shell Skill

Provides shell command execution capabilities and common operations.

## Agent Tools

| Operation | Command |
|-----------|---------|
| Execute command | `exec_shell("command")` |
| Check output | read from command result |
| Working directory | defaults to current workspace |

## Common Commands

### File Operations
```bash
ls -la                    # List files with details
mkdir -p path             # Create directory
rm -rf path              # Remove directory recursively
cp -r src dst             # Copy recursively
mv src dst                # Move/rename
find . -name "*.py"      # Find files
```

### Git Operations (see git skill)
```bash
git status
git add .
git commit -m "message"
git push
```

### npm/Node
```bash
npm install
npm run build
npm test
```

### Python
```bash
python3 -m pip install <package>
python3 script.py
```

## Safety

- Agent should confirm destructive commands (rm -rf, etc.) with user
- Shell whitelist configurable in cdh.config.yaml
- Interactive commands (vim, less, etc.) may not work in agent mode

## Agent Integration

When this skill is active, the agent can:
1. Execute commands via `exec_shell` tool
2. Parse command output for decision making
3. Chain commands with pipes
4. Run background tasks with `&`