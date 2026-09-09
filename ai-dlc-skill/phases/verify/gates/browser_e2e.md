---
name: browser-e2e-gate
description: Local Web E2E verification using Playwright
triggers:
  - web e2e
  - browser test
  - playwright
  - e2e verification
  - browser e2e gate
allowed_tools:
  - Bash
  - Read
  - Glob
phases:
  - verify
---

# Browser E2E Gate

## Overview

Execute local Web application end-to-end tests using Playwright framework.

## Workflow

1. **Identify Target Application**
   - AI Agent determines the Web component under test
   - Determine local service port (default 8080)
   - Read `apps/web/package.json` to extract port from `scripts.dev`

2. **Check Test Files**
   - Scan `apps/web/tests/e2e/*.spec.ts`
   - If no test files exist, return `status: "skipped", message: "No e2e tests found"`

3. **Verify Base URL Reachability**
   ```bash
   curl -f http://localhost:{PORT}
   # Must return HTTP 200
   ```

4. **Execute Tests**
   ```bash
   cd apps/web
   npx playwright test --project=chromium --reporter=json
   ```

5. **Parse Results**
   - Parse Playwright JSON report
   - Extract: passed/failed/skipped counts
   - If failures exist, extract error messages

## Output Format

```json
{
  "gate": "browser_e2e",
  "status": "passed|failed|skipped",
  "total": 10,
  "passed": 9,
  "failed": 1,
  "duration_ms": 15000,
  "failures": [
    {
      "test": "login.spec.ts › should login successfully",
      "error": "Timeout waiting for element #dashboard"
    }
  ]
}
```

## Quality Gate Criteria

| Criterion | Threshold | Rule |
|-----------|-----------|------|
| Test Pass Rate | 100% | WEB-E2E-002 |
| Base URL | Reachable | WEB-E2E-003 |
| Test Files | Must exist | WEB-E2E-001 |

## Error Handling

| Error | Handling |
|-------|----------|
| Port unreachable | Return `status: "error", message: "Cannot connect to localhost:{PORT}"` |
| No test files | Return `status: "skipped", message: "No e2e tests found"` |
| Test failure | Return `status: "failed"` + failure details |
| Playwright not installed | Return `status: "error", message: "Playwright not installed"` |

## Integration with Verify Phase

This gate is invoked during Verify phase when:
- WEB component exists
- BDD scenarios at e2e layer need verification

See also:
- [runners/playwright_local.md](../runners/playwright_local.md)
- [config/base_url.md](../config/base_url.md)