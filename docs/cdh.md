# CDH — Cloud Dev Harness 平台层

> 版本: 1.0.6 (与 onecode 同步)
> 定位: AI Agent 的编排与运维平台

---

## 目录

1. [概述](#1-概述)
2. [架构总览](#2-架构总览)
3. [CLI](#3-cli)
4. [项目脚手架 (AI-DLC)](#4-项目脚手架-ai-dlc)
5. [项目加载器](#5-项目加载器)
6. [Session 管理](#6-session-管理)
7. [Session 聚合器](#7-session-聚合器)
8. [Event Loop](#8-event-loop)
9. [Verification Loop](#9-verification-loop)
10. [Hill-climb Optimizer](#10-hill-climb-optimizer)
11. [配置与状态存储](#11-配置与状态存储)
12. [事件流总览](#12-事件流总览)

---

## 1. 概述

CDH (Cloud Dev Harness) 是 **AI Agent 的编排与运维平台**，位于 onecode 引擎和 TUI 之间，提供：

- **CLI 入口** — 统一管理项目、会话、引擎配置
- **AI-DLC 生命周期** — 脚手架生成四层开发流程 (Understand → Plan → Verify → Deliver)
- **跨引擎服务** — Session 聚合、事件总线、验证门禁、配置优化
- **项目状态管理** — `.cdh/` 目录的创建、加载、持久化

```
关系:
  cdh/      → 平台层 (编排 + 基础设施)
  onecode/  → 引擎层 (Agent 框架)
  tui/      → 展示层 (Textual 终端 UI)
```

---

## 2. 架构总览

```
cdh/
├── __init__.py                    # 包标记
├── __main__.py                    # python -m cdh 入口
├── cli.py                         # Click CLI (794 行)
├── cli_logging.py                 # 文件日志 (轮转, 7 天保留)
├── config.py                      # 活跃项目指针 (~/.cdh/active_project.yaml)
├── project_loader.py              # .cdh/ 目录发现与状态读写
├── scaffold.py                    # AI-DLC 项目脚手架
├── session_store.py               # Session JSON 文件 CRUD
├── cdh_session_aggregator.py      # 跨引擎 Session SQLite 注册表
│
├── event_loop/                    # 事件循环 (L3)
│   ├── bus.py                     # EventBus (pub/sub, 历史)
│   ├── events.py                  # 事件类型定义
│   ├── scheduler.py               # 定时调度器 (cron)
│   └── runner.py                  # 事件→引擎启动器
│
├── optimizer/                     # 配置优化 (L4)
│   ├── loop.py                    # HillclimbLoop 主循环
│   ├── reward.py                  # 奖励信号计算
│   ├── mutation.py                # 参数变异
│   └── tracker.py                 # SQLite 优化轨迹
│
└── verification/                  # 验证循环 (L2)
    ├── loop.py                    # PlatformVerificationLoop
    ├── aggregation.py             # GateResult / AggregateResult
    ├── policy.py                  # 验证策略 + 文件类型检测
    └── gates/                     # 门禁实现
        ├── base.py                # Gate 抽象基类
        ├── lint_gate.py           # ruff check
        └── test_gate.py           # pytest
```

---

## 3. CLI

### 3.1 入口

```bash
cdh [OPTIONS] COMMAND [ARGS]...
```

### 3.2 顶级命令

| 命令 | 说明 |
|------|------|
| `cdh` (无参数) | 启动 TUI Agent Store |
| `cdh tui [--project-dir]` | 启动 TUI |
| `cdh onecode <sub>` | onecode CLI 命名空间 |
| `cdh project <action>` | 项目管理 |
| `cdh session <action>` | 会话管理 |
| `cdh version` | 版本信息 |
| `cdh help [command]` | 帮助 |
| `cdh uninstall` | 移除 ~/.cdh/ 全局状态 |

### 3.3 `cdh onecode` 子命令

挂载 onecode CLI 命令:

| 命令 | 说明 |
|------|------|
| `cdh onecode config` | 打开 TUI 配置编辑器 |
| `cdh onecode config mode` | 获取/设置 Agent 模式 |
| `cdh onecode config model` | 获取/设置默认模型 |
| `cdh onecode config provider` | 获取/设置默认 Provider |
| `cdh onecode config log-level` | 获取/设置日志级别 |
| `cdh onecode config skill` | 管理技能 |
| `cdh onecode config mcp` | 管理 MCP |
| `cdh onecode config list` | 导出 YAML 配置 |
| `cdh onecode codebase` | 管理代码库索引 |
| `cdh onecode memory` | 管理记忆 |
| `cdh onecode skill` | 安装/启用/禁用/移除技能 |
| `cdh onecode mcp` | 配置 MCP |
| `cdh onecode help` | onecode CLI 帮助 |
| `cdh onecode version` | onecode 版本 |

### 3.4 `cdh project` 子命令

| 动作 | 说明 |
|------|------|
| `select` (默认) | 打开项目管理 TUI |
| `list` | 列出项目 |
| `show <name>` | 显示项目详情 |
| `new <name> [path]` | 创建新项目 (交互式组件选择) |
| `init [path]` | 在现有目录初始化 `.cdh/` |
| `load <name>` | 加载项目为当前项目 |
| `add-component <name>` | 为项目添加组件 |
| `add-cross-cutting <name>` | 为项目添加横切关注点 |

### 3.5 `cdh session` 子命令

| 动作 | 说明 |
|------|------|
| `list` | 列出最近会话 |
| `load <id>` | 加载会话 |

### 3.6 启动流程

```
cdh (无参数)
  → 检查 LogLevel 覆盖
  → 设置日志
  → 加载活跃项目 (如果有)
  → 启动 tui.app.A2TUIApp (Agent Store)
```

---

## 4. 项目脚手架 (AI-DLC)

### 4.1 AI-DLC 四层生命周期

```
① Understand (SDD+BDD)    意图 → Spec Delta → BDD Feature 文件
② Plan (SDD+TDD)          设计文档 → Task DAG → 测试计划
③ Verify (BDD+TDD)        Red → Green → Refactor (每场景)
④ Deliver (SDD+Cloud)     Stack Preview → e2e → 生产 + BVT
```

复杂度评估 (L1-L5) 决定激活哪些阶段。

### 4.2 组件规格

| ID | 名称 | 技术栈 | 目录 | FR 前缀 |
|----|------|--------|------|---------|
| `native` | Mobile App | RN/Flutter | `apps/native/` | NATIVE |
| `desktop` | Desktop App | Electron/Tauri | `apps/desktop/` | DESKTOP |
| `web` | Web Frontend | React/Vue/Svelte | `apps/web/` | WEB |
| `backend` | Backend Service | Python/Node/Go | `apps/backend/` | BE |
| `wxa` | WeChat Mini | - | `apps/wxa/` | WXA |
| `mya` | Alipay Mini | - | `apps/mya/` | MYA |
| `tta` | TikTok Mini | - | `apps/tta/` | TTA |

### 4.3 横切关注点

| ID | 说明 |
|----|------|
| `contracts` | aidlc/contracts/CHANGELOG.md |
| `shared` | aidlc/packages/shared/ |
| `openspec` | OpenSpec 变更提案 |
| `cross_stack_features` | 跨栈 BDD Feature |
| `cross_stack_tests` | aidlc/tests/contract, aidlc/tests/cross-stack |
| `provider` | TCB Provider 配置 |
| `tools` | deploy_stack, contract_diff, generate_shared |

### 4.4 脚手架输出

```
<project>/
├── aidlc/
│   ├── project.yaml          # 项目元数据 + 栈拓扑
│   ├── requirements.md       # 需求文档
│   └── CHANGELOG.md
├── apps/
│   ├── <component>/
│   │   ├── src/
│   │   ├── tests/unit/
│   │   ├── tests/e2e/
│   │   └── features/
│   └── ...
├── .cdh/                     # 项目状态 (自动创建)
├── AGENTS.md                 # 项目章程 (质量门禁, 文件规则)
└── CLAUDE.md                 # Claude Code 兼容配置
```

### 4.5 API

```python
def init_dlc_project(workspace_root, project_name, description="") -> bool
def scaffold_dlc_project(workspace_root, project_name, components, description="") -> bool
def add_component(workspace_root, component_id) -> bool
def add_cross_cutting(workspace_root, cross_id) -> bool
```

---

## 5. 项目加载器

### 5.1 `CdhProjectLoader` (静态方法类)

| 方法 | 说明 |
|------|------|
| `find_cdh_dir(workspace_root)` | 向上遍历查找 `.cdh/` |
| `load_project_config(cdh_dir)` | 读取 `.cdh/config.yaml` |
| `load_project_state(cdh_dir)` | 读取 `.cdh/state.json` |
| `save_state(cdh_dir, state_data)` | 写入 `.cdh/state.json` |
| `load_for_workspace(workspace_root)` | 返回项目状态的 Markdown 摘要 |
| `save_last_session / load_last_session` | 持久化最后会话 |
| `save_todos / load_todos` | 持久化 TODO 列表 |
| `save_permissions / load_permissions` | 持久化权限决定 |
| `init_project(workspace_root, name, ...)` | 创建 `.cdh/` 初始化 |

### 5.2 `.cdh/` 目录结构

```
.cdh/
├── config.yaml              # 项目名称 + 配置
├── state.json               # 当前阶段 + 已完成阶段 + Gate 结果
├── last_session.json        # 最后会话 ID
├── todos.json               # TODO 持久化
└── permissions.json         # 权限决定持久化
```

---

## 6. Session 管理

### 6.1 `session_store.py` — SessionData / AgentSession

```python
@dataclass
class SessionData:
    id: str
    name: str
    mode: str
    project: str | None
    model: str
    provider: str
    messages: list
    lifecycle_state: str
    todos: list
    created_at: str
    updated_at: str
```

| 方法 | 说明 |
|------|------|
| `list_sessions()` | 列出所有会话 |
| `load(session_id)` | 加载会话 |
| `delete_by_id(session_id)` | 删除会话 |
| `add_message(message)` | 添加消息 |
| `compact_messages()` | 压缩消息历史 |
| `update_state(**kwargs)` | 更新状态 |

存储位置: `~/.cdh/sessions/{id}.json`

自动迁移: 首次使用时从 `~/.onecode/sessions/` 迁移到 `~/.cdh/sessions/`。

---

## 7. Session 聚合器

### 7.1 `cdh_session_aggregator.py` — CdhSessionAggregator

跨引擎 SQLite Session 注册表。

数据库位置: `~/.cdh/sessions/sessions.db`

表结构:

```sql
sessions (
    id INTEGER PRIMARY KEY,
    engine TEXT NOT NULL,           -- 引擎名
    engine_session_id TEXT NOT NULL, -- 引擎内 ID
    project_name TEXT,
    agent TEXT,
    title TEXT,
    protocol TEXT,
    prompt_count INTEGER DEFAULT 0,
    created_at TEXT,
    last_used TEXT,
    meta_json TEXT,
    UNIQUE(engine, engine_session_id)
)
```

| 方法 | 说明 |
|------|------|
| `register(engine, session_id, agent, ...)` | 注册会话 |
| `update_last_used(engine, session_id)` | 更新时间戳 |
| `increment_prompt_count(engine, session_id)` | 增加提示计数 |
| `get(session_id)` | 按行 ID 获取 |
| `get_by_engine_id(engine, session_id)` | 按引擎 ID 获取 |
| `get_recent(max_results)` | 获取最近会话 |
| `get_by_engine(engine, max_results)` | 按引擎筛选 |
| `get_by_project(project_name, max_results)` | 按项目筛选 |
| `delete(session_id)` | 删除 |
| `count()` | 总数 |
| `list_engines()` | 列出所有引擎 |
| `import_from_tui_db(tui_db_path)` | 从 tui.db 批量导入 |



## 8. Event Loop

### 8.1 `EventBus` (bus.py)

发布/订阅事件总线:

```python
bus = EventBus()
bus.subscribe("file.changed", handler)
bus.publish(Event(type="file.changed", source="watchdog", payload={"path": "..."}))
```

| 方法 | 说明 |
|------|------|
| `subscribe(type, handler)` | 订阅事件 |
| `unsubscribe(type, handler)` | 取消订阅 |
| `publish(event)` | 发布事件 (错误隔离) |
| `get_history(type, limit)` | 获取历史 |
| `start()` / `stop()` | 启动/停止 |

状态: `IDLE → RUNNING → PAUSED → COMPLETED → FAILED`

### 8.2 事件类型

| 常量 | 值 | 发布者 |
|------|-----|--------|
| `SESSION_STARTED` | `session.started` | 引擎 |
| `SESSION_ENDED` | `session.ended` | 引擎 |
| `FILE_CHANGED` | `file.changed` | Watchdog (所有引擎) |
| `TOOL_EXECUTED` | `tool.executed` | 引擎/ACP Tap |
| `TOOL_FAILED` | `tool.failed` | 引擎/ACP Tap |
| `VERIFICATION_PASSED` | `verification.passed` | VerificationLoop |
| `VERIFICATION_FAILED` | `verification.failed` | VerificationLoop |
| `CRON_TICK` | `cron.tick` | Scheduler |
| `CONFIG_CHANGED` | `config.changed` | Optimizer |

### 8.3 `Scheduler` (scheduler.py)

异步定时调度器:

```python
scheduler = Scheduler()
scheduler.add("daily-lint", interval=86400, command="ruff check")
scheduler.start(bus)  # 发布 CRON_TICK 事件
scheduler.stop()
```

- 作业持久化: `~/.cdh/scheduler.db` (JSON)
- 每秒 tick 检查到期作业

### 8.4 `EventRunner` (runner.py)

订阅 `CRON_TICK` 和 `FILE_CHANGED` 事件，作为平台事件处理器。

---

## 9. Verification Loop

### 9.1 `PlatformVerificationLoop` (loop.py)

文件变化触发的验证门禁:

```
引擎写文件 → 文件系统变化 → EventBus(FILE_CHANGED)
  → PlatformVerificationLoop
    → 检查文件类型 (.py/.js/.ts/...)
    → 运行所有 Gate
    → 发布 VERIFICATION_PASSED 或 VERIFICATION_FAILED
```

### 9.2 Gate 门禁

| Gate | 命令 | 说明 |
|------|------|------|
| `LintGate` | `ruff check <project>` | 代码风格检查 |
| `TestGate` | `pytest <project>/tests -x --tb=short` | 测试运行 |

Gate 抽象:

```python
class Gate(ABC):
    name: str
    enabled: bool
    def should_run(self, file_path) -> bool
    async def run(self, project_dir) -> GateResult
```

### 9.3 结果聚合

```python
@dataclass
class GateResult:
    name: str
    status: str           # "passed" / "failed" / "skipped"
    exit_code: int | None
    duration_ms: int
    summary: str
    log_path: str | None

@dataclass
class AggregateResult:
    gate_results: dict[str, GateResult]
    timestamp: str
    # properties: passed, failed, skipped, failed_gates
```

### 9.4 策略

| 策略 | 说明 |
|------|------|
| `EVERY_STEP` | 每次文件变化都验证 |
| `FINAL_ONLY` | 仅在 Session 结束时验证 |
| `CONDITIONAL` | 按文件类型 + 工具名条件验证 |

### 9.5 跨引擎行为

| 引擎 | 触发方式 | 延迟 |
|------|---------|------|
| onecode | 文件变化 + HookManager 内联 | ~100ms (内联) + ~1s (文件) |
| opencode/claude/cursor | 仅文件变化 | ~1s |

---

## 10. Hill-climb Optimizer

### 10.1 `HillclimbLoop` (loop.py)

基于指标的配置优化循环:

```
状态机: IDLE → COLLECTING → EVALUATING → MUTATING → DEPLOYING → COLLECTING ...
```

订阅事件:
- `SESSION_ENDED` → 触发评估
- `TOOL_EXECUTED` → 计数
- `VERIFICATION_PASSED/FAILED` → 统计

### 10.2 指标

| 指标 | 权重 | 推导方式 |
|------|------|---------|
| `test_pass_rate` | 0.4 | VERIFICATION_PASSED / (PASSED + FAILED) |
| `task_completion_pct` | 0.3 | 从 Session metrics 或默认 0.5 |
| `tool_efficiency` | 0.2 | min(1.0, 10.0 / max(tool_call_count, 1)) |
| `user_feedback` | 0.1 | 从 Session 提取 |

奖励 = test_pass * 0.4 + task_complete * 0.3 + tool_eff * 0.2 + user_fb * 0.1

### 10.3 `ConfigMutator` (mutation.py)

```python
@dataclass
class ConfigMutation:
    platform_params: dict       # 如 {"verification.policy": "conditional"}
    engine_params: dict         # 如 {"onecode.dev": {"temperature": 0.7}}
    timestamp: str
    parent_reward: float
```

变异策略:
- reward < 0.5: 总是变异
- reward >= 0.8: 收敛, 不变异
- 其他: 概率变异

可变异参数:

| 参数 | 类型 | 范围 |
|------|------|------|
| `verification.policy` | 枚举 | strict / adaptive / conditional / relaxed |
| `temperature` | float | 0.1 ~ 1.0 |
| `max_iterations` | int | 5 ~ 30 |
| `plan_gate_mode` | 枚举 | auto / on / off |

### 10.4 `RewardCalculator` (reward.py)

```python
RewardCalculator.compute(metrics: SessionMetrics) -> float
RewardCalculator.compute_all(metrics_list) -> float  # 平均
```

### 10.5 `OptimizationTracker` (tracker.py)

SQLite 持久化 (`~/.cdh/optimizer.db`):

```sql
-- sessions 表: 每次 Session 的指标 + 奖励
-- mutations 表: 已应用的变异 + 奖励
```

| 方法 | 说明 |
|------|------|
| `record(metrics, reward)` | 记录 Session 指标 |
| `get_all()` | 所有记录 |
| `count()` | 记录数 |
| `clear()` | 清空 |
| `save_mutation(mutation, reward)` | 记录变异 |
| `get_best_mutation()` | 最佳变异 |

### 10.6 输出: `~/.cdh/agent_config.yaml`

```yaml
version: 1
platform:
  verification:
    policy: conditional
    gates: [lint, test]
engine:
  onecode.dev:
    temperature: 0.8
    max_iterations: 15
  opencode.ai:
    max_turns: 20
```

- `platform`: 所有引擎共享 (verification policy)
- `engine`: 按 identity 索引, 引擎自己决定是否读取

---

## 11. 配置与状态存储

| 文件 | 位置 | 说明 |
|------|------|------|
| 活跃项目 | `~/.cdh/active_project.yaml` | 当前项目指针 |
| 项目配置 | `.cdh/config.yaml` | 项目名称+平台+版本 |
| 项目状态 | `.cdh/state.json` | 阶段+Gate 结果 |
| 优化配置 | `~/.cdh/agent_config.yaml` | L4 变异输出 |
| 优化历史 | `~/.cdh/optimizer.db` | SQLite |
| 调度器 | `~/.cdh/scheduler.db` | JSON |

| Session 聚合 | `~/.cdh/sessions/sessions.db` | SQLite |
| Session 文件 | `~/.cdh/sessions/{id}.json` | JSON |
| 平台日志 | `~/.cdh/logs/cdh.log` | 轮转, 7 天 |
| 项目状态 | `.cdh/todos.json` | TODO |
| 项目状态 | `.cdh/last_session.json` | 最后会话 |
| 项目状态 | `.cdh/permissions.json` | 权限 |

---

## 12. 事件流总览

```
发布者                             事件类型                    订阅者
─────                             ──────                     ──────
所有引擎 (文件变化)                FILE_CHANGED               PlatformVerificationLoop
onecode (直接)                     TOOL_EXECUTED              HillclimbLoop
ACP Event Tap (被动嗅探)           TOOL_EXECUTED              HillclimbLoop
PlatformVerificationLoop           VERIFICATION_PASSED/FAILED HillclimbLoop
Scheduler                          CRON_TICK                  EventRunner → 引擎启动
HillclimbLoop                      CONFIG_CHANGED             (预留)
```

### 数据流依赖

```
Hillclimb 依赖:
  ├── TOOL_EXECUTED 事件计数    → tool_efficiency
  ├── VERIFICATION_PASSED/FAILED → test_pass_rate
  └── SESSION_ENDED 事件         → 触发计算

所有引擎: 文件变化 → PlatformVerificationLoop → EVENT_BUS → Hillclimb
onecode 增强: 额外有 HookManager 内联 + TurnRecord 细粒度指标
```
