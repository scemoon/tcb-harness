# TCB CLI Setup & Authentication

## When to Use CLI vs MCP vs SDK

**Use CLI when:**
- Deploying functions, databases, hosting from CI/CD
- Running one-off administrative tasks
- Scripting cloud operations
- Initial setup and configuration

**Use MCP when:**
- AI agent needs structured, composable tools
- Need to chain multiple operations
- Want type-safe parameter handling

**Use SDK when:**
- Building applications that interact with TCB
- Need programmatic access from within functions
- Complex business logic involving TCB services

## Installation

### Prerequisites

- Node.js 16.x or later
- npm or yarn

### Install CloudBase CLI

```bash
npm install -g @cloudbase/cli
```

Verify installation:

```bash
tcb --version
```

### Update CLI

```bash
npm install -g @cloudbase/cli@latest
```

## Authentication Methods

### Method 1: Interactive Login (Recommended for local dev)

```bash
tcb login
```

Opens browser for Tencent Cloud login. Session stored locally.

**Pros:** No credentials stored in plain text
**Cons:** Not suitable for CI/CD

### Method 2: API Key Authentication (Recommended for CI/CD)

```bash
# Set environment variables
export TENCENTCLOUD_SECRETID=your-secret-id
export TENCENTCLOUD_SECRETKEY=your-secret-key

# Or use TCB-specific credentials
export TCB_SECRET_ID=your-secret-id
export TCB_SECRET_KEY=your-secret-key
```

### Method 3: Configuration File

Store credentials in `~/.tcbrc` (not recommended for production):

```json
{
  "secretId": "your-secret-id",
  "secretKey": "your-secret-key"
}
```

### Method 4: Temporary Credentials via CDH

```bash
cdh cloudbase init --secret-id xxx --secret-key xxx
```

This stores credentials in `~/.cloud-harness-tokens.json` and auto-configures MCP.

## Credential Selection Decision Tree

```
Need to run TCB commands?
├── Local development
│   └── tcb login (interactive)
├── CI/CD pipeline
│   ├── Use environment variables (TCB_SECRET_ID/KEY)
│   └── Never commit credentials to git
├── AI Agent (CDH)
│   └── cdh cloudbase init (stores in ~/.cloud-harness-tokens.json)
└── From within a function
    └── Environment variables (injected by TCB)
```

## Verifying Authentication

### Check Login Status

```bash
tcb env info
```

If authenticated, shows current environment info. If not, shows login prompt.

### Check MCP Status (CDH)

```bash
cdh cloudbase status
```

Shows MCP server connection status and credential validity.

## Environment Variables Reference

| Variable | Description | Source |
|----------|-------------|--------|
| `TENCENTCLOUD_SECRETID` | Tencent Cloud root credential ID | Manual or `cdh cloudbase init` |
| `TENCENTCLOUD_SECRETKEY` | Tencent Cloud root credential key | Manual or `cdh cloudbase init` |
| `TCB_SECRET_ID` | TCB-specific credential ID | Manual or `cdh cloudbase init` |
| `TCB_SECRET_KEY` | TCB-specific credential key | Manual or `cdh cloudbase init` |
| `TCB_ENV_ID` | Target environment ID | Manual or `cdh cloudbase init` |

## Project-Level Configuration

For project-specific settings, create `cloudbaserc.json` in project root:

```json
{
  "envId": "env-xxxxx",
  "$schema": "https://raw.githubusercontent.com/TencentCloudBase/tcb-schema/main/schema.json",
  "region": "ap-shanghai"
}
```

### Environment-Specific Config

```json
{
  "envId": "${TCB_ENV_ID}",
  "region": "ap-shanghai",
  "functionRoot": "./functions",
  "functions": [
    {
      "name": "hello",
      "timeout": 10,
      "memory": 256
    }
  ],
  "hosting": {
    "dev": {
      "cloudPath": "./dist",
      "envId": "env-dev"
    }
  }
}
```

## CLI Configuration

### Set Default Region

```bash
tcb configure set region ap-shanghai
```

### Set Default Environment

```bash
tcb configure set envId env-xxxxx
```

### View Current Config

```bash
tcb configure list
```

## Security Best Practices

1. **Never commit credentials** - Add `*.json` with credentials to `.gitignore`
2. **Use environment variables in CI/CD** - Don't hardcode secrets
3. **Rotate credentials regularly** - Use TCB_SECRET_ID/KEY instead of root credentials
4. **Use least privilege** - Create dedicated API keys with minimal permissions
5. **Don't use root credentials** - TCB-specific credentials are preferred

### .gitignore Example

```
# TCB credentials
cloudbaserc.json
!.cloudbaserc.*.json
.tcbrc

# CDH tokens
.cloud-harness-tokens.json
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| ` command not found: tcb` | CLI not installed | `npm install -g @cloudbase/cli` |
| `Login required` | Not authenticated | `tcb login` or set env vars |
| `Invalid credentials` | Wrong secret ID/key | Verify credentials in TCB console |
| `Permission denied` | Insufficient permissions | Check API key permissions in TCB console |
| `envId not found` | Wrong environment ID | `tcb env list` to see valid environments |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
