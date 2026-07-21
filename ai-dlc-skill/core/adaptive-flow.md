# Adaptive Flow — 自适应流程决策

AI-DLC Master Agent 根据需求复杂度自动裁剪执行阶段。

## 复杂度分级

| 级别 | 触发条件 | 执行阶段 |
|------|---------|---------|
| L1 | 单文件 bug fix，不改行为 | Verify (TDD Red→Green→Refactor) |
| L2 | 单组件新功能，无需 INT 合约 | Understand → Verify |
| L3 | 多组件功能，需要 INT 合约 | Understand → Plan → Verify |
| L4 | 全栈新功能 + 部署 | Understand → Plan → Verify → Deliver |
| L5 | 架构重构/平台迁移 | Plan → Verify |

## ⚠️ 前置检查：Task Registry

每次处理 intent 前必须先执行注册表检查，防止重复执行：

```
task_registry = read(".opencode/plans/task-registry.json")
result = taskRegistry.check(task_registry, intent)

if result.found and result.pendingPhases is empty:
    → SKIP: 返回 "该任务已在 {time} 完成。产物: {artifacts}"
    → 不执行任何 phase

if result.found and result.pendingPhases is not empty:
    → CONTINUE: 跳过 completed phases，只执行 pending/failed phases
    
if not result.found:
    → CONTINUE: 新建任务，执行完整流程
```

详细操作见 `core/task-registry.md`。

## 决策流程

```
Intent 输入
  │
  ├─ ⚡ 1. taskRegistry.check(intent)   ← 新增：查重
  │   ├─ 已完成 → 直接返回结果，不执行
  │   └─ 部分完成 → 跳过已完成 phases
  │
  ├─ 2. 复杂度评估
  │   ├─ 是否单文件/修 bug？           → L1
  │   ├─ 是否单组件且不改合约？        → L2
  │   ├─ 是否多组件/涉及跨组件边界？   → L3
  │   ├─ 是否全栈/需要部署到生产？     → L4
  │   └─ 是否重构/不新增行为/迁移？    → L5
  │
  └─ 3. 输出 `[Lx] Phase 列表` + `taskRegistry.create()`  ← 新增
```

## 复杂度评估 Prompt

分析用户输入时，先判断以下维度：

1. **范围 (Scope)**：单文件 / 单组件 / 多组件 / 全栈
2. **类型 (Type)**：修 bug / 新功能 / 重构 / 迁移
3. **合约 (Contract)**：是否涉及 INT-FR、OpenAPI、AsyncAPI
4. **部署 (Deploy)**：是否需要上线到 production

输出格式：`[Lx] Phase 列表`，如 `[L3] understand → plan → verify`
