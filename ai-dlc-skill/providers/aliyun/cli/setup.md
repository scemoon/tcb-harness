# Aliyun CLI Setup & Authentication

## When to Use CLI vs SDK vs REST API

**Use CLI when:**
- Deploying functions from CI/CD
- Running one-off administrative tasks
- Scripting cloud operations
- Initial setup and configuration

**Use SDK when:**
- Building applications that interact with Aliyun
- Need programmatic access from within functions
- Complex business logic involving Aliyun services

**Use REST API when:**
- CLI/SDK doesn't support specific operation
- Building custom integrations

## Installation

### Prerequisites

- Node.js 14.x or later
- Python 3.x (for fun CLI)

### Install fun CLI (Function Compute)

```bash
npm install @alicloud/fun -g
```

Verify installation:

```bash
fun --version
```

### Install ossutil (OSS)

```bash
# Download ossutil
curl -o ossutil https://gosspublic.alicdn.com/ossutil/1.7.9/ossutil64
chmod +x ossutil
sudo mv ossutil /usr/local/bin/

# Configure
ossutil config
# Follow prompts to enter AccessKey and region
```

### Install aliyun CLI (General)

```bash
pip install aliyun-cli
# or
npm install @alicloud/alicloud-cli -g
```

### Install serverless devs

```bash
npm install @serverless-devs/s -g
```

## Authentication Methods

### Method 1: Access Key (Recommended for CLI)

```bash
# Configure aliyun CLI
aliyun configure

# Or set environment variables
export ALICLOUD_ACCESS_KEY=your-access-key-id
export ALICLOUD_SECRET_KEY=your-access-key-secret
export ALICLOUD_REGION=cn-shanghai
```

### Method 2: RAM Role (Recommended for CI/CD)

Create RAM role with appropriate permissions, then assume role:

```bash
aliyun ram AssumeRole \
  --RoleArn acs:ram::xxx:role/AliyunFunctionComputeRole \
  --RoleSessionName ci-session
```

### Method 3: STS Token (For temporary access)

```javascript
const OSS = require('ali-oss');
const STS = require('aliyun-sdk').STS;

const sts = new STS({
  accessKeyId: process.env.ALICLOUD_ACCESS_KEY,
  accessKeySecret: process.env.ALICLOUD_SECRET_KEY
});

const result = await sts.assumeRole({
  RoleArn: 'acs:ram::xxx:role/upload-role',
  RoleSessionName: 'upload-session'
});
```

## Credential Selection Decision Tree

```
Need to run Aliyun commands?
├── Local development
│   └── aliyun configure (interactive)
├── CI/CD pipeline
│   ├── Use environment variables (ALICLOUD_ACCESS_KEY/KEY)
│   └── Use RAM role for better security
├── From within FC function
│   └── Use service credentials (automatic injection)
└── Never commit credentials to git
```

## Verifying Authentication

### Check Login Status

```bash
# aliyun CLI
aliyun ecs DescribeInstances --region cn-shanghai

# fun CLI
fun --access-key-id $ALICLOUD_ACCESS_KEY --access-key-secret $ALICLOUD_SECRET_KEY
```

### Check OSS

```bash
ossutil ls oss://
```

## Environment Variables Reference

| Variable | Description | Source |
|----------|-------------|--------|
| `ALICLOUD_ACCESS_KEY` | Aliyun access key ID | Manual or `aliyun configure` |
| `ALICLOUD_SECRET_KEY` | Aliyun access key secret | Manual or `aliyun configure` |
| `ALICLOUD_REGION` | Default region | Manual or `aliyun configure` |
| `FUNC_ACCESS_KEY_ID` | FC-specific credential | For FC function calls |
| `FUNC_ACCESS_KEY_SECRET` | FC-specific credential | For FC function calls |

## Project-Level Configuration

### fun CLI (template.yml)

No separate config file needed - credentials passed via env vars or CLI flags.

### ossutil

```bash
# Configure with custom endpoint
ossutil config
# Enter:
# - Access Key ID
# - Access Key Secret
# - Default region (cn-shanghai)
# - Output format (json)
```

### serverless devs (s.yaml)

```yaml
edition: 1.0.0
services:
  my-app:
    component: fc
    props:
      region: ${ALICLOUD_REGION}
      access: default  # uses default credentials
```

## CLI Configuration

### Set Default Region

```bash
export ALICLOUD_REGION=cn-shanghai
```

### Set Output Format

```bash
aliyun configure set --output json
```

### View Current Config

```bash
cat ~/.aliyun/config.json
```

## Security Best Practices

1. **Never commit credentials** - Add to `.gitignore`
2. **Use environment variables in CI/CD** - Don't hardcode secrets
3. **Use RAM roles** - Instead of root credentials
4. **Use least privilege** - Create dedicated RAM policies
5. **Rotate credentials regularly** - Access keys can be rotated

### .gitignore Example

```
# Aliyun credentials
.env
.env.*
aliyun-cli-config.json
ossutil-config.ini

# Function compute
.node-version
.template.yml.bak

# Build outputs
dist/
build/
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `command not found: fun` | CLI not installed | `npm install @alicloud/fun -g` |
| `command not found: ossutil` | CLI not installed | Download and install ossutil |
| `InvalidAccessKeyId` | Wrong credentials | Verify AccessKey in RAM console |
| `SignatureDoesNotMatch` | Secret key mismatch | Check ALICLOUD_SECRET_KEY |
| `Permission denied` | Insufficient RAM permissions | Check RAM policy |

For detailed troubleshooting → `../best-practices/troubleshooting.md`
