# Aliyun CI/CD Integration

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

      - name: Setup Aliyun CLI
        run: |
          npm install -g @alicloud/fun
          npm install -g @serverless-devs/s

      - name: Configure credentials
        run: |
          fun config --access-key-id ${{ secrets.ALICLOUD_ACCESS_KEY }}
          fun config --access-key-secret ${{ secrets.ALICLOUD_SECRET_KEY }}
          fun config --region cn-shanghai

      - name: Deploy Stack
        run: deploy_stack --preview --provider aliyun
        env:
          ALICLOUD_ACCESS_KEY: ${{ secrets.ALICLOUD_ACCESS_KEY }}
          ALICLOUD_SECRET_KEY: ${{ secrets.ALICLOUD_SECRET_KEY }}

      - name: Run E2E Tests
        run: |
          export STACK_URL=$(deploy_stack --preview --provider aliyun --output url)
          pytest apps/web/tests/e2e/ --base-url $STACK_URL --api-url $STACK_URL
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

      - name: Install tools
        run: |
          pip install fun
          pip install ossutil

      - name: Deploy to Staging
        run: deploy_stack --env staging --provider aliyun
        env:
          ALICLOUD_ACCESS_KEY: ${{ secrets.ALICLOUD_ACCESS_KEY }}
          ALICLOUD_SECRET_KEY: ${{ secrets.ALICLOUD_SECRET_KEY }}
          ALICLOUD_REGION: cn-shanghai

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
        run: deploy_stack --env production --provider aliyun
        env:
          ALICLOUD_ACCESS_KEY: ${{ secrets.ALICLOUD_ACCESS_KEY }}
          ALICLOUD_SECRET_KEY: ${{ secrets.ALICLOUD_SECRET_KEY }}
          ALICLOUD_REGION: cn-shanghai

      - name: Run BVT
        run: |
          export PRODUCTION_URL=$(deploy_stack --env production --output url)
          pytest aidlc/tests/bvt/ --stack-url $PRODUCTION_URL
```

## Secrets Configuration

In GitHub repository Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `ALICLOUD_ACCESS_KEY` | Aliyun AccessKey ID |
| `ALICLOUD_SECRET_KEY` | Aliyun AccessKey Secret |
| `ALICLOUD_REGION` | Default region |
| `OSS_BUCKET` | OSS bucket name |
| `FC_SERVICE` | Function Compute service name |

## Database Migration in CI/CD

### Migration Workflow

```yaml
- name: Run RDS Migration
  run: |
    mysql -h ${{ secrets.RDS_HOST }} \
      -P ${{ secrets.RDS_PORT }} \
      -u ${{ secrets.RDS_USER }} \
      -p'${{ secrets.RDS_PASSWORD }}' \
      ${{ secrets.RDS_DATABASE }} < migrations/001.sql
```

### Migration File Structure

```
migrations/
├── 001_create_users.sql
├── 002_add_indexes.sql
└── 003_create_orders.sql
```

## Rollback Strategy

### Automatic Rollback on Failure

```yaml
- name: Deploy Stack
  id: deploy
  run: |
    if ! deploy_stack --env production --provider aliyun; then
      echo "Deployment failed, rolling back..."
      deploy_stack --rollback ${{ env.LAST_STABLE_VERSION }} --provider aliyun
      exit 1
    fi
```

### Manual Rollback

```bash
# List recent versions
fun list functions --service my-service

# Rollback specific function
fun deploy --function hello --service my-service --code-url s3://backup/hello-v1.zip
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

## Cache Strategy

### Cache Node Modules

```yaml
- name: Cache node_modules
  uses: actions/cache@v4
  with:
    path: node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
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
```

## Using serverless devs (s.yaml)

```yaml
edition: 1.0.0
services:
  my-app:
    component: fc
    props:
      region: ${{ ALICLOUD_REGION }}
      access: default
      service:
        name: ${{ FC_SERVICE }}
      function:
        name: hello
        runtime: nodejs16
        handler: index.handler
    hooks:
      post-deploy:
        - run: ossutil cp -r ./dist oss://${{ OSS_BUCKET }}/ --force
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
| `InvalidAccessKeyId` | Secrets not set | Add Aliyun secrets to GitHub |
| `Deploy timeout` | Build takes too long | Optimize build, increase timeout |
| `E2E tests fail` | Deployment issue | Check function logs |
| `RDS connection fails` | Network/VPC issue | Check RDS endpoint and security group |

For general troubleshooting → `../best-practices/troubleshooting.md`
