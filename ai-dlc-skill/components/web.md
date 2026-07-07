# Web 组件开发指南 (WEB-FR-*)

## 技术栈
- 框架: React / Vue / Svelte
- 语言: TypeScript
- 构建: Vite / Webpack
- 测试: Vitest / Jest + Testing Library
- BDD: Cucumber.js / pytest-bdd

## 关键命令
- 构建: `pnpm --filter web build`
- 测试全部: `pnpm --filter web test`
- BDD: `cucumber-js features/`
- Lint: `pnpm --filter web lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `tests/integration/` → 集成测试
- `tests/e2e/` → E2E 测试
- `features/` → BDD feature 文件
- `features/steps/` → BDD step definitions

## FR 命名空间
- Prefix: WEB-FR-NNN
- 范围: 浏览器端行为（SPA / SSR）

## 特定约束
- Web 组件在构建时接收 `BACKEND_URL` 环境变量
- 使用 `aidlc/packages/shared/` 中的生成类型
- API 调用走 `aidlc/packages/shared/api/`
