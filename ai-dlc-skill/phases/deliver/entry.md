---
name: ai-dlc-deliver
description: "Deliver Phase: Stack Preview → e2e → Production + BVT"
entry_point: phases/deliver/entry.md
triggers:
  - deliver
  - deploy
  - release
---

# Deliver Phase (交付)

Deploy full stack, run cross-stack e2e, human approval, production BVT.

## Lifecycle

See `lifecycle.md` for the full phase flow.
See `rules.md` for enforceable rules (DLV-001 to DLV-004 + STK-001 to STK-006).
See `prompt.md` for the sub-agent delegation prompt template.

## 当被委派时

0. 先调用 `TodoClear` 清除上阶段遗留的 todos，确保从空白计划开始
1. `aidlc/tools/deploy_stack.sh --env preview` 统一部署
2. 运行 per-component e2e + cross-stack e2e
3. Staging 部署 + smoke test
4. Human approval gate
5. Production 部署 + BVT + 自动回滚

## 产出

- `STACK_URL` / `BACKEND_URL`
- 各组件 e2e 报告
- 跨栈 e2e 报告
- Stack BVT 报告
