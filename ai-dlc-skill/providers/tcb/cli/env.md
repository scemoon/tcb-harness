# TCB Environment Management

## What is a TCB Environment

A TCB Environment is an isolated namespace containing:
- CloudBase Functions
- CloudBase Database (DocDB)
- MySQL instance
- COS storage bucket
- CloudBase Hosting
- CloudBase Run services

**Each environment has a unique `envId`** (e.g., `env-8a9b6c5d`) used to scope all operations.

## When to Create Environments

| Scenario | Action |
|----------|--------|
| New project | Create dev environment first |
| Team member onboarding | Each developer gets personal dev sandbox |
| Feature branch testing | Deploy to preview environment |
| Pre-production validation | Use staging environment |
| Production release | Use production environment |

## Environment Strategy

### Recommended Structure

| Environment | Purpose | Access | Per-Component Deploy |
|-------------|---------|--------|---------------------|
| `dev-{username}` | Personal dev | Developer only | Allowed |
| `preview` | Integration testing | Team | Stack deploy only |
| `staging` | Pre-production | Team | Stack deploy only |
| `production` | Live traffic | Public | Stack deploy + approval |

## CLI Commands

### List Environments

```bash
tcb env list
```

Output:
```
┌──────────────┬────────────────┬─────────────┐
│ Environment  │ Region         │ Status      │
├──────────────┼────────────────┼─────────────┤
│ env-xxxxx    │ ap-shanghai    │ running     │
│ env-yyyyy    │ ap-beijing     │ running     │
│ dev-sandbox  │ ap-shanghai    │ running     │
└──────────────┴────────────────┴─────────────┘
```

### Create Environment

```bash
tcb env create dev-test --region ap-shanghai
```

**Note:** Environment creation takes 1-2 minutes.

### Switch Environment

```bash
tcb env use env-xxxxx
```

Sets as default for subsequent commands.

### View Environment Info

```bash
tcb env info
```

Shows:
- Environment ID
- Region
- Status
- Created time
- Service quotas

### Delete Environment

```bash
tcb env delete env-xxxxx
```

**Warning:** Deletes all resources in the environment. Cannot be undone.

## Environment Variables in Commands

Most CLI commands accept `--env <envId>` or `-e <envId>`:

```bash
tcb fn list --env env-xxxxx
tcb hosting deploy --env env-xxxxx --dir ./dist
```

Or set default via `cloudbaserc.json`:

```json
{
  "envId": "env-xxxxx"
}
```

## Agent Decision Guide

```
Need to deploy to a shared environment?
├── No (personal dev) → dev-{username} (per-component allowed)
└── Yes (team/shared) → preview/staging/production (stack deploy only)

Deploy command decision:
├── Single function update → tcb fn deploy (per-component OK for dev)
├── Database schema change → tcb db migrate
├── Full stack update → deploy_stack --preview --provider tcb
└── Anything to shared env → deploy_stack (not individual commands)
```

## Personal Dev Sandbox

### Create Personal Sandbox

```bash
tcb env create dev-$USER --region ap-shanghai
```

### Per-Component Workflow

```bash
# Work on a single function
tcb fn deploy --name hello --dir ./functions --env dev-$USER

# Work on hosting
tcb hosting deploy --env dev-$USER --dir ./dist

# Test with local frontend
# Frontend points to preview stack URL
```

### Cleanup

When done with personal sandbox:

```bash
# Option 1: Keep for later use (costs money)
# Option 2: Delete to save money
tcb env delete dev-$USER
```

## Shared Environment Workflow

### Preview Environment

```bash
# Deploy full stack to preview
deploy_stack --preview --provider tcb

# Result:
# STACK_URL=https://{env-id}.tcb-preview.com
# WEB_URL=https://{env-id}-{project}.tcb-preview.com
```

### Staging Environment

```bash
# Deploy after PR merge
deploy_stack --env staging --provider tcb

# Run e2e tests
pytest aidlc/tests/cross-stack/ --stack-url $STACK_URL
```

### Production Environment

```bash
# Deploy with human approval
deploy_stack --env production --provider tcb

# After validation
# Smoke test + BVT
```

## Environment Quotas

| Resource | Limit per Environment |
|----------|----------------------|
| Functions | 100 |
| Collections (DocDB) | 100 |
| Storage (COS) | 50GB |
| Database (DocDB) | 2GB |
| Database (MySQL) | 20GB |
| CloudBase Run | 10 services |

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Environment not found` | Wrong env ID | `tcb env list` to see valid IDs |
| `Permission denied` | No access to environment | Request access from environment owner |
| `Environment creating` | Creation in progress | Wait 1-2 minutes |
| `Resource quota exceeded` | Hit environment limits | Delete unused resources or create new env |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
