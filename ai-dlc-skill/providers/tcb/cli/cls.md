# TCB CLI: CLS Log Search

## When to Use CLS Commands

| Goal | Command | Notes |
|------|---------|-------|
| Search by requestId | `cdh cls search --request-id <id>` | Full call chain tracing |
| Search by keyword | `cdh cls search --function <name> --keyword <kw>` | Error/search logs |
| Time-range search | `cdh cls search --function <name> --start-time ... --end-time ...` | Narrow down timeframe |
| List log topics | `cdh cls topics --function <name>` | Find available topics |

**Note**: `tcb fn logs` does NOT support requestId search. Use CLS for request tracing.

## Why CLS?

腾讯云 SCF logs are automatically shipped to Cloud Log Service (CLS) since 2021-01-29.
CLS supports:
- `SCF_RequestId` field for call chain tracing
- Full-text search on `SCF_Message`
- Time-range queries
- Advanced filtering

## Setup

### Install Dependency

```bash
pip install tencentcloud-sdk-python
```

### Set Credentials

```bash
export TENCENTCLOUD_SECRETID=your-secret-id
export TENCENTCLOUD_SECRETKEY=your-secret-key
# Or use TCB-specific credentials:
export TCB_SECRET_ID=your-secret-id
export TCB_SECRET_KEY=your-secret-key
```

## cdh cls search

### Search by RequestId (Call Chain Tracing)

```bash
cdh cls search --request-id req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --function hello --env $TCB_ENV_ID
```

Output:
```
[2024-01-15T10:30:00Z] req-xxxxxxxx-xxxx-... hello [INFO] 45ms 200
  Function started
[2024-01-15T10:30:00Z] req-xxxxxxxx-xxxx-... hello [INFO] 45ms 200
  Database query completed: SELECT * FROM users
```

### Search Errors

```bash
cdh cls search --function hello --keyword error --limit 50 --env $TCB_ENV_ID
```

### Time Range Search

```bash
cdh cls search --function hello \
  --start-time "2024-01-15 10:00:00" \
  --end-time "2024-01-15 11:00:00" \
  --env $TCB_ENV_ID
```

### JSON Output

```bash
cdh cls search --request-id req-xxxxx --function hello --json | jq .
```

## CLS Log Fields

| Field | Type | Description |
|-------|------|-------------|
| `SCF_RequestId` | text | Request ID (call chain key) |
| `SCF_FunctionName` | text | Function name |
| `SCF_Namespace` | text | Namespace |
| `SCF_Message` | text | Log message content |
| `SCF_StartTime` | long | Call start time (Unix ms) |
| `SCF_Duration` | long | Duration (ms) |
| `SCF_StatusCode` | long | HTTP status code |
| `SCF_Level` | text | Log level (INFO/WARN/ERROR) |
| `SCF_MemUsage` | double | Memory usage (bytes) |
| `SCF_RetryNum` | long | Retry count |

## Common Queries

### Slow Requests (>5s)

```bash
cdh cls search --function hello --keyword "SCF_Duration:>5000"
```

### Memory Issues

```bash
cdh cls search --function hello --keyword "SCF_MemUsage:>1500000000"
```

### HTTP 5xx Errors

```bash
cdh cls search --function hello --keyword "SCF_StatusCode:>=500"
```

### Specific User Request

```bash
cdh cls search --request-id req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --function hello
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `tencentcloud-sdk-python not found` | Missing package | `pip install tencentcloud-sdk-python` |
| `SCF_logset not found` | Logging not enabled | Enable via SCF console |
| `No topic found` | Wrong function/namespace | Check function name and namespace |
| `Credentials error` | Wrong env vars | Verify TENCENTCLOUD_SECRETID/SECRETKEY |
| `Region mismatch` | Wrong region | Set `--region` to match SCF function region |

## Related

- [CLS Console](https://console.cloud.tencent.com/cls) - Web-based log viewer
- [SCF Console](https://console.cloud.tencent.com/scf) - Function logs tab
- [troubleshooting.md](../best-practices/troubleshooting.md) - Full troubleshooting guide
