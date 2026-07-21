# Task Registry — 任务状态注册表

任务状态持久化机制，防止相同 intent 重复执行已完成的 phase。

## 存储位置

`.opencode/plans/task-registry.json`

## 数据结构

```json
{
  "tasks": [
    {
      "id": "task-{hash}",              // intent 哈希标识
      "intent": "用户输入意图摘要",
      "level": "L2",                    // 复杂度级别
      "status": "completed",            // running | completed | failed
      "phases": [
        {
          "name": "understand",
          "status": "completed",
          "startedAt": 1722336000000,
          "completedAt": 1722336600000,
          "artifacts": [
            "aidlc/openspec/changes/{id}/spec-delta.md"
          ],
          "gatePassed": true
        },
        {
          "name": "verify",
          "status": "completed",
          "startedAt": 1722336600000,
          "completedAt": 1722337200000,
          "artifacts": ["apps/web/src/..."],
          "gatePassed": true
        }
      ],
      "createdAt": 1722336000000,
      "updatedAt": 1722337200000
    }
  ]
}
```

## 操作指令

### 查 — 检查任务是否已完成

```json
{
  "action": "taskRegistry.check",
  "intent": "用户输入"
}
```

返回:
- `found: true/false`
- `completedPhases: ["understand", "verify"]`
- `pendingPhases: ["plan"]`
- `level: "L2"`

> 匹配逻辑：对 intent 做语义匹配（非精确）。如果存在 status=completed 且 phases 包含所有应执行 phase，则跳过。

### 写 — 记录阶段完成

```json
{
  "action": "taskRegistry.completePhase",
  "taskId": "task-{hash}",
  "phase": "understand",
  "artifacts": ["aidlc/openspec/changes/{id}/spec-delta.md"],
  "gatePassed": true
}
```

### 写 — 创建新任务

```json
{
  "action": "taskRegistry.create",
  "intent": "用户输入",
  "level": "L2",
  "phases": ["understand", "verify"]
}
```

### 写 — 标记任务失败

```json
{
  "action": "taskRegistry.fail",
  "taskId": "task-{hash}",
  "phase": "understand",
  "error": "Human gate rejected"
}
```

## Master Agent 执行流程（含 Registry）

```
Intent 输入
  │
  ├─ taskRegistry.check(intent)
  │   ├─ found + all phases completed → SKIP（直接返回已有结果）
  │   ├─ found + partially completed → 续跑剩余 phase
  │   └─ not found → 创建新任务 → 走正常流程
  │
  ├─ 复杂度评估 → 选择 phases
  ├─ taskRegistry.create(task)  ← 新增
  │
  ├─ For each phase:
  │   ├─ check phase status from registry
  │   ├─ if completed → SKIP  ← 新增
  │   ├─ TodoClear
  │   ├─ Spawn(agent)
  │   └─ taskRegistry.completePhase(phase)  ← 新增
  │
  └─ All phases done → task complete
```

## 状态机

```
                  ┌─────────┐
                  │ 新建     │
                  └────┬────┘
                       │ taskRegistry.create()
                       ▼
                  ┌─────────┐
                  │ running │
                  └────┬────┘
                       │ 每个 phase 完成
                       ▼
          ┌────────────────────────┐
          │ phase[0..n] completed │
          └────────┬───────────────┘
                   │ 全部完成
                   ▼
              ┌───────────┐
              │ completed │
              └───────────┘
                   │
              ┌───────────┐
              │  failed   │ ← 任一 phase gate 失败
              └───────────┘
```

## Phase 执行状态

| Status | 含义 | 下一步 |
|--------|------|--------|
| `pending` | 未开始 | 执行 |
| `running` | 执行中 | 等待完成 |
| `completed` | 已完成且 gate 通过 | 跳过 |
| `failed` | gate 未通过 | Master 决定重试或 abort |

## 文件操作

Registry 文件 `.opencode/plans/task-registry.json` 由以下规则维护：

- **读取**: Master Agent 每次处理 intent 时最先读取
- **写入**: 只有 Master Agent 写入（phase agent 不直接写）
- **原子性**: 先读 → 修改内存 → 整体写回
- **并发**: 串行执行，无并发问题

## 示例

### 场景：重复提交相同 intent

```python
# 第一次执行
task_registry = read("task-registry.json")
result = check(task_registry, "实现角色管理")
# → not found

# 执行 understand → verify → complete

# 第二次相同 intent
task_registry = read("task-registry.json")
result = check(task_registry, "实现角色管理")
# → found, phase: understand=completed, verify=completed
# → SKIP, 返回 "已在 {time} 完成，产物在 {artifacts}"
```

### 场景：部分完成，续跑

```python
# 第一次：understand 完成，plan 失败
task_registry = read("task-registry.json")
result = check(task_registry, "实现角色管理")
# → found, phase: understand=completed, plan=failed
# → 跳过 understand，重跑 plan

# 第二次：重新执行 plan → verify
```
