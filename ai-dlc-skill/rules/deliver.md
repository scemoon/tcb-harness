# Deliver Rules (DLV-*)

Rules for the Deliver phase: preview deployment, BDD e2e verification, production release, and BVT validation.

## DLV-001: Preview Before Production

**Severity:** MUST

**Description:** Every release MUST be deployed to a preview environment and pass BDD e2e tests before any production deployment. Preview URL is dynamically resolved per cloud platform.

**Valid:**
```bash
deploy_cloud --preview  # TCB or Aliyun, returns URL
pytest tests/e2e/ --preview-url $PREVIEW_URL
```

**Invalid:** Deploying to production without preview e2e verification.

## DLV-002: Production Approval Gate

**Severity:** MUST

**Description:** Production deployment requires explicit human approval. Automated deployment to production without human sign-off is prohibited.

**Valid:** Human reviews preview e2e results, staging smoke, and explicitly confirms "approve" before production deploy.

**Invalid:** Automated production deployment triggered solely by test pass.

## DLV-003: BVT Validation

**Severity:** MUST

**Description:** After every production deployment, BVT (Build Verification Test) MUST run. If BVT fails, automatic rollback MUST be triggered.

**Verification:**
```bash
bvt ${PRODUCTION_URL}
# Checks: health endpoint, core flows, DB connectivity, error rate
```

**Failure handling:**
```bash
deploy_cloud --rollback ${LAST_STABLE_VERSION}
```
