# CDN + Static Website Hosting

## When to Use CDN Hosting

**Use CDN + OSS when:**
- Deploy static websites (SPA, static sites)
- Host web assets with global acceleration
- Serve content with low latency worldwide
- Need automatic HTTPS and custom domains

**Do NOT use CDN+OSS when:**
- Need server-side business logic → Use Function Compute
- Need real-time features → Use Function Compute + WebSocket
- Complex dynamic content → Use SAE or ECS

## Agent Decision Guide

```
Need to serve web content?
├── Static site (HTML/CSS/JS) → OSS + CDN
├── SPA with API backend → OSS + CDN + Function Compute
└── Full web app with SSR → SAE
```

## Hosting Features

| Feature | Description |
|---------|-------------|
| Global CDN | 200+ edge nodes worldwide |
| Automatic HTTPS | Free SSL certificates via Alibaba Cloud CDN |
| Custom Domain | Bring your own domain |
| SPA Routing | Rewrites all 404s to index.html |
| Cache Control | Per-file cache headers |
| CI/CD Integration | Auto-deploy on git push |

## Deployment

### Basic Deployment

```bash
# Upload to OSS
ossutil cp -r ./dist oss://my-bucket/ --update

# Refresh CDN
aliyun cdn RefreshObjectCaches --ObjectType File \
  --ObjectPath http://my-bucket.oss-cn-shanghai.aliyuncs.com/
```

### Using serverless devs

```yaml
edition: 1.0.0
services:
  web:
    component: website
    props:
      bucket: my-bucket
      region: cn-shanghai
      dist: ./dist
      cacheControl: 31536000
```

```bash
s deploy
```

## URL Structure

| Environment | URL Pattern |
|-------------|-------------|
| OSS Origin | `https://{bucket}.{region}.aliyuncs.com` |
| CDN Domain | `https://{cdn-domain}` |
| Custom Domain | `https://{custom-domain}` |

## SPA Configuration

### How SPA Routing Works

For Single Page Applications (Vue, React, Angular):

1. All requests to non-file paths are rewritten to `index.html`
2. Client-side router handles path rendering
3. Direct links and refresh work correctly

### CDN Cache Configuration

```bash
# Set cache rules
aliyun cdn SetFileCacheConfig --CacheType 30 \
  --CacheUrlPropertyList "*.js,*.css,*.png"
```

### Default Cache Behavior

| File Type | Cache Duration |
|-----------|----------------|
| HTML | No cache (or short) |
| JS/CSS | 1 year (immutable with hash) |
| Images | 1 week |
| Other | 1 day |

## Custom Domain

### Add CDN Domain

```bash
aliyun cdn AddCdnDomain \
  --DomainName example.com \
  --CdnType web \
  --SourceType oss \
  --SourceDomain my-bucket.oss-cn-shanghai.aliyuncs.com
```

### Configure DNS

Add CNAME record:
```
Type: CNAME
Host: example.com
Value: example.com.w.kunlungr.com
```

### SSL Certificate

```bash
# Add SSL certificate
aliyun cdn SetCdnDomainSSLCertificate \
  --DomainName example.com \
  --CertType upload \
  --SSLProtocol true \
  --CertFile /path/to/cert.pem \
  --KeyFile /path/to/key.pem
```

## Build Environment Injection

Inject environment-specific values at build time:

```bash
# Set environment variable during build
BACKEND_URL=https://api.example.com pnpm --filter web build
```

This makes variables available during the build process (Vite, Webpack, etc.).

## Integration with Backend

### Pattern: Frontend + Function Compute API

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser                                  │
│   ┌──────────────────────────────────────────────────────┐  │
│   │  Frontend App (OSS + CDN)                            │  │
│   │  - Loads config from window.__ENV__                  │  │
│   │  - Calls API via BACKEND_URL                         │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Function Compute (API Gateway)                  │
│   - /api/users → getUsers()                                 │
│   - /api/orders → createOrder()                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   RDS + TableStore                          │
└─────────────────────────────────────────────────────────────┘
```

### Build with Backend URL

```bash
# Deploy web with BACKEND_URL injected
cd apps/web && BACKEND_URL=$STACK_URL pnpm build

# Upload to OSS
ossutil cp -r ./dist oss://my-bucket/ --update

# Refresh CDN cache
aliyun cdn RefreshObjectCaches --ObjectType directory \
  --ObjectPath http://my-bucket.oss-cn-shanghai.aliyuncs.com/
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `ossutil cp -r ./dist oss://bucket/` | Upload static files |
| `ossutil website oss://bucket --index index.html` | Set index page |
| `aliyun cdn RefreshObjectCaches` | Refresh CDN cache |
| `aliyun cdn DescribeCdnDomainDetail` | Get domain info |
| `aliyun cdn AddCdnDomain` | Add CDN domain |
| `aliyun cdn SetCdnDomainSSLCertificate` | Set SSL certificate |

## Best Practices

1. **Use build tools** - Don't deploy raw HTML, use Vite/Webpack
2. **Enable gzip/brotli** - Configure in build tool for smaller assets
3. **Use immutable hashes** - Filename hashes for cache busting
4. **Optimize images** - Compress images, use WebP format
5. **Set long cache for assets** - JS/CSS with content hash
6. **SPA routing** - Ensure all routes serve index.html
7. **CDN cache** - Use cache invalidation on deploy
8. **Separate buckets** - Dev/staging/prod different buckets

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| 404 on refresh (SPA) | CDN caching old routing | Refresh CDN after deploy |
| Stale content | Cache not cleared | Refresh CDN or use versioned paths |
| Slow first load | Large bundle | Code split, lazy load routes |
| CORS errors | API not allowing origin | Configure CORS in Function Compute |
| CDN not working | DNS not propagated | Wait for CNAME to propagate |
| SSL not ready | Certificate provisioning | Wait 1-10 minutes |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
