# Native 组件开发指南 (NATIVE-FR-*)

## 技术栈
- 框架: React Native / Flutter
- 语言: TypeScript (React Native) / Dart (Flutter)
- 构建: `pnpm build:native`
- 测试: Jest (RN) / flutter_test (Flutter)
- BDD: Detox / Maestro

## 关键命令
- 构建: `pnpm --filter native build`
- 测试全部: `pnpm --filter native test`
- BDD: `detox test` / `maestro test`
- Lint: `pnpm --filter native lint`

## 目录约定
- `src/` → 组件源码
- `tests/unit/` → 单元测试
- `tests/e2e/` → E2E 测试
- `features/` → BDD feature 文件
- `features/steps/` → BDD step definitions

## FR 命名空间
- Prefix: NATIVE-FR-NNN
- 范围: 原生移动端行为（iOS + Android）

## 特定约束
- Native 组件依赖 `BACKEND_URL` 在构建时注入
- E2E 测试在真机或模拟器中运行
- 不包含平台特定 UI 逻辑（web 端）
