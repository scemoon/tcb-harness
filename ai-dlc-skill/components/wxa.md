# WXA 组件开发指南 (WXA-FR-*) — 微信小程序

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 微信原生 / Taro / uni-app | 原生适合轻量；Taro/uni-app 适合多端复用 |
| 语言 | JavaScript / TypeScript | 推荐 TypeScript（类型安全） |
| UI 组件库 | Vant Weapp / WeUI / ColorUI | 默认 Vant Weapp（per skill.yaml） |
| 云服务 | 微信云开发 / TCB | TCB 为默认云 provider |
| 构建 | 微信开发者工具 / Taro CLI / Vite | Taro 项目用 CLI，原生用开发者工具 |
| 测试 | Jest / miniprogram-simtest | 单元测试用 Jest |
| 自动化 | miniprogram-automator | UI 自动化测试 |
| BDD | pytest-bdd + miniprogram-automator | E2E BDD 场景 |

## 计算模式

| 模式 | 类型 | 说明 |
|------|------|------|
| wx.cloud | 云开发 | 微信自带云能力，无需自建后端 |
| tcb | CloudBase | TCB 平台，FaaS 云函数 |
| 混合 | 微信云 + TCB | 微信云存储 + TCB 云函数 |

默认模式: `tcb`（TCB 平台，与其他组件统一）。

## 关键命令

```bash
# 构建
pnpm --filter wxa build

# 测试
pnpm --filter wxa test              # 单元测试
pytest apps/wxa/tests/e2e/ --backend-url $BACKEND_URL  # E2E BDD

# Lint
pnpm --filter wxa lint

# 预览（上传至微信小程序平台，获取预览二维码）
pnpm --filter wxa preview

# 分包构建（如使用分包）
pnpm --filter wxa build --type=plugin
```

## 目录约定

```
apps/wxa/
├── src/
│   ├── components/          # 业务组件
│   ├── pages/               # 页面（按分包组织）
│   ├── subpackages/         # 分包（主包超出 2MB 时拆离）
│   ├── services/            # API 调用层（统一用 BACKEND_URL）
│   ├── store/               # 状态管理（推荐 mobx-miniprogram）
│   ├── utils/               # 工具函数
│   ├── const/               # 常量（API 路由、错误码等）
│   └── app.js / app.json / app.wxss / app.ts   # 应用入口
├── tests/
│   ├── unit/                # Jest 单元测试
│   ├── integration/         # 集成测试
│   └── e2e/                 # BDD E2E（miniprogram-automator）
├── features/                # BDD Gherkin feature 文件
│   └── *.feature
├── mock/                    # 模拟数据（开发环境）
└── cloud/                   # 微信云函数 / TCB 云函数源码
```

## FR 命名空间

- Prefix: `WXA-FR-NNN`
- 范围: 微信小程序客户端行为

## 特定约束

### 平台约束
- 代码包体积限制：主包 ≤ 2MB，分包 ≤ 2MB，总计 ≤ 16MB
- 部分微信 API 仅在真机上可用（模拟器受限）
- 登录凭证 `code` 每次调用 `wx.login()` 不同，需即时交换
- `wx.requestPayment()` 唤起支付前需服务端签名
- 审核周期：首次 3-7 工作日，更新 1-3 工作日（紧急可加急）

### 构建时约束
- `BACKEND_URL` 在构建时通过环境变量注入到 `app.json` 或 `service.js`
- 微信不允许在本地调试时连接未备案的域名（开发时需在 project.config.json 配置）
- 分包引用的静态资源需在分包目录内，不跨分包共享（如需共享用 npm package）

### 安全约束
- `openid` / `unionid` 不得明文暴露在 log 中（SEC-007）
- 用户信息获取必须通过 `wx.getUserProfile()`（非已废弃的 `getUserInfo()`）
- 支付相关逻辑必须在后端完成签名，禁止在前端泄露 merchant key
- 敏感数据存储用 `wx.getStorageSync()` 配合加密，不存明文 token

## 开发流程

### 1. Understand（需求理解 → WXA-FR-*）
- 在 `phases/understand/lifecycle.md` 的 WXA-FR spec template 中声明行为
- `affects: [wxa]` 的 spec delta 必须明确页面路由、触发的微信 API、用户交互流程
- 若 feature 跨组件，声明 `INT-FR-NNN` 关联 `BE-FR-NNN`（如登录、支付）

### 2. Plan（设计 → WXA-FR-* 实现计划）
- 页面结构设计（app.json 中的 pages 列表和分包配置）
- API 层设计（services/ 目录下按 domain 组织）
- 分包策略：超过 1.5MB 主包建议拆分为独立分包
- TCB 云函数接口约定（与 BE-FR-NNN 对齐）

### 3. Verify（测试 → BDD + TDD）
- 单元测试：Jest + @tencent/wxapp-miniprogram-simtest
- E2E：miniprogram-automator 模拟用户操作（点击、页面跳转、表单填写）
- BDD：`pytest-bdd apps/wxa/features/`（场景覆盖登录、主页、核心交易流程）

### 4. Deliver（构建 → 发布）
- 构建：`pnpm --filter wxa build`，BACKEND_URL 注入
- 预览：通过 `wx.uploadFile()` 上传获取 preview 二维码
- 体验版：上传后生成体验版 QR，可分享给内部测试者
- 提交审核：登录微信公众平台人工审核
- 发布：审核通过后手动发布（或开启自动发布）

## 微信 API 使用规范

### 常用 API 分类

| 类别 | API | 说明 |
|------|-----|------|
| 登录 | `wx.login()` | 获取临时 code，换 token 在后端 |
| 用户信息 | `wx.getUserProfile()` | 获取加密用户数据，需用户授权 |
| 支付 | `wx.requestPayment()` | 调起支付，前端仅唤起 |
| 位置 | `wx.getLocation()` | GPS 定位，需声明 privacy |
| 存储 | `wx.setStorage()` / `getStorageSync()` | 本地键值存储 |
| 网络 | `wx.request()` | 请求 BACKEND_URL，需在合法域名列表中 |
| 转发 | `wx.showShareMenu()` | 开启当前页面分享能力 |
| 订阅消息 | `wx.requestSubscribeMessage()` | 一次性订阅消息推送 |

### 云开发 API（TCB 集成）

```javascript
// 使用 @cloudbase/wx-server-sdk（云函数端）
const tcb = require('@cloudbase/wx-server-sdk');
exports.main = async (event, context) => {
  const app = tcb.init();
  const db = app.database();
  // ...
};

// 前端使用 wx.cloud（微信云开发，无需额外依赖）
wx.cloud.init({ env: 'your-env-id' });
wx.cloud.callFunction({ name: 'login', data: {} });
```

## 分包加载策略

| 策略 | 适用场景 | 配置位置 |
|------|----------|----------|
| 主包全量 | 功能 < 10 个页面，总体积 < 1.5MB | 默认 |
| 普通分包 | 功能模块化，需要按需加载 | app.json `subpackages` |
| 插件分包 | 独立业务可拔插 | app.json `plugins` |

分包加载后访问路径：`/pages/subpackage-page/main`（需在 app.json 配置 root）

## CI/CD

```yaml
# .github/workflows/wxa.yml（示例）
- name: Build WXA
  run: |
    cd apps/wxa
    BACKEND_URL=${{ env.BACKEND_URL }} pnpm build

- name: Upload Preview
  uses:微信官方案例/upload-miniprogram@v1
  with:
    appid: ${{ secrets.WX_APPID }}
    version: ${{ env.VERSION }}
    desc: ${{ github.event.head_commit.message }}

- name: E2E Tests
  run: pytest apps/wxa/tests/e2e/ --backend-url ${{ env.BACKEND_URL }}
```

## 与其他组件的集成

- **BE-FR-NNN**：所有网络请求走 `services/` 层，URL 由 `BACKEND_URL` + route 拼接
- **INT-FR-NNN**：跨组件行为（登录态同步、支付回调）需声明在 `contracts/` 中
- **共享类型**：`aidlc/packages/shared/` 中的 OpenAPI 类型通过构建时生成注入
- **Native/Desktop/Web**：各端独立构建，不共享 WXA 代码

## Design System 规范

### 必读规范
| 规范 | 路径 |
|------|------|
| Design Tokens | `phases/plan/design_system/design_tokens.md` |
| Atomic Design | `phases/plan/design_system/atomic_design.md` |
| Component Spec | `phases/plan/design_system/component_spec.md` |
| Accessibility | `phases/plan/design_system/accessibility.md` |
| Theme System | `phases/plan/design_system/theme_system.md` |
| WXA UI | `phases/plan/design_system/platform_ui/wxa.md` |
| Iconography | `phases/plan/design_system/iconography.md` |

### UI 组件库
- **默认**: Vant Weapp
- **主题定制**: 通过 CSS 变量覆盖

### 主题色
```css
page {
  --primary-color: #1989fa;
  --success-color: #07c160;
  --danger-color: #ee0a24;
  --warning-color: #ff976a;
}
```

### 组件分层
- Atom: Button, Cell, Field, Icon
- Molecule: CellGroup, SearchBar, Card
- Organism: NavBar, Tabbar, List
- Template: 页面布局模板
- Page: 业务页面
