# Aliyun Authentication & Credentials

## Credential Types

| Type | Security | Use Case |
|------|----------|----------|
| Access Key (AK/SK) | ⚠️ Medium | CLI, SDK, CI/CD |
| RAM Role (STS) | ✅ Recommended | Temporary access, functions |
| Assume Role | ✅✅ Best | CI/CD with least privilege |

## Agent Decision Guide

```
Need to authenticate with Aliyun?
├── From CI/CD pipeline → Environment variables (ALICLOUD_ACCESS_KEY/KEY)
├── From local CLI → aliyun configure (interactive)
├── From function code → Service credentials (automatic injection)
├── From browser/client → STS token (temporary)
└── Never commit credentials to git
```

## Environment Variables

### For CLI and Server-Side

```bash
# Access Key
export ALICLOUD_ACCESS_KEY=your-access-key-id
export ALICLOUD_SECRET_KEY=your-access-key-secret

# Region
export ALICLOUD_REGION=cn-shanghai
```

### For Function Compute

Functions automatically receive credentials via:
- `ALIBABA_CLOUD_ACCESS_KEY_ID` (injected)
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET` (injected)
- `ALIBABA_CLOUD_SECURITY_TOKEN` (for STS)

## Creating Access Keys

### 1. Create via RAM Console

1. Go to [RAM Console](https://ram.console.aliyun.com/)
2. Navigate to: Users → Create User
3. Create AccessKey (or enable console password)
4. Download CSV with AK/SK

### 2. Create RAM Policy

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "fc:InvokeFunction",
        "fc:CreateFunction",
        "oss:GetObject",
        "oss:PutObject"
      ],
      "Resource": "*"
    }
  ]
}
```

## Temporary Credentials (STS)

For short-lived access, use STS tokens:

### Get STS Token

```javascript
const OSS = require('ali-oss');
const STS = require('aliyun-sdk').STS;

const sts = new STS({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY
});

const result = await sts.assumeRole({
  RoleArn: 'acs:ram::123456789:role/DeveloperRole',
  RoleSessionName: 'dev-session'
});
```

### STS Token Response

```json
{
  "Credentials": {
    "AccessKeyId": "STS.xxx",
    "AccessKeySecret": "xxx",
    "SecurityToken": "xxx",
    "Expiration": "2024-01-01T12:00:00Z"
  }
}
```

### Use STS Token

```javascript
const client = new OSS({
  region: process.env.ALICLOUD_REGION,
  accessKeyId: credentials.AccessKeyId,
  accessKeySecret: credentials.AccessKeySecret,
  stsToken: credentials.SecurityToken,
  bucket: 'my-bucket'
});
```

## RAM Role for Functions

### Create RAM Role

1. Go to RAM Console → Roles → Create Role
2. Select "Aliyun Service" trusted entity
3. Attach policies (e.g., AliyunOSSFullAccess)

### Function Use Role

```yaml
service:
  name: my-service
  role: acs:ram::123456789:role/FCServiceRole
```

Function will automatically receive temporary credentials.

## Credential Security Best Practices

### Do's ✅

1. **Use environment variables** - Don't hardcode credentials
2. **Use RAM roles** - Over direct AccessKeys
3. **Use STS for temporary access** - Credentials expire
4. **Rotate regularly** - Change AccessKeys periodically
5. **Use least privilege** - Grant minimum required permissions
6. **Store in secrets manager** - GitHub Secrets, KMS, etc.

### Don'ts ❌

1. **Commit credentials** - Never commit to git
2. **Use root account** - Create dedicated RAM users
3. **Share credentials** - Each user/service should have own key
4. **Use same credentials everywhere** - Separate per environment

## .gitignore for Credentials

```
# Aliyun credentials
.env
.env.*
aliyun-cli-config.json
ossutil-config.ini

# Function compute
.template.yml.bak

# Build outputs
dist/
build/
```

## Function Authentication

### How Functions Receive Credentials

FC functions automatically have credentials injected:

```javascript
module.exports.handler = async (event, context) => {
  // Available automatically in FC functions
  const accessKeyId = process.env.ALIBABA_CLOUD_ACCESS_KEY_ID;
  const accessKeySecret = process.env.ALIBABA_CLOUD_ACCESS_KEY_SECRET;
  const securityToken = process.env.ALIBABA_CLOUD_SECURITY_TOKEN;

  console.log(`Running with credentials for account`);
};
```

### Calling Aliyun Services from Functions

```javascript
const OSS = require('ali-oss');

module.exports.handler = async (event, context) => {
  // Use injected credentials
  const client = new OSS({
    region: process.env.ALICLOUD_REGION,
    accessKeyId: process.env.ALIBABA_CLOUD_ACCESS_KEY_ID,
    accessKeySecret: process.env.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
    stsToken: process.env.ALIBABA_CLOUD_SECURITY_TOKEN,
    bucket: 'my-bucket'
  });

  const result = await client.list();
  return { buckets: result.buckets };
};
```

## Permission Model (RAM)

### Common Policies

| Policy | Description |
|--------|-------------|
| `AliyunFCFullAccess` | Full Function Compute access |
| `AliyunOSSFullAccess` | Full OSS access |
| `AliyunRDSFullAccess` | Full RDS access |
| `AliyunOTSFullAccess` | Full TableStore access |
| `AliyunCDNFullAccess` | Full CDN access |

### Custom Policy Example

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "oss:GetObject",
        "oss:PutObject",
        "oss:DeleteObject"
      ],
      "Resource": "acs:oss:*:*:my-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "fc:InvokeFunction"
      ],
      "Resource": "acs:fc:*:*:services/my-service/functions/*"
    }
  ]
}
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `InvalidAccessKeyId` | Wrong or expired key | Verify AccessKey in RAM console |
| `SignatureDoesNotMatch` | Key mismatch | Check AccessKey Secret |
| `Permission denied` | Insufficient permissions | Attach more RAM policies |
| `Token expired` | STS token too old | Refresh temporary credentials |

For general troubleshooting → `../best-practices/troubleshooting.md`
