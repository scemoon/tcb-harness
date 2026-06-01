# CloudSpec Workflows

Standard development and deployment pipelines.

## Workflow Types

| Workflow | Purpose |
|----------|---------|
| [deployment](./deployment.yaml) | Release application to cloud |
| [development](./development.yaml) | Local development loop |
| [ci](./ci.yaml) | Continuous integration pipeline |
| [rollback](./rollback.yaml) | Emergency rollback procedure |

## Common Patterns

### Stage Structure

```yaml
stages:
  - name: string              # Stage name
    required: boolean         # Must pass for continue
    parallel: boolean          # Run steps in parallel
    steps:
      - name: string
        command: string | string[]
        env:                  # Environment variables
          KEY: value
        continue_on_error: boolean
        timeout: duration
```

### Conditions

```yaml
conditions:
  branch: string | string[]   # Git branch filter
  changes:                    # File change filter
    - pattern: string
      type: [added, modified, deleted]
```

### Artifacts

```yaml
artifacts:
  - name: string
    path: string
    retention: duration
```

## Environment Promotion

```
dev → staging → production
```

| Environment | Purpose | Deploy Trigger |
|-------------|---------|----------------|
| dev | Development testing | Manual or feature branch |
| staging | Pre-production validation | PR merge to main |
| production | Live traffic | Release tag |
