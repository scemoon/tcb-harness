# Deliver Rules (DLV-*)

Rules for the Deliver phase: unified stack preview, per-component and cross-stack e2e, stack-level production release and BVT.

## DLV-001: Unified Stack Preview Before Production

**Severity:** MUST

**Description:** Every release MUST be deployed as a unified stack preview (backend + web + app together) with per-component e2e AND cross-stack e2e passing before any production deployment. The stack preview URL is dynamically resolved per cloud platform.

**Valid:**
```bash
deploy_stack --preview                          # unified stack URL
export STACK_URL=$(deploy_stack --preview --output url)
pytest apps/{comp}/tests/e2e/ --preview-url $STACK_URL
pytest tests/cross-stack/ --stack-url $STACK_URL
```

**Invalid:** Deploying only one component to preview, or deploying to production without a cross-stack e2e pass.

## DLV-002: Production Approval Gate

**Severity:** MUST

**Description:** Production deployment requires explicit human approval. The approver reviews per-component e2e, cross-stack e2e, staging smoke, AND the `contract-diff.md`. Automated deployment to production without human sign-off is prohibited.

**Valid:** Human reviews per-component + cross-stack e2e reports, staging smoke, and `contract-diff.md`, and explicitly confirms "approve" before production deploy.

**Invalid:** Automated production deployment triggered solely by test pass; or human approval without seeing the contract diff.

## DLV-003: Stack BVT Validation

**Severity:** MUST

**Description:** After every production deployment, BVT (Build Verification Test) MUST run against the **stack** (not just one component). If BVT fails, automatic **stack** rollback to the previous stable stack version MUST be triggered.

**Verification:**
```bash
bvt ${PRODUCTION_URL}
# Checks: backend /health, web smoke, app launch probe, DB, end-to-end login, error rate
```

**Failure handling:**
```bash
deploy_stack --rollback ${LAST_STABLE_STACK_VERSION}
# All components roll back together so the stack stays internally consistent
```

## DLV-004: Per-Component Preview URL Isolation

**Severity:** MUST

**Description:** A component's `e2e` tests run against its own preview URL (or the stack URL when component URLs are not separately resolvable), with `BACKEND_URL` injected as a build-time or runtime config. Tests MUST NOT hardcode production or staging URLs.

**Valid:** `pytest apps/web/tests/e2e/ --preview-url $WEB_URL --api-url $BACKEND_URL` where both come from `deploy_stack --output`.

**Invalid:** `pytest apps/web/tests/e2e/` with hardcoded `https://prod.example.com` URLs.
