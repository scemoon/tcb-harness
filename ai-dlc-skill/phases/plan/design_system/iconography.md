# Iconography — 图标规范

图标是 UI 的重要视觉元素，必须统一管理和使用。

## 图标库选择

| 平台 | 推荐图标库 | 备选 |
|------|------------|------|
| **Web** | Heroicons | Lucide, Font Awesome, Feather |
| **Native** | SF Symbols (iOS) / Material Icons (Android) | React Native Vector Icons |
| **Desktop** | Lucide (Electron) / Native (Tauri) | - |
| **WXA** | Vant Weapp Icon | iconfont |
| **MYA** | Ant Design Mini Icon | - |
| **TTA** | 字节官方 icon | - |

## 图标尺寸规范

| Token | 值 | 用途 |
|-------|-----|------|
| `--icon-size-xs` | `12px` | 紧凑文字旁 (如 Badge 内) |
| `--icon-size-sm` | `16px` | 小尺寸 (如 List Item) |
| `--icon-size-md` | `20px` | 默认尺寸 (如 Button 内) |
| `--icon-size-lg` | `24px` | 大尺寸 (如 Empty State) |
| `--icon-size-xl` | `32px` | 加大 (如 Feature Card) |
| `--icon-size-2xl` | `48px` | 超大 (如导航图标) |

## 图标与文字比例

| 场景 | 图标尺寸 | 文字尺寸 | 间距 |
|------|----------|----------|------|
| Button 内 | 16-20px | 14-16px | 8px |
| Input 内 | 16px | 14px | 8px |
| List Item | 16-20px | 14px | 8-12px |
| Card 标题 | 20-24px | 16-18px | 8px |
| 导航菜单 | 24px | 14px | 12px |
| Empty State | 48-64px | 14px | 16px |

## 图标 Stroke 规范

| 场景 | Stroke Width | 用途 |
|------|--------------|------|
| 细线图标 | 1.5px | 紧凑布局 |
| 标准图标 | 2px | 默认 |
| 粗线图标 | 2.5px | 强调 |

```css
/* Heroicons outline 样式 */
.icon {
  width: var(--icon-size-md);
  height: var(--icon-size-md);
  stroke-width: 2;
  stroke: currentColor;
  fill: none;
}
```

## SVG 图标使用规范

### 正确使用方式

```tsx
// ✅ 使用 SVG 组件
import { BeakerIcon } from '@heroicons/react/24/outline';

<BeakerIcon className="h-5 w-5" />

// ✅ 定制颜色
<BeakerIcon className="h-5 w-5 text-blue-500" />

// ✅ 定制尺寸
<BeakerIcon className="h-8 w-8" />

// ✅ 使用当前文字颜色
<BeakerIcon className="h-5 w-5" style={{ color: 'var(--color-text-secondary)' }} />
```

### 错误使用方式

```tsx
// ❌ 硬编码颜色
<BeakerIcon className="h-5 w-5 text-gray-500" />

// ❌ 使用 img 标签
<img src="/icons/beaker.svg" alt="Beaker" />

// ❌ 使用 font-icon (如 Font Awesome)
<i className="fas fa-beaker"></i>

// ❌ 缺少 aria-label
<BeakerIcon />  // 可访问性缺失
```

## 图标分类

### 操作类图标

| 图标名 | 用途 | 示例 |
|--------|------|------|
| plus | 添加 | 新建、添加 |
| minus | 移除 | 删除、减少 |
| x-mark | 关闭 | 关闭弹窗 |
| check | 确认 | 勾选、完成 |
| pencil | 编辑 | 编辑内容 |
| trash | 删除 | 删除操作 |
| arrow-right | 导航 | 下一页、下一步 |
| arrow-left | 返回 | 返回、上一页 |
| magnifying-glass | 搜索 | 搜索按钮 |

### 状态类图标

| 图标名 | 用途 |
|--------|------|
| check-circle | 成功状态 |
| exclamation-circle | 警告状态 |
| x-circle | 错误状态 |
| information-circle | 信息状态 |
| clock | 加载中 |
| spinner (动画) | 加载中 |

### 导航类图标

| 图标名 | 用途 |
|--------|------|
| home | 首页 |
| user | 个人中心 |
| cog (settings) | 设置 |
| bell | 通知 |
| envelope | 消息 |
| shopping-cart | 购物车 |

### 业务类图标

| 图标名 | 用途 |
|--------|------|
| currency-dollar | 支付相关 |
| chart-bar | 统计 |
| photo | 图片相关 |
| document | 文档 |
| folder | 文件夹 |
| cloud-arrow-up | 上传 |

## 可访问性

### 装饰性图标

```tsx
// ✅ 装饰性图标 - 屏幕阅读器忽略
<button>
  <BeakerIcon className="h-5 w-5" aria-hidden="true" />
  <span>Add Item</span>
</button>
```

### 含义性图标

```tsx
// ✅ 有含义的图标 - 必须有 aria-label
<button aria-label="Search">
  <MagnifyingGlassIcon className="h-5 w-5" />
</button>

// ✅ 配合文字说明
<button aria-describedby="search-hint">
  <MagnifyingGlassIcon className="h-5 w-5" aria-hidden="true" />
</button>
<span id="search-hint" className="sr-only">搜索商品</span>
```

### 屏幕阅读器专用文本

```css
/* .sr-only: 仅屏幕阅读器可见 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

## 图标动画

### Loading Spinner

```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.animate-spin {
  animation: spin 1s linear infinite;
}
```

### 图标过渡

```css
/* 悬停时图标位移 */
.button:hover .icon {
  transform: translateX(2px);
  transition: transform var(--duration-fast) var(--ease-out);
}

/* 悬停时图标颜色变化 */
.button:hover .icon {
  color: var(--color-primary-hover);
}
```

## 平台特殊处理

### Web (React)

```tsx
// 使用 Heroicons
import { IconName } from '@heroicons/react/24/outline';

<IconName className="h-5 w-5" aria-hidden="true" />
```

### Native (React Native)

```tsx
// iOS - SF Symbols
import { SFSymbol } from 'react-native-sfsymbols';

// Android - Material Icons
import Icon from 'react-native-vector-icons/MaterialIcons';

// 通用
import { Ionicons } from '@expo/vector-icons';  // 跨平台
```

### 小程序

```xml
<!-- WXA / MYA / TTA - 使用 Vant Weapp Icon -->
<van-icon name="success" />

<!-- 或使用 iconfont -->
<view class="iconfont icon-success"></view>
```

## 图标文件命名

```
icons/
├── outline/           # 线框风格
│   ├── arrow-right.svg
│   ├── check.svg
│   └── ...
├── solid/             # 实心风格
│   ├── arrow-right.svg
│   ├── check.svg
│   └── ...
└── custom/            # 自定义业务图标
    ├── logo.svg
    ├── brand-icon.svg
    └── ...
```

## 图标管理规则

| 规则 | 说明 |
|------|------|
| 单一来源 | 只从指定图标库引入，不混用 |
| 全局注册 | 图标组件全局注册，按需引入 |
| 禁止新增 | 不随意新增图标，优先复用现有 |
| 统一尺寸 | 使用规范的 6 个尺寸 |
| 统一 stroke | stroke-width 统一为 2px (outline) |
| 支持颜色 | 图标颜色必须可通过 CSS 变量控制 |
| 支持旋转 | loading 类图标支持动画 |

## 常用图标清单 (Web)

```
基础操作: plus, minus, x-mark, check, pencil, trash, share, download, upload
导航箭头: arrow-right, arrow-left, arrow-up, arrow-down, chevron-right
状态: check-circle, x-circle, exclamation-circle, information-circle
通用: home, user, cog, bell, envelope, search, heart, star
业务: currency-dollar, chart-bar, photo, document, folder, cloud
```

## 评审清单

- [ ] 只使用指定的图标库
- [ ] 所有图标尺寸符合 6 档规范
- [ ] stroke-width 统一为 2px (outline)
- [ ] 装饰性图标有 aria-hidden="true"
- [ ] 含义性图标有 aria-label
- [ ] 图标颜色通过 currentColor 或 CSS 变量设置
- [ ] loading 图标有 spin 动画
- [ ] 图标文件按 outline/solid/custom 分类
