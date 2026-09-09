# Aliyun Database Design Best Practices

## Database Selection

### Decision Flow

```
Need to store data?
├── What type of data?
│   ├── Structured, relational → RDS (MySQL/PostgreSQL)
│   ├── Massive scale, time-series → TableStore
│   └── Flexible schema, JSON → TableStore (OTS)
├── What query patterns?
│   ├── Complex joins, aggregations → RDS
│   ├── Simple key-value lookups → TableStore
│   └── Wide-column queries → TableStore
└── What scale?
    ├── < 100k records, complex queries → RDS
    ├── Large scale, simple queries → TableStore
    └── Variable schema, rapid iteration → TableStore
```

## RDS Design Patterns

### Schema Design

#### Rule 1: Normalize for Data Integrity

```sql
-- Good: Proper normalization
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) UNIQUE NOT NULL,
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

-- Order matters! Equality fields first, then sort fields
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
const mysql = require('mysql2/promise');

const pool = mysql.createPool({
  host: process.env.RDS_HOST,
  port: process.env.RDS_PORT || 3306,
  user: process.env.RDS_USER,
  password: process.env.RDS_PASSWORD,
  database: process.env.RDS_DATABASE
});

async function transfer(fromUserId, toUserId, amount) {
  const connection = await pool.getConnection();
  await connection.beginTransaction();

  try {
    await connection.execute(
      'UPDATE accounts SET balance = balance - ? WHERE user_id = ?',
      [amount, fromUserId]
    );

    await connection.execute(
      'UPDATE accounts SET balance = balance + ? WHERE user_id = ?',
      [amount, toUserId]
    );

    await connection.execute(
      'INSERT INTO transactions (from_user, to_user, amount) VALUES (?, ?, ?)',
      [fromUserId, toUserId, amount]
    );

    await connection.commit();

  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}
```

## TableStore Design Patterns

### Data Model

#### Primary Key Design

```javascript
// Primary key structure (required)
// Choose carefully - can't be changed after table creation

// Option 1: User-centric (good for user data access patterns)
primaryKey: [
  { name: 'user_id', type: 'STRING' },
  { name: 'timestamp', type: 'STRING' }  // Sort key
]

// Option 2: Time-series (good for event logs)
primaryKey: [
  { name: 'device_id', type: 'STRING' },
  { name: 'event_time', type: 'STRING' }  // Sort key for time ordering
]

// Option 3: High cardinality (avoid hot partitioning)
primaryKey: [
  { name: 'partition_key', type: 'STRING' },  # e.g., hash of user_id
  { name: 'sort_key', type: 'STRING' }
]
```

### Designing for Query Patterns

```javascript
// Query pattern: Get all events for a user
// Primary key: (user_id, event_time) - Good!
// Query: PK = user_id, SK between time1 and time2

// Query pattern: Get latest events across all users
// Primary key: (device_id, timestamp) - Good!
// Can use Scan with limit and reverse order
```

### Avoid Hot Partitioning

```javascript
// Bad: All writes go to same partition
primaryKey: [
  { name: 'constant_key', type: 'STRING' },  // All data in one partition
  { name: 'timestamp', type: 'STRING' }
]

// Good: Spread writes across partitions
primaryKey: [
  { name: 'user_id_hash', type: 'STRING' },  // Hash user_id for distribution
  { name: 'user_id', type: 'STRING' },
  { name: 'timestamp', type: 'STRING' }
]
```

### Indexing for Non-Primary Key Queries

```javascript
// Create search index for flexible queries
await otsClient.createSearchIndex({
  tableName: 'user_events',
  indexName: 'event_index',
  schema: {
    fieldSchemas: [
      { fieldName: 'event_type', fieldType: 'KEYWORD' },
      { fieldName: 'event_data', fieldType: 'TEXT' },
      { fieldName: 'event_time', fieldType: 'TIMESTAMP' }
    ]
  }
});

// Query using search index
const result = await otsClient.search({
  tableName: 'user_events',
  indexName: 'event_index',
  searchQuery: {
    query: {
      terms: [{ event_type: 'click' }]
    }
  }
});
```

## Cross-Database Patterns

### When to Use Each

| Scenario | Database | Reason |
|----------|----------|--------|
| User profiles | TableStore | Flexible schema, fast writes |
| Orders, transactions | RDS | ACID, complex queries |
| Activity logs | TableStore | High volume, time-series |
| Product catalog | Both | OTS for attributes, RDS for inventory |
| Session data | TableStore | Fast key-value access |

### Example: Hybrid Architecture

```javascript
// User data in TableStore (flexible profile)
const userResult = await otsClient.getRow({
  tableName: 'users',
  primaryKey: [{ user_id: userId }]
});

// Transactions in RDS (ACID integrity)
const [orders] = await pool.execute(
  'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
  [userId]
);

// Analytics in TableStore (high volume write)
await otsClient.putRow({
  tableName: 'analytics',
  primaryKey: [
    { name: 'date', value: '2024-01-01' },
    { name: 'event_id', value: uuid() }
  ],
  attributeColumns: [
    { name: 'user_id', value: userId },
    { name: 'action', value: 'purchase' }
  ]
});
```

## Migration

### RDS Migration

```sql
-- Migration: Add column with default
ALTER TABLE users ADD COLUMN new_column VARCHAR(100) DEFAULT 'default_value';

-- Migration: Add index
CREATE INDEX idx_new_column ON users(new_column);
```

### TableStore Migration

```javascript
// Migration: Add new column (OTS is schema-less, no migration needed)
// Just start writing the new column

// For data backfill:
const stream = await otsClient.getRange({
  tableName: 'users',
  direction: 'FORWARD'
});

for (const row of stream.rows) {
  await otsClient.updateRow({
    tableName: 'users',
    primaryKey: row.primaryKey,
    updateOfAttributeColumns: {
      $SET: { new_field: 'default_value' }
    }
  });
}
```

## Backup and Restore

### RDS Backup

```bash
# Full backup
mysqldump -h ${RDS_HOST} -P ${RDS_PORT} -u ${RDS_USER} -p${RDS_PASSWORD} \
  myapp > backup_$(date +%Y%m%d).sql

# Restore
mysql -h ${RDS_HOST} -P ${RDS_PORT} -u ${RDS_USER} -p${RDS_PASSWORD} \
  myapp < backup_20240101.sql
```

### TableStore Backup

```javascript
// Export to OSS using batchGetRow
const stream = otsClient.getRange({
  tableName: 'users',
  direction: 'FORWARD'
});

const oss = new OSS({ /* ... */ });

for await (const row of stream) {
  await oss.put(`backups/users/${row.primaryKey[0].value}.json`,
    JSON.stringify(row));
}
```

## Performance Checklist

### RDS
- [ ] Indexes for all query patterns
- [ ] Appropriate data types
- [ ] Normalized schema (but not over-normalized)
- [ ] Connection pooling
- [ ] Query using EXPLAIN analyzed

### TableStore
- [ ] Primary key designed for access patterns
- [ ] Hot partition avoided
- [ ] Search index for non-PK queries
- [ ] Batch operations for bulk writes
- [ ] Monitor reserved throughput

## Troubleshooting

For database issues → `../best-practices/troubleshooting.md`
