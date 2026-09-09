# CloudBase Functions (FaaS)

## When to Use CloudBase Functions

**Use CloudBase Functions when:**
- Responding to HTTP requests (API endpoints)
- Processing events (timer triggers, queue messages, file uploads)
- Running short-lived, stateless computations (< 60s)
- Needing automatic scaling without managing servers

**Do NOT use CloudBase Functions when:**
- Execution time exceeds 60 seconds → Use CloudBase Run
- Need persistent connections or background workers
- Require GPU or large memory (> 1536MB)
- Stateful computation requiring local disk persistence

## Agent Decision Guide

```
Need serverless compute?
├── Short task (<60s), event-driven → CloudBase Functions
├── Long-running, persistent state → CloudBase Run
└── Containerized workload → CloudBase Run (--deployMode image)
```

## Function Types

### HTTP Functions

Responding to HTTP requests. Deployed with `--httpFn` flag.

```javascript
// index.js
exports.main = async (event, context) => {
  // event: HTTP request (query, body, headers)
  // context: TCB environment info
  return {
    statusCode: 200,
    body: JSON.stringify({ message: "Hello World" })
  };
};
```

**Access URL pattern:** `https://{env-id}.tcb-preview.com/{function-path}`

### WebSocket Functions

For real-time bidirectional communication. Use `--ws` flag.

```javascript
exports.main = async (event, context) => {
  // event: { type: 'connect' | 'message' | 'disconnect', ... }
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

### Background Functions

Triggered by timers, COS events, or other triggers (not HTTP).

```javascript
// Cron-triggered function
exports.main = async (event, context) => {
  // event: { trigger: 'timer', ... }
  // Run cleanup, send notifications, etc.
};
```

## Function Structure

```
my-function/
├── index.js          # Entry point (exports.main)
├── package.json      # Dependencies
├── cloudbaserc.json  # Function config
└── node_modules/     # Dependencies (if local)
```

### cloudbaserc.json Example

```json
{
  "functionRoot": "./functions",
  "functions": [
    {
      "name": "hello",
      "timeout": 10,
      "memory": 256,
      "handler": "index.main",
      "runtime": "Nodejs16.13",
      "triggers": [
        {
          "name": "myTrigger",
          "type": "timer",
          "config": "0 0 * * * *"
        }
      ]
    }
  ]
}
```

## Deployment Options

### Standard Deployment (COS mode, default)

```bash
tcb fn deploy --name hello --dir ./functions --env $TCB_ENV_ID
```

Files uploaded to COS bucket, extracted at runtime.

### Zip Mode (≤1.5MB)

```bash
tcb fn deploy --name hello --dir ./functions --deployMode zip --env $TCB_ENV_ID
```

For small functions without many dependencies.

### Image Mode (Container)

```bash
tcb fn deploy --name hello --deployMode image --env $TCB_ENV_ID
```

For complex dependencies or custom runtimes.

## CLI Reference

| Command | Description |
|---------|-------------|
| `tcb fn list --env <envId>` | List all functions |
| `tcb fn deploy --name <name> --dir <path> --env <envId>` | Deploy function |
| `tcb fn invoke --name <name> --params '{}' --env <envId>` | Invoke function |
| `tcb fn logs --name <name> --env <envId>` | View function logs |
| `tcb fn detail --name <name> --env <envId>` | Get function details |
| `tcb fn delete --name <name> --env <envId>` | Delete function |
| `tcb fn trigger --name <name> --trigger <trigger> --config <config>` | Create trigger |

## Limits and Quotas

| Limit | Value | Notes |
|-------|-------|-------|
| Timeout | 60s (default), up to 60s | Use CloudBase Run for longer |
| Memory | 128-1536MB | Adjust in cloudbaserc.json |
| Max instances | 100 | Per function, auto-scaling |
| Package size | 256MB (compressed) | Include dependencies |
| Environment variables | 256KB total | Per function |
| Concurrent executions | 1000 (default) | Can request increase |

## Cold Start Optimization

### Problem
Cold start adds 100-500ms latency when function is idle.

### Solutions

1. **Keep function warm with timer trigger**
```json
{
  "triggers": [
    {
      "name": "keep-warm",
      "type": "timer",
      "config": "*/5 * * * *"
    }
  ]
}
```

2. **Reduce package size**
- Minimize dependencies
- Use ES modules
- Tree-shake unused code

3. **Use larger memory allocation**
- More memory → faster CPU → faster cold start
- 512MB+ recommended for latency-sensitive functions

4. **Choose Node.js runtime**
- Node.js cold start is faster than Python

## Error Handling

### Function Errors

```javascript
exports.main = async (event, context) => {
  try {
    // Business logic
    const result = await processData(event);
    return { success: true, data: result };
  } catch (error) {
    // Log error for debugging
    console.error('Error:', error.message);
    // Return error response
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};
```

### Retry Behavior

- HTTP functions: No automatic retry (client should retry)
- Background functions: TCB handles retries based on trigger type
- For critical operations, implement idempotency

## Accessing TCB Services from Functions

```javascript
exports.main = async (event, context) => {
  // Access via TCB environment variables
  const envId = process.env.TCB_ENV_ID;
  const secretId = process.env.TENCENTCLOUD_SECRETID;
  const secretKey = process.env.TENCENTCLOUD_SECRETKEY;

  // Or use TCB DB SDK
  const tcb = require('@cloudbase/node-sdk');
  const app = tcb.init({
    env: envId,
    credentials: { secretId, secretKey }
  });
  const db = app.database();

  // Query database
  const { data } = await db.collection('users').get();
  return { users: data };
};
```

## Best Practices

1. **Stateless design** - Don't rely on in-memory state between invocations
2. **Graceful shutdown** - Return response before cleanup
3. **Idempotent operations** - Handle duplicate invocations gracefully
4. **Structured logging** - Use `console.log` with JSON format
5. **Environment-specific config** - Use env vars, not hardcoded values
6. **Minimize dependencies** - Faster cold start, smaller package
7. **Set appropriate timeout** - Not too short (failures), not too long (cost)

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Function timeout | Long execution | Optimize code or use CloudBase Run |
| 403 Forbidden | Permission error | Check TCB env ID and credentials |
| Cold start too slow | Large package | Minimize dependencies, use timer keep-warm |
| Memory exceeded | Memory limit | Increase memory in cloudbaserc.json |
| Concurrent limit reached | Too many requests | Request increase or implement throttling |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
