# Task Registry — 任务状态注册表

任务状态持久化机制，防止相同 intent 重复执行已完成的 phase。
Registry 作为 `task_registry` 数组存储在 `.cdh/state.json` 中。

## 存储位置

`.cdh/state.json` — 与 sidebar 状态共用同一文件。

## 数据结构

```json
{
  "current_phase": "understand",
  "completed_phases": [],
  "gate_results": {},
  "task_registry": [
    {
      "id": "task-{hash}",
      "intent": "用户输入意图摘要",
      "level": "L2",
      "status": "completed",
      "phases": [
        {
          "name": "understand",
          "status": "completed",
          "artifacts": ["aidlc/openspec/changes/{id}/spec-delta.md"],
          "gatePassed": true
        },
        {
          "name": "verify",
          "status": "completed",
          "artifacts": ["apps/web/src/..."],
          "gatePassed": true
        }
      ]
    }
  ]
}
```

## 操作方式

Master Agent 通过 bash 命令直接读写 `.cdh/state.json`：

```bash
# 读取
cat .cdh/state.json

# 写入（用 python 保持 JSON 格式）
python -c "
import json
s = json.load(open('.cdh/state.json'))
s['current_phase'] = 'verify'
s['completed_phases'].append('understand')
s['task_registry'].append({
  'id': 'task-xxx',
  'intent': '用户意图',
  'level': 'L2',
  'status': 'running',
  'phases': [{'name': 'understand', 'status': 'completed', 'artifacts': [...], 'gatePassed': True}]
})
json.dump(s, open('.cdh/state.json','w'), ensure_ascii=False, indent=2)
"
```

## Master Agent 执行流程

```
Intent 输入
  │
  ├─ 读 .cdh/state.json → 检查 task_registry 匹配
  │   ├─ found + all phases completed → SKIP
  │   ├─ found + partially completed → 续跑
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
                  │ 新建     │
                  └────┬────┘
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
              │  failed   │
              └───────────┘
```

## Phase 执行状态

| Status | 含义 | 下一步 |
|--------|------|--------|
| `pending` | 未开始 | 执行 |
| `running` | 执行中 | 等待完成 |
| `completed` | 已完成且 gate 通过 | 跳过 |
| `failed` | gate 未通过 | 重试或 abort |
