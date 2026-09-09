# CloudBase Database Design Best Practices

## Database Selection

### Decision Flow

```
Need to store data?
├── What type of data?
│   ├── Structured, relational → MySQL
│   ├── JSON documents, flexible schema → DocDB
│   └── Both → Use both (MySQL for transactions, DocDB for documents)
├── What query patterns?
│   ├── Complex joins, aggregations → MySQL
│   ├── Simple key-value lookups → DocDB
│   └── Document-centric queries → DocDB
└── What scale?
    ├── < 100k documents, simple queries → DocDB
    ├── Large scale, complex queries → MySQL with read replicas
    └── Variable schema, rapid iteration → DocDB
```

## DocDB Design Patterns

### Collection Design

#### Rule 1: Design for Query Patterns

Structure documents based on how you'll query them:

```javascript
// Bad: Normalized (requires join simulation)
{
  _id: "order-123",
  userId: "user-456",
  items: [
    { productId: "prod-1", quantity: 2 }
  ]
}

// User data in separate collection
// Requires multiple queries to get order with user info

// Good: Denormalized (duplicated data for query efficiency)
{
  _id: "order-123",
  userId: "user-456",
  userName: "Alice",  // Denormalized for query convenience
  items: [
    { productId: "prod-1", productName: "Widget", quantity: 2 }
  ],
  createdAt: "2024-01-01T00:00:00Z"
}
```

#### Rule 2: Avoid Deep Nesting

```javascript
// Bad: Too deeply nested
{
  _id: "order-123",
  user: {
    profile: {
      settings: {
        preferences: {
          theme: "dark"
        }
      }
    }
  }
}

// Good: Flat structure
{
  _id: "order-123",
  userId: "user-456",
  userTheme: "dark"
}
```

#### Rule 3: Use Meaningful IDs

```javascript
// Prefer business IDs as _id
{
  _id: "order-2024-00123",  // Human-readable
  // vs
  _id: "64a7f8b2c3d4e5f6"    // Random, not meaningful
}
```

### Indexing Strategy

#### Create Indexes for Common Queries

```javascript
// Query: Find active users by email
db.collection('users').createIndex({
  email: 1,
  status: 1
});

// Query: Find orders by user and date
db.collection('orders').createIndex({
  userId: 1,
  createdAt: -1
});

// Query: Search products by category and price
db.collection('products').createIndex({
  category: 1,
  price: 1
});
```

#### Composite Indexes

Create composite indexes for multi-field queries:

```javascript
// Query: { status: 'active', createdAt: { $gte: date } }
db.collection('users').createIndex({
  status: 1,
  createdAt: -1
});

// Order matters! Equality fields first, then sort fields
// Query: { status: 'active', name: 'Alice' }
// Index: { status: 1, name: 1 }
```

#### Index Limitations

| Metric | Limit |
|--------|-------|
| Max indexes per collection | 10 |
| Max index size | 1024 bytes |
| Index fields | Max 10 |

### Query Patterns

#### Pagination

```javascript
const PAGE_SIZE = 20;
const page = event.page || 1;

// Efficient pagination using skip/limit
const { data } = await db.collection('users')
  .where({ status: 'active' })
  .orderBy('createdAt', 'desc')
  .skip((page - 1) * PAGE_SIZE)
  .limit(PAGE_SIZE)
  .get();

// For large datasets, use cursor-based pagination
const { data } = await db.collection('users')
  .where({
    status: 'active',
    _id: db.command.gt(lastId)  // Cursor from last document
  })
  .limit(PAGE_SIZE)
  .get();
```

#### Aggregation Pipeline

```javascript
// Example: Get order statistics per user
db.collection('orders').aggregate()
  .match({ status: 'completed' })
  .group({
    _id: '$userId',
    totalOrders: $.sum(1),
    totalAmount: $.sum('$amount')
  })
  .sort({ totalAmount: -1 })
  .limit(10)
  .end()
```

### Document Update Patterns

#### Atomic Updates

```javascript
// Good: Atomic update
await db.collection('users').doc(userId).update({
  $inc: { loginCount: 1 },
  $set: { lastLogin: new Date() }
});

// Bad: Read-modify-write (race condition)
const user = await db.collection('users').doc(userId).get();
user.loginCount += 1;
await db.collection('users').doc(userId).set(user);
```

#### Conditional Updates

```javascript
// Update only if version matches (optimistic locking)
await db.collection('users').doc(userId).update({
  $set: { name: 'New Name' },
  version: db.command.inc(1)
}, {
  // Only update if version is still 1
  // This requires a where clause
  where: { version: 1 }
});
```

## MySQL Design Patterns

### Schema Design

#### Rule 1: Normalize for Data Integrity

```sql
-- Good: Proper normalization
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  openid VARCHAR(64) UNIQUE NOT NULL,
  nickname VARCHAR(128),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  order_no VARCHAR(64) UNIQUE NOT NULL,
  user_id BIGINT NOT NULL,
  amount DECIMAL(10, 2) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

#### Rule 2: Use Appropriate Data Types

```sql
-- Good: Appropriate types
CREATE TABLE products (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  price DECIMAL(10, 2) NOT NULL,
  stock INT UNSIGNED DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bad: Overly large types
CREATE TABLE products (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(10000),  -- Way too large
  price VARCHAR(100),   -- Should be DECIMAL
  stock VARCHAR(100),   -- Should be INT
);
```

### Indexing Strategy

#### Single Column Index

```sql
-- For queries: WHERE email = 'x'
CREATE INDEX idx_email ON users(email);

-- For queries: WHERE status = 'active'
CREATE INDEX idx_status ON users(status);
```

#### Composite Index

```sql
-- For queries: WHERE status = 'active' ORDER BY created_at DESC
CREATE INDEX idx_status_created ON users(status, created_at DESC);

-- For queries: WHERE user_id = ? AND created_at > ?
CREATE INDEX idx_user_created ON orders(user_id, created_at);
```

#### Covering Index

```sql
-- For queries that only need id, name, email (no lookup)
CREATE INDEX idx_user_covering ON users(status, created_at, id, nickname, email);
```

### Query Optimization

#### Avoid SELECT *

```sql
-- Bad
SELECT * FROM users WHERE id = 1;

-- Good
SELECT id, nickname, email FROM users WHERE id = 1;
```

#### Use EXPLAIN

```sql
EXPLAIN SELECT * FROM orders WHERE user_id = 1;
```

### Transaction Patterns

```javascript
const connection = await mysql.createConnection({
  host: process.env.MYSQL_HOST,
  port: process.env.MYSQL_PORT,
  user: process.env.MYSQL_USER,
  password: process.env.MYSQL_PASSWORD,
  database: process.env.MYSQL_DATABASE
});

await connection.beginTransaction();

try {
  // Deduct from sender
  await connection.execute(
    'UPDATE accounts SET balance = balance - ? WHERE id = ?',
    [amount, fromAccountId]
  );

  // Add to receiver
  await connection.execute(
    'UPDATE accounts SET balance = balance + ? WHERE id = ?',
    [amount, toAccountId]
  );

  // Record transaction
  await connection.execute(
    'INSERT INTO transactions (from, to, amount) VALUES (?, ?, ?)',
    [fromAccountId, toAccountId, amount]
  );

  await connection.commit();

} catch (error) {
  await connection.rollback();
  throw error;
} finally {
  await connection.end();
}
```

## Cross-Database Patterns

### When to Use Each

| Scenario | Database | Reason |
|----------|----------|--------|
| User profiles | DocDB | Flexible schema, simple queries |
| Orders, transactions | MySQL | ACID, complex queries |
| Activity logs | DocDB | High volume, simple writes |
| Product catalog | Both | DocDB for flexible attributes, MySQL for inventory |
| Session data | DocDB | Fast key-value access |

### Example: Hybrid Architecture

```javascript
// User data in DocDB (flexible profile)
const user = await db.collection('users').doc(userId).get();

// Transactions in MySQL (ACID integrity)
const orders = await mysqlQuery(
  'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
  [userId]
);

// Real-time analytics in DocDB (write-heavy)
await db.collection('analytics').add({
  userId,
  action: 'purchase',
  timestamp: new Date()
});
```

## Data Migration

### DocDB Migration

```javascript
// Migration: Add new field with default
async function migrateAddField() {
  const users = await db.collection('users').get();

  for (const user of users.data) {
    await db.collection('users').doc(user._id).update({
      $set: { newField: 'default_value' }
    });
  }
}
```

### MySQL Migration

```sql
-- Migration: Add column with default
ALTER TABLE users ADD COLUMN new_column VARCHAR(100) DEFAULT 'default_value';

-- Migration: Add index
CREATE INDEX idx_new_column ON users(new_column);

-- Migration: Rename column
ALTER TABLE users CHANGE COLUMN old_name new_name VARCHAR(200);
```

## Backup and Restore

### DocDB Export/Import

```bash
# Export
tcb db export --collection users --file ./backup/users.json --env $TCB_ENV_ID

# Import (append)
tcb db import --collection users --file ./backup/users.json --env $TCB_ENV_ID

# Note: Import doesn't replace, it appends
```

### MySQL Backup

```bash
# Via CLI (if MySQL client available)
mysqldump -h ${MYSQL_HOST} -P ${MYSQL_PORT} -u ${MYSQL_USER} -p${MYSQL_PASSWORD} database > backup.sql

# Restore
mysql -h ${MYSQL_HOST} -P ${MYSQL_PORT} -u ${MYSQL_USER} -p${MYSQL_PASSWORD} database < backup.sql
```

## Performance Checklist

### DocDB
- [ ] Indexes for all query patterns
- [ ] Pagination on large result sets
- [ ] Batch operations for bulk updates
- [ ] Limit projection (don't SELECT *)
- [ ] Use cursor-based pagination for large datasets

### MySQL
- [ ] Indexes for WHERE, ORDER BY columns
- [ ] Appropriate data types
- [ ] Normalized schema (but not over-normalized)
- [ ] Query using EXPLAIN analyzed
- [ ] Connection pooling in application

## Troubleshooting

For database issues → `../best-practices/troubleshooting.md`
