# Backend 组件开发指南 (BE-FR-*)

## 技术栈
- 语言: Python / Node.js / Go
- 框架: FastAPI / Express / Gin
- 构建: poetry / pnpm / go build
- 测试: pytest / vitest / go test
- BDD: pytest-bdd

## 关键命令
- 构建: `pnpm --filter backend build`
- 测试全部: `pnpm --filter backend test`
- BDD: `pytest-bdd apps/backend/features/`
- Lint: `pnpm --filter backend lint`
- DB 迁移: `tcb db migrate` / `rds migrate`

## 目录约定
- `src/` → 组件源码（按模块组织）
- `tests/unit/` → 单元测试
- `tests/integration/` → 集成测试（含 DB）
- `tests/e2e/` → E2E 测试（对 preview URL）
- `features/` → BDD feature 文件
- `features/steps/` → BDD step definitions

## FR 命名空间
- Prefix: BE-FR-NNN
- 范围: 服务端/API 行为

## 特定约束
- 后端组件是 Stack 部署的入口点（先部署再暴露 BACKEND_URL）
- API 合约定义在 `contracts/api/`（OpenAPI 3.1）
- 依赖注入使用 provider pattern
- 所有输入必须验证（SEC-002）
- DB 查询必须使用参数化语句（SEC-003）
