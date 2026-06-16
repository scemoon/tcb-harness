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

## 决策流程

```
Intent 输入
  │
  ├─ 是否单文件/修 bug？           → L1
  ├─ 是否单组件且不改合约？        → L2
  ├─ 是否多组件/涉及跨组件边界？   → L3
  ├─ 是否全栈/需要部署到生产？     → L4
  └─ 是否重构/不新增行为/迁移？    → L5
```

## 复杂度评估 Prompt

分析用户输入时，先判断以下维度：

1. **范围 (Scope)**：单文件 / 单组件 / 多组件 / 全栈
2. **类型 (Type)**：修 bug / 新功能 / 重构 / 迁移
3. **合约 (Contract)**：是否涉及 INT-FR、OpenAPI、AsyncAPI
4. **部署 (Deploy)**：是否需要上线到 production

输出格式：`[Lx] Phase 列表`，如 `[L3] understand → plan → verify`
