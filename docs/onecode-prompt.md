# Onecode Engine — System Prompt 架构

## 概述

onecode 引擎的 system prompt 不是单一文件，而是在运行时由多个 Marker Section
动态组装而成。每个 section 通过 `<!-- MARKER_NAME -->` 格式的 HTML 注释标识，
由 `ContextManager` 进行插入、替换或移除。

## 组装流水线

```
Engine 启动
  │
  ├─ set_agent(agent_type)
  │   ├─ <!-- AGENT_CONFIG -->       ← 编译: 描述 + 约束 + Plan Gate + 响应风格 (含 ReAct)
  │   └─ <!-- TOOL_DESCRIPTIONS -->  ← 编译: 工具列表 (过滤后)
  │
  ├─ _load_skills()
  │   ├─ <!-- SKILL:{name} -->       ← 每个已启用的 skill
  │   ├─ <!-- PROJECT_DOC -->        ← AGENTS.md 内容
  │   └─ <!-- CDH_PROJECT -->        ← .cdh/ 项目状态
  │
  ├─ _inject_project_context()       # 项目名/envId (无 marker)
  │
  └─ chat_stream() 每轮
      ├─ <!-- CODEBASE -->           ← BM25 检索结果
      ├─ <!-- MEMORY -->             ← 长期记忆召回
      ├─ <!-- REACT_PHASE -->        ← 轮次计数 + CoT 导航
      ├─ <!-- PENDING_TODOS -->      ← 动态待办提醒
      ├─ <!-- ROUTING_REMINDER -->   ← Spawn 路由引导
      ├─ <!-- PLAN_REMINDER -->      ← 规划提醒
      ├─ <!-- PLAN_MODE_DENIED -->   ← 计划模式拒绝消息
      └─ <!-- FORCE_CONTINUE -->     ← 未完成任务强制延续
```

## Marker Section 索引

| Marker | 来源文件 | 组装位置 | 可替换 | 用途 |
|--------|---------|---------|--------|------|
| `<!-- AGENT_CONFIG -->` | `types.py` → `engine.py:set_agent()` | `set_agent()` L998 | 是 | Agent 身份、约束、ReAct、Plan Gate、响应风格 |
| `<!-- TOOL_DESCRIPTIONS -->` | `types.py` `TOOL_DESCRIPTIONS` | `set_agent()` L1008 | 是 | 工具列表 (prose 格式); 原生工具 provider 会移除 |
| `<!-- SKILL:{name} -->` | `onecode/skills/loader.py` | `_load_skills()` L1042 | 否 | 已启用 skill 的内容 |
| `<!-- PROJECT_DOC -->` | `onecode/agent/project_doc.py` | `_load_skills()` L1049 | 否 | `AGENTS.md` 内容 |
| `<!-- CDH_PROJECT -->` | `onecode/agent/cdh_loader.py` | `_load_skills()` L1055 | 否 | `.cdh/` 项目状态 |
| `<!-- CODEBASE -->` | `onecode/codebase/` | `chat_stream()` L1325 | 是 | BM25 检索到的代码片段 |
| `<!-- MEMORY -->` | `onecode/memory/` | `chat_stream()` L1346 | 是 | 长期记忆召回结果 |
| `<!-- REACT_PHASE -->` | `engine.py` L1411 | `chat_stream()` L1413 | 是 | 轮次计数 + CoT 导航 |
| `<!-- PENDING_TODOS -->` | `engine.py:_refresh_pending_todos_nudge()` L886 | 每轮 | 是 | 待处理 todo 列表 |
| `<!-- PLAN_MODE_DENIED -->` | `engine.py` L1885 | 工具执行阶段 | 否 | 计划模式违规拒绝 |
| `<!-- PLAN_REMINDER -->` | `engine.py` L2079 | 工具执行阶段 | 否 | 软性规划提醒 |
| `<!-- ROUTING_REMINDER -->` | `engine.py` L2101 | 工具执行阶段 | 否 | Spawn 路由引导 |
| `<!-- FORCE_CONTINUE -->` | `engine.py` L1442 | 主循环 | 否 | 未完成任务强制继续 |
| `<!-- NEW_SESSION_HINT -->` | `onecode_agent_acp.py` L1270 | 会话创建 | 否 | 新空白会话提示 |

## AGENT_CONFIG 详细组成

`set_agent()` 在 `engine.py:910-1000` 构建 `AGENT_CONFIG` marker 块。组装顺序：

| 序号 | 内容 | 来源 | 条件 |
|------|------|------|------|
| 1 | Agent 描述 | `AgentConfig.description` | 总是 |
| 2 | 权限限制 (编辑/Shell) | `should_ask_for_edit()` / `should_ask_for_bash()` | 仅当 ASK 模式 |
| 3 | Subagent 约束 | `SUBAGENT_CONSTRAINTS` | 仅当 `AgentMode.SUBAGENT` |
| 4 | Plan Gate | `PLAN_GATE_HARD` / `PLAN_GATE_SOFT` | 仅当 `permission_task != DENY` |
| 5 | 响应风格指导 | 硬编码字符串 (`engine.py:949-996`) | 总是 (主 agent 和 subagent 不同) |

### Plan Gate 条件

| Agent | Gate |
|-------|------|
| `plan` (主 agent) | `PLAN_GATE_HARD` |
| `build` / `solo` (主 agent) | `PLAN_GATE_SOFT` |
| Subagent | 无 gate |
| 只读模式 | 无 gate |

## Provider 层处理

`Provider.prepare_messages()` (`onecode/models/provider.py:323-567`) 在发送给 LLM API 前处理 system prompt：

### 优先级裁切 (32 KiB cap)

当组合 system prompt 超过 32 KiB 时,按优先级裁切：

| 优先级 | Marker | 行为 |
|--------|--------|------|
| 0 | `AGENT_CONFIG` | 始终保留 |
| 1 | `REACT_PHASE` | 高优先级 |
| 2 | `CDH_PROJECT` | 中优先级 |
| 3 | `SKILL:*` | 最新保留,旧者先丢弃 |
| 9 | 其他 | 最先丢弃 |

### Anthropic 风格 (Anthropic, etc.)

- 将 system 从 `messages` 数组提取
- 作为独立 `system` API 参数传递
- 格式: `{"system": [{"type": "text", "text": "..."}]}`

### OpenAI 风格 (OpenAI, DeepSeek, etc.)

- system 作为 `messages[0]` 传递
- 格式: `{"role": "system", "content": "..."}`

### MiniMaxi 特殊处理

- `supports_native_tools()` 返回 `False`
- `<!-- TOOL_DESCRIPTIONS -->` 不会被移除
- Prose 工具描述与 API 请求一起发送

### 原生工具支持

当 provider 支持原生工具 schema (`supports_native_tools() == True`):
- `_strip_agent_config_tool_descriptions()` (`engine.py:1015`) 移除整个
  `<!-- TOOL_DESCRIPTIONS -->` section
- 结构化 `tools` kwarg 替代 prose 描述

## TOOL_DESCRIPTIONS 过滤

`filter_tool_descriptions()` (`types.py:484-520`) 根据 agent 的
`tools`/`disallowed_tools` 配置过滤工具描述:

- `allowlist` 非空 → 仅显示列表中工具
- `denylist` 非空 → 隐藏列表中工具
- 两者皆空 → 显示完整列表

## Prompt 文件管理

engine-level 的基础 prompt 内容存储在 `onecode/agent/agents/prompts/` 目录下,
作为独立的 `.md` 文件:

| 文件 | 对应变量 | 用途 |
|------|---------|------|
| `tool-descriptions.md` | `TOOL_DESCRIPTIONS` | 所有可用工具的定义和使用说明 |
| `plan-gate-hard.md` | `PLAN_GATE_HARD` | 计划模式硬性 gate |
| `plan-gate-soft.md` | `PLAN_GATE_SOFT` | build/solo 模式软性 gate |
| `subagent-constraints.md` | `SUBAGENT_CONSTRAINTS` | 子 Agent 的能力限制 |
| `compaction-instructions.md` | `COMPACTION_INSTRUCTIONS` | 上下文压缩 Agent 提示 |
| `title-instructions.md` | `TITLE_INSTRUCTIONS` | 会话标题生成提示 |
| `summary-instructions.md` | `SUMMARY_INSTRUCTIONS` | 会话摘要生成提示 |

### 加载机制

`types.py` 中的 `load_prompt(name)` 函数负责读取 prompt 文件。读取失败时,
fallback 到内嵌默认值,确保在任何部署环境下都可用。

### 开发流程

- 编辑 `onecode/agent/agents/prompts/*.md` 中的 prompt 内容
- 无需修改 Python 代码即可迭代 prompt 设计
- 文件内容作为包数据 (`pyproject.toml` `tool.setuptools.package-data`) 打包分发
