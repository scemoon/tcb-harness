# TCB CI/CD Integration

## When to Use CI/CD vs Manual Deploy

| Scenario | Approach |
|----------|----------|
| Production deployment | CI/CD (automated, audited) |
| Preview on PR | CI/CD (automatic) |
| Development iteration | CLI (manual) |
| Personal sandbox | CLI (manual) |

## CI/CD Decision Tree

```
Need to automate deployment?
├── Deploy to preview on PR → GitHub Actions (auto)
├── Deploy to staging on merge → GitHub Actions (on merge)
├── Deploy to production on tag → GitHub Actions (on tag + approval)
└── Development iteration → CLI (manual)
```

## GitHub Actions Example

### Preview Deployment (on PR)

```yaml
# .github/workflows/preview.yml
name: Preview Deployment

on:
  pull_request:
    branches: [main]

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        run: npm ci

      - name: Setup TCB credentials
        run: |
          npm install -g @cloudbase/cli
          tcb configure set secretId ${{ secrets.TCB_SECRET_ID }}
          tcb configure set secretKey ${{ secrets.TCB_SECRET_KEY }}
          tcb configure set envId ${{ secrets.TCB_ENV_ID_PREVIEW }}

      - name: Deploy Stack
        run: deploy_stack --preview --provider tcb
        env:
          STACK_URL: ${{ secrets.TCB_ENV_ID_PREVIEW }}

      - name: Run E2E Tests
        run: |
          export STACK_URL=$(deploy_stack --preview --provider tcb --output url)
          pytest apps/web/tests/e2e/ --base-url $STACK_URL --api-url $STACK_URL

      - name: Comment PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: 'Preview deployed to: ${{ env.STACK_URL }}'
            })
```

### Staging Deployment (on merge to main)

```yaml
# .github/workflows/staging.yml
name: Staging Deployment

on:
  push:
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        run: npm ci

      - name: Deploy to Staging
        run: deploy_stack --env staging --provider tcb
        env:
          TCB_SECRET_ID: ${{ secrets.TCB_SECRET_ID }}
          TCB_SECRET_KEY: ${{ secrets.TCB_SECRET_KEY }}
          TCB_ENV_ID: ${{ secrets.TCB_ENV_ID_STAGING }}

      - name: Run Staging E2E
        run: |
          export STACK_URL=$(deploy_stack --env staging --output url)
          pytest aidlc/tests/cross-stack/ --stack-url $STACK_URL
```

### Production Deployment (on release tag)

```yaml
# .github/workflows/production.yml
name: Production Deployment

on:
  release:
    types: [published]

jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        run: npm ci

      - name: Deploy to Production
        run: deploy_stack --env production --provider tcb
        env:
          TCB_SECRET_ID: ${{ secrets.TCB_SECRET_ID }}
          TCB_SECRET_KEY: ${{ secrets.TCB_SECRET_KEY }}
          TCB_ENV_ID: ${{ secrets.TCB_ENV_ID_PRODUCTION }}

      - name: Run BVT
        run: |
          export PRODUCTION_URL=$(deploy_stack --env production --output url)
          pytest aidlc/tests/bvt/ --stack-url $PRODUCTION_URL
```

## Secrets Configuration

In GitHub repository Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `TCB_SECRET_ID` | TCB API key ID |
| `TCB_SECRET_KEY` | TCB API key |
| `TCB_ENV_ID_PREVIEW` | Preview environment ID |
| `TCB_ENV_ID_STAGING` | Staging environment ID |
| `TCB_ENV_ID_PRODUCTION` | Production environment ID |

## Database Migration in CI/CD

### Migration Workflow

```yaml
- name: Run Database Migration
  run: |
    tcb db migrate --env ${{ secrets.TCB_ENV_ID_STAGING }}
```

### Migration File Structure

```
migrations/
├── 001_create_users.sql
├── 002_add_user_indexes.sql
├── 003_create_orders.sql
└── metadata.json
```

### metadata.json (Migration tracking)

```json
{
  "version": 3,
  "applied": [
    { "name": "001_create_users", "appliedAt": "2024-01-01T00:00:00Z" },
    { "name": "002_add_user_indexes", "appliedAt": "2024-01-02T00:00:00Z" },
    { "name": "003_create_orders", "appliedAt": "2024-01-03T00:00:00Z" }
  ]
}
```

## Rollback Strategy

### Automatic Rollback on Failure

```yaml
- name: Deploy Stack
  id: deploy
  run: |
    if ! deploy_stack --env production --provider tcb; then
      echo "Deployment failed, rolling back..."
      deploy_stack --rollback ${{ env.LAST_STABLE_VERSION }} --provider tcb
      exit 1
    fi
```

### Manual Rollback

```bash
# List recent deployments
tcb fn list --env production

# Rollback to specific version
deploy_stack --rollback v1.2.3 --provider tcb
```

## Build Environment Injection

### Inject Backend URL during Build

```yaml
- name: Build Web App
  run: |
    cd apps/web
    BACKEND_URL=${{ env.STACK_URL }} npm run build
  env:
    BACKEND_URL: ${{ env.STACK_URL }}
```

### Access in Frontend Code

```javascript
// Vite example (.env.production)
VITE_API_BASE_URL=$BACKEND_URL
```

## Cache Strategy

### Cache Node Modules

```yaml
- name: Cache node_modules
  uses: actions/cache@v4
  with:
    path: node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

### Cache Build Artifacts

```yaml
- name: Cache dist
  uses: actions/cache@v4
  with:
    path: |
      apps/web/dist
      apps/backend/functions
    key: ${{ runner.os }}-build-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-build-
```

## Monitoring Deployment

### Health Check After Deploy

```yaml
- name: Health Check
  run: |
    for i in {1..10}; do
      if curl -f https://${{ env.STACK_URL }}/health; then
        echo "Health check passed"
        exit 0
      fi
      echo "Waiting for service... ($i/10)"
      sleep 10
    done
    echo "Health check failed"
    exit 1
```

## Best Practices

1. **Separate environments** - preview, staging, production
2. **Use secrets** - Never hardcode credentials
3. **Idempotent deploys** - Can be run multiple times safely
4. **Atomic deployments** - All or nothing
5. **Rollback plan** - Always have a way to revert
6. **Test after deploy** - Run smoke tests or BVT
7. **Notify on failure** - Slack/email on deployment failure

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Login required` | Credentials not set | Check GitHub secrets |
| `Deploy failed` | Build error or quota | Check logs, verify quotas |
| `Migration failed` | SQL error | Check migration file syntax |
| `E2E tests failed` | Deployment issue | Check function logs |

For general troubleshooting → `../best-practices/troubleshooting.md`
