# CloudBase Hosting

## When to Use CloudBase Hosting

**Use CloudBase Hosting when:**
- Deploy static websites (SPA, static sites)
- Host mini-program webview content
- Serve static assets with global CDN
- Need automatic HTTPS and custom domains
- Simple SSR (Server-Side Rendering) with Node.js

**Do NOT use CloudBase Hosting when:**
- Need server-side business logic → Use CloudBase Functions
- Need real-time features → Use CloudBase Functions + WebSocket
- Complex SSR framework → Consider CloudBase Run instead

## Agent Decision Guide

```
Need to serve web content?
├── Static site (HTML/CSS/JS) → CloudBase Hosting
├── SPA with API backend → CloudBase Hosting + CloudBase Functions
├── SSR with Node.js → CloudBase Hosting (Node SSR) or CloudBase Run
└── Full web app with SSR → CloudBase Run (container)
```

## Hosting Features

| Feature | Description |
|---------|-------------|
| Global CDN | 200+ edge nodes worldwide |
| Automatic HTTPS | Free SSL certificates via Let's Encrypt |
| Custom Domain | Bring your own domain |
| SPA Routing | Rewrites all 404s to index.html |
| Cache Control | Per-file cache headers |
| CI/CD Integration | Auto-deploy on git push |

## Deployment

### Basic Deployment

```bash
tcb hosting deploy --env $TCB_ENV_ID --dir ./dist
```

### With Build Environment Variables

```bash
tcb hosting deploy \
  --env $TCB_ENV_ID \
  --dir ./dist \
  --build-env BACKEND_URL=https://api.example.com
```

### With Configuration File (cloudbaserc.json)

```json
{
  "hosting": {
    "dev": {
      "cloudPath": "./dist",
      "envId": "env-xxxxx"
    },
    "release": {
      "cloudPath": "./dist",
      "envId": "env-prod"
    }
  }
}
```

```bash
tcb hosting deploy --env release
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `tcb hosting deploy --env <envId> --dir <path>` | Deploy static site |
| `tcb hosting list --env <envId>` | List hosting projects |
| `tcb hosting detail --env <envId>` | Get hosting details |
| `tcb hosting delete --env <envId>` | Delete hosting project |
| `tcb hosting domain add --domain <domain> --env <envId>` | Add custom domain |

## URL Structure

| Environment | URL Pattern |
|-------------|-------------|
| Preview | `https://{env-id}-{project}.tcb-preview.com` |
| Staging | `https://{env-id}.tcb-preview.com` |
| Production | `https://{custom-domain}` or `https://{env-id}.tcb-ext.com` |

## SPA Configuration

### How SPA Routing Works

For Single Page Applications (Vue, React, Angular):

1. All requests to non-file paths are rewritten to `index.html`
2. Client-side router handles path rendering
3. Direct links and refresh work correctly

```
Request: /user/profile
  ↓ Not a file, not /index.html
  ↓ Rewrite to /index.html
  ↓ Frontend router handles /user/profile
```

### Configuration (if needed)

Usually automatic, but can configure in `cloudbaserc.json`:

```json
{
  "hosting": {
    "dev": {
      "cloudPath": "./dist",
      "ignore": ["*.map"],
      "router": {
        "enable": true,
        "rewrites": [
          { "regxp": "^/api", "target": "https://api.example.com" }
        ]
      }
    }
  }
}
```

## Cache Configuration

### Default Cache Behavior

| File Type | Cache Duration |
|-----------|----------------|
| HTML | No cache (always fresh) |
| JS/CSS | 1 year (immutable) |
| Images | 1 week |
| Other | 1 day |

### Cache Headers

Set custom cache in `cloudbaserc.json`:

```json
{
  "hosting": {
    "dev": {
      "cloudPath": "./dist",
      "headers": [
        {
          "path": "*.json",
          "headers": {
            "Cache-Control": "no-cache"
          }
        }
      ]
    }
  }
}
```

## Environment Injection

Inject environment-specific values at build time:

```bash
# Deploy with build environment
tcb hosting deploy --env $TCB_ENV_ID --dir ./dist --build-env API_URL=$API_URL
```

This makes variables available during the build process (Vite, Webpack, etc.).

### Build Time vs Runtime

| Type | Available | Use Case |
|------|-----------|----------|
| `--build-env` | At build time | `process.env.API_URL` in webpack/vite |
| Runtime env | In browser | Public config loaded from API |

## Custom Domain

### Add Custom Domain

```bash
# Step 1: Add domain
tcb hosting domain add --domain example.com --env $TCB_ENV_ID

# Step 2: Add DNS record (shown after domain add)
# Type: CNAME
# Value: {env-id}.tcb-ext.com

# Step 3: Wait for SSL certificate (automatic)
```

### SSL Certificate

- Automatic issuance via Let's Encrypt
- Renewal before expiration
- Supports wildcard certificates

## Integration with Backend

### Pattern: Frontend + API Functions

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser                                  │
│   ┌──────────────────────────────────────────────────────┐  │
│   │  Frontend App (CloudBase Hosting)                     │  │
│   │  - Loads config from window.__ENV__                  │  │
│   │  - Calls API via BACKEND_URL                         │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              CloudBase Functions (Backend API)               │
│   - /api/users → getUsers()                                 │
│   - /api/orders → createOrder()                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   CloudBase Database                         │
└─────────────────────────────────────────────────────────────┘
```

### Build with Backend URL

```bash
# Deploy web with BACKEND_URL injected
tcb hosting deploy \
  --env $TCB_ENV_ID \
  --dir ./dist \
  --build-env BACKEND_URL=$STACK_URL

# In frontend code
const API_BASE = process.env.BACKEND_URL || 'http://localhost:3000';
```

## Best Practices

1. **Use build tools** - Don't deploy raw HTML, use Vite/Webpack
2. **Enable gzip/brotli** - Configure in build tool for smaller assets
3. **Use immutable hashes** - Filename hashes for cache busting
4. **Optimize images** - Compress images, use WebP format
5. **Set long cache for assets** - JS/CSS with content hash
6. **SPA routing** - Ensure all routes serve index.html
7. **Environment separation** - Different env IDs for dev/staging/prod

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| 404 on refresh (SPA) | Routing not configured | CloudBase handles this automatically |
| Stale content | Cache not cleared | Deploy with `--force` or new path |
| Slow first load | Large bundle | Code split, lazy load routes |
| CORS errors | API not allowing origin | Configure CORS in function |
| Mixed content | HTTP assets on HTTPS page | Use HTTPS for all resources |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
