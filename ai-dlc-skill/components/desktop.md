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

## Design System 规范

### 必读规范
| 规范 | 路径 |
|------|------|
| Design Tokens | `phases/plan/design_system/design_tokens.md` |
| Atomic Design | `phases/plan/design_system/atomic_design.md` |
| Component Spec | `phases/plan/design_system/component_spec.md` |
| Accessibility | `phases/plan/design_system/accessibility.md` |
| Theme System | `phases/plan/design_system/theme_system.md` |
| Desktop UI | `phases/plan/design_system/platform_ui/desktop.md` |
| Iconography | `phases/plan/design_system/iconography.md` |

### 窗口规范
| 项目 | 最小尺寸 | 默认尺寸 |
|------|----------|----------|
| 通用应用 | 1024x600 | 1280x800 |
| 复杂工具 | 1280x720 | 1440x900 |

### 平台菜单规范
| 平台 | 菜单 |
|------|------|
| macOS | 原生菜单 (App/File/Edit/View/Window/Help) |
| Windows | 原生标题栏 + 上下文菜单 |
| Linux | 原生标题栏 |

### 原生能力
- 窗口管理: 最小化/最大化/关闭
- 系统托盘: 后台运行指示器
- 全局快捷键: 设置/偏好设置/帮助
- 文件对话框: 打开/保存
- 拖拽: 支持拖拽文件到窗口
