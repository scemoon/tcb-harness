# Aliyun Troubleshooting Guide

## Quick Diagnosis

Run these commands to diagnose common issues:

```bash
# Check function status
fun list functions --service my-service

# Get function logs
fun logs --function hello --service my-service --tail 50

# Check OSS bucket
ossutil ls oss://my-bucket/

# Check RDS instance
aliyun rds DescribeDBInstances --region cn-shanghai

# Check CDN domain
aliyun cdn DescribeCdnDomainDetail --DomainName example.com
```

## Function Issues

### Function Deployment Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Function not found` | Wrong function name or service | `fun list functions` to verify |
| `Deploy timeout` | Network or package size | Check package size, reduce dependencies |
| `Code package too large` | > 50MB compressed | Minimize dependencies |
| `Invalid handler` | Handler path wrong | Check template.yml handler setting |
| `Runtime not supported` | Wrong runtime | Use nodejs16, python3.9, etc. |

### Function Invocation Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Function timeout` | Execution > timeout | Optimize function, or use SAE |
| `Memory exceeded` | > memory limit | Increase memory in template |
| `Concurrent limit` | > 1000 concurrent | Request increase or implement throttling |
| `Permission denied` | No access to resource | Check RAM policies |
| `Handler not found` | Export name wrong | Module must export `handler` |

### Cold Start Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| First request slow | Cold start | Normal, 500ms-2s expected |
| Every request slow | Large package | Minimize dependencies |
| Slow after idle | Container recycled | Use provisioned concurrency |
| Inconsistent latency | VPC cold start | Avoid VPC if possible |

## Database Issues

### RDS Connection Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Wrong host/port | Check RDS endpoint |
| `Access denied` | Wrong credentials | Verify username/password |
| `Unknown database` | Database doesn't exist | Create database first |
| `Too many connections` | Connection pool exhausted | Close connections properly |

### TableStore Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `OTS permission denied` | No RAM policy | Add OTS permissions to RAM role |
| `OTS throttle` | Throughput exceeded | Increase reserved capacity |
| `OTS table not found` | Wrong table name | `ots listtable` to verify |
| `OTS timeout` | Large query | Reduce limit, paginate |

### Database Performance

| Symptom | Cause | Solution |
|---------|-------|----------|
| Slow queries | No index | Add indexes for WHERE/ORDER BY |
| Timeout | Large result set | Use pagination, limit results |
| High memory | Fetching too much | Add `.limit()`, project fields |
| Connection errors | Pool exhausted | Close connections, check pool size |

## Storage Issues

### OSS Upload/Download Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `Bucket not exist` | Wrong bucket name | Check bucket name |
| `Object not exist` | Wrong object path | Check path (case-sensitive) |
| `Permission denied` | No write access | Check RAM policy |
| `Upload timeout` | Large file | Use multipart upload |
| `Invalid argument` | Path format wrong | Use `oss://bucket/path` format |

### Upload Best Practice for Large Files

```bash
# Use multipart for files > 5GB
ossutil cp ./large-file.zip oss://my-bucket/backups/ \
  --part-size 104857600  # 100MB parts
```

## CDN Issues

### CDN Not Working

| Symptom | Cause | Solution |
|---------|-------|----------|
| 404 on content | Cache not refreshed | Refresh CDN after deploy |
| Old content | CDN serving cached version | Refresh specific path |
| SSL not ready | Certificate provisioning | Wait 1-10 minutes |
| DNS not propagated | CNAME not active | Wait 5-10 minutes |

### Refresh CDN

```bash
# Refresh single file
aliyun cdn RefreshObjectCaches \
  --ObjectType File \
  --ObjectPath http://example.com/index.html

# Refresh directory
aliyun cdn RefreshObjectCaches \
  --ObjectType Directory \
  --ObjectPath http://example.com/static/
```

## Authentication Issues

### Login/Permission Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `InvalidAccessKeyId` | Wrong AccessKey | Verify in RAM console |
| `SignatureDoesNotMatch` | Secret key mismatch | Check AccessKey Secret |
| `Permission denied` | Insufficient RAM permissions | Grant more permissions |
| `Token expired` | STS token too old | Refresh credentials |

### Credential Troubleshooting

```bash
# Check if credentials are set
echo $ALICLOUD_ACCESS_KEY
echo $ALICLOUD_SECRET_KEY

# Verify credentials work
aliyun ecs DescribeInstances --region cn-shanghai
```

## Network Issues

### Function Can't Reach External API

```javascript
// FC functions can access internet by default
// If behind VPC, configure NAT gateway

// Test from function
module.exports.handler = async (event, context) => {
  const response = await fetch('https://api.example.com/data');
  return await response.json();
};
```

### CORS Errors

```javascript
// In function, set CORS headers
module.exports.handler = async (req, resp, context) => {
  resp.setHeader('Access-Control-Allow-Origin', '*');
  resp.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  resp.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
};
```

## CI/CD Issues

### GitHub Actions Deployment Fails

| Error | Cause | Solution |
|-------|-------|----------|
| `InvalidAccessKeyId` | Secrets not set | Add Aliyun secrets to GitHub |
| `Function not found` | Wrong service name | Check FC_SERVICE secret |
| `Deploy timeout` | Build takes too long | Optimize build, increase timeout |
| `E2E tests fail` | Deployment issue | Check function logs |

### Debug CI/CD

```yaml
- name: Debug
  run: |
    echo "ALICLOUD_REGION: ${{ secrets.ALICLOUD_REGION }}"
    fun --access-key-id ${{ secrets.ALICLOUD_ACCESS_KEY }} \
       --access-key-secret ${{ secrets.ALICLOUD_SECRET_KEY }} \
       list functions --service my-service
```

## Performance Issues

### Function Performance

| Symptom | Cause | Solution |
|---------|-------|----------|
| High latency | Cold start | Increase memory, use provisioned |
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
# Function logs
fun logs --function hello --service my-service --tail 100 > logs.txt

# OSS bucket contents
ossutil ls oss://my-bucket/ > bucket.txt

# RDS instance info
aliyun rds DescribeDBInstances --region cn-shanghai > rds.txt
```

### Common Solutions Summary

1. **Deployment fails** → Check credentials, function name, package size
2. **Function timeout** → Optimize code, increase timeout, or use SAE
3. **Database error** → Check indexes, pagination, permissions
4. **Permission denied** → Verify RAM policies, credentials
5. **CDN stale content** → Refresh CDN after deploy
6. **OSS access fails** → Check bucket name, path, RAM policy

### Useful Commands

```bash
# Full function status
fun list functions --service my-service
fun info --function hello --service my-service

# Function logs
fun logs --function hello --service my-service --tail --follow

# OSS debugging
ossutil ls oss://my-bucket/ --max-size 10
ossutil stat oss://my-bucket/path

# RDS debugging
aliyun rds DescribeDBInstanceAttribute --DBInstanceId rm-xxxxx
```
