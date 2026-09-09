# Aliyun Platform Overview

## What is Alibaba Cloud (Aliyun)

Aliyun is Alibaba Cloud's comprehensive cloud computing platform offering 200+ cloud products and services globally. For serverless development, the key services are Function Compute, Serverless App Engine, OSS, RDS, and CDN.

## Core Services

| Service | Type | Description | Limits |
|---------|------|-------------|--------|
| Function Compute (FC) | FaaS | Event-driven serverless functions | 600s timeout, 3GB memory |
| Serverless App Engine (SAE) | CaaS | Container-based hosting | 86400s timeout, 32GB memory |
| RDS MySQL | RDBMS | Relational database | 200GB storage, 32GB memory |
| RDS PostgreSQL | RDBMS | Relational database | 200GB storage, 32GB memory |
| TableStore | NoSQL | Wide-column NoSQL | Unlimited, petabyte scale |
| OSS | Object Storage | File storage | Unlimited, 48TB per object |
| CDN | CDN | Global content delivery | 200+ edge nodes |

## Agent Decision Guide

### When to Use Each Service

```
Need to run code in response to events?
├── Yes → Function Compute (FC)
└── No → Continue

Need long-running process or persistent state?
├── Yes → Serverless App Engine (SAE)
└── No → Continue

Need to store structured data?
├── SQL queries, relations → RDS MySQL/PostgreSQL
├── Massive scale, wide columns → TableStore
└── JSON-like documents → TableStore (OTS)

Need to store files?
└── OSS (Object Storage Service)

Need to host a website?
└── OSS + CDN (static website hosting)
```

### Service Comparison

| Criteria | Function Compute | Serverless App Engine |
|----------|------------------|----------------------|
| Billing | Per invocation + traffic | Per resource usage |
| Cold start | 500ms-2s | 3-10s (if not warm) |
| Max timeout | 600s | 86400s |
| Memory | 128-3GB | Up to 32GB |
| Stateless | Yes (encouraged) | Yes (persistence optional) |
| WebSocket | Yes | Full support |
| Persistent connection | No | Yes |
| Custom runtime | Yes (custom container) | Yes |

### Database Selection

| Criteria | RDS (MySQL/PG) | TableStore |
|----------|---------------|------------|
| Schema | Fixed schema | Schema-less (wide columns) |
| Query language | SQL | SQL-like (Select/Filter) |
| Transactions | Full ACID | Limited |
| Joins | Yes | No (denormalize) |
| Scaling | Vertical + Read replicas | Horizontal auto-split |
| Use when | Traditional RDBMS needs | Massive data, time-series |

## Environment Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Aliyun Account                             │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   Region: cn-shanghai                   │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │  │
│  │  │    FC       │  │    SAE      │  │    RDS      │    │  │
│  │  │  Services   │  │  Instances  │  │  Instances  │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │  │
│  │  │    OSS      │  │ TableStore  │  │    CDN      │    │  │
│  │  │  Buckets    │  │  Instances  │  │  Domains    │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Region Selection

| Region ID | Region Name | Use Case |
|-----------|-------------|----------|
| `cn-shanghai` | Shanghai | China mainland (default) |
| `cn-beijing` | Beijing | China mainland alternative |
| `cn-hangzhou` | Hangzhou | China mainland alternative |
| `ap-southeast-1` | Singapore | Southeast Asia, global access |

## Pricing Model

| Service | Billing | Notes |
|---------|---------|-------|
| Function Compute | Per invocation + CPU-time | Free tier: 1M invocations/month |
| SAE | Per CPU-second + memory | Pay-as-you-go |
| RDS | Per hour + storage | Backup storage extra |
| TableStore | Per request + storage | Reserved capacity cheaper |
| OSS | Per GB stored + traffic | First 50GB free |
| CDN | Per GB transferred | Traffic volume discount |

## Agent Interaction Patterns

### Pattern 1: Event-Driven Function
```javascript
// FC function triggered by HTTP or event
module.exports.handler = async (event, context) => {
  // event contains request data
  // context contains FC info
  return { message: "Hello" };
};
```

### Pattern 2: API Gateway + Function
```javascript
// Deployed as HTTP function
// Accessible at: https://{service}.{region}.fc.devs.com/{path}
```

### Pattern 3: Full-Stack with OSS+CDN
```
Browser → CDN (cached) → OSS (origin)
                      ↓
              Function Compute (API)
                      ↓
                    RDS/OTS
```

## Common Architectures

### Architecture 1: Serverless Web App
```
Browser → CDN → OSS (static) → Function Compute (API) → RDS
                                                        ↓
                                                    OSS (files)
```

### Architecture 2: Event-Driven Processing
```
OSS Upload → Event Trigger → Function Compute → TableStore
                                    ↓
                              OSS (processed files)
```

### Architecture 3: Containerized Microservices
```
Internet → SAE (Load Balancer) → Container Apps → RDS + OSS
```

## Next Steps

- For function development → `services/function-compute.md`
- For container workloads → `services/serverless-app-engine.md`
- For data storage → `services/database.md`
- For file storage → `services/storage.md`
- For static hosting → `services/cdn-hosting.md`
