# Web UI 规范 — 响应式设计

Web 端 UI 规范，基于 Design Tokens，使用 Tailwind CSS 框架。

## 响应式断点

| 名称 | 断点 | 用途 |
|------|------|------|
| `sm` | `640px` | 手机横屏、小平板 |
| `md` | `768px` | 平板竖屏 |
| `lg` | `1024px` | 笔记本 |
| `xl` | `1280px` | 桌面显示器 |
| `2xl` | `1536px` | 大屏显示器 |

### Tailwind 断点配置

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    screens: {
      'sm': '640px',
      'md': '768px',
      'lg': '1024px',
      'xl': '1280px',
      '2xl': '1536px',
    }
  }
}
```

## 栅格系统 (Grid)

### 12 列栅格

| 元素 | 规范 |
|------|------|
| 列数 | 12 |
| 槽宽 (Gutter) | 24px (12px each side) |
| 边距 (Margin) | 16px (mobile), 24px (tablet), 32px (desktop) |
| Max Width | 1280px |

### 栅格 CSS 变量

```css
:root {
  --grid-columns: 12;
  --grid-gutter: 24px;
  --grid-margin-sm: 16px;
  --grid-margin-md: 24px;
  --grid-margin-lg: 32px;
  --grid-max-width: 1280px;
}
```

### 栅格使用

```tsx
// 使用 Tailwind CSS Grid
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-6">
  <div className="md:col-span-1 lg:col-span-4">Sidebar</div>
  <div className="md:col-span-1 lg:col-span-8">Content</div>
</div>
```

## Flex 布局

| 类名 | 用途 |
|------|------|
| `flex-row` | 水平排列 |
| `flex-col` | 垂直排列 |
| `flex-wrap` | 自动换行 |
| `flex-1` | 自动填充剩余空间 |
| `flex-shrink-0` | 禁止收缩 |

## 间距规范

| 类名 | 间距值 | 用途 |
|------|--------|------|
| `gap-1` | 4px | 紧凑间距 |
| `gap-2` | 8px | 小间距 |
| `gap-3` | 12px | 中小间距 |
| `gap-4` | 16px | 中间距 |
| `gap-6` | 24px | 中大间距 |
| `gap-8` | 32px | 大间距 |

## 容器

```tsx
// 响应式容器
<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
  {/* 内容 */}
</div>
```

| 断点 | 边距 | Max Width |
|------|------|-----------|
| Default (mobile) | 16px | - |
| sm | 24px | - |
| lg | 32px | 1280px |

## 常用布局

### 1. 顶部导航布局

```tsx
<header className="sticky top-0 z-50 bg-white border-b border-gray-200">
  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div className="flex justify-between items-center h-16">
      {/* Logo */}
      {/* Nav Links */}
      {/* Actions */}
    </div>
  </div>
</header>
```

### 2. 侧边栏布局

```tsx
<div className="flex min-h-screen">
  {/* Sidebar */}
  <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:fixed lg:inset-y-0">
    {/* Sidebar Content */}
  </aside>

  {/* Main Content */}
  <main className="lg:pl-64">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Page Content */}
    </div>
  </main>
</div>
```

### 3. 卡片网格布局

```tsx
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
  {/* Cards */}
</div>
```

## 响应式隐藏/显示

| 场景 | 类名 |
|------|------|
| 仅 mobile 显示 | `block sm:hidden` |
| 仅 desktop 显示 | `hidden lg:block` |
| mobile 隐藏 | `hidden sm:block` |
| tablet+ 显示 | `hidden md:block` |

## Typography 响应式

| 元素 | Mobile | Desktop |
|------|--------|---------|
| H1 | 2xl (24px) | 4xl (36px) |
| H2 | xl (20px) | 3xl (30px) |
| H3 | lg (18px) | 2xl (24px) |
| Body | base (16px) | base (16px) |
| Small | sm (14px) | sm (14px) |

```tsx
<h1 className="text-2xl sm:text-4xl font-bold tracking-tight">
  响应式标题
</h1>
```

## 移动端适配

### 1. 点击目标尺寸

```css
/* 所有可点击元素最小 44x44px */
button, a, [onClick] {
  min-height: 44px;
  min-width: 44px;
}
```

### 2. 防止水平滚动

```css
/* 禁止水平溢出 */
body {
  overflow-x: hidden;
}
```

### 3. 安全区域

```css
/* iOS notch 和 home indicator */
body {
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
}
```

## CSS 变量输出

```css
/* src/styles/tokens.css */
:root {
  /* 颜色 */
  --color-primary: #3B82F6;
  --color-primary-hover: #2563EB;
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F8FAFC;
  --color-text-primary: #0F172A;
  --color-text-secondary: #475569;
  --color-border-default: #E2E8F0;

  /* 间距 */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;

  /* 圆角 */
  --radius-md: 0.375rem;
  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;

  /* 阴影 */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.1);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);

  /* 断点 */
  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
}
```

## Tailwind 配置

```javascript
// tailwind.config.js
module.exports = {
  content: [
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  darkMode: 'class',  // 或 'media' 跟随系统
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: 'var(--color-primary)',
          hover: 'var(--color-primary-hover)',
        },
      },
      spacing: {
        1: 'var(--space-1)',
        2: 'var(--space-2)',
        // ...
      },
      borderRadius: {
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
    },
  },
  plugins: [],
}
```

## 评审清单

- [ ] 使用 5 个标准断点 (sm/md/lg/xl/2xl)
- [ ] 12 列栅格系统
- [ ] 响应式边距和间距
- [ ] 移动端点击目标 ≥ 44x44px
- [ ] 防止水平溢出
- [ ] 支持深色模式
- [ ] 所有间距使用 Design Tokens
- [ ] 所有颜色使用 CSS 变量
