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
# Check MCP status
cdh cloudbase status

# Reconfigure MCP
cdh cloudbase init --secret-id xxx --secret-key xxx

# Manual MCP test
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | npx @cloudbase/cloudbase-mcp
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
