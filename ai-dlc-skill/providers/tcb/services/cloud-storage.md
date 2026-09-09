# CloudBase Storage (COS)

## When to Use CloudBase Storage

**Use COS (Cloud Object Storage) when:**
- Store files (images, videos, documents)
- Host static assets for CDN delivery
- Store user-generated content
- Backup and archive data
- Store function deployment packages

**Do NOT use COS when:**
- Need database-like queries → Use DocDB
- Need to store < 1KB metadata → Use DocDB field
- Hot data requiring instant retrieval → Consider Tencent Cloud Redis

## Agent Decision Guide

```
Need to store files?
├── User uploads (images, videos) → COS
├── Function code packages → COS (automatic with --deployMode cos)
├── Static website assets → COS + CloudBase Hosting
└── Temporary files during processing → COS with lifecycle policy
```

## Storage Structure

```
Bucket: {env-id}-cos-{region}
├── /uploads/           # User uploaded files
├── /avatars/           # User profile images
├── /documents/         # Document storage
└── /backups/           # Database backups
```

## File Operations

### Upload File

```bash
tcb storage upload --local ./file.txt --remote /uploads/file.txt --env $TCB_ENV_ID
```

### Download File

```bash
tcb storage download --local ./download.txt --remote /uploads/file.txt --env $TCB_ENV_ID
```

### List Files

```bash
tcb storage list --path /uploads --env $TCB_ENV_ID
```

### Delete File

```bash
tcb storage delete --remote /uploads/file.txt --env $TCB_ENV_ID
```

### Get File URL

```bash
tcb storage url --remote /uploads/file.txt --env $TCB_ENV_ID
# Returns: https://{bucket}.cos.{region}.myqcloud.com/uploads/file.txt
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `tcb storage list --path <path> --env <envId>` | List files in path |
| `tcb storage upload --local <path> --remote <path> --env <envId>` | Upload file |
| `tcb storage download --local <path> --remote <path> --env <envId>` | Download file |
| `tcb storage delete --remote <path> --env <envId>` | Delete file |
| `tcb storage url --remote <path> --env <envId>` | Get file URL (with signature) |
| `tcb storage createFolder --path <path> --env <envId>` | Create folder |
| `tcb storage deleteFolder --path <path> --env <envId>` | Delete folder |

## Access Control

### Public vs Private Buckets

| Type | Access | Use Case |
|------|--------|----------|
| Public | Anyone with URL | Static assets, public downloads |
| Private | Requires signature | User uploads, private documents |

### Signed URLs (for private files)

Private files require a signed URL with expiration:

```javascript
// Generate signed URL (valid for 1 hour)
const signedUrl = await app.getTempFileURL({
  filePath: '/uploads/private.pdf',
  maxAge: 3600
});
```

### File Permissions

```javascript
// Make file publicly readable
await app.uploadFile({
  cloudPath: '/uploads/public.txt',
  filePath: './local.txt',
  onUploadProgress: (progress) => {
    console.log(`Uploaded: ${progress.loaded}/${progress.total}`);
  }
});

// Or set ACL via SDK
const cos = app.uploadFile({
  // ...
});
```

## Upload from Functions

### Direct Upload (small files < 5MB)

```javascript
const tcb = require('@cloudbase/node-sdk');
const fs = require('fs');

const app = tcb.init({
  env: process.env.TCB_ENV_ID
});

exports.main = async (event, context) => {
  // event.fileContent is base64 encoded for small files
  const buffer = Buffer.from(event.fileContent, 'base64');

  const result = await app.uploadFile({
    cloudPath: '/uploads/' + event.filename,
    fileContent: buffer
  });

  return { fileID: result.fileID };
};
```

### Server-Side Upload (recommended for large files)

```javascript
// Get upload credentials from TCB
exports.main = async (event, context) => {
  const { fileName, contentType } = event;

  // Get upload parameters
  const uploadData = await app.uploadFile({
    cloudPath: '/uploads/' + fileName
  });

  // Frontend uses these to upload directly to COS
  return {
    url: uploadData.url,           // Upload to this URL
    token: uploadData.token,       // Upload token
    fileId: uploadData.fileID,     // TCB file ID
    cloudPath: uploadData.cloudPath
  };
};
```

### Frontend Upload Example

```javascript
// Get upload credentials from function
const { url, token } = await callFunction({
  name: 'get-upload-params',
  data: { fileName: 'avatar.jpg', contentType: 'image/jpeg' }
});

// Upload directly to COS
const formData = new FormData();
formData.append('key', 'uploads/avatar.jpg');
formData.append('token', token);
formData.append('file', fileInput.files[0]);

await fetch(url, {
  method: 'POST',
  body: formData
});
```

## Storage in CloudBase Hosting

Files in COS are served through CDN for CloudBase Hosting:

```
User Request → CDN Edge → COS Origin → Static File
                      ↓ (cache)
              First request caches result
```

CDN automatically caches:
- Static assets (`.js`, `.css`, `.jpg`, etc.)
- Configurable cache duration

## Limits and Quotas

| Limit | Value |
|-------|-------|
| Max file size | 50GB (single file) |
| Max bucket size | Unlimited |
| Max files per folder | 1000 (recommend pagination) |
| Upload speed | Limited by function memory |
| Download speed | Limited by CDN带宽 |

## Lifecycle Policies

Set automatic deletion or transition for old files:

```javascript
// Via TCB console or API
// Examples:
// - Delete temp files after 7 days
// - Move logs to archive storage after 30 days
// - Clean up failed upload chunks
```

## Best Practices

1. **Use meaningful paths** - `/uploads/{userId}/{timestamp}_{filename}`
2. **Implement cleanup** - Delete old temporary files
3. **Use content type** - Set correct `Content-Type` for browser display
4. **Compress images** - Resize on upload to save storage
5. **Use CDN** - Enable CDN for frequently accessed files
6. **Handle duplicates** - Check if file exists before upload
7. **Secure uploads** - Validate file types, scan for malware

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Upload fails | File too large | Use server-side upload flow |
| 403 Forbidden | Private bucket | Use signed URL |
| File not found | Wrong path | Check path is case-sensitive |
| Slow download | Not cached | Enable CDN caching |
| Upload timeout | Slow connection | Increase function timeout |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
