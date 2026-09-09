# TCB CLI: Functions Management

## When to Use Function Commands

| Goal | Command | Per-Component Allowed |
|------|---------|----------------------|
| Deploy a function | `tcb fn deploy` | dev sandbox only |
| Invoke a function | `tcb fn invoke` | any env |
| View logs | `tcb fn logs` | any env |
| List functions | `tcb fn list` | any env |
| Create trigger | `tcb fn trigger` | dev sandbox only |
| Delete function | `tcb fn delete` | dev sandbox only |

**For shared environments (preview/staging/production), always use `deploy_stack` instead.**

## Decision Tree for Function Operations

```
Need to work with functions?
├── Deploying to shared env → deploy_stack --preview --provider tcb
├── Deploying to personal dev → tcb fn deploy
├── Testing/debugging function → tcb fn invoke
├── Viewing logs → tcb fn logs
├── Checking status → tcb fn list
└── Deleting function → tcb fn delete (dev only)
```

## Deploy Functions

### Standard Deployment

```bash
tcb fn deploy --name hello --dir ./functions --env $TCB_ENV_ID
```

Requirements:
- Directory must contain `cloudbaserc.json` or `package.json`
- Entry point must export `main` function

### Deploy All Functions

```bash
tcb fn deploy --all --env $TCB_ENV_ID
```

Deploys all functions defined in `cloudbaserc.json`.

### HTTP Function

```bash
tcb fn deploy --name api --httpFn --env $TCB_ENV_ID
```

Makes function accessible via HTTP.

### With WebSocket

```bash
tcb fn deploy --name ws-handler --httpFn --ws --env $TCB_ENV_ID
```

### Options

| Option | Description |
|--------|-------------|
| `--name <name>` | Function name |
| `--dir <path>` | Function directory |
| `--env <envId>` | Target environment |
| `--httpFn` | Deploy as HTTP function |
| `--ws` | Enable WebSocket |
| `--deployMode <mode>` | Upload mode: `cos` (default), `zip`, `image` |
| `--force` | Overwrite existing |
| `--yes` | Skip confirmation |

## Invoke Functions

### Sync Invocation

```bash
tcb fn invoke --name hello --params '{}' --env $TCB_ENV_ID
```

Returns function output directly.

### With Parameters

```bash
tcb fn invoke --name hello \
  --params '{"userId": "123", "action": "getProfile"}' \
  --env $TCB_ENV_ID
```

### Async Invocation (background)

```bash
tcb fn invoke --name hello --params '{}' --async --env $TCB_ENV_ID
```

Returns immediately without waiting for result.

## View Logs

### Recent Logs

```bash
tcb fn logs --name hello --env $TCB_ENV_ID
```

### Logs with Limit

```bash
tcb fn logs --name hello --limit 100 --env $TCB_ENV_ID
```

### Logs with Filter

```bash
tcb fn logs --name hello --keyword error --env $TCB_ENV_ID
```

### Follow Logs (tail -f)

```bash
tcb fn logs --name hello --tail --env $TCB_ENV_ID
```

## List Functions

```bash
tcb fn list --env $TCB_ENV_ID
```

Output:
```
┌──────────────┬────────────┬─────────┬───────────────┐
│ Name         │ Runtime    │ Status  │ Modified      │
├──────────────┼────────────┼─────────┼───────────────┤
│ hello        │ Nodejs16.13│ active  │ 2024-01-15    │
│ api-users    │ Nodejs16.13│ active  │ 2024-01-14    │
│ ws-handler   │ Nodejs16.13│ active  │ 2024-01-13    │
└──────────────┴────────────┴─────────┴───────────────┘
```

## Function Details

```bash
tcb fn detail --name hello --env $TCB_ENV_ID
```

Shows:
- Runtime version
- Memory limit
- Timeout
- Trigger configuration
- Environment variables
- Last deployment time

## Delete Function

```bash
tcb fn delete --name hello --env $TCB_ENV_ID
```

**Warning:** Deletes function and all associated triggers. Cannot be undone.

## Triggers

### Create Timer Trigger

```bash
tcb fn trigger create \
  --name hello \
  --trigger cron-daily \
  --type timer \
  --config "0 0 * * * *" \
  --env $TCB_ENV_ID
```

### Create COS Trigger

```bash
tcb fn trigger create \
  --name process-image \
  --trigger image-upload \
  --type cos \
  --config '{"bucket":"my-bucket","filter":{"prefix":"images/"}}' \
  --env $TCB_ENV_ID
```

### List Triggers

```bash
tcb fn trigger list --name hello --env $TCB_ENV_ID
```

### Delete Trigger

```bash
tcb fn trigger delete --name hello --trigger cron-daily --env $TCB_ENV_ID
```

## Common Workflows

### Workflow: Deploy New Function

```bash
# 1. Create function directory
mkdir -p functions/hello
cd functions/hello

# 2. Create entry point
cat > index.js << 'EOF'
exports.main = async (event, context) => {
  return { message: "Hello, World!" };
};
EOF

# 3. Create package.json
cat > package.json << 'EOF'
{ "name": "hello", "version": "1.0.0" }
EOF

# 4. Create function config
cat > cloudbaserc.json << 'EOF'
{
  "functions": [{
    "name": "hello",
    "timeout": 10,
    "memory": 256
  }]
}
EOF

# 5. Deploy
tcb fn deploy --name hello --dir . --env $TCB_ENV_ID

# 6. Test
tcb fn invoke --name hello --params '{}' --env $TCB_ENV_ID
```

### Workflow: Update Production Function

```bash
# NEVER update directly in production
# Always use deploy_stack

deploy_stack --env production --provider tcb
```

### Workflow: Debug Function Error

```bash
# 1. Get recent logs
tcb fn logs --name hello --limit 50 --env $TCB_ENV_ID

# 2. Invoke with test params
tcb fn invoke --name hello --params '{"debug": true}' --env $TCB_ENV_ID

# 3. Check detailed logs
tcb fn logs --name hello --keyword error --env $TCB_ENV_ID

# 4. View function config
tcb fn detail --name hello --env $TCB_ENV_ID
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Function not found` | Wrong name or env | `tcb fn list` to verify |
| `Deploy failed: timeout` | Slow upload | Check network, reduce package size |
| `Invoke failed: timeout` | Function taking too long | Increase timeout, optimize function |
| `Memory exceeded` | Memory limit too low | Increase memory in cloudbaserc.json |
| `Trigger not firing` | Wrong trigger config | Verify cron expression, check logs |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
