# CloudBase Skill

Provides Tencent CloudBase (TCB) management — serverless functions, database, hosting, storage, and environment operations. Supports both `tcb` CLI and `@cloudbase/cloudbase-mcp` MCP server.

## Prerequisites

```bash
# Install CloudBase CLI
npm install -g @cloudbase/cli

# Login (interactive)
tcb login
```

## MCP Server (Auto-Configured)

The `@cloudbase/cloudbase-mcp` package provides structured tool access. When this skill is enabled, onecode automatically registers a CloudBase MCP entry in `~/.onecode/mcp.json` (opencode-style declarative config) and connects it using credentials from environment variables or `~/.cloud-harness-tokens.json`.

**Quick setup (recommended):**
```
cdh cloudbase init --secret-id xxx --secret-key xxx --env-id xxx
```

The opencode-style entry written to `~/.onecode/mcp.json`:

```json
{
  "mcp": {
    "cloudbase": {
      "type": "local",
      "command": ["npx", "-y", "@cloudbase/cloudbase-mcp@latest"],
      "environment": {
        "TENCENTCLOUD_SECRETID": "{env:TENCENTCLOUD_SECRETID}",
        "TENCENTCLOUD_SECRETKEY": "{env:TENCENTCLOUD_SECRETKEY}",
        "CLOUDBASE_ENV_ID": "{env:CLOUDBASE_ENV_ID}"
      },
      "enabled": true
    }
  }
}
```

`{env:VAR}` references are resolved at connect time, so the same config works whether credentials are exported in the environment or stored in the tokens file (which is consulted automatically by `_discover_credentials()`).

**Status / diagnostics:**
```
cdh cloudbase status          # probe + tool count
cdh mcp debug cloudbase       # full config dump + auth state + live probe
```

**Manual config (alternative to auto-config):**

stdio:
```
cdh mcp add cloudbase --type stdio \
  --command npx,-y,@cloudbase/cloudbase-mcp@latest \
  --env TENCENTCLOUD_SECRETID={env:TENCENTCLOUD_SECRETID},TENCENTCLOUD_SECRETKEY={env:TENCENTCLOUD_SECRETKEY}
```

HTTP (hosted mode):
```
cdh mcp add cloudbase --type http \
  --url https://tcb-api.cloud.tencent.com/mcp/v1?env_id=xxx \
  --headers X-TencentCloud-SecretId={env:TENCENTCLOUD_SECRETID}
```

**OAuth (for future remote servers):** `cdh mcp auth <name>` opens a flow and stores the token in `~/.onecode/mcp-auth.json`; `cdh mcp logout <name>` clears it.

### Agent Tools (MCP)

Once the MCP server is connected, use `MCPTool`:

| Operation | Tool |
|-----------|------|
| Deploy function | `MCPTool(server="cloudbase", tool="deploy_function", arguments={...})` |
| Invoke function | `MCPTool(server="cloudbase", tool="invoke_function", arguments={...})` |
| Query database  | `MCPTool(server="cloudbase", tool="query_database", arguments={...})` |
| Deploy hosting  | `MCPTool(server="cloudbase", tool="deploy_hosting", arguments={...})` |
| Upload file     | `MCPTool(server="cloudbase", tool="upload_file", arguments={...})` |
| List resources  | `MCPResources(server="cloudbase", action="list")` |

Refer to the MCP server's tool list at runtime for exact schemas and available tools.

## CLI (Alternative)

### Agent Tools (CLI)

| Operation | Tool |
|-----------|------|
| Execute tcb command | `exec_shell("tcb ...")` |
| Check deployment result | read from command output |

### Environment Management

```bash
tcb env list                        # List all environments
tcb env use <env-id>                # Switch to target environment
tcb env create <env-name>           # Create new environment
tcb env info                        # Show current environment info
```

### Functions (Serverless)

```bash
tcb fn list                         # List all functions
tcb fn deploy --name hello --dir ./functions   # Deploy function
tcb fn invoke --name hello --params '{}'       # Invoke function
tcb fn logs --name hello            # View function logs
tcb fn detail --name hello          # Function details
tcb fn delete --name hello          # Delete function
tcb fn trigger --name hello --cron "0 0 * * *" --url "/cron"  # Set timer trigger
```

### Database

```bash
tcb db list                         # List collections
tcb db query "SELECT * FROM users"  # Query document database
tcb db migrate                      # Run database migrations
tcb db import --collection users --file ./data.json  # Import data
tcb db export --collection users --file ./backup.json # Export data
```

### Hosting (Static Websites)

```bash
tcb hosting deploy --env <env-id>   # Deploy static hosting
tcb hosting list                    # List hosting projects
tcb hosting detail                  # Hosting project details
tcb hosting delete                  # Delete hosting project
```

### Storage

```bash
tcb storage list                    # List files in storage
tcb storage upload --local ./file.txt --remote /path  # Upload file
tcb storage download --local ./out.txt --remote /path # Download file
tcb storage delete --remote /path   # Delete file
tcb storage url --remote /path      # Get file URL
```

## Credential Configuration

| Variable | Description | Source |
|----------|-------------|--------|
| TENCENTCLOUD_SECRETID | Tencent Cloud secret ID | env / `cdh cloudbase init` / `~/.cloud-harness-tokens.json` |
| TENCENTCLOUD_SECRETKEY | Tencent Cloud secret key | env / `cdh cloudbase init` / `~/.cloud-harness-tokens.json` |
| TCB_SECRET_ID | Tencent Cloud secret ID (CLI) | env / tokens file |
| TCB_SECRET_KEY | Tencent Cloud secret key (CLI) | env / tokens file |
| TCB_ENV_ID | Default CloudBase environment ID | env |

## Agent Integration

When this skill is active, the agent can:
1. Auto-configure CloudBase MCP server on skill load (credentials permitting)
2. Use MCP server for structured cloud operations (preferred)
3. Fall back to `tcb` CLI via `exec_shell` when MCP is unavailable
4. Run `cdh cloudbase init` or `cdh cloudbase status` for setup and diagnostics
5. Deploy functions, manage databases, host static sites, and manage storage
6. Chain deployment commands for full-stack delivery
7. Read MCP server resources for environment status and configuration
