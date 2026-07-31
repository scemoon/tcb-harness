# TCB REST API Reference

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
https://tcb-api.cloud.tencent.com/mcp/v1
```

Or use HTTP transport:
```
https://tcb-api.cloud.tencent.com/mcp/v1?env_id=<envId>
```

## Authentication

### Headers

```
X-TencentCloud-SecretId: <your-secret-id>
X-TencentCloud-SecretKey: <your-secret-key>
```

### Environment Parameter

Pass `env_id` in query string or request body.

## Common Endpoints

### Environment

#### Get Environment Info

```
GET /environments/{envId}
```

Response:
```json
{
  "EnvId": "env-xxxxx",
  "Region": "ap-shanghai",
  "Status": "running",
  "CreatedTime": "2024-01-01T00:00:00Z"
}
```

#### List Environments

```
GET /environments
```

### Functions

#### List Functions

```
GET /functions?envId=<envId>
```

Response:
```json
{
  "Functions": [
    {
      "FunctionId": "cloudbaser-xxxxx",
      "FunctionName": "hello",
      "Runtime": "Nodejs16.13",
      "Status": "active",
      "ModifiedTime": "2024-01-15T10:00:00Z"
    }
  ],
  "Total": 1
}
```

#### Deploy Function

```
POST /functions/{functionName}/deploy?envId=<envId>
```

Request:
```json
{
  "CodeUri": "./functions/hello",
  "Handler": "index.main",
  "Runtime": "Nodejs16.13",
  "Timeout": 60,
  "MemorySize": 256,
  "HttpHttpTrigger": {
    "Enable": true,
    "Path": "/hello"
  }
}
```

#### Invoke Function

```
POST /functions/{functionName}/invoke?envId=<envId>
```

Request:
```json
{
  "params": {}
}
```

Response:
```json
{
  "Result": {
    "message": "Hello World"
  },
  "Duration": 15,
  "MemUsage": 65536
}
```

#### Get Function Logs

```
GET /functions/{functionName}/logs?envId=<envId>&limit=50
```

### Database

#### List Collections

```
GET /databases/{envId}/collections
```

#### Query Documents

```
POST /databases/{envId}/collections/{collection}/query
```

Request:
```json
{
  "query": { "status": "active" },
  "limit": 20,
  "offset": 0
}
```

Response:
```json
{
  "data": [
    { "_id": "xxx", "name": "Alice", "status": "active" }
  ],
  "total": 100
}
```

#### Insert Document

```
POST /databases/{envId}/collections/{collection}/insert
```

Request:
```json
{
  "data": { "name": "Bob", "email": "bob@example.com" }
}
```

#### Update Document

```
POST /databases/{envId}/collections/{collection}/update
```

Request:
```json
{
  "query": { "_id": "document-id" },
  "update": { "$set": { "status": "inactive" } }
}
```

#### Delete Document

```
POST /databases/{envId}/collections/{collection}/delete
```

Request:
```json
{
  "query": { "_id": "document-id" }
}
```

### Storage

#### Get Upload File URL

```
POST /storage/{envId}/upload
```

Request:
```json
{
  "cloudPath": "/uploads/avatar.jpg",
  "contentType": "image/jpeg"
}
```

Response:
```json
{
  "url": "https://cos.ap-shanghai.myqcloud.com/...",
  "token": "xxx"
}
```

#### Get Download File URL

```
POST /storage/{envId}/download
```

Request:
```json
{
  "cloudPath": "/uploads/avatar.jpg"
}
```

Response:
```json
{
  "url": "https://cos.ap-shanghai.myqcloud.com/...?sign=xxx",
  "expires": 3600
}
```

#### Delete File

```
POST /storage/{envId}/delete
```

Request:
```json
{
  "cloudPath": "/uploads/avatar.jpg"
}
```

### Hosting

#### Deploy Hosting

```
POST /hosting/{envId}/deploy
```

Request (multipart):
```
files: [binary content]
path: /
```

Response:
```json
{
  "files": ["index.html", "app.js"],
  "urls": ["https://env-xxxxx.tcb-preview.com/"]
}
```

## Error Responses

All API errors follow this format:

```json
{
  "ErrorCode": "INVALID_PARAMETER",
  "ErrorMessage": "Function name is required",
  "RequestId": "req-xxxxx"
}
```

### Common Error Codes

| Code | Meaning |
|------|---------|
| `INVALID_PARAMETER` | Missing or invalid parameter |
| `AUTH_FAILURE` | Authentication failed |
| `RESOURCE_NOT_FOUND` | Resource doesn't exist |
| `RESOURCE_EXIST` | Resource already exists |
| `LIMIT_EXCEEDED` | Quota exceeded |
| `INTERNAL_ERROR` | Server error |

## Rate Limits

| API | Limit |
|-----|-------|
| Function invoke | 1000/min |
| Database query | 500/min |
| Storage operations | 200/min |
| Other APIs | 100/min |

## Best Practices

1. **Use SDK when possible** - Easier than raw API
2. **Implement retry logic** - Handle transient errors
3. **Use pagination** - Don't fetch all data at once
4. **Cache responses** - When data doesn't change frequently
5. **Use appropriate timeout** - Some operations take longer

For SDK reference → `sdk.md`
