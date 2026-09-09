# CloudBase Database

## When to Use Each Database Type

**Use DocDB (NoSQL) when:**
- Schema is flexible or evolving rapidly
- JSON-like data structure (nested objects, arrays)
- No complex joins needed
- High write throughput required
- Data model is document-centric

**Use MySQL (RDBMS) when:**
- Need ACID transactions
- Complex SQL queries with joins
- Fixed, well-defined schema
- Data integrity is critical
- Reporting and analytics

**Do NOT use TCB Database when:**
- Need GraphDB or specialized databases → Use Tencent Cloud directly

## Agent Decision Guide

```
Need to store data?
├── Flexible JSON documents, no joins → DocDB (NoSQL)
├── Relational data, SQL needed → MySQL
└── Both needed → Use DocDB for most data, MySQL for transactions
```

## DocDB (NoSQL Document Database)

### Data Model

- **Collection** = Table (analogous)
- **Document** = Row (JSON object)
- **Field** = Column
- No fixed schema - documents in same collection can have different fields

### Document Example

```json
{
  "_id": "unique-document-id",
  "name": "John Doe",
  "email": "john@example.com",
  "profile": {
    "age": 30,
    "city": "Shanghai"
  },
  "tags": ["developer", "cloud"],
  "createdAt": "2024-01-01T00:00:00Z"
}
```

### Query Syntax (Mongoose-like)

```javascript
// Equal query
db.collection('users').where({ status: 'active' }).get()

// Comparison operators
db.collection('users').where({
  age: db.command.gte(18),
  status: 'active'
}).get()

// Or query
db.collection('users').where(
  db.command.or([
    { status: 'active' },
    { vip: true }
  ])
).get()

// Regex search
db.collection('users').where({
  name: db.RegExp({ pattern: '^John' })
}).get()

// Pagination
db.collection('users').skip(10).limit(20).get()

// Ordering
db.collection('users').orderBy('createdAt', 'desc').get()
```

### Aggregation

```javascript
db.collection('orders').aggregate()
  .match({ status: 'completed' })
  .group({ _id: '$productId', total: $.sum('$amount') })
  .sort({ total: -1 })
  .limit(10)
  .end()
```

## MySQL (Relational Database)

### Connection

```bash
# Via CLI (for migrations and admin)
tcb db migrate --env $TCB_ENV_ID

# Or use standard MySQL client
mysql -h ${MYSQL_HOST} -P ${MYSQL_PORT} -u ${MYSQL_USER} -p${MYSQL_PASSWORD}
```

### Schema Design

```sql
-- Users table
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  openid VARCHAR(64) UNIQUE NOT NULL,
  nickname VARCHAR(128),
  avatar_url VARCHAR(512),
  status TINYINT DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status (status),
  INDEX idx_created (created_at)
);

-- Orders table
CREATE TABLE orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  order_no VARCHAR(64) UNIQUE NOT NULL,
  user_id BIGINT NOT NULL,
  amount DECIMAL(10, 2) NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX idx_user (user_id),
  INDEX idx_order_no (order_no)
);
```

### Transaction Support

```javascript
// Use MySQL for transactions
const connection = await mysql.createConnection({
  host: process.env.MYSQL_HOST,
  port: process.env.MYSQL_PORT,
  user: process.env.MYSQL_USER,
  password: process.env.MYSQL_PASSWORD,
  database: process.env.MYSQL_DATABASE
});

await connection.beginTransaction();
try {
  await connection.execute(
    'INSERT INTO orders (order_no, user_id, amount) VALUES (?, ?, ?)',
    [orderNo, userId, amount]
  );
  await connection.execute(
    'UPDATE users SET status = ? WHERE id = ?',
    ['active', userId]
  );
  await connection.commit();
} catch (error) {
  await connection.rollback();
  throw error;
}
```

## CLI Reference (DocDB)

| Command | Description |
|---------|-------------|
| `tcb db list --env <envId>` | List collections |
| `tcb db query "<sql-like>" --env <envId>` | Query documents |
| `tcb db migrate --env <envId>` | Run migrations |
| `tcb db import --collection <name> --file <path> --env <envId>` | Import JSON |
| `tcb db export --collection <name> --file <path> --env <envId>` | Export to JSON |

## CLI Reference (MySQL)

| Command | Description |
|---------|-------------|
| `tcb db migrate` | Run SQL migrations |
| `tcb db query "<sql>"` | Execute SQL query (admin only) |

## Limits and Quotas

| Limit | DocDB | MySQL |
|-------|-------|-------|
| Storage per env | 2GB | 20GB |
| Max collections | 100 | N/A |
| Max document size | 16MB | N/A |
| Max fields per document | 500 | N/A |
| Concurrent connections | 1000 | 100 |
| Max query result | 1000 (client-side pagination needed) | 10000 |

## Database Selection Flow

```
                    ┌─────────────────┐
                    │ Need to store   │
                    │     data?       │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
      │ Flexible    │ │ Relational, │ │ Need full   │
      │ JSON docs   │ │    SQL      │ │   ACID?     │
      └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
             │               │               │
             ▼               ▼               ▼
        DocDB (NoSQL)   MySQL (RDBMS)    MySQL (RDBMS)
```

## Indexing Strategy

### DocDB Indexes

```javascript
// Create index
db.collection('users').createIndex({
  'email': 1,
  'status': 1,
  'createdAt': -1
}, { background: true });

// Composite index for common queries
// Query: { status: 'active', createdAt: { $gte: date } }
// Index: { status: 1, createdAt: -1 }
```

### MySQL Indexes

```sql
-- Single column
CREATE INDEX idx_email ON users(email);

-- Composite (for WHERE status = ? AND created_at > ?)
CREATE INDEX idx_status_created ON users(status, created_at);

-- Covering index (includes all columns needed)
CREATE INDEX idx_status_created_covering ON users(status, created_at, id, nickname);
```

## Best Practices

### DocDB

1. **Denormalize for read performance** - Embed related data, don't join
2. **Design for query patterns** - Create indexes matching your queries
3. **Use pagination** - Always use `skip()` and `limit()` for large datasets
4. **Implement soft delete** - Don't hard delete, use `status` field
5. **Use meaningful `_id`** - Consider using business IDs as `_id`

### MySQL

1. **Normalize for write integrity** - Use proper relations
2. **Index wisely** - Too many indexes slow writes
3. **Use connection pooling** - Don't create new connection per request
4. **Parameterize queries** - Prevent SQL injection
5. **Use transactions** - For operations affecting multiple tables

## Accessing Databases from Functions

```javascript
const tcb = require('@cloudbase/node-sdk');
const app = tcb.init({
  env: process.env.TCB_ENV_ID,
  credentials: {
    secretId: process.env.TENCENTCLOUD_SECRETID,
    secretKey: process.env.TENCENTCLOUD_SECRETKEY
  }
});

// DocDB
const db = app.database();
const { data } = await db.collection('users').where({ status: 'active' }).get();

// MySQL (via http function calling backend)
const res = await app.callFunction({
  name: 'mysql-query',
  data: { sql: 'SELECT * FROM users' }
});
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Query timeout | Large dataset, no index | Add index, use pagination |
| Connection refused | Wrong credentials | Verify TCB_SECRET_ID/KEY |
| Document too large | > 16MB | Split into smaller docs, use COS for file storage |
| Write quota exceeded | Environment limits | Clean up old data or upgrade environment |
| SQL syntax error | Invalid SQL | Check MySQL syntax (TCB MySQL is standard MySQL) |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
