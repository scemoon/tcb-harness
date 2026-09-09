# Component Spec — 组件规格模板

所有 UI 组件必须按照本模板编写规格说明，确保一致性、可测试性和可访问性。

## 模板结构

```markdown
# {组件名}

## 1. Overview
## 2. Visual Design
## 3. Props & Types
## 4. States & Behaviors
## 5. Composition
## 6. Accessibility
## 7. Testing
## 8. Usage Examples
```

---

## 1. Overview (概述)

```markdown
### 组件名称
{ComponentName}

### 原子层级
Atom | Molecule | Organism | Template

### 简要描述
{一句话描述组件做什么}

### 使用场景
- {场景1}
- {场景2}

### 代码位置
`src/components/{category}/{ComponentName}/`
```

---

## 2. Visual Design (视觉设计)

### 2.1 尺寸变体 (Variants)

| Variant | 高度 | 宽度 | Font Size | 用途 |
|---------|------|------|-----------|------|
| xs | 24px | auto | 12px | 次要操作 |
| sm | 32px | auto | 14px | 紧凑布局 |
| md | 40px | auto | 14px | 默认 (primary) |
| lg | 48px | auto | 16px | 主要操作 |

### 2.2 样式变体 (Styles)

| Style | 背景色 | 边框 | 文字色 | 用途 |
|-------|--------|------|--------|------|
| primary | `--color-primary` | none | white | 主操作 |
| secondary | transparent | `--color-border-default` | `--color-text-primary` | 次操作 |
| ghost | transparent | none | `--color-primary` | 辅助操作 |
| danger | `--color-danger` | none | white | 危险操作 |

### 2.3 视觉规范

```css
/* 基础样式 */
.{component-prefix} {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: var(--radius-md);
  font-family: var(--font-family-sans);
  font-weight: var(--font-weight-medium);
  transition: all var(--duration-fast) var(--ease-in-out);
  cursor: pointer;
  border: 1px solid transparent;
}

/* Focus Ring */
.{component-prefix}:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

---

## 3. Props & Types (属性与类型)

```typescript
interface {ComponentName}Props {
  /** 变体样式 */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  /** 尺寸大小 */
  size?: 'xs' | 'sm' | 'md' | 'lg';
  /** 禁用状态 */
  disabled?: boolean;
  /** 加载状态 */
  loading?: boolean;
  /** 左侧图标 */
  leftIcon?: ReactNode;
  /** 右侧图标 */
  rightIcon?: ReactNode;
  /** 点击回调 */
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void;
  /** 子元素 */
  children?: ReactNode;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: CSSProperties;
  /** 完整宽度 */
  fullWidth?: boolean;
  /** ARIA label (当 children 不够语义化时) */
  'aria-label'?: string;
}
```

### Props 规范

| 规范 | 要求 |
|------|------|
| **必填/可选** | 必须标记哪些是必填 (required)，哪些是可选 |
| **默认值** | 每个可选 prop 必须有默认值 |
| **类型安全** | 必须使用 TypeScript 类型，禁止 any |
| **继承** | 避免继承原生元素属性，使用 composition 替代 |
| **废弃 (deprecated)** | 标记废弃 prop，保留一个版本后移除 |

---

## 4. States & Behaviors (状态与行为)

### 4.1 状态机

| State | 触发条件 | 视觉表现 | 可访问性 |
|-------|----------|----------|----------|
| default | 初始状态 | 正常样式 | 可聚焦 |
| hover | 鼠标悬停 | 背景/边框变化 | cursor: pointer |
| active | 鼠标按下 | 颜色加深 | - |
| focus | Tab 聚焦 / 点击 | focus ring | 可键盘导航 |
| disabled | disabled=true | 50% opacity, 禁用交互 | aria-disabled |
| loading | loading=true | 显示 spinner, 禁用交互 | aria-busy |

### 4.2 交互行为

```markdown
### Click 行为
- 触发条件: 点击 / Enter / Space (当组件可聚焦时)
- onClick 回调在 click 事件触发时执行
- disabled=true 时不触发

### Loading 行为
- loading=true 时:
  - 显示 spinner 替换内容
  - 禁用所有交互
  - 保持宽度不变 (防止布局抖动)
- 动画: spinner 旋转 360deg / 1s linear infinite

### Disabled 行为
- disabled=true 时:
  - pointer-events: none
  - opacity: 0.5
  - aria-disabled: true
  - Tab 键无法聚焦
```

### 4.3 键盘导航

| Key | 行为 |
|-----|------|
| Tab | 聚焦到组件 |
| Enter | 触发 onClick |
| Space | 触发 onClick |

---

## 5. Composition (组合结构)

### 5.1 DOM 结构

```html
<button class="btn">
  <span class="btn__icon btn__icon--left">{leftIcon}</span>
  <span class="btn__text">{children}</span>
  <span class="btn__icon btn__icon--right">{rightIcon}</span>
  <span class="btn__spinner" aria-hidden="true"></span>
</button>
```

### 5.2 CSS 命名 (BEM)

```css
.{block} { }
.{block}__{element} { }
.{block}--{modifier} { }
```

| 示例 | 说明 |
|------|------|
| `btn__icon--left` | icon 元素的 left 变体 |
| `btn--primary` | primary 变体 |
| `btn--disabled` | disabled 状态 |

---

## 6. Accessibility (可访问性)

### 6.1 ARIA 属性

| 属性 | 值 | 条件 |
|------|-----|------|
| role | 'button' | 默认 (button 元素不需要) |
| aria-label | string | 当 children 为空或不够语义化 |
| aria-disabled | 'true' | disabled=true |
| aria-busy | 'true' | loading=true |
| aria-expanded | 'true'/'false' | 如有下拉菜单 |
| aria-haspopup | 'menu'/'dialog'/... | 如有弹出内容 |

### 6.2 焦点管理

```markdown
### 焦点规范
- 必须可通过 Tab 键聚焦
- Focus ring 必须可见 (2px solid, offset 2px)
- 焦点环颜色使用 `--color-border-focus`
- 移动端不需要 focus ring (触摸无键盘)

### 焦点陷阱 (Focus Trap)
- Modal / Dialog 必须实现焦点陷阱
- 焦点循环: 最后一个元素 → 第一个元素
- Escape 键关闭弹窗
```

### 6.3 屏幕阅读器

```markdown
### 文本
- 所有文本必须可被屏幕阅读器读取
- 图标按钮必须提供 aria-label

### 图片
- 有意义的图片必须有 alt
- 装饰性图片 alt=""

### 动态内容
- aria-live="polite" 用于非紧急更新
- aria-live="assertive" 仅用于紧急警告
```

---

## 7. Testing (测试)

### 7.1 单元测试 (Vitest)

```typescript
describe('{ComponentName}', () => {
  describe('Rendering', () => {
    it('renders with default props', () => {});
    it('renders with custom className', () => {});
    it('renders children correctly', () => {});
  });

  describe('Variants', () => {
    it('renders primary variant', () => {});
    it('renders secondary variant', () => {});
    it('renders ghost variant', () => {});
    it('renders danger variant', () => {});
  });

  describe('Sizes', () => {
    it('renders xs size', () => {});
    it('renders sm size', () => {});
    it('renders md size', () => {});
    it('renders lg size', () => {});
  });

  describe('States', () => {
    it('renders disabled state', () => {});
    it('renders loading state with spinner', () => {});
  });

  describe('Interactions', () => {
    it('calls onClick when clicked', () => {});
    it('does not call onClick when disabled', () => {});
    it('does not call onClick when loading', () => {});
  });

  describe('Accessibility', () => {
    it('is focusable', () => {});
    it('has focus ring on focus', () => {});
    it('has aria-label when icon only', () => {});
    it('has aria-disabled when disabled', () => {});
    it('has aria-busy when loading', () => {});
  });
});
```

### 7.2 Storybook (视觉测试)

```typescript
// {ComponentName}.stories.tsx
export default {
  title: 'Components/Atoms/{ComponentName}',
  component: {ComponentName},
  tags: ['autodocs'],
  argTypes: {
    variant: { control: 'select', options: ['primary', 'secondary', 'ghost', 'danger'] },
    size: { control: 'select', options: ['xs', 'sm', 'md', 'lg'] },
    disabled: { control: 'boolean' },
    loading: { control: 'boolean' },
  },
} as Meta<typeof {ComponentName}>;

export const Default = { args: { children: 'Button' } };
export const Primary = { args: { variant: 'primary', children: 'Primary' } };
export const Secondary = { args: { variant: 'secondary', children: 'Secondary' } };
export const Ghost = { args: { variant: 'ghost', children: 'Ghost' } };
export const Danger = { args: { variant: 'danger', children: 'Danger' } };
export const Loading = { args: { loading: true, children: 'Loading...' } };
export const Disabled = { args: { disabled: true, children: 'Disabled' } };
export const WithIcon = { args: { leftIcon: <IconPlus />, children: 'Add' } };
export const FullWidth = { args: { fullWidth: true, children: 'Full Width' } };
```

### 7.3 测试覆盖率要求

| 层级 | 最低覆盖率 |
|------|-----------|
| Atom | 90% |
| Molecule | 80% |
| Organism | 70% |
| Template | 60% |
| Page | 50% |

---

## 8. Usage Examples (使用示例)

### 8.1 正确用法

```tsx
// 基础用法
<Button>Click me</Button>

// 带图标
<Button leftIcon={<IconPlus />}>Add Item</Button>

// 危险操作
<Button variant="danger" onClick={handleDelete}>
  Delete
</Button>

// 加载状态
<Button loading={isSubmitting}>Submitting...</Button>

// 禁用状态
<Button disabled>Not available</Button>

// 充满宽度
<Button fullWidth>Submit</Button>
```

### 8.2 错误用法

```tsx
// ❌ 硬编码颜色
<Button style={{ backgroundColor: 'blue' }}>Blue</Button>

// ❌ 使用 div 代替 button
<div onClick={handleClick}>Click</div>

// ❌ 遗漏 loading 状态宽度固定
<Button loading>{isLoading ? 'Loading...' : 'Submit'}</Button>

// ❌ 遗漏 aria-label
<Button><IconPlus /></Button> // 无文字时必须有 aria-label

// ❌ 禁用状态仍可点击
<button disabled={false} onClick={handleClick}>Button</button>
```

---

## 组件规格检查清单

- [ ] 概述 (Overview) 完整
- [ ] 视觉设计 (Visual Design) 有变体表格
- [ ] Props & Types 有 TypeScript 类型定义
- [ ] States & Behaviors 有完整状态机
- [ ] Composition 有 DOM 结构和 CSS 命名
- [ ] Accessibility 有 ARIA 属性说明
- [ ] Testing 有测试用例和覆盖率要求
- [ ] Usage Examples 有正确/错误示例
- [ ] 有对应的 Storybook stories 文件
- [ ] 有对应的 Vitest 测试文件
