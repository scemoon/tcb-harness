# Cloud Providers

## Default: TCB (Tencent CloudBase)

TCB is the default cloud development platform. Aliyun is also supported.

The provider layer supports a **monorepo multi-component stack** (app + web + backend). Use the `deploy_stack` orchestrator instead of per-component CLI commands for shared environments.

## Provider Comparison

| Capability | TCB | Aliyun |
|-----------|-----|--------|
| **Functions** | CloudBase Functions | Function Compute (FC) |
| **Database** | DocDB + MySQL | TableStore + RDS |
| **Storage** | COS (Cloud Object Storage) | OSS (Object Storage Service) |
| **Hosting** | CloudBase Hosting + Preview | Static Website + CDN |
| **Stack preview URL** | `https://{env-id}.tcb-preview.com` (gateway) | `https://{gateway}.{region}.fc.devs.com` |
| **Default** | Yes | No |

## Stack Deploy

`deploy_stack` is the unified orchestrator. It deploys `backend` first, captures `BACKEND_URL`, then deploys `web` and `app` with `BACKEND_URL` injected. The output is `STACK_URL` (= `BACKEND_URL`) plus per-component URLs.

```bash
deploy_stack --preview --provider tcb
# → STACK_URL=https://{env-id}.tcb-preview.com
# → WEB_URL=https://{env-id}-{project}.tcb-preview.com
# → APP_DIST_URL=internal distribution URL
```

```bash
deploy_stack --preview --provider aliyun
# → STACK_URL=https://{gateway}.{region}.fc.devs.com
# → WEB_URL=https://{bucket}.{region}.oss-website.aliyuncs.com
# → APP_DIST_URL=internal distribution URL
```

## Build Config Injection

`web` and `app` builds receive `BACKEND_URL` at build time. The orchestrator passes it; components must not hardcode URLs.

```bash
# web
pnpm --filter web build --env BACKEND_URL=$BACKEND_URL

# app
cd apps/app && BACKEND_URL=$BACKEND_URL pnpm build
```

## Component URL Resolution

| Component | TCB | Aliyun |
|-----------|-----|--------|
| `backend` (gateway) | `https://{env-id}.tcb-preview.com` | `https://{gateway}.{region}.fc.devs.com` |
| `web` (hosting) | `https://{env-id}-{project}.tcb-preview.com` | `https://{bucket}.{region}.oss-website.aliyuncs.com` |
| `app` (distribution) | internal distribution URL | internal distribution URL |

## BDD E2E Targets

| Test | Target |
|------|--------|
| `apps/backend/tests/e2e/` | `BACKEND_URL` |
| `apps/web/tests/e2e/` | `WEB_URL` + `BACKEND_URL` (as API root) |
| `apps/app/tests/e2e/` | `BACKEND_URL` (built into app) |
| `tests/cross-stack/` | `STACK_URL` (full flow) |

## Dynamic Preview URL

Preview URLs are resolved at deploy time based on the active provider:

- **TCB:** `deploy_stack --preview --provider tcb` → `STACK_URL=https://{env-id}.tcb-preview.com`
- **Aliyun:** `deploy_stack --preview --provider aliyun` → `STACK_URL=https://{gateway}.{region}.fc.devs.com`

Set as `STACK_URL` / `BACKEND_URL` / `WEB_URL` environment variables for BDD e2e tests:

```bash
export STACK_URL=$(deploy_stack --preview --output url)
export BACKEND_URL=$STACK_URL
export WEB_URL=$(deploy_stack --preview --output web_url)
pytest apps/web/tests/e2e/ --base-url $WEB_URL --api-url $BACKEND_URL
pytest tests/cross-stack/ --stack-url $STACK_URL
```

## Stack Rollback

Rollback is at the **stack** level: backend, web, and app revert together to the last stable stack version.

```bash
deploy_stack --rollback ${LAST_STABLE_STACK_VERSION} --provider tcb
```
