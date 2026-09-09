# Accessibility — 可访问性规范

所有 UI 组件必须符合 WCAG 2.1 AA 标准，确保残障人士可正常使用。

## WCAG 2.1 核心标准

| 原则 | 级别 | 要求 |
|------|------|------|
| **可感知** | A | 文本替代、媒体字幕、适应性内容 |
| **可操作** | A | 键盘可访问、无陷阱、足够时间 |
| **可理解** | A | 语言可读、可预测、输入帮助 |
| **健壮** | A | 兼容性、状态可访问性 |

### 对比度要求

| 内容类型 | AA 标准 | AAA 标准 |
|----------|---------|----------|
| 正常文本 (<18px / <14px bold) | 4.5:1 | 7:1 |
| 大文本 (≥18px / ≥14px bold) | 3:1 | 4.5:1 |
| UI 组件/图形 | 3:1 | 3:1 |

### 字体大小规范

```css
/* 最小可访问字体 */
--font-size-min-accessible: 14px;  /* 正常文本 */
--font-size-min-accessible-large: 18px;  /* 大文本 */
```

## 焦点管理 (Focus Management)

### Focus Ring 规范

```css
/* 所有可交互元素的 focus ring */
:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 2px;
}

/* 移除默认 focus ring */
:focus:not(:focus-visible) {
  outline: none;
}
```

### 焦点顺序

```markdown
### Tab 顺序规则
1. 逻辑顺序: 从左到右，从上到下
2. 焦点顺序必须与视觉顺序一致
3. 模态弹窗必须捕获焦点 (focus trap)
4. 关闭弹窗后焦点需返回触发元素
5. 跳过链接 (#main-content) 必须是第一个可聚焦元素
```

### 焦点陷阱 (Focus Trap)

```typescript
// Modal / Dialog 必须实现焦点陷阱
const focusTrap = (container: HTMLElement) => {
  const focusable = container.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0] as HTMLElement;
  const last = focusable[focusable.length - 1] as HTMLElement;

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  container.addEventListener('keydown', handleKeyDown);
  first?.focus();
};
```

## 键盘导航 (Keyboard Navigation)

### 标准键盘交互

| Key | 组件 | 行为 |
|-----|------|------|
| Tab | 全局 | 移动到下一个可聚焦元素 |
| Shift+Tab | 全局 | 移动到上一个可聚焦元素 |
| Enter | Button / Link | 激活 |
| Space | Button / Checkbox | 激活 / 切换 |
| Escape | Modal / Dropdown | 关闭 |
| Arrow Up/Down | Menu / Select | 上下导航 |
| Arrow Left/Right | Tab / Slider | 左右切换 |

### 可交互元素最小集合

```markdown
必须可键盘操作:
- [ ] 所有 Button
- [ ] 所有 Link
- [ ] 所有 Input / Textarea
- [ ] 所有 Select
- [ ] 所有 Checkbox / Radio / Switch
- [ ] 所有 MenuItem
- [ ] 所有 Modal / Dialog
- [ ] 所有 Tooltip (可通过键盘触发)
```

## ARIA 规范

### ARIA 属性速查

| 属性 | 用途 | 示例 |
|------|------|------|
| aria-label | 为元素提供可访问名称 | `<button aria-label="关闭">X</button>` |
| aria-describedby | 关联描述元素 | `<input aria-describedby="hint-email">` |
| aria-required | 标记必填 | `<input aria-required="true">` |
| aria-invalid | 标记错误 | `<input aria-invalid="true">` |
| aria-disabled | 标记禁用 | `<button aria-disabled="true">` |
| aria-expanded | 展开/收起状态 | `<button aria-expanded="false">` |
| aria-hidden | 隐藏于屏幕阅读器 | `<span aria-hidden="true">icon</span>` |
| aria-live | 动态区域 | `<div aria-live="polite">result</div>` |
| aria-busy | 加载状态 | `<div aria-busy="true">` |
| aria-current | 当前项 | `<a aria-current="page">Home</a>` |
| role | 语义角色 | `<div role="dialog">` |

### 常见 ARIA 模式

```markdown
### Button vs Link
- Button: 执行操作 (onClick) → <button> 或 <div role="button">
- Link: 导航 → <a href>

### Form Field
<input
  id="email"
  type="email"
  aria-required="true"
  aria-invalid="false"
  aria-describedby="email-hint email-error"
/>
<span id="email-hint">用于接收验证码</span>
<span id="email-error" aria-live="polite"></span>

### Modal/Dialog
<div role="dialog" aria-modal="true" aria-labelledby="dialog-title">
  <h2 id="dialog-title">确认删除</h2>
  <p>确定要删除此项吗？</p>
  <button>取消</button>
  <button>确定</button>
</div>

### Tabs
<div role="tablist">
  <button role="tab" aria-selected="true" aria-controls="panel-1">Tab 1</button>
  <button role="tab" aria-selected="false" aria-controls="panel-2">Tab 2</button>
</div>
<div role="tabpanel" id="panel-1">Content 1</div>
<div role="tabpanel" id="panel-2" hidden>Content 2</div>
```

## 屏幕阅读器支持

### 必需内容

```markdown
### 图片
- 有意义图片: alt="描述内容"
- 装饰图片: alt="" (空)

### 图标
- 纯装饰图标: aria-hidden="true"
- 有意义图标: aria-label 或可见文字

### 动态内容
- 非紧急更新: aria-live="polite"
- 紧急警告: aria-live="assertive"
- Toast: role="status" 或 role="alert"

### 表单错误
- 错误提示必须关联到对应输入框 (aria-describedby)
- 错误必须可被屏幕阅读器即时读取
```

### 辅助技术测试清单

```markdown
- [ ] NVDA + Chrome 测试
- [ ] VoiceOver + Safari 测试
- [ ] JAWS + Chrome 测试 (可选)
```

## 运动与动画

### 减少运动 (Reduce Motion)

```css
/* 尊重用户减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 动画规范

| 类型 | 最大时长 | 缓动 |
|------|----------|------|
| 微交互 | 100-200ms | ease-out |
| 状态切换 | 200-300ms | ease-in-out |
| 展开/折叠 | 300-500ms | ease-in-out |
| 页面过渡 | 300-500ms | ease-in-out |

## 色彩相关

### 不应仅依赖颜色传达信息

```markdown
❌ 错误: 红色边框表示错误
✅ 正确: 红色边框 + 错误图标 + 错误文字 + aria-invalid

❌ 错误: 灰色表示禁用
✅ 正确: 灰色 + aria-disabled="true" + 鼠标事件禁用
```

## 移动端触摸

```markdown
### 触摸目标尺寸
- 最小: 44x44 CSS pixels (Apple) / 48x48 dp (Material Design)
- 推荐: 48x48 CSS pixels

### 触摸间距
- 相邻可触摸元素间距 ≥ 8px
- 防止误触相邻元素
```

## 法规与标准

| 标准 | 要求级别 |
|------|----------|
| WCAG 2.1 (A) | 强制 (MUST) |
| WCAG 2.1 (AA) | 推荐 (SHOULD) |
| WCAG 2.1 (AAA) | 可选 (MAY) |
| EN 301 549 (欧盟) | 政府采购 |
| Section 508 (美国) | 政府/公共机构 |

## 评审清单

- [ ] 所有文本对比度 ≥ 4.5:1 (AA)
- [ ] 所有 UI 组件对比度 ≥ 3:1 (AA)
- [ ] 所有交互元素可通过键盘操作
- [ ] 所有图标按钮有 aria-label
- [ ] 所有表单有错误提示和关联
- [ ] 模态框实现焦点陷阱
- [ ] 支持 prefers-reduced-motion
- [ ] 触摸目标 ≥ 44x44px
- [ ] 通过 axe-core 自动检测
- [ ] 通过屏幕阅读器手动测试
