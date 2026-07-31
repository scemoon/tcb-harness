# TCB CLI: Hosting Management

## When to Use Hosting Commands

| Goal | Command | Notes |
|------|---------|-------|
| Deploy static site | `tcb hosting deploy` | Main command |
| List hosting projects | `tcb hosting list` | View current deployments |
| Get hosting details | `tcb hosting detail` | See config and URLs |
| Add custom domain | `tcb hosting domain add` | HTTPS auto-provisioned |
| Delete hosting | `tcb hosting delete` | Removes all deployed files |

## Decision Tree for Hosting Operations

```
Need to deploy static content?
├── Deploy to shared env → deploy_stack --preview --provider tcb
├── Deploy to personal dev → tcb hosting deploy
├── Add custom domain → tcb hosting domain add
└── Delete deployment → tcb hosting delete (dev only)
```

## Deploy Static Site

### Basic Deployment

```bash
tcb hosting deploy --env $TCB_ENV_ID --dir ./dist
```

### With Build Environment Variables

```bash
tcb hosting deploy \
  --env $TCB_ENV_ID \
  --dir ./dist \
  --build-env BACKEND_URL=$STACK_URL \
  --build-env API_KEY=$API_KEY
```

### With Configuration File

```json
// cloudbaserc.json
{
  "hosting": {
    "dev": {
      "cloudPath": "./dist",
      "envId": "env-xxxxx",
      "ignore": ["*.map", "node_modules/**"]
    }
  }
}
```

```bash
tcb hosting deploy --env dev
```

### Deployment Options

| Option | Description |
|--------|-------------|
| `--env <envId>` | Target environment |
| `--dir <path>` | Local directory to deploy |
| `--build-env <key=value>` | Environment variables for build |
| `--force` | Overwrite existing files |
| `--yes` | Skip confirmation |

## List Hosting Projects

```bash
tcb hosting list --env $TCB_ENV_ID
```

Output:
```
┌──────────────┬────────────────────────────┬──────────────┐
│ Environment  │ URL                        │ Status       │
├──────────────┼────────────────────────────┼──────────────┤
│ env-xxxxx    │ https://env-xxxxx.tcb-preview.com │ deployed │
└──────────────┴────────────────────────────┴──────────────┘
```

## Get Hosting Details

```bash
tcb hosting detail --env $TCB_ENV_ID
```

Shows:
- Current URL
- Custom domains
- Last deployment time
- File count
- Storage used

## Add Custom Domain

### Step 1: Add Domain

```bash
tcb hosting domain add --domain example.com --env $TCB_ENV_ID
```

Output shows DNS records to add:
```
Please add the following DNS record:
Type: CNAME
Name: example.com
Value: env-xxxxx.tcb-ext.com
```

### Step 2: Configure DNS

Add CNAME record in your DNS provider:
```
Type: CNAME
Host: example.com
Value: env-xxxxx.tcb-ext.com
TTL: 600
```

### Step 3: Wait for SSL

SSL certificate auto-provisions via Let's Encrypt (1-5 minutes).

### Verify Domain

```bash
tcb hosting domain list --env $TCB_ENV_ID
```

### Domain HTTPS

- Certificate auto-provisioned
- Supports custom ports (443 only for HTTPS)
- Redirect from HTTP to HTTPS automatic

## Delete Hosting

```bash
tcb hosting delete --env $TCB_ENV_ID
```

**Warning:** Deletes all deployed files. Cannot be undone.

## URL Patterns

| Environment | URL Pattern |
|-------------|-------------|
| Preview | `https://{env-id}.tcb-preview.com` |
| Custom Domain | `https://{your-domain.com}` |
| Staging | `https://{env-id}.tcb-preview.com` |
| Production | `https://{env-id}.tcb-ext.com` or custom domain |

## Agent Workflows

### Workflow: Deploy Web App with Backend URL

```bash
# 1. Get backend URL from stack
export STACK_URL=$(deploy_stack --preview --provider tcb --output url)

# 2. Deploy web with backend URL injected
tcb hosting deploy \
  --env $TCB_ENV_ID \
  --dir ./dist \
  --build-env BACKEND_URL=$STACK_URL

# 3. Get web URL
export WEB_URL=$(deploy_stack --preview --provider tcb --output web_url)

# 4. Run e2e tests
pytest apps/web/tests/e2e/ --base-url $WEB_URL --api-url $BACKEND_URL
```

### Workflow: Deploy with Cache Busting

```bash
# Deploy with --force to ensure all files uploaded
tcb hosting deploy --env $TCB_ENV_ID --dir ./dist --force

# Or use content-hashed filenames (handled by build tools like Vite)
```

### Workflow: Debug Deployment

```bash
# 1. Check hosting status
tcb hosting detail --env $TCB_ENV_ID

# 2. List deployed files
tcb storage list --path /hosting --env $TCB_ENV_ID

# 3. Verify index.html exists
tcb storage list --path /hosting/index.html --env $TCB_ENV_ID
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `No index.html found` | Directory doesn't contain index.html | Ensure correct `--dir` path |
| `Deployment failed` | Build error | Check build output for errors |
| `404 on routes` | SPA routing not working | Should work automatically, check CDN |
| `Stale content` | Cache not cleared | Deploy with `--force` |
| `Domain not working` | DNS not propagated | Wait 5-10 min, verify CNAME |
| `SSL not ready` | Certificate provisioning | Wait 1-5 minutes |

### SPA Routing Issue

CloudBase Hosting automatically handles SPA routing (rewrites 404 to index.html). If routes return 404:

1. Verify `index.html` exists in deployed files
2. Check CDN cache (deploy with `--force`)
3. Verify your build tool outputs correct paths

For detailed troubleshooting → `../best-practices/troubleshooting.md`
