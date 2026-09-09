# TCB CLI: Database Management

## When to Use Database Commands

| Goal | Command | Notes |
|------|---------|-------|
| List collections | `tcb db list` | DocDB only |
| Query documents | `tcb db query` | DocDB (Mongoose-like syntax) |
| Run migrations | `tcb db migrate` | SQL migrations (MySQL) |
| Import data | `tcb db import` | JSON import to DocDB |
| Export data | `tcb db export` | DocDB to JSON |

## Decision Tree for Database Operations

```
Need to work with database?
├── DocDB (NoSQL)
│   ├── List collections → tcb db list
│   ├── Query data → tcb db query
│   ├── Import/Export → tcb db import/export
│   └── Complex operations → Use SDK or REST API
├── MySQL (RDBMS)
│   ├── Run migrations → tcb db migrate
│   ├── Admin queries → tcb db query (use carefully)
│   └── Application queries → MySQL client in functions
└── Schema changes → Migration files (see ci-cd.md)
```

## DocDB Operations

### List Collections

```bash
tcb db list --env $TCB_ENV_ID
```

Output:
```
┌─────────────────┬────────────┬──────────────────┐
│ Collection      │ Documents  │ Indexes          │
├─────────────────┼────────────┼──────────────────┤
│ users           │ 1,234      │ 2                │
│ orders          │ 5,678      │ 3                │
│ products        │ 890        │ 1                │
└─────────────────┴────────────┴──────────────────┘
```

### Query Documents

```bash
tcb db query "SELECT * FROM users WHERE status = 'active'" --env $TCB_ENV_ID
```

#### Query Syntax Reference

| SQL-like | Description |
|----------|-------------|
| `SELECT * FROM collection` | Get all documents |
| `WHERE field = 'value'` | Equality filter |
| `WHERE field > 10` | Comparison |
| `WHERE field IN ('a','b')` | In list |
| `WHERE field LIKE '%pattern%'` | Regex ( DocDB uses `LIKE` with regex) |
| `ORDER BY field ASC/DESC` | Sort |
| `LIMIT n SKIP m` | Pagination |
| `SELECT field1, field2` | Project specific fields |

#### Query Examples

```bash
# Simple query
tcb db query "SELECT * FROM users" --env $TCB_ENV_ID

# With filter
tcb db query "SELECT * FROM users WHERE status = 'active'" --env $TCB_ENV_ID

# With comparison
tcb db query "SELECT * FROM orders WHERE amount > 100" --env $TCB_ENV_ID

# With pagination
tcb db query "SELECT * FROM users LIMIT 20 SKIP 40" --env $TCB_ENV_ID

# Ordered
tcb db query "SELECT * FROM users ORDER BY createdAt DESC" --env $TCB_ENV_ID
```

### Import Data

```bash
tcb db import --collection users --file ./users.json --env $TCB_ENV_ID
```

Format: JSON array of documents

```json
[
  { "name": "Alice", "email": "alice@example.com" },
  { "name": "Bob", "email": "bob@example.com" }
]
```

### Export Data

```bash
tcb db export --collection users --file ./backup.json --env $TCB_ENV_ID
```

## MySQL Operations

### Run Migrations

```bash
tcb db migrate --env $TCB_ENV_ID
```

Migrations run SQL files in `migrations/` directory.

### Migration File Structure

```
migrations/
├── 001_create_users.sql
├── 002_add_index.sql
└── 003_alter_orders.sql
```

### Migration File Example

```sql
-- migrations/001_create_users.sql

-- UP migration
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  openid VARCHAR(64) UNIQUE NOT NULL,
  nickname VARCHAR(128),
  status TINYINT DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DOWN migration (for rollback)
-- DROP TABLE users;
```

### Run Specific Migration

```bash
tcb db migrate --up --name 001_create_users --env $TCB_ENV_ID
```

### Rollback Last Migration

```bash
tcb db migrate --down --env $TCB_ENV_ID
```

### Check Migration Status

```bash
tcb db migrate --status --env $TCB_ENV_ID
```

Output:
```
┌──────┬────────────────────────────────┬──────────┐
│ File │ Name                           │ Status   │
├──────┼────────────────────────────────┼──────────┤
│ 001  │ create_users                   │ applied  │
│ 002  │ add_index                      │ applied  │
│ 003  │ alter_orders                   │ pending  │
└──────┴────────────────────────────────┴──────────┘
```

## Agent Workflows

### Workflow: Query DocDB from Agent

```bash
# List available collections first
tcb db list --env $TCB_ENV_ID

# Query specific collection
tcb db query "SELECT * FROM users WHERE status = 'active'" --env $TCB_ENV_ID
```

For complex queries, use SDK in a function:

```bash
# Create debug function
tcb fn invoke --name db-debug --params '{"query": "SELECT * FROM users"}' --env $TCB_ENV_ID
```

### Workflow: Data Migration

```bash
# 1. Create migration file
cat > migrations/004_add_email_index.sql << 'EOF'
CREATE INDEX idx_email ON users(email);
EOF

# 2. Run migration
tcb db migrate --env staging

# 3. Verify
tcb db query "SELECT * FROM __migrations" --env staging

# 4. Deploy to production (via deploy_stack)
deploy_stack --env production --provider tcb
```

### Workflow: Backup and Restore

```bash
# Backup
tcb db export --collection users --file ./backup/users_$(date +%Y%m%d).json --env $TCB_ENV_ID

# Restore (careful!)
tcb db import --collection users --file ./backup/users_latest.json --env $TCB_ENV_ID
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Collection not found` | Wrong name | `tcb db list` to see collections |
| `Query syntax error` | Invalid query syntax | Check DocDB query syntax |
| `Import failed` | Invalid JSON format | Verify JSON array format |
| `Migration failed` | SQL error | Check migration file syntax |
| `Permission denied` | No write access | Check environment permissions |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
