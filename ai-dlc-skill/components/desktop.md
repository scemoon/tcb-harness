# Desktop 组件开发指南 (DESKTOP-FR-*)

## 技术栈
- 框架: Electron / Tauri
- 语言: TypeScript (Electron) / Rust + TS (Tauri)
- 构建: `pnpm build:desktop`
- 测试: Vitest / Jest
- BDD: Spectron / WebDriverIO

## 关键命令
- 构建: `pnpm --filter desktop build`
- 测试全部: `pnpm --filter desktop test`
- BDD: `spectron test`
- Lint: `pnpm --filter desktop lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `tests/e2e/` → E2E 测试
- `features/` → BDD feature 文件
- `features/steps/` → BDD step definitions

## FR 命名空间
- Prefix: DESKTOP-FR-NNN
- 范围: 桌面端行为（macOS + Windows + Linux）

## 特定约束
- Desktop 组件依赖 `BACKEND_URL` 在构建时注入
- 支持离线模式（本地优先）
- 自动更新通过内置更新器
