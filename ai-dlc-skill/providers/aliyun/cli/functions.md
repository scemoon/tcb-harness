# Aliyun CLI: Function Compute (fun)

## When to Use Function Commands

| Goal | Command | Notes |
|------|---------|-------|
| Deploy a function | `fun deploy` | Main deployment command |
| Invoke a function | `fun invoke` | For testing |
| View logs | `fun logs` | Real-time logs |
| List functions | `fun list` | Show all functions |
| Delete function | `fun remove` | Removes function + triggers |
| Init template | `fun init` | Create new project |

**For shared environments (preview/staging/production), always use `deploy_stack` instead.**

## Decision Tree for Function Operations

```
Need to work with Function Compute?
├── Deploying to shared env → deploy_stack --preview --provider aliyun
├── Deploying to personal dev → fun deploy
├── Testing/debugging function → fun invoke
├── Viewing logs → fun logs
├── Checking status → fun list
└── Deleting function → fun remove (dev only)
```

## Deploy Functions

### Standard Deployment with template.yml

```bash
fun deploy --template template.yml
```

### Deploy Specific Function

```bash
fun deploy --function hello --service my-service
```

### Deploy All Functions

```bash
fun deploy
```

### Options

| Option | Description |
|--------|-------------|
| `--template <file>` | Use specific template file |
| `--function <name>` | Deploy specific function |
| `--service <name>` | Deploy to specific service |
| `--skip-existing` | Don't overwrite existing |
| `--use-remote` | Force remote build |

## Init New Function

```bash
# HTTP trigger template
fun init --template-name http-trigger-nodejs14 my-function

# Event trigger template
fun init --template-name event-nodejs14 my-function

# Custom runtime
fun init --template-name custom-container my-function
```

### Generated template.yml Example

```yaml
ROSTemplateFormatVersion: '2015-09-01'
Transform: Alibaba Cloud Resource Orchestration Service (ROS)
Resources:
  my-service:
    Type: Alibaba Cloud::Function Compute::Service
    Properties:
      ServiceName: my-service
      Description: My service
  hello:
    Type: Alibaba Cloud::Function Compute::Function
    Properties:
      ServiceName: my-service
      FunctionName: hello
      Runtime: nodejs14
      Handler: index.handler
      MemorySize: 128
      Timeout: 60
      CodeUri: ./
```

## Invoke Functions

### Sync Invocation

```bash
fun invoke --function hello --service my-service
```

### With Event Data

```bash
fun invoke --function hello --service my-service \
  --event '{"key": "value"}'
```

### Async Invocation

```bash
fun invoke --function hello --service my-service --async
```

## View Logs

### Recent Logs

```bash
fun logs --function hello --service my-service
```

### Logs with Limit

```bash
fun logs --function hello --service my-service --tail 100
```

### Follow Logs (tail -f)

```bash
fun logs --function hello --service my-service --tail --follow
```

### Filter Logs

```bash
fun logs --function hello --service my-service | grep ERROR
```

## List Functions

### List All Services

```bash
fun list services
```

### List Functions in Service

```bash
fun list functions --service my-service
```

Output:
```
Functions in service: my-service
┌──────────────┬────────────┬─────────┬───────────────┐
│ Name         │ Runtime    │ Memory  │ Timeout       │
├──────────────┼────────────┼─────────┼───────────────┤
│ hello        │ nodejs14   │ 128MB   │ 60s           │
│ api-users    │ python3.9  │ 256MB   │ 30s           │
└──────────────┴────────────┴─────────┴───────────────┘
```

## Function Details

```bash
fun info --function hello --service my-service
```

Shows:
- Runtime version
- Memory limit
- Timeout
- Handler
- Environment variables
- Last modification time

## Delete Function

```bash
fun remove --function hello --service my-service
```

**Warning:** Deletes function and all associated triggers. Cannot be undone.

## Local Invoke

Test function locally without deployment:

```bash
fun local invoke --function hello --service my-service --event '{"test": true}'
```

## Build Remotely

For functions with complex dependencies:

```bash
fun deploy --use-remote --service my-service --function hello
```

## Common Workflows

### Workflow: Deploy New Function

```bash
# 1. Initialize project
fun init --template-name http-trigger-nodejs14 hello

# 2. Edit code
cd hello
vim index.js

# 3. Deploy
fun deploy

# 4. Test
fun invoke --function hello --service hello
```

### Workflow: Update Function Config

```yaml
# Edit template.yml
function:
  name: hello
  memorySize: 512  # Increase memory
  timeout: 120     # Increase timeout

# Redeploy
fun deploy --function hello --service my-service
```

### Workflow: Debug Function Error

```bash
# 1. Get recent logs
fun logs --function hello --service my-service --tail 50

# 2. Invoke with test event
fun invoke --function hello --service my-service --event '{"debug": true}'

# 3. Check detailed logs
fun logs --function hello --service my-service | grep -i error

# 4. Local invoke for faster iteration
fun local invoke --function hello --service my-service --event '{}'
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Function not found` | Wrong name or service | `fun list functions` to verify |
| `Deploy failed: timeout` | Slow build or network | Check build logs, use `--use-remote` |
| `Invoke timeout` | Function taking too long | Increase timeout in template |
| `Memory exceeded` | Memory limit too low | Increase memory in template |
| `Permission denied` | RAM role missing | Check function compute permissions |
| `Build failed` | Dependency error | Check package.json, use remote build |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
