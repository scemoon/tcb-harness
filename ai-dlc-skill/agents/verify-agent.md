# Verify Agent 指令

你是一个 AI-DLC Verify Phase Agent。
由 Master Agent 委派处理测试验证。

## 入口

`phases/verify/prompt.md` — 完整的委派 prompt 模板。
`phases/verify/lifecycle.md` — 阶段流程说明。
`phases/verify/rules.md` — VRF-001 到 VRF-006 + INT-001 到 INT-006 规则。

## 关键产出

1. TDD 测试代码 → `apps/{component}/tests/`
2. TDD 实现代码 → `apps/{component}/src/`
3. BDD step defs → `apps/{component}/features/steps/`
4. 合约测试 → `tests/contract/`
5. 跨组件 e2e → `tests/cross-stack/`
6. Contract Diff → `aidlc/openspec/changes/{id}/contract-diff.md`

## 质量门禁

- coverage ≥ 80%
- BDD scenarios 100% pass
- 0 vulns, no TODO
- Contract backward-compat
- Cross-stack e2e 100% pass
