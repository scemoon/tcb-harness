---
name: ai-dlc-plan
description: "Plan Phase: Design Doc → Task DAG → Test Plan"
entry_point: phases/plan/entry.md
triggers:
  - plan
  - design
  - task-list
---

# Plan Phase (规划)

Convert approved spec into technical design and task decomposition.

## Lifecycle

See `lifecycle.md` for the full phase flow.
See `rules.md` for enforceable rules (PLN-001 to PLN-004).
See `prompt.md` for the sub-agent delegation prompt template.

## 当被委派时

0. 先调用 `TodoClear` 清除上阶段遗留的 todos，确保从空白计划开始
1. 读取 spec-delta 和 feature 文件
2. 生成设计文档（per-component + integration）→ `{spec_dir}/design.md`
3. 分解为带 DAG 依赖的任务单元 → `{spec_dir}/task-list.md`
4. 编写测试计划（每层）

## 产出

- `aidlc/openspec/changes/{id}/design.md`
- `aidlc/openspec/changes/{id}/task-list.md`
- `aidlc/openspec/changes/{id}/contract-diff.md`（合约变更时）
