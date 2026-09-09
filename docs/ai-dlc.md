# AI-DLC — AI 驱动开发生命周期

> 版本: 4.0.0
> 位置: `ai-dlc-skill/`
> 兼容: CDH >=1.4, OpenCode >=1.15, Claude Code >=1.0, Cursor >=0.45

---

## 目录

1. [概述](#1-概述)
2. [核心循环](#2-核心循环)
3. [自适应流程（复杂度评估）](#3-自适应流程复杂度评估)
4. [Master Agent 编排](#4-master-agent-编排)
5. [Phase 0: Brownfield（存量探索）](#5-phase-0-brownfield存量探索)
6. [Phase ①: Understand（理解）](#6-phase-①understand理解)
7. [Phase ②: Plan（规划）](#7-phase-②plan规划)
8. [Phase ③: Verify（验证）](#8-phase-③verify验证)
9. [Phase ④: Deliver（交付）](#9-phase-④deliver交付)
10. [Integration 合约规约](#10-integration-合约规约)
11. [Stack 栈级规则](#11-stack-栈级规则)
12. [Security 安全基线](#12-security-安全基线)
13. [项目架构](#13-项目架构)
14. [Cloud Provider](#14-cloud-provider)
15. [Quality Gates 质量门](#15-quality-gates-质量门)
16. [Cross-Tool 跨工具导出](#16-cross-tool-跨工具导出)
17. [与 onecode 的集成](#17-与-onecode-的集成)
18. [文件清单](#18-文件清单)

---

## 1. 概述

AI-DLC 是面向 **monorepo 多组件栈** 的 AI 驱动开发生命周期框架。通过五个阶段（Brownfield 可选、Understand、Plan、Verify、Deliver）—— 以及一个一等公民 **Integration** 规约，覆盖从需求到生产的完整开发流。

### 1.1 组件体系

| 前缀 | 组件 | 目录 | FR 命名空间 | 技术栈 |
|------|------|------|-------------|--------|
| NATIVE | Mobile | `apps/native/` | `NATIVE-FR-NNN` | React Native / Flutter |
| DESKTOP | Desktop | `apps/desktop/` | `DESKTOP-FR-NNN` | Electron / Tauri |
| BE | Service | `apps/backend/` | `BE-FR-NNN` | Python / Node / Go |
| WXA | WeChat Mini | `apps/wxa/` | `WXA-FR-NNN` | WeChat Mini Program |
| MYA | Alipay Mini | `apps/mya/` | `MYA-FR-NNN` | Alipay Mini Program |
| TTA | TikTok Mini | `apps/tta/` | `TTA-FR-NNN` | TikTok Mini Program |
| INT | Contracts | `aidlc/contracts/`, `aidlc/packages/shared/` | `INT-FR-NNN` | OpenAPI 3.1 / AsyncAPI 3.0 |

### 1.2 实践方法论

| 实践 | 适用阶段 | 说明 |
|------|----------|------|
| SDD (Spec-Driven Development) | Understand, Plan, Deliver | 意图 → 规格增量 → 设计文档 → 任务 DAG |
| BDD (Behavior-Driven Development) | Understand, Verify | Given/When/Then 场景，≥3 场景/FR |
| TDD (Test-Driven Development) | Plan, Verify | Red → Green → Refactor |

---

## 2. 核心循环

```
0 Brownfield (optional)  Explore existing codebase → Context summary
① Understand (SDD+BDD)   Intent → Spec Delta → BDD Feature Files
② Plan (SDD+TDD)         Design Doc → Task DAG → Test Plan
③ Verify (BDD+TDD)       Red → Green → Refactor per scenario
④ Deliver (SDD+Cloud)    Stack Preview → e2e → Production + BVT
```

各阶段均由 Master Agent 委派给独立的 Sub-Agent（通过 `Spawn`）执行，阶段间有明确的 Gate 检查。

---

## 3. 自适应流程（复杂度评估）

Master Agent 根据需求复杂度动态裁剪执行阶段。

| 级别 | 触发条件 | 执行阶段 |
|------|----------|----------|
| **L1** | 单文件 bug fix，不改行为 | Verify only |
| **L2** | 单组件新功能，不涉及 INT 合约 | Understand → Verify |
| **L3** | 多组件功能，需要 INT 合约 | Understand → Plan → Verify |
| **L4** | 全栈新功能 + 部署 | Understand → Plan → Verify → Deliver |
| **L5** | 架构重构 / 平台迁移 | Plan → Verify |

### 3.1 评估维度

1. **范围 (Scope)**：单文件 / 单组件 / 多组件 / 全栈
2. **类型 (Type)**：修 bug / 新功能 / 重构 / 迁移
3. **合约 (Contract)**：是否涉及 INT-FR、OpenAPI、AsyncAPI
4. **部署 (Deploy)**：是否需要上线到 production

输出格式：`[Lx] Phase 列表`，如 `[L3] understand → plan → verify`

---

## 4. Master Agent 编排

### 4.1 编排流程

1. 分析意图 → 确定复杂度 (L1-L5)
2. 选择要执行的阶段
3. **每个阶段前** 调用 `TodoClear` 重置计划
4. 通过 `Spawn(agent_type="general", prompt=...)` 委派阶段，**使用阶段的 `prompt.md`**
5. 收集结果 → 执行 Gate 检查 → 决定继续或回退

### 4.2 角色边界

- **Master Agent** 负责所有规划：复杂度分析、Todo 创建、Spawn 决策
- **Sub-Agent** 是叶节点：仅执行实现，不嵌套
- **禁止** 将 "分析复杂度" 或 "应不应该 Spawn" 的决策委派给 sub-agent

### 4.3 委派模式

```python
Spawn(
    agent_type="general",
    prompt=f"""
    You are a {Phase} Phase Agent.
    1. Read phases/{phase}/prompt.md for full instructions
    2. Execute the task
    3. Follow phases/{phase}/rules.md
    """
)
```

### 4.4 Agent 清单

| Agent | Entry | Mode |
|-------|-------|------|
| ai-dlc-master | `SKILL.md` | primary |
| ai-dlc-understand | `phases/understand/entry.md` | subagent |
| ai-dlc-plan | `phases/plan/entry.md` | subagent |
| ai-dlc-verify | `phases/verify/entry.md` | subagent |
| ai-dlc-deliver | `phases/deliver/entry.md` | subagent |
| ai-dlc-brownfield | `brownfield/entry.md` | subagent |

---

## 5. Phase 0: Brownfield（存量探索）

### 5.1 目标

为已有项目自动生成语义上下文，辅助 AI Agent 理解代码库。

### 5.2 触发条件

- L2+ 复杂度且有存量代码
- Master Agent 自动调用

### 5.3 流程

```
Brownfield Phase 触发
  → 运行 brownfield/scripts/discover.sh 发现组件
  → 运行 brownfield/scripts/extract-api.sh 提取 API 表面
  → 运行 brownfield/scripts/deps.sh 生成依赖图
  → 生成 aidlc/AI-DLC-CONTEXT.md
```

### 5.4 产出

`aidlc/AI-DLC-CONTEXT.md` 包含：
1. 组件列表 + 技术栈
2. API 端点摘要
3. 跨组件依赖 Mermaid 图
4. 架构速览

### 5.5 在 AI-DLC 流程中的作用

- 确认 `affects` 声明的准确性
- 发现潜在的跨组件依赖
- 为后续 Phase 提供上下文

---

## 6. Phase ①: Understand（理解）

### 6.1 目标

将业务意图转化为无歧义、可验证的需求，在任何设计或编码工作之前。

### 6.2 流程

```
Intent（业务需求/用户故事）
  → 识别范围：影响哪些组件？
  → SDD: Proposal（Why, What, Impact, affects: [...]）
  → SDD: Spec Delta（EARS 格式：ADDED/MODIFIED/REMOVED）
  → BDD: Feature Files（per-component + cross-stack）
  → Gate: 人工审查 → approved 或 revise
```

### 6.3 EARS 格式

| 模式 | 语法 | 用途 |
|------|------|------|
| Ubiquitous | `The system SHALL ...` | 始终生效的规则 |
| Event-Driven | `When {event}, the system SHALL ...` | 事件触发行为 |
| State-Driven | `While {state}, the system SHALL ...` | 状态条件行为 |
| Unwanted | `If {condition}, the system SHALL ...` | 错误处理 |
| Optional | `Where {feature} enabled, the system SHALL ...` | 功能开关 |

### 6.4 制品位置

| 制品 | 位置 |
|------|------|
| Intent | `aidlc/requirements.md` |
| Spec delta | `aidlc/openspec/changes/{id}/spec-delta.md` |
| 组件级 BDD | `apps/{component}/features/{domain}/{feature}.feature` |
| 跨栈 BDD | `aidlc/features/cross-stack/{domain}/{feature}.feature` |
| 合约规格 | `aidlc/contracts/{api,events}/{name}.{yaml,graphql}` |

### 6.5 规则 (UND-001 ~ UND-006)

| 规则 | 级别 | 描述 |
|------|------|------|
| UND-001 | MUST | Intent 文档化，声明 `affects: [...]` 才能开始 spec delta |
| UND-002 | MUST | 所有 FR 使用 EARS 语法 |
| UND-003 | MUST | 每个 FR ≥3 个 BDD 场景（positive/negative/edge），标记命名空间前缀 |
| UND-004 | MUST | 每个 spec delta 声明 `affects: [...]` 字段 |
| UND-005 | MUST | 跨组件 feature 拆分为 per-component FR + INT-FR + cross-stack feature file |
| UND-006 | MUST | Contract-first：任何公开 API/event 变更必须更新 `aidlc/contracts/` |

### 6.6 门禁

- `affects: [...]` 已声明
- Spec delta 使用 EARS 格式
- 每个 FR 标记 `<PREFIX>-FR-NNN`，≥3 个场景
- 多组件：至少 1 个 `INT-FR-NNN` + cross-stack feature file
- 涉及合约：`aidlc/contracts/` 中存在对应合约文件
- 人工审查通过

---

## 7. Phase ②: Plan（规划）

### 7.1 目标

将已批准的规格转化为可逐单元执行的明确技术计划，包含跨组件依赖和合约引用。

### 7.2 流程

```
Approved Spec + BDD Features
  → SDD: Design Doc（per-component 架构、数据模型、API 合约、状态机、Integration 段）
  → SDD: Task Decomposition（带 DAG 的单元，含跨组件边）
  → TDD: Test Plan（per scenario，命名测试层级）
  → INT: Contract Plan（哪些合约变化，版本影响）
  → Gate: 人工审查
```

### 7.3 设计文档结构（多组件）

```markdown
## Design — CHG-{id}
**Affects:** [{components}]
**Contracts touched:** {list or "none"}

### Component: backend (BE-FR-*)
- Architecture, Data model, API surface, State machine

### Integration
- Flow, Contract refs, Failure modes, Backward compat
```

### 7.4 Task DAG 格式

```yaml
units:
  - id: int-contract-1
    fr: INT-FR-001
    affects: [contracts]
    depends_on: []
  - id: be-unit-2
    fr: BE-FR-001
    affects: [backend]
    depends_on: [int-contract-1, be-unit-1]
  - id: cross-stack-1
    fr: INT-FR-001
    affects: [backend]
    depends_on: [be-unit-2]
    layer: cross-stack
```

### 7.5 规则 (PLN-001 ~ PLN-004)

| 规则 | 描述 |
|------|------|
| PLN-001 | 设计文档包含架构、数据模型、API 合约、状态机；多组件必须有 Integration 段 |
| PLN-002 | 任务分解为显式 DAG，包含跨组件边 |
| PLN-003 | Test Plan 先于实现编写，按场景命名测试层级 |
| PLN-004 | 合约变更必须标识版本影响（additive vs breaking），列出受影响消费者和兼容策略 |

### 7.6 门禁

- 设计文档含 per-component + Integration 段
- 任务分解为显式 DAG
- `INT-FR-*` 任务排在消费合约的组件任务之前
- Test Plan 命名了 test layer
- 合约计划标识了 breaking vs additive
- 人工审查通过

---

## 8. Phase ③: Verify（验证）

### 8.1 目标

确保每个 BDD 场景在正确的层级正确实现，每个合约向后兼容，全栈 e2e 流正常工作 —— 在交付之前。

### 8.2 流程

```
Plan + Tasks approved
  → 对每个 DAG 顺序单元：
    对每个 BDD 场景：
      RED:   写测试 → 确认失败
      GREEN: 写最小实现 → 确认通过
      REFACTOR: 清理 → 所有测试通过
  → 组件内单元完成后：重新生成 shared types + contract tests
  → 合约完成后：cross-stack e2e 针对 unified preview
  → Gate: 所有层级通过 + 合约兼容 + cross-stack 通过
```

### 8.3 测试层级

| 层级 | 时机 | 位置 | 运行对象 |
|------|------|------|----------|
| `unit` | Per function/module | `apps/{comp}/tests/unit/` | 本地 |
| `integration` | 组件 + DB/内部 API | `apps/{comp}/tests/integration/` | 本地容器 |
| `e2e` | 全组件 vs preview | `apps/{comp}/tests/e2e/` | 组件 preview URL |
| `cross-stack` | 全多客户端↔backend 流 | `aidlc/tests/cross-stack/` | 统一栈 preview URL |
| `contract` | 合约形状 + 向后兼容 | `aidlc/tests/contract/` | 生成的 `aidlc/packages/shared/` |

### 8.4 合约验证

```bash
aidlc/tools/generate_shared.py       # 重新生成 shared types
pytest aidlc/tests/contract/          # 合约测试 (INT-001)
aidlc/tools/contract_diff.py         # 向后兼容检查 (INT-002)
```

### 8.5 规则

| 规则组 | 编号 | 描述 |
|--------|------|------|
| VRF | VRF-001 | 测试首次必须失败（RED 阶段） |
| VRF | VRF-002 | 仅实现使测试通过的最小代码（GREEN 阶段） |
| VRF | VRF-003 | 重构不改行为 |
| VRF | VRF-004 | ALL BDD 场景在每层通过 |
| VRF | VRF-005 | 所有质量门通过 |
| VRF | VRF-006 | 每个场景在 Plan 指定的层级测试 |
| INT | INT-001 | 所有跨组件 API/events 在 `contracts/` 中标记 `INT-FR-*` |
| INT | INT-002 | 合约变更默认向后兼容；breaking 需人工批准 + CHANGELOG |
| INT | INT-003 | `aidlc/packages/shared/` 从合约生成，组件从此导入 |
| INT | INT-004 | 每个 `INT-FR-*` 在 `aidlc/tests/contract/` 中有测试 |
| INT | INT-005 | 每个 `INT-FR-*` 在 cross-stack feature file 中 ≥3 场景 + 测试 |
| INT | INT-006 | 每个合约变更生成 `contract-diff.md` |

---

## 9. Phase ④: Deliver（交付）

### 9.1 目标

确保将验证过的代码作为一个一致的整体栈交付到生产环境 —— unified preview → per-component e2e → cross-stack e2e → stack BVT → stack rollback。

### 9.2 流程

```
All Verify gates passed
  → Unified Stack Preview Deploy（云平台动态 URL）
  → Per-component BDD e2e（针对组件 preview URL）
  → Cross-stack e2e（全流针对统一栈 URL）
  → Staging Stack Deploy + Smoke
  → Human Approval Gate
  → Production Stack Deploy（全栈作为一个整体单元）
  → Stack BVT (Build Verification Test)
  → Archive: contract-diff.md + e2e 报告 + BVT 报告
  → Gate: BVT pass → 完成 | BVT fail → stack rollback
```

### 9.3 Unified Stack Preview

`deploy_stack --preview` 部署整体栈：

1. `backend` 先部署（functions + DB migrate）
2. 所有客户端（`native`, `desktop`, `wxa`, `mya`, `tta`）并行部署，构建时注入 `BACKEND_URL`
3. 输出：`STACK_URL` (= `BACKEND_URL`) + 各组件 URL

### 9.4 Stack BVT 检查项

1. Backend `/health` 返回 200
2. Native/desktop/mini-program 启动探活
3. 核心 cross-stack 流（login）成功
4. 数据库可达
5. 错误率 < 0.1%
7. 延迟 p99 < 500ms
8. Contract diff 归档

### 9.5 规则

| 规则组 | 编号 | 描述 |
|--------|------|------|
| DLV | DLV-001 | 在 production 之前必须统一栈 preview + 组件 e2e + cross-stack e2e |
| DLV | DLV-002 | Production 部署需要显式人工审批，审核所有报告 |
| DLV | DLV-003 | BVT 必须对 production 运行；失败触发自动栈 rollback |
| DLV | DLV-004 | e2e 测试使用动态 preview URL，从不硬编码 production URL |
| STK | STK-001 | 每个 spec delta、design doc、task list 必须声明 `affects:` |
| STK | STK-002 | 消费合约的 task 必须有显式 `depends_on` 边 |
| STK | STK-003 | 影响 ≥2 个组件的变更必须有 cross-stack e2e |
| STK | STK-004 | 共享环境必须使用 `deploy_stack` 编排器，不能逐组件 ad-hoc 部署 |
| STK | STK-005 | 所有客户端构建时接收 `BACKEND_URL`，从不硬编码 |
| STK | STK-006 | Rollback 是栈级操作；所有组件一起回退 |

---

## 9. Integration 合约规约

### 9.1 三层合约体系

| 层 | 格式 | 位置 |
|----|------|------|
| API | OpenAPI 3.1 | `aidlc/contracts/api/` |
| Events | AsyncAPI 3.0 + CloudEvents | `aidlc/contracts/events/` |
| Functions | Runtime Contract | `aidlc/contracts/functions/` |

### 9.2 合约原则

- **Contract-first**：合约先于实现
- **Backward-compat by default**：默认向后兼容，breaking 需要 MAJOR 版本 bump + 人工批准
- **Shared types 自动生成**：`openapi-typescript | openapi-python` → `aidlc/packages/shared/`
- **Event contracts**：AsyncAPI | CloudEvents，semver-major-for-breaking 版本策略
- 每个合约变更输出 `contract-diff.md`

### 9.3 INT 规则（跨所有阶段）

| 规则 | 描述 |
|------|------|
| INT-001 | 跨组件 API/events 定义在 `contracts/` 中，标记 `INT-FR-*` |
| INT-002 | 合约变更默认向后兼容；breaking 需人工批准 + CHANGELOG |
| INT-003 | `aidlc/packages/shared/` 从合约生成，不可手写 |
| INT-004 | 每个 `INT-FR-*` 有 contract tests |
| INT-005 | 每个 `INT-FR-*` 有 ≥3 cross-stack 场景 |
| INT-006 | 每个合约变更生成 `contract-diff.md` |

---

## 10. Stack 栈级规则

栈级规则适用于所有阶段，保证 monorepo 多组件栈的一致性。

| 规则 | 描述 |
|------|------|
| STK-001 | 每个制品声明 `affects:` 字段 |
| STK-002 | 合约消费任务必须显式声明 `depends_on` |
| STK-003 | 多组件变更必须有 cross-stack e2e |
| STK-004 | 共享环境使用 `deploy_stack` 编排 |
| STK-005 | 客户端 `BACKEND_URL` 构建时注入 |
| STK-006 | Rollback 栈级操作 |

---

## 11. Security 安全基线

所有阶段必须遵守的安全规则。

| 规则 | 级别 | 描述 |
|------|------|------|
| SEC-001 | MUST | Secrets 从安全存储获取，从不硬编码或日志输出 |
| SEC-002 | MUST | 所有用户输入验证：类型、长度、格式、范围 |
| SEC-003 | MUST | 所有数据库查询使用参数化语句 |
| SEC-004 | MUST | CORS 头显式配置；生产环境禁止 wildcard origin |
| SEC-005 | MUST | 公共端点限流：100 req/min 未认证，1000 req/min 已认证 |
| SEC-006 | MUST | 所有生产流量使用 HTTPS；HTTP 重定向至 HTTPS |
| SEC-007 | MUST | 安全事件记录时间戳和行为者身份 |

---

## 12. 项目架构

### 12.1 顶层布局

```
{project_root}/
├── apps/
│   ├── native/          # NATIVE-FR-*   Mobile (Flutter/Dart)
│   ├── desktop/         # DESKTOP-FR-*  Desktop (Electron/TypeScript)
│   ├── backend/         # BE-FR-*       Service (Python/Node/Go)
│   ├── wxa/             # WXA-FR-*      WeChat Mini Program
│   ├── mya/             # MYA-FR-*      Alipay Mini Program
│   └── tta/             # TTA-FR-*      TikTok Mini Program
├── aidlc/contracts/           # INT-FR-*      OpenAPI/AsyncAPI/Runtime Contract
├── aidlc/packages/shared/     # INT-FR-*      Generated shared types
├── aidlc/features/            # BDD feature files
│   └── cross-stack/     # 跨组件集成场景
├── aidlc/tests/
│   ├── contract/        # 合约测试 (INT-FR level)
│   └── cross-stack/     # 跨组件 e2e 测试
├── aidlc/openspec/            # AI-DLC 制品
│   └── changes/{id}/
│       ├── spec-delta.md
│       ├── design.md
│       ├── task-list.md
│       ├── contract-diff.md
│       └── walkthrough.md
├── aidlc/providers/           # 云平台部署配置
│   ├── tcb/
│   └── aliyun/
└── aidlc/tools/               # 生成器 & 工具脚本
    ├── generate_shared.py
    ├── contract_diff.py
    └── deploy_stack.py
```

### 12.2 组件内部结构

```
apps/{component}/
├── src/              # 实现代码
├── tests/
│   ├── unit/         # TDD 单元测试
│   ├── integration/  # 集成测试
│   └── e2e/          # E2E 测试 (against preview URL)
├── features/         # BDD feature files
│   └── steps/        # BDD step definitions
└── .skill/           # 组件级 skill (自动生成)
    └── SKILL.md
```

### 12.3 组件开发速查

| 组件 | 语言 | 框架 | 测试 |
|------|------|------|------|
| Backend | Python/Node/Go | FastAPI/Express/Gin | pytest-bdd |
| Native | TypeScript/Dart | React Native/Flutter | Detox/Maestro |
| Desktop | TypeScript/Rust | Electron/Tauri | Spectron/WebDriverIO |
| WXA | JavaScript | WeChat Mini | Jest/miniprogram-automator |
| MYA | JavaScript | Alipay Mini | Jest |
| TTA | TypeScript | TikTok Mini | Jest |

---

## 13. Cloud Provider

### 13.1 TCB（腾讯云开发，默认）

| 能力 | 规格 |
|------|------|
| Functions | CloudBase Functions (SCF) 或 CloudBase Run (container) |
| DB | DocDB + MySQL |
| Storage | COS |
| Hosting | CloudBase Hosting + Preview |
| Preview URL | `https://{env-id}.tcb-preview.com` |
| FaaS | 60s / 1536MB |
| CaaS | 3600s / 4096MB |

### 13.2 Aliyun（阿里云）

| 能力 | 规格 |
|------|------|
| Functions | Function Compute (FC) 或 SAE 2.0 |
| DB | RDS + TableStore |
| Storage | OSS |
| Hosting | Static Website + CDN |
| Preview URL | `https://{gateway}.{region}.fc.devs.com` |
| FaaS | 600s / 3072MB |
| CaaS | 86400s / 32768MB |

### 13.3 部署流程

```
preview:
  deploy_stack --preview → per-component e2e → cross-stack e2e

staging:
  deploy_stack --staging → smoke test → cross-stack e2e

production:
  human approval → deploy_stack --production → BVT
  BVT fail → automatic stack rollback
```

---

## 14. Quality Gates 质量门

| 门 | 命令 | 阈值 | 范围 |
|----|------|------|------|
| TDD coverage | `pytest --cov` per component | ≥80% | 组件 |
| BDD scenarios | `pytest-bdd features/` | 100% pass | 组件 |
| Security | `bandit -r apps/` | 0 vulns | 组件 |
| Contract tests | `pytest aidlc/tests/contract/` | 100% pass | 跨组件 |
| Contract compat | `aidlc/tools/contract_diff.py` | backward-compat | 跨组件 |
| Cross-stack e2e | `pytest aidlc/tests/cross-stack/ --stack-url $STACK_URL` | 100% pass | 栈 |
| Stack BVT | `bvt ${PRODUCTION_URL}` | all checks pass | 栈 |
| No secrets in diff | audit | 0 | 全栈 |

**质量门配置** (`skill.yaml`)：

```yaml
quality_gates:
  coverage_min: 80
  bdd_pass_rate: 100
  contract_diff: required
  no_todo: true
  no_secrets_in_diff: true
```

---

## 15. Brownfield 存量项目

对已有项目，AI-DLC 支持自动生成语义上下文：

```bash
./brownfield/generate-context.sh       # 生成 aidlc/AI-DLC-CONTEXT.md
./brownfield/scripts/discover.sh       # 组件发现
./brownfield/scripts/extract-api.sh    # API 表面提取
./brownfield/scripts/deps.sh           # 跨组件依赖图
```

输出 `aidlc/AI-DLC-CONTEXT.md` 包含：
- 组件清单 + 技术栈
- API 端点摘要
- 跨组件依赖 Mermaid 图
- 架构概览

---

## 16. Cross-Tool 跨工具导出

AI-DLC 可将规则/配置导出到多个 AI 编码工具：

| 工具 | 输出 | 脚本 |
|------|------|------|
| Cursor | `.cursor/rules/ai-dlc-core.mdc` | `cross-tool/cursor/export.sh` |
| Cline | `.clinerules` | `cross-tool/cline/export.sh` |
| Copilot | `.github/copilot-instructions.md` | `cross-tool/copilot/export.sh` |
| onecode | `.cdh/config.yaml`, `.cdh/state.json`, 组件 `.skill/SKILL.md` | `cross-tool/onecode/export.sh` |

---

## 17. 与 onecode 的集成

### 17.1 OpenCode 插件

`.opencode/plugin/cdh-ai-dlc.ts` 自动将 AI-DLC 内容注入到系统提示中：

1. 查找 `ai-dlc-skill/SKILL.md` 或 `.opencode/skills/ai-dlc-skill/SKILL.md`
2. 读取文件，剥离 YAML frontmatter
3. 将 body 包裹在 `<!-- AI-DLC:start v=3.0.0 -->` ... `<!-- AI-DLC:end -->` 中注入到系统 prompt

### 17.2 项目文档加载

`onecode/agent/project_doc.py` 的 `load_project_doc()` 直接读取 `AGENTS.md` 文件内容并注入为项目上下文（使用 `<!-- PROJECT_DOC -->` 标记）。AGENTS.md 头部包含 `Skill Location` 字段指向 SKILL.md 的实际路径。

注意：`load_project_doc()` 不会解析或追加 SKILL.md 内容——SKILL.md 通过 `<!-- SKILL:ai-dlc-skill -->` 标记单独注入。

### 17.3 CDH 脚手架

`cdh scaffold` 命令创建的 monorepo 项目天然包含 AI-DLC 结构：
- `aidlc/contracts/`、`aidlc/packages/shared/`、`aidlc/tests/`
- `aidlc/providers/tcb/` 云配置
- `aidlc/tools/` 三个核心脚本
- FR 命名空间用于 AI-DLC 生命周期

---

## 18. 文件清单

`ai-dlc-skill/` 目录共 66 个文件：

```
ai-dlc-skill/
├── SKILL.md                         # Master Orchestrator 入口
├── skill.yaml                       # 技能元数据、拓扑、质量门
├── aidlc/
│   ├── CONFIG.md                    # 路径变量定义
│   └── tools/                       # deploy_stack.sh, contract_diff.py, generate_shared.py
│
├── core/
│   ├── adaptive-flow.md             # L1-L5 复杂度评估
│   ├── security.md                  # SEC-001 ~ SEC-007 安全基线
│   └── task-registry.md             # 任务状态注册表
│
├── phases/
│   ├── understand/                  # Phase ①: entry, lifecycle, rules, prompt
│   ├── plan/                        # Phase ②: entry, lifecycle, rules, prompt
│   ├── verify/                      # Phase ③: entry, lifecycle, rules, prompt
│   └── deliver/                     # Phase ④: entry, lifecycle, rules, prompt
│
├── practices/
│   ├── sdd.md                       # Spec-Driven Development
│   ├── bdd.md                       # Behavior-Driven Development
│   └── tdd.md                       # Test-Driven Development
│
├── components/                      # 6 个组件开发指南
│   ├── backend.md, native.md, desktop.md
│   ├── wxa.md, mya.md, tta.md
│
├── architecture/
│   └── project-structure.md         # 项目布局
│
├── contracts/
│   └── README.md                    # 三层合约说明
│
├── providers/
│   ├── README.md
│   ├── tcb/                         # TCB: provider, preview, deployment
│   └── aliyun/                      # Aliyun: provider, preview, deployment
│
├── brownfield/
│   ├── README.md
│   ├── entry.md                     # Brownfield phase entry
│   ├── generate-context.sh
│   └── scripts/                     # discover, extract-api, deps
│
├── cross-tool/
│   ├── README.md
│   ├── cursor/export.sh
│   ├── cline/export.sh
│   ├── copilot/export.sh
│   └── opencode/export.sh
│
├── walkthrough/
│   ├── collect.sh
│   └── template.md
│
└── templates/
    ├── understand/                  # intent, spec-delta, feature
    ├── plan/                        # design, task-list
    ├── verify/                      # test-unit.py
    ├── integration/                 # openapi.yaml, asyncapi.yaml, contract-spec, contract-diff, CHANGELOG
    └── project/                     # README.md, template.md
```
