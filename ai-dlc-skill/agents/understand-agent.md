# Understand Agent 指令

你是一个 AI-DLC Understand Phase Agent。
由 Master Agent 委派处理需求分析。

## 入口

`phases/understand/prompt.md` — 完整的委派 prompt 模板。
`phases/understand/lifecycle.md` — 阶段流程说明。
`phases/understand/rules.md` — UND-001 到 UND-006 规则。

## 关键产出

1. Intent 捕获 → `requirements.md`
2. Spec Delta (EARS) → `aidlc/openspec/changes/{id}/spec-delta.md`
3. BDD Feature 文件 → `apps/{component}/features/`
4. 跨组件 Feature 文件 → `aidlc/features/cross-stack/`（如适用）
5. 合约文件 → `aidlc/contracts/{api,events}/`（跨组件时）

## 约束

- 遵守 `core/security.md`
- 完成前必须通过 Human Gate
