# CloudSpec Providers

Cloud vendor abstraction layer for multi-cloud support.

## Overview

CloudSpec defines a vendor-neutral interface that each cloud provider implements. This allows applications to be portable across cloud platforms.

## Provider Structure

```
providers/
├── README.md           # This file
├── base/               # Provider interface definitions
│   ├── types.yaml      # Common type definitions
│   ├── interface.yaml   # Service interfaces
│   └── config.yaml     # Provider config schema
├── tcb/               # Tencent CloudBase provider
│   ├── provider.yaml   # Provider metadata
│   ├── services/       # Service implementations
│   └── mapping.yaml    # Feature mapping
├── aliyun/            # Alibaba Cloud provider
│   ├── provider.yaml
│   ├── services/
│   └── mapping.yaml
└── aws/               # AWS provider
    ├── provider.yaml
    ├── services/
    └── mapping.yaml
```

## Common Types

Defined in `base/types.yaml`:

```yaml
types:
  Region:
    description: Cloud region identifier
    format: string
    example: "ap-shanghai"

  ResourceID:
    description: Unique resource identifier
    format: string
    pattern: "^[a-z][a-z0-9-]{2,62}$"

  Timestamp:
    description: ISO 8601 timestamp
    format: string
    example: "2024-01-15T10:30:00Z"

  SecretRef:
    description: Reference to secret in secure storage
    format: string
    pattern: "secret://{provider}/{name}"

  Endpoint:
    description: Service endpoint URL
    format: uri
```

## Service Interfaces

Each provider MUST implement these core services:

### ComputeService

```yaml
ComputeService:
  operations:
    list_instances:
      params: { region: Region }
      returns: Instance[]

    create_instance:
      params:
        name: ResourceID
        type: string
        region: Region
        config: object
      returns: Instance

    delete_instance:
      params:
        id: ResourceID
        region: Region
      returns: void
```

### StorageService

```yaml
StorageService:
  operations:
    upload:
      params:
        source: path
        dest: string
        options: object
      returns: StorageObject

    download:
      params:
        source: string
        dest: path
      returns: void

    list:
      params:
        prefix: string
        max_results: integer
      returns: StorageObject[]

    delete:
      params:
        path: string
      returns: void
```

### DatabaseService

```yaml
DatabaseService:
  operations:
    query:
      params:
        sql: string
        params: array
      returns: Record[]

    insert:
      params:
        table: string
        data: object
      returns: RecordID

    update:
      params:
        table: string
        filters: object
        data: object
      returns: integer

    delete:
      params:
        table: string
        filters: object
      returns: integer
```

### FunctionService

```yaml
FunctionService:
  operations:
    deploy:
      params:
        name: ResourceID
        code: path | string
        runtime: string
        config: FunctionConfig
      returns: Deployment

    invoke:
      params:
        name: ResourceID
        payload: object
        sync: boolean
      returns: InvocationResult | void

    list:
      params: { region: Region }
      returns: Function[]

    get_logs:
      params:
        name: ResourceID
        limit: integer
      returns: LogEntry[]
```

### NetworkService

```yaml
NetworkService:
  operations:
    configure_cors:
      params:
        rules: CorsRule[]
      returns: void

    get_domain_cert:
      params:
        domain: string
      returns: Certificate

    create_domain:
      params:
        domain: string
        cert: Certificate
      returns: Domain
```

## Configuration Schema

Each provider configuration:

```yaml
provider:
  name: string              # Provider identifier
  version: string           # Provider spec version
  regions:                 # Supported regions
    - id: string
      name: string
      endpoint: string

credentials:
  type: string              # "api_key" | "oauth" | "service_account"
  fields:                  # Required credential fields
    - name: string
      sensitive: boolean

defaults:
  region: string
  runtime: string
```

## Using Providers

### CLI

```bash
# Add provider
cloud-spec provider add tcb --credentials ./credentials.json

# List providers
cloud-spec provider list

# Set default
cloud-spec provider use tcb

# Check status
cloud-spec provider status
```

### Code

```python
from cloud_spec.providers import get_provider

provider = get_provider("tcb")
instances = provider.compute.list_instances(region="ap-shanghai")
```
