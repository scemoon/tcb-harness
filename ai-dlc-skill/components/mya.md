# MYA 组件开发指南 (MYA-FR-*) — 支付宝小程序

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 支付宝原生 / uni-app | 原生适合轻量；uni-app 适合多端复用 |
| 语言 | JavaScript / TypeScript | 推荐 TypeScript（类型安全） |
| UI 组件库 | Ant Design Mini / ZII | 默认 Ant Design Mini（per skill.yaml） |
| 云服务 | mpserverless / 阿里云 FC | Aliyun 为默认云 provider |
| 构建 | 支付宝开发者工具 / uni-app CLI | 原生项目用开发者工具 |
| 测试 | Jest / miniprogram-simtest | 单元测试用 Jest |
| 自动化 | miniprogram-automator | UI 自动化测试 |
| BDD | pytest-bdd + miniprogram-automator | E2E BDD 场景 |

## 计算模式

| 模式 | 类型 | 说明 |
|------|------|------|
| my.serverless | 云开发 | 支付宝自带云能力（mpserverless） |
| aliyun-fc | 函数计算 | Aliyun Function Compute，FaaS 云函数 |
| 混合 | 支付宝云 + Aliyun | 支付宝云存储 + Aliyun 云函数 |

默认模式: `aliyun-fc`（Aliyun 平台，与其他组件统一）。

## 关键命令

```bash
# 构建
pnpm --filter mya build

# 测试
pnpm --filter mya test              # 单元测试
pytest apps/mya/tests/e2e/ --backend-url $BACKEND_URL  # E2E BDD

# Lint
pnpm --filter mya lint

# 预览（上传至支付宝小程序平台，获取预览二维码）
pnpm --filter mya preview

# 分包构建（如使用分包）
pnpm --filter mya build --type=plugin
```

## 目录约定

```
apps/mya/
├── src/
│   ├── components/          # 业务组件
│   ├── pages/               # 页面（按分包组织）
│   ├── subpackages/         # 分包（主包超出限制时拆离）
│   ├── services/            # API 调用层（统一用 BACKEND_URL）
│   ├── store/               # 状态管理（推荐 mobx-miniprogram）
│   ├── utils/               # 工具函数
│   ├── const/               # 常量（API 路由、错误码等）
│   └── app.js / app.json / app.acss / app.ts   # 应用入口
├── tests/
│   ├── unit/                # Jest 单元测试
│   ├── integration/         # 集成测试
│   └── e2e/                 # BDD E2E（miniprogram-automator）
├── features/                # BDD Gherkin feature 文件
│   └── *.feature
├── mock/                    # 模拟数据（开发环境）
└── cloud/                   # 支付宝云函数 / Aliyun FC 源码
```

## FR 命名空间

- Prefix: `MYA-FR-NNN`
- 范围: 支付宝小程序客户端行为

## 特定约束

### 平台约束
- 代码包体积限制：主包 ≤ 2MB，分包 ≤ 2MB，总计 ≤ 10MB（个人类型 2MB）
- 部分 my API 仅在真机上可用（模拟器受限）
- 登录凭证 `authcode` 每次调用 `my.getAuthCode()` 不同，需即时交换
- `my.tradePay()` 唤起支付前需服务端签名（alipay.trade.pay）
- 审核周期：首次 2-5 工作日，更新 1-2 工作日
- 支付宝小程序需在支付宝开放平台完成域名配置和签约

### 构建时约束
- `BACKEND_URL` 在构建时通过环境变量注入到 `app.json` 或 `service.js`
- 需在 `project.config.json` 中配置 `compileType: miniprogram`
- 分包引用的静态资源需在分包目录内，不跨分包共享

### 安全约束
- `user_id` / `open_id` 不得明文暴露在 log 中（SEC-007）
- 用户信息获取必须通过 `my.getUserInfo()` 或 `my.getPhoneNumber()`
- 支付相关逻辑必须在后端完成签名，禁止在前端泄露 private_key
- 敏感数据存储用 `my.setStorage()` / `my.getStorageSync()` 配合加密，不存明文 token

## 开发流程

### 1. Understand（需求理解 → MYA-FR-*）
- 在 `phases/understand/lifecycle.md` 的 MYA-FR spec template 中声明行为
- `affects: [mya]` 的 spec delta 必须明确页面路由、触发的支付宝 API、用户交互流程
- 若 feature 跨组件，声明 `INT-FR-NNN` 关联 `BE-FR-NNN`（如登录、支付）

### 2. Plan（设计 → MYA-FR-* 实现计划）
- 页面结构设计（app.json 中的 pages 列表和分包配置）
- API 层设计（services/ 目录下按 domain 组织）
- 分包策略：超过 1.5MB 主包建议拆分为独立分包
- Aliyun 云函数接口约定（与 BE-FR-NNN 对齐）

### 3. Verify（测试 → BDD + TDD）
- 单元测试：Jest + miniprogram-simtest
- E2E：miniprogram-automator 模拟用户操作（点击、页面跳转、表单填写）
- BDD：`pytest-bdd apps/mya/features/`（场景覆盖登录、主页、核心交易流程）

### 4. Deliver（构建 → 发布）
- 构建：`pnpm --filter mya build`，BACKEND_URL 注入
- 预览：通过 `my.uploadFile()` 上传获取 preview 二维码
- 体验版：上传后生成体验版 QR，可分享给内部测试者
- 提交审核：登录支付宝开放平台人工审核
- 发布：审核通过后手动发布（或开启自动发布）

## 支付宝 API 使用规范

### 常用 API 分类

| 类别 | API | 说明 |
|------|-----|------|
| 登录 | `my.getAuthCode()` | 获取授权码，换 token 在后端 |
| 用户信息 | `my.getUserInfo()` | 获取用户基本信息 |
| 支付 | `my.tradePay()` | 调起支付，前端仅唤起 |
| 位置 | `my.getLocation()` | GPS 定位，需声明隐私政策 |
| 存储 | `my.setStorage()` / `getStorageSync()` | 本地键值存储 |
| 网络 | `my.request()` | 请求 BACKEND_URL，需在合法域名列表中 |
| 分享 | `my.showShareMenu()` | 开启当前页面分享能力 |
| 推送 | `my.apayMessage()` | 订阅消息推送 |

### 云开发 API（Aliyun 集成）

```javascript
// 使用 @ant-design/mini-cli 或 mpserverless SDK
const mpserverless = require('@antcloud/mpserverless-sdk');
const app = new mpserverless({
  spaceId: 'your-space-id',
  clientSecret: 'your-client-secret',
});
await app.init();

// 调用云函数
const res = await app.callFunction('login', { type: 'alipay' });
```

## 分包加载策略

| 策略 | 适用场景 | 配置位置 |
|------|----------|----------|
| 主包全量 | 功能 < 10 个页面，总体积 < 1.5MB | 默认 |
| 普通分包 | 功能模块化，需要按需加载 | app.json `subPackages` |
| 插件分包 | 独立业务可拔插 | app.json `plugins` |

分包加载后访问路径：`/pages/subpackage-page/index`（需在 app.json 配置 root）

## CI/CD

```yaml
# .github/workflows/mya.yml（示例）
- name: Build MYA
  run: |
    cd apps/mya
    BACKEND_URL=${{ env.BACKEND_URL }} pnpm build

- name: Upload Preview
  uses: alipay/upload-miniprogram@v1
  with:
    appid: ${{ secrets.ALIPAY_APPID }}
    version: ${{ env.VERSION }}
    desc: ${{ github.event.head_commit.message }}

- name: E2E Tests
  run: pytest apps/mya/tests/e2e/ --backend-url ${{ env.BACKEND_URL }}
```

## 与其他组件的集成

- **BE-FR-NNN**：所有网络请求走 `services/` 层，URL 由 `BACKEND_URL` + route 拼接
- **INT-FR-NNN**：跨组件行为（登录态同步、支付回调）需声明在 `contracts/` 中
- **共享类型**：`aidlc/packages/shared/` 中的 OpenAPI 类型通过构建时生成注入
- **Native/Desktop/Web**：各端独立构建，不共享 MYA 代码