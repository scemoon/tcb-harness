# Aliyun Database (RDS + TableStore)

## When to Use Each Database Type

**Use RDS MySQL/PostgreSQL when:**
- Need ACID transactions
- Complex SQL queries with joins
- Fixed, well-defined schema
- Data integrity is critical
- Reporting and analytics
- Traditional web application data

**Use TableStore when:**
- Massive scale (petabyte level)
- Time-series data
- Wide-column storage needs
- High write throughput
- No complex joins needed
- Event logs, sensor data, analytics

## Agent Decision Guide

```
Need to store data?
├── Relational, SQL needed → RDS (MySQL/PostgreSQL)
├── Massive scale, time-series → TableStore
├── Flexible schema, JSON → TableStore (OTS)
└── Both → Use both (RDS for transactions, OTS for logs)
```

## RDS (Relational Database Service)

### Connection

```bash
# Using MySQL client
mysql -h ${RDS_HOST} -P 3306 -u ${RDS_USER} -p${RDS_PASSWORD}

# Using PostgreSQL client
psql -h ${RDS_HOST} -P 5432 -U ${RDS_USER} -d ${RDS_DATABASE}
```

### Schema Design

```sql
-- Users table
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) UNIQUE NOT NULL,
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
const mysql = require('mysql2/promise');

const connection = await mysql.createConnection({
  host: process.env.RDS_HOST,
  port: process.env.RDS_PORT,
  user: process.env.RDS_USER,
  password: process.env.RDS_PASSWORD,
  database: process.env.RDS_DATABASE
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

## TableStore (OTS)

### Data Model

- **Instance** = Database
- **Table** = Collection
- **Row** = Document
- **Column** = Field (dynamic, no fixed schema)

### Table Structure

```javascript
// Primary key structure (required)
const tableSchema = {
  tableName: 'user_events',
  primaryKey: [
    { name: 'user_id', type: 'STRING' },
    { name: 'event_time', type: 'STRING' }  // Sort key
  ],
  // Defined columns (optional - for indexing)
  definedColumns: [
    { name: 'event_type', type: 'STRING' },
    { name: 'event_data', type: 'STRING' }
  ],
  // Reserved throughput
  reservedThroughput: {
    capacityUnit: { read: 1, write: 1 }
  }
};
```

### Query Syntax

```javascript
const { client, Long } = require('aliyun-sdk');

constOTS = new client.OTS({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  endpoint: `https://${process.env.OTS_REGION}.ots.aliyuncs.com`,
  instanceName: process.env.OTS_INSTANCE
});

// Put row
await otsClient.putRow({
  tableName: 'user_events',
  primaryKey: [{ user_id: 'user-123' }, { event_time: '2024-01-01T00:00:00Z' }],
  attributeColumns: [
    { event_type: 'click' },
    { event_data: JSON.stringify({ page: '/home' }) }
  ]
});

// Get row
const result = await otsClient.getRow({
  tableName: 'user_events',
  primaryKey: [{ user_id: 'user-123' }, { event_time: '2024-01-01T00:00:00Z' }]
});

// Query with filter
const queryResult = await otsClient.search({
  tableName: 'user_events',
  indexName: 'event_type_index',
  searchQuery: {
    offset: 0,
    limit: 10,
    query: {
      terms: [{ event_type: 'click' }]
    }
  }
});
```

## CLI Reference (RDS)

| Command | Description |
|---------|-------------|
| `aliyun rds DescribeDBInstances` | List RDS instances |
| `aliyun rds CreateDatabase --DBInstanceId xxx` | Create database |
| `aliyun rds CreateAccount --DBInstanceId xxx` | Create account |
| `mysqldump -h ${HOST} -u ${USER} -p` | Backup database |

## CLI Reference (TableStore)

| Command | Description |
|---------|-------------|
| `ots shell --instance xxx` | Interactive OTS shell |
| `ots listTable --instance xxx` | List tables |
| `ots describeTable --instance xxx --table xxx` | Table schema |

## Limits and Quotas

| Limit | RDS | TableStore |
|-------|-----|------------|
| Storage | 200GB (max) | Unlimited |
| Max connections | 1000 (MySQL) | N/A |
| Max query result | 10000 | 1000 (client pagination) |
| Throughput | Instance size dependent | Pay per request |

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
      │ Relational, │ │ Massive     │ │ Flexible    │
      │    SQL      │ │ scale, time │ │  schema     │
      │             │ │   series    │ │  (JSON)     │
      └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
             │               │               │
             ▼               ▼               ▼
        RDS MySQL      TableStore      TableStore
        (PG also)      (OTS)           (OTS)
```

## Indexing Strategy

### RDS Indexes

```sql
-- Single column
CREATE INDEX idx_email ON users(email);

-- Composite (for WHERE status = ? AND created_at > ?)
CREATE INDEX idx_status_created ON users(status, created_at);

-- Covering index
CREATE INDEX idx_status_created_covering ON users(status, created_at, id, nickname);
```

### TableStore Indexes

```javascript
// Create search index
await otsClient.createSearchIndex({
  tableName: 'user_events',
  indexName: 'event_type_index',
  schema: {
    fieldSchemas: [
      { fieldName: 'event_type', fieldType: 'KEYWORD' },
      { fieldName: 'event_time', fieldType: 'TIMESTAMP' },
      { fieldName: 'event_data', fieldType: 'TEXT' }
    ]
  }
});
```

## Best Practices

### RDS

1. **Normalize for write integrity** - Use proper relations
2. **Index wisely** - Too many indexes slow writes
3. **Use connection pooling** - Don't create new connection per request
4. **Parameterize queries** - Prevent SQL injection
5. **Use transactions** - For operations affecting multiple tables
6. **Enable slow query log** - Monitor and optimize

### TableStore

1. **Design primary key** - Hotspot avoidance (spread writes)
2. **Use search index** - For non-primary key queries
3. **Batch operations** - Use batchWrite for efficiency
4. **Partition by time** - For time-series data
5. **Monitor throughput** - Adjust reserved capacity

## Accessing Databases from Functions

### From Function Compute

```javascript
const mysql = require('mysql2/promise');

module.exports.handler = async (event, context) => {
  // RDS connection
  const connection = await mysql.createConnection({
    host: process.env.RDS_HOST,
    port: process.env.RDS_PORT,
    user: process.env.RDS_USER,
    password: process.env.RDS_PASSWORD,
    database: process.env.RDS_DATABASE
  });

  const [rows] = await connection.execute('SELECT * FROM users LIMIT 10');
  return { users: rows };
};
```

```javascript
// TableStore from FC
const OTS = require('ali-oss');

const otsClient = new OTS({
  region: process.env.ALICLOUD_REGION,
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY,
  bucket: process.env.OTS_INSTANCE
});
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | Wrong host/port | Check RDS/OTS endpoint |
| Access denied | Wrong credentials | Verify RAM permissions |
| Query timeout | Large dataset, no index | Add index, paginate |
| TableStore throttle | Throughput exceeded | Increase reserved capacity |
| SQL syntax error | Invalid SQL | Check MySQL syntax |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
