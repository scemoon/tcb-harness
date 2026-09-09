# Serverless App Engine (SAE)

## When to Use SAE

**Use SAE when:**
- Long-running processes (> 600s timeout)
- Need persistent state or connections
- Require large memory (> 3GB)
- Custom runtime or framework not supported by FC
- Container-based microservices architecture
- WebSocket connections that persist
- Java Spring Boot / PHP / Python applications

**Do NOT use SAE when:**
- Short, stateless functions → Use Function Compute (cheaper)
- Event-driven, bursty workloads → Use Function Compute
- Simple HTTP endpoints → Use Function Compute (cheaper)

## Agent Decision Guide

```
Need compute?
├── Short tasks (<600s), stateless → Function Compute
├── Long-running (>600s) → SAE
├── Custom container image → SAE or FC (custom runtime)
├── JVM-based app (Spring Boot) → SAE
└── WebSocket server → SAE
```

## SAE vs Function Compute

| Criteria | Function Compute | SAE |
|----------|------------------|-----|
| Max timeout | 600s | 86400s |
| Max memory | 3GB | 32GB |
| Cold start | 500ms-2s | 3-10s |
| Pricing | Per invocation | Per CPU-second + memory |
| Container | Custom runtime | Full Docker support |
| SSH/Debug | No | Yes (via logs) |
| Persistent disk | No | Yes (NAS) |
| WebSocket | Yes | Yes |
| JVM support | Limited | Full |
| PHP/Python/Go | Supported | Full support |

## Application Deployment

### Java/Spring Boot

```dockerfile
FROM openjdk:8-jdk-alpine
VOLUME /tmp
ARG JAR_FILE
COPY ${JAR_FILE} app.jar
ENTRYPOINT ["java","-jar","/app.jar"]
```

### PHP

```dockerfile
FROM php:7.4-apache
COPY . /var/www/html/
```

### Python

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app"]
```

## Deployment

### Using serverless devs

```yaml
edition: 1.0.0
services:
  my-app:
    component: sae
    props:
      region: cn-shanghai
      app:
        appName: my-sae-app
        namespaceId: cn-shanghai
        packageType: image
        imageUrl: registry.cn-shanghai.aliyuncs.com/ns/image:latest
        instances: 1-10  # auto-scaling
        cpu: 1
        memory: 2
        envVars:
          NODE_ENV: production
```

```bash
s deploy
```

### Using Console

1. Create application in SAE console
2. Upload container image or code package
3. Configure scaling rules
4. Deploy

## CLI Reference

| Command | Description |
|---------|-------------|
| `s cli sae deploy --app-name my-app` | Deploy application |
| `s cli sae list-apps` | List applications |
| `s cli sae update --instances 3` | Scale application |
| `s cli sae logs --app-name my-app` | View logs |

## Scaling Configuration

### Auto-scaling

```yaml
app:
  scaling:
    minInstances: 1
    maxInstances: 10
    cpuThreshold: 70  # scale up when CPU > 70%
    memoryThreshold: 70
```

### Manual Scaling

```bash
s cli sae update --app-name my-app --instances 5
```

## Access Patterns

### HTTP Endpoint

```bash
# Get application URL
curl https://my-sae-app.cn-shanghai.p.sae.dev/health
```

### WebSocket

```javascript
const ws = new WebSocket('wss://my-sae-app.cn-shanghai.p.sae.dev/ws');
```

### Internal Communication

Applications in same VPC can communicate internally:

```javascript
// From FC function to SAE application
const response = await fetch('http://my-sae-app:8080/api/internal', {
  method: 'POST',
  headers: {
    'X-Internal-Token': process.env.INTERNAL_TOKEN
  },
  body: JSON.stringify({ data })
});
```

## Persistent Storage (NAS)

SAE supports NAS for persistent storage:

```yaml
app:
  nasConfig:
    mountDir: /app/data
    accessMode: ReadWriteMany
```

```javascript
// Write to persistent storage
const fs = require('fs');
const data = fs.readFileSync('/app/data/cache.json', 'utf8');
```

## Limits and Quotas

| Limit | Value |
|-------|-------|
| Max timeout | 86400s |
| Max CPU | 16 cores |
| Max memory | 32GB |
| Max instances | 100 |
| Min instances | 0 (scale to zero) |
| Max concurrent requests | 10000 per instance |
| Max container size | 4GB |

## Best Practices

1. **Graceful shutdown** - Handle SIGTERM for clean shutdown
2. **Health checks** - Implement `/health` endpoint
3. **Logging** - Use structured JSON logging
4. **Environment variables** - Don't hardcode secrets
5. **Connection pooling** - Reuse DB connections
6. **Startup time** - Keep container startup under 60s
7. **Stateless design** - Use external storage for state

### Graceful Shutdown Example

```javascript
const http = require('http');
let isShuttingDown = false;

const server = http.createServer((req, res) => {
  if (isShuttingDown) {
    res.statusCode = 503;
    res.end('Service is restarting');
    return;
  }
  // Handle request
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
s cli sae update --app-name my-app --min-instances 0
```

### Right-size Resources

- Monitor actual CPU/memory usage
- Don't over-provision for peak
- Use auto-scaling to handle spikes

### Cost Comparison

| Service | Use Case | Approximate Cost |
|---------|----------|------------------|
| Function Compute | 100k invocations, 128MB, 100ms | ~$0.02/day |
| SAE | 1 core, 1GB, 24h | ~$0.50/day |

SAE is more predictable but can be more expensive for sporadic workloads.

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Container fails to start | Image error, port issue | Check logs in SAE console |
| 503 errors | Container overloaded | Scale up instances |
| Slow response | Cold start, resource limits | Increase memory, enable min instances |
| Out of memory | Memory limit exceeded | Increase memory allocation |
| Deployment failed | Build or image issue | Check build logs |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
