# Aliyun REST API Reference

## When to Use REST API vs CLI vs SDK

**Use REST API when:**
- Need programmatic access from external systems
- CLI/SDK doesn't support specific operation
- Building custom integrations
- Debugging and testing

**Use SDK when:**
- Building applications (preferred over raw API)
- Need type-safe access

**Use CLI when:**
- One-off operations
- CI/CD pipelines
- Local development

## API Base URL

```
https://{product}.{region}.aliyuncs.com/
```

Common endpoints:
- Function Compute: `https://fc.{region}.aliyuncs.com`
- OSS: `https://oss.{region}.aliyuncs.com`
- RDS: `https://rds.{region}.aliyuncs.com`
- TableStore: `https://ots.{region}.aliyuncs.com`
- CDN: `https://cdn.aliyuncs.com`

## Authentication

### Common Headers

```
Authorization: <signature>
Content-Type: application/json
X-Accees-Key-Id: <access-key-id>
```

### Signature Algorithm

```javascript
const crypto = require('crypto');

function sign(request, accessKeySecret) {
  const stringToSign = crypto
    .createHmac('sha256', accessKeySecret)
    .update(request)
    .digest('base64');
  return stringToSign;
}
```

## Function Compute API

### List Services

```
GET /services
```

### Create Service

```
POST /services
{
  "ServiceName": "my-service",
  "Description": "My service"
}
```

### Deploy Function

```
POST /services/{serviceName}/functions/{functionName}
{
  "Runtime": "nodejs14",
  "Handler": "index.handler",
  "MemorySize": 256,
  "Timeout": 60,
  "Code": {
    "ZipFile": "<base64-encoded-code>"
  }
}
```

### Invoke Function

```
POST /services/{serviceName}/functions/{functionName}/invocations
{
  "event": {}
}
```

## OSS API

### List Buckets

```
GET /?buckets
```

### Put Object

```
PUT /{bucket}/{object}
Content-Type: image/jpeg
Body: <binary-data>
```

### Get Object

```
GET /{bucket}/{object}
```

### Generate Signed URL

```
GET /{bucket}/{object}?Expires=3600&OSSAccessKeyId=xxx&Signature=xxx
```

## RDS API

### Describe Instances

```
GET /instances?RegionId=cn-shanghai
```

### Create Database

```
POST /instances/{instanceId}/databases
{
  "DBName": "myapp",
  "CharacterSetName": "utf8mb4"
}
```

### Create Account

```
POST /instances/{instanceId}/accounts
{
  "AccountName": "appuser",
  "AccountPassword": "StrongPass123!",
  "AccountType": "Normal"
}
```

## CDN API

### Refresh Cache

```
POST /?RefreshObjectCaches
{
  "ObjectPath": ["http://example.com/index.html"],
  "ObjectType": "File"
}
```

### Describe Domain Stats

```
GET /?DomainStats&DomainName=example.com&StartTime=1640000000&EndTime=1640100000
```

## Error Responses

All API errors follow this format:

```json
{
  "Code": "InvalidAccessKeyId",
  "Message": "The specified AccessKeyId is invalid",
  "RequestId": "12345678-1234-1234-1234-123456789012"
}
```

### Common Error Codes

| Code | Meaning |
|------|---------|
| `InvalidAccessKeyId` | Access key not found |
| `SignatureDoesNotMatch` | Signature verification failed |
| `InvalidParameter` | Missing or invalid parameter |
| `ResourceNotFound` | Resource doesn't exist |
| `Unauthorized` | Permission denied |
| `Throttling` | Rate limit exceeded |

## Rate Limits

| API | Limit |
|-----|-------|
| Function Compute invoke | 1000/min |
| OSS | 10000/min (upload), 10000/min (download) |
| RDS | 100/min |
| CDN refresh | 100/day (file), 10/day (directory) |

## Best Practices

1. **Use SDK when possible** - Easier than raw API
2. **Implement retry logic** - Handle transient errors
3. **Use pagination** - Don't fetch all data at once
4. **Cache responses** - When data doesn't change frequently
5. **Use appropriate timeout** - Some operations take longer

For SDK reference → `sdk.md`
