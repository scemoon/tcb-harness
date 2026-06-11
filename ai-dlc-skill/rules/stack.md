# Stack Rules (STK-*)

Rules for monorepo multi-component awareness. Apply to every change in a monorepo with more than one component.

## STK-001: Component Scope Declaration

**Severity:** MUST

**Description:** Every spec delta, design doc, and task list MUST declare `affects: [native, desktop, web, backend, wxa, mya, tta, contracts]`. The declaration drives the FR namespaces used, the test layers required, and the deploy steps that run.

**Valid:**
```markdown
## Change: CHG-001 — User Login
Affects: [web, backend, contracts]
```

**Invalid:** A spec delta / design doc / task list without an `affects` declaration.

## STK-002: Cross-Component Tasks Have Edges

**Severity:** MUST

**Description:** In the task DAG, a task that consumes a contract (e.g. building a web client against a new backend endpoint) MUST have an explicit `depends_on` edge to the contract task and to the producing task. Hidden dependencies are forbidden.

**Valid:**
```yaml
- id: web-login-form
  fr: WEB-FR-001
  depends_on: [int-contract-auth-login, be-login-endpoint]
```

**Invalid:** A web task that depends implicitly on the backend being "ready" with no DAG edge.

## STK-003: Cross-Stack E2E is Mandatory for ≥2 Components

**Severity:** MUST

**Description:** A change with `affects` listing two or more components MUST produce at least one `cross-stack` e2e scenario in `tests/cross-stack/` that exercises the real flow between the affected components. Mocking the other component in `cross-stack` is forbidden.

**Valid:** `INT-FR-001` cross-stack e2e runs the real web client against the real backend preview, verifying the full flow.

**Invalid:** A "cross-stack" test that mocks the backend; or a multi-component change with no `cross-stack` coverage.

## STK-004: Unified Stack Deploy

**Severity:** MUST

**Description:** Preview, staging, and production deploys MUST use the `deploy_stack` orchestrator, which deploys all affected components together and resolves the stack URL. Ad-hoc per-component deploys to a shared environment are forbidden (per-component deploys to isolated dev sandboxes are fine).

**Valid:** `deploy_stack --preview` runs backend and all affected client deploys in dependency order and exports `STACK_URL` / `BACKEND_URL`.

**Invalid:** Deploying only `tcb fn deploy` for backend to a shared preview env, leaving the web side stale.

## STK-005: Cross-Component Build Config Injection

**Severity:** MUST

**Description:** All client builds (`web`, `native`, `desktop`, `wxa`, `mya`, `tta`) MUST receive `BACKEND_URL` (and any other stack-level config) as a build-time or runtime environment variable, not via hardcoded URLs. The injected value MUST come from the `deploy_stack` orchestrator for the current environment.

**Valid:** `pnpm --filter web build --env BACKEND_URL=$BACKEND_URL` driven by `deploy_stack`.

**Invalid:** `apps/web/.env.production` containing `VITE_API_URL=https://prod.example.com` checked into git.

## STK-006: Stack-Level Rollback

**Severity:** MUST

**Description:** Rollback is a stack operation, not a per-component operation. If any component must be reverted, the entire previous stable stack version is rolled back together so internal contracts stay consistent.

**Valid:** `deploy_stack --rollback v1.2.3` reverts the whole stack (backend + all clients) to the version that was last green on BVT.

**Invalid:** Rolling back only the backend while leaving clients on the new version (contract mismatch).
