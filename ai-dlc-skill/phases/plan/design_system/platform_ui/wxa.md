# WXA UI 规范 — 微信小程序

微信小程序 UI 规范，基于 Vant Weapp 组件库。

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 微信原生 / Taro / uni-app | 推荐 Taro (跨端) |
| UI 组件库 | Vant Weapp | 默认 per skill.yaml |
| 语言 | TypeScript | 必选 |
| 样式 | CSS / Sass | - |
| 状态管理 | mobx-miniprogram | 推荐 |

## Vant Weapp 组件规范

### 安装

```bash
npm i @vant/weapp -S --production
```

### app.json 配置

```json
{
  "usingComponents": {
    "van-button": "@vant/weapp/button/index",
    "van-cell": "@vant/weapp/cell/index",
    "van-cell-group": "@vant/weapp/cell-group/index",
    "van-field": "@vant/weapp/field/index",
    "van-icon": "@vant/weapp/icon/index",
    "van-toast": "@vant/weapp/toast/index",
    "van-dialog": "@vant/weapp/dialog/index",
    "van-notify": "@vant/weapp/notify/index",
    "van-picker": "@vant/weapp/picker/index",
    "van-popup": "@vant/weapp/popup/index",
    "van-transition": "@vant/weapp/transition/index"
  }
}
```

## 颜色规范

### Vant Weapp 主题色

```css
/* app.wxss */
page {
  --primary-color: #1989fa;
  --success-color: #07c160;
  --danger-color: #ee0a24;
  --warning-color: #ff976a;
  --gray-color: #323233;
  --text-color: #323233;
  --text-primary: #323233;
  --text-second: #969799;
  --text-disabled: #c8c9cc;
  --background-color: #f7f8fa;
  --background: #f7f8fa;
  --border-color: #ebedf0;
  --border: #ebedf0;
  --divider-color: #ebedf0;
  --radius-md: 8rpx;
  --radius-lg: 16rpx;
  --radius-squared: 8rpx;
}
```

## 字体规范

| 用途 | 字号 | 行高 |
|------|------|------|
| 标题 (H1) | 32rpx | 40rpx |
| 标题 (H2) | 28rpx | 36rpx |
| 标题 (H3) | 24rpx | 32rpx |
| 正文 | 28rpx | 40rpx |
| 小字 | 24rpx | 32rpx |
| 辅助文字 | 20rpx | 28rpx |

```css
/* 字体变量 */
page {
  --font-size-xs: 20rpx;
  --font-size-sm: 24rpx;
  --font-size-base: 28rpx;
  --font-size-lg: 32rpx;
  --font-size-xl: 36rpx;
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
<van-button type="primary" size="large" block>
  主要按钮
</van-button>

<van-button type="default" size="normal" loading="{{loading}}">
  默认按钮
</van-button>

<van-button type="warning" size="small" disabled>
  禁用
</van-button>
```

| type | 用途 |
|------|------|
| primary | 主操作 (蓝色) |
| default | 次操作 |
| warning | 警告操作 (橙色) |
| danger | 危险操作 (红色) |
| info | 信息 (灰色) |

### Cell 单元格

```xml
<van-cell-group>
  <van-cell title="单元格" value="内容" is-link url="/pages/detail/index" />
  <van-cell title="单元格" label="描述信息" border="{{false}}" />
</van-cell-group>
```

### Field 输入框

```xml
<van-field
  value="{{ value }}"
  label="标签"
  placeholder="请输入"
  error="{{ error }}"
  disabled="{{ disabled }}"
  bind:change="onChange"
  bind:blur="onBlur"
/>
```

### 页面结构

```xml
<!-- 标准页面结构 -->
<view class="page">
  <!-- 标题栏 -->
  <van-nav-bar title="标题" left-arrow bind:click-left="onBack" />

  <!-- 内容区 -->
  <view class="page-content">
    <!-- 页面内容 -->
  </view>

  <!-- 底部操作栏 -->
  <view class="page-footer">
    <van-button type="primary" block>确认</van-button>
  </view>
</view>
```

```css
/* page.wxss */
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--background-color);
}

.page-content {
  flex: 1;
  padding: 32rpx;
}

.page-footer {
  padding: 24rpx 32rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  background-color: #fff;
  box-shadow: 0 -2rpx 12rpx rgba(0, 0, 0, 0.05);
}
```

## 分包加载规范

### 主包结构

```
pages/
├── index/           # 首页
├── user/            # 用户中心
└── ...              # 其他核心页面
```

### 分包结构

```
subpackages/
├── goods/           # 商品模块
│   ├── list/        # 商品列表
│   └── detail/      # 商品详情
├── order/           # 订单模块
│   ├── list/        # 订单列表
│   └── detail/      # 订单详情
└── ...
```

### app.json 配置

```json
{
  "subpackages": [
    {
      "root": "subpackages/goods",
      "pages": [
        { "path": "list/index", "name": "goods-list" },
        { "path": "detail/index", "name": "goods-detail" }
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
    wx.request({
      url: BASE_URL + options.url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': wx.getStorageSync('token'),
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
  const { code } = await wx.login();

  // 2. 发送到服务器换取 token
  const res = await request({
    url: '/auth/login',
    method: 'POST',
    data: { code },
  });

  // 3. 存储 token
  wx.setStorageSync('token', res.token);

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
| `.gap-sm` | 小间距 |
| `.gap-md` | 中间距 |
| `.text-center` | 居中文字 |
| `.text-primary` | 主要文字 |
| `.text-secondary` | 次要文字 |
| `.text-ellipsis` | 单行省略 |
| `.text-ellipsis-2` | 两行省略 |

## 安全规范

- `openid` / `unionid` 不得明文暴露在 log 中
- 用户信息获取必须通过 `wx.getUserProfile()`
- 支付相关逻辑必须在后端完成签名
- 敏感数据存储用加密，不存明文 token
- 域名必须在微信公众平台配置

## 评审清单

- [ ] 使用 Vant Weapp 组件库
- [ ] 主题色通过 CSS 变量覆盖
- [ ] 字体使用 rpx 单位
- [ ] 页面结构符合标准布局
- [ ] 分包加载策略正确 (主包 ≤ 2MB)
- [ ] API 请求统一封装
- [ ] 登录流程安全
- [ ] 状态管理使用 mobx-miniprogram
- [ ] 所有敏感数据加密存储
- [ ] 支持暗色模式 (如需要)
