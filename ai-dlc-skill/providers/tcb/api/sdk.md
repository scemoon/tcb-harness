# TCB SDK Reference

## SDK Options

| SDK | Language | Use Case |
|-----|----------|----------|
| `@cloudbase/node-sdk` | Node.js | Server-side (functions, backend) |
| `@cloudbase/js-sdk` | Browser | Client-side web apps |
| `@cloudbase/app` | Mini-program | WXA, MYA, TTA |

## @cloudbase/node-sdk

### Installation

```bash
npm install @cloudbase/node-sdk
```

### Initialization

```javascript
const tcb = require('@cloudbase/node-sdk');

const app = tcb.init({
  env: process.env.TCB_ENV_ID,  // Or 'env-xxxxx'
  credentials: {
    secretId: process.env.TENCENTCLOUD_SECRETID,
    secretKey: process.env.TENCENTCLOUD_SECRETKEY
  }
});
```

### Database (DocDB)

```javascript
const db = app.database();

// Query
const { data } = await db.collection('users')
  .where({ status: 'active' })
  .limit(20)
  .get();

// Insert
const res = await db.collection('users').add({
  name: 'Alice',
  email: 'alice@example.com'
});

// Update
await db.collection('users').doc('doc-id').update({
  name: 'Alice Updated'
});

// Delete
await db.collection('users').doc('doc-id').remove();

// Aggregation
const { data } = await db.collection('orders')
  .aggregate()
  .match({ status: 'completed' })
  .group({ _id: '$productId', total: $.sum('$amount') })
  .end();
```

### Functions

```javascript
// Call another function
const res = await app.callFunction({
  name: 'my-function',
  data: { key: 'value' }
});

// Upload file
const uploadResult = await app.uploadFile({
  cloudPath: '/uploads/avatar.jpg',
  fileContent: buffer
});

// Get temporary file URL
const url = await app.getTempFileURL({
  filePath: '/uploads/private.pdf'
});
```

### Storage Upload/Download

```javascript
// Upload
const uploadResult = await app.uploadFile({
  cloudPath: '/uploads/avatar.jpg',
  fileContent: fs.createReadStream('./avatar.jpg')
});

// Download (get URL)
const url = await app.getTempFileURL({
  filePath: '/uploads/avatar.jpg',
  maxAge: 3600  // 1 hour
});
```

## @cloudbase/js-sdk (Browser)

### Installation

```bash
npm install @cloudbase/js-sdk
```

### Initialization

```javascript
import tcb from "@cloudbase/js-sdk";

const app = tcb.init({
  env: 'env-xxxxx'
});
```

### Anonymous Login

```javascript
// Login anonymously
await app.auth().anonymousAuthProvider().signIn();

// Or with popup
await app.auth().signInWithPopup();
```

### Database

```javascript
const db = app.database();

// Query
const { data } = await db.collection('products')
  .where({ featured: true })
  .limit(10)
  .get();
```

### File Upload

```javascript
// Select file from input
const file = document.querySelector('#file-input').files[0];

// Upload to Cloud Storage
const result = await app.uploadFile({
  cloudPath: `avatars/${Date.now()}_${file.name}`,
  filePath: file
});

// Get URL
const url = await app.getTempFileURL({
  filePath: result.fileID
});
```

## Mini-Program SDK (@cloudbase/app)

### WXA (WeChat Mini-Program)

```javascript
// In mini-program
const tcb = require('@cloudbase/wx-server-sdk');

const app = tcb.init({
  env: 'env-xxxxx'
});

const db = app.database();

// Get openid from event
exports.main = async (event, context) => {
  const { OPENID } = event.userInfo;

  // Query user data
  const { data } = await db.collection('users')
    .where({ _openid: OPENID })
    .get();

  return { user: data[0] };
};
```

## Common Patterns

### Transaction (DocDB)

```javascript
const db = app.database();

try {
  await db.startTransaction();

  await db.collection('accounts').doc(fromId).update({
    balance: db.command.inc(-amount)
  });

  await db.collection('accounts').doc(toId).update({
    balance: db.command.inc(amount)
  });

  await db.commitTransaction();
} catch (e) {
  await db.rollbackTransaction();
  throw e;
}
```

### Batch Operations

```javascript
// Batch insert
const users = [
  { name: 'Alice', email: 'alice@example.com' },
  { name: 'Bob', email: 'bob@example.com' }
];

const res = await db.collection('users').add(users.map(u => ({
  data: u
})));
```

### Operator Reference

```javascript
// Comparison
db.command.eq(value)           // ==
db.command.neq(value)          // !=
db.command.gt(value)           // >
db.command.gte(value)          // >=
db.command.lt(value)           // <
db.command.lte(value)          // <=
db.command.in(values)          // IN
db.command.nin(values)         // NOT IN

// Logical
db.command.and([cond1, cond2]) // AND
db.command.or([cond1, cond2])  // OR
db.command.not(cond)           // NOT

// Update
db.command.set(value)          // SET
db.command.inc(value)          // INCREMENT
db.command.push(values)        // PUSH to array
db.command.pull(values)        // PULL from array
db.command.rename(name)        // RENAME field
db.command.remove()            // REMOVE field
```

## Best Practices

1. **Reuse app instance** - Don't re-initialize on every request
2. **Use transactions** - For multi-document updates
3. **Index wisely** - Create indexes for frequently queried fields
4. **Handle errors** - Wrap SDK calls in try/catch
5. **Use projection** - Only fetch needed fields
6. **Paginate** - Don't fetch large result sets at once

## Error Handling

```javascript
try {
  const { data } = await db.collection('users').get();
} catch (e) {
  if (e.code === 'DATABASE_PERMISSION_DENIED') {
    console.error('No permission to access database');
  } else if (e.code === 'DATABASE_REQUEST_LIMIT') {
    console.error('Request limit exceeded');
  } else {
    throw e;
  }
}
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `auth not available` | Not logged in | Call `app.auth().signIn()` first |
| `database permission denied` | No permission | Check collection rules |
| `upload file too large` | > 5MB via SDK | Use server-side upload flow |
| `function not found` | Wrong name | Check function name in `cloudbaserc.json` |

For troubleshooting → `../best-practices/troubleshooting.md`
