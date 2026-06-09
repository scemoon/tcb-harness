# Cloud Providers

## Default: TCB (Tencent CloudBase)

TCB is the default cloud development platform. Aliyun is also supported.

## Provider Comparison

| Capability | TCB | Aliyun |
|-----------|-----|--------|
| **Functions** | CloudBase Functions | Function Compute (FC) |
| **Database** | DocDB + MySQL | TableStore + RDS |
| **Storage** | COS (Cloud Object Storage) | OSS (Object Storage Service) |
| **Hosting** | CloudBase Hosting + Preview | Static Website + CDN |
| **Preview URL** | `{env-id}-{project}.tcb-preview.com` | Per FC alias endpoint |
| **Default** | ✅ Yes | No |

## Dynamic Preview URL

Preview URLs are resolved at deploy time based on the active provider:

- **TCB:** `tcb hosting deploy --preview` → returns `https://{env-id}.tcb-preview.com`
- **Aliyun:** `fun deploy --preview` → returns `https://{function}.{region}.fc.devs.com`

Set as `PREVIEW_URL` environment variable for BDD e2e tests:

```bash
export PREVIEW_URL=$(deploy_cloud --preview --provider {provider})
pytest tests/e2e/ --preview-url $PREVIEW_URL
```
