---
name: tcb-harness
description: >-
  Full-lifecycle CloudBase (TCB) development harness for WeChat Mini Programs, Web apps, or both.
  Drives structured Spec to Design to Coding (TDD) to Testing to Deploy pipeline with project
  isolation, quality gates, and persistent artifacts. Handles three platform types:
  (1) Mini Program — WeChat Mini Program with wx.cloud; (2) Web — browser-based app with CloudBase Web SDK;
  (3) Official Account — WeChat Official Account H5 (JSSDK + OAuth 2.0); (4) Hybrid — Mini Program + Web frontend sharing one backend.
  Use when developing, testing, or deploying CloudBase projects that need requirement specification,
  UI/service/frontend/backend design, test case generation, test data construction, test
  execution/evaluation/reports, or deployment management. Triggers on: TCB开发, CloudBase项目,
  小程序开发, Web开发, spec设计, TDD开发, 测试用例, 测试数据, 项目部署, harness流程.
---

# TCB Harness

Full-lifecycle development harness for CloudBase (Tencent CloudBase) projects.

## Platform Types

This harness manages three platform configurations:

| 类型 | 简称 | 前端 | 后台 | 认证 |
|------|------|------|------|------|
| 小程序 | MP | 微信小程序（TDesign Miniprogram） | 可选 CloudBase 云函数/云托管 | OPENID 静默 |
| Web | Web | PC 浏览器应用（TDesign React） | CloudBase 云函数/云托管 | Web SDK Auth |
| 移动端 | Mobile | 移动端 H5（TDesign Mobile React） | CloudBase 云函数/云托管 | Web SDK Auth |
| 公众号 | OA | 微信公众号 H5（TDesign React + JSSDK） | CloudBase 云函数/云托管 | OAuth 2.0 |
| 混合项目 | Hybrid | 小程序 + Web + 移动端 + 公众号任意组合 | 统一后台 | 各自平台认证 |

---

## Activation Contract

### Read this first when

- Starting a new CloudBase project (MP / Web / Hybrid)
- Needing structured spec → design → code → test → deploy workflow
- Working on test design (case gen, data gen, evaluation, reports)
- Managing multiple projects with isolation

### Then route to

- CloudBase MCP integration → `cloudbase` skill (CloudBase-specific tools, database, cloud functions, auth)
- Claude Code → `claude-code-cli-openclaw` skill (TDD coding sessions)
- Mini Program specific → `references/miniprogram-guide.md` (TDesign Miniprogram)
- Web specific → `references/web-guide.md` (TDesign React)
- Mobile specific → `references/mobile-guide.md` (TDesign Mobile React)
- Backend specific → `references/backend-guide.md`
- Knowledge Base → `references/knowledge-base.md` (含后台项目必读)

### Do NOT use for

- Non-CloudBase projects (use platform-specific skills instead)
- Simple one-off code generation without lifecycle management

---

## Project Directory Convention

```
projects/{project-name}/
├── .harness/
│   ├── config.json              # 项目配置（平台类型、envId、appid）
│   ├── state.json               # 当前阶段、进度、阻塞项
│   └── deploy-history.json      # 部署历史
├── specs/{spec-name}/
│   ├── requirements.md          # 需求文档
│   ├── design.md                # 技术方案
│   ├── tasks.md                 # 任务分解
│   └── reviews/                 # 评审记录
├── design/
│   ├── ui/                      # UI 设计（全平台通用）
│   │   ├── design-system.md
│   │   ├── color-palette.md
│   │   └── wireframes/
│   ├── frontend/                 # 前端设计（按平台隔离）
│   │   ├── miniprogram/         # 小程序前端设计（可选）
│   │   │   ├── architecture.md
│   │   │   ├── routing.md
│   │   │   ├── component-tree.md
│   │   │   └── subpackage.md
│   │   └── web/                 # Web 前端设计（可选）
│   │       ├── architecture.md
│   │       ├── routing.md
│   │       └── state-management.md
│   ├── backend/                  # 后台设计（可选，无后台时跳过）
│   │   ├── api-contract.md       # API 契约
│   │   ├── data-model.md         # 数据模型
│   │   ├── cloud-functions.md    # 云函数清单
│   │   └── security-rules.md     # 安全规则
│   └── shared/                   # 跨平台共享设计（可选）
│       └── common-types.md       # 共享类型定义
├── src/                          # 源码
│   ├── miniprogram/              # 小程序源码（可选）
│   │   ├── app.js / app.ts
│   │   ├── app.json
│   │   ├── pages/
│   │   ├── components/
│   │   ├── services/
│   │   └── utils/
│   └── web/                      # Web 源码（TDesign React，可选）
│       ├── index.html
│       ├── src/
│       └── dist/
├── cloud/                        # CloudBase 云函数（共享）
│   ├── {function-name}/
│   └── ...
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── test-data/
│   └── reports/
└── docs/
```

**平台决定规则：**
- `config.json` 中 `platform` 字段决定哪些目录生效
- Hybrid 项目：frontend 下同时存在 miniprogram/、web/ 和 mobile/ 中的任意组合
- 无后台项目：backend/ 目录不存在，设计阶段跳过

---

## Core Workflow

```
init → spec → design → coding(TDD) → testing → deploy → iterate
  ↑                                                    │
  └───────────── feedback loop ──────────────────────────┘
```

### Phase Routing

| 用户意图 | 阶段 | 读取 Reference | 执行 |
|---------|------|---------------|------|
| "新项目" / "初始化" | Init | — | `scripts/init_project.py` |
| "写需求" / "spec" | Spec | `references/spec-guide.md` | EARS 流程，自动进入下一子步骤直至阶段完成 |
| "做设计" / "UI设计" | Design | `references/ui-design-guide.md` | 确定平台后路由，自动继续 |
| "做设计" / "服务设计" | Design | `references/service-design-guide.md` | 后台设计，自动继续 |
| "做设计" / "前端设计" | Design | `references/miniprogram-guide.md` 或 `references/web-guide.md` | 按平台路由，自动继续 |
| "写代码" / "开发" | Coding | `references/coding-guide.md` | TDD 红绿重构，自动继续 |
| "写测试" / "测试" | Testing | `references/testing-guide.md` | 用例→数据→执行→报告，自动继续 |
| "部署" / "发布" | Deploy | `references/deploy-guide.md` | 构建→预览→上传→配置，自动继续 |
| "项目状态" | Status | — | `scripts/project_status.py` |
| "继续" | Resume | — | 读 `.harness/state.json` → 续接 |
| "预览" / "preview" | Preview | — | `scripts/preview.py` |
| "preview --platform web" | Preview Web | — | 构建→上传→返回可访问链接+域名加白提示 |
| "preview --platform mp" | Preview MP | — | 构建→preview→输出二维码（手机扫码预览）|
| "preview --platform app" | Preview App | — | App不支持预览，打印引导 |

---


## Auto-Continue Mode

**重要规则：默认自动进入下一阶段，无须等待用户确认。**

当完成当前阶段的一个子步骤后，AI 应自动进入下一子步骤，直到该阶段全部完成才向用户汇报。

- 阶段内：连续执行，直到所有步骤完成
- 阶段间：自动进入下一阶段，直到所有阶段完成
- 用户可随时通过明确指令中断或修改

只在以下情况暂停：
1. 遇到阻塞项（依赖缺失、配置错误、外部依赖不可用）
2. 需要用户做决策（多选项、无明确偏好）
3. 用户明确要求暂停

---

## Design Phase — Platform Routing

Design 阶段根据项目类型路由到不同参考文档：

### 全部项目必读

- `references/ui-design-guide.md` — UI 设计系统、配色、交互模式

### 按需读取

| 平台配置 | 读取 |
|---------|------|
| 含小程序前端 | `references/miniprogram-guide.md` |
| 含 Web 前端 | `references/web-guide.md` |
| 含移动端前端 | `references/mobile-guide.md` |
| 含公众号前端 | `references/official-account-guide.md` |
| 含后台 | `references/backend-guide.md` + `references/service-design-guide.md` |
| 含知识库需求 | `references/knowledge-base.md` |
| 混合项目 | 全部按需读取，跨平台共享设计存入 `design/shared/` |

### Hybrid 特殊规则

当项目同时包含多个前端平台时：
1. 设计产物按平台分别存放（`frontend/miniprogram/`、`frontend/web/`、`frontend/official-account/` 等）
2. 跨平台共享的类型/API 存入 `design/shared/`
3. 后台统一设计，多端共用
4. Coding 阶段可并行开发多端，或按优先级顺序开发

---

## Deploy Phase — Detailed Config Output

Deploy 阶段必须产出完整的部署配置，详见 `references/deploy-guide.md`。核心原则：

- **小程序** — 通过 `miniprogram-ci` 构建/预览/上传
- **Web** — 通过 CloudBase 静态托管部署
- **后台** — 通过 CloudBase MCP 部署云函数/云托管
- **混合项目** — 统一 `deploy-config.json` 描述所有组件的部署状态

部署配置模板见 `assets/templates/deploy/deploy-config.json.tpl`，必须填入：
- 每个云函数的版本、超时、环境变量
- 每个云托管服务的镜像版本、实例规格
- 数据库集合的初始化状态
- 安全规则的最终配置
- 订阅消息模板 ID 映射

---

## Phase Gate Summary

| 过渡 | 必要产出 | 校验 |
|------|---------|------|
| Init → Spec | config.json 含 platform/envId/appid | 文件存在 + valid JSON |
| Spec → Design | requirements.md + design.md + tasks.md | `validate_spec.py` 通过 + 用户确认 |
| Design → Coding | 前端/后台设计文档（按平台配置） | 跨平台一致性检查 + 用户确认 |
| Coding → Testing | 全部任务完成 + 单元测试通过 | `npm test` exit 0 |
| Testing → Deploy | 测试报告，覆盖率 ≥80%，无 P0/P1 失败 | 报告文件存在 + 指标达标 |
| Deploy → 下一Spec | deploy-history.json 更新 + 所有组件部署状态 | 配置与实际环境一致 |

---

## Integration with Other Skills

| Skill | 何时委托 | 方式 |
|-------|---------|------|
| `cloudbase` | CloudBase MCP、云函数、数据库、Auth、存储 | 读取 cloudbase skill 路由表 |
| `claude-code-cli-openclaw` | TDD 编码会话、复杂实现 | 启动 Claude Code session |
| `spec-workflow` (cloudbase 子 skill) | EARS 方法论基础 | 读取 `references/spec-workflow/` |

**规则：** 调用 CloudBase MCP 工具前必须先读 `cloudbase` skill。CloudBase Activation Contract 优先于本 skill。

---

## Resource Index

### scripts/
| 脚本 | 用途 |
|------|------|
| `init_project.py` | 初始化项目脚手架，按平台类型生成目录 |
| `preview.py` | Web/MP/App 预览，支持云开发部署和手机扫码预览 |
| `validate_spec.py` | 需求文档质量校验 |
| `gen_test_cases.py` | 从需求生成测试用例 |
| `gen_test_data.py` | 生成 Mock 测试数据 |
| `project_status.py` | 查询/展示项目状态 |

### references/
| 文档 | 适用 |
|------|------|
| `spec-guide.md` | 全部项目 — Spec 阶段 |
| `ui-design-guide.md` | 全部项目 — UI 设计 |
| `miniprogram-guide.md` | 小程序前端设计 |
| `web-guide.md` | Web 前端设计 |
| `official-account-guide.md` | 公众号前端设计（JSSDK、OAuth）|
| `backend-guide.md` | 后台设计（云函数/云托管） |
| `service-design-guide.md` | API 契约、数据模型 |
| `coding-guide.md` | 全部项目 — 编码规范 + TDD |
| `testing-guide.md` | 全部项目 — 测试方法论 |
| `deploy-guide.md` | 全部项目 — 部署流程 + 配置详情 |
| `tracing-guide.md` | 含后台的项目 — 链路追踪（鹰眼兼容 Trace ID、Span 中间件、日志规范、存储分析） |
| `knowledge-base.md` | 含后台的项目 — 知识库管理（CRUD、搜索、权限、分析） |
| `automation-guide.md` | 含后台的项目 — 自动化测试（接口 Jest+SuperTest、小程序 Midscene、Web Playwright） |

### assets/templates/
| 目录 | 内容 |
|------|------|
| `project/miniprogram/` | 小程序项目模板 |
| `project/web/` | Web 项目模板 |
| `project/official-account/` | 公众号项目模板（H5 + JSSDK）|
| `project/backend/` | 云函数脚手架模板 |
| `spec/` | Spec 文档模板 |
| `testing/` | 测试产出模板 |
| `deploy/` | 部署配置模板 |
