# TCB Authentication & Credentials

## Credential Types

| Type | Security | Use Case |
|------|----------|----------|
| Root Tencent Cloud credentials | ⚠️ Low (full access) | Not recommended |
| TCB-specific API key | ✅ Recommended | Production use |
| Temporary credentials (STS) | ✅✅ Best | Short-lived access |
| Anonymous login | ⚠️ Limited | Client-side only |

## Agent Decision Guide

```
Need to authenticate with TCB?
├── From CI/CD pipeline → Environment variables (TCB_SECRET_ID/KEY)
├── From local CLI → tcb login (interactive)
├── From AI agent (CDH) → cdh cloudbase init
├── From function code → Injected environment variables
└── From browser/client → Anonymous or custom login
```

## Environment Variables

### For CLI and Server-Side

```bash
# Option 1: Tencent Cloud root credentials (not recommended)
export TENCENTCLOUD_SECRETID=AKIDxxxxxxxx
export TENCENTCLOUD_SECRETKEY=xxxxxxxx

# Option 2: TCB-specific credentials (recommended)
export TCB_SECRET_ID=AKIDxxxxxxxx
export TCB_SECRET_KEY=xxxxxxxx

# Environment ID
export TCB_ENV_ID=env-xxxxx
```

### Credential Priority

When both are set, TCB-specific credentials take priority:

```
TCB_SECRET_ID/KEY > TENCENTCLOUD_SECRETID/KEY
```

## Creating API Keys

### 1. Create via Tencent Cloud Console

1. Go to [Tencent Cloud Console](https://console.cloud.tencent.com/)
2. Navigate to: Access Keys → API Key Management
3. Create new key (or use existing)

### 2. Create TCB-Specific Credential

1. Go to TCB Console
2. Navigate to: Settings → API Keys
3. Create new TCB API key

**Benefits of TCB-specific credentials:**
- Limited to TCB services only
- Easier to rotate
- Audit trail per service

## Temporary Credentials (STS)

For short-lived access, use STS tokens:

### Get STS Token

```javascript
const tcb = require('@cloudbase/node-sdk');

const app = tcb.init({
  env: process.env.TCB_ENV_ID
});

// Get temporary credentials
const { credentials } = await app.getTempCredentials();
```

### STS Token Response

```json
{
  "credentials": {
    "tmpSecretId": "临时SecretId",
    "tmpSecretKey": "临时SecretKey",
    "sessionToken": "临时Token"
  },
  "expiredTime": 1640000000
}
```

### Use STS Token

```javascript
const app = tcb.init({
  env: process.env.TCB_ENV_ID,
  credentials: {
    secretId: tempCredentials.tmpSecretId,
    secretKey: tempCredentials.tmpSecretKey,
    sessionToken: tempCredentials.sessionToken
  }
});
```

## Credential Security Best Practices

### Do's ✅

1. **Use environment variables** - Don't hardcode credentials
2. **Rotate regularly** - Change API keys periodically
3. **Use TCB-specific credentials** - Over Tencent Cloud root keys
4. **Use least privilege** - Only grant needed permissions
5. **Store in secrets manager** - GitHub Secrets, Vault, etc.
6. **Use STS for client-side** - Temporary credentials expire

### Don'ts ❌

1. **Commit credentials** - Never commit to git
2. **Use root credentials** - In production workloads
3. **Share credentials** - Each user/service should have own key
4. **Use same credentials everywhere** - Separate per environment

## .gitignore for Credentials

```
# TCB credentials
cloudbaserc.json
!.cloudbaserc.*.json
.tcbrc

# CDH tokens
.cloud-harness-tokens.json

# Environment files
.env
.env.*
!.env.example
```

## Function Authentication

### How Functions Receive Credentials

TCB automatically injects environment variables into functions:

```javascript
exports.main = async (event, context) => {
  // Available automatically in TCB functions
  const envId = process.env.TCB_ENV_ID;
  const secretId = process.env.TENCENTCLOUD_SECRETID;
  const secretKey = process.env.TENCENTCLOUD_SECRETKEY;

  console.log(`Running in environment: ${envId}`);
};
```

### Calling TCB Services from Functions

```javascript
const tcb = require('@cloudbase/node-sdk');

exports.main = async (event, context) => {
  // Use injected credentials automatically
  const app = tcb.init({
    env: process.env.TCB_ENV_ID
    // Credentials auto-injected from environment
  });

  // Query database
  const db = app.database();
  const { data } = await db.collection('users').get();

  return { count: data.length };
};
```

## Client-Side Authentication

### Anonymous Login (for public data)

```javascript
const tcb = require('@cloudbase/js-sdk');

const app = tcb.init({
  env: 'env-xxxxx'
});

// Sign in anonymously
await app.auth().anonymousAuthProvider().signIn();
```

### Custom Login (for authenticated users)

```javascript
const tcb = require('@cloudbase/js-sdk');

const app = tcb.init({
  env: 'env-xxxxx'
});

// After server-side login returns custom token
await app.auth().signInWithCustomToken(customToken);
```

## Permission Model

### TCB Permissions

| Permission | Description |
|------------|-------------|
| `tcb:env:*` | Full environment access |
| `tcb:env:read` | Read-only environment access |
| `tcb:function:*` | Full function management |
| `tcb:function:invoke` | Invoke functions only |
| `tcb:database:*` | Full database access |
| `tcb:storage:*` | Full storage access |
| `tcb:hosting:*` | Full hosting access |

### Creating Limited Permissions

1. Go to [CAM](https://console.cloud.tencent.com/cam)
2. Create custom policy
3. Attach to specific API key
4. Grant minimum required permissions

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Invalid SecretId` | Wrong or expired key | Verify API key in console |
| `Signature failed` | Key mismatch | Check secret key matches |
| `Permission denied` | Insufficient permissions | Grant more permissions |
| `Token expired` | STS token too old | Refresh temporary credentials |
| `Login required` | Not authenticated | Run `tcb login` or set env vars |

For general troubleshooting → `../best-practices/troubleshooting.md`
