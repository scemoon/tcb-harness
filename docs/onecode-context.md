# onecode — Context 管理策略

> 版本: 1.0.0
> 对应引擎: onecode/agent/context.py, engine.py, memory/, codebase/

---

## 目录

1. [概述](#1-概述)
2. [ContextManager 在线上下文](#2-contextmanager-在线上下文)
3. [标记式 System 消息管理](#3-标记式-system-消息管理)
4. [三级压缩管线](#4-三级压缩管线)
5. [System 消息组装与生命周期](#5-system-消息组装与生命周期)
6. [代码库索引 RAG](#6-代码库索引-rag)
7. [长期记忆召回](#7-长期记忆召回)
8. [Provider 层优先级折叠](#8-provider-层优先级折叠)
9. [配置项汇总](#9-配置项汇总)

---

## 1. 概述

onecode 的上下文管理是 **多层、分层** 的系统，核心目标是在有限的上下文窗口内最大化有效信息密度。策略由 5 个协作子系统构成：

| 子系统 | 位置 | 职责 |
|--------|------|------|
| ContextManager | `onecode/agent/context.py` | 在线消息存储、增量 Token 计数、标记式 System 消息管理、三级压缩 |
| System 组装 | `onecode/agent/engine.py` | Agent 运行前/每轮运行时填充 System 消息各段落 |
| Codebase RAG | `onecode/codebase/` | BM25 + Embedding 双路检索，注入代码上下文 |
| Memory Recall | `onecode/memory/` | 金字塔记忆 L0 + BM25 关键词召回 |
| Provider 折叠 | `onecode/models/provider.py` | 发送前按优先级合并 System 消息，超容量时丢弃低优先级段落 |

---

## 2. ContextManager 在线上下文

`ContextManager` 是每一轮对话的在线上下文容器。

### 2.1 消息存储

```python
self.messages: list[Message] = []     # 所有消息
self._token_count = 0                 # 增量 token 计数
```

每个 `Message` 包含 `role`（system/user/assistant/tool）、`content`（str 或 list）、`name`（可选）。

### 2.2 Token 估算

- 优先使用 `tiktoken.encoding_for_model(model)` 获取精确编码
- 未知模型回退到 `cl100k_base`
- 完全失败时使用 `len(text) // 4` 启发式
- 每条消息附加 `STRUCT_OVERHEAD = 20` 结构开销
- Token 计数是**增量的**：`add_message` 时只估算新增消息，避免全量重算

### 2.3 模型自动同步

`set_model(model)` 从 `ModelRegistry` 查找模型的 `context_window`，自动设置 `max_tokens`，确保压缩阈值始终与模型能力匹配。

---

## 3. 标记式 System 消息管理

这是 onecode 上下文管理的**核心设计模式**。System 消息通过 HTML 注释标记（`<!-- MARKER -->`）进行精确插入、替换和删除，无需重建整个 System 消息。

### 3.1 核心方法

```python
def replace_system_section(marker: str, new_content: str) -> bool
    # 在所有 system 消息中查找包含 marker 的消息，替换内容，更新 token 计数

def remove_system_by_marker(marker: str) -> int
    # 移除所有包含指定 marker 的 system 消息，返回移除条数

def add_system(content: str)
    # 追加一条新的 system 消息
```

### 3.2 完整标记清单

| 标记 | 注入时机 | 内容 | 更新策略 |
|------|----------|------|----------|
| `<!-- AGENT_CONFIG -->` | `set_agent()` | Agent 角色描述、权限约束、响应风格指引、Plan Gate | `replace_system_section` |
| `<!-- TOOL_DESCRIPTIONS -->` | `set_agent()` | 工具文档（支持原生 tool schema 的 Provider 会移除此标记） | `replace_system_section` |
| `<!-- REACT_PHASE -->` | 每轮开始 | 当前轮次 CoT 引导：`## Round N — 思考 → Todo → 行动` | `replace_system_section`（轮次递增） |
| `<!-- SKILL:{name} -->` | `_load_skills()` | 技能内容（每个技能一个独立标记） | 全量重加载时 `remove` + `add` |
| `<!-- PROJECT_DOC -->` | `_load_skills()` | AGENTS.md 项目章程 | 全量重加载 |
| `<!-- CDH_PROJECT -->` | `_load_skills()` | `.cdh/` 项目状态 | 全量重加载 |
| `<!-- CODEBASE -->` | 每轮用户输入后 | 代码库检索结果（top-5 chunks） | `replace_system_section` 或 `add` |
| `<!-- MEMORY -->` | 每轮用户输入后 | 长期记忆召回结果 | `replace_system_section` 或 `add` |
| `<!-- PENDING_TODOS -->` | 每轮开始 | 未完成 Todo 列表及强制续写指令 | `replace_system_section`；无待办时 `remove` |
| `<!-- ROUTING_REMINDER -->` | 直接执行工具次数 ≥2 | 任务路由决策引导 | 插入；新轮开始时 `remove` |
| `<!-- PLAN_REMINDER -->` | Plan Gate 软拦截 | 规划与执行分离指引 | 插入；新轮开始时 `remove` |
| `<!-- PLAN_MODE_DENIED -->` | Plan Gate 硬拦截 ≥3 次 | 严重模式违规警告 | 插入；`_reset_react_state` 时 `remove` |
| `<!-- FORCE_CONTINUE -->` | 待办超限延续 | 强制续写指令 | 直接插入 user 消息 |
| `<!-- loaded_todos_resume -->` | 会话恢复 | 已有待办清单 | `replace_system_section` |
| `<!-- NEW_SESSION_HINT -->` | 新会话 | 新会话提示 | 加载待办后 `remove` |

### 3.3 设计优势

- **O(1) 更新**：标记定位直接扫描 `system` 消息列表，不需要解析结构
- **增量替换**：同一标记的内容更新不需要涉及其他标记
- **可组合性**：不同子系统独立管理自己的标记，互不干扰

---

## 4. 三级压缩管线

当 `token_count >= max_tokens * compact_threshold`（默认 50%）时，触发渐进式压缩。

### 4.1 压缩流程

```
should_compact() → true
  │
  ├─ Tier 0: System 消息原地截断
  │   保留 CRITICAL_MARKERS（AGENT_CONFIG、REACT_PHASE）跳过
  │   其他 >8000 字符的 system 消息截断至 4000
  │
  ├─ Tier 1: Light（工具结果压缩）
  │   每个 tool_result 中 >2000 字符的内容截断至 500
  │   如果压缩后低于阈值 → 返回 "light"
  │
  ├─ Tier 2: Medium（旧消息截断）
  │   保留最近 20 条非 system 消息
  │   旧消息中文本 >200 字符截断至 200，列表移除非 tool_use 块
  │   如果压缩后低于阈值 → 返回 "medium"
  │
  └─ Tier 3: Heavy（全量摘要）
      取最后 30 条消息
      构建摘要（每个消息最多 800 字符）
      用 `[Previous context summarized]\n{summary}` 替换全部非 system 消息
      返回 "heavy"
```

### 4.2 Context Length Error 恢复

当 Provider 返回 `ContextLengthError` 时：

1. 先尝试 `compact()`（调用 `should_compact` 后的主动压缩）
2. 如果 `compact == "none"` 且重试 ≥2 次，强制移除 `SKILL`、`PROJECT_DOC`、`CODEBASE`、`MEMORY` 标记
3. 最多重试 3 次，超过则放弃

### 4.3 定期校准

每 3 轮触发一次全量 `_update_token_count()` 校准，修正增量计数的漂移。

---

## 5. System 消息组装与生命周期

### 5.1 初始化阶段

```
set_agent('build'|'plan'|'solo'|...)
  ├─ AGENT_CONFIG（角色 + 权限 + 工作流 + Plan Gate）
  ├─ TOOL_DESCRIPTIONS（工具文档）
  └─ 技能加载（由 _load_skills 触发）
       ├─ SKILL:{name}（每个启用的技能）
       ├─ PROJECT_DOC（AGENTS.md）
       └─ CDH_PROJECT（.cdh/ 项目状态）
```

### 5.2 每轮运行前

```
_pre_turn_context()
  ├─ REMOVE: ROUTING_REMINDER, PLAN_REMINDER
  ├─ PENDING_TODOS（插入或更新）
  ├─ REACT_PHASE（更新为当前轮次）
  ├─ CODEBASE（用户输入触发 BM25 检索）
  ├─ MEMORY（用户输入触发 BM25 召回）
  └─ should_compact() → 三级压缩
```

### 5.3 清理阶段

```
_reset_react_state()
  ├─ REMOVE: PLAN_MODE_DENIED, REACT_PHASE, ROUTING_REMINDER, PENDING_TODOS
  └─ 重置执行计数器

reset()
  ├─ context.reset()（清空全部消息）
  └─ 重置技能加载标记
```

### 5.4 终止判断

```
一轮结束:
  如果无待办 + 无 tool_use → break
  如果有待办 + 无 tool_use → FORCE_CONTINUE 注入，继续
  如果轮次超过 hard_limit:
    无待办 → break
    有待办 → 动态扩展 +5 轮 + FORCE_CONTINUE
  绝对上限 max_iterations → 强制终止
```

---

## 6. 代码库索引 RAG

### 6.1 流程

```
用户输入 → 判断 _should_retrieve_codebase()
  → CodebaseEngine.retrieve(query)
    → ensure_indexed()
      → CodebaseIndexer.index()
        → 扫描项目文件，跳过 exclude_patterns
        → 分块（默认 50 行，10 行重叠）
        → BM25 构建倒排索引
    → CodebaseRetriever.retrieve()
      → bm25 / embedding / hybrid（默认 bm25）
      → top_k=5
  → format_context()
    → 按 max_chunk_tokens（默认 500）预算截断
  → 注入到 System 消息 <-- CODEBASE -->
```

### 6.2 检索策略

| 类型 | 方法 |
|------|------|
| `bm25`（默认） | BM25 Okapi 打分，top-5 |
| `embedding` | 调用 embedding API（OpenAI / Ollama），余弦相似度 |
| `hybrid` | BM25 + Embedding 结果合并去重 |

### 6.3 配置默认值

```python
class CodebaseConfig:
    enabled: bool = True
    auto_retrieve: bool = True
    chunk_strategy: str = "line"
    chunk_lines: int = 50
    chunk_overlap: int = 10
    retriever: str = "bm25"
    top_k: int = 5
    max_chunk_tokens: int = 500
```

---

## 7. 长期记忆召回

### 7.1 架构

```
AgentMemory
  ├── MemoryPyramid（金字塔持久化）
  │     └── L0_CONVERSATION：SQLite + JSON 索引 + .md 文件
  ├── MemoryBackend（SQLite 后端）
  └── HybridRecall（BM25 + 可选 Embedding）
```

### 7.2 召回流程

```
用户输入 → 判断 auto_recall 启用
  → AgentMemory.search_memories(query, top_k=5)
    → HybridRecall.hybrid_recall()
      → BM25 关键词检索 + Embedding 语义检索
      → RRF（倒数排序融合）合并
  → 格式化：## Relevant past memories
  → 注入到 System 消息 <-- MEMORY -->
```

### 7.3 配置默认值

```python
class MemoryConfig:
    enabled: bool = True
    auto_recall: bool = True
    top_k: int = 5
```

---

## 8. Provider 层优先级折叠

在消息发送给 LLM 前，`prepare_messages()` 对 System 消息进行最终处理。

### 8.1 合并规则

所有 system 角色消息按顺序合并为一条，用 `\n\n` 分隔。

### 8.2 容量保护

```python
_SYSTEM_CAP_BYTES = 32_768  # 32 KiB UTF-8 字节
```

当合并后超过 32 KiB 时，按优先级丢弃段落：

| 优先级 | 标记 | 行为 |
|--------|------|------|
| 0（最高） | `AGENT_CONFIG` | **永不丢弃** |
| 1 | `REACT_PHASE` | 尽力保留 |
| 2 | `CDH_PROJECT` | 按容量保留 |
| 3 | `SKILL` | 按容量保留 |
| 9（最低） | 其他 | 优先丢弃 |

如果 `AGENT_CONFIG` 本身被丢弃（极端情况），会强制保留第一个系统段落。

---

## 9. 配置项汇总

| 参数 | 默认值 | 位置 | 说明 |
|------|--------|------|------|
| `max_tokens` | 100000 | `ContextConfig` | 上下文窗口上限，由 `set_model` 自动设置 |
| `compact_threshold` | 0.50 | `ContextConfig` | 触发压缩的 token 比率 |
| `codebase.enabled` | True | `CodebaseConfig` | 是否启用代码库索引 |
| `codebase.auto_retrieve` | True | `CodebaseConfig` | 是否自动检索代码上下文 |
| `codebase.retriever` | bm25 | `CodebaseConfig` | 检索器类型：bm25/embedding/hybrid |
| `codebase.top_k` | 5 | `CodebaseConfig` | 检索返回块数 |
| `codebase.max_chunk_tokens` | 500 | `CodebaseConfig` | 注入上下文的最大 token 预算 |
| `codebase.chunk_lines` | 50 | `CodebaseConfig` | 代码块行数 |
| `codebase.chunk_overlap` | 10 | `CodebaseConfig` | 代码块重叠行数 |
| `memory.enabled` | True | `MemoryConfig` | 是否启用长期记忆 |
| `memory.auto_recall` | True | `MemoryConfig` | 是否自动召回记忆 |
| `memory.top_k` | 5 | `MemoryConfig` | 召回记忆条数 |
| `agent.max_iterations` | — | `GlobalConfig` | 绝对轮次上限（安全网） |

---

## 架构关系图

```
用户输入
  │
  ▼
Engine.chat_stream()
  │
  ├── CodebaseEngine.retrieve() ────────► <!-- CODEBASE -->
  │
  ├── AgentMemory.search_memories() ────► <!-- MEMORY -->
  │
  ├── _refresh_pending_todos_nudge() ───► <!-- PENDING_TODOS -->
  │
  ├── REACT_PHASE 轮次更新 ─────────────► <!-- REACT_PHASE -->
  │
  ├── ContextManager.should_compact()
  │     └── 三级压缩管线
  │
  ├── Provider.prepare_messages()
  │     └── System 消息按优先级折叠
  │
  ▼
LLM Provider（Anthropic / OpenAI / DeepSeek / ...）
```
