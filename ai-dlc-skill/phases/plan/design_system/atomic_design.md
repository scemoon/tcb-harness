# Atomic Design — 原子化设计分层

Atomic Design 是 UI 组件的分层方法论，将界面拆解为 5 个层级：Atom → Molecule → Organism → Template → Page。

## 层级总览

```
Page
  └── Template
        └── Organism
              └── Molecule
                    └── Atom
```

| 层级 | 定义 | 复杂度 | 可复用性 |
|------|------|--------|----------|
| **Atom** | 最小单元，不可拆分 | 低 | 全局复用 |
| **Molecule** | 2-3 个 Atom 简单组合 | 低 | 全局复用 |
| **Organism** | 多个组件复杂组合 | 中 | 跨功能复用 |
| **Template** | 页面骨架布局 | 中 | 同类型页面复用 |
| **Page** | 具体页面实例 | 高 | 特定页面 |

---

## Atom — 原子

**定义**: 最小 UI 单元，不可再拆分，拥有自己的 markup 和样式。

### 类型

| 类型 | 示例组件 |
|------|----------|
| **基础** | Button, Input, Textarea, Select, Checkbox, Radio, Switch |
| **显示** | Badge, Tag, Avatar, Progress, Tooltip |
| **导航** | Tab, Breadcrumb, Pagination |
| **媒体** | Icon, Image, Video |
| **反馈** | Spinner, Skeleton, Alert |

### Atom 规范

```markdown
## Button

### Variants
- primary: 主操作按钮
- secondary: 次级操作
- ghost: 透明背景
- danger: 危险操作

### Sizes
- sm: 高度 32px, font-size xs
- md: 高度 40px, font-size sm (default)
- lg: 高度 48px, font-size base

### States
- default: 默认
- hover: 悬停
- active: 按下
- focus: 聚焦 (focus ring)
- disabled: 禁用
- loading: 加载中

### Props (示例)
- variant: 'primary' | 'secondary' | 'ghost' | 'danger'
- size: 'sm' | 'md' | 'lg'
- disabled: boolean
- loading: boolean
- leftIcon: ReactNode
- rightIcon: ReactNode
- fullWidth: boolean
```

### 设计要求

- 必须可通过 CSS 变量覆盖外观
- 必须支持键盘聚焦状态 (focus ring)
- 尺寸需符合 spacing token
- 文字颜色需满足 WCAG 对比度要求

---

## Molecule — 分子

**定义**: 2-3 个 Atom 组合，形成具有单一功能职责的组件。

### 类型

| 类型 | 示例组件 |
|------|----------|
| **表单** | SearchBar (Input + Button), FormField (Label + Input + ErrorText), DatePicker |
| **卡片** | CardHeader (Avatar + Title + Subtitle), CardFooter (Meta + Action) |
| **数据** | DataRow (Label + Value), StatCard (Icon + Value + Label) |
| **导航** | NavItem (Icon + Text + Badge), BreadcrumbItem |
| **媒体** | ImageWithCaption (Image + Caption), VideoPlayer |

### Molecule 规范

```markdown
## SearchBar

### Composition
- Input (Atom)
- Button (Atom)
- 可选: Dropdown for filter

### States
- default: 默认
- focus: Input 聚焦
- loading: 搜索中 (Button loading)
- results: 显示结果
- empty: 无结果

### Props
- placeholder: string
- onSearch: (value: string) => void
- isLoading: boolean
- value: string

### 行为
- Enter 触发搜索
- 搜索时显示 loading 状态
- 清空按钮在有内容时显示
```

### 设计要求

- Molecule 应有明确的单一职责
- 内部 Atom 状态需联动（如 Input 禁用时 Button 也禁用）
- 可接收外部样式覆盖 (className / style props)

---

## Organism — 有机体

**定义**: 多个 Molecule/Atom 组合，形成独立的功能区块，可跨功能复用。

### 类型

| 类型 | 示例组件 |
|------|----------|
| **布局** | Header, Sidebar, Footer |
| **数据** | DataTable, ListView, CardGrid |
| **表单** | LoginForm, RegisterForm, FilterPanel |
| **导航** | MainNav, TabPanel |
| **反馈** | ToastContainer, Modal, ConfirmDialog |

### Organism 规范

```markdown
## DataTable

### Composition
- TableHeader (Organism): 排序按钮 + 列选择
- TableRow (Molecule): 多列数据
- TableFooter (Organism): 分页信息
- 内部状态: columns, sortConfig, selectedRows

### States
- loading: 骨架屏
- empty: 空状态插画
- error: 错误提示
- populated: 正常数据

### Props
- columns: Column[]
- data: T[]
- sortable: boolean
- selectable: boolean
- pagination: PaginationConfig
- onSort: (key: string, dir: 'asc' | 'desc') => void
- onSelect: (rows: T[]) => void

### 可复用部分
- TableHeader 可单独作为 Organism
- TableRow 可单独作为 Molecule
```

### 设计要求

- Organism 应是独立功能块，不依赖父级数据
- 内部状态需合理管理 (local state vs external state)
- 必须处理空状态、加载状态、错误状态

---

## Template — 模板

**定义**: 页面骨架布局，定义内容区域的结构和位置关系，不含具体业务数据。

### 类型

| 类型 | 用途 |
|------|------|
| **ListTemplate** | 列表页模板 (Header + Filter + Table + Pagination) |
| **DetailTemplate** | 详情页模板 (Header + Content + Sidebar) |
| **FormTemplate** | 表单页模板 (Header + Form + Actions) |
| **DashboardTemplate** | 仪表盘模板 (Header + StatsGrid + Charts) |
| **AuthTemplate** | 认证页模板 (CenterCard + Logo + Form) |

### Template 规范

```markdown
## ListTemplate

### Layout Structure
┌─────────────────────────────────────┐
│ Header: Title + Actions              │
├─────────────────────────────────────┤
│ FilterBar: Search + Filters + Sort  │
├─────────────────────────────────────┤
│ DataTable / ListView                │
│ (内容区域，可滚动)                    │
├─────────────────────────────────────┤
│ Pagination                          │
└─────────────────────────────────────┘

### 占位区域
- Header: 高度 64px, 固定
- FilterBar: 高度 56px
- Pagination: 高度 48px
- 内容区: flex-1, 可滚动

### Responsive
- Desktop: 完整布局
- Tablet: FilterBar 可折叠
- Mobile: 单列列表
```

### 设计要求

- Template 只定义布局结构，不含业务逻辑
- 必须支持响应式断点
- 主要内容区域需可滚动

---

## Page — 页面

**定义**: Template 的具体实例，填充真实数据和业务逻辑。

### 类型

| 类型 | 示例 |
|------|------|
| **业务页面** | UserListPage, ProductDetailPage, OrderPage |
| **认证页面** | LoginPage, RegisterPage, ForgotPasswordPage |
| **设置页面** | AccountSettingsPage, NotificationSettingsPage |
| **错误页面** | NotFoundPage, ErrorPage |

### Page 规范

```markdown
## UserListPage

### Uses Template
- ListTemplate

### Data Binding
- Header: 动态标题 "用户管理"
- FilterBar: 用户状态筛选 (全部/活跃/禁用)
- DataTable: 用户列表数据
- Pagination: 总页数 100

### State Management
- URL state: ?page=1&status=active&search=xxx
- Local state: 选中行、弹窗可见性
- Server state: 用户列表 (React Query / SWR)

### Side Effects
- 页面加载时获取数据
- 筛选变化时重置页码并刷新
- 删除用户后刷新列表

### Routes
- /users (列表)
- /users/:id (详情)
- /users/new (新建)
```

### 设计要求

- Page 是路由级别的组件
- Page 负责数据获取和业务逻辑，布局委托给 Template
- Page 需处理 SEO (metadata)、权限控制

---

## 目录结构约定

```
src/
├── components/
│   ├── atoms/           # Atom 组件
│   │   ├── Button/
│   │   ├── Input/
│   │   └── ...
│   ├── molecules/       # Molecule 组件
│   │   ├── SearchBar/
│   │   ├── FormField/
│   │   └── ...
│   ├── organisms/       # Organism 组件
│   │   ├── Header/
│   │   ├── DataTable/
│   │   └── ...
│   └── templates/       # Template 组件
│       ├── ListTemplate/
│       ├── DetailTemplate/
│       └── ...
├── pages/               # Page 组件 (按路由组织)
│   ├── UserListPage/
│   └── ProductDetailPage/
```

---

## 设计决策规则

| 场景 | 决策 |
|------|------|
| 新组件是 Atom 还是 Molecule？ | 看是否需要多个 Atom 组合才能完成功能 |
| 新组件是 Molecule 还是 Organism？ | 看是否有多个功能区块 / 是否独立存在 |
| 是 Organism 还是 Template？ | Organism 是功能块，Template 是布局结构 |
| 是 Template 还是 Page？ | Template 无业务数据，Page 是具体实例 |
| 何时新建组件？ | 发现重复 UI 模式时抽取，而非预判 |
| 组件复用边界？ | 同一功能类型内复用，跨类型不强行复用 |

---

## 评审清单

新组件创建时检查：

- [ ] 属于正确的原子层级
- [ ] 有对应的 `ComponentName.stories.tsx` (Storybook)
- [ ] 有对应的 `ComponentName.test.tsx` (Vitest)
- [ ] 支持 Design Tokens (CSS 变量)
- [ ] 支持深色模式
- [ ] 有完整的 Props TypeScript 类型
- [ ] 有必要的 ARIA 属性
- [ ] 处理了 disabled / loading / error / empty 状态
- [ ] 单元测试覆盖率 ≥ 80%
