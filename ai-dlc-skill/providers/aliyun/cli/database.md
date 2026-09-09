# Aliyun CLI: Database (RDS & TableStore)

## When to Use Database Commands

| Goal | Command | Notes |
|------|---------|-------|
| List RDS instances | `aliyun rds DescribeDBInstances` | Check instances |
| Create RDS database | `aliyun rds CreateDatabase` | Initialize DB |
| Create RDS account | `aliyun rds CreateAccount` | Set credentials |
| Connect to MySQL | `mysql` client | Direct SQL access |
| TableStore operations | `ots` CLI or SDK | NoSQL operations |

## Decision Tree for Database Operations

```
Need to work with database?
├── RDS MySQL/PostgreSQL
│   ├── List instances → aliyun rds DescribeDBInstances
│   ├── Create database → aliyun rds CreateDatabase
│   ├── Create account → aliyun rds CreateAccount
│   ├── Run SQL → mysql/psql client
│   └── Backup → mysqldump/pg_dump
├── TableStore (OTS)
│   ├── List instances → aliyunots ListInstance
│   ├── List tables → ots listtable
│   ├── Query data → SDK (no CLI for queries)
│   └── Manage table → ots CLI
└── Schema changes → Migration files + CLI
```

## RDS MySQL Operations

### List RDS Instances

```bash
aliyun rds DescribeDBInstances --region cn-shanghai
```

Output:
```json
{
  "Items": {
    "DBInstance": [
      {
        "DBInstanceId": "rm-xxxxx",
        "DBInstanceDescription": "MySQL Production",
        "DBInstanceStatus": "Running",
        "Engine": "MySQL",
        "EngineVersion": "8.0",
        "RegionId": "cn-shanghai"
      }
    ]
  }
}
```

### Create Database

```bash
aliyun rds CreateDatabase \
  --DBInstanceId rm-xxxxx \
  --DBName myapp \
  --CharacterSetName utf8mb4
```

### Create Account

```bash
aliyun rds CreateAccount \
  --DBInstanceId rm-xxxxx \
  --AccountName appuser \
  --AccountPassword 'StrongPass123!' \
  --AccountType Normal
```

### Grant Privileges

```bash
aliyun rds GrantAccountPrivileges \
  --DBInstanceId rm-xxxxx \
  --AccountName appuser \
  --DBName myapp \
  --AccountPrivilege Select,Insert,Update,Delete
```

### Connect to MySQL

```bash
mysql -h rm-xxxxx.mysql.rds.aliyuncs.com \
  -P 3306 \
  -u appuser \
  -p
```

### Backup Database

```bash
mysqldump -h rm-xxxxx.mysql.rds.aliyuncs.com \
  -P 3306 \
  -u appuser \
  -p'mypassword' \
  myapp > backup.sql
```

### Restore Database

```bash
mysql -h rm-xxxxx.mysql.rds.aliyuncs.com \
  -P 3306 \
  -u appuser \
  -p'mypassword' \
  myapp < backup.sql
```

## RDS PostgreSQL Operations

### Connect to PostgreSQL

```bash
psql -h rm-xxxxx.pg.rds.aliyuncs.com \
  -p 5432 \
  -U appuser \
  -d myapp
```

### Backup PostgreSQL

```bash
pg_dump -h rm-xxxxx.pg.rds.aliyuncs.com \
  -p 5432 \
  -U appuser \
  -d myapp > backup.sql
```

## TableStore Operations

### Install OTS CLI

```bash
pip install ots2
```

### List Instances

```bash
aliyun ots ListInstance --region cn-shanghai
```

### Create Instance

```bash
aliyun ots CreateInstance \
  --InstanceName my-ots-instance \
  --Description "My OTS Instance" \
  --Region cn-shanghai
```

### List Tables

```bash
ots listtable --instance_name my-ots-instance
```

### Describe Table

```bash
ots describeTable \
  --instance_name my-ots-instance \
  --table_name users
```

### Create Table

```bash
ots createTable \
  --instance_name my-ots-instance \
  --table_meta '{
    "tableName": "users",
    "primaryKey": [
      {"name": "user_id", "type": "STRING"}
    ]
  }'
```

### Update Table Throughput

```bash
ots updateTable \
  --instance_name my-ots-instance \
  --table_name users \
  --reserved_throughput '{
    "capacity_unit": {"read": 10, "write": 10}
  }'
```

## Database Connection from Functions

### From Function Compute (Node.js)

```javascript
const mysql = require('mysql2/promise');

module.exports.handler = async (event, context) => {
  const connection = await mysql.createConnection({
    host: process.env.RDS_HOST,
    port: process.env.RDS_PORT || 3306,
    user: process.env.RDS_USER,
    password: process.env.RDS_PASSWORD,
    database: process.env.RDS_DATABASE
  });

  const [rows] = await connection.execute('SELECT * FROM users LIMIT 10');
  await connection.end();

  return { users: rows };
};
```

### From Function Compute (Python)

```python
import pymysql
import os

def handler(event, context):
    connection = pymysql.connect(
        host=os.environ['RDS_HOST'],
        port=int(os.environ.get('RDS_PORT', 3306)),
        user=os.environ['RDS_USER'],
        password=os.environ['RDS_PASSWORD'],
        database=os.environ['RDS_DATABASE']
    )

    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM users LIMIT 10')
        rows = cursor.fetchall()

    connection.close()
    return {'users': rows}
```

### From SAE (Java Spring Boot)

```properties
# application.properties
spring.datasource.url=jdbc:mysql://${RDS_HOST}:${RDS_PORT}/${RDS_DATABASE}
spring.datasource.username=${RDS_USER}
spring.datasource.password=${RDS_PASSWORD}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Wrong host/port | Check RDS endpoint |
| `Access denied` | Wrong credentials | Verify username/password |
| `Unknown database` | Database doesn't exist | Create database first |
| `Table not found` | Migration not run | Run migrations |
| `OTS throttle` | Throughput exceeded | Increase reserved capacity |
| `OTS timeout` | Network or table issue | Check instance status |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
