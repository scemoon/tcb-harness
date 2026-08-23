# TTA 组件开发指南 (TTA-FR-*) — 抖音小程序

## 技术栈

| 类别 | 选项 | 说明 |
|------|------|------|
| 框架 | 抖音原生 / uni-app | 原生适合轻量；uni-app 适合多端复用 |
| 语言 | JavaScript / TypeScript | 推荐 TypeScript（per skill.yaml） |
| UI 组件库 | 字节跳动组件库 / Vant | 字节官方组件库 |
| 云服务 | 字节云 / Aliyun FC | Aliyun 为默认云 provider |
| 构建 | 抖音开发者工具 / uni-app CLI | 原生项目用开发者工具 |
| 测试 | Jest / miniprogram-simtest | 单元测试用 Jest |
| 自动化 | miniprogram-automator | UI 自动化测试 |
| BDD | pytest-bdd + miniprogram-automator | E2E BDD 场景 |

## 计算模式

| 模式 | 类型 | 说明 |
|------|------|------|
| tt.cloud | 云开发 | 抖音自带云能力 |
| aliyun-fc | 函数计算 | Aliyun Function Compute，FaaS 云函数 |
| 混合 | 抖音云 + Aliyun | 抖音云存储 + Aliyun 云函数 |

默认模式: `aliyun-fc`（Aliyun 平台，与其他组件统一）。

## 关键命令

```bash
# 构建
pnpm --filter tta build

# 测试
pnpm --filter tta test              # 单元测试
pytest apps/tta/tests/e2e/ --backend-url $BACKEND_URL  # E2E BDD

# Lint
pnpm --filter tta lint

# 预览（上传至抖音小程序平台，获取预览二维码）
pnpm --filter tta preview

# 分包构建（如使用分包）
pnpm --filter tta build --type=plugin
```

## 目录约定

```
apps/tta/
├── src/
│   ├── components/          # 业务组件
│   ├── pages/               # 页面（按分包组织）
│   ├── subpackages/         # 分包（主包超出限制时拆离）
│   ├── services/            # API 调用层（统一用 BACKEND_URL）
│   ├── store/               # 状态管理（推荐 mobx-miniprogram）
│   ├── utils/               # 工具函数
│   ├── const/               # 常量（API 路由、错误码等）
│   └── app.js / app.json / app.ttss / app.ts   # 应用入口
├── tests/
│   ├── unit/                # Jest 单元测试
│   ├── integration/         # 集成测试
│   └── e2e/                 # BDD E2E（miniprogram-automator）
├── features/                # BDD Gherkin feature 文件
│   └── *.feature
├── mock/                    # 模拟数据（开发环境）
└── cloud/                   # 抖音云函数 / Aliyun FC 源码
```

## FR 命名空间

- Prefix: `TTA-FR-NNN`
- 范围: 抖音小程序客户端行为

## 特定约束

### 平台约束
- 代码包体积限制：主包 ≤ 2MB，分包 ≤ 2MB，总计 ≤ 16MB
- 部分 tt API 仅在真机上可用（模拟器受限）
- 登录凭证 `code` 每次调用 `tt.login()` 不同，需即时交换
- `tt.pay()` 唤起支付前需服务端签名
- 审核周期：首次 3-7 工作日，更新 1-3 工作日
- 抖音小程序需在字节跳动开发者平台完成域名配置
- 视频/直播相关功能有特殊类目资质要求（视听类需持证）

### 构建时约束
- `BACKEND_URL` 在构建时通过环境变量注入到 `app.json` 或 `service.js`
- 需在 `project.config.json` 中配置对应抖音项目参数
- 分包引用的静态资源需在分包目录内，不跨分包共享

### 安全约束
- `openid` / `unionid` 不得明文暴露在 log 中（SEC-007）
- 用户信息获取必须通过 `tt.getUserInfo()`
- 支付相关逻辑必须在后端完成签名，禁止在前端泄露 merchant key
- 敏感数据存储用 `tt.setStorage()` / `getStorageSync()` 配合加密，不存明文 token

## 开发流程

### 1. Understand（需求理解 → TTA-FR-*）
- 在 `phases/understand/lifecycle.md` 的 TTA-FR spec template 中声明行为
- `affects: [tta]` 的 spec delta 必须明确页面路由、触发的抖音 API、用户交互流程
- 若 feature 跨组件，声明 `INT-FR-NNN` 关联 `BE-FR-NNN`（如登录、支付、视频内容发布）

### 2. Plan（设计 → TTA-FR-* 实现计划）
- 页面结构设计（app.json 中的 pages 列表和分包配置）
- API 层设计（services/ 目录下按 domain 组织）
- 分包策略：超过 1.5MB 主包建议拆分为独立分包
- 视频/直播相关页面需单独分包（体积累积快）
- Aliyun 云函数接口约定（与 BE-FR-NNN 对齐）

### 3. Verify（测试 → BDD + TDD）
- 单元测试：Jest + miniprogram-simtest
- E2E：miniprogram-automator 模拟用户操作（点击、页面跳转、表单填写）
- BDD：`pytest-bdd apps/tta/features/`（场景覆盖登录、主页、视频播放、直播相关流程）

### 4. Deliver（构建 → 发布）
- 构建：`pnpm --filter tta build`，BACKEND_URL 注入
- 预览：通过 `tt.uploadFile()` 上传获取 preview 二维码
- 体验版：上传后生成体验版 QR，可分享给内部测试者
- 提交审核：登录字节跳动开发者平台人工审核（视频类需额外资质）
- 发布：审核通过后手动发布（或开启自动发布）

## 抖音 API 使用规范

### 常用 API 分类

| 类别 | API | 说明 |
|------|-----|------|
| 登录 | `tt.login()` | 获取临时 code，换 token 在后端 |
| 用户信息 | `tt.getUserInfo()` | 获取用户基本信息 |
| 支付 | `tt.pay()` | 调起支付，前端仅唤起 |
| 位置 | `tt.getLocation()` | GPS 定位，需声明隐私政策 |
| 存储 | `tt.setStorage()` / `getStorageSync()` | 本地键值存储 |
| 网络 | `tt.request()` | 请求 BACKEND_URL，需在合法域名列表中 |
| 分享 | `tt.showShareMenu()` | 开启当前页面分享能力 |
| 视频 | `tt.createVideoContext()` | 视频播放控制 |
| 直播 | `tt.live-player` | 直播拉流组件，需相关类目 |
| 推送 | `tt.subscribeMessage()` | 订阅消息推送 |

### 云开发 API（Aliyun 集成）

```javascript
// 使用字节云 SDK
const tiktokCloud = require('@bytecloud/wx-server-sdk');
exports.main = async (event, context) => {
  const app = tiktokCloud.init();
  const db = app.database();
  // ...
};

// 抖音云函数端调用
tt.cloud.callFunction({
  name: 'login',
  data: { type: 'tiktok' },
  success: (res) => { console.log(res); },
});
```

## 分包加载策略

| 策略 | 适用场景 | 配置位置 |
|------|----------|----------|
| 主包全量 | 功能 < 10 个页面，总体积 < 1.5MB | 默认 |
| 普通分包 | 功能模块化，需要按需加载；视频类页面单独分包 | app.json `subPackages` |
| 插件分包 | 独立业务可拔插 | app.json `plugins` |

分包加载后访问路径：`/pages/subpackage-page/index`（需在 app.json 配置 root）

## CI/CD

```yaml
# .github/workflows/tta.yml（示例）
- name: Build TTA
  run: |
    cd apps/tta
    BACKEND_URL=${{ env.BACKEND_URL }} pnpm build

- name: Upload Preview
  uses: bytedance/upload-miniprogram@v1
  with:
    appid: ${{ secrets.TIKTOK_APPID }}
    version: ${{ env.VERSION }}
    desc: ${{ github.event.head_commit.message }}

- name: E2E Tests
  run: pytest apps/tta/tests/e2e/ --backend-url ${{ env.BACKEND_URL }}
```

## 与其他组件的集成

- **BE-FR-NNN**：所有网络请求走 `services/` 层，URL 由 `BACKEND_URL` + route 拼接
- **INT-FR-NNN**：跨组件行为（登录态同步、支付回调、视频内容同步）需声明在 `contracts/` 中
- **共享类型**：`aidlc/packages/shared/` 中的 OpenAPI 类型通过构建时生成注入
- **Native/Desktop/Web**：各端独立构建，不共享 TTA 代码
- **视频/直播专注意事项**：抖音小程序视频类内容有额外审核规则，需在 plan 阶段明确是否涉及并提前准备资质

## Design System 规范

### 必读规范
| 规范 | 路径 |
|------|------|
| Design Tokens | `phases/plan/design_system/design_tokens.md` |
| Atomic Design | `phases/plan/design_system/atomic_design.md` |
| Component Spec | `phases/plan/design_system/component_spec.md` |
| Accessibility | `phases/plan/design_system/accessibility.md` |
| Theme System | `phases/plan/design_system/theme_system.md` |
| TTA UI | `phases/plan/design_system/platform_ui/tta.md` |
| Iconography | `phases/plan/design_system/iconography.md` |

### UI 组件库
- **默认**: 字节跳动官方组件库
- **备选**: Vant (轻量)
- **主题定制**: 通过 CSS 变量覆盖

### 主题色
```css
page {
  --color-primary: #333333;
  --color-success: #07c160;
  --color-warning: #ff9500;
  --color-danger: #fc5531;
}
```

### 组件分层
- Atom: Button, Cell, Field, Icon
- Molecule: CellGroup, SearchBar, Card
- Organism: NavBar, TabBar, List
- Template: 页面布局模板
- Page: 业务页面

### 视频/直播组件
- 使用 `<video>` 组件
- 使用 `<live-player>` 直播拉流组件
- 视频封面使用 `<image mode="aspectFill">`
- 需申请相关类目资质