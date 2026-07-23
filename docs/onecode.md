# onecode — Core Agent Framework

> 版本: 1.0.6
> 定位: Cloud Dev Harness (CDH) 的 AI Agent 引擎

---

## 目录

1. [概述](#1-概述)
2. [架构总览](#2-架构总览)
3. [Agent 引擎](#3-agent-引擎)
4. [工具系统](#4-工具系统)
5. [LLM Provider 抽象](#5-llm-provider-抽象)
6. [MCP 集成](#6-mcp-集成)
7. [技能系统](#7-技能系统)
8. [代码库索引](#8-代码库索引)
9. [记忆系统](#9-记忆系统)
10. [验证循环](#10-验证循环)
11. [配置系统](#11-配置系统)
12. [CLI](#12-cli)
13. [任务管理](#13-任务管理)
14. [Trace / 可观测性](#14-trace--可观测性)
15. [四层 Loop 集成](#15-四层-loop-集成)

---

## 1. 概述

`onecode` 是 CDH (Cloud Dev Harness) 的核心 AI Agent 引擎，提供：

- **多模态 Agent**：`build`（全工具）、`plan`（只读规划）、`solo`（先规划后执行），含 9 种内置类型
- **三层权限系统**：Agent 类型级、全局安全规则级、工具执行级
- **上下文管理**：三级压缩管线 + 标记式 System 消息管理
- **生命周期钩子**：6 个钩子事件，支持阻断/修改工具行为
- **Subagent 策略**：深度限制、能力隔离、结构化输出契约
- **多 Provider 支持**：7+ LLM 厂商统一接口（Anthropic, OpenAI, DeepSeek, MiniMax, GLM, Ollama 等）
- **23+ 内置工具**：文件操作、搜索、Shell、Web、Git、MCP、Subagent 等
- **MCP 客户端**：SSE / stdio 双传输模式
- **技能系统**：Markdown 驱动的领域知识注入
- **代码库索引**：BM25 检索增强生成 (RAG)
- **多层次记忆**：金字塔 / 召回 / 符号记忆
- **验证循环**：双通道验证（内联 + 平台），Plan Gate 模式
- **安全模型**：凭据保护、路径逃逸防护、XML 注入防护

- **分布式追踪**：JSON 文件导出 / OTLP

```
项目关系:
  cdh/        → 用户交互层 (CLI + TUI)
  onecode/    → 核心引擎层 (Agent 框架)
  tui/        → 终端 UI 层 (Textual)
```

---

## 2. 架构总览

```
onecode/
├── __init__.py          # 版本号
├── __main__.py          # python -m onecode 入口
├── cli.py               # Click CLI (973 行)
├── commands.py          # TUI 斜杠命令
├── config.py            # 配置管理 (GlobalConfig)
├── config_screen.py     # TUI 配置编辑器
├── migrate.py           # ~/.cdh/ → ~/.onecode/ 迁移
│
├── agent/               # Agent 引擎 (核心)
│   ├── engine.py        # 主循环 (ReAct, 2914 行)
│   ├── context.py       # 上下文管理
│   ├── session.py       # Session 管理
│   ├── permissions.py   # 权限系统
│   ├── hooks.py         # 生命周期钩子
│   ├── event_bridge.py  # 事件桥接
│   ├── turn_record.py   # Turn 记录
│   ├── snapshot.py      # 状态快照
│   ├── onecode_agent_acp.py  # ACP Server
│   ├── agents/          # Agent 类型定义
│   └── tools/           # 工具实现 (23+)
│
├── models/              # LLM Provider 抽象
│   ├── provider.py      # 抽象基类
│   ├── registry.py      # Provider 注册表
│   └── providers/       # 7+ 厂商实现
│
├── mcp/                 # MCP 客户端
│   ├── client.py        # SSE + stdio 传输
│   └── manager.py       # Server 生命周期
│
├── skills/              # 技能系统
│   ├── model.py         # 数据模型
│   ├── loader.py        # 加载器 (多层路径发现)
│   ├── manager.py       # 管理 (安装/卸载)
│   ├── create.py        # 脚手架
│   └── frontmatter.py   # YAML frontmatter 解析
│
├── builtin_skills/      # 内置技能
│   ├── git/             # Git 工作流
│   ├── shell/           # Shell 命令
│   ├── agent-browser/   # 浏览器自动化
│   └── skill-creator/   # 技能创建器
│
├── codebase/            # 代码库索引
│   ├── indexer.py       # 文件爬取 + 索引
│   ├── chunker.py       # 分块策略
│   ├── retriever.py     # BM25 检索
│   └── storage.py       # SQLite 存储
│
├── memory/              # 记忆系统
│   ├── pyramid.py       # 金字塔记忆 (4 层)
│   ├── recall.py        # 关键词召回
│   ├── backend.py       # SQLite 持久化
│
├── verification/        # 验证循环
│   ├── loop.py          # 编排器
│   ├── policy.py        # 策略定义
│   ├── aggregation.py   # 结果聚合
│   └── gates/           # 门禁实现
│       ├── lint_gate.py
│       ├── type_gate.py
│       └── test_gate.py
│
│
├── tasks/               # 任务管理
│   ├── models.py        # 数据模型
│   └── manager.py       # 生命周期 + 依赖
│
├── trace/               # 可观测性
│   └── tracer.py        # 分布式追踪
│
├── server/              # HTTP/SSE Server
│   └── app.py           # FastAPI 式 Web 服务
│
├── storage/             # 持久化
│   ├── session.py       # Session 存储
│   ├── project.py       # 项目存储
│   └── activity.py      # 活动日志
│
├── cron/                # 定时调度
├── lsp/                 # LSP 集成 (工具层在 agent/tools/)
└── utils/               # 工具函数
```

---

## 3. Agent 引擎

### 3.1 主循环 (`agent/engine.py`)

核心 ReAct 循环 `chat_stream()`，按 Turn 驱动：

```
用户输入 → 系统提示组装 → LLM 流式调用 → Tool Call → 工具执行
  → 结果回填 → 下一 Turn / 终止
```

每个 Turn 包含：

| 阶段 | 说明 |
|------|------|
| Thought | LLM 推理输出 (流式) |
| Tool Call | LLM 请求调用工具 (名称 + 参数) |
| Tool Execution | 工具实际执行 (沙箱隔离) |
| Observation | 工具结果回填到上下文 |

### 3.2 Agent 模式

| 模式 | 用途 | 权限特征 |
|------|------|---------|
| `build` | 全工具开发 | 编辑/Shell 需审批，只读允许 |
| `plan` | 安全规划/分析 | 所有执行工具 DENY，纯只读 |
| `solo` | 独立任务 | 先计划后执行，与 build 同权限 |

### 3.3 Agent 类型矩阵

#### 主 Agent（用户可见）

| Agent | 模式 | Temperature | MaxTurns | Edit | Bash | Read | WebSearch | 用途 |
|-------|------|-------------|----------|------|------|------|-----------|------|
| **build** | PRIMARY | 0.3 | 10 | ASK | ASK | ALLOW | ALLOW | 全功能开发 |
| **plan** | PRIMARY | 0.2 | 20 | DENY | DENY | ALLOW | ALLOW | 只读规划分析 |
| **solo** | PRIMARY | 0.3 | 10 | ASK | ASK | ALLOW | ALLOW | 先规划后执行 |
| **compaction** | PRIMARY | 0.1 | 0 | DENY | DENY | ALLOW | DENY | 上下文压缩（隐藏） |
| **title** | PRIMARY | 0.1 | 1 | DENY | DENY | ALLOW | DENY | 对话标题生成（隐藏） |
| **summary** | PRIMARY | 0.1 | 2 | DENY | DENY | ALLOW | DENY | 对话总结（隐藏） |

#### Subagent（子 Agent，不可见）

| Agent | 模式 | Edit | Bash | Todo | AskUser | 用途 |
|-------|------|------|------|------|---------|------|
| **general** | SUBAGENT | ALLOW | ALLOW | DENY | DENY | 通用复杂任务 |
| **explore** | SUBAGENT | DENY | DENY | DENY | DENY | 代码库快速搜索 |
| **scout** | SUBAGENT | DENY | DENY | DENY | DENY | 外部依赖调研 |

### 3.4 Subagent 策略

#### 层级限制

```
主 Agent (build/plan/solo)
  └── Subagent (general/explore/scout) [max_depth=1]
        └── ❌ 不能继续 spawn
```

#### 能力限制

| 能力 | general | explore | scout |
|------|---------|---------|-------|
| Spawn | ❌ | ❌ | ❌ |
| AskUser | ❌ | ❌ | ❌ |
| Todo* | ❌ | ❌ | ❌ |
| Agent 工具 | ❌ | ❌ | ❌ |
| 代码库检索 | ❌ | ❌ | ❌ |
| 记忆召回 | ❌ | ❌ | ❌ |
| Batched tool calls | ❌ | ❌ | ❌ |
| Edit / Bash | ✅ | ❌ | ❌ |

#### 结构化输出

Subagent 必须返回结构化报告：

```
SUMMARY:    任务总结
CHANGES:    代码变更摘要
EVIDENCE:   证据/引用
RISKS:      风险
BLOCKERS:   阻塞项
```

### 3.5 权限系统

#### 三层模型

| 层 | 模块 | 范围 | 检查内容 |
|---|------|------|---------|
| L1 | `agents/types.py` | Agent 类型 | 工具类别级 allowlist/denylist |
| L2 | `permissions.py` | 全局安全 | 路径模式 + 命令模式 |
| L3 | `tools/permissions.py` | 工具执行 | 工作区根 + 额外目录 |

#### L1: Agent 类型权限

`AgentConfig.get_tools_config()` 定义 16 个工具类别的权限：

```python
@dataclass
class AgentConfig:
    permission_edit: AgentPermission = ALLOW
    permission_bash: AgentPermission = ALLOW
    permission_read: AgentPermission = ALLOW
    permission_webfetch: AgentPermission = ALLOW
    permission_websearch: AgentPermission = DENY
    permission_task: AgentPermission = ALLOW
    # ... 共 16 个
```

- `tool_allowed(tool_name)` — 检查工具是否在 allowlist/denylist
- `get_bash_permission(command)` — 支持 fnmatch shell 命令模式匹配
- `DENY` 不可被用户覆盖

#### L2: 全局安全规则

`PermissionChecker` / `PermissionSet`:

```python
@dataclass
class PathRule:
    pattern: str          # fnmatch 模式
    permission: AgentPermission
    match_on: str = "path"  # path / filename / stem

@dataclass
class CommandRule:
    pattern: str          # fnmatch 匹配规范化命令
    permission: AgentPermission
```

`create_safe_permission_set()` 内置规则：

| 规则 | 权限 | 示例 |
|------|------|------|
| 敏感文件 | DENY | `.env`, `secrets/**`, `credentials/**` |
| 破坏性命令 | DENY | `rm -rf /`, `dd if=*`, `mkfs.*` |
| fork 炸弹 | DENY | `:(){ :\|:& };:` |
| 提权命令 | ASK | `sudo *`, `chmod 777 *` |
| 网络下载 | ASK | `curl *`, `wget *` |

#### L3: 工具执行权限

`ToolPermissionContext`:

```python
@dataclass
class ToolPermissionContext:
    workspace_root: Path
    additional_working_directories: list[Path]
    deny_names: list[str]
    deny_prefixes: list[str]
```

- `ensure_path_allowed(path)` — 阻止工作区外的文件访问
- `blocks_tool(tool_name)` — 检查工具名是否在拒绝列表

#### 用户覆盖机制

`PermissionStore`（`permissions_store.py`）:

| 方法 | 说明 |
|------|------|
| `set_override(perm_key, permission)` | 用户选择"始终允许/拒绝" |
| `apply_to(agent)` | 切换到 Agent 时重新应用 |
| `snapshot()` | 当前覆盖快照 |

关键约束：Agent 类型的 `DENY` 永不覆盖 — 切换到 plan 模式后 edit 仍然是 DENY。

#### 运行时检查流程

```python
# engine.py: _check_tool_permission()
1. 检查 Agent allowlist/denylist (L1)
2. 映射工具名 → 权限键 (_TOOL_NAME_TO_PERM_KEY)
3. 检查用户覆盖 (PermissionStore)
4. 未知工具 → 检查 tool spec 的 is_read_only
5. 返回 {allowed, requires_approval, error_message}
```

Plan 模式额外执行 `_check_plan_gate()` — 执行工具被调用时，从温和提醒升级到严重警告，3 次后阻断。

### 3.6 生命周期钩子

#### 6 个钩子事件

| 事件 | 触发时机 | 返回值作用 |
|------|---------|-----------|
| `PRE_TOOL_USE` | 工具执行前 | 可阻断或修改参数 |
| `POST_TOOL_USE` | 工具执行后 | 可替换结果 |
| `PRE_MODEL_CALL` | LLM 调用前 | 可修改请求 |
| `POST_MODEL_CALL` | LLM 调用后 | 可修改响应 |
| `PRE_AGENT_START` | Turn 开始 | — |
| `POST_AGENT_END` | Turn 结束 | — |

#### HookManager API

```python
manager = HookManager()
manager.register_pre_tool(my_hook)     # PreToolHook
manager.register_post_tool(my_hook)    # PostToolHook
manager.register(PRE_TOOL_USE, handler)
manager.unregister(PRE_TOOL_USE, handler)
manager.clear()
```

- `run_pre_tool(ctx)` — 依次执行，任一返回 `allowed=False` 则阻断
- `run_post_tool(ctx, result)` — 可替换 `result.data`
- 错误隔离：单个 Hook 异常不影响其他 Hook

#### HookContext

```python
@dataclass
class HookContext:
    agent_name: str
    tool_name: str
    args: dict
    session_id: str
    iteration: int
```

### 3.7 上下文管理策略

#### ContextManager

```python
@dataclass
class ContextConfig:
    max_tokens: int = 100000
    max_messages: int = 1000
    compact_threshold: float = 0.50   # 50% 水位触发压缩
    model: str = "gpt-4"
```

#### 消息存储与 Token 核算

- `add_system()` / `add_user()` / `add_assistant()` / `add_tool_use()` / `add_tool_result()`
- 增量 Token 计数（`tiktoken`，回退为 `len/4` 启发式）
- `set_model()` 同步 `max_tokens` 从 `ModelRegistry`

#### 三级压缩管线

达到 `token_count >= max_tokens * 0.5` 时触发：

```
Level 1 (Light):
  压缩冗长的工具结果（>2000 chars → 500 + truncation marker）

Level 2 (Medium):
  截断旧的非 system 消息（保留最近 10 条）
  旧消息内容 >200 chars → 截断
  移除旧消息中的非 tool_use 块

Level 3 (Heavy):
  全量摘要：取最后 30 条消息
  构建角色前缀内容块
  对最后 20 个 part 生成 LLM 摘要
```

#### 标记式 System 消息管理

使用 HTML 注释标记进行精确替换/移除：

| 标记 | 用途 |
|------|------|
| `<!-- AGENT_CONFIG -->` | Agent 角色和权限 |
| `<!-- TOOL_DESCRIPTIONS -->` | 工具文档 |
| `<!-- REACT_PHASE -->` | CoT 阶段引导 |
| `<!-- CODEBASE -->` | 代码库检索结果 |
| `<!-- MEMORY -->` | 长期记忆召回 |
| `<!-- SKILL:name -->` | 技能内容 |
| `<!-- PROJECT_DOC -->` | AGENTS.md 项目章程 |
| `<!-- CDH_PROJECT -->` | .cdh/ 项目状态 |
| `<!-- PENDING_TODOS -->` | 待办 TODO 提示 |
| `<!-- ROUTING_REMINDER -->` | 路由决策提示 |
| `<!-- PLAN_REMINDER -->` | 计划创建提示 |
| `<!-- PLAN_MODE_DENIED -->` | 模式违规升级警告 |
| `<!-- FORCE_CONTINUE -->` | 继续执行提示 |
| `<!-- loaded_todos_resume -->` | 恢复会话的 TODO |

### 3.8 Turn 记录与快照

#### TurnRecord

```python
@dataclass
class TurnRecord:
    turn_number: int
    thought: str
    tool_name: str
    tool_input: dict | None
    tool_output: Any
    tool_error: str | None
    duration_ms: int
    verification_results: list[dict]

    @property
    def success(self) -> bool:
        return not self.tool_error and not self.verification_failures
```

- 每个触发验证的工具调用创建一个 TurnRecord
- `add_verification(result)` 累积验证结果
- `success` 属性驱动后续决策

#### 快照系统

`SnapshotManager` 管理工作区快照：

| 方法 | 说明 |
|------|------|
| `create(name, description)` | 创建 tar.gz 压缩快照 |
| `restore(snapshot_id)` | 恢复快照 |
| `list()` | 列出所有快照 |
| `delete(snapshot_id)` | 删除快照 |

默认排除：`.git`, `node_modules`, `__pycache__`, `*.pyc`, `.venv`, `.cdh`, `snapshots/`

存储位置：`~/.onecode/snapshots/<uuid>/`

### 3.9 安全模型

#### 凭据处理

- API Key 通过 `${ENV_VAR}` 环境变量引用，不硬编码
- Config Tool 明确不暴露密钥
- `.env`, `secrets/**`, `credentials/**` 自动拒绝

#### 路径逃逸防护

```python
def ensure_path_allowed(self, path: str) -> bool:
    resolved = Path(path).resolve()
    allowed = [self.workspace_root] + self.additional_working_directories
    return any(str(resolved).startswith(str(a.resolve())) for a in allowed)
```

#### Plan 模式安全

- 执行工具硬拒绝
- 违规从温和提醒升级到严重警告（3 次后阻断）

#### Subagent 隔离

- 不能产生孙子 Agent（max_depth = 1）
- 不能与用户交互（AskUser 禁用）
- 不能管理共享 TODO 计划
- 代码库引擎从父 Agent 继承（只读共享实例）
- 跳过代码库自动检索 + 记忆召回（`_disable_retrieval = True`）

#### XML 注入防护

Tool call 解析只转义 5 个 XML 预定义实体：`&lt;` `&gt;` `&quot;` `&apos;` `&amp;`。

#### 文件扩展名限制

`AttachmentsConfig.allowed_extensions` 限制上传类型（默认：`.txt .md .py .json .yaml .sql`）。

### 3.10 运行时策略

- `max_turns` 动态扩展：当有待办 TODO 剩余时，max_turns +5
- 绝对上限：`agent.max_iterations`（默认 100）
- 空转保护：连续 3 个空 Turn（无 tool call）自动终止
- 重试策略：瞬态 Provider 错误最多重试 3 次（指数退避：1s/2s/4s）
- 上下文长度超限：强制压缩并重试 Turn

### 3.11 事件桥接

#### EventBridge

连接 onecode 引擎到 cdh 平台的 EventBus：

```python
class EventBridge:
    def on_tool_event(self, event: ToolEvent)
    def on_session_ended(self)
    def on_verification_passed(self)
    def on_verification_failed(self, result)
```

- 可选集成：仅在 `cdh` 包可用时加载
- 每个事件携带 `session_id`, `tool_name` 等上下文

#### 发布的事件类型

| 事件 | 载荷 | 消费者 |
|------|------|--------|
| `TOOL_EXECUTED` | session_id, tool_name | HillclimbLoop |
| `TOOL_FAILED` | session_id, tool_name, error | HillclimbLoop |
| `SESSION_ENDED` | session_id, turn_count, metrics | HillclimbLoop |
| `VERIFICATION_PASSED` | session_id | HillclimbLoop |
| `VERIFICATION_FAILED` | session_id, failed_gates | HillclimbLoop |

### 3.12 ACP Server (`agent/onecode_agent_acp.py`)

实现 Agent Communication Protocol，通过 stdin/stdout JSON-RPC 通信：

```
方法                             用途
───                              ───
session/create                   创建 Agent Session
session/update                   更新 Session (tool_call, ask_user 等)
session/event (onecode 扩展)     主动事件推送
session/submit                   用户输入提交
session/close                    关闭 Session
```

---

## 4. 工具系统

### 4.1 工具列表

| 工具 | 文件 | 说明 |
|------|------|------|
| `read` | `file_tools.py` | 读文件 |
| `write` | `file_tools.py` | 写文件 |
| `edit` | `file_tools.py` | 精确字符串替换 |
| `insert` | `file_tools.py` | 行级插入 |
| `undo_edit` | `file_tools.py` | 撤销编辑 |
| `apply_patch` | `apply_patch_tool.py` | 应用补丁 |
| `bash` | `bash_tool.py` | Shell 执行 (沙箱隔离) |
| `glob` | `file_tools.py` | 文件通配匹配 |
| `grep` | `file_tools.py` | 内容搜索 |
| `list` | `file_tools.py` | 目录列表 |
| `webfetch` | `web_tools.py` | 网页抓取 |
| `websearch` | `web_tools.py` | 网络搜索 |
| `spawn` | `agent_tools.py` | 启动 Subagent |
| `agent` | `agent_tools.py` | 启动指定类型 Agent |
| `skill` | `skill_tools.py` | 加载技能 |
| `mcp_tool` | `mcp_tools.py` | 调用 MCP 工具 |
| `mcp_resources` | `mcp_tools.py` | 读取 MCP 资源 |
| `config_read` | `config_tool.py` | 读配置 |
| `config_write` | `config_tool.py` | 写配置 |
| `todo_create/get/list/update/output/stop` | `todo_tools.py` | 任务管理 |
| `cron_create/list/remove` | `cron_tools.py` | 定时任务 |
| `git` | `git_tools.py` | Git 操作 |
| `lsp_*` | `lsp_tools.py` | LSP 代码智能 |
| `send_message` | `communication_tools.py` | 发送消息 |
| `ask_user` | `communication_tools.py` | 询问用户 |

### 4.2 沙箱隔离

Shell 执行通过 `SandboxRunner` 提供 4 种隔离模式：

| 模式 | 机制 | 适用平台 |
|------|------|---------|
| `none` | Python `resource` 模块限制 (CPU/内存/进程/FD) | 所有 |
| `bwrap` | Bubblewrap 命名空间隔离 | Linux |
| `docker` | Docker 容器隔离 | 所有 |
| `auto` | 自动选择最佳方案 | 所有 |

### 4.3 工具注册

- `ToolRegistry` — 全局工具注册表
- 工具可被 `disabled_tools` 配置禁用
- 模式感知：`plan` 模式自动限制破坏性工具

---

## 5. LLM Provider 抽象

### 5.1 统一接口

```python
class Provider(ABC):
    async def chat_stream(self, messages, **kwargs) -> AsyncGenerator[StreamEvent, None]
    async def chat(self, messages, **kwargs) -> Message
```

### 5.2 支持的 Provider

| Provider | 默认 Endpoint | 默认模型 |
|----------|--------------|---------|
| Anthropic | `api.anthropic.com/v1` | `claude-opus-4.7` |
| OpenAI | `api.openai.com/v1` | `gpt-5.5-pro` |
| DeepSeek | `api.deepseek.com/v1` | `deepseek-v4-free` |
| MiniMaxi | `api.minimaxi.com/v1` | `MiniMax-M2.7` |
| MiniMax | `api.minimax.com/v1` | `MiniMax-M2.7` |
| GLM | `open.bigmodel.cn/api/paas/v4` | `glm-5.1` |
| Ollama | `localhost:11434` | `llama2` |

### 5.3 自动模型选择

按任务复杂度自动选择模型（详见 §11.5 配置系统）：

| 复杂度 | Agent 类型 | 模型配置键 |
|--------|-----------|-----------|
| 高 | build, solo | `model_auto.complex_tasks` |
| 中 | general | `model_auto.medium_tasks` |
| 低 | explore, scout, compaction, title, summary | `model_auto.simple_tasks` |

---

## 6. MCP 集成

### 6.1 客户端 (`mcp/client.py`)

| 传输 | 说明 | 配置字段 |
|------|------|---------|
| SSE | Server-Sent Events | `url` |
| stdio | 子进程 stdin/stdout | `command`, `args` |
| streamable-http | HTTP 流式 | `url` |

### 6.2 功能

- 工具调用：`mcp_tool(name, arguments)`
- 资源读取：`mcp_resources(uri)`
- 按 Server 分组管理
- 可启用 / 禁用 / 配置环境变量

---

## 7. 技能系统

### 7.1 加载路径 (分层发现)

按优先级从高到低：

1. `~/.onecode/skills/<name>/SKILL.md` — 用户技能（最高优先级）
2. `.agents/skills/<name>/SKILL.md` — Agent 协议标准
3. `onecode/builtin_skills/` — 内置技能（最低优先级 fallback）

同名技能以优先级高的为准。

### 7.2 SKILL.md 格式

```markdown
---
name: skill-name
description: 简短描述
tags: [tag1, tag2]
---

# Skill Name

详细指令、工作流、规则 ...
```

### 7.3 管理命令

```bash
onecode skill list              # 列出所有技能
onecode skill add <path|url>    # 安装技能
onecode skill remove <name>     # 卸载
onecode skill enable <name>     # 启用
onecode skill disable <name>    # 禁用
onecode skill search <keyword>  # 搜索
```

---

## 8. 代码库索引

### 8.1 索引流程

```
文件爬取 → 分块 (50行/10行重叠) → BM25 索引 → SQLite 存储
```

### 8.2 检索

- BM25 算法，对查询与分块评分
- 默认返回 Top-5 分块
- 支持文件扩展名过滤 (25+ 类型)
- 排除 `node_modules`, `__pycache__`, `.git`, `.venv`, `dist`, `build` 等

### 8.3 命令

```bash
onecode codebase index     # 索引项目
onecode codebase search    # 搜索索引
```

---

## 9. 记忆系统

### 9.1 金字塔记忆 (`memory/pyramid.py`)

| 层级 | 特性 | 保留策略 |
|------|------|---------|
| 1. Ephemeral | 当前 Turn 上下文 | Turn 结束即清理 |
| 2. Short-term | 当前 Session 关键信息 | Session 级别 |
| 3. Long-term | 跨 Session 模式 | LLM 驱动的摘要 |
| 4. Core | 用户偏好 + 不变知识 | 持久 |

### 9.2 召回记忆 (`memory/recall.py`)

- BM25 关键词匹配
- 从历史消息中检索相关片段
- SQLite 后端持久化

---

## 10. 验证循环

### 10.1 双通道验证

```
Engine Channel (onecode 内联):
  每次 Write/Edit/Insert/ApplyPatch/Bash 后
  → onecode/verification/
    → LintGate / TypeGate / TestGate
    → 零延迟，step 级别

Platform Channel (所有引擎):
  文件变化 (watchdog)
  → cdh/verification/
    → EventBus → PlatformVerificationLoop
    → 秒级延迟
```

### 10.2 策略模式

| 策略 | 行为 |
|------|------|
| `EVERY_STEP` | 每次工具调用后运行所有 Gate |
| `FINAL_ONLY` | 仅 Session 结束时运行 |
| `CONDITIONAL` (默认) | 仅 Write/Edit/Insert/ApplyPatch/Bash 后触发 |

### 10.3 Gate 实现

| Gate | 命令 | 触发工具 | 作用 |
|------|------|---------|------|
| `LintGate` | `ruff check <dir>` | Write, Edit, Insert, ApplyPatch | 代码风格合规 |
| `TypeGate` | `mypy <dir>` | Write, Edit, Insert, ApplyPatch | 类型安全 |
| `TestGate` | `pytest <dir> -x --tb=short` | Bash, ApplyPatch | 测试通过 |

### 10.4 Plan Gate 模式

| 模式 | 行为 |
|------|------|
| `hard` | Plan 模式：无 TODO 时阻断执行工具 |
| `soft` | build/solo 模式：提示但不阻断 |
| `off` | Subagent 或 task=DENY 时不强制 |

执行工具集合：`{Write, Edit, Insert, ApplyPatch, Bash}`

### 10.5 结果聚合

```python
@dataclass
class GateResult:
    name: str
    status: str        # "passed" / "failed" / "skipped"
    exit_code: int
    duration_ms: int
    summary: str
    log_path: str

@dataclass
class AggregateResult:
    gate_results: dict[str, GateResult]
    failed_gates: list[str]
    success: bool
```

### 10.6 AI-DLC 质量门禁（项目级）

- 测试覆盖率 >= 80%
- BDD 场景 100% 通过
- 零安全漏洞
- `src/` 中无 TODO 注释
- 合约向后兼容（默认）
- 多组件变更必须包含跨栈 e2e 测试

### 10.7 Plan 卫生规则

- 每个新工作批次以 `TodoClear` 开始
- 不追加到旧计划
- 每项任务是 `TodoCreate`
- 简单工作 → 直接执行；复杂工作 → `Spawn` Subagent

---

## 11. 配置系统

### 11.1 配置文件

| 文件 | 位置 | 说明 |
|------|------|------|
| 主配置 | `~/.onecode/onecode.config.yaml` | 全局配置 |
| 平台配置 | `~/.cdh/agent_config.yaml` | L4 优化输出 |
| 环境变量 | `${VAR}` 在 YAML 中解析 | 动态配置 |

### 11.2 Agent 配置层次

```
~/.onecode/onecode.config.yaml     # 用户配置（主）
  ↓ 读取
GlobalConfig
  ├── default_mode: "build"
  ├── default_provider: "minimaxi"
  ├── default_model: "MiniMax-M2.7"
  ├── agent:
  │   ├── max_iterations: 100       # 绝对上限
  │   ├── temperature: 0.7
  │   └── timeout_seconds: 600
  ├── loops.verification:
  │   ├── enabled: true
  │   ├── policy: conditional
  │   └── gates: [lint, type, test]
  └── model_auto:
        ├── simple: minimax-2.7
        ├── medium: minimax-2.7
        └── complex: minimax-2.7
          ↓
~/.cdh/agent_config.yaml            # L4 优化输出（可选覆盖）
  engine.onecode.temperature → agent.temperature
  engine.onecode.max_iterations → agent.max_iterations
  platform.verification.policy → loops.verification.policy
```

### 11.3 按 Agent 类型的配置覆盖

| Agent | Temperature | MaxTurns | TopP |
|-------|-------------|----------|------|
| build | 0.3 | 10 | 0.9 |
| plan | 0.2 | 20 | 0.9 |
| solo | 0.3 | 10 | 0.9 |
| compaction | 0.1 | 0 | 0.9 |
| title | 0.1 | 1 | 0.9 |
| summary | 0.1 | 2 | 0.9 |
| general | 0.3 | 25 | 0.9 |
| explore | 0.2 | 15 | 0.9 |
| scout | 0.2 | 15 | 0.9 |

### 11.4 配置结构

```yaml
provider:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-opus-4.7
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-v4-flash

agent:
  mode: build
  max_iterations: 20

loops:
  verification:
    enabled: true
    policy: conditional
    gates: [lint, type, test]
  event:
    enabled: false
  hillclimb:
    enabled: false

codebase:
  index_enabled: true
  max_chunk_size: 50
  chunk_overlap: 10

memory:
  pyramid_enabled: true
  recall_enabled: true

mcp:
  servers:
    my-server:
      transport: sse
      url: http://localhost:3000/mcp

skills:
  enabled: [git, shell]

sandbox:
  mode: auto

observability:
  tracing: json
```

### 11.5 模型自动选择

按 Agent 类型和任务复杂度自动选择：

| 复杂度 | Agent 类型 | 模型选择 |
|--------|-----------|---------|
| 高 | build, solo | complex_tasks |
| 中 | general | medium_tasks |
| 低 | explore, scout, compaction, title, summary | simple_tasks |

### 11.6 `GlobalConfig` 数据类

`onecode/config.py` 中定义，支持：

- 递归 dict → dataclass 反序列化
- 环境变量插值 `resolve_env()`
- 自动迁移旧版配置

---

## 12. CLI

### 12.1 入口

```bash
onecode [OPTIONS] COMMAND [ARGS]...
```

### 12.2 子命令

| 命令 | 说明 |
|------|------|
| `onecode config` | 交互式配置编辑 |
| `onecode codebase` | 代码库索引管理 |
| `onecode skill` | 技能管理 |
| `onecode mcp` | MCP Server 管理 |
| `onecode memory` | 记忆查看/清理 |
| `onecode help` | 帮助 |
| `onecode version` | 版本信息 |

### 12.3 TUI 斜杠命令

在 A2TUI 聊天界面中：

```
/onecode:provider  切换 LLM Provider
/onecode:model     切换模型
/onecode:skill     管理技能
/onecode:mcp       管理 MCP
/onecode:status    查看状态
```

### 12.4 ACP Server

```bash
onecode-agent-acp
```

通过 stdin/stdout JSON-RPC 提供 ACP 服务。

---

## 13. 任务管理

### 13.1 模型

```python
@dataclass
class Task:
    id: str
    name: str
    description: str
    status: TaskStatus  # pending / active / completed / failed / blocked
    depends_on: list[str]  # 依赖任务 ID
```

### 13.2 功能

- 任务状态追踪
- 依赖关系管理 (DAG)
- 与 TODO 工具集成
- 定时调度 (cron)

---

## 14. Trace / 可观测性

### 14.1 导出格式

| 格式 | 配置 | 说明 |
|------|------|------|
| JSON 文件 | `tracing: json` | 写入 `~/.onecode/traces/` |
| OTLP | `tracing: otlp` | OpenTelemetry 协议 |

### 14.2 Span 结构

每个 Agent Turn 生成一个 Span：

```
- session_span
  ├─ turn_1_span
  │   ├─ llm_call_span
  │   └─ tool_exec_span
  ├─ turn_2_span
  └─ ...
```

---

## 15. 四层 Loop 集成

`onecode` 是 CDH 四层 Loop 架构的 L1 (Agent Loop)，并提供增强通道：

| 层 | 名称 | onecode 角色 |
|----|------|-------------|
| L1 | Agent Loop | **核心**: `engine.py` 的 `chat_stream()` |
| L2 | Verification Loop | **增强通道**: step 级内联 Hook (其他引擎仅文件级) |
| L3 | Event Loop | **增强通道**: 直接 `EventBus.publish()` (其他引擎被动嗅探) |
| L4 | Hill-climb Loop | **增强通道**: `TurnRecord` 提供细粒度指标 (其他引擎平台级) |

详见 `docs/loop.md`。

---

## 附录: 关键文件索引

| 文件 | 职责 |
|------|------|
| `onecode/agent/engine.py` | ReAct 主循环 (~2914 行) |
| `onecode/agent/context.py` | 上下文管理 |
| `onecode/agent/permissions.py` | 权限系统 |
| `onecode/agent/hooks.py` | 生命周期钩子 |
| `onecode/agent/turn_record.py` | Turn 记录 |
| `onecode/agent/onecode_agent_acp.py` | ACP Server |
| `onecode/config.py` | 全局配置 |
| `onecode/cli.py` | CLI 定义 |
| `onecode/commands.py` | TUI 命令 |
| `onecode/models/provider.py` | Provider 抽象基类 |
| `onecode/skills/loader.py` | 技能加载器 |
| `onecode/skills/manager.py` | 技能管理器 |
| `onecode/mcp/client.py` | MCP 客户端 |
| `onecode/codebase/indexer.py` | 代码索引 |
| `onecode/codebase/retriever.py` | BM25 检索 |
| `onecode/memory/pyramid.py` | 金字塔记忆 |
| `onecode/verification/loop.py` | 验证循环 |
| `onecode/trace/tracer.py` | 分布式追踪 |
