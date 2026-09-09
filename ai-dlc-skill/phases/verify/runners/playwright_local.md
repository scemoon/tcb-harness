---
name: playwright-local-runner
description: Playwright local execution runner for Web E2E tests
triggers:
  - playwright run
  - run e2e
  - execute playwright
  - playwright test
allowed_tools:
  - Bash
  - Read
phases:
  - verify
---

# Playwright Local Runner

## Prerequisites

```bash
# Install dependencies (usually done during scaffold)
cd apps/web
pnpm install

# Install browsers (one-time setup)
pnpm exec playwright install chromium
```

## Execution Command

```bash
# Standard execution
cd apps/web
npx playwright test --project=chromium

# With JSON report (for parsing)
npx playwright test --project=chromium --reporter=json

# Specify test file
npx playwright test apps/web/tests/e2e/login.spec.ts

# Headless mode (default)
npx playwright test --project=chromium

# UI mode (for debugging)
npx playwright test --project=chromium --ui

# With custom base URL
BASE_URL=http://localhost:3000 npx playwright test --project=chromium
```

## Report Location

| Type | Location |
|------|----------|
| HTML Report | `apps/web/playwright-report/` |
| JSON Report | stdout (with `--reporter=json`) |
| Trace | `apps/web/test-results/` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `http://localhost:8080` | Override default base URL |
| `PLAYWRIGHT_BROWSERS_PATH` | `~/.cache/ms-playwright` | Browser installation path |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | Some tests failed |
| 2 | Test was interrupted |
| 3 | Configuration error |

## Common Issues

| Issue | Solution |
|-------|----------|
| `Playwright not installed` | Run `pnpm exec playwright install chromium` |
| `Browser already in use` | Kill existing browser processes |
| `Connection refused` | Ensure target app is running on specified port |
| `Timeout` | Increase timeout in `playwright.config.ts` |

## Example Output

```json
{
  "config": {
    "reporters": ["json"]
  },
  "result": {
    "status": "passed",
    "stats": {
      "tests": 5,
      "passed": 5,
      "failed": 0,
      "skipped": 0,
      "duration": 12345
    }
  }
}
```