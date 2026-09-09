---
name: tcb
description: |
  Tencent CloudBase (TCB) knowledge base for AI Agents.
  Covers: CloudBase Functions (FaaS), CloudBase Run (CaaS), DocDB, COS Storage,
  Static Hosting, Environment Management, CLI, REST API, SDK, MCP integration.
  Supports decision-making for architecture selection, deployment, troubleshooting.
triggers:
  - tcb
  - cloudbase
  - 腾讯云
  - cloudbase functions
  - serverless
  - faas
  - caas
services:
  - cloudbase-functions
  - cloudbase-run
  - cloudbase-database
  - cloudbase-storage
  - cloudbase-hosting
compute_modes:
  - cloudbase-functions  # FaaS
  - cloudbase-run        # CaaS
credentials:
  - TENCENTCLOUD_SECRETID
  - TENCENTCLOUD_SECRETKEY
  - TCB_SECRET_ID
  - TCB_SECRET_KEY
  - TCB_ENV_ID
compatibility:
  cdh: ">=1.4"
  opencode: ">=1.15"
---

# Tencent CloudBase (TCB) Knowledge Base

## What is TCB

Tencent CloudBase (TCB) is a serverless cloud development platform providing:

| Service | Type | Use Case |
|---------|------|----------|
| CloudBase Functions | FaaS | Event-driven serverless functions |
| CloudBase Run | CaaS | Long-running container workloads |
| CloudBase Database (DocDB) | NoSQL | Document storage, JSON-like queries |
| MySQL | RDBMS | Relational data, SQL queries |
| COS | Object Storage | Files, images, static assets |
| CloudBase Hosting | Static Hosting | SPA, static sites, mini-program backends |

## Agent Decision Tree

When agent needs to interact with TCB, follow this decision tree:

```
1. What is the goal?
   ├── Deploy/manage cloud functions → services/cloud-functions.md
   ├── Deploy/manage containers → services/cloud-run.md
   ├── Query/modify data → services/cloud-database.md
   ├── Upload/download files → services/cloud-storage.md
   ├── Deploy static website → services/cloud-hosting.md
   ├── Manage environments → cli/env.md
   └── Debug/deploy → best-practices/troubleshooting.md
```

## How to Interact

### MCP Server (Preferred for structured operations)

When `@cloudbase/cloudbase-mcp` is connected, use `MCPTool`:

```
MCPTool(server="cloudbase", tool="deploy_function", arguments={...})
MCPTool(server="cloudbase", tool="invoke_function", arguments={...})
MCPTool(server="cloudbase", tool="query_database", arguments={...})
```

See `integration/mcp-server.md` for complete tool reference.

### CLI (Preferred for scripts and CI/CD)

```
exec_shell("tcb fn deploy --name hello --dir ./functions")
exec_shell("tcb db query \"SELECT * FROM users\"")
```

See `cli/` directory for complete command reference.

### REST API (For programmatic access)

```
POST https://tcb-api.cloud.tencent.com/mcp/v1/<endpoint>
Headers: X-TencentCloud-SecretId, X-TencentCloud-SecretKey
```

See `api/rest-api.md` for endpoint reference.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        TCB Platform                         │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│   Functions │  Cloud Run  │   Database  │     Storage      │
│    (SCF)    │  (CaaS)     │   (DocDB)   │      (COS)       │
├─────────────┴─────────────┴─────────────┴──────────────────┤
│                      CloudBase Hosting                       │
│                   (Static Site + SSR)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
              Environment ID (env-xxxxx)
                    │
     ┌──────────────┼──────────────┐
     │              │              │
   Backend       Web App      Mobile App
  (Functions)   (Hosting)     (via API)
```

## Environment Model

TCB uses **environment** as the fundamental deployment unit. Each environment has:

- Unique `envId` (e.g., `env-8a9b6c5d`)
- Isolated database instance
- Isolated storage bucket
- Isolated function namespace
- Shared CDN/preview domain: `https://{envId}.tcb-preview.com`

| Environment | Purpose | Access |
|-------------|---------|--------|
| `dev-{user}` | Personal dev sandbox | Per-component deploy allowed |
| `preview` | Integration testing | Stack deploy only |
| `staging` | Pre-production | Stack deploy only |
| `production` | Live traffic | Stack deploy + human approval |

## Credential Management

See `security/authentication.md` for complete guide.

| Variable | Description |
|----------|-------------|
| `TENCENTCLOUD_SECRETID` | Tencent Cloud root credential |
| `TENCENTCLOUD_SECRETKEY` | Tencent Cloud root credential |
| `TCB_SECRET_ID` | TCB-specific credential (recommended) |
| `TCB_SECRET_KEY` | TCB-specific credential (recommended) |
| `TCB_ENV_ID` | Target environment ID |

## Quick Reference

### Deploy a Cloud Function

```bash
# 1. Create function directory with cloudbaserc.json
# 2. Deploy
tcb fn deploy --name hello --dir ./functions --env $TCB_ENV_ID

# Or use MCP
MCPTool(server="cloudbase", tool="deploy_function", args={name: "hello", dir: "./functions"})
```

### Query Database

```bash
tcb db query "SELECT * FROM users WHERE status = 'active'" --env $TCB_ENV_ID
```

### Deploy Static Site

```bash
tcb hosting deploy --env $TCB_ENV_ID --dir ./dist
```

## File Structure

```
tcb/
├── SKILL.md                    # This file
├── provider.yaml               # AI-DLC provider config
├── preview.yaml                # Preview deployment flow
├── deployment.yaml             # Production deployment pipeline
├── services/
│   ├── overview.md             # Platform overview
│   ├── cloud-functions.md      # CloudBase Functions (FaaS)
│   ├── cloud-database.md       # DocDB + MySQL
│   ├── cloud-storage.md        # COS object storage
│   ├── cloud-hosting.md        # Static hosting
│   └── cloud-run.md            # CloudBase Run (CaaS)
├── cli/
│   ├── setup.md                # Installation & login
│   ├── env.md                  # Environment management
│   ├── functions.md            # Function management (fn)
│   ├── database.md             # Database management (db)
│   ├── storage.md              # Storage management (storage)
│   └── hosting.md              # Hosting management (hosting)
├── api/
│   ├── rest-api.md             # REST API reference
│   └── sdk.md                  # Node.js SDK
├── integration/
│   ├── mcp-server.md           # MCP server integration
│   └── ci-cd.md                # CI/CD integration
├── security/
│   └── authentication.md       # Auth & credentials
└── best-practices/
    ├── function-design.md      # Function design patterns
    ├── database-design.md      # Database schema design
    └── troubleshooting.md      # Common issues & solutions
```
