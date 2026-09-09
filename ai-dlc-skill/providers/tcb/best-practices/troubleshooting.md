# TCB Troubleshooting Guide

## Quick Diagnosis

Run these commands to diagnose common issues:

```bash
# Check environment
tcb env info

# Check credentials
tcb env list

# List functions
tcb fn list --env $TCB_ENV_ID

# Get function logs
tcb fn logs --name <function-name> --limit 50 --env $TCB_ENV_ID

# Check hosting
tcb hosting detail --env $TCB_ENV_ID
```

## Function Issues

### Function Deployment Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Function not found` | Wrong function name or env | `tcb fn list` to verify |
| `Deploy timeout` | Network or package size | Check package size, reduce dependencies |
| `Code package too large` | > 256MB compressed | Minimize dependencies, use ES modules |
| `Invalid handler` | Handler path wrong | Check cloudbaserc.json handler setting |
| `Runtime not supported` | Wrong runtime | Use Nodejs16.13 or Python3.9 |

### Function Invocation Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Function timeout` | Execution > 60s | Optimize function, or use CloudBase Run |
| `Memory exceeded` | > 1536MB limit | Increase memory or optimize usage |
| `Concurrent limit` | > 100 instances | Request increase or implement throttling |
| `Permission denied` | No DB access | Check collection rules |
| `Handler not found` | Export name wrong | Export must be `exports.main` |

### Cold Start Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| First request slow | Cold start | Normal, 100-500ms expected |
| Every request slow | Large package | Minimize dependencies |
| Slow after idle | Container recycled | Use timer keep-warm trigger |
| Inconsistent latency | Cold starts | Increase memory (faster CPU) |

## Database Issues

### DocDB Query Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Collection not found` | Wrong name | `tcb db list` to see collections |
| `Query syntax error` | Invalid query | Check query syntax |
| `Permission denied` | No read permission | Check collection permissions |
| `Request limit exceeded` | Too many queries | Add indexes, reduce query frequency |
| `Document too large` | > 16MB | Split document into smaller parts |

### MySQL Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Wrong host/port | Check MYSQL_HOST, MYSQL_PORT |
| `Access denied` | Wrong credentials | Verify username/password |
| `Unknown database` | Database doesn't exist | Create database first |
| `Table not found` | Migration not run | Run `tcb db migrate` |
| `Deadlock` | Concurrent writes | Retry with backoff |
| `Lock wait timeout` | Long transaction | Break into smaller transactions |

### Database Performance

| Symptom | Cause | Solution |
|---------|-------|----------|
| Slow queries | No index | Add indexes for WHERE/ORDER BY fields |
| Timeout | Large result set | Use pagination, limit results |
| High memory | Fetching too much | Add `.limit()`, project fields |
| Connection errors | Connection pool exhausted | Close connections, check pool size |

## Storage Issues

### File Upload/Download Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `File not found` | Wrong path | Check path is case-sensitive |
| `Permission denied` | No write access | Check environment permissions |
| `Upload timeout` | File too large (>5MB via SDK) | Use server-side upload flow |
| `Invalid path` | Wrong format | Use `/folder/file.jpg` format |
| `Storage quota exceeded` | Environment limit | Clean up old files |

### Upload Best Practice for Large Files

```javascript
// Instead of SDK upload (>5MB), use server-side upload
exports.main = async (event, context) => {
  // Get upload credentials
  const { url, token, fileID } = await app.uploadFile({
    cloudPath: '/uploads/' + event.filename
  });

  // Return to client for direct upload to COS
  return { uploadUrl: url, token, fileID };
};
```

## Hosting Issues

### Deployment Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `No index.html` | Directory empty or wrong path | Check `--dir` path |
| `Build failed` | Local build error | Fix build, check logs |
| `Permission denied` | No hosting access | Check environment permissions |
| `Storage full` | Quota exceeded | Delete old files |

### SPA Routing 404

| Symptom | Cause | Solution |
|---------|-------|----------|
| 404 on direct URL | CDN caching | Deploy with `--force` |
| 404 on refresh | Routing not configured | CloudBase handles this automatically |
| Stale content | Old files cached | Deploy with `--force` |
| Missing assets | Wrong paths | Check build output paths |

### SSL/Certificate Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Certificate not ready | New domain | Wait 1-5 minutes |
| Certificate expired | Auto-renewal failed | Re-add domain |
| Mixed content | HTTP resources | Use HTTPS for all resources |

## Authentication Issues

### Login/Permission Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Login required` | Not authenticated | Run `tcb login` or set env vars |
| `Invalid credentials` | Wrong secret ID/key | Verify in TCB console |
| `Permission denied` | Insufficient permissions | Grant more permissions in CAM |
| `Token expired` | STS token too old | Refresh credentials |

### Credential Troubleshooting

```bash
# Check if credentials are set
echo $TCB_SECRET_ID
echo $TCB_SECRET_KEY

# Verify credentials work
tcb env info

# If using MCP, check status
cdh cloudbase status
```

## MCP Server Issues

### MCP Not Responding

| Symptom | Cause | Solution |
|---------|-------|----------|
| Timeout on MCP call | Server not running | Restart MCP server |
| `Invalid credentials` | Wrong env vars | Verify TCB_SECRET_ID/KEY |
| `Tool not found` | Wrong tool name | Check MCP server tool list |
| `Environment not found` | Wrong env ID | Verify TCB_ENV_ID |

### MCP Debugging

```bash
# Check MCP status (live probe + tool count)
cdh cloudbase status

# Full diagnostic (config dump + auth state + live probe)
cdh mcp debug cloudbase

# Reconfigure MCP
cdh cloudbase init --secret-id xxx --secret-key xxx

# Clear credentials (logout)
cdh cloudbase logout

# Manual MCP test
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | npx @cloudbase/cloudbase-mcp
```

### Inspecting / Migrating the config

```bash
# Show current config (secret values masked)
cdh mcp list

# Inspect the raw JSON
cat ~/.onecode/mcp.json

# One-shot: migrate legacy mcps.yaml -> mcp.json (auto-backs up)
cdh mcp migrate
```

## Environment Issues

### Environment Not Found

```bash
# List available environments
tcb env list

# Check if correct env is set
tcb env info

# Set correct environment
tcb env use env-xxxxx
```

### Quota Exceeded

| Resource | Limit | Solution |
|----------|-------|----------|
| Functions | 100 | Delete unused functions |
| Collections | 100 | Clean up old collections |
| Storage | 50GB | Delete old files |
| DocDB | 2GB | Archive or delete old data |
| MySQL | 20GB | Clean up old data |

## Network Issues

### Function Can't Reach External API

```javascript
// Check if outbound network is allowed
// TCB functions can access internet by default

// If behind firewall, use TCB VPC or internal services
const result = await app.callFunction({
  name: 'target-function'
});
```

### CORS Errors

```javascript
// In function, set CORS headers
exports.main = async (event, context) => {
  return {
    statusCode: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    },
    body: JSON.stringify(result)
  };
};
```

## CI/CD Issues

### GitHub Actions Deployment Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Login required` | Secrets not set | Add TCB secrets to GitHub |
| `Environment not found` | Wrong env ID | Check GitHub secrets |
| `Deploy timeout` | Build takes too long | Optimize build, increase timeout |
| `E2E tests fail` | Deployment issue | Check function logs |

### Debug CI/CD

```yaml
- name: Debug
  run: |
    echo "TCB_ENV_ID: ${{ secrets.TCB_ENV_ID }}"
    tcb env info
    tcb fn list
```

## Performance Issues

### Function Performance

| Symptom | Cause | Solution |
|---------|-------|----------|
| High latency | Cold start | Increase memory, keep-warm |
| Memory pressure | Large variables | Minimize in-memory data |
| Timeout | Long execution | Optimize, increase timeout |
| Inconsistent | Cold starts | Normal, expect variance |

### Database Performance

| Symptom | Cause | Solution |
|---------|-------|----------|
| Slow queries | Missing index | Add indexes |
| Timeout | Large result | Paginate, limit |
| High memory | Fetching too much | Project fields, limit |

## Getting Help

### Collect Debug Info

```bash
# Environment info
tcb env info > env-info.txt

# Function list and configs
tcb fn list --env $TCB_ENV_ID > functions.txt

# Recent logs
tcb fn logs --name <function> --limit 100 --env $TCB_ENV_ID > logs.txt

# Hosting info
tcb hosting detail --env $TCB_ENV_ID > hosting.txt
```

### Common Solutions Summary

1. **Deployment fails** → Check env ID, credentials, package size
2. **Function timeout** → Optimize code, increase timeout, or use CloudBase Run
3. **Database error** → Check indexes, pagination, permissions
4. **Permission denied** → Verify credentials, check collection rules
5. **Stale content** → Deploy with `--force`, clear CDN cache
6. **MCP not working** → Re-run `cdh cloudbase init`, check credentials

### Useful Commands

```bash
# Full environment status
tcb env info

# Function debugging
tcb fn detail --name <function> --env $TCB_ENV_ID
tcb fn logs --name <function> --tail --env $TCB_ENV_ID

# Database debugging
tcb db list --env $TCB_ENV_ID
tcb db query "SELECT * FROM users LIMIT 1" --env $TCB_ENV_ID

# Storage debugging
tcb storage list --path / --env $TCB_ENV_ID

# MCP debugging
cdh cloudbase status
```

## CLS 日志服务集成 (requestId 追踪)

腾讯云 SCF 自2021年1月29日起自动将函数日志投递至日志服务 CLS，支持通过 `requestId` 进行调用链追踪。

### CLS 日志字段

| 字段名 | 类型 | 含义 |
|--------|------|------|
| `SCF_RequestId` | text | 请求 ID（调用链追踪键） |
| `SCF_FunctionName` | text | 函数名称 |
| `SCF_Namespace` | text | 命名空间 |
| `SCF_Message` | text | 日志内容 |
| `SCF_StartTime` | long | 调用开始时间 (Unix ms) |
| `SCF_Duration` | long | 运行时间 (ms) |
| `SCF_StatusCode` | long | HTTP 状态码 |
| `SCF_Level` | text | 日志级别 (INFO/WARN/ERROR) |
| `SCF_MemUsage` | double | 内存使用 (bytes) |

### 通过 requestId 查询日志

#### 方法1: CLS 控制台 (推荐手动排查)

1. 登录 [腾讯云日志服务控制台](https://console.cloud.tencent.com/cls)
2. 选择与 SCF 函数相同的地域
3. 进入 `SCF_logset` 日志集
4. 选择日志主题：`SCF_logtopic_{函数名}_{命名空间}`
5. 检索条件：`SCF_RequestId:<requestId>`

#### 方法2: SCF 控制台

1. 进入 [SCF 控制台](https://console.cloud.tencent.com/scf)
2. 选择函数 → 日志页签 → **高级检索**
3. 检索条件：`SCF_RequestId:<requestId>`

#### 方法3: cdh cls CLI (自动化)

```bash
# 安装/更新
pip install -U cdh

# 通过 requestId 查询
cdh cls search --request-id req-xxxxx --function hello --env $TCB_ENV_ID

# 关键词查询
cdh cls search --function hello --keyword error --limit 100 --env $TCB_ENV_ID

# 时间范围查询
cdh cls search --function hello --start-time "2026-08-04 10:00:00" --end-time "2026-08-04 12:00:00"
```

#### 方法4: Python API

```python
from cdh.tools.cls_search import CLSLogSearcher

searcher = CLSLogSearcher(region="ap-shanghai")

# 通过 requestId 查询
logs = searcher.search_by_request_id(
    request_id="req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    function_name="hello",
    namespace="default"
)

for log in logs:
    print(f"[{log['time']}] {log['message']}")
```

### 常见检索模式

| 场景 | 检索条件 |
|------|----------|
| 特定请求追踪 | `SCF_RequestId:<requestId>` |
| 错误日志 | `SCF_Message:error OR SCF_Level:ERROR` |
| 超时请求 (>60s) | `SCF_Duration:>60000` |
| 内存超限 (>1.5GB) | `SCF_MemUsage:>1610612736` |
| HTTP 5xx | `SCF_StatusCode:>=500` |
| 特定函数 | `SCF_FunctionName:hello` |
| 特定命名空间 | `SCF_Namespace:default` |
| 时间范围 | `SCF_StartTime:>1722756000000 AND SCF_StartTime:<1722763200000` |

### 权限要求

| 操作 | 所需权限 |
|------|----------|
| 查看 CLS 日志 (控制台) | `QcloudCLSReadOnlyAccess` |
| 调用 CLS API | `QcloudCLSReadOnlyAccess` |
| SCF 默认日志 | 已自动配置（无需额外设置）|

### 计费说明

- CLS 有免费额度（10U/月，约10元）
- SCF 专用日志主题会占用 CLS 免费额度
- 日志默认保留7天

### CLS 日志集/主题命名

| 类型 | 命名规则 |
|------|----------|
| 日志集 | `SCF_logset` (SCF 专用) |
| 日志主题 | `SCF_logtopic_{函数名}_{命名空间}` |

### 注意事项

1. **requestId 获取**：通常在函数响应、错误信息或客户端日志中可以找到
2. **时间范围**：建议结合 `SCF_StartTime` 缩小查询范围
3. **跨地域**：CLS 日志集地域需与 SCF 函数地域一致
4. **索引配置**：新建 SCF 函数时会自动配置索引，无需手动开启

