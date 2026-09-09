---
name: ai-dlc-brownfield
description: "Brownfield Phase: Explore existing codebase → Generate AI-DLC Context"
entry_point: brownfield/entry.md
triggers:
  - brownfield
  - explore
  - context
---

# Brownfield Phase (存量探索)

为已有项目自动生成语义上下文，辅助 AI Agent 理解代码库。

## Lifecycle

Brownfield 是可选的第 0 阶段，在 L2+ 复杂度且有存量代码时触发。

## 当被委派时

1. 运行 `brownfield/scripts/discover.sh` 发现组件
2. 运行 `brownfield/scripts/extract-api.sh` 提取 API 表面
3. 运行 `brownfield/scripts/deps.sh` 生成跨组件依赖图
4. 运行 `brownfield/generate-context.sh` 生成 `aidlc/AI-DLC-CONTEXT.md`

## 产出

- `aidlc/AI-DLC-CONTEXT.md` — 包含：
  - 组件列表 + 技术栈
  - API 端点摘要
  - 跨组件依赖 Mermaid 图
  - 架构速览

## 在 AI-DLC 流程中的应用

Brownfield Phase 输出用于：
1. 确认 `affects` 声明的准确性
2. 发现潜在的跨组件依赖
3. 为后续 Phase 提供上下文

## 约束

- 使用 `explore` agent type 进行代码探索
- 不修改任何现有代码
- 专注于生成准确的上下文摘要
