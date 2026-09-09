# TCB Platform Overview

## What is Tencent CloudBase

Tencent CloudBase (TCB) is a serverless cloud development platform that provides a complete cloud-native backend infrastructure. It eliminates the need to manage servers while providing database, storage, computing, and hosting capabilities.

## Core Services

| Service | Type | Description | Limits |
|---------|------|-------------|--------|
| CloudBase Functions | FaaS | Event-driven serverless functions | 60s timeout, 1536MB memory, 100 max instances |
| CloudBase Run | CaaS | Container-based hosting | 3600s timeout, 4096MB memory |
| CloudBase Database | NoSQL | Document database (JSON-like) | 2GB storage per env |
| MySQL | RDBMS | Relational database | 20GB storage per env |
| COS | Object Storage | File storage | 50GB per env |
| CloudBase Hosting | Static | Static website + SSR support | 2GB per site |

## Agent Decision Guide

### When to Use Each Service

```
Need to run code in response to events?
├── Yes → CloudBase Functions (FaaS)
└── No → Continue

Need long-running process or persistent state?
├── Yes → CloudBase Run (CaaS)
└── No → Continue

Need to store structured data?
├── JSON-like documents → CloudBase Database (DocDB)
├── Relational data with SQL → MySQL
└── Key-value cache → Use memory/redis pattern

Need to store files?
└── COS (Cloud Object Storage)

Need to host a website?
└── CloudBase Hosting (static + optional SSR)

Need all of the above?
└── TCB Environment (all services integrated)
```

### Service Comparison

| Criteria | CloudBase Functions | CloudBase Run |
|----------|---------------------|---------------|
| Billing | Per invocation | Per resource usage |
| Cold start | 100-500ms | 1-5s (if image not warm) |
| Max timeout | 60s | 3600s |
| Memory | 128-1536MB | Up to 4096MB |
| Stateless | Yes (encouraged) | Yes (persistence optional) |
| WebSocket | Yes (with --ws) | Full support |
| Persistent connection | No | Yes |
| GPU support | No | Yes |

### Database Selection

| Criteria | DocDB (NoSQL) | MySQL (RDBMS) |
|----------|---------------|---------------|
| Schema flexibility | Dynamic (no schema) | Fixed schema required |
| Query language | Mongoose-like filters | SQL |
| Transactions | Limited | Full ACID |
| Joins | No (denormalize) | Yes |
| Scaling | Horizontal | Vertical + Read replicas |
| Use when | Rapid iteration, flexible schema | Complex queries, relations, data integrity |

## Environment Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     TCB Environment                          │
│  env-xxxxx                                                    │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Functions  │  │  Database   │  │   Storage   │          │
│  │  Namespace  │  │  (DocDB)    │  │    (COS)    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ Cloud Run   │  │   MySQL     │  │  Hosting    │          │
│  │  Services   │  │             │  │  (CDN)      │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
├──────────────────────────────────────────────────────────────┤
│               Shared: CDN, SSL, Custom Domain                │
└──────────────────────────────────────────────────────────────┘
```

## Region Selection

| Region ID | Region Name | Use Case |
|-----------|-------------|----------|
| `ap-shanghai` | Shanghai | China mainland (default) |
| `ap-beijing` | Beijing | China mainland alternative |
| `ap-guangzhou` | Guangzhou | China mainland alternative |
| `ap-singapore` | Singapore | Southeast Asia |

## Pricing Model

| Service | Billing | Notes |
|---------|---------|-------|
| CloudBase Functions | Per invocation + traffic | Free tier: 100k invocations/month |
| CloudBase Run | Per CPU-second + memory | More predictable than FaaS |
| DocDB | Included in environment | Storage included |
| COS | Per GB stored + traffic | First 50GB free |
| Hosting | Included | CDN traffic may incur cost |

## Agent Interaction Patterns

### Pattern 1: Event-Driven Function
```javascript
// Triggered by HTTP request
exports.main = async (event, context) => {
  // event contains request data
  // context contains TCB info
  return { message: "Hello" };
}
```

### Pattern 2: Background Processing
```javascript
// Triggered by timer or queue
exports.main = async (event) => {
  // Process in background
  // Return result (or don't wait)
}
```

### Pattern 3: API Gateway
```javascript
// Deployed as HTTP function
// Accessible at: https://{env-id}.tcb-preview.com/{path}
```

### Pattern 4: Full-Stack with Hosting
```
Web App (Hosting) → API Functions → Database
     ↓
Static assets (COS CDN)
```

## Common Architectures

### Architecture 1: Serverless Web App
```
Browser → CloudBase Hosting (SPA) → API Functions → DocDB/MySQL
                                    ↓
                              COS (file storage)
```

### Architecture 2: Mini-Program Backend
```
WXA/MYA/TTA → TCB API Gateway → CloudBase Functions → DocDB
                                       ↓
                                   COS (media storage)
```

### Architecture 3: Long-Running Service
```
Internet → CloudBase Run (Container) → DocDB/MySQL + COS
              ↓
         Persistent connections
         Background workers
         GPU workloads
```

## Next Steps

- For function development → `services/cloud-functions.md`
- For container workloads → `services/cloud-run.md`
- For data storage → `services/cloud-database.md`
- For file storage → `services/cloud-storage.md`
- For static hosting → `services/cloud-hosting.md`
