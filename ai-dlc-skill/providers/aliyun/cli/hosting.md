# Aliyun CLI: Hosting (OSS + CDN)

## When to Use Hosting Commands

| Goal | Command | Notes |
|------|---------|-------|
| Deploy static site | `ossutil cp -r` + `cdn refresh` | Main deployment |
| List CDN domains | `aliyun cdn DescribeDomains` | Check domains |
| Add CDN domain | `aliyun cdn AddCdnDomain` | Configure CDN |
| Refresh CDN cache | `aliyun cdn RefreshObjectCaches` | Clear cache |
| SSL certificate | `aliyun cdn SetCdnDomainSSLCertificate` | HTTPS config |
| Set index page | `ossutil website` | Configure hosting |

## Decision Tree for Hosting Operations

```
Need to deploy static content?
├── Deploy to shared env → deploy_stack --preview --provider aliyun
├── Deploy to OSS → ossutil cp -r ./dist oss://bucket/
├── Refresh CDN cache → aliyun cdn RefreshObjectCaches
├── Add custom domain → aliyun cdn AddCdnDomain
└── Configure SSL → aliyun cdn SetCdnDomainSSLCertificate
```

## Deploy Static Site

### Basic Deployment to OSS

```bash
# Upload all files
ossutil cp -r ./dist oss://my-bucket/ --force

# Set index page
ossutil website oss://my-bucket/ --index index.html --error 404.html
```

### With CDN Refresh

```bash
# Upload files
ossutil cp -r ./dist oss://my-bucket/ --force

# Refresh CDN cache (entire bucket)
aliyun cdn RefreshObjectCaches \
  --ObjectType directory \
  --ObjectPath http://my-bucket.oss-cn-shanghai.aliyuncs.com/
```

### With Build Environment Variables

```bash
# Set env vars before build
export BACKEND_URL=https://api.example.com
pnpm --filter web build

# Upload
ossutil cp -r ./dist oss://my-bucket/ --force
```

## CDN Management

### List CDN Domains

```bash
aliyun cdn DescribeDomains --region cn-shanghai
```

### Add CDN Domain

```bash
aliyun cdn AddCdnDomain \
  --DomainName example.com \
  --CdnType web \
  --SourceType oss \
  --SourceDomain my-bucket.oss-cn-shanghai.aliyuncs.com \
  --Region cn-shanghai
```

### Enable HTTPS

```bash
# Add SSL certificate
aliyun cdn SetCdnDomainSSLCertificate \
  --DomainName example.com \
  --CertType upload \
  --SSLProtocol true \
  --CertFile /path/to/cert.pem \
  --KeyFile /path/to/key.pem
```

### Set Cache Rules

```bash
# Set cache for specific file types
aliyun cdn SetFileCacheConfig \
  --CacheType 30 \
  --CacheUrlPropertyList "*.js,*.css,*.png,*.jpg,*.html"
```

### Set Referer Whitelist

```bash
aliyun cdn SetDomainRefererList \
  --DomainName example.com \
  --ReferList "example.com,www.example.com" \
  --ReferType 1  # 1 = whitelist
```

## Refresh CDN Cache

### Refresh Single File

```bash
aliyun cdn RefreshObjectCaches \
  --ObjectType File \
  --ObjectPath http://example.com/index.html
```

### Refresh Directory

```bash
aliyun cdn RefreshObjectCaches \
  --ObjectType Directory \
  --ObjectPath http://example.com/static/
```

### Refresh by Tag

```bash
# Refresh all files with specific tag (requires file management)
aliyun cdn RefreshObjectCachesByTag \
  --Tag "deploy:20240115"
```

### Query Refresh Status

```bash
aliyun cdn DescribeRefreshTasks \
  --TaskId "task-xxxxx"
```

## URL Patterns

| Environment | URL Pattern |
|-------------|-------------|
| OSS Origin | `https://{bucket}.{region}.aliyuncs.com` |
| CDN Domain | `https://{cdn-domain}` |
| Custom Domain | `https://{custom-domain}` |

## Agent Workflows

### Workflow: Deploy Web App with CDN

```bash
# 1. Upload to OSS
ossutil cp -r ./dist oss://my-bucket/ --force

# 2. Refresh CDN
aliyun cdn RefreshObjectCaches \
  --ObjectType directory \
  --ObjectPath http://my-bucket.oss-cn-shanghai.aliyuncs.com/

# 3. Verify
curl -I https://my-bucket.oss-cn-shanghai.aliyuncs.com/index.html
```

### Workflow: Deploy with Custom Domain

```bash
# 1. Add CDN domain
aliyun cdn AddCdnDomain \
  --DomainName example.com \
  --CdnType web \
  --SourceType oss \
  --SourceDomain my-bucket.oss-cn-shanghai.aliyuncs.com

# 2. Configure DNS (manual)
# Add CNAME: example.com -> example.com.w.kunlungr.com

# 3. Wait for DNS propagation (5-10 min)

# 4. Add SSL certificate
aliyun cdn SetCdnDomainSSLCertificate \
  --DomainName example.com \
  --CertType upload \
  --SSLProtocol true \
  --CertFile /path/to/cert.pem \
  --KeyFile /path/to/key.pem

# 5. Upload and refresh
ossutil cp -r ./dist oss://my-bucket/ --force
aliyun cdn RefreshObjectCaches --ObjectType directory \
  --ObjectPath http://example.com/
```

### Workflow: Debug Deployment

```bash
# 1. Check OSS bucket
ossutil ls oss://my-bucket/ --max-size 10

# 2. Check index.html exists
ossutil stat oss://my-bucket/index.html

# 3. Check CDN domain
aliyun cdn DescribeCdnDomainDetail --DomainName example.com

# 4. Test origin directly
curl -I https://my-bucket.oss-cn-shanghai.aliyuncs.com/index.html

# 5. Test CDN
curl -I https://example.com/index.html
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `No index.html found` | Directory doesn't contain index.html | Ensure correct `--dir` path |
| `404 on routes` | SPA routing not working | Set index page in OSS website config |
| `Stale content` | CDN cache not cleared | Refresh CDN after deploy |
| `CDN not working` | DNS not propagated | Wait for CNAME propagation |
| `SSL not ready` | Certificate provisioning | Wait 1-10 minutes |
| `CORS errors` | CDN not allowing origin | Configure CDN referer whitelist |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
