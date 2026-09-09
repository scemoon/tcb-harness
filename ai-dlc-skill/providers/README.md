# Cloud Providers

## Default: TCB (Tencent CloudBase)

TCB is the default cloud development platform. Aliyun is also supported.

The provider layer supports a **monorepo multi-component stack** (native + desktop + web + backend + wxa + mya + tta). Use the `deploy_stack` orchestrator instead of per-component CLI commands for shared environments.

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

`deploy_stack` is the unified orchestrator. It deploys `backend` first, captures `BACKEND_URL`, then deploys all client components with `BACKEND_URL` injected. The output is `STACK_URL` (= `BACKEND_URL`) plus per-component URLs.

```bash
deploy_stack --preview --provider tcb
# → STACK_URL=https://{env-id}.tcb-preview.com
# → WEB_URL=https://{env-id}-{project}.tcb-preview.com
# → NATIVE_DIST_URL=internal distribution URL
# → DESKTOP_DIST_URL=internal distribution URL
# → WXA_URL/MYA_URL/TTA_URL=mini-program preview QR
```

```bash
deploy_stack --preview --provider aliyun
# → STACK_URL=https://{gateway}.{region}.fc.devs.com
# → WEB_URL=https://{bucket}.{region}.oss-website.aliyuncs.com
# → NATIVE_DIST_URL=internal distribution URL
# → DESKTOP_DIST_URL=internal distribution URL
# → WXA_URL/MYA_URL/TTA_URL=mini-program preview QR
```

## Build Config Injection

All client builds receive `BACKEND_URL` at build time. The orchestrator passes it; components must not hardcode URLs.

```bash
# web
pnpm --filter web build --env BACKEND_URL=$BACKEND_URL

# native
cd apps/native && BACKEND_URL=$BACKEND_URL pnpm build

# desktop
cd apps/desktop && BACKEND_URL=$BACKEND_URL pnpm build

# mini-programs (wxa, mya, tta)
cd apps/wxa && BACKEND_URL=$BACKEND_URL pnpm build
cd apps/mya && BACKEND_URL=$BACKEND_URL pnpm build
cd apps/tta && BACKEND_URL=$BACKEND_URL pnpm build
```

## Component URL Resolution

| Component | TCB | Aliyun |
|-----------|-----|--------|
| `backend` (gateway) | `https://{env-id}.tcb-preview.com` | `https://{gateway}.{region}.fc.devs.com` |
| `web` (hosting) | `https://{env-id}-{project}.tcb-preview.com` | `https://{bucket}.{region}.oss-website.aliyuncs.com` |
| `native` (distribution) | internal distribution URL | internal distribution URL |
| `desktop` (distribution) | internal distribution URL | internal distribution URL |
| `wxa` (mini-program) | mini-program preview QR | mini-program preview QR |
| `mya` (mini-program) | mini-program preview QR | mini-program preview QR |
| `tta` (mini-program) | mini-program preview QR | mini-program preview QR |

## BDD E2E Targets

| Test | Target |
|------|--------|
| `apps/backend/tests/e2e/` | `BACKEND_URL` |
| `apps/web/tests/e2e/` | `WEB_URL` + `BACKEND_URL` (as API root) |
| `apps/native/tests/e2e/` | `BACKEND_URL` (built into app) |
| `apps/desktop/tests/e2e/` | `BACKEND_URL` (built into app) |
| `apps/wxa/tests/e2e/` | `BACKEND_URL` (built into app) |
| `apps/mya/tests/e2e/` | `BACKEND_URL` (built into app) |
| `apps/tta/tests/e2e/` | `BACKEND_URL` (built into app) |
| `aidlc/tests/cross-stack/` | `STACK_URL` (full flow) |

## Dynamic Preview URL

Preview URLs are resolved at deploy time based on the active provider:

- **TCB:** `deploy_stack --preview --provider tcb` → `STACK_URL=https://{env-id}.tcb-preview.com`
- **Aliyun:** `deploy_stack --preview --provider aliyun` → `STACK_URL=https://{gateway}.{region}.fc.devs.com`

Set as `STACK_URL` / `BACKEND_URL` / `WEB_URL` / per-component URLs as environment variables for BDD e2e tests:

```bash
export STACK_URL=$(deploy_stack --preview --output url)
export BACKEND_URL=$STACK_URL
export WEB_URL=$(deploy_stack --preview --output web_url)
export NATIVE_URL=$(deploy_stack --preview --output native_url)
export DESKTOP_URL=$(deploy_stack --preview --output desktop_url)
pytest apps/web/tests/e2e/ --base-url $WEB_URL --api-url $BACKEND_URL
pytest apps/native/tests/e2e/ --backend-url $BACKEND_URL
pytest apps/desktop/tests/e2e/ --backend-url $BACKEND_URL
pytest aidlc/tests/cross-stack/ --stack-url $STACK_URL
```

## Stack Rollback

Rollback is at the **stack** level: backend and all client components revert together to the last stable stack version.

```bash
deploy_stack --rollback ${LAST_STABLE_STACK_VERSION} --provider tcb
```
