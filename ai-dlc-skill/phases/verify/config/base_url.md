---
name: verify-config-base-url
description: Base URL configuration for local Web verification
triggers:
  - base url
  - local url
  - localhost
allowed_tools:
  - Read
phases:
  - verify
---

# Base URL Configuration

## Default Ports by Component Type

| Component | Default Port | Start Command |
|-----------|--------------|---------------|
| Web (React/Vue) | 3000 | `npm run dev` |
| Web (Next.js) | 3000 | `npm run dev` |
| Web (Vite) | 5173 | `npm run dev` |
| Backend API | 8080 | `npm run start` |
| Storybook | 6006 | `npm run storybook` |

## How to Determine Port

AI Agent should:

1. Read `apps/web/package.json`
2. Extract port from `scripts.dev` or `scripts.start`
3. Parse common patterns:
   - `--port {N}` or `--port={N}`
   - `PORT={N}`
   - `-p {N}` or `-p{N}`

Example parsing:

```bash
# Extract port from package.json
cat apps/web/package.json | jq -r '.scripts.dev' | grep -oE '[0-9]+'
```

## Stack Preview URL

If application is deployed via `cdh stack preview`:
- Stack URL is set in environment variable `STACK_URL`
- AI Agent should prioritize `STACK_URL` over localhost

## Configuration Precedence

1. `STACK_URL` environment variable (if set)
2. `BASE_URL` environment variable (if set)
3. `http://localhost:{PORT}` from package.json parsing
4. Default: `http://localhost:8080`

## Verification

Before running E2E tests, verify base URL is reachable:

```bash
curl -f -m 5 http://localhost:3000
# HTTP 200 = reachable
# Connection refused = not running
```