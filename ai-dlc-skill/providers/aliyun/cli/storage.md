# Aliyun CLI: Storage (ossutil)

## When to Use Storage Commands

| Goal | Command | Notes |
|------|---------|-------|
| Upload file | `ossutil cp` | Main upload command |
| Download file | `ossutil cp` | Bidirectional |
| List files | `ossutil ls` | Path is case-sensitive |
| Delete file | `ossutil rm` | Permanent deletion |
| Get metadata | `ossutil stat` | Object info |
| Generate signed URL | `ossutil sign` | For private buckets |
| Sync directories | `ossutil sync` | Mirror directories |

## Decision Tree for Storage Operations

```
Need to work with OSS?
├── Upload user content → ossutil cp
├── Download backup/file → ossutil cp
├── List directory → ossutil ls
├── Delete old files → ossutil rm
├── Get public URL → ossutil stat
├── Large file upload → ossutil cp (multipart)
└── Sync between buckets → ossutil sync
```

## Configure ossutil

```bash
ossutil config
```

Enter when prompted:
- AccessKey ID
- AccessKey Secret
- Default region (cn-shanghai or other)
- Output format (json or text)

Or use environment variables:
```bash
export ALICLOUD_ACCESS_KEY=your-key
export ALICLOUD_SECRET_KEY=your-secret
export ALICLOUD_REGION=cn-shanghai
```

## List Files

```bash
ossutil ls oss://my-bucket/
```

Output:
```
LastModifiedTime                   Size(B)  ObjectPath
2024-01-15 10:30:00 +0800      125000  oss://my-bucket/avatar.jpg
2024-01-14 15:22:00 +0800     2400000  oss://my-bucket/doc.pdf
```

### List with Pattern

```bash
# List all jpg files
ossutil ls oss://my-bucket/ --pattern "*.jpg"

# List files in specific prefix
ossutil ls oss://my-bucket/uploads/
```

### List with Pagination

```bash
ossutil ls oss://my-bucket/ --max-size 100 --marker <next-marker>
```

## Upload File

### Basic Upload

```bash
ossutil cp ./avatar.jpg oss://my-bucket/avatars/avatar.jpg
```

### Upload with Content-Type

```bash
ossutil cp ./document.pdf oss://my-bucket/docs/report.pdf \
  --content-type application/pdf
```

### Upload Directory

```bash
ossutil cp -r ./dist oss://my-bucket/ --update
```

### Upload Options

| Option | Description |
|--------|-------------|
| `--update` | Skip if source is older |
| `--force` | Overwrite without prompt |
| `--quiet` | Suppress output |
| `--parallel <num>` | Parallel upload threads |
| `--part-size <size>` | Multipart size |
| `--checkpoint-dir <dir>` | Checkpoint file for resume |

### Multipart Upload (Large Files)

```bash
ossutil cp ./large-file.zip oss://my-bucket/backups/large-file.zip \
  --part-size 104857600  # 100MB parts
```

## Download File

### Basic Download

```bash
ossutil cp oss://my-bucket/avatars/avatar.jpg ./download.jpg
```

### Download with Progress

```bash
ossutil cp oss://my-bucket/backups/archive.zip ./archive.zip \
  --checkpoint-dir ./checkpoint/
```

## Delete File

### Delete Single File

```bash
ossutil rm oss://my-bucket/old-file.jpg
```

### Delete with Confirmation

```bash
ossutil rm oss://my-bucket/temp/ -r
```

### Delete by Pattern

```bash
# Delete all .log files
ossutil rm oss://my-bucket/logs/ --pattern "*.log"
```

### Delete Empty Bucket

```bash
ossutil rm oss://my-bucket/ -a
```

## Get File URL

### Get Object URL

```bash
ossutil stat oss://my-bucket/avatars/avatar.jpg
```

Output:
```
Bucket: my-bucket
Object: /avatars/avatar.jpg
URL: https://my-bucket.oss-cn-shanghai.aliyuncs.com/avatars/avatar.jpg
Size: 125000
LastModified: 2024-01-15 10:30:00
```

### Generate Signed URL

```bash
ossutil sign oss://my-bucket/private.pdf --timeout 3600
```

Returns URL with signature valid for 1 hour.

## Sync Directories

### Sync Local to OSS

```bash
ossutil sync ./dist oss://my-bucket/ --update
```

### Sync OSS to OSS

```bash
ossutil sync oss://bucket1/ oss://bucket2/ --update
```

### Sync with Delete

```bash
# Delete files in target not in source
ossutil sync ./dist oss://my-bucket/ --delete
```

## Set Object Metadata

### Set Cache-Control

```bash
ossutil set-meta oss://my-bucket/ \
  -h "Cache-Control:max-age=31536000" \
  --object "*.js,*.css"
```

### Set Content-Type

```bash
ossutil set-meta oss://my-bucket/images/ \
  -h "Content-Type:image/webp" \
  --object "*.jpg"
```

## Create Bucket

```bash
ossutil mb oss://new-bucket/
```

### With Storage Class

```bash
# Create Infrequent Access bucket
ossutil mb oss://archive-bucket/ --storage-class IA

# Create Archive bucket
ossutil mb oss://cold-bucket/ --storage-class Archive
```

## Bucket Policy

### Set Bucket ACL

```bash
ossutil set-acl oss://my-bucket/ private
```

| ACL | Access |
|-----|--------|
| `private` | Owner only |
| `public-read` | Anyone read |
| `public-read-write` | Anyone read/write |
| `default` | Inherit from bucket |

## Agent Workflows

### Workflow: Upload User Avatar

```bash
# 1. Upload file
ossutil cp ./temp_avatar.jpg \
  oss://my-bucket/avatars/${userId}/avatar.jpg

# 2. Get public URL
ossutil stat oss://my-bucket/avatars/${userId}/avatar.jpg

# 3. Return URL to frontend
```

### Workflow: Backup Database

```bash
# 1. Export database (pseudo-code)
mysqldump -h ${RDS_HOST} -u ${RDS_USER} -p > backup.sql

# 2. Compress
gzip backup.sql

# 3. Upload to OSS
ossutil cp ./backup.sql.gz \
  oss://my-bucket/backups/db_$(date +%Y%m%d).sql.gz

# 4. Cleanup local file
rm backup.sql.gz
```

### Workflow: Static Site Deployment

```bash
# 1. Upload all files
ossutil cp -r ./dist oss://my-bucket/ --force

# 2. Set proper cache headers
ossutil set-meta oss://my-bucket/ \
  -h "Cache-Control:max-age=31536000" \
  --object "*.js,*.css,*.png"

# 3. Set short cache for HTML
ossutil set-meta oss://my-bucket/ \
  -h "Cache-Control:no-cache" \
  --object "*.html"

# 4. Refresh CDN
aliyun cdn RefreshObjectCaches --ObjectType directory \
  --ObjectPath http://my-bucket.oss-cn-shanghai.aliyuncs.com/
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `The bucket you access does not exist` | Wrong bucket name | Check bucket name |
| `The specified object does not exist` | Wrong object path | Check path case-sensitive |
| `Permission denied` | No write access | Check RAM policy |
| `Invalid argument` | Path format wrong | Use `oss://bucket/path` format |
| `Multipart upload failed` | Network issue | Use `--checkpoint-dir` for resume |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
