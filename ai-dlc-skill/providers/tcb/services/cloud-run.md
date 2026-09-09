# CloudBase Run (CaaS)

## When to Use CloudBase Run

**Use CloudBase Run when:**
- Long-running processes (> 60s timeout)
- Need persistent state or connections
- Require GPU or large memory (> 1536MB)
- Custom runtime not supported by Functions
- Container-based microservices architecture
- WebSocket connections that persist

**Do NOT use CloudBase Run when:**
- Short, stateless functions → Use CloudBase Functions
- Event-driven, bursty workloads → Use CloudBase Functions
- Simple HTTP endpoints → Use CloudBase Functions (cheaper)
- Serverless is requirement → Use CloudBase Functions

## Agent Decision Guide

```
Need compute?
├── Short tasks (<60s), stateless → CloudBase Functions
├── Long-running (>60s) → CloudBase Run
├── Custom container image → CloudBase Run
├── GPU workload → CloudBase Run
└── WebSocket server → CloudBase Run
```

## CloudBase Run vs CloudBase Functions

| Criteria | CloudBase Functions | CloudBase Run |
|----------|---------------------|---------------|
| Max timeout | 60s | 3600s |
| Max memory | 1536MB | 4096MB |
| Cold start | 100-500ms | 1-5s |
| Pricing | Per invocation | Per CPU-second + memory |
| Container | No (managed runtime) | Yes (Docker) |
| SSH access | No | No (but logs available) |
| Persistent disk | No | No (stateless containers) |
| WebSocket | Yes | Yes |
| GPU | No | Yes |

## Container Deployment

### Dockerfile Example

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 8080

CMD ["node", "server.js"]
```

### Server Example (Express)

```javascript
const express = require('express');
const app = express();

app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: Date.now() });
});

app.post('/api/process', async (req, res) => {
  const { data } = req.body;
  // Long running task
  const result = await processLongTask(data);
  res.json({ result });
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
```

## Deployment

### Deploy Container

```bash
tcb run deploy --name my-service --image myregistry.azurecr.io/myapp:latest --env $TCB_ENV_ID
```

### Deploy from Local Build

```bash
# Build and push to TCB registry
tcb run deploy --name my-service --dockerfile ./Dockerfile --dir ./ --env $TCB_ENV_ID
```

### Scale Configuration

```bash
# Set min/max instances
tcb run update --name my-service --min-instances 1 --max-instances 10 --env $TCB_ENV_ID

# Set CPU and memory
tcb run update --name my-service --cpu 1 --memory 2 --env $TCB_ENV_ID
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `tcb run deploy --name <name> --image <image> --env <envId>` | Deploy service |
| `tcb run list --env <envId>` | List services |
| `tcb run update --name <name> --min-instances <n> --max-instances <n>` | Update scaling |
| `tcb run logs --name <name> --env <envId>` | View logs |
| `tcb run delete --name <name> --env <envId>` | Delete service |
| `tcb run detail --name <name> --env <envId>` | Get service details |

## Service Configuration

### cloudbaserc.json

```json
{
  "container": {
    "my-service": {
      "image": "myregistry.azurecr.io/myapp:latest",
      "port": 8080,
      "minInstances": 1,
      "maxInstances": 10,
      "cpu": 1,
      "memory": 2,
      "envVars": {
        "NODE_ENV": "production",
        "DATABASE_URL": "${DATABASE_URL}"
      }
    }
  }
}
```

## Access Patterns

### HTTP Endpoint

```bash
# Get service URL
curl https://{service}-{env-id}.tcb-preview.com/health
```

### WebSocket

```javascript
const ws = new WebSocket('wss://{service}-{env-id}.tcb-preview.com');

// Or from functions
const result = await app.callFunction({
  name: 'call-run-service',
  data: { service: 'my-service', path: '/api/data' }
});
```

### Internal Communication

Services in the same environment can communicate internally:

```javascript
// From CloudBase Function to CloudBase Run service
const response = await fetch('http://my-service:8080/api/internal', {
  method: 'POST',
  headers: {
    'X-Internal-Token': process.env.INTERNAL_TOKEN
  },
  body: JSON.stringify({ data })
});
```

## Scaling

### Auto-scaling Configuration

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU | > 70% | Scale up |
| Memory | > 80% | Scale up |
| Request count | > 100/min | Scale up |
| Idle | < 5 min | Scale down to min |

### Manual Scaling

```bash
# Scale immediately
tcb run update --name my-service --instances 5 --env $TCB_ENV_ID

# Scale to zero (cost saving)
tcb run update --name my-service --instances 0 --env $TCB_ENV_ID
```

## Limits and Quotas

| Limit | Value |
|-------|-------|
| Max timeout | 3600s |
| Max CPU | 4 cores |
| Max memory | 8GB |
| Max instances | 20 |
| Min instances | 0 (scale to zero) |
| Concurrent requests | 1000 per instance |
| Max container size | 10GB |

## Best Practices

1. **Graceful shutdown** - Handle SIGTERM for clean shutdown
2. **Health checks** - Implement `/health` endpoint
3. **Logging** - Use structured JSON logging
4. **Environment variables** - Don't hardcode secrets
5. **Connection pooling** - Reuse DB connections
6. **Startup time** - Keep container startup under 30s
7. **Stateless design** - Even with persistent storage, keep compute stateless

### Graceful Shutdown Example

```javascript
let isShuttingDown = false;

app.use((req, res, next) => {
  if (isShuttingDown) {
    res.status(503).json({ error: 'Service is restarting' });
    return;
  }
  next();
});

process.on('SIGTERM', () => {
  console.log('SIGTERM received, starting graceful shutdown');
  isShuttingDown = true;
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
```

## Cost Optimization

### Scale to Zero

For services not always needed:

```bash
# Scale down when not in use
tcb run update --name my-service --min-instances 0 --env $TCB_ENV_ID
```

### Right-size Resources

- Monitor actual CPU/memory usage
- Don't over-provision for peak
- Use auto-scaling to handle spikes

### Cost Comparison

| Service | Use Case | Approximate Cost |
|---------|----------|------------------|
| CloudBase Functions | 100k invocations, 128MB, 100ms | ~$0.05/day |
| CloudBase Run | 1 core, 1GB, 24h | ~$0.50/day |

CloudBase Run is more predictable but can be more expensive for sporadic workloads.

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Container fails to start | Image error, port issue | Check logs: `tcb run logs` |
| 503 errors | Container overloaded | Scale up instances |
| Slow response | Cold start, resource limits | Increase memory, enable min instances |
| Out of memory | Memory limit exceeded | Increase memory allocation |
| Connection refused | Service not ready | Add health check, delay start |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
