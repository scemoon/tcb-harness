# 四层 Loop 架构设计

> 版本: 1.0.6 — 对应分支 `1.0.6`
> 适用范围: `onecode/` 引擎层 + `cdh/` 平台层 + `tui/acp/` ACP 协议层

---

## 目录

1. [概述与设计原则](#1-概述与设计原则)
2. [跨引擎兼容性](#2-跨引擎兼容性)
3. [整体架构图](#3-整体架构图)
4. [状态机模型](#4-状态机模型)
5. [L1: Agent Loop (ReAct)](#5-l1-agent-loop-react)
6. [L2: Verification Loop](#6-l2-verification-loop)
7. [L3: Event Loop](#7-l3-event-loop)
8. [L4: Hill-climb Loop](#8-l4-hill-climb-loop)
9. [ACP 协议扩展: session/event](#9-acp-协议扩展-sessionevent)
10. [配置系统](#10-配置系统)
11. [Cross-engine 数据流](#11-cross-engine-数据流)
12. [引擎兼容性矩阵](#12-引擎兼容性矩阵)
13. [实现路线图](#13-实现路线图)

---

## 1. 概述与设计原则

### 1.1 核心问题

当前 `onecode` 只有单层 ReAct loop (`chat_stream()` in `engine.py`)，缺少：

- **质量控制**：没有系统性门禁验证 agent 输出的质量
- **事件驱动**：没有平台级的事件总线处理定时/文件变化/webhook
- **自演进**：没有基于历史轨迹的参数优化

### 1.2 设计原则

| 编号 | 原则 | 说明 |
|------|------|------|
| P1 | **L1 不动核心** | 现有 ReAct 循环是稳定核心，只增强可观测性，不改控制流 |
| P2 | **增量可插拔** | L2~L4 都是新增独立模块，通过现有接口注入 (EventBus, ACP) |
| P3 | **每层可独立开关** | 通过配置 `loops.*.enabled` 控制 |
| P4 | **不依赖引擎主动合作** | 平台功能通过被动观察（文件变化、ACP 嗅探）实现，不要求外部引擎修改 ACP 实现 |
| P5 | **CDH 管编排与验证，引擎管执行** | L2(L3(L4 的编排/验证部分放在 `cdh/`，L1 在各自引擎中 |

### 1.3 四层职责

| 层 | 名称 | 职责 | 归属 | 跨引擎兼容 |
|----|------|------|------|-----------|
| L1 | Agent Loop | 执行具体 task: Thought→Action→Observation | 引擎私有 | 各自实现 |
| L2 | Verification Loop | 质量门禁: lint/type/test 验证 | `cdh/verification/` (平台) + `onecode/verification/` (可选加速) | ✅ 文件触发，所有引擎自动生效 |
| L3 | Event Loop | 事件总线: 定时/文件变化/ACP 嗅探 → 引擎启动 | `cdh/event_loop/` + `tui/acp/event_tap.py` | ✅ 被动嗅探，零引擎配合 |
| L4 | Hill-climb Loop | 自迭代优化: 基于平台指标的自动调参 | `cdh/optimizer/` | ✅ 指标从平台推导，所有引擎适用 |

---

## 2. 跨引擎兼容性

### 2.1 ACP 架构真相

CDH 通过 ACP (Agent Client Protocol) 与所有引擎通信。**CDH 只实现了 onecode 的 ACP server**。其他引擎的 ACP server 由各自团队独立实现：

```
引擎      ACP Server 位置                       控制方
───      ──────────────────                    ────
onecode  onecode/agent/onecode_agent_acp.py    CDH (本仓库)
opencode opencode 二进制 (npm publish)          opencode 团队
claude   claude-agent-acp (npm publish)         claude 团队
cursor   agent acp (npm publish)                cursor 团队
其他 17  各自独立二进制                          各自团队
```

TUI 的 `tui/acp/agent.py` 是一个**通用 ACP 客户端**，对所有引擎同等待遇——从 TOML 读 `run_command` → 开子进程 → 读写 stdin/stdout JSON-RPC。

**没有代理层、没有包装器、没有拦截器。**

### 2.2 引擎兼容策略

CDH 无法要求外部引擎修改 ACP 实现。解决方案：

| 功能 | 策略 | 实现 |
|------|------|------|
| L2 验证 | **被动文件观察** — 引擎写文件 → 文件系统变化 → CDH 触发验证 | `cdh/verification/loop.py` 监听 `file.changed` 事件 |
| L3 事件 | **ACP 被动嗅探** — 从已有 ACP `session/update` 消息流中提取信息 | `tui/acp/event_tap.py` 在 dispatch 中旁路数据 |
| L4 指标 | **平台推导** — 从事件总线统计 + TUI exit_metrics 提取 | `cdh/optimizer/loop.py` 的 `subscribe()` |

### 2.3 onecode 的额外能力

onecode 是唯一有完整源码的引擎，因此提供可选的增强通道：

| 能力 | 跨引擎通道 | Onecode 增强通道 |
|------|-----------|-----------------|
| 验证触发 | 文件变化 (延迟 ~秒) | `engine.py` 内联 Hook (零延迟, step 级) |
| 事件通知 | ACP 嗅探 (推测) | 直接 `EventBus.publish()` (精确) |
| 指标采集 | 平台推导 (粗粒度) | `TurnRecord` 采集 (细粒度) |

---

## 3. 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CDH 平台层                                       │
│                                                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                      L2: Verification Loop                          │   │
│   │  cdh/verification/                                                   │   │
│   │                                                                       │   │
│   │  订阅: EventBus (file.changed)         触发: 文件变化              │   │
│   │  执行: 在项目目录运行 ruff/mypy/pytest 输出: EventBus               │   │
│   │  适配: 所有引擎 (onecode/opencode/claude 写文件都能触发)           │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                        L3: Event Loop                                │   │
│   │  cdh/event_loop/ + tui/acp/event_tap.py                              │   │
│   │                                                                       │   │
│   │   ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐      │   │
│   │   │  EventBus    │  │  Scheduler   │  │  ACP Event Tap      │      │   │
│   │   │  (pub/sub)   │◄─│  (定时)       │  │  (被动嗅探)          │      │   │
│   │   └──────┬──────┘  └──────────────┘  └─────────┬────────────┘      │   │
│   │          │                                       │                   │   │
│   │          │   从 ACP 流被动提取:                   │                   │   │
│   │          │   tool_call → TOOL_EXECUTED            │                   │   │
│   │          │   agent_message → agent.streaming      │                   │   │
│   │          │                                       │                   │   │
│   │          └────────────────┬──────────────────────┘                   │   │
│   │                           ▼                                          │   │
│   │                 EventRunner → 启动引擎 session                       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                     L4: Hill-climb Loop                               │   │
│   │  cdh/optimizer/                                                       │   │
│   │                                                                       │   │
│   │  输入: EventBus (tool.executed, verification.*, session.ended)       │   │
│   │  计算: reward (test_pass, tool_efficiency, task_complete)            │   │
│   │  输出: ~/.cdh/agent_config.yaml (平台参数 + 引擎参数)               │   │
│   │  适配: 所有引擎 — 指标从平台推导，无需引擎报告                       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │   ACP 子进程边界              │
                    │   stdin/stdout JSON-RPC      │
                    │   (通用协议，所有引擎相同)     │
                    └──────────────┬──────────────┘
                                   │
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                                                                        │
   │   onecode (内置引擎)     opencode (外部引擎)      claude (外部引擎)   │
   │   ──────────────────     ──────────────────     ─────────────────     │
   │   L1: chat_stream()      L1: internal ReAct       L1: internal ReAct   │
   │   ACP: 自有实现           ACP: opencode 二进制   ACP: claude-agent  │
   │   ├─ 直接 EventBus        └─ ACP stdout ──┐      └─ ACP stdout ──┐ │
   │   ├─ 内联 Hook (L2)                           │                       │ │
   │   └─ TurnRecord (L4)                        │                       │ │
   │                                              ▼                       ▼ │
   │                                     TUI ACP Event Tap (被动嗅探)      │
   │                                     ┌──────────────────────┐         │ │
   │                                     │ on_session_update()  │         │ │
   │                                     │ → EventBus publish  │         │ │
   │                                     └──────────────────────┘         │ │
   └─────────────────────────────────────────────────────────────────────────┘
```

### 关键数据流

```
所有引擎 (文件变化触发):
  引擎写文件 → 文件系统变化 → watchdog → EventBus(file.changed)
    → cdh/verification/ → ruff check / mypy / pytest
    → EventBus(verification.passed/failed)
    → cdh/optimizer/ (统计 test_pass_rate)

外部引擎 (ACP 嗅探):
  ACP stdin/stdout: session/update(tool_call)
    → tui/acp/agent.py 的 rpc_session_update()
    → tui/acp/event_tap.py 的 on_session_update() (旁路)
    → EventBus.publish(tool.executed)
    → cdh/optimizer/ (统计 tool_efficiency)

onecode (增强通道):
  engine.py 的 chat_stream() 中 HookManager
    → 直接 EventBus.publish(tool.executed) (零延迟)
    → onecode/verification/ 内联 LintGate (step 级别)
    → TurnRecord 精确 metrics
```

---

## 4. 状态机模型

### 4.1 全局 Layer State (每层独立)

```
                IDLE
                 │
                 ▼
             RUNNING
              │    │
              │    ▼
              │ COMPLETED
              │
              ▼
            FAILED
              │
              ▼
            PAUSED ──▶ RUNNING
```

### 4.2 各层状态枚举

| 层 | 状态值 | 默认 |
|----|--------|------|
| L1 Agent | `IDLE`, `RUNNING` | `IDLE` |
| L2 Verify (platform) | `IDLE`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED` | `IDLE` |
| L2 Verify (onecode) | `IDLE`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED` | `IDLE` |
| L3 Event | `IDLE`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED` | `IDLE` |
| L4 Hillclimb | `IDLE`, `COLLECTING`, `EVALUATING`, `MUTATING`, `DEPLOYING`, `COMPLETED`, `FAILED` | `IDLE` |

---

## 5. L1: Agent Loop (ReAct)

### 5.1 概述

**不做核心改动**。现有 `chat_stream()` in `engine.py:1248` 是稳定的 ReAct 核心。外部引擎各自实现自己的 ReAct 循环，CDH 不介入。

### 5.2 onecode 增强：TurnRecord

```python
# onecode/agent/turn_record.py
@dataclass
class TurnRecord:
    turn_number: int
    thought: str
    tool_name: str
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None
    tool_error: str | None = None
    duration_ms: int = 0
    verification_results: list[dict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        if self.tool_error:
            return False
        for v in self.verification_results:
            if isinstance(v, dict) and v.get("failed_gates"):
                return False
        return True
```

仅 onecode 使用。外部引擎不需要实现。

### 5.3 与上层集成

onecode 的 `engine.py` 中：

```python
# 在 chat_stream() 的 Action 阶段
turn_record = TurnRecord(turn_number=turn, ...)

# L2: onecode 内联验证 (如果启用)
if self._verification_loop and self._verification_loop.should_verify(tool_name):
    agg_result = await self._verification_loop.run_gates(turn_record)
    turn_record.add_verification(agg_result.to_dict())

# L3: onecode 直接 EventBus (如果启用)
if self._event_bridge:
    self._event_bridge.on_tool_event(ToolEvent(...))
```

---

## 6. L2: Verification Loop

### 6.1 双通道架构

```
Platform Channel (所有引擎):
  ┌────────────────────────────────────────────────────────────┐
  │  cdh/verification/                                         │
  │                                                            │
  │  PlatformVerificationLoop                                   │
  │   ├─ subscribe(EventBus) → 监听 file.changed               │
  │   ├─ 文件变化 → 判断 .py/.js/.ts → 执行 gate              │
  │   └─ 输出: verification.passed/failed 事件                 │
  └────────────────────────────────────────────────────────────┘
                  ↑
           文件系统变化 (watchdog)
                  ↑
   onecode/opencode/claude/cursor 写文件 (完全相同)

Engine Channel (仅 onecode):
                    ┌─────────────────────────────────────────┐
                    │  onecode/verification/                  │
                    │                                          │
                    │  VerificationLoop                         │
                    │   ├─ engine.py Hook 调用                 │
                    │   ├─ 每个 step 后条件触发                │
                    │   └─ 零延迟，step 级别控制               │
                    └─────────────────────────────────────────┘
```

### 6.2 Platform Verification Loop

```python
# cdh/verification/loop.py
class PlatformVerificationLoop:
    project_dir: str
    _gates: dict[str, Gate] = {"lint": LintGate(), "test": TestGate()}

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe("file.changed", self._on_file_changed)

    async def _on_file_changed(self, event: Event) -> None:
        if not is_source_file(event.payload["path"]):
            return
        # 运行所有 gate
        for gate in self._gates.values():
            await gate.run(self.project_dir)
```

触发是通过操作系统文件事件（watchdog），与引擎无关。

### 6.3 文件结构

```
cdh/verification/                    onecode/verification/
├── __init__.py                       ├── __init__.py
├── loop.py          (EventBus 驱动)   ├── loop.py          (engine.py 内联)
├── policy.py        (策略)               ├── policy.py        (策略)
├── aggregation.py   (结果聚合)          ├── aggregation.py   (结果聚合)
└── gates/                             └── gates/
    ├── __init__.py                        ├── __init__.py
    ├── base.py                          ├── base.py
    ├── lint_gate.py                     ├── lint_gate.py
    └── test_gate.py                    └── type_gate.py
                                              └── test_gate.py
```

### 6.4 触发策略 (CONDITIONAL)

| 引擎 | 触发方式 | 延迟 | 精度 |
|------|---------|------|------|
| onecode | 文件变化 + HookManager | 秒级 (文件) / 零延迟 (Hook) | step 级 |
| opencode | 文件变化 | 秒级 | 文件级 |
| claude | 文件变化 | 秒级 | 文件级 |
| cursor | 文件变化 | 秒级 | 文件级 |

---

## 7. L3: Event Loop

### 7.1 平台层 (cdh/event_loop/)

```
cdh/event_loop/
├── __init__.py
├── bus.py              # EventBus — pub/sub 核心
│   EventBus.start()
│   EventBus.stop()
│   EventBus.publish(event)
│   EventBus.subscribe(type, handler)
│   EventBus.get_history()
├── events.py           # 事件类型定义
├── scheduler.py        # 持久化定时调度器
└── runner.py           # 事件 → 引擎启动器
```

### 7.2 事件类型

```python
# cdh/event_loop/events.py
@dataclass
class Event:
    type: str
    source: str
    payload: dict[str, Any]

class EventTypes:
    SESSION_ENDED = "session.ended"
    SESSION_STARTED = "session.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    CRON_TICK = "cron.tick"
    FILE_CHANGED = "file.changed"       # 文件系统变化 (所有引擎)
    CONFIG_CHANGED = "config.changed"
    TOOL_EXECUTED = "tool.executed"       # ACP 嗅探或引擎直接推送
    TOOL_FAILED = "tool.failed"
```

### 7.3 ACP Event Tap (tui/acp/event_tap.py)

```python
# tui/acp/event_tap.py
class AcpEventTap:
    """被动嗅探 ACP session/update 流，无需引擎配合。"""

    def on_session_update(self, update: SessionUpdate) -> None:
        """调度点：在 rpc_session_update() 每个 match 分支末尾调用。"""
        if not self._collecting:
            return

        discriminator = update.get("sessionUpdate", "")
        if discriminator == "tool_call":
            self.metrics.tool_call_count += 1
        elif discriminator == "tool_call_update":
            self.metrics.tool_call_updates += 1
        elif discriminator == "ask_user":
            self.metrics.ask_user_count += 1

    def stop_collecting(self) -> dict[str, Any]:
        """Session 结束，推导平台指标。"""
        return {
            "tool_call_count": self.metrics.tool_call_count,
            "tool_efficiency": min(1.0, 10.0 / max(self.metrics.tool_call_count, 1)),
        }
```

集成点：在 `tui/acp/agent.py` 的 `rpc_session_update()` 每个 match 分支末尾增加一行：

```python
self.event_tap.on_session_update(update)
```

**不需要修改 ACP 协议。** 不需要外部引擎做任何事。已有的 `session/update` 消息流已经包含足够信息。

---

## 8. L4: Hill-climb Loop

### 8.1 指标推导 (不依赖引擎报告)

| 指标 | 平台推导方式 | 来源 |
|------|------------|------|
| `test_pass_rate` | 统计 `verification.passed` / `verification.failed` 事件 | `cdh/verification/` |
| `tool_efficiency` | ACP 嗅探统计 tool_call 数: `min(1.0, 10.0 / max(count, 1))` | `tui/acp/event_tap.py` |
| `task_completion_pct` | TUI exit_metrics 或默认 0.5 | TUI / 默认值 |

```python
# cdh/optimizer/loop.py
class HillclimbLoop:
    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(EventTypes.TOOL_EXECUTED, self._on_tool_executed)
        bus.subscribe(EventTypes.VERIFICATION_PASSED, self._on_verification_pass)
        bus.subscribe(EventTypes.VERIFICATION_FAILED, self._on_verification_fail)
        bus.subscribe(EventTypes.SESSION_ENDED, self.on_session_ended)

    def on_session_ended(self, event: Event) -> None:
        metrics = SessionMetrics(
            test_pass_rate=self._test_pass_count / max(self._test_total_count, 1),
            tool_efficiency=min(1.0, 10.0 / max(self._tool_count, 1)),
            task_completion_pct=event.payload.get("task_completion_pct", 0.5),
        )
        self.tracker.record(metrics)
```

### 8.2 输出: agent_config.yaml

```yaml
# ~/.cdh/agent_config.yaml
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

- **platform** 部分：所有引擎共享 (verification policy)
- **engine** 部分：按 `identity` 索引，引擎自己决定读不读
- onecode 的启动器负责把 `onecode.dev` 参数同步到 `onecode.config.yaml`

### 8.3 文件结构

```
cdh/optimizer/
├── __init__.py
├── loop.py          # HillclimbLoop — 主编排, subscribe EventBus
├── reward.py        # 奖励信号计算
├── mutation.py      # 参数变异 + AGENT_CONFIG_PATH
└── tracker.py       # 优化轨迹存储 (SQLite)
```

---

## 9. ACP 协议扩展: session/event

### 9.1 设计原则

**CDH 不要求外部引擎实现任何新 ACP 方法。**

所有跨引擎功能基于两种非侵入机制：

| 机制 | 原理 | 适用引擎 |
|------|------|---------|
| **被动观察** | 嗅探已有 ACP `session/update` 消息 | 所有引擎 |
| **文件系统** | 通过 watchdog 监听文件变化 | 所有引擎 |

### 9.2 session/event 通知 (onecode 增强)

onecode 实现了一个额外的 ACP 通知 `session/event`，用于精确事件推送：

```
ACP session/event (optional, onecode only):

引擎 → TUI:
{
    "jsonrpc": "2.0",
    "method": "session/event",
    "params": {
        "event": {
            "type": "step.completed",
            "payload": {
                "session_id": "xxx",
                "tool_name": "WriteTool",
                "duration_ms": 120
            }
        }
    }
}
```

TUI 端的处理在 `tui/acp/agent.py` 中作为新的 `@jsonrpc.expose()` 可选实现：

```python
@jsonrpc.expose("session/event")
def rpc_session_event(self, sessionId: str, event: dict, **kwargs) -> None:
    """引擎主动推送事件 (onecode-only 增强)。"""
    self.event_bus.publish(Event(
        type=event["type"],
        source="onecode.acp",
        payload=event["payload"],
    ))
```

**外部引擎不实现这个通知，不影响任何功能。** 外部引擎的功能由被动观察+文件系统保证。

---

## 10. 配置系统

### 10.1 平台配置 (onecode.config.yaml)

```yaml
# ~/.cdh/onecode.config.yaml (onecode 持有)
loops:
  verification:
    enabled: true
    policy: conditional
    gates: [lint, type, test]
  event:
    enabled: false
    sources: [cron, filewatch]
  hillclimb:
    enabled: false
    min_sessions: 10
```

### 10.2 平台级配置 (agent_config.yaml)

```yaml
# ~/.cdh/agent_config.yaml (L4 变异输出)
version: 1
platform:
  verification:
    policy: conditional
    gates: [lint, test]
engine:
  onecode.dev:
    temperature: 0.8
    max_iterations: 15
```

### 10.3 Python 配置类

```python
# onecode/config.py
@dataclass
class VerificationConfig:
    enabled: bool = True
    policy: str = "conditional"
    gates: list[str] = field(default_factory=lambda: ["lint", "type", "test"])

@dataclass
class EventLoopConfig:
    enabled: bool = False
    sources: list[str] = field(default_factory=lambda: ["cron", "filewatch"])

@dataclass
class HillclimbConfig:
    enabled: bool = False
    min_sessions: int = 10

@dataclass
class LoopConfig:
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    event: EventLoopConfig = field(default_factory=EventLoopConfig)
    hillclimb: HillclimbConfig = field(default_factory=HillclimbConfig)

@dataclass
class GlobalConfig:
    ...
    loops: LoopConfig = field(default_factory=LoopConfig)
```

---

## 11. Cross-engine 数据流

### 11.1 主数据流

```
                    ┌─────────────────┐
                    │   用户输入       │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │      ACP stdin/stdout       │
              │  (所有引擎通过相同协议)       │
              └──────────────┬──────────────┘
                         │
              ┌──────────▼──────────┐
              │  L1: Agent Loop (ReAct) │
              │  引擎内部执行 task     │
              └──────────┬──────────┘
                         │
          ┌─────────────┼─────────────┐
          │             │              │
          ▼             ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ onecode  │  │ opencode │  │ claude   │
    │ 直接     │  │ ACP 嗅探  │  │ ACP 嗅探  │
    │ EventBus │  │ event_tap│  │ event_tap│
    └────┬─────┘  └────┬─────┘  └────┬─────┘
          │             │              │
          └─────────────┼──────────────┘
                         │
                         ▼
                    ┌──────────┐
                    │ EventBus │
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ L2:      │  │ L3:      │  │ L4:      │
    │ Verify   │  │ Event    │  │ Hill-    │
    │ (file)   │  │ Sched    │  │ climb    │
    └──────────┘  └──────────┘  └──────────┘
```

### 11.2 事件流 (EventBus)

```
发布者                              事件类型                         订阅者
────────                             ──────                         ──────
所有引擎 (文件变化)          ──►   file.changed                 ──►   PlatformVerificationLoop
onecode (直接)                      TOOL_EXECUTED                ──►   HillclimbLoop
ACP Event Tap (被动嗅探)            TOOL_EXECUTED                ──►   HillclimbLoop
PlatformVerificationLoop            verification.passed/failed   ──►   HillclimbLoop
cdh.scheduler              ──►   cron.tick                     ──►   EventRunner → 引擎启动
cdh.optimizer              ──►   config.changed                ──►   (预留)
```

### 11.3 数据依赖

```
L4 Hillclimb 依赖 (平台级，所有引擎):
  ├── TOOL_EXECUTED 事件计数 → tool_efficiency
  ├── verification.passed/failed 统计 → test_pass_rate
  └── SESSION_ENDED 事件 → 触发计算

L4 Hillclimb 依赖 (onecode 增强):
  ├── TurnRecord → 细粒度 tool_efficiency
  └── onecode.log 内存指标 → 精确 task_completion_pct
```

---

## 12. 引擎兼容性矩阵

### 12.1 功能矩阵

| 能力 | onecode (内联) | onecode (ACP) | opencode | claude | cursor |
|------|--------------|------------|---------|--------|---------|
| **L1 Agent Loop** | ✅ 原生 ReAct | ✅ 原生 ReAct | ✅ 原生 | ✅ 原生 | ✅ 原生 |
| **L2 文件触发验证** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **L2 step 级内联验证** | ✅ | — | ❌ | ❌ | ❌ |
| **L3 EventBus 直接** | ✅ | — | ❌ | ❌ | ❌ |
| **L3 ACP 被动嗅探** | — | ✅ | ✅ | ✅ | ✅ |
| **L3 定时调度** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **L4 平台指标** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **L4 细粒度指标** | ✅ | — | ❌ | ❌ | ❌ |
| **session/event 通知** | ✅ | — | ❌ | ❌ | ❌ |

### 12.2 行为矩阵

| 行为 | onecode | opencode/claude/cursor |
|------|---------|------------------------|
| L2 何时触发 | 文件变化 + 每次 WriteTool 后 | 仅文件变化 |
| L2 延迟 | ~100ms (内联) + ~1s (文件) | ~1s (文件) |
| L3 事件精度 | 精确 tool 名称 + 错误状态 | 仅 tool_call 计数 |
| L4 奖励信号 | `test_pass * 0.4 + task_complete * 0.3 + tool_eff * 0.2 + user_fb * 0.1` | `test_pass * 0.5 + tool_eff * 0.3` |
| 配置输出 | `agent_config.yaml` + `onecode.config.yaml` | 仅 `agent_config.yaml` |

---

## 13. 实现路线图

### 13.1 阶段划分

| 阶段 | 内容 | 涉及模块 |
|------|------|---------|
| **P0** | TurnRecord + LoopConfig | `onecode/agent/turn_record.py` + `onecode/config.py` |
| **P1** | Onecode Verification Loop | `onecode/verification/` |
| **P2** | Platform Verification Loop | `cdh/verification/` |
| **P3** | EventBus + Scheduler | `cdh/event_loop/` |
| **P4** | ACP Event Tap | `tui/acp/event_tap.py` + `tui/acp/agent.py` 集成 |
| **P5** | Hillclimb Loop (平台指标 + agent_config.yaml) | `cdh/optimizer/` |
| **P6** | onecode engine.py 集成 | `onecode/agent/engine.py` |
| **P7** | session/event ACP 扩展 (onecode 增强) | `onecode/agent/onecode_agent_acp.py` + `tui/acp/agent.py` |

### 13.2 不变的文件

- `onecode/agent/agents/types.py` — agent 类型定义
- `onecode/agent/context.py` — 上下文管理
- `onecode/agent/session.py` — session CRUD
- `onecode/agent/tools/cron_tools.py` — 引擎内 CronScheduler 保留兼容
- `onecode/models/` — provider 模型
- `onecode/memory/` — 记忆系统
- `onecode/trace/tracer.py` — 追踪不变
- `onecode/storage/session.py` — 引擎内 session 存储不变
- `cdh/cdh_session_aggregator.py` — 平台 session 索引不变
- `cdh/cli.py` — CLI 不变