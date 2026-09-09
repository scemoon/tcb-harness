# Function Compute (FC)

## When to Use Function Compute

**Use Function Compute when:**
- Responding to HTTP requests (API endpoints)
- Processing events (OSS uploads, timers, queue messages)
- Running short-lived, stateless computations (< 600s)
- Needing automatic scaling without managing servers

**Do NOT use Function Compute when:**
- Execution time exceeds 600 seconds → Use SAE
- Need persistent connections or background workers
- Require very large memory (> 3GB)
- Stateful computation requiring local disk persistence

## Agent Decision Guide

```
Need serverless compute?
├── Short task (<600s), event-driven → Function Compute
├── Long-running (>600s) → Serverless App Engine (SAE)
├── Custom container image → Function Compute (custom runtime)
└── Containerized workload → Serverless App Engine (SAE)
```

## Function Types

### HTTP Functions

Responding to HTTP requests via API Gateway.

```javascript
module.exports.handler = async (req, resp, context) => {
  // req: HTTP request { headers, queries, path, method, body }
  // context: FC context info
  return {
    statusCode: 200,
    body: JSON.stringify({ message: "Hello World" })
  };
};
```

**Access URL pattern:** `https://{service}.{region}.fc.devs.com/{functionName}`

### Event Functions

Triggered by various event sources.

```javascript
module.exports.handler = async (event, context) => {
  // event: varies by trigger type
  // e.g., OSS event: { bucket, object, operation }
  // e.g., Timer event: { triggerTime, ... }
  return { processed: true };
};
```

### WebSocket Functions

For real-time bidirectional communication.

```javascript
module.exports.handler = async (event, context) => {
  // event: { type: 'connect' | 'message' | 'disconnect', connectionId, ... }
  switch (event.type) {
    case 'connect':
      // Handle new connection
      break;
    case 'message':
      // Handle incoming message
      break;
    case 'disconnect':
      // Handle disconnection
      break;
  }
};
```

## Function Structure

```
my-project/
├── index.js              # Entry point
├── package.json          # Dependencies
├── template.yml          # FC deployment config
└── .funignore            # Files to exclude
```

### template.yml Example

```yaml
ROSTemplateFormatVersion: '2015-09-01'
Transform: Alibaba Cloud Resource Orchestration Service (ROS)
Resources:
  my-service:
    Type: Alibaba Cloud::Function Compute::Function
    Properties:
      ServiceName: my-service
      FunctionName: hello
      Runtime: nodejs16
      Handler: index.handler
      MemorySize: 256
      Timeout: 60
      CodeUri: ./
      EnvironmentVariables:
        NODE_ENV: production
```

## Deployment

### Using fun CLI

```bash
# Deploy with template
fun deploy --template template.yml

# Deploy specific function
fun deploy --function hello --service my-service

# Deploy all functions in template
fun deploy
```

### Using serverless devs (s.yaml)

```yaml
edition: 1.0.0
services:
  my-app:
    component: fc
    props:
      region: cn-shanghai
      service:
        name: my-service
        description: My service
      function:
        name: hello
        runtime: nodejs16
        handler: index.handler
        memorySize: 256
        timeout: 60
```

```bash
s deploy
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `fun init --template http-trigger` | Initialize new function project |
| `fun deploy --template template.yml` | Deploy from template |
| `fun invoke --function hello --service my-service` | Invoke function |
| `fun logs --function hello --service my-service` | View logs |
| `fun list functions --service my-service` | List functions |
| `fun remove --function hello --service my-service` | Delete function |

## Limits and Quotas

| Limit | Value | Notes |
|-------|-------|-------|
| Timeout | 600s (default), up to 600s | Use SAE for longer |
| Memory | 128-3072MB | Adjust in template |
| Concurrent executions | 1000 (default) | Can request increase |
| Package size | 50MB (compressed) | Include dependencies |
| Environment variables | 4KB total | Per function |
| VPC | Supported | Requires config |

## Cold Start Optimization

### Problem
Cold start adds 500ms-2s latency when function is idle.

### Solutions

1. **Use provisioned concurrency** (paid feature)
```yaml
function:
  name: hello
  provisionedConcurrency: 2  # Keep 2 instances warm
```

2. **Reduce package size**
- Minimize dependencies
- Use ES modules
- Tree-shake unused code

3. **Use larger memory allocation**
- More memory → faster CPU
- 512MB+ recommended for latency-sensitive functions

4. **Avoid VPC if possible**
- VPC adds 10-30s cold start

## Error Handling

### Function Errors

```javascript
module.exports.handler = async (req, resp, context) => {
  try {
    // Business logic
    const result = await processData(req.body);
    return { success: true, data: result };

  } catch (error) {
    // Log error for debugging
    console.error('Error:', error.message);
    // Return error response
    resp.statusCode = 500;
    return { error: error.message };
  }
};
```

### Retry Behavior

- HTTP functions: No automatic retry (client should retry)
- Event functions: Depends on trigger (OSS triggers have built-in retry)
- For critical operations, implement idempotency

## Accessing Aliyun Services from Functions

```javascript
const OSS = require('ali-oss');
const FC = require('@alicloud/fc-builders');

module.exports.handler = async (event, context) => {
  const accessKeyId = process.env.ALICLOUD_ACCESS_KEY;
  const accessKeySecret = process.env.ALICLOUD_SECRET_KEY;

  // Access OSS
  const ossClient = new OSS({
    region: process.env.ALICLOUD_REGION,
    accessKeyId,
    accessKeySecret,
    bucket: 'my-bucket'
  });

  // Access TableStore
  const TableStore = require('tablestore');
  const client = new TableStore.Client({
    accessKeyId,
    accessKeySecret,
    instanceName: 'my-instance',
    region: process.env.ALICLOUD_REGION
  });
};
```

## Best Practices

1. **Stateless design** - Don't rely on in-memory state between invocations
2. **Idempotent operations** - Handle duplicate invocations gracefully
3. **Structured logging** - Use `console.log` with JSON format
4. **Environment-specific config** - Use env vars, not hardcoded values
5. **Minimize dependencies** - Faster cold start, smaller package
6. **Set appropriate timeout** - Not too short (failures), not too long (cost)
7. **Use VPC wisely** - VPC adds cold start time

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Function timeout | Long execution | Optimize code or use SAE |
| 403 Forbidden | Permission error | Check RAM roles |
| Cold start too slow | Large package, VPC | Minimize deps, avoid VPC |
| Memory exceeded | Memory limit exceeded | Increase memory in template |
| Concurrent limit reached | Too many requests | Request increase or implement throttling |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
