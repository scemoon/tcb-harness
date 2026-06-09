# AI-DLC Phase 4: Deliver (交付)

Deploy to production-like environments, verify end-to-end, release with BVT validation.

## Goal

Deliver verified code to production with full confidence through preview environments, BDD e2e tests, and automated BVT.

## Flow

```
All Verify gates passed
  │
  ▼
Preview Deploy (dynamic URL from cloud provider)
  │
  ▼
BDD E2E Tests (against preview URL)
  │
  ▼
Staging Deploy + Smoke Tests
  │
  ▼
Human Approval Gate
  │
  ▼
Production Deploy
  │
  ▼
BVT (Build Verification Test)
  │
  ▼
Gate: BVT pass → done | BVT fail → rollback
```

## Preview Deploy

Deploy to an isolated preview environment. URL is dynamically resolved per platform.

```bash
# TCB (default)
tcb hosting deploy --preview
# → https://{env-id}-{project}.tcb-preview.com

# Aliyun
fun deploy --preview
# → https://{function}-{alias}.{region}.fc.devs.com
```

## BDD E2E Tests

Run the same Gherkin scenarios against the live preview URL.

```bash
export PREVIEW_URL=$(deploy_cloud --preview --output url)
pytest tests/e2e/ --preview-url $PREVIEW_URL
```

## Staging

Deploy to the staging environment for final integration validation.

```bash
deploy_cloud --env staging
pytest tests/integration/ --base-url $STAGING_URL
```

## Human Approval

Production deployment requires explicit human approval.

```bash
# Gate: human-approval required
# Only proceed after explicit "approved" signal
```

## Production Deploy

```bash
deploy_cloud --env production
```

## BVT (Build Verification Test)

Automated health and functionality checks against the production deployment.

```bash
bvt ${PRODUCTION_URL}
# Checks:
# - /health endpoint returns 200
# - Core user flows work (login, API calls)
# - Database connectivity
# - No error rate spikes
```

**Rule DLV-003:** BVT must pass. If BVT fails, automatic rollback to previous stable version.

## Rollback

```bash
# Automatic on BVT failure
deploy_cloud --rollback ${LAST_STABLE_VERSION}
# Manual on demand
deploy_cloud --rollback --version v1.2.3
```

## Artifacts

| Artifact | Purpose |
|----------|---------|
| Preview URL | Dynamic, per-platform |
| BDD e2e report | Scenario pass/fail against live env |
| BVT report | Health check results |
| Deploy log | Version, timestamp, artifacts |

## Gate

**Before marking complete:**
- [ ] Preview deploy succeeded with valid URL
- [ ] All BDD e2e tests pass against preview
- [ ] Staging smoke tests pass
- [ ] Human approval received
- [ ] Production deploy succeeded
- [ ] BVT passed
- [ ] (If BVT failed) Rollback executed and confirmed
