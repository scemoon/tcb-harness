---
name: aliyun
description: |
  Alibaba Cloud (Aliyun) knowledge base for AI Agents.
  Covers: Function Compute (FC), Serverless App Engine (SAE), OSS Storage,
  RDS/MySQL, TableStore, CDN Hosting, REST API, SDK.
  Supports decision-making for architecture selection, deployment, troubleshooting.
triggers:
  - aliyun
  - alibaba cloud
  - function compute
  - fc
  - serverless
  - oss
  - rds
  - 阿里云
services:
  - function-compute
  - serverless-app-engine
  - oss-storage
  - rds
  - tablestore
  - cdn-hosting
compute_modes:
  - fc  # FaaS
  - sae # CaaS
credentials:
  - ALICLOUD_ACCESS_KEY
  - ALICLOUD_SECRET_KEY
  - ALICLOUD_REGION
  - FUNCTION_COMPUTE_SERVICE
compatibility:
  cdh: ">=1.4"
  opencode: ">=1.15"
---

# Alibaba Cloud (Aliyun) Knowledge Base

## What is Aliyun

Aliyun (Alibaba Cloud) is a comprehensive cloud computing platform providing:

| Service | Type | Use Case |
|---------|------|----------|
| Function Compute (FC) | FaaS | Event-driven serverless functions |
| Serverless App Engine (SAE) | CaaS | Long-running container workloads |
| RDS (MySQL/PostgreSQL) | RDBMS | Relational data, SQL queries |
| TableStore | NoSQL | Wide-column storage, massive scale |
| OSS | Object Storage | Files, images, static assets |
| CDN + Static Website | Static Hosting | SPA, static sites, global acceleration |

## Agent Decision Tree

When agent needs to interact with Aliyun, follow this decision tree:

```
1. What is the goal?
   ├── Deploy/manage serverless functions → services/function-compute.md
   ├── Deploy/manage container apps → services/serverless-app-engine.md
   ├── Store/query relational data → services/database.md
   ├── Store/query massive NoSQL data → services/database.md (TableStore)
   ├── Upload/download files → services/storage.md
   ├── Deploy static website → services/cdn-hosting.md
   └── Debug/deploy → best-practices/troubleshooting.md
```

## How to Interact

### CLI Tools

Aliyun uses multiple CLI tools:

| Tool | Purpose |
|------|---------|
| `fun` | Function Compute deployment and management |
| `ossutil` | OSS storage operations |
| `ocs` | TableStore operations |
| `aliyun` | General Aliyun CLI (RDS, etc.) |
| `cdn` | CDN refresh and management |

### REST API (For programmatic access)

```
https://{product}.{region}.aliyuncs.com/
Headers: Authorization, Content-Type
```

See `api/rest-api.md` for endpoint reference.

### SDK (For programmatic access)

```
Node.js, Python, Java, PHP, .NET, Go
```

See `api/sdk.md` for SDK reference.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       Aliyun Platform                        │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│    FC       │    SAE      │    RDS      │      OSS         │
│  (Function  │  (Serverless│  (MySQL/    │   (Object        │
│   Compute)  │   App Eng.) │   PG)       │    Storage)      │
├─────────────┴─────────────┴─────────────┴──────────────────┤
│                    CDN + Static Website                     │
│                  (Global Edge + OSS Origin)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
              Custom Domain + SSL
                    │
     ┌──────────────┼──────────────┐
     │              │              │
   Backend       Web App      Mobile App
  (FC/SAE)     (OSS+CDN)     (via API)
```

## Region Selection

| Region ID | Region Name | Use Case |
|-----------|-------------|----------|
| `cn-shanghai` | Shanghai | China mainland (default) |
| `cn-beijing` | Beijing | China mainland alternative |
| `cn-hangzhou` | Hangzhou | China mainland alternative |
| `ap-southeast-1` | Singapore | Southeast Asia |

## Credential Management

See `security/authentication.md` for complete guide.

| Variable | Description |
|----------|-------------|
| `ALICLOUD_ACCESS_KEY` | Aliyun access key ID |
| `ALICLOUD_SECRET_KEY` | Aliyun access key secret |
| `ALICLOUD_REGION` | Default region |

## Quick Reference

### Deploy a Function

```bash
# Using fun CLI
fun deploy --function hello --service my-service --env $ALICLOUD_REGION

# Using template.yml
fun deploy --template template.yml
```

### Store Files

```bash
# Upload to OSS
ossutil cp ./file.txt oss://bucket/path/

# List bucket
ossutil ls oss://bucket/
```

### Query Database

```bash
# Connect to RDS MySQL
mysql -h ${RDS_HOST} -P 3306 -u ${RDS_USER} -p${RDS_PASSWORD}

# TableStore query
ots select --instance-name xxx --table-name xxx
```

## File Structure

```
aliyun/
├── SKILL.md                    # This file
├── provider.yaml               # AI-DLC provider config
├── preview.yaml                # Preview deployment flow
├── deployment.yaml             # Production deployment pipeline
├── services/
│   ├── overview.md             # Platform overview
│   ├── function-compute.md     # Function Compute (FaaS)
│   ├── serverless-app-engine.md# SAE (CaaS)
│   ├── storage.md              # OSS object storage
│   ├── database.md             # RDS + TableStore
│   └── cdn-hosting.md          # CDN + Static website
├── cli/
│   ├── setup.md                # Installation & login
│   ├── functions.md            # fun CLI reference
│   ├── storage.md              # ossutil reference
│   ├── database.md             # RDS & TableStore CLI
│   └── hosting.md              # OSS + CDN hosting
├── api/
│   ├── rest-api.md             # REST API reference
│   └── sdk.md                  # Multi-language SDK
├── integration/
│   └── ci-cd.md                # CI/CD integration
├── security/
│   └── authentication.md       # Auth & credentials
└── best-practices/
    ├── function-design.md      # Function design patterns
    ├── database-design.md      # Database schema design
    └── troubleshooting.md      # Common issues & solutions
```
