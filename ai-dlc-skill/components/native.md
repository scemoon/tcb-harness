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

## Design System 规范

### 必读规范
| 规范 | 路径 |
|------|------|
| Design Tokens | `phases/plan/design_system/design_tokens.md` |
| Atomic Design | `phases/plan/design_system/atomic_design.md` |
| Component Spec | `phases/plan/design_system/component_spec.md` |
| Accessibility | `phases/plan/design_system/accessibility.md` |
| Theme System | `phases/plan/design_system/theme_system.md` |
| Native UI | `phases/plan/design_system/platform_ui/native.md` |
| Iconography | `phases/plan/design_system/iconography.md` |

### 平台适配要求

| 平台 | 设计语言 | 安全区域 |
|------|----------|----------|
| iOS | Human Interface Guidelines (HIG), SF Pro 字体 | SafeAreaView |
| Android | Material Design 3, Roboto 字体 | WindowInsets |

### iOS 规范
- 使用 `SafeAreaView` 处理刘海屏和 Home Indicator
- 字体: SF Pro (System font)
- 系统蓝: #007AFF
- 最小点击目标: 44x44pt

### Android 规范
- 使用 `WindowInsets` 处理状态栏和导航栏
- 字体: Roboto
- Primary 色: #0066CC
- 最小点击目标: 48x48dp

### 状态管理
- 推荐: Zustand (轻量) / Redux Toolkit (复杂)
- 状态持久化: AsyncStorage / MMKV

### 组件分层
- Atom: Button, Input, Badge, Icon
- Molecule: SearchBar, FormField, CardHeader
- Organism: Header, ListView, DetailCard
- Template: ListScreen, DetailScreen
- Page: UserListScreen, ProductDetailScreen
