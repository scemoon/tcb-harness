---
name: ai-dlc-verify
description: "Verify Phase: TDD Red-Green-Refactor → Contract Test → Quality Gates"
entry_point: phases/verify/entry.md
triggers:
  - verify
  - TDD
  - test
  - quality-gate
---

# Verify Phase (验证)

Execute TDD per BDD scenario, verify contracts, enforce quality gates.

## Lifecycle

See `lifecycle.md` for the full phase flow.
See `rules.md` for enforceable rules (VRF-001 to VRF-006 + INT-001 to INT-006).
See `prompt.md` for the sub-agent delegation prompt template.

## 当被委派时

0. 先调用 `TodoClear` 清除上阶段遗留的 todos，确保从空白计划开始
1. 按 DAG 顺序对每个 unit 执行 TDD Red→Green→Refactor（见 `aidlc/CONFIG.md` 测试目录）
2. 运行合约测试 + 检查 backward-compat
3. 运行 cross-stack e2e
4. 执行质量门禁（cov≥80%, 0 vulns, no TODO）

## Browser E2E Gate

当触发 Web E2E 验证时，执行 Local Browser E2E 测试：

1. **扫描测试文件**
   - 扫描 `apps/web/tests/e2e/*.spec.ts`
   - 如无测试文件，返回 `skipped`

2. **确定目标应用**
   - 读取 `apps/web/package.json` 中的端口配置
   - 默认使用 `http://localhost:8080`

3. **执行测试**
   ```bash
   cd apps/web
   npx playwright test --project=chromium
   ```

4. **返回结果**
   - 解析 Playwright JSON 报告
   - 提取 passed/failed/skipped counts

参见：[gates/browser_e2e.md](gates/browser_e2e.md)

## 产出

- 各组件的单元/集成/e2e 测试
- `aidlc/tests/contract/` 合约测试
- `aidlc/tests/cross-stack/` 跨栈测试
- `aidlc/packages/shared/` 生成的共享类型
