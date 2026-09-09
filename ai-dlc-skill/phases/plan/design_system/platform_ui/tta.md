# TTA UI 规范 — 抖音小程序

抖音小程序 UI 规范，基于字节跳动组件库。

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 抖音原生 / uni-app | 推荐 uni-app (跨端) |
| UI 组件库 | 字节官方组件库 / Vant | 字节官方为默认 |
| 语言 | TypeScript | 必选 |
| 样式 | CSS / Sass | - |
| 状态管理 | mobx-miniprogram | 推荐 |

## 字节跳动组件库

### 安装

```bash
npm i @bytedance/mini-platform-plugin-components -S --production
```

### app.json 配置

```json
{
  "usingComponents": {
    "tta-button": "@bytedance/moni-ui/es/button/index",
    "tta-cell": "@bytedance/moni-ui/es/cell/index",
    "tta-field": "@bytedance/moni-ui/es/field/index",
    "tta-icon": "@bytedance/moni-ui/es/icon/index",
    "tta-toast": "@bytedance/moni-ui/es/toast/index",
    "tta-modal": "@bytedance/moni-ui/es/modal/index"
  }
}
```

## 颜色规范

### 字节跳动主题色

```css
/* app.ttss */
page {
  --color-primary: #333333;
  --color-success: #07c160;
  --color-warning: #ff9500;
  --color-danger: #fc5531;
  --color-info: #4a90e2;
  --color-text-base: #333333;
  --color-text-primary: #333333;
  --color-text-secondary: #666666;
  --color-text-disabled: #cccccc;
  --color-border: #e5e5e5;
  --color-bg: #f5f5f5;
  --color-bg-base: #ffffff;
  --radius-sm: 4rpx;
  --radius-md: 8rpx;
  --radius-lg: 16rpx;
  --radius-full: 999rpx;
}
```

## 字体规范

| 用途 | 字号 | 行高 |
|------|------|------|
| 标题 (H1) | 40rpx | 56rpx |
| 标题 (H2) | 36rpx | 52rpx |
| 标题 (H3) | 32rpx | 48rpx |
| 正文 | 30rpx | 44rpx |
| 小字 | 26rpx | 36rpx |
| 辅助文字 | 24rpx | 32rpx |

```css
/* 字体变量 */
page {
  --font-size-xs: 24rpx;
  --font-size-sm: 26rpx;
  --font-size-base: 30rpx;
  --font-size-lg: 32rpx;
  --font-size-xl: 36rpx;
  --font-size-xxl: 40rpx;
}
```

## 间距规范

| 名称 | 值 | 用途 |
|------|-----|------|
| xs | 8rpx | 紧凑间距 |
| sm | 16rpx | 小间距 |
| md | 24rpx | 中间距 |
| lg | 32rpx | 大间距 |
| xl | 48rpx | 较大间距 |

## 常用组件使用规范

### Button

```xml
<button type="primary" size="lg" block>
  主要按钮
</button>

<button type="default" size="md" loading="{{loading}}">
  默认按钮
</button>

<button type="danger" size="sm" disabled>
  禁用
</button>
```

| type | 用途 |
|------|------|
| primary | 主操作 (黑色 #333333) |
| default | 次操作 (白色) |
| success | 成功操作 (绿色) |
| danger | 危险操作 (红色) |
| warning | 警告操作 (橙色) |

### Cell 单元格

```xml
<cell-group>
  <cell title="单元格" value="内容" isLink="{{true}}" bind:click="onCellClick" />
  <cell title="单元格" description="描述信息" border="{{false}}" />
</cell-group>
```

### Field 输入框

```xml
<input
  value="{{value}}"
  placeholder="请输入"
  type="{{ type }}"
  disabled="{{ disabled }}"
  bind:input="onInput"
  bind:blur="onBlur"
/>
```

### 页面结构

```xml
<!-- 标准页面结构 -->
<view class="page">
  <!-- 标题栏 -->
  <navigation-bar title="标题" back="{{true}}" onBack="onBack" />

  <!-- 内容区 -->
  <scroll-view class="page-content" scroll-y>
    <!-- 页面内容 -->
  </scroll-view>

  <!-- 底部操作栏 -->
  <view class="page-footer">
    <button type="primary" block>确认</button>
  </view>
</view>
```

```css
/* page.ttss */
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg);
}

.page-content {
  flex: 1;
  padding: 32rpx;
}

.page-footer {
  padding: 24rpx 32rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  background-color: var(--color-bg-base);
}
```

## 分包加载规范

### app.json 配置

```json
{
  "subpackages": [
    {
      "root": "pages/order",
      "pages": [
        { "path": "list/index", "name": "order-list" },
        { "path": "detail/index", "name": "order-detail" }
      ]
    }
  ]
}
```

## API 请求规范

```typescript
// request.ts
interface RequestOptions {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: any;
  header?: object;
}

const BASE_URL = 'https://api.example.com';

const request = (options: RequestOptions) => {
  return new Promise((resolve, reject) => {
    tt.request({
      url: BASE_URL + options.url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': tt.getStorageSync('token'),
        ...options.header,
      },
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data);
        } else {
          reject(res);
        }
      },
      fail: reject,
    });
  });
};
```

## 登录流程

```typescript
// login.ts
const login = async () => {
  // 1. 获取 code
  const { code } = await new Promise((resolve) => {
    tt.login({
      success: (res) => resolve(res),
    });
  });

  // 2. 发送到服务器换取 token
  const res = await request({
    url: '/auth/login',
    method: 'POST',
    data: { code, type: 'tiktok' },
  });

  // 3. 存储 token
  tt.setStorageSync('token', res.token);

  return res;
};
```

## 状态管理

```typescript
// store/user.ts
import { observable } from 'mobx-miniprogram';

export const userStore = observable({
  // 状态
  userInfo: null as UserInfo | null,
  token: '',

  // 计算属性
  get isLoggedIn() {
    return !!this.token;
  },

  // Actions
  setUserInfo(userInfo: UserInfo) {
    this.userInfo = userInfo;
  },

  setToken(token: string) {
    this.token = token;
  },
});
```

## 视频/直播相关规范

### 视频播放器

```xml
<video
  src="{{videoUrl}}"
  poster="{{posterUrl}}"
  controls="{{true}}"
  initial-time="0"
  autoplay="{{false}}"
  loop="{{false}}"
  muted="{{false}}"
  bind:play="onPlay"
  bind:pause="onPause"
  bind:ended="onEnded"
  bind:error="onError"
/>
```

### 直播组件

```xml
<live-player
  src="{{liveUrl}}"
  mode="live"
  autoplay="{{true}}"
  bind:statechange="onStateChange"
  bind:error="onError"
/>
```

### 视频封面

```xml
<view class="video-cover">
  <image src="{{coverUrl}}" mode="aspectFill" />
  <view class="play-btn" bind:tap="onPlay">
    <icon type="play" size="48rpx" />
  </view>
  <view class="duration">{{duration}}</view>
</view>
```

## 样式规范

### BEM 命名

```css
/* Block */
.goods-card {
  /* Element */
}

.goods-card__image {
  /* Modifier */
}

.goods-card__image--large {
}
```

### 常用类名

| 类名 | 用途 |
|------|------|
| `.container` | 页面容器 |
| `.flex` | flex 布局 |
| `.flex-row` | 水平排列 |
| `.flex-col` | 垂直排列 |
| `.flex-center` | 居中 |
| `.flex-between` | 两端对齐 |
| `.gap-xs` | 极小间距 |
| `.gap-sm` | 小间距 |
| `.gap-md` | 中间距 |
| `.text-center` | 居中文字 |
| `.text-primary` | 主要文字 |
| `.text-secondary` | 次要文字 |
| `.text-ellipsis` | 单行省略 |

## 安全规范

- `openid` / `unionid` 不得明文暴露在 log 中
- 用户信息获取必须通过 `tt.getUserInfo()`
- 支付相关逻辑必须在后端完成签名
- 敏感数据存储用加密，不存明文 token
- 视频/直播内容需符合抖音审核规范

## 评审清单

- [ ] 使用字节跳动官方组件库
- [ ] 主题色通过 CSS 变量覆盖
- [ ] 字体使用 rpx 单位
- [ ] 页面结构符合标准布局
- [ ] 分包加载策略正确 (主包 ≤ 2MB)
- [ ] API 请求统一封装
- [ ] 登录流程安全 (使用 code)
- [ ] 状态管理使用 mobx-miniprogram
- [ ] 所有敏感数据加密存储
- [ ] 视频/直播组件符合规范
- [ ] 支持暗色模式 (如需要)
