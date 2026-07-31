# TCB CLI: Storage Management

## When to Use Storage Commands

| Goal | Command | Notes |
|------|---------|-------|
| List files | `tcb storage list` | Path is case-sensitive |
| Upload file | `tcb storage upload` | Max 50GB per file |
| Download file | `tcb storage download` | From COS to local |
| Delete file | `tcb storage delete` | Permanent deletion |
| Get file URL | `tcb storage url` | Signed URL for private files |

## Decision Tree for Storage Operations

```
Need to work with files?
├── Upload user content → tcb storage upload
├── Download backup/file → tcb storage download
├── List directory → tcb storage list
├── Delete old files → tcb storage delete
├── Get public URL → tcb storage url
└── Large file upload → Use server-side upload flow (see services/cloud-storage.md)
```

## List Files

```bash
tcb storage list --path /uploads --env $TCB_ENV_ID
```

Output:
```
┌────────────────────────────────┬──────────────┬──────────────────┐
│ Path                           │ Size         │ Last Modified    │
├────────────────────────────────┼──────────────┼──────────────────┤
│ /uploads/avatar.jpg            │ 125 KB       │ 2024-01-15 10:30 │
│ /uploads/doc.pdf               │ 2.3 MB       │ 2024-01-14 15:22 │
│ /uploads/image.png             │ 450 KB       │ 2024-01-13 09:45 │
└────────────────────────────────┴──────────────┴──────────────────┘
```

### List with Pagination

```bash
tcb storage list --path /uploads --num 20 --marker <next-token> --env $TCB_ENV_ID
```

### List Subdirectory

```bash
tcb storage list --path /uploads/2024/01 --env $TCB_ENV_ID
```

## Upload File

### Basic Upload

```bash
tcb storage upload --local ./avatar.jpg --remote /uploads/avatar.jpg --env $TCB_ENV_ID
```

### With Content-Type

```bash
tcb storage upload \
  --local ./document.pdf \
  --remote /documents/report.pdf \
  --content-type application/pdf \
  --env $TCB_ENV_ID
```

### Upload with Progress

```bash
tcb storage upload \
  --local ./large-file.zip \
  --remote /backups/large-file.zip \
  --env $TCB_ENV_ID
# Shows progress bar
```

### Upload Options

| Option | Description |
|--------|-------------|
| `--local <path>` | Local file path |
| `--remote <path>` | Remote COS path |
| `--content-type <type>` | MIME type (auto-detected if not specified) |
| `--env <envId>` | Target environment |

## Download File

### Basic Download

```bash
tcb storage download --local ./download.jpg --remote /uploads/avatar.jpg --env $TCB_ENV_ID
```

### Download with Progress

```bash
tcb storage download \
  --local ./backup.zip \
  --remote /backups/latest.zip \
  --env $TCB_ENV_ID
```

## Delete File

### Delete Single File

```bash
tcb storage delete --remote /uploads/old-file.jpg --env $TCB_ENV_ID
```

### Delete Multiple Files

```bash
# Delete specific files
tcb storage delete --remote /uploads/file1.jpg --env $TCB_ENV_ID
tcb storage delete --remote /uploads/file2.jpg --env $TCB_ENV_ID

# Or use pattern (via function)
# Call function to delete files matching pattern
```

### Delete Folder Contents

```bash
# List first to verify
tcb storage list --path /temp --env $TCB_ENV_ID

# Delete each file
for f in $(tcb storage list --path /temp --env $TCB_ENV_ID | grep -o '/temp/[^ ]*'); do
  tcb storage delete --remote "$f" --env $TCB_ENV_ID
done
```

## Get File URL

### Get Signed URL (Private Files)

```bash
tcb storage url --remote /uploads/private.pdf --env $TCB_ENV_ID
```

Returns a signed URL valid for 1 hour.

### Get URL with Custom Expiry

```bash
tcb storage url --remote /uploads/doc.pdf --expiry 3600 --env $TCB_ENV_ID
```

### URL Types

| File Type | URL Type | Access |
|-----------|----------|--------|
| Public assets | Direct URL | Anyone with link |
| Private files | Signed URL | Valid for expiry period |

## Create/Delete Folder

### Create Folder

```bash
tcb storage createFolder --path /uploads/2024 --env $TCB_ENV_ID
```

**Note:** In COS, "folders" are just empty objects with `/` suffix.

### Delete Empty Folder

```bash
tcb storage deleteFolder --path /uploads/2024 --env $TCB_ENV_ID
```

**Note:** Folder must be empty.

## Agent Workflows

### Workflow: Upload User Avatar

```bash
# 1. Upload file
tcb storage upload \
  --local ./temp_avatar.jpg \
  --remote /avatars/${userId}/avatar.jpg \
  --env $TCB_ENV_ID

# 2. Get public URL (if public bucket)
tcb storage url --remote /avatars/${userId}/avatar.jpg --env $TCB_ENV_ID

# 3. Return URL to frontend
```

### Workflow: Backup Database

```bash
# 1. Export database
tcb db export --collection users --file ./backup/users.json --env $TCB_ENV_ID

# 2. Upload to storage
tcb storage upload \
  --local ./backup/users.json \
  --remote /backups/users_$(date +%Y%m%d).json \
  --env $TCB_ENV_ID

# 3. Cleanup local file
rm ./backup/users.json
```

### Workflow: Cleanup Old Files

```bash
# 1. List files older than 30 days
# (COS doesn't have native date filter, so list and filter in function)

# 2. Delete old temp files
tcb fn invoke --name cleanup-temp-files --params '{}' --env $TCB_ENV_ID
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `File not found` | Wrong path | Check path is case-sensitive |
| `Upload failed` | File too large | Use server-side upload flow |
| `Permission denied` | No write access | Check environment permissions |
| `Invalid path` | Path format wrong | Use `/folder/file.jpg` format |
| `Download failed` | File doesn't exist | Verify with `tcb storage list` |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
