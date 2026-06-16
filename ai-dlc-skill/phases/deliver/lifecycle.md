# AI-DLC Phase 4: Deliver (交付)

Deploy the **full stack** together, verify per-component and cross-stack e2e against the unified preview, release with stack-level BVT.

## Goal

Deliver verified code to production as a coherent stack with full confidence — preview environment, per-component e2e, cross-stack e2e, stack-level BVT, and rollback at the stack level.

## Flow

```
All Verify gates passed (per-component + contract + cross-stack)
  │
  ▼
Unified Stack Preview Deploy (dynamic URL from cloud provider)
  - backend (functions + DB migrate)
  - web (hosting build with BACKEND_URL)
  - native (build with BACKEND_URL; package + upload)
  - desktop (build with BACKEND_URL; package + upload)
  - wxa / mya / tta (build with BACKEND_URL; upload to mini-program platform)
  │
  ▼
Per-component BDD e2e (against component preview URL or stack URL)
  │
  ▼
Cross-stack e2e (full app ↔ web ↔ backend against unified stack URL)
  │
  ▼
Staging Stack Deploy + Smoke
  │
  ▼
Human Approval Gate
  │
  ▼
Production Stack Deploy (whole stack as one unit)
  │
  ▼
Stack BVT (Build Verification Test) — backend /health, app launch probe, web smoke, DB
  │
  ▼
Archive: contract-diff.md + e2e reports + BVT report
  │
  ▼
Gate: BVT pass → done | BVT fail → stack rollback
```

## Unified Stack Preview Deploy

The whole stack is deployed as one unit. The preview URL is the **backend gateway**; all client components (`web`, `native`, `desktop`, `wxa`, `mya`, `tta`) receive it as a build-time or runtime config.

```bash
# TCB (default)
deploy_stack --preview
# → backend: tcb fn deploy --env preview
# → backend: tcb db migrate --env preview
# → web:     tcb hosting deploy --env preview --build-env BACKEND_URL=${STACK_URL}
# → native:  build with BACKEND_URL=${STACK_URL}, upload to internal distribution
# → desktop: build with BACKEND_URL=${STACK_URL}, upload to internal distribution
# → wxa:     build with BACKEND_URL=${STACK_URL}, upload to mini-program platform
# → mya:     build with BACKEND_URL=${STACK_URL}, upload to mini-program platform
# → tta:     build with BACKEND_URL=${STACK_URL}, upload to mini-program platform
# → STACK_URL = https://{env-id}.tcb-preview.com

# Aliyun
deploy_stack --preview
# → backend: fun deploy --env preview
# → web:     oss + cdn deploy with build env
# → native:  build with BACKEND_URL, package
# → desktop: build with BACKEND_URL, package
# → wxa:     build with BACKEND_URL, upload to mini-program platform
# → mya:     build with BACKEND_URL, upload to mini-program platform
# → tta:     build with BACKEND_URL, upload to mini-program platform
# → STACK_URL = https://{gateway}.{region}.fc.devs.com
```

The `deploy_stack` tool resolves the preview URL dynamically per platform and exports it as `STACK_URL` (or `BACKEND_URL` for components to consume).

## Per-Component BDD E2E

```bash
export STACK_URL=$(deploy_stack --preview --output url)
export BACKEND_URL=$STACK_URL

# Backend
pytest apps/backend/tests/e2e/ --base-url $BACKEND_URL

# Web (against web hosting URL; uses BACKEND_URL as API root)
export WEB_URL=$(deploy_stack --preview --output web_url)
pytest apps/web/tests/e2e/ --base-url $WEB_URL --api-url $BACKEND_URL

# Native (against installed package or emulator; uses BACKEND_URL)
pytest apps/native/tests/e2e/ --backend-url $BACKEND_URL

# Desktop (against installed package or emulator; uses BACKEND_URL)
pytest apps/desktop/tests/e2e/ --backend-url $BACKEND_URL

# Mini-programs (wxa, mya, tta) (against emulator or device; uses BACKEND_URL)
pytest apps/wxa/tests/e2e/ --backend-url $BACKEND_URL
pytest apps/mya/tests/e2e/ --backend-url $BACKEND_URL
pytest apps/tta/tests/e2e/ --backend-url $BACKEND_URL
```

## Cross-Stack E2E

```bash
pytest tests/cross-stack/ --stack-url $STACK_URL --verbose
# Runs the full multi-client ↔ backend flow defined in features/cross-stack/
```

**Rule STK-001:** All `cross-stack` scenarios must pass before staging or production.

## Staging

```bash
deploy_stack --env staging
export STAGING_URL=$(deploy_stack --env staging --output url)
pytest tests/cross-stack/ --stack-url $STAGING_URL
smoke-test $STAGING_URL
```

## Human Approval

Production deployment requires explicit human approval. Approval is a **stack** decision — the reviewer sees the per-component e2e results, the cross-stack e2e results, the staging smoke, and the `contract-diff.md`.

## Production Stack Deploy

```bash
deploy_stack --env production
# → Same as preview/staging but with prod env IDs and production secrets
```

## Stack BVT (Build Verification Test)

Automated health and functionality checks against the **production stack**:

```bash
bvt ${PRODUCTION_URL}
# Checks:
#  1. backend /health returns 200
#  2. web home page returns 200 (SSR) or shell loads (SPA)
#  3. native/desktop/mini-program launch probe (deep link resolves against BACKEND_URL)
#  4. Core end-to-end flow (login) succeeds
#  5. Database connectivity (probe query)
#  6. No error rate spikes (5xx < 0.1%, p99 < 500ms)
```

**Rule DLV-003:** BVT must pass. If BVT fails, automatic **stack** rollback to the previous stable stack version.

## Stack Rollback

Rollback is at the stack level — all components revert together so the stack stays internally consistent.

```bash
# Automatic on BVT failure
deploy_stack --rollback ${LAST_STABLE_STACK_VERSION}

# Manual on demand
deploy_stack --rollback --stack-version v1.2.3
```

The previous stable stack version is identified by the `contracts/CHANGELOG.md` version at the time of the last green BVT.

## Artifacts

| Artifact | Purpose |
|----------|---------|
| `STACK_URL` / `BACKEND_URL` | Dynamic, per-platform, per-env |
| Per-component e2e report | Scenario pass/fail per component |
| Cross-stack e2e report | Full flow pass/fail |
| `openspec/changes/{id}/contract-diff.md` | Final contract change record |
| BVT report | Stack-level health check results |
| Deploy log | Stack version, timestamp, component versions |

## Gate

**Before marking complete:**
- [ ] Unified stack preview deploy succeeded; `STACK_URL` and `BACKEND_URL` resolved
- [ ] All per-component BDD e2e tests pass against their preview URLs
- [ ] All cross-stack e2e tests pass against the unified stack URL
- [ ] Staging smoke tests pass
- [ ] Human approval received (covers per-component + cross-stack + staging + contract diff)
- [ ] Production stack deploy succeeded
- [ ] Stack BVT passed
- [ ] (If BVT failed) Stack rollback executed and confirmed
- [ ] `openspec/changes/{id}/contract-diff.md` archived
