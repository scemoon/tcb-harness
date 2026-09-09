# TCB MCP Server Integration

## What is MCP

MCP (Model Context Protocol) provides structured, type-safe tool access for AI agents. Instead of parsing CLI output, agents use typed tools with documented parameters.

## MCP Server: @cloudbase/cloudbase-mcp

The official TCB MCP server provides tools for:
- Deploying functions
- Invoking functions
- Querying databases
- Managing storage
- Deploying hosting
- Getting environment info

## When to Use MCP vs CLI

| Scenario | Use |
|----------|-----|
| AI agent executing cloud operations | MCP (structured, composable) |
| One-off admin task | CLI |
| CI/CD pipeline | CLI (or MCP with token) |
| Scripted automation | CLI |
| Debugging | CLI (more detailed output) |

## Connection Methods

### Auto-Configuration via CDH (Recommended)

```bash
cdh cloudbase init --secret-id xxx --secret-key xxx --env-id xxx
```

This writes the opencode-style entry to `~/.onecode/mcp.json` (with `{env:VAR}` templates that resolve at connect time) and stores the credentials in `~/.cloud-harness-tokens.json`.

The resulting `mcp.json` entry:

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

### stdio (Manual)

```bash
cdh mcp add cloudbase --type stdio \
  --command npx,-y,@cloudbase/cloudbase-mcp@latest \
  --env TENCENTCLOUD_SECRETID={env:TENCENTCLOUD_SECRETID},TENCENTCLOUD_SECRETKEY={env:TENCENTCLOUD_SECRETKEY}
```

### HTTP (For remote servers)

```bash
cdh mcp add cloudbase --type http \
  --url "https://tcb-api.cloud.tencent.com/mcp/v1?env_id=xxx" \
  --headers "X-TencentCloud-SecretId={env:TENCENTCLOUD_SECRETID}"
```

### Diagnostic / OAuth

```bash
cdh cloudbase status          # live probe + tool count
cdh mcp debug cloudbase       # full config dump + live probe
cdh mcp migrate               # one-shot: mcps.yaml -> mcp.json (legacy)
cdh mcp auth <name>           # OAuth flow (for future remote servers)
cdh mcp logout <name>         # clear stored OAuth token
```

## MCP Tools Reference

### Functions

#### deploy_function

Deploy a cloud function.

```javascript
MCPTool(server="cloudbase", tool="deploy_function", arguments={
  name: "hello",
  dir: "./functions/hello",
  envId: "env-xxxxx",
  options: {
    timeout: 60,
    memory: 256,
    httpFn: true
  }
})
```

#### invoke_function

Invoke a function and get result.

```javascript
MCPTool(server="cloudbase", tool="invoke_function", arguments={
  name: "hello",
  params: { userId: "123" },
  envId: "env-xxxxx"
})
```

#### list_functions

List all functions in environment.

```javascript
MCPTool(server="cloudbase", tool="list_functions", arguments={
  envId: "env-xxxxx"
})
```

#### get_function_logs

Get function execution logs.

```javascript
MCPTool(server="cloudbase", tool="get_function_logs", arguments={
  name: "hello",
  envId: "env-xxxxx",
  limit: 50
})
```

### Database

#### query_database

Query DocDB with Mongoose-like syntax.

```javascript
MCPTool(server="cloudbase", tool="query_database", arguments={
  query: "SELECT * FROM users WHERE status = 'active'",
  envId: "env-xxxxx"
})
```

#### insert_document

Insert a document into collection.

```javascript
MCPTool(server="cloudbase", tool="insert_document", arguments={
  collection: "users",
  data: { name: "Alice", email: "alice@example.com" },
  envId: "env-xxxxx"
})
```

#### update_document

Update a document.

```javascript
MCPTool(server="cloudbase", tool="update_document", arguments={
  collection: "users",
  query: { _id: "doc-id" },
  update: { $set: { status: "inactive" } },
  envId: "env-xxxxx"
})
```

#### delete_document

Delete a document.

```javascript
MCPTool(server="cloudbase", tool="delete_document", arguments={
  collection: "users",
  query: { _id: "doc-id" },
  envId: "env-xxxxx"
})
```

### Storage

#### upload_file

Upload a file to COS.

```javascript
MCPTool(server="cloudbase", tool="upload_file", arguments={
  localPath: "./avatar.jpg",
  cloudPath: "/uploads/avatar.jpg",
  envId: "env-xxxxx"
})
```

#### download_file

Download a file from COS.

```javascript
MCPTool(server="cloudbase", tool="download_file", arguments={
  cloudPath: "/uploads/avatar.jpg",
  localPath: "./downloads/avatar.jpg",
  envId: "env-xxxxx"
})
```

#### list_storage

List files in storage path.

```javascript
MCPTool(server="cloudbase", tool="list_storage", arguments={
  path: "/uploads",
  envId: "env-xxxxx"
})
```

#### get_file_url

Get temporary URL for file access.

```javascript
MCPTool(server="cloudbase", tool="get_file_url", arguments={
  cloudPath: "/uploads/private.pdf",
  envId: "env-xxxxx",
  maxAge: 3600
})
```

### Hosting

#### deploy_hosting

Deploy static site.

```javascript
MCPTool(server="cloudbase", tool="deploy_hosting", arguments={
  dir: "./dist",
  envId: "env-xxxxx",
  buildEnv: { BACKEND_URL: "https://api.example.com" }
})
```

### Environment

#### get_environment_info

Get environment details.

```javascript
MCPTool(server="cloudbase", tool="get_environment_info", arguments={
  envId: "env-xxxxx"
})
```

#### list_environments

List all environments.

```javascript
MCPTool(server="cloudbase", tool="list_environments", arguments={})
```

## MCP Resources

### list_resources

List available TCB resources.

```javascript
MCPResources(server="cloudbase", action="list")
```

Returns: Functions, collections, storage paths, environment info.

### resource template

```
cloudbase://{envId}/function/{functionName}
cloudbase://{envId}/collection/{collectionName}
cloudbase://{envId}/storage/{path}
```

## Agent Workflows

### Workflow: Deploy and Test Function

```javascript
// 1. Deploy function
const deployResult = await MCPTool(server="cloudbase", tool="deploy_function", arguments={
  name: "hello",
  dir: "./functions/hello",
  envId: "env-xxxxx"
});

// 2. Invoke function
const invokeResult = await MCPTool(server="cloudbase", tool="invoke_function", arguments={
  name: "hello",
  params: { test: true },
  envId: "env-xxxxx"
});

// 3. Check logs if error
if (invokeResult.error) {
  const logs = await MCPTool(server="cloudbase", tool="get_function_logs", arguments={
    name: "hello",
    envId: "env-xxxxx"
  });
}
```

### Workflow: Query and Update Data

```javascript
// 1. Query users
const users = await MCPTool(server="cloudbase", tool="query_database", arguments={
  query: "SELECT * FROM users WHERE status = 'active' LIMIT 10",
  envId: "env-xxxxx"
});

// 2. Update first user
if (users.data.length > 0) {
  await MCPTool(server="cloudbase", tool="update_document", arguments={
    collection: "users",
    query: { _id: users.data[0]._id },
    update: { $set: { lastAccessed: new Date() } },
    envId: "env-xxxxx"
  });
}
```

## Configuration

### Manual Configuration

Create `~/.cloudbase/mcp.json`:

```json
{
  "envId": "env-xxxxx",
  "credentials": {
    "secretId": "your-secret-id",
    "secretKey": "your-secret-key"
  }
}
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TENCENTCLOUD_SECRETID` | Tencent Cloud credential ID |
| `TENCENTCLOUD_SECRETKEY` | Tencent Cloud credential key |
| `TCB_ENV_ID` | Default environment ID |

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| MCP server not responding | Server not started | Restart MCP server |
| `Invalid credentials` | Wrong secret ID/key | Verify credentials |
| `Environment not found` | Wrong env ID | Check with `cdh cloudbase status` |
| `Tool not found` | Wrong tool name | Check tool list in MCP server docs |

For troubleshooting → `../best-practices/troubleshooting.md`
