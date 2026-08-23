# Theme System — 主题系统

支持浅色/暗色模式切换，通过 CSS 变量实现，无需改变组件代码。

## 主题架构

```
ThemeProvider
  └── CSS Variables (in :root)
        ├── Light Theme (data-theme="light" or default)
        └── Dark Theme (data-theme="dark")
```

## CSS 变量定义

### 浅色主题 (Light)

```css
:root,
[data-theme="light"] {
  /* 背景色 */
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F8FAFC;
  --color-bg-tertiary: #F1F5F9;
  --color-bg-inverse: #0F172A;

  /* 文字色 */
  --color-text-primary: #0F172A;
  --color-text-secondary: #475569;
  --color-text-tertiary: #94A3B8;
  --color-text-inverse: #FFFFFF;
  --color-text-disabled: #CBD5E1;

  /* 边框色 */
  --color-border-default: #E2E8F0;
  --color-border-strong: #94A3B8;
  --color-border-focus: #3B82F6;

  /* 功能色 */
  --color-primary: #3B82F6;
  --color-primary-hover: #2563EB;
  --color-success: #10B981;
  --color-danger: #EF4444;
  --color-warning: #F59E0B;
  --color-info: #06B6D4;

  /* 阴影 (浅色主题更深) */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05);

  /* 遮罩 */
  --color-overlay: rgba(15, 23, 42, 0.5);
}
```

### 暗色主题 (Dark)

```css
[data-theme="dark"] {
  /* 背景色 */
  --color-bg-primary: #0F172A;
  --color-bg-secondary: #1E293B;
  --color-bg-tertiary: #334155;
  --color-bg-inverse: #FFFFFF;

  /* 文字色 */
  --color-text-primary: #F8FAFC;
  --color-text-secondary: #94A3B8;
  --color-text-tertiary: #64748B;
  --color-text-inverse: #0F172A;
  --color-text-disabled: #475569;

  /* 边框色 */
  --color-border-default: #334155;
  --color-border-strong: #64748B;
  --color-border-focus: #60A5FA;

  /* 功能色 (暗色主题稍亮) */
  --color-primary: #60A5FA;
  --color-primary-hover: #3B82F6;
  --color-success: #34D399;
  --color-danger: #F87171;
  --color-warning: #FBBF24;
  --color-info: #22D3EE;

  /* 阴影 (暗色主题更浅) */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.3), 0 2px 4px rgba(0,0,0,0.2);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.3), 0 4px 6px rgba(0,0,0,0.2);

  /* 遮罩 */
  --color-overlay: rgba(0, 0, 0, 0.7);
}
```

## 主题切换机制

### 1. 系统偏好 (默认)

```css
/* 自动跟随系统 */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* 暗色变量 */
  }
}
```

### 2. 手动切换

```typescript
// 切换主题
const toggleTheme = () => {
  const current = document.documentElement.dataset.theme;
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
};

// 初始化
const initTheme = () => {
  const saved = localStorage.getItem('theme');
  if (saved) {
    document.documentElement.dataset.theme = saved;
  }
};
```

### 3. 自动切换 (可选)

```typescript
// 监听系统主题变化
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  if (!localStorage.getItem('theme')) {
    document.documentElement.dataset.theme = e.matches ? 'dark' : 'light';
  }
});
```

## 主题配置

### ThemeProvider (React)

```typescript
interface ThemeProviderProps {
  defaultTheme?: 'light' | 'dark' | 'system';
  children: ReactNode;
}

const ThemeProvider: React.FC<ThemeProviderProps> = ({
  defaultTheme = 'system',
  children
}) => {
  useEffect(() => {
    const saved = localStorage.getItem('theme');
    if (saved) {
      document.documentElement.dataset.theme = saved;
    }
  }, []);

  return <>{children}</>;
};
```

### useTheme Hook

```typescript
const useTheme = () => {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (document.documentElement.dataset.theme as 'light' | 'dark') || 'light';
  });

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem('theme', next);
  };

  return { theme, setTheme, toggleTheme };
};
```

## 组件主题适配

### 正确方式

```tsx
// ✅ 使用 CSS 变量
const Button = styled.button`
  background: var(--color-primary);
  color: var(--color-text-inverse);
`;

// ✅ 使用 CSS 变量
const Card = styled.div`
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-default);
  box-shadow: var(--shadow-sm);
`;
```

### 错误方式

```tsx
// ❌ 硬编码颜色
const Button = styled.button`
  background: #3B82F6;  // 不允许
`;

// ❌ 硬编码阴影
const Card = styled.div`
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);  // 不允许
`;
```

## 图片与媒体

### 暗色模式图片变体

```css
/* 使用 CSS filter 简单处理 */
[data-theme="dark"] img {
  filter: brightness(0.9) contrast(1.1);
}

/* 或使用 picture 元素 */
<picture>
  <source srcset="/logo-dark.svg" media="(prefers-color-scheme: dark)">
  <img src="/logo-light.svg" alt="Logo">
</picture>
```

## 平台特殊处理

### Web

```css
/* 自动应用 */
:root {
  color-scheme: light dark;
}
```

### 小程序

```javascript
// app.ts
App({
  onThemeChange({ theme }) {
    this.globalData.theme = theme;
    // 通知所有页面
  }
});

// 页面中使用
Page({
  data: {
    isDark: false
  },
  onLoad() {
    const app = getApp<IAppOption>();
    this.setData({ isDark: app.globalData.theme === 'dark' });
  }
});
```

### Native (React Native)

```typescript
// 使用 @react-native-community Appearance
import { Appearance } from 'react-native';

const colorScheme = Appearance.getColorScheme();
// 'light' | 'dark' | null

// 监听变化
Appearance.addChangeListener(({ colorScheme }) => {
  // 更新状态
});
```

## 主题切换动画

```css
/* 主题切换平滑过渡 */
html {
  transition:
    background-color var(--duration-normal) var(--ease-in-out),
    color var(--duration-normal) var(--ease-in-out);
}

/* 排除有动画的元素 */
.no-transition {
  transition: none !important;
}
```

## 主题持久化

```typescript
// 存储优先级
1. localStorage.getItem('theme')  // 用户手动选择
2. prefers-color-scheme            // 系统偏好
3. 'light'                         // 默认
```

## 评审清单

- [ ] 所有颜色通过 CSS 变量使用
- [ ] 暗色主题覆盖完整 (背景/文字/边框/阴影/功能色)
- [ ] 主题切换无闪烁 (FOUC)
- [ ] 主题偏好持久化到 localStorage
- [ ] 组件在两种主题下都符合对比度要求
- [ ] 支持 prefers-color-scheme 媒体查询
- [ ] 主题切换有平滑过渡动画 (可选)
- [ ] 图片在暗色模式下无异常 (如需要)
