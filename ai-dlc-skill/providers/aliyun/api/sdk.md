# Aliyun SDK Reference

## SDK Options

| SDK | Language | Use Case |
|-----|----------|----------|
| `@alicloud/fc-builders` | Node.js | Function Compute build/deploy |
| `@alicloud/oss-sdk` | Node.js | OSS operations |
| `ali-oss` | Node.js/Browser | OSS (recommended) |
| `@serverless-devs/sdk` | Multi | Serverless devs |
| `tablestore` | Node.js/Python/Java | TableStore |

## Function Compute SDK (@alicloud/fc)

### Installation

```bash
npm install @alicloud/fc-builders @alicloud/fc
```

### Initialize Client

```javascript
const FC = require('@alicloud/fc');
const fs = require('fs');

const fcClient = new FC({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  region: process.env.ALICLOUD_REGION
});
```

### Deploy Function

```javascript
const zipBuffer = fs.readFileSync('./function.zip');

await fcClient.createFunction('my-service', {
  FunctionName: 'hello',
  Handler: 'index.handler',
  Runtime: 'nodejs14',
  MemorySize: 256,
  Timeout: 60,
  Code: { ZipFile: zipBuffer.toString('base64') }
});
```

### Invoke Function

```javascript
const result = await fcClient.invokeFunction('my-service', 'hello', {
  invocationType: 'Sync',
  payload: JSON.stringify({ key: 'value' })
});

console.log(result.data); // Function response
```

## OSS SDK (ali-oss)

### Installation

```bash
npm install ali-oss
```

### Initialize Client

```javascript
const OSS = require('ali-oss');

const client = new OSS({
  region: process.env.ALICLOUD_REGION,
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  bucket: 'my-bucket'
});
```

### Upload File

```javascript
async function upload(fileName, fileContent) {
  const result = await client.put(fileName, fileContent);
  return result.url;
}

// Or with stream
const stream = fs.createReadStream('./file.txt');
const result = await client.putStream('uploads/file.txt', stream);
```

### Download File

```javascript
const result = await client.get('uploads/file.txt', './download.txt');
```

### List Files

```javascript
const result = await client.list({
  prefix: 'uploads/',
  marker: '',
  'max-keys': 100
});

result.objects.forEach(obj => {
  console.log(obj.name, obj.size);
});
```

### Generate Signed URL

```javascript
const url = client.signatureUrl('private/file.pdf', {
  expires: 3600
});
```

### Multipart Upload

```javascript
const file = fs.createReadStream('./large-file.zip');
const result = await client.multipartUpload('backups/large-file.zip', file, {
  partSize: 10 * 1024 * 1024, // 10MB parts
  progress: (p) => console.log(`Progress: ${p * 100}%`)
});
```

## TableStore SDK

### Installation

```bash
npm install tablestore
```

### Initialize Client

```javascript
const TableStore = require('tablestore');

const client = new TableStore.Client({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  instanceName: 'my-instance',
  region: process.env.ALICLOUD_REGION
});
```

### Put Row

```javascript
await client.putRow({
  tableName: 'users',
  primaryKey: [{ user_id: 'user-123' }],
  attributeColumns: [
    { name: 'name', value: 'Alice' },
    { name: 'email', value: 'alice@example.com' }
  ]
});
```

### Get Row

```javascript
const result = await client.getRow({
  tableName: 'users',
  primaryKey: [{ user_id: 'user-123' }]
});

console.log(result.row.attributes);
```

### Query with Index

```javascript
const result = await client.search({
  tableName: 'users',
  indexName: 'email_index',
  searchQuery: {
    offset: 0,
    limit: 10,
    query: {
      terms: [{ email: 'alice@example.com' }]
    }
  }
});
```

## RDS (MySQL) SDK

### Installation

```bash
npm install mysql2
```

### Connection Pool

```javascript
const mysql = require('mysql2/promise');

const pool = mysql.createPool({
  host: process.env.RDS_HOST,
  port: process.env.RDS_PORT || 3306,
  user: process.env.RDS_USER,
  password: process.env.RDS_PASSWORD,
  database: process.env.RDS_DATABASE,
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
});

// Query
const [rows] = await pool.execute('SELECT * FROM users LIMIT 10');

// Transaction
const connection = await pool.getConnection();
await connection.beginTransaction();
try {
  await connection.execute('INSERT INTO users (name) VALUES (?)', ['Alice']);
  await connection.commit();
} catch (e) {
  await connection.rollback();
} finally {
  connection.release();
}
```

## Common Patterns

### Batch Operations (OSS)

```javascript
async function uploadBatch(files) {
  const promises = files.map(file =>
    client.put(file.key, file.content)
  );
  return Promise.all(promises);
}
```

### Conditional Write (OTS)

```javascript
await client.putRow({
  tableName: 'counters',
  primaryKey: [{ key: 'page_views' }],
  attributeColumns: [
    { name: 'count', value: 1, type: 'increment' }
  ],
  condition: 'IGNORE'  // Ignore if exists
});
```

### Retry with Backoff

```javascript
async function withRetry(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(Math.pow(2, i) * 100);
    }
  }
}
```

## Best Practices

1. **Reuse client instance** - Don't re-initialize on every request
2. **Use connection pooling** - For database connections
3. **Handle errors** - Wrap SDK calls in try/catch
4. **Use multipart for large files** - OSS multipart upload
5. **Close clients** - On function exit

## Error Handling

```javascript
try {
  const result = await client.put(fileName, content);
} catch (e) {
  if (e.code === 'RequestTimeTooSkewed') {
    console.error('Clock issue - check system time');
  } else if (e.code === 'SignatureDoesNotMatch') {
    console.error('Credential issue - check access key');
  } else {
    throw e;
  }
}
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `RequestTimeTooSkewed` | Clock out of sync | Sync system time |
| `InvalidAccessKeyId` | Wrong credentials | Verify access key |
| `oss upload timeout` | Large file | Use multipart upload |
| `OTS throttle` | Exceeded throughput | Add delay between requests |

For troubleshooting → `../best-practices/troubleshooting.md`
