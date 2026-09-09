# Deliver Rules (DLV-*) + Stack Rules (STK-*)

## DLV-001: Unified Stack Preview Before Production
**Severity:** MUST
**Description:** Every release MUST deploy as unified stack preview with per-component e2e + cross-stack e2e passing before production.
**Valid:** `deploy_stack --preview` → `pytest aidlc/tests/cross-stack/ --stack-url $STACK_URL`.
**Invalid:** Deploying only one component to preview.

## DLV-002: Production Approval Gate
**Severity:** MUST
**Description:** Production deployment requires explicit human approval reviewing per-component e2e, cross-stack e2e, staging smoke, and contract-diff.md.
**Valid:** Human reviews all reports and explicitly approves.
**Invalid:** Automated production deployment triggered solely by test pass.

## DLV-003: Stack BVT Validation
**Severity:** MUST
**Description:** After production deploy, BVT MUST run against the stack. Failure triggers automatic stack rollback.
**Valid:** `bvt ${PRODUCTION_URL}` → fail → `deploy_stack --rollback`.
**Invalid:** BVT skip or success with errors.

## DLV-004: Per-Component Preview URL Isolation
**Severity:** MUST
**Description:** e2e tests run against dynamic preview URLs, never hardcoded production URLs.
**Valid:** `pytest apps/web/tests/e2e/ --preview-url $WEB_URL`.
**Invalid:** Hardcoded `https://prod.example.com` in tests.

## STK-001: Component Scope Declaration
**Severity:** MUST
**Description:** Every spec delta, design doc, task list MUST declare `affects:`.
**Valid:** `affects: [web, backend, contracts]`.
**Invalid:** Missing `affects` declaration.

## STK-002: Cross-Component Tasks Have Edges
**Severity:** MUST
**Description:** Tasks consuming a contract MUST have explicit `depends_on` edge to producing task.
**Valid:** `depends_on: [int-contract-auth-login, be-login-endpoint]`.
**Invalid:** Implicit dependency with no DAG edge.

## STK-003: Cross-Stack E2E Mandatory for ≥2 Components
**Severity:** MUST
**Description:** Changes affecting ≥2 components MUST have cross-stack e2e testing real flow between components.
**Valid:** Real web client against real backend preview.
**Invalid:** Cross-stack test that mocks the other component.

## STK-004: Unified Stack Deploy
**Severity:** MUST
**Description:** Shared environments MUST use `deploy_stack` orchestrator, not per-component ad-hoc deploys.
**Valid:** `deploy_stack --preview` deploys all components.
**Invalid:** Ad-hoc per-component deploy to shared preview.

## STK-005: Cross-Component Build Config Injection
**Severity:** MUST
**Description:** All client builds receive `BACKEND_URL` as build-time env var, never hardcoded.
**Valid:** `pnpm --filter web build --env BACKEND_URL=$BACKEND_URL`.
**Invalid:** Hardcoded URLs in `.env.production`.

## STK-006: Stack-Level Rollback
**Severity:** MUST
**Description:** Rollback is stack operation. Entire previous stable version reverts together.
**Valid:** `deploy_stack --rollback v1.2.3` reverts all components.
**Invalid:** Rolling back only backend while leaving clients on new version.
