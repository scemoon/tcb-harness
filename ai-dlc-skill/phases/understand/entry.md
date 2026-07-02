---
name: ai-dlc-understand
description: "Understand Phase: Intent → Spec Delta → BDD Feature Files"
triggers:
  - understand
  - spec-delta
  - EARS
  - feature file
---

# Understand Phase (理解)

Transform business intent into formal specification and behavior scenarios.

## Entry

See `lifecycle.md` for the full phase flow.
See `rules.md` for enforceable rules (UND-001 to UND-006).
See `prompt.md` for the sub-agent delegation prompt template.

## 当被委派时

1. 读取 intent 输入
2. 按 SDD 方法生成 spec-delta（EARS 格式）
3. 为每个 FR 写 BDD feature 文件（≥3 scenarios: positive, negative, edge）
4. 输出到 `aidlc/openspec/changes/{id}/`
