---
name: ai-dlc-verify
description: "Verify Phase: TDD Red-Green-Refactor → Contract Test → Quality Gates"
triggers:
  - verify
  - TDD
  - test
  - quality-gate
---

# Verify Phase (验证)

Execute TDD per BDD scenario, verify contracts, enforce quality gates.

## Entry

See `lifecycle.md` for the full phase flow.
See `rules.md` for enforceable rules (VRF-001 to VRF-006 + INT-001 to INT-006).
See `prompt.md` for the sub-agent delegation prompt template.

## 当被委派时

0. 先调用 `TodoClear` 清除上阶段遗留的 todos，确保从空白计划开始
1. 按 DAG 顺序对每个 unit 执行 TDD Red→Green→Refactor
2. 运行合约测试 + 检查 backward-compat
3. 运行 cross-stack e2e
4. 执行质量门禁（cov≥80%, 0 vulns, no TODO）
