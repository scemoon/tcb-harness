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

## Design System 规范

### 必读规范
| 规范 | 路径 |
|------|------|
| Design Tokens | `phases/plan/design_system/design_tokens.md` |
| Atomic Design | `phases/plan/design_system/atomic_design.md` |
| Component Spec | `phases/plan/design_system/component_spec.md` |
| Accessibility | `phases/plan/design_system/accessibility.md` |
| Theme System | `phases/plan/design_system/theme_system.md` |
| Web UI | `phases/plan/design_system/platform_ui/web.md` |
| Iconography | `phases/plan/design_system/iconography.md` |

### Design Tokens 使用
```css
/* 正确 */
background: var(--color-bg-primary);
color: var(--color-text-primary);
padding: var(--space-4);
border-radius: var(--radius-md);
box-shadow: var(--shadow-sm);

/* 错误 */
background: #FFFFFF;
color: #0F172A;
padding: 16px;
border-radius: 6px;
box-shadow: 0 1px 3px rgba(0,0,0,0.1);
```

### 响应式断点
| 断点 | 宽度 | Tailwind 前缀 |
|------|------|---------------|
| 手机 | < 640px | (无) |
| 平板 | 640px+ | sm: |
| 笔记本 | 768px+ | md: |
| 桌面 | 1024px+ | lg: |
| 大屏 | 1280px+ | xl: |

### 组件分层要求
- Atom 组件: Button, Input, Icon, Badge (全局复用)
- Molecule 组件: SearchBar, FormField, CardHeader (跨功能复用)
- Organism 组件: Header, DataTable, Sidebar (功能区块)
- Template 组件: ListTemplate, DetailTemplate (页面布局)
- Page 组件: UserListPage, ProductDetailPage (业务页面)
