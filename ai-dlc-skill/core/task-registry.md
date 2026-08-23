# Task Registry — 任务状态注册表

任务状态持久化机制，防止相同 intent 重复执行已完成的 phase。
Registry 作为 `task_registry` 数组存储在 `.cdh/state.json` 中。

## 存储位置

`.cdh/state.json` — 与 sidebar 状态共用同一文件。

## 数据结构

```json
{
  "current_phase": "understand",
  "completed_phases": ["understand", "plan"],
  "gate_results": {},
  "fingerprint": "abc123...",
  "task_registry": [
    {
      "fingerprint": "24-char-hash",
      "intent": "用户输入意图摘要",
      "status": "completed",
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:30:00Z",
      "result": "任务完成描述"
    }
  ]
}
```

**Schema 字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fingerprint` | string (24 chars) | 是 | 任务唯一标识，基于 intent 生成 |
| `intent` | string | 是 | 用户意图摘要 |
| `status` | enum | 是 | `pending`/`in_progress`/`completed`/`failed` |
| `created_at` | date-time | 是 | 任务创建时间 |
| `updated_at` | date-time | 是 | 任务最后更新时间 |
| `result` | string | 否 | 任务执行结果描述 |

**顶层字段说明：**

| 字段 | 说明 |
|------|------|
| `current_phase` | 当前正在执行的 phase |
| `completed_phases` | 已完成的 phases 列表 |
| `gate_results` | 各 gate 的执行结果 |

## 操作方式

**注意：使用 CDH 的 `save_state_atomic()` API 以避免竞态条件。**

Master Agent 应通过 CDH API 操作状态，而不是直接 bash 读写：

```python
# 读取
from cdh.project_loader import CdhProjectLoader
state = CdhProjectLoader.load_project_state(cdh_dir)

# 写入（原子操作，防止竞态）
success = CdhProjectLoader.save_state_atomic(cdh_dir, state)
```

如果必须使用 bash：

```bash
# 读取
cat .cdh/state.json

# 写入（使用临时文件 + 原子替换）
python -c "
import json, tempfile, os
state = json.load(open('.cdh/state.json'))
# ... 修改 state ...
# 原子写入
tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
json.dump(state, tmp, ensure_ascii=False, indent=2)
tmp.close()
os.replace(tmp.name, '.cdh/state.json')
"
```

## Master Agent 执行流程

```
Intent 输入
  │
  ├─ 读 .cdh/state.json → 检查 task_registry 匹配
  │   ├─ found + status=completed → SKIP
  │   ├─ found + status=in_progress → 续跑
  │   └─ not found → 创建新 task 条目
  │
  ├─ 复杂度评估 → 选择 phases
  ├─ 写 .cdh/state.json: current_phase=首个phase, task_registry 新增
  │
  ├─ For each phase:
  │   ├─ TodoClear
  │   ├─ Task(agent_type="ai-dlc-{phase}", prompt=...)
  │   ├─ 收集结果 → gate 检查 → AskUser 确认
  │   └─ 写 .cdh/state.json: 追加 completed_phases, 更新 current_phase
  │
  └─ All done → task_registry[].status = "completed"
```

## 状态机

```
                  ┌─────────┐
                  │ pending │
                  └────┬────┘
                       │ 开始执行
                       ▼
                  ┌─────────┐
                  │in_progress │
                  └────┬────┘
                       │ 所有 phases 完成
                       ▼
           ┌────────────────────────┐
           │      completed        │
           └────────────────────────┘
                       │
                       │ 失败
                       ▼
                  ┌─────────┐
                  │ failed  │
                  └─────────┘
```

## Task Status

| Status | 含义 | 下一步 |
|--------|------|--------|
| `pending` | 未开始 | 开始执行 |
| `in_progress` | 执行中 | 等待完成 |
| `completed` | 已完成 | 跳过 |
| `failed` | 失败 | 重试或 abort |

## Phase 完成追踪

Phase 级别的完成状态通过顶层 `completed_phases` 数组追踪：

```json
{
  "current_phase": "verify",
  "completed_phases": ["understand", "plan"]
}
```

这意味着：
- `completed_phases` 包含已完成的 phases
- `current_phase` 是当前正在执行的 phase
- 不在 `completed_phases` 中且不等于 `current_phase` 的 phase 为 pending
