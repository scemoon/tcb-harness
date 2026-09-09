# OSS (Object Storage Service)

## When to Use OSS

**Use OSS when:**
- Store files (images, videos, documents)
- Host static assets for CDN delivery
- Store user-generated content
- Backup and archive data
- Store function deployment packages
- Store function compute code packages

**Do NOT use OSS when:**
- Need database-like queries → Use TableStore or RDS
- Need to store < 1KB metadata → Use TableStore field
- Hot data requiring instant retrieval → Consider Redis

## Agent Decision Guide

```
Need to store files?
├── User uploads (images, videos) → OSS
├── Function code packages → OSS (automatic with FC)
├── Static website assets → OSS + CDN
└── Temporary files during processing → OSS with lifecycle policy
```

## Storage Structure

```
Bucket: my-bucket-{region}
├── /uploads/           # User uploaded files
├── /avatars/           # User profile images
├── /documents/         # Document storage
└── /backups/           # Database backups
```

## File Operations

### Upload File

```bash
ossutil cp ./file.txt oss://my-bucket/uploads/file.txt
```

### Download File

```bash
ossutil cp oss://my-bucket/uploads/file.txt ./download.txt
```

### List Files

```bash
ossutil ls oss://my-bucket/uploads/
```

### Delete File

```bash
ossutil rm oss://my-bucket/uploads/file.txt
```

### Get File URL

```bash
ossutil stat oss://my-bucket/uploads/file.txt
# Returns object URL and metadata
```

## CLI Reference (ossutil)

| Command | Description |
|---------|-------------|
| `ossutil ls oss://bucket/` | List objects |
| `ossutil cp localfile oss://bucket/path/` | Upload file |
| `ossutil cp oss://bucket/path localfile` | Download file |
| `ossutil rm oss://bucket/path` | Delete object |
| `ossutil stat oss://bucket/path` | Object metadata |
| `ossutil mkdir oss://bucket/dir/` | Create directory |
| `ossutil cp -r ./dir oss://bucket/dir/` | Upload directory |
| `ossutil sync oss://bucket1/ oss://bucket2/` | Sync between buckets |
| `ossutil sign oss://bucket/path` | Generate signed URL |

## Access Control

### Bucket Policies

| Type | Access | Use Case |
|------|--------|----------|
| public-read | Anyone with URL | Static assets, public downloads |
| private | Requires signature | User uploads, private documents |

### Signed URLs (for private buckets)

```bash
# Generate signed URL (valid for 1 hour)
ossutil sign oss://my-bucket/private.pdf --timeout 3600
```

### RAM Policy for Functions

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["oss:GetObject", "oss:PutObject"],
      "Resource": "acs:oss:*:*:my-bucket/*"
    }
  ]
}
```

## Upload from Functions

### Direct Upload (Node.js)

```javascript
const OSS = require('ali-oss');

const client = new OSS({
  region: process.env.ALICLOUD_REGION,
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  bucket: 'my-bucket'
});

async function uploadFile(fileName, fileContent) {
  const result = await client.put(fileName, fileContent);
  return result.url;
}
```

### Server-Side Upload (recommended for large files)

```javascript
// Get upload credentials from STS
const STM = require('aliyun-sdk').STS;

const sts = new STM({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  region: process.env.ALICLOUD_REGION
});

const token = await sts.assumeRole({
  RoleArn: 'acs:ram::xxx:role/oss-uploader',
  RoleSessionName: 'uploader-session'
});

// Return credentials to client for direct upload
return {
  AccessKeyId: token.credentials.AccessKeyId,
  AccessKeySecret: token.credentials.AccessKeySecret,
  SecurityToken: token.credentials.SecurityToken,
  bucket: 'my-bucket',
  endpoint: `oss-${process.env.ALICLOUD_REGION}.aliyuncs.com`
};
```

### Frontend Upload Example

```javascript
const client = new OSS({
  region: 'oss-cn-shanghai',
  accessKeyId: uploadData.AccessKeyId,
  accessKeySecret: uploadData.AccessKeySecret,
  stsToken: uploadData.SecurityToken,
  bucket: uploadData.bucket
});

const file = document.querySelector('#file-input').files[0];
const result = await client.put(`uploads/${Date.now()}_${file.name}`, file);
```

## Static Website Hosting

### Enable Static Website

```bash
ossutil website oss://my-bucket --index index.html --error 404.html
```

### Set Cache-Control

```bash
ossutil set-meta oss://my-bucket/path -h "Cache-Control:max-age=31536000"
```

### CDN Integration

```bash
# Add CDN domain
aliyun cdn AddCdnDomain \
  --DomainName example.com \
  --CdnType web \
  --SourceType oss \
  --SourceDomain my-bucket.oss-cn-shanghai.aliyuncs.com
```

## Lifecycle Policies

### Configure Lifecycle

```bash
# Delete temp files after 7 days
ossutil lifecycle --bucket my-bucket --lifecycle-file lifecycle.xml
```

### lifecycle.xml Example

```xml
<LifecycleConfiguration>
  <Rule>
    <ID>delete-temp</ID>
    <Prefix>temp/</Prefix>
    <Status>Enabled</Status>
    <Expiration>
      <Days>7</Days>
    </Expiration>
  </Rule>
  <Rule>
    <ID>archive-logs</ID>
    <Prefix>logs/</Prefix>
    <Status>Enabled</Status>
    <Transition>
      <Days>30</Days>
      <StorageClass>Archive</StorageClass>
    </Transition>
  </Rule>
</LifecycleConfiguration>
```

## Limits and Quotas

| Limit | Value |
|-------|-------|
| Max file size | 48.8TB (single object) |
| Max bucket size | Unlimited |
| Max buckets per account | 100 |
| Max objects per bucket | Unlimited |
| PUT/COPY/POST requests | 5GB max |
| Multipart upload | 48.8TB max |
| Upload speed | Limited by function memory |

## Best Practices

1. **Use meaningful object keys** - `uploads/{userId}/{timestamp}_{filename}`
2. **Implement cleanup** - Delete old temporary files with lifecycle
3. **Use content type** - Set correct Content-Type for browser display
4. **Compress images** - Resize on upload to save storage
5. **Use CDN** - Enable CDN for frequently accessed files
6. **Handle duplicates** - Check if file exists before upload
7. **Secure uploads** - Validate file types, scan for malware
8. **Use multipart** - For files > 5GB

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Upload fails | File too large | Use multipart upload |
| 403 Forbidden | Private bucket | Use signed URL |
| File not found | Wrong path | Check path is case-sensitive |
| Slow download | Not cached | Enable CDN caching |
| Upload timeout | Slow connection | Increase function timeout |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
