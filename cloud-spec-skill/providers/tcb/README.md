# Tencent CloudBase (TCB) Provider

Provider implementation for Tencent CloudBase.

## Provider Metadata

```yaml
provider:
  name: tcb
  display_name: Tencent CloudBase
  version: 1.0.0
  website: https://cloud.tencent.com/product/tcb

regions:
  - id: ap-shanghai
    name: Shanghai
    endpoint: cloud.tencent.com
  - id: ap-beijing
    name: Beijing
  - id: ap-guangzhou
    name: Guangzhou
  - id: ap-singapore
    name: Singapore
  - id: ap-mumbai
    name: Mumbai

services:
  compute: cloudbase
  storage: cloudbase
  database: cloudbase
  functions: cloudbase
  network: cloudbase

capabilities:
  - serverless_functions
  - static_hosting
  - serverless_database
  - serverless_storage
  - authentication
  - serverless_container

limits:
  function_timeout: 20s (configurable up to 60s)
  function_memory: 256MB (configurable up to 1536MB)
  max_instances: 100
  storage_quota: 10GB
  db_read_qps: 500
  db_write_qps: 200

pricing_model: pay_per_invocation
```

## CLI Commands

```bash
# Environment
tcb env list
tcb env create --name <env>
tcb env use <env-id>

# Functions
tcb fn deploy <name> --dir ./functions
tcb fn list
tcb fn invoke <name> --params '{"key": "value"}'
tcb fn logs <name> --limit 100

# Database
tcb db model list
tcb db model pull <model>
tcb db model push <model>
tcb db query <sql>

# Storage
tcb storage upload <local> <remote>
tcb storage download <remote> <local>
tcb storage list <prefix>

# Hosting
tcb hosting deploy <dir> --env <env-id>
tcb hosting list

# Auth
tcb auth get-uid
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| TCB_SECRET_ID | Tencent Cloud secret ID |
| TCB_SECRET_KEY | Tencent Cloud secret key |
| TCB_ENV_ID | CloudBase environment ID |

## Feature Mapping

CloudSpec interface → TCB service:

| CloudSpec | TCB Service |
|-----------|-------------|
| compute.list_instances | tcb env list |
| compute.create_instance | (managed by TCB) |
| storage.upload | tcb storage upload |
| database.query | tcb db query |
| functions.deploy | tcb fn deploy |
| network.configure_cors | (auto-configured) |
