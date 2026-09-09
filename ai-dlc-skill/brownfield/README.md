# Brownfield 存量项目支持

为已有项目自动生成语义上下文，辅助 AI Agent 理解代码库。

## 使用方式

```bash
# 一键生成 aidlc/AI-DLC-CONTEXT.md
./brownfield/generate-context.sh

# 单独步骤
./brownfield/scripts/discover.sh       # 组件发现
./brownfield/scripts/extract-api.sh    # API 表面提取
./brownfield/scripts/deps.sh           # 跨组件依赖图
```

## 产出

`aidlc/AI-DLC-CONTEXT.md` 文件包含：
1. 发现的组件列表 + 技术栈
2. API 端点摘要
3. 跨组件依赖 Mermaid 图
4. 架构速览

模板文件位于 `templates/brownfield/context.md`（用于参考格式）。

## 在 Phase 中的应用

Brownfield 是可选的第 0 阶段，在以下情况触发：
- L2+ 复杂度且有存量代码
- Master Agent 自动调用 `Task(agent_type="explore", prompt="...brownfield/scripts/...")`

Brownfield Phase 输出用于：
1. 确认 `affects` 声明的准确性
2. 发现潜在的跨组件依赖
3. 为后续 Phase 提供上下文
