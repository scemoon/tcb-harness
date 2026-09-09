# Design Tokens — 设计原子

Design Tokens 是设计系统的最小原子单元，通过 CSS 变量形式输出，确保多端一致性。

## 色彩系统 (Color Tokens)

### 语义色 (Semantic Colors)

| Token | Light Mode | Dark Mode | 用途 |
|-------|------------|-----------|------|
| `--color-bg-primary` | `#FFFFFF` | `#0F172A` | 主背景 |
| `--color-bg-secondary` | `#F8FAFC` | `#1E293B` | 次级背景 |
| `--color-bg-tertiary` | `#F1F5F9` | `#334155` | 卡片/容器背景 |
| `--color-bg-inverse` | `#0F172A` | `#FFFFFF` | 反色背景 |
| `--color-text-primary` | `#0F172A` | `#F8FAFC` | 主文字 |
| `--color-text-secondary` | `#475569` | `#94A3B8` | 次级文字 |
| `--color-text-tertiary` | `#94A3B8` | `#64748B` | 弱化文字 |
| `--color-text-inverse` | `#FFFFFF` | `#0F172A` | 反色文字 |
| `--color-text-disabled` | `#CBD5E1` | `#475569` | 禁用文字 |
| `--color-border-default` | `#E2E8F0` | `#334155` | 默认边框 |
| `--color-border-strong` | `#94A3B8` | `#64748B` | 强调边框 |
| `--color-border-focus` | `#3B82F6` | `#60A5FA` | 聚焦边框 |

### 功能色 (Functional Colors)

| Token | Light Mode | Dark Mode | 用途 |
|-------|------------|-----------|------|
| `--color-primary` | `#3B82F6` | `#60A5FA` | 主操作/链接 |
| `--color-primary-hover` | `#2563EB` | `#3B82F6` | 主色悬停 |
| `--color-primary-active` | `#1D4ED8` | `#2563EB` | 主色按下 |
| `--color-primary-subtle` | `#EFF6FF` | `#1E3A5F` | 主色浅底 |
| `--color-secondary` | `#64748B` | `#94A3B8` | 次级操作 |
| `--color-secondary-hover` | `#475569` | `#7C8DA5` | 次色悬停 |
| `--color-success` | `#10B981` | `#34D399` | 成功状态 |
| `--color-success-subtle` | `#ECFDF5` | `#064E3B` | 成功浅底 |
| `--color-danger` | `#EF4444` | `#F87171` | 错误/危险 |
| `--color-danger-hover` | `#DC2626` | `#EF4444` | 危险悬停 |
| `--color-danger-subtle` | `#FEF2F2` | `#450A0A` | 危险浅底 |
| `--color-warning` | `#F59E0B` | `#FBBF24` | 警告状态 |
| `--color-warning-subtle` | `#FFFBEB` | `#451A03` | 警告浅底 |
| `--color-info` | `#06B6D4` | `#22D3EE` | 信息状态 |
| `--color-info-subtle` | `#ECFEFF` | `#083344` | 信息浅底 |

### 状态色 (State Colors)

| Token | 用途 |
|-------|------|
| `--color-overlay` | 遮罩层 (rgba(0,0,0,0.5)) |
| `--color-skeleton` | 骨架屏占位 |
| `--color-skeleton-shine` | 骨架屏动画 |

## 字体系统 (Typography Tokens)

### 字体家族

| Token | 值 | 用途 |
|-------|---|------|
| `--font-family-sans` | `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | 主字体 |
| `--font-family-mono` | `"JetBrains Mono", "Fira Code", Consolas, monospace` | 代码字体 |
| `--font-family-emoji` | `"Apple Color Emoji", "Segoe UI Emoji", sans-serif` | Emoji |

### 字体大小 (Font Size)

| Token | 值 | 用途 |
|-------|---|------|
| `--font-size-xs` | `0.75rem` (12px) | 辅助文字 |
| `--font-size-sm` | `0.875rem` (14px) | 次要文字 |
| `--font-size-base` | `1rem` (16px) | 正文 |
| `--font-size-lg` | `1.125rem` (18px) | 标题 |
| `--font-size-xl` | `1.25rem` (20px) | 小标题 |
| `--font-size-2xl` | `1.5rem` (24px) | 页面标题 |
| `--font-size-3xl` | `1.875rem` (30px) | 大标题 |
| `--font-size-4xl` | `2.25rem` (36px) | 主标题 |

### 字体粗细 (Font Weight)

| Token | 值 | 用途 |
|-------|---|------|
| `--font-weight-normal` | `400` | 正文 |
| `--font-weight-medium` | `500` | 强调 |
| `--font-weight-semibold` | `600` | 标题 |
| `--font-weight-bold` | `700` | 重点 |

### 行高 (Line Height)

| Token | 值 | 用途 |
|-------|---|------|
| `--line-height-tight` | `1.25` | 标题 |
| `--line-height-normal` | `1.5` | 正文 |
| `--line-height-relaxed` | `1.75` | 长文本 |

## 间距系统 (Spacing Tokens)

基准: 4px

| Token | 值 | REM | 用途 |
|-------|-----|-----|------|
| `--space-0` | `0` | 0 | 无间距 |
| `--space-1` | `4px` | 0.25rem | 紧密间距 |
| `--space-2` | `8px` | 0.5rem | 小间距 |
| `--space-3` | `12px` | 0.75rem | 中小间距 |
| `--space-4` | `16px` | 1rem | 中间距 |
| `--space-5` | `20px` | 1.25rem | 中大间距 |
| `--space-6` | `24px` | 1.5rem | 大间距 |
| `--space-8` | `32px` | 2rem | 较大间距 |
| `--space-10` | `40px` | 2.5rem | 大间距 |
| `--space-12` | `48px` | 3rem | 很大间距 |
| `--space-16` | `64px` | 4rem | 巨大间距 |
| `--space-20` | `80px` | 5rem | 超大间距 |
| `--space-24` | `96px` | 6rem | 最大间距 |

## 圆角系统 (Border Radius Tokens)

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-none` | `0` | 无圆角 |
| `--radius-sm` | `0.125rem` (2px) | 小圆角 |
| `--radius-md` | `0.375rem` (6px) | 中圆角 |
| `--radius-lg` | `0.5rem` (8px) | 大圆角 |
| `--radius-xl` | `0.75rem` (12px) | 特大圆角 |
| `--radius-2xl` | `1rem` (16px) | 超大圆角 |
| `--radius-full` | `9999px` | 全圆角 (胶囊) |

## 阴影系统 (Shadow Tokens)

| Token | 值 | 用途 |
|-------|-----|------|
| `--shadow-xs` | `0 1px 2px rgba(0,0,0,0.05)` | 极轻阴影 |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)` | 小阴影 |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06)` | 中阴影 |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)` | 大阴影 |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04)` | 特大阴影 |
| `--shadow-2xl` | `0 25px 50px rgba(0,0,0,0.25)` | 最大阴影 |
| `--shadow-inner` | `inset 0 2px 4px rgba(0,0,0,0.06)` | 内阴影 |
| `--shadow-none` | `none` | 无阴影 |

## 动效系统 (Motion Tokens)

### 时长 (Duration)

| Token | 值 | 用途 |
|-------|-----|------|
| `--duration-instant` | `0ms` | 即时 |
| `--duration-fast` | `100ms` | 快速过渡 |
| `--duration-normal` | `200ms` | 正常过渡 |
| `--duration-slow` | `300ms` | 慢速过渡 |
| `--duration-slower` | `500ms` | 更慢 |
| `--duration slowest` | `700ms` | 最慢 |

### 缓动曲线 (Easing)

| Token | 值 | 用途 |
|-------|-----|------|
| `--ease-linear` | `linear` | 线性 (进度条) |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | 缓入 |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | 缓出 |
| `--ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | 缓入缓出 |
| `--ease-bounce` | `cubic-bezier(0.68, -0.55, 0.265, 1.55)` | 弹性 |

## 图标尺寸 (Icon Size)

| Token | 值 | 用途 |
|-------|-----|------|
| `--icon-size-xs` | `12px` | 紧凑图标 |
| `--icon-size-sm` | `16px` | 小图标 |
| `--icon-size-md` | `20px` | 中图标 |
| `--icon-size-lg` | `24px` | 大图标 |
| `--icon-size-xl` | `32px` | 加大图标 |
| `--icon-size-2xl` | `48px` | 超大图标 |

## Z-Index 层级

| Token | 值 | 用途 |
|-------|-----|------|
| `--z-base` | `0` | 基础层级 |
| `--z-dropdown` | `100` | 下拉菜单 |
| `--z-sticky` | `200` | 粘性定位 |
| `--z-fixed` | `300` | 固定定位 |
| `--z-modal-backdrop` | `400` | 模态遮罩 |
| `--z-modal` | `500` | 模态框 |
| `--z-popover` | `600` | 气泡提示 |
| `--z-tooltip` | `700` | 工具提示 |
| `--z-toast` | `800` | 吐司通知 |

## 使用规范

1. **必须使用 CSS 变量**: 所有 token 必须通过 CSS 变量引用，禁止硬编码
2. **语义化命名**: 优先使用语义色 (`--color-text-primary`)，避免使用视觉色 (`--color-blue-500`)
3. **主题适配**: 深色模式通过 CSS 变量覆盖实现，无需改变组件代码
4. **输出格式**: 所有 token 必须以 CSS Custom Properties 格式输出到 `packages/shared/tokens/`
