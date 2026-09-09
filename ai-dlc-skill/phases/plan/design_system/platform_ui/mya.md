# MYA UI 规范 — 支付宝小程序

支付宝小程序 UI 规范，基于 Ant Design Mini 组件库。

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 支付宝原生 / uni-app | 推荐 uni-app (跨端) |
| UI 组件库 | Ant Design Mini | 默认 per skill.yaml |
| 语言 | TypeScript | 必选 |
| 样式 | CSS / Sass | - |
| 状态管理 | mobx-miniprogram | 推荐 |

## Ant Design Mini 组件规范

### 安装

```bash
npm i ant-design-mini -S --production
```

### app.json 配置

```json
{
  "usingComponents": {
    "ant-button": "ant-design-mini/es/Button/index",
    "ant-cell": "ant-design-mini/es/Cell/index",
    "ant-field": "ant-design-mini/es/Field/index",
    "ant-icon": "ant-design-mini/es/Icon/index",
    "ant-toast": "ant-design-mini/es/Toast/index",
    "ant-modal": "ant-design-mini/es/Modal/index",
    "ant-picker": "ant-design-mini/es/Picker/index",
    "ant-popup": "ant-design-mini/es/Popup/index"
  }
}
```

## 颜色规范

### Ant Design Mini 主题色

```css
/* app.acss */
page {
  --color-primary: #1677ff;
  --color-success: #00b578;
  --color-warning: #ff8f1a;
  --color-error: #ff3141;
  --color-disabled: #bfbfb5;
  --color-text-base: #323232;
  --color-text-secondary: #b2b2b2;
  --color-text-disabled: #bfbfbf;
  --color-text-placeholder: #b2b2b2;
  --color-border-base: #d9d9d9;
  --color-border-light: #e5e5e5;
  --color-border-outline: #b2b2b2;
  --color-fill-base: #f5f5f5;
  --color-fill-secondary: #fafafa;
  --color-bg-color: #ffffff;
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

<button type="warning" size="sm" disabled>
  禁用
</button>
```

| type | 用途 |
|------|------|
| primary | 主操作 (蓝色 #1677ff) |
| default | 次操作 (白色) |
| success | 成功操作 (绿色) |
| warning | 警告操作 (橙色) |
| danger | 危险操作 (红色) |

### Cell 单元格

```xml
<cell-group>
  <cell title="单元格" value="内容" isLink="{{true}}" onClick="onCellClick" />
  <cell title="单元格" brief="描述信息" border="{{false}}" />
</cell-group>
```

### Field 输入框

```xml
<field
  value="{{value}}"
  label="标签"
  placeholder="请输入"
  state="{{ state }}"
  onChange="onChange"
  onBlur="onBlur"
/>
```

### 页面结构

```xml
<!-- 标准页面结构 -->
<view class="page">
  <!-- 标题栏 -->
  <nav-bar title="标题" onLeftTap="onBack" />

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
/* page.acss */
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-color);
}

.page-content {
  flex: 1;
  padding: 32rpx;
}

.page-footer {
  padding: 24rpx 32rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  background-color: #fff;
}
```

## 分包加载规范

### app.json 配置

```json
{
  "subPackages": [
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
    my.request({
      url: BASE_URL + options.url,
      method: options.method || 'GET',
      data: options.data,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': my.getStorageSync({ key: 'token' }),
        ...options.header,
      },
      success: (res) => {
        if (res.status === 200) {
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
  // 1. 获取 authcode
  const { authCode } = await new Promise((resolve) => {
    my.getAuthCode({
      scopes: ['auth_user'],
      success: (res) => resolve(res),
    });
  });

  // 2. 发送到服务器换取 token
  const res = await request({
    url: '/auth/login',
    method: 'POST',
    data: { authCode },
  });

  // 3. 存储 token
  my.setStorageSync({ key: 'token', data: res.token });

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

- `user_id` / `open_id` 不得明文暴露在 log 中
- 用户信息获取必须通过 `my.getUserInfo()` 或 `my.getPhoneNumber()`
- 支付相关逻辑必须在后端完成签名
- 敏感数据存储用加密，不存明文 token

## 评审清单

- [ ] 使用 Ant Design Mini 组件库
- [ ] 主题色通过 CSS 变量覆盖
- [ ] 字体使用 rpx 单位
- [ ] 页面结构符合标准布局
- [ ] 分包加载策略正确 (主包 ≤ 2MB)
- [ ] API 请求统一封装
- [ ] 登录流程安全 (使用 authcode)
- [ ] 状态管理使用 mobx-miniprogram
- [ ] 所有敏感数据加密存储
- [ ] 支持暗色模式 (如需要)
